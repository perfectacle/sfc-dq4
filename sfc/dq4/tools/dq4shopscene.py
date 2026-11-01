"""1장 이무르 가게 장면 검사(libretro snes9x·bsnes): 사기·팔기·취소를 장면마다 수 초에 돌리고 WRAM 으로 판정한다.

장면마다 저장 기록(dq4savefixture)을 이무르(칸 7)에 두고 금화·소지품을 고쳐 이어 하기로 시작한 뒤,
dq4compatcheck.Walker.warp 로 가게 카운터 앞에 서서 입력 열로 가게 흐름을 지난다. 창은 7E:0A00(마지막으로 연 창
번호)이 8프레임 그대로인 값으로 보고, 입력 열은 「이 창이 될 때까지 버튼을 톡톡 누름」, 「목록 커서가 이 값이 될
때까지 아래」 꼴이라 프레임을 세어 기다리지 않는다. 끝나면 금화(7E:2019), 주인공 물건 12칸(7E:2056)·장비 비트
(7E:2054), 가게 임시값($0F21 개수·사람, $0F2C 개수 창 최대·팔 개수)과 지나온 창 차례(지나가도 되는 창 PASS 를
뺀 열이 장면의 windows 와 정확히 같아야 함, 끝 원소가 끝 창)를 기대값과 견준다.
스크린샷은 창이 바뀔 때마다 증거로만 남긴다. 장면마다 같은 입력을 두 번 돌려 두 번 다 통과하고 창 차례·끝 프레임·
끝 WRAM 128KB 가 같아야 통과다(--once 로 끔).

  uv run --locked python sfc/dq4/tools/dq4shopscene.py --rom work/ch1/dq4-ch1-full.sfc --out work/shopscene
  (--only buy-multi,sell-equipped, --core snes9x, --jobs 4, --seed/--seeds)
형식은 sfc/dq4/docs/dq4-shopscene-format.md.
"""
import argparse
import concurrent.futures
import hashlib
import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[1] / 'dq5' / 'tools')]

import dq4ch1walkcheck as wc  # noqa: E402
import dq4compatcheck as cc  # noqa: E402
import dq4cores  # noqa: E402
import dq4savefixture as fx  # noqa: E402

WINDOW = 0x7E0A00      # 마지막으로 연 창 번호
CURSOR = 0x7E0AD7      # 창 커서(가게 창·팔기 목록은 칸 번호)
DIGIT = 0x7E0B02       # 개수 창 5C 의 끝 자리 숫자 타일(02~0B = 0~9)
SHOP_KIND = 0x7E0F20   # 0 도구·1 방어구·2 무기
QTY = 0x7E0F21         # 사기: 개수(장비는 1), 팔기·필드 메뉴: 사람 번호
ITEM = 0x7E0F22        # 사기 목록 커서의 물건
QTY_MAX = 0x7E0F2C     # 개수 창이 떠 있는 동안 최대 | 40(열림) | 80(팔기), 팔기 개수. 다 쓰면 0
QTY_OPEN, QTY_SELL = 0x40, 0x80
GOLD = 0x7E2019        # 3바이트
EQUIP = 0x7E2054       # 주인공 장비 비트(bit n = 물건 칸 n)
ITEMS = 0x7E2056       # 주인공 물건 12칸, 빈 칸 FF

W_COMMAND, W_SHOP, W_LIST, W_PARTNER, W_SELL, W_QTY, W_YESNO = 0x01, 0x33, 0x39, 0x3A, 0x37, 0x5C, 0x32
# 버튼을 누르며 지나가도 되는 창: 메시지 창(00)·상태 창(02)·목록을 둔 채 뜬 메시지(35)·가게 첫 창(34)·
# 금화 창 다시 그리기(58)·닫힘(FF)
PASS = frozenset({0x00, 0x02, 0x34, 0x35, 0x58, 0xFF})
NAMES = {W_COMMAND: '명령', W_SHOP: '가게', W_LIST: '사기 목록', W_PARTNER: '사기 목록', W_SELL: '팔기 목록',
         W_QTY: '개수', W_YESNO: '예/아니요', 0x35: '목록 위 메시지', 0x00: '메시지'}
