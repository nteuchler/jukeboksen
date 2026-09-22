# Clip spelling review

Reviewed all 5,058 word folders and the index context for transcription errors.
Applied 633 likely corrections, updating 931 clip records and moving 188 existing
WAV files into corrected word folders. All 8,180 existing audio files were
preserved without re-encoding; song-derived WAV basenames remain stable.

- `spelling_corrections.tsv`: old folder label and inferred corrected spelling.
  Underscores represent spaces in corrected word labels.
- `folder_review.csv`: every original folder, its destination, file counts, and
  example song context. `unchanged` includes valid names, foreign words, vocal
  sounds and fragments where the intended word could not be reliably recovered.
- `../output/index.json`: corrected `word` and `file` fields, `original_word`
  provenance on changed records, and the reusable `word_corrections` map.

Corrections are best guesses from spelling and indexed lyric context, not a
fresh audio transcription. Some clips can still be misheard or poorly cut.
The corpus already had 26,731 indexed paths without local WAV files; none were
deleted or fabricated during this review. The player skips these missing clips,
including old paths too long for the filesystem.

The importer applies `word_corrections` on subsequent imports and overwrites.
The player rebuilds its word/alias index from the updated index each time it
starts, and recognizes corrected multiword labels in sentences.
`processed_songs`, source song IDs, offsets, confidence scores and approval flags
are preserved. `output/failures.json` is an unchanged historical import error log.

Backup: `../../.backups/text2speech-spelling-20260922T211819318775Z/`.
It contains the original `index.json`, correction table and `rename_log.json`.
The log records each source/destination path, affected index record and original
folder. To reverse this batch, move each `existing_moves` destination back to its
source (without overwriting anything), recreate `original_folders`, then restore
the backed-up index. Do this before any further imports or edits.

Run the migration planner without changes:

```sh
python3 Text2Speech/correct_clip_names.py
```

The planner refuses path collisions instead of overwriting recordings. Applying
it makes another backup and checks the final paths, file identities and sizes.
After a batch is applied, it is safe to leave the correction table in place;
future import corrections are controlled by `output/index.json`.
