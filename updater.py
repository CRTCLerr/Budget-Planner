"""GitHub release update checker for the Budget Planner desktop app."""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
import webbrowser
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


def _prompt_update_flow(root, release: dict, prompt_if_latest: bool) -> None:
    tag = str(release.get("tag_name", ""))
    html_url = str(release.get("html_url", "https://github.com"))
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
            "Open download page now?"
        ),
        parent=root,
    )

    if not wants_update:
        return

    chosen = _pick_windows_asset(assets)
    if chosen is None:
        messagebox.showinfo(
            "Update",
            "No direct Windows installer asset was found. Opening release page.",
            parent=root,
        )
        webbrowser.open(html_url)
        return

    url = str(chosen.get("browser_download_url", ""))
    if not url:
        webbrowser.open(html_url)
        return

    webbrowser.open(url)


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
