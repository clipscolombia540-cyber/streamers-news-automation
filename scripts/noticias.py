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
from pathlib import Path
from zoneinfo import ZoneInfo

# =====================================================
# CONFIGURACIÓN
# =====================================================

HORAS_MAXIMAS = 48
MAX_RESULTADOS = 25
MAX_WESTCOL = 2
MAX_POR_CANAL = 2
RESULTADOS_POR_BUSQUEDA = 8

CARPETA = Path("borradores")
ZONA = ZoneInfo("America/Bogota")

CATEGORIAS = [
    "1. Grandes de Kick",
    "2. Amigos y círculo de Westcol",
    "3. Emergentes y descubrimientos de Kick",
    "4. Otros streamers",
    "5. Influencers y creadores",
    "6. Clips virales, humor y polémicas",
]

CANALES_KICK = {
    "Westcol": "https://kick.com/westcol",
    "La Sapaaaaa": "https://kick.com/lasapaaaaa",
    "Chanty": "https://kick.com/chanty",
    "Samulx": "https://kick.com/samulx",
    "Lonche": "https://kick.com/lonche",
}

# Las búsquedas son puntos de partida, no una lista cerrada
# de los únicos creadores que puede descubrir el radar.
BUSQUEDAS_YOUTUBE = [
    ("1. Grandes de Kick", "Westcol Kick Colombia"),
    ("1. Grandes de Kick", "La Sapaaaaa Kick"),
    ("1. Grandes de Kick", "Chanty Kick Colombia"),
    ("1. Grandes de Kick", "Samulx Kick"),
    ("1. Grandes de Kick", "Lonche Kick Colombia"),
    ("1. Grandes de Kick", "streamer colombiano Kick directo"),

    ("2. Amigos y círculo de Westcol", "Westcol colaboración streamer"),
    ("2. Amigos y círculo de Westcol", "Westcol invitados directo"),
    ("2. Amigos y círculo de Westcol", "Westcol con otros creadores"),

    ("3. Emergentes y descubrimientos de Kick",
     "streamer colombiano Kick pequeño"),
    ("3. Emergentes y descubrimientos de Kick",
     "nuevo streamer colombiano Kick"),
    ("3. Emergentes y descubrimientos de Kick",
     "Kick Colombia directo streamer"),
    ("3. Emergentes y descubrimientos de Kick",
     "clips de streamers colombianos Kick"),
    ("3. Emergentes y descubrimientos de Kick",
     "streamer colombiano desconocido Kick"),
    ("3. Emergentes y descubrimientos de Kick",
     "streamer latino Kick Colombia"),

    ("4. Otros streamers", "streamer colombiano Twitch"),
    ("4. Otros streamers", "streamer colombiano YouTube Gaming"),
    ("4. Otros streamers", "clips de streamers colombianos"),
    ("4. Otros streamers", "streamers colombianos en directo"),

    ("5. Influencers y creadores", "influencer colombiano viral"),
    ("5. Influencers y creadores", "tiktoker colombiano viral"),
    ("5. Influencers y creadores", "creadores de contenido Colombia"),
    ("5. Influencers y creadores", "youtubers colombianos recientes"),

    ("6. Clips virales, humor y polémicas",
     "momentos graciosos streamers colombianos"),
    ("6. Clips virales, humor y polémicas",
     "discusión pelea streamer colombiano"),
    ("6. Clips virales, humor y polémicas",
     "clips virales streamer Colombia"),
    ("6. Clips virales, humor y polémicas",
     "reacciones polémicas influencers colombianos"),
    ("6. Clips virales, humor y polémicas",
     "momentos inesperados directo streamer"),
]

BUSQUEDAS_NOTICIAS = [
    ("1. Grandes de Kick", '"Westcol"'),
    ("1. Grandes de Kick", '"La Sapaaaaa" Kick'),
    ("1. Grandes de Kick", '"Chanty" streamer Colombia'),
    ("1. Grandes de Kick", '"Samulx" streamer'),
    ("1. Grandes de Kick", '"Lonche" streamer Colombia'),

    ("2. Amigos y círculo de Westcol", '"Westcol" colaboración'),
    ("2. Amigos y círculo de Westcol", '"Westcol" invitados streamer'),

    ("3. Emergentes y descubrimientos de Kick",
     '"streamer colombiano" Kick'),
    ("3. Emergentes y descubrimientos de Kick",
     '"nuevo streamer" Colombia'),
    ("3. Emergentes y descubrimientos de Kick",
     '"streamer emergente" Colombia'),

    ("4. Otros streamers", '"streamer colombiano" Twitch'),
    ("4. Otros streamers", '"streamer colombiano" YouTube'),

    ("5. Influencers y creadores", '"influencer colombiano"'),
    ("5. Influencers y creadores", '"tiktoker colombiano"'),
    ("5. Influencers y creadores", '"creador de contenido colombiano"'),

    ("6. Clips virales, humor y polémicas",
     'streamer colombiano polémica viral'),
    ("6. Clips virales, humor y polémicas",
     'streamer colombiano discusión'),
    ("6. Clips virales, humor y polémicas",
     'influencer colombiano video viral'),
]


