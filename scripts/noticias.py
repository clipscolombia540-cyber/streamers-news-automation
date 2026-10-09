
import os
import re
import html
import unicodedata
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from difflib import SequenceMatcher

try:
    import yt_dlp
except ImportError:
    yt_dlp = None


# ==========================================================
# CONFIGURACION
# ==========================================================

HORAS_MAXIMAS = 48
MAX_RESULTADOS = 25
MAX_WESTCOL = 2
MAX_POR_CREADOR = 3

CARPETA_SALIDA = "borradores"
ARCHIVO_SALIDA = os.path.join(
    CARPETA_SALIDA, "radar_creadores.md"
)

AHORA = datetime.now(timezone.utc)
LIMITE = AHORA - timedelta(hours=HORAS_MAXIMAS)

# Terminos que ayudan a reconocer contenido de creadores.
TERMINOS_CREADORES = {
    "streamer", "streamers", "streaming", "kick",
    "twitch", "youtuber", "youtubers", "influencer",
    "influencers", "creador", "creadores", "directo",
    "directos", "transmision", "transmisiones",
    "clip", "clips", "viral", "virales", "stream",
    "podcast", "gaming", "en vivo", "redes sociales",
    "tiktok", "youtube"
}

# Palabras demasiado generales que no deben llenar el radar.
TITULOS_DESCARTADOS = {
    "article headline",
    "breaking news",
    "últimas noticias",
    "ultimas noticias",
    "resultados del fútbol",
    "resultados del futbol",
    "horarios de televisión",
    "horarios de television",
    "programación de televisión",
    "programacion de television"
}

# Consultas enfocadas en creadores y contenido colombiano.
CATEGORIAS = {
    "Grandes de Kick": {
        "consultas": [
            'Westcol streamer Colombia',
            'La Sapaaaaa Kick Colombia',
            'Chanty streamer Colombia',
            'streamers colombianos Kick famosos'
        ],
        "claves": [
            "westcol", "la sapaaaaa", "chanty",
            "kick", "streamer", "streaming",
            "transmision", "directo"
        ]
    },
    "Circulo de Westcol": {
        "consultas": [
            'Westcol amigos colaboradores streamers',
            'Westcol invitados creadores Colombia',
            'streamers amigos de Westcol'
        ],
        "claves": [
            "westcol", "streamer", "kick",
            "colaborador", "colaboracion", "invitado",
            "directo", "creador"
        ]
    },
    "Creadores emergentes": {
        "consultas": [
            'nuevo streamer colombiano Kick',
            'streamer colombiano pequeño creciendo',
            'creador emergente streaming Colombia',
            'nuevo creador de contenido colombiano en vivo'
        ],
        "claves": [
            "streamer", "streaming", "kick", "twitch",
            "creador", "youtube", "youtuber", "directo",
            "en vivo", "contenido", "tiktok"
        ]
    },
    "Otros streamers": {
        "consultas": [
            'streamer colombiano polémica directo',
            'streamer colombiano viral transmisión',
            'streamers Colombia Twitch Kick YouTube',
            'creador colombiano momento viral streaming'
        ],
        "claves": [
            "streamer", "streaming", "kick", "twitch",
            "directo", "transmision", "creador",
            "youtube", "youtuber", "en vivo"
        ]
    },
    "Influencers y creadores": {
        "consultas": [
            'influencer colombiano viral redes sociales',
            'creador de contenido colombiano polémica',
            'influencer Colombia video viral',
            'tiktoker colombiano noticia reciente'
        ],
        "claves": [
            "influencer", "creador", "tiktoker",
            "youtuber", "contenido", "viral",
            "tiktok", "youtube", "redes sociales"
        ]
    },
    "Clips virales y polémicas": {
        "consultas": [
            'streamer colombiano momento viral en vivo',
            'clip viral streamer colombiano polémica',
            'streamer Colombia discusión reacción directo',
            'video viral creador colombiano transmisión'
        ],
        "claves": [
            "viral", "clip", "streamer", "directo",
            "transmision", "polémica", "polemica",
            "discusion", "reaccion", "creador",
            "video", "en vivo"
        ]
    }
}


# ==========================================================
# UTILIDADES
# ==========================================================

def normalizar(texto):
    texto = html.unescape(str(texto or "")).lower()
    texto = unicodedata.normalize("NFD", texto)
    texto = "".join(
        c for c in texto
        if unicodedata.category(c) != "Mn"
    )
    texto = re.sub(r"https?://\S+", " ", texto)
    texto = re.sub(r"[^a-z0-9 ]", " ", texto)
    return re.sub(r"\s+", " ", texto).strip()


