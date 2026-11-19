"""dq4story3compat 이 건너뛰는 구간을 고정 표로 두고, 분모를 구간 표 전체로 세는지(롬 없이)."""
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[1] / 'dq5' / 'tools'), str(HERE.parents[2] / 'fc' / 'dq4' / 'tools')]

import dq4story3 as story  # noqa: E402
import dq4story3compat as compat  # noqa: E402
import dq4storytokens as tokens  # noqa: E402

NAMES = [n for n, _, _ in story.SEGMENTS]
OPTS = {n: o for n, _, o in story.SEGMENTS}
MAIN_SKIPS = {n for n in compat.SKIPPED if not OPTS[n].get('side')}


def results(skip=(), fail=()):
    out = []
    for n in NAMES:
        if n in skip:
            out.append({'name': n, 'status': 'skipped'})
        else:
            out.append({'name': n, 'status': 'failed' if n in fail else 'passed'})
    return out


class SkipTable(unittest.TestCase):
    def test_skips_are_exactly_the_table(self):
        self.assertEqual({n for n, t, o in story.SEGMENTS if compat.skip_reason((n, t, o))}, set(compat.SKIPPED))

    def test_main_line_skips_say_how_the_next_segment_starts(self):
        self.assertEqual(MAIN_SKIPS - set(compat.STAND_IN), {'merchant'})

    def test_stand_ins_drop_only_hooked_tokens(self):
        for name, toks in compat.STAND_IN.items():
            with self.subTest(name):
                orig = dict((n, t) for n, t, _ in story.SEGMENTS)[name].split(';')
                kept = [t for t in orig if t.split(':')[0] not in tokens.HOOKED]
                self.assertEqual(toks.split(';'), kept)

    def test_merchant_leaves_nothing_later_segments_need(self):
        after = NAMES[NAMES.index('merchant') + 1:]
        herb = OPTS['merchant']['items'][0]
        for n in after:
            o = OPTS[n]
            self.assertNotIn(herb, list(o.get('items', ())) + list(o.get('no_items', ()))
                             + [i for _, i in o.get('give', ())], n)
            self.assertNotIn(f'{herb:02X}', dict((m, t) for m, t, _ in story.SEGMENTS)[n].upper(), n)
        gold_set = next(k for k, n in enumerate(after) if 'gold' in OPTS[n])
        checks = [k for k, n in enumerate(after) if 'gold_min' in OPTS[n] and not OPTS[n].get('side')]
        self.assertTrue(all(k > gold_set for k in checks), [after[k] for k in checks])


class Tally(unittest.TestCase):
    SKIP = set(compat.SKIPPED) - set(compat.STAND_IN)

    def test_all_walked_and_the_table_skipped_passes(self):
        t = compat.tally(results(self.SKIP))
        self.assertEqual((t['status'], t['walked'], t['skipped'], t['expected']),
                         ('passed', len(NAMES) - len(self.SKIP), len(self.SKIP), len(NAMES)))

    def test_an_extra_skip_fails(self):
        self.assertEqual(compat.tally(results(self.SKIP | {'tom'}))['status'], 'failed')

    def test_a_missing_skip_fails(self):
        self.assertEqual(compat.tally(results(self.SKIP - {'merchant'}))['status'], 'failed')

    def test_a_short_run_fails(self):
        self.assertEqual(compat.tally(results(self.SKIP)[:-3])['status'], 'failed')

    def test_a_failed_segment_fails(self):
        self.assertEqual(compat.tally(results(self.SKIP, fail={'tom'}))['status'], 'failed')


if __name__ == '__main__':
    unittest.main()
