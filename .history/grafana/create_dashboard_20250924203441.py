import os
import time
import logging
import requests
import json
from typing import Optional, Dict, Any, List, Union
from dataclasses import dataclass, field
from enum import Enum
from functools import lru_cache
from datetime import datetime

# Configuração de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

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

class DockerConfig:
    """Configurações específicas para ambiente Docker"""
    
    @staticmethod
    def get_grafana_config() -> Dict[str, str]:
        """Configurações do Grafana a partir das variáveis de ambiente"""
        return {
            "url": os.getenv("GRAFANA_URL", "http://grafana_dashboard:3000"),
            "admin_user": os.getenv("GF_SECURITY_ADMIN_USER", "admin"),
            "admin_password": os.getenv("GF_SECURITY_ADMIN_PASSWORD", "admin"),
            "public_token": os.getenv("GRAFANA_PUBLIC_TOKEN", "")
        }
    
    @staticmethod
    def get_database_config() -> Dict[str, str]:
        """Configurações do banco a partir das variáveis de ambiente"""
        return {
            "host": "postgres_database",  # Nome do serviço Docker
            "port": "5432",
            "database": os.getenv("POSTGRES_DB", "grafana_database"),
            "user": os.getenv("POSTGRES_USER", "grafana_admin"),
            "password": os.getenv("POSTGRES_PASSWORD", "")
        }

class GrafanaAPI:
    """Cliente API do Grafana para ambiente Docker"""
    
    def __init__(self, base_url: str, api_key: str = None, timeout: int = 30):
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.timeout = timeout
        self.session = self._create_session()
    
    def _create_session(self) -> requests.Session:
        """Cria sessão HTTP reutilizável"""
        session = requests.Session()
        headers = {"Content-Type": "application/json"}
        
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        
        session.headers.update(headers)
        return session
    
    def _make_request(self, method: str, endpoint: str, **kwargs) -> requests.Response:
        """Faz requisição HTTP com tratamento de erro e retry"""
        url = f"{self.base_url}/api{endpoint}"
        max_retries = 3
        retry_delay = 2
        
        for attempt in range(max_retries):
            try:
                response = self.session.request(method, url, timeout=self.timeout, **kwargs)
                response.raise_for_status()
                return response
            except requests.ConnectionError as e:
                if attempt < max_retries - 1:
                    logger.warning(f"Tentativa {attempt + 1} falhou, tentando novamente em {retry_delay}s...")
                    time.sleep(retry_delay)
                    retry_delay *= 2
                else:
                    logger.error(f"Todas as tentativas de conexão falharam: {e}")
                    raise
            except requests.RequestException as e:
                logger.error(f"Erro na requisição {method} {endpoint}: {e}")
                if hasattr(e, 'response') and e.response is not None:
                    logger.error(f"Response: {e.response.text}")
                raise
    
    def get(self, endpoint: str, **kwargs) -> requests.Response:
        return self._make_request("GET", endpoint, **kwargs)
    
    def post(self, endpoint: str, **kwargs) -> requests.Response:
        return self._make_request("POST", endpoint, **kwargs)

