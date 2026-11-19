"""메시지 캔버스 DMA·전송 목록 DMA 가 수직 귀선 안에 끝나는지 V 카운터로 잰다(MesenCE 헤드리스).

검사 롬 사본에 실험 훅을 건다: 게임의 두 DMA 시작(00:8EC5 캔버스 `LDA #$01 / STA $420B`, 00:8D4E 전송 목록
`LDA #$01 / STA.l $00420B`)을 JSL 로 바꿔, DMA 앞뒤에 $2137 로 V 를 붙잡아 $213D 로 읽고 7E:ABF6~ABFD 에 적는다
(시작 낮은·높은, 끝 높은·낮은 바이트 차례). 장면을 dq4windowcheck 출발 상태에서 돌리며 그 쓰기를 dq5msg.lua 의 WW 로
모은다. 화면은 239줄 모드라 1~239 를 그리고 240~261 이 귀선이다. 원본 DQ5 의 캔버스 DMA 는 244 에 시작해 0 에 끝난다
(귀선을 꽉 채움). 끝 V 가 1~239 이면 그 몫의 VRAM 쓰기는 버려진다(MesenCE·snes9x 도 그리는 줄의 VRAM 쓰기를 버림).

판정: 장면마다 DMA 끝 V 가 KNOWN 에 적은 줄(없으면 0)을 넘으면 실패. KNOWN 은 늘면 안 되는 남은 넘침이다.

  MESENCE=… LIBDIR=… ASAR=… uv run --locked python sfc/dq4/tools/dq4vblankcheck.py --rom work/ch1/dq4-ch1.sfc --out work/vblank
"""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[1] / 'dq5' / 'tools')]

import dq4windowcheck as wc  # noqa: E402

LOG = 0x7EABF6               # 8바이트: [캔버스 시작 lo hi][캔버스 끝 hi lo][목록 시작 lo hi][목록 끝 hi lo]
SITES = {0x008EC5: bytes.fromhex('a9018d0b42'), 0x008D4E: bytes.fromhex('a9018f0b4200')}
VBLANK = range(240, 262)

# 장면 → {DMA 종류: 넘어도 되는 끝 줄}. 늘면 실패, 고치면 줄인다. 남은 넘침과 까닭:
#   give-full 목록 1 — 「누구에게」 를 시작하는 두 지우기 항목 가운데 첫째(117칸 두 평면)가 원본처럼 귀선을 다 쓰는데,
#   게이트를 건너뛰어도 NMI 입구 판정 몇 명령(느린 롬)만큼 한 줄 늦게 시작한다
KNOWN = {
    'give-full': {'list': 1},
}

GIVE = ('wait:60,a:6,wait:60,right:4,wait:30,down:4,wait:30,a:6,wait:90,a:6,wait:150,a:6,wait:150,down:4,wait:30,a:6,'
        'wait:200,' + 'b:6,wait:90,' * 4)


def hook_asm(at):
    """실험 훅 asar 글. at = 빈 자리(SNES 주소)."""
    lines = ['lorom', f'org ${at:06X}', 'VA:', '    PHP', '    SEP #$20', '    JSR Lat',
             f'    STA.l ${LOG:06X}', '    XBA', f'    STA.l ${LOG + 1:06X}', '    LDA #$01', '    STA.l $00420B',
             '    JSR Lat', f'    STA.l ${LOG + 3:06X}', '    XBA', f'    STA.l ${LOG + 2:06X}', '    PLP', '    RTL',
             'VB:', '    PHP', '    SEP #$20', '    JSR Lat', f'    STA.l ${LOG + 4:06X}', '    XBA',
             f'    STA.l ${LOG + 5:06X}', '    LDA #$01', '    STA.l $00420B', '    JSR Lat', f'    STA.l ${LOG + 7:06X}',
             '    XBA', f'    STA.l ${LOG + 6:06X}', '    PLP', '    RTL',
             'Lat:', '    LDA.l $00213F', '    LDA.l $002137', '    LDA.l $00213D', '    XBA', '    LDA.l $00213D',
             '    AND #$01', '    XBA', '    RTS',
             'org $008EC5', '    JSL VA', '    NOP', 'org $008D4E', '    JSL VB', '    NOP', '    NOP']
    return '\n'.join(lines) + '\n'


def lorom(a):
    return ((a >> 16) & 0x7F) * 0x8000 + (a & 0x7FFF)


