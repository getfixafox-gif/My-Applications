"""Build script: PyInstaller bundles for Windows and Linux.

Usage::

    python build.py            # build for the current platform
    python build.py --clean    # remove build artefacts first
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist"
BUILD = ROOT / "build"
SPEC = ROOT / "packaging" / "MyApplications.spec"


def ensure_pyinstaller() -> None:
    if importlib.util.find_spec("PyInstaller") is None:
        print("PyInstaller is not installed. Installing...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])


def clean() -> None:
    for directory in (DIST, BUILD):
        if directory.exists():
            print(f"Removing {directory}")
            shutil.rmtree(directory, ignore_errors=True)


def build() -> Path:
    ensure_pyinstaller()
    system = platform.system()
    onefile = os.environ.get("MYAPPLICATIONS_ONEFILE", "1").strip() not in {"0", "false", "no"}
    args = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--distpath",
        str(DIST),
        "--workpath",
        str(BUILD),
        str(SPEC),
    ]
    print("Building for", system, "(one file)" if onefile else "(one folder)")
    subprocess.check_call(args, cwd=ROOT)
    if system == "Windows":
        suffix = ".exe"
    else:
        suffix = ""
    if onefile:
        return DIST / f"MyApplications{suffix}"
    return DIST / "MyApplications" / f"MyApplications{suffix}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Build My Applications")
    parser.add_argument("--clean", action="store_true", help="remove previous artefacts")
    args = parser.parse_args()
    if args.clean:
        clean()
    try:
        target = build()
    except subprocess.CalledProcessError as exc:
        print("Build failed:", exc)
        return 1
    print("Build finished:", target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())