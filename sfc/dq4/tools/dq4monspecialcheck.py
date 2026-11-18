"""dq4monspecial 의 새 몬스터 행동과 같은 몬스터 부르기를 MesenCE 전투 장면으로 보는 검사.
형식: sfc/dq4/docs/dq4-sprite-format.md 「새 행동 번호」.

1장 필드(서장 끝 출발 상태)에서 무리를 롬 치트로 덮어 싸우고, 메시지 입구 24:8C39 의 A(메시지 번호)와 7E:10F4~10F7
(10F5 행동하는 쪽, 10F7 행동)·무리 마릿수 7E:1005~ 를 기록한다(dq5warptrace.lua).

  mixed-*  서로 다른 두 종 무리에서 둘째 종만 부르기(B5 같은 몬스터, C8 みをまもる+たすけ)를 쓰고 나머지는 ようすをみる.
           부른 뒤 둘째 종의 마릿수만 늘어야 한다. 행동하는 쪽을 대상 $10F6 에서 읽으면 첫 종이 불린다
  block-NN キングスライム 이 マホステ(C9)를 쓴 뒤 주인공이 일행 주문 NN(전투원 칸 7E:1073 을 매 프레임 덮음, 대상 81)을
           외우면 외울 때마다 다음 메시지가 1A7「…에게는 주문이 닿지 않는다!」 이어야 한다. 실행 루틴(26:8865)마다 하나
  open-01  マホステ 없이(ようすをみる) 같은 メラ 는 1A7 없이 피해 메시지가 나와야 한다

  python sfc/dq4/tools/dq4monspecialcheck.py --rom work/ch3/dq4-ch1-full.sfc --out work/monspecial
"""
import argparse
import concurrent.futures
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[1] / 'dq5' / 'tools'), str(HERE.parents[2] / 'fc' / 'dq4' / 'tools')]

import dq4battlecheck  # noqa: E402
import dq4ch1walkcheck as wc  # noqa: E402
import dq4fieldencountercheck as fec  # noqa: E402
import dq4fieldport  # noqa: E402
import dq4freshstate  # noqa: E402
import dq4groupcheck  # noqa: E402
import dq4monport  # noqa: E402
import dq4monspecial as S  # noqa: E402
from kr_patch.fc import ines  # noqa: E402

DQ5_TOOLS = HERE.parents[1] / 'dq5' / 'tools'
MESSAGE = 0x248C39
LOG = '7E10F4,7E10F6,7E1005,7E1007'
WAIT_ACTION = '66'                  # ようすをみる
START_CELL = 0x14                   # 1장 필드 구역(dq4ch3monstercheck.CELLS 와 같은 자리)
# 행동하는 쪽 7E:10F5 가 몬스터면 bit7. 주인공은 00
HERO = 0x00
# 섞인 무리: (이름, 첫 종, 둘째 종, 둘째 종의 부르기)
MIXED = (('mixed-b5', 0x07, 0x50, dq4monport.SUMMON_SAME), ('mixed-c8', 0x07, 0x77, S.GUARD))
KING = 0x6B
# 적에게 거는 일행 주문을 실행 루틴(26:8865)마다 하나. メガンテ(15)는 외운 주인공이 쓰러지고, ミナデイン(12)은 혼자인
# 주인공이 외우면 071·072 로 끝나 대상에 닿지 않아 뺌
BLOCK_SPELLS = (0x01, 0x04, 0x07, 0x13, 0x14, 0x16, 0x17, 0x19, 0x1A, 0x1B, 0x1C, 0x1F, 0x20)
SPELL_SLOT, TARGET_SLOT = 0x7E1073, 0x7E1037      # 주인공(전투원 0)의 행동·대상(81 = 무리 0)
HERO_MP = '7E2044=63 7E2045=00'
CAST = 0x070
DAMAGE = (0x069, 0x06A)


def messages(path):
    """[(프레임, 메시지, 10F5, 10F7, 무리 마릿수 넷)]."""
    out = []
    for f, a, kv in fec.lines(path):
        if a != f'{MESSAGE:06X}':
            continue
        f4, f6 = int(kv['7E10F4'], 16), int(kv['7E10F6'], 16)
        counts = int(kv['7E1005'], 16).to_bytes(2, 'little') + int(kv['7E1007'], 16).to_bytes(2, 'little')
        out.append((f, int(kv['A'], 16) & 0xFFFF, f4 >> 8, f6 >> 8, tuple(counts)))
    return out


def mixed_problems(log, summon):
    uses = [i for i, (_, _, actor, act, _) in enumerate(log) if act == summon and actor & 0x80]
    if not uses:
        return ['둘째 종이 부르기를 쓰지 않음']
    # 주인공이 첫 종을 쓰러뜨리면 그 마릿수는 0 이 되므로 1 을 넘은 적이 있는지로 본다
    problems = []
    if max(c[0] for *_, c in log) > 1:
        problems.append(f'첫 종 마릿수가 {max(c[0] for *_, c in log)}(부른 몬스터가 첫 종)')
    if max(c[1] for *_, c in log) < 2:
        problems.append(f'둘째 종 마릿수가 {max(c[1] for *_, c in log)}')
    return problems


