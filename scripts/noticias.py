
import html
import json
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

import requests
import xml.etree.ElementTree as ET

COLOMBIA = timezone(timedelta(hours=-5))
AHORA = datetime.now(COLOMBIA)
LIMITE = AHORA - timedelta(hours=48)

MAX_RESULTADOS = 25
MAX_WESTCOL = 2
MAX_POR_CREADOR = 3
MAX_NOTICIAS = 15
MAX_ITEMS_BUSQUEDA = 8

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

EMERGENTES = [
    "streamer colombiano Kick",
    "streamer colombiano viral",
    "clips streamers Colombia",
]

CABECERAS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/130 Safari/537.36"
}


def limpiar(texto):
    return re.sub(
        r"\s+", " ",
        html.unescape(str(texto or ""))
    ).strip()


def fecha_youtube(video):
    marca = video.get("release_timestamp")
    if marca is None:
        marca = video.get("timestamp")

    if marca is not None:
        try:
            return datetime.fromtimestamp(
                float(marca), tz=timezone.utc
            ).astimezone(COLOMBIA)
        except (ValueError, TypeError, OverflowError, OSError):
            pass

    fecha_texto = video.get("upload_date")
    if fecha_texto and re.fullmatch(r"\d{8}", str(fecha_texto)):
        try:
            return datetime.strptime(
                str(fecha_texto), "%Y%m%d"
            ).replace(tzinfo=COLOMBIA)
        except ValueError:
            pass

    return None


def dentro_de_ventana(fecha):
    return fecha is not None and LIMITE <= fecha <= AHORA


def ejecutar_busqueda_youtube(consulta, max_items):
    comando = [
        sys.executable,
        "-m", "yt_dlp",
        "--dump-single-json",
        "--skip-download",
        "--flat-playlist",
        "--extractor-args", "youtubetab:approximate_date",
        "--no-warnings",
        "--ignore-errors",
        "--playlist-end", str(max_items),
        f"ytsearchdate{max_items}:{consulta}",
    ]

    proceso = subprocess.run(
        comando,
        capture_output=True,
        text=True,
        timeout=90,
    )

    salida = (proceso.stdout or "").strip()
    error = limpiar((proceso.stderr or "")[-700:])

    if not salida:
        print(
            f"  YouTube no devolvió resultados para "
            f"'{consulta}'. Código: {proceso.returncode}"
        )
        if error:
            print(f"  Detalle: {error}")
        return []

    try:
        datos = json.loads(salida)
    except json.JSONDecodeError:
        entradas = []
        for linea in salida.splitlines():
            try:
                entradas.append(json.loads(linea))
            except json.JSONDecodeError:
                continue
        datos = {"entries": entradas}

    if isinstance(datos, dict):
        videos = datos.get("entries") or []
        # Por si yt-dlp devolviera directamente un solo video.
        if not videos and datos.get("id"):
            videos = [datos]
    else:
        videos = []

    print(f"  Resultados brutos: {len(videos)}")

    resultados = []
    sin_fecha = 0
    fuera_ventana = 0

    for video in videos:
        if not isinstance(video, dict):
            continue

        fecha = fecha_youtube(video)

        if fecha is None:
            sin_fecha += 1
            continue

        if not dentro_de_ventana(fecha):
            fuera_ventana += 1
            continue

        video_id = video.get("id")
        enlace = (
            video.get("webpage_url")
            or video.get("original_url")
        )

        if not enlace and video_id:
            enlace = f"https://www.youtube.com/watch?v={video_id}"

        if not enlace:
            continue

        resultados.append({
            "titulo": limpiar(video.get("title") or "Video sin título"),
            "url": enlace,
            "canal": limpiar(
                video.get("channel")
                or video.get("uploader")
                or video.get("channel_id")
                or "Canal no identificado"
            ),
            "fecha": fecha,
            "creador": "",
            "fuente": "Búsqueda pública de YouTube con yt-dlp",
        })

    print(
        f"  Fechas no verificables: {sin_fecha}; "
        f"fuera de 48 h: {fuera_ventana}; "
        f"válidos: {len(resultados)}"
    )

    if error and not resultados:
        print(f"  Aviso de yt-dlp: {error}")

    return resultados


def buscar_youtube(consulta, max_items=MAX_ITEMS_BUSQUEDA):
    try:
        return ejecutar_busqueda_youtube(consulta, max_items)
    except subprocess.TimeoutExpired:
        print(f"  Tiempo agotado buscando: {consulta}")
    except Exception as error:
        print(f"  Error buscando '{consulta}': {error}")

    return []


def buscar_noticias(consulta):
    parametros = {
        "q": f"{consulta} when:2d",
        "hl": "es-419",
        "gl": "CO",
        "ceid": "CO:es-419",
    }

    url = (
        "https://news.google.com/rss/search?"
        + requests.compat.urlencode(parametros)
    )

    resultados = []

    try:
        respuesta = requests.get(
            url,
            headers=CABECERAS,
            timeout=25,
        )
        respuesta.raise_for_status()
        raiz = ET.fromstring(respuesta.content)

        for item in raiz.findall(".//item"):
            titulo = limpiar(item.findtext("title", ""))
            enlace = (item.findtext("link", "") or "").strip()
            pubdate = item.findtext("pubDate", "")

            try:
                fecha = parsedate_to_datetime(pubdate)
                if fecha.tzinfo is None:
                    fecha = fecha.replace(tzinfo=timezone.utc)
                fecha = fecha.astimezone(COLOMBIA)
            except (ValueError, TypeError, OverflowError):
                fecha = None

            if titulo and enlace and dentro_de_ventana(fecha):
                resultados.append({
                    "titulo": titulo,
                    "url": enlace,
                    "fecha": fecha,
                    "creador": "",
                    "fuente": "Google News RSS",
                })

    except Exception as error:
        print(f"Error en Google News ({consulta}): {error}")

    return resultados