STABLE = 8             # 창 번호가 이만큼 그대로여야 그 창으로 본다(창을 다시 그릴 때 잠깐 바뀌는 값을 거름)
TAP = (2, 15)          # 누르는 프레임, 쉬는 프레임. 필드는 A 를 8프레임에 한 번만 받아(걸음 뒤 20·28·60프레임째
#                        누름은 받고 30·40프레임째는 놓침) 주기를 8의 배수가 아닌 17로 두어 누르는 자리를 돌린다
STEP_LIMIT = 1500      # 한 입력 단계가 기다리는 최대 프레임
PICK_LIMIT = 14        # 커서를 옮기는 최대 횟수
SETTLE = 8             # 창에 닿은 뒤 다음 입력까지
QUIET = 400            # 팔기에서 물건을 고른 뒤 누르지 않고 기다리는 프레임: ▼ 가 없으면 이 안에 예/아니요가 뜸

# 가게마다 (순간이동 자리, 카운터 앞 칸, 가게 종류 $0F20). 같은 맵(37/00) 안의 순간이동은 그 칸이 아니라 근처에
# 세운다(도구점 (18,49) 카운터 앞, 방어구점 (34,12) 두 칸 아래). 위를 짧게 한 번 누르면 도구점은 카운터에 막혀
# 돌아서기만 하고 방어구점은 한 칸 올라선다. 더 누르면 방어구점은 카운터 그림 칸 (34,10)까지 올라서므로 한 번만
SHOPS = {'item': ('37/00,18,48', (18, 49), 0), 'armor': ('37/00,34,8', (34, 11), 1)}
X, Y = 0x7E3020, 0x7E3080
FACE = (8, 24)         # 위를 누르는 프레임(돌아서려면 6프레임 넘게, 한 걸음보다 짧게), 걸음이 끝나기를 기다리는 프레임
BASE_ITEMS = (0x42, 0x00)   # 새 게임 밑판: 천 옷·노송나무 막대, 둘 다 장비(비트 0003)
HERB, ANTIDOTE, CHAIN_MAIL, WOOD_HAT = 0xA1, 0xA2, 0x4D, 0x87


@dataclass
class Scene:
    name: str
    title: str
    shop: str
    sets: tuple            # dq4savefixture.SaveSlot.set 의 (키, 값)
    steps: tuple           # 입력 열(Driver.run)
    gold: int              # 끝 금화
    items: tuple           # 끝 물건(빈 칸 빼고)
    equip: int             # 끝 장비 비트
    wram: dict = field(default_factory=dict)   # 끝에 볼 그 밖의 값 {주소: 값}
    windows: tuple = ()    # 지나온 창 차례(PASS 창은 뺌). 끝 원소가 끝 창


def to(button, *windows):
    return ('to', button, windows)


def pick(addr, value, button='down'):
    return ('pick', addr, value, button)


def press(button, times):
    return ('press', button, times)


def wait(window, frames):
    """누르지 않고 frames 안에 window 창이 되는지."""
    return ('wait', window, frames)


def stays(frames):
    """누르지 않고 frames 동안 창이 그대로인지(▼ 기다림)."""
    return ('stays', frames)


def see(addr, value):
    return ('see', addr, value)


def poke(addr, value):
    return ('poke', addr, value)


OPEN = (to('a', W_COMMAND), to('a', W_SHOP))
BUY = OPEN + (to('a', W_LIST, W_PARTNER),)
SELL = OPEN + (pick(CURSOR, 1), to('a', W_SELL))


def items(*extra):
    return ','.join(f'{b:02X}' for b in BASE_ITEMS + extra)


