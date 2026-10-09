import html
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

import requests
import xml.etree.ElementTree as ET

COLOMBIA = timezone(timedelta(hours=-5))
AHORA = datetime.now(COLOMBIA)
LIMITE = AHORA - timedelta(hours=48)
MAX_RESULTADOS = 25
MAX_WESTCOL = 2
MAX_POR_CREADOR = 3
MAX_NOTICIAS = 15
PAUSA_SEGUNDOS = 1
CARPETA = Path("borradores")
SALIDA = CARPETA / "radar_creadores.md"

CREADORES = [
    "Westcol", "MrStivenTC", "Pelicanger", "Samulx", "Chanty",
    "La Sapa", "Lonche de Huevito", "Rey de la City",
]
EMERGENTES = ["streamer colombiano Kick", "streamer colombiano viral", "clips streamers Colombia"]
CABECERAS = {"User-Agent": "Mozilla/5.0 (compatible; RadarPublico/2.0)"}


def limpiar(texto):
    return re.sub(r"\s+", " ", html.unescape(texto or "")).strip()


def fecha_youtube(video):
    fecha = video.get("release_timestamp") or video.get("timestamp")
    if fecha:
        try:
            return datetime.fromtimestamp(float(fecha), tz=timezone.utc).astimezone(COLOMBIA)
        except (ValueError, TypeError, OverflowError, OSError):
            pass
    fecha_texto = video.get("upload_date")
    if fecha_texto and re.fullmatch(r"\d{8}", str(fecha_texto)):
        try:
            return datetime.strptime(fecha_texto, "%Y%m%d").replace(tzinfo=COLOMBIA)
        except ValueError:
            pass
    return None


def dentro_de_ventana(fecha):
    return fecha is not None and LIMITE <= fecha <= AHORA


def buscar_youtube(consulta, max_items=8):
    """Usa yt-dlp para buscar metadatos pÃºblicos; nunca descarga el video."""
    comando = [
        sys.executable, "-m", "yt_dlp", "--dump-single-json", "--skip-download",
        "--no-warnings", "--ignore-errors", "--playlist-end", str(max_items),
        f"ytsearchdate{max_items}:{consulta}",
    ]
    try:
        proceso = subprocess.run(comando, capture_output=True, text=True, timeout=90)
        if proceso.returncode != 0 and not proceso.stdout.strip():
            mensaje = limpiar((proceso.stderr or "")[-500:])
            print(f"YouTube no disponible para '{consulta}': {mensaje}")
            return []
        datos = None
        try:
            datos = __import__("json").loads(proceso.stdout)
        except Exception:
            # Algunas versiones imprimen objetos JSON por lÃ­nea.
            entradas = []
            for linea in (proceso.stdout or "").splitlines():
                try:
                    entradas.append(__import__("json").loads(linea))
                except Exception:
                    continue
            datos = {"entries": entradas}
        videos = datos.get("entries", []) if isinstance(datos, dict) else []
        resultados = []
        for video in videos:
            if not video:
                continue
            fecha = fecha_youtube(video)
            enlace = video.get("webpage_url") or video.get("original_url")
            video_id = video.get("id")
            if not enlace and video_id:
                enlace = f"https://www.youtube.com/watch?v={video_id}"
            if not enlace or not dentro_de_ventana(fecha):
                continue
            resultados.append({
                "titulo": limpiar(video.get("title") or "Video sin tÃ­tulo"),
                "url": enlace,
                "canal": limpiar(video.get("channel") or video.get("uploader") or "Canal no identificado"),
                "fecha": fecha,
                "creador": "",
                "fuente": "BÃºsqueda pÃºblica de YouTube (yt-dlp)",
            })
        return resultados
    except subprocess.TimeoutExpired:
        print(f"Tiempo agotado buscando YouTube: {consulta}")
    except Exception as error:
        print(f"Error buscando YouTube ({consulta}): {error}")
    return []


def buscar_noticias(consulta):
    parametros = {"q": f"{consulta} when:2d", "hl": "es-419", "gl": "CO", "ceid": "CO:es-419"}
    url = "https://news.google.com/rss/search?" + requests.compat.urlencode(parametros)
    resultados = []
    try:
        respuesta = requests.get(url, headers=CABECERAS, timeout=25)
        respuesta.raise_for_status()
        raiz = ET.fromstring(respuesta.content)
        for item in raiz.findall(".//item"):
            titulo = limpiar(item.findtext("title", ""))
            enlace = (item.findtext("link", "") or "").strip()
            pubdate = item.findtext("pubDate", "")
            try:
                fecha = parsedate_to_datetime(pubdate).astimezone(COLOMBIA)
            except (ValueError, TypeError, OverflowError):
                fecha = None
            if titulo and enlace and dentro_de_ventana(fecha):
                resultados.append({"titulo": titulo, "url": enlace, "fecha": fecha, "creador": "", "fuente": "Google News RSS"})
    except Exception as error:
        print(f"Error en Google News ({consulta}): {error}")
    return resultados


def recopilar_clips():
    encontrados = []
    consultas = [(creador, f'{creador} clips') for creador in CREADORES]
    consultas += [(creador, f'{creador} shorts') for creador in CREADORES]
    consultas += [("Emergentes Colombia", q) for q in EMERGENTES]
    for indice, (creador, consulta) in enumerate(consultas, 1):
        print(f"[{indice}/{len(consultas)}] Buscando: {consulta}")
        for video in buscar_youtube(consulta):
            video["creador"] = creador
            encontrados.append(video)
    unicos = {}
    for video in encontrados:
        clave = video["url"].split("&", 1)[0].rstrip("/")
        unicos.setdefault(clave, video)
    return list(unicos.values())


