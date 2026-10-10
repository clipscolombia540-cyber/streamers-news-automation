
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

# ============================================================
# CONFIGURACIÓN GENERAL
# ============================================================

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

# Variantes reconocibles en títulos y nombres de canales.
ALIASES_CREADORES = {
    "Westcol": ["westcol", "west clips", "westclips"],
    "MrStivenTC": [
        "mrstiventc", "mr stiven", "mrstiven", "stiven tc"
    ],
    "Pelicanger": ["pelicanger"],
    "Samulx": ["samulx"],
    "Chanty": ["chanty"],
    "La Sapa": ["la sapa", "lasapa"],
    "Lonche de Huevito": [
        "lonche de huevito", "lonchewey", "lonche"
    ],
    "Rey de la City": [
        "reydelacity", "rey de la city", "elreywiththeclips"
    ],
}

CABECERAS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 Chrome/130 Safari/537.36"
    )
}


# ============================================================
# LIMPIEZA Y DETECCIÓN DE CREADORES
# ============================================================

def limpiar(texto):
    return re.sub(
        r"\s+", " ", html.unescape(str(texto or ""))
    ).strip()


def normalizar(texto):
    return re.sub(
        r"[^a-z0-9]", "", limpiar(texto).lower()
    )


def detectar_creador(video):
    titulo = video.get("titulo", "")
    canal = video.get("canal", "")

    titulo_normalizado = normalizar(titulo)
    canal_normalizado = normalizar(canal)

    # Primero se evalúa el título, que es más útil para comprobar
    # que el contenido realmente trata del streamer.
    for creador, alias in ALIASES_CREADORES.items():
        for nombre in alias:
            clave = normalizar(nombre)

            if clave and clave in titulo_normalizado:
                return creador

    # El canal sirve como segunda señal.
    for creador, alias in ALIASES_CREADORES.items():
        for nombre in alias:
            clave = normalizar(nombre)

            if clave and clave in canal_normalizado:
                return creador

    return None


def es_relevante(video, creador_busqueda):
    detectado = detectar_creador(video)

    if creador_busqueda == "Emergentes Colombia":
        return detectado is not None

    return detectado == creador_busqueda


# ============================================================
# FECHAS
# ============================================================

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


# ============================================================
# BÚSQUEDA GRATUITA EN YOUTUBE MEDIANTE YT-DLP
# ============================================================

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
        f"ytsearch{max_items}:{consulta}",
    ]

    proceso = subprocess.run(
        comando,
        capture_output=True,
        text=True,
        timeout=90,
    )

    salida = (proceso.stdout or "").strip()
    error = limpiar((proceso.stderr or "")[-1000:])

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
            "titulo": limpiar(
                video.get("title") or "Video sin título"
            ),
            "url": enlace,
            "canal": limpiar(
                video.get("channel")
                or video.get("uploader")
                or video.get("channel_id")
                or "Canal no identificado"
            ),
            "fecha": fecha,
            "creador": "",
            "fuente": "YouTube / yt-dlp",
        })

    print(
        f"  Fechas no verificables: {sin_fecha}; "
        f"fuera de 48 h: {fuera_ventana}; "
        f"válidos por fecha: {len(resultados)}"
    )

    if error and not resultados:
        print(f"  Aviso de yt-dlp: {error}")

    return resultados


def buscar_youtube(
    consulta,
    max_items=MAX_ITEMS_BUSQUEDA
):
    try:
        return ejecutar_busqueda_youtube(
            consulta, max_items
        )
    except subprocess.TimeoutExpired:
        print(f"  Tiempo agotado buscando: {consulta}")
    except Exception as error:
        print(f"  Error buscando '{consulta}': {error}")

    return []


# ============================================================
# RECOPILACIÓN Y FILTRADO DE CLIPS
# ============================================================

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

    for indice, (creador, consulta) in enumerate(
        consultas, 1
    ):
        print(f"[{indice}/{total}] Buscando: {consulta}")

        videos = buscar_youtube(consulta)

        for video in videos:
            detectado = detectar_creador(video)

            if not es_relevante(video, creador):
                print(
                    "  DESCARTADO por falta de coincidencia: "
                    f"{video['titulo']} | {video['canal']}"
                )
                continue

            # Etiquetar con el creador detectado para aplicar
            # correctamente los límites por persona.
            video["creador"] = detectado or creador
            encontrados.append(video)

    unicos = {}

    for video in encontrados:
        clave = video["url"].split("&", 1)[0].rstrip("/")

        if clave not in unicos:
            unicos[clave] = video

    print(
        f"Clips después de eliminar duplicados: "
        f"{len(unicos)}"
    )

    return list(unicos.values())


def seleccionar_clips(videos):
    videos.sort(
        key=lambda video: video["fecha"],
        reverse=True
    )

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


