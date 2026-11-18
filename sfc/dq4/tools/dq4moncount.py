"""걸음 전투 무리 조합 가운데 SFC 가 FC 원작보다 몬스터를 덜 놓는 조합을 센다. 형식 문서
sfc/dq4/docs/dq4-sprite-format.md 「2장 전투 몬스터 그림」 의 「FC 보다 덜 놓이는 조합」.

1~3장 구역(CHAPTER_ZONES)의 무리 조합을 FC 무리 짓기 모형으로 모두 늘어놓고(outcomes), 조합마다 FC 가 화면에 놓는
마릿수(fc_shown)와 빌드 롬이 놓는 마릿수(sfc_placed)를 견준다. 어느 무리든 SFC 가 FC 보다 적게 놓으면 「덜 놓이는 조합」 이다.
(장, FC 구역, 때)마다 그 수를 KNOWN 과 견주어, 늘면 실패, 줄면 통과하고 새 수를 알린다. KNOWN 에 없는 곳은 0 이다.

모형과 그 근거:
- 무리 짓기: 빌드의 조우 훅(dq4fieldencounter.ch3_code, 23:E8FE 에서 들어감)은 FC 18:$9D6B~$9F78 을 옮긴 것이고,
  1~3장 구역은 모두 그 훅의 표(dq4fieldencounter.pick_rows)에 있다. 그래서 DQ5 구역 레코드의 칸 무게·마릿수 부호는 쓰이지
  않는다. run_states 는 dq4fieldencounter.fc_formation 을 난수 상태 배열에 한꺼번에 돌린 것이다(시험이 상태마다 견줌).
- 난수: 훅의 난수(rng_next, 23:EAFD)는 state × 3 + 15AD 이고 바이트는 state 의 16~23비트라, 무리 짓기 동안 나오는
  바이트는 들어올 때 state 의 아래 24비트로 모두 정해진다. 잇단 바이트가 서로 얽혀 있어, 바이트를 따로따로 고르다고 보고
  가지를 펴면 실제로는 나오지 않는 조합까지 센다(2장 FC 구역 0B 밤은 펴면 90 조합, 24비트 값 모두로는 26 조합).
  그래서 outcomes 는 아래 24비트 값 2^24 개를 모두 돌린다. 들어올 때 state 는 그 어느 값이든 될 수 있다고 본다. 조우를
  정한 앞의 난수(걸음 조우율)가 state 를 좁히는 것은 세지 않으므로, 센 조합은 실제로 나올 수 있는 조합의 위 끝이다.
  몫(p)은 그 값들 가운데 비율이다.
- 장 k: 훅은 2장 flag(dq4ch2event.CHAPTER2)가 켜져 있으면 k = 1, 3장 flag(dq4fieldencounter.chapter3_flag)면 2, 아니면 0
  으로 FC $A464(더할 마릿수 끝)·$A46C(더할 확률)의 k 칸을 읽는다(ch3_code 의 k_done). 그래서 장 c 의 구역은 k = c − 1 이다.
- 무리 값: 훅은 줄 번호 7E:1009~100B 를 0 으로 둔다(ch3_code 의 pick_slot). 그래서 무리 값은 모두 0 이고, 줄은 그림
  머리의 띄움으로만 정해진다(띄움이면 줄 2, 아니면 줄 0).
- SFC 배치: dq5monlimits.Pictures(빌드 롬).place 그대로(줄 폭 22:9284, 조각 합 22:91DC, 줄마다 타일 22:A119).
- FC 배치: fc_width·fc_shown(그림 자료는 fc/dq4/docs/dq4-fcsprite-format.md 「전투 몬스터 그림」). 폭은 롬에서 읽고, FC
  전투 덤프 여섯의 $7385 와 같았다(スライム 2, 0D 3, 6D·6E 8). 놓인 마리 수($6E49)는 다섯이 fc_shown 과 같았고,
  6D 3마리 무리만 1마리였다(OBJ 부품이 있는 그림이라 아래 한도로 보이나 재지 않음). FC 가 무리를 덜 놓는 한도 가운데 화면 폭만 센다. 14:$812F 는 무리마다 팔레트 칸(14:$9439·
  $93F2)·CHR 칸(14:$9682·$9686)·OBJ 줄마다 수(14:$9ADD)도 보아 넘으면 그 무리를 뺀다(14:$81AE → $81F4). 이것들은 세지
  않으므로 fc_shown 은 FC 가 실제로 놓는 수의 위 끝이고, 덜 놓이는 조합에는 FC 도 그 한도로 덜 놓는 조합이 섞일 수 있다.
  결과의 fc_obj 는 OBJ 부품이 있는 FC 몬스터가 든 조합이다(OBJ 줄마다 수에 걸릴 수 있는 것).

  python sfc/dq4/tools/dq4moncount.py --rom work/ch1/dq4-ch1-full.sfc --out work/moncount
결과: OUT/results.json(곳마다 수, 덜 놓이는 조합 목록).
"""
import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
for _p in (HERE, HERE.parents[1] / 'dq5' / 'tools', ROOT / 'fc' / 'dq4' / 'tools'):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import dq4fieldencounter as FE  # noqa: E402

