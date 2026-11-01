"""장면 검사의 출발점을 저장 기록(SRAM)으로 만든다: 기록 칸 하나를 원하는 값으로 고쳐 넣고, 전원부터 「이어 하기」로
그 자리에 선다. 서장(약 1만8천 프레임)을 걷지 않고 1장의 어느 자리에서든 시작할 수 있다. 형식은
sfc/dq4/docs/dq4-savefixture-format.md.

- SRAM 형식은 DQ5 그대로(sfc/dq5/tools/dq5sram.py): 칸 하나 = WRAM 7E:2000~2A9F, 끝 워드가 체크섬(25:8450).
  켤 때 25:81CF 가 체크섬이 틀린 칸을 지운다.
- 밑판은 새 게임이 첫 기록을 쓴 SRAM(snes9x 로 롬마다 한 번 돌려 원래 체크아웃 work/cache/states/ 에 둔다).
- 이어 할 자리: 7E:2033 bit0-6 = ルーラ 칸, 25:85D5[칸] = 그룹, 25:8621 의 6바이트 항목([BC][BD][X][Y][층][198E])
  중 그 그룹의 첫 것(없으면 항목 0). bit7 이 서 있으면 밤(25:8278 이 시각 075E 를 0190, 아니면 0050 으로).
- 저장되지 않는 것(난수 075B~D, 시각, 주인공 칸·방향, 인물 위치)은 boot 뒤 core.poke 나
  dq4compatcheck.Walker.warp 로 둔다.

  python sfc/dq4/tools/dq4savefixture.py make --rom work/ch1/dq4-ch1-full.sfc --out work/fx/imuru.srm \\
      --set place=imuru --set gold=1000 --set effect=hoimin --set flag=HOIMIN
  python sfc/dq4/tools/dq4savefixture.py check --rom work/ch1/dq4-ch1-full.sfc --out work/savefixture

라이브러리:
  slot = SaveSlot.new_game(rom)          # 밑판(캐시)
  slot.place = 'imuru'; slot.gold = 1000; slot.flags.add('HOIMIN')
  core = open_core(core_path, rom, sysdir, slot.to_sram())
  arrived = boot(core, slot.goal)        # 맵에 선 프레임
"""
import argparse
import ctypes as C
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[1] / 'dq5' / 'tools')]

import dq4cores  # noqa: E402
import dq4compatcheck as cc  # noqa: E402
import dq4ch1walkcheck as wc  # noqa: E402
import dq4prologuecheck as pc  # noqa: E402
from dq4libretro import Core  # noqa: E402
from dq5sram import MAGIC, MAGIC_COPY, SIZE, SLOT_SIZE, SLOTS, STATUS, SUM_AT, USED, checksum  # noqa: E402

WRAM_BASE = 0x2000
LAST_SAVED = 0xC0              # 칸 상태: 마지막으로 기록한 칸(이어 하기 커서가 여기 선다)
PLACE = 0x2033
NIGHT_BIT = 0x80
GOLD = 0x2019                  # 3바이트
HERO = 0x2040                  # 일행 기록 0(42바이트)
HP, MAX_HP, MP, MAX_MP, LEVEL, ITEMS = 0x02, 0x0E, 0x04, 0x10, 0x12, 0x16
ITEM_SLOTS, NO_ITEM = 12, 0xFF
SLOT_TABLE, SLOT_TABLE_ALT, SLOT_COUNT = 0x2585D5, 0x2585EB, 22
PLACE_TABLE, PLACE_ROW = 0x258621, 6
# 새 게임 첫 기록은 약 964프레임에 쓰인다(snes9x). 넉넉히 기다린다
NEW_GAME_FRAMES = 1500
# bsnes 115 는 SRAM 을 retro_get_memory_data 로 내주지 않고(nullptr), 저장 폴더의 <롬>.srm 을 켤 때 읽는다.
# 직렬화 상태 안 SRAM 자리(.srm 에 넣은 8KB 가 그대로 나오는 곳을 찾아 잼)
BSNES_SRAM_OFFSET = 558
# 이어 하기 입력: start 로 타이틀을 넘기고 A 를 16프레임마다. 메뉴 첫 줄이 「모험을 한다」, 칸 목록 커서는 마지막 칸
CONTINUE = [('start', 2), ('wait', 10)] + [('a', 2), ('wait', 14)] * 200
# 켤 때 25:81CF 가 칸을 WRAM 에 미리 불러 2000 블록이 거짓으로 같아진다. 맵·칸으로만 도착을 보고, 그 전은 보지 않는다
ARRIVE_FROM, ARRIVE_BY = 300, 3000
NOSUM_FRAMES = 900
NIGHT_TIME = 0x0190            # 25:8278 이 밤 칸에 두는 시각(낮은 0050)
# ルーラ 칸의 이름(dq4fieldtravel.FC_GROUPS 차례로 포팅한 그룹). 이름 없는 칸은 번호로 준다
PLACES = {'batland': 0x36, '바트랜드': 0x36, 'imuru': 0x37, '이무르': 0x37, 'prologue': 0x3C, '서장': 0x3C,
          'santeem': 0x3D, '산트하임': 0x3D}


