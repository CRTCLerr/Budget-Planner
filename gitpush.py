"""One-command release helper for Budget Planner.

Usage:
	python gitpush.py
	python gitpush.py --version 1.04.08

This script:
1) Ensures you are on main and up to date (fast-forward only).
2) Updates core/app_version.py.
3) Commits the version bump.
4) Pushes main to origin.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
VERSION_FILE = ROOT / "core" / "app_version.py"
VERSION_PATTERN = re.compile(r'APP_VERSION\s*=\s*"([^"]+)"')


def run_git(args: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
	"""Run a git command from repository root with readable output."""
	print(f"\n> git {' '.join(args)}")
	proc = subprocess.run(
		["git", *args],
		cwd=ROOT,
		text=True,
		capture_output=True,
	)
	if proc.stdout.strip():
		print(proc.stdout.strip())
	if proc.stderr.strip():
		print(proc.stderr.strip())
	if check and proc.returncode != 0:
		raise RuntimeError(f"git {' '.join(args)} failed with exit code {proc.returncode}")
	return proc


def read_current_version() -> str:
	text = VERSION_FILE.read_text(encoding="utf-8")
	match = VERSION_PATTERN.search(text)
	if not match:
		raise RuntimeError("Could not find APP_VERSION in core/app_version.py")
	return match.group(1)


def write_version(new_version: str) -> None:
	text = VERSION_FILE.read_text(encoding="utf-8")
	updated, count = VERSION_PATTERN.subn(f'APP_VERSION = "{new_version}"', text, count=1)
	if count != 1:
		raise RuntimeError("Could not update APP_VERSION in core/app_version.py")
	VERSION_FILE.write_text(updated, encoding="utf-8")


def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(description="Release version bump + push helper")
	parser.add_argument(
		"--version",
		help="Release version to set (example: 1.04.08). If omitted, you will be prompted.",
	)
	parser.add_argument(
		"--no-pull",
		action="store_true",
		help="Skip 'git pull --ff-only origin main'.",
	)
	return parser.parse_args()


def main() -> int:
	args = parse_args()

	current_version = read_current_version()
	if args.version:
		next_version = args.version.strip()
	else:
		entered = input(f"Current version is {current_version}. Enter new version: ").strip()
		next_version = entered or current_version

	if not re.fullmatch(r"\d+\.\d+\.\d+", next_version):
		print("Version must look like 1.04.08")
		return 1

	try:
		# Ensure branch and sync state
		branch = run_git(["branch", "--show-current"]).stdout.strip()
		if branch != "main":
			run_git(["checkout", "main"])
		if not args.no_pull:
			run_git(["pull", "--ff-only", "origin", "main"])

		# Apply version bump when needed
		if next_version != current_version:
			write_version(next_version)
			print(f"Updated APP_VERSION: {current_version} -> {next_version}")
		else:
			print(f"APP_VERSION unchanged at {current_version}")

		run_git(["add", str(VERSION_FILE.relative_to(ROOT)).replace("\\", "/")])

		# Commit only if there is staged content
		diff_proc = run_git(["diff", "--cached", "--name-only"], check=False)
		has_staged = bool(diff_proc.stdout.strip())

		if has_staged:
			run_git(["commit", "-m", f"chore: bump release version to v{next_version}"])
		else:
			print("No staged changes to commit.")

		run_git(["push", "origin", "main"])
		print("\nRelease push complete.")
		print("GitHub Actions should now run Build and Publish Release Assets.")
		return 0
	except Exception as exc:  # noqa: BLE001
		print(f"\nError: {exc}")
		return 1


if __name__ == "__main__":
	sys.exit(main())