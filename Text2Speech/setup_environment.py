#!/usr/bin/env python3
"""Create the local virtual environment and install Bumblebee dependencies."""

from __future__ import annotations

import shutil
import subprocess
import sys
import venv
from pathlib import Path


ROOT = Path(__file__).resolve().parent
VENV_PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"
PACKAGES = ("torch", "torchaudio", "demucs", "whisperx", "pydub")


def main() -> int:
    if sys.version_info[:2] != (3, 11):
        print("Python 3.11 is required. Install it, then run: py -3.11 setup_environment.py")
        return 2

    if Path(sys.prefix).resolve() != (ROOT / ".venv").resolve():
        if not VENV_PYTHON.is_file():
            print("Creating .venv ...")
            venv.create(ROOT / ".venv", with_pip=True)
        print("Installing dependencies in .venv ...")
        return subprocess.call([str(VENV_PYTHON), str(Path(__file__).resolve())])

    subprocess.run([sys.executable, "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"], check=True)
    subprocess.run([sys.executable, "-m", "pip", "install", *PACKAGES], check=True)
    if shutil.which("ffmpeg") is None:
        print("\nFFmpeg was not found in PATH. Install it with:")
        print("  winget install --id Gyan.FFmpeg --exact")
        print("Then open a new terminal before running the importer.")
        return 2
    print("\nSetup finished.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
