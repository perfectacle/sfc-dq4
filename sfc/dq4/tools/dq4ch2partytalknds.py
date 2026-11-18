"""NDS 동료 대화 표(PARAM/param_player_talkN.dat)에서 SFC 로 옮길 줄과 그 조건을 고른다(2장·3장).

NDS 표의 형식은 nds/dq4/docs/param-format.md 「동료 대화 표」. 레코드마다 SFC 맵과 SFC flag 조건으로 옮길 수 있으면
줄(dq4ch2partytalk.tsv·dq4ch3partytalk.tsv 의 한 줄)로, 아니면 뺀 까닭을 낸다. 번역문은 이 도구가 만들지 않는다
(dq4ch2partytalk-text.tsv·dq4ch3partytalk-text.tsv).

  uv run --locked python sfc/dq4/tools/dq4ch2partytalknds.py lines JPROOT > sfc/dq4/tools/dq4ch2partytalk.tsv
  uv run --locked python sfc/dq4/tools/dq4ch2partytalknds.py range JPROOT       # 진행 단계 × 장소 범위 표(마크다운)
  uv run --locked python sfc/dq4/tools/dq4ch2partytalknds.py source JPROOT [--kr KRROOT] > work/talk2src.json
  uv run --locked python sfc/dq4/tools/dq4ch2partytalknds.py people JPROOT > sfc/dq4/tools/dq4ch2partytalk-people.tsv
  uv run --locked python sfc/dq4/tools/dq4ch2partytalknds.py --chapter 3 lines JPROOT > sfc/dq4/tools/dq4ch3partytalk.tsv

`people` 는 「방금 말을 건 마을 사람」 조건의 NDS 인물을 SFC 인물(맵·칸·낮밤)과 짝짓는다(rom/dq5.sfc·rom/dq4.nes 를 읽음).
`lines` 는 커밋한 짝 표(PEOPLE_TSV)를 읽는다. 3장은 말 상대가 사건 모듈의 대화라 글 견줌 대신 손으로 정한 짝(OBJECTS3)을
쓰고 `people` 이 없다(--chapter 3 은 lines·range·source).

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
    # 엔돌 성 지하·여관 1층: 인물 대사가 FC 의 그 맵 인물과 맞는다(dq4ch2partytalk-people.tsv). 지하 ccb1a 는 FC 04/05
    # 의 넷, ccb1c 는 FC 04/02 의 투기장 앞 병사, 여관 1층 술집은 마을 맵 40/00 의 셋
    'ccb1a': '40/05', 'ccb1c': '40/02', 'hcy1f1': '40/00',
}
# 짝을 정하지 못한 NDS 맵(FC 맵 둘 가운데 어느 쪽인지 인물로 가르지 못함, 2장에 비어 있는 가게)
UNMAPPED = {'hcm2f1': '엔돌의 빈 가게(FC 2장에는 그 자리에 가게 주인이 있음)'}

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


def records(jp, chapter=2):
    ndsparam, ndstext = _nds()
    maps = ndsparam.map_list(jp)
    people = ndsparam.names(jp, 'b1001000')
    for k, r in enumerate(ndsparam.records(ndsparam.param(jp, f'param_player_talk{chapter}'), 44)):
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


def convert(f, msgs, people=None, objects=None, heard=None):
    """(줄 dict, None) 또는 (None, 뺀 까닭). people 은 짝 표({(NDS 맵, 인물 번호): [짝 행]}), objects 는
    {(NDS 맵, 오브젝트): {인물 번호}}: 직전 대화 값 v 는 2장 그룹의 오브젝트 v + 1 이다(param-format.md). heard 는
    {메시지: {(NDS 맵, 오브젝트)}}(말을 걸면 띄우는 대사): 최근 이벤트 값이 그런 대사면 그 사람에게 말을 건 것으로 본다."""
    def paired(mp, obj):
        return [f"{mp}:{who}" for who in sorted((objects or {}).get((mp, obj), ()))
                if any(r['status'] == SURE for r in (people or {}).get((mp, who), ()))]
    talked = []
    if f['place'][0] != 0xFF:
        for v in f['place']:
            if v != 0xFF:
                talked += paired(f['mapname'], v + 1)
        if not talked:
            return None, '방금 말을 건 마을 사람(SFC 인물 짝 미확인)'
    if f['v0']:
        speakers = [t for mp, obj in sorted((heard or {}).get(f['v0'], ())) if mp == f['mapname']
                    for t in paired(mp, obj)]
        if not speakers:
            return None, '방금 본 사건 대사(최근 이벤트 값)'
        talked = talked or speakers
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
            return None, 'SFC 에 짝이 없는 NDS 이야기 flag(85·96 따위)'
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
            'time': TIMES[f['time']], 'on': on, 'off': off, 'with': with_, 'talked': talked, 'messages': ids,
            'speakers': speakers}, None


def lines(jp, people=None):
    _, ndstext = _nds()
    msgs = ndstext.messages(jp)
    people = read_people() if people is None else people
    objects = {k: set(v) for k, v in script_people(jp, msgs).items()}
    heard = heard_messages(jp, msgs)
    kept, dropped, seen = [], [], set()
    for f in records(jp):
        line, why = convert(f, msgs, people, objects, heard)
        if line is None:
            dropped.append((f, why))
            continue
        key = (line['map'], line['priority'], line['time'], tuple(line['on']), tuple(line['off']),
               tuple(line['with']), tuple(line['talked']), tuple(line['messages']))
        if key in seen:                 # tbf1a·tbf1b 처럼 SFC 의 한 맵에 겹친 같은 줄
            continue
        seen.add(key)
        kept.append(line)
    return kept, dropped


# 「방금 말을 건 마을 사람」: NDS 인물 ↔ SFC 인물 짝. NDS 대사(한자 섞임)와 FC 대사(가나)를 가나 두 글자 묶음으로 견준다
PEOPLE_TSV = HERE / 'dq4ch2partytalk-people.tsv'
PEOPLE_HEAD = ('nds_map', 'person', 'status', 'map', 'cell', 'time', 'score', 'margin', 'fc_message', 'nds_message')
SURE, UNSURE = '확인', '미확인'          # dq4ch2partytalk.SURE 와 같아야 함
TALK_OPS = (0x03, 0x04, 0x05, 0x06)    # 대사 명령(첫 인자가 메시지 번호)
TALKED_TO = 0x4A                       # 「말을 걸면」
CHAPTER_GROUP = 2                      # SCRIPT/<맵>.bin 의 칸 번호 = 장 번호
SURE_SCORE, SURE_MARGIN = 0.6, 0.1     # 견줌 값과, 다른 인물·다른 대사와의 차
WEAK_SCORE, WEAK_MARGIN = 0.45, 0.3    # 값이 낮아도 차가 크면 짝
SHORT = 6                              # 이보다 짧은 FC 대사(「すやすや」 따위)는 똑같을 때만 짝
# 두 사람이 FC 에서 같은 대사(같은 대화 번호)라 글로 가르지 못하는 짝: NDS 오브젝트 자리(x)로 왼쪽·오른쪽을 맞춘다
MANUAL = {
    ('cbf1', '0188'): (('3D/00', (28, 51), 'day'), ('3D/00', (28, 51), 'night')),   # 성문 왼쪽 병사
    ('cbf1', '0189'): (('3D/00', (30, 51), 'day'), ('3D/00', (30, 51), 'night')),   # 성문 오른쪽 병사
}
_PERSON = re.compile(r'@a(\d+)')


def kana(text):
    """대사의 가나만(가타카나는 히라가나로). 화자 머리(@a…@b)와 끝 부호(@c…)는 뺀다."""
    text = re.sub(r'@c\d@?', '', re.sub(r'@a\d*\s*\S*?@b', '', text))
    out = []
    for ch in text:
        if 0x30A1 <= ord(ch) <= 0x30F6:
            ch = chr(ord(ch) - 0x60)
        if 0x3041 <= ord(ch) <= 0x3096 or ch == 'ー':
            out.append(ch)
    return ''.join(out)


def _grams(text):
    return {text[i:i + 2] for i in range(len(text) - 1)}


def similarity(a, b):
    """두 가나 문자열의 두 글자 묶음이 짧은 쪽에서 겹치는 몫(0~1)."""
    ga, gb = _grams(a), _grams(b)
    return len(ga & gb) / min(len(ga), len(gb)) if ga and gb else 0.0


def _script_talks(jp, msgs, group=CHAPTER_GROUP, maps=None):
    """(NDS 맵, 오브젝트 번호, @a 인물 번호, 메시지 번호): 장 그룹(기본 2장) 오브젝트의 대사 명령마다."""
    import ndsscript
    for mp in sorted(maps if maps is not None else set(MAPS) | set(UNMAPPED)):
        path = Path(jp, 'data', 'data', 'SCRIPT', mp + '.bin')
        if not path.exists():
            continue
        d = path.read_bytes()
        code = {o: ins for _n, o, ins in ndsscript.functions(d)}
        seen = obj = -1
        for _depth, name, o, _secs in ndsscript.blocks(d):
            if name == 'scriptgroup':
                seen, obj = seen + 1, -1
            elif name == 'scriptobject':
                obj += 1
            elif name in ndsscript.FUNCS and seen == group:
                for _d, w in code.get(o, ()):
                    if (w[0] & 0xFFFF) in TALK_OPS and len(w) > 1 and w[1] in msgs:
                        who = _PERSON.match(msgs[w[1]])
                        if who and who[1]:
                            yield mp, obj, who[1], w[1]


def heard_messages(jp, msgs):
    """{메시지: {(NDS 맵, 오브젝트)}}: 「말을 걸면」(0x4A) 아래의 대사 명령이 띄우는 메시지."""
    import ndsscript
    out = {}
    for mp in sorted(set(MAPS) | set(UNMAPPED)):
        path = Path(jp, 'data', 'data', 'SCRIPT', mp + '.bin')
        if not path.exists():
            continue
        d = path.read_bytes()
        code = {o: ins for _n, o, ins in ndsscript.functions(d)}
        group = obj = -1
        for _depth, name, o, _secs in ndsscript.blocks(d):
            if name == 'scriptgroup':
                group, obj = group + 1, -1
            elif name == 'scriptobject':
                obj += 1
            elif name in ndsscript.FUNCS and group == CHAPTER_GROUP:
                stack = []
                for depth, w in code.get(o, ()):
                    while stack and stack[-1][0] >= depth:
                        stack.pop()
                    op = w[0] & 0xFFFF
                    if op in TALK_OPS and len(w) > 1 and obj > 0 and any(s[1] == TALKED_TO for s in stack):
                        out.setdefault(w[1], set()).add((mp, obj))
                    stack.append((depth, op))
    return out


def script_people(jp, msgs, group=CHAPTER_GROUP, maps=None):
    """{(NDS 맵, 오브젝트 번호): [인물 번호]}."""
    out = {}
    for mp, obj, who, _m in _script_talks(jp, msgs, group, maps):
        ids = out.setdefault((mp, obj), [])
        if who not in ids:
            ids.append(who)
    return out


def person_messages(jp, msgs):
    """{(NDS 맵, 인물 번호): [메시지 번호]}."""
    out = {}
    for mp, _obj, who, m in _script_talks(jp, msgs):
        ids = out.setdefault((mp, who), [])
        if m not in ids:
            ids.append(m)
    return out


def fc_entries(dq5, dq4):
    """{SFC 맵: [{'cell', 'time', 'message', 'kana'}]}: dq4npcport 가 옮긴 2장 그룹 인물(시작 상태)과 그 FC 대사."""
    sys.path[:0] = [str(HERE), str(HERE.parents[1] / 'dq5' / 'tools'), str(HERE.parents[2] / 'fc' / 'dq4' / 'tools')]
    import dq4npcport
    import dq4text
    _lists, _messages, report = dq4npcport.port(dq5, dq4)
    rom = dq4text.Rom(Path(dq4).read_bytes())
    groups = {m.split('/')[0] for m in MAPS.values() if m != 'field'}
    out = {}
    for mp, people in report.items():
        if mp.split('/')[0] not in groups:
            continue
        for p in people:
            if p.get('service') is not None:
                continue                # 가게·교회 주인의 대화 번호는 어느 맵이나 같아 누구에게 말을 걸었는지 가르지 못한다
            shows = [m for m in p['shows'] if m is not None and m < 0x1000]
            text = ''.join(dq4text.text(dq4text.message_bytes(rom, m)) for m in shows)
            out.setdefault(mp, []).append({'cell': (p['dq5']['x'], p['dq5']['y']), 'time': 'night' if p['night'] else 'day',
                                           'message': f'{shows[0]:03X}' if shows else '', 'kana': kana(text)})
    return out


def pair_people(jp, entries):
    """짝 표의 행들. 줄 조건에 쓰인 NDS 인물마다, 그 NDS 맵의 SFC 맵 인물 가운데 짝을 고른다.

    인물 e 의 짝은 그 맵의 NDS 인물 가운데 견줌 값이 가장 큰 사람이다. 그 값이 SURE_SCORE 이상이고 다른 NDS 인물(대사가
    다른)보다 SURE_MARGIN 이상 크거나, WEAK_SCORE 이상이고 WEAK_MARGIN 이상 크면 「확인」이다. 짧은 FC 대사는 같을 때만."""
    _, ndstext = _nds()
    msgs = ndstext.messages(jp)
    objects = script_people(jp, msgs)
    said = person_messages(jp, msgs)
    wanted = set()
    for f in records(jp):
        if f['place'][0] != 0xFF:
            for v in f['place']:
                if v != 0xFF:
                    wanted |= {(f['mapname'], who) for who in objects.get((f['mapname'], v + 1), ())}
    by_map = {}
    for (mp, who), ids in said.items():
        if MAPS.get(mp, 'field') != 'field':
            by_map.setdefault(MAPS[mp], {})[mp, who] = [kana(msgs[m]) for m in ids]
    rows = []
    for (mp, who) in sorted(wanted):
        nds_message = said[mp, who][0] if (mp, who) in said else ''
        if (mp, who) in MANUAL:
            for sfc, at, time in MANUAL[mp, who]:
                rows.append({'nds_map': mp, 'person': who, 'status': SURE, 'map': sfc, 'cell': at, 'time': time,
                             'score': '', 'margin': '', 'fc_message': '', 'nds_message': nds_message})
            continue
        sfc = MAPS.get(mp)
        found = []
        if sfc and sfc != 'field':
            persons = by_map[sfc]
            for e in entries.get(sfc, ()):
                score = {k: max(similarity(t, e['kana']) for t in texts) for k, texts in persons.items()}
                best = max(score.values())
                if score.get((mp, who)) != best or not best:
                    continue
                mine = set(persons[mp, who])
                rival = max([v for k, v in score.items() if set(persons[k]) != mine] or [0.0])
                margin = best - rival
                sure = (best >= SURE_SCORE and margin >= SURE_MARGIN) or (best >= WEAK_SCORE and margin >= WEAK_MARGIN)
                if len(e['kana']) < SHORT and best < 1:
                    sure = False
                if sure:
                    found.append((e, best, margin))
        if not found:
            rows.append({'nds_map': mp, 'person': who, 'status': UNSURE, 'map': '', 'cell': '', 'time': '',
                         'score': '', 'margin': '', 'fc_message': '', 'nds_message': nds_message})
            continue
        for e, best, margin in found:
            rows.append({'nds_map': mp, 'person': who, 'status': SURE, 'map': sfc, 'cell': e['cell'], 'time': e['time'],
                         'score': f'{best:.2f}', 'margin': f'{margin:.2f}', 'fc_message': e['message'],
                         'nds_message': nds_message})
    return rows


def read_people(path=PEOPLE_TSV):
    """{(NDS 맵, 인물 번호): [행]}. cell 은 (x, y)."""
    out = {}
    if not Path(path).exists():
        return out
    head, *rows = Path(path).read_text(encoding='utf-8').splitlines()
    keys = head.split('\t')
    for r in rows:
        row = dict(zip(keys, r.split('\t')))
        if row['cell']:
            row['cell'] = tuple(int(v) for v in row['cell'].split(','))
        out.setdefault((row['nds_map'], row['person']), []).append(row)
    return out


def cmd_people(jp, dq5, dq4):
    rows = pair_people(jp, fc_entries(dq5, dq4))
    print('\t'.join(PEOPLE_HEAD))
    for r in rows:
        print('\t'.join(','.join(map(str, r[k])) if isinstance(r[k], tuple) else str(r[k]) for k in PEOPLE_HEAD))


# ---- 3장 ----

# NDS 맵 → SFC 맵(여럿이면 그 모두에 같은 줄). 레이크나바 그룹 3E(FC 16·3D), 본몰 3F(FC 05), 엔돌 40(FC 04, 건물 1층은
# 마을 맵), 굴 47(FC 42), 여우 마을·여신상 동굴 48(FC 18·40). 북쪽 동굴은 층마다 같은 한 줄뿐이라 SFC 일곱 층 모두에 둔다.
# 여신상 동굴 deb2a·deb3a 는 단추 앞뒤로 SFC 맵이 둘이다(48/03·04, 48/05·06, dq4ch3endor.CAVE_*)
NORTH_CAVE = tuple(f'3E/{m:02X}' for m in range(0x03, 0x0A))
MAPS3 = {
    'mfout': ('3E/00',), 'mfk1f1': ('3E/00',), 'mfm1f1': ('3E/01',),
    'mgout1': ('48/00',), 'mgout3': ('48/01',),
    'cdout': ('3F/01',), 'cdf1': ('3F/01',), 'cdy1f1': ('3F/01',),
    **{m: NORTH_CAVE for m in ('ddb1a', 'ddb1b', 'ddb2', 'ddb3', 'ddb4', 'ddb5a', 'ddb5b')},
    'deb1': ('48/02',), 'deb2a': ('48/03', '48/04'), 'deb3a': ('48/05', '48/06'), 'deb4': ('48/07',),
    'dfb1a': ('47/00',), 'dfb1b': ('47/01',),
    'hcout': ('40/00',), 'hcm2f1': ('40/00',), 'hcm1f2': ('40/0A',), 'hcm2f2': ('40/08',), 'hcy1b1': ('40/01',),
    'hcy1f2': ('40/0B',), 'ccf1a': ('40/02',), 'ccf2': ('40/06',), 'ccb1a': ('40/05',),
    'saf1': ('45/0E',), '#544': ('field',),
}
# NDS 이야기 flag(param_player_flag 의 3장 프리셋 59~92 가 켜는 번호) → SFC flag 이름(dq4ch3partytalk.CONDITIONS)
STORY3 = {
    137: 'SON_FREED',   # 톰 아들이 돌아옴(프리셋 67)
    140: 'FOXED',       # 여우를 물리침(71)
    142: 'SCOTT', 143: 'LAWRENCE',      # 용병을 고용함(필드 줄, 날수 조건과 함께)
    145: 'LETTER2',     # 본몰 왕에게 엔돌 왕의 편지를 보임(78)
    146: 'ALLOWED',     # 가게를 살 수 있음(80): 엔돌 왕이 「よくぞ もどった」
    149: 'SHOP',        # 가게를 삼(86)
    150: 'ORDER',       # 왕에게 무기 주문을 받음(88)
    151: 'PAID', 152: 'PAID',           # 굴 공사 시작(90): 공사비를 냄
    153: 'RESUMED', 154: 'RESUMED',     # 노인의 소식을 기다림(91): 공사 재개
    156: 'OPENED',      # 굴이 뚫림(92)
}
ORDER3 = ('CHAPTER3', 'SON_FREED', 'FOXED', 'LETTER2', 'ALLOWED', 'SHOP', 'ORDER', 'DELIVERED', 'PAID', 'RESUMED',
          'OPENED')
NAMES3 = {'スコット': 'SCOTT', 'ロレンス': 'LAWRENCE', 'トルネコ': 'TORNEKO', 'トーマス': 'THOMAS'}
ITEMS3 = {140: 'STATUE'}                # NDS 물건 번호 → SFC 물건 이름(dq4ch3partytalk.ITEMS)
DAYS3 = {13: 'SCOTT_DAYS', 14: 'LAWRENCE_DAYS'}     # 조건 13·14: 고용 뒤 지난 날수
# 직전 대화 값 v 는 3장 그룹 오브젝트 v + 1 이다. (NDS 맵, 오브젝트) → SFC 말 상대(dq4ch3partytalk 이 대화 번호로 푸는
# 이름): 「키.대화」 는 3장 사건 모듈 키(dq4ch3slots)와 그 TALKS 이름, 「맵:x-y:낮밤」 은 옮긴 FC 인물(FC 칸)
OBJECTS3 = {
    ('ccb1a', 5): ('40/05:5-2:night',),             # 하녀 「デスピサロが いなくなったのは」
    ('ccb1a', 6): ('W.pizarro_fan',),               # 아주머니 「デスピサロさまが ぜったいに 優勝」
    ('ccf1a', 5): ('E.deliver',),                   # 병사장(납품)
    ('ccf1a', 6): ('W.pizarro_gone',),              # 남자 「デスピサロという男が 優勝しかけた」
    ('ccf2', 3): ('E.king',),
    ('cdf1', 4): ('B.king',),
    ('cdf1', 7): ('3F/01:6-6:day',),                    # 왕자 방의 유모 「武器商人ふぜいの 来てよい所では」
    ('cdy1f1', 2): ('3F/01:6-28:day', '3F/01:6-28:night'),  # 학자 「人を化かす きつねが でるそうだな」
    ('deb3a', 1): ('48/05:19-20:day', '48/05:19-20:night'),   # 거친 사내 「宝箱が 取れねえ」
    ('deb3a', 2): ('48/06:27-9:day', '48/06:27-9:night'),     # 거친 사내 「上から 水が あふれて」
    ('dfb1a', 1): ('T.old_man',),
    **{('hcm1f2', o): ('E.collector',) for o in (1, 3, 4, 5)},
    ('hcm2f1', 1): ('E.nene',), ('hcm2f1', 2): ('E.nene',),
    ('hcm2f2', 1): ('E.seller',), ('hcm2f2', 2): ('E.seller',),
    ('hcout', 9): ('E.scott',),
    ('hcy1b1', 1): ('W.ryan',),
    ('hcy1f2', 3): ('40/0B:11-3:night',),           # 전사 「サントハイムから 人々が 消えた」
    ('mfk1f1', 1): ('W.nun',),
    ('mfm1f1', 3): ('L.nene',), ('mfm1f1', 4): ('L.nene',),
    ('mfout', 10): ('L.son',),
}
# 레코드마다 손으로 옮긴 것: 최근 이벤트 값(v0)이 그 말 상대의 대사면 직전 대화 값과 같게 보고(on·off 를 더함), 맵 안
# 임시 flag 가 SFC 의 다른 맵이면 그 맵으로(flag_c). 근거는 그 레코드의 v0 메시지(NDS 대사)
FIXES3 = {
    5: {'v0': True, 'on': ('DELIVERED',)}, 6: {'v0': True, 'on': ('DELIVERED',)},     # 병사장 「代金を支払おう」
    56: {'v0': True, 'off': ('PAID',)}, 57: {'v0': True, 'off': ('PAID',)},           # 노인 「まず 自分の店を」
    58: {'v0': True, 'on': ('PAID',)}, 59: {'v0': True, 'on': ('PAID',)},             # 노인 「６００００Ｇ 受け取った」
    74: {'v0': True}, 75: {'v0': True}, 76: {'v0': True}, 77: {'v0': True},          # 수집가 「ダメなのか」
    84: {'v0': True, 'on': ('DOG',)}, 88: {'v0': True, 'on': ('DOG',)},               # 스콧 「犬が きらいなのだ」
    # 고용 대사(「やとってくれるか」·「やとってくれますか」)는 「예」 일 때만 뜬다: 방금 그 용병에게 말을 걸어 고용함
    **{k: {'v0': True, 'talked': (who,), 'on': ('HIRED_NOW',)}
       for k, who in ((85, 'E.scott'), (89, 'E.scott'), (96, 'E.lawrence'), (99, 'E.lawrence'))},
    108: {'v0': True},                                                                  # 톰 아들 「返したくなったら」
    40: {'flag_c': {60: ('48/04',)}}, 41: {'flag_c': {60: ('48/04',)}},               # 물이 빠짐: 단추 뒤의 맵
}
# 옮기지 않는 레코드와 까닭(조건은 옮길 수 있으나 SFC 장면과 맞지 않음)
SKIP3 = {
    113: 'SFC 3장의 여행의 문 사당 병사는 2장 대사(「姫さまを 通すな」) 그대로라 「よそ者は 通さない」 에 답하는 말이 맞지 않음',
    114: 'SFC 3장의 여행의 문 사당 병사는 2장 대사(「姫さまを 通すな」) 그대로라 「よそ者は 通さない」 에 답하는 말이 맞지 않음',
}


def convert3(f, msgs):
    """3장 레코드 하나: (줄 dict, None) 또는 (None, 뺀 까닭). 줄은 2장 줄에 have·lack(물건 이름)·days(「이름=값」)가 더해지고
    map 이 SFC 맵 묶음(maps)이다. 토마스(개)는 일행 기록이 아니라 말하는 이를 톨네코로 두고 DOG flag 를 조건에 더한다."""
    k, mp = f['k'], f['mapname']
    if k in SKIP3:
        return None, SKIP3[k]
    fix = FIXES3.get(k, {})
    talked = []
    if f['place'][0] != 0xFF:
        for v in f['place']:
            if v != 0xFF:
                talked += [t for t in OBJECTS3.get((mp, v + 1), ()) if t not in talked]
        if not talked:
            return None, '방금 말을 건 마을 사람(SFC 말 상대 짝 없음)'
    if f['v0'] and not fix.get('v0'):
        return None, '방금 본 사건 대사(최근 이벤트 값)'
    talked = list(fix.get('talked', talked))
    on, off, have, lack, days = ['CHAPTER3', *fix.get('on', ())], list(fix.get('off', ())), [], [], []
    maps = MAPS3.get(mp)
    for c, v in zip(f['codes'], f['vals']):
        if not c:
            continue
        if c in (1, 2):
            (on if c == 1 else off).append(v)
        elif c == 5 and v in fix.get('flag_c', {}):
            maps = fix['flag_c'][v]
        elif c in (7, 8) and v in ITEMS3:
            (have if c == 7 else lack).append(ITEMS3[v])
        elif c in DAYS3:
            days.append(f'{DAYS3[c]}={v}')
        else:
            kinds = {3: '맵 안 임시 flag', 4: '맵 안 임시 flag', 5: '맵 안 임시 flag', 6: '맵 안 임시 flag',
                     7: '물건을 가짐', 8: '물건을 가짐', 12: '들어온 입구', 18: '방금 얻은 열쇠 물건'}
            return None, kinds.get(c, f'조건 종류 {c}')
    ids = message_ids(f)
    if ids is None:
        return None, '예/아니오 물음'
    if maps is None:
        raise SystemExit(f"{k}: NDS 맵 {mp} 의 SFC 짝이 없음")
    story_on, story_off = f['story']
    on.append(story_on)
    if story_off != 0xFFFF:
        off.append(story_off)
    for n in [n for n in on + off if isinstance(n, int)]:
        if n not in STORY3:
            return None, f'SFC 에 짝이 없는 NDS 이야기 flag({n})'
    on = [STORY3.get(n, n) if isinstance(n, int) else n for n in on]
    off = [STORY3.get(n, n) if isinstance(n, int) else n for n in off]
    speakers = []
    for m in ids:
        found = SPEAKER.match(msgs.get(m, ''))
        if not found or found[1] not in NAMES3:
            raise SystemExit(f"{k}: 메시지 {m} 의 말하는 이를 모름")
        speakers.append(NAMES3[found[1]])
    if f['speaker'] not in NAMES3 or NAMES3[f['speaker']] != speakers[0]:
        raise SystemExit(f"{k}: 말하는 인물 {f['speaker']} 와 첫 메시지가 다름")
    if any(mode != 1 for _, mode in f['slots']):
        return None, '일행 칸 조건(걷는 줄 밖·쓰러짐)'
    if 'THOMAS' in speakers:
        on.append('DOG')
        off.append('DOG_AWAY')
    who = ['TORNEKO' if s == 'THOMAS' else s for s in speakers]
    with_ = sorted(set(who[1:]) - {who[0], 'TORNEKO'})
    rank = {n: i for i, n in enumerate(ORDER3)}
    on = sorted(set(on), key=lambda n: (rank.get(n, len(rank)), n))
    off = sorted(set(off), key=lambda n: (rank.get(n, len(rank)), n))
    ordered_on, ordered_off = [rank[n] for n in on if n in rank], [rank[n] for n in off if n in rank]
    if ordered_off and max(ordered_on) >= min(ordered_off):
        return None, 'SFC 에 없는 진행 사이'
    return {'nds': k, 'maps': maps, 'speaker': who[0], 'priority': f['prio'], 'time': TIMES[f['time']],
            'on': on, 'off': off, 'with': with_, 'talked': talked, 'have': have, 'lack': lack, 'days': days,
            'messages': ids, 'speakers': speakers}, None


# 표 밖의 줄: NDS 는 맞는 줄이 하나도 없으면 일행에 따라 정한 문장을 띄운다(param-format.md 「고르기」). 3장은 개 토마스가
# 따라올 때의 512102「ワンワンワン」. 맵을 가리지 않는 줄(map any)이라 지금 맵에서 맞는 줄이 없을 때만 고른다
FALLBACK3 = ({'nds': -1, 'maps': ('any',), 'speaker': 'TORNEKO', 'priority': 13, 'time': 'any',
              'on': ['CHAPTER3', 'DOG'], 'off': ['DOG_AWAY'], 'with': [], 'talked': [], 'have': [], 'lack': [], 'days': [],
              'messages': [512102], 'speakers': ['THOMAS']},)


def lines3(jp):
    """([줄], [(레코드, 뺀 까닭)]). 줄은 SFC 맵마다 하나(maps 를 펼침)이고, 같은 맵에 겹친 같은 줄은 하나만. 끝에 표 밖의
    줄(FALLBACK3)."""
    _, ndstext = _nds()
    msgs = ndstext.messages(jp)
    kept, dropped, seen = [], [], set()
    for f in [*records(jp, 3), *FALLBACK3]:
        if f in FALLBACK3:
            kept.append({**f, 'map': 'any'})
            continue
        line, why = convert3(f, msgs)
        if line is None:
            dropped.append((f, why))
            continue
        for mp in line['maps']:
            one = {**line, 'map': mp}
            key = (mp, one['speaker'], one['priority'], one['time'], tuple(one['on']), tuple(one['off']),
                   tuple(one['with']), tuple(one['talked']), tuple(one['have']), tuple(one['lack']), tuple(one['days']),
                   tuple(one['messages']))
            if key in seen:
                continue
            seen.add(key)
            kept.append(one)
    return kept, dropped


HEAD3 = ('nds', 'map', 'speaker', 'priority', 'time', 'on', 'off', 'with', 'talked', 'have', 'lack', 'days',
         'messages')


HEAD = ('nds', 'map', 'speaker', 'priority', 'time', 'on', 'off', 'with', 'talked', 'messages')


def cmd_lines(jp, chapter=2):
    kept, _ = lines3(jp) if chapter == 3 else lines(jp)
    head = HEAD3 if chapter == 3 else HEAD
    print('\t'.join(head))
    for ln in kept:
        print('\t'.join(str(ln[k]) if not isinstance(ln[k], list) else ','.join(map(str, ln[k])) for k in head))


def cmd_range3(jp):
    """3장: 뺀 까닭별 레코드 수와 뺀 레코드 목록, 맵별 옮긴 줄 수(마크다운)."""
    kept, dropped = lines3(jp)
    why = collections.Counter(w for _, w in dropped)
    print('| 뺀 까닭 | 레코드 |')
    print('| --- | --- |')
    for w, n in why.most_common():
        print(f'| {w} | {n} |')
    print()
    print('| 레코드 | NDS 맵 | 말하는 이 | 첫 메시지 | 뺀 까닭 |')
    print('| --- | --- | --- | --- | --- |')
    for f, w in dropped:
        print(f"| {f['k']} | {f['mapname']} | {f['speaker']} | {f['msg']} | {w} |")
    print()
    per = collections.Counter(ln['map'] for ln in kept)
    print('| SFC 맵 | 줄 |')
    print('| --- | --- |')
    for mp in sorted(per, key=lambda m: (m == 'field', m)):
        print(f'| {mp} | {per[mp]} |')
    total = sum(1 for _ in records(jp, 3))
    print(f'\nNDS 레코드 {total}: 옮긴 레코드 {total - len(dropped)}(SFC 줄 {len(kept)}, 같은 맵에 겹친 줄 제외), '
          f'뺀 레코드 {len(dropped)}')


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


def cmd_source(jp, kr, chapter=2):
    """번역할 메시지: {번호: {'speaker', 'jp', 'kr'}}(일본어 원문과 한글 팬패치 문장, 작업용)."""
    _, ndstext = _nds()
    msgs = ndstext.messages(jp)
    ko = ndstext.messages(kr) if kr else {}
    table = ndstext.kr_table() if kr else {}
    kept, _ = lines3(jp) if chapter == 3 else lines(jp)
    out = {}
    for ln in kept:
        for m, sp in zip(ln['messages'], ln['speakers']):
            out[m] = {'speaker': sp, 'map': ln['map'], 'jp': msgs[m],
                      'kr': ndstext.decode_kr(ko[m], table) if m in ko else ''}
    json.dump(out, sys.stdout, ensure_ascii=False, indent=1)


def main():
    sys.path[:0] = [str(HERE), str(HERE.parents[1] / 'dq5' / 'tools')]
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--chapter', type=int, choices=(2, 3), default=2)
    ap.add_argument('cmd', choices=('lines', 'range', 'source', 'people'))
    ap.add_argument('jp')
    ap.add_argument('--kr')
    ap.add_argument('--dq5', default='rom/dq5.sfc')
    ap.add_argument('--dq4', default='rom/dq4.nes')
    a = ap.parse_args()
    if a.chapter == 3 and a.cmd == 'people':
        raise SystemExit('3장 말 상대 짝은 손으로 정한 표(OBJECTS3)')
    if a.cmd == 'people':
        cmd_people(a.jp, a.dq5, a.dq4)
    elif a.cmd == 'lines':
        cmd_lines(a.jp, a.chapter)
    elif a.cmd == 'range':
        cmd_range3(a.jp) if a.chapter == 3 else cmd_range(a.jp)
    else:
        cmd_source(a.jp, a.kr, a.chapter)


if __name__ == '__main__':
    main()
