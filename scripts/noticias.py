import html
import json
import re
import subprocess
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from difflib import SequenceMatcher
from pathlib import Path


# =====================================================
# CONFIGURACIÓN
# =====================================================

ZONA = timezone(timedelta(hours=-5))
AHORA = datetime.now(timezone.utc)
LIMITE = AHORA - timedelta(hours=48)

MAX_RESULTADOS = 25
MAX_WESTCOL = 2
MAX_POR_CREADOR = 5
TIEMPO_ESPERA = 45

ARCHIVO_SALIDA = Path("borradores/radar_creadores.md")

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 Chrome/130.0 Safari/537.36"
)

STREAMERS = {
    "Westcol": ["Westcol", "WestCol"],
    "Chanty": ["Chanty", "El Chanty"],
    "La Sapa": ["La Sapa", "Leandro La Sapa"],
    "MrStivenTC": ["MrStivenTC", "Mr Stiven TC"],
    "Pelicanger": ["Pelicanger"],
    "Samulx": ["Samulx", "Samul"],
    "Jeanki": ["Jeanki"],
    "Spreen": ["Spreen"],
    "Komanche": ["Komanche"],
    "JuanSGuarnizo": ["JuanSGuarnizo", "Juan S Guarnizo"],
    "Coscu": ["Coscu"],
    "Rivers": ["Rivers streamer"],
    "TheDonato": ["TheDonato", "The Donato"],
}

BUSQUEDAS_GENERALES = {
    "Clips y momentos virales": [
        '"streamer colombiano" clip viral',
        'streamer colombiano momento viral directo',
        'streamer colombiano clip gracioso Twitch Kick',
        'streamer latino momento viral directo',
    ],
    "Polémicas y enfrentamientos": [
        'streamer colombiano polémica directo',
        'streamer colombiano pelea discusión indirecta',
        'streamer colombiano responde polémica streamer',
    ],
    "Colaboraciones y directos": [
        'streamers colombianos colaboración directo',
        'streamer colombiano invitado directo Twitch Kick',
        'streamers colombianos juntos transmisión',
    ],
    "Creadores emergentes": [
        'nuevo streamer colombiano viral',
        'streamer colombiano pequeño se vuelve viral',
    ],
}


# =====================================================
# LIMPIEZA Y NORMALIZACIÓN
# =====================================================

def limpiar(texto):
    texto = html.unescape(str(texto or ""))
    texto = re.sub(r"<[^>]+>", " ", texto)
    return re.sub(r"\s+", " ", texto).strip()


def normalizar(texto):
    texto = limpiar(texto).lower()
    texto = unicodedata.normalize("NFD", texto)
    texto = "".join(
        caracter for caracter in texto
        if unicodedata.category(caracter) != "Mn"
    )
    texto = re.sub(r"https?://\S+", " ", texto)
    texto = re.sub(r"[^a-z0-9\s]", " ", texto)
    return re.sub(r"\s+", " ", texto).strip()


def palabras(texto):
    ignorar = {
        "para", "como", "pero", "desde", "sobre", "entre",
        "este", "esta", "esto", "cuando", "donde", "porque",
        "tras", "ante", "hace", "dice", "dijo", "video",
        "videos", "streamer", "streamers", "colombiano",
        "colombiana", "colombianos", "viral", "directo",
        "directos", "clip", "clips", "nuevo", "nueva",
    }
    return {
        palabra for palabra in normalizar(texto).split()
        if len(palabra) > 2 and palabra not in ignorar
    }


# =====================================================
# FECHAS
# =====================================================

def es_reciente(fecha):
    if not fecha:
        return False

    if fecha.tzinfo is None:
        fecha = fecha.replace(tzinfo=timezone.utc)

    return LIMITE <= fecha.astimezone(timezone.utc) <= AHORA


def fecha_desde_video(video):
    fecha_texto = video.get("upload_date") or ""

    if re.fullmatch(r"\d{8}", str(fecha_texto)):
        try:
            return datetime.strptime(
                fecha_texto, "%Y%m%d"
            ).replace(tzinfo=timezone.utc)
        except ValueError:
            pass

    marca = video.get("release_timestamp")
    if marca is None:
        marca = video.get("timestamp")

    if marca is not None:
        try:
            return datetime.fromtimestamp(
                float(marca), tz=timezone.utc
            )
        except (ValueError, TypeError, OverflowError):
            pass

    return None


def fecha_desde_rss(texto):
    if not texto:
        return None

    try:
        fecha = parsedate_to_datetime(texto)
        if fecha.tzinfo is None:
            fecha = fecha.replace(tzinfo=timezone.utc)
        return fecha.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return None


