
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


# ==========================================
# RADAR GRATUITO DE CREADORES COLOMBIANOS
# ==========================================

HORAS_MAXIMAS = 48
MAX_RESULTADOS = 25
MAX_POR_CREADOR = 3
MAX_WESTCOL = 2

CARPETA = Path("borradores")
ZONA_COLOMBIA = ZoneInfo("America/Bogota")

CREADORES = [
    "Westcol",
    "Pelicanger",
    "Mr Stiven",
    "Juan Guarnizo",
    "La Liendra",
    "Yeferson Cossio",
    "Dani Duke",
    "Luisa Fernanda W",
    "Aida Victoria Merlano",
    "Kika Nieto",
    "Pautips",
    "Ami Rodriguez",
    "Calle y Poche",
    "Spreen",
]

# Búsquedas de YouTube mediante feeds RSS públicos.
BUSQUEDAS_YOUTUBE = [
    "streamers colombianos",
    "clips streamer colombiano",
    "creadores colombianos viral",
    "tiktokers colombianos",
    "influencers colombianos",
]

# Google News RSS busca páginas indexadas relacionadas
# con las plataformas. No garantiza devolver el clip original.
BUSQUEDAS_NOTICIAS = [
    ("Actualidad", '"streamer colombiano"'),
    ("Actualidad", '"creador de contenido colombiano"'),
    ("Actualidad", '"influencer colombiano" viral'),
    ("TikTok", 'site:tiktok.com Colombia streamer OR influencer'),
    ("Twitch", 'site:clips.twitch.tv Colombia streamer'),
    ("Twitch", 'site:twitch.tv Colombia streamer clip'),
    ("Kick", 'site:kick.com Colombia streamer'),
    ("Instagram", 'site:instagram.com/reel Colombia influencer'),
    ("YouTube", 'site:youtube.com Colombia streamer clip'),
]


def ahora_utc():
    return datetime.now(timezone.utc)


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


def limpiar(texto):
    texto = html.unescape(str(texto or ""))
    texto = re.sub(r"<[^>]*>", " ", texto)
    return re.sub(r"\s+", " ", texto).strip()


def normalizar(texto):
    texto = limpiar(texto).lower()
    texto = re.sub(r"https?://\S+", " ", texto)
    texto = re.sub(r"[^a-z0-9áéíóúüñ ]", " ", texto)
    return " ".join(texto.split())


def creador_detectado(titulo, canal=""):
    # Solo usamos el título y el canal reales.
    # No usamos la consulta de búsqueda para asignar un nombre.
    texto = f"{titulo} {canal}".lower()

    for nombre in sorted(CREADORES, key=len, reverse=True):
        if nombre.lower() in texto:
            return nombre

    return "Por descubrir"


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


def registro(titulo, url, fecha, fuente, canal=""):
    titulo = limpiar(titulo)
    url = limpiar(url)

    if not titulo or not url or not fecha:
        return None

    limite = ahora_utc() - timedelta(hours=HORAS_MAXIMAS)
    if not (limite <= fecha <= ahora_utc()):
        return None

    return {
        "titulo": titulo,
        "url": url,
        "fecha": fecha,
        "fuente": fuente,
        "canal": limpiar(canal),
        "creador": creador_detectado(titulo, canal),
    }


# ==========================================
# YOUTUBE: FEEDS RSS DE BÚSQUEDA
# ==========================================

def buscar_youtube():
    resultados = []

    for consulta in BUSQUEDAS_YOUTUBE:
        parametros = urllib.parse.urlencode({
            "search_query": consulta,
        })

        url = (
            "https://www.youtube.com/feeds/videos.xml?"
            + parametros
        )

        try:
            raiz = ET.fromstring(descargar(url))

            ns = {
                "atom": "http://www.w3.org/2005/Atom",
                "yt": "http://www.youtube.com/xml/schemas/2015",
            }

            for item in raiz.findall("atom:entry", ns):
                titulo = item.findtext("atom:title", "", ns)
                canal = item.findtext("atom:author/atom:name", "", ns)
                enlace = item.find("atom:link", ns)
                fecha_texto = item.findtext("atom:published", "", ns)

                if enlace is None:
                    continue

                elemento = registro(
                    titulo,
                    enlace.get("href", ""),
                    parsear_fecha(fecha_texto),
                    "YouTube RSS",
                    canal,
                )

                if elemento:
                    resultados.append(elemento)

            print(f"YouTube RSS consultado: {consulta}")
            time.sleep(1)

        except Exception as error:
            print(f"YouTube RSS no disponible ({consulta}): {error}")

    return resultados


# ==========================================
# GOOGLE NEWS RSS: NOTICIAS Y PÁGINAS INDEXADAS
# ==========================================

def buscar_noticias():
    resultados = []

    for categoria, consulta in BUSQUEDAS_NOTICIAS:
        parametros = urllib.parse.urlencode({
            "q": consulta,
            "hl": "es-419",
            "gl": "CO",
            "ceid": "CO:es-419",
        })

        url = (
            "https://news.google.com/rss/search?"
            + parametros
        )

        try:
            raiz = ET.fromstring(descargar(url))

            for item in raiz.findall(".//item"):
                titulo = item.findtext("title", "")
                enlace = item.findtext("link", "")
                fecha_texto = item.findtext("pubDate", "")
                fuente_xml = item.find("source")

                nombre_fuente = (
                    limpiar(fuente_xml.text)
                    if fuente_xml is not None
                    else "Google News"
                )

                elemento = registro(
                    titulo,
                    enlace,
                    parsear_fecha(fecha_texto),
                    f"Google News — {categoria} — {nombre_fuente}",
                )

                if elemento:
                    resultados.append(elemento)

            print(f"Google News consultado: {categoria}")
            time.sleep(1)

        except Exception as error:
            print(f"Google News no disponible ({categoria}): {error}")

    return resultados


