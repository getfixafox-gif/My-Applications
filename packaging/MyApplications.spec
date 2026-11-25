# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for My Applications (Windows / Linux).

Single-file build: everything (Qt, Pillow, the SQL schema) is packed into one
executable. Set the environment variable ``MYAPPLICATIONS_ONEFILE=0`` to produce
the faster one-folder layout instead.
"""

import os
import sys
from pathlib import Path

ROOT = Path(SPECPATH).parent

ONEFILE = os.environ.get("MYAPPLICATIONS_ONEFILE", "1").strip() not in {"0", "false", "no"}

block_cipher = None

datas = [
    (str(ROOT / "app" / "database" / "schema.sql"), "app/database"),
]

hiddenimports = [
    "PySide6.QtSvg",
    "PySide6.QtNetwork",
    "PIL._tkinter_finder",
    # Pulled in dynamically by app.images.icon_fetcher.
    "app.images.icon_fetcher",
    "app.data.starter_catalog",
]

# Qt modules the application never uses: dropping them keeps the bundle small.
EXCLUDES = [
    "tkinter",
    "matplotlib",
    "numpy",
    "scipy",
    "pandas",
    "IPython",
    "pytest",
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebEngineQuick",
    "PySide6.Qt3DCore",
    "PySide6.Qt3DRender",
    "PySide6.QtQuick",
    "PySide6.QtQuick3D",
    "PySide6.QtQml",
    "PySide6.QtMultimedia",
    "PySide6.QtMultimediaWidgets",
    "PySide6.QtCharts",
    "PySide6.QtDataVisualization",
    "PySide6.QtBluetooth",
    "PySide6.QtNfc",
    "PySide6.QtPositioning",
    "PySide6.QtSerialPort",
    "PySide6.QtTest",
    "PySide6.QtDesigner",
    "PySide6.QtHelp",
    "PySide6.QtOpenGL",
    "PySide6.QtOpenGLWidgets",
    "PySide6.QtPdf",
    "PySide6.QtPdfWidgets",
    "PySide6.QtSql",
    "PySide6.QtNetworkAuth",
    "PySide6.QtRemoteObjects",
    "PySide6.QtScxml",
    "PySide6.QtSensors",
    "PySide6.QtSpatialAudio",
    "PySide6.QtStateMachine",
    "PySide6.QtTextToSpeech",
    "PySide6.QtWebChannel",
    "PySide6.QtWebSockets",
]

a = Analysis(
    [str(ROOT / "main.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=EXCLUDES,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

#: Only the Qt plugins the interface actually needs.
NEEDED_PLUGIN_DIRS = (
    "platforms",
    "styles",
    "imageformats",
    "iconengines",
    "tls",
    "networkinformation",
    "generic",
)


def _keep_binary(entry) -> bool:
    """Drop Qt plugin folders the application never loads."""
    name = entry[0].replace("\\", "/")
    marker = "/plugins/"
    if marker not in name and "\\plugins\\" not in entry[0]:
        return True
    tail = name.split(marker, 1)[-1]
    folder = tail.split("/", 1)[0] if "/" in tail else ""
    if not folder:
        return True
    return folder in NEEDED_PLUGIN_DIRS


binaries = [item for item in a.binaries if _keep_binary(item)]
datas_filtered = [item for item in a.datas if _keep_binary(item)]

if ONEFILE:
    exe = EXE(
        pyz,
        a.scripts,
        binaries,
        datas_filtered,
        [],
        name="MyApplications",
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        runtime_tmpdir=None,
        console=False,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
        icon=None,
    )
else:
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name="MyApplications",
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        console=False,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
        icon=None,
    )
    coll = COLLECT(
        exe,
        binaries,
        a.zipfiles,
        datas_filtered,
        strip=False,
        upx=False,
        upx_exclude=[],
        name="MyApplications",
    )
