from typing import Optional, Dict, Any, List, Union
import logging
import requests
import uuid
 
from dataclasses import dataclass, field
from enum import Enum
from functools import lru_cache
import json
import time
import random
from datetime import datetime, timedelta
from colorama import init, Fore, Style
from tabulate import tabulate
import psycopg2
 
from psycopg2 import sql

from app.core.config import Config_grafana, Config_database
from create_service_account import GrafanaTokenManager

token_manager = GrafanaTokenManager()
api_key = token_manager.execute_workflow()

from  pathlib import Path

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
    def create_timeseries_panel(config: PanelConfig, query: str, 
                               datasource_uid: str, color: str = "blue") -> Dict[str, Any]:
        """Cria painel de série temporal"""
        panel = PanelFactory.create_base_panel("timeseries", config, query, datasource_uid)
        panel["targets"][0]["format"] = "time_series"
        
        panel["fieldConfig"] = {
            "defaults": {
                "color": {"mode": "fixed", "fixedColor": color},
                "custom": {
                    "drawStyle": "line",
                    "lineInterpolation": "linear",
                    "lineWidth": 2,
                    "fillOpacity": 10,
                    "showPoints": "auto",
                    "pointSize": 5
                },
                "unit": config.unit,
                "decimals": config.decimals,
                "min": config.min_val,
                "max": config.max_val
            }
        }
        
        panel["options"] = {
            "tooltip": {"mode": "single"},
            "legend": {
                "showLegend": True,
                "displayMode": "table",
                "placement": "bottom"
            }
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
                    "displayMode": "auto",
                    "filterable": True
                }
            }
        }
        
        panel["options"] = {
            "showHeader": True,
            "footer": {"show": False},
            "cellHeight": "md"
        }
        
        return panel



    @staticmethod
    def create_pie_panel(config: PanelConfig, query: str,
                        datasource_uid: str) -> Dict[str, Any]:
        """Cria painel de pie chart"""
        panel = PanelFactory.create_base_panel("piechart", config, query, datasource_uid)
        
        # Configurações de exibição
        panel["fieldConfig"] = {
            "defaults": {
                "custom": {},
                "unit": "short",   # Pode trocar por "percent" se quiser %
                "decimals": 0
            },
            "overrides": []
        }
        
        panel["options"] = {
            "legend": {
                "displayMode": "table",   # ou "list"
                "placement": "right"      # left, right, bottom
            },
            "reduceOptions": {
                "values": False,
                "calcs": ["lastNotNull"]
            },
            "pieType": "pie",             # "pie" ou "donut"
            "displayLabels": ["name", "percent"]  # mostra nome e %
        }
        
        return panel




