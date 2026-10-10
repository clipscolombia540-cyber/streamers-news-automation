
import html
import json
import re
import subprocess
import sys
import unicodedata
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

import requests

# ============================================================
# CONFIGURACIÓN GENERAL
# ============================================================

COLOMBIA = timezone(timedelta(hours=-5))
AHORA = datetime.now(COLOMBIA)
LIMITE = AHORA - timedelta(hours=48)

MAX_RESULTADOS = 25
MAX_WESTCOL = 2
MAX_POR_CREADOR = 3
MAX_POR_EMERGENTE = 2
MAX_NOTICIAS = 15
MAX_ITEMS_BUSQUEDA = 8

CARPETA = Path("borradores")
SALIDA = CARPETA / "radar_creadores.md"

# Prioridad 1: creadores principales.
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

# Prioridad 2: búsqueda abierta de streamers emergentes.
EMERGENTES = [
    "streamer colombiano Kick",
    "streamer colombiano viral",
    "clips streamers Colombia",
    "streamer colombiano directo",
    "clips Kick Colombia",
]

# Prioridad 3: influencers de respaldo.
# Solo se buscan si los clips principales y emergentes
# no completan el cupo de 25.
INFLUENCERS = [
    "JuanDa",
    "El Mindo",
    "Ami Rodríguez",
    "Tulio Recomienda",
    "La Segura",
    "Los de Ñam",
]

ALIASES_CREADORES = {
    "Westcol": ["westcol", "west clips", "westclips"],
    "MrStivenTC": ["mrstiventc", "mr stiven", "mrstiven", "stiven tc"],
    "Pelicanger": ["pelicanger"],
    "Samulx": ["samulx"],
    "Chanty": ["chanty"],
    "La Sapa": ["la sapa", "lasapa"],
    "Lonche de Huevito": ["lonche de huevito", "lonchewey", "lonche"],
    "Rey de la City": ["reydelacity", "rey de la city", "elreywiththeclips"],
}

ALIASES_INFLUENCERS = {
    "JuanDa": ["juanda", "juan da"],
    "El Mindo": ["el mindo", "elmindo"],
    "Ami Rodríguez": ["ami rodriguez", "amirodriguez"],
    "Tulio Recomienda": ["tulio recomienda", "tuliorecomienda"],
    "La Segura": ["la segura", "lasegura"],
    "Los de Ñam": ["los de ñam", "los de nam", "losdenam"],
}

CABECERAS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 Chrome/130 Safari/537.36"
    )
}


# ============================================================
# LIMPIEZA Y DETECCIÓN
# ============================================================

def limpiar(texto):
    return re.sub(r"\s+", " ", html.unescape(str(texto or ""))).strip()


def normalizar(texto):
    texto = unicodedata.normalize("NFKD", limpiar(texto).lower())
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]", "", texto)


def detectar_en_alias(video, grupos):
    titulo = normalizar(video.get("titulo", ""))
    canal = normalizar(video.get("canal", ""))

    # El título tiene prioridad para evitar atribuciones erróneas.
    for nombre, alias in grupos.items():
        for variante in alias:
            clave = normalizar(variante)
            if clave and clave in titulo:
                return nombre

    for nombre, alias in grupos.items():
        for variante in alias:
            clave = normalizar(variante)
            if clave and clave in canal:
                return nombre

    return None


def detectar_creador(video):
    return detectar_en_alias(video, ALIASES_CREADORES)


def detectar_influencer(video):
    return detectar_en_alias(video, ALIASES_INFLUENCERS)


def es_relevante_principal(video, creador):
    return detectar_creador(video) == creador


def es_relevante_influencer(video, influencer):
    return detectar_influencer(video) == influencer


def parece_contenido_de_creadores(video):
    """
    Filtro amplio para búsquedas de emergentes.
    No exige que el canal ya sea conocido.
    Como la búsqueda es abierta, estos resultados se etiquetan
    para revisión manual y no se presentan como verificados.
    """
    texto = normalizar(
        f"{video.get('titulo', '')} {video.get('canal', '')}"
    )

    palabras = [
        "streamer", "stream", "kick", "twitch", "directo",
        "directos", "clip", "clips", "viral", "gaming",
        "gameplay", "colombia", "colombiano", "colombiana",
        "reaccion", "reacciones", "podcast", "creador",
        "creadores", "influencer", "influencers", "shorts",
    ]

    return any(normalizar(palabra) in texto for palabra in palabras)


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
# BÚSQUEDA EN YOUTUBE
# ============================================================

