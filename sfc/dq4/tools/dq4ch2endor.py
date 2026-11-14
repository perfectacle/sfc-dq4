"""DQ4 2장 엔돌 무술 대회: 아리나 혼자 다섯 상대를 잇달아 이기고 우승해 산트하임에서 온 사자를 만난다.

FC 차례(1D 이벤트 44~47·4A·4D·4E, 1C 이벤트 03):
  1. 투기장(40/07, FC 04/07) 링 안 (0E,0C)에 들어서면 크리프트·브라이가 응원하겠다며 남고(037E·037F), 일행 명령 53 이
     둘을 일행에서 잠시 뺀다($618E bit7, $616E). 왕이 대회 규칙을 말한다(0380).
  2. 상대 ミスター·ハン → ラゴス → ビビアン → サイモン → べロりンマン(특수 전투 07~0B, $6287 & 7 번째). 이길 때마다
     「○ 명 격파」(0381), 약초를 쓰겠느냐(047D·047E·047F), 다음 상대(0382). 지면 침대(04/0E)에서 깨어나 030D~0310.
  3. 다섯을 이기면 데스피사로가 사라져 아리나 우승(0383~0385), 브라이·크리프트(0386·0387)와 일행이 돌아온다($6284|40).
  4. 엔돌 마을(40/00)에서 산트하임에서 온 사자가 쓰러지며 성으로 돌아가라고 한다(038F, $6287|20).

포팅은 동료를 일행 기록 1·2 그대로 두고 일행 수만 1 로 줄인다(leave). 순서 둘은 IN 바이트 위 니블에 맡기고, 되돌릴
때(restore) 셋째를 셈해 일행 수 3 과 함께 다시 쓴다. 기록을 옮기지 않으니 장비·물건·HP 는 그대로다. 대회는 대화
하나가 이어지는 동안 끝나므로(교회·저장이 끼지 않음) 맡긴 값은 저장되는 flag 바이트에 둔다. 지는 전투는 01:868B 의
전멸 처리 대신 01:8715 에 A = 0 을 넘겨 보통 전투 뒤처럼 맵으로 돌아오고, 그 자리에서 일행을 되돌린다.

형식은 sfc/dq4/docs/dq4-chapter2-format.md 「엔돌 무술 대회」.
"""
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[1] / 'dq5' / 'tools')]

import dq4chapter1 as ch1  # noqa: E402
from dq4chapterbox import ENTER, LEAVE  # noqa: E402
from dq4npcport import STAND  # noqa: E402
import dq4ch2battle  # noqa: E402
import dq4ch2event as ch2  # noqa: E402

say, narrate, speak = ch1.say, ch1.narrate, ch1.speak

# 7E:21F4(dq4ch2slots E4). 위 니블은 IN 동안 맡긴 일행 순서 첫 둘(2비트씩)
IDX = 0x64
IN = (IDX, 0x01)               # 대회 중: 동료 둘이 일행에서 빠져 있음(FC $618E bit7)
LOST = (IDX, 0x02)             # 방금 대회 전투에서 짐: 침대 장면을 기다림(FC $6285 bit5 의 짐 갈래)
CHAMPION = (IDX, 0x04)         # 우승(FC $6284&40)
MESSENGER = (IDX, 0x08)        # 산트하임 사자의 말을 들음(FC $6287&20). 빈 산트하임 성 사건이 볼 flag
ORDER_SHIFT = 4
# 7E:21F7 바이트 값: 이긴 상대 수 0~5(FC $6287 & 7)
STAGE = (0x67, 0xFF)
FLAGS = (IN, LOST, CHAMPION, MESSENGER, (IDX, 0xF0), STAGE)
FLAG_AT = 0x7E2190 + IDX
STAGE_AT = 0x7E2190 + STAGE[0]
ROUNDS = 5

ARENA, BEDROOM, TOWN = '40/07', '40/0E', '40/00'      # FC 04/07 투기장, 04/0E 대기실, 04/00 엔돌 마을


def cell(x, y):
    """FC 칸 → 옮긴 인물·순간이동 셀(dq4npcport.cell)."""
    return (2 * x, 2 * y + 1)


# FC 링 안(04/07 의 (08~13, 09~0C)). 주인공은 아래 (0E,0E)~(0E,0D) 의 길로 들어와 (0E,0C)에서 FC 이벤트 44 를 만난다
RING = (0x08 * 2, 0x09 * 2, 0x13 * 2 + 1, 0x0C * 2 + 1)          # (x0, y0, x1, y1) 셀, 양 끝 포함
# 지고 깨어나는 침대 옆: 04/0E 침대 둘(FC (02,08~0A)·(04,08~0A)) 사이
BED_CELL = cell(0x03, 0x09)
# 사자(FC 04/00 목록 1C:$8872 의 레코드 0, 성문 오른쪽 (1A,0A)). FC 1D 이벤트 4D 는 주인공이 성 앞 길(Y = 0A)에 오면
# 사자를 걷게 한다. 포팅은 성 앞 길(셀 Y 19~21)과 해자의 다리(성문 FC (17~18,0B~0C))에 들어서면 사자가 말한다
MESSENGER_CELL = cell(0x1A, 0x0A)
MESSENGER_ROW = (0x10 * 2, 0x0A * 2 - 1, 0x22 * 2, 0x0B * 2 + 1)
MESSENGER_PIC = 0x06           # 산트하임 병사(dq4people 「2장 사건 인물 그림 표」)
# 링 위 상대(FC 04/07 대회 중 목록의 링 위 두 칸 가운데 왼쪽 (0E,0A)). 주인공이 링에 드는 (0E,0C) 바로 위에서 아래를 본다.
# 투기장 목록 맨 앞이라 물체 슬롯 08(그림 7E:3220 + 슬롯)
OPPONENT_CELL = cell(0x0E, 0x0A)
OPPONENT_PIC_AT = 0x7E3220 + 0x08

