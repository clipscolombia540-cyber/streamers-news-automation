import re
import time
import html
import unicodedata
import urllib.request
import urllib.parse
import urllib.error
import xml.etree.ElementTree as ET

from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from zoneinfo import ZoneInfo

MAX_TITULARES = 25
HORAS_MAXIMAS = 48
REINTENTOS = 3

# Nombres conocidos: se pueden ampliar cuando descubramos creadores.
CREADORES_CONOCIDOS = [
    "Westcol",
    "La Liendra",
    "Yeferson Cossio",
    "Aida Victoria",
    "Epa Colombia",
    "Luisa Fernanda W",
    "Dani Duke",
    "Andrea Valdiri",
    "Mr Stiven",
    "Pelicanger",
    "Juan Guarnizo",
]

# Categoría, búsqueda.
# No se clasifican creadores por ciudad sin verificar su origen.
BUSQUEDAS = [
    (
        "Streamers conocidos",
        '"Westcol" OR "streamer colombiano"',
    ),
    (
        "Streamers de Kick",
        'streamer colombiano Kick',
    ),
    (
        "Streamers de Twitch",
        'streamer colombiano Twitch',
    ),
    (
        "Streamers de YouTube",
        'streamer colombiano YouTube directo',
    ),
    (
        "Directos y momentos virales",
        'streamer colombiano directo viral',
    ),
    (
        "Polémicas y declaraciones de streamers",
        'streamer colombiano polémica declaraciones',
    ),
    (
        "Colaboraciones entre streamers",
        'streamers colombianos colaboración',
    ),
    (
        "Descubrir streamers nuevos",
        '"nuevo streamer" Colombia',
    ),
    (
        "Descubrir streamers emergentes",
        'streamer colombiano canal pequeño comunidad',
    ),
    (
        "Descubrir creadores de gaming",
        'creador colombiano gaming transmisiones en vivo',
    ),
    (
        "Streamers colombianos en tendencia",
        'streamer Colombia tendencia redes sociales',
    ),
    (
        "Influencers de TikTok",
        'influencer colombiano TikTok viral',
    ),
    (
        "Influencers de Instagram",
        'influencer colombiano Instagram viral',
    ),
    (
        "YouTubers colombianos",
        'youtuber colombiano nuevo video viral',
    ),
    (
        "Creadores de contenido emergentes",
        '"creador de contenido colombiano" viral',
    ),
    (
        "Noticias de Westcol",
        '"Westcol"',
    ),
    (
        "Noticias de La Liendra",
        '"La Liendra"',
    ),
    (
        "Noticias de Yeferson Cossio",
        '"Yeferson Cossio"',
    ),
    (
        "Noticias de Aida Victoria",
        '"Aida Victoria"',
    ),
    (
        "Noticias de Epa Colombia",
        '"Epa Colombia"',
    ),
    (
        "Noticias de Luisa Fernanda W",
        '"Luisa Fernanda W"',
    ),
    (
        "Noticias de Dani Duke",
        '"Dani Duke"',
    ),
    (
        "Noticias de Andrea Valdiri",
        '"Andrea Valdiri"',
    ),
    (
        "Noticias de Mr Stiven",
        '"Mr Stiven"',
    ),
    (
        "Noticias de Pelicanger",
        '"Pelicanger"',
    ),
    (
        "Noticias de Juan Guarnizo",
        '"Juan Guarnizo"',
    ),
]

PALABRAS_CREADORES = [
    "streamer",
    "streamers",
    "influencer",
    "influencers",
    "creador de contenido",
    "creadora de contenido",
    "creadores de contenido",
    "creadoras de contenido",
    "tiktoker",
    "youtuber",
    "youtubers",
    "twitch",
    "kick",
    "youtube",
    "tiktok",
    "instagram",
    "directo",
    "directos",
    "transmision en vivo",
    "redes sociales",
    "creador digital",
]

INDICIOS_COLOMBIA = [
    "colombia",
    "colombiano",
    "colombiana",
    "colombianos",
    "colombianas",
    "bogota",
    "medellin",
    "cali",
    "barranquilla",
    "bucaramanga",
    "cartagena",
    "pereira",
    "manizales",
    "cucuta",
    "villavicencio",
    "santa marta",
    "ibague",
    "pasto",
    "monteria",
    "neiva",
    "armenia",
    "valledupar",
    "sincelejo",
]


def normalizar(texto):
    texto = html.unescape(texto or "").casefold()
    texto = unicodedata.normalize("NFD", texto)

    return "".join(
        letra
        for letra in texto
        if unicodedata.category(letra) != "Mn"
    )


def limpiar(texto):
    texto = html.unescape(texto or "")
    texto = re.sub(r"<[^>]+>", " ", texto)
    return re.sub(r"\s+", " ", texto).strip()


