import re
import time
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

TEMAS = [
    "Westcol streamer Colombia",
    "streamers colombianos noticias",
    "streamers Colombia polémica",
    "La Liendra redes sociales Colombia",
    "Juan Guarnizo streamer",
    "Spreen streamer Colombia",
    "streamers colombianos Kick Twitch YouTube",
    "creadores de contenido Colombia viral",
]


def limpiar(texto):
    return re.sub(r"\s+", " ", texto or "").strip()


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


def obtener_noticias(tema):
    busqueda = tema + " when:2d"

    url = (
        "https://news.google.com/rss/search?q="
        + urllib.parse.quote(busqueda)
        + "&hl=es-419&gl=CO&ceid=CO:es-419"
    )

    solicitud = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0"},
    )

    raiz = None

    for intento in range(REINTENTOS):
        try:
            with urllib.request.urlopen(
                solicitud, timeout=30
            ) as respuesta:
                raiz = ET.fromstring(respuesta.read())
            break

        except urllib.error.HTTPError as error:
            if error.code == 503 and intento < REINTENTOS - 1:
                espera = 3 * (intento + 1)
                print(
                    f"Error 503. Reintentando en {espera} segundos."
                )
                time.sleep(espera)
            else:
                raise

        except (urllib.error.URLError, TimeoutError):
            if intento == REINTENTOS - 1:
                raise

            time.sleep(3 * (intento + 1))

    if raiz is None:
        raise RuntimeError("No se obtuvo respuesta de Google Noticias")

    limite = datetime.now(timezone.utc) - timedelta(
        hours=HORAS_MAXIMAS
    )

    resultados = []

    for item in raiz.findall("./channel/item"):
        titulo = limpiar(item.findtext("title"))
        enlace = limpiar(item.findtext("link"))
        fecha_texto = limpiar(item.findtext("pubDate"))
        fecha = obtener_fecha(fecha_texto)

        # Excluir noticias antiguas o sin fecha verificable.
        if fecha is None or fecha < limite:
            continue

        if not titulo or not enlace:
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
    fecha_hoy = datetime.now(
        ZoneInfo("America/Bogota")
    ).strftime("%Y-%m-%d")

    lineas = [
        f"# Noticias de streamers colombianos — {fecha_hoy}",
        "",
        f"> Filtro: últimas {HORAS_MAXIMAS} horas.",
        f"> Máximo: {MAX_TITULARES} titulares por búsqueda.",
        "> Revisa las fuentes antes de publicar.",
        "",
    ]

    vistos = set()

    for tema in TEMAS:
        lineas.extend([
            f"## Búsqueda: {tema}",
            "",
        ])

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
                    "No se encontraron noticias recientes nuevas.",
                    "",
                ])

            print(f"{tema}: {nuevas} noticias nuevas.")

        except Exception as error:
            mensaje = f"{type(error).__name__}: {error}"
            print(f"Error en {tema}: {mensaje}")

            lineas.extend([
                f"No se pudo consultar esta búsqueda: {mensaje}",
                "",
            ])

    carpeta = Path("borradores")
    carpeta.mkdir(parents=True, exist_ok=True)

    destino = carpeta / f"noticias-{fecha_hoy}.md"

    destino.write_text(
        "\n".join(lineas) + "\n",
        encoding="utf-8",
    )

    print(f"Informe generado: {destino}")


if __name__ == "__main__":
    main()