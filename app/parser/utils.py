"""
utils.py
Funciones auxiliares: búsqueda por keyword, extracción por regex,
limpieza de texto y utilidades generales del parser.
"""

import re
import logging
from typing import Optional, List, Tuple

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────
# Búsqueda por keyword en bloques de texto
# ──────────────────────────────────────────────────────────────

def buscar_por_keyword(
    texto: str,
    keywords: List[str],
    patron_valor: str = r"[:\s]+(.+?)(?:\n|$)",
    flags: int = re.IGNORECASE,
) -> Optional[str]:
    """
    Busca el valor que sigue a cualquiera de las keywords dadas.

    Ejemplo:
        buscar_por_keyword(texto, ["Nro. Factura", "N° Factura"])
        → Encuentra "Nro. Factura: 0001-00023456" y retorna "0001-00023456"
    """
    for kw in keywords:
        kw_escaped = re.escape(kw)
        patron = kw_escaped + patron_valor
        m = re.search(patron, texto, flags)
        if m:
            valor = m.group(1).strip()
            if valor:
                return valor
    return None


def buscar_patron(
    texto: str,
    patron: str,
    grupo: int = 1,
    flags: int = re.IGNORECASE,
) -> Optional[str]:
    """
    Aplica un patrón regex al texto y retorna el grupo indicado.
    Retorna None si no hay coincidencia.
    """
    m = re.search(patron, texto, flags)
    if m:
        try:
            return m.group(grupo).strip()
        except IndexError:
            return None
    return None


def buscar_todos_patrones(
    texto: str,
    patrones: List[str],
    grupo: int = 1,
    flags: int = re.IGNORECASE,
) -> Optional[str]:
    """
    Intenta cada patrón en orden y retorna el primero que coincida.
    Útil para campos con múltiples formatos posibles.
    """
    for patron in patrones:
        resultado = buscar_patron(texto, patron, grupo, flags)
        if resultado:
            return resultado
    return None


# ──────────────────────────────────────────────────────────────
# Extracción de bloques / secciones
# ──────────────────────────────────────────────────────────────

def extraer_bloque(
    texto: str,
    inicio: str,
    fin: Optional[str] = None,
    flags: int = re.IGNORECASE | re.DOTALL,
) -> Optional[str]:
    """
    Extrae el texto entre dos marcadores (inicio y fin).
    Si fin es None, extrae hasta el final del texto.
    """
    patron_inicio = re.escape(inicio)
    if fin:
        patron_fin = re.escape(fin)
        patron = f"{patron_inicio}(.*?){patron_fin}"
    else:
        patron = f"{patron_inicio}(.*)"

    m = re.search(patron, texto, flags)
    if m:
        return m.group(1).strip()
    return None


def extraer_tabla_por_patron(
    texto: str,
    patron_fila: str,
    flags: int = re.IGNORECASE | re.MULTILINE,
) -> List[Tuple]:
    """
    Extrae múltiples filas de datos usando un patrón con grupos de captura.
    Retorna lista de tuplas con los grupos capturados.
    """
    return re.findall(patron_fila, texto, flags)


# ──────────────────────────────────────────────────────────────
# Limpieza general de texto extraído de PDF
# ──────────────────────────────────────────────────────────────

def limpiar_texto_pdf(texto: Optional[str]) -> str:
    """
    Limpieza estándar para texto extraído de PDF:
    - Elimina caracteres de control
    - Normaliza saltos de línea
    - Colapsa espacios múltiples
    """
    if not texto:
        return ""
    # Normalizar saltos de línea
    texto = texto.replace("\r\n", "\n").replace("\r", "\n")
    # Eliminar caracteres de control excepto \n
    texto = re.sub(r"[^\x20-\x7E\n\xC0-\xFF\u00C0-\u024F]", " ", texto)
    # Colapsar espacios múltiples en la misma línea
    texto = re.sub(r"[ \t]{2,}", " ", texto)
    # Eliminar líneas vacías múltiples
    texto = re.sub(r"\n{3,}", "\n\n", texto)
    return texto.strip()


def unir_lineas_fragmentadas(texto: str, min_longitud: int = 40) -> str:
    """
    Une líneas cortas que probablemente son parte de la misma frase
    (artefacto común en PDFs con columnas).
    """
    lineas = texto.split("\n")
    resultado = []
    buffer = ""

    for linea in lineas:
        linea = linea.strip()
        if not linea:
            if buffer:
                resultado.append(buffer)
                buffer = ""
            resultado.append("")
            continue
        if buffer and len(buffer) < min_longitud:
            buffer += " " + linea
        else:
            if buffer:
                resultado.append(buffer)
            buffer = linea

    if buffer:
        resultado.append(buffer)

    return "\n".join(resultado)


# ──────────────────────────────────────────────────────────────
# Utilidades para valores de lectura eléctrica
# ──────────────────────────────────────────────────────────────

def extraer_lectura_electrica(
    texto: str,
    keyword_seccion: str,
) -> dict:
    """
    Extrae los campos estándar de una sección de lectura eléctrica:
    factor, lect_act, lect_ant, tipo_lec, total.

    Los PDFs de energía suelen presentar tablas con estas columnas.
    """
    resultado = {
        "factor": None,
        "lect_act": None,
        "lect_ant": None,
        "tipo_lec": None,
        "total": None,
    }

    # Intentar extraer el bloque de la sección
    bloque = extraer_bloque(texto, keyword_seccion, fin="\n\n")
    if not bloque:
        bloque = texto

    # Patrón para fila de lectura: Factor | Lect.Act | Lect.Ant | Tipo | Total
    # Adaptado a variaciones comunes en facturas de energía
    patron_fila = (
        r"(\d+[.,]?\d*)"          # factor
        r"\s+(\d+[.,]?\d*)"       # lect_act
        r"\s+(\d+[.,]?\d*)"       # lect_ant
        r"\s+([A-Z]{1,3})"        # tipo_lec
        r"\s+(\d+[.,]?\d*)"       # total
    )

    filas = re.findall(patron_fila, bloque)
    if filas:
        fila = filas[0]
        resultado["factor"] = fila[0]
        resultado["lect_act"] = fila[1]
        resultado["lect_ant"] = fila[2]
        resultado["tipo_lec"] = fila[3]
        resultado["total"] = fila[4]

    return resultado


# ──────────────────────────────────────────────────────────────
# Hash para detección de duplicados
# ──────────────────────────────────────────────────────────────

def calcular_hash_factura(datos: dict) -> str:
    """
    Genera un identificador único basado en campos clave de la factura.
    Usado para detección de duplicados.
    """
    import hashlib
    clave = "|".join([
        str(datos.get("nro_factura", "")),
        str(datos.get("nro_cuenta", "")),
        str(datos.get("fecha_emision", "")),
        str(datos.get("total_detalle_facturacion", "")),
    ])
    return hashlib.md5(clave.encode()).hexdigest()