# ==========================================
# DETECCIÓN DE DUPLICADOS
# ==========================================

def clave_url(url):
    partes = urllib.parse.urlsplit(url)
    parametros = urllib.parse.parse_qs(partes.query)

    # Dos enlaces de YouTube al mismo video son un duplicado.
    if "youtube.com" in partes.netloc:
        video_id = parametros.get("v", [""])[0]
        if video_id:
            return "youtube:" + video_id

    if "youtu.be" in partes.netloc:
        return "youtube:" + partes.path.strip("/")

    return (
        partes.netloc.lower()
        + partes.path.rstrip("/").lower()
    )


def duplicados(a, b):
    if clave_url(a["url"]) == clave_url(b["url"]):
        return True

    titulo_a = normalizar(a["titulo"])
    titulo_b = normalizar(b["titulo"])

    if not titulo_a or not titulo_b:
        return False

    similitud = SequenceMatcher(
        None, titulo_a, titulo_b
    ).ratio()

    if similitud >= 0.86:
        return True

    palabras_a = set(titulo_a.split())
    palabras_b = set(titulo_b.split())
    union = palabras_a | palabras_b

    if len(union) >= 5:
        comun = len(palabras_a & palabras_b)
        if comun / len(union) >= 0.80:
            return True

    return False


def quitar_duplicados(resultados):
    resultados = sorted(
        resultados,
        key=lambda x: x["fecha"],
        reverse=True,
    )

    unicos = []

    for item in resultados:
        if any(duplicados(item, existente) for existente in unicos):
            continue
        unicos.append(item)

    return unicos


# ==========================================
# EQUILIBRAR CREADORES
# ==========================================

def equilibrar(resultados):
    seleccionados = []
    conteo = {}

    # Primero damos prioridad a los creadores identificados,
    # evitando que una sola persona ocupe todo el informe.
    identificados = [
        x for x in resultados
        if x["creador"] != "Por descubrir"
    ]

    descubrimientos = [
        x for x in resultados
        if x["creador"] == "Por descubrir"
    ]

    for item in identificados + descubrimientos:
        nombre = item["creador"].lower()

        maximo = (
            MAX_WESTCOL
            if nombre == "westcol"
            else MAX_POR_CREADOR
        )

        if conteo.get(nombre, 0) >= maximo:
            continue

        seleccionados.append(item)
        conteo[nombre] = conteo.get(nombre, 0) + 1

        if len(seleccionados) >= MAX_RESULTADOS:
            break

    return seleccionados


# ==========================================
# GENERAR INFORME
# ==========================================

def generar_informe(resultados):
    CARPETA.mkdir(exist_ok=True)

    ahora_local = datetime.now(ZONA_COLOMBIA)
    archivo = CARPETA / (
        "radar-" + ahora_local.strftime("%Y-%m-%d") + ".md"
    )

    lineas = [
        "# Radar de creadores colombianos",
        "",
        f"Generado: {ahora_local:%d/%m/%Y %H:%M} (hora Colombia)",
        "",
        f"- Ventana: últimas {HORAS_MAXIMAS} horas.",
        f"- Resultados: {len(resultados)}.",
        f"- Máximo por creador: {MAX_POR_CREADOR}.",
        f"- Máximo para Westcol: {MAX_WESTCOL}.",
        "",
        "> Los feeds y las noticias no garantizan que todos los resultados",
        "> sean clips originales ni que todos los creadores sean colombianos.",
        "> Revisa el canal, la fecha y el enlace antes de publicar.",
        "",
    ]

    if not resultados:
        lineas.extend([
            "No se encontraron resultados recientes con las fuentes consultadas.",
            "",
        ])

    for numero, item in enumerate(resultados, 1):
        fecha = item["fecha"].astimezone(
            ZONA_COLOMBIA
        ).strftime("%d/%m/%Y %H:%M")

        lineas.extend([
            f"## {numero}. {item['titulo']}",
            "",
            f"- **Creador detectado:** {item['creador']}",
            f"- **Fuente:** {item['fuente']}",
            f"- **Canal:** {item['canal'] or 'No identificado'}",
            f"- **Fecha:** {fecha} (Colombia)",
            f"- **Enlace:** {item['url']}",
            "",
        ])

    lineas.extend([
        "---",
        "",
        "## Búsquedas manuales complementarias",
        "",
        "- [TikTok: streamers colombianos](https://www.tiktok.com/search?q=streamers%20colombianos)",
        "- [Twitch: clips](https://www.twitch.tv/directory)",
        "- [Kick](https://kick.com/)",
        "- [Instagram Reels](https://www.instagram.com/)",
        "- [YouTube: streamers colombianos](https://www.youtube.com/results?search_query=streamers+colombianos)",
        "",
        "Estos enlaces son búsquedas manuales, no resultados recopilados automáticamente.",
        "",
    ])

    archivo.write_text(
        "\n".join(lineas),
        encoding="utf-8",
    )

    print(f"Informe guardado: {archivo}")


# ==========================================
# EJECUCIÓN
# ==========================================

def main():
    print("=" * 50)
    print("RADAR GRATUITO DE CREADORES")
    print(f"Ventana: {HORAS_MAXIMAS} horas")
    print("=" * 50)

    resultados = []
    resultados.extend(buscar_youtube())
    resultados.extend(buscar_noticias())

    print(f"Resultados recopilados: {len(resultados)}")

    resultados = quitar_duplicados(resultados)
    print(f"Tras quitar duplicados: {len(resultados)}")

    resultados = equilibrar(resultados)
    print(f"Tras equilibrar creadores: {len(resultados)}")

    generar_informe(resultados)


if __name__ == "__main__":
    main()
