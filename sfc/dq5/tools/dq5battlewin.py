"""DQ5(SFC) 전투 메시지 창. 형식은 sfc/dq5/docs/dq5-graphics-format.md 의 「전투 메시지 창」.

24:8C39 가 푼 전투 메시지의 1바이트 부호를 24:A4A4 가 글자 격자 7E:1DD5(26칸 × 6줄)에 둔다.
  줄 k(7E:0F0E, 0~2)의 글자는 격자 1+2k 줄, 칸은 7E:0F0D. 84(탁점)·83(반탁점)은 칸을 늘리지 않고 바로 위 줄에
  84·83 을 두는데, 첫 줄 위는 창 위 테두리라 테두리에 탁점을 얹은 타일 92·93 을 둔다.
  FF(24:A4F3)는 다음 줄. 셋째 줄 다음이면 24:A569 가 위 테두리(8D)를 다시 쓰고 줄을 올린다.
24:A5D9 는 격자 바이트를 그대로 BG3 타일맵 버퍼 7E:5546(= VRAM 워드 1C00 의 21줄 3칸)부터 한 줄 32칸 간격으로
옮긴다(위 바이트는 창을 열 때 둔 20). 창 틀은 왼쪽 위 8B, 위 8D, 옆 8E, 아래 모서리 97, 아래 98(오른쪽은 좌우 반전).
타일은 BG3 창·메뉴 타일(04:E528, dq5gfx.ui_tiles)과 전투 글자(04:EA28: 2bpp 96~99, 1bpp 9A~AF).

사용:
  python sfc/dq5/tools/dq5battlewin.py rom/dq5.sfc 05E 069 --png work/bw     # 메시지 창 그림
  python sfc/dq5/tools/dq5battlewin.py rom/dq5.sfc --compare work/bd/v0195.vram 05E,069
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
NEWLINE, ENDS = 0xFF, (0xFE, 0xEF, 0xE7)
DIGITS = 0x02                     # 타일 02~0B = 0~9
# 예시 값. F7 은 대기열 이름(주인공·몬스터), FB 는 숫자, ED 는 주인공 이름, F4 는 주문 이름.
HERO = bytes([0x10, 0x10, 0x10, 0x10])


def name_bytes(rom, table, n):
    from dq5text import string
    return string(rom, table, n)


def message_grid(rom, n, subs, grid=None, line=0):
    """메시지 n 을 24:A4A4 처럼 격자(6줄 × 26칸 바이트)에 둔다. subs 는 {제어 바이트: [바이트…] 목록(차례로 꺼냄)}.
    grid·line 을 주면 이어 찍는다(앞 메시지가 끝나면 다음 메시지는 다음 줄부터). (격자, 다음 줄)."""
    if grid is None:
        grid = [[BORDER] * COLS] + [[BLANK] * COLS for _ in range(ROWS - 1)]
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

    for b in dq5battletext.message(rom, n):
        if b in ENDS:
            break
        if b == NEWLINE:
            line, col = line + 1, 0
            if line > 2:
                raise ValueError('셋째 줄 다음 줄 올리기는 그리지 않음')
            continue
        if b >= 0xE2:
            for c in queue[b].pop(0):
                put(c)
            continue
        put(b)
    return grid, line + 1


def messages_grid(rom, msgs):
    """같은 창에 차례로 찍힌 메시지들의 격자. 둘째 메시지부터는 둘째 줄에서 시작하고, 그 줄과 위 탁점 줄을 먼저
    지운다(덤프에서 본 동작: 05E 다음 069, 005(두 줄) 다음 069 가 모두 둘째 줄에 찍힘)."""
    grid, line = None, 0
    for k, n in enumerate(msgs):
        if k:
            line = 1
            grid[2] = [BLANK] * COLS
            grid[3] = [BLANK] * COLS
        grid, line = message_grid(rom, n, example_subs(rom, n), grid, line)
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
    }.get(n, {0xF7: [HERO, monster], 0xFB: [digits(4)], 0xF4: [spell], 0xED: [HERO]})


EXAMPLES = ((0x05E,), (0x069,), (0x06A,), (0x070,), (0x005,), (0x05E, 0x069), (0x001, 0x06A))


def windows(rom):
    """[(파일 이름, 제목, 그림)]. 갤러리용 예시 창."""
    out = []
    for msgs in EXAMPLES:
        img = render(rom, window_map(messages_grid(rom, list(msgs))))
        name = 'battle-message-' + '-'.join(f'{n:03X}' for n in msgs) + '.png'
        title = '전투 메시지 ' + ' + '.join(f'{n:03X}' for n in msgs) + ' ' + \
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
    ap.add_argument('--compare', nargs=2, metavar=('VRAM', 'MSGS'),
                    help='덤프 VRAM 과 같은 창에 찍힌 메시지(쉼표, 차례로)를 견줌')
    args = ap.parse_args()
    rom = Rom(open(args.rom, 'rb').read())
    if args.compare:
        msgs = [int(s, 16) for s in args.compare[1].split(',')]
        same, total, diff = compare(rom, open(args.compare[0], 'rb').read(), messages_grid(rom, msgs))
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
