#!/usr/bin/env python3
"""
garita.py — archivo histórico de tiempos de cruce de la frontera.

Guarda cada CAMBIO que publica la API pública de CBP para los ~50 cruces
México–EE.UU. Ese histórico no existe en ningún lado: CBP publica solo el
estado actual y no lo archiva.

Diseñado para correr solo en GitHub Actions. Guarda en CSV (un archivo por
mes) porque así Git puede versionarlo bien; una base binaria inflaría el
repositorio en cada captura.

Sin dependencias. Solo biblioteca estándar de Python 3.9+.

    python garita.py capturar     una lectura   (esto lo corre GitHub solo)
    python garita.py reporte      regenera REPORTE.md
    python garita.py estado       qué hay ahora mismo
"""

import argparse
import csv
import json
import os
import re
import sqlite3
import sys
import urllib.error
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from html.parser import HTMLParser

try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None

API = "https://bwt.cbp.gov/api/waittimes"
DIR_DATOS = "datos"
DIR_HIST = "historico"
# SANDAG publica 3.5 años de promedios DIARIOS de espera. Es la única historia
# que existe antes de que tú empieces a archivar. Se guarda aparte porque es
# promedio diario: sirve para estacionalidad, no para la tabla por hora.
SANDAG = "https://opendata.sandag.org/resource/5tga-nezt.json"
ESTADO = "estado.json"
BITACORA = "bitacora.csv"
REPORTE = "REPORTE.md"
TZ = "America/Tijuana"
AGENTE = "garita-archivador/2.0 (+archivo historico abierto de tiempos de cruce)"

COLUMNAS = ["capturado_utc", "puerto", "frontera", "puerto_nombre", "cruce",
            "clase", "carril", "estado", "minutos", "carriles_abiertos",
            "hora_cbp", "puerto_estado", "sentido"]

# ── SENTIDO SUR ──────────────────────────────────────────────────────────
# CBP solo mide lo que entra a Estados Unidos. El regreso a Tijuana lo mide
# Caltrans con sensores físicos (piloto SANDAG, 95% de exactitud declarada) y
# lo publica en una tabla HTML que NADIE archiva. Ahí está el dato exclusivo.
SUR_URL = "https://quickmap.dot.ca.gov/borderwait.html"
SUR_RUTAS = {
    ("san ysidro", "i-5"):   ("SB-SY-I5",   "San Ysidro sur (I-5)"),
    ("san ysidro", "i-805"): ("SB-SY-I805", "San Ysidro sur (I-805)"),
    ("otay mesa", "905"):    ("SB-OM-905",  "Otay Mesa sur (SR-905)"),
    ("tecate", "94"):        ("SB-TC-94",   "Tecate sur (SR-94)"),
}

# Cruces de la región Tijuana, con el número de puerto verificado contra la API.
# (Ojo: 250301 NO es Tecate, es Calexico East. Tecate es 250501.)
PUERTOS_TJ = {
    "250401": "San Ysidro",
    "250407": "San Ysidro PedWest",
    "250409": "San Ysidro CBX",
    "250601": "Otay Mesa Pasajeros",
    "250602": "Otay Mesa Comercial",
    "250608": "Otay Mesa POE",       # aparece como 'Update Pending': probablemente Otay II
    "250609": "Otay Mesa",           # idem
    "250501": "Tecate",
}

# Cruces que se muestran con tabla de horas en el reporte automático.
DESTACADOS = [("250601", "Otay Mesa Pasajeros"), ("250401", "San Ysidro")]

CLASES = {"passenger_vehicle_lanes": "pasajeros",
          "pedestrian_lanes": "peatones",
          "commercial_vehicle_lanes": "carga"}
CARRILES = {"standard_lanes": "general", "NEXUS_SENTRI_lanes": "sentri",
            "ready_lanes": "ready", "FAST_lanes": "fast"}
DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]


# ---------------------------------------------------------------- utilidades

def a_minutos(valor):
    """CBP manda '90', '', 'N/A' y a veces '1 hr 30 min'. Normaliza a entero."""
    if valor is None:
        return None
    t = str(valor).strip()
    if not t or t.upper() in ("N/A", "NA", "-"):
        return None
    h = re.search(r"(\d+)\s*hr", t, re.I)
    m = re.search(r"(\d+)\s*min", t, re.I)
    if h or m:
        return (int(h.group(1)) * 60 if h else 0) + (int(m.group(1)) if m else 0)
    d = re.findall(r"\d+", t)
    return int(d[0]) if d else None