class TokenManager:
    """Gerenciador de tokens de API do Grafana"""
    
    def __init__(self, grafana_api: GrafanaAPI, config: Dict[str, str]):
        self.api = grafana_api
        self.config = config
    
    def create_service_account_and_token(self) -> str:
        """Cria service account e token se necessário"""
        sa_name = "dashboard-automation-sa"
        token_name = "dashboard-automation-token"
        
        try:
            # Primeiro tenta usar o token público se existir
            public_token = self.config.get("public_token")
            if public_token:
                logger.info("🔑 Usando token público existente")
                return public_token
            
            # Se não, tenta autenticação básica para criar token
            logger.info("🔐 Fazendo login com credenciais de admin...")
            
            # Login básico
            auth_api = GrafanaAPI(self.config["url"])
            auth_api.session.auth = (self.config["admin_user"], self.config["admin_password"])
            
            # Verificar se service account já existe
            try:
                sa_response = auth_api.get("/serviceaccounts/search", params={"query": sa_name})
                service_accounts = sa_response.json().get("serviceAccounts", [])
                
                if service_accounts:
                    sa_id = service_accounts[0]["id"]
                    logger.info(f"✅ Service account '{sa_name}' já existe (ID: {sa_id})")
                else:
                    # Criar service account
                    sa_payload = {
                        "name": sa_name,
                        "role": "Admin",
                        "isDisabled": False
                    }
                    sa_response = auth_api.post("/serviceaccounts", json=sa_payload)
                    sa_id = sa_response.json()["id"]
                    logger.info(f"✅ Service account '{sa_name}' criado (ID: {sa_id})")
                
                # Criar token
                token_payload = {
                    "name": token_name,
                    "role": "Admin"
                }
                token_response = auth_api.post(f"/serviceaccounts/{sa_id}/tokens", json=token_payload)
                token = token_response.json()["key"]
                
                logger.info("✅ Token de API criado com sucesso")
                return token
                
            except requests.HTTPError as e:
                if e.response.status_code == 409:  # Conflict - já existe
                    logger.warning("⚠️ Token já existe, tentando continuar...")
                    # Se o token já existe, tente usar as credenciais básicas
                    return None
                raise
                
        except Exception as e:
            logger.error(f"❌ Erro ao criar token: {e}")
            # Em caso de erro, retorna None para usar auth básica
            return None

class PanelFactory:
    """Factory para criação de painéis otimizada para Docker"""
    
    @staticmethod
    def create_base_panel(panel_type: str, config: PanelConfig, 
                         query: str, datasource_uid: str, panel_id: int) -> Dict[str, Any]:
        """Cria estrutura base do painel"""
        return {
            "id": panel_id,
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
                "format": "table",
                "hide": False
            }]
        }
    
    @staticmethod
    def create_stat_panel(config: PanelConfig, query: str, datasource_uid: str,
                         thresholds: List[ThresholdStep] = None, panel_id: int = 1) -> Dict[str, Any]:
        """Cria painel do tipo stat"""
        panel = PanelFactory.create_base_panel("stat", config, query, datasource_uid, panel_id)
        
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
                "max": config.max_val,
                "mappings": []
            },
            "overrides": []
        }
        
        panel["options"] = {
            "orientation": "auto",
            "reduceOptions": {
                "calcs": ["lastNotNull"],
                "fields": "",
                "values": False
            },
            "textMode": "auto",
            "colorMode": "value",
            "graphMode": "area",
            "justifyMode": "auto"
        }
        
        return panel
    
    @staticmethod
    def create_table_panel(config: PanelConfig, query: str, 
                          datasource_uid: str, panel_id: int = 1) -> Dict[str, Any]:
        """Cria painel de tabela"""
        panel = PanelFactory.create_base_panel("table", config, query, datasource_uid, panel_id)
        
        panel["fieldConfig"] = {
            "defaults": {
                "custom": {
                    "align": "auto",
                    "displayMode": "auto",
                    "filterable": True,
                    "inspect": False
                },
                "color": {"mode": "palette-classic"},
                "mappings": []
            },
            "overrides": []
        }
        
        panel["options"] = {
            "showHeader": True,
            "cellHeight": "sm",
            "footer": {
                "show": False,
                "reducer": ["sum"],
                "countRows": False,
                "fields": ""
            }
        }
        
        return panel

