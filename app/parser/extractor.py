"""
extractor.py - Parser UTE adaptado para sistema web.
"""
from __future__ import annotations
import logging, re
from pathlib import Path
import pdfplumber
 
logger = logging.getLogger(__name__)
 
COLUMNAS_SALIDA = [
    "archivo","nro_cuenta","nro_factura","fecha_emision","prox_vencimiento",
    "acuerdo_servicio","nro_medidor","tarifa_aplicada",
    "nombre_cliente","direccion_cliente","localidad_cliente","departamento_cliente",
    "potencia_contratada_punta_llano_kw","potencia_contratada_valle_kw",
    "consumo_activo_kwh","consumo_reactivo_kvarh","tension","fases",
    "direccion_servicio","periodo_consumo","zona_electrica",
    "total_detalle_facturacion",
    "energa_llano_factor","energa_llano_lect_act","energa_llano_lect_ant",
    "energa_llano_tipo_lec","energa_llano_total",
    "energa_punta_factor","energa_punta_lect_act","energa_punta_lect_ant",
    "energa_punta_tipo_lec","energa_punta_total",
    "energa_reactiva_factor","energa_reactiva_lect_act","energa_reactiva_lect_ant",
    "energa_reactiva_tipo_lec","energa_reactiva_total",
    "energa_sal_llano_factor","energa_sal_llano_lect_act","energa_sal_llano_lect_ant",
    "energa_sal_llano_tipo_lec","energa_sal_llano_total",
    "energa_sal_punta_factor","energa_sal_punta_lect_act","energa_sal_punta_lect_ant",
    "energa_sal_punta_tipo_lec","energa_sal_punta_total",
    "energa_sal_valle_factor","energa_sal_valle_lect_act","energa_sal_valle_lect_ant",
    "energa_sal_valle_tipo_lec","energa_sal_valle_total",
    "energa_valle_factor","energa_valle_lect_act","energa_valle_lect_ant",
    "energa_valle_tipo_lec","energa_valle_total",
    "npags_pdf",
    "potencia_factor","potencia_lect_act","potencia_lect_ant",
    "potencia_tipo_lec","potencia_total",
    "potencia_valle_factor","potencia_valle_lect_act","potencia_valle_lect_ant",
    "potencia_valle_tipo_lec","potencia_valle_total",
]
 
DATE_PAT = r"(\d{2}[/-]\d{2}[/-]\d{4})"
NUM_UY   = r"\d{1,3}(?:\.\d{3})*(?:,\d+)?|\d+(?:,\d+)?"
 
def _ns(s): return " ".join((s or "").split())
def _ff(pat, txt, flags=re.I):
    m = re.search(pat, txt, flags)
    return m.group(1).strip() if m else ""
def _nm(s):
    if not s: return ""
    s = str(s).strip().replace(" ","")
    return re.sub(r"[^0-9\.,\-]","",s)
 
def _to_num(value):
    if value is None: return None
    if isinstance(value,(int,float)) and not isinstance(value,bool): return value
    raw = str(value).strip()
    if not raw: return None
    if re.search(r"[A-Za-z]",raw) or " - " in raw or "\u2013" in raw: return value
    c = _nm(raw)
    if not c: return value
    if "," in c: c = c.replace(".","").replace(",",".")
    elif c.count(".")>1: c = c.replace(".","")
    if not re.fullmatch(r"-?\d+(?:\.\d+)?",c): return value
    try:
        n = float(c)
        return int(n) if n.is_integer() else n
    except: return value
 
def _read_all(pdf_path):
    parts=[]
    with pdfplumber.open(pdf_path) as pdf:
        for p in pdf.pages: parts.append(p.extract_text() or "")
    return "\n".join(parts)
 
def _page2(pdf_path):
    with pdfplumber.open(pdf_path) as pdf:
        page = pdf.pages[1] if len(pdf.pages)>1 else pdf.pages[0]
        return page.extract_text() or ""
 
