# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
from PyInstaller.utils.hooks import collect_all

# -----------------------------
# Resolve project root robustly
# -----------------------------
here = Path(__file__).resolve().parent

project_root = here
while not (project_root / "config").exists() and project_root.parent != project_root:
    project_root = project_root.parent

# entry script (prefer src/gui_main.py)
entry = project_root / "src" / "gui_main.py"
if not entry.exists():
    entry = project_root / "gui_main.py"

# icon (you can rename freely, just keep path consistent)
icon_path = project_root / "assets" / "icon" / "BookingCurveLab_logo_neon_requested.ico"

# Pillow resources (PIL)
pillow_datas, pillow_binaries, pillow_hiddenimports = collect_all("PIL")

# -----------------------------
# Datas to bundle
# -----------------------------
# 重要：配布EXEに社内データ(xlsx)を同梱しない方が安全＆軽いです。
# どうしても同梱するなら、下のdatasに追加してください。
datas = [
    (str(project_root / "config" / "hotels.json"), "config"),
] + pillow_datas

a = Analysis(
    [str(entry)],
    pathex=[str(project_root), str(project_root / "src")],
    binaries=pillow_binaries,
    datas=datas,
    hiddenimports=pillow_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="BookingCurveLab",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # デバッグ時は True にすると原因追いやすい
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(icon_path) if icon_path.exists() else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="BookingCurveLab",
)