def seleccionar_clips(videos):
    videos.sort(key=lambda v: v["fecha"], reverse=True)
    seleccionados, conteo = [], {}
    for video in videos:
        if len(seleccionados) >= MAX_RESULTADOS:
            break
        creador = video["creador"]
        limite = MAX_WESTCOL if creador.lower() == "westcol" else MAX_POR_CREADOR
        if conteo.get(creador, 0) >= limite:
            continue
        seleccionados.append(video)
        conteo[creador] = conteo.get(creador, 0) + 1
    return seleccionados


def recopilar_noticias():
    consultas = [f'"{creador}" streamer OR directo OR polÃ©mica' for creador in CREADORES]
    consultas += ['streamer colombiano Kick viral', 'creador de contenido colombiano streamer']
    candidatas = []
    for consulta in consultas:
        print(f"Google News: {consulta}")
        candidatas.extend(buscar_noticias(consulta))
    unicas = {}
    for noticia in candidatas:
        unicas.setdefault(noticia["url"], noticia)
    ordenadas = sorted(unicas.values(), key=lambda n: n["fecha"], reverse=True)
    # Diversidad editorial: mÃ¡ximo dos noticias por creador detectado en el tÃ­tulo.
    elegidas, conteo = [], {}
    for noticia in ordenadas:
        titulo = noticia["titulo"].lower()
        creador_detectado = next((c for c in CREADORES if c.lower() in titulo), "Otros")
        if conteo.get(creador_detectado, 0) >= 2:
            continue
        elegidas.append(noticia)
        conteo[creador_detectado] = conteo.get(creador_detectado, 0) + 1
        if len(elegidas) >= MAX_NOTICIAS:
            break
    return elegidas


def escribir_informe(clips, noticias):
    CARPETA.mkdir(parents=True, exist_ok=True)
    lineas = [
        "# Radar automÃ¡tico de creadores y clips", "",
        f"Actualizado: {AHORA.strftime('%d/%m/%Y %I:%M %p')} (hora de Colombia)", "",
        "Ventana objetivo: Ãºltimas 48 horas.",
        f"Clips candidatos encontrados: {len(clips)}.",
        f"Noticias recientes encontradas: {len(noticias)}.", "",
        "> Radar gratuito basado en metadatos pÃºblicos. La bÃºsqueda puede ser bloqueada o limitada por YouTube; confirma los enlaces y los derechos antes de publicar.", "",
        "## Clips y Shorts candidatos de YouTube", "",
    ]
    if clips:
        for video in clips:
            lineas.extend([
                f"### {video['titulo']}", f"- BÃºsqueda/creador: {video['creador']}",
                f"- Canal que publicÃ³: {video['canal']}",
                f"- Publicado: {video['fecha'].strftime('%d/%m/%Y %I:%M %p')}",
                f"- Fuente: {video['fuente']}", f"- Enlace directo: {video['url']}", "",
            ])
    else:
        lineas.extend([
            "No se encontraron videos verificables dentro de las Ãºltimas 48 horas.",
            "La bÃºsqueda de YouTube puede estar bloqueada para el entorno de GitHub Actions. Revisa los registros del workflow; no se inventan resultados.", "",
        ])
    lineas.extend(["## Noticias y contexto (no son necesariamente clips)", ""])
    if noticias:
        for noticia in noticias:
            lineas.append(f"- **{noticia['titulo']}** â {noticia['fecha'].strftime('%d/%m/%Y %I:%M %p')} â [Abrir fuente]({noticia['url']})")
        lineas.append("")
    else:
        lineas.extend(["No se encontraron noticias recientes en Google News RSS.", ""])
    lineas.extend([
        "## Creadores vigilados", "", ", ".join(CREADORES), "",
        "## Criterios", "", f"- MÃ¡ximo de clips: {MAX_RESULTADOS}.",
        f"- MÃ¡ximo de Westcol: {MAX_WESTCOL}.", f"- MÃ¡ximo por otra bÃºsqueda/creador: {MAX_POR_CREADOR}.",
        "- Ventana temporal: 48 horas.", "- DeduplicaciÃ³n por enlace.",
        "- Las noticias se muestran por separado y se limita la repeticiÃ³n por creador.",
        "- Se incluyen bÃºsquedas exploratorias de streamers emergentes colombianos.", "",
        "## Limitaciones", "",
        "La bÃºsqueda no garantiza cobertura exhaustiva de Kick o TikTok. El archivo de TikTok mantiene las fuentes RSS que estÃ©n configuradas; actualmente hay que aÃ±adir feeds vÃ¡lidos para ampliar esa plataforma.",
        "No descargues ni republices videos ajenos sin permiso. AÃ±ade comentario, anÃ¡lisis o contexto original y revisa las polÃ­ticas de monetizaciÃ³n de cada plataforma.", "",
    ])
    SALIDA.write_text("\n".join(lineas), encoding="utf-8")
    print(f"Informe guardado: {SALIDA} | clips: {len(clips)} | noticias: {len(noticias)}")


def main():
    print("=" * 55)
    print("RADAR GRATUITO DE CREADORES")
    print(f"Hora Colombia: {AHORA.strftime('%d/%m/%Y %I:%M %p')}")
    print(f"Ventana desde: {LIMITE.strftime('%d/%m/%Y %I:%M %p')}")
    print("=" * 55)
    clips = seleccionar_clips(recopilar_clips())
    noticias = recopilar_noticias()
    escribir_informe(clips, noticias)


if __name__ == "__main__":
    main()
