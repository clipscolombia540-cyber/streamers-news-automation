
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
    diagnostico = {
        "leidas": 0,
        "sin_fecha": 0,
        "fuera_periodo_antiguas": 0,
        "fecha_futura": 0,
        "duplicadas": 0,
        "dentro_periodo": 0,
    }

    for creador, url in FEEDS.items():
        print(f"Consultando TikTok de {creador}...")

        publicaciones = leer_feed(creador, url)
        diagnostico["leidas"] += len(publicaciones)

        for item in publicaciones:
            fecha = item["fecha"]

            if fecha is None:
                diagnostico["sin_fecha"] += 1
                print(
                    "Publicación omitida por fecha desconocida: "
                    + item["titulo"]
                )
                continue

            if fecha > ahora:
                diagnostico["fecha_futura"] += 1
                continue

            if fecha < limite:
                diagnostico["fuera_periodo_antiguas"] += 1
                continue

            diagnostico["dentro_periodo"] += 1
            clave = re.sub(
                r"[^a-z0-9]",
                "",
                item["enlace"].lower().rstrip("/")
            )

            if clave in encontrados:
                diagnostico["duplicadas"] += 1
                continue

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
        f"**Publicaciones leídas:** {diagnostico['leidas']}",
        f"**Publicaciones encontradas:** {len(lista)}",
        "",
        "## Diagnóstico del feed",
        f"- Sin fecha verificable: {diagnostico['sin_fecha']}",
        f"- Más antiguas que {HORAS} horas: {diagnostico['fuera_periodo_antiguas']}",
        f"- Con fecha futura: {diagnostico['fecha_futura']}",
        f"- Dentro del periodo antes de quitar duplicados: {diagnostico['dentro_periodo']}",
        f"- Duplicadas: {diagnostico['duplicadas']}",
        "",
        "> Este informe depende de los feeds RSS configurados. "
        "No representa todo TikTok. Verifica el contenido y el enlace "
        "antes de publicar.",
        "",
    ]

    if not lista:
        if diagnostico["leidas"] and diagnostico["fuera_periodo_antiguas"] == diagnostico["leidas"]:
            motivo = (
                "El feed sí entregó publicaciones, pero todas son más antiguas "
                f"que {HORAS} horas. Puede que el feed esté desactualizado."
            )
        elif diagnostico["sin_fecha"]:
            motivo = (
                "Algunas publicaciones no traen fecha verificable; no se "
                "incluyen para evitar presentar contenido viejo como nuevo."
            )
        else:
            motivo = (
                "El feed no entregó publicaciones con fecha verificable "
                f"dentro de las últimas {HORAS} horas."
            )

        lineas.extend([
            "No se encontraron publicaciones recientes verificables.",
            "",
            motivo,
            "Esto no confirma que no existan videos nuevos en TikTok; "
            "solo describe lo que entregó el feed configurado.",
            "",
        ])

    else:
        for numero, item in enumerate(lista, start=1):
            fecha = item["fecha"].strftime("%d/%m/%Y %H:%M UTC")
            lineas.extend([
                f"## {numero}. {item['titulo']}",
                f"- **Creador:** {item['creador']}",
                f"- **Fecha reportada:** {fecha}",
                f"- **Enlace:** {item['enlace']}",
                "",
            ])

    carpeta = os.path.dirname(ARCHIVO_SALIDA)
    os.makedirs(carpeta, exist_ok=True)

    with open(ARCHIVO_SALIDA, "w", encoding="utf-8") as archivo:
        archivo.write("\n".join(lineas))

    print("Diagnóstico TikTok: " + str(diagnostico))
    print(f"Informe guardado en {ARCHIVO_SALIDA}")
    print(f"Publicaciones incluidas: {len(lista)}")


if __name__ == "__main__":
    crear_informe()
