#!/usr/bin/env python3
"""Install the minimal dependencies needed for the Bumblebee player."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import venv
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DEFAULT_VENV = ROOT / ".venv"
PLAYER_PACKAGES = ("pydub", "audioop-lts")


def resolve_target_venv() -> Path:
    if os.environ.get("VIRTUAL_ENV"):
        return Path(os.environ["VIRTUAL_ENV"]).resolve()
    return DEFAULT_VENV.resolve()


def resolve_target_python(venv_dir: Path) -> Path:
    if os.name == "nt":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def main() -> int:
    if sys.version_info[:2] < (3, 11) or sys.version_info[:2] >= (3, 14):
        print(
            "Python 3.11-3.13 is required. "
            f"Detected {sys.version_info.major}.{sys.version_info.minor}."
            " Create a matching interpreter and run this script again."
        )
        return 2

    target_venv = resolve_target_venv()
    target_python = resolve_target_python(target_venv)
    if Path(sys.prefix).resolve() != target_venv:
        if not target_python.is_file():
            print(f"Creating venv at {target_venv} ...")
            venv.create(target_venv, with_pip=True)
        print(f"Installing player dependencies in {target_venv} ...")
        return subprocess.call([str(target_python), str(Path(__file__).resolve())])

    subprocess.run([sys.executable, "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"], check=True)
    subprocess.run([sys.executable, "-m", "pip", "install", *PLAYER_PACKAGES], check=True)

    ffmpeg_available = shutil.which("ffmpeg") is not None
    ffplay_available = shutil.which("ffplay") is not None
    aplay_available = shutil.which("aplay") is not None
    espeak_available = shutil.which("espeak-ng") is not None or shutil.which("espeak") is not None
    if not ffmpeg_available and not ffplay_available and not aplay_available and not espeak_available:
        print("\nNo playback or TTS fallback tool was found. Install them with:")
        if os.name == "nt":
            print("  winget install --id Gyan.FFmpeg --exact")
        else:
            print("  sudo apt-get install ffmpeg alsa-utils espeak-ng")
        print("Then open a new terminal before running the player.")
        return 2

    print("\nPlayer setup finished.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
