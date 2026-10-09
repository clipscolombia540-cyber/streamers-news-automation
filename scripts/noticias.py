
import os
import re
import json
import time
import html
import urllib.parse
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET

from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from pathlib import Path
from zoneinfo import ZoneInfo


# =========================
# CONFIGURACIÓN DEL RADAR
# =========================

HORAS_MAXIMAS = 48
MAX_TITULARES = 25
MAX_POR_CREADOR = 3
MAX_WESTCOL = 2

CARPETA_SALIDA = Path("borradores")
ZONA_COLOMBIA = ZoneInfo("America/Bogota")

YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "").strip()

TWITCH_CLIENT_ID = os.getenv("TWITCH_CLIENT_ID", "").strip()
TWITCH_CLIENT_SECRET = os.getenv("TWITCH_CLIENT_SECRET", "").strip()
TWITCH_BROADCASTER_IDS = [
    x.strip()
    for x in os.getenv("TWITCH_BROADCASTER_IDS", "").split(",")
    if x.strip()
]

# Lista semilla: ayuda a reconocer nombres conocidos.
# No representa a todos los creadores colombianos.
CREADORES_CONOCIDOS = [
    "Westcol",
    "Juan Guarnizo",
    "La Liendra",
    "Yeferson Cossio",
    "Dani Duke",
    "Luisa Fernanda W",
    "Aida Victoria Merlano",
    "Pelicanger",
    "Mr Stiven",
    "Spreen",
    "Dalas",
    "TheDonato",
    "AuronPlay",
    "Ami Rodriguez",
    "Kika Nieto",
    "Pautips",
    "Calle y Poche",
]

# Consultas variadas para no depender de un solo nombre.
BUSQUEDAS_YOUTUBE = [
    "streamer colombiano",
    "streamers colombianos clips",
    "creadores colombianos viral",
    "tiktoker colombiano viral",
]

BUSQUEDAS_NOTICIAS = [
    '"streamer colombiano"',
    '"creadores de contenido colombianos"',
    '"influencer colombiano" viral',
    '"YouTuber colombiano"',
    '"TikTok Colombia" creador viral',
    '"Westcol" OR "Pelicanger" OR "Mr Stiven"',
]


# =========================
# UTILIDADES
# =========================

def ahora_utc():
    return datetime.now(timezone.utc)


def fecha_iso(dt):
    return dt.astimezone(timezone.utc).isoformat(
        timespec="seconds"
    ).replace("+00:00", "Z")


def parsear_fecha(valor):
    if not valor:
        return None

    try:
        dt = datetime.fromisoformat(
            valor.replace("Z", "+00:00")
        )
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (ValueError, TypeError):
        return None


def texto_limpio(valor):
    valor = html.unescape(str(valor or ""))
    valor = re.sub(r"<[^>]+>", " ", valor)
    return re.sub(r"\s+", " ", valor).strip()


def clave_texto(valor):
    valor = texto_limpio(valor).lower()
    valor = re.sub(r"https?://\S+", " ", valor)
    valor = re.sub(r"[^a-z0-9áéíóúüñ ]", " ", valor)
    palabras = [
        p for p in valor.split()
        if p not in {
            "el", "la", "los", "las", "de", "del",
            "un", "una", "en", "con", "por", "para",
            "que", "se", "su", "sus", "y", "a"
        }
    ]
    return " ".join(palabras)


def es_reciente(fecha, limite):
    return fecha is not None and limite <= fecha <= ahora_utc()


def detectar_creador(texto):
    texto = texto.lower()

    # Primero se detectan nombres conocidos.
    for nombre in sorted(
        CREADORES_CONOCIDOS, key=len, reverse=True
    ):
        if nombre.lower() in texto:
            return nombre

    # Los demás se mantienen como descubrimientos,
    # no se inventa el nombre de un creador.
    return "Por descubrir"


def es_probablemente_colombiano(texto):
    texto = texto.lower()

    señales = [
        "colombia",
        "colombiano",
        "colombiana",
        "colombianos",
        "colombianas",
        "bogotá",
        "medellín",
        "cali,",
        "barranquilla",
        "bucaramanga",
        "manizales",
        "cartagena",
    ]

    return any(s in texto for s in señales)


