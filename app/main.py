"""
main.py
Punto de entrada de la aplicación FastAPI.
Registra rutas, middleware y eventos de ciclo de vida.
"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.config import configuracion
from app.routes import router
from app.temp_manager import gestor_temp

# Configurar logging antes de cualquier otra cosa
configuracion.configurar_logging()
logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────
# Ciclo de vida de la aplicación
# ──────────────────────────────────────────────────────────────

@asynccontextmanager
async def ciclo_vida(app: FastAPI):
    """Acciones al iniciar y apagar la aplicación."""
    logger.info("Iniciando aplicación de extracción de facturas...")
    gestor_temp.limpiar_al_inicio()
    logger.info(f"Límite de tamaño: {configuracion.limite_tamano_mb} MB")
    yield
    logger.info("Apagando aplicación. Limpiando temporales...")
    gestor_temp.limpiar_al_inicio()


# ──────────────────────────────────────────────────────────────
# Aplicación FastAPI
# ──────────────────────────────────────────────────────────────

app = FastAPI(
    title="Extractor de Facturas PDF",
    description=(
        "API para procesamiento de facturas eléctricas en PDF. "
        "Extrae datos estructurados y genera un Excel consolidado."
    ),
    version="1.0.0",
    lifespan=ciclo_vida,
    docs_url="/docs",
    redoc_url="/redoc",
)

# ── CORS ─────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Rutas de la API ──────────────────────────────────────────
app.include_router(router, prefix="/api/v1")

# ── Archivos estáticos (frontend) ───────────────────────────
directorio_static = Path(__file__).parent / "static"
if directorio_static.exists():
    app.mount("/static", StaticFiles(directory=str(directorio_static)), name="static")


# ── Raíz → sirve el frontend ─────────────────────────────────
@app.get("/", include_in_schema=False)
def raiz():
    index = directorio_static / "index.html"
    if index.exists():
        return FileResponse(str(index))
    return {"mensaje": "API de Extracción de Facturas. Ver /docs para la documentación."}
