
import html
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from difflib import SequenceMatcher
from pathlib import Path
from zoneinfo import ZoneInfo

# =====================================================
# CONFIGURACIÓN
# =====================================================

HORAS_MAXIMAS = 48
MAX_RESULTADOS = 25
MAX_WESTCOL = 2
MAX_POR_CREADOR = 3

CARPETA = Path("borradores")
ZONA = ZoneInfo("America/Bogota")

CATEGORIAS = [
    "1. Grandes de Kick",
    "2. Amigos y círculo de Westcol",
    "3. Emergentes y pequeños de Kick",
    "4. Otros streamers",
    "5. Influencers y creadores",
    "6. Clips virales, humor y polémicas",
]

CANALES_KICK = {
    "Westcol": "https://kick.com/westcol",
    "La Sapaaaaa": "https://kick.com/lasapaaaaa",
    "Chanty": "https://kick.com/chanty",
    "Samulx": "https://kick.com/samulx",
    "Lonche": "https://kick.com/lonche",
}

CREADORES_CONOCIDOS = [
    "Westcol", "La Sapaaaaa", "Chanty", "Samulx", "Lonche",
    "Pelicanger", "Mr Stiven", "Juan Guarnizo", "Spreen",
    "La Liendra", "Yeferson Cossio", "Dani Duke",
    "Luisa Fernanda W", "Aida Victoria Merlano",
    "Kika Nieto", "Pautips", "Ami Rodriguez",
    "Calle y Poche", "TheDonato", "Cristorata",
]

# Las búsquedas se separan por tema para que el informe
# no quede dominado por un solo streamer.

BUSQUEDAS_YOUTUBE = [
    ("1. Grandes de Kick", "Westcol Kick"),
    ("1. Grandes de Kick", "LaSapaaaaa Kick"),
    ("1. Grandes de Kick", "Chanty Kick"),
    ("1. Grandes de Kick", "Samulx Kick"),
    ("1. Grandes de Kick", "Lonche Kick"),
    ("1. Grandes de Kick", "streamers grandes colombianos Kick"),

    ("2. Amigos y círculo de Westcol", "Westcol amigos streamers"),
    ("2. Amigos y círculo de Westcol", "Westcol con otros streamers"),
    ("2. Amigos y círculo de Westcol", "parceros de Westcol directo"),
    ("2. Amigos y círculo de Westcol", "colaboraciones Westcol streamers"),
    ("2. Amigos y círculo de Westcol", "Westcol invitados Kick"),

    ("3. Emergentes y pequeños de Kick", "streamer colombiano emergente Kick"),
    ("3. Emergentes y pequeños de Kick", "streamer pequeño Kick Colombia"),
    ("3. Emergentes y pequeños de Kick", "nuevo streamer colombiano Kick"),
    ("3. Emergentes y pequeños de Kick", "clips streamer Kick colombiano"),
    ("3. Emergentes y pequeños de Kick", "streamer colombiano creciendo Kick"),
    ("3. Emergentes y pequeños de Kick", "directo Kick colombiano"),

    ("4. Otros streamers", "streamers colombianos Twitch"),
    ("4. Otros streamers", "streamers colombianos YouTube Gaming"),
    ("4. Otros streamers", "clips streamers colombianos"),
    ("4. Otros streamers", "streamer colombiano en directo"),

    ("5. Influencers y creadores", "influencers colombianos"),
    ("5. Influencers y creadores", "tiktokers colombianos virales"),
    ("5. Influencers y creadores", "creadores de contenido Colombia"),
    ("5. Influencers y creadores", "influencers colombianos Instagram"),
    ("5. Influencers y creadores", "youtubers colombianos tendencias"),

    ("6. Clips virales, humor y polémicas", "momentos graciosos streamers colombianos"),
    ("6. Clips virales, humor y polémicas", "peleas discusiones streamers colombianos"),
    ("6. Clips virales, humor y polémicas", "reacciones polémicas creadores colombianos"),
    ("6. Clips virales, humor y polémicas", "clips virales Colombia streamer"),
    ("6. Clips virales, humor y polémicas", "momentos inesperados Kick Colombia"),
    ("6. Clips virales, humor y polémicas", "memes influencers colombianos"),
]

