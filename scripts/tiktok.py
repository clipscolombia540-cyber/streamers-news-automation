
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


def obtener_feeds():
    """Permite ampliar feeds desde el entorno sin editar el código.

    Formato de TIKTOK_FEEDS: Nombre=https://feed1.xml;Otro=https://feed2.xml
    Si no se configura, se usa la lista FEEDS predeterminada.
    """
    configuracion = os.environ.get("TIKTOK_FEEDS", "").strip()
    if not configuracion:
        return dict(FEEDS)

    feeds = {}
    for entrada in configuracion.split(";"):
        if "=" not in entrada:
            print("Entrada TIKTOK_FEEDS ignorada; se esperaba Nombre=URL.")
            continue
        nombre, url = entrada.split("=", 1)
        nombre, url = nombre.strip(), url.strip()
        if nombre and url.startswith(("https://", "http://")):
            feeds[nombre] = url
        else:
            print("Entrada TIKTOK_FEEDS ignorada por nombre o URL inválidos.")

    if feeds:
        return feeds
    print("TIKTOK_FEEDS no contenía entradas válidas; se usan los feeds predeterminados.")
    return dict(FEEDS)


def tipo_de_cuenta(nombre):
    """Clasifica los feeds por etiqueta para priorizar cuentas de clips de terceros."""
    etiqueta = (nombre or "").strip().lower()
    if etiqueta.startswith(("clipero:", "clips:", "fan:", "momentos:", "recortes:", "tiktok:")):
        return "Cuenta de clips/terceros"
    if etiqueta.startswith("emergente:"):
        return "Creador emergente"
    if etiqueta.startswith("influencer:"):
        return "Influencer"
    return "Cuenta de creador"


def descripcion_configuracion_feeds():
    """Explica si se usa una lista de feeds personalizada o el feed predeterminado."""
    if os.environ.get("TIKTOK_FEEDS", "").strip():
        return (
            "Configuración: feeds personalizados desde TIKTOK_FEEDS. "
            "Se revisan únicamente las cuentas incluidas en esa variable. "
            "Usa etiquetas Clipero:, Clips:, Fan:, Momentos:, Recortes: o TikTok: "
            "para priorizar cuentas que publican clips de terceros."
        )
    return (
        "Aviso: TIKTOK_FEEDS no está configurado; se usa únicamente el feed "
        "predeterminado de Westcol. Para ampliar la cobertura, configura feeds "
        "RSS recientes de varios creadores en el secreto de GitHub."
    )


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


def filtrar_publicaciones_recientes(publicaciones_por_creador, ahora, horas=HORAS):
    """Filtra por fecha verificable, deduplica y devuelve contadores transparentes."""
    limite = ahora - timedelta(hours=horas)
    encontrados = {}
    diagnostico = {
        "leidas": 0,
        "sin_fecha": 0,
        "fuera_periodo_antiguas": 0,
        "fecha_futura": 0,
        "duplicadas": 0,
        "dentro_periodo": 0,
    }

    for publicaciones in publicaciones_por_creador:
        diagnostico["leidas"] += len(publicaciones)
        for item in publicaciones:
            fecha = item.get("fecha")

            if fecha is None:
                diagnostico["sin_fecha"] += 1
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
                item.get("enlace", "").lower().rstrip("/")
            )
            if not clave:
                # Sin URL no se puede deduplicar ni enlazar de forma fiable.
                continue
            if clave in encontrados:
                diagnostico["duplicadas"] += 1
                continue
            encontrados[clave] = item

    prioridad_tipo = {
        "Cuenta de clips/terceros": 0,
        "Creador emergente": 1,
        "Influencer": 2,
        "Cuenta de creador": 3,
    }
    # Agrupa por feed y alterna publicaciones para que una sola cuenta
    # no ocupe todo el radar cuando publica en ráfaga.
    por_feed = {}
    for item in encontrados.values():
        feed = item.get("creador", "Sin identificar")
        por_feed.setdefault(feed, []).append(item)

    for feed_items in por_feed.values():
        feed_items.sort(key=lambda item: item["fecha"].timestamp(), reverse=True)

    feeds_ordenados = sorted(
        por_feed,
        key=lambda feed: prioridad_tipo.get(tipo_de_cuenta(feed), 9),
    )
    lista = []
    max_por_feed = 8
    ronda = 0
    while len(lista) < MAX_RESULTADOS:
        agregados = 0
        for feed in feeds_ordenados:
            feed_items = por_feed[feed]
            if ronda < min(len(feed_items), max_por_feed):
                lista.append(feed_items[ronda])
                agregados += 1
                if len(lista) >= MAX_RESULTADOS:
                    break
        if agregados == 0:
            break
        ronda += 1

    # Mantiene primero las cuentas de clips y, dentro de cada ronda,
    # favorece publicaciones recientes.
    return lista, diagnostico


def crear_informe():
    ahora = datetime.now(timezone.utc)
    publicaciones_por_creador = []
    feeds = obtener_feeds()

    for creador, url in feeds.items():
        print(f"Consultando TikTok de {creador}...")
        publicaciones = leer_feed(creador, url)
        # Conservamos el nombre del creador asignado por el feed.
        publicaciones_por_creador.append(publicaciones)

    lista, diagnostico = filtrar_publicaciones_recientes(
        publicaciones_por_creador, ahora, HORAS
    )
    for clave, cantidad in diagnostico.items():
        print(f"Diagnóstico TikTok - {clave}: {cantidad}")

    conteo_tipos = {}
    for item in lista:
        tipo = tipo_de_cuenta(item.get("creador", ""))
        conteo_tipos[tipo] = conteo_tipos.get(tipo, 0) + 1

    lineas = [
        "# Radar de clips de TikTok",
        "",
        f"**Actualizado:** {ahora.strftime('%d/%m/%Y %H:%M UTC')}",
        f"**Periodo revisado:** últimas {HORAS} horas",
        f"**Feeds configurados:** {len(feeds)}",
        f"**Estado de configuración:** {descripcion_configuracion_feeds()}",
        f"**Publicaciones leídas:** {diagnostico['leidas']}",
        f"**Publicaciones encontradas:** {len(lista)}",
        "**Distribución por tipo:** " + (
            "; ".join(f"{tipo}: {cantidad}" for tipo, cantidad in sorted(conteo_tipos.items()))
            if conteo_tipos else "sin publicaciones recientes"
        ),
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
                f"- **Tipo de cuenta:** {tipo_de_cuenta(item.get('creador', ''))}",
                f"- **Cuenta monitoreada:** {item['creador']}",
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