# 일행 기록(7E:2040 + 42 × n)과 순서 표. 2장 일행은 아리나(기록 0)·크리프트·브라이
PARTY_AT = ch2.PARTY_AT
COUNTS = (0x7E201D, 0x7E201E, 0x7E201F)        # 일행 수·걷는 수·사본
ORDERS = (0x7E2020, 0x7E2028)                  # 순서·걷는 순서
ALENA_STATUS, ALENA_HP, ALENA_MAX_HP = PARTY_AT + 1, PARTY_AT + 2, PARTY_AT + 0xE
ALENA_EQUIP, ALENA_ITEMS = PARTY_AT + 0x14, PARTY_AT + 0x16
ITEM_SLOTS = 12
HERB = 0xA1                    # DQ5 やくそう
HERB_HEAL = 35                 # FC·DQ5 약초의 30~40 가운데. 대회 사이의 회복은 난수를 쓰지 않는다

# 대회 상대(FC 특수 전투 07~0B). 무리 32~36 에 하나씩. 덮을 DQ5 몬스터는 NDS 그림을
# 담을 수 있는 원래 그림을 가진 번호(dq4monport.EVENT)
OPPONENTS = (
    # (무리, DQ5 몬스터, FC 몬스터, 한글 이름)
    (0x32, 0xAA, 0xAF, '미스터 한'),
    (0x33, 0xA4, 0xB0, '라고스'),
    # 비비안: ニセたいこう(40)에게 지면 snes9x 에서 침대 맵이 검은 화면에서 멈췄다(실측). 40 은 쓰지 않는다
    (0x34, 0x8E, 0xB1, '비비안'),
    (0x35, 0x68, 0xB2, '사이몬'),
    (0x36, 0x72, 0xBA, '베로린맨'),
)
# 링에 서는 상대의 그림(dq4people 「2장 사건 인물 그림 표」), OPPONENTS 차례
OPPONENT_PICS = (0x60, 0x89, 0x1C, 0x1D, 0x34)
GROUP0 = OPPONENTS[0][0]
assert [g for g, *_ in OPPONENTS] == list(range(GROUP0, GROUP0 + ROUNDS))
# 무리 플래그: 도망칠 수 없고 곡은 보통 전투 17(FC·NDS 모두 투기장 전투에 따로 곡을 주지 않음)
BATTLE_FLAGS = dq4ch2battle.NO_FLEE
BATTLES = tuple({"group": g, "members": ((m, 1),), "flags": BATTLE_FLAGS} for g, m, _, _ in OPPONENTS)
MONSTERS = {m: fc for _, m, fc, _ in OPPONENTS}
MONSTER_NAMES = {m: ko for _, m, _, ko in OPPONENTS}
# FC 행동 번호(dq4ch1event.FC_ACTIONS 에 없는 것) → DQ5 몬스터 행동. 07 ヒャド·23 ベホイミ 는 몬스터용 주문 42·5D(カンダタ 의
# 것), 2D ちからを ためる 는 6C. 64 ブーメラン·5F 몬스터의 やくそう 는 DQ5 에 맞는 행동이 없어 공격 73 으로
FC_ACTIONS = {0x07: '42', 0x23: '5D', 0x2D: '6C', 0x64: '73', 0x5F: '73'}

# 대화 스크립트가 부르는 입구(dq4ch2battle 칸 1·2·3). fight 는 공용 전투 루틴처럼 BRK 0E 를 뱅크 06 에서 먼저 돈다
CALLS = {1: 'leave', 2: ('fight', bytes((0x00, 0x0E))), 3: 'herb'}

# 빌리는 인물 스크립트(DQ5 02/06 대체 목록 10:9A2F 칸 2·3: 낮 한 벌, 스크립트 인물)
SCRIPT_LIST = '10:9A2F'
SCRIPTS = {'ring': (2, '10:9A44'), 'messenger': (3, '10:9A5A')}

ARENA_LIST, TOWN_SEEN, TOWN_MESSENGER = 'ch2_endor_arena', 'ch2_endor_town_seen', 'ch2_endor_town_messenger'
ARENA_DONE = 'ch2_endor_arena_done'

