"""Read Raspberry Pi firmware power flags without interrupting web controls."""

import re
import subprocess


def power_status():
    try:
        result = subprocess.run(
            ["vcgencmd", "get_throttled"], capture_output=True, text=True,
            timeout=0.5, check=True,
        )
        match = re.fullmatch(r"throttled=(0x[0-9a-fA-F]+)", result.stdout.strip())
        if not match:
            raise ValueError("Invalid power status")
        flags = int(match.group(1), 16)
    except (OSError, subprocess.SubprocessError, ValueError):
        return {"available": False, "undervoltage": None, "undervoltage_occurred": None}
    return {
        "available": True,
        "undervoltage": bool(flags & 1),
        "undervoltage_occurred": bool(flags & (1 << 16)),
    }
