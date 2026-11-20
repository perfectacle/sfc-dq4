"""팔기 목록 장면에서 창 타일맵·묶음 그림을 함께 보내는 WhWith 와 묶음 그림을 보내는 WhNmi 가 귀선 안에 들고, 주사선
문턱에 기대지 않는지 MesenCE 로 잰다. 형식은 sfc/dq4/docs/dq4-window-text-format.md 「창 타일맵과 그림을 한 NMI 에」.

장면은 dq4windowcheck 의 넘치는 팔기 목록 다섯(SCENES). lua/dq4whwithprobe.lua 가 줄마다 적은 것으로 장면마다 본다.

  붙잡음: WhWith 가 게임의 창 타일맵 요청을 붙잡거나(.wait) 놓은(.give) 일이 없어야 한다. 놓으면 타일맵만 먼저 가 목록
          줄이 비고, 붙잡으면 창이 한 프레임 늦다.
  여유:   WhWith 가 들어오자마자 잰 주사선이 !wh_with_line(WITH_LINE) 앞이고, 잰 직후 그 줄까지 남은 마스터 클록이
          MARGIN 이상. 문턱 바로 앞에서 재면 NMI 첫머리의 명령 몇 개로 붙잡음이 생긴다(NMI 첫머리에 명령을 더한 변이로 정한 값).
  끝 줄:  WhWith·WhNmi 가 건 DMA 가 모두 FIRST_LINE 줄 뒤에 시작해 VBLANK_END 줄 안에 끝난다. 끝은 시작 V·H 에 바이트마다
          8 클록을 더해 셈하고(DMA_CLOCKS), 창 타일맵 DMA 는 보낸 뒤 처음 그림 DMA 자리(.dma)에 닿는 줄로도 본다. 그 밖이면
          화면을 그리는 줄의 VRAM 쓰기는 버려진다(MesenCE·snes9x 실측).
  쓰임:   장면마다 WhWith 가 적어도 한 번 돈다(재지 못한 장면을 통과로 치지 않는다).

  MESENCE=... LIBDIR=... uv run --locked python sfc/dq4/tools/dq4whwithcheck.py --rom work/ch1/dq4-ch1.sfc \\
      --symbols work/wc/wn.sym --out 새폴더
  (wn.sym 은 dq4menupatch.py build 를 DQ4_WINDOWNAME_SYMBOLS 와 함께 돌려 만든다)
"""
import argparse
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

LUA = HERE / 'lua' / 'dq4whwithprobe.lua'
SCENES = ('sell-long-ch1', 'sell-long-ch2', 'sell-long-ch3', 'sell-shop-ch1', 'sell-equip-ch3')
WITH_LINE = 249             # dq4windowname.asm 의 !wh_with_line
LINE_CLOCKS = 1364          # 주사선 하나의 마스터 클록
MARGIN = LINE_CLOCKS        # 한 줄. NMI 첫머리에 약 2800 클록을 더한 변이도 2884 로 통과하고, 문턱을 245 로 둔 판은 414 로 실패
FIRST_LINE = 225
VBLANK_END = 261
DMA_CLOCKS = 8            # DMA 바이트 하나의 마스터 클록(채널 머리 몫은 줄 끝 여유로 봄)
EVENTS = {'meas': 'WhWith_meas', 'go': 'WhWith_go', 'wait': 'WhWith_wait', 'give': 'WhWith_give',
          'done': 'WhWith_done', 'tmend': 'WhWith_dma'}
# DMA 를 거는 코드: 이 심볼부터 다음 심볼 앞까지
RANGES = (('WhWith', 'WhXfer'), ('WhNmi', 'WqRunBytes'))


def parse(text):
    """{'meas': [(프레임, 줄, V, H)], 'dma': [(프레임, V, H, PC, 바이트)], 이름: [(프레임, V, H)]}"""
    out = {'meas': [], 'dma': []}
    for line in text.splitlines():
        p = line.split()
        if len(p) >= 5 and p[1] == 'meas':
            out['meas'].append((int(p[0]), int(p[2]), int(p[3]), int(p[4])))
        elif len(p) >= 6 and p[1] == 'dma':
            out['dma'].append((int(p[0]), int(p[2]), int(p[3]), int(p[4], 16), int(p[5])))
        elif len(p) >= 4:
            out.setdefault(p[1], []).append((int(p[0]), int(p[2]), int(p[3])))
    return out


def margin(v, h):
    """잰 직후(V, H)에서 WITH_LINE 줄 첫머리까지 남은 마스터 클록(이미 넘었으면 음수)."""
    return (WITH_LINE - v) * LINE_CLOCKS - h