# 장마다 걸음 전투가 나는 FC 구역. 1장: 필드 04~06(バトランド·イムル 둘레)과 던전 40~43. 2장: 산트하임·텐페·프레놀·바자의
# 필드 07~0C, 엔돌 둘레 14·15, 서쪽 탑·남쪽 동굴 4C~4F. 3장: dq4fieldencounter.CH3_ZONES.
CHAPTER_ZONES = {
    1: (0x04, 0x05, 0x06, 0x40, 0x41, 0x42, 0x43),
    2: (0x07, 0x08, 0x09, 0x0A, 0x0B, 0x0C, 0x14, 0x15, 0x4C, 0x4D, 0x4E, 0x4F),
    3: FE.CH3_ZONES,
}
# (장, FC 구역, 때): 덜 놓이는 조합 수. 때는 day·night·dungeon(던전은 낮·밤이 같은 목록)
KNOWN = {
    (2, 0x08, 'night'): 1,
    (2, 0x09, 'day'): 4, (2, 0x09, 'night'): 2,
    (2, 0x0B, 'day'): 7, (2, 0x0B, 'night'): 5,
    (2, 0x0C, 'day'): 19, (2, 0x0C, 'night'): 15,
    (2, 0x4C, 'dungeon'): 3, (2, 0x4D, 'dungeon'): 8, (2, 0x4E, 'dungeon'): 9, (2, 0x4F, 'dungeon'): 15,
}

FC_BANK = 0x14
WIDTH_LIMIT = 0x20          # 14:$9C5E CMP #$20: 마리마다 폭 + 1 을 더한 합이 이 값 이상이면 그 마리부터 놓지 않음
BOSS_PICTURE, BOSS_WIDTH_AT = 0xAE, 0x932B   # 14:$9326 CMP #$AE / LDA #$0E: デスピサロ 폭은 고정값
# 14:$9392~$93A3: 폭(BG 가장 오른쪽 열 + 1)에 1 을 더 하는 그림 번호. CMP #xx 의 피연산자 자리
WIDE_CMP_AT = (0x9395, 0x9399, 0x939D, 0x93A1)
CMP_IMM = 0xC9


def _rd(prg, addr):
    return prg[FC_BANK * 0x4000 + (addr & 0x3FFF)]


def wide_pictures(prg):
    """14:$9392 가 폭을 하나 더 늘리는 그림 번호(CMP #xx 넷). $C4 는 이때 그림 번호다(14:$814B 가 $9F0C 로 바꾼 뒤
    $92EF → $9320). 몬스터 번호가 아니다."""
    for a in WIDE_CMP_AT:
        if _rd(prg, a - 1) != CMP_IMM:
            raise ValueError(f'14:{a - 1:04X} 가 CMP # 이 아님')
    return {_rd(prg, a) for a in WIDE_CMP_AT}


