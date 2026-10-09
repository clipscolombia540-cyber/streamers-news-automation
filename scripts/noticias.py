
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode
import time
import re
import html

# ======================================================
# RADAR GRATUITO DE CREADORES COLOMBIANOS
# Sin API de pago, sin claves y sin cookies de usuario.
# ======================================================

COLOMBIA = timezone(timedelta(hours=-5))
AHORA = datetime.now(COLOMBIA)
LIMITE = AHORA - timedelta(hours=48)

MAX_RESULTADOS = 25
MAX_WESTCOL = 2
MAX_POR_CREADOR = 3
PAUSA = 1.5

CARPETA = Path("borradores")
SALIDA = CARPETA / "radar_creadores.md"

CREADORES = [
    "Westcol",
    "MrStivenTC",
    "Pelicanger",
    "Samulx",
    "Chanty",
    "La Sapa",
    "Lonche de Huevito",
    "Rey de la City",
]

CONSULTAS = [
    "{creador} clips",
    "{creador} shorts",
]

CABECERAS = {
    "User-Agent": "Mozilla/5.0 (compatible; RadarPublico/1.0)"
}

NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "media": "http://search.yahoo.com/mrss/",
}


def limpiar(texto):
    texto = html.unescape(texto or "")
    return re.sub(r"\s+", " ", texto).strip()


def convertir_fecha(texto):
    if not texto:
        return None

    try:
        fecha = datetime.fromisoformat(
            texto.strip().replace("Z", "+00:00")
        )
        if fecha.tzinfo is None:
            fecha = fecha.replace(tzinfo=timezone.utc)
        return fecha.astimezone(COLOMBIA)
    except (ValueError, TypeError):
        pass

    try:
        fecha = datetime.strptime(
            texto.strip(), "%Y-%m-%d"
        )
        return fecha.replace(tzinfo=COLOMBIA)
    except (ValueError, TypeError):
        return None


def esta_en_ventana(fecha):
    return fecha is not None and LIMITE <= fecha <= AHORA


def obtener_xml(url):
    respuesta = requests.get(
        url,
        headers=CABECERAS,
        timeout=25,
    )
    respuesta.raise_for_status()
    return ET.fromstring(respuesta.content)


def buscar_youtube(consulta):
    """
    Prueba el feed RSS de búsqueda de YouTube.
    No utiliza yt-dlp ni necesita una clave API.
    """
    parametros = urlencode({
        "search_query": consulta,
        "order": "date",
    })

    url = (
        "https://www.youtube.com/feeds/videos.xml?"
        + parametros
    )

    resultados = []

    try:
        raiz = obtener_xml(url)

        entradas = raiz.findall("atom:entry", NS)
        if not entradas:
            entradas = raiz.findall("entry")

        for entrada in entradas:
            titulo = entrada.findtext(
                "atom:title", default="", namespaces=NS
            ) or entrada.findtext("title", default="")

            publicado = entrada.findtext(
                "atom:published", default="", namespaces=NS
            ) or entrada.findtext("published", default="")

            enlace_elemento = entrada.find(
                "atom:link", NS
            )
            if enlace_elemento is None:
                enlace_elemento = entrada.find("link")

            enlace = ""
            if enlace_elemento is not None:
                enlace = enlace_elemento.attrib.get("href", "")

            autor_elemento = entrada.find("atom:author/atom:name", NS)
            canal = (
                autor_elemento.text
                if autor_elemento is not None
                else "Canal no identificado"
            )

            fecha = convertir_fecha(publicado)

            if not titulo or not enlace:
                continue

            if not esta_en_ventana(fecha):
                continue

            resultados.append({
                "titulo": limpiar(titulo),
                "url": enlace,
                "canal": limpiar(canal),
                "fecha": fecha,
                "creador": "",
                "fuente": "YouTube RSS",
            })

    except requests.RequestException as error:
        print(f"Error de conexión en YouTube RSS ({consulta}): {error}")
    except ET.ParseError as error:
        print(f"XML inválido en YouTube RSS ({consulta}): {error}")
    except Exception as error:
        print(f"Error inesperado en YouTube RSS ({consulta}): {error}")

    return resultados


def buscar_noticias(consulta):
    """
    Fuente de contexto, separada de los clips.
    Google News RSS no necesita una API key.
    """
    parametros = urlencode({
        "q": consulta + " when:2d",
        "hl": "es-419",
        "gl": "CO",
        "ceid": "CO:es-419",
    })

    url = (
        "https://news.google.com/rss/search?"
        + parametros
    )

    resultados = []

    try:
        raiz = obtener_xml(url)

        for item in raiz.findall(".//item"):
            titulo = item.findtext("title", default="")
            enlace = item.findtext("link", default="")
            publicado = item.findtext("pubDate", default="")

            fecha = None
            if publicado:
                try:
                    from email.utils import parsedate_to_datetime
                    fecha = parsedate_to_datetime(publicado)
                    if fecha.tzinfo is None:
                        fecha = fecha.replace(tzinfo=timezone.utc)
                    fecha = fecha.astimezone(COLOMBIA)
                except (ValueError, TypeError, OverflowError):
                    fecha = None

            if not titulo or not enlace or not esta_en_ventana(fecha):
                continue

            resultados.append({
                "titulo": limpiar(titulo),
                "url": enlace,
                "fecha": fecha,
                "creador": "",
                "fuente": "Google News RSS",
            })

    except requests.RequestException as error:
        print(f"Error de conexión en Google News ({consulta}): {error}")
    except ET.ParseError as error:
        print(f"XML inválido en Google News ({consulta}): {error}")
    except Exception as error:
        print(f"Error inesperado en Google News ({consulta}): {error}")

    return resultados


