#!/usr/bin/env python3
"""Interactive Windows player for a Bumblebee song-word clip library."""

from __future__ import annotations

import argparse
import errno
import difflib
import importlib
import json
import random
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Any, TypedDict


AudioSegmentT = Any


class MatchIndex(TypedDict):
    aliases: dict[str, set[str]]
    words: tuple[str, ...]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build and play sentences from generated song-word WAV clips."
    )
    parser.add_argument(
        "output", nargs="?", type=Path, default=Path("output"),
        help="Importer output folder containing index.json (default: output)",
    )
    parser.add_argument("--mode", choices=("random", "best"), default="best")
    parser.add_argument("--gap-ms", type=int, default=180)
    parser.add_argument("--missing-gap-ms", type=int, default=220)
    parser.add_argument("--min-score", type=float, default=0.55)
    parser.add_argument("--target-dbfs", type=float, default=-12.0)
    parser.add_argument("--no-normalize", action="store_true")
    parser.add_argument("--strict", action="store_true", help="Refuse sentences with missing words")
    parser.add_argument("--save", type=Path, help="Save one sentence instead of interactive mode")
    parser.add_argument("--text", help="Sentence used with --save, or played once")
    return parser.parse_args()


def normalize_word(text: str) -> str:
    text = unicodedata.normalize("NFC", text).lower()
    return re.sub(r"[^0-9a-z\u00e6\u00f8\u00e5]+", "", text, flags=re.IGNORECASE)


COMMON_SUFFIXES = ("ernes", "erne", "ende", "ene", "ens", "ers", "er", "en", "et", "e", "s")


def word_variants(word: str) -> set[str]:
    variants = {word}
    stack = [word]
    while stack:
        current = stack.pop()
        for suffix in COMMON_SUFFIXES:
            if len(current) > len(suffix) + 2 and current.endswith(suffix):
                stem = current[:-len(suffix)]
                if stem not in variants:
                    variants.add(stem)
                    stack.append(stem)
    return variants


def build_match_index(library: dict[str, list[dict]]) -> MatchIndex:
    aliases: dict[str, set[str]] = defaultdict(set)
    for canonical_word in library:
        for variant in word_variants(canonical_word):
            aliases[variant].add(canonical_word)
    return {"aliases": dict(aliases), "words": tuple(sorted(library))}


def resolve_library_word(word: str, match_index: MatchIndex, library: dict[str, list[dict]]) -> str | None:
    if word in library:
        return word

    aliases = match_index["aliases"]
    candidates: set[str] = set()
    for variant in word_variants(word):
        candidates.update(aliases.get(variant, ()))
    if candidates:
        return max(candidates, key=lambda candidate: difflib.SequenceMatcher(None, word, candidate).ratio())

    close_matches = difflib.get_close_matches(word, match_index["words"], n=1, cutoff=0.72)
    return close_matches[0] if close_matches else None


def split_sentence(text: str) -> list[str]:
    return [word for token in text.split() if (word := normalize_word(token))]


def load_library(output_dir: Path, min_score: float) -> dict[str, list[dict]]:
    index_path = output_dir / "index.json"
    if not index_path.is_file():
        raise FileNotFoundError(f"Could not find {index_path}")
    with index_path.open("r", encoding="utf-8") as handle:
        index = json.load(handle)

    library: dict[str, list[dict]] = defaultdict(list)
    missing_files = 0
    for record in index.get("clips", []):
        if record.get("approved") is False or float(record.get("score", 1.0)) < min_score:
            continue
        word = normalize_word(str(record.get("word", "")))
        clip_path = output_dir / Path(str(record.get("file", "")))
        try:
            exists = clip_path.is_file()
        except OSError as error:
            if error.errno != errno.ENAMETOOLONG:
                raise
            # Older transcripts can contain hallucinated, endlessly repeated
            # words whose directories could never be created by the importer.
            exists = False
        if word and exists:
            item = dict(record)
            item["absolute_path"] = clip_path
            library[word].append(item)
        else:
            missing_files += 1
    if missing_files:
        print(f"Warning: ignored {missing_files} index entries with missing files.")
    return dict(library)