def _recon_tension(raw):
    # Separa números pegados a "kV", y "kV" pegado a palabras
    raw = re.sub(r"(\d)(kV)", r"\1 \2", raw, flags=re.I)
    raw = re.sub(r"(kV)(en|En)", r"\1 \2", raw)
    raw = re.sub(r"(en)(Baja|Alta|Media)", r"\1 \2", raw, flags=re.I)
    raw = re.sub(r"(Baja|Alta|Media)(tensi)", r"\1 \2", raw, flags=re.I)
    # Cortar en "ADT" o "Rural" o "Tipo" para no mezclar con zona
    raw = re.split(r"\s+(?:ADT|Rural|Urbana|Tipo\s+de)", raw, maxsplit=1, flags=re.I)[0]
    return _ns(raw)
 
def _recon_zona(raw):
    raw = re.sub(r"(ADT)(\d)", r"\1 \2", raw)
    raw = re.sub(r"(\d)([-\u2013])([A-Z])", r"\1 \2 \3", raw)
    raw = re.sub(r"([a-z\xe1\xe9\xed\xf3\xfa])([A-Z\xc1\xc9\xcd\xd3\xda])", r"\1 \2", raw)
    raw = re.sub(r"(densidad)(alta|baja|media)", r"\1 \2", raw, flags=re.I)
    raw = re.sub(r"(Urbana)(densidad)", r"\1 \2", raw, flags=re.I)
    raw = re.sub(r"(Rural)(densidad)", r"\1 \2", raw, flags=re.I)
    return _ns(raw)
 
def _group_words(words, ytol=4.0):
    if not words: return []
    lineas=[]
    for w in sorted(words,key=lambda x:(x["top"],x["x0"])):
        if not lineas or abs(w["top"]-lineas[-1][0]["top"])>ytol: lineas.append([w])
        else: lineas[-1].append(w)
    return [_ns(" ".join(x["text"] for x in sorted(l,key=lambda x:x["x0"]))) for l in lineas]
 
def _clean_header(linea):
    linea=_ns(linea)
    linea=re.sub(r"\bHoja\s+\d+\s+de\s+\d+\b","",linea,flags=re.I)
    linea=re.sub(r"\bDETALLE\s+DE\b","",linea,flags=re.I)
    linea=re.sub(r"\bFACTURA\b","",linea,flags=re.I)
    linea=re.sub(r"\b\d{10}\b","",linea)
    linea=re.sub(r"\b\d{2}/\d{2}/\d{4}\b","",linea)
    return _ns(linea)
 
def extract_cliente_ubicacion(pdf_path):
    p2=_page2(pdf_path)
    stops=("DETALLE DE FACTURA","MEDIDOR Nro","MEDIDOR NRO","OFICINA COMERCIAL",
           "Acuerdo de Servicio","Tarifa Aplicada","Direccion del","Período de","Periodo de")
    skips=[re.compile(r"^UTE\b",re.I),re.compile(r"^ADMINISTRACI",re.I),
           re.compile(r"^PARAGUAY\s+\d+",re.I),re.compile(r"^R\.?U\.?T\.?",re.I),
           re.compile(r"^(098|0800|\+?\d{2,})"),re.compile(r"^Hoja\s+\d+",re.I),
           re.compile(r"^\d{2}/\d{2}/\d{4}$"),re.compile(r"^\d{10}$")]
    enc=[]
    try:
        with pdfplumber.open(pdf_path) as pdf:
            page=pdf.pages[1] if len(pdf.pages)>1 else pdf.pages[0]
            words=page.extract_words(use_text_flow=False,keep_blank_chars=False)
        wc=[w for w in words if page.width*0.28<=w["x0"]<=page.width*0.78 and w["top"]<=page.height*0.24]
        for l in _group_words(wc):
            if any(s.lower() in l.lower() for s in stops): break
            if any(p.search(l) for p in skips): continue
            l=_clean_header(l)
            if l: enc.append(l)
    except: enc=[]
    if not enc:
        for l in [_ns(x) for x in p2.splitlines() if _ns(x)]:
            if any(s.lower() in l.lower() for s in stops): break
            if any(p.search(l) for p in skips): continue
            l=_clean_header(l)
            if l: enc.append(l)
    enc=[l for l in enc if not re.fullmatch(r"(DETALLE|DE|FACTURA)(\s+(DETALLE|DE|FACTURA))*",l,re.I)]
    nombre=enc[0] if enc else ""
    direccion=enc[1] if len(enc)>1 else ""
    localidad=departamento=""
    idx=None
    for i,l in enumerate(enc[2:],start=2):
        if re.search(r"\s-\s*CP\b|\bCP\s*\d",l,re.I): idx=i; break
    if idx is not None:
        localidad=enc[idx]
        post=enc[idx+1:]; departamento=post[-1] if post else ""
    else:
        if len(enc)>2: localidad=enc[2]
        if len(enc)>3: departamento=enc[-1]
    if localidad:
        localidad=re.split(r"\s-\s*CP\b|\bCP\s*\d",localidad,maxsplit=1,flags=re.I)[0]
        localidad=_ns(localidad)
 
    # FIX: Si localidad no se extrajo por coordenadas, buscar en texto de página 1
    if not localidad:
        at = _read_all(pdf_path)
        m = re.search(r"([A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑ\s]+)\s*-\s*CP\s*\d", at)
        if m: localidad = _ns(m.group(1))
 
    if not departamento and localidad.upper() in ("MONTEVIDEO","TACUAREMBO","TACUAREMBÓ",
        "MALDONADO","SALTO","PAYSANDU","PAYSANDÚ","RIVERA","ROCHA","FLORIDA","FLORES",
        "COLONIA","SAN JOSE","SAN JOSÉ","SORIANO","RIO NEGRO","RÍO NEGRO","ARTIGAS",
        "LAVALLEJA","TREINTA Y TRES","CERRO LARGO","DURAZNO","CANELONES"):
        departamento = localidad
 
    return {"nombre_cliente":nombre,"direccion_cliente":direccion,
            "localidad_cliente":localidad,"departamento_cliente":departamento}
 