# 21:805A 등과 같은 이 해킹의 루틴
BATTLE_SONG, BATTLE_PREP, BATTLE_PREP2 = 0x268F43, 0x04D9CE, 0x0384D1   # 01:868B 가 전투 앞에 부르는 셋
BATTLE_RUN = 0x268DF1          # 전투(A = 무리). 돌아오면 A = 결과(80 전멸)
BATTLE_AFTER = 0x018715        # 전투 뒤 맵으로(A = 80 이면 전멸 처리 01:88ED). 01:868B 의 끝
LOSE = 0x80


def _al(a):
    return bytes((a & 0xFF, a >> 8 & 0xFF, a >> 16))


class Asm:
    """짧은 상대 분기 이름표가 있는 바이트 묶음."""

    def __init__(self):
        self.items = []

    def __call__(self, *parts):
        for p in parts:
            self.items.append(bytes((p,)) if isinstance(p, int) else bytes(p))
        return self

    def br(self, op, label):
        self.items.append(('br', op, label))
        return self

    def label(self, name):
        self.items.append(('label', name))
        return self

    def brl(self, label):
        self.items.append(('brl', label))
        return self

    def bytes(self):
        at, pos = {}, 0
        for it in self.items:
            if isinstance(it, tuple) and it[0] == 'label':
                at[it[1]] = pos
            else:
                pos += {'br': 2, 'brl': 3}[it[0]] if isinstance(it, tuple) else len(it)
        out = bytearray()
        for it in self.items:
            if isinstance(it, tuple) and it[0] == 'br':
                d = at[it[2]] - (len(out) + 2)
                if not -128 <= d <= 127:
                    raise ValueError(f'분기 {it[2]} 가 멂({d})')
                out += bytes((it[1], d & 0xFF))
            elif isinstance(it, tuple) and it[0] == 'brl':
                out += bytes((0x82,)) + ((at[it[1]] - (len(out) + 3)) & 0xFFFF).to_bytes(2, 'little')
            elif not isinstance(it, tuple):
                out += it
        return bytes(out)


def lda(a):
    return b'\xAF' + _al(a)


def sta(a):
    return b'\x8F' + _al(a)


BEQ, BNE, BCC, BCS, BRA = 0xF0, 0xD0, 0x90, 0xB0, 0x80


def _refresh():
    import dq4ch1event
    return dq4ch1event.REFRESH


def _restore(a):
    """IN 이면 맡긴 순서로 일행 셋을 되돌리고 IN 과 맡긴 순서를 지운다. M 8 에서 들어와 M 8 로 나간다."""
    a(lda(FLAG_AT), 0x29, IN[1]).br(BEQ, 'restored')
    for k, shift in enumerate((ORDER_SHIFT, ORDER_SHIFT + 2)):
        a(lda(FLAG_AT), *(0x4A,) * shift, 0x29, 0x03)
        for t in ORDERS:
            a(sta(t + k))
    # 셋째는 0·1·2 가운데 남은 하나
    a(0xA9, 0x03, 0x38, b'\xEF' + _al(ORDERS[0]), 0x38, b'\xEF' + _al(ORDERS[0] + 1))
    for t in ORDERS:
        a(sta(t + 2))
    a(0xA9, 0x03)
    for c in COUNTS:
        a(sta(c))
    a(lda(FLAG_AT), 0x29, 0x0F & ~IN[1], sta(FLAG_AT))
    a(_refresh(), 0xE2, 0x20)
    a.label('restored')


def _leave():
    """대화 입구 1: 맡길 순서 첫 둘을 IN 바이트 위 니블에, 일행을 아리나 하나로. 이긴 수를 0 으로(FC 1D 이벤트 44)."""
    a = Asm()(ENTER)
    a(lda(ORDERS[0]), 0x29, 0x03, 0x48)                                   # PHA 순서 0
    a(lda(ORDERS[0] + 1), 0x29, 0x03, 0x0A, 0x0A, 0x03, 0x01)              # | 순서 1 << 2
    a(*(0x0A,) * ORDER_SHIFT, 0x83, 0x01)                                  # << 4, STA $01,S
    a(lda(FLAG_AT), 0x29, 0x0F & ~(IN[1] | LOST[1]), 0x03, 0x01, 0x09, IN[1], sta(FLAG_AT), 0x68)
    a(0xA9, 0x00)
    for t in ORDERS:
        a(sta(t))
    a(sta(STAGE_AT), 0xA9, 0x01)
    for c in COUNTS:
        a(sta(c))
    a(_refresh(), LEAVE)
    return a.bytes()