def choose_clip(options: list[dict], mode: str) -> dict:
    if mode == "best":
        return max(options, key=lambda item: float(item.get("score", 1.0)))
    weights = [max(0.05, float(item.get("score", 1.0)) ** 3) for item in options]
    return random.choices(options, weights=weights, k=1)[0]


def combine_phrase_clips(words: list[str], library: dict[str, list[dict]]) -> list[str]:
    """Match corrected multiword labels, e.g. 'i morgen', as one audio clip."""
    phrases = {
        tuple(split_sentence(str(record.get("word", ""))))
        for options in library.values() for record in options
        if " " in str(record.get("word", ""))
    }
    phrases = {phrase for phrase in phrases if len(phrase) > 1}
    sizes = sorted({len(phrase) for phrase in phrases}, reverse=True)
    combined = []
    position = 0
    while position < len(words):
        for size in sizes:
            candidate = tuple(words[position:position + size])
            if candidate in phrases:
                combined.append(" ".join(candidate))
                position += size
                break
        else:
            combined.append(words[position])
            position += 1
    return combined


def normalize_volume(audio: AudioSegmentT, target_dbfs: float) -> AudioSegmentT:
    if audio.dBFS == float("-inf"):
        return audio
    return audio.apply_gain(max(-12.0, min(12.0, target_dbfs - audio.dBFS)))


