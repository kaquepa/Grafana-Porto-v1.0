import logging
 
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse  
from fastapi.staticfiles import StaticFiles
from routes.pipeline import router as pipeline_router

# Logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Diretórios
DIR = Path(__file__).resolve().parent
STATIC_DIR = DIR / "static"
TEMPLATES_DIR = DIR / "templates"

# FastAPI
app = FastAPI(
    title="Simulador Portuário API",
    description="API para dashboard e controle de gruas",
    version="1.0.0",
    docs_url="/docs"
)

# Configurar arquivos estáticos
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# CORS para consumo externo (frontend, Grafana, etc)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)

# Middleware para garantir UTF-8 em todas as respostas JSON
@app.middleware("http")
async def ensure_utf8_response(request, call_next):
    response = await call_next(request)
    if response.headers.get("content-type", "").startswith("application/json"):
        response.headers["content-type"] = "application/json; charset=utf-8"
    return response

# Routers
app.include_router(pipeline_router)