# ============================================================
# NOTICIAS: SECCIÓN INDEPENDIENTE DE LOS CLIPS
# ============================================================

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
                    fecha = fecha.replace(
                        tzinfo=timezone.utc
                    )

                fecha = fecha.astimezone(COLOMBIA)

            except (
                ValueError,
                TypeError,
                OverflowError
            ):
                fecha = None

            if (
                titulo
                and enlace
                and dentro_de_ventana(fecha)
            ):
                resultados.append({
                    "titulo": titulo,
                    "url": enlace,
                    "fecha": fecha,
                    "creador": "",
                    "fuente": "Google News RSS",
                })

    except Exception as error:
        print(
            f"Error en Google News ({consulta}): {error}"
        )

    return resultados


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
        conteo[detectado] = (
            conteo.get(detectado, 0) + 1
        )

        if len(elegidas) >= MAX_NOTICIAS:
            break

    return elegidas


# ============================================================
# GENERACIÓN DEL INFORME MARKDOWN
# ============================================================

def escribir_informe(clips, noticias):
    CARPETA.mkdir(
        parents=True,
        exist_ok=True
    )

    lineas = [
        "# Radar automático de creadores y clips",
        "",
        (
            f"Actualizado: "
            f"{AHORA.strftime('%d/%m/%Y %I:%M %p')} "
            "(hora de Colombia)"
        ),
        "",
        "Ventana objetivo: últimas 48 horas.",
        f"Clips candidatos encontrados: {len(clips)}.",
        f"Noticias recientes encontradas: {len(noticias)}.",
        "",
        (
            "> Radar gratuito basado en metadatos públicos. "
            "Verifica los enlaces y los derechos antes de publicar."
        ),
        "",
        "## Clips y Shorts candidatos de YouTube",
        "",
    ]

    if clips:
        for video in clips:
            lineas.extend([
                f"### {video['titulo']}",
                f"- Creador detectado: {video['creador']}",
                f"- Canal que publicó: {video['canal']}",
                (
                    f"- Publicado: "
                    f"{video['fecha'].strftime('%d/%m/%Y %I:%M %p')}"
                ),
                f"- Fuente: {video['fuente']}",
                f"- Enlace directo: {video['url']}",
                "",
            ])
    else:
        lineas.extend([
            (
                "No se encontraron videos verificables "
                "dentro de las últimas 48 horas."
            ),
            "",
            (
                "Revisa los registros del workflow para ver "
                "los resultados brutos y los descartes."
            ),
            (
                "No se inventan resultados ni se asume que "
                "un video sin fecha sea reciente."
            ),
            "",
        ])

    lineas.extend([
        "## Noticias y contexto (no son necesariamente clips)",
        "",
    ])

    if noticias:
        for noticia in noticias:
            fecha = noticia["fecha"].strftime(
                "%d/%m/%Y %I:%M %p"
            )

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
        f"- Máximo total de clips: {MAX_RESULTADOS}.",
        f"- Máximo de Westcol: {MAX_WESTCOL}.",
        (
            f"- Máximo por otro creador: "
            f"{MAX_POR_CREADOR}."
        ),
        "- Ventana temporal: 48 horas.",
        "- Deduplicación por enlace.",
        "- Filtro de relevancia por título y canal.",
        "- Noticias separadas de los clips.",
        "- Búsquedas exploratorias de creadores emergentes.",
        "",
        "## Limitaciones",
        "",
        (
            "Los filtros por título y canal pueden descartar "
            "clips válidos si no mencionan al creador."
        ),
        (
            "La búsqueda pública puede fallar o no devolver "
            "fechas verificables. No garantiza cobertura completa "
            "de Kick o TikTok."
        ),
        (
            "No descargues ni republices videos ajenos sin permiso. "
            "Añade comentario, análisis o contexto original y "
            "revisa las políticas de monetización de cada plataforma."
        ),
        "",
    ])

    SALIDA.write_text(
        "\n".join(lineas),
        encoding="utf-8"
    )

    print(
        f"Informe guardado: {SALIDA} | "
        f"clips: {len(clips)} | noticias: {len(noticias)}"
    )


# ============================================================
# INICIO
# ============================================================

def main():
    print("=" * 55)
    print("RADAR GRATUITO DE CREADORES")
    print(
        f"Hora Colombia: "
        f"{AHORA.strftime('%d/%m/%Y %I:%M %p')}"
    )
    print(
        f"Ventana desde: "
        f"{LIMITE.strftime('%d/%m/%Y %I:%M %p')}"
    )
    print("=" * 55)

    clips = seleccionar_clips(
        recopilar_clips()
    )

    noticias = recopilar_noticias()

    escribir_informe(
        clips,
        noticias
    )


if __name__ == "__main__":
    main()