def lorom(addr):
    return (addr >> 16 & 0x7F) * 0x8000 + (addr & 0x7FFF)


def wram_index(addr):
    """7E:2000~2A9F(또는 하위 16비트) → 칸 안 오프셋. 칸 밖이면 ValueError(저장되지 않음)."""
    a = addr & 0xFFFF if addr >> 16 in (0, 0x7E) else -1
    if not WRAM_BASE <= a < WRAM_BASE + SUM_AT:
        raise ValueError(f'{addr:06X} 은 기록 칸(7E:2000~2A9D) 밖: 이어 한 뒤 core.poke 로 둔다')
    return a - WRAM_BASE


def place_rows(rom):
    """{ルーラ 칸: (그룹, (BC, BD, X, Y, 층, 198E) 또는 None)}. 칸의 그룹을 자리 표에서 찾은 첫 항목. 표에 없는 그룹의
    칸으로 이어 하면 필드에 선다(1장 롬 칸 11·16 실측) — 전멸 뒤(01:899F)와 달리 항목 0 으로 가지 않는다."""
    table = SLOT_TABLE if rom[0x8001] else SLOT_TABLE_ALT
    groups = rom[lorom(table):lorom(table) + SLOT_COUNT]
    rows, t = [], lorom(PLACE_TABLE)
    while rom[t] != 0xFF:
        rows.append(tuple(rom[t:t + PLACE_ROW]))
        t += PLACE_ROW
    return {k: (g, next((r for r in rows if r[0] == g), None)) for k, g in enumerate(groups)}


def place_slot(rom, place):
    """이름(PLACES)·그룹 이름·칸 번호 → ルーラ 칸 번호."""
    if isinstance(place, int):
        return place
    if re.fullmatch(r'\d+', place):
        return int(place)
    group = PLACES[place]
    return next(k for k, (g, _) in place_rows(rom).items() if g == group)


def frame_sram(slots, last=None):
    """맨바닥 SRAM: 머리 두 곳, 쓰는 칸 비트, 마지막 칸 상태, 칸마다 체크섬을 맞춘 블록. slots = {칸 번호(0~2): 블록}."""
    s = bytearray(SIZE)
    s[0:len(MAGIC)] = MAGIC
    s[MAGIC_COPY:MAGIC_COPY + len(MAGIC)] = MAGIC
    last = max(slots) if last is None else last
    for n, blk in slots.items():
        blk = bytearray(blk)
        total = checksum(blk)
        blk[SUM_AT], blk[SUM_AT + 1] = total & 0xFF, total >> 8
        s[SLOTS[n]:SLOTS[n] + SLOT_SIZE] = blk
        s[USED] |= 1 << n
        s[STATUS + n] = LAST_SAVED if n == last else 0
    return bytes(s)


def main_checkout():
    try:
        first = subprocess.run(['git', 'worktree', 'list', '--porcelain'], cwd=HERE, capture_output=True,
                               text=True, check=True).stdout.splitlines()[0]
        return Path(first.removeprefix('worktree '))
    except (subprocess.CalledProcessError, IndexError, FileNotFoundError):
        return HERE.parents[2]


def cache_dir():
    return Path(os.environ.get('DQ4_STATES_CACHE') or main_checkout() / 'work' / 'cache' / 'states')


