# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules

hiddenimports = ['win32print', 'win32api']
hiddenimports += collect_submodules('win32')
# GUI deps — pystray necesita ser explícito porque carga backend según OS.
hiddenimports += [
    'pystray._win32',
    'PIL._tkinter_finder',
    'PIL.ImageFont',
    'PIL.ImageDraw',
]


a = Analysis(
    ['pulstock_agent.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=hiddenimports,
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
    a.binaries,
    a.datas,
    [],
    name='PulstockAgent',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    # IMPORTANT: console=False = modo "windowed" — al doble click NO sale la
    # ventana negra de cmd. Toda la interacción es por GUI Tkinter / system
    # tray. Si necesitas debug en consola, usa: PulstockAgent.exe --cli
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
