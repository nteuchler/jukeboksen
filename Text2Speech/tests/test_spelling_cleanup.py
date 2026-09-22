import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from bumblebee_import import corrected_word, safe_component
from bumblebee_player import combine_phrase_clips, load_library
from correct_clip_names import migrate


def make_library(tmp_path):
    output = tmp_path / 'output'
    for folder in ['avokaten', 'advokaten', 'gitaren']:
        (output / 'clips' / folder).mkdir(parents=True)
    (output / 'clips/avokaten/song_01.wav').write_bytes(b'original audio one')
    (output / 'clips/advokaten/song_02.wav').write_bytes(b'original audio two')
    records = [
        {'word': 'avokaten', 'file': 'clips/avokaten/song_01.wav', 'score': .9, 'approved': None},
        {'word': 'advokaten', 'file': 'clips/advokaten/song_02.wav', 'score': .8, 'approved': True},
        {'word': 'gitaren', 'file': 'clips/gitaren/missing.wav', 'score': .7, 'approved': False},
    ]
    index = {'version': 1, 'clips': records, 'processed_songs': {'song': {'song_id': 'song'}}}
    (output / 'index.json').write_text(json.dumps(index))
    corrections = tmp_path / 'map.tsv'
    corrections.write_text('avokaten\tadvokaten\ngitaren\tguitaren\n')
    return output, corrections, index


def test_migration_merges_without_losing_audio_and_updates_missing_references(tmp_path):
    output, corrections, original = make_library(tmp_path)
    summary = migrate(output, corrections, tmp_path / 'backups', apply=True)
    assert summary['moved_existing_files'] == 1
    assert summary['existing_missing_references'] == 1
    assert not (output / 'clips/avokaten').exists()
    assert (output / 'clips/advokaten/song_01.wav').read_bytes() == b'original audio one'
    assert (output / 'clips/advokaten/song_02.wav').read_bytes() == b'original audio two'
    new = json.loads((output / 'index.json').read_text())
    assert new['clips'][0]['word'] == 'advokaten'
    assert new['clips'][0]['original_word'] == 'avokaten'
    assert new['clips'][2]['file'] == 'clips/guitaren/missing.wav'
    assert new['clips'][2]['approved'] is False
    assert new['processed_songs'] == original['processed_songs']
    assert corrected_word('avokaten', new) == 'advokaten'
    assert corrected_word('allerede', new) == 'allerede'
    assert len(load_library(output, 0)['advokaten']) == 2
    backup = next((tmp_path / 'backups').iterdir())
    assert json.loads((backup / 'index.json').read_text()) == original
    assert json.loads((backup / 'rename_log.json').read_text())['complete']


def test_collision_aborts_before_touching_index_or_audio(tmp_path):
    output, corrections, original = make_library(tmp_path)
    target = output / 'clips/advokaten/song_01.wav'
    target.write_bytes(b'different recording')
    with pytest.raises(ValueError, match='Collision'):
        migrate(output, corrections, tmp_path / 'backups', apply=True)
    assert target.read_bytes() == b'different recording'
    assert (output / 'clips/avokaten/song_01.wav').exists()
    assert json.loads((output / 'index.json').read_text()) == original


def test_dry_run_does_not_rename(tmp_path):
    output, corrections, original = make_library(tmp_path)
    migrate(output, corrections, tmp_path / 'backups')
    assert (output / 'clips/avokaten/song_01.wav').exists()
    assert json.loads((output / 'index.json').read_text()) == original
    assert not (tmp_path / 'backups').exists()


def test_multiword_clip_is_available_in_normal_sentence():
    library = {'imorgen': [{'word': 'i morgen'}], 'en': [{'word': 'en'}],
               'engang': [{'word': 'en gang'}], 'venengang': [{'word': 'ven en gang'}]}
    assert combine_phrase_clips(['jeg', 'kommer', 'i', 'morgen'], library) == ['jeg', 'kommer', 'i morgen']
    assert combine_phrase_clips(['min', 'ven', 'en', 'gang'], library) == ['min', 'ven en gang']
    assert combine_phrase_clips(['jeg', 'har', 'en', 'bil'], library) == ['jeg', 'har', 'en', 'bil']


def test_player_skips_old_uncreatable_paths(tmp_path):
    output, _, _ = make_library(tmp_path)
    path = output / 'index.json'
    index = json.loads(path.read_text())
    index['clips'].append({'word': 'næh ' * 100,
                          'file': 'clips/' + 'næh_' * 100 + '/song.wav', 'score': 1})
    path.write_text(json.dumps(index))
    library = load_library(output, 0)
    assert sum(map(len, library.values())) == 2
