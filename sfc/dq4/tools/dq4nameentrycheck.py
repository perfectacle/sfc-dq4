"""MesenCE 로 이름 조합·삭제·Y 완료·새 게임 저장을 확인한다.

ASAR 빌드의 DQ4_NAMEENTRY_SYMBOLS 파일과 결과 롬을 받는다. 커서 위치만 WRAM 에 지정하고,
A/B/Y 는 실제 컨트롤러 입력으로 보낸다. 각 사례 사이에는 조합 상태를 비운다.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess

import dq4nameentry as ne

HERE = Path(__file__).resolve().parent
CASES = [
    ('<', ''), ('!', ''),
    ('ㄱㅏㅂㅅㅏ', '갑사'), ('ㄱㅏㅂㅅㅏ<', '갑ㅅ'), ('ㄱㅏㅂㅅㅏ<<', '갑'),
    ('ㄱㅗㅏㄴ<', '과'), ('ㄱㅗㅏㄴ<<', '고'), ('ㄱㅗㅏㄴ<<<', 'ㄱ'), ('ㄱㅗㅏㄴ<<<<', ''),
    ('ㄸㅑ', 'ㄸ'), ('ㄸㅑ<', ''), ('ㄱㅏㄴㅏㄷㅏㄹㅏㄱㅏ', '가나다락'),
    ('ㄹㅏㅇㅣㅇㅏㄴ', '라이안'),
]


def lua_array(values):
    return '{' + ','.join(str(v) for v in values) + '}'


def config(path, symbols):
    labels = {}
    for line in Path(symbols).read_text().splitlines():
        if ':' not in line or ' ' not in line:
            continue
        address, name = line.split(' ', 1)
        try:
            labels[name] = int(address.replace(':', ''), 16)
        except ValueError:
            continue
    grid = [cell for row in ne.GRID for cell in row + [None] * (ne.ROW_CELLS - len(row))]
    lines = ['return {', f'loop={labels["NeLoop"]}, finish={labels["NeReturn"]},', 'cases={']
    for keys, expected in CASES:
        inputs = [-1 if c == '<' else -2 if c == '!' else grid.index(c) for c in keys]
        glyphs = [ne.GLYPHS.index(c) for c in expected]
        lines.append('{keys=' + lua_array(inputs) + ', expected=' + lua_array(glyphs)
                     + ', label=' + json.dumps(keys + ' → ' + expected, ensure_ascii=False) + '},')
    lines += ['},', 'initials=' + lua_array(ne.JAMO.index(c) for c in ne.CHO) + ',',
              'medials=' + lua_array(ne.JAMO.index(c) for c in ne.JUNG) + ',', 'syllables={']
    lines += [f'[{ord(c) - 0xAC00}]={i + len(ne.JAMO)},' for i, c in enumerate(ne.KS)]
    encoded = b''.join(ne.code_bytes(ne.GLYPHS.index(c)) for c in CASES[-1][1])
    lines += ['},', 'encoded=' + lua_array(encoded) + ',}']
    path.write_text('\n'.join(lines))


def field_tiles(rom, name):
    out = bytearray(256)
    for i, char in enumerate(name.ljust(ne.MAX_CHARS, '＊')):
        glyph = ne.GLYPHS.index(char)
        offset = (ne.GLYPH_BANK + glyph // 1024) * 0x8000 + glyph % 1024 * 32
        raw = rom[offset:offset + 32]
        for col in range(2):
            for row in range(16):
                at = (128 if row >= 8 else 0) + i * 32 + col * 16 + row % 8 * 2
                out[at:at + 2] = bytes((raw[col * 16 + row], 255))
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rom', type=Path, required=True)
    parser.add_argument('--symbols', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    mesence = os.environ.get('MESENCE')
    if not mesence:
        parser.error('MESENCE 에 MesenCE 실행 파일을 주세요')
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    result = out / 'composition.txt'
    if result.exists():
        parser.error('--out 은 이전 검사 결과가 없는 폴더를 주세요')
    probe_rom = out / ('name-entry-' + out.name + '.sfc')
    shutil.copyfile(args.rom, probe_rom)
    cfg = out / 'cases.lua'
    config(cfg, args.symbols)
    env = dict(os.environ, SHOT_DIR=str(out), NAME_ENTRY_CASES=str(cfg))
    if not env.get('LIBDIR'):
        env['LIBDIR'] = subprocess.check_output(['uv', 'run', '--locked', 'krpatch', 'sfc', 'lua'], text=True).strip()
    subprocess.run([mesence, '--testrunner', str(probe_rom), str(HERE / 'lua/dq4nameentrycheck.lua')],
                   env=env, check=True, timeout=180)
    report = result.read_text()
    print(report, end='')
    if 'FAIL' in report or 'TIMEOUT' in report or report.count('PASS') != len(CASES) + 2:
        raise SystemExit('이름 입력 실측 실패')
    vram = (out / 'tiles.bin').read_bytes()
    actual = vram[0x4F80:0x5000] + vram[0x5F80:0x6000]
    expected = field_tiles(args.rom.read_bytes(), CASES[-1][1])
    differences = sum(a != b for a, b in zip(actual, expected))
    print(f'이름 칸 VRAM: {len(actual)}바이트 중 {differences} 차이')
    if differences or len(actual) != 256:
        raise SystemExit('이름 칸 VRAM 불일치')


if __name__ == '__main__':
    main()
