
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

# Agrega aquí los feeds RSS de otros creadores cuando los tengas.
# Por ahora se conserva el feed que ya está configurado.
FEEDS = {
    "Westcol": "https://rss.app/feeds/sf6KmIdBp9qAeT52.xml",
}


def convertir_fecha(texto):
    if not texto:
        return None

    texto = texto.strip()

    # Intentar primero formatos ISO 8601.
    try:
        fecha = datetime.fromisoformat(
            texto.replace("Z", "+00:00")
        )

        if fecha.tzinfo is None:
            fecha = fecha.replace(tzinfo=timezone.utc)

        return fecha.astimezone(timezone.utc)

    except (ValueError, TypeError, OverflowError):
        pass

    # Intentar formatos habituales de RSS.
    try:
        fecha = parsedate_to_datetime(texto)

        if fecha.tzinfo is None:
            fecha = fecha.replace(tzinfo=timezone.utc)

        return fecha.astimezone(timezone.utc)

    except (ValueError, TypeError, OverflowError):
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

        # Leer publicaciones RSS.
        for item in raiz.findall(".//item"):
            titulo = html.unescape(
                (item.findtext("title") or "").strip()
            )

            enlace = (
                item.findtext("link") or ""
            ).strip()

            fecha_texto = (
                item.findtext("pubDate")
                or item.findtext(
                    "{http://www.w3.org/2005/Atom}published"
                )
                or item.findtext(
                    "{http://www.w3.org/2005/Atom}updated"
                )
                or item.findtext(
                    "{http://purl.org/dc/elements/1.1/}date"
                )
                or ""
            ).strip()

            if not enlace:
                continue

            resultados.append({
                "creador": creador,
                "titulo": titulo or f"Publicación de {creador}",
                "enlace": enlace,
                "fecha": convertir_fecha(fecha_texto),
            })

        # Si el feed usa Atom, leer sus entradas.
        if not resultados:
            ns = {
                "atom": "http://www.w3.org/2005/Atom"
            }

            for item in raiz.findall(".//atom:entry", ns):
                titulo = item.findtext(
                    "atom:title", "", ns
                ).strip()

                enlace_elemento = item.find(
                    "atom:link", ns
                )

                enlace = ""

                if enlace_elemento is not None:
                    enlace = enlace_elemento.get("href", "")

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
                        "fecha": convertir_fecha(fecha_texto),
                    })

    except Exception as error:
        print(f"Error leyendo el feed de {creador}: {error}")

    print(
        f"Feed de {creador}: "
        f"{len(resultados)} publicaciones leídas"
    )

    return resultados


def crear_informe():
    ahora = datetime.now(timezone.utc)
    limite = ahora - timedelta(hours=HORAS)

    encontrados = {}

    for creador, url in FEEDS.items():
        print(f"Consultando TikTok de {creador}...")

        publicaciones = leer_feed(creador, url)

        for item in publicaciones:
            fecha = item["fecha"]

            # No inventar ni asumir fechas que no estén verificadas.
            if fecha is None:
                print(
                    "Publicación omitida por fecha desconocida: "
                    + item["titulo"]
                )
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
        key=lambda item: item["fecha"],
        reverse=True
    )[:MAX_RESULTADOS]

    lineas = [
        "# Radar de clips de TikTok",
        "",
        f"**Actualizado:** {ahora.strftime('%d/%m/%Y %H:%M UTC')}",
        f"**Periodo revisado:** últimas {HORAS} horas",
        f"**Feeds configurados:** {len(FEEDS)}",
        f"**Publicaciones encontradas:** {len(lista)}",
        "",
        "> Este informe depende de los feeds RSS configurados. "
        "No representa todo TikTok. Verifica el contenido y el enlace "
        "antes de publicar.",
        "",
    ]

    if not lista:
        lineas.extend([
            "No se encontraron publicaciones con fecha verificable "
            "dentro del periodo revisado.",
            "",
            "Esto no confirma que no existan videos nuevos. "
            "Puede que el feed no los haya entregado o que no incluya "
            "fechas verificables.",
            "",
        ])

    else:
        for numero, item in enumerate(lista, start=1):
            fecha = item["fecha"].strftime(
                "%d/%m/%Y %H:%M UTC"
            )

            lineas.extend([
                f"## {numero}. {item['titulo']}",
                f"- **Creador:** {item['creador']}",
                f"- **Fecha reportada:** {fecha}",
                f"- **Enlace:** {item['enlace']}",
                "",
            ])

    carpeta = os.path.dirname(ARCHIVO_SALIDA)
    os.makedirs(carpeta, exist_ok=True)

    with open(
        ARCHIVO_SALIDA,
        "w",
        encoding="utf-8"
    ) as archivo:
        archivo.write("\n".join(lineas))

    print(f"Informe guardado en {ARCHIVO_SALIDA}")
    print(f"Publicaciones incluidas: {len(lista)}")


if __name__ == "__main__":
    crear_informe()
