import os
import shutil
from pathlib import Path

import PyInstaller.__main__

# -----------------------------
# CONFIGURATION
# -----------------------------

APP_NAME = "Budget Planner"

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENTRY_POINT = PROJECT_ROOT / "main.py"
ICON_FILE = PROJECT_ROOT / "assets" / "moneylogo.ico"

# Folders to include in the .exe
INCLUDE_FOLDERS = [
    PROJECT_ROOT / "ui",
    PROJECT_ROOT / "data",
    PROJECT_ROOT / "assets",
]

# -----------------------------
# CLEAN OLD BUILDS
# -----------------------------
for folder in (
    PROJECT_ROOT / "build",
    PROJECT_ROOT / "dist",
    PROJECT_ROOT / f"{APP_NAME}.spec",
):
    if folder.exists():
        if folder.is_dir():
            shutil.rmtree(folder)
        else:
            folder.unlink()

# -----------------------------
# COLLECT DATA FILES
# -----------------------------
datas = []

for folder in INCLUDE_FOLDERS:
    if folder.exists():
        datas.append(f"{folder}{os.pathsep}{folder.name}")

# -----------------------------
# BUILD COMMAND
# -----------------------------
cmd = [
    str(ENTRY_POINT),
    "--onedir",
    "--noconsole",
]

# Add icon if present
if ICON_FILE.exists():
    cmd.append(f"--icon={ICON_FILE}")

# Add data folders
for d in datas:
    cmd.append(f"--add-data={d}")

# Hidden imports needed for direct Windows printer selection/printing.
for hidden_import in (
    "win32con",
    "win32print",
    "win32ui",
    "pywintypes",
):
    cmd.append(f"--hidden-import={hidden_import}")

# This app is Tkinter-based; exclude Qt bindings so PyInstaller does not
# pull in PySide6 from the local Python environment.
for excluded_module in (
    "PySide6",
    "PyQt6",
    "PyQt5",
):
    cmd.append(f"--exclude-module={excluded_module}")

# Name the executable
cmd.append(f"--name={APP_NAME}")

print(cmd)

# -----------------------------
# RUN PYINSTALLER
# -----------------------------
PyInstaller.__main__.run(cmd)

print("\n\nBuild complete!")
print(f"Your EXE is located in: {PROJECT_ROOT / 'dist' / APP_NAME}")
