"""포팅 롬의 인물마다 원작 FC 인물 그림의 종류와 실제로 싣는 세트의 종류가 맞는지 본다(에뮬레이터 없음).

원작 쪽: dq4npcport.port 가 원작 롬에서 읽는 맵마다의 인물(낮·밤, 1장 사건 뒤 목록 포함)과 그 FC 그림 번호.
포팅 쪽: 포팅 롬의 인물 목록(기본 목록과 깃발로 바꾸는 대체 목록, dq5npc)에서 인물마다 DQ5 그림 번호를 읽고,
그 그림을 그 맵 그룹에서 싣는 세트를 롬의 인물 훅(dq4people.HOOK_AT)을 65816 해석기로 돌려 얻는다.
세트가 dq4people.PEOPLE 의 인물이 바꿔 넣은 것이면 그 역할, 아니면 DQ5 원래 그림의 종류다.
둘을 FC 칸(DQ5 셀)·시간대로 짝짓고 sfc/dq4/people-kinds.toml 의 종류·갈래로 견준다.

  맞음      종류가 같다
  비슷함    사람 갈래(남자·여자·노인·아이·왕)는 같고 종류만 다르다(실패 아님)
  어긋남    갈래가 다르거나, 사람이 아닌 갈래에서 종류가 다르다. 표의 [[allow]] 에 있으면 허용

대사 단서(여자·노인·아이 말투)는 보조로 적기만 한다. 사건이 더하는 따라 걷는 그림(프레아·구한 아이)도 함께 본다.

  python sfc/dq4/tools/dq4peoplematchcheck.py --rom work/ch1/dq4-ch1-full.sfc [--json OUT] [--all]
"""
import argparse
import json
import re
import sys
import tomllib
from pathlib import Path

HERE = Path(__file__).resolve().parent
DQ5_TOOLS = HERE.parents[1] / 'dq5' / 'tools'
FC_TOOLS = HERE.parents[2] / 'fc' / 'dq4' / 'tools'
for _p in (HERE, DQ5_TOOLS, FC_TOOLS):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

KINDS = HERE.parent / 'people-kinds.toml'
HUMAN = frozenset(('왕', '노인', '남자', '여자', '아이'))
UNSEEN = '안 보임'
MAP_GROUP = 0x00BC
HOOK_SITE = 0x1FCF45
# 말투 단서. 순서대로 먼저 맞는 것을 쓴다(노인 말투 「わし」 가 여자 어미 「わ」 보다 앞)
CUES = (
    ('노인', re.compile(r'わし[はもがの　]|じゃ(?:[。！？]|よ|のう|ろう)|のう[。…]|おるか[？。]')),
    ('아이', re.compile(r'ぼく[はもが　]|おじちゃん|だよーだ|えーん')),
    ('여자', re.compile(r'あたし|わたくし|ですわ|ますわ|かしら|わ[。！]|わよ[。！]|わね[。！]|のよ[。！]|くださいな|まし[。！]')),
)
# 사건 코드가 일행 뒤에 더하는 그림: (이름, DQ5 맵, dq4ch1event 의 FC 그림 상수)
FOLLOWERS = (('따라 걷는 프레아', '37/02', 'FC_FLARE_PICTURE'), ('따라 걷는 구한 아이', '39/04', 'FC_CHILD_PICTURE'))


def load_kinds(path=KINDS):
    doc = tomllib.loads(Path(path).read_text())
    problems = validate(doc)
    if problems:
        raise SystemExit(f'{path}: ' + '; '.join(problems))
    return doc


def validate(doc):
    """표 안에서 모르는 종류·갈래, 형식이 틀린 번호, 이유 없는 허용을 찾는다."""
    kinds = doc.get('kinds', {})
    out = [f'종류 {k} 의 갈래 {c} 가 사람·동물·몬스터·물체·안 보임이 아님'
           for k, c in kinds.items() if c not in HUMAN | {'동물', '몬스터', '물체', UNSEEN}]
    for section in ('fc', 'sfc', 'roles'):
        for key, kind in doc.get(section, {}).items():
            if kind not in kinds:
                out.append(f'[{section}] {key}: 모르는 종류 {kind}')
            if section != 'roles' and not re.fullmatch(r'[0-9A-F]{2}', key):
                out.append(f'[{section}] {key}: 두 자리 대문자 16진이 아님')
    for a in doc.get('allow', []):
        if not a.get('reason') or not {'map', 'fc', 'gfx'} <= a.keys():
            out.append(f'[[allow]] {a}: map·fc·gfx·reason 이 모두 있어야 함')
    return out