def recopilar_clips():
    encontrados = []
    errores_vistos = set()

    total = len(CREADORES) * len(CONSULTAS)
    actual = 0

    for creador in CREADORES:
        for plantilla in CONSULTAS:
            actual += 1
            consulta = plantilla.format(creador=creador)

            print(f"[{actual}/{total}] YouTube RSS: {consulta}")

            resultados = buscar_youtube(consulta)
            print(f"    Resultados recientes: {len(resultados)}")

            for video in resultados:
                video["creador"] = creador
                encontrados.append(video)

            time.sleep(PAUSA)

    # Eliminar duplicados por enlace.
    unicos = {}
    for video in encontrados:
        clave = video["url"].split("&")[0].rstrip("/")
        if clave not in unicos:
            unicos[clave] = video

    return list(unicos.values())


def seleccionar_clips(videos):
    videos.sort(key=lambda x: x["fecha"], reverse=True)

    seleccionados = []
    conteo = {}

    for video in videos:
        if len(seleccionados) >= MAX_RESULTADOS:
            break

        creador = video["creador"]
        limite = (
            MAX_WESTCOL
            if creador.lower() == "westcol"
            else MAX_POR_CREADOR
        )

        if conteo.get(creador, 0) >= limite:
            continue

        seleccionados.append(video)
        conteo[creador] = conteo.get(creador, 0) + 1

    return seleccionados


def recopilar_noticias():
    noticias = []
    consultas = [
        f'"{creador}" streamer' for creador in CREADORES
    ]

    for consulta in consultas:
        print(f"Google News RSS: {consulta}")

        noticias.extend(buscar_noticias(consulta))
        time.sleep(PAUSA)

    unicas = {}
    for noticia in noticias:
        if noticia["url"] not in unicas:
            unicas[noticia["url"]] = noticia

    return sorted(
        unicas.values(),
        key=lambda x: x["fecha"],
        reverse=True,
    )[:15]


def escribir_informe(clips, noticias):
    CARPETA.mkdir(parents=True, exist_ok=True)

    lineas = [
        "# Radar automático de creadores y clips",
        "",
        f"Actualizado: {AHORA.strftime('%d/%m/%Y %I:%M %p')} "
        "(hora de Colombia)",
        "",
        "Ventana objetivo: últimas 48 horas.",
        f"Clips candidatos encontrados: {len(clips)}.",
        f"Noticias recientes encontradas: {len(noticias)}.",
        "",
        "> Fuentes públicas gratuitas. La cobertura depende de los "
        "feeds disponibles; no garantiza encontrar todos los clips "
        "ni confirma derechos de reutilización o monetización.",
        "",
        "## Clips y Shorts candidatos de YouTube",
        "",
    ]

    if clips:
        for video in clips:
            lineas.extend([
                f"### {video['titulo']}",
                f"- Creador relacionado con la búsqueda: {video['creador']}",
                f"- Canal que publicó: {video['canal']}",
                f"- Publicado: {video['fecha'].strftime('%d/%m/%Y %I:%M %p')}",
                f"- Fuente: {video['fuente']}",
                f"- Enlace: {video['url']}",
                "",
            ])
    else:
        lineas.extend([
            "No se encontraron videos recientes en los feeds de búsqueda.",
            "",
            "Revisa los registros de GitHub Actions para ver si la fuente "
            "está vacía, bloqueada o no disponible.",
            "",
        ])

    lineas.extend([
        "## Noticias y contexto (no son necesariamente clips)",
        "",
    ])

    if noticias:
        for noticia in noticias:
            lineas.append(
                f"- **{noticia['titulo']}** — "
                f"{noticia['fecha'].strftime('%d/%m/%Y %I:%M %p')} — "
                f"[Abrir fuente]({noticia['url']})"
            )
        lineas.append("")
    else:
        lineas.extend([
            "No se encontraron noticias recientes en Google News RSS.",
            "",
        ])

    lineas.extend([
        "## Creadores vigilados",
        "",
        ", ".join(CREADORES),
        "",
        "## Límites",
        "",
        f"- Máximo total de clips: {MAX_RESULTADOS}.",
        f"- Máximo de Westcol: {MAX_WESTCOL}.",
        f"- Máximo de cada otro creador: {MAX_POR_CREADOR}.",
        "- Duplicados eliminados por enlace.",
        "- Fechas fuera de las últimas 48 horas excluidas.",
        "- Noticias separadas de los videos.",
        "",
        "## Limitaciones",
        "",
        "Este radar no busca de forma exhaustiva en TikTok, Instagram, "
        "Twitch o Kick. Tampoco garantiza que cada video encontrado "
        "sea un clip viral o que pueda reutilizarse legalmente.",
        "",
    ])

    SALIDA.write_text("\n".join(lineas), encoding="utf-8")

    print(f"Informe guardado: {SALIDA}")
    print(f"Clips seleccionados: {len(clips)}")
    print(f"Noticias: {len(noticias)}")


def main():
    print("=" * 50)
    print("RADAR GRATUITO DE CREADORES")
    print(f"Hora Colombia: {AHORA.strftime('%d/%m/%Y %I:%M %p')}")
    print(f"Desde: {LIMITE.strftime('%d/%m/%Y %I:%M %p')}")
    print("=" * 50)

    videos = recopilar_clips()
    clips = seleccionar_clips(videos)
    noticias = recopilar_noticias()

    escribir_informe(clips, noticias)


if __name__ == "__main__":
    main()