def _fight():
    """대화 입구 2(BRK 0E 뒤): 이긴 수 번째 상대와 싸운다. 이기면 BATTLE_WON 과 이긴 수를 올린다. 지면 전멸 처리 없이
    맵으로 돌아와 아리나를 되살려 HP 를 채우고 일행을 되돌린 뒤 LOST 를 켠다."""
    won = dq4ch2battle.WON_AT
    a = Asm()(ENTER, 0xE2, 0x30)
    a(lda(won), 0x29, 0x7F, sta(won))
    a(lda(STAGE_AT), 0xC9, ROUNDS - 1).br(BCC, 'pick')(0xA9, ROUNDS - 1)
    a.label('pick')(0x18, 0x69, GROUP0, 0x48)
    for r in (BATTLE_SONG, BATTLE_PREP, BATTLE_PREP2):
        a(0x22, _al(r))
    a(0x68, 0x22, _al(BATTLE_RUN), 0xC9, LOSE).br(BEQ, 'lost')
    # 이기면 링 위 상대를 다음 상대 그림으로. 전투 뒤 맵 화면을 되살리는 01:8A87 이 슬롯마다 그림(3220)으로 OBJ 타일을
    # 다시 올리므로 BATTLE_AFTER 앞에 바꾼다(맵 위에서 바로 올리면 화면이 켜져 있어 VRAM 에 써지지 않음)
    a(lda(STAGE_AT), 0x1A)
    for k in range(1, ROUNDS):
        a(0xC9, k).br(BNE, f'pic{k}')(0xA9, OPPONENT_PICS[k]).br(BRA, 'pic').label(f'pic{k}')
    a.br(BRA, 'after').label('pic')(sta(OPPONENT_PIC_AT)).label('after')
    a(0x22, _al(BATTLE_AFTER), 0xE2, 0x30)
    a(lda(won), 0x09, 0x80, sta(won), lda(STAGE_AT), 0x1A, sta(STAGE_AT)).brl('end')
    a.label('lost')(0xA9, 0x00, 0x22, _al(BATTLE_AFTER), 0xE2, 0x30)
    a(lda(ALENA_STATUS), 0x29, 0x0F, 0x09, 0x80, sta(ALENA_STATUS))
    a(0xC2, 0x20, lda(ALENA_MAX_HP), sta(ALENA_HP), 0xE2, 0x20)
    _restore(a)
    a(lda(FLAG_AT), 0x09, LOST[1], sta(FLAG_AT)).label('end')
    return a.bytes() + LEAVE


def _herb():
    """대화 입구 3: 아리나 물건 칸의 첫 약초를 빼고(뒤 칸을 당기고 장비 비트도 한 칸씩 내림) HP 를 HERB_HEAL 만큼."""
    a = Asm()(ENTER, 0xE2, 0x30, 0xA2, 0x00)
    a.label('find')(0xBF, _al(ALENA_ITEMS), 0xC9, HERB).br(BEQ, 'found')
    a(0xE8, 0xE0, ITEM_SLOTS).br(BCC, 'find').brl('end')
    a.label('found')(0xDA)                                                  # PHX: 칸 k
    a.label('shift')(0xE0, ITEM_SLOTS - 1).br(BCS, 'last')
    a(0xBF, _al(ALENA_ITEMS + 1), 0x9F, _al(ALENA_ITEMS), 0xE8).br(BRA, 'shift')
    a.label('last')(0xA9, 0xFF, sta(ALENA_ITEMS + ITEM_SLOTS - 1), 0xFA)   # PLX
    # 장비 비트: 칸 k 아래는 그대로, 위는 한 칸 내림. low = (1 << k) - 1, 새 = (m & low) | ((m >> 1) & ~low)
    a(0xC2, 0x20, 0xA9, 0x00, 0x00, 0xE0, 0x00).br(BEQ, 'low')
    a.label('ones')(0x38, 0x2A, 0xCA).br(BNE, 'ones')
    a.label('low')(0x48, lda(ALENA_EQUIP), 0x23, 0x01, 0x48)               # PHA low / AND $01,S / PHA
    a(lda(ALENA_EQUIP), 0x4A, 0x03, 0x03, 0x43, 0x03, 0x03, 0x01, sta(ALENA_EQUIP), 0x68, 0x68)
    a(lda(ALENA_HP), 0x18, 0x69, HERB_HEAL, 0x00, 0xCF, _al(ALENA_MAX_HP)).br(BCC, 'heal')
    a(lda(ALENA_MAX_HP))
    a.label('heal')(sta(ALENA_HP), 0xE2, 0x20).label('end')
    return a.bytes() + LEAVE


# 우승을 알린 왕의 말(FC 0385) 뒤 곡. NDS 투기장 관중석 스크립트(cccf2)가 같은 자리에서 곡을 멈추고 ME 46
# ファンファーレ大 를 튼 뒤 맵 곡으로 돌아온다. FC 는 곡이 없다. 끝나는 곡이어야 한다(dq4songwait.PORT_SONGS)
CHAMPION_SONG = 0x29


SONG_STOP, SONG_PLAY, SONG_FLUSH, SONG_WAIT = 0x24FE91, 0x24FE9A, 0x24FE44, 0x24FF0F


