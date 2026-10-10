#!/usr/bin/env python3
"""Genera un Short dinámico de DEDSAFIO/streamers con narración original.
Usa clips locales SOLO si el operador tiene permiso para reutilizarlos. Sin clips,
crea una pieza animada de noticias y lo indica en el artefacto de fuentes.
"""
import asyncio, html, os, re, subprocess, sys, textwrap, xml.etree.ElementTree as ET
from html.parser import HTMLParser
from datetime import datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import quote, urlparse
import requests
from PIL import Image, ImageDraw, ImageFont
import edge_tts

OUT=Path("salida"); WORK=OUT/"partes"; CLIPS=Path("assets/clips")
W,H=1080,1920
VOICE=os.getenv("TTS_VOICE","es-CO-SalomeNeural")
QUERIES=[
    '"DEDSAFIO" when:2d',
    '"DEDSAFIO 4" Gulag when:2d',
    'streamers Dedsafio hoy when:2d',
    'site:kick.com DEDSAFIO clips when:2d',
]
HEADERS={"User-Agent":"Mozilla/5.0 (compatible; ClipsColombiaBot/2.0)"}

def run(cmd):
    subprocess.run(cmd,check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)

def clean(s):
    return re.sub(r"\s+"," ",html.unescape(re.sub(r"<[^>]+>","",s or ""))).strip()

KICK_EVENT_URL="https://kick.com/events/01a0a3d9-602d-7db9-84f4-f740827ec04f?no-embedded-player=1"

class LinkParser(HTMLParser):
    def __init__(self):
        super().__init__(); self.links=[]; self._href=None; self._text=[]
    def handle_starttag(self,tag,attrs):
        if tag=="a":
            self._href=dict(attrs).get("href",""); self._text=[]
    def handle_data(self,data):
        if self._href is not None: self._text.append(data)
    def handle_endtag(self,tag):
        if tag=="a" and self._href is not None:
            self.links.append((self._href,clean(" ".join(self._text))))
            self._href=None; self._text=[]

def fetch_kick_moments():
    """Read public highlight links/titles from Kick's Dedsafio event page; never downloads video."""
    try:
        response=requests.get(KICK_EVENT_URL,headers=HEADERS,timeout=25)
        response.raise_for_status()
        parser=LinkParser(); parser.feed(response.text)
        found=[]; seen=set()
        for href,title in parser.links:
            low=href.lower()
            if not title or len(title)<3 or not any(x in low for x in ("/clip","/clips/","/video/","/videos/")):
                continue
            if href.startswith("/"): href="https://kick.com"+href
            if not href.startswith("https://kick.com/") or title.lower() in seen: continue
            seen.add(title.lower())
            found.append({"title":title,"link":href,"source":"Kick · momento destacado","age":0,"kind":"moment"})
            if len(found)>=3: break
        if found:
            print(f"MOMENTOS_KICK_ENCONTRADOS={len(found)}")
            return found
        print("Kick cargó la página sin enlaces de momentos legibles; se usará el RSS de respaldo.")
    except Exception as exc:
        print(f"Advertencia al leer momentos de Kick: {exc}",file=sys.stderr)
    return []

def fetch_items():
    # Prefer real public moment metadata over generic headlines. Video files are not downloaded.
    moments=fetch_kick_moments()
    if moments: return moments
    found=[]; seen=set()
    for query in QUERIES:
        url="https://news.google.com/rss/search?q="+quote(query)+"&hl=es-419&gl=CO&ceid=CO:es-419"
        try:
            response=requests.get(url,headers=HEADERS,timeout=25); response.raise_for_status()
            root=ET.fromstring(response.content)
            for item in root.findall(".//item"):
                title=clean(item.findtext("title","")); link=clean(item.findtext("link",""))
                source_el=item.find("source")
                source=clean(source_el.text if source_el is not None else urlparse(link).netloc)
                pubdate=item.findtext("pubDate","")
                if not title or not link or title.lower() in seen: continue
                try:
                    date=parsedate_to_datetime(pubdate); age=(datetime.now(date.tzinfo)-date).total_seconds()
                except Exception: age=999999999
                if 0 <= age <= 2*86400:
                    seen.add(title.lower())
                    found.append({"title":title,"link":link,"source":source,"age":age,"kind":"news"})
        except Exception as exc:
            print(f"Advertencia RSS {query!r}: {exc}",file=sys.stderr)
    found.sort(key=lambda x:x["age"])
    return found[:3]

def font(size,bold=False):
    paths=[
      "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
      "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf"]
    for p in paths:
        if Path(p).exists(): return ImageFont.truetype(p,size)
    return ImageFont.load_default()

