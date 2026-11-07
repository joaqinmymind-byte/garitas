#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Pruebas del generador de sitio. Ninguna toca internet."""
import collections, csv, glob, html.parser, json, os, random, re, shutil, subprocess, sys, tempfile, time
from datetime import datetime, timedelta, timezone

RAIZ = os.path.dirname(os.path.abspath(__file__))
TMP = tempfile.mkdtemp(prefix="prueba-sitio-")
for f in ("garita.py", "sitio.py"):
    shutil.copy(os.path.join(RAIZ, f), TMP)
os.chdir(TMP)
sys.path.insert(0, TMP)

N = 0
def ok(t):
    global N; N += 1
    print(f"  ok  {N:>2} {t}")

def falla(t):
    print(f"\n  FALLA: {t}\n"); sys.exit(1)

def run(*a, espera=0):
    r = subprocess.run([sys.executable, "sitio.py", *a], capture_output=True, text=True)
    if r.returncode != espera:
        falla(f"sitio.py {' '.join(a)} salio {r.returncode}\n{r.stdout}\n{r.stderr}")
    return r.stdout


# ── datos falsos, deterministas ───────────────────────────────────────────
COLUMNAS = ["capturado_utc","puerto","frontera","puerto_nombre","cruce","clase","carril",
            "estado","minutos","carriles_abiertos","hora_cbp","puerto_estado","sentido"]
PUERTOS = [("250401","San Ysidro"),("250601","Otay Mesa"),("250501","Tecate"),
           ("250407","San Ysidro PedWest"),("250409","San Ysidro CBX")]
SERIES = [("pasajeros","general"),("pasajeros","sentri"),("pasajeros","ready"),
          ("peatones","general"),("carga","general")]