# =====================================================
# IDENTIFICAR CREADORES Y RELEVANCIA
# =====================================================

def identificar_creador(texto):
    texto_normalizado = normalizar(texto)

    for nombre, variantes in STREAMERS.items():
        for variante in variantes:
            buscado = normalizar(variante)

            if not buscado:
                continue

            if buscado in texto_normalizado:
                return nombre

    return ""


def es_westcol(item):
    return item.get("creador") == "Westcol"


def es_relevante(titulo, descripcion=""):
    texto = normalizar(f"{titulo} {descripcion}")

    terminos = [
        "streamer", "streamers", "streaming", "twitch",
        "kick", "directo", "directos", "en vivo",
        "transmision", "clip", "clips", "viral",
        "creador de contenido", "youtuber",
        "westcol", "chanty", "la sapa", "mrstiventc",
        "pelicanger", "samulx", "jeanki", "spreen",
        "komanche", "juansguarnizo", "coscu",
        "rivers", "thedonato",
    ]

    return any(normalizar(termino) in texto for termino in terminos)


def categoria_de(titulo, descripcion=""):
    texto = normalizar(f"{titulo} {descripcion}")

    polemica = [
        "polemica", "pelea", "discusion", "enfrentamiento",
        "indirecta", "responde a", "critica a", "denuncia",
        "insulta", "amenaza", "acusa", "controversia",
    ]

    colaboracion = [
        "colaboracion", "colabora", "invitado",
        "juntos en directo", "hace directo con",
        "transmision conjunta", "se une a",
    ]

    emergente = [
        "nuevo streamer", "streamer emergente",
        "se vuelve viral", "desconocido se hace viral",
        "pequeno streamer",
    ]

    if any(p in texto for p in polemica):
        return "Polémicas y enfrentamientos"

    if any(p in texto for p in colaboracion):
        return "Colaboraciones y directos"

    if any(p in texto for p in emergente):
        return "Creadores emergentes"

    return "Clips y momentos virales"


# =====================================================
# GOOGLE NEWS RSS
# =====================================================

def buscar_google_news(consulta, categoria=None):
    resultados = []

    parametros = {
        "q": f"{consulta} when:2d",
        "hl": "es-419",
        "gl": "CO",
        "ceid": "CO:es-419",
    }

    url = (
        "https://news.google.com/rss/search?"
        + urllib.parse.urlencode(parametros)
    )

    solicitud = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT},
    )

    try:
        with urllib.request.urlopen(
            solicitud, timeout=TIEMPO_ESPERA
        ) as respuesta:
            contenido = respuesta.read()

        raiz = ET.fromstring(contenido)

    except Exception as error:
        print(
            f"Aviso Google News: no se pudo buscar "
            f"'{consulta}': {error}"
        )
        return resultados

    for entrada in raiz.findall(".//item"):
        titulo = limpiar(entrada.findtext("title", ""))
        enlace = limpiar(entrada.findtext("link", ""))
        descripcion = limpiar(
            entrada.findtext("description", "")
        )
        fecha = fecha_desde_rss(
            entrada.findtext("pubDate", "")
        )
        fuente = limpiar(
            entrada.findtext("source", "Google News")
        )

        if not titulo or not enlace or not es_reciente(fecha):
            continue

        creador = identificar_creador(
            f"{titulo} {descripcion}"
        )

        # Para las búsquedas de un streamer específico,
        # exigimos que aparezca identificado en la noticia.
        if creador == "" and not categoria:
            continue

        if not es_relevante(titulo, descripcion):
            continue

        resultados.append({
            "titulo": titulo,
            "url": enlace,
            "descripcion": descripcion,
            "fecha": fecha,
            "categoria": categoria or categoria_de(
                titulo, descripcion
            ),
            "tipo": "Noticia",
            "creador": creador,
            "fuente": fuente or "Google News",
        })

    return resultados


# =====================================================
# YOUTUBE
# =====================================================

