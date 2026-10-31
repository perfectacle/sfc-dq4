"""서장 수련의 칼 효과(NDS 효과 303·311)를 SFC BG3 타일로 옮긴다.

  capture  NDS 서장 세이브스테이트에서 mlb1a 를 다시 불러, 칼 효과음 412(주인공)·416(검사)이 난 프레임부터
           FRAMES 프레임 동안 화면의 효과 자리를 잘라 ASSETS/nds/dq4/effect/spar/<효과>/fNN.png 로 둔다(desmume 헤드리스).
  apply    그 프레임을 BG3 2bpp 타일·프레임마다 세 색 팔레트로 바꿔 BANK 에 넣는다. 프레임이 없으면 롬을 그대로 둔다.

  DESMUME_CORE=… python sfc/dq4/tools/dq4sparfx.py capture --state work/state/dq4ds-ch0.state --assets "$DQ4_ASSETS"
  python sfc/dq4/tools/dq4sparfx.py apply --base IN.sfc --assets "$DQ4_ASSETS" --out OUT.sfc

dq4prologue 의 수련 루틴이 BANK 머리의 표시를 보고, 있으면 합마다 프레임 목록을 차례로 올린다.
형식은 sfc/dq4/docs/dq4-prologue-format.md 「칼 효과」.
"""
import argparse
import os
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(HERE), str(HERE.parents[1] / 'dq5' / 'tools')]

from dq4chapterbox import BG3_CHR, CANVAS  # noqa: E402  메시지 창 안쪽 BG3 타일을 효과 그림 자리로 빌린다

FX_DIR = Path('nds') / 'dq4' / 'effect' / 'spar'
EFFECTS = (('303', 412), ('311', 416))      # (효과 이름, 그 효과와 함께 나는 NDS 효과음)
FRAMES = 26                                  # 효과음 프레임부터. 두 효과 모두 25프레임 안에 사라짐(실측)
CROP = (88, 52, 164, 124)                    # NDS 위 화면(256x192)에서 두 효과가 다 드는 자리
# SFC 화면(256x224)에 둘 자리. NDS 화면을 세로 가운데에 두면 y + 16 인데, 타일에 맞추려 4점 올린다
COL, ROW, COLS, ROWS = CROP[0] // 8, (CROP[1] + 16) // 8, 10, 9
BANK = 0x4F8000
MAGIC = b'SPFX'
LEAD = 2
DARK = 24                                    # 이보다 어두운 화소(밝기 합/3)는 투명


def capture(state, assets, rom):
    sys.path.insert(0, str(ROOT / 'nds' / 'dq4' / 'tools'))
    import ndsplay
    import ndssound
    import ndswarp
    work = ROOT / 'work' / 'sparfx'
    work.mkdir(parents=True, exist_ok=True)
    p = ndsplay.Player(ndsplay.core_path(), str(rom), str(work))
    p.load(str(state))
    p.run(2)
    r = ndssound.Recorder(p)
    r.install()
    p.frame = 0
    ndswarp.enter(p, 'mlb1a', preset=0, settle=1)
    shots = {}
    while p.frame < 900:
        r.run(1)
        shots[p.frame] = p.image().convert('RGB').crop((CROP[0], 192 + CROP[1], CROP[2], 192 + CROP[3]))
    for name, se in EFFECTS:
        start = next(f for f, kind, n, _ in r.log if kind == 'se' and n == se)
        out = Path(assets) / FX_DIR / name
        out.mkdir(parents=True, exist_ok=True)
        for k in range(FRAMES):
            shots[start + k].save(out / f'f{k:02d}.png')
        print(f'{name}: 효과음 {se} {start} 프레임부터 {FRAMES}장')


