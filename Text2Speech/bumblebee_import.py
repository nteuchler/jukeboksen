#!/usr/bin/env python3
"""Build a word-clip library from a folder of songs.

Pipeline:
  1. Demucs isolates vocals for easier recognition.
  2. WhisperX transcribes and aligns individual words.
  3. The corresponding time ranges are cut from the ORIGINAL song.
  4. clips/index.json records every generated clip.

Use only audio you are legally allowed to process.
"""

from __future__ import annotations

import argparse
import gc
import hashlib
import json
import re
import shutil
import subprocess
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

SUPPORTED_EXTENSIONS = {".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Automatically split songs into indexed, word-level WAV clips."
    )
    parser.add_argument("input", type=Path, help="Folder containing songs")
    parser.add_argument("output", type=Path, help="Folder to create/update")
    parser.add_argument("--language", default="da", help="Whisper language code (default: da)")
    parser.add_argument(
        "--model",
        default="small",
        help="Whisper model (default: small; use large-v3 on a capable GPU)",
    )
    parser.add_argument("--device", choices=("auto", "cuda", "cpu"), default="auto")
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--padding-ms", type=int, default=100)
    parser.add_argument("--min-score", type=float, default=0.45)
    parser.add_argument("--fade-ms", type=int, default=12)
    parser.add_argument("--keep-vocals", action="store_true", help="Keep separated vocal WAV files")
    parser.add_argument("--overwrite", action="store_true", help="Reprocess songs already in the index")
    parser.add_argument("--dry-run", action="store_true", help="List songs without processing them")
    return parser.parse_args()


def safe_component(text: str, fallback: str = "word") -> str:
    text = unicodedata.normalize("NFC", text).lower().strip()
    text = re.sub(r"[^0-9a-z\u00e6\u00f8\u00e5]+", "_", text, flags=re.IGNORECASE)
    return text.strip("_") or fallback
    text = re.sub(r"[^0-9a-zæøå]+", "_", text, flags=re.IGNORECASE)
    return text.strip("_") or fallback


def normalize_word(text: str) -> str:
    text = unicodedata.normalize("NFC", text).lower().strip()
    # Strip punctuation while preserving Danish letters and apostrophes inside words.
    return re.sub(
        r"(^[^0-9a-z\u00e6\u00f8\u00e5]+|[^0-9a-z\u00e6\u00f8\u00e5]+$)",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"(^[^0-9a-zæøå]+|[^0-9a-zæøå]+$)", "", text, flags=re.IGNORECASE)
    return text


def song_id(path: Path, root: Path) -> str:
    relative = str(path.relative_to(root))
    digest = hashlib.sha1(relative.encode("utf-8")).hexdigest()[:8]
    return f"{safe_component(path.stem, 'song')}_{digest}"


def run(command: list[str]) -> None:
    print("  $", " ".join(command), flush=True)
    subprocess.run(command, check=True)


def find_songs(folder: Path) -> list[Path]:
    return sorted(
        path for path in folder.rglob("*")
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
    )


def load_index(path: Path) -> dict:
    if path.exists():
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    return {"version": 1, "clips": [], "processed_songs": {}}


def corrected_word(word: str, index: dict) -> str:
    """Reuse reviewed labels when importing or overwriting song clips."""
    return index.get("word_corrections", {}).get(safe_component(word), word)


