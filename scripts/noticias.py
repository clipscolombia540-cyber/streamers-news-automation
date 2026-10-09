
import json
import re
import subprocess
import sys
import time
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote_plus

# ==========================================================
# CONFIGURACION DEL RADAR
# ==========================================================

COLOMBIA = timezone(timedelta(hours=-5))
AHORA = datetime.now(COLOMBIA)
LIMITE = AHORA - timedelta(hours=48)

MAX_RESULTADOS = 25
MAX_WESTCOL = 2
MAX_POR_CREADOR = 3
RESULTADOS_POR_BUSQUEDA = 10
PAUSA_ENTRE_BUSQUEDAS = 2

CARPETA = Path("borradores")
ARCHIVO_SALIDA = CARPETA / "radar_creadores.md"

# Enfoque inicial: creadores colombianos.
# No se incluyen perfiles que no estén en esta lista.
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

# Se buscan publicaciones de terceros, clips y Shorts.
BUSQUEDAS = [
    '"{creador}" clips',
    '"{creador}" shorts',
]

# ==========================================================
# UTILIDADES
# ==========================================================

def normalizar(texto):
    texto = unicodedata.normalize("NFKD", str(texto or ""))
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", texto.lower()).strip()


def fecha_publicacion(video):
    """
    Devuelve una fecha verificable si yt-dlp proporciona
    timestamp o upload_date.

    Si solo hay fecha sin hora, se conserva como fecha
    aproximada y no se inventa una hora.
    """
    timestamp = video.get("release_timestamp")
    if timestamp is None:
        timestamp = video.get("timestamp")

    if timestamp is not None:
        try:
            fecha = datetime.fromtimestamp(
                float(timestamp), tz=timezone.utc
            ).astimezone(COLOMBIA)
            return fecha, True
        except (ValueError, TypeError, OverflowError, OSError):
            pass

    upload_date = video.get("upload_date")
    if upload_date:
        try:
            fecha = datetime.strptime(
                str(upload_date), "%Y%m%d"
            ).replace(tzinfo=COLOMBIA)
            return fecha, False
        except ValueError:
            pass

    return None, False


def dentro_de_ventana(fecha, tiene_hora):
    if fecha is None:
        return False

    if tiene_hora:
        return LIMITE <= fecha <= AHORA

    # Una fecha sin hora no permite comprobar con exactitud
    # el límite de 48 horas. Solo se acepta el día actual
    # o el anterior; el informe lo marcará como aproximado.
    return (
        fecha.date() >= LIMITE.date()
        and fecha.date() <= AHORA.date()
    )


def formatear_fecha(fecha, tiene_hora):
    if tiene_hora:
        return fecha.strftime("%d/%m/%Y %I:%M %p")

    return fecha.strftime("%d/%m/%Y") + " (hora no disponible)"


def obtener_url(video):
    url = video.get("webpage_url") or video.get("original_url")

    if url and url.startswith("https://"):
        return url

    video_id = video.get("id")
    if video_id:
        return f"https://www.youtube.com/watch?v={video_id}"

    return None


def clave_video(video):
    video_id = video.get("id")
    if video_id:
        return str(video_id)

    url = obtener_url(video)
    if url:
        return url.split("&")[0]

    return normalizar(video.get("title", ""))


def parece_clip(video):
    """
    Reduce resultados que parecen videos completos o noticias.
    No garantiza que un video tenga derechos de reutilización.
    """
    titulo = normalizar(video.get("title", ""))
    canal = normalizar(video.get("channel") or video.get("uploader") or "")

    palabras_clip = (
        "clip", "clips", "short", "shorts", "momento",
        "momentos", "viral", "stream", "directo", "reaccion"
    )

    es_corto = video.get("duration") is not None and video.get("duration", 0) <= 180
    tiene_palabra = any(p in titulo for p in palabras_clip)
    canal_de_clips = any(
        p in canal for p in ("clips", "shorts", "momentos")
    )

    return es_corto or tiene_palabra or canal_de_clips


# ==========================================================
# BUSQUEDA YOUTUBE
# ==========================================================

