"""NDS 2장 동료 대화 표(PARAM/param_player_talk2.dat)에서 SFC 로 옮길 줄과 그 조건을 고른다.

NDS 표의 형식은 nds/dq4/docs/param-format.md 「동료 대화 표」. 레코드마다 SFC 맵과 SFC flag 조건으로 옮길 수 있으면
줄(dq4ch2partytalk.tsv 의 한 줄)로, 아니면 뺀 까닭을 낸다. 번역문은 이 도구가 만들지 않는다(dq4ch2partytalk-text.tsv).

  uv run --locked python sfc/dq4/tools/dq4ch2partytalknds.py lines JPROOT > sfc/dq4/tools/dq4ch2partytalk.tsv
  uv run --locked python sfc/dq4/tools/dq4ch2partytalknds.py range JPROOT       # 진행 단계 × 장소 범위 표(마크다운)
  uv run --locked python sfc/dq4/tools/dq4ch2partytalknds.py source JPROOT [--kr KRROOT] > work/talk2src.json

JPROOT/KRROOT 는 `krpatch nds unpack` 으로 푼 일본판·한글 팬패치 폴더(그 아래 data/data/).
"""
import argparse
import collections
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
NDS_TOOLS = HERE.parents[2] / 'nds' / 'dq4' / 'tools'

# NDS 맵 이름 → SFC 맵. FC 는 마을 1층 건물을 마을 맵에 함께 두므로 NDS 의 건물 1층 맵도 마을 맵으로 간다. 서쪽 탑 층은
# FC 2E 의 계단 연결(04 ↔ 03 ↔ 02 ↔ 01 ↔ 05 ↔ 00, 도착 03)로, 엔돌은 FC 04 의 계단 연결과 인물로 짝지었다
MAPS = {
    'cbout': '3D/00', 'cbf1': '3D/00', 'cbf2': '3D/01', 'cbf3': '3D/02',
    'mcout1': '3D/03', 'mcout2': '3D/03', 'mck1f1': '3D/03', 'mcm1f1': '3D/03', 'mcm2f1': '3D/03',
    'mcm3f1': '3D/03', 'mcy1f1': '3D/03',
    'mdout': '3D/04', 'mdi1f1': '3D/04', 'mdm1f1': '3D/04', 'mdm2f1': '3D/04', 'mdm3f1': '3D/04',
    'mdy1f1': '3D/04', 'mdy1f2': '3D/05',
    'hcout': '40/00', 'hck1f1': '40/00', 'ccout': '40/00', 'hcy1b1': '40/01', 'ccf1a': '40/02', 'ccf2': '40/06',
    'ccf3': '40/0C', 'cccf1a': '40/0E', 'cccf1b': '40/0E', 'cccf2': '40/07',
    'mbout': '45/00', 'mbk1f1': '45/02', 'mbk1f2': '45/02',
    'meout': '45/05', 'mem1f1': '45/05', 'mey1f1': '45/05',
    'tbf5': '45/06', 'tbf3': '45/07', 'tbf2': '45/08', 'tbf1a': '45/09', 'tbf1b': '45/09', 'tbb1': '45/0A',
    'tbf4': '45/0B',
    'dcb1': '45/0C', 'dcb2': '45/0D', 'saf1': '45/0E', 'sbm1f1': '45/0F', 'sbout': '45/0F', 'sby1f1': '45/0F',
    '#544': 'field',
}
# 짝을 정하지 못한 NDS 맵(FC 맵 둘 가운데 어느 쪽인지 인물로 가르지 못함, 2장에 비어 있는 가게)
UNMAPPED = {'ccb1a': '엔돌 성 지하(FC 04/05·04/0D 중 어느 쪽인지 미확인)',
            'ccb1c': '엔돌 성 지하(FC 04/05·04/0D 중 어느 쪽인지 미확인)',
            'hcm2f1': '엔돌의 빈 가게(FC 2장에는 그 자리에 가게 주인이 있음)'}

