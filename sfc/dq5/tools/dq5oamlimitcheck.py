"""필드 OAM·슬롯 칸 목록·필드 물체 슬롯의 한도와 실내 X·Y 128 을 MesenCE에서 잰다(dq5objlayout.py 의 OAM·필드 슬롯 검사 근거).

장면은 모두 dq5warp.lua 로 내려 가만히 두거나 조금 걷고 600프레임 무렵 덤프한다(lua/dq5rangewatch.lua → dq5gfxdump.lua).
  oam: 양탄자(필드 (328,27), LATESET=1954=80)를 1프레임으로 하고 부분 1 을 12x9, 부분 3 을 3x1·4x1·12x1 로 늘려 OBJ 가
    128·129·137장이 되게 한다(어린 주인공 8장 포함). 7E:1993(00:EC1F 가 남기는 OBJ 수)·보이는 OBJ·크기 비트가 켜진 OBJ 를
    세고, 7E:0500~05FF 쓰기를 모아 128장을 넘은 OBJ 가 높은 표(0500~051F)와 그 뒤(0520~)에 쓰였는지 본다. 129·137 은
    dq5objlayout.py 가 거부하므로 OAM 검사를 늦춰 만든다.
  line: 부분 1 을 18x4, 부분 3 을 18x2 로 해 한 줄에 OBJ 가 32장을 넘게 한다. 부분 3 은 색 연산 그림자(팔레트 5)라 화면과
    견줄 수 없어 01:BDD7 의 LDX #$0A00 을 0000 으로(ROMPATCH) 팔레트 0 으로 그린다. 줄마다 OAM 에 걸친 수, PPU 의
    rangeOver, 넘친 줄에서 화면에 안 나온 OBJ 가 OAM 번호가 큰 쪽인지 본다.
  cells: 9프레임 7x2·3x3·7x2(칸 1,332개)의 칸 표를 롬 밖 30:8000 에 두어(롬을 2MB 로) 걷고 A 로 창을 열었다 닫는 동안,
    슬롯 칸 목록이 칸 표와 같은지와 7E:8060~9FFF 에 쓴 코드를 본다.
  vflip: 天空城 그림자(81-2)를 4x2 → 4x4 로 하고 아래 세 줄을 상하 반전(12칸, 원래 표 8칸보다 김)해 표가 옮겨지는지,
    슬롯 9 칸 목록의 상하 반전 비트와 OAM 이 그대로인지(필드 (310,60), LATESET=1954=81).
  field: 어른 시절(ADULT=1, $1948 = 2)로 필드 (328,27)에 내려 세계 0 물체 11개가 슬롯 8~12 에 놓이는지, 물체를 13·14개
    더해 1983 = 20·21 일 때 주인공 슬롯이 그대로인지, 양탄자에 타면 슬롯 8·9 의 물체가 탈것 부분으로 바뀌는지 본다.
    14개는 dq5objlayout.py 가 거부하므로 필드 슬롯 검사를 끈 채 만든다.
  edge: 폭 128 인 실내 16/00 의 (126,40)·(127,42)·(128,44)·(129,46)에 1x1 물체를 두고 (124,42)에 서서, 128·129 도 그 칸에
    놓여 OAM 에 나오는지 본다.
  MESENCE=… python sfc/dq5/tools/dq5oamlimitcheck.py rom/dq5.sfc --state work/state/ship.mss
"""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest import mock

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dq5objlayout as L  # noqa: E402
import dq5sprite as S  # noqa: E402
from dq5map import Rom  # noqa: E402
from dq5objlayoutcheck import screen_match, w16  # noqa: E402

HERE = Path(__file__).resolve().parent
DUMP = 600
CARPET = {'FIELD': '328,27', 'LATESET': '1954=80'}
OAM_ROMS = {'oam128': (3, 1), 'oam129': (4, 1), 'oam137': (12, 1)}
EDGE = [(126, 40), (127, 42), (128, 44), (129, 46)]
EDGE_HERO = (124, 42)
FIELD_EXTRA = {'field20': 13, 'field21': 14}