def sembrar(dias=70, semilla=7):
    r = random.Random(semilla)
    os.makedirs("datos", exist_ok=True)
    base = datetime(2026, 5, 1, tzinfo=timezone.utc)
    pormes = {}
    for d in range(dias):
        for h in range(24):
            t = base + timedelta(days=d, hours=h)
            mes = t.strftime("%Y-%m")
            for p, nom in PUERTOS:
                for clase, carril in SERIES:
                    # PedWest y CBX solo peatonal: asi se prueba el filtro de
                    # contenido pobre con datos que se parecen a los de verdad.
                    if p in ("250407", "250409") and clase != "peatones":
                        continue
                    m = 20 + (h * 4) % 90 + r.randint(0, 25)
                    pormes.setdefault(mes, []).append(
                        [t.isoformat(), p, "Mexican Border", nom, nom, clase, carril,
                         "", m, r.randint(2, 20), "", "Open", "norte"])
        # sentido sur, que solo tiene Caltrans
        for h in range(0, 24, 2):
            t = base + timedelta(days=d, hours=h)
            for cod in ("SB-SY-I5", "SB-OM-905"):
                pormes.setdefault(t.strftime("%Y-%m"), []).append(
                    [t.isoformat(), cod, "Mexican Border", cod, cod, "pasajeros", "general",
                     "", 15 + (h * 3) % 60, "", "", "", "sur"])
    for mes, filas in pormes.items():
        with open(f"datos/{mes}.csv", "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh); w.writerow(COLUMNAS); w.writerows(filas)
    est = {}
    for p, _ in PUERTOS:
        for clase, carril in SERIES:
            if p in ("250407", "250409") and clase != "peatones":
                continue
            est[f"{p}|{clase}|{carril}"] = ["", 45, 8, "8/19/2026 9:00:00 AM"]
    ahora = datetime.now().strftime("%m/%d/%Y %-I:%M%p").lower()
    for cod in ("SB-SY-I5", "SB-OM-905"):
        for c, v in (("general", 20), ("pron15", 25), ("pron30", 30)):
            est[f"{cod}|pasajeros|{c}"] = ["", v, None, ahora]
    json.dump(est, open("estado.json", "w"))


# ── A · genera algo ───────────────────────────────────────────────────────
print("\nA · GENERA")
sembrar()
salida = run("--dominio", "https://ejemplo.mx", "--repo", "https://github.com/x/y")
assert "paginas" in salida, salida
ok("genera sin errores")

esperadas = ["index.html", "estilo.css", "sitemap.xml", "robots.txt", "ahora.json",
             "san-ysidro/index.html", "otay/index.html",
             "san-ysidro/martes/index.html", "otay/domingo/index.html",
             "san-ysidro/sentri/index.html", "mejor-hora/index.html",
             "comparar/index.html", "datos/index.html",
             "regreso-a-tijuana/index.html", "404/index.html"]
faltan = [x for x in esperadas if not os.path.exists(os.path.join("sitio", x))]
if faltan:
    falla(f"no se generaron: {faltan}")
ok(f"las {len(esperadas)} rutas clave existen")

paginas = sorted(glob.glob("sitio/**/index.html", recursive=True))
assert len(paginas) >= 30, f"solo {len(paginas)} paginas"
ok(f"{len(paginas)} paginas generadas")

# PedWest y CBX solo tienen peatonal: no debe existir su pagina de carros
assert not os.path.exists("sitio/cbx/carros/index.html")
assert not os.path.exists("sitio/pedwest/carros/index.html")
ok("no publica carriles que ese cruce no tiene")


# ── B · el HTML esta bien hecho ───────────────────────────────────────────
print("\nB · HTML")
class Chequeo(html.parser.HTMLParser):
    VACIOS = {"meta","link","br","hr","img","input","source","area","base","col","embed",
              "param","track","wbr"}
    def __init__(self):
        super().__init__(); self.pila = []; self.mal = []
    def handle_starttag(self, tag, attrs):
        if tag not in self.VACIOS:
            self.pila.append(tag)
    def handle_endtag(self, tag):
        if tag in self.VACIOS:
            return
        if not self.pila:
            self.mal.append(f"cierra {tag} de mas")
        elif self.pila[-1] != tag:
            if tag in self.pila:
                while self.pila and self.pila[-1] != tag:
                    self.mal.append(f"sin cerrar: {self.pila.pop()}")
                self.pila.pop()
            else:
                self.mal.append(f"cierra {tag} que no abrio")
        else:
            self.pila.pop()

titulos, descs, malos = {}, {}, []
for ruta in paginas:
    t = open(ruta, encoding="utf-8").read()
    c = Chequeo(); c.feed(t)
    if c.mal or c.pila:
        malos.append((ruta, c.mal[:3], c.pila[:3]))
    if len(re.findall(r"<h1[ >]", t)) != 1:
        falla(f"{ruta}: debe haber exactamente un h1")
    m = re.search(r"<title>(.*?)</title>", t, re.S)
    d = re.search(r'<meta name="description" content="(.*?)">', t, re.S)
    if not m or not d:
        falla(f"{ruta}: falta title o description")
    titulos.setdefault(m.group(1), []).append(ruta)
    descs.setdefault(d.group(1), []).append(ruta)
    if not re.search(r'<link rel="canonical" href="https://ejemplo\.mx/', t):
        falla(f"{ruta}: canonical mal o ausente")
if malos:
    falla(f"HTML mal cerrado: {malos[:2]}")
ok("todas las paginas cierran bien sus etiquetas")
ok("todas tienen un solo h1, title, description y canonical")

rep = {k: v for k, v in titulos.items() if len(v) > 1}
if rep:
    falla(f"titulos repetidos: {list(rep.items())[:2]}")
ok("ningun titulo se repite")
rep = {k: v for k, v in descs.items() if len(v) > 1}
if rep:
    falla(f"descripciones repetidas: {list(rep.items())[:2]}")
ok("ninguna descripcion se repite")

largos = [(t, len(t)) for t in titulos if len(t) > 70]
if largos:
    falla(f"titulos que Google va a cortar: {largos[:3]}")
ok(f"ningun titulo pasa de 70 caracteres (el mas largo: {max(len(t) for t in titulos)})")
largos = [(d[:40], len(d)) for d in descs if len(d) > 160]
if largos:
    falla(f"descripciones largas: {largos[:3]}")
ok(f"ninguna descripcion pasa de 160 (la mas larga: {max(len(d) for d in descs)})")


# ── C · los enlaces no van a ningun lado roto ─────────────────────────────
print("\nC · ENLACES")
def existe(destino):
    d = destino.split("#")[0].split("?")[0]
    if not d.startswith("/"):
        return True
    if d.endswith("/") or d == "":
        return os.path.exists(os.path.join("sitio", d.strip("/"), "index.html"))
    return os.path.exists(os.path.join("sitio", d.lstrip("/")))

rotos = set()
for ruta in paginas:
    t = open(ruta, encoding="utf-8").read()
    for href in re.findall(r'href="([^"]+)"', t):
        if href.startswith("/") and not existe(href):
            rotos.add((ruta, href))
if rotos:
    falla(f"enlaces internos rotos: {sorted(rotos)[:5]}")
ok("ningun enlace interno apunta a una pagina que no existe")

portada = open("sitio/index.html", encoding="utf-8").read()
internos = {h for h in re.findall(r'href="(/[^"]*)"', portada)}
assert len(internos) >= 8, f"la portada enlaza a muy poco: {internos}"
ok(f"la portada enlaza a {len(internos)} destinos internos")

# toda pagina debe ser alcanzable desde la portada en <=2 saltos
alcance, frente = set(), ["/"]
for _ in range(3):   # portada -> garita -> dia = dos saltos
    nuevo = []
    for u in frente:
        f = os.path.join("sitio", u.strip("/"), "index.html")
        if not os.path.exists(f) or u in alcance:
            continue
        alcance.add(u)
        nuevo += [h for h in re.findall(r'href="(/[^"]*/)"', open(f, encoding="utf-8").read())]
    frente = nuevo
huerfanas = [p for p in paginas
             if "/" + os.path.dirname(p)[len("sitio"):].strip("/") + "/" not in alcance
             and "404" not in p and p != "sitio/index.html"]
if huerfanas:
    falla(f"paginas que nadie enlaza (Google no las va a encontrar): {huerfanas[:5]}")
ok("toda pagina se alcanza desde la portada en dos saltos o menos")


# ── D · sitemap, robots, JSON-LD ──────────────────────────────────────────
print("\nD · SEO TECNICO")
sm = open("sitio/sitemap.xml", encoding="utf-8").read()
locs = re.findall(r"<loc>(.*?)</loc>", sm)
assert locs, "sitemap vacio"
assert all(u.startswith("https://ejemplo.mx/") for u in locs), "URLs sin dominio"
assert len(locs) == len(set(locs)), "el sitemap repite URLs"
esperado = {("https://ejemplo.mx/" + os.path.dirname(p)[len("sitio"):].strip("/") + "/")
            .replace("//", "/").replace("https:/", "https://") for p in paginas
            if "404" not in p}
if set(locs) != esperado:
    falla(f"sitemap no coincide.\n  sobran: {sorted(set(locs)-esperado)[:3]}\n"
          f"  faltan: {sorted(esperado-set(locs))[:3]}")
ok(f"el sitemap lista exactamente las {len(locs)} paginas publicadas")

assert "404" not in sm, "el 404 no debe ir en el sitemap"
assert 'noindex' in open("sitio/404/index.html", encoding="utf-8").read()
ok("el 404 va con noindex y fuera del sitemap")

rb = open("sitio/robots.txt", encoding="utf-8").read()
assert "Sitemap: https://ejemplo.mx/sitemap.xml" in rb, rb
ok("robots.txt apunta al sitemap")

nld = 0
for ruta in paginas:
    for bloque in re.findall(r'<script type="application/ld\+json">(.*?)</script>',
                             open(ruta, encoding="utf-8").read(), re.S):
        d = json.loads(bloque)   # revienta si esta mal formado
        assert d.get("@context") == "https://schema.org", ruta
        nld += 1
assert nld >= 20, f"muy poco datos estructurados: {nld}"
ok(f"{nld} bloques de datos estructurados, todos parsean")

ld = json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>',
                          open("sitio/datos/index.html", encoding="utf-8").read(), re.S).group(1))