def buscar_youtube(consulta):
    """
    Usa ytsearchdate para priorizar resultados recientes.
    No utiliza --flat-playlist: intenta obtener los metadatos
    completos de cada video para poder comprobar la fecha.
    """
    comando = [
        sys.executable,
        "-m",
        "yt_dlp",
        "--dump-single-json",
        "--skip-download",
        "--no-warnings",
        "--ignore-errors",
        "--playlist-end",
        str(RESULTADOS_POR_BUSQUEDA),
        "ytsearchdate" + str(RESULTADOS_POR_BUSQUEDA) + ":" + consulta,
    ]

    try:
        proceso = subprocess.run(
            comando,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )

        if proceso.returncode != 0 and not proceso.stdout.strip():
            mensaje = (proceso.stderr or "").strip()
            print(f"Advertencia en búsqueda: {consulta}: {mensaje[:250]}")
            return []

        salida = proceso.stdout.strip()
        if not salida:
            return []

        datos = json.loads(salida)

        if isinstance(datos, dict):
            entradas = datos.get("entries")
            if entradas is not None:
                return [v for v in entradas if isinstance(v, dict)]
            return [datos] if datos.get("id") else []

        return []

    except subprocess.TimeoutExpired:
        print(f"Tiempo agotado en: {consulta}")
    except json.JSONDecodeError:
        print(f"No se pudo interpretar la respuesta de: {consulta}")
    except Exception as error:
        print(f"Error buscando {consulta}: {error}")

    return []


def recopilar_videos():
    candidatos = []
    vistos = set()

    total_busquedas = len(CREADORES) * len(BUSQUEDAS)
    numero_busqueda = 0

    for creador in CREADORES:
        for plantilla in BUSQUEDAS:
            numero_busqueda += 1
            consulta = plantilla.format(creador=creador)

            print(
                f"[{numero_busqueda}/{total_busquedas}] "
                f"Buscando {consulta}"
            )

            videos = buscar_youtube(consulta)

            for video in videos:
                video_id = clave_video(video)
                if not video_id or video_id in vistos:
                    continue

                vistos.add(video_id)

                fecha, tiene_hora = fecha_publicacion(video)
                if not dentro_de_ventana(fecha, tiene_hora):
                    continue

                url = obtener_url(video)
                titulo = (video.get("title") or "").strip()

                if not url or not titulo:
                    continue

                # Las búsquedas están hechas para este creador.
                # Se etiqueta como candidato asociado, sin afirmar
                # que sea oficial ni que tenga permiso de reutilización.
                candidatos.append({
                    "id": video_id,
                    "creador": creador,
                    "titulo": titulo,
                    "url": url,
                    "canal": (
                        video.get("channel")
                        or video.get("uploader")
                        or "Canal no identificado"
                    ),
                    "fecha": fecha,
                    "tiene_hora": tiene_hora,
                    "duracion": video.get("duration"),
                    "es_clip": parece_clip(video),
                    "vistas": video.get("view_count"),
                })

            time.sleep(PAUSA_ENTRE_BUSQUEDAS)

    return candidatos


# ==========================================================
# FILTRADO, ORDEN Y DEDUPLICACION
# ==========================================================

def seleccionar_resultados(candidatos):
    # Prioriza clips y Shorts; después, los demás videos recientes.
    candidatos.sort(
        key=lambda v: (
            not v["es_clip"],
            v["fecha"] or datetime.min.replace(tzinfo=COLOMBIA),
        ),
        reverse=False,
    )

    # Reordenar dentro de cada grupo por fecha descendente.
    clips = [v for v in candidatos if v["es_clip"]]
    otros = [v for v in candidatos if not v["es_clip"]]

    clips.sort(key=lambda v: v["fecha"], reverse=True)
    otros.sort(key=lambda v: v["fecha"], reverse=True)

    seleccionados = []
    conteo = {}

    for video in clips + otros:
        if len(seleccionados) >= MAX_RESULTADOS:
            break

        creador = video["creador"]
        limite_creador = (
            MAX_WESTCOL if normalizar(creador) == "westcol"
            else MAX_POR_CREADOR
        )

        if conteo.get(creador, 0) >= limite_creador:
            continue

        seleccionados.append(video)
        conteo[creador] = conteo.get(creador, 0) + 1

    return seleccionados


