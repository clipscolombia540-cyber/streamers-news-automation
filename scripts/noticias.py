import html
import json
import re
import subprocess
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from difflib import SequenceMatcher
from pathlib import Path

# =====================================================
# CONFIGURACIÓN GENERAL
# =====================================================

ZONA = timezone(timedelta(hours=-5))
AHORA = datetime.now(timezone.utc)
LIMITE = AHORA - timedelta(hours=48)

MAX_RESULTADOS = 25
MAX_WESTCOL = 2

CARPETA_SALIDA = Path("borradores")
ARCHIVO_SALIDA = CARPETA_SALIDA / "radar_creadores.md"

# =====================================================
# STREAMERS Y VARIANTES DE BÚSQUEDA
# =====================================================

STREAMERS = {
    "Westcol": ["Westcol", "WestCol"],
    "Chanty": ["Chanty", "El Chanty"],
    "La Sapa": ["La Sapa", "Leandro La Sapa"],
    "MrStivenTC": ["MrStivenTC", "Mr Stiven"],
    "Pelicanger": ["Pelicanger"],
    "Samulx": ["Samulx", "Samul"],
    "Jeanki": ["Jeanki"],
    "Spreen": ["Spreen"],
    "Komanche": ["Komanche"],
    "JuanSGuarnizo": ["JuanSGuarnizo"],
    "Coscu": ["Coscu"],
    "Rivers": ["Rivers streamer"],
    "TheDonato": ["TheDonato"],
}

# Búsquedas generales para descubrir nuevos streamers.
BUSQUEDAS_GENERALES = {
    "Clips y momentos virales": [
        '"clip de streamer colombiano"',
        '"momento viral streamer" Colombia',
        '"clip viral Kick" streamer',
        '"streamer colombiano" directo viral',
        '"streamer latino" clip viral',
    ],
    "Polémicas y enfrentamientos": [
        '"streamer colombiano" polémica',
        '"streamer colombiano" pelea',
        '"streamer colombiano" indirecta',
        '"streamer Kick" polémica Colombia',
        '"streamer latino" enfrentamiento',
    ],
    "Colaboraciones y directos": [
        '"streamers colombianos" colaboración',
        '"Westcol" streamer colaboración',
        '"Chanty" streamer directo',
        '"La Sapa" streamer directo',
        '"streamer colombiano" transmisión en vivo',
    ],
    "Creadores emergentes": [
        '"nuevo streamer colombiano"',
        '"streamer colombiano" viral',
        '"streamer colombiano" Kick',
        '"streamer colombiano" Twitch',
        '"streamer latino" nuevo streamer',
    ],
}

# Se buscan noticias por nombre, además de las búsquedas generales.
BUSQUEDAS_POR_STREAMER = {
    nombre: [
        f'"{variante}" streamer',
        f'"{variante}" directo OR Kick OR Twitch',
        f'"{variante}" clip OR polémica OR viral',
    ]
    for nombre, variantes in STREAMERS.items()
    for variante in [variantes[0]]
}

BUSQUEDAS_YOUTUBE = [
    "Westcol",
    "Chanty streamer",
    "La Sapa streamer",
    "MrStivenTC",
    "Pelicanger",
    "Samulx streamer",
    "Jeanki streamer",
    "streamer colombiano clip viral",
    "streamer colombiano Kick",
    "streamer latino polémica",
]

PALABRAS_STREAMING = [
    "streamer", "streamers", "streaming",
    "kick", "twitch", "directo", "directos",
    "en vivo", "transmisión", "transmision",
    "clip", "clips", "gaming", "videojuego",
    "videojuegos", "youtuber gamer",
]

PALABRAS_RUIDO = [
    "pronóstico del tiempo",
    "oferta laboral",
    "empleo",
    "resultado de fútbol",
    "resultado futbol",
    "bolsa de valores",
    "receta de cocina",
]

# =====================================================
# FUNCIONES AUXILIARES
# =====================================================

def limpiar(texto):
    texto = html.unescape(texto or "")
    texto = re.sub(r"<[^>]+>", " ", texto)
    return re.sub(r"\s+", " ", texto).strip()


def normalizar(texto):
    texto = limpiar(texto).lower()
    texto = re.sub(r"https?://\S+", " ", texto)
    texto = re.sub(r"[^a-z0-9áéíóúüñ ]", " ", texto)
    return re.sub(r"\s+", " ", texto).strip()


def fecha_rss(valor):
    if not valor:
        return None

    try:
        fecha = parsedate_to_datetime(valor)

        if fecha.tzinfo is None:
            fecha = fecha.replace(tzinfo=timezone.utc)

        return fecha.astimezone(timezone.utc)

    except (TypeError, ValueError, OverflowError):
        return None


def es_reciente(fecha):
    return (
        fecha is not None
        and LIMITE <= fecha <= AHORA + timedelta(minutes=10)
    )


