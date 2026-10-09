
import os
import re
import html
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

ARCHIVO_SALIDA = "borradores/clips_tiktok.md"
HORAS = 48
MAX_RESULTADOS = 25

FEEDS = {
    "Westcol": "https://rss.app/feeds/sf6KmIdBp9qAeT52.xml",
}

def fecha_publicacion(texto):
    if not texto:
        return None

    try:
        fecha = parsedate_to_datetime(texto)
        if fecha.tzinfo is None:
            fecha = fecha.replace(tzinfo=timezone.utc)
        return fecha.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return None

def leer_feed(creador, url):
    resultados = []

    try:
        respuesta = requests.get(
            url,
            timeout=25,
            headers={"User-Agent": "Mozilla/5.0"}
        )
        respuesta.raise_for_status()
        raiz = ET.fromstring(respuesta.content)

        for item in raiz.findall(".//item"):
            titulo = html.unescape(
                (item.findtext("title") or "").strip()
            )
            enlace = (item.findtext("link") or "").strip()
            fecha_texto = (
                item.findtext("pubDate")
                or item.findtext("{http://www.w3.org/2005/Atom}published")
                or item.findtext("{http://www.w3.org/2005/Atom}updated")
                or ""
            ).strip()

            if not enlace:
                continue

            fecha = fecha_publicacion(fecha_texto)

            resultados.append({
                "creador": creador,
                "titulo": titulo or f"Publicación de {creador}",
                "enlace": enlace,
                "fecha": fecha,
            })

        # Algunos feeds utilizan el formato Atom en lugar de RSS.
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        if not resultados:
            for item in raiz.findall(".//atom:entry", ns):
                titulo = item.findtext("atom:title", "", ns).strip()
                enlace_elemento = item.find("atom:link", ns)
                enlace = (
                    enlace_elemento.get("href", "")
                    if enlace_elemento is not None else ""
                )
                fecha_texto = (
                    item.findtext("atom:published", "", ns)
                    or item.findtext("atom:updated", "", ns)
                ).strip()

                if enlace:
                    resultados.append({
                        "creador": creador,
                        "titulo": html.unescape(
                            titulo or f"Publicación de {creador}"
                        ),
                        "enlace": enlace,
                        "fecha": fecha_publicacion(fecha_texto),
                    })

    except Exception as error:
        print(f"Error leyendo feed de {creador}: {error}")

    return resultados

def crear_informe():
    ahora = datetime.now(timezone.utc)
    limite = ahora - timedelta(hours=HORAS)
    encontrados = {}

    for creador, url in FEEDS.items():
        print(f"Consultando feed de {creador}...")
        for item in leer_feed(creador, url):
            fecha = item["fecha"]

            # No asumir que una fecha desconocida es reciente.
            if fecha is None:
                print(f"Publicación sin fecha verificable: {item['titulo']}")
                continue

            if fecha < limite or fecha > ahora:
                continue

            clave = re.sub(
                r"[^a-z0-9]",
                "",
                item["enlace"].lower().rstrip("/")
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
        f"**Actualizado:** {ahora.strftime('%d/%m/%Y %H:%M UTC')}",
        f"**Ventana:** últimas {HORAS} horas",
        f"**Fuentes configuradas:** {len(FEEDS)}",
        "",
        "> Fuente: feeds RSS configurados. La disponibilidad y las fechas "
        "dependen de la información publicada por cada feed. "
        "Verifica cada enlace antes de publicar.",
        "",
    ]

    if not lista:
        lineas.extend([
            "No se encontraron publicaciones con fecha verificable "
            "dentro de las últimas 48 horas.",
            "",
            "Esto no significa que no existan videos nuevos.",
            ""
        ])
    else:
        for numero, item in enumerate(lista, start=1):
            fecha = item["fecha"].strftime("%d/%m/%Y %H:%M UTC")
            lineas.extend([
                f"## {numero}. {item['titulo']}",
                f"- **Creador:** {item['creador']}",
                f"- **Fecha reportada:** {fecha}",
                f"- **Enlace:** {item['enlace']}",
                ""
            ])

    os.makedirs(os.path.dirname(ARCHIVO_SALIDA), exist_ok=True)
    with open(ARCHIVO_SALIDA, "w", encoding="utf-8") as archivo:
        archivo.write("\n".join(lineas))

    print(f"Informe guardado en {ARCHIVO_SALIDA}")
    print(f"Publicaciones incluidas: {len(lista)}")

if __name__ == "__main__":
    crear_informe()
