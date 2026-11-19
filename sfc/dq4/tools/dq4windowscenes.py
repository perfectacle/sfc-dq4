"""창 경계 상태 장면: 창이 가장 넓거나 가득 찰 때를 만드는 출발 상태·값·입력과, 그 상태에서 정적으로 셈한 기대 창 꼴.

형식은 sfc/dq4/docs/dq4-window-text-format.md 「창 레코드 정적 검사」. 장면은 dq4windowcheck 의 출발 상태(STATES 의 이름)에서
dq5warp.lua SET 꼴 값을 넣고 같은 입력 문법으로 창을 연다. 창 기록 틀(dq4winwatch)이 이 장면을 돌려 화면의 창과
expected() 를 견준다. 에뮬레이터 없이 쓰는 것은 expected() 뿐이다.

  uv run --locked python sfc/dq4/tools/dq4windowscenes.py --rom work/ch1/dq4-ch1.sfc [--scene 이름]
"""
import argparse
import sys
from dataclasses import dataclass

import dq4windowlint as wl
from dq4savefixture import HERO, HP, MAX_HP, MP, MAX_MP, LEVEL, ITEMS, ITEM_SLOTS

RECORD = 42                     # 일행 기록 한 사람(7E:2040 + 사람 × 42)
GOLD = 0x7E2019                 # 24비트(dq4savefixture.GOLD)
HERO_NAME = 0x7E2001
# 1장 일행에 넣을 수 있는 동료 종류(dq4compatcheck.party_pokes). 네 명까지
COMPANIONS = ('05', '06', '07')
# 주인공 이름을 한글 넉 자(창 이름 칸 5칸을 꽉 채움)로. dq4windowcheck.NAME 과 같은 표시 바이트
LONG_NAME = '97338C3799299827'
ITEM_KIND = 5


def wide_items(data):
    """그림이 가장 넓은 물건 번호들(창 이름 칸을 꽉 채움). 빌드한 롬의 색인(dq4windowlint)에서 고른다."""
    widths = wl.Widths(data, 'hack')
    top = widths.table(ITEM_KIND, 0)
    out = []
    for n in range(0x100):
        at = wl.u16(data, wl.TEXT_BANK << 16 | wl.INDEX + ITEM_KIND * 0x200 + n * 2)
        if at and data[wl.lorom(wl.TEXT_BANK << 16 | at)] == top:
            out.append(n)
    return tuple(out)


def u24(addr, value):
    return ';'.join(f'{addr + i & 0xFFFFFF:06X}={value >> 8 * i & 0xFF:02X}' for i in range(3))


def member(i, field, value, n=2):
    a = 0x7E0000 | HERO + i * RECORD + field
    return ';'.join(f'{a + k:06X}={value >> 8 * k & 0xFF:02X}' for k in range(n))


def maxed(people):
    """사람마다 HP·MP·레벨 최대(HP·MP 999, 레벨 99 — dq4windowlint.NUMBER_FIELDS)."""
    return ';'.join(member(i, f, v, k) for i in range(people)
                    for f, v, k in ((HP, 999, 2), (MAX_HP, 999, 2), (MP, 999, 2), (MAX_MP, 999, 2), (LEVEL, 99, 1)))


def full_bag(people, items):
    return ';'.join(f'{0x7E0000 | HERO + i * RECORD + ITEMS + k:06X}={items[k % len(items)]:02X}'
                    for i in range(people) for k in range(ITEM_SLOTS))


@dataclass(frozen=True)
class Scene:
    name: str
    state: str                  # dq4windowcheck.STATES 의 이름
    people: int                 # 주인공 포함 일행 수
    sets: str                   # dq5warp.lua SET 꼴(주소=값;…). 일행 기록은 party 로 따로
    inputs: str                 # dq4windowcheck 입력 문법
    windows: tuple              # 이 장면에서 뜨는 창(그리는 차례)
    why: str

    @property
    def party(self):
        return ','.join(COMPANIONS[:self.people - 1])