def crear_registro(
    titulo,
    url,
    fuente,
    fecha,
    canal="",
    consulta="",
    creador=None,
):
    titulo = texto_limpio(titulo)
    if not titulo or not url or not fecha:
        return None

    identificador = (
        url.split("?", 1)[0].rstrip("/")
        if "youtube.com/watch" not in url
        else url
    )

    texto = f"{titulo} {canal} {consulta}"
    creador_detectado = creador or detectar_creador(texto)

    return {
        "titulo": titulo,
        "url": url,
        "id": identificador,
        "fuente": fuente,
        "fecha": fecha,
        "canal": texto_limpio(canal),
        "consulta": consulta,
        "creador": creador_detectado,
        "texto": texto,
    }


def pedir_json(url, headers=None, data=None):
    req = urllib.request.Request(
        url,
        headers=headers or {},
        data=data,
        method="POST" if data is not None else "GET",
    )

    with urllib.request.urlopen(req, timeout=25) as respuesta:
        contenido = respuesta.read().decode("utf-8", "replace")
        return json.loads(contenido)


# =========================
# YOUTUBE DATA API
# =========================

def buscar_youtube(limite):
    resultados = []

    if not YOUTUBE_API_KEY:
        print(
            "YouTube: omitido. Falta el secreto YOUTUBE_API_KEY."
        )
        return resultados

    for consulta in BUSQUEDAS_YOUTUBE:
        parametros = {
            "part": "snippet",
            "type": "video",
            "q": consulta,
            "regionCode": "CO",
            "relevanceLanguage": "es",
            "order": "date",
            "publishedAfter": fecha_iso(limite),
            "maxResults": 15,
            "key": YOUTUBE_API_KEY,
        }

        url = (
            "https://www.googleapis.com/youtube/v3/search?"
            + urllib.parse.urlencode(parametros)
        )

        try:
            datos = pedir_json(url)

            for item in datos.get("items", []):
                video_id = item.get("id", {}).get("videoId")
                snippet = item.get("snippet", {})

                if not video_id:
                    continue

                titulo = snippet.get("title", "")
                canal = snippet.get("channelTitle", "")
                fecha = parsear_fecha(
                    snippet.get("publishedAt", "")
                )

                if not es_reciente(fecha, limite):
                    continue

                # Las consultas ya están orientadas a Colombia,
                # pero se exige una señal colombiana o un nombre
                # reconocido para reducir resultados internacionales.
                texto = f"{titulo} {canal} {consulta}"
                if not (
                    es_probablemente_colombiano(texto)
                    or detectar_creador(texto) != "Por descubrir"
                    or "colombiano" in consulta
                    or "colombianos" in consulta
                ):
                    continue

                registro = crear_registro(
                    titulo=titulo,
                    url=f"https://www.youtube.com/watch?v={video_id}",
                    fuente="YouTube",
                    fecha=fecha,
                    canal=canal,
                    consulta=consulta,
                )

                if registro:
                    resultados.append(registro)

            # Pausa pequeña para no lanzar solicitudes seguidas.
            time.sleep(1)

        except urllib.error.HTTPError as error:
            print(
                f"YouTube ({consulta}): HTTP {error.code}"
            )
            if error.code == 403:
                print(
                    "Revisa la clave, los permisos y la cuota de API."
                )
        except Exception as error:
            print(f"YouTube ({consulta}): {error}")

    return resultados


# =========================
# GOOGLE NEWS RSS
# =========================