def _fanfare(song):
    """DQ5 25:FD00 처럼 1A·곡 틀기·대기열 비우기 뒤 24:FF0F 로 끝을 기다리고, 맵 곡($194B)을 24:FE9A 로 다시 튼다.
    25:FD00 끝의 00:CE61 대신 24:FE9A 인 까닭은 dq4ch1event._fanfare. DB 는 ENTER 가 둔 00."""
    jsl = lambda a: bytes((0x22,)) + _al(a)  # noqa: E731
    return (bytes((0x08, 0xE2, 0x20)) + jsl(SONG_STOP) +                      # PHP / SEP #$20 / JSL 24:FE91(1A)
            bytes((0xA9, song)) + jsl(SONG_PLAY) + jsl(SONG_FLUSH) +            # LDA #곡 / JSL 24:FE9A / JSL 24:FE44
            bytes((0xA9, song)) + jsl(SONG_WAIT) +                              # LDA #곡 / JSL 24:FF0F
            bytes((0xAD, 0x4B, 0x19, 0x29, 0x7F)) + jsl(SONG_PLAY) + b'\x28')   # LDA $194B / AND #$7F / JSL 24:FE9A / PLP


def _champion():
    """우승 뒤(인물 스크립트 37): 팡파르 뒤 일행을 되돌린다."""
    a = Asm()(ENTER, _fanfare(CHAMPION_SONG))
    _restore(a)
    return a.bytes() + LEAVE


def _clear(flag):
    return lda(FLAG_AT) + bytes((0x29, ~flag[1] & 0xFF)) + sta(FLAG_AT)


def _ring_cond():
    """인물 명령 05: 2장에 두 사람이 합류했고, 우승 뒤도 진 뒤도 아니며, 대회 중이거나 일행 셋이고, 주인공이 링 안이면
    A = 0. 대회 중(IN)이면 링 인물의 대화가 곧 다음 판이라, 대회 중 상태로 들어와도 이긴 수 번째 상대부터 잇는다."""
    near = bytes((0xC2, 0x30, 0xA9, 0x00, 0x00, 0x28, 0x6B))
    far = bytes((0xC2, 0x30, 0xA9, 0x01, 0x00, 0x28, 0x6B))
    a = Asm()(0x08, 0xE2, 0x30)
    a(lda(0x7E2190 + ch2.JOINED[0]), 0x29, ch2.JOINED[1]).br(BEQ, 'far')
    a(lda(FLAG_AT), 0x29, CHAMPION[1] | LOST[1]).br(BNE, 'far')
    a(lda(FLAG_AT), 0x29, IN[1]).br(BNE, 'rect')
    a(lda(COUNTS[0]), 0xC9, 0x03).br(BNE, 'far')
    a.label('rect')
    x0, y0, x1, y1 = RING
    for table, lo, hi in ((0x7E3020, x0, x1), (0x7E3080, y0, y1)):
        a(lda(table), 0x29, 0x7F, 0xC9, lo).br(BCC, 'far')(0xC9, hi + 1).br(BCS, 'far')
    a(near).label('far')(far)
    return a.bytes()


def _messenger_cond():
    """인물 명령 05: 우승했고 사자의 말을 아직 듣지 않았으며 주인공이 사자의 줄에 오면 A = 0."""
    import dq4prologue
    inside = dq4prologue._inside(*MESSENGER_ROW)
    far = bytes((0xC2, 0x30, 0xA9, 0x01, 0x00, 0x28, 0x6B))
    a = Asm()(0x08, 0xE2, 0x30, lda(FLAG_AT), 0x29, MESSENGER[1]).br(BNE, 'far')
    a(0x28).br(BRA, 'inside').label('far')(far).label('inside')(inside)
    return a.bytes()


def _event_bytes(tokens):
    return b''.join(bytes((0x60, t[1] & 0xFF, t[1] >> 8)) if isinstance(t, tuple) else t for t in tokens)


def _bed_tokens(ctx):
    """지면: 대기실 침대 옆으로 옮겨 크리프트·브라이의 말(FC 030D~0310)."""
    g, n = (int(v, 16) for v in BEDROOM.split('/'))
    bed = ctx.msg['bed'] if ctx.msg else 0
    return [bytes((0x90, g, n, *BED_CELL, 0x01, 0x80)) + bytes((0xC2,)) * 4, ('msg', bed), b'\xff']


# dq4brkscan: native() 이름 가운데 이벤트 스크립트 자료
DATA_ENTRIES = ('bed_event',)


def native(ctx):
    out = bytearray()
    at = {}

    def put(name, b):
        at[name] = ctx.code_at + len(out)
        out.extend(b)
    put('leave', _leave())
    put('fight', _fight())
    put('herb', _herb())
    put('champion', _champion())
    put('ring', _ring_cond())
    put('messenger_row', _messenger_cond())
    put('bed_event', _event_bytes(_bed_tokens(ctx)))
    put('bed', ch2._event_call(at['bed_event'], _clear(LOST)))
    return bytes(out), at


def events(ctx):
    return [_bed_tokens(ctx)]


def monster_doc(prg, dq5=None):
    """dq5tables/1 몬스터 칸: 필드 몬스터와 같은 FC 능력치·행동(dq4monport.fc_entry, 행동 번호 표는 이 모듈의 FC_ACTIONS 를
    포함). 사건 전투라 드롭은 없다(FF). dq5(원래 DQ5 롬 바이트)를 주면 MP 를 DQ5 주문 MP 에 맞춘다."""
    import dq4monport
    return [{"id": f"{m:02X}", **dq4monport.fc_entry(prg, fc, dq5=dq5)} for m, fc in MONSTERS.items()]


