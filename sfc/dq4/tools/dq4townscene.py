"""여관·교회·저장 칸 장면 검사(libretro bsnes·snes9x). 장면마다 저장 기록(dq4savefixture)으로 이무르에서 이어 하고,
여관 주인·신부와 말하거나 타이틀 메뉴를 고른 뒤 WRAM·SRAM 값으로 판정한다. 형식은
sfc/dq4/docs/dq4-town-scene-format.md.

  check     여관(묵기·밤에 묵기·금화 모자람·거절), 교회(되살리기·해독·저주 풀기·계시·기도로 칸 1·2·3 저장과 이어 하기),
            타이틀(기록 복사·지우기, 빈 SRAM, 체크섬이 틀린 칸)
  daynight  필드에서 시각 7E:075E 를 해 질 녘·새벽 경계값마다 붙든 채 걸어(dusk·dawn), 또 붙들지 않고 걸어 넘겨(cross)
            필드 팔레트 2·3번 줄·인물 11·12번 줄·7E:1AA1 이 시각 표(01:A16B)대로 바뀌는지. 낮 끝·밤 첫 값으로 이무르에
            들어서 인물 목록이 낮·밤으로 갈리는지(town_edge)
  oldsave   옛 1장 IPS(비공개 에셋 저장소 이력)로 만든 롬의 새 게임 기록을 지금 롬으로 이어 해 본 결과를 남긴다(판정 없음)

  uv run --locked python sfc/dq4/tools/dq4townscene.py check --rom work/ch1/dq4-ch1-full.sfc --out work/townscene
  uv run --locked python sfc/dq4/tools/dq4townscene.py daynight --rom work/ch1/dq4-ch1-full.sfc --out work/townnight
  DQ4_ASSETS=… uv run --locked python sfc/dq4/tools/dq4townscene.py oldsave --rom work/ch1/dq4-ch1-full.sfc --out work/oldsave

알려진 실패(KNOWN)는 그 문제로만 실패하면 known 으로 쳐 전체가 통과하고, 풀리거나 다르게 실패하면 실패한다.

선택 창은 상태를 저장하고 아래(또는 위)를 눌러 커서 7E:0AD7 이 움직이는지 본 뒤 되돌려 알아본다. 글이 찍히는 동안 누른
A 가 막 뜬 창을 고르는 일 없이, 창마다 정한 칸을 고른다.
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(HERE), str(HERE.parents[1] / 'dq5' / 'tools'), str(ROOT / 'fc' / 'dq4' / 'tools')]

import dq4cores  # noqa: E402
import dq4compatcheck as cc  # noqa: E402
import dq4ch1walkcheck as wc  # noqa: E402
import dq4savefixture as fx  # noqa: E402
from dq5sram import MAGIC, SLOT_SIZE, SLOTS, STATUS, SUM_AT, USED, checksum  # noqa: E402

CURSOR = 0x7E0AD7              # 고르기 창의 커서 칸(교회 메뉴·예/아니요·기록 목록·타이틀 메뉴)
TALKING = 0x7E0F20             # 여관·교회 처리기가 도는 동안 0 이 아님
INN_TOTAL = 0x7E0F28           # 여관이 셈한 값(1인 값 × 일행 수)
TIME = 0x7E075E
PARTY_COUNT = 0x7E201D
RECORD, RECORD_SIZE = 0x7E2040, 42
STATE, HP, MP, EXP, MAX_HP, MAX_MP, LEVEL, NEXT_EXP = 0x01, 0x02, 0x04, 0x0B, 0x0E, 0x10, 0x12, 0x26
ALIVE, POISON, CURSE = 0x80, 0x20, 0x08
MORNING, NIGHT_START = 0x0050, 0x00F0
# 프로브: 누르고 기다린 뒤 커서를 본다. 고르기 창은 누른 지 몇 프레임 안에 커서를 옮긴다
PROBE_HOLD, PROBE_WAIT, PROBE_EVERY = 6, 14, 5
# 글 넘기기 A 의 주기와 누르는 길이. 고르기 창이 뜨면 다음 A 전에 프로브가 먼저 알아본다. 필드 명령 창은 7E:007F & 7 = 0
# 인 프레임에만 입력을 읽으므로(dq4npccheck.TALKS) 8프레임을 눌러야 빠지지 않는다
ADVANCE_EVERY, ADVANCE_HOLD = 40, 8
# 이무르 37/00: 이어 하면 교회 신부(50,7) 아래 (50,9) 에 선다. 여관 주인(34,37)은 카운터 너머라 (34,41) 에 내려 위로 한
# 걸음 걸어 (34,40) 에서 말한다
IMURU = 'imuru'
INN_WARP = '37/00,34,40'
INN_FC = (0x12, 0x00)          # FC 이무르 그룹·맵(dq4shop.inn_price)
HOIMIN = '05'
# 이어 한 뒤 기록 칸과 다를 수 있는 바이트(맵에 들어설 때 게임이 고침, dq4-savefixture-format.md)
REWRITTEN = {0x2193, 0x21C7, 0x21CB, 0x21CC}
# 교회 메뉴 칸
PRAY, ORACLE, REVIVE, CURE, UNCURSE = range(5)
# 타이틀 메뉴(기록이 있을 때): 모험을 한다·설정을 바꾼다·만든다·복사한다·지운다
TITLE_COPY, TITLE_ERASE = 3, 4


class Probe:
    """한 코어의 입력·고르기 창 알아보기. step 은 한 프레임 돌리는 함수(Walker.step 이면 bsnes cheat 도 이어 감)."""

    def __init__(self, core, step=None):
        self.c = core
        self.step = step or core.run

    def press(self, key, hold, wait=0):
        for _ in range(hold):
            self.step({key})
        for _ in range(wait):
            self.step(set())

    def idle(self, frames):
        self.press('wait', 0, frames)

    def choosing(self):
        """고르기 창이 입력을 기다리는지. 상태를 저장해 아래·위를 눌러 보고 커서가 움직였는지 본 뒤 되돌린다."""
        st, before = self.c.save(), self.c.rd(CURSOR)
        for key in ('down', 'up'):
            for _ in range(PROBE_HOLD):
                self.c.run({key})
            for _ in range(PROBE_WAIT):
                self.c.run(set())
            moved = self.c.rd(CURSOR) != before
            self.c.load(st)
            if moved:
                return True
        return False

    def pick(self, target):
        """커서를 target 에 두고 A. 다다르지 못하면 False. 글 넘기기 A 를 누른 채로 창이 뜨면 이어 누른 A 는 새 입력이
        아니라 먹히지 않으므로 먼저 뗀다."""
        self.idle(12)
        for _ in range(16):
            at = self.c.rd(CURSOR)
            if at == target:
                self.press('a', ADVANCE_HOLD, 30)
                return True
            self.press('down' if at < target else 'up', ADVANCE_HOLD, 12)
        return False

    def converse(self, answers, default=None, limit=2500, watch=None, talk=True, until=None):
        """대화를 끝까지: 고르기 창마다 answers 를 차례로 고르고, 다 쓰면 default(칸 번호, 'b' 면 B 로 닫음).
        default 가 None 이면 답을 다 쓴 뒤로는 프로브하지 않는다. bsnes 는 여관의 잠드는 연출(소리 손잡기를 기다림)
        도중에 상태를 저장·되돌리면 그 손잡기가 풀리지 않아 멈췄다(같은 입력을 프로브 없이 넣으면 끝까지 감).
        talk 면 여관·교회 처리기(7E:0F20)가 돌다 멈춘 프레임에서, until() 이 참이 된 프레임에서 끝낸다.
        watch(frame) 는 프레임마다 부른다.
        돌려주는 것: {'choices': [(프레임, 고른 칸, 창이 뜰 때의 커서)], 'ended': 프레임 또는 None}."""
        choices, began, t0 = [], None, self.c.n
        while self.c.n - t0 < limit:
            if until and until():
                return {'choices': choices, 'ended': self.c.n}
            if talk:
                if self.c.rd(TALKING):
                    began = began or self.c.n
                elif began is not None:
                    return {'choices': choices, 'ended': self.c.n}
            probing = default is not None or len(choices) < len(answers)
            if probing and (self.c.n - t0) % PROBE_EVERY == 0 and self.choosing():
                k = len(choices)
                target = answers[k] if k < len(answers) else default
                choices.append((self.c.n, target, self.c.rd(CURSOR)))
                if target is None or target == 'b':
                    self.press('b', ADVANCE_HOLD, 30)
                elif not self.pick(target):
                    choices[-1] = (self.c.n, f'{target} 에 닿지 못함', choices[-1][2])
                    return {'choices': choices, 'ended': None}
                continue
            self.step({'a'} if (self.c.n - t0) % ADVANCE_EVERY < ADVANCE_HOLD else set())
            if watch:
                watch(self.c.n)
        return {'choices': choices, 'ended': None}


def record(core, n, field, size=1):
    return core.rd(RECORD + n * RECORD_SIZE + field, size)


def members(core):
    return [{'state': record(core, n, STATE), 'hp': record(core, n, HP, 2), 'max_hp': record(core, n, MAX_HP, 2),
             'mp': record(core, n, MP, 2), 'max_mp': record(core, n, MAX_MP, 2), 'level': record(core, n, LEVEL)}
            for n in range(core.rd(PARTY_COUNT))]


def snapshot(core):
    return {'gold': core.rd(fx.GOLD, 3), 'time': core.rd(TIME, 2), 'party': members(core)}


def slot_block(sram, n):
    return sram[SLOTS[n]:SLOTS[n] + SLOT_SIZE]


def slot_ok(sram, n):
    blk = slot_block(sram, n)
    return bool(sram[USED] & 1 << n) and checksum(blk) == blk[SUM_AT] | blk[SUM_AT + 1] << 8


def block_diff(block, wram, skip=()):
    """기록 칸(AA0)과 WRAM 7E:2000~ 의 다른 주소(체크섬 워드 빼고)."""
    return [f'{fx.WRAM_BASE + i:04X}' for i in range(SUM_AT)
            if block[i] != wram[fx.WRAM_BASE + i] and fx.WRAM_BASE + i not in skip]


def judge_inn(before, after, total, price, stayed, night=False):
    """여관 판정. stayed 면 금화가 1인 값 × 일행 수만큼 줄고 모두 HP·MP 가득, 시각이 아침. 아니면 아무것도 바뀌지 않음."""
    problems = []
    count = len(before['party'])
    if stayed:
        if total != price * count:
            problems.append(f'여관 값 7E:0F28 = {total}(기대 {price} × {count})')
        if before['gold'] - after['gold'] != price * count:
            problems.append(f'금화 {before["gold"]} → {after["gold"]}(기대 {price * count} 줄어듦)')
        for k, m in enumerate(after['party']):
            if m['hp'] != m['max_hp'] or m['mp'] != m['max_mp']:
                problems.append(f'일행 {k} HP {m["hp"]}/{m["max_hp"]} MP {m["mp"]}/{m["max_mp"]}')
        if after['time'] != MORNING:
            problems.append(f'시각 {after["time"]:04X}(기대 아침 {MORNING:04X})')
        if night and before['time'] < NIGHT_START:
            problems.append(f'밤 장면인데 묵기 전 시각 {before["time"]:04X}')
    elif before != after:
        problems.append(f'묵지 않았는데 바뀜: {before} → {after}')
    return problems


def judge_church(before, after, who, cost, want_state):
    """교회 판정: 일행 who 의 상태 바이트가 want_state, 금화가 cost 만큼 줄어듦. 되살리면 HP 가 0 이 아님."""
    problems = []
    m = after['party'][who]
    if m['state'] != want_state:
        problems.append(f'일행 {who} 상태 {before["party"][who]["state"]:02X} → {m["state"]:02X}(기대 {want_state:02X})')
    if want_state & ALIVE and not m['hp']:
        problems.append(f'일행 {who} HP 0')
    if before['gold'] - after['gold'] != cost:
        problems.append(f'금화 {before["gold"]} → {after["gold"]}(기대 {cost} 줄어듦)')
    return problems


def judge_saved(sram_before, sram_after, wram_at_write, slot, others_kept=True):
    """기도 저장 판정: 칸 slot 이 쓰는 칸·체크섬이 맞고, 쓴 순간의 WRAM 7E:2000~2A9D 와 같고, 다른 칸은 그대로."""
    problems = []
    if not slot_ok(sram_after, slot):
        problems.append(f'칸 {slot + 1} 이 쓰는 칸·체크섬이 아님(쓰는 칸 {sram_after[USED]:02X})')
    if wram_at_write is None:
        problems.append(f'칸 {slot + 1} 이 쓰이지 않음')
    else:
        diff = block_diff(slot_block(sram_after, slot), wram_at_write)
        if diff:
            problems.append(f'칸 {slot + 1} 이 쓴 순간의 WRAM 과 다름: {" ".join(diff[:20])}')
    if others_kept:
        for n in range(3):
            if n != slot and slot_block(sram_before, n) != slot_block(sram_after, n):
                problems.append(f'칸 {n + 1} 이 바뀜')
    return problems


def judge_loaded(block, wram):
    """이어 한 WRAM 이 기록 칸과 같은지(맵에 들어설 때 고치는 네 바이트 빼고)."""
    diff = block_diff(block, wram, REWRITTEN)
    return [f'이어 한 WRAM 이 기록 칸과 다름: {" ".join(diff[:20])}'] if diff else []


def corrupt(sram, slot):
    """칸 slot 의 체크섬을 1비트 틀리게."""
    s = bytearray(sram)
    s[SLOTS[slot] + SUM_AT] ^= 0x01
    return bytes(s)


def inn_price(dq4_path):
    import dq4shop
    from kr_patch.fc import ines
    return dq4shop.inn_price(ines.prg(Path(dq4_path).read_bytes()), *INN_FC)


class Town:
    """이무르에서 이어 한 Walker 하나. with 로 닫는다."""

    def __init__(self, core_name, rom, out, slot, warp=None, seed=0):
        out.mkdir(parents=True, exist_ok=True)
        self.sram = slot.to_sram()
        (out / 'c.srm').write_bytes(self.sram)
        self.w = cc.Walker(str(dq4cores.core_path(core_name)), rom, out)
        self.c = self.w.c
        self.out = out
        self.rng = cc.sets(wc.rng_for(seed))
        self.p = Probe(self.c, self.w.step)
        try:
            fx.load_sram(self.c, self.sram)
            self.arrived = fx.boot(self.c, slot.goal, step=self.w.step)
            if self.arrived is None:
                raise RuntimeError(f'이어 할 자리 {slot.goal} 에 서지 않음')
            self.c.poke(self.rng)
            if warp:
                where = self.w.warp(warp, '', self.rng)[-1]
                if where != warp[:5]:
                    raise RuntimeError(f'순간이동이 {where} 에 섬')
        except BaseException:
            fx.close(self.c)
            raise

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        fx.close(self.c)

    def talk(self, answers, default='b', watch=None):
        """위를 보고(서 있는 자리에서 상대가 위) 말을 건다."""
        self.p.press('up', 6, 30)
        return self.p.converse([0] + list(answers), default, watch=watch)


def base_slot(rom):
    slot = fx.SaveSlot.new_game(rom)
    slot.place = IMURU
    slot.gold = 100
    return slot


def put_member(slot, n, **values):
    fields = {'state': (STATE, 1), 'hp': (HP, 2), 'mp': (MP, 2), 'exp': (EXP, 3), 'next_exp': (NEXT_EXP, 3),
              'level': (LEVEL, 1)}
    for k, v in values.items():
        field, size = fields[k]
        slot._put(fx.HERO + n * RECORD_SIZE + field, v, size)


# ---------------------------------------------------------------- 장면

def scene_inn(core, rom, out, seed, kind, dq4):
    """여관: stay(낮), night(밤 → 아침), poor(금화 모자람), refuse(아니요)."""
    price = inn_price(dq4)
    slot = base_slot(rom)
    slot.set_party(HOIMIN)
    put_member(slot, 0, hp=5)
    put_member(slot, 1, hp=1, mp=0)
    if kind == 'night':
        slot.night = True
    if kind == 'poor':
        slot.gold = price * 2 - 1
    with Town(core, rom, out, slot, INN_WARP, seed) as t:
        t.c.poke([(INN_TOTAL, 0), (INN_TOTAL + 1, 0)])
        before = snapshot(t.c)
        # 위로 한 걸음 걸어 카운터 앞에 서고, 그 자리에서 다시 위를 보고 말한다
        t.p.press('up', 6, 30)
        talk = t.talk([1 if kind == 'refuse' else 0], default=None)
        after = snapshot(t.c)
        t.c.shot(out / 'end.png')
        total = t.c.rd(INN_TOTAL, 2)
    problems = [] if talk['ended'] else ['대화가 끝나지 않음']
    problems += judge_inn(before, after, total, price, kind in ('stay', 'night'), kind == 'night')
    return {'problems': problems, 'price': price, 'total': total, 'before': before, 'after': after, **talk}


def scene_church(core, rom, out, seed, kind):
    """교회 되살리기·해독·저주 풀기."""
    slot = base_slot(rom)
    if kind == 'revive':
        slot.set_party(HOIMIN)
        put_member(slot, 1, state=0x00, hp=0)
        who, item, pick_who = 1, REVIVE, 1
    elif kind == 'cure':
        put_member(slot, 0, state=ALIVE | POISON)
        who, item, pick_who = 0, CURE, 0
    else:
        put_member(slot, 0, state=ALIVE | CURSE)
        who, item, pick_who = 0, UNCURSE, 0
    with Town(core, rom, out, slot, seed=seed) as t:
        before = snapshot(t.c)
        talk = t.talk([item, pick_who, 0])
        after = snapshot(t.c)
        t.c.shot(out / 'end.png')
    level = before['party'][who]['level']
    cost = 5 if kind == 'cure' else level * 10
    problems = [] if talk['ended'] else ['대화가 끝나지 않음']
    problems += judge_church(before, after, who, cost, ALIVE)
    return {'problems': problems, 'cost': cost, 'before': before, 'after': after, **talk}


def scene_oracle(core, rom, out, seed):
    """계시: 다음 레벨까지 남은 경험치. 메시지가 그 수를 받는 WRAM 칸을 찾아 기록 값과 견준다."""
    slot = base_slot(rom)
    put_member(slot, 0, exp=0x000100, next_exp=0x00ABCD)
    want = 0x00ABCD - 0x000100
    seen = {}
    def hits(w):
        return {a for a in range(0x2000 - 2) if w[a] | w[a + 1] << 8 | w[a + 2] << 16 == want}

    with Town(core, rom, out, slot, seed=seed) as t:
        # 말하기 전부터 그 값이 있던 자리는 우연이므로 뺀다
        already = hits(bytes(t.c.wram()[:0x2000]))

        def watch(n):
            if not seen:
                found = sorted(hits(bytes(t.c.wram()[:0x2000])) - already)
                if found:
                    seen.update(frame=n, at=[f'{a:04X}' for a in found])
        talk = t.talk([ORACLE], watch=watch)
        t.c.shot(out / 'end.png')
    problems = [] if talk['ended'] else ['대화가 끝나지 않음']
    if not seen:
        problems.append(f'남은 경험치 {want} 가 7E:0000~1FFF 에 나타나지 않음')
    return {'problems': problems, 'want': want, 'seen': seen, **talk}


def scene_save(core, rom, out, seed, n):
    """기도로 칸 n(0~2)에 저장 → 그 SRAM 으로 전원부터 이어 하기."""
    slot = base_slot(rom)
    gold = 3000 + n + 1
    write = {}
    with Town(core, rom, out / 'save', slot, seed=seed) as t:
        t.c.poke([(0x7E0000 | fx.GOLD + k, gold >> 8 * k & 0xFF) for k in range(3)])
        sram_before = fx.read_sram(t.c)

        def watch(frame):
            if 'frame' not in write:
                s = fx.read_sram(t.c)
                if slot_block(s, n) != slot_block(sram_before, n):
                    write.update(frame=frame, wram=bytes(t.c.wram()[:0x20000]))

        talk = t.talk([PRAY, 0, n], default=0, watch=watch)
        sram_after = fx.read_sram(t.c)
        t.c.shot(out / 'save.png')
    problems = [] if talk['ended'] else ['대화가 끝나지 않음']
    problems += judge_saved(sram_before, sram_after, write.get('wram'), n)
    res = {'gold': gold, 'written': write.get('frame'), 'used': f'{sram_after[USED]:02X}',
           'slot_status': [f'{sram_after[STATUS + k]:02X}' for k in range(3)], **talk}
    if problems:
        return {'problems': problems, **res}
    path = dq4cores.core_path(core)
    (out / 'load').mkdir(parents=True, exist_ok=True)
    with fx.closing(fx.open_core(path, rom, out / 'load', sram_after)) as c:
        loaded = continue_from(c, n, slot.goal)
        at = loaded['ended']
        p = Probe(c)
        p.idle(90)
        w = bytes(c.wram()[:0x20000])
        c.shot(out / 'load.png')
    if at is None:
        problems.append(f'이어 하기가 {slot.goal} 에 서지 않음')
    else:
        problems += judge_loaded(slot_block(sram_after, n), w)
        got = int.from_bytes(w[fx.GOLD:fx.GOLD + 3], 'little')
        if got != gold:
            problems.append(f'이어 한 금화 {got}(기대 {gold}, 칸 {n + 1})')
    return {'problems': problems, 'loaded_at': at, 'list_cursor': [x[2] for x in loaded['choices']], **res}


def continue_from(c, n, goal, limit=1500):
    """타이틀에서 「모험을 한다」 → 기록 목록의 칸 n 을 골라 이어 하고 goal(BC, BD, X, Y)에 선 프레임을 돌려준다.
    목록은 쓰인 칸만 차례로 보이고, 처음 커서는 마지막으로 기록한 칸이 아닐 수 있어(교회 기록 뒤 실측) 직접 고른다."""
    used = fx.saved_slots(fx.read_sram(c))
    if n not in used:
        raise ValueError(f'칸 {n + 1} 이 쓰인 칸 {[u + 1 for u in used]} 에 없음')
    p = Probe(c)
    p.press('start', 2, 10)
    at = lambda: (c.rd(0x7E00BC), c.rd(0x7E00BD), c.rd(0x7E3020), c.rd(0x7E3080)) == tuple(goal)  # noqa: E731
    talk = p.converse([0, used.index(n)], default='b', limit=limit, talk=False, until=lambda: c.n >= fx.ARRIVE_FROM and at())
    return talk


def title_core(core, rom, out, sram):
    out.mkdir(parents=True, exist_ok=True)
    return fx.open_core(dq4cores.core_path(core), rom, out, sram)


def scene_copy(core, rom, out, seed):
    """타이틀 「모험의 서를 복사한다」: 칸 1 → 칸 2."""
    slot = base_slot(rom)
    sram = slot.to_sram(0)
    with fx.closing(title_core(core, rom, out, sram)) as c:
        p = Probe(c)
        p.press('start', 2, 10)
        talk = p.converse([TITLE_COPY, 0, 0, 0], default='b', limit=1500, talk=False,
                          until=lambda: fx.read_sram(c)[USED] & 2)
        p.idle(120)
        after = fx.read_sram(c)
        c.shot(out / 'end.png')
    problems = []
    if not slot_ok(after, 1) or slot_block(after, 1)[:SUM_AT] != slot_block(sram, 0)[:SUM_AT]:
        problems.append(f'칸 2 가 칸 1 의 복사가 아님(쓰는 칸 {after[USED]:02X})')
    if slot_block(after, 0) != slot_block(sram, 0):
        problems.append('칸 1 이 바뀜')
    return {'problems': problems, 'used': f'{after[USED]:02X}', **talk}


def scene_erase(core, rom, out, seed):
    """타이틀 「모험의 서를 지운다」: 칸 1·2 중 칸 2."""
    slot = base_slot(rom)
    other = fx.SaveSlot(slot.block, slot.rom)
    other.gold = 2222
    sram = fx.frame_sram({0: slot.to_block(), 1: other.to_block()}, last=0)
    with fx.closing(title_core(core, rom, out, sram)) as c:
        p = Probe(c)
        p.press('start', 2, 10)
        talk = p.converse([TITLE_ERASE, 1, 0], default='b', limit=1500, talk=False,
                          until=lambda: not fx.read_sram(c)[USED] & 2)
        p.idle(120)
        after = fx.read_sram(c)
        c.shot(out / 'end.png')
    problems = []
    if after[USED] & 2:
        problems.append(f'칸 2 의 쓰는 칸 비트가 남음({after[USED]:02X})')
    if not slot_ok(after, 0) or slot_block(after, 0) != slot_block(sram, 0):
        problems.append('칸 1 이 바뀜')
    return {'problems': problems, 'used': f'{after[USED]:02X}', **talk}


def scene_blank(core, rom, out, seed):
    """빈 SRAM(모두 0): 새 게임 입력(dq4savefixture.new_game_sram 과 같음)으로 머리를 쓰고 칸 하나만 기록한다."""
    import dq4prologuecheck as pc
    sram = bytes(fx.SIZE)
    with fx.closing(title_core(core, rom, out, sram)) as c:
        period, held_for = fx.NEW_GAME_TAP
        held, written = set(), None
        while c.n < fx.NEW_GAME_FRAMES:
            c.run(held)
            n = c.n
            held = ({'y'} if any(f <= n < f + ln for f, ln in fx.NEW_GAME_YS) else
                    {'a'} if n < pc.TAP_UNTIL and n % period < held_for else set())
            if written is None and fx.saved_slots(fx.read_sram(c)):
                written = n
        after = fx.read_sram(c)
        c.shot(out / 'end.png')
    problems = []
    used = fx.saved_slots(after)
    if after[:len(MAGIC)] != MAGIC:
        problems.append('머리가 쓰이지 않음')
    if len(used) != 1:
        problems.append(f'쓴 칸 {[u + 1 for u in used]}(기대 하나)')
    return {'problems': problems, 'written': written, 'slots': [u + 1 for u in used]}


def scene_badsum(core, rom, out, seed):
    """칸 1(금화 1111)·칸 2(금화 2222, 마지막 기록)에서 칸 2 체크섬을 틀리게: 칸 2 는 지워지고 칸 1 로 이어 한다."""
    slot = base_slot(rom)
    one, two = fx.SaveSlot(slot.block, slot.rom), fx.SaveSlot(slot.block, slot.rom)
    one.gold, two.gold = 1111, 2222
    sram = corrupt(fx.frame_sram({0: one.to_block(), 1: two.to_block()}, last=1), 1)
    with fx.closing(title_core(core, rom, out, sram)) as c:
        at = fx.boot(c, slot.goal)
        after = fx.read_sram(c)
        gold = c.rd(fx.GOLD, 3)
        c.shot(out / 'end.png')
    problems = []
    if at is None:
        problems.append('칸 1 로 이어 하지 못함')
    if after[USED] & 2 or any(slot_block(after, 1)):
        problems.append(f'체크섬이 틀린 칸 2 가 지워지지 않음(쓰는 칸 {after[USED]:02X})')
    if not slot_ok(after, 0):
        problems.append('칸 1 이 지워짐')
    if at is not None and gold != 1111:
        problems.append(f'이어 한 금화 {gold}(기대 1111)')
    return {'problems': problems, 'arrived': at, 'gold': gold, 'used': f'{after[USED]:02X}'}


# 알려진 실패: 장면 → (까닭, 그때 나는 문제인지 보는 함수). 그 문제로만 실패하면 known 으로 치고, 다르게 실패하거나
# 통과하면 failed — 고쳐지면 여기서 빼라는 뜻이다
def _stuck(problems):
    return problems == ['대화가 끝나지 않음']


def _no_field_color(problems):
    return bool(problems) and all('걸어도' in p for p in problems)


def _no_dusk(problems):
    return len(problems) == 1 and problems[0].startswith('dusk: 밤 인물 표지')


SOUND_STUCK = '소리 패치 롬(dq4-ch1-sound.sfc 이후)은 {} 뒤 기도 문구에서 멈춤(7E:0F20 그대로). 소리 패치 전 dq4-ch1.sfc 는 끝까지 감'
FIELD_COLOR = ('libretro 두 코어에서 1장 필드의 시각 색(01:A055)이 걸어도, 필드를 다시 불러와도 낮 벌 그대로. '
               '원인 미확인(dq4-town-scene-format.md 「남은 것」)')
KNOWN = {
    'church_revive': (SOUND_STUCK.format('되살린'), _stuck),
    'church_cure': (SOUND_STUCK.format('해독한'), _stuck),
    'church_uncurse': (SOUND_STUCK.format('저주를 푼'), _stuck),
    'dusk': (FIELD_COLOR, _no_field_color),
    'dawn': (FIELD_COLOR, _no_field_color),
    'cross': (FIELD_COLOR, _no_dusk),
}

SCENES = {
    'inn_stay': lambda c, r, o, s, a: scene_inn(c, r, o, s, 'stay', a.dq4),
    'inn_night': lambda c, r, o, s, a: scene_inn(c, r, o, s, 'night', a.dq4),
    'inn_poor': lambda c, r, o, s, a: scene_inn(c, r, o, s, 'poor', a.dq4),
    'inn_refuse': lambda c, r, o, s, a: scene_inn(c, r, o, s, 'refuse', a.dq4),
    'church_revive': lambda c, r, o, s, a: scene_church(c, r, o, s, 'revive'),
    'church_cure': lambda c, r, o, s, a: scene_church(c, r, o, s, 'cure'),
    'church_uncurse': lambda c, r, o, s, a: scene_church(c, r, o, s, 'uncurse'),
    'church_oracle': lambda c, r, o, s, a: scene_oracle(c, r, o, s),
    'save_slot1': lambda c, r, o, s, a: scene_save(c, r, o, s, 0),
    'save_slot2': lambda c, r, o, s, a: scene_save(c, r, o, s, 1),
    'save_slot3': lambda c, r, o, s, a: scene_save(c, r, o, s, 2),
    'title_copy': lambda c, r, o, s, a: scene_copy(c, r, o, s),
    'title_erase': lambda c, r, o, s, a: scene_erase(c, r, o, s),
    'title_blank': lambda c, r, o, s, a: scene_blank(c, r, o, s),
    'badsum': lambda c, r, o, s, a: scene_badsum(c, r, o, s),
}


def verdict(name, problems, known=True):
    """passed·known(알려진 실패가 그대로)·failed."""
    if known and name in KNOWN:
        if KNOWN[name][1](problems):
            return 'known'
        if not problems:
            problems.append(f'알려진 실패가 풀림: KNOWN 에서 {name} 을 뺄 것')
        return 'failed'
    return 'failed' if problems else 'passed'


# ---------------------------------------------------------------- 낮밤 경계(daynight)

TIME_TABLE, TIME_ROWS = 0x01A16B, 10     # [하한 16비트][색인 × 2] 항목, 뒤에서부터 하한 ≤ 시각인 첫 항목
TIME_SETS = 0x01A189                     # 색인 × 2 → 뱅크 01 의 벌 주소(60바이트: 2번 줄 색 1~15, 3번 줄 색 1~15)
NIGHT_OBJ, DAY_OBJ = 0x01A422, 0x01A45E  # 인물 11·12번 줄 색 1~15 두 줄(60바이트). 색인 0C 이상이면 밤 쪽
NIGHT_OBJ_FROM = 0x0C
FIELD_LINES, OBJ_LINES = (0x7E3956, 0x7E3976), (0x7E3A76, 0x7E3A96)
FIELD_COLORS = 13                        # 2·3번 줄 색 14·15 는 몇 프레임마다 오가므로 1~13 만 견줌
OBJ_NIGHT_FLAG = 0x7E1AA1
TIME_STOP = (0x7E2190, 0x02)
# 바트랜드 출구 앞(걷기 검사 field 구간의 끝 줄). 순간이동은 한 칸 아래 (28,81) 에 선다
FIELD_FROM, FIELD_WALK = '36/00,28,80', '28,81;down:120'
# 붙들어 볼 경계값: 해 질 녘(낮 마지막 00ED 부터)과 새벽(밤 마지막 01FC 부터 낮 첫 0002 까지)
BOUNDARIES = {'dusk': (0x00ED, 0x00EE, 0x00EF, 0x00F0, 0x00F1, 0x00F2),
              'dawn': (0x01FC, 0x01FD, 0x01FE, 0x01FF, 0x0000, 0x0001, 0x0002)}
FOLLOW_LIMIT = 600
# 붙들지 않고 넘기: (시작, 넘겨야 할 시각)
CROSSINGS = {'dusk': (0x00EA, 0x00F3), 'dawn': (0x01F9, 0x0003)}
CROSS_LIMIT = 3000
SET_NAMES = {'낮': 0x0050, 'EE': 0x00EE, 'EF': 0x00EF, 'F0': 0x00F0, 'F1': 0x00F1, '밤': 0x0100}
TOWN_EDGE = (0x00EF, 0x00F0)             # 이무르에 들어설 때 붙드는 시각: 낮 마지막·밤 첫 값
TOWN_ENTRY = '37/00,50,8'


def lorom_word(rom, addr):
    o = fx.lorom(addr)
    return rom[o] | rom[o + 1] << 8


def time_index(rom, t):
    """시각 t 의 벌 색인(× 2). 01:A132 와 같이 표를 뒤에서부터 보아 하한이 t 이하인 첫 항목."""
    o = fx.lorom(TIME_TABLE)
    rows = [(rom[o + 3 * k] | rom[o + 3 * k + 1] << 8, rom[o + 3 * k + 2]) for k in range(TIME_ROWS)]
    return next(idx for low, idx in reversed(rows) if low <= t)


def expected_palette(rom, t):
    """시각 t 의 (2번 줄 색 1~13, 3번 줄 색 1~13, 인물 11번 줄, 12번 줄, 밤 인물 표지) 바이트."""
    idx = time_index(rom, t)
    o = fx.lorom(0x010000 | lorom_word(rom, TIME_SETS + idx))
    obj = fx.lorom(NIGHT_OBJ if idx >= NIGHT_OBJ_FROM else DAY_OBJ)
    return {'line2': rom[o:o + 2 * FIELD_COLORS].hex(), 'line3': rom[o + 30:o + 30 + 2 * FIELD_COLORS].hex(),
            'obj11': rom[obj:obj + 30].hex(), 'obj12': rom[obj + 30:obj + 60].hex(),
            'night_obj': int(idx >= NIGHT_OBJ_FROM), 'set': f'{lorom_word(rom, TIME_SETS + idx):04X}'}


def wram_palette(core):
    w = core.wram()
    get = lambda a, n: bytes(w[a & 0x1FFFF:(a & 0x1FFFF) + n]).hex()  # noqa: E731
    return {'line2': get(FIELD_LINES[0], 2 * FIELD_COLORS), 'line3': get(FIELD_LINES[1], 2 * FIELD_COLORS),
            'obj11': get(OBJ_LINES[0], 30), 'obj12': get(OBJ_LINES[1], 30), 'night_obj': core.rd(OBJ_NIGHT_FLAG)}


def judge_palette(want, got):
    return [k for k in ('line2', 'line3', 'obj11', 'obj12', 'night_obj') if want[k] != got[k]]


def close_windows(step, times=3):
    """이어 하기 입력의 A 가 연 명령 창·서 있으면 뜨는 상태 창을 B 로 닫는다(필드는 8프레임마다 입력을 읽음)."""
    for _ in range(times):
        for _ in range(ADVANCE_HOLD):
            step({'b'})
        for _ in range(30):
            step(set())


def field_walker(core, rom, out, seed):
    """이무르에서 이어 해 바트랜드 출구 앞으로 순간이동한 뒤 걷기 검사(dq4ch1walkcheck 의 field 구간)의 끝처럼 아래로
    걸어 필드에 나간 Walker. 자리 표에 없는 칸으로 이어 하면 필드 (0,0)에 서서 걷지 못하고(실측), 같은 맵 안의 순간이동은
    도착을 알아보지 못해 다른 마을에서 순간이동한다."""
    slot = fx.SaveSlot.new_game(rom)
    slot.place = IMURU
    sram = slot.to_sram()
    out.mkdir(parents=True, exist_ok=True)
    (out / 'c.srm').write_bytes(sram)
    w = cc.Walker(str(dq4cores.core_path(core)), rom, out)
    rng = cc.sets(wc.rng_for(seed))
    try:
        fx.load_sram(w.c, sram)
        if fx.boot(w.c, slot.goal, step=w.step) is None:
            raise RuntimeError(f'이어 할 자리 {slot.goal} 에 서지 않음')
        w.c.poke(rng)
        close_windows(w.step)
        w.warp(FIELD_FROM, '', rng)
        close_windows(w.step)
        w.walk(FIELD_WALK, {})
        if w.c.rd(0x7E00BE) & 0x80:
            raise RuntimeError('바트랜드에서 걸어 나가 필드에 서지 않음')
        w.c.poke(rng)
    except BaseException:
        fx.close(w.c)
        raise
    return w, w.c.n


def walk_until(w, done, limit):
    """좌우로 번갈아 걸으며(막히면 위아래) 프레임마다 done() 을 본다. 참이 된 때까지 걸은 프레임 또는 None."""
    keys = ('left', 'right', 'up', 'down')
    k, last, still = 0, None, 0
    for n in range(limit):
        if n % 24 == 0:
            k = (k + 1) % 2 if still < 24 else (k + 1) % 4
        w.step({keys[k]})
        here = (w.c.rd(0x7E00B6, 2), w.c.rd(0x7E00B8, 2))
        still = still + 1 if here == last else 0
        last = here
        if done():
            return n + 1
    return None


def palette_follows(w, rom, limit):
    """걸으며 팔레트 버퍼가 지금 시각의 표 값과 같아질 때까지. 필드 색 갱신(02:AD2E → 01:A055)은 걷는 동안
    $7F 가 몇 프레임에 한 번 맞을 때만 돌아, 한 걸음 직후에는 앞 시각의 색이 남아 있을 수 있다."""
    return walk_until(w, lambda: not judge_palette(expected_palette(rom, w.c.rd(TIME, 2)), wram_palette(w.c)), limit)


def night_pinned(core, rom, out, seed, name):
    """필드에서 시각을 경계값 하나씩에 붙든 채 걸어, 팔레트 버퍼(2·3번 줄 색 1~13, 인물 11·12번 줄, 7E:1AA1)가 그 값의
    표(01:A16B) 벌로 바뀌는지."""
    w, at = field_walker(core, rom, out, seed)
    rom_bytes = Path(rom).read_bytes()
    rows, problems = [], []
    with fx.closing(w.c):
        if w.c.rd(TIME_STOP[0]) & TIME_STOP[1]:
            problems.append(f'시간 멈춤 7E:2190 bit1 이 켜져 있음({w.c.rd(TIME_STOP[0]):02X})')
        for t in BOUNDARIES[name]:
            w.pokes = [(TIME, t & 0xFF), (TIME + 1, t >> 8)]
            took = palette_follows(w, rom_bytes, FOLLOW_LIMIT)
            want = expected_palette(rom_bytes, t)
            rows.append({'time': f'{t:04X}', 'set': want['set'], 'night_obj': want['night_obj'], 'frames': took})
            if took is None:
                bad = judge_palette(want, wram_palette(w.c))
                problems.append(f'시각 {t:04X}: {FOLLOW_LIMIT} 프레임 걸어도 {" ".join(bad)} 가 표(벌 {want["set"]})와 다름')
        w.pokes = []
        w.c.shot(out / 'end.png')
    return {'problems': problems, 'field_at': at, 'steps': rows}


def night_cross(core, rom, out, seed):
    """붙들지 않고 걸어 해 질 녘과 새벽을 넘기: 시각이 오르는 동안 팔레트 버퍼가 고른 벌을 차례로 적고, 끝에서 표와 같은지."""
    w, at = field_walker(core, rom, out, seed)
    rom_bytes = Path(rom).read_bytes()
    problems, legs = [], {}
    with fx.closing(w.c):
        for leg, (start, end) in CROSSINGS.items():
            w.c.poke([(TIME, start & 0xFF), (TIME + 1, start >> 8)])
            seen = []

            def done():
                got = wram_palette(w.c)
                tag = next((s for s in SET_NAMES if expected_palette(rom_bytes, SET_NAMES[s])['line2'] == got['line2']),
                           '?')
                if not seen or seen[-1][1] != tag:
                    seen.append((f'{w.c.rd(TIME, 2):04X}', tag, got['night_obj']))
                t = w.c.rd(TIME, 2)
                return (t - start) & 0x1FF >= (end - start) & 0x1FF and not judge_palette(
                    expected_palette(rom_bytes, t), got)

            took = walk_until(w, done, CROSS_LIMIT)
            legs[leg] = {'frames': took, 'seen': seen, 'time': f'{w.c.rd(TIME, 2):04X}'}
            if took is None:
                problems.append(f'{leg}: {CROSS_LIMIT} 프레임 안에 {end:04X} 을 넘겨 표 색이 되지 않음({seen})')
            elif not any(n for _, _, n in seen) and leg == 'dusk':
                problems.append(f'{leg}: 밤 인물 표지 7E:1AA1 이 켜지지 않음({seen})')
        w.c.shot(out / 'end.png')
    return {'problems': problems, 'field_at': at, 'legs': legs}


def talk_numbers(core):
    """맵이 쓰는 인물 슬롯(8 부터 7E:1983 앞까지)의 대화 번호."""
    used = core.rd(0x7E1983)
    return [f'{core.rd(0x7E3700 + n) & 0xF:X}{core.rd(0x7E36E0 + n):02X}' for n in range(8, min(used, 0x20))]


def night_town(core, rom, out, seed):
    """바트랜드에서 시각을 낮 끝(00EF)·밤 첫 값(00F0)에 붙든 채 이무르로 순간이동해, 인물 목록이 이어 하기로 선 낮·밤
    목록과 같은지. 붙들지 않으면 순간이동 중 걸음으로 시각이 넘어간다."""
    lists, problems = {}, []
    for tag, t in zip(('day', 'night'), TOWN_EDGE):
        slot = base_slot(rom)
        slot.place = 'batland'
        with Town(core, rom, out / tag, slot, seed=seed) as town:
            close_windows(town.w.step)
            town.w.pokes = [(TIME, t & 0xFF), (TIME + 1, t >> 8)]
            where = town.w.warp(TOWN_ENTRY)[-1]
            town.w.pokes = []
            lists[tag] = {'map': where, 'time': f'{town.c.rd(TIME, 2):04X}', 'talk': talk_numbers(town.c)}
            town.c.shot(out / f'{tag}.png')
        if where != TOWN_ENTRY[:5]:
            problems.append(f'{tag}: {where} 에 섬')
    for tag, night in (('boot_day', False), ('boot_night', True)):
        slot = base_slot(rom)
        slot.night = night
        with Town(core, rom, out / tag, slot, seed=seed) as town:
            lists[tag] = {'map': '37/00', 'time': f'{town.c.rd(TIME, 2):04X}', 'talk': talk_numbers(town.c)}
    if lists['day']['talk'] != lists['boot_day']['talk']:
        problems.append('낮 끝(00EF)에 들어선 인물 목록이 낮 목록과 다름')
    if lists['night']['talk'] != lists['boot_night']['talk']:
        problems.append('밤 첫 값(00F0)에 들어선 인물 목록이 밤 목록과 다름')
    if lists['boot_day']['talk'] == lists['boot_night']['talk']:
        problems.append('이무르 낮·밤 인물 목록이 같음(판정이 갈리지 않음)')
    return {'problems': problems, 'lists': lists}


NIGHT_SCENES = {
    'dusk': lambda c, r, o, s, a: night_pinned(c, r, o, s, 'dusk'),
    'dawn': lambda c, r, o, s, a: night_pinned(c, r, o, s, 'dawn'),
    'cross': lambda c, r, o, s, a: night_cross(c, r, o, s),
    'town_edge': lambda c, r, o, s, a: night_town(c, r, o, s),
}


# ---------------------------------------------------------------- 옛 롬의 기록(oldsave)

ASSETS_IPS = 'sfc/dq4/ips/dq4-ch1.ips'


def old_rom(assets, rev, dq5, dest):
    """에셋 저장소 rev 의 1장 IPS 를 원본 DQ5 에 입힌 롬."""
    from kr_patch import ips
    git = ['git', '-C', str(assets)]
    if not rev:
        revs = subprocess.run(git + ['log', '--format=%h', '--reverse', '--', ASSETS_IPS], capture_output=True,
                              text=True, check=True).stdout.split()
        rev = revs[0]
    patch = subprocess.run(git + ['show', f'{rev}:{ASSETS_IPS}'], capture_output=True, check=True).stdout
    source = subprocess.run(git + ['show', f'{rev}:{Path(ASSETS_IPS).parent / "SOURCE.txt"}'], capture_output=True,
                            text=True).stdout
    dest.write_bytes(ips.apply(Path(dq5).read_bytes(), patch))
    return rev, source.strip()


def oldsave(args, cores):
    """옛 1장 롬에서 새 게임이 쓴 기록을 지금 롬으로 이어 한 결과를 남긴다. 형식이 같은지 판정하지 않고 기록만."""
    out = args.out.resolve()
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f'{out} is not empty')
    out.mkdir(parents=True)
    assets = os.environ.get('DQ4_ASSETS')
    if not assets:
        raise SystemExit('DQ4_ASSETS(비공개 에셋 저장소 체크아웃)가 필요')
    rom = args.rom.resolve()
    old = out / 'old.sfc'
    rev, source = old_rom(assets, args.old_rev, ROOT / 'rom' / 'dq5.sfc', old)
    report = {'old_rev': rev, 'old_source': source, 'old_sha1': hashlib.sha1(old.read_bytes()).hexdigest(),
              'rom_sha1': hashlib.sha1(rom.read_bytes()).hexdigest(), 'cores': {}}
    try:
        sram = fx.new_game_sram(old)
    except Exception as e:  # noqa: BLE001 — 옛 롬이 새 게임 기록을 못 쓰는 것도 결과다
        report['old_new_game'] = f'{type(e).__name__}: {e}'
        sram = None
    if sram is not None:
        used = fx.saved_slots(sram)
        block = slot_block(sram, used[0])
        now = fx.base_block(fx.new_game_sram(rom))
        report['old_new_game'] = {'slots': [u + 1 for u in used], 'differs_from_now': sum(a != b for a, b in zip(block, now))}
        place = block[fx.PLACE - fx.WRAM_BASE] & 0x7F
        _, row = fx.place_rows(rom.read_bytes()).get(place, (None, None))
        for name in cores:
            dest = out / name
            dest.mkdir()
            res = {'place': place, 'goal': list(row[:4]) if row else None}
            with fx.closing(fx.open_core(dq4cores.core_path(name), rom, dest, sram)) as c:
                script = [b for b, f in fx.CONTINUE for _ in range(f)]
                first = None
                while c.n < fx.ARRIVE_BY:
                    b = script[c.n] if c.n < len(script) else 'wait'
                    c.run(set() if b == 'wait' else {b})
                    if first is None and c.n >= fx.ARRIVE_FROM and c.rd(0x7E00BC) != 0 and c.rd(0x7E3020):
                        first = c.n
                after = fx.read_sram(c)
                w = bytes(c.wram()[:0x20000])
                res.update(first_map_frame=first, map=f'{w[0xBC]:02X}/{w[0xBD]:02X}', cell=[w[0x3020], w[0x3080]],
                           field=not w[0xBE] & 0x80, kept=[u + 1 for u in fx.saved_slots(after)],
                           block_diff=len(block_diff(block, w, REWRITTEN)), flags=fx.wram_summary(c)['flags'])
                c.shot(dest / 'end.png')
            report['cores'][name] = res
    (out / 'results.json').write_text(json.dumps(report, ensure_ascii=False, indent=1) + '\n')
    print(json.dumps(report, ensure_ascii=False, indent=1))
    return 0


def run_one(args):
    """_one: 한 프로세스에서 장면 하나(코어 하나는 프로세스마다 하나만 연다)."""
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    try:
        table = NIGHT_SCENES if args.mode == '_night' else SCENES
        res = table[args.scene](args.core, args.rom.resolve(), out, args.seed, args)
    except Exception as e:  # noqa: BLE001 — 장면 하나가 깨져도 결과 파일에 남긴다
        res = {'problems': [f'{type(e).__name__}: {e}']}
    res['choices'] = [list(x) for x in res.get('choices', [])]
    res.update(status=verdict(args.scene, res['problems'], args.known), seconds=round(time.time() - t0, 1))
    if args.scene in KNOWN and args.known:
        res['known'] = KNOWN[args.scene][0]
    (out / 'result.json').write_text(json.dumps(res, ensure_ascii=False, indent=1) + '\n')
    return 0 if res['status'] in ('passed', 'known') else 1


def fan_out(mode, args, units):
    """units = [(이름, 코어, 시드)] 를 --jobs 개 프로세스로 돌려 out/<시드>/<코어>/<이름>/result.json 을 모은다."""
    out = args.out.resolve()
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f'{out} is not empty')
    out.mkdir(parents=True)
    for name in {u[1] for u in units}:
        if not dq4cores.core_path(name).exists():
            raise SystemExit(f'{dq4cores.core_path(name)} 가 없음: sfc/dq4/tools/dq4cores.py 로 빌드')
    rom = args.rom.resolve()
    fx.SaveSlot.new_game(rom)
    t0 = time.time()
    pending, running, results = list(units), {}, {}
    while pending or running:
        while pending and len(running) < args.jobs:
            name, core, seed = pending.pop(0)
            dest = out / f'seed{seed}' / core / name
            dest.mkdir(parents=True)
            log = (dest / 'log.txt').open('w')
            cmd = [sys.executable, __file__, mode, '--scene', name, '--core', core, '--seed', str(seed),
                   '--rom', str(rom), '--out', str(dest), '--dq4', str(args.dq4.resolve())]
            if not args.known:
                cmd.append('--no-known')
            running[(name, core, seed)] = (subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT), log, dest,
                                           time.time())
        time.sleep(0.2)
        for key, (proc, log, dest, started) in list(running.items()):
            if proc.poll() is None and time.time() - started < cc.UNIT_TIMEOUT:
                continue
            if proc.poll() is None:
                proc.kill()
                proc.wait()
            log.close()
            f = dest / 'result.json'
            results[key] = (json.loads(f.read_text()) if f.exists() else
                            {'status': 'failed', 'problems': ['장면 프로세스가 결과를 남기지 않음']})
            del running[key]
    report = {'rom_sha1': hashlib.sha1(rom.read_bytes()).hexdigest(), 'scenes': {}}
    for (name, core, seed), r in sorted(results.items()):
        report['scenes'].setdefault(name, {})[f'{core}/seed{seed}'] = r
    report['status'] = 'passed' if all(r['status'] in ('passed', 'known') for r in results.values()) else 'failed'
    report['seconds'] = round(time.time() - t0, 1)
    (out / 'results.json').write_text(json.dumps(report, ensure_ascii=False, indent=1) + '\n')
    summary = {name: {k: (v['status'], v.get('seconds'), v['problems'][:3]) for k, v in per.items()}
               for name, per in report['scenes'].items()}
    print(json.dumps({'status': report['status'], 'rom_sha1': report['rom_sha1'], 'seconds': report['seconds'],
                      'scenes': summary}, ensure_ascii=False, indent=1))
    return 0 if report['status'] == 'passed' else 1


def seeds_of(args):
    return [int(s) for s in args.seeds.split(',')] if args.seeds else [args.seed]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('mode', choices=('check', 'daynight', 'oldsave', '_one', '_night'))
    ap.add_argument('--rom', required=True, type=Path)
    ap.add_argument('--out', required=True, type=Path)
    ap.add_argument('--dq4', type=Path, default=ROOT / 'rom' / 'dq4.nes', help='FC 롬(여관 값의 기준)')
    ap.add_argument('--core', choices=('all', *cc.CORES), default='all')
    ap.add_argument('--only', nargs='+', help='이 장면만')
    ap.add_argument('--scene')
    ap.add_argument('--seed', type=int, default=0, help='난수 7E:075B~075D 시드(dq4ch1walkcheck.rng_for)')
    ap.add_argument('--seeds', help='시드 여럿(쉼표). 시드마다 따로 돌고 모두 통과해야 통과')
    ap.add_argument('--jobs', type=int, default=4)
    ap.add_argument('--no-known', dest='known', action='store_false',
                    help='알려진 실패(KNOWN)도 그대로 실패로(소리 패치 전 롬 등에서 그 장면을 볼 때)')
    ap.add_argument('--old-rev', help='oldsave: 에셋 저장소에서 옛 IPS 를 꺼낼 커밋(기본 가장 오래된 1장 IPS)')
    args = ap.parse_args(argv)
    cores = list(cc.CORES) if args.core == 'all' else [args.core]
    if args.mode in ('_one', '_night'):
        return run_one(args)
    if args.mode == 'check':
        names = args.only or list(SCENES)
        return fan_out('_one', args, [(n, c, s) for s in seeds_of(args) for n in names for c in cores])
    if args.mode == 'daynight':
        names = args.only or list(NIGHT_SCENES)
        return fan_out('_night', args, [(n, c, s) for s in seeds_of(args) for n in names for c in cores])
    return oldsave(args, cores)


if __name__ == '__main__':
    sys.exit(main())