def fc_width(prg, mid):
    """FC 몬스터 mid 의 폭($7385 + 무리, 14:$9320 이 $D2 에 셈): 그림 타일 배치 가운데 BG 배치(머리 bit6)의 열(자리 바이트
    아래 4비트) 최댓값 + 1, 그림 번호가 wide_pictures 이면 + 1, デスピサロ 는 14:$932B 의 값."""
    import dq4fcsprite as S
    p = S.mon_pic(prg, mid)
    if p == BOSS_PICTURE:
        return _rd(prg, BOSS_WIDTH_AT)
    tiles, *_ = S.mon_stream(prg, p)
    w = 0
    for pls, _ in tiles:
        for h, pos in pls:
            if h & 0x40:
                w = max(w, pos[0] & 0x0F)
    return w + 1 + (p in wide_pictures(prg))


def fc_has_obj(prg, mid):
    """그림에 OBJ 배치(머리 bit6 = 0)가 있는지. OBJ 줄마다 수 한도(14:$9ADD)에 걸릴 수 있는 몬스터."""
    import dq4fcsprite as S
    p = S.mon_pic(prg, mid)
    tiles, *_ = S.mon_stream(prg, p)
    return any(not h & 0x40 for pls, _ in tiles for h, _ in pls)


def fc_shown(widths, groups):
    """14:$9C54: 무리 차례로 마리마다 폭 + 1 을 합에 더해 WIDTH_LIMIT 이상이 되면 그 무리는 거기까지, 다음 무리로.
    합($CA)은 전투마다 0 에서 시작해 무리를 건너 이어진다. groups [(FC 몬스터, 마릿수)] → 무리마다 놓는 수."""
    used, out = 0, []
    for m, n in groups:
        k = 0
        while k < n and used + widths[m] + 1 < WIDTH_LIMIT:
            used += widths[m] + 1
            k += 1
        out.append(k)
    return out


def sfc_placed(pictures, groups):
    """빌드 롬이 놓는 수: dq5monlimits.Pictures.place 에 [(DQ5 몬스터, 마릿수, 무리 값 0)]."""
    kept = pictures.place([(m, n, 0) for m, n in groups])[0]
    return [j for _, j, *_ in kept]


STATE_BITS = 24
GROUPS, FIELD = 4, 13       # 무리 칸 넷, 칸마다 FC 몬스터 8비트 + 마릿수 5비트


class _Rng:
    """states 마다 따로 도는 rng_next(23:EAFD). mask 가 참인 칸만 한 걸음 나아간다."""

    def __init__(self, states):
        self.cur = states.astype(np.uint32)

    def __call__(self, mask):
        nxt = (self.cur * np.uint32(3) + np.uint32(FE.RNG_ADD)) & np.uint32((1 << STATE_BITS) - 1)
        self.cur = np.where(mask, nxt, self.cur)
        return (nxt >> 16 & 0xFF).astype(np.int32)


def _pick(rng, entries, mask):
    """fc_pick(entries, rnd()) 를 칸마다: 고른 칸, 없거나 mask 가 거짓이면 −1. 목록이 비어도 난수는 한 번 쓴다."""
    r = rng(mask)
    if not entries:
        return np.full(mask.shape, -1, np.int32)
    total = sum(w for _, w in entries)
    if total > 0xFF:
        raise ValueError(f'무게 합 {total} 이 FF 를 넘음(FC 는 8비트로 더함)')
    r = r if total == 0xFF else total * r >> 8
    idx = np.searchsorted(np.cumsum([w for _, w in entries]), r, side='left')
    return np.where(mask, np.array([s for s, _ in entries] + [-1], np.int32)[idx], -1)