def judge(expected, actual, kinds):
    """'맞음'·'비슷함'·'어긋남', 어느 쪽이든 안 보이면 '건너뜀'."""
    if UNSEEN in (expected, actual):
        return '건너뜀'
    if expected == actual:
        return '맞음'
    a, b = kinds[expected], kinds[actual]
    if a == b and a in HUMAN:
        return '비슷함'
    return '어긋남'


def cue(text):
    text = re.sub(r'\{[^}]*\}', '', re.sub(r'\{(?:END|WAIT)\}', '。', text))
    for name, pattern in CUES:
        if pattern.search(text):
            return name
    return ''


def cue_disagrees(c, kind_class):
    return bool(c) and {'노인': '노인', '아이': '아이', '여자': '여자'}[c] != kind_class


def allowed(row, allows):
    for a in allows:
        if (a['map'], int(a['fc'], 16), int(a['gfx'], 16)) == (row['map'], row['fc'], row['gfx']):
            return a['reason']
    return None


def hook_set(rom, group, picture):
    """그 맵 그룹(깃발은 모두 꺼짐)에서 그림 번호 → 세트. 훅이 없는 롬은 25:86D0 표를 그대로 읽는다."""
    import dq4people
    from dq5map import lorom
    if rom[lorom(HOOK_SITE)] != 0x22:
        return rom[lorom(0x2586D0 + picture)]
    from w65816 import Cpu
    wram = bytearray(0x20000)
    wram[MAP_GROUP] = group
    cpu = Cpu(rom, wram)
    cpu.x, cpu.p = picture, 0x30
    cpu.jsl(dq4people.cpu(dq4people.HOOK_AT))
    return cpu.a & 0xFF


def role_sets(rom):
    """{세트: dq4people 역할}. 인물이 세트를 그 자리에서 바꿔 넣으므로 세트가 곧 그 인물의 그림이다."""
    import dq4people
    from dq5map import Rom
    r = Rom(rom)
    out = {}
    for p in dq4people.PEOPLE:
        if p.pictures == dq4people.LEADER_PICTURES:
            continue
        out.setdefault(dq4people.target(p, r)[0], p.role)
    return out


def actual_kind(gfx, s, roles_by_set, doc):
    """(종류, 근거)."""
    if s in roles_by_set:
        role = roles_by_set[s]
        if role not in doc['roles']:
            raise SystemExit(f'people-kinds.toml [roles] 에 dq4people 역할 {role} 이 없음')
        return doc['roles'][role], f'NDS {role}'
    key = f'{gfx:02X}'
    if key not in doc['sfc']:
        raise SystemExit(f'people-kinds.toml [sfc] 에 DQ5 그림 {key} 이 없음(세트 {s:02X})')
    return doc['sfc'][key], 'DQ5 원래'


def rom_people(rom, maps):
    """포팅 롬 인물 목록의 [{map, list, night, x, y, gfx}]. x·y 는 엔트리의 DQ5 셀(방향 비트 뺌)."""
    from dq5map import Rom
    from dq5npc import list_entries, map_list, overrides, parse
    r = Rom(rom)
    out = []
    for m in maps:
        bc, bd = (int(v, 16) for v in m.split('/'))
        lists = [('기본', map_list(r, bc, bd))] + [(f'깃발 {n:02X}&{k:02X}', a) for n, k, a in overrides(r, bc, bd)]
        for name, at in lists:
            for a, _ in list_entries(r, at):
                for night in (False, True):
                    f = parse(r, a, night)
                    if f is None or f['gfx'] == 0:
                        continue
                    out.append({'map': m, 'list': name, 'night': night, 'x': f['x'] & 0x7F, 'y': f['y'] & 0x7F,
                                'gfx': f['gfx']})
    return out