def fecha_segura(fecha):
    if not fecha:
        return None

    try:
        if isinstance(fecha, (int, float)):
            resultado = datetime.fromtimestamp(
                fecha, timezone.utc
            )
        else:
            resultado = fecha

        if resultado.tzinfo is None:
            resultado = resultado.replace(tzinfo=timezone.utc)

        return resultado.astimezone(timezone.utc)
    except (ValueError, TypeError, OverflowError, OSError):
        return None


def dentro_del_periodo(fecha):
    return fecha is not None and LIMITE <= fecha <= AHORA


def palabras(texto):
    ignorar = {
        "para", "como", "pero", "desde", "hasta",
        "sobre", "entre", "este", "esta", "estos",
        "estas", "donde", "cuando", "porque", "tras",
        "ante", "con", "por", "una", "uno", "unos",
        "unas", "los", "las", "del", "que", "fue",
        "sus", "son", "ser", "hay", "más", "mas",
        "the", "and", "for", "with", "from", "this",
        "that", "his", "her", "into", "after"
    }
    return {
        palabra for palabra in normalizar(texto).split()
        if len(palabra) > 2 and palabra not in ignorar
    }


def es_titulo_valido(titulo):
    t = normalizar(titulo)

    if len(t) < 16:
        return False

    if any(malo in t for malo in TITULOS_DESCARTADOS):
        return False

    if t in {"sin titulo", "untitled", "video", "noticia"}:
        return False

    return True


def es_relevante(titulo, categoria):
    t = normalizar(titulo)
    claves = [
        normalizar(clave)
        for clave in CATEGORIAS[categoria]["claves"]
    ]

    # Debe existir una señal temática concreta.
    if not any(clave in t for clave in claves):
        return False

    # Evita que temas completamente ajenos se cuelen
    # por compartir una palabra demasiado genérica.
    señales_fuertes = {
        "streamer", "streamers", "streaming", "kick",
        "twitch", "youtuber", "youtubers", "influencer",
        "influencers", "tiktoker", "creador", "creadores",
        "transmision", "directo", "directos", "clip",
        "clips", "tiktok", "youtuber", "youtube",
        "westcol", "chanty", "sapaaaaa", "contenido"
    }

    tokens = palabras(t)
    if not tokens.intersection(señales_fuertes):
        return False

    return True


def es_westcol(registro):
    texto = normalizar(
        registro.get("titulo", "") + " " +
        registro.get("creador", "")
    )
    return "westcol" in texto or "west col" in texto


def identificar_creador(titulo, canal=""):
    texto = normalizar(titulo + " " + canal)

    conocidos = [
        "westcol", "la sapaaaaa", "chanty",
        "samulx", "lonche"
    ]

    for nombre in conocidos:
        if nombre in texto:
            return nombre.title()

    # No se inventa un creador a partir del medio de prensa.
    return canal.strip() or "No identificado"


# ==========================================================
# GOOGLE NEWS RSS
# ==========================================================

def buscar_noticias(consulta, categoria):
    query = f'{consulta} when:2d'
    parametros = {
        "q": query,
        "hl": "es-419",
        "gl": "CO",
        "ceid": "CO:es-419"
    }

    url = (
        "https://news.google.com/rss/search?"
        + urllib.parse.urlencode(parametros)
    )

    solicitud = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; RadarCreadores/1.0)"
        }
    )

    resultados = []

    try:
        with urllib.request.urlopen(
            solicitud, timeout=20
        ) as respuesta:
            raiz = ET.fromstring(respuesta.read())

        for item in raiz.findall(".//item"):
            titulo = (item.findtext("title") or "").strip()
            enlace = (item.findtext("link") or "").strip()
            fecha_texto = item.findtext("pubDate")
            fuente_elemento = item.find("source")
            fuente = (
                fuente_elemento.text.strip()
                if fuente_elemento is not None
                and fuente_elemento.text
                else "Google News"
            )

            if not es_titulo_valido(titulo) or not enlace:
                continue

            if not es_relevante(titulo, categoria):
                continue

            try:
                fecha = fecha_segura(
                    parsedate_to_datetime(fecha_texto)
                )
            except (TypeError, ValueError, OverflowError):
                fecha = None

            # Si la fecha no es fiable, no se presenta como reciente.
            if not dentro_del_periodo(fecha):
                continue

            resultados.append({
                "categoria": categoria,
                "titulo": titulo,
                "url": enlace,
                "fecha": fecha,
                "fuente": fuente,
                "creador": identificar_creador(titulo),
                "tipo": "Artículo / noticia",
                "plataforma": "Google News"
            })

    except Exception as error:
        print(
            f"[AVISO] No se pudo consultar Google News "
            f"({consulta}): {error}"
        )

    return resultados


# ==========================================================
# YOUTUBE
# ==========================================================