def run_states(row, fc, tables, k, night, states):
    """fc_formation 을 states(난수 상태 배열)마다 한꺼번에: (FC 몬스터 [n, 4](없으면 −1), 마릿수 [n, 4], 첫 칸 [n]).
    row 는 pick_rows 의 한 줄(고를 칸), fc 는 같은 구역의 zone_data(prg, z, 같은 번호)(FC 몬스터 번호)."""
    _, _, third, fourth, modes, _ = row
    first, second = modes['night' if night else 'day']
    mons = np.array([m if m != 0xFF else -1 for m in fc['monsters']], np.int32)
    n = len(states)
    rng = _Rng(states)
    mon = np.full((n, GROUPS), -1, np.int32)
    cnt = np.zeros((n, GROUPS), np.int32)
    rows = np.arange(n)
    slot = _pick(rng, first, np.ones(n, bool))

    multi = (slot >= 0) & (slot < 5)
    mon[multi, 0], cnt[multi, 0] = mons[slot[multi]], 1
    groups = multi.astype(np.int32)
    on = multi.copy()
    for limit in (None, third, fourth):
        if limit is not None:
            on &= rng(on) < limit
        s2 = _pick(rng, second, on)
        on &= s2 >= 0
        mon[rows[on], groups[on]], cnt[rows[on], groups[on]] = mons[s2[on]], 1
        groups += on
    total, at, on = groups.copy(), np.zeros(n, np.int32), multi.copy()
    while True:
        on &= total < tables['extra_max'][k]
        if not on.any():
            break
        on &= rng(on) < tables['extra_p'][k]
        at = np.where(on & (at >= groups), 0, at)
        cnt[rows[on], at[on]] += 1
        at, total = at + on, total + on

    lead = slot == 5
    mon[lead, 0], cnt[lead, 0] = mons[5], 1
    s2 = _pick(rng, second, lead)
    lead &= s2 >= 0
    r = rng(lead)
    mon[lead, 1], cnt[lead, 1] = mons[s2[lead]], 3 + (5 * r[lead] >> 8)

    solo = (slot >= 6) & (slot < 11)
    code = fc['codes'] >> 3 * np.clip(slot - 6, 0, 4) & 7
    r = rng(solo)
    mon[solo, 0] = mons[slot[solo]]
    cnt[solo, 0] = (np.array(tables['solo_add'])[code] + (np.array(tables['solo_cnt'])[code] * r >> 8))[solo]

    one = slot == 11
    mon[one, 0], cnt[one, 0] = mons[11], 1

    for fs, members in fc['formations'].items():
        form = slot == fs
        g = 0
        for m, add, c in members:
            r = rng(form)          # 18:$9E2D 는 몬스터가 FF 인 무리도 마릿수를 굴린다
            if m != 0xFF:
                mon[form, g], cnt[form, g] = m, add + (c * r[form] >> 8)
                g += 1
    return mon, cnt, slot


def outcomes(row, fc, tables, k, night, chunk=1 << 22):
    """{무리 [(FC 몬스터, 마릿수)] 튜플: 몫}: 난수 상태 아래 STATE_BITS 비트의 모든 값에서 훅이 짓는 무리(고를 칸이 없는
    상태는 뺌). 몫은 그 값들 가운데 그 무리가 나오는 비율. 마릿수 0 인 무리는 뺀다(두 쪽 모두 놓지 않음)."""
    out = defaultdict(int)
    for lo in range(0, 1 << STATE_BITS, chunk):
        mon, cnt, slot = run_states(row, fc, tables, k, night, np.arange(lo, lo + chunk, dtype=np.uint32))
        key = np.zeros(len(slot), np.int64)
        for i in range(GROUPS):
            live = cnt[:, i] > 0
            key |= np.where(live, (mon[:, i] & 0xFF) | cnt[:, i] << 8, 0).astype(np.int64) << FIELD * i
        keys, counts = np.unique(key[slot >= 0], return_counts=True)
        for v, c in zip(keys.tolist(), counts.tolist()):
            groups = []
            for i in range(GROUPS):
                f = v >> FIELD * i & ((1 << FIELD) - 1)
                if f:
                    groups.append((f & 0xFF, f >> 8))
            out[tuple(groups)] += c
    return {g: c / (1 << STATE_BITS) for g, c in out.items()}


