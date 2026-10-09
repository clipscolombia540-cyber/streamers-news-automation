
import os
import re
import html
import unicodedata
import difflib
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode
from urllib.request import Request, urlopen

try:
    from yt_dlp import YoutubeDL
except ImportError:
    YoutubeDL = None


# =========================================================
# CONFIGURACION
# =========================================================

HORAS = 48
MAX_RESULTADOS = 25
MAX_WESTCOL = 2
MAX_POR_BUSQUEDA = 8

CATEGORIAS = [
    "Grandes de Kick",
    "Circulo de Westcol",
    "Creadores emergentes",
    "Otros streamers",
    "Influencers y creadores",
    "Clips virales y polemicas",
]

# Cada grupo tiene búsquedas propias.
# Westcol NO es el centro de todas las búsquedas.
BUSQUEDAS = {
    "Grandes de Kick": [
        '"Westcol" streamer',
        '"La Sapaaaaa" streamer OR Kick',
        '"La Sapa" streamer Colombia',
        '"Chanty" streamer Colombia',
        'streamers colombianos famosos Kick',
    ],
    "Circulo de Westcol": [
        'streamers amigos de Westcol Colombia',
        'colaboracion streamers colombianos Kick',
        'creadores que hicieron stream con Westcol',
    ],
    "Creadores emergentes": [
        'streamer colombiano emergente viral',
        'nuevo streamer colombiano se vuelve viral',
        'streamer colombiano clip viral',
        'pequeño streamer colombiano polémica',
        'streamer colombiano directo sorprende',
    ],
    "Otros streamers": [
        'streamer colombiano Twitch noticia',
        'streamer colombiano Kick noticia',
        'streamer colombiano YouTube directo',
        'streamer latino polémica reciente',
        'streamer colombiano anuncia noticia',
        'streamer colombiano viral en directo',
    ],
    "Influencers y creadores": [
        'influencer colombiano viral noticia',
        'creador de contenido colombiano polémica',
        'tiktoker colombiano viral noticia',
        'youtuber colombiano noticia reciente',
    ],
    "Clips virales y polemicas": [
        'clip viral streamer colombiano',
        'momento viral directo streamer',
        'polémica streamer colombiano',
        'discusión streamer colombiano en vivo',
        'reacción viral streamer latino',
    ],
}

CREADORES = {
    "Westcol": [
        "westcol",
    ],
    "La Sapa": [
        "la sapaaaaa",
        "lasapaaaaa",
        "la sapa",
    ],
    "Chanty": [
        "chanty",
    ],
    "Samu": [
        "samulx",
    ],
    "Lonche": [
        "lonche",
    ],
    "El Agropecuario": [
        "el agropecuario",
    ],
    "Camilo Cifuentes": [
        "camilo cifuentes",
    ],
}

TERMINOS_STREAMER = [
    "streamer", "streamers", "streaming", "kick",
    "twitch", "en vivo", "directo", "stream",
    "youtuber", "gaming", "gamer",
]

TERMINOS_INFLUENCER = [
    "influencer", "influencers", "tiktoker", "tiktok",
    "creador de contenido", "creadora de contenido",
    "youtuber", "instagramer", "viral en redes",
]

TERMINOS_CLIP = [
    "clip viral", "momento viral", "polémica", "polemica",
    "pelea", "discusión", "discusion", "insulta",
    "expone", "reacciona", "en vivo", "directo",
]

EXCLUSIONES = [
    "pronóstico del tiempo", "resultado del partido",
    "tabla de posiciones", "liga betplay", "fútbol profesional",
    "futbol profesional", "mercado de fichajes",
    "perro perdido", "gato perdido",
]

AHORA = datetime.now(timezone.utc)
LIMITE = AHORA - timedelta(hours=HORAS)


# =========================================================
# UTILIDADES
# =========================================================

def normalizar(texto):
    texto = html.unescape(str(texto or "")).lower()
    texto = unicodedata.normalize("NFD", texto)
    texto = "".join(
        c for c in texto if unicodedata.category(c) != "Mn"
    )
    return re.sub(r"\s+", " ", texto).strip()


def limpiar_titulo(titulo):
    titulo = html.unescape(str(titulo or "")).strip()
    titulo = re.sub(r"\s+", " ", titulo)
    return titulo


def fecha_rss(valor):
    if not valor:
        return None

    try:
        from email.utils import parsedate_to_datetime
        fecha = parsedate_to_datetime(valor)
        if fecha.tzinfo is None:
            fecha = fecha.replace(tzinfo=timezone.utc)
        return fecha.astimezone(timezone.utc)
    except Exception:
        return None


