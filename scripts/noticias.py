import re
import time
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

# Nombres conocidos: son un punto de partida, no una lista cerrada.
CREADORES = [
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

# Búsquedas para descubrir creadores que todavía no conocemos.
BUSQUEDAS = [
    ("Streamers colombianos", '"streamer colombiano"'),
    ("Streamers emergentes", '"nuevo streamer colombiano"'),
    ("Streamers virales", '"streamer colombiano viral"'),
    ("Streamers de Kick", 'streamer colombiano Kick'),
    ("Streamers de Twitch", 'streamer colombiano Twitch'),
    ("Streamers de YouTube", 'streamer colombiano YouTube'),
    ("Directos y polémicas", 'streamer colombiano polémica'),
    ("Nuevos creadores", '"creador de contenido colombiano"'),
    ("Influencers colombianos", '"influencer colombiano"'),
    ("Influencers virales", 'influencer colombiano viral'),
    ("TikTok colombiano", 'tiktoker colombiano viral'),
    ("YouTubers colombianos", 'youtuber colombiano viral'),
    ("Creadores de Medellín", 'streamer creador Medellín Colombia'),
    ("Creadores de Bogotá", 'streamer creador Bogotá Colombia'),
    ("Creadores de Cali", 'streamer creador Cali Colombia'),
    ("Creadores de Barranquilla", 'streamer creador Barranquilla Colombia'),
    ("Colaboraciones", 'streamer influencer colombiano colaboración'),
    ("Noticias de Westcol", '"Westcol"'),
    ("Noticias de La Liendra", '"La Liendra"'),
    ("Noticias de Yeferson Cossio", '"Yeferson Cossio"'),
    ("Noticias de Aida Victoria", '"Aida Victoria"'),
    ("Noticias de Epa Colombia", '"Epa Colombia"'),
    ("Noticias de Luisa Fernanda W", '"Luisa Fernanda W"'),
    ("Noticias de Dani Duke", '"Dani Duke"'),
    ("Noticias de Andrea Valdiri", '"Andrea Valdiri"'),
    ("Noticias de Mr Stiven", '"Mr Stiven"'),
    ("Noticias de Pelicanger", '"Pelicanger"'),
    ("Noticias de Juan Guarnizo", '"Juan Guarnizo"'),
]

PALABRAS_CREADORES = [
    "streamer", "streamers", "influencer", "influencers",
    "creador de contenido", "creadora de contenido",
    "creadores de contenido", "creadoras de contenido",
    "tiktoker", "youtuber", "youtubers",
    "twitch", "kick", "youtube", "tiktok",
    "transmision en vivo", "directo", "directos",
    "redes sociales", "creador digital",
]

INDICIOS_COLOMBIA = [
    "colombia", "colombiano", "colombiana",
    "colombianos", "colombianas",
    "bogota", "medellin", "cali", "barranquilla",
    "bucaramanga", "cartagena", "pereira",
    "manizales", "cucuta", "villavicencio",
    "santa marta", "ibague", "pasto", "monteria",
    "neiva", "armenia", "valledupar", "sincelejo",
]


def normalizar(texto):
    texto = (texto or "").casefold()
    texto = unicodedata.normalize("NFD", texto)
    return "".join(
        letra for letra in texto
        if unicodedata.category(letra) != "Mn"
    )


def limpiar(texto):
    return re.sub(r"\s+", " ", texto or "").strip()


def es_relevante(titulo, descripcion):
    texto = normalizar(titulo + " " + descripcion)

    # Si menciona a un creador conocido, aceptar el resultado.
    if any(normalizar(nombre) in texto for nombre in CREADORES):
        return True

    # Para descubrir nombres nuevos, exigir señales de Colombia
    # y términos relacionados con creadores o plataformas.
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


def consultar(tema):
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
            print(f"Error 503. Reintento en {espera} segundos.")
            time.sleep(espera)

        except (urllib.error.URLError, TimeoutError):
            if intento == REINTENTOS - 1:
                raise

            time.sleep(3 * (intento + 1))

    raise RuntimeError("No se pudo consultar Google Noticias")


def obtener_noticias(tema):
    raiz = consultar(tema)
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

        if fecha is None or fecha < limite:
            continue

        if not es_relevante(titulo, descripcion):
            continue

        resultados.append({
            "titulo": titulo,
            "enlace": enlace,
            "fecha": fecha_texto,
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
        f"> Noticias de las últimas {HORAS_MAXIMAS} horas.",
        f"> Hasta {MAX_TITULARES} titulares por búsqueda.",
        "> Se priorizan streamers y se incluyen otros influencers.",
        "> Verifica la información antes de publicar.",
        "",
    ]

    vistos = set()

    for categoria, tema in BUSQUEDAS:
        lineas.extend([f"## {categoria}", ""])

        try:
            noticias = obtener_noticias(tema)
            nuevas = 0

            for noticia in noticias:
                enlace = noticia["enlace"]

                if enlace in vistos:
                    continue

                vistos.add(enlace)
                nuevas += 1

                lineas.extend([
                    "### " + noticia["titulo"],
                    "- Fecha: " + noticia["fecha"],
                    "- Enlace: " + enlace,
                    "- Estado: pendiente de verificación",
                    "",
                ])

            if nuevas == 0:
                lineas.extend([
                    "No se encontraron resultados nuevos.",
                    "",
                ])

            print(f"{categoria}: {nuevas} noticias.")

        except Exception as error:
            mensaje = f"{type(error).__name__}: {error}"
            print(f"Error en {categoria}: {mensaje}")

            lineas.extend([
                f"No se pudo consultar esta búsqueda: {mensaje}",
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