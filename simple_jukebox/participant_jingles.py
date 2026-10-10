"""Match participant names to soundbytes while preserving surrounding text."""
from pathlib import Path
import re


JINGLE_DIR = Path(__file__).with_name('assets') / 'DeltagerJingles'
AUDIO_SUFFIXES = {'.mp3', '.wav', '.ogg', '.flac', '.m4a'}


def sentence_parts(text, directory=None):
    directory = Path(directory) if directory is not None else JINGLE_DIR
    names = {}
    for path in sorted(directory.glob('*')):
        if not path.is_file() or path.suffix.lower() not in AUDIO_SUFFIXES:
            continue
        name = path.stem.strip()
        if not name:
            continue
        names.setdefault(name.casefold(), path)
        if name.lower().endswith('s jingle'):
            names.setdefault(name[:-8].strip().casefold(), path)
    if not names:
        return [(text, None)]
    pattern = re.compile(r'(?<!\w)(?:' + '|'.join(
        re.escape(name) for name in sorted(names, key=lambda name: (-len(name), name))
    ) + r')(?!\w)', re.IGNORECASE)
    parts = []
    cursor = 0
    for match in pattern.finditer(text):
        if match.start() > cursor:
            parts.append((text[cursor:match.start()], None))
        parts.append((match.group(), names[match.group().casefold()]))
        cursor = match.end()
    if cursor < len(text):
        parts.append((text[cursor:], None))
    return parts