class SaveSlot:
    """기록 칸 하나(7E:2000~2A9F 의 AA0 바이트). 값을 고친 뒤 to_sram() 으로 SRAM 8KB 를 만든다."""

    def __init__(self, block, rom):
        if len(block) != SLOT_SIZE:
            raise ValueError(f'칸은 {SLOT_SIZE:X} 바이트')
        self.block = bytearray(block)
        self.rom = bytes(rom)

    @classmethod
    def new_game(cls, rom_path, core_path=None):
        rom = Path(rom_path).read_bytes()
        return cls(base_block(new_game_sram(rom_path, core_path)), rom)

    def _get(self, addr, n=1):
        i = wram_index(addr)
        return int.from_bytes(self.block[i:i + n], 'little')

    def _put(self, addr, value, n=1):
        i = wram_index(addr + n - 1) - (n - 1)
        self.block[i:i + n] = value.to_bytes(n, 'little')

    def poke(self, addr, value):
        self._put(addr, value)

    def apply_sets(self, text):
        """dq5warp.lua SET 꼴(`2058=CD;2223|08;…`, = | &)."""
        for a, op, v in re.findall(r'(\w+)([=|&])(\w+)', text or ''):
            addr, val = int(a, 16), int(v, 16)
            old = self._get(addr)
            self.poke(addr, val if op == '=' else old | val if op == '|' else old & val)

    @property
    def gold(self):
        return self._get(GOLD, 3)

    @gold.setter
    def gold(self, value):
        self._put(GOLD, value, 3)

    def hero(self, field, n=1):
        return self._get(HERO + field, n)

    def set_hero(self, level=None, hp=None, max_hp=None, mp=None, max_mp=None, items=None):
        for field, v, n in ((LEVEL, level, 1), (HP, hp, 2), (MAX_HP, max_hp, 2), (MP, mp, 2), (MAX_MP, max_mp, 2)):
            if v is not None:
                self._put(HERO + field, v, n)
        if items is not None:
            if len(items) > ITEM_SLOTS:
                raise ValueError(f'물건은 {ITEM_SLOTS} 칸')
            for k in range(ITEM_SLOTS):
                self._put(HERO + ITEMS + k, items[k] if k < len(items) else NO_ITEM)

    def items(self):
        return [b for b in (self.hero(ITEMS + k) for k in range(ITEM_SLOTS)) if b != NO_ITEM]

    def set_party(self, kinds):
        """동료 종류(`05` 호이민 등, dq4compatcheck.party_pokes). 주인공 뒤에 차례로."""
        for a, v in cc.party_pokes(kinds, self.rom):
            self.poke(a, v)

    def effect(self, name):
        """dq4ch1walkcheck.EFFECTS 의 앞 구간이 기록에 남기는 것(호이민 합류, 우물 상자)."""
        e = wc.EFFECTS[name]
        if 'party' in e:
            self.set_party(e['party'])
        self.apply_sets(e.get('set', ''))

    def flag(self, name, on=True):
        addr, mask = wc.FLAGS[name]
        old = self._get(addr)
        self.poke(addr, old | mask if on else old & ~mask & 0xFF)

    def flags(self):
        return sorted(k for k, (a, m) in wc.FLAGS.items() if self._get(a) & m)

    @property
    def place(self):
        return self._get(PLACE) & ~NIGHT_BIT & 0xFF

    @place.setter
    def place(self, value):
        slot = place_slot(self.rom, value)
        if not 0 <= slot < SLOT_COUNT:
            raise ValueError(f'ルーラ 칸은 0~{SLOT_COUNT - 1}')
        self.poke(PLACE, self._get(PLACE) & NIGHT_BIT | slot)

    @property
    def night(self):
        return bool(self._get(PLACE) & NIGHT_BIT)

    @night.setter
    def night(self, on):
        self.poke(PLACE, self._get(PLACE) & ~NIGHT_BIT & 0xFF | (NIGHT_BIT if on else 0))

    @property
    def goal(self):
        """이어 하면 설 자리 (BC, BD, X, Y)."""
        group, row = place_rows(self.rom)[self.place]
        if row is None:
            raise ValueError(f'ルーラ 칸 {self.place}(그룹 {group:02X})는 자리 표 25:8621 에 없어 이어 하면 필드에 섬: '
                             '표에 있는 칸을 고른다')
        return row[:4]

    def to_block(self):
        blk = bytearray(self.block)
        total = checksum(blk)
        blk[SUM_AT], blk[SUM_AT + 1] = total & 0xFF, total >> 8
        return bytes(blk)

    def to_sram(self, slot=0):
        return frame_sram({slot: self.to_block()})

    def set(self, key, value):
        """CLI --set 하나(`gold=1000`, `party=05`, `flag=HOIMIN`, `flag=-HOIMIN`, `effect=hoimin`, `place=imuru`,
        `night=1`, `level=10`, `hp=99`, `items=CD,01`, `poke=2058=CD;2223|08`)."""
        if key == 'gold':
            self.gold = int(value)
        elif key == 'party':
            self.set_party(value)
        elif key == 'flag':
            for name in value.split(','):
                self.flag(name.lstrip('-'), not name.startswith('-'))
        elif key == 'effect':
            for name in value.split(','):
                self.effect(name)
        elif key == 'place':
            self.place = value
        elif key == 'night':
            self.night = value not in ('0', 'false', '')
        elif key in ('level', 'hp', 'max_hp', 'mp', 'max_mp'):
            self.set_hero(**{key: int(value)})
        elif key == 'items':
            self.set_hero(items=[int(x, 16) for x in value.split(',') if x])
        elif key == 'poke':
            self.apply_sets(value)
        else:
            raise ValueError(f'모르는 값: {key}')