def synthesize_tts_word(word: str) -> AudioSegmentT | None:
    candidates: list[list[str]] = []
    # prefer Danish voices/locale where supported
    for executable in ("espeak-ng", "espeak"):
        if shutil.which(executable):
            # prefer Danish voice, slower speed, and slightly calmer pitch for clearer speech
            candidates.append([executable, "-v", "da", "-s", "150", "-p", "50", "-w", "", word])
            candidates.append([executable, "-v", "da+f3", "-s", "150", "-p", "50", "-w", "", word])
            candidates.append([executable, "-v", "da", "-w", "", word])
            candidates.append([executable, "-w", "", word])
    for executable in ("pico2wave",):
        if shutil.which(executable):
            candidates.append([executable, "-w", "", word])

    for command in candidates:
        temp_file: Path | None = None
        audio: AudioSegmentT | None = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as handle:
                temp_file = Path(handle.name)
            cmd = list(command)
            # locate the -w argument position and replace its placeholder with the temp file
            try:
                w_index = cmd.index("-w")
                cmd[w_index + 1] = str(temp_file)
            except ValueError:
                # some TTS variants take output file as the next-to-last arg
                if len(cmd) >= 2:
                    cmd[-2] = str(temp_file)
            completed = subprocess.run(cmd, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if completed.returncode != 0 or not temp_file.is_file():
                continue
            audio = AudioSegment.from_wav(temp_file)
            return audio
        except Exception:
            continue
        finally:
            if temp_file is not None:
                temp_file.unlink(missing_ok=True)
    return None


def build_sentence(words: list[str], library: dict[str, list[dict]], match_index: MatchIndex, mode: str,
                   gap_ms: int, missing_gap_ms: int, normalize: bool,
                   target_dbfs: float, strict: bool) -> tuple[AudioSegmentT | None, list[str], list[dict]]:
    words = combine_phrase_clips(words, library)
    resolved_words = [resolve_library_word(normalize_word(word), match_index, library) for word in words]
    missing = [word for word, resolved_word in zip(words, resolved_words) if resolved_word is None]
    if missing and strict:
        return None, missing, []
    sentence = AudioSegment.empty()
    selections: list[dict] = []
    for position, (word, resolved_word) in enumerate(zip(words, resolved_words)):
        options = library.get(resolved_word) if resolved_word else None
        if options:
            selected = choose_clip(options, mode)
            audio = AudioSegment.from_wav(selected["absolute_path"])
            sentence += normalize_volume(audio, target_dbfs) if normalize else audio
            selected = dict(selected)
            selected["input_word"] = word
            selected["matched_word"] = resolved_word or word
            selections.append(selected)
            pause = gap_ms
        else:
            fallback_audio = synthesize_tts_word(word)
            if fallback_audio is not None:
                sentence += normalize_volume(fallback_audio, target_dbfs) if normalize else fallback_audio
                selections.append({
                    "input_word": word,
                    "matched_word": word,
                    "song": "tts-fallback",
                    "start": 0.0,
                    "tts_fallback": True,
                })
                pause = gap_ms
            else:
                pause = missing_gap_ms
                if strict:
                    missing.append(word)
                    return None, list(dict.fromkeys(missing)), selections
        if position < len(words) - 1 and pause:
            sentence += AudioSegment.silent(duration=pause)
    return sentence if len(sentence) else None, missing, selections


def play_wav(audio: AudioSegmentT) -> None:
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as handle:
            temporary_path = Path(handle.name)
        audio.export(temporary_path, format="wav")

        if sys.platform == "win32":
            import winsound
            winsound.PlaySound(str(temporary_path), winsound.SND_FILENAME)
            return

        ffplay = shutil.which("ffplay")
        if ffplay:
            subprocess.run([ffplay, "-nodisp", "-autoexit", str(temporary_path)], check=False)
            return

        aplay = shutil.which("aplay")
        if aplay:
            subprocess.run([aplay, "-q", str(temporary_path)], check=False)
            return

        try:
            import simpleaudio as sa
            wave_obj = sa.WaveObject(str(temporary_path))
            play_obj = wave_obj.play()
            play_obj.wait_done()
            return
        except Exception as exc:
            raise RuntimeError(
                "No supported audio player found. Install ffmpeg/ffplay, aplay, or simpleaudio."
            ) from exc
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def describe_selections(selections: list[dict]) -> None:
    for selected in selections:
        input_word = str(selected.get("input_word", selected.get("matched_word", "?")))
        matched_word = str(selected.get("matched_word", input_word))
        label = input_word if input_word == matched_word else f"{input_word} -> {matched_word}"
        print(f"  {label:<24} {selected.get('song', '?')} @ {float(selected.get('start', 0.0)):.2f}s")


def main() -> int:
    args = parse_args()
    global AudioSegment
    try:
        _AudioSegment = importlib.import_module("pydub").AudioSegment
    except ImportError:
        print("pydub is missing. Run setup_environment.py first.", file=sys.stderr)
        return 2
    AudioSegment = _AudioSegment
    try:
        library = load_library(args.output.expanduser().resolve(), args.min_score)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Cannot load clip library: {exc}", file=sys.stderr)
        return 2
    clip_count = sum(len(items) for items in library.values())
    print(f"Loaded {clip_count} clips covering {len(library)} different words.")
    if not library:
        print("The library contains no usable clips.", file=sys.stderr)
        return 2
    match_index = build_match_index(library)

    def process(text: str, save_path: Path | None = None) -> bool:
        words = split_sentence(text)
        if not words:
            print("No words found.")
            return False
        audio, missing, selections = build_sentence(
            words, library, match_index, args.mode, max(0, args.gap_ms), max(0, args.missing_gap_ms),
            not args.no_normalize, args.target_dbfs, args.strict,
        )
        if missing:
            print("Missing:", ", ".join(dict.fromkeys(missing)))
        if audio is None:
            print("Sentence was not played.")
            return False
        describe_selections(selections)
        if save_path:
            destination = save_path.expanduser().resolve()
            destination.parent.mkdir(parents=True, exist_ok=True)
            audio.export(destination, format="wav")
            print(f"Saved: {destination}")
        else:
            play_wav(audio)
        return True

    if args.text:
        process(args.text, args.save)
        return 0
    if args.save:
        print("--save requires --text.", file=sys.stderr)
        return 2
    print("Type a Danish sentence and press Enter. Commands: :quit, :words, :help")
    while True:
        try:
            text = input("\nBumblebee> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not text:
            continue
        if text.lower() in {":quit", ":exit", "quit", "exit"}:
            break
        if text.lower() == ":help":
            print("Enter text to play it. :words lists the available vocabulary. :quit exits.")
        elif text.lower() == ":words":
            print(", ".join(sorted(library)))
        else:
            try:
                process(text)
            except Exception as exc:
                print(f"Playback failed: {exc}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