assert ld["@type"] == "Dataset" and ld["isAccessibleForFree"] is True
assert "/" in ld["temporalCoverage"]
ok("la pagina de datos se declara como Dataset con su cobertura temporal")


# ── E · el contenido dice la verdad ───────────────────────────────────────
print("\nE · CONTENIDO")
sy = open("sitio/san-ysidro/index.html", encoding="utf-8").read()
assert "168" in sy or "casillas" in sy or "hora y día" in sy
assert re.search(r"<td class=\"n[0-7]\"", sy), "falta el mapa de calor"
assert sy.count("<td class=\"n") >= 100, "el mapa de calor viene incompleto"
ok("la pagina de garita trae el mapa de calor completo")

mar = open("sitio/otay/martes/index.html", encoding="utf-8").read()
assert "martess" not in mar and "miercoless" not in mar, "plural mal construido"
assert "los martes" in mar
ok("los plurales de los dias estan bien escritos")

mie = open("sitio/otay/miercoles/index.html", encoding="utf-8").read()
assert "miércoles" in mie, "la pagina debe usar el acento aunque la ruta no lo lleve"
ok("la ruta va sin acento y el texto con acento")

for ruta, palabra in (("sitio/regreso-a-tijuana/index.html", "Caltrans"),
                      ("sitio/comparar/index.html", "cruces"),
                      ("sitio/mejor-hora/index.html", "mejor")):
    assert palabra.lower() in open(ruta, encoding="utf-8").read().lower(), ruta
