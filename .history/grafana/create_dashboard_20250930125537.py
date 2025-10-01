from typing import Dict, Any, List, Union, Optional
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
    """Cliente API do Grafana simples"""
    
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
            raise
    
    def get(self, endpoint: str, **kwargs) -> requests.Response:
        return self._request("GET", endpoint, **kwargs)
    
    def post(self, endpoint: str, **kwargs) -> requests.Response:
        return self._request("POST", endpoint, **kwargs)
    
    def delete(self, endpoint: str, **kwargs) -> requests.Response:
        return self._request("DELETE", endpoint, **kwargs)
    
    def put(self, endpoint: str, **kwargs) -> requests.Response:
        return self._request("PUT", endpoint, **kwargs)

class PanelFactory:
    """Factory para criação de painéis SIMPLES"""
    
    @staticmethod
    def _base_panel(panel_type: str, config: PanelConfig, query: str, ds_uid: str) -> Dict[str, Any]:
        return {
            "type": panel_type,
            "title": config.title,
            "description": config.description,
            "gridPos": {"x": config.x_pos, "y": config.y_pos, "w": config.width, "h": config.height},
            "datasource": {"type": "postgres", "uid": ds_uid},
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
    """Gerenciador de layout simples"""
    
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
        
        return panels

class DashboardManager:
    """Gerenciador SIMPLES de dashboards"""
    
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

    def create_datasource(self, uid: str) -> str:
        """Método SIMPLES para criar datasource"""
        datasource_config = {
            "name": "PostgreSQL-Porto-Operacional",
            "type": "postgres", 
            "uid": uid,
            "access": "proxy",
            "url": f"{Config_database.HOST}:{Config_database.PORT}",
            "database": Config_database.DATABASE,
            "user": Config_database.USER,
            "isDefault": True,
            "secureJsonData": {
                "password": Config_database.PASSWORD
            },
            "jsonData": {
                "sslmode": "disable",
                "postgresVersion": 1500
            }
        }
        
        try:
            # Remove existente se houver
            try:
                self.api.delete(f"/datasources/uid/{uid}")
                time.sleep(1)
            except:
                pass
            
            # Cria novo
            response = self.api.post("/datasources", json=datasource_config)
            
            if response.status_code in [200, 201]:
                logger.info("✅ Datasource criado")
                time.sleep(3)
                return uid
            else:
                logger.error(f"❌ Erro: {response.text}")
                return uid
                
        except Exception as e:
            logger.error(f"💥 Erro: {e}")
            return uid

    @lru_cache(maxsize=1)
    def get_queries(self) -> Dict[str, str]:
        """Queries SQL"""
        return {
            "Eficiência Operacional": "SELECT 85.5 as value",
            "Navios atendidos": "SELECT COUNT(*) as value FROM operations WHERE status = 'completed'",
            "Navios à Espera": "SELECT COUNT(*) as value FROM vessel_queue WHERE status = 'waiting'",
            "Cais Ocupados": "SELECT COUNT(*) as value FROM berths WHERE status = 'occupied'",
            "Percentagem de ocupação dos Cais": "SELECT 65.2 as value",
            "Tempo de espera na fila": "SELECT '00:25:30' as avg_wait_time, '01:15:45' as max_wait_time",
            "Estado na Alfandega": "SELECT 'Navio A' as vessel_name, 'Aprovado' as status, NOW() as last_update",
            "Cronograma dos Cais": "SELECT 'Cais 1' as berth_name, 'Navio X' as vessel_name, NOW() as start_time, NOW() + INTERVAL '2 hours' as end_time"
        }
    
    def create_panels(self, ds_uid: str) -> List[Dict[str, Any]]:
        """Cria painéis"""
        queries = self.get_queries()
        panels = []
        
        panel_configs = [
            ("Eficiência Operacional", "stat", {"unit": "percent", "max_val": 100}, "efficiency"),
            ("Navios atendidos", "stat", {}, "efficiency"),
            ("Navios à Espera", "stat", {}, "waiting"),
            ("Cais Ocupados", "stat", {}, "occupation"),
            ("Percentagem de ocupação dos Cais", "stat", {"unit": "percent", "max_val": 100}, "occupation"),
            ("Tempo de espera na fila", "table", {}, None),
            ("Estado na Alfandega", "table", {}, None),
            ("Cronograma dos Cais", "table", {}, None)
        ]
        
        for title, ptype, extra_config, threshold_key in panel_configs:
            config = PanelConfig(title=title, **extra_config)
            
            if ptype == "stat":
                thresholds = self.THRESHOLDS.get(threshold_key, [])
                panels.append(PanelFactory.stat_panel(config, queries[title], ds_uid, thresholds))
            else:
                panels.append(PanelFactory.table_panel(config, queries[title], ds_uid))
        
        logger.info(f"Criados {len(panels)} painéis")
        return panels
    
    def create_dashboard(self, config: DashboardConfig, panels: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Cria dashboard"""
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
                "schemaVersion": 36,
                "editable": True
            },
            "overwrite": True,
            "message": f"Dashboard criado em {datetime.now().isoformat()}"
        }
        
        response = self.api.post("/dashboards/db", json=payload)
        logger.info(f"Dashboard '{config.title}' criado")
        return response.json()

def execute():
    """Função principal SIMPLES"""
    logger.info("🚀 Iniciando configuração...")
    
    try:
        # Gera token
        token_manager = GrafanaTokenManager()
        api_key = token_manager.execute_workflow()
        
        # Conecta ao Grafana
        api = GrafanaAPI(Config_grafana.URL, api_key)
        manager = DashboardManager(api)
        
        # Cria datasource
        logger.info("🔌 Criando datasource...")
        ds_uid = manager.create_datasource("postgres-porto-uid")
        ###-----------------------------
        ###-----------------------------
        
        # Cria dashboard
        logger.info("📊 Criando dashboard...")
        panels = manager.create_panels(ds_uid)
        config = DashboardConfig(
            title="Dashboard Operacional do Porto", 
            uid="Porto", 
            time_from="now-7d", 
            refresh="30s"
        )
        
        result = manager.create_dashboard(config, panels)
        
        logger.info(f"\n{'='*60}")
        logger.info("🎉 CONFIGURAÇÃO CONCLUÍDA!")
        logger.info(f"📊 Dashboard: {Config_grafana.URL}/d/Porto")
        logger.info("💡 Os dados devem aparecer automaticamente")
        logger.info(f"{'='*60}\n")
        
        return 0
        
    except Exception as e:
        logger.error(f"💥 Erro: {e}")
        return 1

if __name__ == "__main__":
    exit_code = execute()
    if exit_code == 0:
        logger.info("🎯 Iniciando simulação de dados...")
        simulator = PortDataSimulator()
        simulator.run_simulation()
    else:
        logger.error("❌ Configuração falhou")
        sys.exit(exit_code)