def _palette(pixels):
    """밝은 화소를 밝기 순으로 셋으로 나눠 평균 색. 프레임마다 셋을 새로 고른다(사그라지는 프레임은 어두운 셋)."""
    lit = sorted(pixels, key=sum)
    if not lit:
        return [(0, 0, 0)] * 3
    parts = [lit[i * len(lit) // 3:(i + 1) * len(lit) // 3] or lit for i in range(3)]
    return [tuple(sum(c[j] for c in part) // len(part) for j in range(3)) for part in parts]


def _bgr555(rgb):
    r, g, b = (round(c * 31 / 255) for c in rgb)
    return (b << 10 | g << 5 | r).to_bytes(2, 'little')


def frame_tiles(img):
    """(타일 ROWS x COLS 의 2bpp 바이트를 행마다, 팔레트 8바이트, 빈 행 집합의 반대(그림이 있는 행))."""
    w, h = img.size
    canvas = [[(0, 0, 0)] * (COLS * 8) for _ in range(ROWS * 8)]
    top = 0                                  # 4점 올린 자리(ROW)
    for y in range(h):
        for x in range(w):
            canvas[top + y][x] = img.getpixel((x, y))
    lit = [c for row in canvas for c in row if sum(c) / 3 >= DARK]
    pal = _palette(lit)
    index = [[0 if sum(c) / 3 < DARK else
              1 + min(range(3), key=lambda i: sum((a - b) ** 2 for a, b in zip(c, pal[i]))) for c in row]
             for row in canvas]
    rows, used = [], set()
    for ty in range(ROWS):
        data = bytearray()
        for tx in range(COLS):
            for y in range(8):
                v = index[ty * 8 + y][tx * 8:tx * 8 + 8]
                data += bytes((sum((p & 1) << (7 - x) for x, p in enumerate(v)),
                               sum((p >> 1 & 1) << (7 - x) for x, p in enumerate(v))))
        if any(data):
            used.add(ty)
        rows.append(bytes(data))
    return rows, bytes(2) + b''.join(_bgr555(c) for c in pal), used


def build(assets):
    """BANK 에 넣을 바이트. 머리: MAGIC, 효과마다 프레임 목록 주소(워드). 목록: FRAMES 개의 레코드 주소.
    레코드 8바이트: VRAM 워드 주소, 타일 자료 주소, 크기, 팔레트 주소(모두 BANK 안). 프레임마다 그 프레임과 앞 프레임에
    그림이 있는 행만 올리고, 목록의 첫 프레임은 앞 합의 잘린 효과를 지우도록 모든 행을 올린다."""
    from PIL import Image
    base = BANK & 0xFFFF
    head = bytearray(MAGIC) + bytes(2 * len(EFFECTS))
    blob = bytearray()
    records, lists = {}, []

    def at(offset):
        return base + offset

    pending = []        # (레코드 키, 자료 바이트, 팔레트)
    for name, _ in EFFECTS:
        folder = Path(assets) / FX_DIR / name
        # 올린 타일은 다음 프레임 화면에 보이고 효과음 요청도 한 프레임 늦게 잡혀(실측 2프레임 늦음), LEAD 장 앞에서 시작해
        # 끝은 마지막(빈) 프레임으로 채운다
        names = [f'f{min(k + LEAD, FRAMES - 1):02d}.png' for k in range(FRAMES)]
        frames = [frame_tiles(Image.open(folder / n).convert('RGB')) for n in names]
        keys, before = [], set(range(ROWS))
        for rows, pal, used in frames:
            need = sorted(used | before) or [0]
            r0, r1 = need[0], need[-1]
            data = b''.join(rows[r0:r1 + 1])
            key = (r0, data, pal)
            keys.append(key)
            if key not in records:
                records[key] = None
                pending.append(key)
            before = used
        lists.append(keys)
    # 자리 매기기: 머리, 목록, 레코드, 자료·팔레트
    lists_at = len(head)
    rec_at = lists_at + sum(2 * FRAMES for _ in lists)
    data_at = rec_at + 8 * len(pending)
    chunk_at = {}
    for r0, data, pal in pending:
        for c in (data, pal):
            if c not in chunk_at:
                chunk_at[c] = data_at + len(blob)
                blob += c
    for i, key in enumerate(pending):
        records[key] = rec_at + 8 * i
    out = bytearray(head)
    for i, keys in enumerate(lists):
        out[4 + 2 * i:6 + 2 * i] = at(len(out)).to_bytes(2, 'little')
        for key in keys:
            out += at(records[key]).to_bytes(2, 'little')
    for r0, data, pal in pending:
        vram = BG3_CHR + (CANVAS + r0 * COLS) * 8
        out += b''.join(v.to_bytes(2, 'little') for v in (vram, at(chunk_at[data]), len(data), at(chunk_at[pal])))
    out += blob
    if len(out) > 0x8000:
        raise ValueError(f'칼 효과 자료 {len(out)}바이트가 뱅크를 넘음')
    return bytes(out)


def apply(base, assets, out):
    data = bytearray(Path(base).read_bytes())
    if not all((Path(assets) / FX_DIR / name / f'f{FRAMES - 1:02d}.png').exists() for name, _ in EFFECTS):
        print(f'{Path(assets) / FX_DIR} 에 칼 효과 프레임이 없어 효과 없이 둔다', file=sys.stderr)
        Path(out).write_bytes(data)
        return
    blob = build(assets)
    o = (BANK >> 16) * 0x8000 + (BANK & 0x7FFF)
    if any(data[o:o + len(blob)]):
        raise SystemExit(f'{BANK:06X}: 비어 있지 않은 자리')
    data[o:o + len(blob)] = blob
    Path(out).write_bytes(data)
    print(f'칼 효과 {len(blob)}바이트 → {BANK:06X}')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    c = sub.add_parser('capture')
    c.add_argument('--state', required=True, type=Path)
    c.add_argument('--rom', type=Path, default=ROOT / 'rom' / 'dq4ds.nds')
    c.add_argument('--assets', type=Path, default=os.environ.get('DQ4_ASSETS'))
    a = sub.add_parser('apply')
    a.add_argument('--base', required=True, type=Path)
    a.add_argument('--assets', type=Path, default=os.environ.get('DQ4_ASSETS'))
    a.add_argument('--out', required=True, type=Path)
    args = ap.parse_args()
    if args.cmd == 'capture':
        capture(args.state, args.assets, args.rom)
    else:
        apply(args.base, args.assets, args.out)


if __name__ == '__main__':
    main()