def saved_slots(sram):
    """머리가 맞고 쓰는 칸 비트가 서 있고 체크섬이 맞는 칸 번호들(켤 때 SRAM 은 아무 값이나 들어 있다)."""
    if sram[:len(MAGIC)] != MAGIC:
        return []
    return [n for n, off in enumerate(SLOTS) if sram[USED] & 1 << n and
            checksum(sram[off:off + SLOT_SIZE]) == sram[off + SUM_AT] | sram[off + SUM_AT + 1] << 8]


def base_block(sram):
    """새 게임 SRAM 에서 마지막으로 기록한 칸."""
    used = saved_slots(sram)
    if not used:
        raise ValueError('쓰인 칸이 없음')
    n = max(used, key=lambda k: sram[STATUS + k] & 0x80)
    return sram[SLOTS[n]:SLOTS[n] + SLOT_SIZE]


def sram_ptr(core):
    size = core.lib.retro_get_memory_size(0)
    return (C.c_ubyte * size).from_address(core.lib.retro_get_memory_data(0)) if size else None


def read_sram(core):
    view = sram_ptr(core)
    if view is not None:
        return bytes(view[:SIZE])
    return core.save()[0][BSNES_SRAM_OFFSET:BSNES_SRAM_OFFSET + SIZE]


def open_core(core_path, rom, sysdir, sram=None):
    """코어를 열고 SRAM 을 넣는다. bsnes 는 켤 때 저장 폴더(sysdir)의 <롬 이름>.srm 을 읽으므로 열기 전에 파일로,
    snes9x 는 열린 뒤 retro_get_memory_data(0) 에 쓴다. 둘 다 넣은 SRAM 이 그대로 보이는지 맞춰 본다."""
    sysdir = Path(sysdir)
    sysdir.mkdir(parents=True, exist_ok=True)
    srm = sysdir / (Path(rom).stem + '.srm')
    if sram is not None:
        srm.write_bytes(sram)
    elif srm.exists():
        srm.unlink()
    core = Core(str(core_path), str(rom), str(sysdir))
    if sram is not None:
        view = sram_ptr(core)
        if view is not None:
            C.memmove(view, sram, SIZE)
        if read_sram(core) != sram:
            raise RuntimeError(f'{core.name}: 넣은 SRAM 이 코어에 보이지 않음')
    return core


def close(core):
    """게임을 내린다. 한 프로세스의 Core 는 같은 dylib 의 전역 상태를 나눠 쓰므로, 다음 Core 를 열기 전에 부른다
    (bsnes 는 내리지 않고 다음 게임을 열면 저장 폴더의 .srm 대신 앞 게임의 SRAM 이 남는다)."""
    core.lib.retro_unload_game()


