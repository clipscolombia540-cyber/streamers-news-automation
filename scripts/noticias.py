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


# =========================================================
# CONFIGURACIÓN
# =========================================================

ZONA = timezone(timedelta(hours=-5))
AHORA = datetime.now(timezone.utc)
LIMITE = AHORA - timedelta(hours=48)
MAX_RESULTADOS = 25
MAX_WESTCOL = 2

CARPETA_SALIDA = Path("reportes")
ARCHIVO_SALIDA = CARPETA_SALIDA / "radar_streamers.md"

# Cada búsqueda tiene una categoría principal.
BUSQUEDAS = {
    "Grandes de Kick": [
        '"Westcol" streamer',
        '"La Sapa" streamer OR Kick',
        '"La Sapaaaaa" streamer',
        '"MrStivenTC" streamer',
    ],
    "Círculo de Westcol": [
        '"Westcol" colaboradores streamer',
        '"Westcol" amigos streamers',
        '"Westcol" Kick polémica',
    ],
    "Creadores emergentes": [
        'streamer colombiano emergente',
        'nuevo streamer colombiano viral',
        'streamer colombiano Kick viral',
        'creador de contenido colombiano directo viral',
    ],
    "Otros streamers": [
        'streamer colombiano Twitch',
        'streamer colombiano YouTube directo',
        'streamer colombiano Kick',
        'streamers Colombia polémica',
        'streamer latino viral directo',
    ],
    "Clips virales y polémicas": [
        'clip viral streamer colombiano',
        'momento viral streamer Kick',
        'polémica streamer colombiano',
        'clip de streamer latino viral',
    ],
    "Influencers y creadores": [
        'creador de contenido colombiano viral',
        'influencer colombiano polémica redes',
    ],
}

BUSQUEDAS_YOUTUBE = [
    "streamer colombiano viral",
    "streamer colombiano clip",
    "streamer colombiano Kick",
    "streamers Colombia polémica",
    "clip viral streamer latino",
    "Westcol streamer",
]

NOMBRES_CONOCIDOS = [
    "Westcol",
    "La Sapa",
    "La Sapaaaaa",
    "MrStivenTC",
    "Pelicanger",
    "Spreen",
    "Komanche",
    "JuanSGuarnizo",
    "Coscu",
    "TheDonato",
    "AriGameplays",
    "Rivers",
]

PALABRAS_RELEVANTES = [
    "streamer", "streamers", "kick", "twitch", "directo",
    "en vivo", "streaming", "clip", "clips", "viral",
    "youtube", "creador de contenido", "transmisión",
    "transmision", "polémica", "polemica",
]

PALABRAS_RUIDO = [
    "pronóstico del tiempo", "oferta laboral", "empleo",
    "resultado de fútbol", "resultado futbol",
    "bolsa de valores", "receta de cocina",
]


# =========================================================
# UTILIDADES
# =========================================================

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
    return fecha is not None and LIMITE <= fecha <= AHORA + timedelta(minutes=10)


def es_relevante(titulo, descripcion=""):
    texto = normalizar(titulo + " " + descripcion)

    if any(normalizar(p) in texto for p in PALABRAS_RUIDO):
        return False

    return any(normalizar(p) in texto for p in PALABRAS_RELEVANTES)


def es_westcol(texto):
    return "westcol" in normalizar(texto)


def identificar_creador(texto):
    texto_norm = normalizar(texto)

    for nombre in NOMBRES_CONOCIDOS:
        if normalizar(nombre) in texto_norm:
            return nombre

    return "No identificado"


def puntuacion(item):
    texto = normalizar(item["titulo"] + " " + item["descripcion"])
    puntos = 0

    if any(p in texto for p in ["streamer", "kick", "twitch", "directo"]):
        puntos += 3

    if any(p in texto for p in ["viral", "clip", "polémica", "polemica"]):
        puntos += 2

    if item.get("tipo") == "Video de YouTube":
        puntos += 2

    if item.get("creador") != "No identificado":
        puntos += 1

    if es_westcol(item["titulo"]):
        puntos -= 1

    return puntos


def duplicado(a, b):
    ta = normalizar(a["titulo"])
    tb = normalizar(b["titulo"])

    if ta == tb:
        return True

    similitud = SequenceMatcher(None, ta, tb).ratio()

    if similitud >= 0.84:
        return True

    # Evita repetir una misma historia con títulos ligeramente distintos.
    palabras_a = set(ta.split())
    palabras_b = set(tb.split())
    comunes = palabras_a & palabras_b

    if len(comunes) >= 5:
        union = palabras_a | palabras_b
        if union and len(comunes) / len(union) >= 0.72:
            return True

    return False


# =========================================================
# GOOGLE NEWS RSS
# =========================================================

def buscar_google_news(consulta, categoria):
    consulta_completa = f"{consulta} when:2d"
    url = (
        "https://news.google.com/rss/search?q="
        + urllib.parse.quote(consulta_completa)
        + "&hl=es-419&gl=CO&ceid=CO:es-419"
    )

    solicitud = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 ClipsColombiaRadar/1.0"},
    )

    try:
        with urllib.request.urlopen(solicitud, timeout=20) as respuesta:
            contenido = respuesta.read()
    except Exception as error:
        print(f"Aviso: falló Google News para '{consulta}': {error}")
        return []

    resultados = []

    try:
        raiz = ET.fromstring(contenido)
    except ET.ParseError:
        return []

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
            "creador": identificar_creador(titulo),
            "fuente": "Google News RSS",
        })

    return resultados


