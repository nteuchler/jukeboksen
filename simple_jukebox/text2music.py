"""Render text with the repo's song-word library in a cancellable subprocess."""
from pathlib import Path
import sys
from simple_jukebox.participant_jingles import sentence_parts


def render(text, destination, library_path, jingle_directory=None):
    from pydub import AudioSegment
    from Text2Speech import bumblebee_player as player

    player.AudioSegment = AudioSegment
    parts = sentence_parts(text, jingle_directory)
    if not any(jingle or player.split_sentence(part) for part, jingle in parts):
        raise ValueError('Enter text containing Danish words or numbers')
    library = None
    audio = AudioSegment.empty()
    for part, jingle in parts:
        if jingle is not None:
            segment = AudioSegment.from_file(jingle)
        else:
            words = player.split_sentence(part)
            if not words:
                continue
            if library is None:
                library = player.load_library(Path(library_path), .55)
                if not library:
                    raise ValueError('The text2Music library has no usable clips')
            segment, _, _ = player.build_sentence(
                words, library, player.build_match_index(library), 'best', 180, 220,
                True, -12.0, False,
            )
        if segment is None:
            raise ValueError('text2Music could not produce audio for this text')
        if len(audio):
            audio += AudioSegment.silent(duration=180)
        audio += segment
    if not len(audio):
        raise ValueError('text2Music could not produce audio for this text')
    audio.export(destination, format='wav')


if __name__ == '__main__':
    text_file, destination, library, error_file = map(Path, sys.argv[1:])
    try:
        render(text_file.read_text(encoding='utf-8'), destination, library)
    except Exception as error:
        error_file.write_text(str(error), encoding='utf-8')
        raise SystemExit(1)