def extract_total(pdf_path):
    p2=_page2(pdf_path); at=_read_all(pdf_path)
    pats=[re.compile(r"DETALLE\s+DE\s+FACTURACION[\s\S]{0,2500}?\bTOTAL\b\s*("+NUM_UY+r")",re.I),
          re.compile(r"DETALLE\s+DE\s+FACTURACION[\s\S]{0,2500}?\nTOTAL\s+("+NUM_UY+r")",re.I)]
    for txt in [p2,at]:
        for pat in pats:
            m=pat.search(txt)
            if m: return _nm(m.group(1))
    return ""
 
def extract_cuadro_superior(pdf_path, archivo):
    at=_read_all(pdf_path); p2=_page2(pdf_path)
    cliente=extract_cliente_ubicacion(pdf_path)
    total=extract_total(pdf_path)
 
    nro_cuenta=_ff(r"\b(\d{10})\b",p2) or _ff(r"\b(\d{10})\b",at)
    acuerdo=(_ff(r"Acuerdo\s+de\s+[Ss]ervicio\s+(\d{7,12})",p2) or
             _ff(r"Acuerdo\s+de\s+[Ss]ervicio[:\s]+(\d{7,12})",at))
    nro_medidor=(_ff(r"MEDIDOR\s+Nro\.?\s*(\d+)",p2) or
                 _ff(r"Nro\.\s*Medidor\s+(\d+)",p2) or
                 _ff(r"MEDIDOR\s+Nro\.?\s*(\d+)",at))
 
    nro_factura=fecha_emision=prox_venc=""
    ml=re.search(r"\b([A-Z])\s*(\d{6,10})\s+"+DATE_PAT+r"\s+"+DATE_PAT+r"\b",at)
    if ml:
        nro_factura=f"{ml.group(1)} {ml.group(2)}"; fecha_emision=ml.group(3); prox_venc=ml.group(4)
    else:
        mnf=re.search(r"\b([A-Z])\s*(\d{6,10})\b",at)
        if mnf: nro_factura=f"{mnf.group(1)} {mnf.group(2)}"
 
    # Tarifa - buscar en p2 tabla y en p1 texto libre
    tarifa=""
    mt=re.search(r"Tarifa\s+Aplicada\s+([^\n]+)",p2,re.I)
    if mt: tarifa=_ns(mt.group(1))
    if not tarifa:
        mt=re.search(r"([A-Za-z\xc0-\xff][^\n]{3,})\n\s*Tarifa\s+Aplicada\s*\n([^\n]*)",p2,re.I)
        if mt:
            p1b=_ns(mt.group(1)); p2b=re.split(r"Direcci|Potencia|Consumo",mt.group(2))[0]
            tarifa=_ns((p1b+" "+p2b).strip(" -"))
    if not tarifa: tarifa=_ns(_ff(r"Tarifa:\s*(.+?)(?=\n|Potencia|$)",at))
    # Limpiar tarifa: quitar texto de dirección pegado (ej: "GranConsumidor RUTAGOMEZ...")
    if tarifa:
        import re as _re
        tarifa = _re.split(r"\s+[A-Z]{2,}(?:[A-Z,\.\d]+){3,}", tarifa)[0]
        tarifa = _re.sub(r"([a-z\xf3\xf1\xe9\xed\xfa])([A-Z])", r"\1 \2", tarifa)
        tarifa = _ns(tarifa)
 
    # Consumo Activo
    consumo_activo=""
    for pat in [r"\(kWh\)\s+(\d[\d\.,]*)",r"\(kWh\)\s*\n\s*(\d[\d\.,]*)",
                r"Consumo\s+Activo\s*\n?\s*\(kWh\)\s+(\d[\d\.,]*)"]:
        m=re.search(pat,p2)
        if m: consumo_activo=_nm(m.group(1)); break
    if not consumo_activo: consumo_activo=_nm(_ff(r"Consumo\s+Activo[^\d]*(\d[\d\.,]*)",at))
 
    # Consumo Reactivo
    consumo_reactivo=""
    for pat in [r"Consumo\s+Reactiv[ao]\s*\n?\s*\(kVArh\)\s+(\d[\d\.,]*)",
                r"(\d[\d\.,]*)\s+\d[\d\.,]*\s+\d{2}/\d{2}/\d{4}[^\n]*\n[^\n]*\(kVArh\)",
                r"(\d[\d\.,]*)\s*\n\s*\(kVArh\)",r"\(kVArh\)\s+(\d[\d\.,]*)"]:
        m=re.search(pat,p2,re.I)
        if m: consumo_reactivo=_nm(m.group(1)); break
    if not consumo_reactivo: consumo_reactivo="0"
 
    # Potencia Punta-Llano
    PP=r"\d+(?:[,\.]\d+)?\s*[-\u2013]\s*\d+(?:[,\.]\d+)?"
    pot_punta_llano=""
    for pat in [r"Punta\s*[–\-]\s*Llano\s*\(kW\)\s*("+PP+r")",
                r"Punta\s*[–\-]\s*Llano\s*\(kW\)\s*\n\s*("+PP+r")",
                r"("+PP+r")[^\n]*\n[^\n]*Punta\s*[–\-]\s*Llano"]:
        m=re.search(pat,p2,re.I)
        if m: pot_punta_llano=_ns(m.group(1)); break
    if not pot_punta_llano:
        m=re.search(r"Punta\s*[–\-]\s*Llano\s*\(kW\)[:\s]*("+PP+r")",at,re.I)
        if m: pot_punta_llano=_ns(m.group(1))
 
    # FIX: Potencia Contratada Valle - en p2 la línea dice "(kVArh) Valle (kW) Consumo"
    # y el valor 5000 está en la línea anterior como "345144 5000 28/02/2026a31/03/2026"
    pot_valle=""
    # Patrón nuevo: número seguido de "Potencia Contratada Valle (kW)" o similar en tabla
    m=re.search(r"Potencia\s+Contratada\s*\n?\s*Valle\s*\(kW\)\s+(\d[\d\.,]*)",p2,re.I)
    if m: pot_valle=_nm(m.group(1))
    if not pot_valle:
        # En este formato: "345144 5000 28/02/2026..." con "(kVArh) Valle (kW)" en la sig. línea
        m=re.search(r"\d[\d\.,]*\s+(\d[\d\.,]*)\s+\d{2}[/\-]\d{2}[/\-]\d{4}[^\n]*\n[^\n]*Valle\s*\(kW\)",p2,re.I)
        if m: pot_valle=_nm(m.group(1))
    if not pot_valle:
        m=re.search(r"Valle\s*\(kW\)\s+(\d[\d\.,]*)",p2,re.I)
        if m: pot_valle=_nm(m.group(1))
    if not pot_valle: pot_valle="0"
 
    # FIX: Tensión - separar de zona que viene pegada
    # Línea real: "Nro. Medidor 00816206898 Tensión 31,5kVenMediatensión ADT5-Ruraldensidadbaja"
    tension=""
    m=re.search(r"Tensi[o\xf3]n\s+([\d,\.]+\s*kV[^\n]+?)(?=\s*(?:Tipo\s+de\s+Zona|\n|$))",p2,re.I)
    if m: tension=_recon_tension(m.group(1))
    if not tension:
        m=re.search(r"Tensi[o\xf3]n\s+(.+?)(?=\n)",p2,re.I)
        if m: tension=_recon_tension(m.group(1))
 
    fases=(_ns(_ff(r"Fases?\s+([\w\xe1\xe9\xed\xf3\xfa]+)",p2)) or
           _ns(_ff(r"Fases?\s*[:\-]?\s*([^\n]+)",at)))
 
    # Dirección del servicio
    direccion=""
    # FIX: en p2 el campo viene pegado "RUTAGOMEZ,26GRAL.LEANDRO" → usar palabras
    m=re.search(r"Direcci[o\xf3]n\s+del\s*\n?\s*[Ss]ervicio\s+([^\n]+)",p2,re.I)
    if m:
        val=_ns(m.group(1))
        # Reconstruir espacios si viene todo pegado
        val=re.sub(r"([a-z\xf3\xf1\xe9\xed\xfa])([A-Z\xd3\xd1\xc9\xcd\xda])",r"\1 \2",val)
        val=re.sub(r"(\d)([A-Z])",r"\1 \2",val)
        direccion=_ns(val)
    if not direccion:
        m=re.search(r"Acuerdo\s+de\s+[Ss]ervicio:\s*\d+[^\n]*\n([\s\S]+?)(?=\nTarifa:)",at,re.I)
        if m:
            ls=[_ns(l) for l in m.group(1).splitlines() if _ns(l)]
            dp=[]
            for l in ls:
                tn=bool(re.search(r'\d',l)); ec=bool(re.match(r'^[A-Z\xc1\xc9\xcd\xd3\xda\xd1\s]+$',l) and 3<len(l)<30)
                if tn and not re.match(r'^(R\.U\.T\.|---+|\.\.\.)',l,re.I):
                    if not re.search(r'(Total|Importe|Concepto|\$|CAE|Rango|Fecha\s+de\s+vto)',l,re.I): dp.append(l)
                elif ec: dp.append(l)
                if len(dp)==3: break
            if dp: direccion=", ".join(dp)
 
    # Período de consumo
    periodo=""
    mp=re.search(r"Per[i\xed]odo\s+de\s*\n?\s*[Cc]onsumo\s+(\d{2}[/\-]\d{2}[/\-]\d{4})\s*a\s*(\d{2}[/\-]\d{2}[/\-]\d{4})",p2,re.I)
    if mp: periodo=f"{mp.group(1)} a {mp.group(2)}"
    if not periodo:
        m=re.search(r"(\d{2}/\d{2}/\d{4})a(\d{2}/\d{2}/\d{4})",p2)
        if m: periodo=f"{m.group(1)} a {m.group(2)}"
    if not periodo:
        m=re.search(DATE_PAT+r"\s*a\s*"+DATE_PAT,at)
        if m: periodo=f"{m.group(1)} a {m.group(2)}"
 
    # FIX: Zona eléctrica - viene pegada a tensión: "31,5kVenMediatensión ADT5-Ruraldensidadbaja"
    zona=""
    m=re.search(r"Tipo\s+de\s*\n?\s*Zona\s*\n?\s*El[e\xe9]ctrica\s*\n?\s*([^\n]+)",p2,re.I)
    if m: zona=_recon_zona(m.group(1))
    if not zona:
        # Buscar en línea de tensión - la zona viene después del texto de tensión
        m=re.search(r"Tensi[o\xf3]n\s+[\d,\.]+\s*kV[^\n]*(ADT\s*\d+[^\n]+)",p2,re.I)
        if m: zona=_recon_zona(m.group(1))
    if not zona:
        m=re.search(r"(ADT\s*\d+[-\u2013][A-Za-z][^\n]+?)(?=\n|\Z)",p2)
        if m: zona=_recon_zona(m.group(1))
    if not zona:
        zona=_ns(_ff(r"(?:Tipo\s+de\s+Zona|Zona\s+El[e\xe9]ctrica)\s*[:\-]?\s*([^\n]+)",at))
 
    return {
        "archivo":archivo,"nro_cuenta":nro_cuenta,"nro_factura":nro_factura,
        "fecha_emision":fecha_emision,"prox_vencimiento":prox_venc,
        "acuerdo_servicio":acuerdo,"nro_medidor":nro_medidor,"tarifa_aplicada":tarifa,
        "potencia_contratada_punta_llano_kw":pot_punta_llano,
        "potencia_contratada_valle_kw":pot_valle,
        "consumo_activo_kwh":consumo_activo,"consumo_reactivo_kvarh":consumo_reactivo,
        "tension":tension,"fases":fases,"direccion_servicio":direccion,
        "periodo_consumo":periodo,"zona_electrica":zona,
        "total_detalle_facturacion":total,
        "nombre_cliente":cliente["nombre_cliente"],
        "direccion_cliente":direccion or cliente["direccion_cliente"],
        "localidad_cliente":cliente["localidad_cliente"],
        "departamento_cliente":cliente["departamento_cliente"],
    }
 
