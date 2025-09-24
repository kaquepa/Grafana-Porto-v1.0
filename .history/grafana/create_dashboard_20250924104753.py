from curses.panel import panel
from typing import Optional, Dict, Any, List, Union
import logging
import requests, re, uuid
from dataclasses import dataclass, field
from enum import Enum
from functools import lru_cache
import json
import time
import random
from datetime import datetime, timedelta
from colorama import init, Fore, Style
import psycopg2
from psycopg2 import sql


from frontend.core.config import Config_grafana, Config_database
from create_service_account import GrafanaTokenManager
 

token_manager = GrafanaTokenManager()
api_key = token_manager.execute_workflow()

from  pathlib import Path

import sys
sys.path.insert(0, '/app')  # Adiciona o diretório raiz do projeto ao sys.path
from streaming import PortDataSimulator

logger = logging.getLogger(__name__)
init(autoreset=True)

class ThresholdColor(Enum):
    GREEN = "green"
    YELLOW = "yellow"
    RED = "red"
    BLUE = "blue"

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
    """Configuração do dashboard"""
    title: str
    uid: str
    tags: List[str] = field(default_factory=lambda: ["automated", "porto", "operacional"])
    time_from: str = "now-24h"
    time_to: str = "now"
    refresh: str = "30s"

class GrafanaAPI:
    """Cliente API do Grafana otimizado"""
    
    def __init__(self, base_url: str, api_key: str, timeout: int = 30):
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.timeout = timeout
        self.session = self._create_session()
    
    def _create_session(self) -> requests.Session:
        """Cria sessão HTTP reutilizável"""
        session = requests.Session()
        session.headers.update({
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        })
        return session
    
    def _make_request(self, method: str, endpoint: str, **kwargs) -> requests.Response:
        """Faz requisição HTTP com tratamento de erro"""
        url = f"{self.base_url}/api{endpoint}"
        try:
            response = self.session.request(method, url, timeout=self.timeout, **kwargs)
            response.raise_for_status()
            return response
        except requests.RequestException as e:
            logger.error(f"Erro na requisição {method} {endpoint}: {e}")
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"Response content: {e.response.text}")
            raise
    
    def get(self, endpoint: str, **kwargs) -> requests.Response:
        return self._make_request("GET", endpoint, **kwargs)
    
    def post(self, endpoint: str, **kwargs) -> requests.Response:
        return self._make_request("POST", endpoint, **kwargs)
    
    def put(self, endpoint: str, **kwargs) -> requests.Response:
        return self._make_request("PUT", endpoint, **kwargs)

class PanelFactory:
    """Factory para criação de painéis"""
    @staticmethod
    def create_base_panel(panel_type: str, config: PanelConfig, 
                         query: str, datasource_uid: str) -> Dict[str, Any]:
        """Cria estrutura base do painel"""
        return {
            "type": panel_type,
            "title": config.title,
            "description": config.description,
            "gridPos": {
                "x": config.x_pos,
                "y": config.y_pos,
                "w": config.width,
                "h": config.height
            },
            "targets": [{
                "datasource": {
                    "type": "postgres",
                    "uid": datasource_uid
                },
                "refId": "A",
                "rawSql": query,
                "format": "table"
            }]
        }
    @staticmethod
    def create_stat_panel(config: PanelConfig, query: str, datasource_uid: str,
                         thresholds: List[ThresholdStep] = None) -> Dict[str, Any]:
        """Cria painel do tipo stat"""
        panel = PanelFactory.create_base_panel("stat", config, query, datasource_uid)
        
        threshold_steps = thresholds or [
            ThresholdStep(ThresholdColor.GREEN.value, 0),
            ThresholdStep(ThresholdColor.RED.value, 80)
        ]
        
        panel["fieldConfig"] = {
            "defaults": {
                "color": {"mode": "thresholds"},
                "thresholds": {
                    "mode": "absolute",
                    "steps": [step.to_dict() for step in threshold_steps]
                },
                "unit": config.unit,
                "decimals": config.decimals,
                "min": config.min_val,
                "max": config.max_val
            }
        }
        
        panel["options"] = {
            "orientation": "auto",
            "reduceOptions": {
                "calcs": ["lastNotNull"],
                "fields": "",
                "values": False
            },
            "textMode": "value_and_name",
            "colorMode": "value",
            "graphMode": "area",
            "justifyMode": "center"
        }
        
        return panel
    @staticmethod
    def create_table_panel(config: PanelConfig, query: str, 
                          datasource_uid: str) -> Dict[str, Any]:
        """Cria painel de tabela"""
        panel = PanelFactory.create_base_panel("table", config, query, datasource_uid)
        
        panel["fieldConfig"] = {
            "defaults": {
                "custom": {
                    "align": "center",
                    "displayMode": "color-text", # "auto",
                    "filterable": True
                },
                "color": {
                "mode": "thresholds",          # usa thresholds para colorir
                "scheme": "green-yellow-red"   # gradiente verde-amarelo-vermelho
            }
            }
        }
        
        panel["options"] = {
            "showHeader": True,
            "footer": {"show": False},
            "cellHeight": "md"
        }
        
        return panel