def buscar_google_news(limite):
    resultados = []

    for consulta in BUSQUEDAS_NOTICIAS:
        parametros = {
            "q": consulta,
            "hl": "es-419",
            "gl": "CO",
            "ceid": "CO:es-419",
        }

        url = (
            "https://news.google.com/rss/search?"
            + urllib.parse.urlencode(parametros)
        )

        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 (compatible; RadarCreadores/1.0)"
                },
            )

            with urllib.request.urlopen(req, timeout=25) as respuesta:
                xml = respuesta.read()

            raiz = ET.fromstring(xml)

            for item in raiz.findall(".//item"):
                titulo = item.findtext("title", "")
                enlace = item.findtext("link", "")
                fecha_texto = item.findtext("pubDate", "")
                fuente = item.findtext("source", "Google News")

                try:
                    from email.utils import parsedate_to_datetime
                    fecha = parsedate_to_datetime(fecha_texto)
                    if fecha.tzinfo is None:
                        fecha = fecha.replace(tzinfo=timezone.utc)
                    fecha = fecha.astimezone(timezone.utc)
                except Exception:
                    fecha = None

                if not es_reciente(fecha, limite):
                    continue

                texto = f"{titulo} {consulta}"

                # Evita noticias claramente ajenas al radar.
                if not (
                    es_probablemente_colombiano(texto)
                    or detectar_creador(texto) != "Por descubrir"
                    or "colombiano" in consulta
                    or "colombianos" in consulta
                ):
                    continue

                registro = crear_registro(
                    titulo=titulo,
                    url=enlace,
                    fuente=f"Google News — {fuente}",
                    fecha=fecha,
                    consulta=consulta,
                )

                if registro:
                    resultados.append(registro)

            time.sleep(1)

        except Exception as error:
            print(f"Google News ({consulta}): {error}")

    return resultados


# =========================
# TWITCH CLIPS API OPCIONAL
# =========================

def obtener_token_twitch():
    if not TWITCH_CLIENT_ID or not TWITCH_CLIENT_SECRET:
        return None

    datos = urllib.parse.urlencode({
        "client_id": TWITCH_CLIENT_ID,
        "client_secret": TWITCH_CLIENT_SECRET,
        "grant_type": "client_credentials",
    }).encode()

    respuesta = pedir_json(
        "https://id.twitch.tv/oauth2/token",
        headers={
            "Content-Type": "application/x-www-form-urlencoded"
        },
        data=datos,
    )

    return respuesta.get("access_token")


def buscar_twitch(limite):
    resultados = []

    if not (
        TWITCH_CLIENT_ID
        and TWITCH_CLIENT_SECRET
        and TWITCH_BROADCASTER_IDS
    ):
        print(
            "Twitch: omitido. Configura credenciales e IDs de canales."
        )
        return resultados

    try:
        token = obtener_token_twitch()
        if not token:
            return resultados

        headers = {
            "Client-Id": TWITCH_CLIENT_ID,
            "Authorization": f"Bearer {token}",
        }

        inicio = fecha_iso(limite)
        fin = fecha_iso(ahora_utc())

        for broadcaster_id in TWITCH_BROADCASTER_IDS:
            parametros = {
                "broadcaster_id": broadcaster_id,
                "started_at": inicio,
                "ended_at": fin,
                "first": 20,
            }

            url = (
                "https://api.twitch.tv/helix/clips?"
                + urllib.parse.urlencode(parametros)
            )

            datos = pedir_json(url, headers=headers)

            for clip in datos.get("data", []):
                fecha = parsear_fecha(
                    clip.get("created_at", "")
                )
                if not es_reciente(fecha, limite):
                    continue

                titulo = clip.get("title", "Clip de Twitch")
                creador = clip.get(
                    "broadcaster_name", "Canal de Twitch"
                )

                registro = crear_registro(
                    titulo=titulo,
                    url=clip.get("url", ""),
                    fuente="Twitch Clips",
                    fecha=fecha,
                    canal=creador,
                    creador=creador,
                )

                if registro:
                    resultados.append(registro)

    except Exception as error:
        print(f"Twitch: {error}")

    return resultados


# =========================
# DEDUPLICACIÓN Y EQUILIBRIO
# =========================

def son_duplicados(a, b):
    if a["id"] == b["id"]:
        return True

    titulo_a = clave_texto(a["titulo"])
    titulo_b = clave_texto(b["titulo"])

    if not titulo_a or not titulo_b:
        return False

    similitud = SequenceMatcher(
        None, titulo_a, titulo_b
    ).ratio()

    # Coincidencia de títulos casi idénticos.
    if similitud >= 0.84:
        return True

    # Detecta títulos con muchas palabras en común,
    # aunque cambie el orden.
    palabras_a = set(titulo_a.split())
    palabras_b = set(titulo_b.split())

    if len(palabras_a) >= 5 and len(palabras_b) >= 5:
        interseccion = len(palabras_a & palabras_b)
        union = len(palabras_a | palabras_b)

        if union and interseccion / union >= 0.78:
            return True

    return False