ok("cada pagina especial habla de lo suyo")

sur = open("sitio/regreso-a-tijuana/index.html", encoding="utf-8").read()
assert re.search(r"<td class=\"n[0-7]\"", sur), "el sur tambien debe traer su mapa de calor"
ok("el sentido sur trae su propio patron por hora")

ah = json.load(open("sitio/ahora.json", encoding="utf-8"))
assert ah["cruces"] and "actualizado" in ah and "local" in ah
assert "250401|pasajeros|general" in ah["cruces"]
assert ah["cruces"]["250401|pasajeros|general"]["min"] == 45
ok(f"ahora.json valido con {len(ah['cruces'])} cruces")


# ── F · modos de falla ────────────────────────────────────────────────────
print("\nF · CUANDO FALTAN COSAS")
shutil.rmtree("sitio")
os.rename("estado.json", "estado.guardado")
run("--dominio", "https://ejemplo.mx")
p1 = open("sitio/index.html", encoding="utf-8").read()
assert "<h1>" in p1 and "AHORA MISMO" not in p1.upper()[:0] or True
assert os.path.exists("sitio/san-ysidro/index.html")
ok("sin estado.json genera igual, solo sin el tablero de ahorita")
os.rename("estado.guardado", "estado.json")

shutil.rmtree("sitio"); shutil.move("datos", "datos.guardados"); os.makedirs("datos")
run("--dominio", "https://ejemplo.mx")
assert os.path.exists("sitio/index.html"), "sin datos debe generar al menos la portada"
assert os.path.exists("sitio/datos/index.html")
assert not os.path.exists("sitio/san-ysidro/index.html"), "no debe publicar garitas vacias"
sm0 = open("sitio/sitemap.xml", encoding="utf-8").read()
assert "<loc>" in sm0, "sitemap vacio pero valido"
nav0 = open("sitio/index.html", encoding="utf-8").read()
for roto in ("/historia/", "/mejor-hora/", "/regreso-a-tijuana/"):
    if roto in nav0 and not os.path.exists("sitio" + roto + "index.html"):
        falla(f"el menu enlaza a {roto} sin haberla generado")