def carpet_doc(sizes, frames=1):
    """양탄자 부분마다 크기·프레임 수만 바꾼 문서. 칸은 타일 0~2E 를 차례로 돌려 쓴다(양탄자 타일 47개)."""
    out = []
    for part, (cols, rows) in sizes.items():
        grid = lambda k: [' '.join(f'{(k * 7 + r * cols + c) % 47:02x}' for c in range(cols))  # noqa: E731
                          for r in range(rows)]
        out.append({'part': part, 'size': f'{cols}x{rows}', 'frames': frames,
                    'cells': {f'{d}{f}': grid(k) for k, d in enumerate(L.DIRS) for f in range(frames)}})
    return {'format': L.FORMAT, 'vehicles': out}


def build(rom, doc, path, vehicle_at=None, at=None, guard=True):
    """문서를 빌드해 path 에 쓴다. guard 가 거짓이면 OAM·슬롯 검사를 늦춰 넘친 롬을 만든다."""
    if guard:
        manifest = L.patch(rom, doc, at, vehicle_at)
    else:
        with mock.patch.object(L, 'OAM_LIMIT', 0x400), mock.patch.object(L, 'check_slots'):
            manifest = L.patch(rom, doc, at, vehicle_at)
    path.write_bytes(L.built(rom, manifest).d)
    return path


def rejected(rom, doc, vehicle_at=None, at=None):
    try:
        L.patch(rom, doc, at, vehicle_at)
    except ValueError as error:
        return str(error)
    return None


def run(rom, dest, extra, state, mesence, libdir):
    dest.mkdir()
    env = {k: v for k, v in os.environ.items()
           if k not in ('ADULT', 'ANYWHERE', 'BATTLE', 'FIELD', 'GROUP', 'LATESET', 'PARTY', 'POKE', 'ROMPATCH', 'TO',
                        'SAVE', 'SET', 'WAGON', 'EVERY', 'FROM', 'WATCHR', 'DUMPF')}
    env.update({'LIBDIR': str(libdir), 'STATE': str(state), 'SHOT_DIR': str(dest), 'MAXF': '1000', 'SETTLE': '120',
                'TEST': 'wait:500', 'DUMPF': f'{DUMP},{DUMP + 1}', 'WATCHR': '7E0500-7E05FF',
                'NEXT': str(HERE / 'lua' / 'dq5gfxdump.lua')} | extra)
    with (dest / 'mesen.log').open('w', encoding='utf-8') as log:
        subprocess.run([str(mesence), '--testrunner', str(rom), str(HERE / 'lua' / 'dq5rangewatch.lua'),
                        '--Snes.DisableFrameSkipping=true'], env=env, stdout=log, stderr=subprocess.STDOUT,
                       check=True, timeout=300)
    d = {k: (dest / f'f{DUMP:05d}.{k}').read_bytes() for k in ('wram', 'vram', 'oam', 'cgram')}
    d['png'] = Image.open(dest / f'f{DUMP + 1:05d}.png').convert('RGB')
    d['ppu'] = dict(line.split('=', 1) for line in (dest / f'f{DUMP:05d}.ppu.txt').read_text().split())
    d['rw'] = [line.split() for line in (dest / 'rw.txt').read_text().splitlines()]
    return d