def ejecutar_busqueda_youtube(consulta, max_items=MAX_ITEMS_BUSQUEDA):
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
            f"YouTube no devolvió resultados para '{consulta}'. "
            f"Código: {proceso.returncode}"
        )
        if error:
            print(f"Detalle: {error}")
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
        enlace = video.get("webpage_url") or video.get("original_url")

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
            "categoria": "",
            "fuente": "YouTube / yt-dlp",
        })

    print(
        f"  Resultados brutos: {len(videos)} | "
        f"sin fecha: {sin_fecha} | "
        f"fuera de 48 h: {fuera_ventana} | "
        f"válidos: {len(resultados)}"
    )

    if error and not resultados:
        print(f"Aviso yt-dlp: {error}")

    return resultados


def buscar_youtube(consulta):
    try:
        return ejecutar_busqueda_youtube(consulta)
    except subprocess.TimeoutExpired:
        print(f"Tiempo agotado buscando: {consulta}")
    except Exception as error:
        print(f"Error buscando '{consulta}': {error}")

    return []


# ============================================================
# RECOPILAR PRINCIPALES, EMERGENTES E INFLUENCERS
# ============================================================

def recopilar_principales():
    encontrados = []

    consultas = [
        (creador, f"{creador} clips")
        for creador in CREADORES
    ]
    consultas += [
        (creador, f"{creador} shorts")
        for creador in CREADORES
    ]

    for indice, (creador, consulta) in enumerate(consultas, 1):
        print(f"[Principales {indice}/{len(consultas)}] {consulta}")

        for video in buscar_youtube(consulta):
            detectado = detectar_creador(video)

            if not es_relevante_principal(video, creador):
                continue

            video["creador"] = detectado
            video["categoria"] = "Principal"
            encontrados.append(video)

    return encontrados


def recopilar_emergentes():
    encontrados = []

    for indice, consulta in enumerate(EMERGENTES, 1):
        print(f"[Emergentes {indice}/{len(EMERGENTES)}] {consulta}")

        for video in buscar_youtube(consulta):
            detectado = detectar_creador(video)

            # Si es un creador principal, no lo duplicamos como emergente.
            if detectado:
                continue

            if not parece_contenido_de_creadores(video):
                print(
                    f"  Emergente descartado por relevancia: "
                    f"{video['titulo']} | {video['canal']}"
                )
                continue

            canal = video["canal"] or "Canal no identificado"
            video["creador"] = f"Emergente: {canal}"
            video["categoria"] = "Emergente por verificar"
            encontrados.append(video)

    return encontrados


def recopilar_influencers():
    encontrados = []

    consultas = []
    for influencer in INFLUENCERS:
        consultas.append((influencer, f"{influencer} video"))
        consultas.append((influencer, f"{influencer} shorts"))

    for indice, (influencer, consulta) in enumerate(consultas, 1):
        print(f"[Influencers {indice}/{len(consultas)}] {consulta}")

        for video in buscar_youtube(consulta):
            detectado = detectar_influencer(video)

            if not es_relevante_influencer(video, influencer):
                continue

            video["creador"] = detectado
            video["categoria"] = "Influencer de respaldo"
            encontrados.append(video)

    return encontrados


def quitar_duplicados(videos):
    unicos = {}

    for video in videos:
        url = video.get("url", "")
        clave = url.split("&", 1)[0].rstrip("/")

        if clave and clave not in unicos:
            unicos[clave] = video

    return list(unicos.values())


def recopilar_clips():
    # Siempre se recopilan principales y emergentes primero.
    principales = recopilar_principales()
    emergentes = recopilar_emergentes()

    base = quitar_duplicados(principales + emergentes)
    seleccion_base = seleccionar_clips(base)

    # Solo se buscan influencers si los resultados anteriores
    # no llenan el cupo total.
    if len(seleccion_base) < MAX_RESULTADOS:
        faltantes = MAX_RESULTADOS - len(seleccion_base)
        print(
            f"Solo hay {len(seleccion_base)} clips priorizados. "
            f"Buscando influencers para cubrir hasta {faltantes} espacios."
        )

        influencers = recopilar_influencers()
        combinados = quitar_duplicados(base + influencers)
        return seleccionar_clips(combinados)

    return seleccion_base


# ============================================================
# SELECCIÓN POR PRIORIDAD Y LÍMITES
# ============================================================

def seleccionar_clips(videos):
    prioridad = {
        "Principal": 0,
        "Emergente por verificar": 1,
        "Influencer de respaldo": 2,
    }

    videos = sorted(
        videos,
        key=lambda video: (
            prioridad.get(video.get("categoria", ""), 9),
            -video["fecha"].timestamp(),
        ),
    )

    seleccionados = []
    conteo = {}

    for video in videos:
        if len(seleccionados) >= MAX_RESULTADOS:
            break

        creador = video.get("creador") or "Sin identificar"
        categoria = video.get("categoria", "")

        if creador.lower() == "westcol":
            limite = MAX_WESTCOL
        elif categoria == "Emergente por verificar":
            limite = MAX_POR_EMERGENTE
        else:
            limite = MAX_POR_CREADOR

        if conteo.get(creador, 0) >= limite:
            continue

        seleccionados.append(video)
        conteo[creador] = conteo.get(creador, 0) + 1

    return seleccionados


