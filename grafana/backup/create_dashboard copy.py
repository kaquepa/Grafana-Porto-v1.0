from typing import Optional, Dict, Any, List, Union
import logging
import requests
import uuid
from datetime import datetime
from dataclasses import dataclass, field
from enum import Enum
from functools import lru_cache
import json
import time

from app.core.config import Config_grafana, Config_database
from create_service_account import GrafanaTokenManager

token_manager = GrafanaTokenManager()
api_key = token_manager.execute_workflow()

# Configuração de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ThresholdColor(Enum):
    """Cores padrão para thresholds"""
    GREEN = "green"
    YELLOW = "yellow"
    RED = "red"
    BLUE = "blue"


@dataclass
class ThresholdStep:
    """Passo de threshold"""
    color: str
    value: Optional[Union[int, float]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {"color": self.color, "value": self.value}


@dataclass
class PanelConfig:
    """Configuração base para painéis"""
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


class LayoutManager:
    """Gerenciador de layout do dashboard"""
    
    GRID_WIDTH = 24
    
    @staticmethod
    def get_panel_layouts() -> List[Dict[str, Any]]:
        """Define o layout dos painéis de forma proporcional e harmoniosa"""
        return [
            # Linha 1: Painéis de estatísticas principais
            {"title": "Eficiência Operacional", "type": "stat", "w": 6, "h": 6, "x": 0, "y": 0},
            {"title": "Navios em Espera", "type": "stat", "w": 6, "h": 6, "x": 6, "y": 0},
            {"title": "Cais Ocupados", "type": "stat", "w": 6, "h": 6, "x": 12, "y": 0},
            {"title": "Ocupação do Cais", "type": "stat", "w": 6, "h": 6, "x": 18, "y": 0},

            # Linha 2: Operações de Importação e Exportação lado a lado
            {"title": "Operações de Importação", "type": "timeseries", "w": 12, "h": 8, "x": 0, "y": 6},
            {"title": "Operações de Exportação", "type": "timeseries", "w": 12, "h": 8, "x": 12, "y": 6},

            # Linha 3: Status Alfândega e Cronograma dos Cais lado a lado
            {"title": "Status Alfândega", "type": "table", "w": 12, "h": 10, "x": 0, "y": 14},
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
            # Simula uma query de teste via API do Grafana
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
            "eficiencia_operacional": """
                SELECT COALESCE(efficiency_percent, 0) as efficiency_percent 
                FROM v_operational_efficiency 
                ORDER BY timestamp DESC 
                LIMIT 1
            """,
            "navios_espera": """
                SELECT COALESCE(count(*), 0) as waiting_count 
                FROM vessels 
                WHERE status = 'waiting'
            """,
            "cais_ocupados": """
                SELECT COALESCE(count(*), 0) as occupied_count 
                FROM berths 
                WHERE status = 'occupied'
            """,
            "ocupacao_cais": """
                SELECT COALESCE(
                    ROUND((COUNT(CASE WHEN status = 'occupied' THEN 1 END) * 100.0 / NULLIF(COUNT(*), 0)), 2), 
                    0
                ) as occupation_percent 
                FROM berths
            """,
            "alfandega_status": """
                SELECT 
                    vessel_name, 
                    status, 
                    last_update 
                FROM customs_clearance 
                ORDER BY last_update DESC
            """,
            "operacoes_importacao": """
                SELECT 
                    timestamp AS "time", 
                    COALESCE(import_efficiency, 0) as import_efficiency 
                FROM v_import_operations 
                WHERE $__timeFilter(timestamp)
                ORDER BY timestamp
            """,
            "operacoes_exportacao": """
                SELECT 
                    timestamp AS "time", 
                    COALESCE(export_efficiency, 0) as export_efficiency 
                FROM v_export_operations 
                WHERE $__timeFilter(timestamp)
                ORDER BY timestamp
            """,
            "cronograma_cais": """
                SELECT 
                    berth_name, 
                    vessel_name, 
                    arrival_time, 
                    departure_time, 
                    status 
                FROM berth_schedule 
                ORDER BY berth_name
            """
        }
    
    def create_porto_panels(self, datasource_uid: str) -> List[Dict[str, Any]]:
        """Cria todos os painéis do dashboard portuário"""
        queries = self.get_queries()
        panels = []
        
        # Eficiência Operacional
        config = PanelConfig(
            title="Eficiência Operacional",
            width=6, height=6,
            unit="percent",
            max_val=100,
            description="Eficiência operacional do porto"
        )
        panels.append(PanelFactory.create_stat_panel(
            config, queries["eficiencia_operacional"], 
            datasource_uid, self.EFFICIENCY_THRESHOLDS
        ))
        
        # Navios em Espera
        config = PanelConfig(
            title="Navios em Espera",
            width=4, height=6,
            description="Navios aguardando atracagem"
        )
        panels.append(PanelFactory.create_stat_panel(
            config, queries["navios_espera"],
            datasource_uid, self.WAITING_THRESHOLDS
        ))
        
        # Cais Ocupados
        config = PanelConfig(
            title="Cais Ocupados",
            width=4, height=6,
            description="Número de cais ocupados"
        )
        panels.append(PanelFactory.create_stat_panel(
            config, queries["cais_ocupados"],
            datasource_uid
        ))
        
        # Ocupação do Cais
        config = PanelConfig(
            title="Ocupação do Cais",
            width=6, height=6,
            unit="percent",
            max_val=100,
            description="Percentual de ocupação dos cais"
        )
        panels.append(PanelFactory.create_stat_panel(
            config, queries["ocupacao_cais"],
            datasource_uid, self.OCCUPATION_THRESHOLDS
        ))
        
        # Status Alfândega
        config = PanelConfig(
            title="Status Alfândega",
            width=8, height=8,
            description="Status de liberação alfandegária"
        )
        panels.append(PanelFactory.create_table_panel(
            config, queries["alfandega_status"], datasource_uid
        ))
        
        # Operações de Importação
        config = PanelConfig(
            title="Operações de Importação",
            width=12, height=8,
            unit="percent",
            description="Eficiência das operações de importação"
        )
        panels.append(PanelFactory.create_timeseries_panel(
            config, queries["operacoes_importacao"], 
            datasource_uid, "green"
        ))
        
        # Operações de Exportação
        config = PanelConfig(
            title="Operações de Exportação",
            width=12, height=8,
            unit="percent",
            description="Eficiência das operações de exportação"
        )
        panels.append(PanelFactory.create_timeseries_panel(
            config, queries["operacoes_exportacao"],
            datasource_uid, "blue"
        ))
        
        # Cronograma dos Cais
        config = PanelConfig(
            title="Cronograma dos Cais",
            width=24, height=10,
            description="Programação e status dos cais"
        )
        panels.append(PanelFactory.create_table_panel(
            config, queries["cronograma_cais"], datasource_uid
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


def verify_database_setup():
    """Verifica se as tabelas foram criadas no banco"""
    import psycopg2
    
    try:
        conn = psycopg2.connect(
            host=Config_database.HOST,
            port=Config_database.PORT,
            database=Config_database.DATABASE,
            user=Config_database.USER,
            password=Config_database.PASSWORD
        )
        
        cursor = conn.cursor()
        
        # Verificar tabelas principais
        tables_to_check = ['vessels', 'berths', 'customs_clearance', 'operations', 'operational_stats']
        
        for table in tables_to_check:
            cursor.execute(f"SELECT COUNT(*) FROM information_schema.tables WHERE table_name = '{table}';")
            count = cursor.fetchone()[0]
            if count > 0:
                cursor.execute(f"SELECT COUNT(*) FROM {table};")
                records = cursor.fetchone()[0]
                logger.info(f"✅ Tabela {table}: {records} registros")
            else:
                logger.error(f"❌ Tabela {table} não encontrada")
        
        # Verificar views
        views_to_check = ['v_operational_efficiency', 'berth_schedule']
        
        for view in views_to_check:
            cursor.execute(f"SELECT COUNT(*) FROM information_schema.views WHERE table_name = '{view}';")
            count = cursor.fetchone()[0]
            if count > 0:
                logger.info(f"✅ View {view} existe")
            else:
                logger.error(f"❌ View {view} não encontrada")
        
        cursor.close()
        conn.close()
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Erro ao verificar banco de dados: {e}")
        return False


def main():
    """Função principal"""
    
    logger.info("🚀 Iniciando configuração do Dashboard do Porto...")
    
    # Verificar banco de dados primeiro
    logger.info("🔍 Verificando configuração do banco de dados...")
    if not verify_database_setup():
        logger.error("❌ Banco de dados não está configurado corretamente")
        logger.error("💡 Execute o script init.sql no PostgreSQL primeiro")
        return 1
    
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
            title="Dashboard Operacional do Porto - Visão Completa",
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
    exit(main())