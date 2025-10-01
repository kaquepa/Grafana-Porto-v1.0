from typing import Optional, Dict, Any, List, Union
import logging
import requests
from dataclasses import dataclass, field
from enum import Enum
from functools import lru_cache
import time
from datetime import datetime

from frontend.core.config import Config_grafana, Config_database
from create_service_account import GrafanaTokenManager

import sys
sys.path.insert(0, '/app')
from streaming import PortDataSimulator

logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class ThresholdColor(Enum):
    GREEN = "green"
    YELLOW = "yellow"
    RED = "red"

@dataclass
class ThresholdStep:
    color: str
    value: Optional[Union[int, float]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {"color": self.color, "value": self.value}

@dataclass
class PanelConfig:
    title: str
    width: int = 8
    height: int = 6
    x_pos: int = 0
    y_pos: int = 0
    description: str = ""
    unit: str = "none"
    decimals: int = 0
    min_val: Optional[Union[int, float]] = 0
    max_val: Optional[Union[int, float]] = None

@dataclass
class DashboardConfig:
    title: str
    uid: str
    tags: List[str] = field(default_factory=lambda: ["automated", "porto", "operacional"])
    time_from: str = "now-24h"
    time_to: str = "now"
    refresh: str = "30s"

class GrafanaAPI:
    """Cliente API do Grafana com session reutilizável"""
    
    def __init__(self, base_url: str, api_key: str, timeout: int = 30):
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        })
    
    def _request(self, method: str, endpoint: str, **kwargs) -> requests.Response:
        url = f"{self.base_url}/api{endpoint}"
        try:
            response = self.session.request(method, url, timeout=self.timeout, **kwargs)
            response.raise_for_status()
            return response
        except requests.RequestException as e:
            logger.error(f"Erro {method} {endpoint}: {e}")
            if hasattr(e, 'response') and e.response:
                logger.error(f"Response: {e.response.text}")
            raise
    
    def get(self, endpoint: str, **kwargs) -> requests.Response:
        return self._request("GET", endpoint, **kwargs)
    
    def post(self, endpoint: str, **kwargs) -> requests.Response:
        return self._request("POST", endpoint, **kwargs)

class PanelFactory:
    """Factory para criação de painéis"""
    
    @staticmethod
    def _base_panel(panel_type: str, config: PanelConfig, query: str, ds_uid: str) -> Dict[str, Any]:
        return {
            "type": panel_type,
            "title": config.title,
            "description": config.description,
            "gridPos": {"x": config.x_pos, "y": config.y_pos, "w": config.width, "h": config.height},
            "targets": [{
                "datasource": {"type": "postgres", "uid": ds_uid},
                "refId": "A",
                "rawSql": query,
                "format": "table"
            }]
        }
    
    @staticmethod
    def stat_panel(config: PanelConfig, query: str, ds_uid: str, thresholds: List[ThresholdStep]) -> Dict[str, Any]:
        panel = PanelFactory._base_panel("stat", config, query, ds_uid)
        panel["fieldConfig"] = {
            "defaults": {
                "color": {"mode": "thresholds"},
                "thresholds": {"mode": "absolute", "steps": [s.to_dict() for s in thresholds]},
                "unit": config.unit,
                "decimals": config.decimals,
                "min": config.min_val,
                "max": config.max_val
            }
        }
        panel["options"] = {
            "orientation": "auto",
            "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
            "textMode": "value_and_name",
            "colorMode": "value",
            "graphMode": "area",
            "justifyMode": "center"
        }
        return panel
    
    @staticmethod
    def table_panel(config: PanelConfig, query: str, ds_uid: str) -> Dict[str, Any]:
        panel = PanelFactory._base_panel("table", config, query, ds_uid)
        panel["fieldConfig"] = {
            "defaults": {
                "custom": {"align": "center", "displayMode": "color-text", "filterable": True},
                "color": {"mode": "thresholds", "scheme": "green-yellow-red"}
            }
        }
        panel["options"] = {"showHeader": True, "footer": {"show": False}, "cellHeight": "md"}
        return panel

