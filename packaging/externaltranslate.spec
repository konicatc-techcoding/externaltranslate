# PyInstaller onedir build. Run it through `scripts/build_windows.py`, which
# builds the frontend first — a bundle without `frontend/dist` starts, serves
# the API and 404s the page, which is a confusing thing to ship.
#
# onedir, not onefile: onefile unpacks itself to a temporary directory on every
# start, which costs seconds before the first caption and confuses antivirus.
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

PROJECT_ROOT = Path(SPECPATH).resolve().parent

# Paths inside the bundle mirror the repository, so `backend.app.resources`
# resolves them the same way whether or not the program is frozen.
datas = [
    (str(PROJECT_ROOT / "config" / "default.yaml"), "config"),
    (str(PROJECT_ROOT / "frontend" / "dist"), "frontend/dist"),
]

# google-genai ships data files and imports parts of itself lazily; sounddevice
# and pyaudiowpatch carry the PortAudio DLL, without which the program starts
# and then finds no audio devices at all.
datas += collect_data_files("google.genai")
datas += collect_data_files("sounddevice")
datas += collect_data_files("pyaudiowpatch")

# Every module the program reaches through `importlib.import_module` or an
# import inside a function. PyInstaller only follows imports it can see
# statically, so each of these would be missing from the bundle and would fail
# at the moment the operator opened the audio panel — not at startup.
hiddenimports = [
    "pyaudiowpatch",
    "sounddevice",
    "soxr",
    "uvicorn",
    "websockets",
    "websockets.exceptions",
    "uvicorn.logging",
    "uvicorn.loops.auto",
    "uvicorn.loops.asyncio",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.protocols.websockets.websockets_impl",
    "uvicorn.lifespan.on",
]
hiddenimports += collect_submodules("google.genai")

analysis = Analysis(
    [str(PROJECT_ROOT / "packaging" / "entry.py")],
    pathex=[str(PROJECT_ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    # Nothing in the shipped program renders plots or opens notebooks; leaving
    # these out keeps the folder from doubling in size.
    excludes=["matplotlib", "tkinter", "PIL", "pytest", "IPython"],
    noarchive=False,
)

pyz = PYZ(analysis.pure)

exe = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="ExternalTranslate",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    # A console, deliberately: it prints the URL and any startup failure, and
    # closing it stops the service. A windowed build would fail invisibly.
    console=True,
    disable_windowed_traceback=False,
)

collect = COLLECT(
    exe,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=False,
    name="ExternalTranslate",
)
