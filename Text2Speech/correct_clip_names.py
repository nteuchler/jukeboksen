#!/usr/bin/env python3
"""Apply reviewed spelling corrections without overwriting or re-encoding clips.

Run without --apply to inspect a plan. The journal and original index are saved
in a timestamped backup directory before any moves. Audio basenames retain their
song IDs, time offsets and occurrence IDs for importer compatibility.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from bumblebee_import import safe_component


def migrate(output: Path, corrections: Path, backup_root: Path, apply: bool = False):
    output = output.resolve()
    index_path = output / 'index.json'
    original = index_path.read_bytes()
    index = json.loads(original)
    mapping = dict(csv.reader(corrections.read_text().splitlines(), delimiter='\t'))
    folders = sorted(p.name for p in (output / 'clips').iterdir() if p.is_dir())
    files = {p.relative_to(output).as_posix(): (p.stat().st_ino, p.stat().st_size)
             for p in (output / 'clips').rglob('*') if p.is_file()}
    records = index['clips']
    old_paths = {r['file'] for r in records}
    all_paths = old_paths | files.keys()
    moves = {}
    for old in all_paths:
        parts = Path(old).parts
        if len(parts) != 3 or parts[0] != 'clips':
            raise ValueError(f'Unexpected clip path: {old}')
        if parts[1] in mapping:
            new_folder = safe_component(mapping[parts[1]].replace('_', ' '))
            new = f'clips/{new_folder}/{parts[2]}'
            if new != old:
                if new in all_paths or new in moves.values():
                    raise ValueError(f'Collision: {old} -> {new}; no files changed')
                moves[old] = new
    changed_records = []
    for number, record in enumerate(records):
        label = Path(record['file']).parent.name
        if label in mapping:
            changed_records.append({'record': number, 'old_word': record['word'],
                                    'old_file': record['file']})
            record.setdefault('original_word', record['word'])
            record['word'] = mapping[label].replace('_', ' ')
            record['file'] = moves.get(record['file'], record['file'])
    index.setdefault('word_corrections', {}).update({
        key: value.replace('_', ' ') for key, value in mapping.items()
    })
    index['updated_at'] = datetime.now(timezone.utc).isoformat()
    summary = {'reviewed_folders': len(folders), 'corrected_labels': len(mapping),
               'updated_records': len(changed_records),
               'moved_existing_files': len(files.keys() & moves.keys()),
               'existing_files': len(files), 'existing_missing_references': len(old_paths - files.keys())}
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if not apply:
        return summary
    # Guard against a concurrent importer or file copy between planning and apply.
    if index_path.read_bytes() != original:
        raise RuntimeError('Index changed during review; rerun the migration')
    current = {p.relative_to(output).as_posix(): (p.stat().st_ino, p.stat().st_size)
               for p in (output / 'clips').rglob('*') if p.is_file()}
    if current != files:
        raise RuntimeError('Clips changed during review; rerun the migration')
    backup = backup_root / datetime.now(timezone.utc).strftime('text2speech-spelling-%Y%m%dT%H%M%S%fZ')
    backup.mkdir(parents=True)
    (backup / 'index.json').write_bytes(original)
    shutil.copy2(corrections, backup / corrections.name)
    journal = {'output': str(output), 'summary': summary,
               'original_index_sha256': hashlib.sha256(original).hexdigest(),
               'original_folders': folders, 'moves': moves,
               'existing_moves': {a: b for a, b in moves.items() if a in files},
               'changed_records': changed_records, 'complete': False}
    journal_path = backup / 'rename_log.json'
    journal_path.write_text(json.dumps(journal, ensure_ascii=False, indent=2))
    completed = []
    try:
        for old, new in journal['existing_moves'].items():
            destination = output / new
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists():
                raise FileExistsError(destination)
            (output / old).rename(destination)
            completed.append((old, new))
        for old_label, new_label in mapping.items():
            source = output / 'clips' / old_label
            destination = output / 'clips' / safe_component(new_label.replace('_', ' '))
            if source != destination and source.is_dir():
                destination.mkdir(exist_ok=True)
                source.rmdir()  # Only removes empty directories.
        expected_files = {moves.get(path, path): identity for path, identity in files.items()}
        actual_files = {p.relative_to(output).as_posix(): (p.stat().st_ino, p.stat().st_size)
                        for p in (output / 'clips').rglob('*') if p.is_file()}
        assert actual_files == expected_files, 'File preservation check failed'
        new_paths = {r['file'] for r in records}
        assert len(new_paths) == len(old_paths), 'Index paths became duplicated'
        assert len(new_paths - actual_files.keys()) == summary['existing_missing_references']
        assert not actual_files.keys() - new_paths, 'Unindexed clips created'
        temporary = index_path.with_suffix('.json.spelling.tmp')
        temporary.write_text(json.dumps(index, ensure_ascii=False, indent=2) + '\n')
        temporary.replace(index_path)
    except BaseException:
        for name in folders:
            (output / 'clips' / name).mkdir(exist_ok=True)
        for old, new in reversed(completed):
            (output / new).rename(output / old)
        index_path.write_bytes(original)
        raise
    journal['complete'] = True
    journal_path.write_text(json.dumps(journal, ensure_ascii=False, indent=2))
    print('Backup and reversal log:', backup)
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path(__file__).parent / 'output')
    parser.add_argument('--corrections', type=Path, default=Path(__file__).parent / 'review/spelling_corrections.tsv')
    parser.add_argument('--backup-root', type=Path, default=Path(__file__).resolve().parents[1] / '.backups')
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    migrate(args.output, args.corrections, args.backup_root, args.apply)
