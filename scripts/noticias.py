
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
MAX_POR_CREADOR = 5
MAX_WESTCOL = 2
TIEMPO_ESPERA = 30

ARCHIVO_SALIDA = Path("borradores/radar_creadores.md")

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 Chrome/130.0 Safari/537.36"
)

# Lista actualizada de creadores.
# Se excluye Jeanki por ahora.
STREAMERS = {
    "Westcol": ["Westcol", "WestCol"],
    "MrStivenTC": ["MrStivenTC", "Mr Stiven TC"],
    "Pelicanger": ["Pelicanger"],
    "Samulx": ["Samulx"],
    "Chanty": ["Chanty", "El Chanty"],
    "La Sapa": ["La Sapa", "Leandro La Sapa"],
    "Lonche de Huevito": [
        "Lonche de Huevito",
        "Lonche Huevito",
    ],
    "Rey de la City": [
        "Rey de la City",
        "Rey de City",
    ],
    "Spreen": ["Spreen"],
    "Komanche": ["Komanche"],
    "JuanSGuarnizo": [
        "JuanSGuarnizo",
        "Juan S Guarnizo",
    ],
    "Coscu": ["Coscu"],
    "Rivers": ["Rivers streamer"],
    "TheDonato": ["TheDonato", "The Donato"],
}