COUNT_WORDS = ('한', '두', '세', '네', '다섯')


def _pages(*speakers):
    """말하는 이가 바뀌는 메시지: (이름 또는 None, 쪽들)."""
    out = []
    for name, pages in speakers:
        part = speak(name, *pages) if name else say(*pages)
        out += part[:-1] + [ch1.PAGE]
    return out[:-1] + [ch1.END]


# FC 메시지 번호. 무술 대회 장면은 FC 원문을 옮겼다
MESSAGES = {
    # 037E·037F
    'cheer': _pages(('크리프트', ('공주님, 그럼 저는/여기서 응원하고/있겠습니다.',)),
                    ('브라이', ('부디 무운을/빌겠사옵니다!',))),
    # 0380
    'rules': speak('왕', '잘 왔다, 아리나 공주!/시합은 승자 진출전으로/다섯 명을 쓰러뜨리면/결승전에 나갈 수 있다!',
                   '지금까지 다섯 명을/쓰러뜨리고 올라온 자는/아직 데스피사로/하나뿐이다.', '그럼 시합을/시작하겠다!'),
    # 0381(이긴 수 1~4)
    **{f'win{k}': say(f'아리나 공주님/{COUNT_WORDS[k - 1]} 명 격파!') for k in range(1, ROUNDS)},
    # 047D·047E·047F
    'herb_ask': say('아리나여, 다음 시합에/대비해 가지고 있는/약초를 쓰겠는가?'),
    'herb_more': say('약초를 더/쓰겠는가?'),
    'no_herb': say('이런! 아리나는/약초를 가지고 있지/않지 않은가!'),
    'herb_used': narrate('아리나는 약초를/썼다!/상처가 회복되었다.'),
    # 0382(다음 상대)
    **{f'next{k}': say(f'다음 대전 상대는/{OPPONENTS[k][3]}/입니다!') for k in range(1, ROUNDS)},
    # 0383·0384·0385
    'final': _pages((None, ('아리나 공주님/다섯 명 격파!',)),
                    ('왕', ('아리나 공주여!/잘도 이겨 냈도다!', '이제부터 드디어/결승전이다!/데스피사로를/이리로 들라!')),
                    ('왕', ('어찌 된 것이냐?/어서 데스피사로를/불러오너라!',)),
                    ('왕', ('뭐라!? 아무리 찾아도/데스피사로가/없다고!?/으음…………', '…………',
                            '알았다!/없는 자는 어쩔 수/없는 노릇!', '무술 대회는/아리나 공주의/우승이로다!'))),
    # 0386·0387
    'champion': _pages(('브라이', ('공주님,/해내셨군요!',)),
                       ('크리프트', ('아리나 공주님,/우승을 축하드립니다!',))),
    # 030D~0310
    'bed': _pages(('크리프트', ('오오, 공주님!/정신이 드셨습니까!?',)),
                  ('브라이', ('참으로/아까웠사옵니다……',)),
                  ('크리프트', ('듣자 하니 시합 중에도/약초를 써도 된다던데……',)),
                  ('브라이', ('어쨌든 당분간은/수련을 더 쌓으셔야/겠습니다!', '자, 공주님/가시지요!'))),
    # 038F
    'messenger': say('아리나 공주님!/어서 산트하임 성으로/돌아가십시오!/으…… 크헉!'),
    # 2장 엔돌 사람 가운데 3장과 말이 다른 사람(FC 2장 시작 상태의 대화)
    'cook': say('매일 밤 저녁 메뉴를/생각하는 것도/힘들어요.'),                                    # 07EE
    'dislike': say('데스피사로라는 사람,/저는 아무래도/좋아지지가 않아요.'),                         # 054F
    'shop_old': say('아래 가게는/쉬느냐고?', '나도 이제 나이가/들어서 말이야./가게를 팔아 그 돈으로/은퇴라도 하고 싶은데……',  # 063B
                    '여기서 장사를/하고 싶다는 사람이/어디 없으려나.'),                                  # 063C
    'shop_buy': say('가게를 사고 싶다고?/장사꾼도 아닌/당신들한테는 무리야./그만두시게.'),           # 0548
    'entrant': say('당신들도/무술 대회에?/그런데 생각해 보면……',                                  # 07EF
                   '임금님께서 이렇게까지/강한 자를 모으시는/데에는 무슨 까닭이/있을 것 같군요.'),
    'daughter': say('우리 딸이 요즘/하늘만 쳐다보고/있어요.', '무슨 일일까요……'),                    # 07F0
    'bard': say('당신에게 승리의/노래를 바치지요./오른손엔 강철 발톱/랄랄라……'),                     # 07F2
    'casino': say('지하에 있는 카지노에/가 보셨나요?/아이고, 오늘은/한몫 벌었지 뭐예요.'),            # 07F1
    'sleep': say('새근새근……'),                                                                      # 07F3
    'ominous': say('대회에서는/데스피사로라는 자가/이기고 올라가고 있는데/어쩐지 불길한 이름이야……'),  # 07F5
    'dream': say('쿨쿨……/데스피사로 님/거기예요!/음냐음냐……'),                                     # 07F4
}