def save_index(path: Path, index: dict) -> None:
    index["updated_at"] = datetime.now(timezone.utc).isoformat()
    temporary = path.with_suffix(".json.tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(index, handle, ensure_ascii=False, indent=2)
    temporary.replace(path)


def separate_vocals(song: Path, sid: str, work: Path, device: str) -> Path:
    staging = work / "staging"
    demucs_out = work / "demucs"
    staging.mkdir(parents=True, exist_ok=True)
    staged_song = staging / f"{sid}{song.suffix.lower()}"
    shutil.copy2(song, staged_song)

    run([
        sys.executable, "-m", "demucs",
        "--two-stems", "vocals",
        "-n", "htdemucs",
        "-d", device,
        "--out", str(demucs_out),
        str(staged_song),
    ])
    vocals = demucs_out / "htdemucs" / sid / "vocals.wav"
    if not vocals.exists():
        raise FileNotFoundError(f"Demucs did not create {vocals}")
    return vocals


def flatten_words(aligned_result: dict) -> list[dict]:
    words: list[dict] = []
    for segment in aligned_result.get("segments", []):
        for item in segment.get("words", []):
            if "start" in item and "end" in item and item.get("word"):
                words.append(item)
    return words


def main() -> int:
    args = parse_args()
    input_dir = args.input.expanduser().resolve()
    output_dir = args.output.expanduser().resolve()

    if not input_dir.is_dir():
        print(f"Input folder does not exist: {input_dir}", file=sys.stderr)
        return 2
    if args.padding_ms < 0 or args.fade_ms < 0:
        print("Padding and fade must be non-negative.", file=sys.stderr)
        return 2

    songs = find_songs(input_dir)
    if not songs:
        print("No supported audio files found.")
        return 0
    print(f"Found {len(songs)} song(s).")
    if args.dry_run:
        for song in songs:
            print(song.relative_to(input_dir))
        return 0

    try:
        import torch
        import whisperx
        from pydub import AudioSegment
    except ImportError as exc:
        print(
            f"Missing Python dependency: {exc.name}\n"
            "Install dependencies with: pip install demucs whisperx pydub",
            file=sys.stderr,
        )
        return 2

    if shutil.which("ffmpeg") is None:
        print("FFmpeg is required but was not found in PATH.", file=sys.stderr)
        return 2

    device = args.device
    if device == "auto":
        device = "cuda" if torch.cuda.is_available() else "cpu"
    compute_type = "float16" if device == "cuda" else "int8"
    print(f"Using {device}; loading WhisperX {args.model} for language {args.language}...")

    output_dir.mkdir(parents=True, exist_ok=True)
    clips_dir = output_dir / "clips"
    work_dir = output_dir / "work"
    vocals_dir = output_dir / "vocals"
    clips_dir.mkdir(exist_ok=True)
    work_dir.mkdir(exist_ok=True)
    index_path = output_dir / "index.json"
    index = load_index(index_path)

    try:
        asr_model = whisperx.load_model(
            args.model,
            device,
            compute_type=compute_type,
            language=args.language,
        )
        align_model, align_metadata = whisperx.load_align_model(
            language_code=args.language,
            device=device,
        )
    except Exception as exc:
        print(f"Could not load the speech models ({type(exc).__name__}).", file=sys.stderr)
        print(
            "WhisperX downloads its models from Hugging Face the first time it runs. "
            "Check your internet connection or firewall, then run the importer again.",
            file=sys.stderr,
        )
        if device == "cuda":
            torch.cuda.empty_cache()
        return 2

    failures: list[dict] = []
    for number, song in enumerate(songs, start=1):
        relative = str(song.relative_to(input_dir))
        sid = song_id(song, input_dir)
        print(f"\n[{number}/{len(songs)}] {relative}")

        if relative in index["processed_songs"] and not args.overwrite:
            print("  Already processed; skipping.")
            continue

        try:
            vocals_path = separate_vocals(song, sid, work_dir, device)
            print("  Demucs finished; loading the separated vocals...", flush=True)
            detection_audio = whisperx.load_audio(str(vocals_path))
            print(
                "  Transcribing vocals (this has no progress bar and can take several minutes on CPU)...",
                flush=True,
            )
            transcription = asr_model.transcribe(
                detection_audio,
                batch_size=args.batch_size,
            )
            print("  Aligning the detected words...", flush=True)
            aligned = whisperx.align(
                transcription["segments"],
                align_model,
                align_metadata,
                detection_audio,
                device,
                return_char_alignments=False,
            )
            detected_words = flatten_words(aligned)
            print("  Cutting word clips from the original song...", flush=True)
            original = AudioSegment.from_file(song)
            generated: list[dict] = []

            if args.overwrite:
                old_files = {
                    clip["file"] for clip in index["clips"]
                    if clip.get("song_id") == sid
                }
                index["clips"] = [
                    clip for clip in index["clips"] if clip.get("song_id") != sid
                ]
                for old_file in old_files:
                    old_path = output_dir / old_file
                    if old_path.is_file():
                        old_path.unlink()

            for occurrence, item in enumerate(detected_words):
                word = normalize_word(item["word"])
                score = float(item.get("score", 1.0))
                if not word or score < args.min_score:
                    continue
                original_word = word
                word = corrected_word(word, index)

                start_ms = max(0, round(float(item["start"]) * 1000) - args.padding_ms)
                end_ms = min(len(original), round(float(item["end"]) * 1000) + args.padding_ms)
                if end_ms <= start_ms:
                    continue

                word_folder = clips_dir / safe_component(word)
                word_folder.mkdir(parents=True, exist_ok=True)
                filename = f"{sid}_{start_ms:08d}_{occurrence:04d}.wav"
                destination = word_folder / filename
                clip_audio = original[start_ms:end_ms]
                fade = min(args.fade_ms, len(clip_audio) // 3)
                if fade:
                    clip_audio = clip_audio.fade_in(fade).fade_out(fade)
                clip_audio.export(destination, format="wav")

                record = {
                    "word": word,
                    "file": destination.relative_to(output_dir).as_posix(),
                    "song": relative,
                    "song_id": sid,
                    "start": float(item["start"]),
                    "end": float(item["end"]),
                    "score": score,
                    "approved": None,
                }
                if word != original_word:
                    record["original_word"] = original_word
                index["clips"].append(record)
                generated.append(record)

            index["processed_songs"][relative] = {
                "song_id": sid,
                "detected_words": len(detected_words),
                "generated_clips": len(generated),
                "processed_at": datetime.now(timezone.utc).isoformat(),
            }
            save_index(index_path, index)
            print(f"  Generated {len(generated)} clips from {len(detected_words)} aligned words.")

            if args.keep_vocals:
                vocals_dir.mkdir(exist_ok=True)
                shutil.copy2(vocals_path, vocals_dir / f"{sid}.wav")

        except Exception as exc:  # Continue so one broken song does not stop the batch.
            failures.append({"song": relative, "error": str(exc)})
            print(f"  FAILED: {exc}", file=sys.stderr)
            save_index(index_path, index)

    shutil.rmtree(work_dir, ignore_errors=True)

    print(f"\nDone. Index: {index_path}")
    print(f"Total indexed clips: {len(index['clips'])}")
    if failures:
        failure_path = output_dir / "failures.json"
        failure_path.write_text(json.dumps(failures, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Failures: {len(failures)} (see {failure_path})")

    del asr_model, align_model
    gc.collect()
    if device == "cuda":
        torch.cuda.empty_cache()
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