def fc_index(report, alt_maps):
    """{맵: {(밤, x, y): [원작 인물]}}. 사건 뒤 목록(alt_maps: 이름 → 맵)도 그 맵에 모은다."""
    out = {}
    for key, people in report.items():
        m = key if '/' in key else alt_maps[key]
        for p in people:
            out.setdefault(m, {}).setdefault((p['night'], p['dq5']['x'], p['dq5']['y']), []).append(p)
    return out


def compare(rows, index, doc, set_of, roles_by_set, text_of=lambda p: ''):
    """rows(rom_people)에 원작 짝·종류·판정을 붙인다. set_of(맵 그룹, 그림) → 세트. 짝이 없는 인물(사건이 더한
    보이지 않는 인물 등)은 '짝 없음'. 같은 칸·시간에 그림이 다른 원작 인물이 여럿이면 가장 좋은 판정을 쓴다."""
    order = {'맞음': 0, '건너뜀': 1, '비슷함': 2, '어긋남': 3}
    out = []
    for row in rows:
        s = set_of(int(row['map'][:2], 16), row['gfx'])
        kind, source = actual_kind(row['gfx'], s, roles_by_set, doc)
        row = {**row, 'set': s, 'kind': kind, 'source': source}
        cands = index.get(row['map'], {}).get((row['night'], row['x'], row['y']), [])
        if not cands:
            out.append({**row, 'result': '짝 없음'})
            continue
        best = None
        for p in cands:
            key = f"{p['picture']:02X}"
            if key not in doc['fc']:
                raise SystemExit(f'people-kinds.toml [fc] 에 FC 그림 {key} 이 없음({row["map"]})')
            want = doc['fc'][key]
            r = judge(want, kind, doc['kinds'])
            if best is None or order[r] < order[best[0]]:
                best = (r, p, want)
        r, p, want = best
        text = text_of(p)
        c = cue(text)
        full = {**row, 'fc': p['picture'], 'talk': p['talk'], 'want': want, 'result': r, 'cue': c, 'text': text,
                'fc_x': p['x'], 'fc_y': p['y']}
        if r == '어긋남':
            reason = allowed(full, doc.get('allow', []))
            if reason:
                full.update(result='허용', reason=reason)
        out.append(full)
    return out


def follower_rows(doc, set_of, roles_by_set):
    import dq4ch1event
    import dq4npcport
    out = []
    for name, m, const in FOLLOWERS:
        fc = getattr(dq4ch1event, const)
        gfx = dq4npcport.PICTURES[fc]
        s = set_of(int(m[:2], 16), gfx)
        kind, source = actual_kind(gfx, s, roles_by_set, doc)
        want = doc['fc'][f'{fc:02X}']
        row = {'map': m, 'list': name, 'night': False, 'x': None, 'y': None, 'gfx': gfx, 'set': s, 'kind': kind,
               'source': source, 'fc': fc, 'talk': None, 'want': want, 'result': judge(want, kind, doc['kinds']),
               'cue': '', 'text': '', 'fc_x': None, 'fc_y': None}
        if row['result'] == '어긋남' and (reason := allowed(row, doc.get('allow', []))):
            row.update(result='허용', reason=reason)
        out.append(row)
    return out


