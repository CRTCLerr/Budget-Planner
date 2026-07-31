"""GitHub release update checker for the Budget Planner desktop app."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path
from tkinter import messagebox

from core.app_version import APP_VERSION

GITHUB_OWNER = "CRTCLerr"
GITHUB_REPO = "Budget-Planner"
LATEST_RELEASE_API = (
    f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"
)


def _parse_version(raw: str) -> tuple[int, ...]:
    text = raw.strip().lower()
    if text.startswith("v"):
        text = text[1:]

    parts: list[int] = []
    for token in text.replace("-", ".").split("."):
        digits = "".join(ch for ch in token if ch.isdigit())
        if digits:
            parts.append(int(digits))

    return tuple(parts) if parts else (0,)


def _is_newer(remote_tag: str, local_version: str) -> bool:
    remote = _parse_version(remote_tag)
    local = _parse_version(local_version)
    return remote > local


def _is_windows_program_files_install(exe_path: Path) -> bool:
    if not sys.platform.startswith("win"):
        return False

    try:
        resolved = exe_path.resolve()
    except OSError:
        resolved = exe_path

    program_files_roots = [
        os.environ.get("ProgramFiles", ""),
        os.environ.get("ProgramFiles(x86)", ""),
    ]

    lowered = str(resolved).lower()
    for root in program_files_roots:
        root = root.strip()
        if root and lowered.startswith(str(Path(root)).lower()):
            return True
    return False


def _pick_windows_asset(assets: list[dict], prefer_installer: bool = False) -> dict | None:
    if prefer_installer:
        for asset in assets:
            name = str(asset.get("name", "")).lower()
            if name.endswith(".msi"):
                return asset

        for asset in assets:
            name = str(asset.get("name", "")).lower()
            if name.endswith(".exe") and (
                "setup" in name or "installer" in name or "install" in name
            ):
                return asset

        for asset in assets:
            name = str(asset.get("name", "")).lower()
            if name.endswith(".zip"):
                return asset

    else:
        # Portable installs should prefer zip/portable assets over installer EXEs.
        for asset in assets:
            name = str(asset.get("name", "")).lower()
            if name.endswith(".zip"):
                return asset

    for asset in assets:
        name = str(asset.get("name", "")).lower()
        if name.endswith(".exe") and not (
            "setup" in name or "installer" in name or "install" in name
        ):
            return asset

    for asset in assets:
        name = str(asset.get("name", "")).lower()
        if name.endswith(".msi"):
            return asset

    if not prefer_installer:
        for asset in assets:
            name = str(asset.get("name", "")).lower()
            if name.endswith(".exe") and (
                "setup" in name or "installer" in name or "install" in name
            ):
                return asset

    return None


def _pick_linux_asset(assets: list[dict]) -> dict | None:
    tagged = []
    generic = []

    for asset in assets:
        name = str(asset.get("name", "")).lower()
        if not name:
            continue

        if "linux" in name and (
            name.endswith(".appimage")
            or name.endswith(".tar.gz")
            or name.endswith(".bin")
            or "." not in Path(name).name
        ):
            tagged.append(asset)
        elif (
            name.endswith(".appimage")
            or name.endswith(".tar.gz")
            or name.endswith(".bin")
            or "." not in Path(name).name
        ):
            generic.append(asset)

    if tagged:
        return tagged[0]
    if generic:
        return generic[0]
    return None


def _current_platform() -> str:
    if sys.platform.startswith("win"):
        return "windows"
    if sys.platform.startswith("linux"):
        return "linux"
    return "other"


def _pick_release_asset_for_current_platform(assets: list[dict]) -> dict | None:
    current = _current_platform()
    if current == "windows":
        exe_path = Path(sys.executable).resolve() if getattr(sys, "frozen", False) else Path(".")
        prefer_installer = _is_windows_program_files_install(exe_path)
        return _pick_windows_asset(assets, prefer_installer=prefer_installer)
    if current == "linux":
        return _pick_linux_asset(assets)
    return None


def _fetch_latest_release() -> dict | None:
    req = urllib.request.Request(
        LATEST_RELEASE_API,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "BudgetPlanner-UpdateChecker",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            payload = resp.read().decode("utf-8")
            return json.loads(payload)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError):
        return None


def _settings_base() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "BudgetPlanner"
    base.mkdir(parents=True, exist_ok=True)
    return base


def _status_file() -> Path:
    return _settings_base() / "update_status.json"


def _save_pending_update(tag: str) -> None:
    payload = {"pending_tag": tag}
    _status_file().write_text(json.dumps(payload), encoding="utf-8")


def notify_post_update_status(root) -> None:
    """Notify user on startup when a previous update cycle completed."""
    path = _status_file()
    if not path.exists():
        return

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        pending_tag = str(payload.get("pending_tag", "")).strip()
    except (OSError, json.JSONDecodeError):
        pending_tag = ""

    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass

    if pending_tag and not _is_newer(pending_tag, APP_VERSION):
        messagebox.showinfo(
            "Update Complete",
            f"Budget Planner has been updated to {APP_VERSION}.",
            parent=root,
        )
        return

    messagebox.showinfo(
        "Update Status",
        f"Update cycle finished. Current version: {APP_VERSION}.",
        parent=root,
    )


def _download_asset(url: str, name: str) -> Path | None:
    updates_dir = _settings_base() / "updates"
    updates_dir.mkdir(parents=True, exist_ok=True)
    destination = updates_dir / name

    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/octet-stream",
            "User-Agent": "BudgetPlanner-Updater",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=90) as resp, destination.open("wb") as fh:
            fh.write(resp.read())
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError):
        return None

    return destination


def _build_powershell_updater_script(script_path: Path) -> None:
    script = r'''param(
    [int]$AppPid,
    [string]$AssetPath,
    [string]$InstallDir,
    [string]$ExePath
)

$ErrorActionPreference = "SilentlyContinue"
$launchedInstaller = $false

if ($AppPid -gt 0) {
    Wait-Process -Id $AppPid
}

$ext = [System.IO.Path]::GetExtension($AssetPath).ToLowerInvariant()

if ($ext -eq ".zip") {
    $stage = Join-Path $env:TEMP ("BudgetPlannerUpdate_" + [guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Path $stage -Force | Out-Null

    Expand-Archive -Path $AssetPath -DestinationPath $stage -Force

    $source = $stage
    $dirs = Get-ChildItem -Path $stage -Directory
    if ($dirs.Count -eq 1) {
        $source = $dirs[0].FullName
    }

    robocopy $source $InstallDir /E /R:2 /W:1 /NFL /NDL /NJH /NJS /NP | Out-Null
}
elseif ($ext -eq ".msi") {
    $p = Start-Process -FilePath "msiexec.exe" -ArgumentList "/i", $AssetPath -PassThru
    if ($p) {
        Wait-Process -Id $p.Id
    }
}
elseif ($ext -eq ".exe") {
    # For portable one-file releases, replace the running executable directly.
    # If replacement fails (for example due to permissions), treat the asset as
    # an installer and run it interactively.
    $copied = $false
    try {
        $tempNew = "$ExePath.new"
        Copy-Item -Path $AssetPath -Destination $tempNew -Force
        Move-Item -Path $tempNew -Destination $ExePath -Force
        $copied = $true
    }
    catch {
        $copied = $false
    }

    if (-not $copied) {
        $launchedInstaller = $true
        $p = Start-Process -FilePath $AssetPath -PassThru
        if ($p) {
            Wait-Process -Id $p.Id
        }
    }
}

if (-not $launchedInstaller) {
    if (Test-Path $ExePath) {
        Start-Process -FilePath $ExePath
    }
}
'''
    script_path.write_text(script, encoding="utf-8")


def _build_linux_updater_script(script_path: Path) -> None:
        script = r'''#!/usr/bin/env bash
set -eu

APP_PID="$1"
ASSET_PATH="$2"
EXE_PATH="$3"

if [ "${APP_PID}" -gt 0 ] 2>/dev/null; then
    while kill -0 "${APP_PID}" 2>/dev/null; do
        sleep 1
    done
fi

LOWER_ASSET="$(printf '%s' "${ASSET_PATH}" | tr '[:upper:]' '[:lower:]')"
STAGE_DIR=""
SOURCE_BIN="${ASSET_PATH}"

if [[ "${LOWER_ASSET}" == *.tar.gz ]]; then
    STAGE_DIR="$(mktemp -d)"
    tar -xzf "${ASSET_PATH}" -C "${STAGE_DIR}"

    SOURCE_BIN="$(find "${STAGE_DIR}" -type f -perm -u+x | head -n 1)"
    if [ -z "${SOURCE_BIN}" ]; then
        SOURCE_BIN="$(find "${STAGE_DIR}" -type f | head -n 1)"
    fi
fi

if [ -z "${SOURCE_BIN}" ] || [ ! -f "${SOURCE_BIN}" ]; then
    exit 1
fi

cp -f "${SOURCE_BIN}" "${EXE_PATH}.new"
chmod +x "${EXE_PATH}.new"
mv -f "${EXE_PATH}.new" "${EXE_PATH}"

if [ -n "${STAGE_DIR}" ] && [ -d "${STAGE_DIR}" ]; then
    rm -rf "${STAGE_DIR}"
fi

nohup "${EXE_PATH}" >/dev/null 2>&1 &
'''
        script_path.write_text(script, encoding="utf-8")


def _launch_external_apply_and_restart(root, downloaded_asset: Path, target_tag: str) -> None:
    if not getattr(root, "tk", None):
        return

    if not getattr(sys, "frozen", False):
        messagebox.showinfo(
            "Update Downloaded",
            (
                f"Update package downloaded to:\n{downloaded_asset}\n\n"
                "Automatic apply+restart is available in the packaged app build."
            ),
            parent=root,
        )
        return

    exe_path = Path(sys.executable).resolve()
    install_dir = exe_path.parent

    _save_pending_update(target_tag)

    if sys.platform.startswith("win"):
        script_path = _settings_base() / "apply_update.ps1"
        _build_powershell_updater_script(script_path)

        creation_flags = 0
        if hasattr(subprocess, "DETACHED_PROCESS"):
            creation_flags |= subprocess.DETACHED_PROCESS
        if hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
            creation_flags |= subprocess.CREATE_NEW_PROCESS_GROUP

        subprocess.Popen(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(script_path),
                "-AppPid",
                str(os.getpid()),
                "-AssetPath",
                str(downloaded_asset),
                "-InstallDir",
                str(install_dir),
                "-ExePath",
                str(exe_path),
            ],
            creationflags=creation_flags,
            close_fds=True,
        )
    elif sys.platform.startswith("linux"):
        script_path = _settings_base() / "apply_update.sh"
        _build_linux_updater_script(script_path)
        script_path.chmod(0o755)

        subprocess.Popen(
            [
                "/bin/bash",
                str(script_path),
                str(os.getpid()),
                str(downloaded_asset),
                str(exe_path),
            ],
            start_new_session=True,
            close_fds=True,
        )
    else:
        messagebox.showinfo(
            "Update Downloaded",
            f"Update package downloaded to:\n{downloaded_asset}",
            parent=root,
        )
        return

    messagebox.showinfo(
        "Updating",
        "Budget Planner is closing now to apply the update. It will restart automatically.",
        parent=root,
    )
    root.after(200, root.destroy)


def _start_update_download_and_apply(root, url: str, name: str, tag: str) -> None:
    messagebox.showinfo(
        "Downloading Update",
        "Update download started. You will be prompted before restart.",
        parent=root,
    )

    def worker() -> None:
        downloaded = _download_asset(url, name)
        if downloaded is None:
            root.after(
                0,
                lambda: messagebox.showerror(
                    "Update Failed",
                    "The update package could not be downloaded.",
                    parent=root,
                ),
            )
            return

        root.after(0, lambda: _launch_external_apply_and_restart(root, downloaded, tag))

    threading.Thread(target=worker, daemon=True).start()


def _prompt_update_flow(root, release: dict, prompt_if_latest: bool) -> None:
    tag = str(release.get("tag_name", "")).strip()
    assets = list(release.get("assets", []))

    if not _is_newer(tag, APP_VERSION):
        if prompt_if_latest:
            messagebox.showinfo(
                "No Updates",
                f"You are up to date. Current version: {APP_VERSION}",
                parent=root,
            )
        return

    wants_update = messagebox.askyesno(
        "Update Available",
        (
            f"A new version ({tag}) is available.\n"
            f"Current version: {APP_VERSION}\n\n"
            "Download and install now?"
        ),
        parent=root,
    )

    if not wants_update:
        return

    chosen = _pick_release_asset_for_current_platform(assets)
    if chosen is None:
        platform_name = _current_platform()
        if platform_name == "windows":
            expected = ".exe, .msi, .zip"
        elif platform_name == "linux":
            expected = "linux one-file asset (.AppImage, .bin, or executable)"
        else:
            expected = "an asset for the current platform"

        messagebox.showerror(
            "Update Unavailable",
            f"No supported {platform_name} asset ({expected}) was found in this release.",
            parent=root,
        )
        return

    name = str(chosen.get("name", "update_asset")).strip()
    url = str(chosen.get("browser_download_url", ""))
    if not url:
        messagebox.showerror(
            "Update Unavailable",
            "Release asset URL is missing.",
            parent=root,
        )
        return

    if not getattr(root, "settings", None) or not root.settings.auto_update_install:
        wants_download = messagebox.askyesno(
            "Download Update",
            "Auto-install is disabled. Download and install this update now?",
            parent=root,
        )
        if not wants_download:
            return

    _start_update_download_and_apply(root, url, name, tag)


def check_for_updates(root, prompt_if_latest: bool = True) -> None:
    """Check GitHub releases in background and prompt user in the UI thread."""

    def worker() -> None:
        release = _fetch_latest_release()
        if not release:
            if prompt_if_latest:
                root.after(
                    0,
                    lambda: messagebox.showerror(
                        "Update Check Failed",
                        "Could not contact GitHub Releases right now.",
                        parent=root,
                    ),
                )
            return
        root.after(0, lambda: _prompt_update_flow(root, release, prompt_if_latest))

    threading.Thread(target=worker, daemon=True).start()


def schedule_auto_update_check(root) -> None:
    """Run a startup check that only notifies when an update is available."""
    check_for_updates(root, prompt_if_latest=False)
