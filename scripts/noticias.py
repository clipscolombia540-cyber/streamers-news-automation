
import html
import json
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from collections import Counter
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

try:
    from zoneinfo import ZoneInfo
    ZONA = ZoneInfo("America/Bogota")
except Exception:
    ZONA = timezone(timedelta(hours=-5))

try:
    import yt_dlp
except ImportError:
    yt_dlp = None


# =========================================================
# CONFIGURACION
# =========================================================

HORAS_MAXIMAS = 48
MAX_RESULTADOS = 25
MAX_WESTCOL = 2
MAX_POR_CREADOR = 3
RESULTADOS_POR_BUSQUEDA = 10

CARPETA_SALIDA = Path("borradores")
ARCHIVO_SALIDA = CARPETA_SALIDA / "radar_creadores.md"

AHORA = datetime.now(timezone.utc)
LIMITE = AHORA - timedelta(hours=HORAS_MAXIMAS)

# Consultas separadas por categoría.
# Se usan varias frases para no depender de una única búsqueda.

BUSQUEDAS = {
    "Grandes de Kick": [
        "WestCOL directo Kick Colombia",
        "La Sapaaaaa directo Kick",
        "Chanty streamer Colombia Kick",
        "Samulx streamer Kick",
        "Lonche streamer Kick Colombia",
    ],

    "Circulo de Westcol": [
        "Westcol amigos streamers Colombia",
        "Westcol colaboradores streamers",
        "streamers con Westcol Colombia",
        "clip Westcol amigos directo",
        "Westcol invitados directo reciente",
    ],

    "Creadores emergentes": [
        "streamer colombiano Kick directo pequeño",
        "nuevo streamer colombiano Kick",
        "streamer emergente Colombia directo",
        "clips streamer colombiano desconocido",
        "streamer colombiano jugando Kick",
        "pequeño streamer colombiano viral",
        "nuevo creador de contenido Colombia streaming",
        "streamer colombiano directo hoy",
        "clips Kick Colombia streamer",
        "streamer latino Kick Colombia reciente",
    ],

    "Otros streamers": [
        "streamer colombiano directo reciente",
        "streamers colombianos Twitch clips",
        "streamer colombiano YouTube Gaming",
        "clips de streamers colombianos recientes",
        "directo streamer Colombia gaming",
        "streamer latinoamericano Colombia clips",
        "creadores gaming colombianos recientes",
        "streamer colombiano reacciones directo",
        "streamer colombiano jugando en vivo",
        "clips virales streamers Colombia",
    ],

    "Influencers y creadores": [
        "influencer colombiano reciente",
        "creadores de contenido Colombia polémica",
        "influencers colombianos entrevista reciente",
        "creador colombiano video viral",
        "influencer colombiano redes sociales noticia",
    ],

    "Clips virales y polémicas": [
        "pelea streamer colombiano clip",
        "discusión streamer Colombia directo",
        "momento viral streamer colombiano",
        "polémica influencer colombiano reciente",
        "clip gracioso streamer colombiano",
        "reacción streamer colombiano viral",
        "streamer colombiano discusión en vivo",
    ],
}


# =========================================================
# UTILIDADES
# =========================================================

def limpiar_texto(valor):
    if not valor:
        return ""
    valor = html.unescape(str(valor))
    return re.sub(r"\s+", " ", valor).strip()


def normalizar(valor):
    valor = limpiar_texto(valor).lower()
    valor = re.sub(r"[^a-z0-9áéíóúñü ]", " ", valor)
    return re.sub(r"\s+", " ", valor).strip()


