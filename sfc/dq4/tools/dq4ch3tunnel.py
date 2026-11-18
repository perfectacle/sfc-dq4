"""DQ4 3장 굴과 장 끝(dq4ch3slots 'T'): 굴 공사비, 공사 재개, 뚫린 굴, 굴을 지나 3장 끝.

FC 그룹 42(エンドール 와 ブランカ 를 잇는 굴)는 SFC 그룹 47 이다(dq4groupbuild): 47/00 = 막힌 42/00, 47/01 = 뚫린 42/01.
FC 차례(fc/dq4/docs/dq4-chapter3-format.md 「사건 차례」 22~25·「굴과 장 끝」):
  1. 42/00 노인(대화 06C): 0892 「はい」 → 가게가 있으면 60000G 를 받고 0896·0897($6287|=40, $6285|=10), 모자라면 0895,
     가게가 없으면 0894, 「いいえ」 0893. $6285&10 인 동안(필드에 나가기 전)은 0897.
  2. 필드에 나갔다 와서 다시 말을 걸면 0898, $6287|=80(공사 재개).
  3. 굴이 뚫리면 필드 (79,5D) 가 42/01 (05,0F) 로 간다. 42/01 에는 이주민 둘이 서쪽 출구로, 나그네가 동쪽 출구로 걸어
     빠진다(블록 05:$BC90·$BCCE).
  4. 42/01 동쪽 계단 (1F,02) 으로 나가면 장 끝(1A:$B86E): 서술 037C → 장 끝 곡 → 기록 → 4장.

포팅: 공사 재개 뒤 엔돌 40/01 에 들면 소식(엔돌 모듈의 NOTICE)이 오고, 엔돌 네네의 대화(엔돌 모듈이 news_talk 로 감쌈)가
개통을 알리며 OPENED 를 켠다. 필드에 나갔다 온 것은 47/00 이 필드에서만 들어오는 맵이라는 점으로 안다(맵에 들 때 보이지
않는 인물이 WAITING 을 끔). 장 끝은 2장 끝과 같은 꼴로 서술 → 3장 엔딩 곡 → dq4chapterbox.ENDING3(「제4장 몬바바라의 자매 /
― 다음에 계속 ―」) → 타이틀이다. 형식은
sfc/dq4/docs/dq4-chapter3-format.md 「굴과 장 끝」.
"""
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[1] / 'dq5' / 'tools')]

import dq4chapter1 as ch1  # noqa: E402
import dq4ch2event as ch2  # noqa: E402
from dq4chapterbox import ENTER, LEAVE, fade, wait  # noqa: E402

IDX = 0x77                      # 7E:2207
PAID = (IDX, 0x01)              # 공사비를 냄(FC $6287&40)
WAITING = (IDX, 0x02)           # 낸 뒤 아직 필드에 나가지 않음(FC $6285&10). 47/00 에 들 때 끔
RESUMED = (IDX, 0x04)           # 공사 재개(FC $6287&80)
OPENED = (IDX, 0x08)            # 굴이 뚫림: 엔돌 네네의 알림을 들음(FC $62AA&08). news_talk 이 켬
FLAGS = (PAID, WAITING, RESUMED, OPENED)
# 필드 (79,5D) 가 47/01 로 가는 조건
OPEN = OPENED

GROUP = 0x47
BLOCKED, OPEN_MAP = '47/00', '47/01'
END_SCENE = 'end3'              # dq4chapterbox.ENDING3 의 이름
# 장 끝 곡: 곡 자리 14 エンディング第三章(FC 곡 0A, dq4sound-game.args). 밤낮으로 고르는 곡이 아니라 그대로 간다
ENDING_SONG = 0x14
SONG_STOP, SONG_PLAY = 0x24FE91, 0x24FE9A
SONG_WAIT_MAX = 300             # 곡 자료를 SPC 로 보내는 데 약 120프레임(dq4ch2ending.SONG_WAIT_MAX 와 같음)
HERO_X, HERO_Y = 0x7E3020, 0x7E3080
FLAG_AT = 0x7E2190


def cell(x, y):
    """FC 칸 → 옮긴 인물·도착 셀(dq4npcport.cell, dq4groupbuild.cell)."""
    return (2 * x, 2 * y + 1)


