"""
run.py
Punto de entrada para desarrollo local.
En producción (Railway), usar el Procfile.
"""
import uvicorn
from app.config import configuracion

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=configuracion.host,
        port=configuracion.puerto,
        reload=True,
        log_level=configuracion.nivel_log.lower(),
    )