# =========================================================
# YOUTUBE OPCIONAL (YT-DLP)
# =========================================================

def buscar_youtube(consulta):
    comando = [
        sys.executable, "-m", "yt_dlp",
        "--dump-single-json",
        "--flat-playlist",
        "--no-warnings",
        "--skip-download",
        f"ytsearch8:{consulta}",
    ]

    try:
        proceso = subprocess.run(
            comando,
            capture_output=True,
            text=True,
            timeout=70,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []

    if proceso.returncode != 0 or not proceso.stdout.strip():
        return []

    try:
        datos = json.loads(proceso.stdout)
    except json.JSONDecodeError:
        return []

    entradas = datos.get("entries") or []
    resultados = []

    for video in entradas:
        titulo = limpiar(video.get("title", ""))
        video_id = video.get("id", "")
        canal = limpiar(video.get("channel") or video.get("uploader") or "")
        fecha_texto = video.get("upload_date", "")

        fecha = None
        if re.fullmatch(r"\d{8}", fecha_texto or ""):
            try:
                fecha = datetime.strptime(
                    fecha_texto, "%Y%m%d"
                ).replace(tzinfo=timezone.utc)
            except ValueError:
                fecha = None

        if not titulo or not video_id or not es_reciente(fecha):
            continue

        if not es_relevante(titulo, canal):
            continue

        resultados.append({
            "titulo": titulo,
            "url": f"https://www.youtube.com/watch?v={video_id}",
            "descripcion": f"Canal: {canal}" if canal else "",
            "fecha": fecha,
            "categoria": "Clips virales y polémicas",
            "tipo": "Video de YouTube",
            "creador": identificar_creador(titulo),
            "fuente": "YouTube",
        })

    return resultados


# =========================================================
# RECOLECCIÓN Y SELECCIÓN
# =========================================================

def recolectar():
    candidatos = []

    for categoria, consultas in BUSQUEDAS.items():
        for consulta in consultas:
            print(f"Buscando [{categoria}]: {consulta}")
            candidatos.extend(buscar_google_news(consulta, categoria))

    for consulta in BUSQUEDAS_YOUTUBE:
        print(f"Buscando en YouTube: {consulta}")
        candidatos.extend(buscar_youtube(consulta))

    return candidatos


def quitar_duplicados(candidatos):
    candidatos.sort(
        key=lambda x: (puntuacion(x), x["fecha"]),
        reverse=True,
    )

    unicos = []

    for item in candidatos:
        repetido = any(
            duplicado(item, existente)
            for existente in unicos
        )

        if not repetido:
            unicos.append(item)

    return unicos


def seleccionar(candidatos):
    # Limita historias de Westcol y prioriza diversidad.
    por_categoria = {}

    for item in candidatos:
        por_categoria.setdefault(item["categoria"], []).append(item)

    seleccionados = []
    usados = set()
    westcol = 0

    # Primero, una noticia por categoría si existe.
    for categoria in BUSQUEDAS:
        for item in por_categoria.get(categoria, []):
            clave = item["url"]

            if clave in usados:
                continue

            if es_westcol(item["titulo"]):
                if westcol >= MAX_WESTCOL:
                    continue
                westcol += 1

            seleccionados.append(item)
            usados.add(clave)
            break

    # Después, llenar hasta 25 con las mejores historias restantes.
    restantes = sorted(
        candidatos,
        key=lambda x: (puntuacion(x), x["fecha"]),
        reverse=True,
    )

    for item in restantes:
        if len(seleccionados) >= MAX_RESULTADOS:
            break

        if item["url"] in usados:
            continue

        if es_westcol(item["titulo"]) and westcol >= MAX_WESTCOL:
            continue

        if es_westcol(item["titulo"]):
            westcol += 1

        seleccionados.append(item)
        usados.add(item["url"])

    return seleccionados


# =========================================================
# INFORME MARKDOWN
# =========================================================

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
        f"**Candidatos recogidos antes de eliminar duplicados:** {total_candidatos}",
        "",
        "> Fuentes utilizadas: Google News RSS y, si está instalado, yt-dlp para YouTube. "
        "No se consultan todas las publicaciones de Kick, TikTok, Twitch e Instagram. "
        "Los resultados dependen de lo que las fuentes permitan encontrar.",
        "",
    ]

    for categoria in BUSQUEDAS:
        grupo = [
            item for item in seleccionados
            if item["categoria"] == categoria
        ]

        lineas.extend(["## " + categoria, ""])

        if not grupo:
            lineas.extend([
                "_No se encontraron resultados relevantes y recientes para esta categoría._",
                "",
            ])
            continue

        for item in grupo:
            lineas.append(f"### [{item['titulo']}]({item['url']})")
            lineas.append(f"- **Fecha:** {fecha_local(item['fecha'])}")
            lineas.append(f"- **Creador identificado:** {item['creador']}")
            lineas.append(f"- **Tipo:** {item['tipo']}")
            lineas.append(f"- **Fuente:** {item['fuente']}")

            if item["descripcion"]:
                lineas.append(f"- **Contexto:** {item['descripcion']}")

            lineas.append("")

    lineas.extend([
        "---",
        "",
        "## Nota editorial",
        "",
        "Verifica el enlace y el contexto original antes de publicar un clip. "
        "No se debe atribuir una historia a un streamer si el protagonista no está confirmado.",
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
    generar_informe(seleccionados, len(candidatos))


if __name__ == "__main__":
    main()