def extract_lecturas_pivotadas(pdf_path):
    at=_read_all(pdf_path)
    with pdfplumber.open(pdf_path) as pdf:
        pt=pdf.pages[1].extract_text() if len(pdf.pages)>1 else (pdf.pages[0].extract_text() or "")
 
    TIPO_PAT=(r"Potencia(?:\s+(?:Punta|Valle|Llano))?"
              r"|Energ[i\xed]a\s+(?:Punta|Valle|Llano|Reactiva(?:\s+Q4)?|sal\.?\s*(?:Punta|Valle|Llano))"
              r"|Energ[i\xed]a\s+[Ss]al\.\s*(?:Punta|Valle|Llano)"
              r"|Punta(?:\s+NO?\s+[Hh][a\xe1]bil(?:es)?)?"
              r"|Fuera\s+de\s+Punta|Valle|Llano|Reactiva(?:\s+Q4)?")
    rp=re.compile(
        rf"(?P<tipo>{TIPO_PAT})\s+(?P<ant>{NUM_UY})\s+(?P<act>{NUM_UY})\s+"
        rf"(?P<factor>\d+)\s+(?P<total>{NUM_UY})\s+(?P<tlec>[A-Za-z\u00C0-\u00FF]+)\b",
        re.I|re.M)
 
    rows=[]; seen=set()
    for src in [pt,at]:
        if rows: break
        for m in rp.finditer(src):
            tipo=_ns(m.group("tipo")); key=(tipo.lower(),m.group("ant"),m.group("act"))
            if key in seen: continue
            seen.add(key)
            rows.append({"tipo":tipo,"lect_ant":_nm(m.group("ant")),"lect_act":_nm(m.group("act")),
                         "factor":m.group("factor"),"total":_nm(m.group("total")),
                         "tipo_lec":_ns(m.group("tlec"))})
 
    # Mapeo: orden importa — más específico primero
    MAPEO=[
        # Potencia
        ("potencia valle",          "potencia_valle"),
        ("potencia punta",          "potencia"),
        ("potencia llano",          "potencia"),
        ("potencia",                "potencia"),
        # Energía Sal. (salida) — más específico antes que genérico
        ("energ\xe9a sal. punta",  "energa_sal_punta"),
        ("energ\xe9a sal. valle",  "energa_sal_valle"),
        ("energ\xe9a sal. llano",  "energa_sal_llano"),
        ("energia sal. punta",      "energa_sal_punta"),
        ("energia sal. valle",      "energa_sal_valle"),
        ("energia sal. llano",      "energa_sal_llano"),
        ("energ\xe9a sal punta",   "energa_sal_punta"),
        ("energ\xe9a sal valle",   "energa_sal_valle"),
        ("energ\xe9a sal llano",   "energa_sal_llano"),
        ("energia sal punta",       "energa_sal_punta"),
        ("energia sal valle",       "energa_sal_valle"),
        ("energia sal llano",       "energa_sal_llano"),
        # Energía genérica
        ("energ\xe9a punta",       "energa_punta"),
        ("energ\xe9a valle",       "energa_valle"),
        ("energ\xe9a llano",       "energa_llano"),
        ("energ\xe9a reactiva",    "energa_reactiva"),
        ("energia punta",           "energa_punta"),
        ("energia valle",           "energa_valle"),
        ("energia llano",           "energa_llano"),
        ("energia reactiva",        "energa_reactiva"),
        ("punta",                   "energa_punta"),
        ("valle",                   "energa_valle"),
        ("llano",                   "energa_llano"),
        ("reactiva",                "energa_reactiva"),
    ]
 
    result={}
    # FIX: Energía Reactiva = suma de Reactiva + Reactiva Q4
    # Primero acumular los totales de reactiva
    reactiva_total_sum = None
 
    for r in rows:
        tl=r["tipo"].lower()
        pref=next((v for k,v in MAPEO if k in tl), None)
        if pref is None:
            cb=re.sub(r"\s+","_",tl); cb=re.sub(r"[^a-z0-9_]","",cb); pref=cb
 
        # Para reactiva, acumular totales de Reactiva + Reactiva Q4
        if pref=="energa_reactiva":
            t=_to_num(r["total"])
            if isinstance(t,(int,float)):
                reactiva_total_sum=(reactiva_total_sum or 0)+t
 
        # Solo escribir si el prefijo no existe aún (el primero gana, salvo reactiva)
        if f"{pref}_lect_ant" not in result:
            result[f"{pref}_lect_ant"]=r["lect_ant"]
            result[f"{pref}_lect_act"]=r["lect_act"]
            result[f"{pref}_factor"]=r["factor"]
            result[f"{pref}_total"]=r["total"]
            result[f"{pref}_tipo_lec"]=r["tipo_lec"]
 
    # Aplicar suma de reactiva si corresponde
    if reactiva_total_sum is not None:
        result["energa_reactiva_total"]=str(int(reactiva_total_sum)) if isinstance(reactiva_total_sum,float) and reactiva_total_sum.is_integer() else str(reactiva_total_sum)
 
    return result
 
