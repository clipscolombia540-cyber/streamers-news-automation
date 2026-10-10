
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
# CONFIGURACION GENERAL
# ============================================================

COLOMBIA = timezone(timedelta(hours=-5))
AHORA = datetime.now(COLOMBIA)
LIMITE = AHORA - timedelta(hours=48)

# Cupo amplio para que no se quede el radar en pocos clips.
MAX_RESULTADOS = 60
MAX_WESTCOL = 8
MAX_POR_CREADOR = 8
MAX_POR_EMERGENTE = 5
MAX_NOTICIAS = 15
MAX_ITEMS_BUSQUEDA = 25
MAX_POR_CUENTA_CLIPS = 8

CARPETA = Path("borradores")
SALIDA = CARPETA / "radar_creadores.md"
CATALOGO_SERIES = CARPETA / "series_detectadas.json"

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

# Busquedas abiertas para descubrir creadores que aun no conocemos.
EMERGENTES = [
    "clips streamers colombianos ultimas horas",
    "momentos streamers colombianos Kick",
    "mejores clips Kick Colombia",
    "streamer colombiano viral directo",
    "recortes directos streamers Colombia",
    "clips twitch Colombia streamer",
    "streamer emergente colombiano",
    "clips de nuevos streamers colombianos",
]

# Cuentas y canales que publican clips.
# Se separan del streamer original para que no compartan su limite.
CUENTAS_CLIPS = [
    "Westclips",
    "West Clips Colombia",
    "Clips de streamers Colombia",
    "Clips Kick Colombia",
    "Clips Colombia",
    "Momentos de Streamers",
    "Recortes de Streamers",
    "Clips de Kick Colombia",
]

INFLUENCERS = [
    "JuanDa",
    "El Mindo",
    "Ami Rodriguez",
    "Tulio Recomienda",
    "La Segura",
    "Los de Nam",
    "La Liendra",
    "Yeferson Cossio",
    "Dani Duke",
    "Luisa Fernanda W",
    "Pautips",
    "Aida Victoria Merlano",
    "Kika Nieto",
    "Yina Calderón",
]


ALIASES_CREADORES = {
    "Westcol": ["westcol"],
    "MrStivenTC": ["mrstiventc", "mr stiven", "mrstiven", "stiven tc"],
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

ALIASES_INFLUENCERS = {
    "JuanDa": ["juanda", "juan da"],
    "El Mindo": ["el mindo", "elmindo"],
    "Ami Rodriguez": ["ami rodriguez", "amirodriguez"],
    "Tulio Recomienda": ["tulio recomienda", "tuliorecomienda"],
    "La Segura": ["la segura", "lasegura"],
    "Los de Nam": ["los de nam", "losdenam", "los de ñam"],
    "La Liendra": ["la liendra", "laliendra"],
    "Yeferson Cossio": ["yeferson cossio", "yefersoncossio"],
    "Dani Duke": ["dani duke", "daniduke"],
    "Luisa Fernanda W": ["luisa fernanda w", "luisafw", "luisa fernanda"],
    "Pautips": ["pautips", "paula galindo"],
    "Aida Victoria Merlano": ["aida victoria", "aidavictoria", "aida victoria merlano"],
    "Kika Nieto": ["kika nieto", "kikanieto"],
    "Yina Calderón": ["yina calderon", "yinacalderon", "yina"],

}

# Series, eventos y retos de streamers, especialmente Minecraft.
# Se rastrean como noticias de creadores, no como realities de television.
PROGRAMAS = [
    "DEDsafio Minecraft",
    "series de Minecraft de streamers",
    "eventos de Minecraft de creadores",
    "eventos de streamers colombianos",
]

ALIASES_PROGRAMAS = {
    "DEDsafio Minecraft": [
        "dedsafio minecraft", "dedsafio", "ded'safio", "ded safio",
        "dedsafio mc", "ded minecraft",
    ],
    "Series de Minecraft de streamers": [
        "serie de minecraft", "series de minecraft", "minecraft streamer",
        "minecraft con streamers", "minecraft de streamers",
    ],
    "Eventos de Minecraft de creadores": [
        "evento de minecraft", "eventos de minecraft", "minecraft extremo",
        "minecraft hardcore", "minecraft con creadores",
    ],
    "Eventos de streamers colombianos": [
        "evento de streamers colombianos", "streamers colombianos",
        "creadores colombianos streaming",
    ],
}

ALIASES_CUENTAS_CLIPS = [
    "westclips",
    "west clips",
    "westclip",
    "clips de streamers",
    "clips kick",
    "streamer clips",
    "clips colombia",
    "clip colombia",
    "clips de kick",
    "recortes de streamers",
    "momentos de streamers",
    "streamer colombiano clips",
    "clips colombianos",
    "clips de colombia",
]

CABECERAS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 Chrome/130 Safari/537.36"
    )
}


# ============================================================
# LIMPIEZA Y DETECCION
# ============================================================

def limpiar(texto):
    return re.sub(
        r"\s+", " ", html.unescape(str(texto or ""))
    ).strip()


def normalizar(texto):
    texto = unicodedata.normalize("NFKD", limpiar(texto).lower())
    texto = "".join(
        c for c in texto if not unicodedata.combining(c)
    )
    return re.sub(r"[^a-z0-9]", "", texto)

