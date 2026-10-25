"""DQ5(SFC) 전투 메시지 창. 형식은 sfc/dq5/docs/dq5-graphics-format.md 의 「전투 메시지 창」.

24:8C39 가 푼 전투 메시지의 1바이트 부호를 24:A4A4 가 글자 격자 7E:1DD5(26칸 × 6줄)에 둔다.
  줄 k(7E:0F0E, 0~2)의 글자는 격자 1+2k 줄, 칸은 7E:0F0D. 84(탁점)·83(반탁점)은 칸을 늘리지 않고 바로 위 줄에
  84·83 을 두는데, 첫 줄 위는 창 위 테두리라 테두리에 탁점을 얹은 타일 92·93 을 둔다.
  FF·FD(24:A4F3)는 다음 줄. 셋째 줄에서 다음 줄로 가면 7E:0F0B 비트 7(BRK 9E~A0 로 이어 찍기)일 때 24:A569 가
  줄을 올리고(위 테두리 8D 를 다시 쓰고 한 타일 줄씩 두 번, 4프레임 간격), 아니면 셋째 줄 처음부터 덮어 쓴다.
  FE 도 끝에서 한 번 다음 줄로 간다. 같은 창의 둘째 메시지(BRK A4~A6, 24:8634)는 둘째·셋째 줄을 지우고 둘째 줄부터.
24:A5D9 는 격자 바이트를 그대로 BG3 타일맵 버퍼 7E:5546(= VRAM 워드 1C00 의 21줄 3칸)부터 한 줄 32칸 간격으로
옮긴다(위 바이트는 창을 열 때 둔 20). 창 틀은 왼쪽 위 8B, 위 8D, 옆 8E, 아래 모서리 97, 아래 98(오른쪽은 좌우 반전).
타일은 BG3 창·메뉴 타일(04:E528, dq5gfx.ui_tiles)과 전투 글자(04:EA28: 2bpp 96~99, 1bpp 9A~AF).

사용:
  python sfc/dq5/tools/dq5battlewin.py rom/dq5.sfc 05E 069 --png work/bw     # 메시지 창 그림
  python sfc/dq5/tools/dq5battlewin.py rom/dq5.sfc --compare work/bd/v0195.vram 05E,069
  python sfc/dq5/tools/dq5battlewin.py rom/dq5.sfc --scroll --compare work/bs/v00380.vram 05E,006
--scroll 은 둘째 메시지부터 BRK 9E 로 이어 찍는다(지우지 않고 줄 올리기).
--compare 는 전투 덤프의 VRAM BG3 타일맵(21~27줄 2~29칸)과 칸마다(타일·속성) 비교한다. 메시지 안 이름·숫자는
예시 값(주인공 ああああ, 몬스터 スライム, 숫자 4·1)을 넣는다.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from dq5map import Rom, lorom  # noqa: E402
import dq5battletext  # noqa: E402

COLS, ROWS = 26, 6
MAP_ROW, MAP_COL = 21, 3          # 7E:5546 = 타일맵 21줄 3칸
ATTR = 0x2000                     # 우선순위, BG3 팔레트 0
BORDER, BLANK = 0x8D, 0x01
DAKUTEN, HANDAKUTEN = 0x84, 0x83
BORDER_MARK = {DAKUTEN: 0x92, HANDAKUTEN: 0x93}
BATTLE_TILES = 0x04EA28
NEWLINES, ENDS = (0xFF, 0xFD), (0xFE, 0xEF, 0xE7)
SILENT = (0xF2,)                  # 글자를 두지 않는 부호(F2 는 24:886C 효과음)
DIGITS = 0x02                     # 타일 02~0B = 0~9
# 예시 값. F7 은 대기열 이름(주인공·몬스터), FB 는 숫자, ED 는 주인공 이름, F4 는 주문 이름.
HERO = bytes([0x10, 0x10, 0x10, 0x10])


def name_bytes(rom, table, n):
    from dq5text import string
    return string(rom, table, n)


def new_grid():
    return [[BORDER] * COLS] + [[BLANK] * COLS for _ in range(ROWS - 1)]


def shift_rows(grid):
    """24:A5C5: 격자 2~5줄을 1~4줄로 한 타일 줄 올린다."""
    grid[1:5] = [row[:] for row in grid[2:6]]


def scroll_up(grid, steps=2):
    """24:A569 가 셋째 줄 다음 줄로 갈 때 하는 일. steps=1 이면 첫 걸음(4프레임 뒤 둘째 걸음)까지만."""
    grid[0] = [BORDER] * COLS
    shift_rows(grid)
    grid[5] = [BLANK] * COLS
    if steps < 2:
        return
    # 첫 걸음 뒤 1줄은 둘째 줄의 탁점 줄이다. 그 탁점은 위 테두리로 올라가 92·93 이 된다.
    grid[0] = [BORDER_MARK.get(b, BORDER) for b in grid[1]]
    shift_rows(grid)


def place(grid, line, code, subs, scroll=False):
    """1바이트 부호 code 를 24:A4A4 처럼 격자에 이어 둔다. subs 는 {제어 바이트: [바이트…] 목록(차례로 꺼냄)}.
    scroll 은 7E:0F0B 비트 7. (격자, 다음 메시지가 시작할 줄)."""
    queue = {k: list(v) for k, v in subs.items()}
    col = 0

    def put(b):
        nonlocal col
        if b in (DAKUTEN, HANDAKUTEN):
            grid[2 * line][col] = BORDER_MARK[b] if line == 0 else b
            return
        if col < COLS:
            grid[1 + 2 * line][col] = b
        col += 1

    def newline():
        nonlocal line, col
        if line < 2:
            line += 1
        elif scroll:
            scroll_up(grid)
        col = 0

    for b in code:
        if b in ENDS:
            if b == 0xFE or (b == 0xEF and col):
                newline()
            break
        if b in NEWLINES:
            newline()
            continue
        if b in SILENT:
            continue
        if b >= 0xE2:
            for c in queue[b].pop(0):
                put(c)
            continue
        put(b)
    return grid, line


def message_grid(rom, n, subs, grid=None, line=0, scroll=False):
    """메시지 n 을 격자(6줄 × 26칸 바이트)에 둔다. grid·line 을 주면 이어 찍는다. (격자, 다음 줄)."""
    return place(new_grid() if grid is None else grid, line, dq5battletext.message(rom, n), subs, scroll)


def messages_grid(rom, msgs, scroll=False):
    """같은 창에 차례로 찍힌 메시지들의 격자. 둘째 메시지부터는 BRK A4(24:8634)처럼 둘째·셋째 줄(격자 2~5줄)을
    지우고 둘째 줄에서 시작한다. scroll 이면 BRK 9E(24:85E4)처럼 지우지 않고 앞 메시지의 FE 가 넘긴 줄에서 잇는다."""
    grid, line = new_grid(), 0
    for k, n in enumerate(msgs):
        if k and not scroll:
            line = 1
            for r in range(2, ROWS):
                grid[r] = [BLANK] * COLS
        grid, line = message_grid(rom, n, example_subs(rom, n), grid, line, scroll and k > 0)
    return grid


def window_map(grid):
    """BG3 타일맵 21~27줄 2~29칸의 낱말(타일 | 속성)."""
    rows = []
    for r in range(ROWS):
        left = 0x8B if r == 0 else 0x8E
        rows.append([ATTR | left] + [ATTR | b for b in grid[r]] + [ATTR | 0x4000 | left])
    rows.append([ATTR | 0x97] + [ATTR | 0x98] * COLS + [ATTR | 0x4000 | 0x97])
    return rows


def battle_tiles(rom):
    """BG3 타일 번호 → 2bpp 16바이트. 창·메뉴 타일 0~149 와 전투 글자 96~AF."""
    import dq5gfx
    ui = dq5gfx.ui_tiles(rom)
    tiles = {t: ui[t * 16:t * 16 + 16] for t in range(len(ui) // 16)}
    o = lorom(BATTLE_TILES)
    for i in range(4):
        tiles[0x96 + i] = bytes(b for r in range(8) for b in (rom.d[o + i * 16 + r], rom.d[o + i * 16 + 8 + r]))
    o += 64
    for i in range(22):
        tiles[0x9A + i] = bytes(b for r in range(8) for b in (rom.d[o + i * 8 + r], 0xFF))
    return tiles


def render(rom, words, pal=None):
    from PIL import Image
    import dq5gfx
    if pal is None:
        o = lorom(dq5gfx.UI_PALETTE)
        pal = dq5gfx.cgram_colors(rom.d[o:o + 8])
    tiles = battle_tiles(rom)
    img = Image.new('RGB', (len(words[0]) * 8, len(words) * 8), pal[0])
    for y, row in enumerate(words):
        for x, w in enumerate(row):
            t = tiles.get(w & 0x3FF)
            if t is None:
                continue
            p = (w >> 10) & 7
            ti = dq5gfx.tile_image(dq5gfx.chr_2bpp(t), pal[p * 4:p * 4 + 4], bool(w & 0x4000), bool(w & 0x8000))
            img.paste(ti, (x * 8, y * 8), ti)
    return img


def example_subs(rom, n):
    """메시지마다의 예시 대기열."""
    monster = name_bytes(rom, 4, 0)    # スライム
    digits = lambda v: bytes(DIGITS + int(c) for c in str(v))  # noqa: E731
    spell = name_bytes(rom, 3, 1)      # メラ
    return {
        0x05E: {0xF7: [HERO]},
        0x069: {0xF7: [monster], 0xFB: [digits(4)]},
        0x001: {0xF7: [monster]},
        0x005: {0xED: [HERO]},
        0x06A: {0xF7: [HERO], 0xFB: [digits(1)]},
        0x070: {0xF7: [HERO], 0xF4: [spell]},
        0x10E: {0xF7: [monster]},
        0x006: {0xED: [HERO], 0xF5: [name_bytes(rom, 5, 128)]},   # はめつのたて(덤프에 찍힌 값)
    }.get(n, {0xF7: [HERO, monster], 0xFB: [digits(4)], 0xF4: [spell], 0xED: [HERO]})


EXAMPLES = ((0x05E,), (0x069,), (0x06A,), (0x070,), (0x005,), (0x05E, 0x069), (0x001, 0x06A))
# BRK 9E 로 이어 찍어 줄을 올리는 예. 006 은 쪽 넘김(FD)마다 줄을 올린다.
SCROLL_EXAMPLES = ((0x05E, 0x006),)


def windows(rom):
    """[(파일 이름, 제목, 그림)]. 갤러리용 예시 창."""
    out = []
    for msgs, scroll in [(m, False) for m in EXAMPLES] + [(m, True) for m in SCROLL_EXAMPLES]:
        img = render(rom, window_map(messages_grid(rom, list(msgs), scroll)))
        name = 'battle-message-' + '-'.join(f'{n:03X}' for n in msgs) + ('-scroll' if scroll else '') + '.png'
        title = '전투 메시지 ' + ' + '.join(f'{n:03X}' for n in msgs) + (' 이어 찍기(줄 올림)' if scroll else '') + ' ' + \
            ' / '.join(dq5battletext.show(rom, dq5battletext.message(rom, n)) for n in msgs)
        out.append((name, title, img))
    return out


def export_all(rom, outdir):
    """예시 창 그림을 outdir 에 쓰고 갤러리 항목 목록을 돌려준다."""
    os.makedirs(outdir, exist_ok=True)
    items = []
    for name, title, img in windows(rom):
        img.save(os.path.join(outdir, name))
        items.append({'cat': 'screens', 'group': '전투 메시지 창', 'path': name, 'w': img.width, 'h': img.height,
                      'title': title, 'note': '24:A4A4 격자 → 24:A5D9 타일맵, 창 틀 8B·8D·8E·97·98. 이름·숫자는 예시 값'})
    return items


def compare(rom, vram, grids):
    """덤프 VRAM 의 BG3 타일맵(워드 1C00) 21~27줄 2~29칸과 창 낱말을 칸마다 견준다."""
    want = window_map(grids)
    same = total = 0
    diff = []
    for r, row in enumerate(want):
        for c, w in enumerate(row):
            a = (0x1C00 + (MAP_ROW + r) * 32 + MAP_COL - 1 + c) * 2
            got = vram[a] | vram[a + 1] << 8
            total += 1
            if got == w:
                same += 1
            else:
                diff.append((MAP_ROW + r, MAP_COL - 1 + c, f'{got:04X}', f'{w:04X}'))
    return same, total, diff


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('rom')
    ap.add_argument('msgs', nargs='*', type=lambda s: int(s, 16))
    ap.add_argument('--png', help='그림 폴더')
    ap.add_argument('--scroll', action='store_true', help='둘째 메시지부터 BRK 9E 로 이어 찍기(줄 올리기)')
    ap.add_argument('--compare', nargs=2, metavar=('VRAM', 'MSGS'),
                    help='덤프 VRAM 과 같은 창에 찍힌 메시지(쉼표, 차례로)를 견줌')
    args = ap.parse_args()
    rom = Rom(open(args.rom, 'rb').read())
    if args.compare:
        msgs = [int(s, 16) for s in args.compare[1].split(',')]
        same, total, diff = compare(rom, open(args.compare[0], 'rb').read(), messages_grid(rom, msgs, args.scroll))
        print(f'{args.compare[0]}: 칸 {same}/{total} 같음', diff[:8])
    if args.png:
        for it in export_all(rom, args.png):
            print(it['path'], it['title'])
    elif args.msgs:
        for n in args.msgs:
            for row in messages_grid(rom, [n]):
                print(' '.join(f'{b:02X}' for b in row))
    return 0


if __name__ == '__main__':
    sys.exit(main())