BUSQUEDAS_NOTICIAS = [
    ("1. Grandes de Kick", '"Westcol"'),
    ("1. Grandes de Kick", '"La Sapaaaaa" streamer'),
    ("1. Grandes de Kick", '"Chanty" streamer Colombia'),
    ("1. Grandes de Kick", '"Samulx" streamer'),
    ("1. Grandes de Kick", '"Lonche" streamer Colombia'),
    ("1. Grandes de Kick", '"streamer colombiano" Kick'),

    ("2. Amigos y círculo de Westcol", '"Westcol" amigos streamers'),
    ("2. Amigos y círculo de Westcol", '"Westcol" colaboración streamer'),
    ("2. Amigos y círculo de Westcol", '"Westcol" invitado directo'),
    ("2. Amigos y círculo de Westcol", '"Westcol" creadores de contenido'),

    ("3. Emergentes y pequeños de Kick", '"nuevo streamer" Colombia Kick'),
    ("3. Emergentes y pequeños de Kick", '"streamer colombiano" emergente'),
    ("3. Emergentes y pequeños de Kick", 'streamer pequeño colombiano viral'),

    ("4. Otros streamers", '"streamer colombiano" Twitch'),
    ("4. Otros streamers", '"streamer colombiano" YouTube'),
    ("4. Otros streamers", 'directos streamers Colombia'),

    ("5. Influencers y creadores", '"influencer colombiano"'),
    ("5. Influencers y creadores", '"tiktoker colombiano" viral'),
    ("5. Influencers y creadores", '"creador de contenido colombiano"'),
    ("5. Influencers y creadores", 'influencer colombiano Instagram TikTok'),

    ("6. Clips virales, humor y polémicas", 'streamer colombiano pelea polémica'),
    ("6. Clips virales, humor y polémicas", 'streamer colombiano discusión viral'),
    ("6. Clips virales, humor y polémicas", 'momentos graciosos streamer colombiano'),
    ("6. Clips virales, humor y polémicas", 'video viral influencer colombiano'),
    ("6. Clips virales, humor y polémicas", 'reacción polémica streamer Colombia'),
]


# =====================================================
# UTILIDADES
# =====================================================

def limpiar(texto):
    texto = html.unescape(str(texto or ""))
    texto = re.sub(r"<[^>]*>", " ", texto)
    return re.sub(r"\s+", " ", texto).strip()


def normalizar(texto):
    texto = limpiar(texto).lower()
    texto = re.sub(r"https?://\S+", " ", texto)
    texto = re.sub(r"[^a-z0-9áéíóúüñ ]", " ", texto)
    return " ".join(texto.split())


def parsear_fecha(valor):
    if not valor:
        return None

    try:
        fecha = datetime.fromisoformat(
            valor.strip().replace("Z", "+00:00")
        )
        if fecha.tzinfo is None:
            fecha = fecha.replace(tzinfo=timezone.utc)
        return fecha.astimezone(timezone.utc)
    except (ValueError, TypeError):
        pass

    try:
        fecha = parsedate_to_datetime(valor)
        if fecha.tzinfo is None:
            fecha = fecha.replace(tzinfo=timezone.utc)
        return fecha.astimezone(timezone.utc)
    except (ValueError, TypeError, OverflowError):
        return None


def descargar(url):
    solicitud = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; RadarCreadores/1.0)",
            "Accept": "application/rss+xml, application/xml, text/xml",
        },
    )

    with urllib.request.urlopen(solicitud, timeout=20) as respuesta:
        return respuesta.read()


def detectar_creador(titulo, canal=""):
    texto = normalizar(f"{titulo} {canal}")

    for nombre in sorted(CREADORES_CONOCIDOS, key=len, reverse=True):
        if normalizar(nombre) in texto:
            return nombre

    return "Por descubrir"


def detectar_categoria(titulo, categoria_original):
    texto = normalizar(titulo)

    # No asignamos amistades como hechos confirmados:
    # solo clasificamos contenido relacionado con Westcol.
    if categoria_original == "2. Amigos y círculo de Westcol":
        return categoria_original

    if categoria_original == "1. Grandes de Kick":
        return categoria_original

    return categoria_original


def crear_registro(
    titulo, url, fecha, fuente, categoria, canal=""
):
    titulo = limpiar(titulo)
    url = limpiar(url)

    if not titulo or not url or not fecha:
        return None

    ahora = datetime.now(timezone.utc)
    limite = ahora - timedelta(hours=HORAS_MAXIMAS)

    if not limite <= fecha <= ahora:
        return None

    return {
        "titulo": titulo,
        "url": url,
        "fecha": fecha,
        "fuente": fuente,
        "categoria": detectar_categoria(titulo, categoria),
        "canal": limpiar(canal),
        "creador": detectar_creador(titulo, canal),
    }