SCENES = [
    Scene('buy-one', '사기 1개(돈이 하나 값뿐이라 개수를 묻지 않음)', 'item', (('gold', '10'),),
          BUY + (pick(ITEM, HERB), to('a', W_YESNO), to('a', W_SHOP)),
          gold=2, items=BASE_ITEMS + (HERB,), equip=0x0003, wram={QTY_MAX: 0},
          windows=(W_COMMAND, W_SHOP, W_PARTNER, W_YESNO, W_SHOP)),
    Scene('buy-multi', '약초 3개 사기(개수 창, 합계 24G)', 'item', (('gold', '1000'),),
          BUY + (pick(ITEM, HERB), to('a', W_QTY), see(QTY_MAX, QTY_OPEN | 9), see(DIGIT, 0x03), press('up', 2),
                 see(DIGIT, 0x05),
                 to('a', W_YESNO), to('a', W_SHOP)),
          gold=976, items=BASE_ITEMS + (HERB,) * 3, equip=0x0003, wram={QTY_MAX: 0, QTY: 1},
          windows=(W_COMMAND, W_SHOP, W_PARTNER, W_QTY, W_YESNO, W_SHOP)),
    Scene('buy-qty-cap', '개수 창 위·아래가 1~최대(돈 20G 로 2개)에서 멈춤', 'item', (('gold', '20'),),
          BUY + (pick(ITEM, HERB), to('a', W_QTY), see(QTY_MAX, QTY_OPEN | 2), press('up', 3), see(DIGIT, 0x04),
                 press('down', 3), see(DIGIT, 0x03), press('up', 1), see(DIGIT, 0x04),
                 to('a', W_YESNO), to('a', W_SHOP)),
          gold=4, items=BASE_ITEMS + (HERB, HERB), equip=0x0003, wram={QTY_MAX: 0},
          windows=(W_COMMAND, W_SHOP, W_PARTNER, W_QTY, W_YESNO, W_SHOP)),
    Scene('buy-short', '금화 모자람(5G 로 8G 약초)', 'item', (('gold', '5'),),
          BUY + (pick(ITEM, HERB), to('a', W_SHOP)),
          gold=5, items=BASE_ITEMS, equip=0x0003,
          windows=(W_COMMAND, W_SHOP, W_PARTNER, W_SHOP)),
    Scene('buy-bag-full', '가방 가득(12칸)에서 사기', 'item', (('gold', '1000'), ('items', items(*(ANTIDOTE,) * 10))),
          BUY + (pick(ITEM, HERB), to('a', W_SHOP)),
          gold=1000, items=BASE_ITEMS + (ANTIDOTE,) * 10, equip=0x0003,
          windows=(W_COMMAND, W_SHOP, W_PARTNER, W_SHOP)),
    Scene('buy-no', '사기 확인에서 아니요(B): 「아쉽네요」 ▼ 뒤 사기 목록', 'item', (('gold', '10'),),
          BUY + (pick(ITEM, HERB), to('a', W_YESNO), to('b', 0x00), to('a', W_LIST, W_PARTNER)),
          gold=10, items=BASE_ITEMS, equip=0x0003,
          windows=(W_COMMAND, W_SHOP, W_PARTNER, W_YESNO, W_PARTNER)),
    Scene('buy-back', '사기 목록에서 B 로 가게 창', 'item', (('gold', '10'),),
          BUY + (to('b', W_SHOP),),
          gold=10, items=BASE_ITEMS, equip=0x0003,
          windows=(W_COMMAND, W_SHOP, W_PARTNER, W_SHOP)),
    Scene('sell-one', '약초 하나 팔기(6G, 값 묻기까지 ▼ 없이)', 'item', (('gold', '20'), ('items', items(HERB, ANTIDOTE))),
          SELL + (pick(CURSOR, 2), to('a', 0x00), wait(W_YESNO, QUIET), to('a', W_SHOP)),
          gold=26, items=BASE_ITEMS + (ANTIDOTE,), equip=0x0003, wram={QTY_MAX: 0},
          windows=(W_COMMAND, W_SHOP, W_SELL, W_YESNO, W_SHOP)),
    Scene('sell-multi', '약초 3개 팔기(개수 창 위 세 번이어도 최대 3)', 'item',
          (('gold', '20'), ('items', items(HERB, HERB, HERB, ANTIDOTE))),
          SELL + (pick(CURSOR, 2), to('a', W_QTY), see(QTY_MAX, QTY_SELL | QTY_OPEN | 3), press('up', 3),
                  see(DIGIT, 0x05),
                  to('a', W_YESNO), to('a', W_SHOP)),
          gold=38, items=BASE_ITEMS + (ANTIDOTE,), equip=0x0003, wram={QTY_MAX: 0},
          windows=(W_COMMAND, W_SHOP, W_SELL, W_QTY, W_YESNO, W_SHOP)),
    Scene('sell-equipped', '장비한 천 옷 팔기: 알림 ▼ 에서 멈춘 뒤 7G, 장비 비트가 남은 칸을 따라 당겨짐', 'item',
          (('gold', '20'), ('items', items(HERB))),
          SELL + (pick(CURSOR, 0, 'up'), to('a', 0x00), stays(QUIET), to('a', W_YESNO), to('a', W_SHOP)),
          gold=27, items=(0x00, HERB), equip=0x0001, wram={QTY_MAX: 0},
          windows=(W_COMMAND, W_SHOP, W_SELL, W_YESNO, W_SHOP)),
    Scene('sell-qty-no', '약초 2개를 고른 뒤 아니요(B): 팔기 목록으로, 개수($0F2C) 0 으로', 'item',
          (('gold', '20'), ('items', items(HERB, HERB))),
          SELL + (pick(CURSOR, 2), to('a', W_QTY), press('up', 1), see(DIGIT, 0x04), to('a', W_YESNO),
                  to('b', 0x00), to('a', W_SELL)),
          gold=20, items=BASE_ITEMS + (HERB, HERB), equip=0x0003, wram={QTY_MAX: 0},
          windows=(W_COMMAND, W_SHOP, W_SELL, W_QTY, W_YESNO, W_SELL)),
    Scene('sell-back', '팔기 목록에서 B 로 가게 창', 'item', (('gold', '20'), ('items', items(HERB))),
          SELL + (to('b', W_SHOP),),
          gold=20, items=BASE_ITEMS + (HERB,), equip=0x0003,
          windows=(W_COMMAND, W_SHOP, W_SELL, W_SHOP)),
    Scene('armor-equip', '나무 모자를 사고 바로 장비(120G)', 'armor', (('gold', '1000'),),
          BUY + (pick(ITEM, WOOD_HAT), to('a', W_YESNO), to('a', 0x00), to('a', W_YESNO), to('a', W_SHOP)),
          gold=880, items=BASE_ITEMS + (WOOD_HAT,), equip=0x0007,
          windows=(W_COMMAND, W_SHOP, W_PARTNER, W_YESNO, W_YESNO, W_SHOP)),
    Scene('armor-cannot-equip', '$0F21 = 3 을 남긴 채 장비할 수 없는 체인 메일 사기: 한 벌만(350G)', 'armor',
          (('gold', '1000'),),
          BUY + (poke(QTY, 3), pick(ITEM, CHAIN_MAIL), see(QTY, 3), to('a', W_YESNO), to('a', 0x00), to('a', W_YESNO),
                 to('a', W_SHOP)),
          gold=650, items=BASE_ITEMS + (CHAIN_MAIL,), equip=0x0003,
          windows=(W_COMMAND, W_SHOP, W_PARTNER, W_YESNO, W_YESNO, W_SHOP)),
]


