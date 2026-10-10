#!/usr/bin/env python3
"""Publish a rights-cleared vertical video to YouTube Shorts and TikTok.

The workflow invokes this script only on manual dispatch. The media URL must point
to a file the user owns or is authorized to publish. YouTube defaults to private;
TikTok defaults to SELF_ONLY. No source-radar link is downloaded automatically.
"""
import json
import os
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlencode

import requests

YOUTUBE_UPLOAD_SCOPE = "https://www.googleapis.com/auth/youtube.upload"
YOUTUBE_TOKEN_URL = "https://oauth2.googleapis.com/token"
YOUTUBE_UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/videos"
TIKTOK_API = "https://open.tiktokapis.com/v2"


def required(name):
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Falta configurar el secreto/variable {name}.")
    return value


def raise_api_error(response, service):
    """Raise a useful API error without ever printing authorization headers/tokens."""
    if response.ok:
        return
    try:
        details = response.json()
    except ValueError:
        details = response.text[:1500]
    raise RuntimeError(f"{service} respondió HTTP {response.status_code}: {json.dumps(details, ensure_ascii=False)[:2500]}")


def download_video(url, destination):
    if not url.startswith("https://"):
        raise RuntimeError("VIDEO_URL debe ser una URL HTTPS directa al archivo de video.")
    with requests.get(url, stream=True, timeout=(20, 120), allow_redirects=True) as response:
        response.raise_for_status()
        content_type = response.headers.get("content-type", "").lower()
        if "text/html" in content_type:
            raise RuntimeError("VIDEO_URL devolvió una página web, no un archivo de video directo.")
        total = 0
        max_bytes = 250 * 1024 * 1024
        with open(destination, "wb") as output:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if not chunk:
                    continue
                total += len(chunk)
                if total > max_bytes:
                    raise RuntimeError("El video supera el límite de seguridad de 250 MB para esta primera versión.")
                output.write(chunk)
    if total < 1024:
        raise RuntimeError("El archivo descargado está vacío o es demasiado pequeño.")
    return total


def youtube_access_token():
    response = requests.post(
        YOUTUBE_TOKEN_URL,
        data={
            "client_id": required("YOUTUBE_CLIENT_ID"),
            "client_secret": required("YOUTUBE_CLIENT_SECRET"),
            "refresh_token": required("YOUTUBE_REFRESH_TOKEN"),
            "grant_type": "refresh_token",
        },
        timeout=30,
    )
    raise_api_error(response, "Google OAuth al renovar el token")
    data = response.json()
    if not data.get("access_token"):
        raise RuntimeError("Google no devolvió un access_token para YouTube.")
    return data["access_token"]


def publish_youtube(video_path, title, description, tags, privacy):
    token = youtube_access_token()
    metadata = {
        "snippet": {
            "title": title[:100],
            "description": description[:5000],
            "tags": tags,
            "categoryId": "24",
            "defaultLanguage": "es",
        },
        "status": {
            "privacyStatus": privacy,
            "selfDeclaredMadeForKids": False,
        },
    }
    start = requests.post(
        YOUTUBE_UPLOAD_URL + "?" + urlencode({"uploadType": "resumable", "part": "snippet,status"}),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=UTF-8",
            "X-Upload-Content-Type": "video/mp4",
            "X-Upload-Content-Length": str(Path(video_path).stat().st_size),
        },
        json=metadata,
        timeout=60,
    )
    raise_api_error(start, "YouTube al iniciar la subida")
    upload_url = start.headers.get("Location")
    if not upload_url:
        raise RuntimeError("YouTube no devolvió la URL de carga reanudable.")
    with open(video_path, "rb") as video:
        upload = requests.put(
            upload_url,
            data=video,
            headers={"Content-Type": "video/mp4"},
            timeout=(30, 600),
        )
    raise_api_error(upload, "YouTube al transferir el video")
    result = upload.json()
    video_id = result.get("id")
    if not video_id:
        raise RuntimeError("YouTube no devolvió el ID del video: " + json.dumps(result)[:500])
    print(f"YouTube: https://youtube.com/shorts/{video_id} (privacidad: {privacy})")
    return video_id


def tiktok_access_token():
    # Tokens are supplied as GitHub Actions secrets. TikTok app authorization,
    # video.publish scope and app audit are managed in TikTok for Developers.
    return required("TIKTOK_ACCESS_TOKEN")