def dma_end(v, h, n):
    """시작(V, H)에서 n 바이트 DMA 가 끝나는 줄."""
    return v + (h + n * DMA_CLOCKS) // LINE_CLOCKS


def judge(rec):
    """(실패 까닭 목록, 요약)."""
    bad = []
    meas = rec['meas']
    if not meas:
        bad.append('WhWith 가 돌지 않음')
    holds = sorted(rec.get('wait', []) + rec.get('give', []))
    if holds:
        bad.append(f'붙잡음 {len(holds)}번(첫 프레임 {holds[0][0]})')
    ends = []
    for f, v, h in rec.get('go', []):
        after = [e for e in rec.get('tmend', []) if e[0] == f and (e[1], e[2]) > (v, h)]
        ends.append((min(after)[1] if after else None, f))
    over = [(v, f) for v, f in ends if v is None or not FIRST_LINE <= v <= VBLANK_END]
    if over:
        bad.append(f'타일맵 DMA 가 귀선 밖에 끝남 {len(over)}번(첫 프레임 {over[0][1]} V {over[0][0]})')
    late = [(f, line) for f, line, v, h in meas if line >= WITH_LINE]
    if late:
        bad.append(f'문턱 뒤에서 잼 {len(late)}번(첫 프레임 {late[0][0]} 줄 {late[0][1]})')
    small = min((margin(v, h), f) for f, line, v, h in meas) if meas else None
    if small is not None and small[0] < MARGIN:
        bad.append(f'여유 {small[0]} < {MARGIN}(프레임 {small[1]})')
    out = [(f, v, end) for f, v, h, pc, n in rec['dma'] for end in [dma_end(v, h, n)]
           if v < FIRST_LINE or end > VBLANK_END]
    if out:
        bad.append(f'귀선 밖 DMA {len(out)}번(첫 프레임 {out[0][0]} V {out[0][1]} → {out[0][2]})')
    lines = [v for f, v, h, pc, n in rec['dma']]
    last = max((dma_end(v, h, n) for f, v, h, pc, n in rec['dma']), default=None)
    tm = [v for v, f in ends if v is not None]
    summary = (f'WhWith {len(meas)}번, 여유 최소 {small[0] if small else "-"}, 타일맵 끝 V {max(tm) if tm else "-"}, '
               f'DMA {len(lines)}번 시작 V {min(lines) if lines else "-"}~{max(lines) if lines else "-"} 끝 V {last}')
    return bad, summary


def probe_env(syms):
    ev = ','.join(f'{k}={syms[v]:06X}' for k, v in EVENTS.items())
    rng = ','.join(f'{syms[a]:06X}-{syms[b]:06X}' for a, b in RANGES)
    return {'WHEV': ev, 'WHRANGE': rng}


def run_scenes(rom_path, syms, out, mesence, libdir):
    import dq4windowcheck as wc
    rom = Path(rom_path).read_bytes()
    states = wc.make_states(mesence, Path(rom_path), rom, out / 'states')
    found = {s[0]: s for s in wc.scenes(states['shop'], states['shop'], states['shop'], states['battle'])}
    os.environ.update(probe_env(syms))
    saved = wc.PROBE
    wc.PROBE = LUA
    try:
        for name in SCENES:
            s = found[name]
            folder = out / name
            if folder.exists():
                continue
            end = max(s[5][-1], wc.EVERY.get(name, range(1))[-1])
            wc.run(mesence, libdir, Path(rom_path), rom, folder, s[:5] + (range(60, end + 1, 100),))
    finally:
        wc.PROBE = saved


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--rom', type=Path, required=True)
    ap.add_argument('--symbols', type=Path, required=True, help='dq4menupatch 가 쓴 wn.sym')
    ap.add_argument('--out', type=Path, required=True)
    a = ap.parse_args()
    import dq4windowcheck as wc
    syms = wc.symbols(a.symbols)
    a.out.mkdir(parents=True, exist_ok=True)
    run_scenes(a.rom, syms, a.out.resolve(), os.environ['MESENCE'], os.environ['LIBDIR'])
    failed = 0
    for name in SCENES:
        path = a.out / name / 'whwith.txt'
        rec = parse(path.read_text()) if path.exists() else {'meas': [], 'dma': []}
        bad, summary = judge(rec)
        print(f'{"FAIL" if bad else "PASS"} {name} {summary}' + (f'  {"; ".join(bad)}' if bad else ''))
        failed += bool(bad)
    if failed:
        print(f'{failed}개 장면 실패')
        sys.exit(1)


if __name__ == '__main__':
    main()