class Fail(Exception):
    pass


class Driver:
    """한 프레임씩 돌리며 창을 따라간다. step(buttons) 는 한 프레임, rd(addr) 는 WRAM 한 바이트."""

    def __init__(self, step, rd, frame=lambda: 0, shot=None):
        self._step, self.rd, self.frame, self.shot = step, rd, frame, shot
        self.raw, self.same, self.window = None, 0, None
        self.path, self.log = [], []

    def step(self, buttons=()):
        self._step(set(buttons))
        v = self.rd(WINDOW)
        self.same = self.same + 1 if v == self.raw else 1
        self.raw = v
        if self.same == STABLE and v != self.window:
            self.window = v
            self.path.append(v)
            self.log.append((self.frame(), f'{v:02X}'))
            if self.shot:
                self.shot(len(self.path), v)

    def face_up(self, x, y):
        """위를 한 번 짧게 눌러(한 걸음보다 짧게) 카운터를 보게 하고 (x, y) 에 섰는지 본다."""
        for _ in range(FACE[0]):
            self.step({'up'})
        self.idle(FACE[1])
        if (self.rd(X), self.rd(Y)) != (x, y):
            raise Fail(f'카운터 앞 ({x},{y}) 이 아니라 ({self.rd(X)},{self.rd(Y)}) 에 섬')

    def idle(self, n):
        for _ in range(n):
            self.step()

    def tap(self, button):
        for _ in range(TAP[0]):
            self.step({button})
        for _ in range(TAP[1]):
            self.step()

    def to(self, button, windows):
        """windows 가운데 한 창이 될 때까지 button 을 톡톡 누른다. 처음 창과 PASS 밖의 창에 서면 실패.
        창 번호가 목표가 된 프레임에 바로 손을 뗀다: 8프레임 그대로이기를 기다리며 누르면 새 창이 그 버튼을 받는다
        (돈이 모자란 뒤의 가게 창에서 A 가 「사기」 를 골라 목록으로 돌아갔음)."""
        start, frames, n = self.window, 0, 0
        while self.window not in windows:
            if self.window not in PASS and self.window != start:
                raise Fail(f'{button} 을 누르다 {self.window:02X} 창에 섬(기대 {"/".join(f"{w:02X}" for w in windows)})')
            if frames >= STEP_LIMIT:
                raise Fail(f'{STEP_LIMIT} 프레임 안에 {"/".join(f"{w:02X}" for w in windows)} 창이 되지 않음')
            if self.raw in windows:
                self.step()
            else:
                self.step({button} if n % sum(TAP) < TAP[0] else set())
                n += 1
            frames += 1
        self.idle(SETTLE)

    def pick(self, addr, value, button):
        for _ in range(PICK_LIMIT):
            if self.rd(addr) == value:
                self.idle(SETTLE)
                return
            self.tap(button)
        raise Fail(f'{button} 을 {PICK_LIMIT} 번 눌러도 {addr & 0xFFFF:04X} 가 {value:02X} 이 되지 않음(지금 {self.rd(addr):02X})')

    def run(self, steps, poke_fn):
        for st in steps:
            kind = st[0]
            if kind == 'to':
                self.to(st[1], st[2])
            elif kind == 'pick':
                self.pick(st[1], st[2], st[3])
            elif kind == 'press':
                for _ in range(st[2]):
                    self.tap(st[1])
                self.idle(SETTLE)
            elif kind == 'wait':
                for _ in range(st[2]):
                    if self.window == st[1]:
                        break
                    self.step()
                else:
                    raise Fail(f'누르지 않고 {st[2]} 프레임 안에 {st[1]:02X} 창이 되지 않음(지금 {self.window:02X})')
                self.idle(SETTLE)
            elif kind == 'stays':
                start = self.window
                for _ in range(st[1]):
                    self.step()
                    if self.window != start:
                        raise Fail(f'누르지 않았는데 {start:02X} 창이 {self.window:02X} 로 바뀜')
            elif kind == 'see':
                if self.rd(st[1]) != st[2]:
                    raise Fail(f'{st[1] & 0xFFFF:04X} = {self.rd(st[1]):02X}(기대 {st[2]:02X})')
            elif kind == 'poke':
                poke_fn(st[1], st[2])
            else:
                raise ValueError(kind)