def publish_tiktok(video_path, title, privacy):
    token = tiktok_access_token()
    creator_response = requests.post(
        f"{TIKTOK_API}/post/publish/creator_info/query/",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={},
        timeout=30,
    )
    raise_api_error(creator_response, "TikTok al consultar la cuenta")
    creator = creator_response.json()
    if creator.get("error", {}).get("code") != "ok":
        raise RuntimeError("TikTok no pudo consultar la cuenta creadora: " + json.dumps(creator.get("error", {})))
    allowed = creator.get("data", {}).get("privacy_level_options", [])
    if privacy not in allowed:
        raise RuntimeError(f"TikTok no permite la privacidad solicitada {privacy!r}; opciones actuales: {allowed}")

    size = Path(video_path).stat().st_size
    chunk_size = min(size, 10 * 1024 * 1024)
    chunks = (size + chunk_size - 1) // chunk_size
    init = requests.post(
        f"{TIKTOK_API}/post/publish/video/init/",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=UTF-8"},
        json={
            "post_info": {
                "title": title[:2200],
                "privacy_level": privacy,
                "disable_comment": False,
                "disable_duet": False,
                "disable_stitch": False,
            },
            "source_info": {
                "source": "FILE_UPLOAD",
                "video_size": size,
                "chunk_size": chunk_size,
                "total_chunk_count": chunks,
            },
        },
        timeout=60,
    )
    raise_api_error(init, "TikTok al iniciar la publicación")
    init_data = init.json()
    if init_data.get("error", {}).get("code") != "ok":
        raise RuntimeError("TikTok rechazó la publicación: " + json.dumps(init_data.get("error", {})))
    upload_url = init_data.get("data", {}).get("upload_url")
    publish_id = init_data.get("data", {}).get("publish_id")
    if not upload_url or not publish_id:
        raise RuntimeError("TikTok no devolvió upload_url/publish_id.")

    with open(video_path, "rb") as video:
        index = 0
        while True:
            chunk = video.read(chunk_size)
            if not chunk:
                break
            first = index * chunk_size
            last = first + len(chunk) - 1
            put = requests.put(
                upload_url,
                data=chunk,
                headers={
                    "Content-Type": "video/mp4",
                    "Content-Length": str(len(chunk)),
                    "Content-Range": f"bytes {first}-{last}/{size}",
                },
                timeout=(30, 300),
            )
            raise_api_error(put, "TikTok al transferir el video")
            index += 1
    print(f"TikTok: carga enviada; publish_id={publish_id}. El estado final puede tardar en actualizarse.")
    return publish_id


def main():
    # A mandatory rights confirmation prevents accidental publication of radar links.
    if os.getenv("CONFIRM_RIGHTS", "").lower() != "true":
        raise RuntimeError("Confirma CONFIRM_RIGHTS=true solo si tienes los derechos o permiso para publicar este archivo.")
    video_url = required("VIDEO_URL")
    title = required("VIDEO_TITLE")
    description = os.getenv("VIDEO_DESCRIPTION", "").strip()
    tags = [tag.strip().lstrip("#") for tag in os.getenv("VIDEO_TAGS", "StreamersColombia,ClipsColombia,Shorts").split(",") if tag.strip()]
    youtube_privacy = os.getenv("YOUTUBE_PRIVACY", "private").strip()
    tiktok_privacy = os.getenv("TIKTOK_PRIVACY", "SELF_ONLY").strip()
    if youtube_privacy not in {"private", "unlisted", "public"}:
        raise RuntimeError("YOUTUBE_PRIVACY debe ser private, unlisted o public.")
    if tiktok_privacy not in {"SELF_ONLY", "PUBLIC_TO_EVERYONE", "MUTUAL_FOLLOW_FRIENDS", "FOLLOWER_OF_CREATOR"}:
        raise RuntimeError("TIKTOK_PRIVACY no es una opción válida.")
    targets = {x.strip().lower() for x in os.getenv("PUBLISH_TO", "youtube,tiktok").split(",") if x.strip()}
    if not targets or not targets <= {"youtube", "tiktok"}:
        raise RuntimeError("PUBLISH_TO solo acepta youtube, tiktok o youtube,tiktok.")
    with tempfile.TemporaryDirectory() as temp:
        video_path = str(Path(temp) / "upload.mp4")
        size = download_video(video_url, video_path)
        print(f"Archivo descargado: {size} bytes.")
        if "youtube" in targets:
            publish_youtube(video_path, title, description, tags, youtube_privacy)
        if "tiktok" in targets:
            publish_tiktok(video_path, title, tiktok_privacy)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
