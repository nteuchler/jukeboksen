# Bumblebee song-word importer

This program extracts Danish song words into WAV clips and plays new sentences
with those clips. It uses Python scripts only; there are no batch launchers.

## First-time setup

Install 64-bit Python 3.11, then open PowerShell in this folder and run:

```powershell
py -3.11 setup_environment.py
```

The setup creates `.venv` and installs the required Python packages. If it
reports that FFmpeg is missing, install it with:

```powershell
winget install --id Gyan.FFmpeg --exact
```

Open a new terminal after installing FFmpeg.

## Process songs

Put MP3, WAV, FLAC, M4A, AAC or OGG files in `songs`, then run:

```powershell
.\.venv\Scripts\python.exe bumblebee_import.py songs output --language da --device auto --model small --batch-size 2
```

Clips are written under `output\clips`; their metadata is in
`output\index.json`. CPU transcription has no percentage bar and may take
several minutes per song.

To use different folders:

```powershell
.\.venv\Scripts\python.exe bumblebee_import.py "D:\Music\Danish songs" "D:\Bumblebee output" --language da --model small --batch-size 2
```

## Play sentences

After processing at least one song, run:

```powershell
.\.venv\Scripts\python.exe bumblebee_player.py output --mode random
```

At the `Bumblebee>` prompt, type a sentence. Use `:words` to list available
words and `:quit` to exit.

To save a sentence rather than play it:

```powershell
.\.venv\Scripts\python.exe bumblebee_player.py output --text "jeg har pizza" --save sentence.wav
```

## Useful options

```powershell
# List songs without processing them
.\.venv\Scripts\python.exe bumblebee_import.py songs output --dry-run

# Reprocess already indexed songs
.\.venv\Scripts\python.exe bumblebee_import.py songs output --language da --overwrite

# Use the most accurate model on a capable GPU
.\.venv\Scripts\python.exe bumblebee_import.py songs output --language da --device cuda --model large-v3
```

## Reviewed clip spellings

The library index now contains reviewed spelling corrections and retains the
original labels as `original_word`. Both the player and importer use
`output/index.json`; restart the player after updating it. The importer reuses
its `word_corrections` map during future imports, including `--overwrite`.
Corrected multiword clips can be used in ordinary sentences.

See `review/README.md`, `review/folder_review.csv` and
`review/spelling_corrections.tsv` for the review and backup details.