def es_relevante(titulo, descripcion=""):
    texto = normalizar(titulo + " " + descripcion)

    if any(normalizar(p) in texto for p in PALABRAS_RUIDO):
        return False

    return any(normalizar(p) in texto for p in PALABRAS_STREAMING)


def identificar_creador(texto):
    texto_norm = normalizar(texto)

    for nombre, variantes in STREAMERS.items():
        for variante in variantes:
            if normalizar(variante) in texto_norm:
                return nombre

    return "No identificado"


def es_westcol(item):
    return identificar_creador(
        item["titulo"] + " " + item["descripcion"]
    ) == "Westcol"


def puntuacion(item):
    texto = normalizar(item["titulo"] + " " + item["descripcion"])
    puntos = 0

    if item["creador"] != "No identificado":
        puntos += 5

    if any(p in texto for p in [
        "clip", "viral", "polémica", "polemica",
        "pelea", "directo", "en vivo",
    ]):
        puntos += 3

    if any(p in texto for p in ["kick", "twitch", "streamer"]):
        puntos += 2

    if item["tipo"] == "Video de YouTube":
        puntos += 2

    return puntos


# =====================================================
# DETECCIÓN DE DUPLICADOS
# =====================================================

def duplicado(a, b):
    titulo_a = normalizar(a["titulo"])
    titulo_b = normalizar(b["titulo"])

    if titulo_a == titulo_b:
        return True

    if a["url"] == b["url"]:
        return True

    if SequenceMatcher(
        None, titulo_a, titulo_b
    ).ratio() >= 0.82:
        return True

    palabras_a = set(titulo_a.split())
    palabras_b = set(titulo_b.split())

    # Evitar comparar títulos con muy pocas palabras.
    if len(palabras_a) < 4 or len(palabras_b) < 4:
        return False

    comunes = palabras_a & palabras_b
    union = palabras_a | palabras_b

    similitud = len(comunes) / len(union) if union else 0

    # Solo se considera duplicado si hay bastante coincidencia.
    return len(comunes) >= 5 and similitud >= 0.68


def quitar_duplicados(candidatos):
    candidatos.sort(
        key=lambda x: (puntuacion(x), x["fecha"]),
        reverse=True,
    )

    unicos = []

    for item in candidatos:
        if not any(duplicado(item, existente) for existente in unicos):
            unicos.append(item)

    return unicos


# =====================================================
# GOOGLE NEWS RSS
# =====================================================