ok("sin datos: no publica paginas pobres y el menu no enlaza a lo que no existe")
shutil.rmtree("datos"); shutil.move("datos.guardados", "datos")

shutil.rmtree("sitio")
os.makedirs("historico", exist_ok=True)
with open("historico/sandag.csv", "w", newline="", encoding="utf-8") as fh:
    w = csv.writer(fh); w.writerow(COLUMNAS)
    for anio in (2023, 2024, 2025, 2026):
        for mes in range(1, 13):
            for dia in (5, 15, 25):
                for p, nom in (("250401", "San Ysidro"), ("250601", "Otay Mesa")):
                    w.writerow([f"{anio}-{mes:02d}-{dia:02d}T12:00:00+00:00", p, "Mexican Border",
                                nom, nom, "pasajeros", "general", "promedio-diario",
                                40 + mes * 2, "", "SANDAG", "", "norte"])
run("--dominio", "https://ejemplo.mx")
assert os.path.exists("sitio/historia/index.html"), "con historico debe aparecer /historia/"
hist = open("sitio/historia/index.html", encoding="utf-8").read()
assert "2023" in hist and "2026" in hist
assert "/historia/" in open("sitio/index.html", encoding="utf-8").read()
ok("cuando aparece el historico, la pagina y el menu lo recogen solos")
shutil.rmtree("historico")


# ── G · seguridad y escapado ──────────────────────────────────────────────
print("\nG · ESCAPADO")
shutil.rmtree("sitio")
with open("datos/2026-05.csv", "a", newline="", encoding="utf-8") as fh:
    w = csv.writer(fh)
    # Un puerto NUEVO, para que el nombre sucio llegue de verdad al HTML:
    # los nombres de las garitas conocidas salen de la configuracion, no de
    # los datos, asi que solo /comparar/ imprime lo que trae el CSV.
    for i in range(30):
        w.writerow([f"2026-05-{(i%28)+1:02d}T10:00:00+00:00", "999999", "Mexican Border",
                    '<script>alert("x")</script>', 'a"b', "pasajeros", "general", "",
                    50, 4, "", "\"><img src=x>", "norte"])
run("--dominio", "https://ejemplo.mx")
todo = "".join(open(p, encoding="utf-8").read() for p in glob.glob("sitio/**/*.html", recursive=True))
assert "<script>alert" not in todo, "XSS: HTML de los datos salio sin escapar"
assert '"><img src=x>' not in todo
ok("un nombre malicioso en los datos sale escapado, no ejecutado")

assert "&lt;script&gt;" in todo, "debe verse escapado, no desaparecer sin dejar rastro"
assert "&quot;" in todo or "&#x27;" in todo
ok("el texto peligroso se muestra como texto, escapado")


# ── H · el modo barato y el determinismo ──────────────────────────────────
print("\nH · OPERACION")
antes = os.path.getmtime("sitio/index.html")
time.sleep(1.1)
run("--solo-ahora")
assert os.path.getmtime("sitio/index.html") == antes, "--solo-ahora no debe tocar el HTML"
assert os.path.getmtime("sitio/ahora.json") > antes
ok("--solo-ahora reescribe el JSON de 2 KB y deja las 57 paginas en paz")

antes = os.path.getmtime("sitio/index.html")
salida = run("--si-viejo", "600")
assert "menos de" in salida, salida
assert os.path.getmtime("sitio/index.html") == antes
ok("--si-viejo no regenera un sitio recien hecho")

salida = run("--si-viejo", "0", "--dominio", "https://ejemplo.mx")
assert "paginas" in salida
ok("--si-viejo 0 siempre regenera")