# =====================================================
# YOUTUBE RSS
# =====================================================

def buscar_youtube():
    resultados = []

    for categoria, consulta in BUSQUEDAS_YOUTUBE:
        url = (
            "https://www.youtube.com/feeds/videos.xml?"
            + urllib.parse.urlencode({"search_query": consulta})
        )

        try:
            raiz = ET.fromstring(descargar(url))
            ns = {"atom": "http://www.w3.org/2005/Atom"}

            for item in raiz.findall("atom:entry", ns):
                titulo = item.findtext("atom:title", "", ns)
                canal = item.findtext(
                    "atom:author/atom:name", "", ns
                )
                fecha = parsear_fecha(
                    item.findtext("atom:published", "", ns)
                )
                enlace = item.find("atom:link", ns)

                if enlace is None:
                    continue

                registro = crear_registro(
                    titulo=titulo,
                    url=enlace.get("href", ""),
                    fecha=fecha,
                    fuente="YouTube RSS",
                    categoria=categoria,
                    canal=canal,
                )

                if registro:
                    resultados.append(registro)

            print(f"YouTube consultado: {consulta}")
            time.sleep(1)

        except Exception as error:
            print(f"YouTube RSS falló ({consulta}): {error}")

    return resultados


# =====================================================
# GOOGLE NEWS RSS
# =====================================================

def buscar_noticias():
    resultados = []

    for categoria, consulta in BUSQUEDAS_NOTICIAS:
        parametros = urllib.parse.urlencode({
            "q": consulta,
            "hl": "es-419",
            "gl": "CO",
            "ceid": "CO:es-419",
        })

        url = "https://news.google.com/rss/search?" + parametros

        try:
            raiz = ET.fromstring(descargar(url))

            for item in raiz.findall(".//item"):
                titulo = item.findtext("title", "")
                enlace = item.findtext("link", "")
                fecha = parsear_fecha(
                    item.findtext("pubDate", "")
                )

                fuente_xml = item.find("source")
                fuente = (
                    limpiar(fuente_xml.text)
                    if fuente_xml is not None
                    else "Google News"
                )

                registro = crear_registro(
                    titulo=titulo,
                    url=enlace,
                    fecha=fecha,
                    fuente=f"Google News — {fuente}",
                    categoria=categoria,
                )

                if registro:
                    resultados.append(registro)

            print(f"Google News consultado: {consulta}")
            time.sleep(1)

        except Exception as error:
            print(f"Google News falló ({consulta}): {error}")

    return resultados


# =====================================================
# DEDUPLICACIÓN
# =====================================================

def clave_url(url):
    partes = urllib.parse.urlsplit(url)
    host = partes.netloc.lower()

    if "youtube.com" in host:
        video_id = urllib.parse.parse_qs(
            partes.query
        ).get("v", [""])[0]
        if video_id:
            return "youtube:" + video_id

    if "youtu.be" in host:
        return "youtube:" + partes.path.strip("/")

    return host + partes.path.rstrip("/").lower()


def son_duplicados(a, b):
    if clave_url(a["url"]) == clave_url(b["url"]):
        return True

    titulo_a = normalizar(a["titulo"])
    titulo_b = normalizar(b["titulo"])

    if not titulo_a or not titulo_b:
        return False

    return SequenceMatcher(
        None, titulo_a, titulo_b
    ).ratio() >= 0.88


def quitar_duplicados(resultados):
    resultados = sorted(
        resultados,
        key=lambda x: x["fecha"],
        reverse=True,
    )

    unicos = []

    for item in resultados:
        if any(son_duplicados(item, otro) for otro in unicos):
            continue
        unicos.append(item)

    return unicos


# =====================================================
# SELECCIÓN EQUILIBRADA POR CATEGORÍA
# =====================================================