def buscar_youtube(consulta):
    comando = [
        sys.executable,
        "-m",
        "yt_dlp",
        "--dump-single-json",
        "--flat-playlist",
        "--no-warnings",
        "--skip-download",
        "--ignore-errors",
        f"ytsearch10:{consulta}",
    ]

    try:
        proceso = subprocess.run(
            comando,
            capture_output=True,
            text=True,
            timeout=90,
            check=False,
        )

    except (OSError, subprocess.TimeoutExpired) as error:
        print(f"ERROR YouTube '{consulta}': {error}")
        return []

    if proceso.returncode != 0 or not proceso.stdout.strip():
        detalle = (proceso.stderr or "").strip()
        print(f"ERROR YouTube '{consulta}':")
        print(detalle[:800] if detalle else "Sin respuesta")
        return []

    try:
        datos = json.loads(proceso.stdout)

    except json.JSONDecodeError as error:
        print(f"ERROR: JSON inválido de YouTube: {error}")
        print(proceso.stdout[:200])
        return []

    resultados = []

    for video in datos.get("entries") or []:
        if not video:
            continue

        titulo = limpiar(video.get("title", ""))
        video_id = video.get("id", "")
        canal = limpiar(
            video.get("channel")
            or video.get("uploader")
            or ""
        )

        fecha = fecha_desde_video(video)

        if not titulo or not video_id:
            continue

        if not fecha:
            print(
                f"YouTube sin fecha: {titulo} "
                f"| Canal: {canal}"
            )
            continue

        if not es_reciente(fecha):
            continue

        creador = identificar_creador(
            f"{titulo} {canal}"
        )

        # Evita incorporar videos que no se relacionen
        # con un streamer identificado o una búsqueda útil.
        if not creador and not es_relevante(titulo, canal):
            continue

        resultados.append({
            "titulo": titulo,
            "url": f"https://www.youtube.com/watch?v={video_id}",
            "descripcion": f"Canal: {canal}" if canal else "",
            "fecha": fecha,
            "categoria": "Clips y momentos virales",
            "tipo": "Video de YouTube",
            "creador": creador,
            "fuente": "YouTube",
        })

    print(
        f"YouTube: {len(resultados)} resultados válidos "
        f"para '{consulta}'"
    )
    return resultados


# =====================================================
# DUPLICADOS
# =====================================================

def mismo_evento(a, b):
    titulo_a = normalizar(a.get("titulo", ""))
    titulo_b = normalizar(b.get("titulo", ""))

    if not titulo_a or not titulo_b:
        return False

    if titulo_a == titulo_b:
        return True

    similitud = SequenceMatcher(
        None, titulo_a, titulo_b
    ).ratio()

    if similitud >= 0.76:
        return True

    palabras_a = palabras(titulo_a)
    palabras_b = palabras(titulo_b)

    if palabras_a and palabras_b:
        comun = palabras_a & palabras_b
        proporcion = len(comun) / max(
            1, min(len(palabras_a), len(palabras_b))
        )

        if len(comun) >= 4 and proporcion >= 0.80:
            return True

    # Detecta coberturas del mismo suceso que mencionan
    # al mismo creador y comparten varias palabras clave.
    creador_a = a.get("creador", "")
    creador_b = b.get("creador", "")

    if creador_a and creador_a == creador_b:
        if len(palabras_a & palabras_b) >= 3:
            return True

    return False


def eliminar_duplicados(items):
    ordenados = sorted(
        items,
        key=lambda x: x.get("fecha") or LIMITE,
        reverse=True,
    )

    unicos = []

    for item in ordenados:
        duplicado = False

        for existente in unicos:
            if mismo_evento(item, existente):
                duplicado = True

                # Si encontramos el video original de YouTube
                # para la misma noticia, preferimos ese enlace.
                if (
                    item.get("fuente") == "YouTube"
                    and existente.get("fuente") != "YouTube"
                ):
                    existente.update(item)

                break

        if not duplicado:
            unicos.append(item)

    return unicos


# =====================================================
# SELECCIÓN DE RESULTADOS
# =====================================================

def seleccionar(items):
    items = eliminar_duplicados(items)

    # Primero se priorizan los resultados que tienen
    # enlace a un video original de YouTube.
    items.sort(
        key=lambda x: (
            x.get("fuente") == "YouTube",
            x.get("fecha") or LIMITE,
        ),
        reverse=True,
    )

    seleccionados = []
    conteo_creador = {}
    conteo_westcol = 0

    for item in items:
        if len(seleccionados) >= MAX_RESULTADOS:
            break

        creador = item.get("creador", "")

        if creador == "Westcol":
            if conteo_westcol >= MAX_WESTCOL:
                continue

        if creador:
            if conteo_creador.get(creador, 0) >= MAX_POR_CREADOR:
                continue

        seleccionados.append(item)

        if creador == "Westcol":
            conteo_westcol += 1

        if creador:
            conteo_creador[creador] = (
                conteo_creador.get(creador, 0) + 1
            )

    return seleccionados


# =====================================================
# INFORME MARKDOWN
# =====================================================