def wrap(draw,text,f,maxw):
    out=[]; line=""
    for word in text.split():
        test=(line+" "+word).strip()
        if draw.textbbox((0,0),test,font=f)[2] <= maxw: line=test
        else:
            if line: out.append(line)
            line=word
    if line: out.append(line)
    return out

def make_card(path,tag,title,source,index,total):
    im=Image.new("RGB",(W,H),(9,10,22)); d=ImageDraw.Draw(im)
    # Graphic identity: high-contrast streamer palette, comic burst, stickers and progress bar.
    d.ellipse((-300,-180,850,900),fill=(54,18,102))
    d.ellipse((540,90,1450,1040),fill=(9,70,92))
    d.polygon([(0,1120),(1080,790),(1080,1920),(0,1920)],fill=(18,18,35))
    d.rounded_rectangle((55,70,1025,178),radius=30,fill=(255,54,95))
    d.text((88,94),"CLIPS COLOMBIA  /  DEDSAFIO",font=font(37,True),fill="white")
    d.rounded_rectangle((70,260,520,340),radius=22,fill=(90,235,255))
    d.text((94,278),tag.upper()[:28],font=font(30,True),fill=(7,13,28))
    d.text((72,410),"¡OJO!",font=font(58,True),fill=(255,214,67))
    y=535
    for line in wrap(d,title,font(67,True),920)[:7]:
        d.text((74,y),line,font=font(67,True),fill="white",stroke_width=2,stroke_fill=(0,0,0)); y+=88
    d.rounded_rectangle((68,1370,1012,1575),radius=34,fill=(255,214,67))
    note="EL CONTEXTO IMPORTA: mira la fuente completa"
    yy=1412
    for line in wrap(d,note,font(34,True),850):
        d.text((105,yy),line,font=font(34,True),fill=(25,20,22)); yy+=48
    d.text((75,1645),("FUENTE: "+source)[:55],font=font(29,True),fill=(190,225,255))
    d.text((75,1770),f"RADAR DEDSAFIO  •  {index}/{total}",font=font(29,True),fill=(90,235,255))
    # Decorative progress stripe makes the card feel like a social-video edit.
    d.rounded_rectangle((70,1850,1010,1872),radius=10,fill=(55,58,82))
    d.rounded_rectangle((70,1850,70+int(940*index/max(total,1)),1872),radius=10,fill=(255,54,95))
    im.save(path,quality=92)

async def voice(text,path):
    await edge_tts.Communicate(text,VOICE,rate="+12%",volume="+5%").save(str(path))

def dur(path):
    return float(subprocess.check_output(["ffprobe","-v","error","-show_entries","format=duration","-of","default=noprint_wrappers=1:nokey=1",str(path)],text=True).strip())

def make_overlay(path,tag,title,source):
    # Transparent overlay so authorized footage remains visible underneath.
    im=Image.new("RGBA",(W,H),(0,0,0,0)); d=ImageDraw.Draw(im)
    d.rounded_rectangle((42,55,1038,205),radius=28,fill=(9,10,22,220))
    d.rounded_rectangle((58,72,410,132),radius=18,fill=(255,54,95,245))
    d.text((78,82),"CLIPS COLOMBIA",font=font(27,True),fill=(255,255,255,255))
    d.text((62,150),tag.upper()[:35],font=font(28,True),fill=(90,235,255,255))
    d.rounded_rectangle((42,1350,1038,1850),radius=34,fill=(9,10,22,222))
    yy=1410
    for line in wrap(d,title,font(58,True),900)[:5]:
        d.text((72,yy),line,font=font(58,True),fill=(255,255,255,255),stroke_width=2,stroke_fill=(0,0,0,255)); yy+=73
    d.text((72,1780),("FUENTE: "+source)[:48],font=font(27,True),fill=(90,235,255,255))
    im.save(path)

def available_clips():
    return sorted(p for p in CLIPS.glob("*") if p.suffix.lower() in {".mp4",".mov",".mkv",".webm"})

