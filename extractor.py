"""yt-dlp wrappers for resolving URLs, listing channels, and fetching captions."""
from __future__ import annotations

import json
import re
import time
import random
import hashlib
from pathlib import Path
from typing import Iterator
from urllib.parse import urlparse, parse_qs

import yt_dlp


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

CACHE_DIR = Path.home() / ".yt_timed_text_cache"
CACHE_DIR.mkdir(exist_ok=True)


def _cache_path(video_id: str, lang: str) -> Path:
    safe = hashlib.sha1(f"{video_id}_{lang}".encode()).hexdigest()[:16]
    return CACHE_DIR / f"{video_id}_{lang}_{safe}.json"


# ---------------------------------------------------------------------------
# URL parsing
# ---------------------------------------------------------------------------

VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")


def classify_url(url: str) -> dict:
    """Return {type: 'video'|'channel', id|handle, raw}."""
    url = url.strip()
    p = urlparse(url)
    host = (p.netloc or "").lower()
    path = p.path or ""

    # youtu.be/<id>
    if host.endswith("youtu.be"):
        vid = path.lstrip("/").split("/")[0]
        if VIDEO_ID_RE.match(vid):
            return {"type": "video", "id": vid}

    # youtube.com/watch?v=<id>
    if "youtube.com" in host:
        if path == "/watch":
            qs = parse_qs(p.query)
            vid = (qs.get("v") or [""])[0]
            if VIDEO_ID_RE.match(vid):
                return {"type": "video", "id": vid}

        # /shorts/<id>
        if path.startswith("/shorts/"):
            vid = path.split("/")[2]
            if VIDEO_ID_RE.match(vid):
                return {"type": "video", "id": vid}

        # /@handle, /channel/<id>, /c/<name>, /user/<name>
        if path.startswith(("/@", "/channel/", "/c/", "/user/")):
            return {"type": "channel", "handle": url}

    # Bare 11-char id
    if VIDEO_ID_RE.match(url):
        return {"type": "video", "id": url}

    raise ValueError(f"Unrecognized YouTube URL: {url}")


# ---------------------------------------------------------------------------
# yt-dlp helpers
# ---------------------------------------------------------------------------

_BASE_OPTS = {
    "quiet": True,
    "no_warnings": True,
    "skip_download": True,
    "extractor_args": {"youtube": {"player_client": ["web", "android"]}},
}


def resolve_video(video_id: str) -> dict:
    """Get metadata for a single video."""
    opts = {**_BASE_OPTS}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
    return {
        "id": info["id"],
        "title": info.get("title") or info["id"],
        "duration": info.get("duration"),
        "thumbnail": info.get("thumbnail"),
        "channel": info.get("channel"),
        "channel_id": info.get("channel_id"),
        "subtitles": list((info.get("subtitles") or {}).keys()),
        "automatic_captions": list((info.get("automatic_captions") or {}).keys()),
    }


def resolve_channel(url: str) -> dict:
    """Get channel metadata (without listing every video)."""
    opts = {**_BASE_OPTS, "extract_flat": "in_playlist", "playlistend": 1}
    # Normalize to /videos tab so we get the uploads playlist
    if not url.rstrip("/").endswith("/videos"):
        url = url.rstrip("/") + "/videos"
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    return {
        "id": info.get("channel_id") or info.get("id"),
        "title": info.get("channel") or info.get("title"),
        "url": url,
        "video_count": info.get("playlist_count") or info.get("n_entries"),
    }


def stream_channel_videos(url: str) -> Iterator[dict]:
    """Yield {id, title, duration, thumbnail} per video in a channel.

    Uses flat extraction so it scales to thousands of videos.
    """
    if not url.rstrip("/").endswith("/videos"):
        url = url.rstrip("/") + "/videos"

    opts = {
        **_BASE_OPTS,
        "extract_flat": "in_playlist",
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
        for entry in info.get("entries") or []:
            if not entry:
                continue
            vid = entry.get("id")
            if not vid:
                continue
            yield {
                "id": vid,
                "title": entry.get("title") or vid,
                "duration": entry.get("duration"),
                "thumbnail": (entry.get("thumbnails") or [{}])[-1].get("url")
                or f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg",
            }


def list_caption_languages(video_id: str) -> dict:
    """Return {manual: [{code, name}], auto: [{code, name}]}."""
    opts = {**_BASE_OPTS}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(
            f"https://www.youtube.com/watch?v={video_id}", download=False
        )

    def fmt(d):
        out = []
        for code, tracks in (d or {}).items():
            name = code
            if tracks and isinstance(tracks, list):
                name = tracks[0].get("name") or code
            out.append({"code": code, "name": name})
        return out

    return {
        "manual": fmt(info.get("subtitles")),
        "auto": fmt(info.get("automatic_captions")),
        "title": info.get("title"),
    }


def fetch_captions_json(video_id: str, lang: str = "en", prefer_manual: bool = True) -> dict:
    """Return parsed json3 captions for the video in the given language.

    Falls back to auto-captions if manual isn't available. Uses disk cache.
    """
    cache = _cache_path(video_id, lang)
    if cache.exists():
        try:
            return json.loads(cache.read_text(encoding="utf-8"))
        except Exception:
            cache.unlink(missing_ok=True)

    # yt-dlp will write subtitle file alongside; we capture by hooking the URL
    # Instead, ask yt-dlp for info, then download the json3 url directly via its HTTP client.
    opts = {
        **_BASE_OPTS,
        "writesubtitles": True,
        "writeautomaticsub": True,
        "subtitleslangs": [lang],
        "subtitlesformat": "json3",
    }

    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(
            f"https://www.youtube.com/watch?v={video_id}", download=False
        )

        manual = (info.get("subtitles") or {}).get(lang)
        auto = (info.get("automatic_captions") or {}).get(lang)

        chosen = None
        chosen_kind = None
        if prefer_manual and manual:
            chosen = manual
            chosen_kind = "manual"
        elif auto:
            chosen = auto
            chosen_kind = "auto"
        elif manual:
            chosen = manual
            chosen_kind = "manual"

        if not chosen:
            raise LookupError(
                f"No captions available for {video_id} in language '{lang}'."
            )

        # Pick json3 format
        json3 = next((t for t in chosen if t.get("ext") == "json3"), None) or chosen[0]
        url = json3["url"]

        # Use yt-dlp's urlopen so it handles cookies/headers correctly
        data = ydl.urlopen(url).read().decode("utf-8", errors="replace")

    parsed = json.loads(data)
    parsed["_meta"] = {
        "video_id": video_id,
        "lang": lang,
        "kind": chosen_kind,
        "fetched_at": int(time.time()),
    }
    cache.write_text(json.dumps(parsed), encoding="utf-8")
    return parsed


def polite_sleep():
    """Small jitter between batch requests to avoid rate limiting."""
    time.sleep(0.5 + random.random())
