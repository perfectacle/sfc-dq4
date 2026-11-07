"""FC DQ4 레벨업 실측: 장 시작 1레벨 기록의 경험치를 레벨 L 문턱으로 두고 スライム 한 전투로 올려 기록을 읽는다.

레벨업 난수 10:$A241(결과 $8A·$8B)을 메모리에서 LDA #$79 / STA $8A / LDA #0 / STA $8B / RTS 로 바꿔 R = 121 로
고정한다. 그러면 증가 = 곡선 증가분 × 121 / 121 이다(fc/dq4/docs/dq4-data-format.md 「레벨업」). 전투는
lua/guestai.lua 로 일으키고(조우 판정을 메모리에서 바꿈), 레벨업 글은 A 를 4 프레임마다 눌러 넘긴다. 레벨업 글이 길어
MesenCE testrunner 가 결과를 쓰기 전에 끝나지 않도록, 한 판에 한 사람만 일행($616A)에 두고 레벨·사람마다 따로 돌린다.

  MESENCE=… uv run --locked python fc/dq4/tools/dq4levelup.py --state work/state/dq4-ch2-start.mss \\
      --who 7,1,4 --set 627F=01 --levels 1,5,10,15,20 --out work/fclevelup

--set 은 출발 전에 쓸 것(dq4warp.sh SET). 2장 시작 기록이면 브라이·크리프트 합류 flag($627F bit0)를 켜 두어야 필드를
걸을 때 합류 사건이 걸리지 않는다. 출력은 레벨마다 그 레벨의 능력치·최대 HP·MP·
경험치·주문 비트(+1B~+1D)·소지품.
"""
import argparse
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parents[2]
sys.path.insert(0, str(TOOLS))

RECORD, RECORD_SIZE = 0x6001, 30
RNG = (0x10, 0xA241, bytes.fromhex('a979858aa900858b60'))
# 한 사람이 한 전투에 1 → 20 을 오르면 글이 약 1만 프레임이다(힘이 약한 ブライ 는 スライム 를 쓰러뜨리기까지 더 걸림).
# 셋이 함께 4만 5천 프레임을 주자 MesenCE testrunner 가 결과를 쓰기 전에 끝났다
FRAMES = {5: 5000, 10: 8000, 15: 12000, 20: 15000, 30: 22000}
# 레벨 바이트는 글보다 먼저 오르므로 레벨만으로는 다 올랐는지 모른다. 전투가 끝나 필드로 돌아오면 누르는 A 마다 이 글이
# 떴다(guestai.txt 의 msg). 이 글이 한 번이라도 떴으면 다 오른 것으로 본다
FIELD_MSG = '02F0'


def frames(level):
    return next(v for k, v in sorted(FRAMES.items()) if level <= k) if level <= max(FRAMES) else max(FRAMES.values())


def record(sram, who):
    r = sram[RECORD - 0x6000 + RECORD_SIZE * who:][:RECORD_SIZE]
    return {'level': r[5], 'str': r[6], 'agi': r[7], 'vit': r[8], 'int': r[9], 'luck': r[10],
            'max_hp': r[0xC] | r[0xD] << 8, 'max_mp': r[0xE] | r[0xF] << 8,
            'exp': int.from_bytes(r[0x10:0x13], 'little'), 'items': r[0x13:0x1B].hex(' '),
            'spells': r[0x1B:0x1E].hex(' ')}


def lua_dir():
    return subprocess.run(['uv', 'run', '--locked', 'krpatch', 'fc', 'lua'], capture_output=True, text=True,
                          check=True).stdout.strip()


def warp(state, out, sets):
    env = dict(os.environ, STATE=str(state), SET=';'.join(sets))
    subprocess.run(['sh', str(TOOLS / 'dq4warp.sh'), str(out), 'field', '0', 'A4', '32'], env=env, cwd=ROOT,
                   check=True, capture_output=True)
    return out / 'warp.mss'


def run(start, level, who, out, prg):
    import dq4data
    out.mkdir(parents=True, exist_ok=True)
    for f in out.glob('*'):
        f.unlink()
    exp = dq4data.curve(prg, who, 0, level)[0].to_bytes(3, 'little').hex()
    sets = [f'616A={0x80 | who:02X}000000', f'{RECORD + RECORD_SIZE * who + 0x10:04X}={exp}']
    bank, addr, code = RNG
    env = dict(os.environ, LIBDIR=lua_dir(), STATE=str(start), SHOT_DIR=str(out), MAXF=str(frames(level)),
               SET=';'.join(sets), PRG=f'{bank * 0x4000 + (addr & 0x3FFF):X}={code.hex()}', MON='00:1',
               A_EVERY='4', A_HOLD='2')
    subprocess.run([sys.executable, str(ROOT / 'sfc' / 'dq4' / 'tools' / 'dq4mesen.py'),
                    '--nes.ramPowerOnState=AllZeros', str(ROOT / 'rom' / 'dq4.nes'),
                    str(TOOLS / 'lua' / 'guestai.lua')], env=env, cwd=ROOT, capture_output=True)
    sram, log = out / 'end.sram', out / 'guestai.txt'
    if not sram.exists():
        return None
    r = record(sram.read_bytes(), who)
    r['done'] = any(line.endswith(f'msg {FIELD_MSG}') for line in log.read_text().splitlines())
    return r


def main():
    from kr_patch.fc import ines
    import dq4data
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--state', type=Path, required=True)
    ap.add_argument('--who', default='7,1,4', help='인물 번호(dq4data.PARTY), 쉼표로')
    ap.add_argument('--set', action='append', default=[], help='출발 전에 쓸 주소=바이트들')
    ap.add_argument('--levels', default='1,5,10,15,20')
    ap.add_argument('--out', type=Path, default=ROOT / 'work' / 'fclevelup')
    args = ap.parse_args()
    if not os.environ.get('MESENCE'):
        sys.exit('MESENCE 에 MesenCE 실행 파일 경로를 주세요')
    who = [int(v) for v in args.who.split(',')]
    prg = ines.prg((ROOT / 'rom' / 'dq4.nes').read_bytes())
    out = args.out.resolve()
    start = warp(args.state.resolve(), out / 'warp', args.set)
    jobs = [(lv, w) for lv in (int(v) for v in args.levels.split(',')) for w in who]
    with ThreadPoolExecutor(4) as pool:
        done = list(pool.map(lambda j: (*j, run(start, *j, out / f'L{j[0]}-{j[1]}', prg)), jobs))
    bad = 0
    for lv, w, r in done:
        if r is None:
            print(f'L{lv} {dq4data.PARTY[w]}: 결과 없음')
            bad += 1
            continue
        flag = '' if r['level'] == lv and r['done'] else f'  ← 레벨 {r["level"]}, 전투가 끝나지 않음(FRAMES 를 늘릴 것)'
        bad += bool(flag)
        print(f"L{lv:2d} {dq4data.PARTY[w]} ちから {r['str']} すばやさ {r['agi']} たいりょく {r['vit']} "
              f"かしこさ {r['int']} うんのよさ {r['luck']} 최대HP {r['max_hp']} 최대MP {r['max_mp']} "
              f"경험치 {r['exp']} 주문 {r['spells']} 소지품 {r['items']}{flag}")
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
