import json
from pathlib import Path
import tempfile
import unittest

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


if __name__ == '__main__':
    unittest.main()