# FC 42/01 동쪽 계단 (1F,02)(필드 (84,5A) 로 나가는 출구). FC 는 이 계단을 밟아 나갈 때 장 끝 검사(1A:$B86E, $44 = 1F)
# 가 걸린다(열 1F 를 걷기만 해서는 걸리지 않음, 실측). DQ5 는 계단에 닿는 걸음 끝에 출구로 나가 인물 스크립트가 끼어들
# 틈이 없다(실측: 계단 칸을 보고 조작을 막아도 필드로 나감). 그래서 장 끝 인물을 계단 위에 보이지 않게 세워 계단을
# 막고, 주인공이 계단 앞 칸에서 계단 쪽 방향 키를 누르면(계단으로 나가려 하면) 장 끝을 건다
END_STAIRS = (0x1F, 0x02)
# (계단 앞 FC 칸, 그 쪽 방향 키 $4219 비트): 왼쪽 (1E,02) 에서 오른쪽, 아래 (1F,03) 에서 위
END_APPROACH = (((0x1E, 0x02), 0x01), ((0x1F, 0x03), 0x08))
# 뚫린 뒤 엔돌 쪽 입구(필드 (79,5D))로 드는 자리: 42/01 (05,0F) 계단
OPEN_ARRIVAL = cell(0x05, 0x0F)

# 옮긴 인물(FC 칸): 42/00 인부 둘·노인, 42/01 이주민 둘(서쪽으로)·노인·나그네(동쪽으로)·안내인
WORKERS = ((0x0E, 0x02), (0x0E, 0x03))
OLD_MAN = (0x12, 0x0A)
MIGRANTS = ((0x16, 0x04), (0x17, 0x04))
OLD_MAN_OPEN, TRAVELER, GUIDE = (0x12, 0x0E), (0x0C, 0x07), (0x13, 0x03)
# FC 걷기 블록의 목표 칸 차례(05:$BC90 이주민, 05:$BCCE 나그네). 끝 칸에서 숨는다(FC 명령 08)
MIGRANT_PATH = ((0x12, 0x04), (0x12, 0x06), (0x0A, 0x06), (0x0A, 0x0C), (0x05, 0x0C), (0x05, 0x0F))
# FC 나그네는 계단 (1F,02) 에서 숨지만, 그 칸에는 장 끝 인물이 서 있어 바로 아래 (1F,03) 에서 숨는다
TRAVELER_PATH = ((0x13, 0x07), (0x13, 0x05), (0x1F, 0x05), (0x1F, 0x03))

# 걷는 인물은 FC 처럼 한 칸(FC 칸, 셀 둘)씩 걷는다(pace). 걸음마다 지금 자리에서 그 토막 끝까지의 셀 사각형을 옆으로
# GAP 셀, 앞으로 GAP 셀 넓힌 곳에 주인공이 있으면 기다린다. 인물은 2×2 셀이라 셀 차가 2 보다 작으면 겹쳐 보이고, 걸음
# 도중에는 주인공 셀이 다음 셀로 먼저 바뀐다. 엔진의 걸음 막기만 믿으면 주인공이 비키는 순간 인물이 그 칸으로 들어와 몇
# 프레임 겹쳤다(heroblock 실측 7프레임)
GAP = 2
# 한 칸에 드는 프레임(FC 실측: 이주민 96, 나그네 약 128). 한 칸 걸음(16프레임)이 끝나면 다음 이동 간격 차례에 pace 가 다음
# 칸을 정해, 간격 하나에 한 칸 간다(실측: 간격 32 에 32프레임마다 한 칸). 그래서 간격 = 칸 프레임
TILE_FRAMES = {'migrant': 96, 'traveler': 128}
# 둘째 이주민은 첫째 한 칸 뒤 (17,04)에서 같은 스크립트로 걷는다. 길의 첫 칸을 그 칸으로 둔다
WALKS = {'migrant': ((0x17, 0x04), MIGRANT_PATH), 'traveler': (TRAVELER, TRAVELER_PATH)}
NPC_SLOT = 0x7E0090                         # 스크립트를 돌리는 인물 슬롯(01:C800 이 둠)
NPC_X, NPC_X_HI, NPC_Y, NPC_Y_HI = 0x7E3020, 0x7E3040, 0x7E3080, 0x7E30A0
GOAL_X, GOAL_X_HI, GOAL_Y, GOAL_Y_HI = 0x7E3560, 0x7E3580, 0x7E35A0, 0x7E35C0   # 명령 13 의 자리

# 빌린 인물 스크립트(DQ5 04/03 목록 05:996C, dq4ch3slots T). 칸마다 (칸 번호, 스크립트 길이 바이트 주소, 그 길이)
SCRIPT_LIST = '05:996C'
SCRIPTS = {'migrant': (0, '05:9973', 48), 'traveler': (1, '05:99AB', 36), 'ender': (2, '05:99D7', 28),
           'notice': (3, '05:99FB', 28), 'reset': (7, '05:9A6E', 10)}
# 개통 소식: FC 1C:$9C8C 는 $6287&80(공사 재개)이면 엔돌 04/01(SFC 40/01 카지노)에 들 때
# $6286|=01. 그 flag 는 엔돌 모듈의 NOTICE 이고, 엔돌 네네가 news_talk 로 그것을 본다. 3장 동안의 닫힌 카지노
# 목록(dq4ch3towns)이 기본 목록에서 이 인물을 베껴 간다
NOTICE_MAP = '40/01'

