import re
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path

TEMAS = [
    "Westcol",
    "streamers Colombia",
    "polémica streamer",
    "Kick streamer Colombia",
    "Twitch streamer Colombia",
]

def limpiar(texto):
    return re.sub(r"\s+", " ", texto or "").strip()

def obtener_noticias(tema):
    url = (
        "https://news.google.com/rss/search?q="
        + urllib.parse.quote(tema)
        + "&hl=es-419&gl=CO&ceid=CO:es-419"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=20) as respuesta:
        raiz = ET.fromstring(respuesta.read())
    resultados = []
    for item in raiz.findall("./channel/item")[:8]:
        resultados.append({
            "titulo": limpiar(item.findtext("title")),
            "enlace": limpiar(item.findtext("link")),
            "fecha": limpiar(item.findtext("pubDate")),
        })
    return resultados

def main():
    fecha = datetime.now(ZoneInfo("America/Bogota")).strftime("%Y-%m-%d")
    lineas = [
        f"# Noticias para revisar — {fecha}",
        "",
        "> Borrador automático: verifica cada noticia antes de publicar.",
        "",
    ]
    vistos = set()
    for tema in TEMAS:
        lineas.extend([f"## Búsqueda: {tema}", ""])
        try:
            noticias = obtener_noticias(tema)
            nuevas = 0
            for noticia in noticias:
                enlace = noticia["enlace"]
                if not enlace or enlace in vistos:
                    continue
                vistos.add(enlace)
                nuevas += 1
                lineas.extend([
                    "### " + noticia["titulo"],
                    "- Fecha de la fuente: " + noticia["fecha"],
                    "- Enlace: " + enlace,
                    "- Estado: pendiente de verificación",
                    "",
                ])
            if nuevas == 0:
                lineas.extend(["No se encontraron resultados nuevos.", ""])
        except Exception as error:
            lineas.extend([
                f"No se pudo consultar esta búsqueda: {error}",
                "",
            ])
    carpeta = Path("borradores")
    carpeta.mkdir(parents=True, exist_ok=True)
    destino = carpeta / f"noticias-{fecha}.md"
    destino.write_text("\n".join(lineas), encoding="utf-8")
    print(f"Informe generado: {destino}")

if __name__ == "__main__":
    main()