# ============================================================
# NOTICIAS DE GOOGLE NEWS RSS
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
                    fecha = fecha.replace(tzinfo=timezone.utc)
                fecha = fecha.astimezone(COLOMBIA)
            except (ValueError, TypeError, OverflowError):
                fecha = None

            if titulo and enlace and dentro_de_ventana(fecha):
                resultados.append({
                    "titulo": titulo,
                    "url": enlace,
                    "fecha": fecha,
                    "fuente": "Google News RSS",
                })

    except Exception as error:
        print(f"Error en Google News ({consulta}): {error}")

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
    consultas += [
        f'"{influencer}" creador contenido'
        for influencer in INFLUENCERS
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
        titulo_normalizado = normalizar(noticia["titulo"])

        detectado = next(
            (
                creador
                for creador, alias in {
                    **ALIASES_CREADORES,
                    **ALIASES_INFLUENCERS,
                }.items()
                if any(
                    normalizar(nombre) in titulo_normalizado
                    for nombre in alias
                )
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


# ============================================================
# GENERACIÓN DEL INFORME
# ============================================================

def escribir_informe(clips, noticias):
    CARPETA.mkdir(parents=True, exist_ok=True)

    lineas = [
        "# Radar automático de creadores y clips",
        "",
        (
            f"Actualizado: {AHORA.strftime('%d/%m/%Y %I:%M %p')} "
            "(hora de Colombia)"
        ),
        "",
        "Ventana objetivo: últimas 48 horas.",
        f"Clips incluidos: {len(clips)}.",
        f"Noticias recientes: {len(noticias)}.",
        "",
        (
            "> Radar basado en metadatos públicos. Verifica cada enlace "
            "y los derechos antes de publicar."
        ),
        "",
        "## Clips y Shorts candidatos de YouTube",
        "",
    ]

    if clips:
        for video in clips:
            lineas.extend([
                f"### {video['titulo']}",
                f"- Categoría: {video.get('categoria', 'Sin categoría')}",
                f"- Creador/canal detectado: {video['creador']}",
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
            "No se encontraron videos con fechas verificables "
            "dentro de las últimas 48 horas.",
            "",
            "Esto no demuestra que no existan videos nuevos.",
            "Revisa los registros del workflow para conocer los descartes.",
            "",
        ])

    lineas.extend([
        "## Noticias y contexto",
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
        "## Creadores principales vigilados",
        "",
        ", ".join(CREADORES),
        "",
        "## Influencers de respaldo",
        "",
        ", ".join(INFLUENCERS),
        "",
        "## Búsquedas de emergentes",
        "",
        ", ".join(EMERGENTES),
        "",
        "## Criterios",
        "",
        f"- Máximo total: {MAX_RESULTADOS} clips.",
        f"- Máximo de Westcol: {MAX_WESTCOL}.",
        f"- Máximo por creador identificado: {MAX_POR_CREADOR}.",
        f"- Máximo por canal emergente: {MAX_POR_EMERGENTE}.",
        "- Prioridad: principales, emergentes y luego influencers.",
        "- Los emergentes se marcan para revisión manual.",
        "- Ventana temporal: 48 horas.",
        "- Deduplicación por enlace.",
        "- Noticias separadas de los clips.",
        "",
        "## Limitaciones",
        "",
        (
            "Las búsquedas públicas no garantizan cobertura completa "
            "de YouTube, Kick o TikTok. Los canales emergentes necesitan "
            "verificación manual."
        ),
        (
            "No descargues ni republices videos ajenos sin permiso. "
            "Añade comentario, análisis o contexto original y revisa "
            "las políticas de monetización de cada plataforma."
        ),
        "",
    ])

    SALIDA.write_text("\n".join(lineas), encoding="utf-8")

    print(
        f"Informe guardado: {SALIDA} | "
        f"clips: {len(clips)} | noticias: {len(noticias)}"
    )


# ============================================================
# INICIO
# ============================================================

def main():
    print("=" * 60)
    print("RADAR GRATUITO DE CREADORES")
    print(f"Hora Colombia: {AHORA.strftime('%d/%m/%Y %I:%M %p')}")
    print(f"Ventana desde: {LIMITE.strftime('%d/%m/%Y %I:%M %p')}")
    print("=" * 60)

    clips = recopilar_clips()
    noticias = recopilar_noticias()
    escribir_informe(clips, noticias)


if __name__ == "__main__":
    main()