def a_entero(valor):
    if valor is None:
        return None
    d = re.findall(r"\d+", str(valor))
    return int(d[0]) if d else None


def zona(nombre=TZ):
    if ZoneInfo is None:
        return timezone.utc
    try:
        return ZoneInfo(nombre)
    except Exception:
        return timezone.utc


def bajar(url=API, limite=45):
    pet = urllib.request.Request(url, headers={"User-Agent": AGENTE, "Accept": "application/json"})
    with urllib.request.urlopen(pet, timeout=limite) as r:
        return json.loads(r.read().decode("utf-8", errors="replace"))


SANDAG_PUERTOS = {
    "san_ysidro": ("250401", "San Ysidro"), "otay_mesa": ("250601", "Otay Mesa Pasajeros"),
    "tecate": ("250501", "Tecate"), "calexico_east": ("250301", "Calexico East"),
    "calexico": ("250302", "Calexico"), "andrade": ("250201", "Andrade"),
}


def _sandag_serie(tipo):
    """'Passenger_vehicle_NEXUS_SENTRI_Lane' -> ('pasajeros','sentri')"""
    t = (tipo or "").lower()
    clase = ("peatones" if t.startswith("pedestrian")
             else "carga" if t.startswith("commercial") else "pasajeros")
    carril = ("sentri" if ("nexus" in t or "sentri" in t)
              else "ready" if "ready" in t
              else "fast" if "fast" in t else "general")
    return clase, carril


def importar_sandag(paginas=None, desde_archivo=None):
    """Baja el histórico completo de SANDAG, paginado."""
    if desde_archivo:
        yield from json.load(open(desde_archivo, encoding="utf-8"))
        return
    lote, offset = 10000, 0
    while True:
        url = f"{SANDAG}?$limit={lote}&$offset={offset}&$order=date"
        datos = bajar(url)
        if not datos:
            break
        yield from datos
        if len(datos) < lote:
            break
        offset += lote
        if paginas and offset // lote >= paginas:
            break


def bajar_texto(url, limite=45):
    pet = urllib.request.Request(url, headers={"User-Agent": AGENTE, "Accept": "text/html"})
    with urllib.request.urlopen(pet, timeout=limite) as r:
        return r.read().decode("utf-8", errors="replace")


def aplanar(datos, solo_mexico=False):
    """Convierte el JSON anidado de CBP en renglones planos."""
    for p in datos:
        if not isinstance(p, dict):
            continue
        frontera = (p.get("border") or "").strip()
        if solo_mexico and "Mexic" not in frontera:
            continue
        base = {"puerto": (p.get("port_number") or "").strip(),
                "frontera": frontera,
                "puerto_nombre": (p.get("port_name") or "").strip(),
                "cruce": (p.get("crossing_name") or "").strip(),
                "puerto_estado": (p.get("port_status") or "").strip()}
        if not base["puerto"]:
            continue
        for lc, clase in CLASES.items():
            bloque = p.get(lc)
            if not isinstance(bloque, dict):
                continue
            for lk, carril in CARRILES.items():
                s = bloque.get(lk)
                if not isinstance(s, dict) or not s:
                    continue
                estado = (s.get("operational_status") or "").strip()
                if estado.upper() in ("N/A", "NA", "-"):
                    estado = ""
                minutos = a_minutos(s.get("delay_minutes"))
                abiertos = a_entero(s.get("lanes_open"))
                hora = (s.get("update_time") or "").strip()
                if not estado and minutos is None and abiertos is None and not hora:
                    continue  # carril que ese puerto no tiene
                f = dict(base)
                f.update({"clase": clase, "carril": carril, "estado": estado,
                          "minutos": minutos, "carriles_abiertos": abiertos,
                          "hora_cbp": hora, "sentido": "norte"})
                yield f


class _Tabla(HTMLParser):
    """Extrae las filas de cualquier tabla HTML. Sin dependencias."""
    def __init__(self):
        super().__init__()
        self.filas, self._fila, self._celda, self._dentro = [], [], [], False

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self._fila = []
        elif tag in ("td", "th"):
            self._dentro, self._celda = True, []

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._dentro:
            self._fila.append(" ".join("".join(self._celda).split()))
            self._dentro = False
        elif tag == "tr" and self._fila:
            self.filas.append(self._fila)
            self._fila = []

    def handle_data(self, dato):
        if self._dentro:
            self._celda.append(dato)