def build_video(items):
    OUT.mkdir(exist_ok=True); WORK.mkdir(parents=True,exist_ok=True)
    clips=available_clips()
    if clips:
        print(f"CLIPS_AUTORIZADOS_ENCONTRADOS={len(clips)}")
    else:
        print("AVISO: no hay clips locales autorizados; se usará fondo animado original, no metraje de terceros.")
    has_moments=any(item.get("kind")=="moment" for item in items)
    if has_moments:
        cards=[{"tag":"DEDSAFIO HOY","title":"LOS MOMENTOS MÁS DUROS DEL GULAG 🔥","source":"Momentos públicos de Kick",
                "voice":"¡Mi gente, ojo a esto! Estos son algunos de los momentos destacados de Dedsafio que están circulando hoy. Vamos uno por uno, y les dejamos la fuente para que vean el contexto completo."}]
    else:
        cards=[{"tag":"RADAR DE HOY","title":"LO QUE SE MUEVE EN DEDSAFIO","source":"Clips Colombia",
                "voice":"¡Pilas, parceros! Este es el radar de Dedsafio. Vamos con publicaciones recientes y su contexto, sin inventarnos momentos."}]
    for i,item in enumerate(items,1):
        if item.get("kind")=="moment":
            narration=f"Momento destacado número {i}: {item['title']}. Este clip aparece en la página pública del evento de Dedsafio en Kick. Abre la fuente para ver el momento completo y su contexto."
            tag=f"MOMENTO {i}"
        else:
            narration=f"Ojo con este tema de Dedsafio: {item['title']}. El titular viene de {item['source']}. Revisa la publicación original y su contexto antes de darlo por confirmado."
            tag=f"TEMA {i}"
        cards.append({"tag":tag,"title":item["title"],"source":item["source"],"voice":narration})
    cards.append({"tag":"TU TURNO","title":"¿CUÁL FUE EL MEJOR MOMENTO?","source":"Clips Colombia",
      "voice":"Ahora te toca a ti, mi gente: ¿cuál fue el mejor momento de Dedsafio? Déjalo en comentarios y comparte el radar."})
    total=len(cards); segments=[]; sources=[]
    for idx,card in enumerate(cards,1):
        img=WORK/f"card_{idx:02d}.jpg"; aud=WORK/f"voice_{idx:02d}.mp3"; seg=WORK/f"segment_{idx:02d}.mp4"
        make_card(img,card["tag"],card["title"],card["source"],idx,total)
        asyncio.run(voice(card["voice"],aud)); seconds=dur(aud)+0.3
        # Use a locally supplied authorized clip as a moving background when available.
        clip=clips[(idx-2)%len(clips)] if clips and 1 < idx < total else None
        if clip:
            overlay=WORK/f"overlay_{idx:02d}.png"
            make_overlay(overlay,card["tag"],card["title"],card["source"])
            vf=("scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,"
                "eq=contrast=1.08:saturation=1.18")
            run(["ffmpeg","-y","-stream_loop","-1","-i",str(clip),"-i",str(aud),"-i",str(overlay),
                 "-filter_complex",f"[0:v]{vf}[base];[base][2:v]overlay=0:0:format=auto,format=yuv420p[v]",
                 "-map","[v]","-map","1:a","-t",f"{seconds:.2f}","-r","30","-c:v","libx264",
                 "-preset","veryfast","-c:a","aac","-b:a","128k","-shortest",str(seg)])
        else:
            # Subtle zoom/pan means even the fallback isn't a static slideshow.
            run(["ffmpeg","-y","-loop","1","-i",str(img),"-i",str(aud),"-t",f"{seconds:.2f}",
                 "-vf",f"scale=1200:2134,zoompan=z='min(zoom+0.0008,1.06)':d=1:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1080x1920:fps=30,format=yuv420p",
                 "-r","30","-c:v","libx264","-preset","veryfast","-tune","stillimage","-c:a","aac","-b:a","128k","-shortest",str(seg)])
        segments.append(seg)
    concat=WORK/"lista.txt"; concat.write_text("".join(f"file '{p.resolve()}'\n" for p in segments),encoding="utf-8")
    output=OUT/"clips_colombia_short.mp4"
    run(["ffmpeg","-y","-f","concat","-safe","0","-i",str(concat),"-c","copy","-movflags","+faststart",str(output)])
    return output,clips

def main():
    items=fetch_items()
    if not items:
        raise RuntimeError("No encontré titulares de Dedsafio recientes en las últimas 48 horas. No se publica un resumen inventado.")
    video,clips=build_video(items)
    lines=["Short narrado de momentos destacados/radar Dedsafio. Se usan títulos y enlaces públicos; el generador NO descarga ni reutiliza automáticamente el metraje de terceros. Abre las fuentes originales para ver el contexto.",
           "Clips de video: "+(f"{len(clips)} archivo(s) local(es) autorizados." if clips else "No incluidos; faltan archivos de video autorizados en assets/clips/.")]
    lines += [f"- {i['title']}\n  Fuente: {i['source']}\n  Enlace: {i['link']}" for i in items]
    (OUT/"fuentes.txt").write_text("\n\n".join(lines),encoding="utf-8")
    print(f"VIDEO_GENERADO={video}"); print(f"CLIPS_USADOS={len(clips)}"); print("FUENTES=salida/fuentes.txt")

if __name__=="__main__": main()
