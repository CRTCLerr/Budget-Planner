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


def _pick_windows_asset(assets: list[dict]) -> dict | None:
    for asset in assets:
        name = str(asset.get("name", "")).lower()
        if name.endswith(".zip"):
            return asset

    for asset in assets:
        name = str(asset.get("name", "")).lower()
        if name.endswith(".exe") or name.endswith(".msi"):
            return asset

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
    $p = Start-Process -FilePath $AssetPath -PassThru
    if ($p) {
        Wait-Process -Id $p.Id
    }
}

Start-Process -FilePath $ExePath
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

    script_path = _settings_base() / "apply_update.ps1"
    _build_powershell_updater_script(script_path)
    _save_pending_update(target_tag)

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

    chosen = _pick_windows_asset(assets)
    if chosen is None:
        messagebox.showerror(
            "Update Unavailable",
            "No supported Windows asset (.zip, .exe, .msi) was found in this release.",
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