# Heurística conservadora basada únicamente en el título. No demuestra
# el idioma del audio; evita candidatos cuyo título parece claramente inglés.
PALABRAS_ES = {
    "de", "la", "el", "en", "que", "por", "para", "con", "una", "un",
    "los", "las", "del", "como", "pero", "porque", "esto", "esta",
    "este", "asi", "cuando", "donde", "quien", "reacciona", "reaccion",
    "colombia", "colombiano", "colombiana", "directo", "streamer",
    "rompio", "dice", "dijo", "habla", "cuenta", "nuevo", "nueva",
}
PALABRAS_EN = {
    "the", "and", "with", "when", "what", "why", "how", "about", "wants",
    "want", "take", "takes", "my", "his", "her", "their", "new", "shows",
    "show", "talks", "talk", "gave", "gets", "got", "into", "from", "this",
    "that", "they", "them", "she", "he", "are", "was", "were", "is", "it's",
    "its", "official", "video", "explained", "story", "reacts", "reaction",
    "girlfriend", "brother", "incredible", "everything", "explanation",
}

def titulo_probablemente_en_ingles(titulo):
    """Detecta títulos claramente ingleses; no infiere el idioma del audio."""
    palabras = re.findall(r"[a-záéíóúüñ]+", limpiar(titulo).lower())
    if len(palabras) < 3:
        return False
    espanolas = sum(1 for p in palabras if normalizar(p) in PALABRAS_ES)
    inglesas = sum(1 for p in palabras if normalizar(p) in PALABRAS_EN)
    # Evita descartar por dos palabras ambiguas; exige tres señales inglesas.
    return inglesas >= 3 and espanolas == 0


def detectar_en_alias(video, grupos):
    titulo = normalizar(video.get("titulo", ""))
    canal = normalizar(video.get("canal", ""))

    # Primero se busca en el titulo.
    for nombre, alias in grupos.items():
        for variante in alias:
            clave = normalizar(variante)
            if clave and clave in titulo:
                return nombre

    # Despues se busca en el canal.
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


def detectar_creador_relacionado(video):
    """Busca el creador mencionado en el título sin confundirlo con la cuenta publicadora."""
    solo_titulo = {"titulo": video.get("titulo", ""), "canal": ""}
    return (
        detectar_en_alias(solo_titulo, ALIASES_CREADORES)
        or detectar_en_alias(solo_titulo, ALIASES_INFLUENCERS)
    )


def es_cuenta_de_clips(video):
    canal = normalizar(video.get("canal", ""))
    titulo = normalizar(video.get("titulo", ""))

    # La cuenta publicadora tiene prioridad para clasificar clips.
    # Asi, un video de Westclips no consume el cupo de Westcol.
    for alias in ALIASES_CUENTAS_CLIPS:
        clave = normalizar(alias)
        if clave and clave in canal:
            return True

    # Algunas cuentas de clips tienen el nombre del streamer
    # en el canal, pero anuncian que son una cuenta de clips.
    palabras_clip = [
        "clips", "clip", "recortes", "momentos",
    ]
    if any(p in canal for p in palabras_clip):
        return True

    # En busquedas especificas, el titulo tambien puede identificar
    # una cuenta de clips, siempre que el canal indique que los publica.
    if "westclips" in titulo and any(
        p in canal for p in palabras_clip
    ):
        return True

    return False


def parece_contenido_de_creadores(video):
    """Acepta resultados con senales explicitas de streaming y contexto colombiano."""
    titulo = normalizar(video.get("titulo", ""))
    canal = normalizar(video.get("canal", ""))
    texto = "{} {}".format(titulo, canal)

    senales_stream = (
        "streamer", "streamers", "kick", "twitch", "directo",
        "directos", "stream", "clips", "clip", "recortes",
        "momentos de stream", "reaccion a stream",
    )
    senales_colombia = (
        "colombia", "colombiano", "colombiana", "colombianos",
        "colombianas", "colombian",
    )

    tiene_senal_stream = any(p in texto for p in senales_stream)
    tiene_contexto_colombiano = any(p in texto for p in senales_colombia)

    # Una busqueda de streamers colombianos puede devolver deportes o videojuegos
    # que solo mencionan Kick/stream. Exigimos que el resultado tambien muestre
    # una senal colombiana en el titulo o canal antes de etiquetarlo como emergente.
    return tiene_senal_stream and tiene_contexto_colombiano


def es_relevante_para_radar(video):
    """Evita aceptar cuentas de clips extranjeras sin relación con creadores vigilados."""
    return bool(
        detectar_creador(video)
        or detectar_influencer(video)
        or parece_contenido_de_creadores(video)
    )


def canal_parece_oficial(video, creador):
    """Descarta publicaciones del canal oficial al buscar recortes de terceros."""
    canal = normalizar(video.get("canal", ""))
    alias = ALIASES_CREADORES.get(creador, [normalizar(creador)])
    palabras_clip = ("clip", "clips", "recortes", "momentos", "fan", "fans")
    if any(p in canal for p in palabras_clip):
        return False
    return any(normalizar(a) == canal for a in alias if normalizar(a)) or any(
        normalizar(a) in canal and len(normalizar(a)) >= 5 for a in alias
    )