def summarize(rows):
    """(FC 그림, 원작 종류, DQ5 그림, 세트, 실제 종류, 판정) 별 인물 수와 맵."""
    out = {}
    for r in rows:
        if r['result'] in ('짝 없음', '맞음', '건너뜀'):
            continue
        key = (r['fc'], r['want'], r['gfx'], r['set'], r['kind'], r['result'])
        e = out.setdefault(key, {'count': 0, 'people': set(), 'maps': set(), 'cues': set()})
        e['count'] += 1
        e['people'].add((r['map'], r['fc_x'], r['fc_y'], r['talk']))
        e['maps'].add(r['map'])
        if r['cue']:
            e['cues'].add(r['cue'])
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--rom', default='work/ch1/dq4-ch1-full.sfc', type=Path)
    ap.add_argument('--dq4', default='rom/dq4.nes')
    ap.add_argument('--dq5', default='rom/dq5.sfc')
    ap.add_argument('--kinds', default=KINDS, type=Path)
    ap.add_argument('--json', type=Path, help='인물마다의 판정을 JSON 으로')
    ap.add_argument('--all', action='store_true', help='어긋남·허용뿐 아니라 비슷함도 인물마다 찍기')
    args = ap.parse_args()

    import dq4ch1event
    import dq4npcport
    import dq4talk
    import dq4text
    from dq4environmentrom import GROUPS

    doc = load_kinds(args.kinds)
    rom = args.rom.read_bytes()
    fc_rom = dq4text.Rom(Path(args.dq4).read_bytes())
    _, _, report = dq4npcport.port(args.dq5, args.dq4)
    alt_maps = {dq4ch1event.alt_name(state, m): m for state, _, maps in dq4ch1event.ALT_STATES for m in maps}

    def text_of(p):
        msgs = [m for m in p['shows'] if m is not None and m < dq4talk.SERVICE]
        return ''.join(dq4text.symbolize(dq4text.message_bytes(fc_rom, m)) for m in msgs)

    maps = sorted('%02X/%02X' % v for v in GROUPS.values())
    roles_by_set = role_sets(rom)
    set_of = lambda group, gfx: hook_set(rom, group, gfx)  # noqa: E731
    rows = (compare(rom_people(rom, maps), fc_index(report, alt_maps), doc, set_of, roles_by_set, text_of)
            + follower_rows(doc, set_of, roles_by_set))

    counts = {}
    for r in rows:
        counts[r['result']] = counts.get(r['result'], 0) + 1
    print('판정별 인물 수(낮·밤 따로, 대체 목록 포함): ' + ', '.join(f'{k} {v}' for k, v in sorted(counts.items())))
    print('\n| FC 그림 | 원작 종류 | DQ5 그림 | 세트 | 실제 종류 | 판정 | 인물(엔트리) | 대사 단서 | 맵 |')
    print('| --- | --- | --- | --- | --- | --- | --- | --- | --- |')
    for (fc, want, gfx, s, kind, result), e in sorted(summarize(rows).items(), key=lambda kv: (kv[0][5], kv[0][0])):
        print(f"| `{fc:02X}` | {want} | `{gfx:02X}` | `{s:02X}` | {kind} | {result} | {len(e['people'])}({e['count']}) | "
              f"{'·'.join(sorted(e['cues'])) or '-'} | {' '.join(sorted(e['maps']))} |")
    show = ('어긋남', '허용', '비슷함') if args.all else ('어긋남', '허용')
    for r in rows:
        if r['result'] not in show:
            continue
        where = f"FC ({r['fc_x']:02X},{r['fc_y']:02X}) DQ5 ({r['x']},{r['y']})" if r['x'] is not None else '사건'
        line = re.sub(r'\{[A-Z0-9:]+\}', ' ', r['text'])[:40]
        extra = f" 허용: {r['reason']}" if r['result'] == '허용' else ''
        flag = ' (단서 어긋남)' if cue_disagrees(r['cue'], doc['kinds'][r['kind']]) else ''
        print(f"{r['result']}: {r['map']} {r['list']} {'밤' if r['night'] else '낮'} {where} 대화 "
              f"{'-' if r['talk'] is None else format(r['talk'], '03X')} FC `{r['fc']:02X}` {r['want']} → "
              f"DQ5 `{r['gfx']:02X}` 세트 `{r['set']:02X}` {r['kind']}({r['source']}) 단서 {r['cue'] or '-'}{flag} "
              f"「{line}」{extra}")
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(rows, ensure_ascii=False, indent=1) + '\n')
    bad = counts.get('어긋남', 0)
    print(f"\n{'실패' if bad else '통과'}: 어긋남 {bad}, 허용 {counts.get('허용', 0)}, 비슷함 {counts.get('비슷함', 0)}, "
          f"짝 없음 {counts.get('짝 없음', 0)}")
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
