
import os
import re
import html
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote_plus

ARCHIVO_SALIDA = "borradores/clips_tiktok.md"
HORAS = 48
MAX_RESULTADOS = 25

CREADORES = [
    "Westcol", "Chanty streamer", "La Sapa streamer",
    "MrStivenTC", "Pelicanger", "Samulx", "Jeanki streamer",
    "Spreen", "Komanche", "JuanSGuarnizo", "Coscu",
    "Rivers streamer", "TheDonato",
    "streamer colombiano viral", "nuevo streamer colombiano"
]

def buscar_google_news(consulta):
    url = (
        "https://news.google.com/rss/search?q="
        + quote_plus(consulta)
        + "+when%3A2d&hl=es-419&gl=CO&ceid=CO%3Aes-419"
    )

    try:
        respuesta = requests.get(
            url,
            timeout=20,
            headers={"User-Agent": "Mozilla/5.0"}
        )
        respuesta.raise_for_status()
        raiz = ET.fromstring(respuesta.content)
        resultados = []

        for item in raiz.findall(".//item"):
            titulo = item.findtext("title", "").strip()
            enlace = item.findtext("link", "").strip()
            fecha_texto = item.findtext("pubDate", "").strip()
            fuente = item.findtext("source", "").strip()

            if not titulo or not enlace:
                continue

            try:
                fecha = parsedate_to_datetime(fecha_texto)
                if fecha.tzinfo is None:
                    fecha = fecha.replace(tzinfo=timezone.utc)
                fecha = fecha.astimezone(timezone.utc)
            except (TypeError, ValueError):
                fecha = None

            resultados.append({
                "titulo": html.unescape(titulo),
                "enlace": enlace,
                "fecha": fecha,
                "fuente": fuente or "Google News"
            })

        return resultados

    except Exception as error:
        print(f"Error buscando {consulta}: {error}")
        return []

def parece_tiktok(item):
    texto = (item["titulo"] + " " + item["enlace"]).lower()
    menciona_tiktok = "tiktok.com" in texto or "tiktok" in texto
    es_video = any(
        palabra in texto
        for palabra in ["clip", "video", "viral", "directo", "streamer"]
    )
    return menciona_tiktok and es_video

def crear_informe():
    ahora = datetime.now(timezone.utc)
    limite = ahora - timedelta(hours=HORAS)
    encontrados = {}

    for creador in CREADORES:
        consulta = f'"{creador}" TikTok clip OR viral'
        print(f"Buscando: {creador}")
        for item in buscar_google_news(consulta):
            fecha = item["fecha"]

            if fecha is None or fecha < limite or fecha > ahora:
                continue

            if not parece_tiktok(item):
                continue

            clave = re.sub(
                r"[^a-z0-9]",
                "",
                item["titulo"].lower()
            )

            if clave not in encontrados:
                encontrados[clave] = item

    lista = sorted(
        encontrados.values(),
        key=lambda x: x["fecha"],
        reverse=True
    )[:MAX_RESULTADOS]

    lineas = [
        "# Radar de clips virales de TikTok",
        "",
        f"**Actualizado:** {ahora.astimezone().strftime('%d/%m/%Y %H:%M UTC')}",
        f"**Ventana:** últimas {HORAS} horas",
        "",
        "> Esta búsqueda usa resultados públicos de Google News. "
        "No representa una búsqueda completa de TikTok. "
        "Los enlaces se deben comprobar antes de publicar.",
        "",
    ]

    if not lista:
        lineas += [
            "No se encontraron resultados verificables en esta ejecución.",
            "",
            "Esto no significa que no existan clips nuevos en TikTok.",
            ""
        ]
    else:
        for i, item in enumerate(lista, start=1):
            fecha = item["fecha"].strftime("%d/%m/%Y %H:%M UTC")
            lineas += [
                f"## {i}. {item['titulo']}",
                f"- **Fecha reportada:** {fecha}",
                f"- **Fuente:** {item['fuente']}",
                f"- **Enlace para revisar:** {item['enlace']}",
                ""
            ]

    os.makedirs(os.path.dirname(ARCHIVO_SALIDA), exist_ok=True)
    with open(ARCHIVO_SALIDA, "w", encoding="utf-8") as archivo:
        archivo.write("\n".join(lineas))

    print(f"Informe guardado en {ARCHIVO_SALIDA}")
    print(f"Resultados encontrados: {len(lista)}")

if __name__ == "__main__":
    crear_informe()
