"""일행 たたかう 의 회심 판정(20:C697~C6C4) 앞 조건 셋이 회심을 막거나 일으키는지 1장 롬에서 재는 검사(MesenCE 헤드리스).
형식은 sfc/dq4/docs/dq4-sound-port-format.md 「회심을 직접 일으키기」.

20:C697  BIT $100E / BMI 회심아님        $100E bit7
20:C69C  LDA #$1A / XBA / LDA $10F5 / BMI 회심아님(공격하는 쪽이 몬스터)
20:C6A4  BRK 8D(필드 41, 하위 1A) / LDA $49 / BNE 회심
20:C6AC  JSL $268D0A / BCS 회심           주인공 가진 물건 첫 일곱 칸이 26:8D33 과 같음
20:C6B2  LDA #$20 / JSL $00953A / CMP #$00 / BEQ 회심   1/32 난수
20:C6BC  CLC / RTS(회심 아님)   20:C6BE  LDA #$80 / STA $0DA8 / SEC / RTS(회심)

장면은 dq4battlecheck 의 들판 장면(서장 끝 상태에서 자리를 잡고 조우 루틴을 정한 무리로 덮음, 몬스터 HP 1)이고, 사례마다
검사 롬 사본에서 난수 판정만 「늘 회심」(20:C6B3 = 01) 또는 「회심 없음」(20:C6B9 = FF, 0~31 이 FF 와 같지 않음)으로 바꾸고
조건 하나를 켠다. lua/dq4critprobe.lua 가 판정을 지날 때마다 들어온 값·필드 41·가진 물건 결과와 갈래를 적는다. 첫 판정
(주인공의 첫 공격)의 갈래가 사례의 기대와 같아야 한다.

  MESENCE=… LIBDIR=… python sfc/dq4/tools/dq4critcheck.py --rom work/ch1/dq4-ch1-full.sfc --out work/critcheck
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import sys

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[1] / 'dq5' / 'tools')]

import dq4battlecheck as bc  # noqa: E402
import dq4ch1walkcheck as wc  # noqa: E402

PROBE = HERE / 'lua' / 'dq4critprobe.lua'
SITE, SITE_BYTES = 0x20C697, bytes.fromhex('2C0E103020A91AEBADF5103018008D8041A549D012220A8D26B00CA920223A9500C900F0021860A9808DA80D3860')
ALWAYS = (0x20C6B3, 0x01)      # LDA #$20 → #$01: 난수 0~0, 늘 0
NEVER = (0x20C6B9, 0xFF)       # CMP #$00 → #$FF: 난수 0~31 은 FF 와 같지 않음
ITEMS_AT = 0x2056              # 일행 레코드 0(주인공)의 가진 물건 첫 칸
ITEMS = bytes.fromhex('000A91023C64FF')    # 26:8D33(DQ5 「반드시 동료가 되는 가진 물건」)과 같은 일곱 칸


def lorom(addr):
    return (addr >> 16 & 0x7F) * 0x8000 + (addr & 0x7FFF)


def roll(kind):
    addr, value = {'always': ALWAYS, 'never': NEVER}[kind]
    return f'{lorom(addr):X}={value:02X}'


# 사례: (이름, 난수, SET(불러온 뒤 한 번), POKE(매 프레임), 기대 갈래)
CASES = [
    ('always', 'always', '', '', 'crit'),
    ('never', 'never', '', '', 'nocrit'),
    ('flag100e', 'always', '', '7E100E=80', 'nocrit'),
    ('state1a', 'never', '', '7E0767=40', 'crit'),
    ('items', 'never', ';'.join(f'{ITEMS_AT + i:04X}={b:02X}' for i, b in enumerate(ITEMS)), '', 'crit'),
]


def parse(text):
    """crit.txt → 판정마다 {enter, f41, reads, have, result}."""
    out, cur = [], None
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 2:
            continue
        if parts[1] == 'enter':
            cur = {'enter': dict(kv.split('=') for kv in parts[2:])}
            out.append(cur)
        elif cur is None:
            continue
        elif parts[1] == 'f41':
            kv = dict(p.split('=', 1) for p in parts[2:])
            cur['f41'], cur['reads'] = kv['49'], [r for r in kv.get('reads', '').split(',') if r]
        elif parts[1] == 'have':
            cur['have'] = parts[2].split('=')[1]
        elif parts[1] in ('crit', 'nocrit'):
            cur['result'] = parts[1]
    return out


def run_case(mesence, rom, data, base, out, case, seed=0):
    name, kind, sets, pokes, want = case
    scene = bc.SCENES['field']
    dest = out / name
    state = base
    names = [s[0] for s in wc.SEGMENTS]
    extra, party = wc.setup(wc.SEGMENTS, names.index(scene['after']) + 1)
    for k, seg in enumerate(scene['prep']):
        r = wc.segment(mesence, rom, state, dest / seg[0], seg, wc.NO_ENCOUNTERS,
                       *((extra, party) if k == 0 else ('', '')), seed, readset=True)
        if r['status'] != 'passed':
            return {'name': name, 'status': 'failed', 'problems': [f'자리 잡기 {seg[0]}: {r["problems"]}']}
        state = dest / seg[0] / 'end.mss'
    patch = ';'.join((bc.force_patch(scene['group']), bc.weak_patch(data, [m for m, _ in scene['group']]), roll(kind)))
    run_dir = dest / 'battle'
    env = {'NEXT': str(bc.BATTLE), 'STATE': str(state), 'ROMPATCH': patch, 'AFTERPATCH': wc.NO_ENCOUNTERS,
           'SET': ';'.join(x for x in (f'{wc.rng_for(seed)};{wc.DAY_SET}', sets) if x),
           'POKE': ';'.join(x for x in (wc.HERO_HP, pokes) if x), 'STEP': scene['step'], 'KEYS': 'a',
           'MOVE': scene['move'], 'MAXF': '3000', 'KANATABLE': bc.kana_range()}
    wc.run(mesence, rom, PROBE, run_dir, env, 300)
    text = (run_dir / 'crit.txt').read_text() if (run_dir / 'crit.txt').exists() else ''
    passes = parse(text)
    first = passes[0] if passes else {}
    problems = []
    if not passes:
        problems.append('회심 판정을 지나지 않음')
    elif first.get('result') != want:
        problems.append(f'첫 판정 {first.get("result")}, 기대 {want}')
    return {'name': name, 'status': 'failed' if problems else 'passed', 'problems': problems, 'want': want,
            'first': first, 'passes': len(passes)}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--rom', required=True, type=Path)
    ap.add_argument('--out', required=True, type=Path)
    ap.add_argument('--base', type=Path, help='서장 끝 세이브스테이트(같은 롬). 없으면 만든다(상태 캐시)')
    ap.add_argument('--cases', help='쉼표로 고른 사례만')
    args = ap.parse_args()
    mesence = Path(os.environ['MESENCE'])
    out = args.out.resolve()
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f'{out} is not empty')
    out.mkdir(parents=True, exist_ok=True)
    rom = out / 'c.sfc'
    shutil.copyfile(args.rom.resolve(), rom)
    data = rom.read_bytes()
    o = lorom(SITE)
    if data[o:o + len(SITE_BYTES)] != SITE_BYTES:
        raise SystemExit(f'{SITE:06X}: {data[o:o + len(SITE_BYTES)].hex()} — 회심 판정 코드가 바뀜')
    if args.base:
        base = args.base.resolve()
    else:
        # 서장은 읽은 바이트 캐시 없이 걷는다(dq4bigpiccheck 와 같은 까닭). 상태 캐시는 쓴다
        base, pro = wc.prologue(mesence, rom, data, out, wc.SEGMENTS, wc.StateCache(data), readset=False)
        if pro['status'] != 'passed':
            raise SystemExit(f'서장 실패: {pro["problems"]}')
    names = args.cases.split(',') if args.cases else [c[0] for c in CASES]
    results = [run_case(mesence, rom, data, base, out, c) for c in CASES if c[0] in names]
    ok = all(r['status'] == 'passed' for r in results)
    (out / 'results.json').write_text(json.dumps({'status': 'passed' if ok else 'failed', 'cases': results},
                                                 ensure_ascii=False, indent=1) + '\n')
    for r in results:
        print(json.dumps(r, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