def recopilar_clips():
    encontrados = []

    consultas = [
        (creador, f"{creador} clips")
        for creador in CREADORES
    ]

    consultas += [
        (creador, f"{creador} shorts")
        for creador in CREADORES
    ]

    consultas += [
        ("Emergentes Colombia", consulta)
        for consulta in EMERGENTES
    ]

    total = len(consultas)

    for indice, (creador, consulta) in enumerate(consultas, 1):
        print(f"[{indice}/{total}] Buscando: {consulta}")

        for video in buscar_youtube(consulta):
            video["creador"] = creador
            encontrados.append(video)

    unicos = {}

    for video in encontrados:
        clave = video["url"].split("&", 1)[0].rstrip("/")
        if clave not in unicos:
            unicos[clave] = video

    return list(unicos.values())


def seleccionar_clips(videos):
    videos.sort(key=lambda video: video["fecha"], reverse=True)

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
    consultas = [
        f'"{creador}" streamer OR directo OR polémica'
        for creador in CREADORES
    ]

    consultas += [
        "streamer colombiano Kick viral",
        "creador de contenido colombiano streamer",
    ]

    candidatas = []

    for consulta in consultas:
        print(f"Google News: {consulta}")
        candidatas.extend(buscar_noticias(consulta))

    unicas = {}

    for noticia in candidatas:
        unicas.setdefault(noticia["url"], noticia)

    ordenadas = sorted(
        unicas.values(),
        key=lambda noticia: noticia["fecha"],
        reverse=True,
    )

    elegidas = []
    conteo = {}

    for noticia in ordenadas:
        titulo = noticia["titulo"].lower()

        detectado = next(
            (
                creador
                for creador in CREADORES
                if creador.lower() in titulo
            ),
            "Otros",
        )

        if conteo.get(detectado, 0) >= 2:
            continue

        elegidas.append(noticia)
        conteo[detectado] = conteo.get(detectado, 0) + 1

        if len(elegidas) >= MAX_NOTICIAS:
            break

    return elegidas


def escribir_informe(clips, noticias):
    CARPETA.mkdir(parents=True, exist_ok=True)

    lineas = [
        "# Radar automático de creadores y clips",
        "",
        f"Actualizado: {AHORA.strftime('%d/%m/%Y %I:%M %p')} (hora de Colombia)",
        "",
        "Ventana objetivo: últimas 48 horas.",
        f"Clips candidatos encontrados: {len(clips)}.",
        f"Noticias recientes encontradas: {len(noticias)}.",
        "",
        "> Radar gratuito basado en metadatos públicos. "
        "La búsqueda puede ser limitada por YouTube. "
        "Verifica los enlaces y los derechos antes de publicar.",
        "",
        "## Clips y Shorts candidatos de YouTube",
        "",
    ]

    if clips:
        for video in clips:
            lineas.extend([
                f"### {video['titulo']}",
                f"- Búsqueda/creador: {video['creador']}",
                f"- Canal que publicó: {video['canal']}",
                f"- Publicado: {video['fecha'].strftime('%d/%m/%Y %I:%M %p')}",
                f"- Fuente: {video['fuente']}",
                f"- Enlace directo: {video['url']}",
                "",
            ])
    else:
        lineas.extend([
            "No se encontraron videos verificables dentro de las últimas 48 horas.",
            "",
            "Consulta los registros del workflow para ver los resultados brutos, "
            "las fechas no verificables y los posibles errores de YouTube.",
            "No se inventan resultados ni se asume que un video sin fecha sea reciente.",
            "",
        ])

    lineas.extend([
        "## Noticias y contexto (no son necesariamente clips)",
        "",
    ])

    if noticias:
        for noticia in noticias:
            fecha = noticia["fecha"].strftime("%d/%m/%Y %I:%M %p")
            lineas.append(
                f"- **{noticia['titulo']}** — {fecha} — "
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
        "## Criterios",
        "",
        f"- Máximo de clips: {MAX_RESULTADOS}.",
        f"- Máximo de Westcol: {MAX_WESTCOL}.",
        f"- Máximo por otra búsqueda/creador: {MAX_POR_CREADOR}.",
        "- Ventana temporal: 48 horas.",
        "- Deduplicación por enlace.",
        "- Noticias separadas de los clips.",
        "- Búsquedas exploratorias de streamers emergentes colombianos.",
        "",
        "## Limitaciones",
        "",
        "La búsqueda de YouTube puede fallar, limitarse o no proporcionar fechas. "
        "Este radar no garantiza cobertura exhaustiva de Kick o TikTok.",
        "No descargues ni republices videos ajenos sin permiso. "
        "Añade comentario, análisis o contexto original y revisa las políticas "
        "de monetización de cada plataforma.",
        "",
    ])

    SALIDA.write_text("\n".join(lineas), encoding="utf-8")

    print(
        f"Informe guardado: {SALIDA} | "
        f"clips: {len(clips)} | noticias: {len(noticias)}"
    )


def main():
    print("=" * 55)
    print("RADAR GRATUITO DE CREADORES")
    print(f"Hora Colombia: {AHORA.strftime('%d/%m/%Y %I:%M %p')}")
    print(f"Ventana desde: {LIMITE.strftime('%d/%m/%Y %I:%M %p')}")
    print("=" * 55)

    clips = seleccionar_clips(recopilar_clips())
    noticias = recopilar_noticias()

    escribir_informe(clips, noticias)


if __name__ == "__main__":
    main()