def observed(rd):
    gold = rd(GOLD) | rd(GOLD + 1) << 8 | rd(GOLD + 2) << 16
    held = tuple(b for b in (rd(ITEMS + k) for k in range(12)) if b != 0xFF)
    return {'gold': gold, 'items': held, 'equip': rd(EQUIP) | rd(EQUIP + 1) << 8,
            'qty': rd(QTY), 'qty_max': rd(QTY_MAX), 'kind': rd(SHOP_KIND)}


def judge(scene, seen, path, window, rd):
    """끝 상태를 기대와 견줘 문제 목록."""
    problems = []
    if seen['kind'] != SHOPS[scene.shop][2]:
        problems.append(f'가게 종류 {seen["kind"]}(기대 {SHOPS[scene.shop][2]})')
    if seen['gold'] != scene.gold:
        problems.append(f'금화 {seen["gold"]}(기대 {scene.gold})')
    if seen['items'] != tuple(scene.items):
        problems.append(f'물건 {hexes(seen["items"])}(기대 {hexes(scene.items)})')
    if seen['equip'] != scene.equip:
        problems.append(f'장비 비트 {seen["equip"]:04X}(기대 {scene.equip:04X})')
    got = [w for w in path if w not in PASS]
    if got != list(scene.windows):
        problems.append(f'창 차례 {hexes(got)}(기대 {hexes(scene.windows)})')
    if window != scene.windows[-1]:
        problems.append(f'끝 창 {window if window is None else f"{window:02X}"}(기대 {scene.windows[-1]:02X})')
    for addr, value in scene.wram.items():
        if rd(addr) != value:
            problems.append(f'{addr & 0xFFFF:04X} = {rd(addr):02X}(기대 {value:02X})')
    return problems