class LayoutManager:
    """Gerenciador de layout - define posições dos painéis"""
    
    LAYOUTS = [
        {"title": "Eficiência Operacional", "type": "stat", "w": 3, "h": 6, "x": 0, "y": 0},
        {"title": "Navios atendidos", "type": "stat", "w": 3, "h": 6, "x": 3, "y": 0},
        {"title": "Navios à Espera", "type": "stat", "w": 3, "h": 6, "x": 6, "y": 0},
        {"title": "Cais Ocupados", "type": "stat", "w": 3, "h": 6, "x": 9, "y": 0},
        {"title": "Percentagem de ocupação dos Cais", "type": "stat", "w": 3, "h": 6, "x": 12, "y": 0},
        {"title": "Tempo de espera na fila", "type": "table", "w": 9, "h": 6, "x": 15, "y": 0},
        {"title": "Estado na Alfandega", "type": "table", "w": 12, "h": 10, "x": 0, "y": 14},
        {"title": "Cronograma dos Cais", "type": "table", "w": 12, "h": 10, "x": 12, "y": 14}
    ]
    
    @classmethod
    def apply(cls, panels: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        layout_map = {(l["title"], l["type"]): l for l in cls.LAYOUTS}
        
        for panel in panels:
            key = (panel.get("title"), panel.get("type"))
            layout = layout_map.get(key)
            
            if layout:
                panel["gridPos"] = {"x": layout["x"], "y": layout["y"], "w": layout["w"], "h": layout["h"]}
            else:
                logger.warning(f"Layout não encontrado para: {key}")
                panel["gridPos"] = {"x": 0, "y": 100, "w": 12, "h": 8}
        
        return panels

class DashboardManager:
    """Gerenciador principal de dashboards"""
    
    # Thresholds reutilizáveis
    THRESHOLDS = {
        "efficiency": [
            ThresholdStep(ThresholdColor.RED.value, 0),
            ThresholdStep(ThresholdColor.YELLOW.value, 70),
            ThresholdStep(ThresholdColor.GREEN.value, 85)
        ],
        "occupation": [
            ThresholdStep(ThresholdColor.GREEN.value, 0),
            ThresholdStep(ThresholdColor.YELLOW.value, 60),
            ThresholdStep(ThresholdColor.RED.value, 80)
        ],
        "waiting": [
            ThresholdStep(ThresholdColor.GREEN.value, 0),
            ThresholdStep(ThresholdColor.YELLOW.value, 3),
            ThresholdStep(ThresholdColor.RED.value, 5)
        ]
    }
    
    def __init__(self, api: GrafanaAPI):
        self.api = api
            
    def test_datasource(self, uid: str):
        """Testa a conexão do datasource via API Grafana"""
        try:
            response = self.api.post(f"/api/datasources/uid/{uid}/test")
            if response.status_code == 200:
                logger.info(f"Datasource {uid} está funcionando: {response.json()}")
            else:
                logger.error(f"Falha ao testar datasource {uid}: {response.text}")
        except Exception as e:
            logger.error(f"Erro ao testar datasource {uid}: {e}")
    def _get_or_create_datasource(self, uid: str, api_key: str) -> str:
        """
        Verifica se o datasource existe no Grafana.
        Se não existir, cria. Sempre define como default.
        """
        config = {
            "uid": uid,
            "name": "grafana-postgresql-datasource",
            "type": "postgres",
            "access": "proxy",
            "url": f"{Config_database.HOST}:{Config_database.PORT}",
            "database": Config_database.DATABASE,
            "user": Config_database.USER,
            "secureJsonData": {"password": Config_database.PASSWORD},
            "jsonData": {
                "sslmode": "disable",
                "postgresVersion": 1200,
                "maxOpenConns": 100,
                "maxIdleConns": 100,
                "connMaxLifetime": 14400
            },
            "isDefault": True
        }

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        # 1️⃣ Tenta buscar datasource existente - CORRIGIDO
        response = self.api.get(f"/datasources/uid/{uid}", headers=headers)  # Removido /api duplicado
        if response.status_code == 200:
            data = response.json()
            ds_id = data["id"]  # id numérico
            logger.info(f"Datasource {uid} existe, atualizando para default...")
            # CORRIGIDO aqui também
            self.api.put(f"/datasources/{ds_id}", json=config, headers=headers)
            self.test_datasource(uid)
            return uid
        elif response.status_code != 404:
            logger.error(f"Erro ao buscar datasource {uid}: {response.status_code} {response.text}")
            response.raise_for_status()

        # 2️⃣ Cria datasource se não existir - CORRIGIDO
        response = self.api.post("/datasources", json=config, headers=headers)  # Removido /api duplicado
        if response.status_code in [200, 201]:
            logger.info(f"Datasource {uid} criado com sucesso e definido como default")
            self.test_datasource(uid)
            return uid
        else:
            logger.error(f"Falha ao criar datasource: {response.status_code} {response.text}")
            response.raise_for_status()
    def get_or_create_datasource(self, uid: str, api_key: str, retries: int = 10, delay: int = 3) -> str:
        """
        Verifica se o datasource existe no Grafana. Se não existir, cria.
        Sempre define como default. Faz retry enquanto o Grafana não estiver pronto.
        
        :param uid: UID do datasource
        :param api_key: API Key com permissões de admin
        :param retries: Número máximo de tentativas
        :param delay: Tempo (em segundos) entre tentativas
        :return: UID do datasource
        """
        config = {
            "uid": uid,
            "name": "grafana-postgresql-datasource",
            "type": "postgres",
            "access": "proxy",
            "url": f"{Config_database.HOST}:{Config_database.PORT}",
            "database": Config_database.DATABASE,
            "user": Config_database.USER,
            "secureJsonData": {"password": Config_database.PASSWORD},
            "jsonData": {
                "sslmode": "disable",
                "postgresVersion": 1500,
                "maxOpenConns": 100,
                "maxIdleConns": 100,
                "connMaxLifetime": 14400
            },
            "isDefault": True
        }

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        for attempt in range(1, retries + 1):
            try:
                # 1️⃣ Tenta buscar datasource existente
                response = self.api.get(f"/datasources/uid/{uid}", headers=headers)
                if response.status_code == 200:
                    ds_id = response.json()["id"]
                    logger.info(f"Datasource {uid} existe, atualizando para default...")
                    self.api.put(f"/datasources/{ds_id}", json=config, headers=headers)
                    self.test_datasource(uid)
                    return uid
                elif response.status_code == 404:
                    # 2️⃣ Cria datasource se não existir
                    response = self.api.post("/datasources", json=config, headers=headers)
                    if response.status_code in [200, 201]:
                        logger.info(f"Datasource {uid} criado com sucesso e definido como default")
                        self.test_datasource(uid)
                        return uid
                    else:
                        logger.warning(f"Tentativa {attempt}: falha ao criar datasource: {response.status_code} {response.text}")
                else:
                    logger.warning(f"Tentativa {attempt}: erro ao buscar datasource: {response.status_code} {response.text}")
            except Exception as e:
                logger.warning(f"Tentativa {attempt}: erro ao conectar com Grafana: {e}")

            logger.info(f"Aguardando {delay} segundos antes de tentar novamente...")
            time.sleep(delay)

        raise RuntimeError(f"Não foi possível criar/atualizar o datasource {uid} após {retries} tentativas")


    @lru_cache(maxsize=1)
    def get_queries(self) -> Dict[str, str]:
        """Queries SQL - cached para evitar recriação"""
        return {
            "Eficiência Operacional": """
                SELECT
                    DATE_TRUNC('minute', start_time) + INTERVAL '3 min' * FLOOR(EXTRACT('minute' FROM start_time)::int / 3) as time,
                    ROUND(AVG(CASE WHEN planned_duration > 0 THEN LEAST(100.0, (planned_duration::float / NULLIF(actual_duration, 0)) * 100) ELSE NULL END)::numeric, 1) as value
                FROM operations
                WHERE start_time >= $__timeFrom() AND start_time <= $__timeTo() AND status = 'completed'
                GROUP BY 1
            """,
            "Navios atendidos": "SELECT COUNT(*) as \" \" FROM operations WHERE status = 'completed'",
            "Navios à Espera": "SELECT COUNT(*) as \" \" FROM vessel_queue WHERE status = 'waiting'",
            "Cais Ocupados": "SELECT COUNT(*) as \" \" FROM berths WHERE status = 'occupied'",
            "Percentagem de ocupação dos Cais": """
                SELECT ROUND((COUNT(CASE WHEN status = 'occupied' THEN 1 END) * 100.0 / NULLIF(COUNT(*), 0)), 2) as \" \"
                FROM berths
            """,
            "Tempo de espera na fila": """
                SELECT
                    TO_CHAR(CAST(COALESCE(MIN(EXTRACT(EPOCH FROM (start_service_time - arrival_time))), 0) * INTERVAL '1 second' AS INTERVAL), 'HH24:MI:SS') AS min_wait_time,
                    TO_CHAR(CAST(COALESCE(AVG(EXTRACT(EPOCH FROM (start_service_time - arrival_time))), 0) * INTERVAL '1 second' AS INTERVAL), 'HH24:MI:SS') AS avg_wait_time,
                    TO_CHAR(CAST(COALESCE(MAX(EXTRACT(EPOCH FROM (start_service_time - arrival_time))), 0) * INTERVAL '1 second' AS INTERVAL), 'HH24:MI:SS') AS max_wait_time
                FROM vessel_queue
                WHERE status = 'completed' AND start_service_time IS NOT NULL AND arrival_time IS NOT NULL AND start_service_time >= arrival_time
            """,
            "Estado na Alfandega": """
                SELECT v.vessel_name, c.status, TO_CHAR(c.last_update, 'YYYY-MM-DD HH24:MI:SS') AS last_update
                FROM customs_clearance c
                JOIN vessels v ON c.vessel_id = v.vessel_id
                ORDER BY c.last_update DESC LIMIT 50
            """,
            "Cronograma dos Cais": """
                SELECT b.berth_number AS berth_name, v.vessel_name,
                    TO_CHAR(o.start_time, 'YYYY-MM-DD HH24:MI:SS') AS arrival_time,
                    TO_CHAR(o.end_time, 'YYYY-MM-DD HH24:MI:SS') AS departure_time, o.status
                FROM operations o
                JOIN berths b ON o.berth_id = b.berth_id
                JOIN vessels v ON o.vessel_id = v.vessel_id
                WHERE o.start_time >= CURRENT_DATE
                ORDER BY b.berth_number, o.start_time
            """
        }
    
    def create_panels(self, ds_uid: str) -> List[Dict[str, Any]]:
        """Cria todos os painéis do dashboard"""
        queries = self.get_queries()
        panels = []        
        # Configurações dos painéis (título, tipo, thresholds)
        panel_configs = [
            ("Eficiência Operacional", "stat", {"unit": "percent", "max_val": 100}, "efficiency"),
            ("Navios atendidos", "stat", {}, "efficiency"),
            ("Navios à Espera", "stat", {}, "waiting"),
            ("Cais Ocupados", "stat", {}, "occupation"),
            ("Percentagem de ocupação dos Cais", "stat", {"unit": "percent", "max_val": 100}, "occupation"),
            ("Tempo de espera na fila", "table", {"unit": "s"}, None),
            ("Estado na Alfandega", "table", {}, None),
            ("Cronograma dos Cais", "table", {}, None)
        ]
        
        for title, ptype, extra_config, threshold_key in panel_configs:
            config = PanelConfig(title=title, **extra_config)
            
            if ptype == "stat":
                panels.append(PanelFactory.stat_panel(config, queries[title], ds_uid, self.THRESHOLDS[threshold_key]))
            else:
                panels.append(PanelFactory.table_panel(config, queries[title], ds_uid))
        
        logger.info(f"Criados {len(panels)} painéis")
        return panels
    
    def create_dashboard(self, config: DashboardConfig, panels: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Cria ou atualiza dashboard"""
        panels = LayoutManager.apply(panels)
        
        payload = {
            "dashboard": {
                "uid": config.uid,
                "title": config.title,
                "tags": config.tags,
                "timezone": "browser",
                "panels": panels,
                "time": {"from": config.time_from, "to": config.time_to},
                "refresh": config.refresh,
                "schemaVersion": 30,
                "editable": True
            },
            "overwrite": True,
            "message": f"Dashboard atualizado em {datetime.now().isoformat()}"
        }
        
        response = self.api.post("/dashboards/db", json=payload)
        logger.info(f"Dashboard '{config.title}' criado/atualizado")
        return response.json()

def execute():
    """Função principal"""
    logger.info("Iniciando configuração do Dashboard...")
    
    # Gera token
    token_manager = GrafanaTokenManager()
    api_key = token_manager.execute_workflow()
    
    # Conecta ao Grafana
    api = GrafanaAPI(Config_grafana.URL, api_key)
    manager = DashboardManager(api)
    
    # Datasource (provisioned ou cria novo)
    ds_uid = manager.get_or_create_datasource("postgres-porto-uid", api_key)
    
    # Cria painéis e dashboard
    panels = manager.create_panels(ds_uid)
    config = DashboardConfig(title="Dashboard Operacional do Porto", uid="Porto", time_from="now-7d", refresh="10s")
    manager.create_dashboard(config, panels)
    
    print(f"\n{'='*60}")
    print("CONFIGURAÇÃO CONCLUÍDA")
    print(f"Dashboard: {config.title}")
    print(f"URL: {Config_grafana.URL}/d/{config.uid}")
    print(f"{'='*60}\n")
    
    return 0

if __name__ == "__main__":
    execute()
    simulator = PortDataSimulator()
    simulator.run_simulation()