# =====================================================
# UTILIDADES
# =====================================================

def limpiar(texto):
    texto = html.unescape(str(texto or ""))
    texto = re.sub(r"<[^>]*>", " ", texto)
    return re.sub(r"\s+", " ", texto).strip()


def normalizar(texto):
    texto = limpiar(texto).lower()
    texto = re.sub(r"https?://\S+", " ", texto)
    texto = re.sub(r"[^a-z0-9áéíóúüñ ]", " ", texto)
    return " ".join(texto.split())


def parsear_fecha(valor):
    if not valor:
        return None

    try:
        fecha = datetime.fromisoformat(
            str(valor).replace("Z", "+00:00")
        )
        if fecha.tzinfo is None:
            fecha = fecha.replace(tzinfo=timezone.utc)
        return fecha.astimezone(timezone.utc)
    except (ValueError, TypeError):
        pass

    try:
        fecha = parsedate_to_datetime(valor)
        if fecha.tzinfo is None:
            fecha = fecha.replace(tzinfo=timezone.utc)
        return fecha.astimezone(timezone.utc)
    except (ValueError, TypeError, OverflowError):
        return None


def descargar(url):
    solicitud = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 RadarCreadores/2.0",
            "Accept": "application/rss+xml, application/xml, text/xml",
        },
    )
    with urllib.request.urlopen(solicitud, timeout=25) as respuesta:
        return respuesta.read()


def fecha_valida(fecha):
    if not fecha:
        return False

    ahora = datetime.now(timezone.utc)
    return ahora - timedelta(hours=HORAS_MAXIMAS) <= fecha <= ahora


def crear_registro(
    titulo, url, fecha, fuente, categoria, canal=""
):
    titulo = limpiar(titulo)
    url = limpiar(url)
    canal = limpiar(canal)

    if not titulo or not url or not fecha_valida(fecha):
        return None

    # IMPORTANTE:
    # La identidad se basa primero en el canal que publicó el video.
    # Que un título mencione a Westcol NO convierte automáticamente
    # al autor del video en Westcol.
    creador = canal or "Por identificar"

    return {
        "titulo": titulo,
        "url": url,
        "fecha": fecha,
        "fuente": fuente,
        "categoria": categoria,
        "canal": canal or "No identificado",
        "creador": creador,
    }


# =====================================================
# YOUTUBE: BÚSQUEDA REAL MEDIANTE yt-dlp
# =====================================================

def buscar_youtube():
    resultados = []

    for categoria, consulta in BUSQUEDAS_YOUTUBE:
        comando = [
            sys.executable, "-m", "yt_dlp",
            "--dump-single-json",
            "--flat-playlist",
            "--no-warnings",
            "--ignore-errors",
            f"ytsearch{RESULTADOS_POR_BUSQUEDA}:{consulta}",
        ]

        try:
            proceso = subprocess.run(
                comando,
                capture_output=True,
                text=True,
                timeout=70,
                check=False,
            )

            if proceso.returncode != 0 and not proceso.stdout.strip():
                print(
                    f"YouTube sin resultados para '{consulta}': "
                    f"{proceso.stderr[-300:]}"
                )
                continue

            datos = json.loads(proceso.stdout)
            entradas = datos.get("entries") or []

            for video in entradas:
                if not video:
                    continue

                titulo = video.get("title", "")
                canal = (
                    video.get("channel")
                    or video.get("uploader")
                    or video.get("channel_id")
                    or ""
                )

                fecha = None
                timestamp = video.get("release_timestamp")
                if timestamp is None:
                    timestamp = video.get("timestamp")

                if timestamp:
                    try:
                        fecha = datetime.fromtimestamp(
                            float(timestamp), timezone.utc
                        )
                    except (ValueError, TypeError, OverflowError, OSError):
                        fecha = None

                if not fecha:
                    fecha_texto = video.get("upload_date", "")
                    if re.fullmatch(r"\d{8}", str(fecha_texto)):
                        try:
                            fecha = datetime.strptime(
                                fecha_texto, "%Y%m%d"
                            ).replace(tzinfo=timezone.utc)
                        except ValueError:
                            fecha = None

                enlace = video.get("url") or video.get("webpage_url") or ""
                video_id = video.get("id", "")

                if video_id and not enlace.startswith("http"):
                    enlace = f"https://www.youtube.com/watch?v={video_id}"

                registro = crear_registro(
                    titulo=titulo,
                    url=enlace,
                    fecha=fecha,
                    fuente="YouTube",
                    categoria=categoria,
                    canal=canal,
                )

                if registro:
                    resultados.append(registro)

            print(
                f"YouTube: '{consulta}' -> "
                f"{len(entradas)} candidatos"
            )

        except subprocess.TimeoutExpired:
            print(f"YouTube agotó el tiempo: {consulta}")
        except json.JSONDecodeError:
            print(f"YouTube devolvió datos no válidos: {consulta}")
        except Exception as error:
            print(f"Error en YouTube ({consulta}): {error}")

    return resultados