def convertir_fecha(valor):
    """Convierte fechas ISO, RFC822 o timestamps a UTC."""
    if valor is None or valor == "":
        return None

    if isinstance(valor, (int, float)):
        try:
            return datetime.fromtimestamp(valor, tz=timezone.utc)
        except (ValueError, OverflowError, OSError):
            return None

    valor = str(valor).strip()

    try:
        fecha = datetime.fromisoformat(valor.replace("Z", "+00:00"))
        if fecha.tzinfo is None:
            fecha = fecha.replace(tzinfo=timezone.utc)
        return fecha.astimezone(timezone.utc)
    except ValueError:
        pass

    try:
        fecha = parsedate_to_datetime(valor)
        if fecha.tzinfo is None:
            fecha = fecha.replace(tzinfo=timezone.utc)
        return fecha.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError):
        pass

    # yt-dlp puede devolver YYYYMMDD, sin hora exacta.
    if re.fullmatch(r"\d{8}", valor):
        try:
            fecha = datetime.strptime(valor, "%Y%m%d")
            # El mediodía evita tratar todos los videos como publicados
            # exactamente a medianoche. Sigue siendo una fecha aproximada.
            fecha = fecha.replace(hour=12, tzinfo=timezone.utc)
            return fecha
        except ValueError:
            return None

    return None


def fecha_reciente(fecha):
    if not fecha:
        return False
    return LIMITE <= fecha <= AHORA + timedelta(minutes=10)


def formatear_fecha(fecha):
    if not fecha:
        return "Fecha no disponible"
    return fecha.astimezone(ZONA).strftime("%d/%m/%Y %I:%M %p")


def crear_registro(
    titulo,
    url,
    creador,
    fuente,
    fecha,
    categoria,
    fecha_aproximada=False,
):
    titulo = limpiar_texto(titulo)
    url = limpiar_texto(url)
    creador = limpiar_texto(creador) or "Canal por identificar"
    fuente = limpiar_texto(fuente) or "Fuente desconocida"

    if not titulo or not url or not fecha:
        return None

    if not fecha_reciente(fecha):
        return None

    return {
        "titulo": titulo,
        "url": url,
        "creador": creador,
        "fuente": fuente,
        "fecha": fecha,
        "categoria": categoria,
        "fecha_aproximada": fecha_aproximada,
    }


def es_contenido_westcol(item):
    texto = normalizar(
        item["creador"] + " " + item["titulo"]
    )
    return "westcol" in texto or "west col" in texto


def clave_url(url):
    url = limpiar_texto(url)
    url = url.split("?")[0].rstrip("/")
    return url.lower()


# =========================================================
# BUSQUEDA EN YOUTUBE CON yt-dlp
# =========================================================

def buscar_youtube(consulta, categoria):
    resultados = []

    if yt_dlp is None:
        print("AVISO: yt-dlp no está instalado.")
        return resultados

    opciones = {
        "quiet": True,
        "no_warnings": True,
        "ignoreerrors": True,
        "skip_download": True,
        "extract_flat": "in_playlist",
        "socket_timeout": 15,
    }

    try:
        with yt_dlp.YoutubeDL(opciones) as ydl:
            datos = ydl.extract_info(
                f"ytsearch{RESULTADOS_POR_BUSQUEDA}:{consulta}",
                download=False,
            )

        if not datos:
            return resultados

        entradas = datos.get("entries") or []

        for video in entradas:
            if not video:
                continue

            titulo = video.get("title") or ""
            canal = (
                video.get("channel")
                or video.get("uploader")
                or video.get("channel_id")
                or "Canal por identificar"
            )

            url = video.get("webpage_url") or video.get("url") or ""

            if url and not url.startswith("http"):
                video_id = video.get("id") or url
                if video_id:
                    url = f"https://www.youtube.com/watch?v={video_id}"

            if not url:
                continue

            fecha = convertir_fecha(
                video.get("release_timestamp")
                or video.get("timestamp")
            )
            fecha_aproximada = False

            if fecha is None:
                fecha = convertir_fecha(video.get("upload_date"))
                if fecha is not None:
                    fecha_aproximada = True

            registro = crear_registro(
                titulo=titulo,
                url=url,
                creador=canal,
                fuente="YouTube",
                fecha=fecha,
                categoria=categoria,
                fecha_aproximada=fecha_aproximada,
            )

            if registro:
                resultados.append(registro)

    except Exception as error:
        print(f"AVISO YouTube [{consulta}]: {error}")

    return resultados


# =========================================================
# BUSQUEDA EN GOOGLE NEWS RSS
# =========================================================

