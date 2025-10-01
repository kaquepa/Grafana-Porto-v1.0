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
    """Cliente API do Grafana otimizado"""
    
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
    
    def put(self, endpoint: str, **kwargs) -> requests.Response:
        return self._request("PUT", endpoint, **kwargs)
    
    def delete(self, endpoint: str, **kwargs) -> requests.Response:
        return self._request("DELETE", endpoint, **kwargs)

class PanelFactory:
    """Factory para criação de painéis otimizada"""
    
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
                "format": "table",
                "interval": ""
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
    """Gerenciador de layout otimizado"""
    
    LAYOUTS = [
        {"title": "Eficiência Operacional", "type": "stat", "w": 6, "h": 8, "x": 0, "y": 0},
        {"title": "Navios atendidos", "type": "stat", "w": 6, "h": 8, "x": 6, "y": 0},
        {"title": "Navios à Espera", "type": "stat", "w": 6, "h": 8, "x": 12, "y": 0},
        {"title": "Cais Ocupados", "type": "stat", "w": 6, "h": 8, "x": 18, "y": 0},
        {"title": "Percentagem de ocupação dos Cais", "type": "stat", "w": 8, "h": 8, "x": 0, "y": 8},
        {"title": "Tempo de espera na fila", "type": "table", "w": 16, "h": 8, "x": 8, "y": 8},
        {"title": "Estado na Alfandega", "type": "table", "w": 12, "h": 10, "x": 0, "y": 16},
        {"title": "Cronograma dos Cais", "type": "table", "w": 12, "h": 10, "x": 12, "y": 16}
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
    """Gerenciador principal de dashboards - VERSÃO COMPLETA E OTIMIZADA"""
    
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

    def _execute_comprehensive_test(self, ds_uid: str) -> bool:
        """Teste abrangente do datasource com múltiplas estratégias"""
        test_scenarios = [
            {
                "name": "Teste de conexão básica",
                "query": "SELECT 1 as connection_test, NOW() as test_time",
                "expect_data": True
            },
            {
                "name": "Teste de query complexa", 
                "query": """
                    SELECT 
                        'operational' as system_status,
                        85.5 as test_efficiency,
                        COUNT(*) as test_count
                    FROM information_schema.tables 
                    WHERE table_schema = 'public'
                """,
                "expect_data": True
            },
            {
                "name": "Teste de funções de tempo",
                "query": "SELECT NOW() as current_time, EXTRACT(HOUR FROM NOW()) as current_hour",
                "expect_data": True
            }
        ]
        
        successful_tests = 0
        
        for test in test_scenarios:
            try:
                payload = {
                    "queries": [{
                        "refId": "TEST",
                        "datasource": {"type": "postgres", "uid": ds_uid},
                        "rawSql": test["query"],
                        "format": "table"
                    }],
                    "from": "now-5m",
                    "to": "now"
                }
                
                response = self.api.post("/ds/query", json=payload)
                result = response.json()
                
                if "results" in result and "TEST" in result["results"]:
                    test_result = result["results"]["TEST"]
                    if not test_result.get("error"):
                        successful_tests += 1
                        logger.info(f"✅ {test['name']} - OK")
                    else:
                        logger.warning(f"⚠️ {test['name']} - Erro: {test_result.get('error')}")
                else:
                    logger.warning(f"⚠️ {test['name']} - Estrutura de resposta inválida")
                    
            except Exception as e:
                logger.warning(f"⚠️ {test['name']} - Falha: {str(e)[:100]}")
        
        # Considera sucesso se pelo menos 2 testes passarem
        return successful_tests >= 2

    def _activate_datasource(self, ds_uid: str) -> bool:
        """Ativa o datasource simulando o 'Save & Test'"""
        try:
            # 1. Obtém informações atuais do datasource
            response = self.api.get(f"/datasources/uid/{ds_uid}")
            ds_info = response.json()
            ds_id = ds_info["id"]
            
            logger.info(f"🎯 Ativando datasource {ds_uid} (ID: {ds_id})")
            
            # 2. Prepara payload de atualização com TODOS os campos necessários
            update_payload = {
                "id": ds_id,
                "uid": ds_uid,
                "name": ds_info["name"],
                "type": ds_info["type"],
                "access": ds_info["access"],
                "url": ds_info["url"],
                "database": ds_info.get("database"),
                "user": ds_info.get("user"),
                "isDefault": True,
                "readOnly": False,
                "jsonData": ds_info.get("jsonData", {}),
                "secureJsonData": {
                    "password": Config_database.PASSWORD  # 🔑 CRÍTICO: Re-envia a senha
                }
            }
            
            # 3. Atualiza o datasource (simula o clique em "Save & Test")
            self.api.put(f"/datasources/{ds_id}", json=update_payload)
            logger.info("💾 Datasource atualizado e ativado")
            
            # 4. Aguarda processamento
            time.sleep(3)
            
            # 5. Testa novamente após ativação
            if self._execute_comprehensive_test(ds_uid):
                logger.info("🎉 Datasource completamente ativado e testado!")
                return True
            else:
                logger.warning("⚠️ Datasource atualizado mas teste pós-ativação falhou")
                return False
                
        except Exception as e:
            logger.error(f"💥 Falha na ativação do datasource: {e}")
            return False

    def create_datasource(self, uid: str, max_retries: int = 5) -> str:
        """Cria e configura COMPLETAMENTE o datasource via API"""
        
        # 🔥 CONFIGURAÇÃO COMPLETA E CORRETA
        datasource_config = {
            "uid": uid,
            "name": "PostgreSQL-Porto-Operacional",
            "type": "postgres",
            "typeName": "PostgreSQL",
            "typeLogoUrl": "public/app/plugins/datasource/postgres/img/postgresql_logo.svg",
            "access": "proxy",
            "url": f"{Config_database.HOST}:{Config_database.PORT}",
            "database": Config_database.DATABASE,
            "user": Config_database.USER,
            "basicAuth": False,
            "isDefault": True,
            "readOnly": False,
            "withCredentials": False,
            
            # 🔑 CRÍTICO: Campos de segurança
            "secureJsonData": {
                "password": Config_database.PASSWORD
            },
            
            # ⚙️ Configurações JSON obrigatórias
            "jsonData": {
                "sslmode": "disable",
                "postgresVersion": 1500,
                "maxOpenConns": 50,
                "maxIdleConns": 25,
                "maxIdleConnsAuto": False,
                "connMaxLifetime": 7200,
                "timescaledb": False,
                "tlsAuth": False,
                "tlsAuthWithCACert": False,
                "tlsConfigurationMethod": "file-path"
            },
            
            # 🏷️ Metadados importantes
            "version": 1
        }
        
        for attempt in range(1, max_retries + 1):
            try:
                logger.info(f"🔄 Tentativa {attempt}/{max_retries} para configurar datasource")
                
                # 1. Remove datasource existente
                try:
                    response = self.api.get(f"/datasources/uid/{uid}")
                    ds_data = response.json()
                    self.api.delete(f"/datasources/{ds_data['id']}")
                    logger.info("🗑️ Datasource anterior removido")
                    time.sleep(2)
                except requests.HTTPError as e:
                    if e.response.status_code == 404:
                        logger.info("📭 Criando novo datasource do zero")
                    else:
                        logger.warning(f"⚠️ Erro ao verificar: {e}")
                
                # 2. Cria novo datasource
                logger.info("🆕 Enviando configuração completa do datasource...")
                response = self.api.post("/datasources", json=datasource_config)
                created_ds = response.json()
                logger.info(f"📄 Datasource criado - ID: {created_ds.get('id')}")
                
                # 3. Aguarda processamento
                logger.info("⏳ Aguardando configuração...")
                time.sleep(5)
                
                # 4. ✅ ATIVAÇÃO COMPLETA (Save & Test automático)
                if self._complete_datasource_activation(uid):
                    logger.info("🎉 Datasource completamente configurado e ativado!")
                    return uid
                else:
                    logger.warning(f"❌ Falha na ativação completa (tentativa {attempt})")
                    if attempt < max_retries:
                        time.sleep(5)
                        
            except Exception as e:
                logger.error(f"💥 Erro na tentativa {attempt}: {e}")
                if attempt >= max_retries:
                    raise RuntimeError(f"Falha final ao criar datasource: {e}")
                time.sleep(5)
        
        raise RuntimeError(f"❌ Não foi possível configurar datasource após {max_retries} tentativas")
    def _complete_datasource_activation(self, ds_uid: str) -> bool:
        """Ativação COMPLETA do datasource (equivalente a preencher todos os campos + Save & Test)"""
        try:
            # 1. Obtém o datasource criado
            response = self.api.get(f"/datasources/uid/{ds_uid}")
            ds_info = response.json()
            ds_id = ds_info["id"]
            
            logger.info(f"🎯 Realizando ativação completa do datasource {ds_uid}")
            
            # 2. Prepara payload de ATIVAÇÃO COMPLETA
            activation_payload = {
                "id": ds_id,
                "uid": ds_uid,
                "name": "PostgreSQL-Porto-Operacional",
                "type": "postgres",
                "typeName": "PostgreSQL",
                "access": "proxy",
                "url": f"{Config_database.HOST}:{Config_database.PORT}",
                "database": Config_database.DATABASE,
                "user": Config_database.USER,
                "basicAuth": False,
                "isDefault": True,
                "readOnly": False,
                "withCredentials": False,
                
                # 🔑 CRÍTICO: Reforça TODOS os campos
                "secureJsonData": {
                    "password": Config_database.PASSWORD
                },
                
                # ⚙️ Configurações COMPLETAS
                "jsonData": {
                    "sslmode": "disable",
                    "postgresVersion": 1500,
                    "maxOpenConns": 50,
                    "maxIdleConns": 25,
                    "maxIdleConnsAuto": False,
                    "connMaxLifetime": 7200,
                    "timescaledb": False,
                    "tlsAuth": False,
                    "tlsAuthWithCACert": False,
                    "tlsConfigurationMethod": "file-path",
                    "enableSecureSocksProxy": False
                },
                
                "version": ds_info.get("version", 1) + 1
            }
            
            # 3. ATUALIZA o datasource (equivalente a preencher todos os campos e clicar "Save & Test")
            logger.info("💾 Salvando configuração completa...")
            update_response = self.api.put(f"/datasources/{ds_id}", json=activation_payload)
            
            if update_response.status_code != 200:
                logger.error(f"❌ Falha ao salvar configuração: {update_response.text}")
                return False
            
            logger.info("✅ Configuração salva com sucesso")
            
            # 4. Aguarda aplicação
            time.sleep(3)
            
            # 5. TESTA a conexão
            logger.info("🧪 Testando conexão...")
            test_result = self._execute_comprehensive_connection_test(ds_uid)
            
            if test_result:
                logger.info("🎊 DataSource completamente ativo e funcional!")
                return True
            else:
                logger.warning("⚠️ DataSource configurado mas teste falhou")
                return False
                
        except Exception as e:
            logger.error(f"💥 Falha na ativação completa: {e}")
            return False
    def _execute_comprehensive_connection_test(self, ds_uid: str) -> bool:
        """Teste de conexão abrangente e realista"""
        test_queries = [
            {
                "name": "Teste de conexão básica",
                "query": "SELECT 1 as test_value, NOW() as timestamp, 'active' as status",
                "min_rows": 1
            },
            {
                "name": "Teste de tabelas do porto", 
                "query": """
                    SELECT 
                        (SELECT COUNT(*) FROM operations) as total_operations,
                        (SELECT COUNT(*) FROM vessels) as total_vessels,
                        (SELECT COUNT(*) FROM berths) as total_berths
                """,
                "min_rows": 1
            },
            {
                "name": "Teste de dados temporais",
                "query": "SELECT NOW() as current_time, EXTRACT(HOUR FROM NOW()) as hour, EXTRACT(MINUTE FROM NOW()) as minute",
                "min_rows": 1
            }
        ]
        
        successful_tests = 0
        
        for test in test_queries:
            try:
                payload = {
                    "queries": [{
                        "refId": "A",
                        "datasource": {"type": "postgres", "uid": ds_uid},
                        "rawSql": test["query"],
                        "format": "table",
                        "intervalMs": 60000
                    }],
                    "from": "now-5m",
                    "to": "now"
                }
                
                response = self.api.post("/ds/query", json=payload)
                result = response.json()
                
                # Verificação robusta da resposta
                if "results" in result and "A" in result["results"]:
                    query_result = result["results"]["A"]
                    
                    if not query_result.get("error"):
                        # Verifica se tem dados
                        frames = query_result.get("frames", [])
                        if frames and len(frames) > 0:
                            data = frames[0].get("data", {})
                            values = data.get("values", [])
                            
                            if len(values) > 0 and len(values[0]) >= test["min_rows"]:
                                successful_tests += 1
                                logger.info(f"✅ {test['name']} - OK")
                                continue
                
                logger.warning(f"⚠️ {test['name']} - Resposta inválida ou sem dados")
                
            except Exception as e:
                logger.warning(f"⚠️ {test['name']} - Erro: {str(e)[:100]}")
        
        # Requer pelo menos 2 testes bem-sucedidos
        return successful_tests >= 2

    def verify_datasource_status(self, ds_uid: str) -> Dict[str, Any]:
        """Verifica status detalhado do datasource"""
        try:
            response = self.api.get(f"/datasources/uid/{ds_uid}")
            ds_info = response.json()
            
            status = {
                "configured": True,
                "name": ds_info.get("name"),
                "type": ds_info.get("type"),
                "url": ds_info.get("url"),
                "database": ds_info.get("database"),
                "user": ds_info.get("user"),
                "isDefault": ds_info.get("isDefault", False),
                "jsonData": ds_info.get("jsonData", {}),
                "missing_fields": []
            }
            
            # Verifica campos obrigatórios
            required_fields = ["name", "type", "url", "database", "user"]
            for field in required_fields:
                if not ds_info.get(field):
                    status["missing_fields"].append(field)
            
            # Testa conexão
            status["connection_test"] = self._execute_comprehensive_connection_test(ds_uid)
            
            return status
            
        except Exception as e:
            return {
                "configured": False,
                "error": str(e),
                "missing_fields": ["all"],
                "connection_test": False
            }



    @lru_cache(maxsize=1)
    def get_queries(self) -> Dict[str, str]:
        """Queries SQL otimizadas"""
        return {
            "Eficiência Operacional": """
                SELECT
                    DATE_TRUNC('minute', start_time) + INTERVAL '3 min' * FLOOR(EXTRACT('minute' FROM start_time)::int / 3) as time,
                    ROUND(AVG(CASE WHEN planned_duration > 0 THEN LEAST(100.0, (planned_duration::float / NULLIF(actual_duration, 0)) * 100) ELSE NULL END)::numeric, 1) as value
                FROM operations
                WHERE start_time >= $__timeFrom() AND start_time <= $__timeTo() AND status = 'completed'
                GROUP BY 1
                ORDER BY 1
            """,
            "Navios atendidos": """
                SELECT COUNT(*) as value 
                FROM operations 
                WHERE status = 'completed' AND start_time >= $__timeFrom() AND start_time <= $__timeTo()
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
                    ROUND((COUNT(CASE WHEN status = 'occupied' THEN 1 END) * 100.0 / NULLIF(COUNT(*), 0)), 2) as value
                FROM berths
            """,
            "Tempo de espera na fila": """
                SELECT
                    TO_CHAR(CAST(COALESCE(MIN(EXTRACT(EPOCH FROM (start_service_time - arrival_time))), 0) * INTERVAL '1 second' AS INTERVAL), 'HH24:MI:SS') AS min_wait_time,
                    TO_CHAR(CAST(COALESCE(AVG(EXTRACT(EPOCH FROM (start_service_time - arrival_time))), 0) * INTERVAL '1 second' AS INTERVAL), 'HH24:MI:SS') AS avg_wait_time,
                    TO_CHAR(CAST(COALESCE(MAX(EXTRACT(EPOCH FROM (start_service_time - arrival_time))), 0) * INTERVAL '1 second' AS INTERVAL), 'HH24:MI:SS') AS max_wait_time
                FROM vessel_queue
                WHERE status = 'completed' AND start_service_time IS NOT NULL AND arrival_time IS NOT NULL
            """,
            "Estado na Alfandega": """
                SELECT 
                    v.vessel_name, 
                    c.status, 
                    TO_CHAR(c.last_update, 'YYYY-MM-DD HH24:MI:SS') AS last_update
                FROM customs_clearance c
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
    
    def create_panels(self, ds_uid: str) -> List[Dict[str, Any]]:
        """Cria todos os painéis do dashboard"""
        queries = self.get_queries()
        panels = []
        
        panel_configs = [
            ("Eficiência Operacional", "stat", {"unit": "percent", "max_val": 100, "decimals": 1}, "efficiency"),
            ("Navios atendidos", "stat", {"unit": "short", "min_val": 0}, "efficiency"),
            ("Navios à Espera", "stat", {"unit": "short", "min_val": 0}, "waiting"),
            ("Cais Ocupados", "stat", {"unit": "short", "min_val": 0}, "occupation"),
            ("Percentagem de ocupação dos Cais", "stat", {"unit": "percent", "max_val": 100, "decimals": 1}, "occupation"),
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
        
        logger.info(f"✅ Criados {len(panels)} painéis")
        return panels
    
    def create_dashboard(self, config: DashboardConfig, panels: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Cria ou atualiza dashboard com configuração completa"""
        panels = LayoutManager.apply(panels)
        
        dashboard_payload = {
            "dashboard": {
                "uid": config.uid,
                "title": config.title,
                "tags": config.tags,
                "timezone": "browser",
                "panels": panels,
                "time": {"from": config.time_from, "to": config.time_to},
                "refresh": config.refresh,
                "schemaVersion": 36,
                "version": 1,
                "editable": True,
                "graphTooltip": 1,
                "timepicker": {},
                "links": []
            },
            "overwrite": True,
            "message": f"Dashboard atualizado automaticamente em {datetime.now().isoformat()}"
        }
        
        response = self.api.post("/dashboards/db", json=dashboard_payload)
        result = response.json()
        
        logger.info(f"📊 Dashboard '{config.title}' criado/atualizado com sucesso")
        logger.info(f"🔗 URL: {result.get('url', 'N/A')}")
        
        return result





def execute():
    """Função principal otimizada"""
    logger.info("🚀 Iniciando configuração automática do Dashboard...")
    
    try:
        # Gera token
        token_manager = GrafanaTokenManager()
        api_key = token_manager.execute_workflow()
        
        # Conecta ao Grafana
        api = GrafanaAPI(Config_grafana.URL, api_key)
        manager = DashboardManager(api)
        
        # ✅ Cria e ATIVA o datasource (sem necessidade de "Save & Test" manual)
        logger.info("🔌 Criando e ativando datasource PostgreSQL...")
        ds_uid = manager.create_datasource("postgres-porto-uid")
        
        # Cria painéis e dashboard
        logger.info("📊 Configurando painéis...")
        panels = manager.create_panels(ds_uid)
        
        config = DashboardConfig(
            title="Dashboard Operacional do Porto", 
            uid="Porto", 
            time_from="now-7d", 
            refresh="10s",
            tags=["automated", "porto", "operacional", "real-time"]
        )
        
        manager.create_dashboard(config, panels)
        
        # Mensagem final
        print(f"\n{'='*70}")
        print("🎉 CONFIGURAÇÃO 100% AUTOMÁTICA CONCLUÍDA!")
        print("✅ DataSource ativado automaticamente")
        print("✅ Painéis configurados e funcionais") 
        print("✅ Nenhuma ação manual necessária")
        print(f"📊 Dashboard: {config.title}")
        print(f"🔗 URL: {Config_grafana.URL}/d/{config.uid}")
        print(f"{'='*70}\n")
        
        return 0
        
    except Exception as e:
        logger.error(f"💥 Erro crítico na configuração: {e}")
        return 1

if __name__ == "__main__":
    exit_code = execute()
    if exit_code == 0:
        logger.info("🎯 Iniciando simulação de dados...")
        simulator = PortDataSimulator()
        simulator.run_simulation()
    else:
        logger.error("❌ Configuração falhou, simulação não iniciada")
        sys.exit(exit_code)