def _minutos_sur(txt):
    """Caltrans escribe 'No Wait', '15 min', '1 hr 30 min' o vacío."""
    if not txt:
        return None
    t = txt.strip()
    if not t or t.upper() in ("N/A", "NA", "-", "--"):
        return None
    if "no wait" in t.lower():
        return 0
    return a_minutos(t)


def aplanar_sur(html):
    """Convierte la tabla de Caltrans en renglones. Guarda además los
    pronósticos a +15 y +30 min, para poder medirle la puntería a Caltrans."""
    parser = _Tabla()
    try:
        parser.feed(html)
    except Exception:
        return
    sello = ""
    m = re.search(r"[Ll]ast updated[:\s]*([0-9/]+\s*[0-9:]+\s*[apmAPM\.]*)", html)
    if m:
        sello = m.group(1).strip()
    for fila in parser.filas:
        if len(fila) < 3:
            continue
        puerto_txt = fila[0].lower().strip()
        ruta_txt = fila[1].lower().strip()
        clave = None
        for (p, r), valor in SUR_RUTAS.items():
            if p in puerto_txt and r in ruta_txt.replace("sr-", "").replace("sr ", ""):
                clave = valor
                break
        if not clave:
            continue
        codigo, nombre = clave
        # columna 2 = actual; 3 y 4 = pronóstico a +15 y +30 si vienen
        for i, carril in ((2, "general"), (3, "pron15"), (4, "pron30")):
            if i >= len(fila):
                continue
            minutos = _minutos_sur(fila[i])
            if minutos is None:
                continue
            yield {"puerto": codigo, "frontera": "Mexican Border", "puerto_nombre": nombre,
                   "cruce": nombre, "puerto_estado": "", "clase": "pasajeros",
                   "carril": carril, "estado": "ok", "minutos": minutos,
                   "carriles_abiertos": None, "hora_cbp": sello, "sentido": "sur"}


# ----------------------------------------------------------- almacenamiento

