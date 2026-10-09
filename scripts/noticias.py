import re
import time
import urllib.request
import urllib.parse
import urllib.error
import xml.etree.ElementTree as ET
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path

MAX_TITULARES = 25

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


def obtener_noticias(tema):
    url = (
        "https://news.google.com/rss/search?q="
        + urllib.parse.quote(tema)
        + "&hl=es-419&gl=CO&ceid=CO:es-419"
    )

    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0"},
    )

    raiz = None

    for intento in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as respuesta:
                raiz = ET.fromstring(respuesta.read())
            break

        except urllib.error.HTTPError as error:
            if error.code == 503 and intento < 2:
                espera = 3 * (intento + 1)
                print(
                    f"Error 503. Reintentando en {espera} segundos."
                )
                time.sleep(espera)
            else:
                raise

        except (urllib.error.URLError, TimeoutError):
            if intento == 2:
                raise
            time.sleep(3 * (intento + 1))

    if raiz is None:
        raise RuntimeError(
            "No se pudo consultar Google Noticias"
        )

    resultados = []

    for item in raiz.findall("./channel/item")[:MAX_TITULARES]:
        titulo = limpiar(item.findtext("title"))
        enlace = limpiar(item.findtext("link"))
        fecha = limpiar(item.findtext("pubDate"))

        if titulo and enlace:
            resultados.append({
                "titulo": titulo,
                "enlace": enlace,
                "fecha": fecha,
            })

    return resultados


def main():
    fecha = datetime.now(
        ZoneInfo("America/Bogota")
    ).strftime("%Y-%m-%d")

    lineas = [
        f"# Noticias para revisar — {fecha}",
        "",
        "> Borrador automático de noticias sobre streamers.",
        "> Verifica las fuentes antes de publicar.",
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
                    "- Fecha de la fuente: "
                    + (noticia["fecha"] or "No indicada"),
                    "- Enlace: " + enlace,
                    "- Estado: pendiente de verificación",
                    "",
                ])

            if nuevas == 0:
                lineas.extend([
                    "No se encontraron resultados nuevos.",
                    "",
                ])

            print(
                f"Búsqueda completada: {tema}. "
                f"Titulares nuevos: {nuevas}"
            )

        except Exception as error:
            mensaje = f"{type(error).__name__}: {error}"

            print(
                f"Falló la búsqueda {tema}: {mensaje}"
            )

            lineas.extend([
                f"No se pudo consultar esta búsqueda: {mensaje}",
                "",
            ])

    carpeta = Path("borradores")
    carpeta.mkdir(parents=True, exist_ok=True)

    destino = carpeta / f"noticias-{fecha}.md"

    destino.write_text(
        "\n".join(lineas),
        encoding="utf-8",
    )

    print(f"Informe generado: {destino}")


if __name__ == "__main__":
    main()