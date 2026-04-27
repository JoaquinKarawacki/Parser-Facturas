"""
normalizer.py
Convierte cadenas extraídas del PDF a tipos de datos correctos.
Maneja formatos latinos (coma decimal, punto separador de miles) y anglosajones.
"""

import re
import logging
from typing import Optional, Union

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────
# Normalización numérica
# ──────────────────────────────────────────────────────────────

def normalizar_numero(valor: Optional[str]) -> Optional[float]:
    """
    Convierte una cadena a float con soporte para formatos:
    - Latino:     "1.234,56"  →  1234.56
    - Anglosajón: "1,234.56"  →  1234.56
    - Simple:     "1234"      →  1234.0
    - Con símbolo:"$1.234,56" →  1234.56
    Retorna None si no se puede convertir.
    """
    if valor is None:
        return None

    texto = str(valor).strip()

    # Eliminar símbolos de moneda, espacios, asteriscos
    texto = re.sub(r"[€$£¥\s*]", "", texto)

    if not texto:
        return None

    # Detectar formato: si hay coma Y punto, determinar cuál es decimal
    tiene_punto = "." in texto
    tiene_coma = "," in texto

    try:
        if tiene_punto and tiene_coma:
            # El último separador es el decimal
            ultimo_punto = texto.rfind(".")
            ultima_coma = texto.rfind(",")
            if ultima_coma > ultimo_punto:
                # Formato latino: 1.234,56
                texto = texto.replace(".", "").replace(",", ".")
            else:
                # Formato anglosajón: 1,234.56
                texto = texto.replace(",", "")
        elif tiene_coma and not tiene_punto:
            # Puede ser separador de miles "1,234" o decimal "1,56"
            partes = texto.split(",")
            if len(partes) == 2 and len(partes[1]) <= 2:
                # Probablemente decimal: "1,56" → "1.56"
                texto = texto.replace(",", ".")
            else:
                # Separador de miles: "1,234" → "1234"
                texto = texto.replace(",", "")
        elif tiene_punto and not tiene_coma:
            # Puede ser separador de miles "1.234" o decimal "1.56"
            partes = texto.split(".")
            if len(partes) == 2 and len(partes[1]) == 3:
                # Probablemente miles: "1.234" → "1234"
                texto = texto.replace(".", "")
            # Si no, lo dejamos como está (decimal anglosajón)

        return float(texto)

    except (ValueError, AttributeError):
        logger.debug(f"No se pudo normalizar el número: '{valor}'")
        return None


def normalizar_entero(valor: Optional[str]) -> Optional[int]:
    """Convierte a int, pasando primero por normalizar_numero."""
    num = normalizar_numero(valor)
    if num is None:
        return None
    return int(round(num))


# ──────────────────────────────────────────────────────────────
# Normalización de texto
# ──────────────────────────────────────────────────────────────

def normalizar_texto(valor: Optional[str]) -> Optional[str]:
    """Limpia espacios múltiples, saltos de línea y caracteres de control."""
    if valor is None:
        return None
    texto = str(valor)
    texto = re.sub(r"[\r\n\t]+", " ", texto)
    texto = re.sub(r"\s{2,}", " ", texto)
    return texto.strip() or None


