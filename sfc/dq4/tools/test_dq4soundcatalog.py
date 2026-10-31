import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

import dq4soundcatalog as catalog

ROM = Path(__file__).resolve().parents[3] / 'rom/dq5.sfc'


class CatalogTests(unittest.TestCase):
    def test_gate_overlap_and_boundary(self):
        score = {'channels': [{}], 'timeline': [
            {'op': 'note', 'tick': 0, 'gate': 4, 'note': 60},
            {'op': 'note', 'tick': 2, 'gate': 2, 'note': 64},
            {'op': 'note', 'tick': 4, 'gate': 4, 'note': 67, 'bend': 1},
        ]}
        result = catalog.score_metrics(score)
        self.assertEqual(result['peak_gate_voices'], 2)
        self.assertEqual(result['midi_range'], [60, 67])
        self.assertEqual(result['expressive_features'], ['bend'])

    def test_catalog_keeps_missing_scores_and_does_not_promote_candidates(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)

            def write(relative, data):
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(data), encoding='utf-8')

            write('sfc/dq5/sound/sfx/index.json', [
                {'id': identifier, 'command': '0C ' + identifier.replace('-', ' '), 'scene': cue}
                for cue, (identifier, _, _) in catalog.NATIVE_CUES.items()
            ])
            write('sfc/dq5/sound/songs/index.json', [])
            write('nds/dq4/sound/songs/index.json', {
                '01': {'kind': 'STRM', 'title': 'title', 'name': 'stream', 'score': None},
                '05': {'kind': 'SSEQ', 'title': 'field', 'name': 'field', 'score': 'missing.json'},
            })
            write('nds/dq4/sound/sfx/index.json', {
                '12C': {'title': 'select', 'name': 'select', 'score': 'select.json'},
            })
            write('nds/dq4/sound/sfx/select.json', {
                'id': '12C', 'kind': 'sfx', 'channels': [{}],
                'timeline': [{'op': 'note', 'tick': 1, 'gate': 2, 'note': 60}],
            })
            result = catalog.build_catalog(root)
            self.assertEqual(result['summary'], {
                'songs': 2, 'sfx': 1, 'exact_reuse_verified': 0, 'unsupported': 1,
            })
            self.assertEqual(result['entries'][0]['conversion_status'], 'existing_overture')
            self.assertEqual(result['entries'][1]['requirements'], ['missing_score_file'])
            candidate = result['entries'][2]
            self.assertEqual(candidate['reuse_candidates'][0]['dq5'], '33-00')
            self.assertIsNone(candidate['exact_reuse'])
            self.assertEqual(candidate['conversion_status'], 'not_evaluated')
            self.assertEqual(result, catalog.build_catalog(root))

    def test_asset_relative_paths_cannot_escape(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, '폴더 밖'):
                catalog.score_path(Path(directory), '../outside.json')

    @unittest.skipUnless(ROM.exists(), 'user supplied DQ5 ROM required')
    def test_inn_reuse_checks_both_complete_parts(self):
        notes = ([86, 85, 84, 83, 81, 74, 86], [78, 77, 76, 74, 72, 66, 78])
        score = {'timeline': [
            {'tick': i * 24, 'note': note, 'ch': f'track{ch}', 'op': 'note'}
            for ch, part in enumerate(notes) for i, note in enumerate(part)
        ]}
        result = catalog.verify_inn(score, ROM)
        self.assertEqual([e['matched_notes'] for e in result['evidence']], [7, 7])
        score['timeline'][-1]['note'] += 1
        with self.assertRaisesRegex(ValueError, '음높이 불일치'):
            catalog.verify_inn(score, ROM)

    def test_inn_reuse_merges_two_dq5_tracks_per_part(self):
        # 지어낸 4트랙 시퀀스를 1D 자리에 둔다. 트랙 0·1 이 NDS track0, 2·3 이 track1 이고 둘째 트랙은 쉼 뒤에 이어 분다.
        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'dq5/tools'))
        import dq5song
        seq = dq5song.assemble([
            'tempo 20', 'track A', 'track B', 'track C', 'track D',
            'A:', '  note 30 len 18', '  note 32', '  note 34', '  end',
            'B:', '  rest len 48', '  note 35 len 18', '  note 37', '  end',
            'C:', '  note 28 len 18', '  note 29', '  note 2B', '  end',
            'D:', '  rest len 48', '  note 2D len 18', '  note 2F', '  end',
        ])
        parts = ([0x30, 0x32, 0x34, 0x35, 0x37], [0x28, 0x29, 0x2B, 0x2D, 0x2F])
        score = {'timeline': [
            {'tick': i * 24, 'note': note + 23, 'ch': f'track{ch}', 'op': 'note'}
            for ch, part in enumerate(parts) for i, note in enumerate(part)
        ]}
        with tempfile.TemporaryDirectory() as directory, \
                mock.patch('dq5spc.sequences', return_value={0x1D: (0, 0, len(seq))}), \
                mock.patch('dq5spc.body', return_value=seq):
            rom = Path(directory) / 'dq5.sfc'
            rom.write_bytes(b'')
            result = catalog.verify_inn(score, rom)
            self.assertEqual([e['matched_notes'] for e in result['evidence']], [5, 5])
            self.assertEqual([e['max_tick_difference'] for e in result['evidence']], [0, 0])
            score['timeline'][3]['tick'] += 2
            with self.assertRaisesRegex(ValueError, '1틱 초과'):
                catalog.verify_inn(score, rom)
            score['timeline'][3]['tick'] -= 2
            score['timeline'][-1]['note'] += 1
            with self.assertRaisesRegex(ValueError, '음높이 불일치'):
                catalog.verify_inn(score, rom)
            del score['timeline'][0]
            with self.assertRaisesRegex(ValueError, '음 수 불일치'):
                catalog.verify_inn(score, rom)


if __name__ == '__main__':
    unittest.main()