def buscar_youtube(consulta, categoria):
    if yt_dlp is None:
        return []

    opciones = {
        "extract_flat": True,
        "quiet": True,
        "no_warnings": True,
        "ignoreerrors": True,
        "skip_download": True,
        "socket_timeout": 15
    }

    resultados = []

    try:
        with yt_dlp.YoutubeDL(opciones) as ydl:
            info = ydl.extract_info(
                f"ytsearch8:{consulta} after:{LIMITE:%Y%m%d}",
                download=False
            )

        if not info:
            return []

        for video in info.get("entries") or []:
            if not video:
                continue

            titulo = (video.get("title") or "").strip()
            video_id = video.get("id")
            canal = (
                video.get("channel")
                or video.get("uploader")
                or ""
            )

            if not video_id or not es_titulo_valido(titulo):
                continue

            if not es_relevante(titulo, categoria):
                continue

            fecha = fecha_segura(video.get("timestamp"))

            # upload_date solo tiene precisión de día, no de hora.
            # Se usa como fecha aproximada y se etiqueta como tal.
            fecha_aproximada = False
            upload_date = video.get("upload_date")

            if fecha is None and upload_date:
                try:
                    dia = datetime.strptime(
                        upload_date, "%Y%m%d"
                    ).replace(tzinfo=timezone.utc)
                    fecha = dia
                    fecha_aproximada = True
                except ValueError:
                    fecha = None

            if not dentro_del_periodo(fecha):
                continue

            resultados.append({
                "categoria": categoria,
                "titulo": titulo,
                "url": f"https://www.youtube.com/watch?v={video_id}",
                "fecha": fecha,
                "fecha_aproximada": fecha_aproximada,
                "fuente": canal or "YouTube",
                "creador": identificar_creador(titulo, canal),
                "tipo": "Video de YouTube",
                "plataforma": "YouTube"
            })

    except Exception as error:
        print(
            f"[AVISO] No se pudo consultar YouTube "
            f"({consulta}): {error}"
        )

    return resultados


# ==========================================================
# DUPLICADOS Y AGRUPACION DE HISTORIAS
# ==========================================================

def misma_historia(a, b):
    ta = normalizar(a["titulo"])
    tb = normalizar(b["titulo"])

    if ta == tb:
        return True

    pa = palabras(ta)
    pb = palabras(tb)

    if not pa or not pb:
        return False

    interseccion = pa.intersection(pb)
    similitud = len(interseccion) / max(
        1, min(len(pa), len(pb))
    )

    # Para acontecimientos compartidos por varios titulares,
    # por ejemplo "robot golpea a Westcol".
    palabras_evento = {
        "robot", "golpe", "golpea", "agrede",
        "pelea", "discusion", "escandalo",
        "polémica", "polemica", "detenido",
        "viral", "transmision", "directo"
    }

    evento_compartido = bool(
        interseccion.intersection(palabras_evento)
    )

    if similitud >= 0.72:
        return True

    if similitud >= 0.50 and evento_compartido:
        return True

    if (
        "westcol" in ta and "westcol" in tb
        and "robot" in ta and "robot" in tb
    ):
        return True

    return SequenceMatcher(None, ta, tb).ratio() >= 0.84


def agrupar_historias(registros):
    grupos = []

    # Primero se procesan los resultados más recientes.
    registros.sort(
        key=lambda r: r["fecha"],
        reverse=True
    )

    for registro in registros:
        encontrado = None

        for grupo in grupos:
            if misma_historia(registro, grupo["principal"]):
                encontrado = grupo
                break

        if encontrado:
            urls = {
                fuente["url"]
                for fuente in encontrado["fuentes"]
            }

            if registro["url"] not in urls:
                encontrado["fuentes"].append(registro)

            # Conserva las distintas categorías relacionadas.
            if registro["categoria"] not in encontrado["categorias"]:
                encontrado["categorias"].append(
                    registro["categoria"]
                )
        else:
            grupos.append({
                "principal": registro,
                "fuentes": [registro],
                "categorias": [registro["categoria"]]
            })

    return grupos


# ==========================================================
# SELECCION EQUILIBRADA
# ==========================================================

def seleccionar_resultados(grupos):
    por_categoria = {
        categoria: [] for categoria in CATEGORIAS
    }

    for grupo in grupos:
        categoria = grupo["principal"]["categoria"]
        por_categoria[categoria].append(grupo)

    for categoria in por_categoria:
        por_categoria[categoria].sort(
            key=lambda g: g["principal"]["fecha"],
            reverse=True
        )

    elegidos = []
    creadores = {}
    westcol_total = 0

    # Una ronda por categoría evita que las primeras
    # categorías consuman todos los cupos.
    while len(elegidos) < MAX_RESULTADOS:
        hubo_candidatos = False

        for categoria in CATEGORIAS:
            if len(elegidos) >= MAX_RESULTADOS:
                break

            while por_categoria[categoria]:
                grupo = por_categoria[categoria].pop(0)
                principal = grupo["principal"]

                if grupo in elegidos:
                    continue

                hubo_candidatos = True

                if es_westcol(principal):
                    if westcol_total >= MAX_WESTCOL:
                        continue

                creador = normalizar(
                    principal.get("creador", "")
                )

                if creador and creador != "no identificado":
                    if creadores.get(creador, 0) >= MAX_POR_CREADOR:
                        continue

                elegidos.append(grupo)

                if es_westcol(principal):
                    westcol_total += 1

                if creador and creador != "no identificado":
                    creadores[creador] = (
                        creadores.get(creador, 0) + 1
                    )

                break

        if not hubo_candidatos:
            break

    return elegidos


