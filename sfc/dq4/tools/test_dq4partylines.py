"""장마다 일행 전용 OBJ 줄(dq4people.PARTIES)이 그 장 일행이 서는 모든 맵 그룹에서 그 일행 색으로 실리는지 롬 없이 본다.

그룹은 빌드 데이터(dq4groupbuild.LINKS 의 장, FLAG_VISITS)로 모으고, 그 장 걷기 검사 표(dq4ch<N>walkcheck)와 필드 길
검사 표(dq4ch<N>fieldwalkcheck)가 들르는 맵이 그 안에 드는지 견준다. 새 장의 검사·빌드 옵션·깃발·일행 인물이 생겼는데
PARTIES 에 그 장이 없으면 실패한다. 헤드리스 CGRAM 실측은 가드 dq4-party-palette(dq4partypalcheck.py).
"""
import importlib
import re
import sys
import tomllib
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[1] / 'dq5' / 'tools'), str(HERE.parents[2] / 'fc' / 'dq4' / 'tools')]

import dq4groupbuild  # noqa: E402
import dq4people as P  # noqa: E402

ADD = '— dq4people.PARTIES 에 그 장 일행(역할)을 넣으라'
MAP = re.compile(r'^([0-9A-F]{2})/[0-9A-F]{2}$')


def person(role):
    found = [p for p in P.PEOPLE if p.role == role]
    return found[0] if len(found) == 1 else None


def walk_chapters():
    """{장: 걷기 검사 모듈 이름} — dq4ch<N>walkcheck.py 파일에서."""
    return {int(m[1]): f'dq4ch{m[1]}walkcheck' for f in HERE.glob('dq4ch*walkcheck.py')
            if (m := re.fullmatch(r'dq4ch(\d+)walkcheck\.py', f.name))}


def walk_groups(chapter):
    """그 장 걷기 검사 표가 순간이동하거나 끝에 서는 맵의 그룹. 머리(HEAD) 앞 구간은 앞 장에서 넘어오는 길이라
    머리 마지막 구간부터 센다."""
    mod = importlib.import_module(walk_chapters()[chapter])
    head = getattr(mod, 'HEAD', 0)
    groups = set()
    for seg in mod.SEGMENTS[max(head - 1, 0):]:
        to = [seg[2].split(',')[0]] if seg[1] == 'warp' else []
        want = seg[3] if len(seg) > 3 and isinstance(seg[3], dict) else {}
        for m in to + ([want['map']] if isinstance(want.get('map'), str) else []):
            if MAP.match(m):
                groups.add(int(m[:2], 16))
    return groups


def field_groups(chapter):
    """그 장 필드 길 검사(dq4ch<N>fieldwalkcheck.LEGS)가 들르는 FC 그룹의 맵 그룹."""
    path = HERE / f'dq4ch{chapter}fieldwalkcheck.py'
    if not path.exists():
        return set()
    mod = importlib.import_module(path.stem)
    fc_group = {m['fc']: g for g, maps in dq4groupbuild.LINKS.items() for m in maps}
    return {fc_group[f] for _, _, start, places in mod.LEGS for f in (start, *places) if isinstance(f, int)}


class TableTests(unittest.TestCase):
    def test_every_party_role_is_a_main_person_with_its_own_line(self):
        for chapter, roles in P.PARTIES.items():
            lines = []
            for role in roles:
                p = person(role)
                self.assertIsNotNone(p, f'{chapter}장 {role}: PEOPLE 에 하나만 있어야 함')
                self.assertTrue(p.main and p.palette is not None, f'{chapter}장 {role}: 전용 줄이 없음')
                if p.flag is not None:
                    self.assertEqual(P.FLAG_CHAPTERS.get(p.flag), chapter, f'{chapter}장 {role}: FLAG_CHAPTERS')
                lines.append(p.palette)
            self.assertEqual(len(lines), len(set(lines)), f'{chapter}장 일행 줄이 겹침')

    def test_every_party_person_flag_build_and_walk_has_a_chapter(self):
        listed = {r for roles in P.PARTIES.values() for r in roles}
        for p in P.PEOPLE:
            if p.main and p.palette is not None:
                self.assertIn(p.role, listed, f'전용 줄 {p.palette} 을 쓰는 {p.role} {ADD}')
        for flag, chapter in P.FLAG_CHAPTERS.items():
            self.assertIn(chapter, P.PARTIES, f'깃발 {flag} 의 {chapter}장 {ADD}')
        build = (HERE / 'dq4build.py').read_text()
        for n in map(int, re.findall(r"'--chapter(\d+)'", build)):
            self.assertIn(n, P.PARTIES, f'dq4build --chapter{n} 의 {n}장 {ADD}')
        for n in walk_chapters():
            self.assertIn(n, P.PARTIES, f'dq4ch{n}walkcheck 의 {n}장 {ADD}')

    def test_unflagged_party_lines_are_unique(self):
        # 깃발 없는 전용 줄은 세트 팔레트 기본 줄이라 장 하나만 쓸 수 있다
        fixed = [p.palette for p in P.PEOPLE if p.main and p.palette is not None and p.flag is None]
        self.assertEqual(len(fixed), len(set(fixed)))


