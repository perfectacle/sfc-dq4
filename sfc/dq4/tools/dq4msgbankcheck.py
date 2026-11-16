"""보행 메시지 넷째 자리(55·56) 검사(MesenCE 헤드리스).

1장 롬의 메시지 묶음 셋을 넷째 자리로 옮긴 시험 롬을 만든다: 묶음 하나는 뱅크 55(색인 뱅크 1E), 하나는 55 끝에서
56 으로 걸치게(디코더가 뱅크 끝에서 INC $F2 로 넘어감), 하나는 뱅크 56(색인 뱅크 1F). 자리는 그 롬의 넷째 자리에서
이미 놓인 메시지 뒤의 빈 곳으로 정한다(places). 색인 항목만 새 자리로 고치고
옛 바이트는 그대로 두므로, 훅이 표를 거치지 않으면 다른 바이트를 읽어 코드가 달라진다. 서장 끝 상태(원래 롬으로
만든 것, dq4freshstate)에서 두 장면의 첫 보행 메시지(24:8BAF)를 그 묶음의 번호로 바꿔 끼우고, 색인 훅이 돌려준 스트림
주소와 디코더가 돌려준 코드를 원래 롬의 메시지와 견준다(lua/dq4msgbank.lua). 장면은 성 앞(36/00)의 빈 곳에 「はなす」
(대화 명령)와, 탑 위 보스(39/04)에게 말을 걸어 전투로 들어가는 대사(dq4battlemsgcheck 의 보스 장면)다. 전투 안의 메시지는
따로 둔 전투 색인(24:8C60)을 읽어 이 훅을 지나지 않는다. 시험 롬은 메시지 바이트와 색인만 다르고 코드는 같아 원래 롬의
상태를 그대로 불러도 된다.

  MESENCE=… LIBDIR=… python sfc/dq4/tools/dq4msgbankcheck.py --rom work/ch1/dq4-ch1-full.sfc --out work/msgbank
형식은 sfc/dq4/docs/dq4-menu-format.md 「다른 메시지 더하기」.
"""
import argparse
import json
import os
import shutil
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[1] / 'dq5' / 'tools')]

import dq4battlemsgcheck as bmc  # noqa: E402
import dq4freshstate  # noqa: E402
import dq4menumsg as mm  # noqa: E402
import dq4readset  # noqa: E402
from dq5exitcheck import dp86_allowed, warp_exit  # noqa: E402
from dq5hangul import DECODER, DECODER_END, decode_check  # noqa: E402
from dq5map import Rom, lorom  # noqa: E402
from dq5textwrite import base_package, index_cpu, index_table, relocated  # noqa: E402

LUA = HERE / 'lua' / 'dq4msgbank.lua'
WARP_LUA = HERE.parents[1] / 'dq5' / 'tools' / 'lua' / 'dq5warp.lua'
SCENES = {
    'field': {'TO': '36/00,38,25', 'TEST': 'idle:20,a:4,wait:20,a:4,wait:400', 'MAXF': '1200', 'SETTLE': '120'},
    'boss': {'TO': bmc.BOSS_CELL, 'SET': bmc.HERO, 'LATESET': bmc.RNG, 'SETTLE': '120', 'MAXF': '1500',
             'TEST': 'up:20,idle:10,a:4,wait:40,' + ','.join(['a:4,wait:30'] * 30)},
}
# (묶음 번호, 띄울 메시지). 차례대로 뱅크 55 안·55→56 걸침·뱅크 56 안에 둔다. 띄울 메시지는 창에서 끝까지 찍히는 것으로
# 고른다(dq4-josa-format.md 의 바꿔 끼우기 실측)
PLACES = ((0x05, 0x057), (0x18, 0x18A), (0x1C, 0x1CD))
FOURTH, FOURTH_END, BORDER = 0x558000, 0x570000, 0x568000
ALIGN = 0x100
# (장면, 띄울 메시지)
CASES = (('field', 0x057), ('field', 0x18A), ('field', 0x1CD), ('boss', 0x18A))


def group_bytes(data, banks, index, group):
    """묶음의 (첫 바이트 파일 위치, 끝 파일 위치, 첫 비트)."""
    v = Rom(data).u24(index + 3 * group)
    decoder = Rom(data).u24(DECODER + 1)
    _, end = decode_check(data, decoder=decoder, bank_mask=banks, with_end=True, index=index + 3 * group, count=16)
    return lorom(index_cpu(v, banks)), lorom(end), v & 7


