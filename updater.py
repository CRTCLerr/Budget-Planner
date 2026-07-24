"""GitHub release update checker for the Budget Planner desktop app."""

from __future__ import annotations

import json
import os
import tempfile
import threading
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path
from tkinter import messagebox

from app_version import APP_VERSION

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
        if name.endswith(".exe") or name.endswith(".msi"):
            return asset

    for asset in assets:
        name = str(asset.get("name", "")).lower()
        if name.endswith(".zip"):
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


def _download_asset(url: str, name: str) -> Path | None:
    download_dir = Path(tempfile.gettempdir()) / "BudgetPlannerUpdates"
    download_dir.mkdir(parents=True, exist_ok=True)
    destination = download_dir / name

    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/octet-stream",
            "User-Agent": "BudgetPlanner-Updater",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=60) as resp, open(destination, "wb") as fh:
            fh.write(resp.read())
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError):
        return None

    return destination


def _prompt_update_flow(root, release: dict) -> None:
    tag = str(release.get("tag_name", ""))
    html_url = str(release.get("html_url", "https://github.com"))
    assets = list(release.get("assets", []))

    if not _is_newer(tag, APP_VERSION):
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
        webbrowser.open(html_url)
        messagebox.showinfo(
            "Update",
            "No direct Windows installer asset was found. Opening the release page.",
            parent=root,
        )
        return

    name = str(chosen.get("name", "update_asset"))
    url = str(chosen.get("browser_download_url", ""))
    if not url:
        webbrowser.open(html_url)
        return

    downloaded = _download_asset(url, name)
    if downloaded is None:
        webbrowser.open(html_url)
        messagebox.showerror(
            "Update Failed",
            "Could not download the update automatically. Opening release page.",
            parent=root,
        )
        return

    messagebox.showinfo(
        "Update Ready",
        (
            f"Update downloaded to:\n{downloaded}\n\n"
            "The installer will launch now. Close the app after installer starts."
        ),
        parent=root,
    )

    try:
        os.startfile(str(downloaded))  # type: ignore[attr-defined]
    except OSError:
        webbrowser.open(html_url)


def schedule_auto_update_check(root) -> None:
    """Start a background release check and prompt user if update exists."""

    def worker() -> None:
        release = _fetch_latest_release()
        if not release:
            return
        root.after(0, lambda: _prompt_update_flow(root, release))

    threading.Thread(target=worker, daemon=True).start()
