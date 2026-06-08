"""FastAPI server: serves the SPA and exposes caption-fetching endpoints.

Run with:  python app.py
Or via the packaged binary, which auto-opens the browser.
"""
from __future__ import annotations

import io
import json
import re
import sys
import threading
import time
import webbrowser
import zipfile
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import (
    JSONResponse,
    StreamingResponse,
    FileResponse,
    Response,
)
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import extractor


# ---------------------------------------------------------------------------
# Paths (work in both dev and PyInstaller-frozen mode)
# ---------------------------------------------------------------------------

def resource_path(rel: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))
    return base / rel


STATIC_DIR = resource_path("static")


app = FastAPI(title="YT Timed Text")


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class ResolveBody(BaseModel):
    url: str


class BatchBody(BaseModel):
    video_ids: list[str]
    lang: str = "en"


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

@app.post("/api/resolve")
def resolve(body: ResolveBody):
    try:
        cls = extractor.classify_url(body.url)
    except ValueError as e:
        raise HTTPException(400, str(e))

    try:
        if cls["type"] == "video":
            return {"type": "video", **extractor.resolve_video(cls["id"])}
        else:
            return {"type": "channel", **extractor.resolve_channel(cls["handle"])}
    except Exception as e:
        raise HTTPException(500, f"Failed to resolve: {e}")


@app.get("/api/captions/{video_id}/languages")
def caption_languages(video_id: str):
    try:
        return extractor.list_caption_languages(video_id)
    except Exception as e:
        raise HTTPException(500, f"Failed to list languages: {e}")


@app.get("/api/captions/{video_id}")
def get_captions(video_id: str, lang: str = "en"):
    try:
        data = extractor.fetch_captions_json(video_id, lang)
    except LookupError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        raise HTTPException(500, f"Failed to fetch captions: {e}")

    # Sniff for download via Content-Disposition
    filename = f"{video_id}_{lang}.json"
    return Response(
        content=json.dumps(data),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/channel/videos")
def channel_videos(url: str):
    """Stream channel video list as NDJSON so big channels render progressively."""
    def gen():
        try:
            for v in extractor.stream_channel_videos(url):
                yield json.dumps(v) + "\n"
        except Exception as e:
            yield json.dumps({"_error": str(e)}) + "\n"

    return StreamingResponse(gen(), media_type="application/x-ndjson")


def _slug(s: str, max_len: int = 80) -> str:
    s = re.sub(r"[^\w\s-]", "", s, flags=re.UNICODE).strip()
    s = re.sub(r"[\s_-]+", "_", s)
    return s[:max_len] or "untitled"


@app.post("/api/captions/batch")
def captions_batch(body: BatchBody):
    """Stream a ZIP containing one JSON per requested video."""
    ids = body.video_ids
    lang = body.lang or "en"

    def gen():
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            manifest = []
            for i, vid in enumerate(ids):
                try:
                    data = extractor.fetch_captions_json(vid, lang)
                    title = data.get("_meta", {}).get("title") or vid
                    # Try to get a real title from a quick resolve if missing
                    try:
                        meta = extractor.resolve_video(vid)
                        title = meta.get("title") or title
                    except Exception:
                        pass
                    name = f"{vid}_{_slug(title)}.json"
                    zf.writestr(name, json.dumps(data, ensure_ascii=False))
                    manifest.append({"id": vid, "file": name, "ok": True})
                except Exception as e:
                    err = f"{vid}_ERROR.txt"
                    zf.writestr(err, f"Failed to fetch {vid} ({lang}): {e}\n")
                    manifest.append({"id": vid, "file": err, "ok": False, "error": str(e)})
                extractor.polite_sleep()
            zf.writestr("manifest.json", json.dumps(manifest, indent=2))
        buf.seek(0)
        yield buf.read()

    filename = f"captions_{int(time.time())}.zip"
    return StreamingResponse(
        gen(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------------------
# Static SPA
# ---------------------------------------------------------------------------

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
def root():
    idx = STATIC_DIR / "index.html"
    if idx.exists():
        return FileResponse(str(idx))
    return JSONResponse({"error": "static/index.html missing"}, 500)


# ---------------------------------------------------------------------------
# Auto-update yt-dlp on startup (best-effort)
# ---------------------------------------------------------------------------

def _try_self_update_ytdlp():
    """Try to upgrade yt-dlp in the background. Safe to fail."""
    def run():
        try:
            import subprocess
            subprocess.run(
                [sys.executable, "-m", "pip", "install", "--upgrade", "--quiet", "yt-dlp"],
                timeout=60,
                check=False,
            )
        except Exception:
            pass

    threading.Thread(target=run, daemon=True).start()


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

def _port_in_use(port: int) -> bool:
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) == 0


def main():
    import uvicorn

    port = 8000
    url = f"http://127.0.0.1:{port}"

    # If a server is already running, just (re-)open the browser and wait.
    # We intentionally keep this Terminal window open rather than exiting
    # immediately — macOS treats an app that quits in under ~5 s as a crash
    # and will block future launches with "not open anymore".
    if _port_in_use(port):
        print(f"\nYT Timed Text is already running at {url}")
        print("Opening browser… close this window whenever you like.\n")
        try:
            webbrowser.open(url)
        except Exception:
            pass
        try:
            input()  # keep the Terminal alive until the user closes it
        except (EOFError, KeyboardInterrupt):
            pass
        return

    # Auto-update yt-dlp in the background (no-op when running as a frozen binary)
    if not getattr(sys, "frozen", False):
        _try_self_update_ytdlp()

    # Open browser shortly after the server starts
    def open_browser():
        time.sleep(1.0)
        try:
            webbrowser.open(url)
        except Exception:
            pass

    threading.Thread(target=open_browser, daemon=True).start()

    print(f"\nYT Timed Text running at {url}\nPress Ctrl+C to stop.\n")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    main()
