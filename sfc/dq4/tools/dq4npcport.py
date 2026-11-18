"""FC DQ4 town people of the new DQ5 groups (dq4environmentrom.GROUPS) as dq5npcrelocate/1 lists and
their Japanese FC text as dq5text/1 messages appended after DQ5's 3,200 walking messages.

Each FC person record of the day and the night list becomes one DQ5 entry of that time. It copies a DQ5
template entry: a standing one, or one that wanders (script 19 03 03) with the FC step interval. The
picture is a placeholder DQ5 townsperson of the same role (PICTURES) until DQ4 sprites exist. The talk is
the FC talk of chapter 1 at the start (dq4talk.predict with chapter 0, no flags, no party): the messages it
shows are joined into one new DQ5 message (FIRST_MESSAGE-, gap-free), shown by an appended talk script (talk_doc).
People who open a shop, an inn, a church or the deposit in FC take the DQ5 talk number of the same service
instead (dq4shopport).

  python sfc/dq4/tools/dq4npcport.py --out work/dq4-npcs
"""

import argparse
import json
import sys
import unicodedata
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
DQ5_TOOLS = TOOLS.parents[1] / "dq5" / "tools"
FC_TOOLS = TOOLS.parents[2] / "fc" / "dq4" / "tools"
for path in (TOOLS, DQ5_TOOLS, FC_TOOLS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import dq4talk  # noqa: E402
import dq4text  # noqa: E402
import dq5text  # noqa: E402
from dq5hangul import MESSAGES  # noqa: E402
from dq4environmentrom import GROUPS  # noqa: E402
from dq4environmentmap import edit_cells, sheet_art  # noqa: E402
import dq4block  # noqa: E402
import dq4map  # noqa: E402
import dq4npcblock  # noqa: E402
from dq4groupbuild import cell, chapter, fc_map, has_people  # noqa: E402
import dq4shopport  # noqa: E402
import dq4prologue  # noqa: E402
from dq4shopport import merchants  # noqa: E402
from kr_patch.fc import ines  # noqa: E402

# Template entries (dq5npcrelocate `from`): one-time entries with no extra byte. STAND has no script and
# interval 0; WALK has the most common wander script 19 03 03 (walk within 3x3 of the start).
# 기타 bit4-5 가 00 이라 말을 걸면 주인공 쪽으로 돈다(05:86C5 1번은 30 이라 정면만 봄)
STAND = {"list": "05:870A", "index": 2}
WALK = {"list": "05:8857", "index": 6}
# 같은 FC 그림이라도 NDS 가 다른 시트로 그리는 인물: (맵, 처음 보이는 FC 대사) -> DQ5 그림(dq4people 의 시트).
# NDS 맵 스크립트에서 같은 대사를 하는 오브젝트의 모습 번호로 골랐다(nds/dq4/tools/ndsscript.py dump)
NDS_LOOKS = {
    # 바트랜드 성 앞의 장로(NDS ham2f1 長老 h039, 대사 287·320). 9C 는 서장 장로 시트를 싣는 빌린 그림
    ("36/00", 1932): 0x9C, ("36/00", 1312): 0x9C,
    # 사막 바자의 아저씨(NDS mem1f1·mey1f1 砂漠のおじさん h058). 그 시트가 없어 おじさん h002 로 둔다
    ("45/05", 1583): 0x38, ("45/05", 1362): 0x38,
    # 사란의 역사 학자(FC 그림 29, NDS mbw1f1 学者 h033, 대사 95566)
    ("45/04", 1807): 0x1F,
    # 3·4장의 이름 있는 인물. FC 는 여자·아이·대신·바니걸·무희 그림으로 두고 NDS 는 따로 그린다(dq4people 의 시트):
    # 레이크나바 집과 엔돌 가게의 네네(ネネ h139)·포포로(ポポロ h140), 몬바바라 극장의 좌장(座長 h142)과 쫓기는
    # 린다(リンダ h074), 엔돌 카지노의 마냐(マーニャ h124)
    ("3E/01", 2058): 0x22, ("40/00", 2150): 0x22, ("40/08", 2065): 0x22,
    ("3E/01", 1633): 0x95, ("3E/01", 1364): 0x95, ("40/08", 1364): 0x95,
    ("41/02", 1684): 0x8B, ("41/03", 1390): 0x8B,
    ("41/00", 1681): 0x66,
    ("40/01", 2323): 0x69,
    # 3·4장 마을 사람 가운데 NDS 가 FC 와 다른 모습으로 그리는 인물. FC 대사와 NDS 오브젝트 대사를 가나만 남겨 견주어
    # (difflib 비 0.75 이상, 같은 마을의 NDS 맵 안에서) 짝지은 오브젝트의 모습 번호다. 새 시트:
    # 여행 상인(旅の商人 h010) 68, 해적(海賊 h067) 59, 선원(船員 h012) 97, 바텐더(バーテン h028) 6D,
    # 레이크나바 무기점의 다츠(ダーツ h065) 6A, 하바리아 감옥의 예티(イエティ h175) 62, 배의 벡(ベック h078) 61,
    # 본몰 감옥의 노예(奴隷 h014) 44, 시녀(侍女 h056) 25, 집시 여자(ジプシー女 h063) 96, 젊은 아내(若妻 h004) 71,
    # 본몰의 릭 왕자(若き王 h037) 86
    ("41/00", 1382): 0x68, ("41/00", 1680): 0x68, ("41/00", 2216): 0x68, ("40/0B", 2136): 0x68,
    ("41/00", 1679): 0x59, ("41/00", 1383): 0x59, ("3E/00", 1658): 0x59,
    ("43/00", 2256): 0x97, ("43/03", 2268): 0x97, ("43/04", 1709): 0x97,
    ("40/01", 2038): 0x6D, ("43/01", 1695): 0x6D, ("43/01", 1409): 0x6D,
    ("3E/00", 806): 0x6A, ("3E/02", 2175): 0x6A,
    ("43/02", 1697): 0x62,
    ("43/03", 1706): 0x61,
    ("3F/00", 2111): 0x44,
    ("3F/01", 1368): 0x25,
    ("41/00", 1673): 0x96,
    ("3E/01", 1636): 0x71,
    ("3F/01", 2103): 0x86, ("3F/01", 2105): 0x86,
    # 이미 있는 시트로 바꾸는 자리: 남자(男 h000) 03, 죄수(囚人 h013) 3D, 병사(兵士 h015) 06, 무희(踊り子 h026) 28,
    # 하녀(メイド h029) 82, 학자(学者 h033) 1F, 아저씨(おじさん h002) 38. 엔돌·몬바바라·킹 레오 성의 전사(戦士
    # h018) 넷, 엔돌 투기장의 검사(剣士 h019), 킹 레오 성의 학자 둘은 바꾸지 않는다: 그 맵 그룹의 같은 줄에 서는
    # 위병·린다·발자크·여전사의 색을 민다(발자크 색 거리 12.8 → 15.4)
    ("3E/00", 2123): 0x03, ("3E/00", 2067): 0x03, ("3F/01", 1647): 0x03, ("40/02", 1609): 0x03, ("40/02", 1355): 0x03,
    ("41/00", 1677): 0x03, ("41/01", 2568): 0x03, ("44/02", 1402): 0x03,
    ("40/05", 1615): 0x3D,
    ("40/01", 1601): 0x06,
    ("40/00", 1591): 0x28, ("41/01", 1388): 0x28,
    ("40/05", 1614): 0x82, ("40/05", 1372): 0x82,
    ("40/06", 1611): 0x1F,
    ("3E/01", 2083): 0x38,
}
# FC 가 제자리에서 방향만 바꾸게 하는 인물(블록이 방향 23·돌기 05·06 과 쉼만 되풀이, turn_loop)의 틀. 이 해킹에서 가지
# 않는 DQ5 29/00 의 스크립트 인물들이고, 스크립트는 turn_scripts 가 FC 블록대로 덮는다. 되풀이 꼴 하나에 칸 하나
TURN_SRCS = tuple(({"list": "05:CB65", "index": i}, at)
                  for i, at in ((0, "05:CB6C"), (2, "05:CBA5"), (5, "05:CBE8"), (6, "05:CC11")))
# 쉼 한 차례는 지금 방향을 다시 두는 2F 다. 2F 는 이동 간격의 한 차례를 끝내지만 38 같은 명령은 끝내지 않고 이어 가
# 쉼이 되지 않았고, 37 은 들어가며 한 프레임을 기다려(00:9506) 게임 전체가 늦어졌다(실측)
TURN_FACE = (0x80, 0x10, 0x40, 0x20)     # FC 방향 0~3(위·오른쪽·아래·왼쪽) → 인물 명령 2F 의 7E:31E0
# A person FC puts on a bed lies in it: a one-time entry with 기타 bit7 (lying, drawn rotated 8 px lower) and bit4
# (does not turn when spoken to, which would swap the head to the foot of the bed), no script.
LIE = {"list": "10:A4E9", "index": 14}
# DQ5 이동 간격 range for ported walkers (dq5_interval). sfc/dq4/guards: dq4npcwalkcheck measures the steps
WALK_FASTEST, WALK_SLOWEST = 8, 15
LIE_GROUPS = range(0x36, 0x3D)    # 서장·1장 그룹. 2장 이후는 그 장을 옮길 때 화면으로 보고 넓힌다
# FC picture (dq4talk.sprite without the 80 bit) -> DQ5 picture of a townsperson of the same role, chosen by
# eye from the two sprite sheets (dq4fcsprite.py field, dq5sprite.py).
PICTURES = {
    0x0F: 0x14,  # king
    0x10: 0x01,  # minister
    0x11: 0x06,  # soldier
    0x12: 0x04,  # lady
    0x13: 0x17,  # woman with long hair (Flare, the mothers of Imuru)
    0x14: 0x29,  # man
    0x15: 0x0B,  # child
    0x16: 0x09,  # bald old man (NDS draws them 老人 h005, see NDS_LOOKS)
    0x17: 0x40,  # man in a green cap (shopkeepers; NDS 商人 h009)
    0x18: 0x03,  # man
    0x19: 0x07,  # man
    0x1B: 0x15,  # priest
    0x25: 0x24,  # cat (unused DQ5 picture carrying NDS ネコ h047, dq4people)
    0x28: 0x19,  # woman
    0x36: 0x05,  # nun
    0x27: 0x4E,  # fire (48 is on the list of pictures nobody talks to, 05:862F)
    0x40: 0x9B,  # horned monster in a robe with a staff: Pisaro's minion, as 0x41 (NDS ピサロの手先 h153)
    0x41: 0x9B,  # purple monster
    0x45: 0x1F,  # wizard
    0x3D: 0x5B,  # heal slime
    0x1A: 0x0E,  # princess
    0x1C: 0x51,  # skeleton
    0x1D: 0x28,  # dancer
    0x1E: 0x1A,  # man in a green cap
    0x1F: 0x45,  # hobbit
    0x20: 0x3D,  # man in stripes
    0x21: 0x40,  # bearded merchant
    0x22: 0x0D,  # woman soldier
    0x23: 0x23,  # fox
    0x24: 0x20,  # dog
    0x26: 0x26,  # horse
    0x29: 0x09,  # bald old man
    0x2A: 0x50,  # slime
    0x2B: 0xA1,  # boat
    0x2C: 0x52,  # cloud
    0x2D: 0x0F,  # purple-haired man
    0x2E: 0x0D,  # sky castle man
    0x2F: 0x8F,  # sky castle woman
    0x30: 0x5C,  # waterfall
    0x31: 0xA1,  # river boat
    0x32: 0xA0,  # wagon
    0x33: 0x87,  # round rock
    0x35: 0x75,  # machine
    0x37: 0x3A,  # miner
    0x38: 0x29,  # farmer
    0x39: 0x67,  # armoured guard
    0x3A: 0x0A,  # bunny girl
    0x3B: 0x21,  # young man
    0x3C: 0x9D,  # dragon
    0x3E: 0x5E,  # baby dragon
    0x3F: 0x88,  # purple monster
    0x42: 0x52,  # ghost
    0x43: 0x74,  # brown beast
    0x44: 0x60,  # imp with a fork
    0x46: 0x6E,  # brown beast
    0x47: 0x8A,  # winged demon
    0x49: 0x15,  # priest
    0x4A: 0x1C,  # fortune teller
    0x4B: 0x28,  # dancer
    0x4C: 0x1F,  # wizard
    0x4D: 0x36,  # merchant
    0x4E: 0x08,  # soldier
    0x4F: 0x2F,  # princess
    0x53: 0x9D,  # big monster, quarter
    0x54: 0x9D,  # big monster, quarter
    0x55: 0x9D,  # big monster, quarter
    0x56: 0x9D,  # big monster, quarter
    0x57: 0x43,  # workman
    0x58: 0x8E,  # sky castle soldier
    0x59: 0x9B,  # purple demon
    0x5E: 0x29,  # man (drawn invisible in FC)
    0x5F: 0xA0,  # wagon
    0x60: 0x52,  # balloon, left edge
    0x61: 0x52,  # balloon
    0x62: 0x52,  # balloon, right edge
    0x66: 0x70,  # statue
    0x67: 0x70,  # statue
    0x68: 0x33,  # green-haired boy
    0x69: 0x0F,  # purple-haired man
    0x6A: 0x4E,  # fire
    0x6C: 0x4E,  # fire
    0x76: 0x9B,  # purple demon
}
FACING = ("up", "right", "down", "left")
# Placeholder line for a person whose FC talk shows nothing at the start of chapter 1.
NOTHING = "＜なにもない＞"
# Ported lines are new messages after DQ5's own, right after chapter 1's and the prologue's Korean messages
# (dq4chapter1.TALK_BASE), gap-free.
FIRST_MESSAGE = dq4prologue.TALK_END + 0x3C6
assert FIRST_MESSAGE > MESSAGES
# Talk numbers 900- run talk scripts appended by dq5talkwrite --extra-at, gap-free from 900: the prologue's
# first (dq4prologue.talk_doc), then chapter 1's event talks (dq4ch1event), then one `msg` script per ported
# message. A talk number T >= 26D shows message
# T + 3C6 directly, but the talk numbers below 900 reach only a few of the new messages.
SCRIPT_TALK = 0x900
LINE, PAGE, END = 0x1000, 0x1002, 0x1001
# FC F4 는 30프레임 쉼(16:$80E9), DQ5 100D 는 31프레임 멈춤(24:84E9).
PAUSE = 0x100D
# FC 이름 0(勇者)은 새 게임에서 지은 이름이고, DQ5 는 그 이름을 7E:2001 에 두고 1012 로 찍는다.
HERO = 0x1012
NIGHT = 0x78
MAX_CELL = 0x7F


def fc_state(night, flags=None, chapter_number=1):
    """A chapter at its start: $615A = chapter - 1, no flags or party, $62ED day or night. flags {address: value}
    sets event flags for a later state."""
    ram = bytearray(0x8000)
    ram[0x615A] = chapter_number - 1
    ram[0x62ED] = NIGHT if night else 0
    for a, v in (flags or {}).items():
        ram[a] = v
    return dq4talk.State(ram)


def bed_cells(prg, fc_group, number):
    """FC cells of a bed's foot (bed_left with bed_right on its right): a person FC puts there sleeps."""
    source = dq4block.Map(prg, fc_group, number)
    edit_cells(source, fc_group, number)
    art = sheet_art(prg, source.t)
    name = lambda x, y: art.get(source.cell(x, y) & 31, ("",))[0]  # noqa: E731
    return {(x, y) for y in range(source.h) for x in range(source.w - 1)
            if name(x, y) == "bed_left" and name(x + 1, y) == "bed_right"}


def hidden_people(prg):
    """(DQ5 map, night, FC talk, FC x, FC y) of every FC record a ported map leaves out because FC hides it on entry."""
    out = []
    for name, (group, number) in sorted(GROUPS.items(), key=lambda kv: kv[1]):
        fc_group, fc_number = fc_map(prg, group, number)
        if not has_people(fc_group):
            continue
        for night in (False, True):
            for rec in dq4talk.npc_list(prg, fc_group, fc_number, night):
                if dq4npcblock.hidden_on_entry(rec, night):
                    out.append((f"{group:02X}/{number:02X}", night, dq4talk.talk_id(rec, night), *dq4talk.pos(rec, night)))
    return out


def fc_blocks(prg, fc_group, number, night, ram=None):
    """(뱅크, 블록 본문 주소 또는 None) per record of dq4talk.npc_list, in the same order."""
    bank, start = dq4map.place_list(prg, fc_group, number, dq4map.ram_flags(ram) if ram is not None else None)
    bit = 0x08 if night else 0x10
    out = []
    for _, f, blocks in dq4npcblock.records(prg, bank, start)[0]:
        if f & bit:
            body, ln = blocks[1 if night and f & 0x10 else 0]
            out.append((bank, body if ln else None))
    return out


def dq5_interval(fc_step):
    """DQ5 이동 간격 for a person FC walks every fc_step turns (0 stands). FC takes a turn every 16 frames
    (fc/dq4/docs/dq4-script-format.md), the DQ5 wander script 19 steps far less often per unit: DQ5 interval 1 walks
    without a break. Doubling FC and keeping to DQ5's own wanderers (8 and 15, the most common) gives one step in
    about 2 s, as DQ5 townsfolk walk."""
    return min(WALK_SLOWEST, max(WALK_FASTEST, 2 * fc_step)) if fc_step else 0


def turn_loop(prg, bank, body, facing):
    """FC 블록이 처음부터 쉼(00·01, 82 n 01 81)과 방향(23 d, 05 +1, 06 −1)만 하고 83 으로 처음에 돌아가며, 한 바퀴 안의
    방향이 둘 이상이면 [('rest', 차례 수) | ('face', 0~3)], 아니면 None. facing 은 레코드의 처음 방향이고 05·06 은 거기서
    센다. 05·06 이 있으면 처음 방향으로 돌아올 때까지(4바퀴 안) 펼친다."""
    if body is None:
        return None
    out, d, relative = [], facing, False
    for _ in range(4):
        p = body
        for _ in range(64):
            c, arg = dq4npcblock.rd(prg, bank, p), dq4npcblock.rd(prg, bank, p + 1)
            if c in (0x00, 0x01):
                out.append(('rest', 1))
                p += 1
            elif c == 0x82 and dq4npcblock.rd(prg, bank, p + 2) in (0x00, 0x01) \
                    and dq4npcblock.rd(prg, bank, p + 3) == 0x81:
                out.append(('rest', arg))
                p += 4
            elif c in (0x05, 0x06, 0x23):
                d = arg & 3 if c == 0x23 else (d + (1 if c == 0x05 else -1)) & 3
                relative |= c != 0x23
                out.append(('face', d))
                p += 2 if c == 0x23 else 1
            elif c == 0x83 and (p + (arg - 0x100 if arg & 0x80 else arg)) & 0xFFFF == body:
                break
            else:
                return None
        else:
            return None
        if not relative or d == facing:
            break
    else:
        return None
    turned = {k for kind, k in out if kind == 'face'}
    return out if len(turned) > 1 and any(kind == 'rest' for kind, _ in out) else None


def turn_commands(loop):
    """turn_loop 를 인물 스크립트 명령으로: 차례마다 2F 하나(방향을 바꾸거나 지금 방향을 다시 둠). 되풀이는 마지막 방향에서
    다시 시작하므로 앞쪽 쉼도 그 방향이다."""
    d = [n for kind, n in loop if kind == 'face'][-1]
    out = []
    for kind, n in loop:
        if kind == 'face':
            d = n
        out += [{"op": "2F", "args": [TURN_FACE[d]]} for _ in range(1 if kind == 'face' else n)]
    out[0] = {**out[0], "label": "top"}
    return out + [{"op": "03", "args": [], "target": "top"}]


def turn_scripts(report):
    """port 의 보고에서 제자리 도는 인물의 틀 스크립트(dq5npcrelocate scripts 항목)."""
    made = {}
    for people in report.values():
        for p in people:
            if p.get("turn_src") is not None:
                made.setdefault(p["turn_src"], p["turn"])
    return [{"address": TURN_SRCS[k][1], "commands": turn_commands(loop)} for k, loop in sorted(made.items())]


def fc_people(prg, fc_group, number, night, flags=None):
    """FC person records of a map at that time: FC cell, facing, step interval, picture, messages. With flags
    the list is the one FC picks for those event flags (dq4map.place_records). The interval is the FC command
    interval at the block's first step (dq4npcblock.walk_interval): 0 for a person FC never walks, whatever the
    record's interval (a soldier whose block waits for an event and stands keeps interval 1 in the record)."""
    state = fc_state(night, flags, chapter(fc_group))
    ram = state.ram if flags else None
    recs = dq4talk.npc_list(prg, fc_group, number, night, ram=ram)
    blocks = fc_blocks(prg, fc_group, number, night, ram)
    if len(blocks) != len(recs):
        raise ValueError(f"{fc_group:02X}/{number:02X}: {len(recs)} records but {len(blocks)} blocks")
    out = []
    for rec, (bank, body) in zip(recs, blocks):
        if dq4npcblock.hidden_on_entry(rec, night):
            # FC hides it before it is ever drawn. Ported, it would be seen, and a wanderer could stand on a stair.
            # An event that shows it again has to bring it back with its own list (test_dq4npcport HiddenPeopleTest).
            continue
        x, y = dq4talk.pos(rec, night)
        step = dq4npcblock.walk_interval(prg, bank, body, rec[2] & 0x0F if night else rec[2] >> 4)
        # Facing comes from the picture's byte: byte 3, or byte 7 at night when F bit0 is off (1C:$99B3).
        facing = rec[7] if night and not rec[0] & 1 else rec[3]
        turn = turn_loop(prg, bank, body, facing & 3) if not step else None
        out.append({"x": x, "y": y, "facing": FACING[facing & 3], "interval": step,
                    **({"turn": turn, "turn_step": rec[2] & 0x0F if night else rec[2] >> 4} if turn else {}),
                    "picture": dq4talk.sprite(rec, night) & 0x7F, "talk": dq4talk.talk_id(rec, night),
                    "shows": dq4talk.predict(prg, dq4talk.talk_id(rec, night), state)})
    return out


def _codes_of_char():
    table = {}
    for code, char in enumerate("".join(dq5text.CHARS)):
        table.setdefault(char, code)
    return table


CODE_OF = _codes_of_char()
FULLWIDTH_DIGITS = {ord(c): ord(c) + 0xFEE0 for c in "0123456789"}
REVERSE = {code: char for char, code in CODE_OF.items()}


def _pieces(text):
    """dq4text symbols as a list: control names as str, characters as ("char", c)."""
    pieces, i = [], 0
    while i < len(text):
        if text[i] == "{":
            j = text.index("}", i)
            pieces.append(text[i + 1:j])
            i = j + 1
        else:
            pieces.append(("char", text[i]))
            i += 1
    return pieces


def _skip_speaker(pieces, k):
    """Index after a speaker mark 「＊「」 (and a line break after it) at k, or k. DQ5 puts the mark on a
    message and a page itself (24:8AF9), so a written one would show twice."""
    if pieces[k:k + 2] == [("char", "＊"), ("char", "「")]:
        k += 2
        if pieces[k:k + 1] == ["LINE"]:
            k += 1
    return k


def _code(m, char):
    if char not in CODE_OF:
        char = unicodedata.normalize("NFKC", char).translate(FULLWIDTH_DIGITS)
    if char not in CODE_OF:
        raise ValueError(f"FC message {m:04X}: no DQ5 character for {char!r}")
    return CODE_OF[char]


def dq5_codes(rom, messages):
    """FC messages (dq4text symbols) as one DQ5 message: {LINE} -> line break, {WAIT} -> page, a dakuten
    mark {3D} joins the next kana, messages are joined by pages. Speaker marks at the start of a message or
    a page are dropped, and a page is never doubled or left empty at the end."""
    codes = []

    def page():
        if codes and codes[-1] != PAGE:
            codes.append(PAGE)
    for m in messages:
        pieces = _pieces(dq4text.symbolize(dq4text.message_bytes(rom, m)))
        page()
        k = 0
        while k < len(pieces) and pieces[k] == "NOINDENT":
            k += 1
        k = _skip_speaker(pieces, k)
        while k < len(pieces):
            p = pieces[k]
            k += 1
            if isinstance(p, tuple):
                codes.append(_code(m, p[1]))
            elif p == "LINE":
                codes.append(LINE)
            elif p == "PAUSE":
                codes.append(PAUSE)
            elif p == "NAME:0":
                codes.append(HERO)
            elif p == "WAIT":
                page()
                k = _skip_speaker(pieces, k)
            elif p == "3D":
                if k >= len(pieces) or not isinstance(pieces[k], tuple):
                    raise ValueError(f"FC message {m:04X}: dakuten mark without a character")
                codes.append(_code(m, unicodedata.normalize("NFC", pieces[k][1] + "\u3099")))
                k += 1
            elif p in ("NOINDENT", "STOP") or p.startswith("SOUND:"):
                # No sound control in DQ5 walking text: the placeholder text goes without them. A STOP before
                # more text would need a DQ5 wait, which these messages do not have.
                if p == "STOP" and k < len(pieces) and pieces[k] != "END":
                    raise ValueError(f"FC message {m:04X}: {{STOP}} before more text")
            elif p == "END":
                break
            else:
                raise ValueError(f"FC message {m:04X}: no DQ5 code for {{{p}}}")
    while codes and codes[-1] == PAGE:
        codes.pop()
    return codes + [END]


def nothing_codes():
    return [CODE_OF[c] for c in NOTHING] + [END]


def first_talk():
    """Talk number of the first ported message's script: the prologue's, chapter 1's and chapter 2's event scripts
    come first."""
    import dq4ch1event
    import dq4ch2event
    import dq4ch3event
    import dq4prologue
    return (SCRIPT_TALK + len(dq4prologue.talk_doc()["scripts"]) + len(dq4ch1event.TALKS) +
            len(dq4ch2event.talk_names()) + len(dq4ch3event.talk_names()))


def allocate(texts, key, codes):
    """Message number of a line (key = the FC messages it shows), a new one in order of first use."""
    if key not in texts:
        texts[key] = (FIRST_MESSAGE + len(texts), codes())
    return texts[key][0]


def talk_doc(messages):
    """dq5talk/1: the prologue's appended scripts, chapter 1's event scripts, and then one script per ported
    message in id order, so message FIRST_MESSAGE + k has talk number first_talk() + k. The event scripts show
    messages right after the ported ones (dq4ch1event.MESSAGES)."""
    import dq4ch1event
    import dq4prologue
    doc = dq4prologue.talk_doc()
    first = first_talk()
    ids = [m["id"] for m in messages]
    if ids != list(range(FIRST_MESSAGE, FIRST_MESSAGE + len(ids))):
        raise ValueError(f"ported messages must run gap-free from {FIRST_MESSAGE:X}")
    events = dq4ch1event.talk_numbers(SCRIPT_TALK + len(doc["scripts"]))
    doc["scripts"] += [{"talk": f"{events[name]:03X}", "body": body}
                       for name, body in zip(dq4ch1event.TALKS, dq4ch1event.talk_scripts(FIRST_MESSAGE + len(ids)))]
    import dq4ch2event
    ch2 = SCRIPT_TALK + len(doc["scripts"])
    ch2_first = FIRST_MESSAGE + len(ids) + len(dq4ch1event.MESSAGES)
    doc["scripts"] += [{"talk": f"{ch2 + k:03X}", "body": body}
                       for k, body in enumerate(dq4ch2event.talk_scripts(ch2_first))]
    import dq4ch3event
    ch3 = SCRIPT_TALK + len(doc["scripts"])
    ch3_first = ch2_first + dq4ch2event.message_count()
    doc["scripts"] += [{"talk": f"{ch3 + k:03X}", "body": body}
                       for k, body in enumerate(dq4ch3event.talk_scripts(ch3_first))]
    doc["scripts"] += [{"talk": f"{first + k:03X}", "body": [{"op": "msg", "id": f"{m:03X}"}]}
                       for k, m in enumerate(ids)]
    return doc


def port(dq5_path, dq4_path, with_people=True):
    """(dq5npcrelocate lists, dq5text messages, report); `with_people` False ports no FC people. After the maps'
    own lists come the lists of later states (dq4ch1event.ALT_STATES) as {"name": dq4ch1event.alt_name(state, map),
    "entries": …}, reported under the same name; their new lines get message numbers after the start state's."""
    import dq4ch1event
    data = Path(dq4_path).read_bytes()
    items = dq4shopport.dq5_items(dq4shopport.dq5item.Rom(Path(dq5_path).read_bytes()))
    prg, rom = ines.prg(data), dq4text.Rom(data)
    first = first_talk()
    texts = {}
    lists, report = [], {}
    turns = {}

    def people_of(name, fc_group, fc_number, flags=None):
        entries, people = [], []
        shops = merchants(prg, fc_group, fc_number, items)
        group = int(name[:2], 16) if "/" in name else GROUPS[name][0]
        dq5_map = name if "/" in name else "%02X/%02X" % GROUPS[name]
        beds = bed_cells(prg, fc_group, fc_number) if group in LIE_GROUPS else set()
        for night in (False, True) if has_people(fc_group, with_people) else ():
            for p in fc_people(prg, fc_group, fc_number, night, flags):
                if max(cell(p["x"], p["y"])) > MAX_CELL:
                    # Parked far off the map until an event brings them (エンドール 04/02 night, (1A,7F)·(1B,7F)):
                    # the DQ5 person record holds 7-bit cells.
                    continue
                shows = [m for m in p["shows"] if m is not None]
                predicted = [m - dq4talk.SERVICE for m in shows if m >= dq4talk.SERVICE]
                service = shops.get((p["x"], p["y"], night))
                if service is None and predicted and dq4shopport.has_goods(prg, predicted[0], fc_group, fc_number, items):
                    service = dq4shopport.SERVICE[predicted[0]]
                message = None
                if service is not None:
                    # A seller stays behind the counter: the DQ5 wander script would walk off it.
                    talk = service
                    p = {**p, "interval": 0}
                else:
                    # A seller with nothing DQ5 has (has_goods) keeps the lines before its service.
                    shows = [m for m in shows if m < dq4talk.SERVICE]
                    message = allocate(texts, tuple(shows),
                                       lambda: dq5_codes(rom, shows) if shows else nothing_codes())
                    talk = first + message - FIRST_MESSAGE
                if p["picture"] not in PICTURES:
                    raise ValueError(f"{name}: FC picture {p['picture']:02X} has no DQ5 picture")
                gfx = NDS_LOOKS.get((dq5_map, p["shows"][0] if p["shows"] else None), PICTURES[p["picture"]])
                x, y = cell(p["x"], p["y"])
                fields = {"x": x, "y": y, "facing": p["facing"], "talk": talk,
                          "gfx": gfx, "layer": 0, "interval": dq5_interval(p["interval"])}
                template = WALK if p["interval"] else STAND
                turn_src = None
                if p.get("turn") and p.get("turn_step") and service is None:
                    # FC 는 16프레임에 한 차례, DQ5 스크립트는 이동 간격 × 8프레임에 한 차례
                    turn_src = turns.setdefault(tuple(p["turn"]), len(turns))
                    if turn_src >= len(TURN_SRCS):
                        raise ValueError(f"{name}: 제자리 도는 꼴이 {len(TURN_SRCS)}가지를 넘음(TURN_SRCS 를 늘릴 것)")
                    template = TURN_SRCS[turn_src][0]
                    fields["interval"] = min(15, 2 * p["turn_step"])
                if (p["x"], p["y"]) in beds and service is None:
                    # Lying on the bed's row, half a block right so the head rests on the pillow and the foot of
                    # the bed shows. The lying picture is the standing one turned clockwise: facing down turns the
                    # front view so the eyes stand one above the other and the face reads as turned to the wall;
                    # facing right (as most DQ5 sleepers) turns the side view to a face up from the pillow.
                    fields.update(x=x + 1, y=y - 1, facing="right", interval=0)
                    template, turn_src = LIE, None
                entries.append({"from": template, "time": "night" if night else "day", "fields": fields})
                people.append({**p, "night": night, "service": service, "turn_src": turn_src,
                               "message": None if message is None else f"{message:03X}", "dq5": fields})
        return entries, people

    for name, (group, number) in sorted(GROUPS.items(), key=lambda kv: kv[1]):
        fc_group, fc_number = fc_map(prg, group, number)
        m = f"{group:02X}/{number:02X}"
        entries, people = people_of(name, fc_group, fc_number)
        lists.append({"map": m, "entries": entries})
        report[m] = people
    for state, flags, maps in dq4ch1event.ALT_STATES:
        for m in maps:
            group, number = (int(v, 16) for v in m.split("/"))
            entries, people = people_of(m, *fc_map(prg, group, number), flags)
            lists.append({"name": dq4ch1event.alt_name(state, m), "entries": entries})
            report[dq4ch1event.alt_name(state, m)] = people
    messages = [{"id": m, "codes": codes} for m, codes in sorted(texts.values())]
    return lists, messages, report


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dq5", default="rom/dq5.sfc")
    ap.add_argument("--dq4", default="rom/dq4.nes")
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    lists, messages, report = port(args.dq5, args.dq4)
    (args.out / "npc-lists.json").write_text(json.dumps(lists, ensure_ascii=False, indent=1) + "\n")
    (args.out / "messages.json").write_text(json.dumps({"format": "dq5text/1", "messages": messages}) + "\n")
    (args.out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n")
    print(json.dumps({m: len(v) for m, v in report.items()} | {"messages": len(messages)}))


if __name__ == "__main__":
    main()