# NDS 이야기 flag(진행도 프리셋 param_player_flag 의 누적 차례) → SFC flag 이름(dq4ch2partytalk.FLAGS)
STORY = {
    82: 'CHAPTER2',     # 2장 초기 상태
    84: 'JOINED',       # 사란 도착(성을 나설 때 두 사람이 합류함)
    86: 'TEMPE_HEARD',  # 텐페 부탁을 받음
    87: 'WON', 88: 'WON',               # 텐페 괴물을 물리침
    90: 'KIDNAPPED', 91: 'KIDNAPPED',   # 가짜 공주가 납치됨(91: 동굴의 아이와 이야기함, SFC 에 없음)
    92: 'BRACELET', 93: 'BRACELET',     # 황금의 팔찌를 얻음
    94: 'RESCUED',      # 가짜 공주를 구함
    95: 'BAZAAR',       # 왕이 병든 것을 바자에서 들음
    97: 'HEARD', 98: 'HEARD',           # 곤 영감·마로니와 이야기함(SFC 에 없음): 왕좌의 방 병사에게 들은 뒤로 본다
    100: 'GOT',         # 지저귐의 꿀을 얻음
    101: 'CURED',       # 왕이 나음
    104: 'MESSENGER',   # 엔돌에서 산트하임 사자의 말을 들음(2장 엔딩)
}
# 엔돌 왕과 이야기함(102). SFC 대회는 왕을 만나지 않아도 열리므로 켜짐·꺼짐 모두 「우승 전」으로 본다
BEFORE_CHAMPION = 102
# 진행 차례(유효하지 않은 조합 가리기). NDS 프리셋의 누적 차례와 같다
ORDER = ('CHAPTER2', 'JOINED', 'TEMPE_HEARD', 'WON', 'KIDNAPPED', 'BRACELET', 'RESCUED', 'BAZAAR', 'HEARD', 'GOT',
         'CURED', 'CHAMPION', 'MESSENGER')
NAMES = {'アリーナ': 'ALENA', 'クリフト': 'KIRYL', 'ブライ': 'BREY'}
TIMES = {0: 'any', 2: 'day', 4: 'night'}


def _nds():
    sys.path.insert(0, str(NDS_TOOLS))
    import ndsparam
    import ndstext
    return ndsparam, ndstext


def records(jp):
    ndsparam, ndstext = _nds()
    maps = ndsparam.map_list(jp)
    people = ndsparam.names(jp, 'b1001000')
    for k, r in enumerate(ndsparam.records(ndsparam.param(jp, 'param_player_talk2'), 44)):
        f = ndsparam.talk_fields(r)
        f['k'] = k
        f['mapname'] = maps[f['map']] if f['map'] < len(maps) else f"#{f['map']}"
        f['speaker'] = people.get(f['who'] - 1, f['who'])
        yield f


def message_ids(f):
    """레코드가 띄우는 메시지 번호들. 1~9 는 그 수만큼, 네·다섯 자리는 일 자리 수만큼(함께 말하는 사람이 섞임)."""
    n = f['count']
    if 100 <= n < 1000:
        return None                     # はい/いいえ 물음(2장에는 옮길 줄에 없음)
    return [f['msg'] + i for i in range(n % 10 if n >= 1000 else n)]


SPEAKER = re.compile(r'@a@b([^「]+)「')


def convert(f, msgs):
    """(줄 dict, None) 또는 (None, 뺀 까닭)."""
    if f['place'][0] != 0xFF:
        return None, '방금 말을 건 마을 사람(직전 대화 값)'
    if f['v0']:
        return None, '방금 본 사건 대사(최근 이벤트 값)'
    codes = [(c, v) for c, v in zip(f['codes'], f['vals']) if c]
    if any(c not in (1, 2) for c, _ in codes):
        kinds = {3: '맵 안 임시 flag', 4: '맵 안 임시 flag', 5: '맵 안 임시 flag', 6: '맵 안 임시 flag',
                 7: '물건을 가짐', 12: '들어온 입구', 18: '방금 얻은 열쇠 물건'}
        return None, next(kinds.get(c, f'조건 종류 {c}') for c, _ in codes if c not in (1, 2))
    ids = message_ids(f)
    if ids is None:
        return None, '예/아니오 물음'
    if f['mapname'] in UNMAPPED:
        return None, UNMAPPED[f['mapname']]
    if f['mapname'] not in MAPS:
        raise SystemExit(f"{f['k']}: NDS 맵 {f['mapname']} 의 SFC 짝이 없음")
    on, off = ['CHAPTER2'], []
    story_on, story_off = f['story']
    flags_on = [story_on] + [v for c, v in codes if c == 1]
    flags_off = ([] if story_off == 0xFFFF else [story_off]) + [v for c, v in codes if c == 2]
    for n in flags_on + flags_off:
        if n == BEFORE_CHAMPION:
            off.append('CHAMPION')
        elif n not in STORY:
            raise SystemExit(f"{f['k']}: NDS 이야기 flag {n} 의 SFC 짝이 없음")
    on += [STORY[n] for n in flags_on if n != BEFORE_CHAMPION]
    off += [STORY[n] for n in flags_off if n != BEFORE_CHAMPION]
    on, off = sorted(set(on), key=ORDER.index), sorted(set(off), key=ORDER.index)
    if off and max(map(ORDER.index, on)) >= min(map(ORDER.index, off)):
        return None, 'SFC 에 없는 진행 사이(곤 영감·마로니·엔돌 왕과 이야기한 것)'
    speakers = []
    for m in ids:
        found = SPEAKER.match(msgs.get(m, ''))
        if not found or found[1] not in NAMES:
            raise SystemExit(f"{f['k']}: 메시지 {m} 의 말하는 이를 모름")
        speakers.append(NAMES[found[1]])
    if f['speaker'] not in NAMES or NAMES[f['speaker']] != speakers[0]:
        raise SystemExit(f"{f['k']}: 말하는 인물 {f['speaker']} 와 첫 메시지가 다름")
    with_ = sorted({NAMES[n] for n, mode in f['slots'] if mode == 1} | set(speakers[1:]) - {speakers[0]})
    if any(mode != 1 for _, mode in f['slots']):
        return None, '일행 칸 조건(걷는 줄 밖·쓰러짐)'
    return {'nds': f['k'], 'map': MAPS[f['mapname']], 'speaker': speakers[0], 'priority': f['prio'],
            'time': TIMES[f['time']], 'on': on, 'off': off, 'with': with_, 'messages': ids,
            'speakers': speakers}, None