# 맵에 들 때의 도착: 2A:F28D 의 맵별 예외는 그룹이 16 이 아니면 2A:F29D 의 CMP #$28 / BNE 로 다음 예외로 간다. 그
# 4바이트를 JML 훅으로 바꿔, 그룹 47 의 맵 00 도착이고 OPEN 이면 47/01 계단으로 바꾼다(입구별 도착 훅 dq4entrancehook
# 이 $BD·$C1·$C2 를 정한 뒤다). 층 $C3·방향 $198E 는 그 훅이 정한 값(층 1, 방향 0) 그대로다
ENTER_SITE, ENTER_ORIG = 0x2AF29D, bytes((0xC9, 0x28, 0xD0, 0x18))
ENTER_NEXT, ENTER_28 = 0x2AF2B9, 0x2AF2A1
# dq4brkscan: PHP 로 시작하지 않는 진입점. enter 는 원래 코드의 P 를 그대로 이어 쓰는 JML 훅
CODE_ENTRIES = ('enter',)


def _al(a):
    return bytes((a & 0xFF, a >> 8 & 0xFF, a >> 16))


def _asm():
    from dq4ch2endor import Asm
    return Asm()


def legs(start, path):
    """[(토막 시작 셀, 끝 셀)]."""
    out, here = [], cell(*start)
    for goal in path:
        out.append((here, cell(*goal)))
        here = cell(*goal)
    return out


