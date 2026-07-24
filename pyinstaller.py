import os
import shutil
import PyInstaller.__main__

# -----------------------------
# CONFIGURATION
# -----------------------------

APP_NAME = "Budget Planner"
ENTRY_POINT = "main.py"   # Your app's launcher file
ICON_FILE = "assets/moneylogo.ico"  # Optional, remove if not using

# Folders to include in the .exe
INCLUDE_FOLDERS = [
    "ui",
    "data",
    "assets",
]

# -----------------------------
# CLEAN OLD BUILDS
# -----------------------------
for folder in ("build", "dist", f"{APP_NAME}.spec"):
    if os.path.exists(folder):
        if os.path.isdir(folder):
            shutil.rmtree(folder)
        else:
            os.remove(folder)

# -----------------------------
# COLLECT DATA FILES
# -----------------------------
datas = []

for folder in INCLUDE_FOLDERS:
    if os.path.exists(folder):
        datas.append(f"{folder}{os.pathsep}{folder}")

# -----------------------------
# BUILD COMMAND
# -----------------------------
cmd = [
    ENTRY_POINT,
    "--onedir",
    "--noconsole",
]

# Add icon if present
if os.path.exists(ICON_FILE):
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
print(f"Your EXE is located in: dist/{APP_NAME}.exe")
