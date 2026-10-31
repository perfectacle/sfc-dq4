"""MesenCE 로 보행 메시지의 주인공 이름(1012)이 한글 부호·가나 이름 모두 맞는 글자 코드가 되는지 검사한다.

선실 세이브스테이트에서 파파스에게 말을 걸고, 메시지 첫 코드를 1012 로 바꿔(lua/dq4namegamecheck.lua) 24:A7B6 이
쌓은 코드를 파이썬 기준과 견준다. 사례마다 롬 사본과 출력 폴더를 따로 둔다.

  MESENCE=... uv run --locked python sfc/dq4/tools/dq4namegamecheck.py --rom 롬 --state work/state/ship.mss --out 새폴더
"""
import argparse
import os
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[1] / 'dq5' / 'tools')]

import dq4mesen as mesen  # noqa: E402
import dq4namegame as ng  # noqa: E402
import dq4nameentry as ne  # noqa: E402
from dq5map import Rom  # noqa: E402
from dq5text import MARK_CODES, MARK_KEYS, STRING_CODES  # noqa: E402

PRE = 'b:4,wait:40,up:3,wait:20,a:4,wait:30,a:4,wait:200'
# (이름, 이름 바이트). 한글은 표시 있는 부호, 가나는 원래 1바이트 부호(84 xx 는 탁점).
CASES = [
    ('라이안', None), ('크리프트', None), ('ㄱ힝', None), ('땟땠', None),
    ('kana', bytes.fromhex('10101010')), ('dakuten', bytes.fromhex('14842918')),
    ('lone-tag', bytes.fromhex('1085')),            # 마지막 바이트가 표시면 원래 경로(깨진 저장 방어)
]


def name_bytes(name, raw):
    if raw is None:
        raw = b''.join(ne.code_bytes(ne.GLYPHS.index(ch)) for ch in name)
    return raw.ljust(8, b'\x01')


def expected(rom, name, raw):
    """24:A7B6 이 쌓을 코드(끝 FFFF 포함)."""
    if raw is None:
        return ng.message_codes(name) + [0xFFFF]
    out, i = [], 0
    while i < len(raw):
        b = raw[i]
        if b == 0x84:
            i += 1
            k = next(j for j in range(256) if rom.u8(MARK_KEYS + j) == raw[i])
            out.append(rom.u16(MARK_CODES + k * 2))
        else:
            out.append(rom.u16(STRING_CODES + b * 2))
        i += 1
    return out + [0xFFFF]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--rom', type=Path, required=True)
    ap.add_argument('--state', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    a = ap.parse_args()
    mesence = os.environ.get('MESENCE')
    if not mesence:
        ap.error('MESENCE 에 MesenCE 실행 파일을 주세요')
    out = a.out.resolve()
    if out.exists():
        ap.error('--out 은 아직 없는 폴더를 주세요')
    rom = Rom(a.rom.read_bytes())
    libdir = os.environ.get('LIBDIR') or subprocess.check_output(
        ['uv', 'run', '--locked', 'krpatch', 'sfc', 'lua'], text=True).strip()
    failed = 0
    for i, (name, raw) in enumerate(CASES):
        folder = out / f'case{i}'
        folder.mkdir(parents=True)
        data = name_bytes(name, raw)
        env = dict(os.environ, LIBDIR=libdir, SHOT_DIR=str(folder), STATE=str(a.state.resolve()), NAME=data.hex(),
                   PRE=PRE, SHOT='200', MAXF='220')
        mesen.run(mesence, a.rom, HERE / 'lua' / 'dq4namegamecheck.lua', folder=folder, tag='namegame', extra=(),
                  env=env, check=False, timeout=120, capture_output=True)
        got = (folder / 'codes.txt').read_text().split() if (folder / 'codes.txt').exists() else []
        want = [f'{c:04X}' for c in expected(rom, name, raw)]
        ok = got == want
        failed += not ok
        print(f'{"PASS" if ok else "FAIL"} {name} {data.hex(" ")} got={" ".join(got)} want={" ".join(want)}')
    if failed:
        raise SystemExit(f'{failed}개 사례 실패')


if __name__ == '__main__':
    main()