def hexes(bs):
    return ' '.join(f'{b:02X}' for b in bs)


def by_name(names):
    table = {s.name: s for s in SCENES}
    unknown = [n for n in names if n not in table]
    if unknown:
        raise SystemExit(f'모르는 장면: {", ".join(unknown)} (있는 것: {", ".join(table)})')
    return [table[n] for n in names]


def run_scene(core_name, rom, scene_name, out, seed=0):
    """한 코어에서 장면 하나: 기록 → 이어 하기 → 카운터 앞 → 입력 열 → 판정. 결과 dict."""
    scene = by_name([scene_name])[0]
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    slot = fx.SaveSlot.new_game(rom)
    slot.place = 'imuru'
    for k, v in scene.sets:
        slot.set(k, v)
    sram = slot.to_sram()
    # Walker 는 out/c.sfc 를 out 을 저장 폴더로 연다: bsnes 가 읽을 c.srm 을 먼저 둔다
    (out / 'c.srm').write_bytes(sram)
    res = {'scene': scene.name, 'core': core_name, 'seed': seed}
    walker = None
    try:
        walker = cc.Walker(str(dq4cores.core_path(core_name)), rom, out, seed)
        # 머신 전체 헤드리스 자리를 기다린 시간은 장면 시간에서 뺀다
        t0 += walker.c.slot.waited
        core = walker.c
        fx.load_sram(core, sram)
        if fx.boot(core, slot.goal, step=walker.step) is None:
            return {**res, 'status': 'failed', 'problems': ['이어 하기에서 이무르에 서지 않음'],
                    'seconds': round(time.time() - t0, 1)}
        pins = wc.pins({}, seed)
        walker.warp(SHOPS[scene.shop][0], pins, cc.sets(pins))
        res['at'] = [core.rd(0x7E3020), core.rd(0x7E3080)]
        res['start_frame'] = core.n

        def shot(k, w):
            core.shot(out / f'{k:02d}-{w:02X}.png')

        drv = Driver(walker.step, core.rd, lambda: core.n, shot)
        problems = []
        try:
            drv.face_up(*SHOPS[scene.shop][1])
            drv.run(scene.steps, lambda a, v: core.poke([(a, v)]))
            drv.idle(STABLE)
        except Fail as e:
            problems.append(f'입력: {e}')
        core.shot(out / 'end.png')
        seen = observed(core.rd)
        problems += judge(scene, seen, drv.path, drv.window, core.rd)
        res.update(path=[NAMES.get(w, f'{w:02X}') for w in drv.path], windows=drv.log, end_frame=core.n,
                   frames=core.n - res['start_frame'], gold=seen['gold'], items=hexes(seen['items']),
                   equip=f'{seen["equip"]:04X}',
                   wram_sha1=hashlib.sha1(bytes(core.wram()[:0x20000])).hexdigest())
    finally:
        if walker is not None:
            fx.close(walker.c)
    res.update(status='failed' if problems else 'passed', problems=problems, seconds=round(time.time() - t0, 1))
    return res


def _job(args):
    core_name, rom, scene_name, out, seed = args
    try:
        return run_scene(core_name, rom, scene_name, out, seed)
    except Exception as e:  # 한 장면이 죽어도 나머지는 결과를 남긴다
        return {'scene': scene_name, 'core': core_name, 'seed': seed, 'status': 'failed',
                'problems': [f'{type(e).__name__}: {e}']}


