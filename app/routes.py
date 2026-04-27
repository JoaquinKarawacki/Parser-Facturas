"""
routes.py
Endpoints de la API REST para subida de PDFs, procesamiento y descarga del Excel.
"""

import logging
import uuid
from pathlib import Path
from typing import List

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse, JSONResponse, Response

from app.parser.extractor import extraer_factura, registro_vacio, COLUMNAS_SALIDA
from app.services.excel_writer import generar_excel
from app.temp_manager import gestor_temp, DIRECTORIO_TEMP
from app.config import configuracion

logger = logging.getLogger(__name__)
router = APIRouter()


# ──────────────────────────────────────────────────────────────
# Endpoint: subir y procesar PDFs
# ──────────────────────────────────────────────────────────────

@router.post(
    "/procesar",
    summary="Sube facturas PDF y retorna el Excel consolidado",
    response_description="JSON con el ID del Excel generado",
)
async def procesar_facturas(
    archivos: List[UploadFile] = File(..., description="Uno o más archivos PDF de facturas"),
):
    """
    Flujo completo:
    1. Recibe los PDFs
    2. Los guarda temporalmente en /tmp
    3. Extrae datos de cada uno
    4. Genera el Excel consolidado
    5. Elimina los PDFs
    6. Retorna un ID para descargar el Excel
    """
    # ── Validar que hay archivos ─────────────────────────────────
    if not archivos:
        raise HTTPException(status_code=400, detail="No se recibieron archivos.")

    # ── Validar extensión y tamaño ───────────────────────────────
    archivos_validos = []
    errores_validacion = []

    for archivo in archivos:
        nombre = archivo.filename or "sin_nombre"
        extension = Path(nombre).suffix.lower()

        if extension not in configuracion.extensiones_permitidas:
            errores_validacion.append(f"{nombre}: extensión no permitida ({extension}).")
            continue

        contenido = await archivo.read()
        await archivo.seek(0)

        if len(contenido) > configuracion.limite_tamano_bytes:
            errores_validacion.append(
                f"{nombre}: supera el límite de {configuracion.limite_tamano_mb} MB."
            )
            continue

        if not contenido.startswith(b"%PDF"):
            errores_validacion.append(f"{nombre}: no es un PDF válido.")
            continue

        archivos_validos.append((archivo, contenido))

    if not archivos_validos:
        raise HTTPException(
            status_code=400,
            detail=f"Ningún archivo válido. Errores: {'; '.join(errores_validacion)}",
        )

    # ── Guardar PDFs en directorio temporal de sesión ───────────
    directorio_sesion = gestor_temp.crear_directorio_sesion()
    rutas_pdf: List[Path] = []

    try:
        for archivo, contenido in archivos_validos:
            nombre_seguro = _nombre_seguro(archivo.filename)
            ruta = directorio_sesion / nombre_seguro
            ruta.write_bytes(contenido)
            rutas_pdf.append(ruta)
            logger.info(f"PDF guardado temporalmente: {nombre_seguro}")

        # ── Procesar cada PDF ────────────────────────────────────
        registros = []
        errores_procesamiento = []

        for ruta_pdf in rutas_pdf:
            try:
                datos = extraer_factura(ruta_pdf)
                registros.append(datos)
                logger.info(f"Factura procesada: {ruta_pdf.name}")
            except Exception as e:
                logger.error(f"Error procesando {ruta_pdf.name}: {e}", exc_info=True)
                registros.append(registro_vacio(ruta_pdf.name, str(e)))
                errores_procesamiento.append(ruta_pdf.name)

    finally:
        # ── ELIMINAR PDFs inmediatamente ─────────────────────────
        gestor_temp.eliminar_directorio_sesion(directorio_sesion)
        logger.info("PDFs temporales eliminados.")

    # ── Generar Excel ────────────────────────────────────────────
    try:
        bytes_excel = generar_excel(registros)
    except Exception as e:
        logger.error(f"Error generando Excel: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error generando Excel: {e}")

    # ── Guardar Excel temporal con ID único ──────────────────────
    id_excel = uuid.uuid4().hex
    ruta_excel = DIRECTORIO_TEMP / f"{id_excel}.xlsx"
    ruta_excel.write_bytes(bytes_excel)
    gestor_temp.registrar_excel(id_excel, ruta_excel)

    logger.info(f"Excel generado: {ruta_excel.name} ({len(registros)} facturas)")

    respuesta = {
        "estado": "ok",
        "id_excel": id_excel,
        "facturas_procesadas": len(registros),
        "facturas_con_error": errores_procesamiento,
        "advertencias_validacion": errores_validacion,
    }
    return JSONResponse(content=respuesta)


# ──────────────────────────────────────────────────────────────
# Endpoint: descargar Excel
# ──────────────────────────────────────────────────────────────

@router.get(
    "/descargar/{id_excel}",
    summary="Descarga el Excel generado por su ID",
)
def descargar_excel(id_excel: str):
    """
    Descarga el Excel y lo elimina del servidor inmediatamente.
    El archivo solo puede descargarse una vez.
    """
    # Validar ID (solo hex)
    if not id_excel.isalnum() or len(id_excel) != 32:
        raise HTTPException(status_code=400, detail="ID de Excel inválido.")

    ruta = gestor_temp.obtener_ruta_excel(id_excel)
    if not ruta:
        raise HTTPException(
            status_code=404,
            detail="Archivo no encontrado. Puede haber expirado o ya fue descargado.",
        )

    # Leer en memoria ANTES de eliminar, para que el archivo no desaparezca
    # mientras FileResponse intenta enviarlo (causa el Internal Server Error)
    contenido = ruta.read_bytes()
    gestor_temp.eliminar_excel(id_excel)

    return Response(
        content=contenido,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="facturas_consolidadas.xlsx"'},
    )


# ──────────────────────────────────────────────────────────────
# Endpoint: estado del servicio
# ──────────────────────────────────────────────────────────────

@router.get("/estado", summary="Verifica que el servicio está activo")
def estado():
    return {"estado": "activo", "version": "1.0.0"}


# ──────────────────────────────────────────────────────────────
# Utilidades internas
# ──────────────────────────────────────────────────────────────

def _nombre_seguro(nombre: str) -> str:
    """
    Sanitiza el nombre de archivo para evitar path traversal.
    Conserva solo caracteres seguros.
    """
    import re
    nombre = Path(nombre).name  # Elimina cualquier ruta
    nombre = re.sub(r"[^\w\s\-\.]", "_", nombre)
    nombre = nombre[:200]  # Limitar longitud
    return nombre or "factura.pdf"
