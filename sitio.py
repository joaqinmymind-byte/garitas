#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sitio.py — convierte el archivo de garitas en un sitio estatico indexable.

Por que existe:
    Los competidores del nicho no crecieron por prensa ni por pauta. Crecieron
    por busqueda: 75% del trafico de garitacenter.com es organico. La gente
    teclea "cuanta fila hay para cruzar" y "a que hora conviene cruzar por
    Otay el martes". Ninguno de los diez sitios gratuitos contesta la segunda,
    porque ninguno guarda historia. Nosotros si.

    Este generador arma una pagina por garita, por carril y por dia de la
    semana, cada una contestando exactamente una de esas preguntas con datos
    propios. Sin JavaScript para el contenido, sin dependencias, sin build.

Uso:
    python sitio.py                      genera ./sitio
    python sitio.py --destino publico    otra carpeta
    python sitio.py --dominio https://garitas.mx
    python sitio.py --si-viejo 55        solo si el sitio ya tiene 55 min

Se apoya en garita.py para leer los datos; no duplica logica de analisis.
"""

import argparse
import csv
import html
import json
import os
import shutil
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone

import garita as G

DESTINO = "sitio"
DOMINIO = ""          # se llena con --dominio; sin el, las URLs quedan relativas
# De donde relee la pagina el numero de ahorita. Si le pasas --estado-url con
# el raw de tu repositorio, el sitio se publica cada hora pero el numero sigue
# siendo de hace 15 minutos, sin gastar una sola corrida extra.
ESTADO_URL = ""
MESES_SITIO = 6       # cuanta historia lee para las tablas por hora
# Si el sitio no vive en la raiz del dominio (GitHub Pages de proyecto lo
# sirve en /repo/), aqui va ese prefijo. Con dominio propio se queda vacio.
BASE = ""
MIN_LECTURAS = 40     # menos que esto es contenido pobre: no se publica la pagina
MIN_CELDAS = 24       # y con menos de 24 casillas de 168 tampoco

# ── que se publica ────────────────────────────────────────────────────────
# Cada garita con su slug, su nombre para titulo y como la busca la gente.
GARITAS = [
    {"puerto": "250401", "slug": "san-ysidro", "prefiere": ["carros", "sentri", "ready", "peatonal"], "nombre": "San Ysidro",
     "corto": "San Ysidro", "articulo": "la garita de San Ysidro",
     "tambien": "la línea, Puerta México, San Isidro"},
    {"puerto": "250601", "slug": "otay", "prefiere": ["carros", "sentri", "ready", "peatonal"], "nombre": "Otay Mesa",
     "corto": "Otay", "articulo": "la garita de Otay",
     "tambien": "Mesa de Otay, Otay Centenario"},
    {"puerto": "250501", "slug": "tecate", "prefiere": ["carros", "peatonal", "carga"], "nombre": "Tecate",
     "corto": "Tecate", "articulo": "la garita de Tecate",
     "tambien": "cruce de Tecate"},
    {"puerto": "250407", "slug": "pedwest", "prefiere": ["peatonal", "peatonal-ready"], "nombre": "PedWest",
     "corto": "PedWest", "articulo": "el cruce peatonal PedWest",
     "tambien": "El Chaparral peatonal"},
    {"puerto": "250409", "slug": "cbx", "prefiere": ["peatonal", "peatonal-ready"], "nombre": "CBX",
     "corto": "CBX", "articulo": "el puente del CBX",
     "tambien": "Cross Border Xpress, puente del aeropuerto"},
    {"puerto": "250602", "slug": "otay-comercial", "prefiere": ["carga", "fast"], "nombre": "Otay Comercial",
     "corto": "Otay carga", "articulo": "la garita comercial de Otay",
     "tambien": "Otay carga, cruce de tráileres"},
]

# Los carriles, con el nombre que usa la gente y no el que usa CBP.
CARRILES = [
    {"slug": "carros",   "clase": "pasajeros", "carril": "general",
     "nombre": "carros",           "largo": "carriles generales de carros"},
    {"slug": "sentri",   "clase": "pasajeros", "carril": "sentri",
     "nombre": "SENTRI",           "largo": "carril SENTRI"},
    {"slug": "ready",    "clase": "pasajeros", "carril": "ready",
     "nombre": "Ready Lane",       "largo": "Ready Lane de carros"},
    {"slug": "peatonal", "clase": "peatones",  "carril": "general",
     "nombre": "peatonal",         "largo": "cruce peatonal"},
    {"slug": "peatonal-ready", "clase": "peatones", "carril": "ready",
     "nombre": "peatonal Ready",   "largo": "cruce peatonal Ready Lane"},
    {"slug": "carga",    "clase": "carga",     "carril": "general",
     "nombre": "carga",            "largo": "carriles de carga"},
    {"slug": "fast",     "clase": "carga",     "carril": "fast",
     "nombre": "FAST",             "largo": "carril FAST de carga"},
]

DIAS = G.DIAS
DIAS_SLUG = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"]
# En espanol 'los lunes' no lleva s, pero 'los sabados' si. Escribir "los martess"
# es la clase de detalle que le dice al lector que el sitio lo hizo una maquina.
PLURAL = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábados", "domingos"]


# ── identidad visual ──────────────────────────────────────────────────────
# Misma materia que el prototipo: concreto, cal, junta de cimbra, vapor de
# sodio. Sin fuentes externas a proposito: cada peticion extra son 300 ms en
# un telefono en la fila, y ahi es donde se lee esto.
CSS = """*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
:root{
--losa:#D9DBD2;--cal:#F1F1EA;--cal2:#E5E6DC;--linea:#C2C5B9;--linea2:#D2D4C9;
--tinta:#14161A;--tinta2:#4B514C;--tinta3:#63695F;
--sodio:#A85008;--sodio-d:#833E06;--digito:#F0A93A;
--letrero:#1C6B3F;--alto:#A81B0C;--raya:#8A6706;--placa:#1D4E89;
--tablero:#101418;--tablero2:#171C22;--flap:#262C33;
--s0:#EDEEE6;--s1:#F8F1E7;--s2:#EEDBC4;--s3:#E2C39C;--s4:#D6A871;--s5:#895C24;--s6:#724C1D;--s7:#5B3C15;--s8:#40290C;
--u:4px;--r:2px;
--font:system-ui,-apple-system,'Segoe UI',Roboto,'Helvetica Neue',Arial,sans-serif;
--mono:ui-monospace,'SF Mono',SFMono-Regular,Menlo,Consolas,'Liberation Mono',monospace}
@media(prefers-color-scheme:dark){:root{
--losa:#0E1114;--cal:#161A1E;--cal2:#1D2227;--linea:#2B3138;--linea2:#232930;
--tinta:#E8E9E3;--tinta2:#A8AEA6;--tinta3:#878D85;
--sodio:#E08A2E;--sodio-d:#F0A93A;--letrero:#4FA972;--alto:#E4675A;--placa:#6FA0DA;
--s0:#1A1F24;--s1:#2D2316;--s2:#40311C;--s3:#553F20;--s4:#6A4D25;--s5:#C28F47;--s6:#D1A261;--s7:#DEB67C;--s8:#EAC999}}
html{-webkit-text-size-adjust:100%}
body{background:var(--losa);color:var(--tinta);font-family:var(--font);
line-height:1.55;font-size:17px;padding-bottom:calc(var(--u)*16)}
a{color:var(--sodio);text-underline-offset:3px;text-decoration-thickness:1px}
a:hover{color:var(--sodio-d)}
.envoltura{max-width:960px;margin:0 auto;padding:0 calc(var(--u)*4)}
header.cinta{background:var(--tablero);color:#E8E9E3;border-bottom:3px solid var(--sodio)}
header.cinta .envoltura{display:flex;align-items:baseline;gap:calc(var(--u)*4);
padding-top:calc(var(--u)*3);padding-bottom:calc(var(--u)*3);flex-wrap:wrap}
header.cinta a{color:#E8E9E3;text-decoration:none}
.marca{font-weight:800;letter-spacing:.14em;text-transform:uppercase;font-size:15px}
.marca span{color:var(--digito)}
nav.cinta-nav{display:flex;gap:calc(var(--u)*4);flex-wrap:wrap;font-size:14px}
nav.cinta-nav a{color:#A8AEA6}
nav.cinta-nav a:hover,nav.cinta-nav a[aria-current]{color:var(--digito)}
main{padding-top:calc(var(--u)*8)}
h1{font-size:clamp(26px,5vw,38px);line-height:1.15;letter-spacing:-.02em;font-weight:800;
margin-bottom:calc(var(--u)*3)}
h2{font-size:clamp(19px,3.4vw,24px);letter-spacing:-.01em;font-weight:700;
margin:calc(var(--u)*10) 0 calc(var(--u)*3);padding-top:calc(var(--u)*3);
border-top:1px solid var(--linea)}
h3{font-size:17px;font-weight:700;margin:calc(var(--u)*6) 0 calc(var(--u)*2)}
p{margin-bottom:calc(var(--u)*3);max-width:68ch}
.entrada{font-size:19px;color:var(--tinta2);max-width:64ch}
.miga{font-size:13px;color:var(--tinta3);margin-bottom:calc(var(--u)*3);
text-transform:uppercase;letter-spacing:.08em}
.miga a{color:var(--tinta3)}
.pie-nota{font-size:14px;color:var(--tinta3);max-width:68ch}
/* tablero: la firma */
.tablero{background:var(--tablero);border:1px solid var(--flap);border-radius:var(--r);
padding:calc(var(--u)*4);margin:calc(var(--u)*5) 0}
.tablero h2{color:#E8E9E3;border:0;margin:0 0 calc(var(--u)*3);padding:0;font-size:15px;
text-transform:uppercase;letter-spacing:.12em}
.rejilla{display:grid;grid-template-columns:repeat(auto-fit,minmax(132px,1fr));
gap:0;border-top:1px solid var(--flap);border-left:1px solid var(--flap)}
.digito{background:var(--tablero2);padding:calc(var(--u)*3);
border-right:1px solid var(--flap);border-bottom:1px solid var(--flap)}
.digito .etq{font-size:11px;color:#878D85;text-transform:uppercase;letter-spacing:.08em;
display:block;margin-bottom:calc(var(--u));line-height:1.3}
.digito .num{font-family:var(--mono);font-size:30px;font-weight:700;color:var(--digito);
font-variant-numeric:tabular-nums;line-height:1;white-space:nowrap;display:block}
.digito .num small{font-size:13px;color:#878D85;font-weight:400}
.digito .car{display:block;font-size:11px;color:#6B7169;margin-top:calc(var(--u));
font-family:var(--mono);white-space:nowrap}
.digito.cerrado .num{color:#878D85}
/* tarjetas y datos */
.caja{background:var(--cal);border:1px solid var(--linea);border-radius:var(--r);
padding:calc(var(--u)*4);margin:calc(var(--u)*4) 0}
.caja.acento{border-left:3px solid var(--sodio)}
.dato{display:flex;gap:calc(var(--u)*6);flex-wrap:wrap;margin:calc(var(--u)*4) 0}
.dato div{min-width:120px}
.dato .k{font-size:12px;text-transform:uppercase;letter-spacing:.08em;color:var(--tinta3);
display:block}
.dato .v{font-family:var(--mono);font-size:26px;font-weight:700;font-variant-numeric:tabular-nums}
.v.bueno{color:var(--letrero)}.v.malo{color:var(--alto)}
/* mapa de calor */
.desliz{overflow-x:auto;-webkit-overflow-scrolling:touch;margin:calc(var(--u)*4) 0;
border:1px solid var(--linea);border-radius:var(--r);background:var(--cal)}
table.calor{border-collapse:collapse;width:100%;font-family:var(--mono);font-size:12px;
font-variant-numeric:tabular-nums}
table.calor th,table.calor td{padding:calc(var(--u)*1.5) calc(var(--u));text-align:center;
border:1px solid var(--linea2);white-space:nowrap}
table.calor thead th{background:var(--cal2);font-weight:600;font-size:11px;color:var(--tinta2)}
table.calor tbody th{background:var(--cal2);text-align:left;padding-left:calc(var(--u)*2);
font-weight:600;position:sticky;left:0}
table.calor td{color:var(--tinta);font-weight:600;min-width:30px}
td.n0{background:var(--s0);color:var(--tinta3)}
td.n1{background:var(--s1)}td.n2{background:var(--s2)}td.n3{background:var(--s3)}
td.n4{background:var(--s4)}td.n5{background:var(--s5)}td.n6{background:var(--s6)}
td.n7{background:var(--s7)}td.n8{background:var(--s8)}
td.n1,td.n2,td.n3,td.n4{color:#14161A}
td.n5,td.n6,td.n7,td.n8{color:#F6EAD8}
@media(prefers-color-scheme:dark){
td.n1,td.n2,td.n3,td.n4{color:#EDD8B4}
td.n5,td.n6,td.n7,td.n8{color:#101418}}
.escala{display:flex;align-items:center;gap:calc(var(--u)*3);font-size:12px;
color:var(--tinta3);margin-top:calc(var(--u)*2);flex-wrap:wrap}
.escala .paso{display:inline-flex;align-items:center;gap:calc(var(--u));white-space:nowrap;
font-family:var(--mono)}
.escala i{display:inline-block;width:22px;height:12px;border:1px solid var(--linea)}
/* tabla normal */
table.lista{border-collapse:collapse;width:100%;font-size:15px;margin:calc(var(--u)*4) 0}
table.lista th,table.lista td{padding:calc(var(--u)*2) calc(var(--u)*2);
border-bottom:1px solid var(--linea);text-align:left}
table.lista tbody tr:last-child td{border-bottom:0}
table.lista th{font-size:12px;text-transform:uppercase;letter-spacing:.08em;
color:var(--tinta3);font-weight:600}
table.lista td.num{font-family:var(--mono);text-align:right;font-variant-numeric:tabular-nums}
/* fichas de enlaces */
.fichas{display:grid;grid-template-columns:repeat(auto-fill,minmax(190px,1fr));
gap:calc(var(--u)*2);margin:calc(var(--u)*4) 0;padding:0;list-style:none}
.fichas a{display:block;background:var(--cal);border:1px solid var(--linea);
border-radius:var(--r);padding:calc(var(--u)*3);text-decoration:none;color:var(--tinta);
border-left:3px solid var(--linea)}
.fichas a:hover{border-left-color:var(--sodio);background:var(--cal2)}
.fichas b{display:block;font-size:16px}
.fichas span{display:block;font-size:13px;color:var(--tinta3);margin-top:2px}
footer{border-top:1px solid var(--linea);margin-top:calc(var(--u)*14);
padding-top:calc(var(--u)*5);font-size:14px;color:var(--tinta3)}
footer a{color:var(--tinta2)}
.saltar{position:absolute;left:-9999px}
.saltar:focus{left:calc(var(--u)*4);top:calc(var(--u)*2);background:var(--cal);
padding:calc(var(--u)*2);z-index:9}
@media(max-width:640px){
nav.cinta-nav{flex-wrap:nowrap;overflow-x:auto;-webkit-overflow-scrolling:touch;
scrollbar-width:none;padding-bottom:2px}
nav.cinta-nav::-webkit-scrollbar{display:none}
nav.cinta-nav a{white-space:nowrap}}
@media(max-width:520px){body{font-size:16px}.digito .num{font-size:26px}
.envoltura{padding:0 calc(var(--u)*3)}
h2{margin-top:calc(var(--u)*8)}}
"""


# ── utilidades de plantilla ───────────────────────────────────────────────
def e(t):
    return html.escape(str(t), quote=True)


def corta(t, tope=158):
    """Google recorta la descripcion como a 160 caracteres. Cortar a mitad de
    palabra se ve descuidado justo donde mas importa: en el resultado."""
    t = " ".join(str(t).split())
    if len(t) <= tope:
        return t
    corte = t[:tope]
    espacio = corte.rfind(" ")
    return (corte[:espacio] if espacio > tope * 0.6 else corte).rstrip(" ,;:.") + "…"


def _rel(ruta):
    """El enlace que va DENTRO de la pagina, relativo a la raiz del sitio
    (con el prefijo de --base si lo hay). Asi el mismo generador sirve para
    GitHub Pages en /repo/ y para un dominio propio, sin tocar nada."""
    ruta = ruta.strip("/")
    return (BASE + "/" + ruta + "/") if ruta else (BASE + "/")


def _act(archivo):
    """Un archivo suelto en la raiz del sitio: estilo.css, ahora.json."""
    return BASE + "/" + archivo.lstrip("/")


def _url(ruta):
    """La URL completa: solo para canonical, og:url y el sitemap, que son los
    unicos lugares donde Google exige saber el dominio de verdad.
    Tolera que le pases el dominio ya con el prefijo de --base pegado: es el
    error mas facil de cometer y produce URLs duplicadas, que es justo lo que
    mas castiga un buscador."""
    if not DOMINIO:
        return _rel(ruta)
    raiz = DOMINIO.rstrip("/")
    if BASE and raiz.endswith(BASE):
        raiz = raiz[: -len(BASE)]
    return raiz + _rel(ruta)


NAV = [("/", "Ahorita"), ("/mejor-hora/", "Mejor hora"),
       ("/regreso-a-tijuana/", "Regreso"), ("/comparar/", "Comparar"),
       ("/historia/", "Historia"), ("/datos/", "Datos abiertos")]


def pagina(ruta, titulo, descripcion, cuerpo, jsonld=None, actualizado=None,
           miga=None, sin_indexar=False, nav=None):
    """El esqueleto. Un solo archivo CSS compartido: se cachea entre paginas."""
    canon = _url(ruta)
    migas = ""
    if miga:
        partes = " › ".join(f'<a href="{e(_rel(u))}">{e(t)}</a>' if u else e(t)
                            for t, u in miga)
        migas = f'<p class="miga">{partes}</p>'
    ld = ""
    if jsonld:
        ld = ('<script type="application/ld+json">'
              + json.dumps(jsonld, ensure_ascii=False, separators=(",", ":"))
              + "</script>")
    sello = actualizado or ""
    robots = '<meta name="robots" content="noindex,follow">' if sin_indexar else ""
    return f"""<!doctype html>
<html lang="es-MX">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(titulo)}</title>
<meta name="description" content="{e(descripcion)}">
{robots}
<link rel="canonical" href="{e(canon)}">
<link rel="stylesheet" href="{e(_act("estilo.css"))}">
<meta property="og:type" content="website">
<meta property="og:locale" content="es_MX">
<meta property="og:title" content="{e(titulo)}">
<meta property="og:description" content="{e(descripcion)}">
<meta property="og:url" content="{e(canon)}">
<meta name="theme-color" content="#101418">
{ld}
</head>
<body>
<a class="saltar" href="#principal">Saltar al contenido</a>
<header class="cinta">
  <div class="envoltura">
    <a class="marca" href="{e(_rel("/"))}">GARITAS<span>.</span></a>
    <nav class="cinta-nav" aria-label="Secciones">
      {' '.join(f'<a href="{e(_rel(u))}"{" aria-current=page" if u == "/" + ruta.strip("/") + "/" or (u == "/" and not ruta.strip("/")) else ""}>{e(t)}</a>' for u, t in (nav if nav is not None else NAV))}
    </nav>
  </div>
</header>
<main id="principal" class="envoltura">
{migas}
{cuerpo}
<footer>
<p>Datos de la API pública de <a href="https://bwt.cbp.gov/" rel="nofollow">CBP</a>
(sentido norte) y de <a href="https://quickmap.dot.ca.gov/borderwait.html" rel="nofollow">Caltrans</a>
(sentido sur). El histórico lo archiva este proyecto cada 15 minutos, porque nadie más lo guarda.
Todo es <a href="{e(_rel("datos"))}">abierto y descargable</a>.</p>
<p>{e(sello)}</p>
</footer>
</main>
</body>
</html>
"""


def escribir(destino, ruta, contenido):
    ruta = ruta.strip("/")
    carpeta = os.path.join(destino, ruta) if ruta else destino
    os.makedirs(carpeta, exist_ok=True)
    with open(os.path.join(carpeta, "index.html"), "w", encoding="utf-8") as fh:
        fh.write(contenido)


# Los cortes salen de la realidad de la garita, no de una rampa matematica.
# Con la escala anterior casi todo San Ysidro caia en los dos escalones mas
# oscuros y el mapa dejaba de decir nada: la espera tipica vive entre 60 y
# 180 minutos, asi que ahi es donde hay que poner la resolucion.
CORTES = (20, 40, 60, 80, 100, 130, 180)


def nivel(m):
    """Minutos -> escalon de color, del 1 al 8. 0 es 'no hay dato'."""
    if m is None:
        return 0
    for i, tope in enumerate(CORTES, start=1):
        if m < tope:
            return i
    return 8


def humano(m):
    """90 -> '1 h 30 min'. La gente no piensa en minutos arriba de una hora."""
    m = int(m)
    if m < 60:
        return f"{m} min"
    h, r = divmod(m, 60)
    return f"{h} h" if not r else f"{h} h {r} min"


# ── piezas reutilizables ──────────────────────────────────────────────────
def calor(celdas, resaltar_dia=None):
    """La tabla de 168 casillas. Es el corazon del sitio: es lo unico que
    ninguno de los diez competidores gratuitos puede mostrar."""
    out = ['<div class="desliz"><table class="calor">',
           "<caption class=\"saltar\">Mediana de espera por hora y día</caption>",
           "<thead><tr><th scope=\"col\">día</th>"
           + "".join(f'<th scope="col">{h:02d}</th>' for h in range(24))
           + "</tr></thead><tbody>"]
    for d in range(7):
        marca = ' style="outline:2px solid var(--sodio);outline-offset:-2px"' if d == resaltar_dia else ""
        out.append(f'<tr{marca}><th scope="row">{DIAS[d][:3]}</th>')
        for h in range(24):
            m = G.mediana(celdas.get((d, h), []))
            if m is None:
                out.append('<td class="n0" aria-label="sin dato">·</td>')
            else:
                k = len(celdas[(d, h)])
                out.append(f'<td class="n{nivel(m)}" title="{DIAS[d]} {h:02d}:00 · '
                           f'{int(m)} min · {k} lectura{"s" if k != 1 else ""}">{int(m)}</td>')
        out.append("</tr>")
    out.append("</tbody></table></div>")
    tramos, piso = [], 0
    for i, tope in enumerate(CORTES, start=1):
        tramos.append(f'<span class="paso"><i style="background:var(--s{i})"></i>'
                      f'{"0" if not piso else e(humano(piso))}</span>')
        piso = tope
    tramos.append(f'<span class="paso"><i style="background:var(--s8)"></i>'
                  f'{e(humano(piso))}+</span>')
    out.append('<p class="escala">' + "".join(tramos)
               + f' <span>el salto de tono marca la hora y {CORTES[4] - 60} minutos · '
                 'pasa el cursor sobre una casilla para ver cuántas lecturas la respaldan</span></p>')
    return "".join(out)


def extremos(celdas):
    con = {k: G.mediana(v) for k, v in celdas.items() if v}
    if not con:
        return None
    mejor = min(con.items(), key=lambda kv: kv[1])
    peor = max(con.items(), key=lambda kv: kv[1])
    return {"mejor_dia": mejor[0][0], "mejor_hora": mejor[0][1], "mejor_min": int(mejor[1]),
            "peor_dia": peor[0][0], "peor_hora": peor[0][1], "peor_min": int(peor[1]),
            "llenas": len(con)}


def bloque_extremos(x):
    return (f'<div class="caja acento"><div class="dato">'
            f'<div><span class="k">Mejor momento</span>'
            f'<span class="v bueno">{e(humano(x["mejor_min"]))}</span>'
            f'<span class="k">{e(DIAS[x["mejor_dia"]])} {x["mejor_hora"]:02d}:00</span></div>'
            f'<div><span class="k">Peor momento</span>'
            f'<span class="v malo">{e(humano(x["peor_min"]))}</span>'
            f'<span class="k">{e(DIAS[x["peor_dia"]])} {x["peor_hora"]:02d}:00</span></div>'
            f'<div><span class="k">Diferencia</span>'
            f'<span class="v">{e(humano(x["peor_min"] - x["mejor_min"]))}</span>'
            f'<span class="k">entre escoger bien y escoger mal</span></div>'
            f"</div></div>")


def horas_del_dia(celdas, d):
    """Las 24 horas de un dia, como lista de (hora, minutos o None)."""
    return [(h, G.mediana(celdas.get((d, h), []))) for h in range(24)]


def tabla_dia(celdas, d):
    filas = [(h, m, len(celdas.get((d, h), []))) for h, m in horas_del_dia(celdas, d)
             if m is not None]
    if not filas:
        return ""
    out = ['<div class="desliz"><table class="lista">',
           "<thead><tr><th>hora</th><th>espera típica</th><th></th>"
           "<th>lecturas</th></tr></thead><tbody>"]
    mx = max(m for _, m, _ in filas) or 1
    for h, m, n in filas:
        ancho = max(3, int(100 * m / mx))
        # Decir cuantas lecturas hay detras de cada hora es la diferencia entre
        # un dato y una adivinanza con formato bonito.
        out.append(f'<tr><td>{h:02d}:00</td><td class="num">{e(humano(m))}</td>'
                   f'<td style="width:45%"><span style="display:block;height:12px;'
                   f'width:{ancho}%;background:var(--s{nivel(m)})"></span></td>'
                   f'<td class="num" style="color:var(--tinta3)">{n}</td></tr>')
    out.append("</tbody></table></div>")
    flojas = sum(1 for _, _, n in filas if n < 3)
    if flojas:
        out.append(f'<p class="pie-nota">{flojas} de las {len(filas)} horas se apoyan en menos '
                   f'de tres lecturas todavía. Se afinan solas conforme el archivo crece.</p>')
    return "".join(out)


def fichas(items):
    return ('<ul class="fichas">'
            + "".join(f'<li><a href="{e(_rel(u))}"><b>{e(t)}</b>'
                      + (f"<span>{e(s)}</span>" if s else "") + "</a></li>"
                      for u, t, s in items)
            + "</ul>")


# ── "ahora mismo" ─────────────────────────────────────────────────────────
# El HTML se regenera cada hora (cuesta caro), pero el numero de ahorita se
# actualiza cada 15 minutos en un JSON de 2 KB que la pagina relee sola.
# Asi la portada nunca miente y no pagamos por regenerar 80 paginas.
def leer_ahora(tz):
    est = G.leer_estado()
    out = {"actualizado": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "local": datetime.now(tz).strftime("%d/%m/%Y %H:%M"), "cruces": {}}
    for clave, v in (est or {}).items():
        puerto, clase, carril = clave.split("|")
        try:
            minutos = v[1]
            abiertos = v[2] if len(v) > 2 else None
        except (TypeError, IndexError):
            continue
        out["cruces"][f"{puerto}|{clase}|{carril}"] = {
            "min": minutos, "carriles": abiertos}
    return out


def _dato_ahora(ahora, puerto, clase, carril):
    return (ahora.get("cruces") or {}).get(f"{puerto}|{clase}|{carril}")


def tablero(ahora, entradas, titulo="Ahora mismo"):
    """entradas: lista de (etiqueta, puerto, clase, carril)."""
    if not entradas:
        return ""
    celdas = []
    for etq, puerto, clase, carril in entradas:
        d = _dato_ahora(ahora, puerto, clase, carril)
        clave = f"{puerto}|{clase}|{carril}"
        if not d or d.get("min") is None:
            celdas.append(f'<div class="digito cerrado" data-cruce="{e(clave)}">'
                          f'<span class="etq">{e(etq)}</span>'
                          f'<span class="num">—</span></div>')
            continue
        car = d.get("carriles")
        extra = f'<span class="car">{car} carriles abiertos</span>' if car else ""
        celdas.append(f'<div class="digito" data-cruce="{e(clave)}">'
                      f'<span class="etq">{e(etq)}</span>'
                      f'<span class="num">{int(d["min"])}<small> min</small></span>{extra}</div>')
    sello = ahora.get("local", "")
    return (f'<section class="tablero"><h2>{e(titulo)} '
            f'<span id="sello" style="color:#878D85;font-weight:400">· {e(sello)}</span></h2>'
            f'<div class="rejilla">{"".join(celdas)}</div></section>')


def vivo():
    """El refresco del tablero. Sin JavaScript la pagina igual sirve: los
    numeros ya vienen escritos. Esto solo los pone al dia."""
    fuente = ("var U='" + ESTADO_URL + "',R=1;" if ESTADO_URL
              else "var U='" + _act("ahora.json") + "',R=0;")
    return VIVO.replace("/*FUENTE*/", fuente)


VIVO = """<script>
(function(){var t=document.querySelectorAll('[data-cruce]');if(!t.length)return;
/*FUENTE*/
function crudo(j){var c={};for(var k in j){var v=j[k];c[k]={min:v[1],carriles:v[2]}}
return{cruces:c}}
function p(){fetch(U+(U.indexOf('?')<0?'?':'&')+Math.floor(Date.now()/6e4)).then(function(r){return r.json()})
.then(function(j){var d=R?crudo(j):j;var s=document.getElementById('sello');if(s&&d.local)s.textContent='\\u00b7 '+d.local;
t.forEach(function(n){var v=d.cruces[n.dataset.cruce],m=n.querySelector('.num'),c=n.querySelector('.car');if(!m)return;
if(!v||v.min===null){n.classList.add('cerrado');m.textContent='\\u2014';if(c)c.textContent='';return}
n.classList.remove('cerrado');m.innerHTML=v.min+'<small> min</small>';
if(c)c.textContent=v.carriles?v.carriles+' carriles abiertos':''})})
.catch(function(){})}
setInterval(p,3e5);document.addEventListener('visibilitychange',function(){if(!document.hidden)p()})})();
</script>"""


# ── páginas de garita ─────────────────────────────────────────────────────
def _faq(pares):
    return {"@context": "https://schema.org", "@type": "FAQPage",
            "mainEntity": [{"@type": "Question", "name": p,
                            "acceptedAnswer": {"@type": "Answer", "text": r}}
                           for p, r in pares]}


def _miga(*pares):
    return list(pares)


def carriles_con_datos(cx, puerto, tz):
    """Solo los carriles que de verdad tienen historia. Publicar una pagina
    vacia es peor que no publicarla: Google lo llama contenido pobre."""
    vivos = []
    for c in CARRILES:
        celdas, n = G.tabla_horas(cx, puerto, c["clase"], c["carril"], tz)
        if n >= MIN_LECTURAS and len([k for k, v in celdas.items() if v]) >= MIN_CELDAS:
            vivos.append((c, celdas, n))
    return vivos


def pag_garita(g, vivos, ahora):
    if not vivos:
        return None
    c, celdas, n = vivos[0]
    x = extremos(celdas)
    ent = [(f"{cc['nombre']}", g["puerto"], cc["clase"], cc["carril"]) for cc, _, _ in vivos]

    cuerpo = [f'<h1>Garita de {e(g["nombre"])}: cuánta fila hay y a qué hora conviene cruzar</h1>']
    cuerpo.append(f'<p class="entrada">Espera típica en {e(g["articulo"])} hacia Estados Unidos, '
                  f'hora por hora y día por día, calculada con {n:,} lecturas propias. '
                  f'No es un promedio inventado: es lo que de verdad ha pasado.</p>')
    cuerpo.append(tablero(ahora, ent))
    if x:
        cuerpo.append(f'<h2>La mejor y la peor hora en {e(g["corto"])}</h2>')
        cuerpo.append(bloque_extremos(x))
        cuerpo.append(f'<p>En {e(g["articulo"])}, {e(c["largo"])}, el mejor momento de la semana '
                      f'es el <strong>{e(DIAS[x["mejor_dia"]])} a las {x["mejor_hora"]:02d}:00</strong> '
                      f'({e(humano(x["mejor_min"]))}) y el peor el '
                      f'<strong>{e(DIAS[x["peor_dia"]])} a las {x["peor_hora"]:02d}:00</strong> '
                      f'({e(humano(x["peor_min"]))}). Escoger bien la hora te ahorra '
                      f'<strong>{e(humano(x["peor_min"] - x["mejor_min"]))}</strong>.</p>')
    cuerpo.append(f'<h2>Espera por hora y día de la semana</h2>')
    cuerpo.append(f'<p>Mediana en minutos, {e(c["largo"])}, hora de Tijuana. '
                  f'Cada casilla es lo que ha pasado a esa hora de ese día.</p>')
    cuerpo.append(calor(celdas))
    dias = dias_publicables(celdas)
    if dias:
        cuerpo.append("<h2>Ver por día</h2>")
        cuerpo.append(fichas([(f"{g['slug']}/{DIAS_SLUG[d]}", f"{DIAS[d].capitalize()}",
                               f"a qué hora cruzar el {DIAS[d]}") for d in dias]))
    # vivos[0] es el carril que ya se muestra en esta misma pagina: enlazarlo
    # seria mandarte a donde ya estas.
    if len(vivos) > 1:
        cuerpo.append("<h2>Ver por carril</h2>")
        cuerpo.append(fichas([(f"{g['slug']}/{cc['slug']}", cc["nombre"].capitalize(),
                               f"{nn:,} lecturas") for cc, _, nn in vivos[1:]]))
    cuerpo.append('<h2>De dónde sale este número</h2>')
    cuerpo.append('<p>De la API pública de CBP, leída cada 15 minutos y guardada desde entonces. '
                  'CBP solo publica el dato de este instante: cuando el número cambia, el anterior '
                  'desaparece y nadie más lo estaba guardando. Por eso existe este archivo, y por eso '
                  f'<a href="{_rel("datos")}">está abierto</a> para quien lo quiera usar.</p>')
    cuerpo.append(f'<p class="pie-nota">También se busca como: {e(g["tambien"])}.</p>')
    cuerpo.append(vivo())

    faq = []
    if x:
        faq = [(f"¿A qué hora hay menos fila en la garita de {g['nombre']}?",
                f"El mejor momento de la semana es el {DIAS[x['mejor_dia']]} a las "
                f"{x['mejor_hora']:02d}:00, con {humano(x['mejor_min'])} de espera típica."),
               (f"¿Cuál es la peor hora para cruzar por {g['nombre']}?",
                f"El {DIAS[x['peor_dia']]} a las {x['peor_hora']:02d}:00, con "
                f"{humano(x['peor_min'])}. Son {humano(x['peor_min'] - x['mejor_min'])} más "
                f"que en el mejor momento.")]
    desc = (f"Espera típica en la garita de {g['nombre']} hora por hora y día por día. "
            + (f"Mejor momento: {DIAS[x['mejor_dia']]} {x['mejor_hora']:02d}:00 con "
               f"{humano(x['mejor_min'])}. " if x else "")
            + "Con histórico propio desde que CBP lo publica.")
    return {"ruta": g["slug"],
            "titulo": f"Garita de {g['nombre']}: tiempo de espera por hora | Garitas",
            "desc": desc, "cuerpo": "\n".join(cuerpo),
            "jsonld": _faq(faq) if faq else None,
            "miga": _miga(("Garitas", "/"), (g["nombre"], None))}


MIN_HORAS_DIA = 8   # menos de 8 de 24 horas no contesta la pregunta del titulo


def dias_publicables(celdas):
    """Que dias tienen suficiente material. Se calcula una sola vez y se
    reparte, para que la pagina de la garita no enlace a un dia que no existe."""
    return [d for d in range(7)
            if sum(1 for h in range(24) if celdas.get((d, h))) >= MIN_HORAS_DIA]


def pag_dia(g, d, celdas, c, ahora, vivos, hermanas=()):
    """La pagina que contesta la busqueda de oro: 'a que hora cruzar por
    Otay el martes'. Ningun competidor la tiene."""
    horas = [(h, m) for h, m in horas_del_dia(celdas, d) if m is not None]
    if len(horas) < MIN_HORAS_DIA:
        return None
    mejor = min(horas, key=lambda hm: hm[1])
    peor = max(horas, key=lambda hm: hm[1])
    dia = DIAS[d]

    cuerpo = [f'<h1>¿A qué hora conviene cruzar por {e(g["corto"])} el {e(dia)}?</h1>']
    cuerpo.append(f'<p class="entrada">El {e(dia)}, {e(g["articulo"])} está en su mejor momento a las '
                  f'<strong>{mejor[0]:02d}:00</strong> ({e(humano(mejor[1]))}) y en el peor a las '
                  f'<strong>{peor[0]:02d}:00</strong> ({e(humano(peor[1]))}).</p>')
    cuerpo.append(tablero(ahora, [(cc["nombre"], g["puerto"], cc["clase"], cc["carril"])
                                  for cc, _, _ in vivos]))
    cuerpo.append(f'<h2>Hora por hora, los {e(PLURAL[d])}</h2>')
    cuerpo.append(f'<p>Mediana de espera en {e(c["largo"])}, hora de Tijuana.</p>')
    cuerpo.append(tabla_dia(celdas, d))
    tempranas = [m for h, m in horas if 4 <= h < 9]
    if tempranas:
        cuerpo.append(f'<p>De madrugada, entre las 04:00 y las 09:00, el {e(dia)} promedia '
                      f'{e(humano(int(G.mediana(tempranas))))}. Es el tramo que usa el que cruza a '
                      f'trabajar todos los días.</p>')
    cuerpo.append(f'<h2>Cómo se ve la semana completa</h2>')
    cuerpo.append(calor(celdas, resaltar_dia=d))
    otros = [(f"{g['slug']}/{DIAS_SLUG[o]}", DIAS[o].capitalize(), None)
             for o in dias_publicables(celdas) if o != d]
    if otros:
        cuerpo.append("<h2>Otros días</h2>")
        cuerpo.append(fichas(otros))
    otras = [(f"{o['slug']}/{DIAS_SLUG[d]}", f"{o['corto']} el {dia}", None)
             for o in GARITAS if o["slug"] != g["slug"] and o["slug"] in hermanas]
    if otras:
        cuerpo.append("<h2>Otras garitas</h2>")
        cuerpo.append(fichas(otras))
    cuerpo.append(vivo())

    faq = [(f"¿A qué hora cruzar por {g['nombre']} el {dia}?",
            f"El {dia}, la menor espera en {g['articulo']} es a las {mejor[0]:02d}:00, "
            f"con {humano(mejor[1])} de mediana. La peor es a las {peor[0]:02d}:00, "
            f"con {humano(peor[1])}.")]
    return {"ruta": f"{g['slug']}/{DIAS_SLUG[d]}",
            "titulo": f"A qué hora cruzar por {g['corto']} el {dia} | Garitas",
            "desc": (f"El {dia} conviene cruzar por {g['nombre']} a las {mejor[0]:02d}:00 "
                     f"({humano(mejor[1])}). Evita las {peor[0]:02d}:00 ({humano(peor[1])}). "
                     f"Hora por hora, con histórico propio."),
            "cuerpo": "\n".join(cuerpo), "jsonld": _faq(faq),
            "miga": _miga(("Garitas", "/"), (g["nombre"], g["slug"]), (dia.capitalize(), None))}


def pag_carril(g, c, celdas, n, ahora):
    x = extremos(celdas)
    if not x:
        return None
    cuerpo = [f'<h1>{e(g["nombre"])} por {e(c["nombre"])}: tiempo de espera por hora</h1>']
    cuerpo.append(f'<p class="entrada">Espera típica en {e(c["largo"])} de {e(g["articulo"])}, '
                  f'con {n:,} lecturas propias.</p>')
    cuerpo.append(tablero(ahora, [(c["nombre"], g["puerto"], c["clase"], c["carril"])]))
    cuerpo.append(bloque_extremos(x))
    cuerpo.append("<h2>Espera por hora y día de la semana</h2>")
    cuerpo.append(calor(celdas))
    cuerpo.append("<h2>Ver por día</h2>")
    cuerpo.append(fichas([(f"{g['slug']}/{DIAS_SLUG[d]}", DIAS[d].capitalize(), None)
                          for d in range(7)]))
    cuerpo.append(vivo())
    return {"ruta": f"{g['slug']}/{c['slug']}",
            "titulo": f"{g['nombre']} {c['nombre']}: espera por hora | Garitas",
            "desc": (f"Espera en {c['largo']} de {g['nombre']}. Mejor momento: "
                     f"{DIAS[x['mejor_dia']]} {x['mejor_hora']:02d}:00 con "
                     f"{humano(x['mejor_min'])}. Con histórico propio."),
            "cuerpo": "\n".join(cuerpo),
            "jsonld": _faq([(f"¿Cuánto se hace en el {c['nombre']} de {g['nombre']}?",
                             f"Entre {humano(x['mejor_min'])} en el mejor momento "
                             f"({DIAS[x['mejor_dia']]} {x['mejor_hora']:02d}:00) y "
                             f"{humano(x['peor_min'])} en el peor "
                             f"({DIAS[x['peor_dia']]} {x['peor_hora']:02d}:00).")]),
            "miga": _miga(("Garitas", "/"), (g["nombre"], g["slug"]),
                          (c["nombre"].capitalize(), None))}


# ── páginas de sitio ──────────────────────────────────────────────────────
def pag_inicio(cx, ahora, tz, resumen, disponibles=()):
    # Una casilla por garita, del carril que de verdad le importa a esa garita:
    # en el CBX nadie pregunta por los carros, y en Otay comercial nadie por SENTRI.
    porslug = {c["slug"]: c for c in CARRILES}
    ent = []
    for g in GARITAS:
        for pref in g["prefiere"]:
            c = porslug[pref]
            if _dato_ahora(ahora, g["puerto"], c["clase"], c["carril"]):
                etq = g["corto"] if pref in ("carros", "peatonal", "carga") else f"{g['corto']} {c['nombre']}"
                ent.append((etq, g["puerto"], c["clase"], c["carril"]))
                break
    # Y el SENTRI de las dos grandes aparte, que es media Tijuana.
    for g in GARITAS[:2]:
        c = porslug["sentri"]
        if _dato_ahora(ahora, g["puerto"], c["clase"], c["carril"]):
            ent.append((f"{g['corto']} SENTRI", g["puerto"], c["clase"], c["carril"]))
    # El numero primero: quien abre esto en la fila no viene a leer un parrafo.
    cuerpo = ['<h1>Garitas de Tijuana: cuánta fila hay ahorita</h1>',
              tablero(ahora, ent),
              '<p class="entrada">La espera de este momento en San Ysidro, Otay, Tecate, '
              'PedWest y el CBX — y, lo que no encuentras en otro lado, '
              '<strong>a qué hora conviene cruzar</strong>, calculado con historia propia.</p>']
    cuerpo.append("<h2>Escoge tu garita</h2>")
    cuerpo.append(fichas([(g["slug"], g["nombre"], resumen.get(g["slug"], ""))
                          for g in GARITAS if g["slug"] in resumen]))
    extras = [f for f in (
        ("mejor-hora", "La mejor hora de la semana", "las 168 horas, ordenadas"),
        ("regreso-a-tijuana", "El regreso a Tijuana", "el sentido sur, que CBP no mide"),
        ("comparar", "Comparar todos los cruces", "toda la frontera, ordenada"),
        ("historia", "Cómo ha cambiado desde 2011", "quince años de tendencia"),
        ("datos", "Bajar los datos", "abiertos, en CSV")) if f[0] in disponibles]
    if extras:
        cuerpo.append("<h2>Lo que nadie más te dice</h2>")
        cuerpo.append(fichas(extras))
    cuerpo.append("<h2>Por qué este sitio existe</h2>")
    cuerpo.append('<p>CBP publica cuánta fila hay <em>en este momento</em>, y nada más. '
                  'Cuando el número cambia, el anterior desaparece para siempre. Canadá sí publica '
                  'su histórico; Estados Unidos no, y nadie lo estaba guardando.</p>')
    cuerpo.append('<p>Este proyecto lo guarda desde hace meses, cada 15 minutos, de los '
                  'cincuenta y tantos cruces de la frontera. Con esa historia se puede contestar '
                  'la única pregunta que de verdad importa cuando vas a cruzar: '
                  '<strong>¿a qué hora me conviene salir?</strong></p>')
    cuerpo.append(vivo())
    return {"ruta": "", "titulo": "Garitas de Tijuana: cuánta fila hay ahorita y a qué hora cruzar",
            "desc": ("Tiempo de espera en las garitas de Tijuana ahora mismo: San Ysidro, Otay, "
                     "Tecate, PedWest y CBX. Y la mejor hora para cruzar cada día, con histórico propio."),
            "cuerpo": "\n".join(cuerpo),
            "jsonld": {"@context": "https://schema.org", "@type": "WebSite",
                       "name": "Garitas", "url": _url("/"), "inLanguage": "es-MX"}}


def pag_mejor_hora(cx, tz):
    bloques, filas_ld = [], []
    for g in GARITAS:
        vivos = carriles_con_datos(cx, g["puerto"], tz)
        if not vivos:
            continue
        c, celdas, n = vivos[0]
        con = sorted(((G.mediana(v), k) for k, v in celdas.items() if v))
        if len(con) < 20:
            continue
        bloques.append(f'<h2>{e(g["nombre"])}</h2>')
        bloques.append(f'<p>Las diez mejores horas de la semana en {e(c["largo"])}.</p>')
        f = ['<table class="lista"><thead><tr><th>día y hora</th><th>espera</th></tr></thead><tbody>']
        for m, (d, h) in con[:10]:
            f.append(f'<tr><td>{e(DIAS[d])} {h:02d}:00</td>'
                     f'<td class="num">{e(humano(m))}</td></tr>')
        f.append("</tbody></table>")
        bloques.append("".join(f))
        peor = con[-1]
        bloques.append(f'<p class="pie-nota">La peor: {e(DIAS[peor[1][0]])} a las '
                       f'{peor[1][1]:02d}:00, con {e(humano(peor[0]))}.</p>')
        filas_ld.append((f"¿Cuál es la mejor hora para cruzar por {g['nombre']}?",
                         f"El {DIAS[con[0][1][0]]} a las {con[0][1][1]:02d}:00, "
                         f"con {humano(con[0][0])} de espera típica."))
    if not bloques:
        return None
    cuerpo = ['<h1>La mejor hora para cruzar la garita</h1>',
              '<p class="entrada">Las 168 horas de la semana, ordenadas de menos a más fila, '
              'garita por garita. Calculado con el archivo propio, no con promedios generales.</p>']
    cuerpo += bloques
    return {"ruta": "mejor-hora", "titulo": "La mejor hora para cruzar la garita | Garitas",
            "desc": ("Las mejores y peores horas para cruzar por San Ysidro, Otay, Tecate y CBX, "
                     "ordenadas con datos reales de los últimos meses."),
            "cuerpo": "\n".join(cuerpo), "jsonld": _faq(filas_ld),
            "miga": _miga(("Garitas", "/"), ("Mejor hora", None))}


def pag_sur(cx, ahora, tz):
    """El dato exclusivo: el regreso a Tijuana. Caltrans lo publica con
    sensores fisicos, nadie lo archiva y ninguna app del nicho lo muestra."""
    est = G.leer_estado()
    filas, ent = [], []
    for codigo, nombre in G.SUR_RUTAS.values():
        act = est.get(f"{codigo}|pasajeros|general")
        if not act or act[1] is None:
            continue
        p15 = est.get(f"{codigo}|pasajeros|pron15")
        p30 = est.get(f"{codigo}|pasajeros|pron30")
        f = lambda d: "—" if not d or d[1] is None else humano(d[1])
        filas.append(f'<tr><td>{e(nombre)}</td><td class="num"><strong>{e(humano(act[1]))}</strong></td>'
                     f'<td class="num">{e(f(p15))}</td><td class="num">{e(f(p30))}</td></tr>')
        ent.append((nombre, codigo, "pasajeros", "general"))
    if not filas:
        return None
    sello = next((est[f"{c}|pasajeros|general"][3] for c, _ in G.SUR_RUTAS.values()
                  if est.get(f"{c}|pasajeros|general") and est[f"{c}|pasajeros|general"][3]), "")
    horas = G._edad_sello(sello, tz) if sello else None
    aviso = nota_sello = ""
    if horas is not None and horas > 2:
        aviso = (f'<div class="caja acento"><p><strong>Cuidado: este dato tiene '
                 f'{horas:.0f} horas.</strong> Caltrans firmó su página el {e(sello)} y no la ha '
                 f'vuelto a actualizar. Los números de abajo ya no son de ahora.</p></div>')
    elif horas is not None:
        nota_sello = (f'<p class="pie-nota">Firmado por Caltrans el {e(sello)}, '
                      f'hace {horas*60:.0f} minutos.</p>')

    hist = cx.execute(
        "SELECT puerto, capturado_utc, minutos FROM lecturas WHERE sentido='sur' "
        "AND carril='general' AND minutos<>''").fetchall()
    porruta = defaultdict(lambda: defaultdict(list))
    for h in hist:
        try:
            local = datetime.fromisoformat(h["capturado_utc"]).astimezone(tz)
        except ValueError:
            continue
        porruta[h["puerto"]][(local.weekday(), local.hour)].append(int(h["minutos"]))

    cuerpo = ['<h1>El regreso a Tijuana: cuánto se hace hacia el sur</h1>',
              '<p class="entrada">CBP solo mide lo que entra a Estados Unidos. '
              'El regreso lo mide <strong>Caltrans</strong>, con sensores físicos sobre el acceso '
              'a la garita — y ninguna de las apps de garita lo publica. Aquí sí, con pronóstico '
              'a 15 y 30 minutos.</p>',
              aviso,
              tablero(ahora, ent, "Hacia Tijuana, ahora mismo"),
              '<div class="desliz"><table class="lista"><thead><tr><th>ruta</th><th>ahora</th>'
              '<th>en 15 min</th><th>en 30 min</th></tr></thead><tbody>'
              + "".join(filas) + "</tbody></table></div>",
              nota_sello]
    for codigo, nombre in G.SUR_RUTAS.values():
        celdas = porruta.get(codigo)
        if not celdas or len([k for k, v in celdas.items() if v]) < MIN_CELDAS:
            continue
        cuerpo.append(f"<h2>{e(nombre)} · por hora y día</h2>")
        cuerpo.append(calor(celdas))
    cuerpo.append("<h2>Por qué esto no lo tiene nadie</h2>")
    cuerpo.append('<p>Caltrans publica estos números en una tabla que se sobrescribe sola. '
                  'Nadie los estaba guardando, así que el patrón del regreso —a qué hora se '
                  'hace bola para volver a Tijuana— simplemente no existía en ninguna parte. '
                  'Este archivo lo está construyendo desde cero.</p>')
    cuerpo.append('<p>Guardamos también los pronósticos a 15 y 30 minutos de Caltrans. '
                  'En unos meses vamos a poder medirle la puntería, y ese es un dato que '
                  'no tiene absolutamente nadie.</p>')
    cuerpo.append(vivo())
    return {"ruta": "regreso-a-tijuana",
            "titulo": "Regreso a Tijuana: espera hacia el sur en San Ysidro y Otay | Garitas",
            "desc": ("Cuánto se hace de regreso a Tijuana por I-5, I-805 y la 905, ahora mismo y "
                     "con pronóstico a 15 y 30 minutos. El sentido que CBP no mide."),
            "cuerpo": "\n".join(cuerpo),
            "miga": _miga(("Garitas", "/"), ("Regreso a Tijuana", None))}


def pag_comparar(cx):
    filas = cx.execute(
        "SELECT puerto_nombre, frontera, COUNT(*) n, AVG(CAST(minutos AS INTEGER)) prom, "
        "MIN(CAST(minutos AS INTEGER)) mn, MAX(CAST(minutos AS INTEGER)) mx "
        "FROM lecturas WHERE clase='pasajeros' AND carril='general' AND minutos<>'' "
        "AND sentido='norte' GROUP BY puerto HAVING n>=20 ORDER BY prom DESC").fetchall()
    if not filas:
        return None
    cuerpo = ['<h1>Todos los cruces de la frontera, comparados</h1>',
              '<p class="entrada">Los cruces terrestres a Estados Unidos ordenados por espera '
              f'promedio en carriles generales de carros. {len(filas)} cruces, con datos propios. '
              'Este cuadro no existe en ninguna otra parte.</p>',
              '<div class="desliz"><table class="lista"><thead><tr><th>cruce</th><th>frontera</th>'
              '<th>promedio</th><th>mínimo</th><th>máximo</th><th>lecturas</th>'
              '</tr></thead><tbody>']
    for f in filas:
        frontera = "México" if "Mexic" in (f["frontera"] or "") else "Canadá"
        cuerpo.append(f'<tr><td>{e(f["puerto_nombre"])}</td><td>{frontera}</td>'
                      f'<td class="num"><strong>{e(humano(f["prom"]))}</strong></td>'
                      f'<td class="num">{f["mn"]:.0f}</td><td class="num">{f["mx"]:.0f}</td>'
                      f'<td class="num">{f["n"]:,}</td></tr>')
    cuerpo.append("</tbody></table></div>")
    cuerpo.append('<p class="pie-nota">Promedio de todas las lecturas archivadas, incluidas las '
                  'horas muertas de la madrugada. Sirve para comparar cruces entre sí, no para '
                  'planear tu salida: para eso usa la tabla por hora de cada garita.</p>')
    return {"ruta": "comparar", "titulo": "Comparar todos los cruces de la frontera | Garitas",
            "desc": (f"Los {len(filas)} cruces terrestres a Estados Unidos ordenados por espera "
                     "promedio, con mínimo y máximo. Datos propios archivados cada 15 minutos."),
            "cuerpo": "\n".join(cuerpo),
            "miga": _miga(("Garitas", "/"), ("Comparar", None))}


def pag_historia():
    cx, n = G.cargar_historico()
    if not cx or n < 100:
        return None
    MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
             "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
    cuerpo = ['<h1>Cómo han cambiado las garitas desde 2011</h1>',
              '<p class="entrada">Promedio de espera año por año y mes por mes, encadenando las '
              'dos series abiertas de SANDAG: la mensual de 2011 a 2022 —un dataset que ellos '
              'mismos descontinuaron y nadie usa— y la diaria de 2023 en adelante.</p>']
    hubo = False
    for puerto, nombre in (("250401", "San Ysidro"), ("250601", "Otay Mesa")):
        filas = cx.execute(
            "SELECT capturado_utc, minutos FROM h WHERE puerto=? AND clase='pasajeros' "
            "AND carril='general' AND minutos<>''", (puerto,)).fetchall()
        if len(filas) < 60:
            continue
        hubo = True
        pormes, poranio = defaultdict(list), defaultdict(list)
        for f in filas:
            try:
                d = datetime.fromisoformat(f["capturado_utc"])
            except ValueError:
                continue
            pormes[d.month].append(int(f["minutos"]))
            poranio[d.year].append(int(f["minutos"]))
        cuerpo.append(f"<h2>{e(nombre)}</h2>")
        cuerpo.append('<div class="desliz"><table class="lista"><thead><tr><th>año</th>'
                      '<th>espera promedio</th><th></th></tr></thead><tbody>')
        mx = max(G.mediana(v) for v in poranio.values()) or 1
        for a, v in sorted(poranio.items()):
            m = G.mediana(v)
            cuerpo.append(f'<tr><td>{a}</td><td class="num">{e(humano(m))}</td>'
                          f'<td style="width:55%"><span style="display:block;height:12px;'
                          f'width:{max(3, int(100*m/mx))}%;background:var(--s{nivel(m)})"></span></td></tr>')
        cuerpo.append("</tbody></table></div>")
        peor = max(pormes.items(), key=lambda kv: G.mediana(kv[1]))
        mejor = min(pormes.items(), key=lambda kv: G.mediana(kv[1]))
        cuerpo.append(f'<p>Por temporada, el mes más pesado en {e(nombre)} es '
                      f'<strong>{e(MESES[peor[0]-1])}</strong> ({e(humano(G.mediana(peor[1])))}) '
                      f'y el más ligero <strong>{e(MESES[mejor[0]-1])}</strong> '
                      f'({e(humano(G.mediana(mejor[1])))}).</p>')
    if not hubo:
        return None
    cuerpo.append("<h2>Una advertencia honesta</h2>")
    cuerpo.append('<p>El tramo 2011–2022 son promedios <em>mensuales</em> y el de 2023 en adelante '
                  'son promedios <em>diarios</em>. No son la misma medida, y por eso la serie sirve '
                  'para ver la tendencia y la temporada, no para comparar un año contra otro al '
                  'minuto. Lo decimos porque casi nadie lo dice.</p>')
    return {"ruta": "historia", "titulo": "Cómo han cambiado las garitas desde 2011 | Garitas",
            "desc": ("Espera promedio en San Ysidro y Otay Mesa año por año desde 2011 y por "
                     "temporada, con las dos series abiertas de SANDAG encadenadas."),
            "cuerpo": "\n".join(cuerpo),
            "miga": _miga(("Garitas", "/"), ("Historia", None))}


def pag_datos(repo, total, desde, hasta):
    """La pagina que consigue enlaces: medios y agencias citan a quien
    regala el dato limpio."""
    cuerpo = ['<h1>Los datos, abiertos</h1>',
              '<p class="entrada">Todo lo que ves aquí sale de un archivo público que cualquiera '
              'puede bajar, revisar y usar. Si eres periodista, investigador o desarrollador, '
              'llévatelo — solo pedimos que digas de dónde salió.</p>']
    cuerpo.append(f'<div class="caja"><div class="dato">'
                  f'<div><span class="k">Lecturas archivadas</span>'
                  f'<span class="v">{total:,}</span></div>'
                  f'<div><span class="k">Desde</span><span class="v">{e(desde)}</span></div>'
                  f'<div><span class="k">Cadencia</span><span class="v">15 min</span></div>'
                  f"</div></div>")
    cuerpo.append("<h2>Qué hay</h2>")
    cuerpo.append('<table class="lista"><thead><tr><th>archivo</th><th>qué trae</th></tr></thead>'
                  '<tbody>'
                  '<tr><td><code>datos/AAAA-MM.csv</code></td><td>una lectura por cambio, de los '
                  '~56 cruces, con clase, carril, minutos y carriles abiertos. Un archivo por mes; '
                  'los meses cerrados van comprimidos.</td></tr>'
                  '<tr><td><code>historico/sandag.csv</code></td><td>promedio diario de SANDAG, '
                  'de 2023 a hoy.</td></tr>'
                  '<tr><td><code>historico/sandag_mensual.csv</code></td><td>promedio mensual de '
                  'SANDAG, de 2011 a 2022. Dataset descontinuado.</td></tr>'
                  '<tr><td><code>bitacora.csv</code></td><td>cada intento de captura, con duración '
                  'y errores. Para que puedas verificar que el archivo es continuo.</td></tr>'
                  '<tr><td><code>ahora.json</code></td><td>el estado de este momento, en JSON.</td></tr>'
                  "</tbody></table>")
    if repo:
        cuerpo.append(f'<p><a href="{e(repo)}">Bajar todo del repositorio</a> · '
                      f'<a href="{e(_act("ahora.json"))}">ver <code>ahora.json</code></a></p>')
    cuerpo.append("<h2>Cómo citarlo</h2>")
    cuerpo.append('<p>«Archivo abierto de tiempos de cruce fronterizo», con enlace a este sitio. '
                  'Los datos de origen son de CBP y Caltrans, obra del gobierno de Estados Unidos '
                  'y por lo tanto de dominio público; lo que aportamos es haberlos guardado.</p>')
    cuerpo.append("<h2>¿Eres medio de comunicación?</h2>")
    cuerpo.append('<p>Varios medios de Tijuana y San Diego publican el reporte de garitas a mano, '
                  'varias veces al día. Si quieres el dato en automático —un JSON, un widget, o lo '
                  'que te sirva— está disponible y es gratis, con atribución.</p>')
    cuerpo.append("<h2>Las limitaciones, dichas de frente</h2>")
    cuerpo.append('<p>Esto guarda lo que CBP <em>dice</em>, no lo que de verdad tardaste. Se sabe '
                  'que el número oficial se queda corto; es la queja de todas las reseñas de las '
                  'apps de garita. Lo que este archivo da con confianza es <strong>la forma</strong>: '
                  'el patrón por hora, por día y por temporada, que es real aunque el nivel esté '
                  'mal calibrado.</p>')
    return {"ruta": "datos", "titulo": "Datos abiertos de tiempos de cruce fronterizo | Garitas",
            "desc": (f"{total:,} lecturas de espera en los cruces México–EE.UU., archivadas cada "
                     "15 minutos desde " + desde + ". Abiertas, en CSV, para periodistas e "
                     "investigadores."),
            "cuerpo": "\n".join(cuerpo),
            "jsonld": {"@context": "https://schema.org", "@type": "Dataset",
                       "name": "Archivo abierto de tiempos de cruce fronterizo México–EE.UU.",
                       "description": ("Lecturas de tiempo de espera de los cruces terrestres "
                                       "México–Estados Unidos y Canadá–Estados Unidos, archivadas "
                                       "cada 15 minutos desde la API pública de CBP, más el sentido "
                                       "sur de Caltrans."),
                       "temporalCoverage": f"{desde}/{hasta}",
                       "license": "https://creativecommons.org/publicdomain/zero/1.0/",
                       "isAccessibleForFree": True,
                       "creator": {"@type": "Organization", "name": "Garitas"},
                       **({"url": repo} if repo else {})},
            "miga": _miga(("Garitas", "/"), ("Datos abiertos", None))}


# ── ensamblado ────────────────────────────────────────────────────────────
def sitemap(rutas):
    hoy = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    urls = "".join(
        f"<url><loc>{e(_url(r))}</loc><lastmod>{hoy}</lastmod>"
        f"<changefreq>{'hourly' if r in ('', 'regreso-a-tijuana') else 'daily'}</changefreq>"
        f"<priority>{'1.0' if r == '' else '0.8' if '/' not in r else '0.6'}</priority></url>"
        for r in rutas)
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            + urls + "</urlset>\n")


def robots():
    linea = f"Sitemap: {DOMINIO.rstrip('/')}/sitemap.xml\n" if DOMINIO else ""
    return "User-agent: *\nAllow: /\n\n" + linea


def construir(destino=DESTINO, repo=""):
    tz = G.zona()
    # Un semestre basta para las tablas por hora y acota el costo de cada
    # corrida; la historia larga vive en /historia/, que lee historico/.
    cx, total = G.cargar_todo(meses=MESES_SITIO)
    ahora = leer_ahora(tz)
    os.makedirs(destino, exist_ok=True)

    rango = cx.execute("SELECT MIN(capturado_utc) a, MAX(capturado_utc) b "
                       "FROM lecturas").fetchone()
    desde = (rango["a"] or "")[:10] or "hoy"
    hasta = (rango["b"] or "")[:10] or "hoy"
    sello = (f"Actualizado {datetime.now(tz).strftime('%d/%m/%Y %H:%M')} "
             f"(hora de Tijuana) · {total:,} lecturas archivadas.")

    # Primera pasada: cuales garitas tienen material para publicarse. Hay que
    # saberlo ANTES de escribir nada, porque cada pagina enlaza a las demas y
    # un enlace a una pagina que no existe es un 404 servido a Google.
    con_datos = {g["slug"]: carriles_con_datos(cx, g["puerto"], tz) for g in GARITAS}
    publicables = {k for k, v in con_datos.items() if v}

    paginas, resumen = [], {}
    for g in GARITAS:
        if g["slug"] not in publicables:
            continue
        vivos = con_datos[g["slug"]]
        p = pag_garita(g, vivos, ahora)
        if not p:
            continue
        paginas.append(p)
        x = extremos(vivos[0][1])
        if x:
            resumen[g["slug"]] = (f"mejor: {DIAS[x['mejor_dia']]} "
                                  f"{x['mejor_hora']:02d}:00 · {humano(x['mejor_min'])}")
        c0, celdas0, _ = vivos[0]
        for d in dias_publicables(celdas0):
            pd = pag_dia(g, d, celdas0, c0, ahora, vivos, publicables)
            if pd:
                paginas.append(pd)
        for c, celdas, n in vivos[1:]:
            pc = pag_carril(g, c, celdas, n, ahora)
            if pc:
                paginas.append(pc)

    # Las especiales primero: la portada necesita saber cuales salieron para
    # no ofrecer fichas a paginas que no existen.
    for f in (lambda: pag_mejor_hora(cx, tz),
              lambda: pag_sur(cx, ahora, tz),
              lambda: pag_comparar(cx),
              pag_historia,
              lambda: pag_datos(repo, total, desde, hasta)):
        p = f()
        if p:
            paginas.append(p)
    disponibles = {p["ruta"] for p in paginas}
    paginas.insert(0, pag_inicio(cx, ahora, tz, resumen, disponibles))

    # El menu solo puede enlazar a lo que se publico. Si un dia no hay
    # historico o no hay sur, esas paginas no existen y enlazarlas seria
    # mandar a Google -y al lector- a un 404.
    hechas = {p["ruta"] for p in paginas}
    nav = [(u, t) for u, t in NAV if u == "/" or u.strip("/") in hechas]
    for p in paginas:
        escribir(destino, p["ruta"],
                 pagina(p["ruta"], p["titulo"], corta(p["desc"]), p["cuerpo"],
                        p.get("jsonld"), sello, p.get("miga"), nav=nav))

    with open(os.path.join(destino, "estilo.css"), "w", encoding="utf-8") as fh:
        fh.write(CSS)
    with open(os.path.join(destino, "ahora.json"), "w", encoding="utf-8") as fh:
        json.dump(ahora, fh, ensure_ascii=False, separators=(",", ":"))
    with open(os.path.join(destino, "sitemap.xml"), "w", encoding="utf-8") as fh:
        fh.write(sitemap(sorted(p["ruta"] for p in paginas)))
    with open(os.path.join(destino, "robots.txt"), "w", encoding="utf-8") as fh:
        fh.write(robots())
    # Cloudflare Pages sirve /x/ desde /x/index.html sin ayuda, pero un 404
    # propio evita que un enlace roto se vea como sitio caido.
    escribir(destino, "404", pagina(
        "404", "Esa página no existe | Garitas",
        "La página que buscas no existe. Ve a la portada para ver la fila de ahorita.",
        '<h1>Esa página no existe</h1><p>Puede que la garita que buscas todavía no tenga '
        f'suficiente historia para publicarla. <a href="{_rel("/")}">Ve a la portada</a> para ver '
        'la fila de este momento.</p>', None, sello, None, sin_indexar=True, nav=nav))
    return {"paginas": len(paginas), "lecturas": total, "desde": desde}


def solo_ahora(destino=DESTINO):
    """Cada 15 minutos: 2 KB en vez de regenerar 80 paginas."""
    os.makedirs(destino, exist_ok=True)
    with open(os.path.join(destino, "ahora.json"), "w", encoding="utf-8") as fh:
        json.dump(leer_ahora(G.zona()), fh, ensure_ascii=False, separators=(",", ":"))


def _sitio_reciente(destino, minutos):
    portada = os.path.join(destino, "index.html")
    if not minutos or not os.path.exists(portada):
        return False
    return (time.time() - os.path.getmtime(portada)) / 60 < minutos


def main():
    global DOMINIO, ESTADO_URL, MESES_SITIO, BASE
    p = argparse.ArgumentParser(description="genera el sitio estatico")
    p.add_argument("--destino", default=DESTINO)
    p.add_argument("--dominio", default="", help="https://tudominio.com, para las URLs canonicas")
    p.add_argument("--base", default="",
                   help="prefijo si el sitio no vive en la raiz, p.ej. /garitas")
    p.add_argument("--repo", default="", help="URL del repositorio, para la pagina de datos")
    p.add_argument("--estado-url", default="",
                   help="URL cruda de estado.json (el raw de tu repo) para refrescar cada 15 min")
    p.add_argument("--meses", type=int, default=MESES_SITIO,
                   help="cuantos archivos mensuales leer; 0 = todos")
    p.add_argument("--si-viejo", type=int, default=0, metavar="MIN",
                   help="solo regenerar si el sitio ya tiene mas de MIN minutos")
    p.add_argument("--solo-ahora", action="store_true",
                   help="solo reescribir ahora.json (barato, cada 15 min)")
    a = p.parse_args()
    DOMINIO = a.dominio.rstrip("/")
    BASE = ("/" + a.base.strip("/")) if a.base.strip("/") else ""
    ESTADO_URL = a.estado_url.strip()
    MESES_SITIO = a.meses
    if a.solo_ahora:
        solo_ahora(a.destino)
        print("ahora.json actualizado.")
        return 0
    if _sitio_reciente(a.destino, a.si_viejo):
        solo_ahora(a.destino)
        print(f"El sitio tiene menos de {a.si_viejo} min; solo actualice ahora.json.")
        return 0
    inicio = time.time()
    r = construir(a.destino, a.repo)
    print(f"{r['paginas']} paginas · {r['lecturas']:,} lecturas · desde {r['desde']} "
          f"· {time.time()-inicio:.1f}s -> {a.destino}/")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
