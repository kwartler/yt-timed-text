# PyInstaller spec — builds a single-file binary for Mac/Windows.
# Usage:
#   pip install pyinstaller
#   pyinstaller yt_timed_text.spec
#
# Output: dist/yt-timed-text (Mac/Linux) or dist/yt-timed-text.exe (Windows)

# -*- mode: python ; coding: utf-8 -*-
import sys
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

block_cipher = None

hiddenimports = []
hiddenimports += collect_submodules("yt_dlp")
hiddenimports += collect_submodules("uvicorn")
hiddenimports += collect_submodules("fastapi")

datas = [("static", "static")]
datas += collect_data_files("yt_dlp")

a = Analysis(
    ["app.py"],
    pathex=["."],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="yt-timed-text",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

if sys.platform == "darwin":
    app_bundle = BUNDLE(
        exe,
        name="yt-timed-text.app",
        bundle_identifier="com.kwartler.yt-timed-text",
    )
