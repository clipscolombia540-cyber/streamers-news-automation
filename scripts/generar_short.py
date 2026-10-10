#!/usr/bin/env python3
"""Genera un Short narrado original a partir de titulares RSS públicos.
No descarga ni reutiliza el audio/video de terceros; solo muestra titulares breves,
fuentes y una narración prudente basada en la información visible.
"""
import asyncio
import html
import os
import re
import subprocess
import sys
import textwrap
import xml.etree.ElementTree as ET
from datetime import datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import quote, urlparse

import requests
from PIL import Image, ImageDraw, ImageFont
import edge_tts

OUT = Path("salida")
WORK = OUT / "partes"
W, H = 1080, 1920
VOICE = os.getenv("TTS_VOICE", "es-CO-SalomeNeural")
QUERIES = [
    'Westcol streamer',
    'streamers colombianos Twitch Kick',
    'MrStivenTC OR Pelicanger streamer',
]
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; ClipsColombiaBot/1.0)"}


def run(cmd):
    subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def clean(s):
    return re.sub(r"\\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", s or ""))).strip()


def fetch_items():
    found = []
    seen = set()
    for query in QUERIES:
        url = "https://news.google.com/rss/search?q=" + quote(query + " when:7d") + "&hl=es-419&gl=CO&ceid=CO:es-419"
        try:
            response = requests.get(url, headers=HEADERS, timeout=25)
            response.raise_for_status()
            root = ET.fromstring(response.content)
            for item in root.findall(".//item"):
                title = clean(item.findtext("title", ""))
                link = clean(item.findtext("link", ""))
                source_el = item.find("source")
                source = clean(source_el.text if source_el is not None else urlparse(link).netloc)
                pubdate = item.findtext("pubDate", "")
                if not title or not link or title.lower() in seen:
                    continue
                seen.add(title.lower())
                try:
                    date = parsedate_to_datetime(pubdate)
                    age = (datetime.now(date.tzinfo) - date).total_seconds()
                except Exception:
                    age = 999999999
                # Only recent results, and don't imply that the headline alone confirms details.
                if age <= 7 * 86400:
                    found.append({"title": title, "link": link, "source": source, "age": age})
        except Exception as exc:
            print(f"Advertencia: falló búsqueda RSS {query!r}: {exc}", file=sys.stderr)
    found.sort(key=lambda x: x["age"])
    return found[:3]


def load_font(size, bold=False):
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    ]
    for path in candidates:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def wrap_lines(draw, text, font, max_width):
    words = text.split()
    lines, line = [], ""
    for word in words:
        test = (line + " " + word).strip()
        if draw.textbbox((0, 0), test, font=font)[2] <= max_width:
            line = test
        else:
            if line:
                lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines


def make_card(path, eyebrow, title, source, index, total):
    # Original graphic generated from shapes and text; no third-party video/image assets.
    im = Image.new("RGB", (W, H), (13, 17, 38))
    px = im.load()
    for y in range(H):
        for x in range(W):
            glow = max(0, 1 - (((x - 180) / 900) ** 2 + ((y - 330) / 1100) ** 2) ** 0.5)
            px[x, y] = (int(13 + 24 * glow), int(17 + 13 * glow), int(38 + 52 * glow))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((64, 88, 1016, 200), radius=32, fill=(118, 68, 255))
    d.text((100, 120), "CLIPS COLOMBIA  •  RADAR", font=load_font(40, True), fill="white")
    d.text((76, 290), eyebrow.upper(), font=load_font(37, True), fill=(93, 226, 255))
    lines = wrap_lines(d, title, load_font(67, True), 900)
    y = 410
    for line in lines[:9]:
        d.text((76, y), line, font=load_font(67, True), fill=(255, 255, 255), stroke_width=1, stroke_fill=(0, 0, 0))
        y += 88
    d.rounded_rectangle((70, 1330, 1010, 1535), radius=32, fill=(30, 37, 67), outline=(93, 226, 255), width=3)
    note = "Titular para revisar: consulta la fuente y su contexto completo."
    ny = 1370
    for line in wrap_lines(d, note, load_font(34), 850):
        d.text((105, ny), line, font=load_font(34), fill=(230, 235, 255))
        ny += 48
    d.text((76, 1605), "FUENTE: " + (source[:54] if source else "medio enlazado"), font=load_font(30, True), fill=(180, 190, 220))
    d.text((76, 1770), f"NOTICIA {index} DE {total}  •  INFORMACIÓN EN DESARROLLO", font=load_font(28, True), fill=(93, 226, 255))
    im.save(path, quality=92)