def es_relevante(titulo, descripcion):
    texto = normalizar(titulo + " " + descripcion)

    # Aceptar noticias que mencionen a un creador conocido.
    if any(
        normalizar(nombre) in texto
        for nombre in CREADORES_CONOCIDOS
    ):
        return True

    # Para descubrir nombres nuevos, exigir señales tanto
    # de Colombia como de actividad de creadores.
    es_colombiano = any(
        normalizar(palabra) in texto
        for palabra in INDICIOS_COLOMBIA
    )

    es_creador = any(
        normalizar(palabra) in texto
        for palabra in PALABRAS_CREADORES
    )

    return es_colombiano and es_creador


def obtener_fecha(texto):
    if not texto:
        return None

    try:
        fecha = parsedate_to_datetime(texto)

        if fecha.tzinfo is None:
            fecha = fecha.replace(tzinfo=timezone.utc)

        return fecha.astimezone(timezone.utc)

    except (ValueError, TypeError, OverflowError):
        return None


def consultar_google(tema):
    consulta = tema + " when:2d"

    url = (
        "https://news.google.com/rss/search?q="
        + urllib.parse.quote(consulta)
        + "&hl=es-419&gl=CO&ceid=CO:es-419"
    )

    solicitud = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0"},
    )

    for intento in range(REINTENTOS):
        try:
            with urllib.request.urlopen(
                solicitud, timeout=30
            ) as respuesta:
                return ET.fromstring(respuesta.read())

        except urllib.error.HTTPError as error:
            if error.code != 503 or intento == REINTENTOS - 1:
                raise

            espera = 3 * (intento + 1)
            print(
                f"Error 503. Reintentando en {espera} segundos."
            )
            time.sleep(espera)

        except (urllib.error.URLError, TimeoutError):
            if intento == REINTENTOS - 1:
                raise

            time.sleep(3 * (intento + 1))

    raise RuntimeError("No se pudo consultar Google Noticias")


def obtener_noticias(tema):
    raiz = consultar_google(tema)

    limite = datetime.now(timezone.utc) - timedelta(
        hours=HORAS_MAXIMAS
    )

    resultados = []

    for item in raiz.findall("./channel/item"):
        titulo = limpiar(item.findtext("title"))
        enlace = limpiar(item.findtext("link"))
        fecha_texto = limpiar(item.findtext("pubDate"))
        descripcion = limpiar(item.findtext("description"))
        fecha = obtener_fecha(fecha_texto)

        if not titulo or not enlace:
            continue

        # Excluir noticias viejas o sin fecha verificable.
        if fecha is None or fecha < limite:
            continue

        if not es_relevante(titulo, descripcion):
            continue

        resultados.append({
            "titulo": titulo,
            "enlace": enlace,
            "fecha": fecha_texto,
            "fecha_utc": fecha,
        })

        if len(resultados) >= MAX_TITULARES:
            break

    return resultados


def main():
    hoy = datetime.now(
        ZoneInfo("America/Bogota")
    ).strftime("%Y-%m-%d")

    lineas = [
        f"# Radar de creadores colombianos — {hoy}",
        "",
        f"> Antigüedad máxima: {HORAS_MAXIMAS} horas.",
        f"> Hasta {MAX_TITULARES} titulares por búsqueda.",
        "> Categorías: streamers conocidos, emergentes e influencers.",
        "> No se asigna ciudad de origen sin verificación.",
        "> Verifica cada fuente antes de publicar.",
        "",
    ]

    vistos = set()
    total = 0

    for categoria, tema in BUSQUEDAS:
        lineas.extend([
            f"## {categoria}",
            "",
        ])

        try:
            noticias = obtener_noticias(tema)
            nuevas = 0

            for noticia in noticias:
                enlace = noticia["enlace"]

                # Evitar repetir la misma noticia en el informe.
                if enlace in vistos:
                    continue

                vistos.add(enlace)
                nuevas += 1
                total += 1

                lineas.extend([
                    "### " + noticia["titulo"],
                    "- Fecha: " + noticia["fecha"],
                    "- Enlace: " + enlace,
                    "- Estado: pendiente de verificación",
                    "",
                ])

            if nuevas == 0:
                lineas.extend([
                    "No hubo resultados nuevos que cumplieran "
                    "los filtros de fecha y relevancia.",
                    "",
                ])

            print(f"{categoria}: {nuevas} noticias nuevas.")

        except Exception as error:
            mensaje = f"{type(error).__name__}: {error}"
            print(f"Error en {categoria}: {mensaje}")

            lineas.extend([
                f"No se pudo consultar esta búsqueda: {mensaje}",
                "",
            ])

    lineas.extend([
        "---",
        "",
        f"Total de noticias únicas: {total}",
        "",
    ])

    carpeta = Path("borradores")
    carpeta.mkdir(parents=True, exist_ok=True)

    destino = carpeta / f"noticias-{hoy}.md"

    destino.write_text(
        "\n".join(lineas) + "\n",
        encoding="utf-8",
    )

    print(f"Informe generado: {destino}")


if __name__ == "__main__":
    main()