def name_sets(name=LONG_NAME):
    return ';'.join(f'{HERO_NAME + i:06X}={name[i * 2:i * 2 + 2]}' for i in range(len(name) // 2))


OPEN = 'b:4,wait:40,up:10,wait:20,a:10,wait:30,'
STATUS = 'b:4,wait:40,up:10,wait:20,a:10,wait:30,down:4,wait:10,right:4,wait:10,a:10,wait:60'
ITEM_LIST = OPEN + 'down:4,wait:10,down:4,wait:10,down:4,wait:10,a:10,wait:40,a:10,wait:60,a:10,wait:60'
SHOP_WHO = 'wait:30,up:6,wait:30,a:4,wait:30,a:4,wait:90,a:4,wait:60,a:4,wait:60,' + 'a:4,wait:80,' * 3

def scenes(data):
    """빌드한 롬으로 장면 목록을 만든다(넓은 물건 번호를 롬에서 고르므로)."""
    wide = wide_items(data)
    return (
        *(Scene(f'party{n}', 'shop', n, maxed(n) + ';' + u24(GOLD, 99999), OPEN + 'wait:60', (0x01, 0x02),
                f'일행 {n}명: 필드 상태 창(02)이 사람마다 열을 늘림. HP·MP 999, 레벨 99, 금화 99999') for n in range(1, 5)),
        Scene('long-name', 'shop', 4, name_sets() + ';' + maxed(4), OPEN + 'wait:60', (0x01, 0x02),
              '주인공 이름 한글 넉 자: 이름 칸 5칸이 맨 오른쪽 사람에서 오른쪽 테두리에 닿음'),
        Scene('gold-max', 'shop', 2, u24(GOLD, 99999), SHOP_WHO, (0x33, 0x05, 0x39, 0x3A),
              '금화 99999(상한): 골드 창 05 다섯 자리'),
        Scene('bag-full', 'shop', 4, full_bag(4, wide), ITEM_LIST, (0x01, 0x0E, 0x0F, 0x10),
              '네 사람 소지품 12칸을 가장 넓은 물건으로: 물건 목록 0F·어떻게 할까 제목(2E)'),
        Scene('shop-full', 'shop', 4, full_bag(4, wide) + ';' + u24(GOLD, 99999), SHOP_WHO, (0x33, 0x05, 0x39, 0x3A),
              '가게 사기 → 누구에게(3A)에 넷, 모두 소지품 가득(「 N개 소지」 열)'),
        Scene('equip-wide', 'shop', 1, full_bag(1, wide), STATUS, (0x01, 0x0B, 0x07, 0x08),
              '가장 넓은 장비 이름이 장비 칸(08 줄 01 + E0~E3)에 뜸'),
        Scene('page-turn', 'shop', 1, full_bag(1, wide), ITEM_LIST + ',' + 'down:4,wait:20,' * 13, (0x01, 0x0E, 0x0F),
              '물건 목록 쪽 넘김(12칸 넘어 다음 쪽)'),
        Scene('monsters4', 'battle', 4, maxed(4), 'wait:400', (0x17, 0x1B, 0x19),
              '전투 몬스터 무리 넷(1B 의 줄 넷)·전투 상태 창 사람 넷'),
    )


def rect(win, people):
    """일행 수에 따른 화면 사각형(dq4windowlint.bounds 를 사람 수로)."""
    w, h = win.w, win.h
    if win.per_member and not win.vertical:
        w = win.w + (people - 1) * (win.w - 1)
    elif win.party_height:
        h = people * 2 + 3
    return win.x, win.y, w, h


def expected(data, scene):
    """창 번호 → {'rect', 'inner', 'rows'(줄마다 마지막 칸 + 1, 모르면 None)}. 화면의 창과 견줄 기대 꼴."""
    widths = wl.Widths(data, 'hack')
    out = {}
    for n in scene.windows:
        win = wl.parse(data, n, widths)
        out[n] = {'rect': rect(win, scene.people), 'inner': wl.inner_width(win),
                  'rows': [wl.row_end(cells) for cells in win.rows]}
    return out


def frames(inputs):
    """입력 문자열이 끝나는 프레임(누름·기다림 길이의 합)."""
    return sum(int(tok.split(':')[1]) for tok in inputs.split(',') if ':' in tok)


# 전투 장면은 걸을 때마다 조우(dq4windowcheck 의 battle 장면과 같은 ROMPATCH)
ROMPATCH = {'battle': '8523=FF'}


def windowcheck_scenes(data, states):
    """dq4windowcheck.scenes() 꼴 튜플(이름, 세이브스테이트, POKE, ROMPATCH, PRE, 프레임). states = {'shop': 경로, 'battle': 경로}.
    일행은 dq4compatcheck.party_pokes 로 둔다. 창 기록 틀은 모든 프레임을 보므로 프레임은 입력이 끝난 뒤 한 프레임."""
    import dq4compatcheck
    out = []
    for s in scenes(data):
        party = ';'.join(f'{a:06X}={v:02X}' for a, v in dq4compatcheck.party_pokes(s.party, data))
        if s.people == 1:
            # 출발 상태는 일행 둘(dq4windowcheck.STATES). party_pokes 는 동료가 없으면 아무것도 쓰지 않아 수를 직접 줄인다
            party = '7E201D=01;7E201E=01;7E201F=01'
        poke = ';'.join(x for x in (party, s.sets) if x)
        end = frames(s.inputs) + 60
        out.append((f'edge-{s.name}', states[s.state], poke, ROMPATCH.get(s.state, ''), s.inputs, range(end, end + 1)))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--rom', required=True)
    ap.add_argument('--scene')
    args = ap.parse_args()
    from pathlib import Path
    data = Path(args.rom).read_bytes()
    for s in scenes(data):
        if args.scene and s.name != args.scene:
            continue
        print(f'{s.name}: {s.why}')
        for n, e in expected(data, s).items():
            print(f'  {n:02X} {e["rect"]} 안쪽 {e["inner"]} 줄 {e["rows"]}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