def extraer_factura(ruta_pdf: Path) -> dict:
    logger.info(f"Procesando: {ruta_pdf.name}")
    pdf_path=str(ruta_pdf)
    try:
        with pdfplumber.open(pdf_path) as pdf: npags=len(pdf.pages)
    except: npags=0
    try: cuadro=extract_cuadro_superior(pdf_path,ruta_pdf.name)
    except Exception as e:
        logger.error(f"Error cuadro ({ruta_pdf.name}): {e}",exc_info=True); cuadro={"archivo":ruta_pdf.name}
    try: lecturas=extract_lecturas_pivotadas(pdf_path)
    except Exception as e:
        logger.error(f"Error lecturas ({ruta_pdf.name}): {e}",exc_info=True); lecturas={}
    datos={**cuadro,**lecturas,"npags_pdf":npags}
    return _construir_registro(datos)
 
def _construir_registro(datos):
    TEXTO={"archivo","nro_cuenta","nro_medidor","acuerdo_servicio","nro_factura",
           "tarifa_aplicada","tension","fases","direccion_servicio","nombre_cliente",
           "direccion_cliente","localidad_cliente","departamento_cliente",
           "periodo_consumo","zona_electrica","fecha_emision","prox_vencimiento",
           "potencia_contratada_punta_llano_kw"}
    TLEC={c for c in COLUMNAS_SALIDA if c.endswith("_tipo_lec")}
    reg={}
    for col in COLUMNAS_SALIDA:
        v=datos.get(col)
        if col in TEXTO or col in TLEC: reg[col]=str(v).strip() if v not in (None,"") else None
        else: reg[col]=_to_num(v)
    return reg
 
def registro_vacio(nombre_archivo, error):
    d={col:None for col in COLUMNAS_SALIDA}; d["archivo"]=nombre_archivo; d["_error"]=error
    return d
 