def buscar_google_news(consulta, categoria):
    consulta_completa = f"{consulta} when:2d"

    url = (
        "https://news.google.com/rss/search?q="
        + urllib.parse.quote(consulta_completa)
        + "&hl=es-419&gl=CO&ceid=CO:es-419"
    )

    solicitud = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 ClipsColombiaRadar/2.0"},
    )

    try:
        with urllib.request.urlopen(solicitud, timeout=20) as respuesta:
            contenido = respuesta.read()

    except Exception as error:
        print(f"Aviso: error de Google News en '{consulta}': {error}")
        return []

    try:
        raiz = ET.fromstring(contenido)

    except ET.ParseError:
        print(f"Aviso: RSS no válido para '{consulta}'")
        return []

    resultados = []

    for entrada in raiz.findall(".//item"):
        titulo = limpiar(entrada.findtext("title", ""))
        enlace = (entrada.findtext("link", "") or "").strip()
        descripcion = limpiar(entrada.findtext("description", ""))
        fecha = fecha_rss(entrada.findtext("pubDate", ""))

        if not titulo or not enlace or not es_reciente(fecha):
            continue

        if not es_relevante(titulo, descripcion):
            continue

        resultados.append({
            "titulo": titulo,
            "url": enlace,
            "descripcion": descripcion[:500],
            "fecha": fecha,
            "categoria": categoria,
            "tipo": "Noticia",
            "creador": identificar_creador(titulo + " " + descripcion),
            "fuente": "Google News RSS",
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
        print(f"Aviso: YouTube no respondió para '{consulta}': {error}")
        return []

    if proceso.returncode != 0 or not proceso.stdout.strip():
        print(f"Aviso: no se encontraron datos de YouTube para '{consulta}'")
        return []

    try:
        datos = json.loads(proceso.stdout)

    except json.JSONDecodeError:
        print(f"Aviso: respuesta JSON inválida para '{consulta}'")
        return []

    resultados = []

    for video in datos.get("entries") or []:
        titulo = limpiar(video.get("title", ""))
        video_id = video.get("id", "")
        canal = limpiar(
            video.get("channel")
            or video.get("uploader")
            or ""
        )

        fecha_texto = video.get("upload_date", "")
        fecha = None

        if re.fullmatch(r"\d{8}", fecha_texto or ""):
            try:
                fecha = datetime.strptime(
                    fecha_texto, "%Y%m%d"
                ).replace(tzinfo=timezone.utc)

            except ValueError:
                fecha = None

        # Sin fecha verificable no se incluye el video.
        if not titulo or not video_id or not es_reciente(fecha):
            continue

        if not es_relevante(titulo, canal):
            continue

        url_video = video.get("url", "")

        if not url_video or not str(url_video).startswith("http"):
            url_video = f"https://www.youtube.com/watch?v={video_id}"

        resultados.append({
            "titulo": titulo,
            "url": url_video,
            "descripcion": f"Canal: {canal}" if canal else "",
            "fecha": fecha,
            "categoria": "Clips y momentos virales",
            "tipo": "Video de YouTube",
            "creador": identificar_creador(titulo + " " + canal),
            "fuente": "YouTube",
        })

    return resultados


# =====================================================
# RECOLECCIÓN DE RESULTADOS
# =====================================================

def recolectar():
    candidatos = []

    for nombre, consultas in BUSQUEDAS_POR_STREAMER.items():
        for consulta in consultas:
            print(f"Buscando streamer [{nombre}]: {consulta}")

            candidatos.extend(
                buscar_google_news(consulta, f"Streamers: {nombre}")
            )

    for categoria, consultas in BUSQUEDAS_GENERALES.items():
        for consulta in consultas:
            print(f"Buscando [{categoria}]: {consulta}")

            candidatos.extend(
                buscar_google_news(consulta, categoria)
            )

    for consulta in BUSQUEDAS_YOUTUBE:
        print(f"Buscando en YouTube: {consulta}")
        candidatos.extend(buscar_youtube(consulta))

    return candidatos


# =====================================================
# SELECCIÓN Y LÍMITES
# =====================================================

def seleccionar(candidatos):
    candidatos = sorted(
        candidatos,
        key=lambda x: (puntuacion(x), x["fecha"]),
        reverse=True,
    )

    seleccionados = []
    westcol = 0

    for item in candidatos:
        if len(seleccionados) >= MAX_RESULTADOS:
            break

        if any(duplicado(item, elegido) for elegido in seleccionados):
            continue

        if es_westcol(item):
            if westcol >= MAX_WESTCOL:
                continue
            westcol += 1

        seleccionados.append(item)

    return seleccionados


# =====================================================
# GENERACIÓN DEL INFORME
# =====================================================

def fecha_local(fecha):
    return fecha.astimezone(ZONA).strftime("%d/%m/%Y %I:%M %p")


def generar_informe(seleccionados, total_candidatos):
    CARPETA_SALIDA.mkdir(parents=True, exist_ok=True)

    lineas = [
        "# Radar de Streamers — Clips Colombia",
        "",
        f"**Actualizado:** {AHORA.astimezone(ZONA).strftime('%d/%m/%Y %I:%M %p')}",
        "**Ventana de búsqueda:** últimas 48 horas",
        f"**Resultados seleccionados:** {len(seleccionados)} de máximo {MAX_RESULTADOS}",
        f"**Candidatos recogidos:** {total_candidatos}",
        "",
        "> Radar enfocado en streamers. Las noticias se deben verificar "
        "en su fuente original antes de publicar.",
        "",
    ]

    categorias = list(BUSQUEDAS_GENERALES.keys())

    categorias += [
        f"Streamers: {nombre}"
        for nombre in STREAMERS
    ]

    for categoria in categorias:
        grupo = [
            item for item in seleccionados
            if item["categoria"] == categoria
        ]

        lineas.extend([f"## {categoria}", ""])

        if not grupo:
            lineas.extend([
                "_Sin resultados recientes verificados para esta categoría._",
                "",
            ])
            continue

        for item in grupo:
            lineas.append(f"### [{item['titulo']}]({item['url']})")
            lineas.append(f"- **Fecha:** {fecha_local(item['fecha'])}")
            lineas.append(f"- **Streamer identificado:** {item['creador']}")
            lineas.append(f"- **Tipo:** {item['tipo']}")
            lineas.append(f"- **Fuente:** {item['fuente']}")

            if item["descripcion"]:
                lineas.append(f"- **Contexto:** {item['descripcion']}")

            lineas.append("")

    lineas.extend([
        "---",
        "",
        "## Revisión editorial",
        "",
        "- Confirma que el protagonista sea el streamer indicado.",
        "- Prioriza el enlace original del clip o directo.",
        "- No publiques rumores como hechos confirmados.",
        "- Los resultados dependen de las fuentes disponibles y pueden ser incompletos.",
        "",
    ])

    ARCHIVO_SALIDA.write_text(
        "\n".join(lineas),
        encoding="utf-8",
    )

    print(f"Informe generado: {ARCHIVO_SALIDA}")
    print(f"Resultados seleccionados: {len(seleccionados)}")


def main():
    candidatos = recolectar()
    unicos = quitar_duplicados(candidatos)
    seleccionados = seleccionar(unicos)

    generar_informe(
        seleccionados,
        len(candidatos),
    )


if __name__ == "__main__":
    main()