def count(build, prg, dq5):
    """{'places': {(장, FC 구역, 때): {...}}, 'short': [...]}: 장·구역·때마다 조합 수와 덜 놓이는 조합."""
    import dq4groupbuild
    import dq5encounterwrite
    import dq5monlimits
    from dq5map import Rom
    enc = dq5encounterwrite.dump(Rom(dq5))
    _, _, report = FE.docs(prg, dq5, enc, dq4groupbuild.dungeon_zones(prg).values())
    rows = {row[1]: row for row in FE.pick_rows(prg, report)}
    tables = FE.fc_tables(prg)
    pictures = dq5monlimits.Pictures(Rom(build))
    same = {i: i for i in range(256)}
    widths, objs = {}, {}
    places, short = {}, []
    for ch, zones in CHAPTER_ZONES.items():
        for z in zones:
            row = rows[z]
            fc = FE.zone_data(prg, z, same)
            dungeon = row[4]['day'] == row[4]['night']
            for night in ((False,) if dungeon else (False, True)):
                mode = 'dungeon' if dungeon else 'night' if night else 'day'
                combos = outcomes(row, fc, tables, ch - 1, night)
                bad = 0
                for groups, p in sorted(combos.items()):
                    for m, _ in groups:
                        if m not in widths:
                            widths[m], objs[m] = fc_width(prg, m), fc_has_obj(prg, m)
                    want = fc_shown(widths, groups)
                    dq5g = [(FE.MONSTERS[m], n) for m, n in groups]
                    got = sfc_placed(pictures, dq5g)
                    if any(g < w for g, w in zip(got, want)):
                        bad += 1
                        short.append({'chapter': ch, 'fc_zone': z, 'area': row[0], 'mode': mode,
                                      'fc': [list(g) for g in groups], 'dq5': [list(g) for g in dq5g],
                                      'fc_shown': want, 'placed': got, 'p': p,
                                      'fc_widths': [widths[m] for m, _ in groups],
                                      'fc_obj': any(objs[m] for m, _ in groups)})
                places[ch, z, mode] = {'area': row[0], 'combos': len(combos), 'short': bad,
                                       'p_short': sum(s['p'] for s in short[len(short) - bad:])}
    return {'places': places, 'short': short}


def judge(places, known=None):
    """(늘어난 곳, 줄어든 곳): [(곳, 알려진 수, 지금 수)]. known 에 없는 곳은 0."""
    known = KNOWN if known is None else known
    up, down = [], []
    for key in sorted(set(places) | set(known)):
        was, now = known.get(key, 0), places.get(key, {}).get('short', 0)
        if now > was:
            up.append((key, was, now))
        elif now < was:
            down.append((key, was, now))
    return up, down


def label(key):
    ch, z, mode = key
    return f'{ch}장 FC 구역 {z:02X} {mode}'


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--rom', type=Path, required=True, help='빌드 롬')
    ap.add_argument('--dq4', type=Path, default=ROOT / 'rom' / 'dq4.nes')
    ap.add_argument('--dq5', type=Path, default=ROOT / 'rom' / 'dq5.sfc')
    ap.add_argument('--out', type=Path, required=True)
    args = ap.parse_args()
    from kr_patch.fc import ines
    res = count(args.rom.read_bytes(), ines.prg(args.dq4.read_bytes()), args.dq5.read_bytes())
    places = res['places']
    up, down = judge(places)
    args.out.mkdir(parents=True, exist_ok=True)
    doc = {'places': [{'chapter': ch, 'fc_zone': z, 'mode': mode, **v} for (ch, z, mode), v in sorted(places.items())],
           'short': res['short'], 'grew': [[label(k), a, b] for k, a, b in up],
           'shrank': [[label(k), a, b] for k, a, b in down]}
    (args.out / 'results.json').write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding='utf-8')
    for ch in CHAPTER_ZONES:
        n = sum(v['short'] for (c, _, _), v in places.items() if c == ch)
        total = sum(v['combos'] for (c, _, _), v in places.items() if c == ch)
        print(f'{ch}장: 조합 {total}, FC 보다 덜 놓이는 조합 {n}')
    for key, v in sorted(places.items()):
        if v['short']:
            print(f'  {label(key)} (DQ5 구역 {v["area"]}): {v["short"]}/{v["combos"]}, 확률 합 {v["p_short"]:.2%}')
    for key, was, now in down:
        print(f'줄었음: {label(key)} {was} → {now}. KNOWN 을 {now} 로 낮춘다')
    for key, was, now in up:
        print(f'늘었음: {label(key)} {was} → {now}')
    if up:
        sys.exit(1)
    print('통과')


if __name__ == '__main__':
    main()