def lines(jp):
    _, ndstext = _nds()
    msgs = ndstext.messages(jp)
    kept, dropped, seen = [], [], set()
    for f in records(jp):
        line, why = convert(f, msgs)
        if line is None:
            dropped.append((f, why))
            continue
        key = (line['map'], line['priority'], line['time'], tuple(line['on']), tuple(line['off']),
               tuple(line['with']), tuple(line['messages']))
        if key in seen:                 # tbf1a·tbf1b 처럼 SFC 의 한 맵에 겹친 같은 줄
            continue
        seen.add(key)
        kept.append(line)
    return kept, dropped


HEAD = ('nds', 'map', 'speaker', 'priority', 'time', 'on', 'off', 'with', 'messages')


def cmd_lines(jp):
    kept, _ = lines(jp)
    print('\t'.join(HEAD))
    for ln in kept:
        print('\t'.join(str(ln[k]) if not isinstance(ln[k], list) else ','.join(map(str, ln[k])) for k in HEAD))


def cmd_range(jp):
    """2장 진행 단계 × 장소별로 옮긴 줄 수 / 뺀 줄 수."""
    kept, dropped = lines(jp)
    import dq4ch2partytalk as pt
    stages = pt.STAGES
    places = sorted({ln['map'] for ln in kept} | set(MAPS.values()), key=lambda m: (m == 'field', m))
    table = collections.defaultdict(lambda: [0, 0])
    for ln in kept:
        for s, (name, flags) in enumerate(stages):
            if all(f in flags for f in ln['on']) and not any(f in flags for f in ln['off']):
                table[s, ln['map']][0] += 1
    for f, _ in dropped:
        mp = MAPS.get(f['mapname'], f['mapname'])
        on, off = f['story']
        for s, (name, flags) in enumerate(stages):
            if STORY.get(on, 'CHAPTER2') in flags and (off == 0xFFFF or STORY.get(off) not in flags):
                table[s, mp][1] += 1
    print('| 단계 | ' + ' | '.join(places) + ' |')
    print('| --- |' + ' --- |' * len(places))
    for s, (name, _) in enumerate(stages):
        print(f'| {name} | ' + ' | '.join('/'.join(map(str, table[s, p])) if table[s, p] != [0, 0] else '' for p in places)
              + ' |')
    why = collections.Counter(w for _, w in dropped)
    print()
    print('| 뺀 까닭 | 레코드 |')
    print('| --- | --- |')
    for w, n in why.most_common():
        print(f'| {w} | {n} |')
    print(f'\n옮긴 줄 {len(kept)}, 뺀 레코드 {len(dropped)}, NDS 레코드 {len(kept) + len(dropped)}(SFC 맵 하나에 겹친 줄 제외)')


def cmd_source(jp, kr):
    """번역할 메시지: {번호: {'speaker', 'jp', 'kr'}}(일본어 원문과 한글 팬패치 문장, 작업용)."""
    _, ndstext = _nds()
    msgs = ndstext.messages(jp)
    ko = ndstext.messages(kr) if kr else {}
    table = ndstext.kr_table() if kr else {}
    kept, _ = lines(jp)
    out = {}
    for ln in kept:
        for m, sp in zip(ln['messages'], ln['speakers']):
            out[m] = {'speaker': sp, 'map': ln['map'], 'jp': msgs[m],
                      'kr': ndstext.decode_kr(ko[m], table) if m in ko else ''}
    json.dump(out, sys.stdout, ensure_ascii=False, indent=1)


def main():
    sys.path[:0] = [str(HERE), str(HERE.parents[1] / 'dq5' / 'tools')]
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('cmd', choices=('lines', 'range', 'source'))
    ap.add_argument('jp')
    ap.add_argument('--kr')
    a = ap.parse_args()
    if a.cmd == 'lines':
        cmd_lines(a.jp)
    elif a.cmd == 'range':
        cmd_range(a.jp)
    else:
        cmd_source(a.jp, a.kr)


if __name__ == '__main__':
    main()
