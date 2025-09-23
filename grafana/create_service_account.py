import os
import sys
import time
from pathlib import Path
from typing import Dict, Any, Optional
import requests
from requests import Session, Response

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.append(str(BASE_DIR / "frontend"))  # Ajusta o caminho para importar 'frontend'

# Importa instâncias já configuradas
try:
    from frontend.core.config import Config_grafana
    print(f"✅ Config carregado: URL={Config_grafana.URL}")
except ImportError as e:
    print(f"❌ Erro: Não foi possível importar configs: {e}")
    sys.exit(1)


class GrafanaTokenManager:
    def __init__(self):
        if not Config_grafana.ADMIN_USER or not Config_grafana.ADMIN_PASSWORD:
            raise ValueError("❌ Credenciais do Grafana não configuradas!")

        self.config: Dict[str, Any] = {
            "wait_timeout": Config_grafana.WAIT_TIMEOUT,
            "env_file": BASE_DIR / "grafana" / "grafana_api_key.txt",
            "grafana_url": Config_grafana.URL,
            "sa_name": Config_grafana.SERVICE_NAME,
            "token_name": Config_grafana.TOKEN_NAME,
            "api_key": Config_grafana.API_KEY,
        }

        self.session = Session()
        self.session.auth = (Config_grafana.ADMIN_USER, Config_grafana.ADMIN_PASSWORD)
        self.session.headers.update({
            "Content-Type": "application/json",
            "Accept": "application/json",
        })

        self.sa_id: Optional[int] = None
        self.api_key: Optional[str] = None

    def _request(self, method: str, path: str, **kwargs) -> Response:
        url = f"{self.config['grafana_url']}{path}"
        resp = self.session.request(method, url, **kwargs)
        resp.raise_for_status()
        return resp

    def wait_for_grafana(self):
        print("⏳ Aguardando inicialização do Grafana...")
        timeout = self.config["wait_timeout"]
        for _ in range(timeout):
            try:
                r = self._request("GET", "/api/health", timeout=5)
                if r.ok:
                    print("✅ Grafana está operacional")
                    return
            except Exception:
                time.sleep(1)
        raise TimeoutError("Timeout excedido aguardando Grafana")

    def get_service_account_id(self) -> Optional[int]:
        r = self._request("GET", "/api/serviceaccounts/search",
                          params={"query": self.config["sa_name"]})
        for acc in r.json().get("serviceAccounts", []):
            if acc.get("name") == self.config["sa_name"]:
                return acc.get("id")
        return None

    def create_service_account(self) -> int:
        print(f"📌 Verificando service account: {self.config['sa_name']}")
        self.sa_id = self.get_service_account_id()
        if self.sa_id:
            print(f"ℹ️ Service account já existe (ID: {self.sa_id})")
            return self.sa_id
        r = self._request("POST", "/api/serviceaccounts", json={
            "name": self.config["sa_name"], "role": "Admin"
        })
        return r.json()["id"]

    def get_existing_token_id(self) -> Optional[int]:
        if not self.sa_id:
            return None
        r = self._request("GET", f"/api/serviceaccounts/{self.sa_id}/tokens")
        for token in r.json():
            if token.get("name") == self.config["token_name"]:
                return token.get("id")
        return None

    def _delete_token_by_id(self, token_id: int):
        try:
            self._request("DELETE", f"/api/serviceaccounts/{self.sa_id}/tokens/{token_id}")
        except Exception as e:
            print(f"⚠️ Erro ao remover token: {e}")

    def _validate_token(self, token: str) -> bool:
        if not token:
            return False
        try:
            r = requests.get(f"{self.config['grafana_url']}/api/datasources",
                             headers={"Authorization": f"Bearer {token}"}, timeout=5)
            return r.ok
        except Exception:
            return False

    def create_api_token(self) -> str:
        token = self.config.get("api_key")
        if token and self._validate_token(token):
            print("🔁 Usando token existente válido")
            return token

        existing_id = self.get_existing_token_id()
        if existing_id:
            self._delete_token_by_id(existing_id)

        r = self._request("POST", f"/api/serviceaccounts/{self.sa_id}/tokens", json={
            "name": self.config["token_name"], "role": "Admin"
        })
        token = r.json().get("key")
        if not self._validate_token(token):
            raise ValueError("❌ Token criado inválido")
        self.update_env_file(token)
        return token

    def update_env_file(self, token: str):
        file_path = Path(self.config["env_file"])
        file_path.parent.mkdir(parents=True, exist_ok=True)

        lines = file_path.read_text().splitlines() if file_path.exists() else []
        new_lines = [f"GRAFANA_API_KEY={token}" if line.startswith("GRAFANA_API_KEY=") else line for line in lines]

        if not any(line.startswith("GRAFANA_API_KEY=") for line in new_lines):
            new_lines.append(f"GRAFANA_API_KEY={token}")

        file_path.write_text("\n".join(new_lines) + "\n")
        print(f"📄 Token atualizado em {file_path.resolve()}")

    def execute_workflow(self) -> str:
        self.wait_for_grafana()
        self.sa_id = self.get_service_account_id() or self.create_service_account()
        self.api_key = self.create_api_token()
        print("✅ Token válido disponível")
        return self.api_key


""" 
if __name__ == "__main__":
    try:
        manager = GrafanaTokenManager()
        token = manager.execute_workflow()
        print(f"🔑 Token: {token[:20]}...")
    except Exception as e:
        print(f"❌ Erro: {e}")
        sys.exit(1)

"""