def tiles(walker):
    """길 처음부터 끝까지의 FC 칸 수(스크립트가 pace 를 되풀이할 횟수)."""
    return sum((abs(bx - ax) + abs(by - ay)) // 2 for (ax, ay), (bx, by) in legs(*WALKS[walker]))


def interval(walker):
    return TILE_FRAMES[walker]


def leg_rows(walker):
    """pace 표의 토막 줄(5바이트): 움직이는 축(0 = X, 1 = Y), 고정 축 셀, 움직이는 축의 작은·큰 셀, 끝 셀."""
    out = bytearray()
    for (ax, ay), (bx, by) in legs(*WALKS[walker]):
        along_y = ax == bx
        fixed, start, goal = (ax, ay, by) if along_y else (ay, ax, bx)
        out += bytes((int(along_y), fixed, min(start, goal), max(start, goal), goal))
    return bytes(out) + b'\xff'


def _pace(at, tables):
    """인물 명령 05(표를 쓰는 공용 루틴과 걷는 인물마다 입구). 인물 자리가 놓인 토막(시작 칸 포함, 끝 칸 뺌)을 표에서
    찾아, 주인공이 그 토막의 옆 GAP 셀 안이고 앞으로는 지금 자리부터 끝 + GAP 셀 안이면 A = 1(기다림). 아니면 걸어갈
    자리(명령 13 의 자리)를 지금 자리에서 끝 쪽으로 한 칸(셀 둘) 두고 A = 0. 길 위가 아니면(끝 칸) 자리를 그대로 두고
    A = 0 이라 뒤의 명령 14 가 곧바로 지나간다. at 은 이 코드가 놓일 주소, tables 는 {인물: 표 주소}(같은 뱅크).
    (바이트, {인물: 입구 주소})."""
    from dq4ch2endor import BCC, BEQ, BNE, BRA
    BPL = 0x10
    a = _asm()
    entries = {}
    names = list(tables)
    t = lambda k: (min(tables.values()) + k) & 0xFFFF   # noqa: E731
    base = min(tables.values())
    for i, w in enumerate(names):
        a.label(f'in_{w}')(0x08, 0xE2, 0x30, 0x8B, 0x4B, 0xAB, 0xA0, (tables[w] - base) & 0xFF)
        if i + 1 < len(names):
            a.brl('common')
    a.label('common')(0xAF, _al(NPC_SLOT), 0xAA)
    rd = lambda tab: (0xBF, _al(tab), 0x29, 0x7F)          # noqa: E731  LDA long,X / AND #$7F
    hero = lambda tab: (0xAF, _al(tab), 0x29, 0x7F)        # noqa: E731
    tb = lambda k: (0xB9, *t(k).to_bytes(2, 'little'))      # noqa: E731  LDA 표+k,Y
    cmp = lambda k: (0xD9, *t(k).to_bytes(2, 'little'))     # noqa: E731  CMP 표+k,Y
    a.label('loop')(*tb(0)).br(BPL, 'row').brl('none')
    a.label('row').br(BNE, 'vert')
    a(*rd(NPC_Y), *cmp(1)).br(BNE, 'next')(*hero(HERO_Y), 0x48, *hero(HERO_X), 0x48, *rd(NPC_X), 0x48).br(BRA, 'have')
    a.label('skip')(0x68, 0x68, 0x68)
    a.label('next')(0xC8, 0xC8, 0xC8, 0xC8, 0xC8).brl('loop')
    a.label('vert')(*rd(NPC_X), *cmp(1)).br(BNE, 'next')(*hero(HERO_X), 0x48, *hero(HERO_Y), 0x48, *rd(NPC_Y), 0x48)
    # 스택: 1,S 인물 자리, 2,S 주인공 움직이는 축, 3,S 주인공 옆 축
    a.label('have')(0xA3, 0x01, *cmp(2)).br(BCC, 'skip')
    a(*tb(3), 0xC3, 0x01).br(BCC, 'skip')
    a(0xA3, 0x01, *cmp(4)).br(BEQ, 'skip')
    a(0xA3, 0x03, 0x18, 0x69, GAP, *cmp(1)).br(BCC, 'go')
    a(*tb(1), 0x18, 0x69, GAP, 0xC3, 0x03).br(BCC, 'go')
    a(*tb(4), 0xC3, 0x01).br(BCC, 'dec')
    a(0xA3, 0x02, 0xC3, 0x01).br(BCC, 'go')
    a(*tb(4), 0x18, 0x69, GAP, 0xC3, 0x02).br(BCC, 'go').br(BRA, 'wait')
    a.label('dec')(0xA3, 0x01, 0xC3, 0x02).br(BCC, 'go')
    a(0xA3, 0x02, 0x18, 0x69, GAP, *cmp(4)).br(BCC, 'go')
    a.label('wait')(0x68, 0x68, 0x68, 0xAB, 0xC2, 0x30, 0xA9, 0x01, 0x00, 0x28, 0x6B)
    a.label('go')
    for here, there in ((NPC_X, GOAL_X), (NPC_X_HI, GOAL_X_HI), (NPC_Y, GOAL_Y), (NPC_Y_HI, GOAL_Y_HI)):
        a(0xBF, _al(here), 0x9F, _al(there))
    for axis, goal in ((0, GOAL_X), (1, GOAL_Y)):
        a.label(f'ax{axis}')
        if axis == 0:
            a(*tb(0)).br(BNE, 'ax1')
        a(*tb(4), 0xC3, 0x01, 0xBF, _al(goal)).br(BCC, f'down{axis}')
        a(0x18, 0x69, 0x02).br(BRA, f'put{axis}')
        a.label(f'down{axis}')(0x38, 0xE9, 0x02)
        a.label(f'put{axis}')(0x9F, _al(goal)).br(BRA, 'done')
    a.label('done')(0x68, 0x68, 0x68)
    a.label('none')(0xAB, 0xC2, 0x30, 0xA9, 0x00, 0x00, 0x28, 0x6B)
    code = a.bytes()
    # 입구마다 8바이트 앞머리와(마지막 입구 말고) common 으로 가는 BRL 3바이트
    entries = {w: at + k * 11 for k, w in enumerate(names)}
    return code, entries


def hero_rect(x, y):
    """FC 칸 → 주인공 셀 사각형(주인공은 FC 칸 (x, y) 에서 셀 2x~2x+1, 2y+1~2y+2 에 선다)."""
    return (2 * x, 2 * y + 1, 2 * x + 1, 2 * y + 2)


def _bump():
    """인물 명령 05: 주인공이 계단 앞 칸(END_APPROACH)에서 계단 쪽 방향 키를 누르고 있으면 A = 0, 아니면 1."""
    from dq4ch2endor import BCC, BCS, BEQ, BRA
    a = _asm()(0x08, 0xE2, 0x30)
    for k, (fc, pad) in enumerate(END_APPROACH):
        x0, y0, x1, y1 = hero_rect(*fc)
        for table, lo, hi in ((HERO_X, x0, x1), (HERO_Y, y0, y1)):
            a(0xAF, _al(table), 0x29, 0x7F, 0xC9, lo).br(BCC, f'no{k}')(0xC9, hi + 1).br(BCS, f'no{k}')
        a(0xAF, 0x19, 0x42, 0x00, 0x29, pad).br(BEQ, f'no{k}').br(BRA, 'yes')
        a.label(f'no{k}')
    a(0xC2, 0x30, 0xA9, 0x01, 0x00).br(BRA, 'end')
    a.label('yes')(0xC2, 0x30, 0xA9, 0x00, 0x00)
    a.label('end')(0x28, 0x6B)
    return a.bytes()


def _dark():
    """맵을 어둡게 한 뒤 주화면을 BG3(창)만으로: 검은 화면에 서술 창만 남는다. dq4prologue._darken 에서 곡 줄이기를
    뺀 것이다. FC 는 서술 동안 맵 곡을 그대로 두고, 서술이 끝난 뒤 장 끝 곡을 튼다."""
    return (ENTER + fade(14, 0, 2) +
            bytes((0xA9, 0x04, 0x8D, 0x33, 0x07, 0x8D, 0x2C, 0x21, 0x8D, 0x2D, 0x21)) + wait(1) +
            bytes((0xA9, 0x0F, 0x8D, 0x1D, 0x00)) + LEAVE)


def _ending_song():
    """맵 곡을 멈추고(1A) 장 끝 곡을 튼 뒤, 지금 곡($1D8B)이 그 곡이 될 때까지(상한 SONG_WAIT_MAX) 검은 화면으로 기다린다.
    기다리지 않으면 끝 상자가 곡보다 먼저 뜬다(dq4ch2ending.native 와 같은 기다림). FC 징글 동안(415프레임)은 끝 상자가
    먼저 부르는 「완」 상자(dq4chapterbox.DONE3)가 뜬다."""
    loop = (bytes((0xDA,)) + wait(1) + bytes((0xFA,                          # PHX / BRK 09 01 / PLX
            0xAD, 0x8B, 0x1D, 0xC9, ENDING_SONG, 0xF0, 0x03, 0xCA)))          # LDA $1D8B / CMP #곡 / BEQ 끝 / DEX
    return (ENTER + bytes((0x22,)) + _al(SONG_STOP) +                         # JSL 24:FE91
            bytes((0xA9, ENDING_SONG, 0x22)) + _al(SONG_PLAY) +               # LDA #곡 / JSL 24:FE9A
            bytes((0xE2, 0x20, 0xC2, 0x10, 0xA2, *SONG_WAIT_MAX.to_bytes(2, 'little'))) + loop +
            bytes((0xD0, -(len(loop) + 2) & 0xFF)) + LEAVE)  # BNE 고리


# FC 3장 끝(1A:$B8FF·다음 장 시작)을 지난 뒤의 값(실측: 금화 12345·맡긴 돈 1234·가방 다섯을 두고 계단으로): 금화 100(4장 시작
# 금화), 가방·맡긴 돈 비움, 3장 끝낸 장 비트. 톨네코 레코드는 그대로
NEXT_GOLD = 100


def _handover():
    """장 끝 곡 뒤, 끝 상자 앞에서 부른다. 3장 flag 를 끄고 3장만 쓰던 맡긴 동료 칸 43~49(dq4ch3slots.CHAPTER_END_CLEAR: 네네
    가게 물건·3장 변수)와 맡긴 물건·맡긴 금화를 0 으로, 금화를 NEXT_GOLD 로 둔다. 4장 넘김은 이 뒤에 4장 일행을 싣는다."""
    import dq4ch3event as ch3
    import dq4ch3slots as slots
    lo, hi = slots.CHAPTER_END_CLEAR
    body = bytearray(bytes((0xC2, 0x30)))
    # 첫 두 칸을 0 으로 두고 한 칸 뒤로 베껴 나가면 MVN 이 0 을 끝까지 민다(dq4ch3event._transfer 와 같음)
    for at, n in ((lo, hi - lo), (ch2.BANK_ITEMS_AT, ch2.BANK_ITEMS)):
        body += bytes((0xA9, 0x00, 0x00, 0x8F)) + _al(at) + ch2._mvn(at, at + 1, n - 1)
    body += bytes((0xA9, 0x00, 0x00, 0x8F)) + _al(ch2.BANK_GOLD_AT)
    body += bytes((0xA9, *NEXT_GOLD.to_bytes(2, 'little'), 0x8F)) + _al(ch2.GOLD_AT)
    body += bytes((0xE2, 0x20, 0xA9, 0x00, 0x8F)) + _al(ch2.GOLD_AT + 2)
    body += ch3._flag_off(ch3.CHAPTER3)
    return ENTER + bytes(body) + LEAVE


def _enter_hook():
    """2A:F29D 에서 JML(A = $BC, M8). 그룹 47 의 맵 00 도착이고 OPEN 이면 47/01 의 OPEN_ARRIVAL 로. 끝에 원래 4바이트
    (CMP #$28 / BNE)의 두 갈래로 JML."""
    from dq4ch2endor import BEQ, BNE
    x, y = OPEN_ARRIVAL
    a = _asm()(0xC9, GROUP).br(BNE, 'orig')
    a(0xA5, 0xBD).br(BNE, 'back')                                              # LDA $BD / BNE
    a(0xAF, _al(FLAG_AT + OPEN[0]), 0x29, OPEN[1]).br(BEQ, 'back')
    a(0xA9, int(OPEN_MAP[3:], 16), 0x85, 0xBD, 0xA9, x, 0x85, 0xC1, 0xA9, y, 0x85, 0xC2)
    a.label('back')(0xA5, 0xBC)
    a.label('orig')(0xC9, 0x28).br(BEQ, 'is28')(0x5C, _al(ENTER_NEXT))
    a.label('is28')(0x5C, _al(ENTER_28))
    return a.bytes()


def native(ctx):
    """(바이트, {이름: 주소}). 모두 ctx.code_at 부터 이 모듈 몫 안에 둔다."""
    out = bytearray()
    at = {}
    for name, code in (('bump', _bump()), ('dark', _dark()), ('ending_song', _ending_song()), ('handover', _handover()),
                       ('enter', _enter_hook())):
        at[name] = ctx.code_at + len(out)
        out += code
    # pace 루틴 뒤에 걷는 인물마다 표. 코드 길이는 표 주소와 상관없어(즉값 폭 고정) 한 번 세고 다시 짠다
    rows = {w: leg_rows(w) for w in WALKS}
    pace_at = ctx.code_at + len(out)
    size = len(_pace(pace_at, {w: pace_at for w in WALKS})[0])
    tables, k = {}, pace_at + size
    for w, r in rows.items():
        tables[w], k = k, k + len(r)
    code, entries = _pace(pace_at, tables)
    out += code + b''.join(rows.values())
    at.update({f'{w}_pace': e for w, e in entries.items()})
    return bytes(out), at


def hooks(ctx):
    return [(ENTER_SITE, ENTER_ORIG, bytes((0x5C,)) + _al(ctx.at['enter']))]


# FC 메시지를 옮겼다. 인물은 입말, 서술은 해라체
MESSAGES = {
    # 노인(06C): 0892·0893·0894·0895·0896·0897·0898
    'ask': ch1.say('동쪽 항구 마을로/가려고 이 동굴을/파기 시작했지.',
                   '배를 손에 넣어/온 세상의 보물을/모으는 게/내 꿈이었다네.',
                   '하지만 돈도/바닥이 나고/나도 나이를/먹어 버렸지.',
                   '60000골드만 있으면/공사를 다시 할 텐데……/어떤가? 내 꿈을/이어 주지 않겠나?'),
    'refused': ch1.say('그런가, 아쉽구먼.'),
    'no_shop': ch1.say('오오, 고맙네!/그럼 우선 자네/가게부터 가지게나./모든 건 그다음일세!'),
    'short': ch1.say('오오, 이어 주겠나!?/그럼 60000골드를/가져오기를/기다리고 있겠네!'),
    'paid': ch1.say('세상에, 해 주겠나!?/60000골드, 분명히/받았네!'),
    'plan': ch1.say('이 돈으로 사람을/구해서 당장 공사를/다시 시작하겠네!/기대하며 기다리게나!'),
    'resumed': ch1.say('오오, 톨네코 씨!/덕분에 공사를/다시 시작할 수/있었다네!',
                       '완성되면/자네 집 쪽으로/알릴 테니/기다려 주게나.'),
    # 인부(2E3·2E4 → 0682·0683)
    'dig': ch1.say('파고 파고/또 파고……', '엔돌의 카지노가/드디어 다시/문을 열었다더라./제길, 빨리 하고 싶네!'),
    'heave': ch1.say('영차 영차!'),
    # 뚫린 굴: 이주민(2E8·2E7 → 0687·0686), 노인(06D → 08A5), 나그네(06E → 08A6), 안내인(06F → 08A7)
    'migrant_woman': ch1.say('엔돌에는 카지노랑/술집이 있다니까/우리도 일자리를/얻을 수 있을 거야!'),
    'migrant_man': ch1.say('우리는 엔돌로/갈 생각이야.'),
    'opened': ch1.say('오오, 톨네코 씨!/동굴이 뚫렸다네!', '내 꿈을 이어서/온 세상의 보물을/모아 주게나!'),
    'traveler': ch1.say('전설의 무기를/찾아 여행하고/있소.', '동굴을 빠져나가/동쪽 나라로 가면/분명 실마리를/얻을 수 있을 거요.'),
    'guide': ch1.say('여러 사람들이/저마다 꿈을 안고/이곳을 지나갑니다.', '톨네코 님!/부디 조심해서/가십시오!'),
    # 엔돌 네네의 개통 알림(075): 08A0 → 「예」 08A2·「아니요」 08A4 → 08A3. 알림 전 공사 재개 뒤면 08A1
    'news': ch2._speaker_pages('네네', '여보, 어서 와요!/방금 소식이 왔는데/동굴이 뚫렸대요!',
                               '그런데 저는/무슨 말인지/잘 모르겠어서……', '설마 당신……/또 여행을 떠날/생각이에요?'),
    'news_yes': ch2._speaker_pages('네네', '알았어요./이제 아무 말도/안 할게요.'),
    'news_no': ch2._speaker_pages('네네', '괜찮아요./그런 거짓말로/저를 달래지/않아도 돼요……',
                                  '저도 천공의 검/소문은 들었어요./그걸 찾으러 갈/생각이죠……'),
    'news_farewell': ch2._speaker_pages('네네', '당신은 늘/꿈이 없으면/못 사는 사람……',
                                        '그런 당신이라서/나도 좋아하게/된 거겠죠.',
                                        '다녀와요, 여보!/언제까지나/기다릴게요!'),
    'no_news': ch2._speaker_pages('네네', '여보, 어서 와요!/네? 무슨 소식이요?/아뇨, 아무것도/안 왔는데요.',
                                  '그보다 여보,/일하느라/피곤하죠?',
                                  '카지노가 다시/열었다던데/가끔은 놀다/와요. 네?'),
    # 장 끝 서술(037C)
    'end': ch1.narrate('이리하여 톨네코는/전설의 무기와/보물을 찾아/동쪽으로 길을 떠났다.',
                       '모든 무기를 손에 넣어/세계 제일의/무기상인이 되는 것./그것이 톨네코의 꿈이었다.'),
}
TALKS = ('old_man', 'dig', 'heave', 'migrant_woman', 'migrant_man', 'opened', 'traveler', 'guide')
CALLS = {'pay_works': ('pay', 60000)}

YES_COND = {"code": "05"}


def talk_scripts(ctx):
    pay = [ctx.call('pay_works'),
           ctx.when(ctx.paid(), [ctx.say('paid'), ctx.say('plan'), ctx.flag_on(PAID), ctx.flag_on(WAITING)],
                    [ctx.say('short')])]
    # 가게를 산 뒤(엔돌 모듈의 SHOP, FC $6286&20)에만 받는다. FC 는 「はい」 뒤에 본다
    import dq4ch3endor
    ask = [ctx.say('ask'), ctx.when(YES_COND, [ctx.when(ctx.flag(dq4ch3endor.SHOP), pay, [ctx.say('no_shop')])],
                                    [ctx.say('refused')])]
    old_man = [ctx.when(ctx.flag(WAITING), [ctx.say('plan')],
                        [ctx.when(ctx.flag(PAID), [ctx.say('resumed'), ctx.flag_on(RESUMED)], ask)])]
    return [old_man] + [[ctx.say(name)] for name in TALKS[1:]]


def _own(ctx):
    """다른 3장 모듈의 Context(ctx)와 같은 번호 매김으로 만든 이 모듈의 Context(메시지 번호만 씀)."""
    import dq4ch3event as ev
    before = len(ev.MESSAGES)
    for key, mod in ev.modules():
        if key == ctx.key:
            break
        before += len(getattr(mod, 'MESSAGES', {}))
    first = min(ctx.msg.values()) - before if ctx.msg else None
    return next(c for c in ev.contexts(first) if c.key == 'T')


def news_talk(ctx, entered, otherwise):
    """엔돌 네네의 대화(FC 075)에 끼울 갈래. ctx 는 부르는 모듈(엔돌)의 Context, entered 는 공사 재개 뒤 엔돌 가게
    (FC 04/01)에 들어감 flag(FC $6286&01, 엔돌 모듈 몫), otherwise 는 네네의 원래 대화 명령. entered 면 개통 알림 뒤
    OPENED 를 켜고(필드 입구가 뚫린 굴로), 아니고 공사 재개 뒤면 「소식 없음」. 메시지는 이 모듈 것이다."""
    own = _own(ctx)
    say = own.say
    news = [say('news'), own.when(YES_COND, [say('news_yes')], [say('news_no')]), say('news_farewell'),
            own.flag_on(OPENED)]
    return [own.when(own.flag(entered), news, [own.when(own.flag(RESUMED), [say('no_news')], otherwise)])]


def _cmd(op, *args, **kw):
    return {"op": op, "args": list(args), **kw}


def _walk(ctx, walker):
    """FC 걸음 빠르기: 이동 간격을 칸 프레임으로 두고(1D), 셀마다 8프레임(1E 01) 걸음으로 pace → 도착 → 되풀이를
    길의 칸 수만큼(02 n … 01). 남는 되풀이는 끝 칸에서 pace 가 자리를 그대로 두어 곧바로 지나간다."""
    return [_cmd('1E', 0x01), _cmd('1D', interval(walker)), _cmd('02', tiles(walker)),
            _cmd('05', *_al(ctx.at[f'{walker}_pace'])), _cmd('14'), _cmd('01')]


def scripts(ctx):
    at, msg = ctx.at, ctx.msg
    lo, hi = (lambda v: v & 0xFF), (lambda v: v >> 8)
    call = lambda a: _cmd('37', *_al(a))  # noqa: E731
    # 끝 상자 장면. 4장으로 넘기는 빌드가 생기면 handover 뒤 끝 상자 대신 4장 넘김을 부른다
    end_box = (ctx.points or {}).get(END_SCENE, 0)
    out = {
        # 계단으로 나가려 하면: 조작을 막고 검은 화면 → 서술 → 장 끝 곡 → 넘김 값 → 「완」·「다음에 계속」 상자, 버튼을 누르면
        # 타이틀(돌아오지 않음)
        'ender': [_cmd('28'), _cmd('05', *_al(at['bump'])), _cmd('3F'), call(at['dark']),
                  _cmd('21', lo(msg['end']), hi(msg['end'])), call(at['ending_song']), call(at['handover']),
                  call(end_box), _cmd('16')],
        # 조작을 막지 않고 FC 빠르기로 한 칸씩 걷는다. 주인공이 앞 길 둘레에 있으면 비킬 때까지 기다린다(위 GAP)
        'migrant': _walk(ctx, 'migrant') + [_cmd('52'), _cmd('16')],
        'traveler': _walk(ctx, 'traveler') + [_cmd('52'), _cmd('16')],
        # 40/01 에 들 때 공사 재개 뒤면 소식이 옴
        'notice': [_cmd('28'), _cmd('52'), _cmd('06', 0x80 | RESUMED[0], RESUMED[1], target='end'),
                   _cmd('10', *_notice()), _cmd('16', label='end')],
        # 47/00 은 필드에서만 들어오므로, 맵에 들 때 끄면 「필드에 나갔다 옴」 이다
        'reset': [_cmd('28'), _cmd('52'), _cmd('11', WAITING[0], ~WAITING[1] & 0xFF), _cmd('16')],
    }
    return [{"address": SCRIPTS[k][1], "commands": v} for k, v in out.items()]


def _notice():
    import dq4ch3endor
    return dq4ch3endor.NOTICE


def _src(name):
    return {"list": SCRIPT_LIST, "index": SCRIPTS[name][0]}


def _scripted(entries, where, name, talk):
    """옮긴 인물(셀 where, 낮·밤)을 빌린 스크립트 name 으로 걷게 한다. 간격 1 이면 프레임마다 한 명령."""
    hit = 0
    for k, e in enumerate(entries):
        if (e["fields"]["x"], e["fields"]["y"]) == where:
            entries[k] = {**e, "from": _src(name), "fields": {**e["fields"], "talk": talk, "interval": 1}}
            hit += 1
    if not hit:
        raise SystemExit(f'굴: {where} 에 걷게 할 인물이 없음')


def npc_lists(lists, ctx):
    """47/00·47/01 의 옮긴 목록에 한글 대화와 걷는 인물, 보이지 않는 인물(WAITING 끄기·장 끝)을 넣는다."""
    if BLOCKED not in lists:
        return [], []           # 인물 없이 옮긴 목록(dq4npcport.port 의 with_people=False)
    t = ctx.talk
    for where, name in ((OLD_MAN, 'old_man'), (WORKERS[0], 'dig'), (WORKERS[1], 'heave')):
        ctx.retalk(lists, BLOCKED, cell(*where), t[name])
    lists[BLOCKED]["entries"] += ch2._invisible(_src('reset'), t['old_man'])
    entries = lists[OPEN_MAP]["entries"]
    for where, name in ((MIGRANTS[0], 'migrant_woman'), (MIGRANTS[1], 'migrant_man')):
        _scripted(entries, cell(*where), 'migrant', t[name])
    _scripted(entries, cell(*TRAVELER), 'traveler', t['traveler'])
    for where, name in ((OLD_MAN_OPEN, 'opened'), (GUIDE, 'guide')):
        ctx.retalk(lists, OPEN_MAP, cell(*where), t[name])
    # 장 끝 인물: 계단 위에 보이지 않게 서서(28 만, 52 로 치우지 않음) 계단을 막는다
    ex, ey = cell(*END_STAIRS)
    entries += [{**e, "fields": {**e["fields"], "x": ex, "y": ey}} for e in ch2._invisible(_src('ender'), t['opened'])]
    lists[NOTICE_MAP]["entries"] += ch2._invisible(_src('notice'), t['opened'])
    return [], []


# FC 대화 번호(npccheck 의 시작 표 키)
FC_TALKS = {'old_man': 0x06C, 'dig': 0x2E3, 'heave': 0x2E4, 'opened': 0x06D, 'guide': 0x06F}


def start_messages(ctx):
    """3장 처음 상태에서 서 있는 인물의 첫 메시지(걷는 이주민·나그네는 npccheck 가 건너뜀)."""
    m = ctx.msg
    first = {'old_man': 'ask', 'dig': 'dig', 'heave': 'heave', 'opened': 'opened', 'guide': 'guide'}
    return {(BLOCKED if name in ('old_man', 'dig', 'heave') else OPEN_MAP, talk, None): m[first[name]]
            for name, talk in FC_TALKS.items()}