class LayoutManager:
    """Gerenciador de layout do dashboard"""
    
    GRID_WIDTH = 24
    
    @staticmethod
    def get_panel_layouts() -> List[Dict[str, Any]]:
        """Define o layout dos painéis de forma proporcional e harmoniosa"""
        return [
        # Linha 1: Painéis de estatísticas principais (6 painéis lado a lado)
        {"title": "Eficiência Operacional", "type": "stat", "w": 4, "h": 6, "x": 0,  "y": 0},
        {"title": "Navios à Espera",         "type": "stat", "w": 4, "h": 6, "x": 4,  "y": 0},
        {"title": "Cais Ocupados",           "type": "stat", "w": 4, "h": 6, "x": 8,  "y": 0},
        {"title": "Percentagem de Ocupação", "type": "stat", "w": 4, "h": 6, "x": 12, "y": 0},
        {"title": "Tempo Médio na Fila",     "type": "stat", "w": 4, "h": 6, "x": 16, "y": 0},
        {"title": "Estatísticas dos Cais",   "type": "piechart", "w": 4, "h": 6, "x": 20, "y": 0},

        # Linha 2: Operações de Importação e Exportação lado a lado
        {"title": "Importação", "type": "timeseries", "w": 12, "h": 8, "x": 0,  "y": 6},
        {"title": "Exportação", "type": "timeseries", "w": 12, "h": 8, "x": 12, "y": 6},

        # Linha 3: Estados da Alfândega e Cronograma dos Cais lado a lado
        {"title": "Estado na Alfândega", "type": "table", "w": 12, "h": 10, "x": 0,  "y": 14},
        {"title": "Cronograma dos Cais", "type": "table", "w": 12, "h": 10, "x": 12, "y": 14}
    ]
    
    @staticmethod
    def apply_layout(panels: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Aplica layout aos painéis"""
        layouts = {(layout["title"], layout["type"]): layout 
                  for layout in LayoutManager.get_panel_layouts()}
        
        for panel in panels:
            key = (panel.get("title"), panel.get("type"))
            if key in layouts:
                layout = layouts[key]
                panel["gridPos"] = {
                    "x": layout["x"], "y": layout["y"],
                    "w": layout["w"], "h": layout["h"]
                }
            else:
                logger.warning(f"Layout não encontrado para painel: {key}")
        
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
            logger.info("✅ Conexão com banco de dados confirmada")
            return True
        except Exception as e:
            logger.error(f"❌ Erro ao testar conexão com banco: {e}")
            return False
    
    @lru_cache(maxsize=32)
    def get_queries(self) -> Dict[str, str]:
        """Retorna queries do sistema (cacheable)"""
        return {
            "Eficiência Operacional": """
                SELECT COALESCE(efficiency_percent, 0)  
                FROM v_operational_efficiency
                ORDER BY timestamp DESC
                LIMIT 1
            """,
            
            "Navios à Espera": """
                SELECT count(*)  
                FROM vessel_queue
            """,
            
            "Cais Ocupados": """
                SELECT count(*)  
                FROM berths
                WHERE status = 'occupied'
            """,
            
            "Percentagem de ocupação dos Cais": """
                SELECT
                    ROUND(
                        (COUNT(CASE WHEN status = 'occupied' THEN 1 END) * 100.0 / NULLIF(COUNT(*), 0)), 2
                    )  
                FROM berths
            """,
            
            "Estado na Alfandega": """
                SELECT
                    v.vessel_name,
                    c.status,
                    c.last_update
                FROM customs_clearance as c
                JOIN vessels v ON c.vessel_id = v.vessel_id
                ORDER BY c.last_update DESC
                LIMIT 50
            """,

            "Navios atendidos": """ 
                                SELECT COUNT(*) 
                                FROM operations 
                                WHERE status = 'completed'
            
            """,
            "Tempo Médio na fila": """ 
                                SELECT AVG(waiting_time) 
                                FROM vessel_queue 
                                WHERE waiting_time > 0   
            
            """,
            "Estatisticas dos cais": """ 
                                SELECT 
                                    status AS "Status",
                                    COUNT(*) AS "Total"
                                FROM berths
                                WHERE status IN ('available', 'occupied', 'maintenance')
                                GROUP BY status;
            
            """,
            "Importação": """
                SELECT
                    ROUND(
                        100.0 * COUNT(CASE WHEN operation_type='import' AND status='completed' THEN 1 END) 
                        / NULLIF(COUNT(CASE WHEN operation_type='import' THEN 1 END), 0), 2
                    ) as import_success_rate
                FROM operations
                WHERE start_time >= NOW() - INTERVAL '24 hours'
            """,
            
            "Exportação": """
                SELECT
                    ROUND(
                        100.0 * COUNT(CASE WHEN operation_type='export' AND status='completed' THEN 1 END) 
                        / NULLIF(COUNT(CASE WHEN operation_type='export' THEN 1 END), 0), 2
                    ) as export_success_rate
                FROM operations
                WHERE start_time >= NOW() - INTERVAL '24 hours'
            """,
            
            "Cronograma dos cais": """
                SELECT
                    b.berth_number AS berth_name,
                    v.vessel_name,
                    o.start_time AS arrival_time,
                    o.end_time AS departure_time,
                    o.status
                FROM operations o
                JOIN berths b ON o.berth_id = b.berth_id
                JOIN vessels v ON o.vessel_id = v.vessel_id
                WHERE o.start_time >= CURRENT_DATE
                ORDER BY b.berth_number, o.start_time
            """,
            
            # Queries adicionais sugeridas para análise temporal
            "operacoes_por_hora": """
                SELECT
                    DATE_TRUNC('hour', start_time) as hour,
                    operation_type,
                    COUNT(*) as total_operations,
                    COUNT(CASE WHEN status='completed' THEN 1 END) as completed_operations,
                    ROUND(
                        100.0 * COUNT(CASE WHEN status='completed' THEN 1 END) / COUNT(*), 2
                    ) as success_rate
                FROM operations
                WHERE start_time >= NOW() - INTERVAL '24 hours'
                GROUP BY DATE_TRUNC('hour', start_time), operation_type
                ORDER BY hour DESC, operation_type
            """
        }
    

  
    
    def create_porto_panels(self, datasource_uid: str) -> List[Dict[str, Any]]:
            """Cria todos os painéis do dashboard portuário"""
            queries = self.get_queries()
            panels = []

            # Estatisticas dos cais
            config = PanelConfig(
                title="Estatisticas dos cais",
                width=6, height=6,
                unit="percent",
                max_val=100,
                description="Estatisticas dos cais"
            )
            panels.append(PanelFactory.create_pie_panel(
                config, queries["Estatisticas dos cais"], 
                datasource_uid
            )) #, self.EFFICIENCY_THRESHOLDS

            # Eficiência Operacional
            config = PanelConfig(
                title="Eficiência Operacional",
                width=6, height=6,
                unit="percent",
                max_val=100,
                description="Eficiência operacional"
            )
            panels.append(PanelFactory.create_stat_panel(
                config, queries["Eficiência Operacional"], 
                datasource_uid, self.EFFICIENCY_THRESHOLDS
            ))

            # Tempo Médio na fila
            config = PanelConfig(
                title="Tempo Médio na fila",
                width=6, height=6,
                unit="percent",
                max_val=100,
                description="Tempo Médio na fila"
            )
            panels.append(PanelFactory.create_stat_panel(
                config, queries["Tempo Médio na fila"], 
                datasource_uid, self.EFFICIENCY_THRESHOLDS
            ))
            
             
            # Navios atendidos
            config = PanelConfig(
                title="Navios atendidos",
                width=6, height=6,
                unit="percent",
                max_val=100,
                description="Navios atendidos"
            )
            panels.append(PanelFactory.create_stat_panel(
                config, queries["Navios atendidos"], 
                datasource_uid, self.EFFICIENCY_THRESHOLDS
            ))
            

            # Navios em Espera
            config = PanelConfig(
                title="Navios à Espera",
                width=4, height=6,
                description="Navios aguardando atracagem"
            )
            panels.append(PanelFactory.create_stat_panel(
                config, queries["Navios à Espera"],
                datasource_uid, self.WAITING_THRESHOLDS
            ))
            
            # Cais Ocupados
            config = PanelConfig(
                title="Cais Ocupados",
                width=4, height=6,
                description="Cais Ocupados"
            )
            panels.append(PanelFactory.create_stat_panel(
                config, queries["Cais Ocupados"],
                datasource_uid, self.OCCUPATION_THRESHOLDS
            ))
            
            # Percentagem de ocupação dos Cais
            config = PanelConfig(
                title="Percentagem de ocupação dos Cais",
                width=6, height=6,
                unit="percent",
                max_val=100,
                description="Percentual de ocupação dos cais"
            )
            panels.append(PanelFactory.create_stat_panel(
                config, queries["Percentagem de ocupação dos Cais"],
                datasource_uid, self.OCCUPATION_THRESHOLDS
            ))
            
            # Estado na Alfandega
            config = PanelConfig(
                title="Estado na Alfandega",
                width=8, height=8,
                description="Estado na Alfandega"
            )
            panels.append(PanelFactory.create_table_panel(
                config, queries["Estado na Alfandega"], datasource_uid
            ))
            
            # Operações de Importação
            config = PanelConfig(
                title="Operações de Importação",
                width=12, height=8,
                unit="percent",
                description="Eficiência das operações de importação"
            )
            panels.append(PanelFactory.create_timeseries_panel(
                config, queries["Importação"], 
                datasource_uid,"green"
            ))
            
            # Operações de Exportação
            config = PanelConfig(
                title="Operações de Exportação",
                width=12, height=8,
                unit="percent",
                description="Eficiência das operações de exportação"
            )
            panels.append(PanelFactory.create_timeseries_panel(
                config, queries["Exportação"],
                datasource_uid, "blue"
            ))
            
            # Cronograma dos Cais
            config = PanelConfig(
                title="Cronograma dos Cais",
                width=24, height=10,
                description="Cronograma dos cais"
            )
            panels.append(PanelFactory.create_table_panel(
                config, queries["Cronograma dos cais"], datasource_uid
            ))
            
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
                
                # Testar conexão
                if self.test_database_connection(uid):
                    return uid
                else:
                    logger.warning("⚠️ Datasource existe mas conexão falhou")
                    
            except requests.HTTPError as e:
                if e.response.status_code != 404:
                    raise
            
            # Criar ou recriar datasource
            try:
                logger.info(f"📡 Criando datasource {uid}...")
                response = self.api.post("/datasources", json=datasource_config)
                logger.info(f"✅ Datasource {uid} criado com sucesso")
                
                # Aguardar um pouco para o datasource estar pronto
                time.sleep(2)
                
                # Testar conexão após criação
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
            """Cria ou atualiza dashboard"""
            dashboard_payload = {
                "dashboard": {
                    "uid": config.uid,
                    "title": config.title,
                    "tags": config.tags,
                    "timezone": "browser",
                    "panels": LayoutManager.apply_layout(panels),
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
            title="Dashboard Operacional do Porto - Visão  Geral",
            uid="porto-operacional-completo",
            time_from="now-7d",
            refresh="1m"
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
    
 