#!/usr/bin/env python3
"""Sube el Short recién generado a YouTube con privacidad privada."""
from pathlib import Path

try:
    from scripts.publicar import publish_youtube
except ModuleNotFoundError:
    # When executed as `python scripts/subir_short_generado.py`, Python adds
    # the scripts directory (not the repository root) to sys.path.
    from publicar import publish_youtube

video = Path("salida/clips_colombia_short.mp4")
if not video.is_file() or video.stat().st_size < 1024:
    raise RuntimeError("No existe un Short generado válido.")
sources_path = Path("salida/fuentes.txt")
sources = sources_path.read_text(encoding="utf-8") if sources_path.exists() else ""
description = (
    "Radar de Dedsafio con narración y edición originales. "
    "Los titulares se presentan como pistas para consultar la fuente; revisa el contexto completo.\n\n"
    + sources[:4500]
)
publish_youtube(
    str(video),
    "DEDSAFIO HOY 🔥 Momentos y noticias #Shorts",
    description,
    ["ClipsColombia", "Dedsafio", "Streamers", "Shorts", "Gaming"],
    "private",
)