def generar_informe(items, candidatos):
    ahora_local = datetime.now(ZONA)

    lineas = [
        "# Radar de streamers y clips",
        "",
        f"**Actualizado:** {ahora_local:%d/%m/%Y %I:%M %p}",
        "",
        "- Ventana: últimas 48 horas.",
        f"- Resultados: {len(items)} de un máximo de {MAX_RESULTADOS}.",
        f"- Candidatos recopilados: {candidatos}.",
        "- Máximo de historias de Westcol: 2.",
        "- Se filtran noticias antiguas y duplicados.",
        "",
    ]

    if not items:
        lineas.extend([
            "## Sin resultados verificables",
            "",
            "No se encontraron resultados que cumplieran los filtros.",
            "Revisa los registros de GitHub Actions para ver "
            "si falló alguna fuente o si los resultados "
            "no tenían fecha verificable.",
            "",
        ])

    categorias = [
        "Clips y momentos virales",
        "Polémicas y enfrentamientos",
        "Colaboraciones y directos",
        "Creadores emergentes",
    ]

    for categoria in categorias:
        grupo = [
            item for item in items
            if item.get("categoria") == categoria
        ]

        lineas.extend([f"## {categoria}", ""])

        if not grupo:
            lineas.extend(["Sin resultados.", ""])
            continue

        for item in grupo:
            fecha = item.get("fecha")
            fecha_local = (
                fecha.astimezone(ZONA).strftime("%d/%m %I:%M %p")
                if fecha else "Fecha desconocida"
            )

            creador = item.get("creador") or "Sin identificar"

            lineas.extend([
                f"### [{item['titulo']}]({item['url']})",
                "",
                f"- **Creador:** {creador}",
                f"- **Fecha:** {fecha_local}",
                f"- **Tipo:** {item.get('tipo', 'Noticia')}",
                f"- **Fuente:** {item.get('fuente', 'No identificada')}",
                "",
            ])

            descripcion = limpiar(item.get("descripcion", ""))

            if descripcion:
                lineas.extend([
                    f"> {descripcion[:500]}",
                    "",
                ])

    lineas.extend([
        "---",
        "",
        "## Streamers vigilados",
        "",
        ", ".join(STREAMERS.keys()),
        "",
        "_El radar depende de la disponibilidad de las fuentes. "
        "La ausencia de resultados no demuestra que no haya "
        "ocurrido nada durante el periodo._",
        "",
    ])

    return "\n".join(lineas)


# =====================================================
# EJECUCIÓN PRINCIPAL
# =====================================================

def main():
    print("=" * 55)
    print("INICIANDO RADAR DE STREAMERS")
    print(f"Hora UTC: {AHORA:%Y-%m-%d %H:%M}")
    print("Ventana: últimas 48 horas")
    print("=" * 55)

    candidatos = []

    # Búsquedas generales de Google News.
    for categoria, consultas in BUSQUEDAS_GENERALES.items():
        for consulta in consultas:
            print(f"Google News [{categoria}]: {consulta}")
            candidatos.extend(
                buscar_google_news(consulta, categoria)
            )

    # Búsquedas individuales de streamers.
    for nombre, variantes in STREAMERS.items():
        variante = variantes[0]

        consultas = [
            f'"{variante}" streamer',
            f'"{variante}" directo OR Kick OR Twitch',
            f'"{variante}" clip OR polémica OR viral',
        ]

        for consulta in consultas:
            print(f"Google News [{nombre}]: {consulta}")
            candidatos.extend(
                buscar_google_news(consulta)
            )

    # Búsquedas de YouTube para los creadores vigilados.
    # Se priorizan las búsquedas de los nombres concretos.
    for nombre, variantes in STREAMERS.items():
        consulta = f'{variantes[0]} streamer clip'
        print(f"YouTube [{nombre}]: {consulta}")
        candidatos.extend(buscar_youtube(consulta))

    print("-" * 55)
    print(f"Candidatos recopilados: {len(candidatos)}")

    # Solo conservar historias relacionadas con streamers
    # identificados. Las noticias generales pueden quedar
    # como candidatas, pero no entran sin identificación.
    filtrados = []

    for item in candidatos:
        if not item.get("creador"):
            item["creador"] = identificar_creador(
                f"{item.get('titulo', '')} "
                f"{item.get('descripcion', '')}"
            )

        if item.get("creador"):
            filtrados.append(item)

    print(f"Candidatos con streamer identificado: {len(filtrados)}")

    seleccionados = seleccionar(filtrados)

    print(f"Resultados seleccionados: {len(seleccionados)}")

    informe = generar_informe(
        seleccionados,
        len(candidatos),
    )

    ARCHIVO_SALIDA.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    ARCHIVO_SALIDA.write_text(
        informe,
        encoding="utf-8",
    )

    print(f"Informe guardado en: {ARCHIVO_SALIDA}")
    print("RADAR FINALIZADO")


if __name__ == "__main__":
    main()