def buscar_google_news(consulta, categoria):
    resultados = []

    consulta_completa = f"{consulta} when:2d"
    parametros = urllib.parse.urlencode({
        "q": consulta_completa,
        "hl": "es-419",
        "gl": "CO",
        "ceid": "CO:es-419",
    })

    url_rss = (
        "https://news.google.com/rss/search?"
        + parametros
    )

    solicitud = urllib.request.Request(
        url_rss,
        headers={
            "User-Agent": (
                "Mozilla/5.0 "
                "(compatible; RadarCreadores/1.0)"
            )
        },
    )

    try:
        with urllib.request.urlopen(solicitud, timeout=20) as respuesta:
            contenido = respuesta.read()

        raiz = ET.fromstring(contenido)

        for item in raiz.findall(".//item"):
            titulo = item.findtext("title") or ""
            enlace = item.findtext("link") or ""
            fecha_texto = item.findtext("pubDate") or ""
            fuente = item.findtext("source") or "Google News"

            fecha = convertir_fecha(fecha_texto)

            # La noticia puede incluir el medio al final del título.
            partes = titulo.rsplit(" - ", 1)
            if len(partes) == 2:
                titulo = partes[0]
                fuente = partes[1] or fuente

            registro = crear_registro(
                titulo=titulo,
                url=enlace,
                creador=fuente,
                fuente="Google News",
                fecha=fecha,
                categoria=categoria,
            )

            if registro:
                resultados.append(registro)

    except Exception as error:
        print(f"AVISO Google News [{consulta}]: {error}")

    return resultados


# =========================================================
# RECOPILACION Y DEDUPLICACION
# =========================================================

def recopilar_resultados():
    por_categoria = {categoria: [] for categoria in BUSQUEDAS}
    vistos = set()

    total_consultas = sum(len(qs) for qs in BUSQUEDAS.values())
    numero_consulta = 0

    for categoria, consultas in BUSQUEDAS.items():
        for consulta in consultas:
            numero_consulta += 1
            print(
                f"[{numero_consulta}/{total_consultas}] "
                f"{categoria}: {consulta}"
            )

            candidatos = buscar_youtube(consulta, categoria)

            # Las noticias pueden complementar los resultados,
            # especialmente cuando no hay suficientes videos.
            candidatos.extend(
                buscar_google_news(consulta, categoria)
            )

            for item in candidatos:
                llave = clave_url(item["url"])
                if not llave or llave in vistos:
                    continue

                vistos.add(llave)
                por_categoria[categoria].append(item)

            # Pausa breve para no disparar demasiadas consultas seguidas.
            time.sleep(0.25)

    for categoria in por_categoria:
        por_categoria[categoria].sort(
            key=lambda item: item["fecha"],
            reverse=True,
        )

    return por_categoria


# =========================================================
# SELECCION DE RESULTADOS
# =========================================================

def seleccionar_resultados(por_categoria):
    seleccionados = []
    urls_vistas = set()
    conteo_creador = Counter()
    conteo_westcol = 0

    # Las categorías se recorren en el orden de configuración.
    for categoria in BUSQUEDAS:
        candidatos = por_categoria.get(categoria, [])

        for item in candidatos:
            if len(seleccionados) >= MAX_RESULTADOS:
                break

            llave = clave_url(item["url"])
            if llave in urls_vistas:
                continue

            es_westcol = es_contenido_westcol(item)
            if es_westcol and conteo_westcol >= MAX_WESTCOL:
                continue

            creador_normalizado = normalizar(item["creador"])
            if not creador_normalizado:
                creador_normalizado = "canal por identificar"

            if conteo_creador[creador_normalizado] >= MAX_POR_CREADOR:
                continue

            urls_vistas.add(llave)
            seleccionados.append(item)
            conteo_creador[creador_normalizado] += 1

            if es_westcol:
                conteo_westcol += 1

    seleccionados.sort(
        key=lambda item: item["fecha"],
        reverse=True,
    )

    return seleccionados


# =========================================================
# INFORME MARKDOWN
# =========================================================