def free_spot(rom, size=0x80):
    """뱅크 00~3F 끝(FE00~FF7F) 가운데 한 가지 바이트(00 또는 FF)로만 찬 자리."""
    for bank in range(min(0x40, len(rom) // 0x8000)):
        o = lorom(bank << 16 | 0xFE00)
        seg = rom[o:o + size]
        if len(seg) == size and len(set(seg)) == 1 and seg[0] in (0x00, 0xFF):
            return bank << 16 | 0xFE00
    raise SystemExit('실험 훅을 둘 빈 자리가 없음')


def patch(rom_path, out, asar):
    rom = rom_path.read_bytes()
    for a, orig in SITES.items():
        if rom[lorom(a):lorom(a) + len(orig)] != orig:
            raise SystemExit(f'{a:06X} 가 원래 DMA 바이트가 아님: {rom[lorom(a):lorom(a) + len(orig)].hex()}')
    at = free_spot(rom)
    with tempfile.TemporaryDirectory() as t:
        src = Path(t) / 'vc.asm'
        src.write_text(hook_asm(at))
        dst = out / 'vblank.sfc'
        dst.write_bytes(rom)
        r = subprocess.run([asar, '--no-title-check', '--fix-checksum=off', str(src), str(dst)],
                           capture_output=True, text=True)
        if r.returncode:
            raise SystemExit(f'asar: {r.stdout}{r.stderr}')
    return dst


def events(text):
    """[(프레임, 'canvas'|'list', 시작 V, 끝 V)] msg.txt 의 WW 쓰기에서. 끝 낮은 바이트가 마지막에 쓰인다."""
    cur, out = {}, []
    for line in text.splitlines():
        m = re.match(r'(\d+) W 7EABF([6-9A-D])=([0-9A-F]{2})', line)
        if not m:
            continue
        f, k, v = int(m[1]), int(m[2], 16) - 6, int(m[3], 16)
        cur[k] = v
        if k == 3:
            out.append((f, 'canvas', cur.get(1, 0) << 8 | cur.get(0, 0), cur.get(2, 0) << 8 | v))
        elif k == 7:
            out.append((f, 'list', cur.get(5, 0) << 8 | cur.get(4, 0), cur.get(6, 0) << 8 | v))
    return out


def late(end):
    """끝 V 가 귀선 뒤로 넘은 줄 수(귀선 안이면 0, 0 줄은 그리지 않는 줄이라 넘지 않음)."""
    return 0 if end in VBLANK or end == 0 else end


def judge(name, evs):
    """[문제 글] 장면 하나."""
    allow = KNOWN.get(name, {})
    problems = []
    for kind in ('canvas', 'list'):
        worst = max((late(e) for _, k, _, e in evs if k == kind), default=0)
        if worst > allow.get(kind, 0):
            frames = [f for f, k, _, e in evs if k == kind and late(e) == worst]
            problems.append(f'{name} {kind} DMA 끝 V {worst}(허용 {allow.get(kind, 0)}), 프레임 {frames[:5]}')
    return problems


def scenes(states):
    shop = states['shop']
    known = {s[0]: s for s in wc.scenes(shop, shop, shop, states['battle'])}
    out = [known['shopwho'], known['talk02-full'], known['partyitems']]
    bag = ';'.join(f'7E{0x2056 + i:04X}={b:02X}' for i, b in enumerate(wc.FULL_BAG))
    out.append(('give-full', shop, bag, '', GIVE, range(60, 1400)))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--rom', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--asar', default=os.environ.get('ASAR', 'asar'))
    ap.add_argument('--only', help='이 장면만(쉼표로)')
    a = ap.parse_args()
    mesence = os.environ.get('MESENCE')
    libdir = os.environ.get('LIBDIR') or subprocess.check_output(['uv', 'run', '--locked', 'krpatch', 'sfc', 'lua'],
                                                                  text=True).strip()
    if not mesence:
        ap.error('MESENCE 를 주세요')
    out = a.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    rom_path = patch(a.rom, out, a.asar)
    rom = rom_path.read_bytes()
    st = wc.make_states(mesence, rom_path, rom, out / 'states')
    todo = scenes(st)
    if a.only:
        todo = [s for s in todo if s[0] in a.only.split(',')]
    os.environ['WW'] = ','.join(f'{LOG + k:06X}' for k in range(8))
    report, problems = {}, []
    for s in todo:
        # 덤프는 끝 두 프레임만(판정은 WW 쓰기로)
        scene = s[:5] + (range(s[5][-1] - 1, s[5][-1] + 1),)
        folder = out / s[0]
        wc.run(mesence, libdir, rom_path, rom, folder, scene)
        evs = events((folder / 'msg.txt').read_text())
        report[s[0]] = evs
        p = judge(s[0], evs)
        problems += p
        worst = {k: max((late(e) for _, kk, _, e in evs if kk == k), default=0) for k in ('canvas', 'list')}
        print(f"{'FAIL' if p else 'PASS'} {s[0]} DMA {len(evs)}번, 넘친 끝 V 캔버스 {worst['canvas']} 목록 {worst['list']}",
              flush=True)
    (out / 'vblank.json').write_text(json.dumps(report), encoding='utf-8')
    if problems:
        raise SystemExit('\n'.join(problems))


if __name__ == '__main__':
    main()