async def make_voice(text, path):
    await edge_tts.Communicate(text, VOICE, rate="+3%").save(str(path))


def duration(path):
    result = subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(path)
    ], text=True)
    return float(result.strip())


def build_video(items):
    OUT.mkdir(exist_ok=True)
    WORK.mkdir(parents=True, exist_ok=True)
    segments = []
    narration = [
        "¡Pilas, parceros! Este es el radar de Clips Colombia: noticias y temas de creadores para revisar con contexto.",
    ]
    for item in items:
        narration.append("Entre los titulares recientes aparece: " + item["title"] + ". Este es el titular publicado por " + item["source"] + ". El titular por sí solo no confirma todos los detalles; entra a la fuente original para conocer el contexto.")
    narration.append("¿Qué creador quieres que revisemos en el próximo radar? Síguenos en Clips Colombia y comparte tu opinión con respeto.")
    total = len(items) + 2
    cards = [{
        "eyebrow": "RADAR DE CREADORES",
        "title": "Lo más reciente del mundo streamer colombiano",
        "source": "Clips Colombia",
        "voice": narration[0],
    }]
    for i, item in enumerate(items, start=1):
        cards.append({
            "eyebrow": f"NOTICIA {i}",
            "title": item["title"],
            "source": item["source"],
            "voice": narration[i],
        })
    cards.append({
        "eyebrow": "CIERRE",
        "title": "¿A quién revisamos después? Déjanos tu opinión",
        "source": "Clips Colombia",
        "voice": narration[-1],
    })
    concat_file = WORK / "lista.txt"
    for idx, card in enumerate(cards, start=1):
        image_path = WORK / f"card_{idx:02d}.jpg"
        audio_path = WORK / f"voice_{idx:02d}.mp3"
        segment_path = WORK / f"segment_{idx:02d}.mp4"
        make_card(image_path, card["eyebrow"], card["title"], card["source"], idx, total)
        asyncio.run(make_voice(card["voice"], audio_path))
        seconds = duration(audio_path) + 0.25
        run([
            "ffmpeg", "-y", "-loop", "1", "-i", str(image_path), "-i", str(audio_path),
            "-t", f"{seconds:.3f}", "-vf", "scale=1080:1920,format=yuv420p",
            "-r", "30", "-c:v", "libx264", "-preset", "veryfast", "-tune", "stillimage",
            "-c:a", "aac", "-b:a", "128k", "-shortest", str(segment_path)
        ])
        segments.append(segment_path)
    concat_file.write_text("".join(f"file '{p.resolve()}'\n" for p in segments), encoding="utf-8")
    output = OUT / "clips_colombia_short.mp4"
    run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file),
        "-c", "copy", "-movflags", "+faststart", str(output)
    ])
    return output


def main():
    items = fetch_items()
    if not items:
        raise RuntimeError("No encontré titulares recientes. No se generó video para evitar inventar noticias.")
    video = build_video(items)
    (OUT / "fuentes.txt").write_text(
        "Short generado a partir de titulares RSS públicos. Verifica los artículos completos antes de publicar.\n\n" +
        "\n".join(f"- {i['title']}\n  Fuente: {i['source']}\n  Enlace: {i['link']}" for i in items),
        encoding="utf-8"
    )
    print(f"VIDEO_GENERADO={video}")
    print("FUENTES=salida/fuentes.txt")


if __name__ == "__main__":
    main()