class LayoutManager:
    """Gerenciador de layout otimizado"""
    
    @staticmethod
    def get_panel_layouts() -> List[Dict[str, Any]]:
        """Layout responsivo para Docker"""
        return [
            # Linha 1: Métricas principais (6 painéis, 4 colunas cada)
            {"title": "Eficiência Operacional", "w": 4, "h": 8, "x": 0, "y": 0},
            {"title": "Navios atendidos", "w": 4, "h": 8, "x": 4, "y": 0},
            {"title": "Navios à Espera", "w": 4, "h": 8, "x": 8, "y": 0},
            {"title": "Cais Ocupados", "w": 4, "h": 8, "x": 12, "y": 0},
            {"title": "Percentagem de ocupação dos Cais", "w": 4, "h": 8, "x": 16, "y": 0},
            {"title": "Tempo de espera na fila", "w": 4, "h": 8, "x": 20, "y": 0},
            
            # Linha 2: Tabelas
            {"title": "Estado na Alfandega", "w": 12, "h": 10, "x": 0, "y": 8},
            {"title": "Cronograma dos Cais", "w": 12, "h": 10, "x": 12, "y": 8}
        ]
    
    @staticmethod
    def apply_layout(panels: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Aplica layout aos painéis"""
        layouts = {layout["title"]: layout for layout in LayoutManager.get_panel_layouts()}
        
        for panel in panels:
            title = panel.get("title")
            if title in layouts:
                layout = layouts[title]
                panel["gridPos"] = {
                    "x": layout["x"], 
                    "y": layout["y"],
                    "w": layout["w"], 
                    "h": layout["h"]
                }
        
        return panels

class DashboardManager:
    """Gerenciador principal - versão Docker"""
    
    # Thresholds
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
    
    def wait_for_services(self, max_wait: int = 120):
        """Espera os serviços estarem prontos"""
        logger.info("⏳ Aguardando serviços estarem prontos...")
        
        start_time = time.time()
        while time.time() - start_time < max_wait:
            try:
                # Testa Grafana
                response = self.api.get("/health")
                if response.status_code == 200:
                    logger.info("✅ Grafana está pronto")
                    return True
            except:
                logger.info("⏳ Aguardando Grafana...")
                time.sleep(5)
        
        logger.error("❌ Timeout aguardando serviços")
        return False

    @lru_cache(maxsize=32)
    def get_queries(self) -> Dict[str, str]:
        """Queries otimizadas para Docker"""
        return {
            "Eficiência Operacional": """
                SELECT 
                    COALESCE(
                        ROUND(
                            AVG(
                                CASE 
                                    WHEN planned_duration > 0 AND actual_duration > 0 THEN 
                                        LEAST(100.0, (planned_duration::float / actual_duration) * 100)
                                    ELSE NULL 
                                END
                            )::numeric, 1
                        ), 75.5
                    ) as value
                FROM operations
                WHERE status = 'completed'
            """,
            
            "Navios atendidos": """
                SELECT COUNT(*) as value
                FROM operations 
                WHERE status = 'completed'
            """,
            
            "Navios à Espera": """
                SELECT COUNT(*) as value
                FROM vessel_queue 
                WHERE status = 'waiting'
            """,
            
            "Cais Ocupados": """
                SELECT COUNT(*) as value
                FROM berths
                WHERE status = 'occupied'
            """,
            
            "Percentagem de ocupação dos Cais": """
                SELECT
                    COALESCE(
                        ROUND(
                            (COUNT(CASE WHEN status = 'occupied' THEN 1 END) * 100.0 / 
                             NULLIF(COUNT(*), 0)), 2
                        ), 0
                    ) as value
                FROM berths
            """,
            
            "Tempo de espera na fila": """
                SELECT
                    'Mínimo' as tipo,
                    COALESCE(
                        ROUND(EXTRACT(EPOCH FROM MIN(start_service_time - arrival_time)) / 3600, 2), 0
                    ) as horas
                FROM vessel_queue
                WHERE status = 'completed' 
                  AND start_service_time IS NOT NULL 
                  AND arrival_time IS NOT NULL
                  AND start_service_time >= arrival_time
                
                UNION ALL
                
                SELECT
                    'Médio' as tipo,
                    COALESCE(
                        ROUND(EXTRACT(EPOCH FROM AVG(start_service_time - arrival_time)) / 3600, 2), 0
                    ) as horas
                FROM vessel_queue
                WHERE status = 'completed' 
                  AND start_service_time IS NOT NULL 
                  AND arrival_time IS NOT NULL
                  AND start_service_time >= arrival_time
                
                UNION ALL
                
                SELECT
                    'Máximo' as tipo,
                    COALESCE(
                        ROUND(EXTRACT(EPOCH FROM MAX(start_service_time - arrival_time)) / 3600, 2), 0
                    ) as horas
                FROM vessel_queue
                WHERE status = 'completed' 
                  AND start_service_time IS NOT NULL 
                  AND arrival_time IS NOT NULL
                  AND start_service_time >= arrival_time
            """,
            
            "Estado na Alfandega": """
                SELECT
                    v.vessel_name as "Navio",
                    CASE 
                        WHEN c.status = 'pending' THEN 'Pendente'
                        WHEN c.status = 'approved' THEN 'Aprovado'
                        WHEN c.status = 'rejected' THEN 'Rejeitado'
                        ELSE c.status
                    END as "Status",
                    TO_CHAR(c.last_update, 'DD/MM/YYYY HH24:MI') as "Última Atualização"
                FROM customs_clearance c
                JOIN vessels v ON c.vessel_id = v.vessel_id
                ORDER BY c.last_update DESC
                LIMIT 15
            """,
            
            "Cronograma dos Cais": """
                SELECT
                    b.berth_number as "Cais",
                    v.vessel_name as "Navio",
                    TO_CHAR(o.start_time, 'DD/MM HH24:MI') as "Chegada",
                    TO_CHAR(o.end_time, 'DD/MM HH24:MI') as "Partida",
                    CASE 
                        WHEN o.status = 'active' THEN 'Ativo'
                        WHEN o.status = 'completed' THEN 'Concluído'
                        WHEN o.status = 'scheduled' THEN 'Agendado'
                        ELSE o.status
                    END as "Status"
                FROM operations o
                JOIN berths b ON o.berth_id = b.berth_id
                JOIN vessels v ON o.vessel_id = v.vessel_id
                WHERE o.start_time >= CURRENT_DATE - INTERVAL '1 day'
                ORDER BY b.berth_number, o.start_time
                LIMIT 20
            """
        }
    
    def create_porto_panels(self, datasource_uid: str) -> List[Dict[str, Any]]:
        """Cria painéis do porto"""
        queries = self.get_queries()
        panels = []
        panel_id = 1

        # Painéis de estatística
        stat_panels = [
            ("Eficiência Operacional", "percent", 100, self.EFFICIENCY_THRESHOLDS),
            ("Navios atendidos", "none", None, None),
            ("Navios à Espera", "none", None, self.WAITING_THRESHOLDS),
            ("Cais Ocupados", "none", None, self.OCCUPATION_THRESHOLDS),
            ("Percentagem de ocupação dos Cais", "percent", 100, self.OCCUPATION_THRESHOLDS),
        ]

        for title, unit, max_val, thresholds in stat_panels:
            config = PanelConfig(
                title=title,
                unit=unit,
                max_val=max_val,
                description=f"Métrica: {title}"
            )
            panels.append(PanelFactory.create_stat_panel(
                config, queries[title], datasource_uid, thresholds, panel_id
            ))
            panel_id += 1

        # Painéis de tabela
        table_panels = [
            "Tempo de espera na fila",
            "Estado na Alfandega", 
            "Cronograma dos Cais"
        ]

        for title in table_panels:
            config = PanelConfig(
                title=title,
                description=f"Tabela: {title}"
            )
            panels.append(PanelFactory.create_table_panel(
                config, queries[title], datasource_uid, panel_id
            ))
            panel_id += 1

        logger.info(f"📊 Criados {len(panels)} painéis")
        return panels
    
    def create_datasource_if_not_exists(self, datasource_config: Dict[str, Any]) -> str:
        """Cria datasource se não existir"""
        uid = datasource_config["uid"]
        
        try:
            response = self.api.get(f"/datasources/uid/{uid}")
            logger.info(f"✅ Datasource {uid} já existe")
            return uid
        except requests.HTTPError as e:
            if e.response.status_code != 404:
                raise
        
        try:
            logger.info(f"📡 Criando datasource {uid}...")
            response = self.api.post("/datasources", json=datasource_config)
            logger.info(f"✅ Datasource {uid} criado com sucesso")
            time.sleep(2)  # Aguarda estar pronto
        except Exception as e:
            logger.error(f"❌ Erro ao criar datasource: {e}")
            raise
        
        return uid
    
    def create_or_update_dashboard(self, config: DashboardConfig, 
                                  panels: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Cria ou atualiza dashboard"""
        panels_with_layout = LayoutManager.apply_layout(panels)
        
        dashboard_payload = {
            "dashboard": {
                "id": None,
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
                "schemaVersion": 39,
                "version": 1,
                "editable": True,
                "fiscalYearStartMonth": 0,
                "graphTooltip": 0,
                "links": [],
                "liveNow": False,
                "weekStart": ""
            },
            "overwrite": True,
            "message": f"Dashboard criado automaticamente em {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}"
        }
        
        try:
            response = self.api.post("/dashboards/db", json=dashboard_payload)
            result = response.json()
            logger.info(f"✅ Dashboard '{config.title}' criado com sucesso!")
            return result
        except Exception as e:
            logger.error(f"❌ Erro ao criar dashboard: {e}")
            raise


def main():
    """Função principal para ambiente Docker"""
    logger.info("🚀 Iniciando Dashboard Manager para Docker...")
    
    # Configurações do ambiente Docker
    grafana_config = DockerConfig.get_grafana_config()
    db_config = DockerConfig.get_database_config()
    
    logger.info(f"🔗 Grafana URL: {grafana_config['url']}")
    logger.info(f"🗄️  Database: {db_config['host']}:{db_config['port']}/{db_config['database']}")
    
    try:
        # Criar API sem token inicialmente
        api = GrafanaAPI(grafana_config["url"])
        
        # Gerenciar token
        token_manager = TokenManager(api, grafana_config)
        token = token_manager.create_service_account_and_token()
        
        if token:
            # Recriar API com token
            api = GrafanaAPI(grafana_config["url"], token)
            logger.info("✅ Usando autenticação via token")
        else:
            # Usar autenticação básica
            api.session.auth = (grafana_config["admin_user"], grafana_config["admin_password"])
            logger.info("✅ Usando autenticação básica")
        
        # Criar manager
        manager = DashboardManager(api)
        
        # Aguardar serviços
        if not manager.wait_for_services():
            raise Exception("Timeout aguardando serviços")
        
        # Configuração do datasource
        datasource_config = {
            "uid": "postgres-porto-docker",
            "name": "PostgreSQL Porto Docker",
            "type": "postgres",
            "access": "proxy",
            "url": f"{db_config['host']}:{db_config['port']}",
            "database": db_config["database"],
            "user": db_config["user"],
            "secureJsonData": {
                "password": db_config["password"]
            },
            "jsonData": {
                "sslmode": "disable",
                "postgresVersion": 1200,
                "maxOpenConns": 10,
                "maxIdleConns": 2,
                "connMaxLifetime": 14400,
                "timescaledb": False
            }
        }
        
        # Criar datasource
        logger.info("📊 Configurando datasource...")
        datasource_uid = manager.create_datasource_if_not_exists(datasource_config)
        
        # Criar painéis
        logger.info("📈 Criando painéis...")
        panels = manager.create_porto_panels(datasource_uid)
        
        # Configurar dashboard
        dashboard_config = DashboardConfig(
            title="Dashboard Operacional do Porto",
            uid="porto-operacional-docker",
            time_from="now-7d",
            refresh="30s"
        )
        
        # Criar dashboard
        logger.info("🎯 Criando dashboard...")
        result = manager.create_or_update_dashboard(dashboard_config, panels)
        
        print("\n" + "="*60)
        print("🎉 DASHBOARD CRIADO COM SUCESSO!")
        print("="*60)
        print(f"📊 Dashboard: {dashboard_config.title}")
        print(f"🔗 URL: {grafana_config['url']}/d/{dashboard_config.uid}")
        print(f"🔄 Refresh: {dashboard_config.refresh}")
        print(f"📅 Período: {dashboard_config.time_from} até {dashboard_config.time_to}")
        print("="*60)
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Erro na execução: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)