def block_problems(log, spell, shielded=True):
    start = next((i for i, m in enumerate(log) if m[1] == S.MSG_MIST), None) if shielded else 0
    if start is None:
        return ['マホステ(09B)가 나오지 않음']
    # 기록 끝(MAXF)에 걸려 다음 메시지가 없는 외움은 세지 않는다
    casts = [i for i in range(start, len(log) - 1) if log[i][1] == CAST and log[i][2] == HERO and log[i][3] == spell]
    if not casts:
        return [f'マホステ 뒤 주인공이 {spell:02X} 를 외우지 않음']
    problems = []
    for i in casts:
        nxt = log[i + 1][1] if i + 1 < len(log) else None
        if shielded and nxt != S.MSG_BLOCKED:
            problems.append(f'{log[i][0]}프레임 외운 뒤 {nxt if nxt is None else f"{nxt:03X}"}(1A7 아님)')
        if not shielded and (nxt == S.MSG_BLOCKED or nxt not in DAMAGE):
            problems.append(f'マホステ 없이 외운 뒤 {nxt if nxt is None else f"{nxt:03X}"}(피해 메시지 아님)')
    return problems


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--rom', required=True, type=Path)
    ap.add_argument('--dq4', default='rom/dq4.nes', type=Path)
    dq4freshstate.add_argument(ap)
    ap.add_argument('--out', required=True, type=Path)
    ap.add_argument('--jobs', type=int, default=4)
    ap.add_argument('--only', help='장면 이름 앞부분을 쉼표로')
    a = ap.parse_args(argv)
    mesence = Path(os.environ['MESENCE'])
    out = a.out.resolve()
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f'{out} is not empty')
    out.mkdir(parents=True, exist_ok=True)
    rom = a.rom.resolve()
    data = rom.read_bytes()
    prg = ines.prg(a.dq4.read_bytes())
    state = dq4freshstate.resolve(a.state, mesence, rom, out / 'start')
    dq4groupcheck.WARP = DQ5_TOOLS / 'lua' / 'dq5warptrace.lua'
    import dq4ch3monstercheck as C
    g, props = dq4fieldport.fc_field(prg, 0)
    x, y = fec.stand(g, props, C.CELLS[START_CELL])
    field = dq4fieldport.stand(x, y)

    def acts(m, act):
        return f'{wc.MONSTERS + m * 25 + 17:X}={act * 6}'

    def scene(name, groups, actions, poke='', presses=24, maxf=4200):
        patch = [dq4fieldport.warp_patch(data, *field), fec.RATES, dq4battlecheck.force_patch(groups)]
        patch += [acts(m, act) for m, act in actions]
        got = dq4groupcheck.scene(mesence, rom, state, out, name, FIELD='{},{}'.format(*field), ROMPATCH=';'.join(patch),
                                  TEST='idle:16,right:40,left:40,' + ','.join(['wait:60,a:2'] * presses), MAXF=str(maxf),
                                  TRACE=f'{MESSAGE:06X}', LOG=LOG,
                                  POKE=f"{wc.HERO_HP} {C.CLOCK['day']} {poke}".strip())
        trace = out / name / 'trace.txt'
        return got, messages(trace) if trace.exists() else []

    def mixed(name, first, second, summon):
        got, log = scene(name, [(first, 1), (second, 1)], [(first, WAIT_ACTION), (second, f'{summon:02X}')])
        problems = [got['error']] if 'error' in got else mixed_problems(log, summon)
        return name, {'ok': not problems, 'problems': problems, 'messages': [f'{m:03X}' for _, m, *_ in log][:40]}

    def block(spell, shielded=True):
        name = f'{"block" if shielded else "open"}-{spell:02X}'
        poke = f'{SPELL_SLOT:06X}={spell:02X} {TARGET_SLOT:06X}=81 {HERO_MP}'
        got, log = scene(name, [(KING, 1)], [(KING, f'{S.MAHOSTE if shielded else 0x66:02X}')], poke)
        problems = [got['error']] if 'error' in got else block_problems(log, spell, shielded)
        return name, {'ok': not problems, 'problems': problems, 'messages': [f'{m:03X}' for _, m, *_ in log][:40]}

    jobs = [(mixed, *m) for m in MIXED] + [(block, s) for s in BLOCK_SPELLS] + [(block, 0x01, False)]
    if a.only:
        names = lambda j: j[1] if j[0] is mixed else f'{"block" if len(j) == 2 else "open"}-{j[1]:02X}'  # noqa: E731
        jobs = [j for j in jobs if any(names(j).startswith(p) for p in a.only.split(','))]
    with concurrent.futures.ThreadPoolExecutor(a.jobs) as pool:
        results = dict(f.result() for f in [pool.submit(fn, *args) for fn, *args in jobs])
    ok = all(r['ok'] for r in results.values())
    (out / 'results.json').write_text(json.dumps({'status': 'passed' if ok else 'failed', 'checks': results},
                                                 ensure_ascii=False, indent=1) + '\n')
    for k, r in results.items():
        print(k, 'ok' if r['ok'] else r['problems'][:3])
    print('passed' if ok else 'failed')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