def clasificar_video(video, categoria_preferida=None):
    """
    Clasifica primero las cuentas de clips para no confundirlas
    con el streamer mencionado en el titulo.
    """
    if es_cuenta_de_clips(video):
        video["creador"] = "Cuenta de clips: {}".format(
            video.get("canal", "Canal no identificado")
        )
        video["categoria"] = "Cuenta de clips"
        return video

    creador = detectar_creador(video)
    if creador:
        video["creador"] = creador
        video["categoria"] = "Principal"
        return video

    influencer = detectar_influencer(video)
    if influencer:
        video["creador"] = influencer
        video["categoria"] = "Influencer de respaldo"
        return video

    canal = video.get("canal") or "Canal no identificado"
    video["creador"] = "Emergente: {}".format(canal)
    video["categoria"] = categoria_preferida or "Emergente por verificar"
    return video


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
# BUSQUEDA EN YOUTUBE
# ============================================================
# yt-dlp retiró ytsearchdate en versiones recientes. Usamos ytsearch
# y los filtros del radar descartan videos de más de 48 horas.

def ejecutar_busqueda_youtube(
    consulta, max_items=MAX_ITEMS_BUSQUEDA
):
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
        "ytsearch{}:{}".format(max_items, consulta),
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
            "YouTube no devolvio resultados para '{}'. Codigo: {}".format(
                consulta, proceso.returncode
            )
        )
        if error:
            print("Detalle: {}".format(error))
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

        # Se mantiene el filtro de 48 horas.
        # Si YouTube no proporciona una fecha verificable,
        # el resultado no se presenta como reciente.
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
            enlace = "https://www.youtube.com/watch?v={}".format(
                video_id
            )

        if not enlace:
            continue

        resultados.append({
            "titulo": limpiar(
                video.get("title") or "Video sin titulo"
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
            "categoria": "",
            "fuente": "YouTube / yt-dlp",
            # En busquedas planas estas metricas no siempre vienen disponibles.
            "vistas": video.get("view_count"),
            "likes": video.get("like_count"),
            "duracion_segundos": video.get("duration"),
        })

    print(
        "  Brutos: {} | sin fecha: {} | fuera de 48 h: {} | validos: {}".format(
            len(videos), sin_fecha, fuera_ventana, len(resultados)
        )
    )

    if error and not resultados:
        print("Aviso yt-dlp: {}".format(error))

    return resultados


def buscar_youtube(consulta):
    try:
        return ejecutar_busqueda_youtube(consulta)
    except subprocess.TimeoutExpired:
        print("Tiempo agotado buscando: {}".format(consulta))
    except Exception as error:
        print("Error buscando '{}': {}".format(consulta, error))

    return []


# ============================================================
# RECOPILACION DE TODAS LAS CATEGORIAS
# ============================================================

def recopilar_principales():
    """Busca recortes de terceros de creadores conocidos, no solo canales oficiales."""
    encontrados = []
    consultas = []
    # Consultas centradas en recortes publicados por terceros; se evita
    # gastar cupos en búsquedas demasiado generales de videos oficiales.
    formatos = (
        "clips en español",
        # Se priorizan consultas complementarias para reducir tiempo total.
        "shorts en español",
        "clip de terceros",
        "mejores clips",
        "recortes en español",
    )

    for creador in CREADORES:
        for formato in formatos:
            consultas.append((creador, "{} {}".format(creador, formato)))

    for indice, (creador, consulta) in enumerate(consultas, 1):
        print("[Clips de terceros {}/{}] {}".format(indice, len(consultas), consulta))

        for video in buscar_youtube(consulta):
            if es_cuenta_de_clips(video):
                detectado = detectar_creador(video)
                if detectado != creador:
                    print("  Cuenta de clips descartada por no mencionar a {}: {}".format(creador, video.get("titulo", "")))
                    continue
                video["creador"] = "Cuenta de clips: {}".format(video.get("canal", "Canal no identificado"))
                video["categoria"] = "Cuenta de clips"
                encontrados.append(video)
                continue

            detectado = detectar_creador(video)
            if detectado != creador:
                continue

            if canal_parece_oficial(video, creador):
                print("  Canal oficial omitido para priorizar terceros: {}".format(video.get("canal", "")))
                continue

            video["creador"] = detectado
            video["categoria"] = "Clip de terceros"
            encontrados.append(video)

    return encontrados

def recopilar_cuentas_clips():
    encontrados = []

    for indice, cuenta in enumerate(CUENTAS_CLIPS, 1):
        # Una consulta combinada por cuenta evita repetir búsquedas casi idénticas.
        consultas = [
            "{} clips shorts momentos en español Colombia".format(cuenta),
        ]

        for consulta in consultas:
            print(
                "[Cuentas de clips {}/{}] {}".format(
                    indice, len(CUENTAS_CLIPS), consulta
                )
            )

            for video in buscar_youtube(consulta):
                canal = normalizar(video.get("canal", ""))
                titulo = normalizar(video.get("titulo", ""))

                if not es_relevante_para_radar(video):
                    print("  Cuenta de clips descartada por falta de relación colombiana verificable: {}".format(video.get("titulo", "")))
                    continue

                # Evita etiquetar cualquier video del streamer original
                # como una cuenta de clips por el simple titulo.
                canal_indica_clips = (
                    any(
                        normalizar(alias) in canal
                        for alias in ALIASES_CUENTAS_CLIPS
                    )
                    or any(
                        palabra in canal
                        for palabra in ("clips", "clip", "recortes")
                    )
                )

                if not canal_indica_clips:
                    # En una consulta exacta de una cuenta de clips,
                    # aceptamos el resultado solo si el titulo o canal
                    # mantiene una relacion clara con esa cuenta.
                    clave_cuenta = normalizar(cuenta)
                    if clave_cuenta not in canal and clave_cuenta not in titulo:
                        continue

                video["creador"] = "Cuenta de clips: {}".format(
                    video["canal"]
                )
                video["categoria"] = "Cuenta de clips"
                encontrados.append(video)

    return encontrados


def recopilar_emergentes():
    encontrados = []

    for indice, consulta in enumerate(EMERGENTES, 1):
        print(
            "[Emergentes {}/{}] {}".format(
                indice, len(EMERGENTES), consulta
            )
        )

        for video in buscar_youtube(consulta):
            if es_cuenta_de_clips(video):
                if not es_relevante_para_radar(video):
                    print("  Clip descartado por falta de relación colombiana verificable: {}".format(video.get("titulo", "")))
                    continue
                video["creador"] = "Cuenta de clips: {}".format(
                    video["canal"]
                )
                video["categoria"] = "Cuenta de clips"
                encontrados.append(video)
                continue

            # Si es un creador conocido, no lo duplicamos como emergente.
            if detectar_creador(video):
                continue

            if not parece_contenido_de_creadores(video):
                print(
                    "  Emergente descartado por relevancia: {} | {}".format(
                        video["titulo"], video["canal"]
                    )
                )
                continue

            canal = video["canal"] or "Canal no identificado"
            video["creador"] = "Emergente: {}".format(canal)
            video["categoria"] = "Emergente por verificar"
            encontrados.append(video)

    return encontrados


def recopilar_influencers():
    encontrados = []
    consultas = []

    for influencer in INFLUENCERS:
        consultas.append((influencer, "{} clips en español".format(influencer)))
        consultas.append((influencer, "{} momentos en español".format(influencer)))
        consultas.append((influencer, "{} shorts en español".format(influencer)))

    for indice, (influencer, consulta) in enumerate(consultas, 1):
        print(
            "[Influencers {}/{}] {}".format(
                indice, len(consultas), consulta
            )
        )

        for video in buscar_youtube(consulta):
            if es_cuenta_de_clips(video):
                if not es_relevante_para_radar(video):
                    print("  Clip de influencer descartado por falta de relación verificable: {}".format(video.get("titulo", "")))
                    continue
                video["creador"] = "Cuenta de clips: {}".format(
                    video["canal"]
                )
                video["categoria"] = "Cuenta de clips"
                encontrados.append(video)
                continue

            detectado = detectar_influencer(video)
            if detectado != influencer:
                continue

            video["creador"] = detectado
            video["categoria"] = "Influencer de respaldo"
            encontrados.append(video)

    return encontrados


# ============================================================
# DEDUPLICACION Y SELECCION
# ============================================================

def quitar_duplicados(videos):
    unicos = {}

    for video in videos:
        url = video.get("url", "")
        clave = url.split("&", 1)[0].rstrip("/")

        if clave and clave not in unicos:
            unicos[clave] = video

    return list(unicos.values())


def puntaje_tendencia(video):
    """Puntaje heurístico de interés; no equivale a vistas ni a una tendencia oficial."""
    titulo = normalizar(video.get("titulo", ""))
    puntos = 0
    senales_fuertes = (
        "viral", "se hizo viral", "tendencia", "momento epico",
        "momento historico", "nadie esperaba", "final inesperado",
        "reaccion viral", "mejores momentos", "record",
    )
    senales_medias = (
        "reaccion", "muertes", "muerte", "final", "ganador",
        "ganadora", "reto", "desafio", "dedsafio", "hardcore",
        "sorpresa", "traicion", "pelea", "troleo", "fails",
        "fails", "clip", "clips",
    )
    puntos += 3 * sum(1 for senal in senales_fuertes if normalizar(senal) in titulo)
    puntos += sum(1 for senal in senales_medias if normalizar(senal) in titulo)

    # Las metricas de plataforma pesan mas que las palabras del titulo cuando existen.
    # Escalas conservadoras para que una cifra aislada no domine todo el radar.
    try:
        vistas = int(video.get("vistas") or 0)
    except (TypeError, ValueError):
        vistas = 0
    try:
        likes = int(video.get("likes") or 0)
    except (TypeError, ValueError):
        likes = 0
    if vistas >= 100000:
        puntos += 8
    elif vistas >= 25000:
        puntos += 6
    elif vistas >= 5000:
        puntos += 4
    elif vistas >= 1000:
        puntos += 2
    if likes >= 10000:
        puntos += 4
    elif likes >= 1000:
        puntos += 2
    elif likes >= 100:
        puntos += 1

    # Premia ligeramente los clips vinculados a una serie/evento identificado.
    creador = normalizar(video.get("creador", ""))
    if any(senal in creador for senal in ("dedsafio", "serie", "evento", "minecraft")):
        puntos += 1
    return puntos


def seleccionar_clips(videos):
    prioridad = {
        "Clip de terceros": 0,
        "Cuenta de clips": 1,
        "Emergente por verificar": 2,
        "Influencer de respaldo": 3,
        "Principal": 4,
    }

    antes = len(videos)
    videos = [
        video for video in videos
        if not titulo_probablemente_en_ingles(video.get("titulo", ""))
    ]
    descartados_idioma = antes - len(videos)
    if descartados_idioma:
        print(
            "Candidatos descartados por título probablemente en inglés: {}".format(
                descartados_idioma
            )
        )

    videos = sorted(
        videos,
        key=lambda video: (
            prioridad.get(video.get("categoria", ""), 9),
            -puntaje_tendencia(video),
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
        elif categoria in ("Cuenta de clips", "Clip de terceros"):
            limite = MAX_POR_CUENTA_CLIPS
        elif categoria == "Emergente por verificar":
            limite = MAX_POR_EMERGENTE
        else:
            limite = MAX_POR_CREADOR

        if conteo.get(creador, 0) >= limite:
            continue

        seleccionados.append(video)
        conteo[creador] = conteo.get(creador, 0) + 1

    return seleccionados

def cargar_catalogo_series():
    """Lee el catalogo persistente de pistas de series/eventos descubiertos."""
    try:
        datos = json.loads(CATALOGO_SERIES.read_text(encoding="utf-8"))
        pistas = datos.get("series", [])
        return pistas if isinstance(pistas, list) else []
    except (OSError, json.JSONDecodeError, AttributeError):
        return []


def guardar_catalogo_series(series):
    """Guarda pistas nuevas para volver a buscarlas en ejecuciones futuras."""
    CARPETA.mkdir(parents=True, exist_ok=True)
    ordenadas = sorted(
        series.values(),
        key=lambda item: item.get("ultima_deteccion", ""),
        reverse=True,
    )[:100]
    CATALOGO_SERIES.write_text(
        json.dumps(
            {"actualizado": AHORA.isoformat(), "series": ordenadas},
            ensure_ascii=False,
            indent=2,
        ) + "\\n",
        encoding="utf-8",
    )


def inferir_pista_serie(video):
    """Extrae un nombre candidato; las pistas inferidas deben revisarse antes de tratarlas como serie confirmada."""
    titulo = limpiar(video.get("titulo", ""))
    normal = normalizar(titulo)
    if "dedsafio" in normal or "dedsafío" in titulo.lower() or "ded safio" in normal:
        return "DEDsafio Minecraft"

    # Formatos con nombre relativamente identificable.
    patrones = [
        r"([A-Z0-9][A-Za-z0-9'’_-]*(?:\s+[A-Z0-9][A-Za-z0-9'’_-]*){0,3}\s+SMP)\b",
        r"\b(Minecraft\s+(?:Extremo|Hardcore))\b",
        r"\b(?:serie|evento)\s+(?:de\s+)?Minecraft\s+(?:con|de)\s+([A-Za-z0-9'’_-]+(?:\s+[A-Za-z0-9'’_-]+){0,2})",
    ]
    for patron in patrones:
        coincidencia = re.search(patron, titulo, flags=re.IGNORECASE)
        if coincidencia:
            nombre = limpiar(coincidencia.group(1)).strip(" -|:")
            if len(nombre) >= 4 and normalizar(nombre) not in {
                "minecraft", "serie de minecraft", "evento de minecraft"
            }:
                return nombre

    # Si no se reconoce un nombre formal, conservar una pista del título
    # para búsquedas posteriores sin presentarla como serie confirmada.
    limpio = re.sub(
        r"(?i)\b(mejores momentos|momentos|reacciones?|muertes?|clips?|shorts?|highlights|resumen|español|espanol|parte \d+|día \d+|dia \d+)\b",
        " ",
        titulo,
    )
    limpio = re.sub(r"[|:—–_-]+", " ", limpio)
    limpio = limpiar(limpio)
    if len(limpio.split()) >= 2:
        return limpio[:100]
    return None


def recopilar_clips_programas():
    """Busca series conocidas, sigue pistas guardadas y descubre nuevas."""
    encontrados = []
    catalogo = {
        normalizar(item.get("nombre", "")): item
        for item in cargar_catalogo_series()
        if isinstance(item, dict) and item.get("nombre")
    }
    consultas = [
        "DEDSAFIO Minecraft clips español",
        "DEDSAFIO 4 mejores momentos",
        "DEDSAFIO Minecraft muertes clips",
        "DEDSAFIO Minecraft reacciones clips",
        "clips DEDSAFIO Westcol Spreen",
        "clips series Minecraft streamers español",
        "momentos eventos Minecraft creadores clips",
        "nueva serie Minecraft streamers clips español",
        "nueva serie Minecraft creadores mejores momentos",
        "nuevo evento Minecraft streamers clips",
        "clips nueva serie de streamers español",
        "nuevas series de streamers colombianos clips",
        "mejores momentos serie Minecraft reciente",
        "clips eventos streamers español últimas horas",
        "nueva serie de creadores de contenido clips",
    ]

    # Reutilizar pistas de ejecuciones anteriores para buscar más clips del mismo tema.
    pistas_previas = sorted(
        catalogo.values(),
        key=lambda item: item.get("ultima_deteccion", ""),
        reverse=True,
    )[:4]
    for pista in pistas_previas:
        nombre = limpiar(pista.get("nombre", ""))
        if nombre and normalizar(nombre) != normalizar("DEDsafio Minecraft"):
            consultas.append('"{}" clips'.format(nombre[:90]))

    senales_clip = (
        "clip", "clips", "short", "shorts", "momento", "momentos",
        "muerte", "muertes", "reaccion", "reacciones", "resumen",
        "mejores", "highlights", "limbo", "bossfight",
    )
    for consulta in dict.fromkeys(consultas):
        print("[Series y eventos / descubrimiento] {}".format(consulta))
        for video in buscar_youtube(consulta):
            titulo = normalizar(video.get("titulo", ""))
            canal = normalizar(video.get("canal", ""))
            es_dedsafio = "dedsafio" in titulo or "dedsafio" in canal or "ded safio" in titulo
            es_minecraft = "minecraft" in titulo or "minecraft" in canal
            es_evento_o_serie = any(
                palabra in titulo or palabra in canal
                for palabra in (
                    "serie", "series", "evento", "eventos", "streamer",
                    "streamers", "creador", "creadores", "hardcore",
                    "extremo", "smp",
                )
            )
            es_clip = any(senal in titulo for senal in senales_clip) or any(
                palabra in canal for palabra in ("clips", "clip", "recortes", "momentos")
            )
            es_serie_minecraft = es_minecraft and (es_evento_o_serie or es_clip)
            es_serie_streamers = es_evento_o_serie and es_clip and any(
                palabra in titulo or palabra in canal
                for palabra in ("streamer", "streamers", "creador", "creadores", "colombia")
            )
            if not es_clip or not (es_dedsafio or es_serie_minecraft or es_serie_streamers):
                continue

            if es_dedsafio:
                nombre_pista = "DEDsafio Minecraft"
                video["creador"] = "Programa: DEDsafio Minecraft"
            else:
                nombre_pista = inferir_pista_serie(video)
                video["creador"] = (
                    "Series y eventos Minecraft" if es_serie_minecraft
                    else "Series y eventos de streamers"
                )
            video["categoria"] = "Clip de terceros"
            encontrados.append(video)

            if nombre_pista:
                clave = normalizar(nombre_pista)
                existente = catalogo.get(clave, {})
                enlaces = list(existente.get("enlaces", []))
                if video.get("url") and video["url"] not in enlaces:
                    enlaces.insert(0, video["url"])
                catalogo[clave] = {
                    "nombre": nombre_pista,
                    "tipo": "serie_o_tema_candidato",
                    "confirmada": bool(es_dedsafio or existente.get("confirmada", False)),
                    "primera_deteccion": existente.get("primera_deteccion", AHORA.isoformat()),
                    "ultima_deteccion": AHORA.isoformat(),
                    "canal_muestra": video.get("canal", ""),
                    "enlaces": enlaces[:5],
                }

    guardar_catalogo_series(catalogo)
    print("Pistas de series/eventos guardadas en catalogo: {}".format(len(catalogo)))
    return encontrados


def recopilar_clips():
    # Todas las categorias se buscan en cada ejecucion, incluidas series/eventos.
    # Los influencers ya no dependen de que falten resultados.
    principales = recopilar_principales()
    cuentas_clips = recopilar_cuentas_clips()
    programas = recopilar_clips_programas()
    emergentes = recopilar_emergentes()
    influencers = recopilar_influencers()

    combinados = quitar_duplicados(
        principales + cuentas_clips + programas + emergentes + influencers
    )

    print(
        "Candidatos unicos antes de limites: {}".format(
            len(combinados)
        )
    )

    seleccionados = seleccionar_clips(combinados)

    print(
        "Clips seleccionados para el informe: {}".format(
            len(seleccionados)
        )
    )

    return seleccionados


# ============================================================
# NOTICIAS DE GOOGLE NEWS RSS
# ============================================================

def buscar_noticias(consulta):
    parametros = {
        "q": "{} when:2d".format(consulta),
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
        print("Error en Google News ({}): {}".format(consulta, error))

    return resultados


def es_noticia_promocional(titulo):
    """Descarta titulares claramente publicitarios, no noticias personales o virales."""
    titulo_normalizado = normalizar(titulo)
    senales_comerciales = (
        "porkcolombia",
        "campana publicitaria",
        "publicidad de",
        "publicidad pagada",
        "anuncio publicitario",
        "contenido patrocinado",
        "patrocinado por",
        "patrocinio de",
        "embajador de marca",
        "alianza comercial",
        "receta patrocinada",
        "promocion de",
        "promociona la marca",
    )
    return any(
        normalizar(senal) in titulo_normalizado
        for senal in senales_comerciales
    )


def recopilar_noticias():
    consultas = [
        '"{}" streamer OR directo OR polemica'.format(creador)
        for creador in CREADORES
    ]

    consultas += [
        "streamer colombiano Kick viral",
        "creador de contenido colombiano streamer",
        "clips streamer Colombia viral",
    ]

    consultas += [
        '"{}" creador contenido'.format(influencer)
        for influencer in INFLUENCERS
    ]

    # Noticias recientes de series, retos y eventos de streamers; prioridad DEDsafio Minecraft.
    consultas_programas = []
    for programa in PROGRAMAS:
        consultas_programas.extend([
            '"{}" Colombia participantes'.format(programa),
            '"{}" eliminado OR eliminada OR eliminación'.format(programa),
            '"{}" polémica OR sorpresa OR noticia'.format(programa),
        ])
    consultas += consultas_programas

    candidatas = []

    for consulta in consultas:
        print("Google News: {}".format(consulta))
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
        if es_noticia_promocional(noticia["titulo"]):
            print("Noticia descartada por posible contenido promocional: {}".format(
                noticia["titulo"]
            ))
            continue

        titulo_normalizado = normalizar(noticia["titulo"])

        todos_alias = {
            **ALIASES_CREADORES,
            **ALIASES_INFLUENCERS,
        }

        detectado = next(
            (
                creador
                for creador, alias in todos_alias.items()
                if any(
                    normalizar(nombre) in titulo_normalizado
                    for nombre in alias
                )
            ),
            "Otros",
        )

        # Si no es una noticia sobre un creador conocido, comprobar programas.
        programa_detectado = next(
            (
                programa
                for programa, alias in ALIASES_PROGRAMAS.items()
                if any(normalizar(nombre) in titulo_normalizado for nombre in alias)
            ),
            None,
        )

        if detectado == "Otros" and programa_detectado:
            detectado = "Programa: {}".format(programa_detectado)
            noticia["tema"] = programa_detectado
        elif detectado != "Otros":
            noticia["tema"] = "Creadores"
        else:
            print("Noticia descartada por falta de creador o programa relevante: {}".format(
                noticia["titulo"]
            ))
            continue

        if conteo.get(detectado, 0) >= 2:
            continue

        elegidas.append(noticia)
        conteo[detectado] = conteo.get(detectado, 0) + 1

        if len(elegidas) >= MAX_NOTICIAS:
            break

    return elegidas


# ============================================================
# BORRADORES DE COPY PARA REVISION HUMANA
# ============================================================

def generar_borrador_copy(video):
    """Genera copy prudente a partir de metadatos, sin inventar hechos."""
    titulo = (video.get("titulo") or "Clip por revisar").strip()
    creador = (video.get("creador") or "").strip()
    if video.get("categoria") == "Cuenta de clips":
        creador = detectar_creador_relacionado(video) or creador
    if not creador or creador.lower() in ("otros", "sin identificar"):
        creador = (video.get("canal") or "este creador").strip()

    hashtags = [
        "#StreamersColombia",
        "#ClipsColombia",
        "#CreadoresColombianos",
        "#EnDirecto",
    ]
    categoria = video.get("categoria", "")
    if categoria == "Emergente por verificar":
        hashtags = [
            "#StreamerEmergente",
            "#StreamersColombia",
            "#ClipsColombia",
            "#GamingColombia",
        ]
    elif categoria == "Influencer de respaldo":
        hashtags = [
            "#InfluencersColombia",
            "#CreadoresColombianos",
            "#ClipsColombia",
        ]

    return {
        "gancho_a": "¿Ya habías visto este momento de {}? 👀".format(creador),
        "gancho_b": "Mira este fragmento y cuéntanos qué opinas 👇",
        "gancho_c": "Un momento para revisar del contenido de {}.".format(creador),
        "titulo": titulo[:100],
        "texto_pantalla": titulo[:70],
        "descripcion": (
            "Fragmento relacionado con {}. Revisa el contexto completo "
            "en la fuente original y deja tu opinión con respeto. "
            "Publicar solo si tienes permiso o autorización para usar el material."
        ).format(creador),
        "hashtags": " ".join(hashtags),
    }


# ============================================================
# GENERACION DEL INFORME
# ============================================================

def escribir_informe(clips, noticias):
    CARPETA.mkdir(parents=True, exist_ok=True)

    lineas = [
        "# Radar automatico de creadores y clips",
        "",
        "Actualizado: {} (hora de Colombia)".format(
            AHORA.strftime("%d/%m/%Y %I:%M %p")
        ),
        "",
        "Ventana objetivo: ultimas 48 horas.",
        "Clips incluidos: {}.".format(len(clips)),
        "Noticias recientes: {}.".format(len(noticias)),
        "Distribución por categoría: {}.".format(
            ", ".join(
                "{}: {}".format(categoria, cantidad)
                for categoria, cantidad in sorted(
                    __import__("collections").Counter(
                        video.get("categoria", "Sin categoria")
                        for video in clips
                    ).items()
                )
            ) or "sin clips"
        ),
        "",
        (
            "> Radar basado en metadatos publicos. Verifica cada enlace "
            "y los derechos antes de publicar."
        ),
        "",
        "## Clips y Shorts candidatos de YouTube",
        "",
    ]

    if clips:
        for video in clips:
            lineas.extend([
                "### {}".format(video["titulo"]),
                "- Categoria: {}".format(
                    video.get("categoria", "Sin categoria")
                ),
                "- Creador/canal detectado: {}".format(
                    video.get("creador", "Sin identificar")
                ),
                *(
                    ["- Creador relacionado en el título: {}".format(
                        detectar_creador_relacionado(video)
                    )]
                    if video.get("categoria") == "Cuenta de clips"
                    and detectar_creador_relacionado(video)
                    else []
                ),
                "- Canal que publico: {}".format(video["canal"]),
                "- Publicado: {}".format(
                    video["fecha"].strftime("%d/%m/%Y %I:%M %p")
                ),
                "- Fuente: {}".format(video["fuente"]),
                *(
                    ["- Vistas reportadas por YouTube: {}".format(
                        "{:,}".format(int(video["vistas"])).replace(",", ".")
                    )]
                    if video.get("vistas") is not None
                    and str(video.get("vistas")).isdigit()
                    else []
                ),
                *(
                    ["- Me gusta reportados: {}".format(
                        "{:,}".format(int(video["likes"])).replace(",", ".")
                    )]
                    if video.get("likes") is not None
                    and str(video.get("likes")).isdigit()
                    else []
                ),
                "- Puntaje heurístico de interés: {}".format(
                    puntaje_tendencia(video)
                ),
                "- Enlace directo: {}".format(video["url"]),
                "",
            ])
    else:
        lineas.extend([
            "No se encontraron videos con fechas verificables "
            "dentro de las ultimas 48 horas.",
            "",
            "Esto no demuestra que no existan videos nuevos.",
            "Revisa los registros del workflow para conocer los descartes.",
            "",
        ])

    lineas.extend([
        "## Borradores de copy para clips (revisar antes de publicar)",
        "",
        (
            "Los textos son propuestas iniciales basadas solo en el título y "
            "los metadatos. Verifica el contenido real, evita sacar frases "
            "de contexto y publica únicamente con derechos o permiso."
        ),
        "",
    ])

    if clips:
        for video in clips:
            copy = generar_borrador_copy(video)
            lineas.extend([
                "### {}".format(video["titulo"]),
                "- **Gancho A:** {}".format(copy["gancho_a"]),
                "- **Gancho B:** {}".format(copy["gancho_b"]),
                "- **Gancho C:** {}".format(copy["gancho_c"]),
                "- **Título sugerido:** {}".format(copy["titulo"]),
                "- **Texto en pantalla:** {}".format(copy["texto_pantalla"]),
                "- **Descripción:** {}".format(copy["descripcion"]),
                "- **Hashtags:** {}".format(copy["hashtags"]),
                "- **Fuente original:** {}".format(video.get("url", "")),
                "",
            ])
    else:
        lineas.extend([
            "No hay clips para generar borradores en esta ejecución.",
            "",
        ])

    lineas.extend([
        "## Noticias y contexto",
        "",
    ])

    if noticias:
        for noticia in noticias:
            fecha = noticia["fecha"].strftime("%d/%m/%Y %I:%M %p")
            etiqueta = noticia.get("tema", "Creadores")
            lineas.append(
                "- **[{}] {}** — {} — [Abrir fuente]({})".format(
                    etiqueta, noticia["titulo"], fecha, noticia["url"]
                )
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
        "## Cuentas de clips rastreadas",
        "",
        ", ".join(CUENTAS_CLIPS),
        "",
        "## Influencers rastreados",
        "",
        ", ".join(INFLUENCERS),
        "",
        "## Series y eventos de streamers rastreados",
        "",
        ", ".join(PROGRAMAS),
        "",
    ])

    series_catalogo = sorted(
        cargar_catalogo_series(),
        key=lambda item: item.get("ultima_deteccion", ""),
        reverse=True,
    )
    lineas.extend([
        "## Catalogo persistente de series y temas detectados",
        "",
        "Las pistas nuevas se guardan entre ejecuciones y se vuelven a buscar. Las inferidas por títulos son candidatas, no confirmaciones oficiales.",
        "",
    ])
    if series_catalogo:
        for pista in series_catalogo[:30]:
            estado = "confirmada" if pista.get("confirmada") else "candidata por revisar"
            lineas.append("- **{}** ({}) — última detección: {}".format(
                pista.get("nombre", "Tema sin nombre"),
                estado,
                pista.get("ultima_deteccion", "sin fecha")[:10],
            ))
            for enlace in pista.get("enlaces", [])[:2]:
                lineas.append("  - {}".format(enlace))
        lineas.append("")
    else:
        lineas.extend(["Todavía no hay pistas guardadas; se llenará al encontrar resultados útiles.", ""])

    lineas.extend([
        "## Busquedas de emergentes",
        "",
        ", ".join(EMERGENTES),
        "",
        "## Criterios",
        "",
        "- Maximo total: {} clips.".format(MAX_RESULTADOS),
        "- Maximo de Westcol: {}.".format(MAX_WESTCOL),
        "- Maximo por creador identificado: {}.".format(
            MAX_POR_CREADOR
        ),
        "- Maximo por cuenta de clips: {}.".format(
            MAX_POR_CUENTA_CLIPS
        ),
        "- Maximo por canal emergente: {}.".format(
            MAX_POR_EMERGENTE
        ),
        "- Prioridad de selección: clips de terceros primero, después cuentas de clips, emergentes e influencers; los canales oficiales quedan como respaldo.",
        "- Las búsquedas por creador usan consultas centradas en clips, Shorts y recortes para favorecer publicaciones de cuentas independientes.",
        "- La distribución por categoría permite comprobar en cada informe cuántos resultados son clips de terceros o cuentas de clips.",
        "- Filtro de emergentes: exige una senal de streaming y una referencia explicita a Colombia en el titulo o canal.",
        "- Se buscan todas las categorias en cada ejecucion.",
        "- Los emergentes se marcan para revision manual.",
        "- Idioma objetivo: español; las consultas priorizan videos, reacciones y momentos en español. El título original puede conservar palabras en otro idioma.",
        "- Ventana temporal: 48 horas.",
        "- Deduplicacion por enlace.",
        "- Noticias separadas de los clips.",
        "",
        "## Limitaciones",
        "",
        (
            "Las busquedas publicas no garantizan cobertura completa "
            "de YouTube, Kick o TikTok. El numero de resultados depende "
            "de lo que devuelva el buscador y de las fechas disponibles."
        ),
        (
            "No descargues ni republices videos ajenos sin permiso. "
            "Anade comentario, analisis o contexto original y revisa "
            "las politicas de monetizacion de cada plataforma."
        ),
        "",
    ])

    SALIDA.write_text("\n".join(lineas), encoding="utf-8")

    print(
        "Informe guardado: {} | clips: {} | noticias: {}".format(
            SALIDA, len(clips), len(noticias)
        )
    )


# ============================================================
# INICIO
# ============================================================

def main():
    print("=" * 60)
    print("RADAR DE CREADORES Y CLIPS")
    print("Hora Colombia: {}".format(
        AHORA.strftime("%d/%m/%Y %I:%M %p")
    ))
    print("Ventana desde: {}".format(
        LIMITE.strftime("%d/%m/%Y %I:%M %p")
    ))
    print("Maximo de clips: {}".format(MAX_RESULTADOS))
    print("=" * 60)

    clips = recopilar_clips()
    noticias = recopilar_noticias()
    escribir_informe(clips, noticias)


if __name__ == "__main__":
    main()
