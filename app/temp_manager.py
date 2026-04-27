"""
temp_manager.py
Gestión del ciclo de vida de archivos temporales.
Garantiza la eliminación de PDFs y Excels tras el procesamiento/descarga.
"""

import logging
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# Directorio base para temporales
DIRECTORIO_TEMP = Path("/tmp/factura_extractor")
DIRECTORIO_TEMP.mkdir(parents=True, exist_ok=True)

# Tiempo máximo en segundos para conservar un Excel antes de eliminarlo
TIMEOUT_EXCEL_SEGUNDOS = 300  # 5 minutos


class GestorArchivosTemporales:
    """
    Administra la creación y eliminación automática de archivos temporales.
    Cada sesión de subida recibe un directorio único en /tmp.
    Los Excels generados tienen un timer de expiración.
    """

    def __init__(self):
        self._excels_pendientes: Dict[str, dict] = {}
        self._lock = threading.Lock()
        self._iniciar_limpieza_periodica()

    # ──────────────────────────────────────────────────────
    # Gestión de directorios de sesión
    # ──────────────────────────────────────────────────────

    def crear_directorio_sesion(self) -> Path:
        """
        Crea un directorio único para la sesión de subida actual.
        Formato: /tmp/factura_extractor/<uuid4>/
        """
        id_sesion = uuid.uuid4().hex
        directorio = DIRECTORIO_TEMP / id_sesion
        directorio.mkdir(parents=True, exist_ok=True)
        logger.debug(f"Directorio de sesión creado: {directorio}")
        return directorio

    def eliminar_directorio_sesion(self, directorio: Path) -> None:
        """
        Elimina el directorio de sesión y todos sus archivos.
        Llamado inmediatamente después de procesar los PDFs.
        """
        try:
            if directorio.exists():
                for archivo in directorio.iterdir():
                    archivo.unlink(missing_ok=True)
                directorio.rmdir()
                logger.info(f"Directorio de sesión eliminado: {directorio}")
        except Exception as e:
            logger.warning(f"No se pudo eliminar directorio {directorio}: {e}")

    # ──────────────────────────────────────────────────────
    # Gestión de Excels generados
    # ──────────────────────────────────────────────────────

    def registrar_excel(self, id_excel: str, ruta: Path) -> None:
        """
        Registra un Excel generado con su timestamp de creación.
        Será eliminado automáticamente tras TIMEOUT_EXCEL_SEGUNDOS.
        """
        with self._lock:
            self._excels_pendientes[id_excel] = {
                "ruta": ruta,
                "creado_en": time.time(),
            }
        logger.debug(f"Excel registrado para limpieza: {id_excel}")

    def obtener_ruta_excel(self, id_excel: str) -> Optional[Path]:
        """Retorna la ruta del Excel si todavía existe."""
        with self._lock:
            entrada = self._excels_pendientes.get(id_excel)
            if entrada and entrada["ruta"].exists():
                return entrada["ruta"]
        return None

    def eliminar_excel(self, id_excel: str) -> None:
        """Elimina el Excel y lo desregistra del tracker."""
        with self._lock:
            entrada = self._excels_pendientes.pop(id_excel, None)

        if entrada:
            try:
                ruta = entrada["ruta"]
                if ruta.exists():
                    ruta.unlink()
                    logger.info(f"Excel eliminado tras descarga: {ruta.name}")
            except Exception as e:
                logger.warning(f"No se pudo eliminar Excel {id_excel}: {e}")

    # ──────────────────────────────────────────────────────
    # Limpieza periódica (background thread)
    # ──────────────────────────────────────────────────────

    def _iniciar_limpieza_periodica(self) -> None:
        """Inicia un hilo daemon que elimina Excels expirados cada 60 segundos."""
        hilo = threading.Thread(target=self._bucle_limpieza, daemon=True)
        hilo.start()

    def _bucle_limpieza(self) -> None:
        while True:
            time.sleep(60)
            self._limpiar_excels_expirados()

    def _limpiar_excels_expirados(self) -> None:
        ahora = time.time()
        with self._lock:
            expirados = [
                id_ex for id_ex, datos in self._excels_pendientes.items()
                if ahora - datos["creado_en"] > TIMEOUT_EXCEL_SEGUNDOS
            ]

        for id_ex in expirados:
            logger.info(f"Excel expirado por timeout, eliminando: {id_ex}")
            self.eliminar_excel(id_ex)

    # ──────────────────────────────────────────────────────
    # Limpieza de /tmp al inicio
    # ──────────────────────────────────────────────────────

    def limpiar_al_inicio(self) -> None:
        """Elimina residuos de ejecuciones anteriores en /tmp."""
        try:
            if DIRECTORIO_TEMP.exists():
                for entrada in DIRECTORIO_TEMP.iterdir():
                    if entrada.is_dir():
                        for archivo in entrada.iterdir():
                            archivo.unlink(missing_ok=True)
                        try:
                            entrada.rmdir()
                        except OSError:
                            pass
                    elif entrada.is_file():
                        entrada.unlink(missing_ok=True)
            logger.info("Limpieza inicial de /tmp completada.")
        except Exception as e:
            logger.warning(f"Error en limpieza inicial: {e}")


# Instancia global
gestor_temp = GestorArchivosTemporales()
