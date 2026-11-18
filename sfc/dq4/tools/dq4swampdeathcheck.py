"""3장 롬에서 독늪에서 쓰러짐(dq4swampdeath)을 본다(MesenCE 헤드리스). 1장 장면(라이안 혼자·호이민 동행)은 dq4ch1savecheck 의
swamp-* 이다.

3장 출발 상태(dq4ch3walkcheck.head)에서 필드 줄 41 의 독늪(80~82, 여신상 동굴 입구 둘레) 왼쪽 언덕 (7E,41)에 서서 오른쪽으로
걷는다. 조우 없음, 난수(7E:075B·075C) 고정. 장면(SCENES):
  torneko  톨네코 혼자 HP 2: 쓰러짐 메시지 586, 전멸 처리 01:88EF 한 번, 금화 반(FC 12:$ADC2)
  safe     같은데 소지품에 철 금고: 금화 그대로(FC 3장)
  scott    톨네코와 용병 スコット, スコット 만 HP 2: 586, スコット 레코드 쓰러짐(+1 bit7 꺼짐)·관(7E:1978), 전멸 없음, 금화 그대로

  MESENCE=… LIBDIR=… python sfc/dq4/tools/dq4swampdeathcheck.py --rom work/ch3/dq4-ch1-full.sfc --out work/swampdeath
형식은 sfc/dq4/docs/dq4-field-format.md 「독늪에서 쓰러짐」.
"""
import argparse
import concurrent.futures
import json
import os
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DQ5_TOOLS = HERE.parents[1] / 'dq5' / 'tools'
for p in (HERE, DQ5_TOOLS):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import dq4ch1walkcheck as wc  # noqa: E402
import dq4ch3partytalkcheck as ptc  # noqa: E402
import dq4ch3walkcheck as cw3  # noqa: E402
import dq4dungeonencountercheck as enc  # noqa: E402
import dq4fieldport  # noqa: E402
import dq4groupcheck  # noqa: E402
import dq4swampdeath as sd  # noqa: E402
from dq4itemport import IRON_SAFE  # noqa: E402

START = (0x7E, 0x41)
GOLD = 1000
RNG = '075B=55;075C=AA'
MESSAGE, WIPE = '248BAF', '0188EF'
# 이름 → (일행 용병, 레코드마다 HP, 철 금고, 쓰러질 레코드, 전멸)
SCENES = {'torneko': ((), (2,), False, (), True), 'safe': ((), (2,), True, (), True),
          'scott': (('scott',), (0x30, 2), False, (1,), False)}
TEST = 'idle:16,' + ','.join(['right:40,wait:40,a:8'] * 40)


def run(mesence, rom, start, out, name):
    members, hps, safe, dead, wipe = SCENES[name]
    data = rom.read_bytes()
    dq4groupcheck.WARP = DQ5_TOOLS / 'lua' / 'dq5warptrace.lua'
    cell = dq4fieldport.stand(*START)
    sets = [f'2019={GOLD & 0xFF:02X}', f'201A={GOLD >> 8:02X}', '201B=00']
    if members:
        sets += ptc.party_writes(data, members)
        sets += [f'{a:04X}|{v:02X}' for a, (v, _) in ptc.flag_bytes({'CHAPTER3', 'SCOTT'}).items() if v]
    sets += [f'{0x2042 + 42 * n:04X}={v:02X};{0x2043 + 42 * n:04X}=00' for n, v in enumerate(hps)]
    if safe:
        sets.append(f'{(sd.PARTY_ITEMS & 0xFFFF):04X}={IRON_SAFE:02X}')
    got = dq4groupcheck.scene(mesence, rom, start, out, name, FIELD='{},{}'.format(*cell),
                              ROMPATCH=f'{dq4fieldport.warp_patch(data, *cell)};{wc.NO_ENCOUNTERS}', TEST=TEST,
                              MAXF='4500', SET=';'.join(sets), POKE=RNG, TRACE=f'{MESSAGE},{WIPE}', LOG='7E201D')
    rows = list(enc.lines(out / name / 'trace.txt')) if (out / name / 'trace.txt').exists() else []
    ram = (out / name / 'final.wram').read_bytes() if (out / name / 'final.wram').exists() else bytes(0x20000)
    gold = ram[0x2019] | ram[0x201A] << 8 | ram[0x201B] << 16
    messages = [int(kv['A'], 16) & 0xFFFF for _, pc, kv in rows if pc == MESSAGE]
    wipes = sum(pc == WIPE for _, pc, _ in rows)
    dead_now = [n for n in range(len(hps)) if not ram[0x2041 + 42 * n] & 0x80]
    coffins = [n for n in range(ram[0x1967]) if ram[0x1978 + n] & 0x80]
    problems = []
    if sd.DIED not in messages:
        problems.append(f'쓰러짐 메시지 {sd.DIED:03X} 이 뜨지 않음({[f"{m:03X}" for m in messages[:8]]})')
    if wipes != (1 if wipe else 0):
        problems.append(f'전멸 처리 {wipes}번')
    want_gold = GOLD // 2 if wipe and not safe else GOLD
    if gold != want_gold:
        problems.append(f'금화 {gold}(기대 {want_gold})')
    if not wipe and (dead_now != list(dead) or coffins != list(dead)):
        problems.append(f'쓰러진 레코드 {dead_now}·관 {coffins}(기대 {list(dead)})')
    return name, {'status': 'failed' if problems else 'passed', 'problems': problems, **got, 'gold': gold,
                  'dead': dead_now, 'coffins': coffins, 'messages': [f'{m:03X}' for m in messages[:12]]}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--rom', required=True, type=Path, help='dq4build.py --chapter3 의 롬')
    ap.add_argument('--out', required=True, type=Path)
    ap.add_argument('--jobs', type=int, default=3)
    ap.add_argument('--base', type=Path, help='같은 롬으로 만든 3장 출발 상태. 주면 머리를 건너뜀')
    wc.add_seed_args(ap)
    args = ap.parse_args()
    mesence = Path(os.environ['MESENCE'])
    out = args.out.resolve()
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f'{out} is not empty')
    out.mkdir(parents=True, exist_ok=True)
    rom = out / 'c.sfc'
    shutil.copyfile(args.rom.resolve(), rom)
    data = rom.read_bytes()
    if args.base:
        start, head = args.base.resolve(), []
    else:
        cache = None if args.no_state_cache else wc.StateCache(data)
        start, head = cw3.head(mesence, rom, data, out, cache, repeat=2 if cache else 1)
    if start is None or any(r['status'] != 'passed' for r in head):
        print(json.dumps({'status': 'failed', 'head': head}, ensure_ascii=False))
        return 1
    with concurrent.futures.ThreadPoolExecutor(args.jobs) as pool:
        results = dict(f.result() for f in [pool.submit(run, mesence, rom, start, out, n) for n in SCENES])
    ok = all(r['status'] == 'passed' for r in results.values())
    report = {'status': 'passed' if ok else 'failed', 'scenes': results}
    (out / 'results.json').write_text(json.dumps(report, ensure_ascii=False, indent=1) + '\n')
    print(json.dumps(report, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