def normalizar_fecha(valor: Optional[str]) -> Optional[str]:
    """
    Intenta normalizar fechas al formato ISO (YYYY-MM-DD).
    Soporta varios formatos comunes en facturas latinoamericanas.
    Retorna la cadena original si no puede parsear.
    """
    if valor is None:
        return None

    texto = str(valor).strip()

    MESES = {
        "ene": "01", "feb": "02", "mar": "03", "abr": "04",
        "may": "05", "jun": "06", "jul": "07", "ago": "08",
        "sep": "09", "oct": "10", "nov": "11", "dic": "12",
        "enero": "01", "febrero": "02", "marzo": "03", "abril": "04",
        "mayo": "05", "junio": "06", "julio": "07", "agosto": "08",
        "septiembre": "09", "octubre": "10", "noviembre": "11", "diciembre": "12",
        "january": "01", "february": "02", "march": "03", "april": "04",
        "june": "06", "july": "07", "august": "08",
        "september": "09", "october": "10", "november": "11", "december": "12",
        "jan": "01", "apr": "04", "jun": "06", "jul": "07", "aug": "08",
        "sep": "09", "oct": "10", "nov": "11", "dec": "12",
    }

    patrones = [
        # DD/MM/YYYY o DD-MM-YYYY
        (r"(\d{1,2})[\/\-\.](\d{1,2})[\/\-\.](\d{4})", "dmy"),
        # YYYY/MM/DD o YYYY-MM-DD
        (r"(\d{4})[\/\-\.](\d{1,2})[\/\-\.](\d{1,2})", "ymd"),
        # DD de Mes de YYYY
        (r"(\d{1,2})\s+de\s+(\w+)\s+de\s+(\d{4})", "dmy_texto"),
        # Mes DD, YYYY
        (r"(\w+)\s+(\d{1,2})[,\s]+(\d{4})", "mdy_texto"),
    ]

    for patron, formato in patrones:
        m = re.search(patron, texto, re.IGNORECASE)
        if not m:
            continue
        try:
            if formato == "dmy":
                return f"{m.group(3)}-{m.group(2).zfill(2)}-{m.group(1).zfill(2)}"
            elif formato == "ymd":
                return f"{m.group(1)}-{m.group(2).zfill(2)}-{m.group(3).zfill(2)}"
            elif formato == "dmy_texto":
                mes = MESES.get(m.group(2).lower())
                if mes:
                    return f"{m.group(3)}-{mes}-{m.group(1).zfill(2)}"
            elif formato == "mdy_texto":
                mes = MESES.get(m.group(1).lower())
                if mes:
                    return f"{m.group(3)}-{mes}-{m.group(2).zfill(2)}"
        except Exception:
            continue

    # Retornar el texto original si no se pudo parsear
    return normalizar_texto(texto)


# ──────────────────────────────────────────────────────────────
# Normalización por tipo de campo
# ──────────────────────────────────────────────────────────────

# Define qué campos son numéricos y cuáles son texto/fecha
CAMPOS_NUMERICOS = {
    "potencia_contratada_punta_llano_kw",
    "potencia_contratada_valle_kw",
    "consumo_activo_kwh",
    "consumo_reactivo_kvarh",
    "total_detalle_facturacion",
    "energa_llano_factor",
    "energa_llano_lect_act",
    "energa_llano_lect_ant",
    "energa_llano_total",
    "energa_punta_factor",
    "energa_punta_lect_act",
    "energa_punta_lect_ant",
    "energa_punta_total",
    "energa_reactiva_factor",
    "energa_reactiva_lect_act",
    "energa_reactiva_lect_ant",
    "energa_reactiva_total",
    "energa_valle_factor",
    "energa_valle_lect_act",
    "energa_valle_lect_ant",
    "energa_valle_total",
    "npags_pdf",
    "potencia_factor",
    "potencia_lect_act",
    "potencia_lect_ant",
    "potencia_total",
    "potencia_valle_factor",
    "potencia_valle_lect_act",
    "potencia_valle_lect_ant",
    "potencia_valle_total",
}

CAMPOS_FECHA = {
    "fecha_emision",
    "prox_vencimiento",
}

CAMPOS_ENTEROS = {
    "npags_pdf",
    "fases",
}


def normalizar_campo(nombre_campo: str, valor: Optional[str]) -> Union[float, int, str, None]:
    """
    Aplica la normalización correcta según el tipo de campo.
    """
    if valor is None or str(valor).strip() == "":
        return None

    if nombre_campo in CAMPOS_FECHA:
        return normalizar_fecha(valor)

    if nombre_campo in CAMPOS_ENTEROS:
        return normalizar_entero(valor)

    if nombre_campo in CAMPOS_NUMERICOS:
        return normalizar_numero(valor)

    return normalizar_texto(valor)
