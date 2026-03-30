# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller spec for NBA Connections.
# Build with:  pyinstaller nba_connections.spec
#
# All Python + package data is bundled into a single folder (--onedir).
# The resulting executable is in dist/nba-connections/nba-connections[.exe].

import os

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

# SPECPATH is provided by PyInstaller and points to this spec file's directory
# (src/compile/). Use it to reference files in the parent src/ directory.
_SRC = os.path.normpath(os.path.join(SPECPATH, ".."))

# Bundle nba_api's static JSON data (player/team lists)
datas = [(os.path.join(_SRC, "templates"), "templates")]
datas += collect_data_files("nba_api")

# nba_api uses dynamic imports for its endpoints; collect them explicitly
hidden_imports = collect_submodules("nba_api")

a = Analysis(
    [os.path.join(_SRC, "start", "start.py")],
    pathex=[_SRC],           # makes app.py importable as 'app' from the bundle
    binaries=[],
    datas=datas,
    hiddenimports=hidden_imports + ["app"],  # 'app' is imported by name at runtime
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,   # --onedir: binaries go in the COLLECT step
    name="nba-connections",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    console=True,            # Keep console window (needed for API key prompt)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,         # arm64 (native); runs on Intel via Rosetta 2
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="nba-connections",
)
