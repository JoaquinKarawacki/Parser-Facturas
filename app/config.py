"""
config.py
Configuración centralizada de la aplicación.
Lee variables de entorno con valores por defecto seguros.
"""

import os
import logging
from dataclasses import dataclass, field
from typing import Set


@dataclass
class Configuracion:
    """
    Parámetros de configuración leídos desde variables de entorno.
    Compatibles con Railway y .env local.
    """

    # Archivos
    limite_tamano_mb: int = field(
        default_factory=lambda: int(os.getenv("LIMITE_TAMANO_MB", "20"))
    )
    extensiones_permitidas: Set[str] = field(
        default_factory=lambda: set(
            os.getenv("EXTENSIONES_PERMITIDAS", ".pdf").split(",")
        )
    )

    # Logging
    nivel_log: str = field(
        default_factory=lambda: os.getenv("NIVEL_LOG", "INFO").upper()
    )

    # Railway / servidor
    puerto: int = field(
        default_factory=lambda: int(os.getenv("PORT", "8000"))
    )
    host: str = field(
        default_factory=lambda: os.getenv("HOST", "0.0.0.0")
    )
    workers: int = field(
        default_factory=lambda: int(os.getenv("WORKERS", "1"))
    )

    @property
    def limite_tamano_bytes(self) -> int:
        return self.limite_tamano_mb * 1024 * 1024

    def configurar_logging(self) -> None:
        """Inicializa el sistema de logging de la aplicación."""
        nivel = getattr(logging, self.nivel_log, logging.INFO)
        logging.basicConfig(
            level=nivel,
            format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        # Silenciar loggers ruidosos de librerías externas
        logging.getLogger("pdfminer").setLevel(logging.WARNING)
        logging.getLogger("pdfplumber").setLevel(logging.WARNING)
        logging.getLogger("urllib3").setLevel(logging.WARNING)
        logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


# Instancia global
configuracion = Configuracion()
