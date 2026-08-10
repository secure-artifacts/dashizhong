import sys

from cx_Freeze import Executable, setup


build_exe_options = {
    # Direct imports are detected automatically. Only keep packages with
    # substantial dynamic imports here; do not force-collect all of PyQt6.
    "packages": ["yt_dlp", "vlc"],
    "excludes": [
        "PyQt6.QtDesigner",
        "PyQt6.QtMultimedia",
        "PyQt6.QtPdf",
        "PyQt6.QtQml",
        "PyQt6.QtQuick",
        "tkinter",
        "websockets",
        "win32com",
    ],
    "include_files": [
        ("assets/fonts", "assets/fonts"),
        ("assets/sounds", "assets/sounds"),
        "logo.png",
        "logo.ico",
    ],
}

base = "gui" if sys.platform == "win32" else None

setup(
    name="SuperTools",
    version="1.0",
    description="SuperTools retained desktop utilities",
    options={"build_exe": build_exe_options},
    executables=[
        Executable(
            "main.py",
            base=base,
            target_name="SuperTools.exe",
            icon="logo.ico",
        )
    ],
)