def boot(core, goal, settle=90, step=None):
    """전원 직후의 코어에서 이어 하기 입력을 넣고, 맵·칸이 goal(BC, BD, X, Y)이 된 프레임을 돌려준다(못 서면 None).
    그 뒤 settle 프레임을 더 돌린다. step 은 한 프레임 돌리는 함수(dq4compatcheck.Walker.step 등)."""
    step = step or core.run
    script = [b for b, f in CONTINUE for _ in range(f)]
    arrived = None
    while core.n < ARRIVE_BY:
        b = script[core.n] if core.n < len(script) else 'wait'
        step(set() if b == 'wait' else {b})
        if core.n >= ARRIVE_FROM and (core.rd(0x7E00BC), core.rd(0x7E00BD), core.rd(0x7E3020), core.rd(0x7E3080)) == tuple(goal):
            arrived = core.n
            break
    if arrived is None:
        return None
    for _ in range(settle):
        step(set())
    return arrived


def new_game_sram(rom_path, core_path=None):
    """새 게임이 첫 기록을 쓴 SRAM. 롬 SHA-1 마다 한 번 snes9x 로 돌려 cache_dir() 에 둔다."""
    rom_path = Path(rom_path)
    sha = hashlib.sha1(rom_path.read_bytes()).hexdigest()
    path = cache_dir() / f'savefixture-newgame-{sha}.srm'
    if path.exists():
        return path.read_bytes()
    core_path = core_path or dq4cores.core_path('snes9x')
    work = cache_dir() / f'savefixture-newgame-{sha}-{os.getpid()}'
    core = open_core(core_path, rom_path, work)
    # dq4compatcheck.Walker.boot 와 같은 부팅 입력(서장 검사의 새 게임)
    ys = [(f, 2) for f in range(900, 1600, 150)]
    held = set()
    written = None
    for n in range(1, NEW_GAME_FRAMES + 1):
        core.run(held)
        held = ({'y'} if any(f <= n < f + ln for f, ln in ys) else
                {'a'} if n < pc.TAP_UNTIL and n % 40 < 4 else set())
        s = read_sram(core)
        if written is None and n >= ARRIVE_FROM and saved_slots(s):
            written = n
        if written is not None and n >= written + 30:
            break
    if written is None:
        raise RuntimeError(f'{NEW_GAME_FRAMES} 프레임 안에 새 게임이 기록을 쓰지 않음')
    close(core)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(f'.{os.getpid()}.tmp')
    tmp.write_bytes(s)
    tmp.replace(path)
    for f in work.iterdir():
        f.unlink()
    work.rmdir()
    return s


def wram_summary(core):
    """이어 한 뒤 WRAM 의 값(검사가 견줌)."""
    w = bytes(core.wram()[:0x20000])
    return {'map': '%02X/%02X' % (w[0xBC], w[0xBD]), 'cell': [w[0x3020], w[0x3080]],
            'gold': int.from_bytes(w[GOLD:GOLD + 3], 'little'), 'party': w[0x201D],
            'flags': sorted(k for k, (a, m) in wc.FLAGS.items() if w[a & 0xFFFF] & m),
            'time': w[0x075E] | w[0x075F] << 8}


# 검사가 고치는 값: 금화·주인공 레벨·HP·셋째 칸 そらとぶくつ·호이민 합류(동료와 flag)·이어 할 자리 이무르
CHECK_SETS = [('gold', '12345'), ('level', '10'), ('hp', '99'), ('max_hp', '99'), ('poke', '2058=CD;2223|08'),
              ('effect', 'hoimin'), ('flag', 'HOIMIN'), ('place', 'imuru')]
# 이어 한 뒤 순간이동하는 곳(탑 안 39/04)
CHECK_WARP = '39/04,46,41'