# 2장 엔돌 사람: (맵, 낮/밤, FC 칸) → 대화 이름. 자리와 그림은 3장 시작 상태와 같고 말만 다르다(FC 2장 시작 상태로
# 대화를 돌린 것. test_dq4ch2endor 가 FC 롬과 견준다)
TOWNSFOLK = {
    ('40/04', 'day', (0x08, 0x02)): 'cook',
    ('40/05', 'night', (0x05, 0x02)): 'dislike',
    ('40/08', 'day', (0x03, 0x03)): 'shop_old',
    ('40/08', 'night', (0x05, 0x02)): 'shop_buy',
    ('40/08', 'night', (0x01, 0x03)): 'shop_buy',
    ('40/0A', 'day', (0x06, 0x03)): 'entrant',
    ('40/0A', 'night', (0x07, 0x05)): 'daughter',
    ('40/0B', 'day', (0x07, 0x08)): 'bard',
    ('40/0B', 'day', (0x03, 0x01)): 'casino',
    ('40/0B', 'night', (0x03, 0x01)): 'casino',
    ('40/0B', 'night', (0x07, 0x08)): 'sleep',
    ('40/0B', 'night', (0x05, 0x08)): 'sleep',
    ('40/0B', 'night', (0x0B, 0x03)): 'ominous',
    ('40/0B', 'night', (0x01, 0x02)): 'dream',
}
# 대화 이름마다 FC 가 띄우는 메시지(test_dq4ch2endor 가 FC 대화를 2장 시작 상태로 돌려 견준다)
FC_SHOWS = {'cook': (0x7EE,), 'dislike': (0x54F,), 'shop_old': (0x63B, 0x63C), 'shop_buy': (0x548,),
            'entrant': (0x7EF,), 'daughter': (0x7F0,), 'bard': (0x7F2,), 'casino': (0x7F1,), 'sleep': (0x7F3,),
            'ominous': (0x7F5,), 'dream': (0x7F4,)}
TOWN_TALKS = tuple(dict.fromkeys(TOWNSFOLK.values()))
TALKS = ('ring', 'messenger') + TOWN_TALKS


def _msg(ctx, k):
    return {"op": "msg", "id": f"{ctx.msg[k]:03X}"}


def _flag_on(flag):
    return {"op": "flag-on", "index": flag[0], "mask": flag[1]}


def _is(flag, then, other=None):
    out = {"op": "if", "cond": {"code": "1B", "index": flag[0], "mask": flag[1]}, "then": then}
    return {**out, "else": other} if other is not None else out


def _stage_cond(k):
    """대화 조건: 이긴 수가 k. 조건 1A 는 바이트가 값과 「다름」 이라(dq5-text-format) 뒤집는다."""
    return {"code": "1A", "index": STAGE[0], "value": k, "not": True}


def _stage_is(k, then):
    return {"op": "if", "cond": _stage_cond(k), "then": then}


def _herbs(ctx, depth=3):
    """약초를 쓰겠느냐(047D) → 예이고 가졌으면 쓰고 「더 쓰겠느냐」(047E) 를 depth 번까지. 없으면 047F."""
    yes = {"code": "05"}
    has = {"code": "11", "item": HERB}
    use = [dq4ch2battle.talk_call(3), _msg(ctx, 'herb_used')]
    body = None
    for _ in range(depth):
        more = [_msg(ctx, 'herb_more'), {"op": "if", "cond": yes, "then": [body]}] if body else []
        body = {"op": "if", "cond": has, "then": use + more, "else": _msg(ctx, 'no_herb')}
    return [_msg(ctx, 'herb_ask'), {"op": "if", "cond": yes, "then": [body]}]


def _ring_talk(ctx):
    """링 인물의 대화. 대회 앞(IN 꺼짐): 응원 → 일행 빼기 → 왕의 말. 대회 중: 한 판 싸우고, 이기면 다섯째면 우승,
    아니면 「○ 명 격파」·약초·다음 상대. 끝에 ANSWERED(인물 스크립트가 기다림)."""
    bout = [dq4ch2battle.talk_call(2), {"op": "if", "cond": dq4ch2battle.won_cond(), "then": [
        {"op": "if", "cond": _stage_cond(ROUNDS),
         "then": [_msg(ctx, 'final'), _flag_on(CHAMPION)],
         "else": [*(_stage_is(k, [_msg(ctx, f'win{k}')]) for k in range(1, ROUNDS)), *_herbs(ctx),
                  *(_stage_is(k, [_msg(ctx, f'next{k}')]) for k in range(1, ROUNDS))]}]}]
    enter = [_msg(ctx, 'cheer'), dq4ch2battle.talk_call(1), _msg(ctx, 'rules')]
    return [_is(IN, bout, enter), _flag_on(ch2.ANSWERED)]