# =====================================================
# GOOGLE NEWS RSS
# =====================================================

def buscar_noticias():
    resultados = []

    for categoria, consulta in BUSQUEDAS_NOTICIAS:
        parametros = urllib.parse.urlencode({
            "q": f"{consulta} when:2d",
            "hl": "es-419",
            "gl": "CO",
            "ceid": "CO:es-419",
        })

        url = "https://news.google.com/rss/search?" + parametros

        try:
            raiz = ET.fromstring(descargar(url))

            for item in raiz.findall(".//item"):
                titulo = item.findtext("title", "")
                enlace = item.findtext("link", "")
                fecha = parsear_fecha(item.findtext("pubDate", ""))

                fuente_xml = item.find("source")
                fuente = (
                    limpiar(fuente_xml.text)
                    if fuente_xml is not None
                    else "Google News"
                )

                # Google News no siempre indica el autor original.
                # No inferimos que el creador del artículo sea Westcol.
                registro = crear_registro(
                    titulo=titulo,
                    url=enlace,
                    fecha=fecha,
                    fuente=f"Google News — {fuente}",
                    categoria=categoria,
                    canal="",
                )

                if registro:
                    resultados.append(registro)

            print(f"Google News consultado: {consulta}")

        except Exception as error:
            print(f"Google News falló ({consulta}): {error}")

    return resultados


# =====================================================
# CLASIFICACIÓN Y DEDUPLICACIÓN
# =====================================================

def clave_url(url):
    partes = urllib.parse.urlsplit(url)
    host = partes.netloc.lower()

    if "youtube.com" in host:
        video_id = urllib.parse.parse_qs(
            partes.query
        ).get("v", [""])[0]
        if video_id:
            return "youtube:" + video_id

    if "youtu.be" in host:
        return "youtube:" + partes.path.strip("/")

    return host + partes.path.rstrip("/").lower()


def quitar_duplicados(resultados):
    resultados = sorted(
        resultados,
        key=lambda item: item["fecha"],
        reverse=True,
    )

    unicos = []
    urls = set()

    for item in resultados:
        clave = clave_url(item["url"])

        if clave in urls:
            continue

        urls.add(clave)
        unicos.append(item)

    return unicos


def es_mencion_westcol(item):
    texto = normalizar(
        item["titulo"] + " " + item["canal"]
    )
    return "westcol" in texto


def seleccionar_resultados(resultados):
    grupos = {categoria: [] for categoria in CATEGORIAS}

    for item in resultados:
        categoria = item["categoria"]

        # No colocar automáticamente toda mención de Westcol
        # en la categoría de grandes de Kick.
        if (
            categoria == "2. Amigos y círculo de Westcol"
            and not es_mencion_westcol(item)
        ):
            continue

        grupos.setdefault(categoria, []).append(item)

    for categoria in grupos:
        grupos[categoria].sort(
            key=lambda item: item["fecha"],
            reverse=True,
        )

    seleccionados = []
    conteo_canal = {}
    conteo_westcol = 0

    # Rondas por categoría para dar oportunidades a todas.
    while len(seleccionados) < MAX_RESULTADOS:
        hubo_cambio = False

        for categoria in CATEGORIAS:
            if len(seleccionados) >= MAX_RESULTADOS:
                break

            grupo = grupos.get(categoria, [])

            while grupo:
                item = grupo.pop(0)

                # No se conoce la identidad del autor en Google News.
                # Se usa el título como clave temporal para evitar
                # que todos los artículos cuenten como un solo creador.
                canal = normalizar(item["canal"])
                clave_canal = canal or normalizar(item["titulo"])

                if "westcol" in normalizar(item["creador"]):
                    if conteo_westcol >= MAX_WESTCOL:
                        continue

                if conteo_canal.get(clave_canal, 0) >= MAX_POR_CANAL:
                    continue

                seleccionados.append(item)
                conteo_canal[clave_canal] = (
                    conteo_canal.get(clave_canal, 0) + 1
                )

                if "westcol" in normalizar(item["creador"]):
                    conteo_westcol += 1

                hubo_cambio = True
                break

        if not hubo_cambio:
            break

    return sorted(
        seleccionados,
        key=lambda item: (
            CATEGORIAS.index(item["categoria"]),
            -item["fecha"].timestamp(),
        ),
    )


