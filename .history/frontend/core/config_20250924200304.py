from pathlib import Path
from dotenv import load_dotenv, dotenv_values
import os
from typing import Dict, Any, Optional

# Caminho absoluto relativo à raiz do projeto
BASE_DIR = Path(__file__).resolve().parents[3]  # raiz do projeto

class GrafanaConfig:
    def __init__(self, env_file: Optional[str] = None):
        env_file = Path(env_file or BASE_DIR / "grafana" / "grafana_api_key.txt")

        if env_file.exists():
            print(f"📄 Carregando configurações de: {env_file.resolve()}")
            values = dotenv_values(env_file)
            os.environ.update(values)
        else:
            print(f"⚠️ Arquivo {env_file.resolve()} não encontrado!")

        # Definir variáveis com fallback
        self.URL: str = os.getenv("GRAFANA_URL", "http://grafana_dashboard:3000")
        self.ADMIN_USER: str = os.getenv("GF_SECURITY_ADMIN_USER")
        self.ADMIN_PASSWORD: str = os.getenv("GF_SECURITY_ADMIN_PASSWORD")
        self.SERVICE_NAME: str = os.getenv("SA_NAME", "dashboards-service-v2")
        self.TOKEN_NAME: str = os.getenv("GRAFANA_TOKEN_NAME", "dashboard-token")
        self.API_KEY: Optional[str] = os.getenv("GRAFANA_API_KEY")
        self.WAIT_TIMEOUT: int = int(os.getenv("GRAFANA_WAIT_TIMEOUT", 60))

class DatabaseConfig:
    def __init__(self, env_file: Optional[str] = None):
        env_file = Path(env_file or Path(__file__).parent / ".env")
        load_dotenv(dotenv_path=env_file)

        self.USER: str = os.getenv("POSTGRES_USER")
        self.PASSWORD: str = os.getenv("POSTGRES_PASSWORD")
        self.DATABASE: str = os.getenv("POSTGRES_DB")
        
        # ✅ CORREÇÃO CRÍTICA: No Docker, use 'postgres_database' em vez de 'localhost'
        self.HOST: str = self._get_correct_host()
        self.PORT: int = int(os.getenv("POSTGRES_PORT", 5432))

    def _get_correct_host(self) -> str:
        """Retorna o host correto baseado no ambiente"""
        host = os.getenv("POSTGRES_HOST", "localhost")
        
        # ✅ Se estiver rodando no Docker, use o nome do serviço
        if host == "localhost" and self._is_running_in_docker():
            return "postgres_database"
        return host

    def _is_running_in_docker(self) -> bool:
        """Verifica se está rodando em container Docker"""
        return os.path.exists("/.dockerenv") or os.getenv("DOCKER_CONTAINER") == "true"

    @property
    def connection_string(self) -> str:
        return f"postgresql://{self.USER}:{self.PASSWORD}@{self.HOST}:{self.PORT}/{self.DATABASE}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "user": self.USER,
            "password": self.PASSWORD,
            "database": self.DATABASE,
            "host": self.HOST,
            "port": self.PORT,
            "connection_string": self.connection_string,
        }

# Instâncias globais (singleton)
Config_database = DatabaseConfig()
Config_grafana = GrafanaConfig()