# ==========================================================
# INFORME
# ==========================================================

def escribir_informe(grupos, encontrados, descartados):
    os.makedirs(CARPETA_SALIDA, exist_ok=True)

    with open(
        ARCHIVO_SALIDA, "w", encoding="utf-8"
    ) as archivo:
        archivo.write("# Radar de creadores colombianos\n\n")
        archivo.write(
            f"**Generado:** {AHORA.astimezone().strftime('%d/%m/%Y %H:%M UTC%z')}\n\n"
        )
        archivo.write(
            f"**Periodo:** últimas {HORAS_MAXIMAS} horas.\n\n"
        )
        archivo.write(
            f"**Historias seleccionadas:** {len(grupos)} de "
            f"{MAX_RESULTADOS} posibles.\n\n"
        )
        archivo.write(
            "> Importante: los artículos de prensa no son clips "
            "originales. Abre el enlace y verifica el contenido, "
            "la fecha y el contexto antes de publicar.\n\n"
        )

        for categoria in CATEGORIAS:
            archivo.write(f"## {categoria}\n\n")

            lista = [
                grupo for grupo in grupos
                if categoria in grupo["categorias"]
            ]

            if not lista:
                archivo.write(
                    "_No se encontraron historias relevantes "
                    "y recientes para esta categoría._\n\n"
                )
                continue

            for grupo in lista:
                r = grupo["principal"]
                fecha = r["fecha"].strftime("%d/%m/%Y %H:%M UTC")

                if r.get("fecha_aproximada"):
                    fecha += " (aproximada: solo se conoce el día)"

                archivo.write(f"### {r['titulo']}\n\n")
                archivo.write(f"- **Fecha:** {fecha}\n")
                archivo.write(
                    f"- **Creador/canal:** {r['creador']}\n"
                )
                archivo.write(
                    f"- **Tipo:** {r['tipo']}\n"
                )
                archivo.write(
                    f"- **Plataforma:** {r['plataforma']}\n"
                )
                archivo.write(f"- **Enlace:** {r['url']}\n")

                if len(grupo["fuentes"]) > 1:
                    archivo.write("- **Otras fuentes:**\n")
                    for fuente in grupo["fuentes"]:
                        if fuente["url"] == r["url"]:
                            continue
                        archivo.write(
                            f"  - {fuente['fuente']}: "
                            f"{fuente['url']}\n"
                        )

                archivo.write("\n")

        archivo.write("---\n\n")
        archivo.write("## Resumen de ejecución\n\n")
        archivo.write(
            f"- Candidatos encontrados antes de filtrar: "
            f"{encontrados}\n"
        )
        archivo.write(
            f"- Candidatos descartados por filtros: "
            f"{descartados}\n"
        )
        archivo.write(
            f"- Historias finales: {len(grupos)}\n"
        )

    print(f"Informe creado: {ARCHIVO_SALIDA}")
    print(f"Candidatos consultados: {encontrados}")
    print(f"Descartados por filtros: {descartados}")
    print(f"Historias finales: {len(grupos)}")


# ==========================================================
# EJECUCION
# ==========================================================

def main():
    candidatos = []
    consultas_realizadas = 0

    for categoria, configuracion in CATEGORIAS.items():
        print(f"\nBuscando: {categoria}")

        for consulta in configuracion["consultas"]:
            consultas_realizadas += 1

            candidatos.extend(
                buscar_noticias(consulta, categoria)
            )

            candidatos.extend(
                buscar_youtube(consulta, categoria)
            )

    cantidad_inicial = len(candidatos)

    # Elimina repeticiones exactas de URL.
    urls_vistas = set()
    unicos = []

    for registro in candidatos:
        url = registro["url"].split("&utm_")[0]

        if url in urls_vistas:
            continue

        urls_vistas.add(url)
        unicos.append(registro)

    grupos = agrupar_historias(unicos)
    seleccionados = seleccionar_resultados(grupos)

    descartados = max(
        0, cantidad_inicial - len(seleccionados)
    )

    escribir_informe(
        seleccionados,
        cantidad_inicial,
        descartados
    )


if __name__ == "__main__":
    main()