def seleccionar_resultados(resultados):
    grupos = {categoria: [] for categoria in CATEGORIAS}

    for item in sorted(
        resultados,
        key=lambda x: x["fecha"],
        reverse=True,
    ):
        grupos.setdefault(item["categoria"], []).append(item)

    seleccionados = []
    conteo = {}

    # Una ronda por categoría para repartir los resultados.
    while len(seleccionados) < MAX_RESULTADOS:
        hubo_cambio = False

        for categoria in CATEGORIAS:
            if len(seleccionados) >= MAX_RESULTADOS:
                break

            grupo = grupos.get(categoria, [])

            while grupo:
                item = grupo.pop(0)
                creador = item["creador"].lower()

                maximo = (
                    MAX_WESTCOL
                    if creador == "westcol"
                    else MAX_POR_CREADOR
                )

                if conteo.get(creador, 0) >= maximo:
                    continue

                seleccionados.append(item)
                conteo[creador] = conteo.get(creador, 0) + 1
                hubo_cambio = True
                break

        if not hubo_cambio:
            break

    return sorted(
        seleccionados,
        key=lambda x: (
            CATEGORIAS.index(x["categoria"])
            if x["categoria"] in CATEGORIAS else 99,
            -x["fecha"].timestamp(),
        ),
    )


# =====================================================
# GENERAR INFORME
# =====================================================

def generar_informe(resultados):
    CARPETA.mkdir(exist_ok=True)

    ahora = datetime.now(ZONA)
    archivo = CARPETA / (
        "radar-" + ahora.strftime("%Y-%m-%d") + ".md"
    )

    lineas = [
        "# Radar colombiano de streamers e influencers",
        "",
        f"Generado: {ahora:%d/%m/%Y %H:%M} (hora Colombia)",
        "",
        f"- Ventana: últimas {HORAS_MAXIMAS} horas.",
        f"- Resultados: {len(resultados)} de máximo {MAX_RESULTADOS}.",
        f"- Máximo por creador: {MAX_POR_CREADOR}.",
        f"- Máximo de Westcol: {MAX_WESTCOL}.",
        "",
        "## Canales principales de Kick",
        "",
    ]

    for nombre, url in CANALES_KICK.items():
        lineas.append(f"- [{nombre}]({url})")

    lineas.extend([
        "",
        "> Las fuentes gratuitas no garantizan acceso directo a todos",
        "> los clips o transmisiones de cada plataforma.",
        "> Las búsquedas de amistades y colaboraciones no confirman",
        "> por sí solas relaciones personales.",
        "",
    ])

    for categoria in CATEGORIAS:
        lineas.extend([f"# {categoria}", ""])

        elementos = [
            item for item in resultados
            if item["categoria"] == categoria
        ]

        if not elementos:
            lineas.extend([
                "No se encontraron resultados recientes en esta sección.",
                "",
            ])
            continue

        for item in elementos:
            fecha = item["fecha"].astimezone(ZONA).strftime(
                "%d/%m/%Y %H:%M"
            )

            lineas.extend([
                f"## {item['titulo']}",
                "",
                f"- **Creador:** {item['creador']}",
                f"- **Canal:** {item['canal'] or 'No identificado'}",
                f"- **Fuente:** {item['fuente']}",
                f"- **Fecha:** {fecha} (Colombia)",
                f"- **Enlace:** {item['url']}",
                "",
            ])

    lineas.extend([
        "---",
        "",
        "# Búsquedas manuales",
        "",
        "- [Kick](https://kick.com/)",
        "- [Buscar streamers colombianos en Kick](https://www.google.com/search?q=site%3Akick.com+streamer+colombiano)",
        "- [Twitch](https://www.twitch.tv/directory)",
        "- [TikTok: creadores colombianos](https://www.tiktok.com/search?q=creadores%20colombianos)",
        "- [Instagram](https://www.instagram.com/)",
        "- [YouTube: clips de streamers colombianos](https://www.youtube.com/results?search_query=clips+streamers+colombianos)",
        "",
        "Los enlaces manuales no son resultados recopilados automáticamente.",
        "",
    ])

    archivo.write_text("\n".join(lineas), encoding="utf-8")
    print(f"Informe guardado: {archivo}")


# =====================================================
# EJECUCIÓN
# =====================================================

def main():
    print("=" * 55)
    print("RADAR COLOMBIANO DE CREADORES")
    print(f"Periodo: últimas {HORAS_MAXIMAS} horas")
    print("=" * 55)

    resultados = []
    resultados.extend(buscar_youtube())
    resultados.extend(buscar_noticias())

    print(f"Resultados recopilados: {len(resultados)}")

    resultados = quitar_duplicados(resultados)
    print(f"Tras quitar duplicados: {len(resultados)}")

    resultados = seleccionar_resultados(resultados)
    print(f"Resultados seleccionados: {len(resultados)}")

    generar_informe(resultados)


if __name__ == "__main__":
    main()
