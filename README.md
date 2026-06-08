# YT Timed Text

A small local app that downloads YouTube closed-caption JSON from a single
video or any channel.

- Paste a video URL → pick language → download `.json`
- Paste a channel URL → pick which videos → download a `.zip` of all transcripts

Runs locally. Nothing is uploaded anywhere.

---

## Easiest install (recommended)

1. Go to the [Releases](../../releases) page.
2. Download the file for your platform:
   - **Mac (Apple Silicon, M1/M2/M3/M4):** `yt-timed-text-mac-arm64.zip`
   - **Windows:** `yt-timed-text-windows.exe`
3. **Mac:** unzip the file — you'll get `yt-timed-text.app`. Double-click it. A Terminal window opens and your browser will navigate to `http://127.0.0.1:8000`.  
   **Windows:** double-click the `.exe`. Your browser will open to `http://127.0.0.1:8000`.

### First-launch security warnings

These binaries are not code-signed, so your OS will warn you the first time:

**Mac:** "cannot be opened because it is from an unidentified developer."
- Right-click `yt-timed-text.app` → **Open** → click **Open** in the dialog.
- Or clear the quarantine flag in Terminal, then double-click normally:
  ```
  xattr -dr com.apple.quarantine ~/Downloads/yt-timed-text.app
  ```

**Windows:** "Windows protected your PC" (SmartScreen).
- Click **More info** → **Run anyway**.

You only do this once per download.

---

## Run from source (developers)

```bash
git clone <this repo>
cd yt_timed_text
pip install -r requirements.txt
python app.py
```

The browser opens automatically.

### Build your own binary

```bash
pip install pyinstaller
pyinstaller yt_timed_text.spec
# Output: dist/yt-timed-text  (or .exe on Windows)
```

---

## Where data is stored

- Caption cache: `~/.yt_timed_text_cache/` — delete to clear.
- No accounts, no telemetry.

## Troubleshooting

**"No captions available"** — that video genuinely has none. YouTube only
auto-generates them for some videos, and many channels disable them.

**"Sign in to confirm you're not a bot"** — YouTube occasionally throttles.
Wait a few minutes, or restart the app (it auto-updates yt-dlp at launch
when running from source, which fixes most extraction issues).

**Channel listing is slow** — channels with thousands of videos take a
minute to enumerate. Rows appear progressively as they're discovered.

**Batch downloads are slow** — the app paces requests (~1s between videos)
to avoid YouTube's rate limits. For 100 videos expect ~2 minutes.