def leer_estado():
    if os.path.exists(ESTADO):
        try:
            return json.load(open(ESTADO, encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def anexar(filas, momento):
    """Agrega al CSV del mes. Un archivo por mes para que Git lo maneje bien."""
    os.makedirs(DIR_DATOS, exist_ok=True)
    ruta = os.path.join(DIR_DATOS, momento[:7] + ".csv")
    nuevo = not os.path.exists(ruta)
    with open(ruta, "a", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        if nuevo:
            w.writerow(COLUMNAS)
        for f in filas:
            w.writerow([momento, f["puerto"], f["frontera"], f["puerto_nombre"], f["cruce"],
                        f["clase"], f["carril"], f["estado"],
                        "" if f["minutos"] is None else f["minutos"],
                        "" if f["carriles_abiertos"] is None else f["carriles_abiertos"],
                        f["hora_cbp"], f["puerto_estado"], f.get("sentido", "norte")])
    return ruta


def cargar_todo():
    """Junta todos los CSV en una base en memoria para poder consultarlos."""
    cx = sqlite3.connect(":memory:")
    cx.row_factory = sqlite3.Row
    cx.execute(f"CREATE TABLE lecturas ({','.join(c + ' TEXT' for c in COLUMNAS)})")
    total = 0
    if os.path.isdir(DIR_DATOS):
        for nombre in sorted(os.listdir(DIR_DATOS)):
            if not nombre.endswith(".csv"):
                continue
            with open(os.path.join(DIR_DATOS, nombre), encoding="utf-8") as fh:
                r = csv.DictReader(fh)
                lote = [[fila.get(c, "") for c in COLUMNAS] for fila in r]
            if lote:
                cx.executemany(f"INSERT INTO lecturas VALUES ({','.join('?' * len(COLUMNAS))})", lote)
                total += len(lote)
    cx.commit()
    return cx, total


def bitacorear(momento, ms, puertos, nuevas, error):
    nuevo = not os.path.exists(BITACORA)
    with open(BITACORA, "a", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        if nuevo:
            w.writerow(["momento_utc", "ms", "puertos", "filas_nuevas", "error"])
        w.writerow([momento, ms, puertos, nuevas, error or ""])


# ------------------------------------------------------------------ análisis

def mediana(v):
    if not v:
        return None
    s = sorted(v)
    n = len(s)
    return float(s[n // 2]) if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


def tabla_horas(cx, puerto, clase="pasajeros", carril="general", tz=None):
    tz = tz or zona()
    filas = cx.execute(
        "SELECT capturado_utc, minutos FROM lecturas WHERE puerto=? AND clase=? AND carril=? "
        "AND minutos<>'' ", (puerto, clase, carril)).fetchall()
    celdas = defaultdict(list)
    for f in filas:
        try:
            local = datetime.fromisoformat(f["capturado_utc"]).astimezone(tz)
        except ValueError:
            continue
        celdas[(local.weekday(), local.hour)].append(int(f["minutos"]))
    return celdas, len(filas)


def md_tabla_horas(celdas, n):
    out = ["| día | " + " | ".join(f"{h:02d}" for h in range(24)) + " |",
           "|---|" + "---|" * 24]
    for d in range(7):
        fila = [DIAS[d][:3]]
        for h in range(24):
            m = mediana(celdas.get((d, h), []))
            fila.append("·" if m is None else str(int(m)))
        out.append("| " + " | ".join(fila) + " |")
    con = {k: mediana(v) for k, v in celdas.items() if v}
    if con:
        mejor = min(con.items(), key=lambda kv: kv[1])
        peor = max(con.items(), key=lambda kv: kv[1])
        out += ["",
                f"**Mejor hora:** {DIAS[mejor[0][0]]} a las {mejor[0][1]:02d}:00 → "
                f"**{int(mejor[1])} min** ({len(celdas[mejor[0]])} lecturas)  ",
                f"**Peor hora:** {DIAS[peor[0][0]]} a las {peor[0][1]:02d}:00 → **{int(peor[1])} min**  ",
                f"**Diferencia:** {int(peor[1] - mejor[1])} minutos entre la mejor y la peor.  ",
                f"*{n:,} lecturas · faltan "
                f"{sum(1 for d in range(7) for h in range(24) if not celdas.get((d, h)))} de 168 casillas.*"]
    return "\n".join(out)


def md_comparacion(cx, clase="pasajeros", carril="general", minimo=3):
    filas = cx.execute(
        "SELECT puerto_nombre, frontera, COUNT(*) n, AVG(CAST(minutos AS INTEGER)) prom, "
        "MIN(CAST(minutos AS INTEGER)) mn, MAX(CAST(minutos AS INTEGER)) mx "
        "FROM lecturas WHERE clase=? AND carril=? AND minutos<>'' "
        "GROUP BY puerto HAVING n>=? ORDER BY prom DESC", (clase, carril, minimo)).fetchall()
    if not filas:
        return "*Todavía no hay suficiente historia para comparar.*"
    out = ["| cruce | frontera | promedio | mínimo | máximo | lecturas |",
           "|---|---|---:|---:|---:|---:|"]
    for f in filas:
        frontera = "México" if "Mexic" in (f["frontera"] or "") else "Canadá"
        out.append(f"| {f['puerto_nombre']} | {frontera} | **{f['prom']:.0f} min** | "
                   f"{f['mn']:.0f} | {f['mx']:.0f} | {f['n']:,} |")
    out.append(f"\n*{len(filas)} cruces. Este cuadro no existe en ninguna otra parte.*")
    return "\n".join(out)


def md_ahora(tz):
    """Todos los cruces de la región Tijuana, con carros, peatonal y carga."""
    est = leer_estado()
    if not est:
        return "*Sin lecturas todavía.*"
    porc = defaultdict(dict)
    for clave, v in est.items():
        puerto, clase, carril = clave.split("|")
        porc[puerto][f"{clase}|{carril}"] = v

    def celda(puerto, clase, carril):
        d = porc.get(puerto, {}).get(f"{clase}|{carril}")
        if not d or d[1] is None:
            return "—"
        abiertos = f" ({d[2]})" if d[2] is not None else ""
        return f"{d[1]} min{abiertos}"

    out = ["| cruce | autos | Ready | SENTRI | peatonal | carga | FAST |",
           "|---|---:|---:|---:|---:|---:|---:|"]
    hay = False
    for puerto, nombre in PUERTOS_TJ.items():
        fila = [celda(puerto, "pasajeros", "general"), celda(puerto, "pasajeros", "ready"),
                celda(puerto, "pasajeros", "sentri"), celda(puerto, "peatones", "general"),
                celda(puerto, "carga", "general"), celda(puerto, "carga", "fast")]
        if all(c == "—" for c in fila):
            continue
        hay = True
        out.append(f"| {nombre} | " + " | ".join(fila) + " |")
    if not hay:
        return "*Sin lecturas de la región Tijuana todavía.*"
    out.append("\n*Entre paréntesis, carriles abiertos.*")
    return "\n".join(out)


def md_rancio(tz):
    """CBP a veces deja de actualizar un puerto y sigue mostrando el mismo número.
    Detectarlo es señal de calidad: si tu dato es viejo, dilo tú antes que el usuario."""
    est = leer_estado()
    if not est:
        return ""
    congelados = defaultdict(list)
    for clave, v in est.items():
        puerto, clase, carril = clave.split("|")
        if puerto in PUERTOS_TJ and v[1] is not None:
            congelados[v[3] or "sin hora"].append(f"{PUERTOS_TJ[puerto]} {clase}/{carril}")
    if len(congelados) <= 1:
        return ""
    viejos = sorted(congelados.items())[:2]
    filas = [f"- `{hora}` → {len(series)} series" for hora, series in viejos if hora != "sin hora"]
    return ("\n**Horas de actualización distintas entre puertos:**\n" + "\n".join(filas)
            + "\n\n*Si un puerto se queda con la misma hora varias capturas seguidas, "
              "CBP dejó de actualizarlo. Vale más decirlo que fingir que el dato es fresco.*\n") if filas else ""


def md_titulares(cx, tz):
    """Titulares automáticos. La estrategia de crecimiento depende de que los medios
    te citen; esto les deja el material servido."""
    filas = cx.execute(
        "SELECT capturado_utc, minutos FROM lecturas WHERE puerto='250601' AND clase='pasajeros' "
        "AND carril='general' AND minutos<>''").fetchall()
    if len(filas) < 50:
        return ""
    ahora = datetime.now(timezone.utc)
    sem1, sem2 = [], []
    for f in filas:
        try:
            t = datetime.fromisoformat(f["capturado_utc"])
        except ValueError:
            continue
        d = (ahora - t).days
        if d < 7:
            sem1.append(int(f["minutos"]))
        elif d < 14:
            sem2.append(int(f["minutos"]))
    if len(sem1) < 20 or len(sem2) < 20:
        return ""
    a, b = mediana(sem1), mediana(sem2)
    if not a or not b:
        return ""
    cambio = (a - b) / b * 100
    verbo = "subió" if cambio > 0 else "bajó"
    return (f"\n## Titular de la semana\n\n"
            f"> La espera en **Otay Mesa** {verbo} **{abs(cambio):.0f}%** esta semana contra la anterior: "
            f"de {int(b)} a {int(a)} minutos de mediana.\n\n"
            f"*Generado solo. Úsalo como material para medios locales.*\n")


def md_sur():
    """El regreso a Tijuana. Caltrans lo publica, nadie lo archiva,
    y ninguna app del ecosistema lo muestra."""
    est = leer_estado()
    filas = []
    for codigo, nombre in SUR_RUTAS.values():
        act = est.get(f"{codigo}|pasajeros|general")
        p15 = est.get(f"{codigo}|pasajeros|pron15")
        p30 = est.get(f"{codigo}|pasajeros|pron30")
        if not act or act[1] is None:
            continue
        fmt = lambda d: "—" if not d or d[1] is None else f"{d[1]} min"
        filas.append(f"| {nombre} | **{act[1]} min** | {fmt(p15)} | {fmt(p30)} |")
    if not filas:
        return ""
    return ("\n## Regreso a Tijuana (sentido sur)\n\n"
            "| ruta | ahora | en 15 min | en 30 min |\n|---|---:|---:|---:|\n"
            + "\n".join(filas)
            + "\n\n*Fuente: Caltrans, con sensores físicos sobre el acceso a la garita. "
              "CBP no mide este sentido. Ninguna app del ecosistema lo publica.*\n")


def md_salud():
    if not os.path.exists(BITACORA):
        return "*Sin bitácora.*"
    with open(BITACORA, encoding="utf-8") as fh:
        filas = list(csv.DictReader(fh))
    if not filas:
        return "*Sin bitácora.*"
    fallas = sum(1 for f in filas if f["error"])
    tam = sum(os.path.getsize(os.path.join(DIR_DATOS, n)) for n in os.listdir(DIR_DATOS)
              if n.endswith(".csv")) / 1024 / 1024 if os.path.isdir(DIR_DATOS) else 0
    try:
        dias = max((datetime.fromisoformat(filas[-1]["momento_utc"])
                    - datetime.fromisoformat(filas[0]["momento_utc"])).days, 1)
    except ValueError:
        dias = 1
    # La proyección solo tiene sentido con al menos una semana corriendo.
    proyeccion = (f" · proyección {tam / dias * 365:.0f} MB al año" if dias >= 7
                  else " · falta historia para proyectar el tamaño")
    return (f"- **Archivando desde:** {filas[0]['momento_utc'][:16].replace('T', ' ')} UTC\n"
            f"- **Capturas:** {len(filas):,} · {100 * (len(filas) - fallas) / len(filas):.1f}% exitosas\n"
            f"- **Tamaño:** {tam:.1f} MB{proyeccion}\n"
            f"- **Días archivando:** {dias}")


# ------------------------------------------------------------------ comandos

def cmd_capturar(args):
    inicio = datetime.now(timezone.utc)
    momento = inicio.isoformat(timespec="seconds")
    error, puertos, nuevas, aviso_sur = None, 0, 0, ""
    try:
        datos = (json.load(open(args.desde_archivo, encoding="utf-8"))
                 if args.desde_archivo else bajar(args.url))
        filas = list(aplanar(datos, solo_mexico=args.solo_mexico))
        # El sentido sur viene de Caltrans y es opcional: si falla, no tumba
        # la captura del norte, que es la principal.
        if not args.sin_sur:
            try:
                html = (open(args.sur_desde_archivo, encoding="utf-8").read()
                        if args.sur_desde_archivo else bajar_texto(SUR_URL))
                sur = list(aplanar_sur(html))
                filas.extend(sur)
                if sur:
                    aviso_sur = f" · {len(sur)} series del sur"
            except Exception as e:
                aviso_sur = f" · sur no disponible ({type(e).__name__})"
        puertos = len({f["puerto"] for f in filas})
        previo = leer_estado()
        cambios, nuevo_estado = [], dict(previo)
        for f in filas:
            clave = f"{f['puerto']}|{f['clase']}|{f['carril']}"
            actual = [f["estado"], f["minutos"], f["carriles_abiertos"], f["hora_cbp"]]
            if previo.get(clave) != actual:
                cambios.append(f)
            nuevo_estado[clave] = actual
        if cambios:
            anexar(cambios, momento)
        json.dump(nuevo_estado, open(ESTADO, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
        nuevas = len(cambios)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as e:
        error = f"red: {e}"
    except (json.JSONDecodeError, ValueError) as e:
        error = f"json: {e}"
    ms = int((datetime.now(timezone.utc) - inicio).total_seconds() * 1000)
    bitacorear(momento, ms, puertos, nuevas, error)
    if error:
        print(f"[{momento}] ERROR {error}", file=sys.stderr)
        return 0  # no truena el workflow: queda registrado y sigue
    print(f"[{momento}] {puertos} puertos · {nuevas} cambios{aviso_sur} · {ms} ms")
    return 0


def cmd_importar(args):
    """Siembra el archivo con la historia de SANDAG. Se corre una sola vez."""
    os.makedirs(DIR_HIST, exist_ok=True)
    ruta = os.path.join(DIR_HIST, "sandag.csv")
    vistos, filas = set(), []
    for r in importar_sandag(args.paginas, args.desde_archivo):
        fecha = (r.get("date") or "")[:10]
        nombre = (r.get("port_name") or "").strip().lower()
        if not fecha or nombre not in SANDAG_PUERTOS:
            continue
        try:
            minutos = int(round(float(r.get("waiting_ave"))))
        except (TypeError, ValueError):
            continue
        codigo, bonito = SANDAG_PUERTOS[nombre]
        clase, carril = _sandag_serie(r.get("type"))
        clave = (fecha, codigo, clase, carril)
        if clave in vistos:
            continue
        vistos.add(clave)
        filas.append([fecha + "T12:00:00+00:00", codigo, "Mexican Border", bonito, bonito,
                      clase, carril, "promedio-diario", minutos, "", "SANDAG", "", "norte"])
    if not filas:
        print("SANDAG no devolvió nada utilizable.", file=sys.stderr)
        return 1
    filas.sort(key=lambda f: f[0])
    with open(ruta, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(COLUMNAS)
        w.writerows(filas)
    print(f"{len(filas):,} promedios diarios importados a {ruta}")
    print(f"Del {filas[0][0][:10]} al {filas[-1][0][:10]} · "
          f"{len({f[1] for f in filas})} puertos")
    print("Ahora corre:  python garita.py reporte")
    return 0


def cargar_historico():
    ruta = os.path.join(DIR_HIST, "sandag.csv")
    if not os.path.exists(ruta):
        return None, 0
    cx = sqlite3.connect(":memory:")
    cx.row_factory = sqlite3.Row
    cx.execute(f"CREATE TABLE h ({','.join(c + ' TEXT' for c in COLUMNAS)})")
    with open(ruta, encoding="utf-8") as fh:
        lote = [[f.get(c, "") for c in COLUMNAS] for f in csv.DictReader(fh)]
    if lote:
        cx.executemany(f"INSERT INTO h VALUES ({','.join('?' * len(COLUMNAS))})", lote)
    cx.commit()
    return cx, len(lote)


def md_estacional():
    """Lo que solo se puede ver con años: el patrón por mes y por día de semana."""
    cx, n = cargar_historico()
    if not cx or n < 100:
        return ""
    MESES = ["ene", "feb", "mar", "abr", "may", "jun",
             "jul", "ago", "sep", "oct", "nov", "dic"]
    out = []
    for puerto, nombre in (("250601", "Otay Mesa"), ("250401", "San Ysidro")):
        filas = cx.execute(
            "SELECT capturado_utc, minutos FROM h WHERE puerto=? AND clase='pasajeros' "
            "AND carril='general' AND minutos<>''", (puerto,)).fetchall()
        if len(filas) < 60:
            continue
        pormes, pordia, poranio = defaultdict(list), defaultdict(list), defaultdict(list)
        for f in filas:
            try:
                d = datetime.fromisoformat(f["capturado_utc"])
            except ValueError:
                continue
            v = int(f["minutos"])
            pormes[d.month].append(v)
            pordia[d.weekday()].append(v)
            poranio[d.year].append(v)
        linea_mes = " | ".join(str(int(mediana(pormes[m]))) if pormes.get(m) else "·"
                               for m in range(1, 13))
        linea_dia = " | ".join(str(int(mediana(pordia[d]))) if pordia.get(d) else "·"
                               for d in range(7))
        out.append(f"\n**{nombre}** · {len(filas):,} días\n\n"
                   "| " + " | ".join(MESES) + " |\n" + "|---" * 12 + "|\n| " + linea_mes + " |\n\n"
                   "| " + " | ".join(d[:3] for d in DIAS) + " |\n" + "|---" * 7 + "|\n| " + linea_dia + " |\n\n"
                   + " · ".join(f"**{a}**: {int(mediana(v))} min" for a, v in sorted(poranio.items())))
    if not out:
        return ""
    return ("\n## Patrón de largo plazo\n\n"
            "*Promedio diario de espera, carriles generales de pasajeros. "
            f"Fuente: histórico abierto de SANDAG, {n:,} registros desde 2023.*\n"
            + "\n".join(out) + "\n")


def cmd_reporte(args):
    tz = zona(args.tz)
    cx, total = cargar_todo()
    hoy = datetime.now(tz).strftime("%d/%m/%Y %H:%M")
    partes = [f"# Garitas — reporte automático\n",
              f"*Actualizado {hoy} (hora de Tijuana) · {total:,} lecturas archivadas*\n",
              "## Ahora mismo — región Tijuana\n", md_ahora(tz),
              "\n*Solo sentido norte (hacia Estados Unidos). CBP no publica el sentido sur.*\n",
              md_sur(), "\n## Salud del archivo\n", md_salud(), md_rancio(tz)]
    for puerto, nombre in DESTACADOS:
        celdas, n = tabla_horas(cx, puerto, tz=tz)
        partes += [f"\n## {nombre} — mediana de espera por hora\n",
                   "*Carriles generales de pasajeros, en minutos, hora de Tijuana.*\n",
                   md_tabla_horas(celdas, n) if n >= 10
                   else f"*Solo hay {n} lecturas. Se necesita más historia; deja que corra unos días.*"]
    partes += [md_titulares(cx, tz), md_estacional()]
    partes += ["\n## Comparación de toda la frontera\n",
               "*Carriles generales de pasajeros.*\n", md_comparacion(cx)]
    partes += ["\n---\n",
               "*Datos de la API pública de CBP (`bwt.cbp.gov/api/waittimes`), archivados cada 15 minutos. "
               "CBP publica solo el estado actual y no lo guarda; esto es el histórico que falta. "
               "Los números son lo que CBP reporta, que se sabe que subestima la espera real.*"]
    texto = "\n".join(partes) + "\n"
    open(REPORTE, "w", encoding="utf-8").write(texto)
    print(f"{REPORTE} regenerado · {total:,} lecturas")
    return 0


def cmd_predecir(args):
    """La predicción honesta: mediana, rango y cuántas lecturas la respaldan.
    Si el rango es ancho o hay pocas lecturas, se dice; no se finge precisión."""
    tz = zona(args.tz)
    cx, _ = cargar_todo()
    celdas, n = tabla_horas(cx, args.puerto, args.clase, args.carril, tz)
    ahora = datetime.now(tz)
    dia = args.dia if args.dia is not None else ahora.weekday()
    hora = args.hora if args.hora is not None else (ahora.hour + 1) % 24
    v = celdas.get((dia, hora), [])
    nombre = PUERTOS_TJ.get(args.puerto, args.puerto)
    print(f"\n{nombre} · {DIAS[dia]} a las {hora:02d}:00 · {args.clase}/{args.carril}")
    if len(v) < 3:
        print(f"  Sin datos suficientes ({len(v)} lecturas). Deja correr el archivo unos días.")
        return 0
    s_ = sorted(v)
    q1, q3 = s_[len(s_) // 4], s_[3 * len(s_) // 4]
    print(f"  Esperado: {int(mediana(v))} minutos")
    print(f"  Rango habitual: {q1} a {q3} minutos")
    print(f"  Respaldo: {len(v)} lecturas · peor visto {max(v)} min")
    if q3 - q1 > 40:
        print("  Aviso: el rango es muy ancho. Esta hora es impredecible, no confíes en la mediana.")
    mejores = sorted(((mediana(vv), h) for (d, h), vv in celdas.items() if d == dia and len(vv) >= 3))[:3]
    if mejores:
        print("  Mejores horas de ese día: " + ", ".join(f"{h:02d}:00 ({int(m)} min)" for m, h in mejores))
    return 0


def cmd_estado(args):
    est = leer_estado()
    if not est:
        print("Sin lecturas todavía. Corre:  python garita.py capturar")
        return 0
    filas = []
    for clave, v in sorted(est.items()):
        puerto, clase, carril = clave.split("|")
        if v[1] is not None:
            filas.append((puerto, clase, carril, v[1], v[2]))
    print(f"{'PUERTO':<10}{'CLASE':<11}{'CARRIL':<9}{'ESPERA':>8}{'ABIERTOS':>10}")
    print("-" * 48)
    for p, c, ca, m, ab in filas[:args.limite]:
        print(f"{p:<10}{c:<11}{ca:<9}{str(m) + ' min':>8}{(ab if ab is not None else '—'):>10}")
    print(f"\n{len(filas)} series con dato. Reporte completo: {REPORTE}")
    return 0


def main():
    p = argparse.ArgumentParser(description="Archivo histórico de tiempos de cruce de la frontera.")
    p.add_argument("--tz", default=TZ)
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("capturar", help="una lectura; esto lo corre GitHub solo")
    c.add_argument("--url", default=API)
    c.add_argument("--solo-mexico", action="store_true")
    c.add_argument("--desde-archivo")
    c.add_argument("--sin-sur", action="store_true", help="no capturar el sentido sur de Caltrans")
    c.add_argument("--sur-desde-archivo", help="leer el HTML del sur de un archivo local")
    c.set_defaults(f=cmd_capturar)

    i = sub.add_parser("importar", help="siembra 3.5 años de historia de SANDAG (una sola vez)")
    i.add_argument("--paginas", type=int, help="limitar páginas, para probar")
    i.add_argument("--desde-archivo", help="leer un JSON local en vez de la red")
    i.set_defaults(f=cmd_importar)

    r = sub.add_parser("reporte", help="regenera REPORTE.md")
    r.set_defaults(f=cmd_reporte)

    pr = sub.add_parser("predecir", help="cuánto esperar un día y hora dados")
    pr.add_argument("--puerto", default="250601")
    pr.add_argument("--dia", type=int, help="0=lunes … 6=domingo. Default: hoy")
    pr.add_argument("--hora", type=int, help="0-23. Default: la siguiente hora")
    pr.add_argument("--clase", default="pasajeros")
    pr.add_argument("--carril", default="general")
    pr.set_defaults(f=cmd_predecir)

    e = sub.add_parser("estado", help="qué hay ahora mismo")
    e.add_argument("--limite", type=int, default=40)
    e.set_defaults(f=cmd_estado)

    args = p.parse_args()
    sys.exit(args.f(args) or 0)


if __name__ == "__main__":
    main()
