"""세트 팔레트 표(OBJ 팔레트 4~7)와 늘린 맵 팔레트 줄을 MesenCE에서 원본과 견준다.

02/06 의 밤 인물 둘을 낮으로 바꿔 주인공 위에 세운다(dq5npcrecord.py, 세트 04 = 6타일, 세트 84 = 8타일).
고친 롬은 dq5objpalette.py --at 으로 세트 04 를 OBJ 팔레트 5, 84 를 6, 주인공 82 를 7 로 두고, 팔레트 5·6·7 의 색을 바꾸고,
02/06 에 OBJ 팔레트 7 줄(0F)을 덮는 새 맵 팔레트 항목을 더하고, 04/06 의 기존 항목(13번, 줄 0B)의 색을 바꾼다.
두 롬에서 dq5gfxdump.lua 로 덤프해, CGRAM OBJ 줄이 그 롬에서 예측한 색인지, 인물 슬롯마다 그 세트 타일을 쓰는 OAM 이
세트 팔레트로 그려졌는지(dq5sprite.compare 와 슬롯별 셈) 본다. 출력은 --out 의 새 하위 폴더에 둔다.
  MESENCE=… python sfc/dq5/tools/dq5setpalettecheck.py rom/dq5.sfc --state work/state/ship.mss [--at 3B:8000]
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dq5sprite as S  # noqa: E402
from dq5map import Rom  # noqa: E402
from dq5objpalette import FORMAT  # noqa: E402
from dq5objpalettecheck import RECORDS, SCENES, DUMPF, run, tool  # noqa: E402

HERE = Path(__file__).resolve().parent
SETS = {0x04: 5, 0x84: 6, 0x82: 7}
MAP_ENTRY, NEW_LINE = 13, 0x0F


def lines(rom, scene):
    """그 맵을 불러온 뒤의 CGRAM OBJ 줄 0~7 예측: 04:96D6 위에 맵 팔레트 항목을 차례로(조건은 늘 참인 것만)."""
    want = [[rom.u16(S.OBJ_PALETTES + (p * 16 + i) * 2) for i in range(16)] for p in range(8)]
    bc, bd = scene >> 8, scene & 0xFF
    for e in S.map_palettes(rom):
        if e['bc'] == bc and e['bd'] in (bd, 0xFF) and e['flag'] == 0xFF and 8 <= e['line'] <= 15:
            want[e['line'] - 8] = e['colors']
    return want


def slot_palettes(rom, wram, oam):
    """인물 슬롯마다 {세트: {OAM 팔레트: 그 세트 타일을 쓰는 보이는 OBJ 수}}."""
    w16 = lambda a: wram[a] | wram[a + 1] << 8  # noqa: E731
    items = S.oam_groups(oam)
    out = {}
    for slot in range(min(wram[0x1983], 0x20)):
        g = wram[0x3220 + slot]
        if g >= S.GFX_COUNT:
            continue
        s = S.gfx_set(rom, g, wram[0x21B3])
        rec = S.set_record(rom, s)
        cells = [w16(w16(0x8000 + wram[0x3200 + slot]) + i * 2) for i in range(48)]
        base = (cells[0] & 0x1FF) - (rec['cells'][0] & 0x7F)
        seen = out.setdefault(f'{s:02X}', {})
        for it in items:
            if it and base <= it[2] < base + rec['tiles']:
                p = (it[3] >> 1) & 7
                seen[p] = seen.get(p, 0) + 1
    return out


def look(rom, dest, scene):
    want = lines(rom, scene)
    out = []
    for tag in DUMPF.split(','):
        name = f'f{int(tag):05d}'
        rd = lambda ext: (dest / f'{name}.{ext}').read_bytes()  # noqa: E731
        cgram = rd('cgram')
        got = [[cgram[256 + (p * 16 + i) * 2] | cgram[257 + (p * 16 + i) * 2] << 8 for i in range(16)] for p in range(8)]
        stats = {}
        S.compare(rom, rd('wram'), rd('vram'), rd('oam'), cgram, stats, False)
        out.append({'dump': name, 'cgram_lines_same': [got[p][1:] == want[p][1:] for p in range(8)],
                    'groups': stats.get('groups', 0), 'hits': stats.get('hits', 0),
                    'other_palette': stats.get('other_palette', 0),
                    'slots': slot_palettes(rom, rd('wram'), rd('oam'))})
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('rom', type=Path)
    ap.add_argument('--state', required=True, type=Path)
    ap.add_argument('--mesence', default=os.environ.get('MESENCE'))
    ap.add_argument('--at', default='3B:8000')
    ap.add_argument('--out', type=Path, default='work/setpalettecheck')
    args = ap.parse_args()
    if not args.mesence:
        ap.error('--mesence 또는 MESENCE가 필요함')
    try:
        original, state, mesence = args.rom.resolve(), args.state.resolve(), Path(args.mesence).resolve()
        for path in (original, state, mesence):
            if not path.is_file():
                raise ValueError(f'파일 없음: {path}')
        args.out.mkdir(parents=True, exist_ok=True)
        out = Path(tempfile.mkdtemp(prefix='run-', dir=args.out.resolve()))
        print(f'실행 출력: {out}', flush=True)
        base = Rom(original.read_bytes())
        entry = S.map_palettes(base)[MAP_ENTRY]
        if (entry['bc'], entry['bd'], entry['line']) != (4, 6, 0x0B):
            raise ValueError('맵 팔레트 13번이 04/06 줄 0B 가 아님')
        if any(e['bc'] == 2 and e['bd'] in (6, 0xFF) for e in S.map_palettes(base)):
            raise ValueError('02/06 을 덮는 원래 맵 팔레트 항목이 있음(예측이 틀어짐)')
        # 팔레트마다 다른 띠: 5 는 빨강 오름, 6 은 초록 오름, 7 은 파랑 오름. 02/06 의 새 줄은 7 의 거꾸로.
        band = lambda shift: [(i * 2) << shift | (31 - i * 2) << (10 - shift) for i in range(1, 16)]  # noqa: E731
        doc = {'format': FORMAT,
               'palettes': [{'palette': 5, 'colors': band(0)}, {'palette': 6, 'colors': band(5)},
                            {'palette': 7, 'colors': band(10)}],
               'map_palettes': [{'index': MAP_ENTRY, 'colors': [((c & 0x1F) << 10) | (c & 0x3E0) | (c >> 10)
                                                                for c in entry['colors'][1:]]}],
               'new_map_palettes': [{'map': '02/06', 'line': f'{NEW_LINE:02X}', 'colors': band(10)[::-1]}],
               'sets': [{'set': f'{s:02X}', 'palette': p} for s, p in SETS.items()]}
        (out / 'palette.json').write_text(json.dumps(doc, indent=1) + '\n', encoding='utf-8')
        (out / 'records.json').write_text(json.dumps(RECORDS, indent=1) + '\n', encoding='utf-8')
        tool('dq5objpalette.py', original, 'check', out / 'palette.json', '--at', args.at)
        tool('dq5objpalette.py', original, 'patch', out / 'palette.json', '-o', out / 'palette.dq5patch.json', '--at', args.at)
        tool('dq5npcrecord.py', original, 'patch', out / 'records.json', '-o', out / 'records.dq5patch.json')
        roms = {}
        for name, patches in (('original', [out / 'records.dq5patch.json']),
                              ('edited', [out / 'records.dq5patch.json', out / 'palette.dq5patch.json'])):
            roms[name] = out / f'{name}.sfc'
            tool('dq5build.py', original, 'build', *patches, '-o', roms[name], '--ips', out / f'{name}.ips')
        krlua = Path(subprocess.run(['krpatch', 'sfc', 'lua'], capture_output=True, text=True,
                                    check=True, timeout=30).stdout.strip())
        libdir = out / 'lib'
        shutil.copytree(krlua, libdir)
        shutil.copyfile(HERE / 'lua/dq5warp.lua', libdir / 'boot.lua')
        results = {}
        for name, rom in roms.items():
            built = Rom(rom.read_bytes())
            for scene, to, key in SCENES:
                results[f'{name}-{scene}'] = look(built, run(rom, f'{name}-{scene}', to, out, state, mesence, libdir), key)
        edited = Rom(roms['edited'].read_bytes())

        def every(case, test):
            return all(test(r) for r in results[case])

        def drawn(case, s, p):
            return every(case, lambda r: set(r['slots'].get(f'{s:02X}', {})) == {p})

        new_line = lines(edited, 0x0206)[NEW_LINE - 8]
        checks = {
            'cgram': all(every(case, lambda r: all(r['cgram_lines_same'])) for case in results),
            'oam': all(every(case, lambda r: r['groups'] == r['hits'] > 0 and r['other_palette'] == 0) for case in results),
            'original-palette': all(drawn('original-0206', s, S.set_record(base, s)['palette']) for s in SETS),
            'set-palette': all(drawn('edited-0206', s, p) for s, p in SETS.items()) and drawn('edited-0406', 0x82, 7),
            'new-line': new_line[1:] == doc['new_map_palettes'][0]['colors'] and new_line != lines(edited, 0x0406)[NEW_LINE - 8],
            'table': edited.u8(0x01996A) == 0x22 and S.map_palette_table(edited) != S.MAP_PALETTES,
        }
        (out / 'results.json').write_text(json.dumps({'results': results, 'checks': checks}, ensure_ascii=False,
                                                     indent=2) + '\n', encoding='utf-8')
        for case, rows in results.items():
            r = rows[-1]
            pals = ', '.join(f'{s} {"·".join(f"{p}×{n}" for p, n in sorted(v.items()))}' for s, v in sorted(r['slots'].items()))
            print(f'{case} {r["dump"]}: CGRAM OBJ 줄 0~7 예측과 같음 {sum(r["cgram_lines_same"])}/8, '
                  f'OAM 묶음 {r["hits"]}/{r["groups"]}, 슬롯 세트의 OAM 팔레트 {pals}')
        for key, ok in checks.items():
            print(f'{key}: {"통과" if ok else "불일치"}')
        if not all(checks.values()):
            raise ValueError('불일치: ' + ', '.join(k for k, ok in checks.items() if not ok))
        print(f'검사 {len(checks)}개 통과')
        return 0
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        print(f'오류: {error}', file=sys.stderr)
        if isinstance(error, subprocess.CalledProcessError) and error.stderr:
            print(error.stderr, file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