def deterministic(a, b):
    """같은 입력 두 번의 결과가 같은지: 창 차례(프레임 포함)와 끝 WRAM."""
    keys = ('windows', 'end_frame', 'wram_sha1')
    return all(a.get(k) == b.get(k) for k in keys)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--rom', required=True, type=Path)
    ap.add_argument('--out', required=True, type=Path)
    ap.add_argument('--core', choices=('all', *cc.CORES), default='all')
    ap.add_argument('--only', help='장면 이름(쉼표)')
    ap.add_argument('--jobs', type=int, default=4, help='함께 도는 코어 프로세스(기본 4)')
    ap.add_argument('--once', action='store_true', help='같은 입력 두 번 견주기를 끔')
    ap.add_argument('--list', action='store_true', help='장면 목록만 찍음')
    group = ap.add_mutually_exclusive_group()
    group.add_argument('--seed', type=int, help='순간이동 뒤 난수 시드(기본 0)')
    group.add_argument('--seeds', help='시드 여럿(쉼표)')
    args = ap.parse_args()
    if args.list:
        for s in SCENES:
            print(f'{s.name:16} {s.shop:6} {s.title}')
        return 0
    seeds = wc.seeds_of(args)
    scenes = by_name(args.only.split(',')) if args.only else SCENES
    rom = args.rom.resolve()
    out = args.out.resolve()
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f'{out} is not empty')
    names = list(cc.CORES) if args.core == 'all' else [args.core]
    for name in names:
        if not dq4cores.core_path(name).exists():
            raise SystemExit(f'{dq4cores.core_path(name)} 가 없음: sfc/dq4/tools/dq4cores.py 로 빌드하거나 '
                             f'{cc.CORES[name]} 로 코어 파일을 줌')
    t0 = time.time()
    fx.SaveSlot.new_game(rom)  # 밑판을 먼저 한 번 만들어 프로세스들이 함께 만들지 않게
    runs = (1,) if args.once else (1, 2)
    jobs = [(name, rom, s.name, out / f'seed-{seed}' / name / s.name / f'run{r}', seed)
            for seed in seeds for name in names for s in scenes for r in runs]
    with concurrent.futures.ProcessPoolExecutor(max_workers=max(1, min(args.jobs, 4))) as pool:
        results = list(pool.map(_job, jobs))
    report = {'rom_sha1': hashlib.sha1(rom.read_bytes()).hexdigest(),
              'cores': {n: dq4cores.sha256(dq4cores.core_path(n)) for n in names}, 'scenes': []}
    rows = []
    for seed in seeds:
        for s in scenes:
            row = {'scene': s.name, 'title': s.title, 'seed': seed}
            for name in names:
                mine = [r for r in results if r['scene'] == s.name and r['core'] == name and r['seed'] == seed]
                first = mine[0]
                problems = []
                for k, r in enumerate(mine[1:], 2):
                    problems += [f'{k}번째: {p}' for p in r['problems']]
                problems += first['problems']
                if len(mine) > 1 and all(r['status'] == 'passed' for r in mine) and not deterministic(mine[0], mine[1]):
                    problems.append(f'같은 입력 두 번이 다름: 끝 프레임 {mine[0].get("end_frame")}/{mine[1].get("end_frame")}, '
                                    f'WRAM {mine[0].get("wram_sha1", "")[:8]}/{mine[1].get("wram_sha1", "")[:8]}')
                row[name] = {**first, 'problems': problems, 'status': 'failed' if problems else 'passed'}
            rows.append(row)
    report['scenes'] = rows
    report['status'] = 'passed' if all(r[n]['status'] == 'passed' for r in rows for n in names) else 'failed'
    report['seconds'] = round(time.time() - t0, 1)
    (out / 'results.json').write_text(json.dumps(report, ensure_ascii=False, indent=1) + '\n')
    for r in rows:
        cells = []
        for n in names:
            c = r[n]
            cells.append(f'{n} {"통과" if c["status"] == "passed" else "실패"} {c.get("frames", "-")}f {c.get("seconds", "-")}s')
        print(f'{r["scene"]:16} seed {r["seed"]} | ' + ' | '.join(cells))
        for n in names:
            for p in r[n]['problems']:
                print(f'    {n}: {p}')
    print(json.dumps({'status': report['status'], 'rom_sha1': report['rom_sha1'], 'seconds': report['seconds']},
                     ensure_ascii=False))
    return 0 if report['status'] == 'passed' else 1


if __name__ == '__main__':
    sys.exit(main())