def identificar_creador(titulo, canal=""):
    texto = normalizar(titulo)

    # Solo asignar un protagonista si aparece en el título.
    for nombre, variantes in CREADORES.items():
        if any(normalizar(v) in texto for v in variantes):
            return nombre

    return canal.strip() or "No identificado"


def es_westcol(historia):
    texto = normalizar(
        historia.get("titulo", "") + " " +
        historia.get("creador", "")
    )
    return "westcol" in texto


def es_relevante(titulo):
    texto = normalizar(titulo)

    if any(normalizar(x) in texto for x in EXCLUSIONES):
        return False

    terminos = TERMINOS_STREAMER + TERMINOS_INFLUENCER

    # Evita aceptar cualquier noticia solo porque sea viral.
    return any(normalizar(x) in texto for x in terminos)


def categoria_por_titulo(titulo, categoria_busqueda):
    texto = normalizar(titulo)

    # Una noticia sobre un clip no debe aparecer repetida
    # en varias secciones. Se le asigna una sola categoría.
    if any(normalizar(x) in texto for x in [
        "clip viral", "momento viral", "polemica",
        "pelea entre streamers", "discusion en vivo",
    ]):
        return "Clips virales y polemicas"

    if any(normalizar(x) in texto for x in TERMINOS_INFLUENCER):
        if not any(normalizar(x) in texto for x in [
            "streamer", "streamers", "kick", "twitch",
            "en vivo", "directo",
        ]):
            return "Influencers y creadores"

    if "westcol" in texto:
        if any(normalizar(x) in texto for x in [
            "amigo de westcol", "junto a westcol",
            "con westcol", "en stream de westcol",
        ]):
            # No asumir que toda persona que sale en su directo
            # pertenece automáticamente a su círculo.
            return categoria_busqueda
        return "Grandes de Kick"

    return categoria_busqueda


def fecha_dentro_del_periodo(fecha):
    return fecha is not None and LIMITE <= fecha <= AHORA


def puntuar(titulo, categoria, fuente):
    texto = normalizar(titulo)
    puntos = 0

    if any(normalizar(x) in texto for x in TERMINOS_STREAMER):
        puntos += 3

    if any(normalizar(x) in texto for x in TERMINOS_CLIP):
        puntos += 2

    if identificar_creador(titulo) != "No identificado":
        puntos += 2

    if categoria == "Creadores emergentes":
        puntos += 1

    if "youtube.com/watch" in fuente or "youtu.be/" in fuente:
        puntos += 2

    return puntos


# =========================================================
# BUSQUEDA EN GOOGLE NEWS RSS (GRATUITA)
# =========================================================

def buscar_google_news(consulta, categoria):
    resultados = []

    parametros = urlencode({
        "q": consulta + " when:2d",
        "hl": "es-419",
        "gl": "CO",
        "ceid": "CO:es-419",
    })

    url = "https://news.google.com/rss/search?" + parametros
    solicitud = Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 ClipsColombiaRadar/1.0"},
    )

    try:
        with urlopen(solicitud, timeout=15) as respuesta:
            contenido = respuesta.read()

        raiz = ET.fromstring(contenido)

        for item in raiz.findall(".//item")[:MAX_POR_BUSQUEDA]:
            titulo = limpiar_titulo(
                item.findtext("title", default="")
            )
            enlace = item.findtext("link", default="").strip()
            fecha = fecha_rss(
                item.findtext("pubDate", default="")
            )
            fuente = item.findtext("source", default="Google News")

            if not titulo or not enlace:
                continue

            if not fecha_dentro_del_periodo(fecha):
                continue

            if not es_relevante(titulo):
                continue

            resultados.append({
                "titulo": titulo,
                "url": enlace,
                "fecha": fecha,
                "fuente": fuente,
                "categoria": categoria,
                "creador": identificar_creador(titulo),
                "tipo": "Noticia",
                "precision_fecha": "fecha y hora de RSS",
            })

    except Exception as error:
        print(f"[Google News] No se pudo buscar '{consulta}': {error}")

    return resultados


# =========================================================
# BUSQUEDA EN YOUTUBE (GRATUITA CON yt-dlp)
# =========================================================