def quitar_duplicados(registros):
    # Primero los más recientes.
    registros = sorted(
        registros,
        key=lambda x: x["fecha"],
        reverse=True,
    )

    unicos = []

    for registro in registros:
        if any(
            son_duplicados(registro, existente)
            for existente in unicos
        ):
            continue

        unicos.append(registro)

    return unicos


def limitar_por_creador(registros):
    conteo = {}
    seleccionados = []

    # Primera pasada: repartir entre creadores.
    for registro in registros:
        creador = registro["creador"]
        clave = creador.lower()

        limite = (
            MAX_WESTCOL
            if "westcol" in clave
            else MAX_POR_CREADOR
        )

        if conteo.get(clave, 0) >= limite:
            continue

        seleccionados.append(registro)
        conteo[clave] = conteo.get(clave, 0) + 1

        if len(seleccionados) >= MAX_TITULARES:
            break

    return seleccionados


# =========================
# INFORME MARKDOWN
# =========================

def generar_informe(registros):
    ahora_local = datetime.now(ZONA_COLOMBIA)
    fecha_archivo = ahora_local.strftime("%Y-%m-%d")

    CARPETA_SALIDA.mkdir(parents=True, exist_ok=True)
    ruta = CARPETA_SALIDA / f"radar-{fecha_archivo}.md"

    lineas = [
        f"# Radar de creadores colombianos — {fecha_archivo}",
        "",
        f"Generado: {ahora_local.strftime('%Y-%m-%d %H:%M')} (hora Colombia)",
        "",
        f"- Ventana consultada: últimas {HORAS_MAXIMAS} horas.",
        f"- Resultados incluidos: {len(registros)}.",
        f"- Máximo por creador: {MAX_POR_CREADOR}.",
        f"- Máximo para Westcol: {MAX_WESTCOL}.",
        "",
        "> La búsqueda no garantiza descubrir a todos los creadores colombianos. "
        "Verifica el origen del creador y el contexto antes de publicar.",
        "",
    ]

    if not registros:
        lineas.extend([
            "No se encontraron resultados que cumplieran los filtros.",
            "",
            "Esto no significa que no haya actividad: las fuentes o consultas "
            "pueden no haber devuelto resultados recientes.",
            "",
        ])
    else:
        for numero, registro in enumerate(registros, start=1):
            fecha = registro["fecha"].astimezone(
                ZONA_COLOMBIA
            ).strftime("%d/%m/%Y %H:%M")

            lineas.extend([
                f"## {numero}. {registro['titulo']}",
                "",
                f"- **Creador/canal:** {registro['creador']}",
                f"- **Fuente:** {registro['fuente']}",
                f"- **Fecha:** {fecha} (Colombia)",
                f"- **Canal:** {registro['canal'] or 'No identificado'}",
                f"- **Enlace:** {registro['url']}",
                "",
            ])

    lineas.extend([
        "---",
        "",
        "## Búsquedas manuales complementarias",
        "",
        "- [Buscar clips colombianos en TikTok](https://www.tiktok.com/search?q=streamers%20colombianos)",
        "- [Buscar clips colombianos en Kick](https://kick.com/)",
        "- [Buscar Reels colombianos en Instagram](https://www.instagram.com/)",
        "",
        "Estos enlaces son accesos manuales; el informe no afirma haber "
        "consultado automáticamente esas plataformas.",
        "",
    ])

    ruta.write_text("\n".join(lineas), encoding="utf-8")
    print(f"Informe guardado: {ruta}")


# =========================
# EJECUCIÓN PRINCIPAL
# =========================

def main():
    limite = ahora_utc() - timedelta(hours=HORAS_MAXIMAS)

    print("=" * 55)
    print("RADAR DE CREADORES COLOMBIANOS")
    print(f"Inicio: {fecha_iso(ahora_utc())}")
    print(f"Ventana: últimas {HORAS_MAXIMAS} horas")
    print("=" * 55)

    registros = []
    registros.extend(buscar_youtube(limite))
    registros.extend(buscar_google_news(limite))
    registros.extend(buscar_twitch(limite))

    print(f"Resultados antes de deduplicar: {len(registros)}")

    registros = quitar_duplicados(registros)
    print(f"Después de deduplicar: {len(registros)}")

    registros = limitar_por_creador(registros)
    print(f"Después de equilibrar creadores: {len(registros)}")

    generar_informe(registros)


if __name__ == "__main__":
    main()