def check_core(name, rom, out):
    """한 코어에서 (a) 고친 값이 불러온 WRAM 과 같은지 (b) 체크섬이 틀린 칸이 지워지는지 (c) 같은 입력 두 번이
    WRAM 128KB 가 같은지 (d) 이어 한 뒤 순간이동해 도착하는지."""
    path = dq4cores.core_path(name)
    out.mkdir(parents=True, exist_ok=True)
    slot = SaveSlot.new_game(rom)
    for k, v in CHECK_SETS:
        slot.set(k, v)
    sram, block, goal = slot.to_sram(), slot.to_block(), slot.goal
    res, problems = {'core': None, 'goal': list(goal)}, []
    t0 = time.time()

    runs = []
    for tag in ('a', 'b'):
        core = open_core(path, rom, out / tag, sram)
        res['core'] = core.name
        at = boot(core, goal)
        runs.append((at, bytes(core.wram()[:0x20000]), wram_summary(core)))
        core.shot(out / f'{tag}.png')
        close(core)
    at, w, loaded = runs[0]
    res['arrived'] = at
    if at is None:
        problems.append(f'{ARRIVE_BY} 프레임 안에 이어 할 자리 {goal} 에 서지 않음')
    else:
        res['block_diff'] = [f'{WRAM_BASE + i:04X}' for i in range(SUM_AT) if w[WRAM_BASE + i] != block[i]]
        changed = edited_addrs(SaveSlot.new_game(rom), slot)
        bad = [f'{a:04X}' for a in changed if w[a] != block[a - WRAM_BASE]]
        res['edited'] = len(changed)
        if bad:
            problems.append(f'(a) 고친 값이 불러온 WRAM 과 다름: {bad}')
        res['loaded'] = loaded
        if 'HOIMIN' not in loaded['flags'] or loaded['gold'] != 12345:
            problems.append(f'(a) 불러온 flag·금화가 다름: {loaded}')
    res['determinism_diff'] = sum(x != y for x, y in zip(runs[0][1], runs[1][1]))
    if runs[0][0] != runs[1][0] or res['determinism_diff']:
        problems.append(f'(c) 같은 입력 두 번이 다름: 도착 {runs[0][0]}/{runs[1][0]}, WRAM {res["determinism_diff"]} 바이트')

    night = SaveSlot(slot.block, slot.rom)
    night.night = True
    core = open_core(path, rom, out / 'night', night.to_sram())
    at = boot(core, goal, settle=0)
    res['night'] = {'arrived': at, 'time': f'{core.rd(0x7E075E, 2):04X}'}
    if at is None or core.rd(0x7E075E, 2) != NIGHT_TIME:
        problems.append(f'(a) 밤 칸이 밤 시각으로 서지 않음: {res["night"]}')
    close(core)

    bad_sum = bytearray(sram)
    bad_sum[SLOTS[0] + SUM_AT] ^= 0x01
    core = open_core(path, rom, out / 'nosum', bytes(bad_sum))
    # 칸은 켤 때가 아니라 타이틀을 넘겨 기록 목록을 고를 때(snes9x 397프레임) 지워진다
    script = [b for b, f in CONTINUE for _ in range(f)]
    erased = None
    while core.n < NOSUM_FRAMES:
        b = script[core.n]
        core.run(set() if b == 'wait' else {b})
        after = read_sram(core)
        if erased is None and not after[USED] & 1 and not any(after[SLOTS[0]:SLOTS[0] + SLOT_SIZE]):
            erased = core.n
    res['nosum_erased'] = erased
    if erased is None:
        problems.append(f'(b) 체크섬이 틀린 칸이 {NOSUM_FRAMES} 프레임 안에 지워지지 않음(쓰는 칸 {after[USED]:02X})')
    close(core)

    wout = out / 'warp'
    wout.mkdir(exist_ok=True)
    # Walker 는 out/c.sfc 를 out 을 저장 폴더로 연다: bsnes 가 읽을 c.srm 을 먼저 둔다
    (wout / 'c.srm').write_bytes(sram)
    walker = cc.Walker(str(path), rom, wout)
    view = sram_ptr(walker.c)
    if view is not None:
        C.memmove(view, sram, SIZE)
    at = boot(walker.c, goal, step=walker.step)
    if at is None:
        problems.append('(d) 순간이동 앞 이어 하기에서 서지 않음')
    else:
        maps = walker.warp(CHECK_WARP, wc.pins({}), cc.sets(wc.pins({})))
        res['warp'] = {**wram_summary(walker.c), 'frame': walker.c.n}
        if maps[-1] != CHECK_WARP[:5]:
            problems.append(f'(d) 순간이동이 {maps[-1]} 에 섬(기대 {CHECK_WARP[:5]})')
        if 'HOIMIN' not in res['warp']['flags'] or res['warp']['gold'] != 12345 or res['warp']['party'] != 2:
            problems.append(f'(d) 순간이동 뒤 일행·flag·금화가 바뀜: {res["warp"]}')
        walker.c.shot(wout / 'end.png')
    close(walker.c)
    res.update(status='failed' if problems else 'passed', problems=problems, seconds=round(time.time() - t0, 1),
               core_sha256=dq4cores.sha256(path))
    return res


