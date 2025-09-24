from datetime import datetime
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import os, logging
import psycopg2
from psycopg2 import pool
from psycopg2.extras import DictCursor

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1")

# Templates e estáticos
BASE_DIR = os.path.dirname(os.path.dirname(__file__))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))
router.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")

# Variáveis de ambiente obrigatórias
REQUIRED_ENV = ["POSTGRES_HOST","POSTGRES_PORT","POSTGRES_DB","POSTGRES_USER","POSTGRES_PASSWORD"]
missing = [e for e in REQUIRED_ENV if not os.getenv(e)]
if missing:
    raise RuntimeError(f"Variáveis de ambiente faltando: {', '.join(missing)}")



DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError
# Pool de conexões
try:
    conn_pool = pool.SimpleConnectionPool(minconn=1, maxconn=5, **DB_CONFIG)
except Exception as e:
    raise RuntimeError(f"Erro ao criar pool de conexões: {e}")

@router.get("/", include_in_schema=False, response_class=HTMLResponse)
async def root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@router.get("/estado-cais")
def estado_cais():
    """
    Retorna [{berth_id:int, ocupado:bool}, ...]
    """
    conn = None
    try:
        conn = conn_pool.getconn()
        with conn.cursor(cursor_factory=DictCursor) as cur:
            cur.execute("SELECT berth_id, status FROM berths ORDER BY berth_id;")
            rows = cur.fetchall()
        return [
            {"berth_id": r["berth_id"], "ocupado": r["status"] == "occupied"}
            for r in rows
        ]
    except Exception as e:
        logger.exception("Erro ao buscar estado dos cais")
        raise HTTPException(status_code=500, detail="Erro no banco de dados")
    finally:
        if conn:
            conn_pool.putconn(conn)