# ==========================================================
# GENERACION DEL INFORME
# ==========================================================

def escribir_informe(candidatos, seleccionados):
    CARPETA.mkdir(parents=True, exist_ok=True)

    lineas = [
        "# Radar automático de creadores y clips",
        "",
        f"Actualizado: {AHORA.strftime('%d/%m/%Y %I:%M %p')} "
        "(hora de Colombia)",
        "",
        "Ventana objetivo: últimas 48 horas.",
        f"Videos encontrados con fecha utilizable: {len(candidatos)}.",
        f"Resultados seleccionados: {len(seleccionados)} "
        f"de un máximo de {MAX_RESULTADOS}.",
        "",
        "> Este radar encuentra candidatos públicos de YouTube. "
        "No confirma que el contenido sea reutilizable, que el canal "
        "sea oficial ni que el video pueda monetizarse.",
        "",
    ]

    clips = [v for v in seleccionados if v["es_clip"]]
    otros = [v for v in seleccionados if not v["es_clip"]]

    lineas.extend([
        "## Clips y Shorts candidatos",
        "",
    ])

    if clips:
        for video in clips:
            fecha = formatear_fecha(
                video["fecha"], video["tiene_hora"]
            )
            lineas.extend([
                f"### {video['titulo']}",
                f"- Creador asociado a la búsqueda: {video['creador']}",
                f"- Canal que publicó: {video['canal']}",
                f"- Publicación: {fecha}",
                f"- Enlace original: {video['url']}",
                "",
            ])
    else:
        lineas.extend([
            "No se encontraron clips con fechas utilizables "
            "en las búsquedas realizadas.",
            "",
        ])

    lineas.extend([
        "## Otros videos recientes relacionados",
        "",
    ])

    if otros:
        for video in otros:
            fecha = formatear_fecha(
                video["fecha"], video["tiene_hora"]
            )
            lineas.extend([
                f"- **{video['titulo']}** — {video['creador']} "
                f"— {fecha} — [Ver video]({video['url']})",
            ])
        lineas.append("")
    else:
        lineas.extend([
            "No se encontraron otros videos para esta sección.",
            "",
        ])

    lineas.extend([
        "## Creadores vigilados",
        "",
        ", ".join(CREADORES),
        "",
        "## Límites aplicados",
        "",
        f"- Máximo total: {MAX_RESULTADOS}.",
        f"- Máximo de Westcol: {MAX_WESTCOL}.",
        f"- Máximo por cada otro creador: {MAX_POR_CREADOR}.",
        "- Duplicados por ID o enlace: eliminados.",
        "- Sin fecha de publicación utilizable: excluidos.",
        "- Fechas sin hora exacta: identificadas como aproximadas.",
        "",
        "## Nota sobre cobertura",
        "",
        "La búsqueda utiliza resultados públicos de YouTube. "
        "No representa una búsqueda exhaustiva de TikTok ni de "
        "todas las cuentas de terceros.",
        "",
    ])

    ARCHIVO_SALIDA.write_text(
        "\n".join(lineas),
        encoding="utf-8",
    )

    print(f"\nInforme guardado en: {ARCHIVO_SALIDA}")
    print(f"Candidatos con fecha: {len(candidatos)}")
    print(f"Resultados seleccionados: {len(seleccionados)}")


def main():
    print("=" * 55)
    print("RADAR DE CREADORES Y CLIPS")
    print(f"Hora Colombia: {AHORA.strftime('%d/%m/%Y %I:%M %p')}")
    print(f"Desde: {LIMITE.strftime('%d/%m/%Y %I:%M %p')}")
    print("=" * 55)

    candidatos = recopilar_videos()
    seleccionados = seleccionar_resultados(candidatos)
    escribir_informe(candidatos, seleccionados)


if __name__ == "__main__":
    main()
