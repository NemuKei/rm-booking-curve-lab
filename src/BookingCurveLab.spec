# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_all

pillow_datas, pillow_binaries, pillow_hiddenimports = collect_all('PIL')


a = Analysis(
    ['gui_main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('../config/hotels.json', 'config'),
        ('../data/namba_daikokucho/大国町_時系列データ.xlsx', 'data/namba_daikokucho'),
        ('../data/hotel_kansai/ホテル関西_時系列データ.xlsx', 'data/hotel_kansai'),
        ('../data/domemae/ドーム前_時系列データ.xlsx', 'data/domemae'),
    ] + pillow_datas,
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
    name='BookingCurveLab',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='BookingCurveLab',
)