class GroupTests(unittest.TestCase):
    def test_walk_and_field_checks_stay_in_the_party_groups(self):
        for chapter in sorted(P.PARTIES):
            if chapter == 0:
                continue
            groups = set(P.party_groups(chapter))
            for kind, seen in (('걷기', walk_groups(chapter) if chapter in walk_chapters() else set()),
                               ('필드 길', field_groups(chapter))):
                for g in sorted(seen - groups):
                    self.fail(f'{chapter}장 {kind} 검사가 들르는 그룹 {g:02X} 가 party_groups({chapter}) 에 없음 — '
                              f'dq4people.FLAG_VISITS 에 더하라')

    def test_party_lines_hold_the_party_color_in_every_group(self):
        pins = tomllib.loads(P.PINS.read_text())['person']
        for chapter, roles in sorted(P.PARTIES.items()):
            groups = P.party_groups(chapter)
            self.assertTrue(groups, f'{chapter}장 그룹 없음')
            for role in roles:
                p = person(role)
                for g in groups:
                    where = f'{chapter}장 {role} 줄 {p.palette} 그룹 {g:02X}'
                    if p.flag is not None:
                        self.assertIn(f'{g:02X}/FF', P.flag_maps(p.flag), f'{where}: 깃발 줄을 덮지 않음')
                    shared = sorted(n for n, q in pins.items() if f'{g:02X}' in q['groups'] and q['line'] == p.palette)
                    self.assertFalse(shared, f'{where}: 공용 인물이 같은 줄')
                    self.assertNotIn(p.palette, P.LENT_LINES.get(g, ()), f'{where}: 빌린 줄')
                    # 같은 장에 켜질 수 있는 다른 전용 줄 인물이 같은 줄을 쓰지 않는다(장 깃발은 다음 장에서 꺼짐)
                    rivals = [q.role for q in P.PEOPLE if q is not p and q.main and q.palette == p.palette
                              and q.flag is not None and P.FLAG_CHAPTERS.get(q.flag) == chapter]
                    self.assertFalse(rivals, f'{where}: {rivals}')

    def test_chapter3_followers_keep_their_colors_in_every_party_group(self):
        # 3장에서 일행 뒤를 따라 걷는 그림(개·용병)은 전용 줄이 없어 PARTIES 에 넣지 않는다. 그 장 모든 그룹에서 제 색이
        # 나오려면 그림이 NDS 인물이고, 공용 줄이면 배치 표의 그룹이 그 장 그룹을 덮고, 전용 줄이면 그 장 줄이어야 한다.
        # KNOWN 은 지금 main 에서 어긋난 것(3장 쪽에서 고칠 것). 고치면 이 시험이 그 줄을 지우라고 실패한다
        import dq4ch1event
        import dq4mercenary
        from dq4npcport import PICTURES
        followers = {'개': PICTURES[dq4ch1event.FC_DOG_PICTURE], '스콧': dq4mercenary.PICTURES['scott'],
                     '로렌스': dq4mercenary.PICTURES['lawrence']}
        pins = tomllib.loads(P.PINS.read_text())['person']
        groups = set(P.party_groups(3))
        found = {}
        for name, picture in followers.items():
            people = [p for p in P.PEOPLE if picture in p.pictures and p.group in (None, *groups)]
            if not people:
                found[name] = 'NDS 인물이 아님(DQ5 세트 그대로 공용 줄)'
            elif people[0].palette is not None:
                if P.FLAG_CHAPTERS.get(people[0].flag) != 3:
                    found[name] = f'{people[0].role} 의 다른 장 전용 줄 {people[0].palette}'
            else:
                missing = groups - {int(g, 16) for g in pins[people[0].role]['groups']}
                if missing:
                    found[name] = '배치 표 그룹에 없음 ' + ','.join(f'{g:02X}' for g in sorted(missing))
        known = {
            '개': '배치 표 그룹에 없음 3F,40,47,48',
            '스콧': 'NDS 인물이 아님(DQ5 세트 그대로 공용 줄)',
            '로렌스': '브라이 의 다른 장 전용 줄 5',
        }
        self.assertEqual(found, known)

    def test_flag_maps_cover_endor_in_chapter2(self):
        self.assertIn('40/FF', P.flag_maps(P.CHAPTER2))
        self.assertIn('40/FF', P.flag_maps(P.CHAPTER3))


if __name__ == '__main__':
    unittest.main()