def oam(d):
    """OAM 128장 → (번호, X 9비트, Y, 타일, 속성, 큰 크기)."""
    o = d['oam']
    out = []
    for i in range(128):
        x, y, t, a = o[i * 4:i * 4 + 4]
        h = o[512 + i // 4] >> (i % 4) * 2 & 3
        out.append((i, x | (h & 1) << 8, y, t | (a & 1) << 8, a, bool(h & 2)))
    return out


def oam_stats(d):
    ents = oam(d)
    shown = [e for e in ents if e[2] < 0xE0 and e[1] < 0x100]
    # rw.txt 줄: 종류 PC 처음 마지막 횟수 낮은주소 높은주소. 높은 표 비트는 00:EDC3 이 0500 + OBJ 번호 / 4 에 쓴다.
    writes = [r for r in d['rw'] if r[0] == 'w']
    return {'1993': d['wram'][0x1993], 'visible': len(shown), 'big': sum(e[5] for e in ents),
            'high': max(int(r[6], 16) & 0xFFFF for r in writes),
            'writers': sorted(f'{r[1]} {int(r[5], 16) & 0xFFFF:04X}~{int(r[6], 16) & 0xFFFF:04X}' for r in writes),
            'rider': [e[0] for e in shown if e[3] < 0x180]}


def line_stats(d):
    """한 줄에 걸친 OAM 수가 가장 많은 줄과, 그 8줄에 걸친 팔레트 0 OBJ 가운데 화면에 안 나온 것."""
    items = S.oam_groups(d['oam'])
    band = {}
    for i, it in enumerate(items):
        if it and -8 < it[0] < 256:
            for y in range(it[1], it[1] + 8):
                band.setdefault(y, []).append(i)
    top = max(band, key=lambda y: len(band[y]))
    shown, hidden = [], []
    for i in band[top]:
        same, total = screen_match(d, [items[i]], [items[j] for j in range(i) if items[j]])
        if total:
            (shown if same == total else hidden).append(i)
    return {'line': top, 'count': len(band[top]), 'range_over': d['ppu'].get('ppu.rangeOver') == 'true',
            'shown': shown, 'hidden': hidden}


def slot_cells(w, slot, count):
    base = w16(w, 0x8000 + w[0x3200 + slot])
    return base, [w16(w, base + i * 2) for i in range(count)]


def cell_words(rom, name, attr):
    p = L.vehicle_part(rom, name)
    cells = [0x180 + (c & 0x7F) | (0x4000 if c & 0x80 else 0) | attr
             for c in (rom.u8(p['table'] + i) for i in range(p['copied']))]
    return [c | (0x8000 if i in p['vflip'] else 0) for i, c in enumerate(cells)]


def slots(w, first, end):
    return {s: (w[0x3220 + s], w[0x34E0 + s], w[0x3500 + s], w[0x3040 + s] << 8 | w[0x3020 + s],
                w[0x30A0 + s] << 8 | w[0x3080 + s]) for s in range(first, end)}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('rom', type=Path)
    ap.add_argument('--state', required=True, type=Path)
    ap.add_argument('--mesence', default=os.environ.get('MESENCE'))
    ap.add_argument('--out', type=Path, default='work/oamlimitcheck')
    ap.add_argument('--jobs', type=int, default=4)
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
        rom = Rom(original.read_bytes())
        checks = {}

        oam_docs = {k: carpet_doc({'80-1': (12, 9), '80-2': (3, 3), '80-3': v}) for k, v in OAM_ROMS.items()}
        checks['tool-oam'] = rejected(rom, oam_docs['oam128'], 0x0BFBB0) is None and \
            'OAM' in (rejected(rom, oam_docs['oam129'], 0x0BFBB0) or '')
        line_doc = carpet_doc({'80-1': (18, 4), '80-2': (3, 3), '80-3': (18, 2)})
        cells_doc = carpet_doc({'80-1': (7, 2), '80-2': (3, 3), '80-3': (7, 2)}, frames=9)
        vflip_doc = {'format': L.FORMAT, 'vehicles': [{'part': '81-2', 'size': '4x4', 'cells': {
            'all': ['10 11 h11 h10'] + ['v10 v11 hv11 hv10'] * 3}}]}
        base_objects = L.dump(rom)['objects']
        field_docs = {k: {'format': L.FORMAT, 'objects': base_objects + [
            {'map': 'field0', 'x': 40 + 2 * i, 'y': 128, 'cells': ['42']} for i in range(n)]}
            for k, n in FIELD_EXTRA.items()}
        checks['tool-field'] = rejected(rom, field_docs['field20'], at=0x16FE10) is None and \
            'field0' in (rejected(rom, field_docs['field21'], at=0x16FE10) or '')
        edge_doc = {'format': L.FORMAT, 'objects': base_objects + [
            {'map': '16/00', 'x': x, 'y': y, 'cells': ['00']} for x, y in EDGE]}

        roms = {k: build(rom, doc, out / f'{k}.sfc', 0x0BFBB0, guard=False) for k, doc in oam_docs.items()}
        roms['line'] = build(rom, line_doc, out / 'line.sfc', 0x0BFBB0)
        roms['cells'] = build(rom, cells_doc, out / 'cells.sfc', 0x308000)
        roms['vflip'] = build(rom, vflip_doc, out / 'vflip.sfc', 0x04FEE0)
        for k, doc in field_docs.items():
            roms[k] = build(rom, doc, out / f'{k}.sfc', at=0x16FE10, guard=False)
        roms['edge'] = build(rom, edge_doc, out / 'edge.sfc', at=0x16FE10)

        krlua = Path(subprocess.run(['krpatch', 'sfc', 'lua'], capture_output=True, text=True,
                                    check=True, timeout=30).stdout.strip())
        libdir = out / 'lib'
        shutil.copytree(krlua, libdir)
        shutil.copyfile(HERE / 'lua/dq5warp.lua', libdir / 'boot.lua')
        adult = {'ADULT': '1', 'FIELD': '328,27'}
        jobs = {
            'carpet': (original, CARPET),
            **{k: (roms[k], CARPET) for k in OAM_ROMS},
            'line': (roms['line'], CARPET | {'ROMPATCH': 'BDD8=00'}),
            'carpet-line': (original, CARPET | {'ROMPATCH': 'BDD8=00'}),
            'cells': (roms['cells'], CARPET | {'TEST': 'wait:60,a:4,wait:60,b:4,wait:60,left:120,up:120',
                                               'WATCHR': '7E8060-7E9FFF'}),
            'vflip': (roms['vflip'], {'FIELD': '310,60', 'LATESET': '1954=81'}),
            'field': (original, adult),
            'field-carpet': (original, adult | {'LATESET': '1954=80'}),
            **{k: (roms[k], adult) for k in FIELD_EXTRA},
            'edge': (roms['edge'], {'TO': '16/00,{},{}'.format(*EDGE_HERO)}),
        }
        with ThreadPoolExecutor(args.jobs) as pool:
            futures = {k: pool.submit(run, path, out / k, extra, state, mesence, libdir)
                       for k, (path, extra) in jobs.items()}
            got = {k: f.result() for k, f in futures.items()}

        # oam: 128장까지는 모두 보이고, 넘친 OBJ 는 높은 표(0500~)를 덮어 앞 OBJ 의 크기·X 위 비트를 바꾼다.
        stats = {k: oam_stats(got[k]) for k in ('carpet', *OAM_ROMS)}
        for k, s in stats.items():
            print(f'{k}: 1993={s["1993"]} 보이는 OBJ {s["visible"]} 큰 OBJ {s["big"]} 0500~ 쓴 끝 {s["high"]:04X} '
                  f'주인공 OAM {s["rider"]}\n  0500~05FF 쓴 코드 {s["writers"]}')
        checks['oam-carpet'] = stats['carpet']['1993'] == 26 and stats['carpet']['visible'] == 26
        checks['oam-128'] = stats['oam128']['1993'] == 128 and stats['oam128']['visible'] == 128 and \
            stats['oam128']['big'] == 0 and stats['oam128']['high'] == 0x051F
        checks['oam-129'] = stats['oam129']['1993'] == 129 and stats['oam129']['visible'] < 128 and \
            stats['oam129']['big'] > 0 and stats['oam129']['high'] == 0x0520
        checks['oam-137'] = stats['oam137']['1993'] == 137 and stats['oam137']['high'] > 0x0520

        # line: 32장을 넘는 줄에서 화면에 안 나온 OBJ 는 그 줄 OBJ 가운데 OAM 번호가 큰 쪽이다.
        line, base_line = line_stats(got['line']), line_stats(got['carpet-line'])
        print(f'line: 줄 {line["line"]} OBJ {line["count"]} rangeOver {line["range_over"]} 보임 {len(line["shown"])} '
              f'안 보임 {line["hidden"]}')
        print(f'carpet-line: 줄 {base_line["line"]} OBJ {base_line["count"]} rangeOver {base_line["range_over"]}')
        checks['line'] = line['count'] > 32 and line['range_over'] and line['hidden'] and \
            min(line['hidden']) > max(line['shown']) and not base_line['range_over']

        # cells: 슬롯 칸 목록 1,332칸이 칸 표와 같고, 7E:8060~ 에 쓴 것은 맵을 불러올 때와 16:F855 뿐이다.
        crom, w = Rom(roms['cells'].read_bytes()), got['cells']['wram']
        same = total = 0
        spans = []
        for n, slot, attr in (('80-1', 1, 0), ('80-2', 8, 0), ('80-3', 9, 0x0A00)):
            want = cell_words(crom, n, attr)
            base, cells = slot_cells(w, slot, len(want))
            same += sum(a == b for a, b in zip(cells, want))
            total += len(want)
            spans.append((base, base + len(want) * 2))
        writers = sorted({r[1] for r in got['cells']['rw'] if r[0] == 'w'})
        print(f'cells: 칸 목록 {same}/{total} 같음, 자리 {spans[0][0]:04X}~{spans[-1][1] - 1:04X}, 쓴 코드 {writers}, '
              f'1993={w[0x1993]}')
        checks['cells'] = same == total == 1332 and set(writers) <= {'1FD15D', '1FD02D', '16F855'}

        # vflip: 옮긴 상하 반전 표(12칸)가 슬롯 9 칸 목록과 OAM 에 그대로.
        vrom, w = Rom(roms['vflip'].read_bytes()), got['vflip']['wram']
        want = cell_words(vrom, '81-2', 0x0A00)[:16]
        _, cells = slot_cells(w, 9, 16)
        flipped = [e for e in oam(got['vflip']) if e[2] < 0xE0 and e[4] >> 1 & 7 == 5]
        moved = vrom.u24(L.VEHICLE_PARTS['81-2']['vflip'])
        print(f'vflip: 표 {moved >> 16:02X}:{moved & 0xFFFF:04X}, 슬롯 9 {w[0x34E9]}x{w[0x3509]} 칸 목록 '
              f'{sum(a == b for a, b in zip(cells, want))}/16, 그림자 OBJ {len(flipped)} 가운데 상하 반전 '
              f'{sum(bool(e[4] & 0x80) for e in flipped)}')
        checks['vflip'] = moved != rom.u24(L.VEHICLE_PARTS['81-2']['vflip']) and cells == want and \
            len(flipped) == 16 and sum(bool(e[4] & 0x80) for e in flipped) == 12

        # field: 물체는 슬롯 8 부터, 20 까지는 주인공 그대로, 21 이면 슬롯 20(주인공 X·Y)이 덮인다. 양탄자는 8·9 를 덮는다.
        base = got['field']['wram']
        for k in ('field', *FIELD_EXTRA):
            w = got[k]['wram']
            print(f'{k}: 1982={w[0x1982]:02X} 1983={w[0x1983]:02X} 주인공 칸 {slots(w, 0, 1)[0][3:]}')
        hero = slots(base, 0, 1)[0][3:]
        checks['field-objects'] = (base[0x1982], base[0x1983]) == (8, 0x13)
        checks['field-20'] = got['field20']['wram'][0x1983] == 0x20 and slots(got['field20']['wram'], 0, 1)[0][3:] == hero
        checks['field-21'] = got['field21']['wram'][0x1983] == 0x21 and slots(got['field21']['wram'], 0, 1)[0][3:] != hero
        before, after = slots(base, 8, 10), slots(got['field-carpet']['wram'], 8, 10)
        print(f'field 슬롯 8·9: {before} → 양탄자 {after}')
        checks['field-carpet'] = all(v[:3] == (0xFE, 1, 1) for v in before.values()) and \
            [v[1:3] for v in after.values()] == [(3, 3), (3, 1)]

        # edge: 실내는 128 을 따로 보지 않아 128·129 도 그 칸에 놓이고 OAM 에 나온다.
        w = got['edge']['wram']
        placed = slots(w, w[0x1982], w[0x1983])
        # 주인공 타일은 VRAM 앞쪽(00~), 맵 OBJ 타일은 7E:1997 자리(16/00 은 80 넘어)부터다.
        shown = [e for e in oam(got['edge']) if e[2] < 0xE0]
        hero_x = min(e[1] for e in shown if e[3] < 0x80)
        xs = sorted(e[1] for e in shown if 0x80 <= e[3] < 0x180)
        print(f'edge: 물체 슬롯 {[(v[3], v[4]) for v in placed.values()]}, 주인공 왼쪽 X {hero_x}, 물체 OAM X {xs}')
        checks['edge'] = [(v[3], v[4]) for v in placed.values()] == EDGE and \
            xs == [hero_x + (x - EDGE_HERO[0]) * 8 for x, _ in EDGE]

        for key, ok in checks.items():
            print(f'{key}: {"통과" if ok else "불일치"}')
        if not all(checks.values()):
            raise ValueError('불일치: ' + ', '.join(k for k, ok in checks.items() if not ok))
        print(f'검사 {len(checks)}개 통과')
        return 0
    except (OSError, ValueError, KeyError, StopIteration, subprocess.SubprocessError) as error:
        print(f'오류: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