def places(data, sizes):
    """시험 묶음 셋의 파일 위치. 넷째 자리(55:8000~56:FFFF)에 이미 놓인 메시지(0 아닌 마지막 바이트) 뒤에서: 첫째는 뱅크 55,
    둘째는 가운데가 56:8000 에 오게(걸침), 셋째는 뱅크 56. 자리가 모자라면 멈춘다(메시지가 넷째 자리를 그만큼 채움)."""
    lo, hi, border = lorom(FOURTH), lorom(FOURTH_END - 1) + 1, lorom(BORDER)
    used = next((o + 1 for o in range(hi - 1, lo - 1, -1) if data[o]), lo)
    up = lambda o: -(-o // ALIGN) * ALIGN  # noqa: E731
    first = up(used)
    cross = border - sizes[1] // 2
    third = up(cross + sizes[1])
    if first + sizes[0] > cross or not first < border or third + sizes[2] > hi:
        raise ValueError(f'넷째 메시지 자리에 시험 묶음을 둘 빈 곳이 모자람(메시지가 {used:06X} 까지, 묶음 {list(sizes)})')
    return first, cross, third


def test_rom(data):
    """(시험 롬, 묶음 목록). 묶음은 {'group','swap','bank','cross','expected'}."""
    _, banks = relocated(data)
    if isinstance(banks, int):
        raise ValueError('표 꼴 색인 훅이 아닌 롬')
    index, total = index_table(data, banks)
    messages = base_package(data)[0]
    out = bytearray(data)
    cases = []
    spans = [group_bytes(data, banks, index, group) for group, _ in PLACES]
    spots = places(data, [end - start for start, end, _ in spans])
    for k, ((group, swap), (start, end, bit), o) in enumerate(zip(PLACES, spans, spots)):
        chunk = data[start:end]
        if k == 1 and not o < lorom(BORDER) < o + len(chunk):
            raise ValueError('걸치게 둘 묶음이 뱅크 경계를 넘지 않음')
        if any(out[o:o + len(chunk)]):
            raise ValueError(f'{o:06X}~ 가 비어 있지 않음')
        out[o:o + len(chunk)] = chunk
        p = lorom(index) + 3 * group
        out[p:p + 3] = mm.index_entry(o, bit)
        cases.append({'group': group, 'swap': swap, 'bank': o // 0x8000, 'cross': k == 1, 'at': o,
                      'expected': [c for m in range(group * 16, swap + 1) for c in messages[m]]})
    again = base_package(bytes(out))[0]
    if again != messages:
        raise ValueError('옮긴 시험 롬의 메시지가 원래와 다름(파이썬 풀이)')
    return bytes(out), cases


def run(mesence, libdir, rom, state, out, case, ret, scene='field'):
    out.mkdir(parents=True)
    env = {k: v for k, v in os.environ.items() if k not in ('POKE', 'ROMPATCH', 'BATTLE', 'FIELD', 'SET', 'LATESET')}
    env.update(SCENES[scene], LIBDIR=str(libdir), STATE=str(state), SHOT_DIR=str(out), DRIVER=str(WARP_LUA),
               WARPEXIT=f'{warp_exit(rom):X}', DP86OK=dp86_allowed(rom), SWAP=f'{case["swap"]:03X}', RETURN_PC=ret,
               CODES=str(len(case['expected'])))
    dq4readset.run(mesence, rom, LUA, out, env, timeout=600, accept=dq4readset.warp_finished)
    path = out / 'decoded.txt'
    lines = path.read_text().split() if path.exists() else []
    stream = int(lines[0].split('=')[1], 16) if lines and lines[0].startswith('stream=') else None
    codes = [int(x, 16) for x in lines[1:]]
    return {'scene': scene, 'group': f'{case["group"]:02X}', 'swap': f'{case["swap"]:03X}', 'cross': case['cross'],
            'stream': None if stream is None else f'{stream:06X}', 'bank_ok': stream is not None and stream >> 16 ==
            case['bank'], 'codes': len(codes), 'expected': len(case['expected']),
            'codes_ok': codes == case['expected']}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--rom', required=True, type=Path)
    dq4freshstate.add_argument(ap)
    ap.add_argument('--out', required=True, type=Path)
    ap.add_argument('--mesence', default=os.environ.get('MESENCE'))
    args = ap.parse_args()
    if not args.mesence or not os.environ.get('LIBDIR'):
        raise SystemExit('MESENCE 와 LIBDIR 을 주세요')
    rom, out = args.rom.resolve(), args.out.resolve()
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    data = rom.read_bytes()
    moved, cases = test_rom(data)
    test = out / 'msgbank.sfc'
    test.write_bytes(moved)
    state = dq4freshstate.resolve(args.state, args.mesence, rom, out / 'start')
    decoder, _ = relocated(data)
    ret = f'{decoder + DECODER_END - DECODER - 1:06X}'
    by_swap = {c['swap']: c for c in cases}
    with ThreadPoolExecutor(len(CASES)) as ex:
        results = list(ex.map(lambda k: run(Path(args.mesence), Path(os.environ['LIBDIR']), test, state,
                                            out / f'{CASES[k][0]}-{CASES[k][1]:03X}', by_swap[CASES[k][1]], ret,
                                            CASES[k][0]), range(len(CASES))))
    ok = all(r['bank_ok'] and r['codes_ok'] for r in results) and any(r['cross'] for r in results)
    report = {'status': 'passed' if ok else 'failed', 'cases': results}
    (out / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=1))
    print(json.dumps(report, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