class LayoutManager:
    """Gerenciador de layout do dashboard"""
    
    GRID_WIDTH = 24
    
    @staticmethod
    def get_panel_layouts() -> List[Dict[str, Any]]:
        """Define o layout dos painéis com títulos EXATOS dos painéis criados"""
        return [
            # Linha 1: estatísticas principais (24 colunas no total)
            {"title": "Eficiência Operacional",           "type": "stat", "w": 3, "h": 6, "x": 0,  "y": 0},
            {"title": "Navios atendidos",                 "type": "stat", "w": 3, "h": 6, "x": 3,  "y": 0},
            {"title": "Navios à Espera",                  "type": "stat", "w": 3, "h": 6, "x": 6,  "y": 0},
            {"title": "Cais Ocupados",                    "type": "stat", "w": 3, "h": 6, "x": 9,  "y": 0},
            {"title": "Percentagem de ocupação dos Cais", "type": "stat", "w": 3, "h": 6, "x": 12, "y": 0},
            # Painel maior para tempo de espera
            {"title": "Tempo de espera na fila",          "type": "table","w": 9, "h": 6, "x": 15, "y": 0},

            # Linha 2: tabelas maiores
            {"title": "Estado na Alfandega", "type": "table","w": 12,"h": 10,"x": 0,  "y": 14},
            {"title": "Cronograma dos Cais", "type": "table","w": 12,"h": 10,"x": 12, "y": 14}
        ]
    
    @staticmethod
    def apply_layout(panels: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Aplica layout aos painéis com correspondência exata"""
        layouts = {(layout["title"], layout["type"]): layout 
                  for layout in LayoutManager.get_panel_layouts()}
        
        applied_count = 0
        for panel in panels:
            key = (panel.get("title"), panel.get("type"))
            if key in layouts:
                layout = layouts[key]
                panel["gridPos"] = {
                    "x": layout["x"], "y": layout["y"],
                    "w": layout["w"], "h": layout["h"]
                }
                applied_count += 1
                logger.info(f"✅ Layout aplicado: {key}")
            else:
                logger.warning(f"⚠️  Layout não encontrado: {key}")
                # Layout padrão para painéis não mapeados
                panel["gridPos"] = {
                    "x": 0, "y": 100,  # Posiciona no final
                    "w": 12, "h": 8
                }
        
        logger.info(f"📊 Layouts aplicados: {applied_count}/{len(panels)}")
        return panels

class DashboardManager:
    """Gerenciador principal de dashboards"""
    
    # Thresholds predefinidos
    EFFICIENCY_THRESHOLDS = [
        ThresholdStep(ThresholdColor.RED.value, 0),
        ThresholdStep(ThresholdColor.YELLOW.value, 70),
        ThresholdStep(ThresholdColor.GREEN.value, 85)
    ]
    
    OCCUPATION_THRESHOLDS = [
        ThresholdStep(ThresholdColor.GREEN.value, 0),
        ThresholdStep(ThresholdColor.YELLOW.value, 60),
        ThresholdStep(ThresholdColor.RED.value, 80)
    ]
    
    WAITING_THRESHOLDS = [
        ThresholdStep(ThresholdColor.GREEN.value, 0),
        ThresholdStep(ThresholdColor.YELLOW.value, 3),
        ThresholdStep(ThresholdColor.RED.value, 5)
    ]
    
    def __init__(self, grafana_api: GrafanaAPI):
        self.api = grafana_api
    
    def test_database_connection(self, datasource_uid: str) -> bool:
        """Testa a conexão com o banco de dados"""
        test_query = "SELECT 1 as test"
        try:
            response = self.api.post("/ds/query", json={
                "queries": [{
                    "refId": "A",
                    "datasource": {"uid": datasource_uid},
                    "rawSql": test_query,
                    "format": "table"
                }]
            })
            
            # Verificar se a resposta é válida
            if response.status_code == 200:
                result = response.json()
                logger.info(f"✅ Conexão com banco de dados confirmada. Resposta: {result}")
                return True
            else:
                logger.error(f"❌ Erro na resposta do banco: Status {response.status_code}, Resposta: {response.text}")
                return False
                
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Erro de requisição ao testar conexão: {e}")
            return False
        except Exception as e:
            logger.error(f"❌ Erro inesperado ao testar conexão com banco: {e}")
            return False
        

    def test_datasource_health(self, datasource_uid: str) -> bool:
        """Testa a saúde do datasource via endpoint específico"""
        try:
            # Primeiro tenta o endpoint de health do datasource
            response = self.api.get(f"/datasources/uid/{datasource_uid}/health")
            
            if response.status_code == 200:
                health_data = response.json()
                logger.info(f"✅ Health check do datasource OK: {health_data}")
                return True
            else:
                logger.warning(f"⚠️ Health check falhou: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Erro no health check: {e}")
            return False
        



    @lru_cache(maxsize=32)
    def get_queries(self) -> Dict[str, str]:
        """Retorna queries do sistema - CHAVES ALINHADAS COM TÍTULOS"""
        return {
            # Títulos EXATOS dos painéis criados
            "Eficiência Operacional": """
                 SELECT
                    DATE_TRUNC('minute', start_time) + 
                    INTERVAL '3 min' * FLOOR(EXTRACT('minute' FROM start_time)::int / 3) as time,
                    'Eficiência' as metric,
                    ROUND(
                        AVG(
                            CASE 
                                WHEN planned_duration > 0 THEN 
                                    LEAST(100.0, (planned_duration::float / NULLIF(actual_duration, 0)) * 100)
                                ELSE NULL 
                            END
                        )::numeric, 1
                    ) as value
                FROM operations
                WHERE start_time >= $__timeFrom() 
                AND start_time <= $__timeTo()
                AND status = 'completed'
                GROUP BY DATE_TRUNC('minute', start_time) + 
                        INTERVAL '3 min' * FLOOR(EXTRACT('minute' FROM start_time)::int / 3)
            """,
            
            "Navios atendidos": """ 
                SELECT COUNT(*)  as " " -- total_vessels
                FROM operations 
                WHERE status = 'completed'
            """,
            


            "Navios à Espera": """
                SELECT COUNT(*) as " " -- waiting_vessels
                    FROM vessel_queue vq
                    WHERE vq.status = 'waiting'
            """,
            
        
            
            "Cais Ocupados": """
                SELECT count(*)   as " " -- occupied_berths
                FROM berths
                WHERE status = 'occupied'
            """,
            
            
            "Percentagem de ocupação dos Cais": """
                SELECT
                    ROUND(
                        (COUNT(CASE WHEN status = 'occupied' THEN 1 END) * 100.0 / NULLIF(COUNT(*), 0)), 2
                    )  as " " -- occupation_rate
                FROM berths
            """,
            
            
            "Tempo de espera na fila": """
                        SELECT
                                TO_CHAR(CAST(COALESCE(MIN(EXTRACT(EPOCH FROM (start_service_time - arrival_time))), 0) * INTERVAL '1 second' AS INTERVAL), 'HH24:MI:SS') AS min_wait_time,
                                TO_CHAR(CAST(COALESCE(AVG(EXTRACT(EPOCH FROM (start_service_time - arrival_time))), 0) * INTERVAL '1 second' AS INTERVAL), 'HH24:MI:SS') AS avg_wait_time,
                                TO_CHAR(CAST(COALESCE(MAX(EXTRACT(EPOCH FROM (start_service_time - arrival_time))), 0) * INTERVAL '1 second' AS INTERVAL), 'HH24:MI:SS') AS max_wait_time
                            FROM vessel_queue
                            WHERE status = 'completed'
                                AND start_service_time IS NOT NULL
                                AND arrival_time IS NOT NULL
                                AND start_service_time >= arrival_time;

                """,
            
            
            
            "Estado na Alfandega": """
                SELECT
                    v.vessel_name,
                    c.status,
                    TO_CHAR(c.last_update, 'YYYY-MM-DD HH24:MI:SS') AS last_update
                FROM customs_clearance as c
                JOIN vessels v ON c.vessel_id = v.vessel_id
                ORDER BY c.last_update DESC
                LIMIT 50
            """,
            
            "Cronograma dos Cais": """
                SELECT
                    b.berth_number AS berth_name,
                    v.vessel_name,
                    TO_CHAR(o.start_time, 'YYYY-MM-DD HH24:MI:SS') AS arrival_time,
                    TO_CHAR(o.end_time, 'YYYY-MM-DD HH24:MI:SS') AS departure_time,
                    o.status
                FROM operations o
                JOIN berths b ON o.berth_id = b.berth_id
                JOIN vessels v ON o.vessel_id = v.vessel_id
                WHERE o.start_time >= CURRENT_DATE
                ORDER BY b.berth_number, o.start_time
            """
        }
    
    
    def create_porto_panels(self, datasource_uid: str) -> List[Dict[str, Any]]:
        """Cria painéis com títulos CONSISTENTES para alinhamento perfeito"""
        queries = self.get_queries()
        panels = []

        # 1. Eficiência Operacional
        config = PanelConfig(
            title="Eficiência Operacional",
            width=4, height=6,
            unit="percent",
            max_val=100,
            description="Eficiência operacional do porto"
        )
        panels.append(PanelFactory.create_stat_panel(
            config, queries["Eficiência Operacional"], 
            datasource_uid, self.EFFICIENCY_THRESHOLDS
        ))


        # 2. Navios atendidos
        config = PanelConfig(
            title="Navios atendidos",
            width=8, height=4,
            description="Total de navios atendidos"
        )
        panels.append(PanelFactory.create_stat_panel(
            config, queries["Navios atendidos"], 
            datasource_uid, self.EFFICIENCY_THRESHOLDS
        ))

        # 3. Navios à Espera
        config = PanelConfig(
            title="Navios à Espera",
            width=4, height=4,
            description="Navios aguardando atracagem"
        )
        panels.append(PanelFactory.create_stat_panel(
            config, queries["Navios à Espera"],
            datasource_uid, self.WAITING_THRESHOLDS
        ))

        # 4. Cais Ocupados
        config = PanelConfig(
            title="Cais Ocupados",
            width=4, height=4,
            description="Número de cais atualmente ocupados"
        )
        panels.append(PanelFactory.create_stat_panel(
            config, queries["Cais Ocupados"],
            datasource_uid, self.OCCUPATION_THRESHOLDS
        ))

        # 5. Percentagem de ocupação dos Cais
        config = PanelConfig(
            title="Percentagem de ocupação dos Cais",
            width=4, height=4,
            unit="percent",
            max_val=100,
            description="Percentual de ocupação dos cais"
        )
        panels.append(PanelFactory.create_stat_panel(
            config, queries["Percentagem de ocupação dos Cais"],
            datasource_uid, self.OCCUPATION_THRESHOLDS
        ))

        # 6. Tempo de espera na fila
        config = PanelConfig(
            title="Tempo de espera na fila",
            width=4, height=4,
            unit= "s",  
            description="Tempo de espera dos navios"
        )
        panels.append(PanelFactory.create_table_panel(
            config, queries["Tempo de espera na fila"], 
            datasource_uid
        ))  


        # 7. Estado na Alfandega (Table)
        config = PanelConfig(
            title="Estado na Alfandega",
            width=12, height=10,
            description="Status dos processos alfandegários"
        )
        panels.append(PanelFactory.create_table_panel(
            config, queries["Estado na Alfandega"], datasource_uid
        ))

        # 8. Cronograma dos Cais (Table)
        config = PanelConfig(
            title="Cronograma dos Cais",
            width=12, height=10,
            description="Programação de uso dos cais"
        )
        panels.append(PanelFactory.create_table_panel(
            config, queries["Cronograma dos Cais"], datasource_uid
        ))

        logger.info(f"📊 Criados {len(panels)} painéis")
        return panels
    
    def dashboard_exists(self, uid: str) -> bool:
        """Verifica se dashboard existe"""
        try:
            self.api.get(f"/dashboards/uid/{uid}")
            return True
        except requests.HTTPError as e:
            if e.response.status_code == 404:
                return False
            raise
    
    def create_datasource_if_not_exists(self, datasource_config: Dict[str, Any]) -> str:
        """Cria datasource se não existir"""
        uid = datasource_config["uid"]
        
        try:
            response = self.api.get(f"/datasources/uid/{uid}")
            logger.info(f"✅ Datasource {uid} já existe")
            
            if self.test_database_connection(uid):
                return uid
            else:
                logger.warning("⚠️ Datasource existe mas conexão falhou")
                
        except requests.HTTPError as e:
            if e.response.status_code != 404:
                raise
        
        try:
            logger.info(f"📡 Criando datasource {uid}...")
            response = self.api.post("/datasources", json=datasource_config)
            logger.info(f"✅ Datasource {uid} criado com sucesso")
            
            time.sleep(2)  # Aguarda datasource estar pronto
            
            if self.test_database_connection(uid):
                return uid
            else:
                logger.error("❌ Datasource criado mas conexão falhou")
                
        except Exception as e:
            logger.error(f"❌ Erro ao criar datasource: {e}")
            raise
        
        return uid
    
    def create_or_update_dashboard(self, config: DashboardConfig, 
                                  panels: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Cria ou atualiza dashboard com layout aplicado"""
        # Aplicar layout ANTES de enviar
        panels_with_layout = LayoutManager.apply_layout(panels)
        
        dashboard_payload = {
            "dashboard": {
                "uid": config.uid,
                "title": config.title,
                "tags": config.tags,
                "timezone": "browser",
                "panels": panels_with_layout,
                "time": {
                    "from": config.time_from,
                    "to": config.time_to
                },
                "refresh": config.refresh,
                "schemaVersion": 30,
                "version": 0,
                "editable": True
            },
            "overwrite": True,
            "message": f"Dashboard atualizado em {datetime.now().isoformat()}"
        }
        
        try:
            response = self.api.post("/dashboards/db", json=dashboard_payload)
            result = response.json()
            logger.info(f"✅ Dashboard '{config.title}' criado/atualizado com sucesso")
            return result
        except Exception as e:
            logger.error(f"❌ Erro ao criar/atualizar dashboard: {e}")
            raise


def execute():
    """Função principal"""
    
    logger.info("🚀 Iniciando configuração do Dashboard do Porto...")
    
    # Verificar banco de dados primeiro
    logger.info("🔍 Verificando configuração do banco de dados...")    
    # Configurações
    GRAFANA_CONFIG = {
        "base_url": Config_grafana.URL,
        "api_key": api_key
    }
    
    # Configuração do datasource corrigida
    DATASOURCE_CONFIG = {
        "uid": "postgres-porto-uid",
        "name": "PostgreSQL Porto",
        "type": "postgres",
        "access": "proxy",
        "url": f"{Config_database.HOST}:{Config_database.PORT}",
        "database": Config_database.DATABASE,
        "user": Config_database.USER,
        "secureJsonData": {
            "password": Config_database.PASSWORD
        },
        "jsonData": {
            "sslmode": "disable",
            "postgresVersion": 1200,
            "maxOpenConns": 100,
            "maxIdleConns": 100,
            "maxIdleConnsAuto": True,
            "connMaxLifetime": 14400,
            "timescaledb": False
        },
        "isDefault": False,
        "readOnly": False
    }
    
    try:
        # Inicializar API
        logger.info("🔗 Conectando ao Grafana...")
        api = GrafanaAPI(
            GRAFANA_CONFIG["base_url"],
            GRAFANA_CONFIG["api_key"]
        )
        
        # Criar gerenciador
        manager = DashboardManager(api)
        
        # Criar datasource
        logger.info("📊 Configurando datasource...")
        datasource_uid = manager.create_datasource_if_not_exists(DATASOURCE_CONFIG)
        
        # Criar painéis
        logger.info("📈 Criando painéis do dashboard...")
        panels = manager.create_porto_panels(datasource_uid)
        
        # Configurar dashboard
        dashboard_config = DashboardConfig(
            title="Dashboard Operacional do Porto",
            uid="Porto",
            time_from="now-7d",
            refresh="10s"
        )
        
        # Criar dashboard
        logger.info("🎯 Criando dashboard...")
        result = manager.create_or_update_dashboard(dashboard_config, panels)
        
        print("\n" + "="*60)
        print("🎉 CONFIGURAÇÃO CONCLUÍDA COM SUCESSO!")
        print("="*60)
        print(f"📊 Dashboard: {dashboard_config.title}")
        print(f"🔗 URL: {GRAFANA_CONFIG['base_url']}/d/{dashboard_config.uid}")
        print(f"🔄 Refresh: {dashboard_config.refresh}")
        print(f"📅 Período: {dashboard_config.time_from} até {dashboard_config.time_to}")
        print("="*60)
        
    except Exception as e:
        logger.error(f"❌ Erro na execução: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    execute() #exit(execute())
    simulator = PortDataSimulator()
    simulator.run_simulation()    
    
 