def edited_addrs(before, after):
    return [WRAM_BASE + i for i in range(SUM_AT) if before.block[i] != after.block[i]]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('mode', choices=('make', 'check', '_core'))
    ap.add_argument('--rom', required=True, type=Path)
    ap.add_argument('--out', required=True, type=Path)
    ap.add_argument('--set', action='append', default=[], metavar='KEY=VALUE', help='SaveSlot.set 의 값(여러 번)')
    ap.add_argument('--slot', type=int, default=1, choices=(1, 2, 3), help='make: 넣을 칸')
    ap.add_argument('--core', choices=('all', *cc.CORES), default='all')
    args = ap.parse_args()
    rom = args.rom.resolve()
    if args.mode == 'make':
        slot = SaveSlot.new_game(rom)
        for kv in args.set:
            k, v = kv.split('=', 1)
            slot.set(k, v)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_bytes(slot.to_sram(args.slot - 1))
        print(json.dumps({'out': str(args.out), 'place': slot.place, 'goal': list(slot.goal), 'night': slot.night,
                          'gold': slot.gold, 'flags': slot.flags(), 'items': [f'{b:02X}' for b in slot.items()]},
                         ensure_ascii=False))
        return 0
    out = args.out.resolve()
    if args.mode == '_core':
        res = check_core(args.core, rom, out)
        (out / 'core.json').write_text(json.dumps(res, ensure_ascii=False, indent=1) + '\n')
        return 0 if res['status'] == 'passed' else 1
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f'{out} is not empty')
    names = list(cc.CORES) if args.core == 'all' else [args.core]
    for name in names:
        if not dq4cores.core_path(name).exists():
            raise SystemExit(f'{dq4cores.core_path(name)} 가 없음: sfc/dq4/tools/dq4cores.py 로 빌드하거나 '
                             f'{cc.CORES[name]} 로 코어 파일을 줌')
    t0 = time.time()
    # 밑판을 먼저 한 번 만들어 두 코어 프로세스가 함께 만들지 않게
    SaveSlot.new_game(rom)
    procs = {}
    for name in names:
        (out / name).mkdir(parents=True)
        with (out / name / 'log.txt').open('w') as log:
            procs[name] = subprocess.Popen([sys.executable, __file__, '_core', '--core', name, '--rom', str(rom),
                                            '--out', str(out / name)], stdout=log, stderr=subprocess.STDOUT)
    report = {'rom_sha1': hashlib.sha1(rom.read_bytes()).hexdigest(), 'cores': {}}
    for name, proc in procs.items():
        try:
            proc.wait(timeout=cc.UNIT_TIMEOUT)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        f = out / name / 'core.json'
        report['cores'][name] = (json.loads(f.read_text()) if f.exists() else
                                 {'status': 'failed', 'problems': ['코어 프로세스가 결과를 남기지 않음']})
    report['status'] = 'passed' if all(r['status'] == 'passed' for r in report['cores'].values()) else 'failed'
    report['seconds'] = round(time.time() - t0, 1)
    (out / 'results.json').write_text(json.dumps(report, ensure_ascii=False, indent=1) + '\n')
    print(json.dumps({'status': report['status'], 'rom_sha1': report['rom_sha1'], 'seconds': report['seconds'],
                      **{k: {'status': v['status'], 'arrived': v.get('arrived'), 'problems': v.get('problems')}
                         for k, v in report['cores'].items()}}, ensure_ascii=False))
    return 0 if report['status'] == 'passed' else 1


if __name__ == '__main__':
    sys.exit(main())