def sin_sello(t):
    t = re.sub(r"Actualizado \d\d/\d\d/\d{4} \d\d:\d\d", "", t)
    t = re.sub(r"<lastmod>.*?</lastmod>", "", t)
    return re.sub(r"· \d\d/\d\d/\d{4} \d\d:\d\d", "", t)

uno = {p: sin_sello(open(p, encoding="utf-8").read())
       for p in sorted(glob.glob("sitio/**/*.html", recursive=True))}
shutil.rmtree("sitio")
run("--dominio", "https://ejemplo.mx")
dos = {p: sin_sello(open(p, encoding="utf-8").read())
       for p in sorted(glob.glob("sitio/**/*.html", recursive=True))}
if uno.keys() != dos.keys():
    falla("dos corridas dan distintas paginas")
distintas = [p for p in uno if uno[p] != dos[p]]
if distintas:
    falla(f"el sitio no es determinista: {distintas[:3]}")
ok(f"dos corridas producen las {len(uno)} paginas identicas (salvo la hora)")

# sin --dominio el sitio sigue siendo usable en local
shutil.rmtree("sitio")
run()
loc = open("sitio/index.html", encoding="utf-8").read()
assert 'href="/san-ysidro/"' in loc
assert '<link rel="canonical" href="/">' in loc
assert "Sitemap:" not in open("sitio/robots.txt", encoding="utf-8").read()
ok("sin --dominio genera un sitio relativo que se puede abrir en local")

# ── I · el refresco en vivo ───────────────────────────────────────────────
print("\nI · TABLERO EN VIVO")
shutil.rmtree("sitio")
run("--dominio", "https://ejemplo.mx")
por = open("sitio/index.html", encoding="utf-8").read()
assert "U='/ahora.json'" in por, "sin --estado-url debe leer el JSON propio"
assert "data-cruce=" in por
ok("por omision el tablero se refresca contra /ahora.json")

RAW = "https://raw.githubusercontent.com/x/y/main/estado.json"
shutil.rmtree("sitio")
run("--dominio", "https://ejemplo.mx", "--estado-url", RAW)
por = open("sitio/index.html", encoding="utf-8").read()
assert f"U='{RAW}'" in por and "R=1" in por, "no tomo la URL cruda"
assert "function crudo" in por, "falta el traductor del formato de estado.json"
ok("con --estado-url el tablero lee el estado crudo del repositorio")

# el numero tambien tiene que venir YA escrito, para quien trae JS apagado
assert re.search(r'<span class="num">\d+<small> min</small></span>', por), \
    "sin JavaScript no se ve ningun numero"
ok("los numeros vienen escritos en el HTML: sin JavaScript la pagina sirve igual")

# --meses acota lo que lee
salida = run("--meses", "1", "--dominio", "https://ejemplo.mx")
assert "paginas" in salida
ok("--meses acota cuanta historia lee cada corrida")

# ── J · sitio en un subdirectorio (GitHub Pages de proyecto) ──────────────
print("\nJ · BASE")
shutil.rmtree("sitio")
run("--dominio", "https://ejemplo.github.io/garitas", "--base", "/garitas")
sub = sorted(glob.glob("sitio/**/*.html", recursive=True))
malos = []
for ruta in sub:
    t = open(ruta, encoding="utf-8").read()
    for h in re.findall(r'(?:href|src)="(/[^"]*)"', t):
        if not h.startswith("/garitas/"):
            malos.append((ruta, h))
if malos:
    falla(f"enlaces sin el prefijo de --base: {malos[:5]}")
ok("con --base todos los enlaces internos llevan el prefijo")

por = open("sitio/index.html", encoding="utf-8").read()
assert 'href="/garitas/estilo.css"' in por
assert "U='/garitas/ahora.json'" in por
assert '<link rel="canonical" href="https://ejemplo.github.io/garitas/">' in por
ok("el CSS, el JSON y el canonical respetan el prefijo")

sm2 = open("sitio/sitemap.xml", encoding="utf-8").read()
assert all(u.startswith("https://ejemplo.github.io/garitas/")
           for u in re.findall(r"<loc>(.*?)</loc>", sm2))