def buscar_youtube(consulta, categoria):
    resultados = []

    if YoutubeDL is None:
        return resultados

    opciones = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "extract_flat": True,
        "ignoreerrors": True,
    }

    try:
        with YoutubeDL(opciones) as ydl:
            datos = ydl.extract_info(
                f"ytsearch{MAX_POR_BUSQUEDA}:{consulta}",
                download=False,
            )

        for video in (datos or {}).get("entries", []) or []:
            if not video:
                continue

            titulo = limpiar_titulo(video.get("title", ""))
            video_id = video.get("id")
            canal = video.get("channel") or video.get("uploader") or ""
            url = video.get("url") or ""

            if video_id:
                url = f"https://www.youtube.com/watch?v={video_id}"

            if not titulo or not url:
                continue

            fecha = None
            precision = "fecha no disponible"

            # timestamp es más preciso cuando el extractor lo ofrece.
            timestamp = video.get("release_timestamp") or video.get("timestamp")

            if timestamp:
                try:
                    fecha = datetime.fromtimestamp(
                        timestamp, tz=timezone.utc
                    )
                    precision = "fecha y hora de YouTube"
                except Exception:
                    fecha = None

            # upload_date solo trae el día, no la hora.
            if fecha is None:
                upload_date = video.get("upload_date")
                if upload_date and len(upload_date) == 8:
                    try:
                        fecha = datetime.strptime(
                            upload_date, "%Y%m%d"
                        ).replace(tzinfo=timezone.utc)
                        precision = "día de publicación; hora desconocida"
                    except Exception:
                        fecha = None

            if not fecha_dentro_del_periodo(fecha):
                continue

            if not es_relevante(titulo):
                continue

            resultados.append({
                "titulo": titulo,
                "url": url,
                "fecha": fecha,
                "fuente": canal or "YouTube",
                "categoria": categoria,
                "creador": identificar_creador(titulo, canal),
                "tipo": "Video original",
                "precision_fecha": precision,
            })

    except Exception as error:
        print(f"[YouTube] No se pudo buscar '{consulta}': {error}")

    return resultados


# =========================================================
# DEDUPLICACION
# =========================================================

def similitud_titulos(a, b):
    a = normalizar(a)
    b = normalizar(b)

    if a == b:
        return 1.0

    return difflib.SequenceMatcher(None, a, b).ratio()


def misma_historia(a, b):
    # Un mismo enlace jamás debe contar dos veces.
    if a["url"].rstrip("/") == b["url"].rstrip("/"):
        return True

    # Títulos muy parecidos suelen ser la misma noticia.
    if similitud_titulos(a["titulo"], b["titulo"]) >= 0.78:
        return True

    # Comparación adicional de palabras importantes.
    palabras_a = {
        p for p in normalizar(a["titulo"]).split()
        if len(p) >= 4
    }
    palabras_b = {
        p for p in normalizar(b["titulo"]).split()
        if len(p) >= 4
    }

    if palabras_a and palabras_b:
        interseccion = len(palabras_a & palabras_b)
        union = len(palabras_a | palabras_b)

        if union and interseccion / union >= 0.68:
            return True

    return False


def agrupar_historias(candidatos):
    grupos = []

    # Primero, los resultados más útiles.
    candidatos.sort(
        key=lambda x: puntuar(
            x["titulo"], x["categoria"], x["url"]
        ),
        reverse=True,
    )

    for candidato in candidatos:
        grupo_encontrado = None

        for grupo in grupos:
            if any(
                misma_historia(candidato, fuente)
                for fuente in grupo["fuentes"]
            ):
                grupo_encontrado = grupo
                break

        if grupo_encontrado:
            urls = {
                fuente["url"] for fuente in grupo_encontrado["fuentes"]
            }

            if candidato["url"] not in urls:
                grupo_encontrado["fuentes"].append(candidato)

            continue

        grupos.append({
            "principal": candidato,
            "fuentes": [candidato],
        })

    return grupos


# =========================================================
# SELECCION EQUILIBRADA
# =========================================================