BUSQUEDAS_GENERALES = {
    "Clips y momentos virales": [
        '"streamer colombiano" clip viral',
        'streamer colombiano momentos graciosos',
        'streamers colombianos clips recientes',
    ],
    "Polémicas y enfrentamientos": [
        'streamer colombiano polémica reciente',
        'streamer colombiano discusión directo',
    ],
    "Colaboraciones y directos": [
        'streamers colombianos colaboración reciente',
        'streamer colombiano invitado directo',
    ],
    "Creadores emergentes": [
        'streamer colombiano emergente viral',
        'nuevo creador colombiano viral',
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
        c for c in texto
        if unicodedata.category(c) != "Mn"
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
        "short", "shorts", "oficial",
    }
    return {
        p for p in normalizar(texto).split()
        if len(p) > 2 and p not in ignorar
    }


# =====================================================
# FECHAS
# =====================================================

def es_reciente(fecha):
    if not fecha:
        return False

    if fecha.tzinfo is None:
        fecha = fecha.replace(tzinfo=timezone.utc)

    fecha = fecha.astimezone(timezone.utc)
    return LIMITE <= fecha <= AHORA


def fecha_desde_video(video):
    fecha_texto = str(video.get("upload_date") or "")

    if re.fullmatch(r"\d{8}", fecha_texto):
        try:
            return datetime.strptime(
                fecha_texto, "%Y%m%d"
            ).replace(tzinfo=timezone.utc)
        except ValueError:
            pass

    for campo in ("release_timestamp", "timestamp"):
        marca = video.get(campo)
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
# IDENTIFICACIÓN DE CREADORES
# =====================================================

def identificar_creador(texto):
    texto_normalizado = normalizar(texto)

    # Los nombres más largos se revisan primero.
    nombres = sorted(
        STREAMERS.items(),
        key=lambda elemento: max(
            len(normalizar(v)) for v in elemento[1]
        ),
        reverse=True,
    )

    for nombre, variantes in nombres:
        for variante in variantes:
            buscado = normalizar(variante)
            if buscado and buscado in texto_normalizado:
                return nombre

    return ""


def categoria_de(titulo, descripcion=""):
    texto = normalizar(f"{titulo} {descripcion}")

    polemica = [
        "polemica", "pelea", "discusion", "enfrentamiento",
        "indirecta", "responde a", "critica a", "denuncia",
        "controversia",
    ]

    colaboracion = [
        "colaboracion", "colabora", "invitado",
        "juntos en directo", "transmision conjunta",
        "se une a",
    ]

    emergente = [
        "nuevo streamer", "streamer emergente",
        "se vuelve viral", "pequeno streamer",
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
            raiz = ET.fromstring(respuesta.read())

    except Exception as error:
        print(f"Google News no disponible: {consulta}: {error}")
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

        # Las noticias generales también deben mencionar
        # a uno de los creadores que vigilamos.
        if not creador:
            continue

        resultados.append({
            "titulo": titulo,
            "url": enlace,
            "descripcion": descripcion,
            "fecha": fecha,
            "categoria": categoria or categoria_de(
                titulo, descripcion
            ),
            "tipo": "Noticia o publicación indexada",
            "creador": creador,
            "fuente": fuente or "Google News",
        })

    return resultados


# =====================================================
# YOUTUBE: CLIPS DE TERCEROS Y SHORTS
# =====================================================

def buscar_youtube(consulta, creador_objetivo=""):
    comando = [
        sys.executable,
        "-m",
        "yt_dlp",
        "--dump-single-json",
        "--flat-playlist",
        "--no-warnings",
        "--skip-download",
        "--ignore-errors",
        "--playlist-end", "10",
        f"ytsearch10:{consulta}",
    ]

    try:
        proceso = subprocess.run(
            comando,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        print(f"YouTube no disponible ({consulta}): {error}")
        return []

    if proceso.returncode != 0 or not proceso.stdout.strip():
        print(f"YouTube sin respuesta útil: {consulta}")
        return []

    try:
        datos = json.loads(proceso.stdout)
    except json.JSONDecodeError:
        print(f"YouTube devolvió datos no válidos: {consulta}")
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

        if not titulo or not video_id:
            continue

        fecha = fecha_desde_video(video)

        # No inventamos la fecha si YouTube no la entrega.
        if not fecha or not es_reciente(fecha):
            continue

        texto = f"{titulo} {canal}"
        creador = identificar_creador(texto)

        # La búsqueda de un creador debe producir resultados
        # que realmente lo mencionen en el título o canal.
        if creador_objetivo and creador != creador_objetivo:
            continue

        if not creador:
            continue

        resultados.append({
            "titulo": titulo,
            "url": f"https://www.youtube.com/watch?v={video_id}",
            "descripcion": f"Canal que publica: {canal}",
            "fecha": fecha,
            "categoria": categoria_de(titulo, canal),
            "tipo": "Clip o video de YouTube",
            "creador": creador,
            "fuente": "YouTube",
        })

    print(
        f"YouTube: {len(resultados)} válidos "
        f"para la búsqueda '{consulta}'"
    )
    return resultados


# =====================================================
# DEDUPLICACIÓN
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

    if similitud >= 0.84:
        return True

    palabras_a = palabras(titulo_a)
    palabras_b = palabras(titulo_b)
    comunes = palabras_a & palabras_b

    if (
        len(comunes) >= 4
        and len(comunes) / max(
            1, min(len(palabras_a), len(palabras_b))
        ) >= 0.85
    ):
        return True

    # Solo agrupamos títulos diferentes como un mismo suceso
    # cuando el creador coincide y comparten varias palabras.
    creador_a = a.get("creador", "")
    creador_b = b.get("creador", "")

    return bool(
        creador_a
        and creador_a == creador_b
        and len(comunes) >= 5
    )


def eliminar_duplicados(items):
    ordenados = sorted(
        items,
        key=lambda x: x.get("fecha") or LIMITE,
        reverse=True,
    )

    unicos = []

    for item in ordenados:
        existente = next(
            (
                anterior for anterior in unicos
                if anterior.get("url") == item.get("url")
                or mismo_evento(item, anterior)
            ),
            None,
        )

        if existente is None:
            unicos.append(item)

    return unicos


# =====================================================
# SELECCIÓN
# =====================================================

def seleccionar(items):
    items = eliminar_duplicados(items)

    # Los videos se priorizan; después, la fecha más reciente.
    items.sort(
        key=lambda x: (
            x.get("fuente") == "YouTube",
            x.get("fecha") or LIMITE,
        ),
        reverse=True,
    )

    seleccionados = []
    conteos = {}

    for item in items:
        if len(seleccionados) >= MAX_RESULTADOS:
            break

        creador = item.get("creador", "")
        limite_creador = (
            MAX_WESTCOL if creador == "Westcol"
            else MAX_POR_CREADOR
        )

        if creador and conteos.get(creador, 0) >= limite_creador:
            continue

        seleccionados.append(item)

        if creador:
            conteos[creador] = conteos.get(creador, 0) + 1

    return seleccionados


# =====================================================
# INFORME
# =====================================================

def generar_informe(items, candidatos, errores):
    ahora_local = datetime.now(ZONA)

    lineas = [
        "# Radar automático de streamers y clips",
        "",
        f"**Actualizado:** {ahora_local:%d/%m/%Y %I:%M %p}",
        "",
        "- Ventana de búsqueda: últimas 48 horas.",
        f"- Resultados seleccionados: {len(items)} de {MAX_RESULTADOS}.",
        f"- Candidatos recopilados: {candidatos}.",
        "- Máximo de resultados de Westcol: 2.",
        "- Se excluyen resultados sin fecha verificable.",
        "- Se intenta evitar duplicados sin agrupar clips distintos.",
        "",
        "> Este informe reúne resultados indexados de Google News "
        "y YouTube. No representa una búsqueda completa de TikTok.",
        "",
    ]

    if errores:
        lineas.extend([
            "## Avisos de ejecución",
            "",
        ])
        lineas.extend(f"- {error}" for error in errores)
        lineas.append("")

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
            lineas.extend(["Sin resultados verificables.", ""])
            continue

        for item in grupo:
            fecha = item.get("fecha")
            fecha_local = (
                fecha.astimezone(ZONA).strftime("%d/%m %I:%M %p")
                if fecha else "Fecha desconocida"
            )

            titulo = item["titulo"].replace("[", "\\[").replace("]", "\\]")

            lineas.extend([
                f"### [{titulo}]({item['url']})",
                "",
                f"- **Creador mencionado:** {item.get('creador') or 'Sin identificar'}",
                f"- **Fecha:** {fecha_local}",
                f"- **Tipo:** {item.get('tipo', 'Resultado')}",
                f"- **Fuente:** {item.get('fuente', 'No identificada')}",
                "",
            ])

            descripcion = limpiar(item.get("descripcion", ""))
            if descripcion:
                lineas.extend([
                    f"> {descripcion[:400]}",
                    "",
                ])

    lineas.extend([
        "---",
        "",
        "## Creadores vigilados",
        "",
        ", ".join(STREAMERS.keys()),
        "",
        "_Que no haya resultados no significa que no existan clips; "
        "puede indicar que las fuentes no los indexaron, que no "
        "entregaron una fecha verificable o que falló una búsqueda._",
        "",
    ])

    return "\n".join(lineas)


# =====================================================
# EJECUCIÓN
# =====================================================

def main():
    print("=" * 55)
    print("INICIANDO RADAR DE CREADORES")
    print(f"Hora UTC: {AHORA:%Y-%m-%d %H:%M}")
    print("Ventana: últimas 48 horas")
    print("=" * 55)

    candidatos = []
    errores = []

    # 1. Búsquedas generales de noticias.
    for categoria, consultas in BUSQUEDAS_GENERALES.items():
        for consulta in consultas:
            print(f"Google News [{categoria}]: {consulta}")
            resultados = buscar_google_news(consulta, categoria)
            candidatos.extend(resultados)

    # 2. Búsquedas de noticias por creador.
    for nombre, variantes in STREAMERS.items():
        nombre_busqueda = variantes[0]

        consulta = f'"{nombre_busqueda}" (clip OR viral OR streamer)'
        print(f"Google News [{nombre}]: {consulta}")

        resultados = buscar_google_news(consulta)
        candidatos.extend(resultados)

    # 3. Búsqueda de videos publicados por terceros.
    # Se usan términos que suelen aparecer en títulos de clips.
    for nombre, variantes in STREAMERS.items():
        nombre_busqueda = variantes[0]

        consultas = [
            f'"{nombre_busqueda}" clip',
            f'"{nombre_busqueda}" shorts momentos',
        ]

        for consulta in consultas:
            print(f"YouTube [{nombre}]: {consulta}")
            candidatos.extend(
                buscar_youtube(consulta, nombre)
            )
            time.sleep(1)

    print("-" * 55)
    print(f"Candidatos antes de deduplicar: {len(candidatos)}")

    filtrados = []
    for item in candidatos:
        if not item.get("creador"):
            item["creador"] = identificar_creador(
                f"{item.get('titulo', '')} "
                f"{item.get('descripcion', '')}"
            )

        if item.get("creador") and es_reciente(item.get("fecha")):
            filtrados.append(item)

    print(f"Candidatos con fecha y creador: {len(filtrados)}")

    seleccionados = seleccionar(filtrados)
    print(f"Resultados finales: {len(seleccionados)}")

    informe = generar_informe(
        seleccionados,
        len(candidatos),
        errores,
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