def talk_scripts(ctx):
    bodies = {'ring': _ring_talk(ctx),
              'messenger': [_msg(ctx, 'messenger'), _flag_on(MESSENGER), _flag_on(ch2.ANSWERED)]}
    return [bodies[name] if name in bodies else [_msg(ctx, name)] for name in TALKS]


def _cmd(op, *args, **kw):
    return {"op": op, "args": list(args), **kw}


def _wait_answer():
    a = ch2.ANSWERED
    return [_cmd('09', 0x80 | a[0], a[1]), _cmd('11', a[0], ~a[1] & 0xFF)]


def scripts(ctx):
    at, base = ctx.at, ctx.base
    call = lambda a: _cmd('37', *_al(a))  # noqa: E731
    lo, hi = (lambda v: v & 0xFF), (lambda v: v >> 8)
    msg = lambda k: _cmd('21', lo(ctx.msg[k]), hi(ctx.msg[k])) if ctx.msg else _cmd('21', 0, 0)  # noqa: E731
    ring = [_cmd('28'), _cmd('52'), _cmd('05', *_al(at['ring'])), _cmd('3F'),
            call(base['talk_here']) | {"label": "bout"}, *_wait_answer(),
            _cmd('06', *CHAMPION, target='won'), _cmd('06', *LOST, target='lost'), _cmd('03', target='bout'),
            call(at['champion']) | {"label": "won"}, msg('champion'), _cmd('40'), _cmd('16'),
            call(at['bed']) | {"label": "lost"}, _cmd('16')]
    messenger = [_cmd('05', *_al(at['messenger_row'])), _cmd('3F'), call(base['talk_here']), *_wait_answer(),
                 _cmd('40'), _cmd('16')]
    return [{"address": SCRIPTS['ring'][1], "commands": ring},
            {"address": SCRIPTS['messenger'][1], "commands": messenger}]


def _src(name):
    return {"list": SCRIPT_LIST, "index": SCRIPTS[name][0]}


def _at(e):
    return (e["fields"]["x"], e["fields"]["y"])


def npc_lists(lists, ctx):
    t = ctx.talk
    if ARENA not in lists:
        return [], []           # 인물 없이 옮긴 목록(dq4npcport.port 의 with_people=False)
    ring = {"from": _src('ring'), "time": "day",
            "fields": {"x": 0, "y": 1, "facing": "down", "talk": t['ring'], "gfx": 0x01, "layer": 0, "interval": 1}}
    messenger = {"from": _src('messenger'), "time": "day",
                 "fields": {"x": MESSENGER_CELL[0], "y": MESSENGER_CELL[1], "facing": "down", "talk": t['messenger'],
                            "gfx": MESSENGER_PIC, "layer": 0, "interval": 1}}
    # 대회 앞·대회 중에는 첫 상대가 링에 서 있고, 판을 이기면 _fight 가 그림을 다음 상대로 바꾼다. 우승 뒤에는 없음
    opponent = {"from": STAND, "time": "day",
                "fields": {"x": OPPONENT_CELL[0], "y": OPPONENT_CELL[1], "facing": "down", "talk": t['ring'],
                           "gfx": OPPONENT_PICS[0], "layer": 0, "interval": 0}}
    new = [{"name": ARENA_LIST, "entries": [opponent] + list(lists[ARENA]["entries"]) + [ring]},
           {"name": ARENA_DONE, "entries": list(lists[ARENA]["entries"]) + [ring]},
           {"name": TOWN_SEEN, "entries": list(lists[TOWN]["entries"])},
           # 사자는 목록 맨 앞(물체 슬롯 08): 뒤에 두면 마을 사람 그림 뒤에 실려 타일이 OBJ VRAM 끝을 넘었다(실측)
           {"name": TOWN_MESSENGER, "entries": [messenger] + list(lists[TOWN]["entries"])}]

    def on(m, flag, name):
        return {"map": m, "flag": flag[0], "when": "on", "mask": flag[1], "list": f"new:{name}"}
    # 대체 표는 앞 줄부터 맞는 첫 줄을 쓴다: 나중 상태를 먼저
    over = [on(TOWN, MESSENGER, TOWN_SEEN), on(TOWN, CHAMPION, TOWN_MESSENGER), on(ARENA, CHAMPION, ARENA_DONE),
            on(ARENA, ch2.CHAPTER2, ARENA_LIST)]
    by_map = {}
    for (m, time, fc), name in TOWNSFOLK.items():
        by_map.setdefault(m, {})[(time, cell(*fc))] = name
    for m, table in sorted(by_map.items()):
        hit, entries = set(), []
        for e in lists[m]["entries"]:
            key = (e["time"], _at(e))
            if key in table:
                hit.add(key)
                e = {**e, "fields": {**e["fields"], "talk": t[table[key]]}}
            entries.append(e)
        if hit != set(table):
            raise SystemExit(f'엔돌 {m}: 2장 대화를 줄 인물이 없음 {sorted(set(table) - hit)}')
        name = f'ch2_endor_{m.replace("/", "")}'
        new.append({"name": name, "entries": entries})
        over.append(on(m, ch2.CHAPTER2, name))
    return new, over