def seleccionar_resultados(grupos):
    # Clasificación única por historia.
    for grupo in grupos:
        principal = grupo["principal"]
        principal["categoria"] = categoria_por_titulo(
            principal["titulo"],
            principal["categoria"],
        )

    grupos.sort(
        key=lambda g: puntuar(
            g["principal"]["titulo"],
            g["principal"]["categoria"],
            g["principal"]["url"],
        ),
        reverse=True,
    )

    seleccionados = []
    contador_westcol = 0
    contador_categoria = {c: 0 for c in CATEGORIAS}

    # Primera pasada: dar espacio a distintas categorías.
    for categoria in CATEGORIAS:
        for grupo in grupos:
            if len(seleccionados) >= MAX_RESULTADOS:
                break

            principal = grupo["principal"]

            if principal["categoria"] != categoria:
                continue

            if grupo in seleccionados:
                continue

            if es_westcol(grupo["principal"]):
                if contador_westcol >= MAX_WESTCOL:
                    continue

            seleccionados.append(grupo)
            contador_categoria[categoria] += 1

            if es_westcol(grupo["principal"]):
                contador_westcol += 1

    # Segunda pasada: completar solo con historias únicas.
    for grupo in grupos:
        if len(seleccionados) >= MAX_RESULTADOS:
            break

        if grupo in seleccionados:
            continue

        if es_westcol(grupo["principal"]):
            if contador_westcol >= MAX_WESTCOL:
                continue
            contador_westcol += 1

        seleccionados.append(grupo)

    return seleccionados


# =========================================================
# INFORME
# =========================================================

def escribir_informe(grupos, candidatos):
    os.makedirs("reportes", exist_ok=True)

    ahora_local = datetime.now().astimezone()
    nombre = "reportes/radar_streamers.md"

    with open(nombre, "w", encoding="utf-8") as archivo:
        archivo.write("# Radar de streamers y creadores\n\n")
        archivo.write(
            f"**Generado:** {ahora_local:%d/%m/%Y %H:%M %Z}\n\n"
        )
        archivo.write(f"**Ventana:** últimas {HORAS} horas\n\n")
        archivo.write(f"**Historias únicas:** {len(grupos)}\n\n")
        archivo.write(
            f"**Máximo de resultados:** {MAX_RESULTADOS}\n\n"
        )
        archivo.write(
            "**Fuentes consultadas:** Google News RSS y YouTube "
            "mediante yt-dlp. No implica acceso directo a Kick, "
            "Twitch, TikTok o Instagram.\n\n"
        )

        for categoria in CATEGORIAS:
            historias = [
                g for g in grupos
                if g["principal"]["categoria"] == categoria
            ]

            archivo.write(f"## {categoria}\n\n")

            if not historias:
                archivo.write(
                    "_No se encontraron historias que superaran "
                    "los filtros en esta categoría._\n\n"
                )
                continue

            for grupo in historias:
                p = grupo["principal"]
                fecha = p["fecha"].astimezone()

                archivo.write(f"### {p['titulo']}\n\n")
                archivo.write(
                    f"- **Creador/canal:** {p['creador']}\n"
                )
                archivo.write(f"- **Fuente:** {p['fuente']}\n")
                archivo.write(
                    f"- **Fecha:** {fecha:%d/%m/%Y %H:%M %Z}\n"
                )
                archivo.write(
                    f"- **Precisión de fecha:** "
                    f"{p['precision_fecha']}\n"
                )
                archivo.write(f"- **Tipo:** {p['tipo']}\n")
                archivo.write(f"- **Enlace:** {p['url']}\n")

                alternas = []
                vistas = {p["url"]}

                for fuente in grupo["fuentes"]:
                    if fuente["url"] in vistas:
                        continue
                    vistas.add(fuente["url"])
                    alternas.append(fuente)

                if alternas:
                    archivo.write("- **Otras fuentes:**\n")
                    for fuente in alternas[:5]:
                        archivo.write(
                            f"  - [{fuente['fuente']}]"
                            f"({fuente['url']})\n"
                        )

                archivo.write("\n")

        archivo.write("---\n\n")
        archivo.write(
            "_El radar prioriza la relevancia y la diversidad. "
            "Si hay pocas historias que cumplan los filtros, "
            "no inventa resultados para completar el cupo._\n"
        )

    print(f"Informe generado: {nombre}")
    print(f"Historias únicas seleccionadas: {len(grupos)}")
    print(f"Candidatos consultados: {len(candidatos)}")


# =========================================================
# EJECUCION
# =========================================================

def main():
    candidatos = []

    for categoria, consultas in BUSQUEDAS.items():
        print(f"\nBuscando: {categoria}")

        for consulta in consultas:
            print(f"  - {consulta}")

            candidatos.extend(
                buscar_google_news(consulta, categoria)
            )

            candidatos.extend(
                buscar_youtube(consulta, categoria)
            )

    grupos = agrupar_historias(candidatos)
    seleccionados = seleccionar_resultados(grupos)

    escribir_informe(seleccionados, candidatos)


if __name__ == "__main__":
    main()