# =====================================================
# GENERAR INFORME
# =====================================================

def generar_informe(resultados):
    CARPETA.mkdir(exist_ok=True)

    ahora = datetime.now(ZONA)
    archivo = CARPETA / (
        "radar-" + ahora.strftime("%Y-%m-%d") + ".md"
    )

    lineas = [
        "# Radar colombiano de streamers e influencers",
        "",
        f"Generado: {ahora:%d/%m/%Y %H:%M} (hora Colombia)",
        "",
        f"- Periodo: últimas {HORAS_MAXIMAS} horas.",
        f"- Resultados: {len(resultados)} de máximo {MAX_RESULTADOS}.",
        f"- Máximo de Westcol: {MAX_WESTCOL} cuando se identifica el canal.",
        "",
        "## Canales principales de Kick",
        "",
    ]

    for nombre, url in CANALES_KICK.items():
        lineas.append(f"- [{nombre}]({url})")

    lineas.extend([
        "",
        "> Los resultados son candidatos encontrados en búsquedas,",
        "> no una lista exhaustiva de todos los directos o clips.",
        "> Las búsquedas de emergentes no verifican por sí solas",
        "> el número de seguidores ni la popularidad del canal.",
        "",
    ])

    for categoria in CATEGORIAS:
        lineas.extend([f"# {categoria}", ""])

        elementos = [
            item for item in resultados
            if item["categoria"] == categoria
        ]

        if not elementos:
            lineas.extend([
                "No se encontraron resultados recientes en esta sección.",
                "",
            ])
            continue

        for item in elementos:
            fecha = item["fecha"].astimezone(ZONA).strftime(
                "%d/%m/%Y %H:%M"
            )

            lineas.extend([
                f"## {item['titulo']}",
                "",
                f"- **Canal o autor:** {item['canal']}",
                f"- **Fuente:** {item['fuente']}",
                f"- **Fecha:** {fecha} (Colombia)",
                f"- **Enlace:** {item['url']}",
                "",
            ])

    lineas.extend([
        "---",
        "",
        "# Búsquedas directas",
        "",
        "- [Kick](https://kick.com/)",
        "- [Kick Colombia en Google](https://www.google.com/search?q=site%3Akick.com+Colombia+streamer)",
        "- [Twitch](https://www.twitch.tv/directory)",
        "- [TikTok](https://www.tiktok.com/search?q=streamer%20colombiano)",
        "- [Instagram](https://www.instagram.com/)",
        "- [YouTube: clips colombianos](https://www.youtube.com/results?search_query=clips+streamers+colombianos)",
        "",
        "Los enlaces de esta sección son búsquedas manuales,",
        "no resultados recopilados automáticamente.",
        "",
    ])

    archivo.write_text("\n".join(lineas), encoding="utf-8")
    print(f"Informe guardado: {archivo}")


# =====================================================
# EJECUCIÓN
# =====================================================

def main():
    print("=" * 55)
    print("RADAR COLOMBIANO DE CREADORES")
    print(f"Periodo: últimas {HORAS_MAXIMAS} horas")
    print("=" * 55)

    resultados = []
    resultados.extend(buscar_youtube())
    resultados.extend(buscar_noticias())

    print(f"Candidatos recopilados: {len(resultados)}")

    resultados = quitar_duplicados(resultados)
    print(f"Tras deduplicar: {len(resultados)}")

    resultados = seleccionar_resultados(resultados)
    print(f"Resultados seleccionados: {len(resultados)}")

    generar_informe(resultados)


if __name__ == "__main__":
    main()