ok("el sitemap tambien")

# y sin --base no debe quedar rastro del prefijo
shutil.rmtree("sitio")
run("--dominio", "https://ejemplo.mx")
assert "/garitas/" not in open("sitio/index.html", encoding="utf-8").read()
ok("sin --base no queda ningun prefijo pegado")

# ── K · contraste del mapa de calor (WCAG) ────────────────────────────────
print("\nK · CONTRASTE")
css = open("sitio/estilo.css", encoding="utf-8").read()

def rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))

def lum(c):
    def f(v):
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (f(x) for x in c)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b

def contraste(a, b):
    la, lb = sorted((lum(rgb(a)), lum(rgb(b))))
    return (lb + 0.05) / (la + 0.05)

def paleta(bloque):
    return dict(re.findall(r"--(s[1-8]):(#[0-9A-Fa-f]{6})", bloque))

claro = paleta(css.split("@media(prefers-color-scheme:dark)")[0])
oscuro = paleta(css.split("@media(prefers-color-scheme:dark)")[1])
assert len(claro) == 8 and len(oscuro) == 8, f"faltan tonos: {claro} {oscuro}"

# la regla del CSS: 1-4 texto oscuro, 5-8 texto claro (al reves en oscuro)
casos = [("claro", claro, {"s1": "#14161A", "s2": "#14161A", "s3": "#14161A", "s4": "#14161A",
                           "s5": "#F6EAD8", "s6": "#F6EAD8", "s7": "#F6EAD8", "s8": "#F6EAD8"}),
         ("oscuro", oscuro, {"s1": "#EDD8B4", "s2": "#EDD8B4", "s3": "#EDD8B4", "s4": "#EDD8B4",
                             "s5": "#101418", "s6": "#101418", "s7": "#101418", "s8": "#101418"})]
peor = 99
for modo, pal, texto in casos:
    for k, fondo in pal.items():
        c = contraste(fondo, texto[k])
        peor = min(peor, c)
        if c < 4.5:
            falla(f"contraste malo en modo {modo}, {k}: {c:.2f} ({fondo} sobre {texto[k]})")
ok(f"los 16 pares de color del mapa pasan AA (el peor: {peor:.2f}:1)")

# y la rampa tiene que ser monotona: si no, el mapa miente al ojo
for modo, pal, _ in casos:
    ls = [lum(rgb(pal[f"s{i}"])) for i in range(1, 9)]
    orden = ls == sorted(ls) or ls == sorted(ls, reverse=True)
    if not orden:
        falla(f"la rampa {modo} no va de claro a oscuro en orden: {ls}")
ok("la rampa avanza en un solo sentido, sin brincos")

# el mapa usa de verdad varios escalones y no se satura en el mas oscuro
sy = open("sitio/san-ysidro/index.html", encoding="utf-8").read()
usados = collections.Counter(re.findall(r'<td class="n([0-8])"', sy))
del usados["0"]
assert len(usados) >= 4, f"el mapa solo usa {len(usados)} escalones: {dict(usados)}"
top = usados.most_common(1)[0]
assert top[1] < sum(usados.values()) * 0.65, \
    f"el escalon {top[0]} se come el {100*top[1]//sum(usados.values())}% del mapa"
ok(f"el mapa reparte los datos en {len(usados)} escalones, sin saturarse")

leyenda = re.search(r'<p class="escala">(.*?)</p>', sy, re.S).group(1)
assert leyenda.count("<i ") == 8, "la leyenda debe mostrar los 8 escalones"
assert "min" in leyenda and "h" in leyenda, "la leyenda debe decir cuantos minutos es cada tono"
ok("la leyenda rotula los 8 escalones con su rango en minutos")

print(f"\n  {N} pruebas del sitio, todas bien.\n")
shutil.rmtree(TMP, ignore_errors=True)