def crear_informe(por_categoria, seleccionados):
    CARPETA_SALIDA.mkdir(parents=True, exist_ok=True)

    ahora_local = AHORA.astimezone(ZONA)
    lineas = [
        "# Radar de creadores colombianos",
        "",
        f"**Actualizado:** {ahora_local.strftime('%d/%m/%Y %I:%M %p')}",
        f"**Ventana de búsqueda:** últimas {HORAS_MAXIMAS} horas",
        f"**Resultados incluidos:** {len(seleccionados)} de máximo {MAX_RESULTADOS}",
        "",
        "> Fuentes: resultados de búsqueda de YouTube y Google News RSS. "
        "La disponibilidad depende de lo que estas fuentes publiquen e indexen.",
        "",
        "> Algunas entradas de YouTube solo incluyen la fecha, sin hora exacta. "
        "Esas horas se estiman y pueden tener un margen de error.",
        "",
    ]

    conteo_final = Counter(
        item["categoria"] for item in seleccionados
    )

    for categoria in BUSQUEDAS:
        lineas.append(f"## {categoria}")
        lineas.append("")

        items = [
            item for item in seleccionados
            if item["categoria"] == categoria
        ]

        if not items:
            candidatos = por_categoria.get(categoria, [])
            lineas.append(
                "No se encontraron resultados que cumplan el filtro "
                "de fecha en las fuentes consultadas."
            )

            if candidatos:
                lineas.append(
                    f"Se encontraron {len(candidatos)} candidatos antes "
                    "de aplicar los límites generales del informe."
                )

            lineas.append("")
            continue

        for numero, item in enumerate(items, start=1):
            fecha = formatear_fecha(item["fecha"])
            nota_fecha = (
                " *(hora estimada; solo se recibió la fecha)*"
                if item.get("fecha_aproximada")
                else ""
            )

            lineas.extend([
                f"### {numero}. {item['titulo']}",
                f"- **Creador o canal:** {item['creador']}",
                f"- **Fuente:** {item['fuente']}",
                f"- **Publicado:** {fecha}{nota_fecha}",
                f"- **Enlace:** {item['url']}",
                "",
            ])

    lineas.extend([
        "---",
        "",
        "## Resumen de recopilación",
        "",
        f"- Resultados finales: {len(seleccionados)}",
        f"- Límite por creador: {MAX_POR_CREADOR}",
        f"- Límite de contenido asociado a Westcol: {MAX_WESTCOL}",
        "",
        "### Resultados por categoría",
        "",
    ])

    for categoria in BUSQUEDAS:
        lineas.append(
            f"- {categoria}: {conteo_final.get(categoria, 0)}"
        )

    lineas.extend([
        "",
        "## Importante",
        "",
        "Este radar no garantiza encontrar todos los directos ni todos "
        "los clips de Kick, Twitch, TikTok o Instagram. La búsqueda "
        "automática depende de fuentes accesibles sin autenticación y "
        "de que el contenido esté indexado. No se inventan resultados "
        "para completar categorías.",
        "",
    ])

    ARCHIVO_SALIDA.write_text(
        "\n".join(lineas),
        encoding="utf-8",
    )

    print(f"Informe guardado en: {ARCHIVO_SALIDA}")
    print(f"Total de resultados: {len(seleccionados)}")

    for categoria in BUSQUEDAS:
        print(
            f"{categoria}: "
            f"{conteo_final.get(categoria, 0)}"
        )


# =========================================================
# EJECUCION PRINCIPAL
# =========================================================

def main():
    print("=" * 60)
    print("INICIANDO RADAR DE CREADORES COLOMBIANOS")
    print(f"Hora UTC: {AHORA.isoformat()}")
    print(f"Filtro: últimas {HORAS_MAXIMAS} horas")
    print("=" * 60)

    if yt_dlp is None:
        print(
            "ERROR: falta yt-dlp. Instálalo con "
            "'python -m pip install yt-dlp'."
        )

    por_categoria = recopilar_resultados()
    seleccionados = seleccionar_resultados(por_categoria)
    crear_informe(por_categoria, seleccionados)

    print("RADAR FINALIZADO")


if __name__ == "__main__":
    main()
