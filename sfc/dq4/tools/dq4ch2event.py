"""DQ4 2장 「말괄량이 공주의 모험」 첫머리: 1장 끝에서 2장으로 넘어가 산트하임 왕좌의 방(3D/01)에서 시작한다.

1장 끝 서술 뒤 네이티브 transfer 가 일행을 아리나 하나로 바꾸고(주인공 기록 0 을 아리나로 덮음), 이벤트 스크립트로
3D/01 에 옮긴다. 그 맵은 검게 불러오고(dq4chapterbox.CHAPTER2), 왕 자리의 인물 스크립트가 2장 제목 상자 → NDS 서두
서술 → 맵 밝히기 → 왕의 말을 돌린다. 형식은 sfc/dq4/docs/dq4-chapter2-format.md.
"""
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[1] / 'dq5' / 'tools')]

import dq4chapter1 as ch1  # noqa: E402
from dq4chapterbox import DB0, ENTER, LEAVE  # noqa: E402

# 깃발(7E:2190 + 첫 값). DQ5 가 켜기만 하고 비트로 보지 않는 자리(sfc/dq5/docs/dq5-flags.md)
CHAPTER2 = (0x78, 0x10)        # 7E:2208 bit4  2장 진행 중(1장 끝에서 켬). 주인공 그림을 아리나 대역으로
OPENING = (0x78, 0x40)         # 7E:2208 bit6  2장 첫머리(제목 상자·서두·왕의 말)를 기다림. 옮길 때 켜고 첫머리 끝에 끔
KICKED = (0x07, 0x40)          # 7E:2197 bit6  왕의 방 벽을 걷어참(FC $627F&02). 아래 이야기 깃발과 같은 빌린 묶음
JOINED = (0x5A, 0x02)          # 7E:21EA bit1  브라이·크리프트가 동료가 됨(FC $627F&01)
# 성문 병사·브라이·크리프트와 이야기함(FC $627E&02·04·08). 셋 다 이야기하면 왕의 방 벽 앞의 수리공이 낮에도 비킨다
# (FC 1C:$A0F7). DQ5 레ヌール城(04/06·04/07·04/02)의 인물·맵 루틴만 보거나 아무도 보지 않는 비트를 빌린다
TALKED_GATE = (0x0D, 0x01)     # 7E:219D bit0  DQ5 롬에서 켜는 곳도 보는 곳도 없음
TALKED_BREY = (0x06, 0x02)     # 7E:2196 bit1
TALKED_KIRYL = (0x06, 0x08)    # 7E:2196 bit3
READY = (0x07, 0x04)           # 7E:2197 bit2  셋 다 이야기함
# 맵을 옮길 때 지워지는 칸(7E:21A3). 벽 앞의 물음에 대답했음: 인물 스크립트가 대화가 끝나기를 기다린다
ANSWERED = (0x13, 0x01)
# 텐페 제물 사건. DQ5 롬에서 켜는 곳도 끄는 곳도 보는 곳도 없는 비트(dq5flags.py)
TEMPE_HEARD = (0x78, 0x01)     # 7E:2208 bit0  촌장의 부탁에 「예」(FC $6281&10)
TEMPE_GONE = (0x78, 0x02)      # 7E:2208 bit1  신부에게 제물 대신 가겠다고 함(FC $6281&08)
TEMPE_ALTAR = (0x78, 0x04)     # 7E:2208 bit2  바구니에 실려 제단 앞으로 옮겨짐. 다음 단계의 보스 전투가 볼 flag

THRONE = '3D/01'               # FC 01/01 산트하임 왕좌의 방
START_CELL = (0x09 * 2, 0x08 * 2 + 1)   # FC (09,08): 왕 앞
KING_CELL = (0x09 * 2, 0x07 * 2 + 1)    # FC (09,07), 옮긴 인물 자리(dq4npcport 의 2y+1)

# 스크립트를 빌리는 인물: 이 해킹에서 가지 않는 DQ5 맵의, 한 시간대에만 놓이는 스크립트 인물
KING_SRC, KING_SCRIPT = {"list": "05:C6C3", "index": 0}, "05:C6CA"       # 21/09
ASKER_SRC, ASKER_SCRIPT = {"list": "05:C433", "index": 7}, "05:C4BA"     # 21/00
OPENER_SRC, OPENER_SCRIPT = {"list": "05:89A3", "index": 7}, "05:8A07"   # 01/05
PRIEST_SRC, PRIEST_SCRIPT = {"list": "05:C433", "index": 0}, "05:C43A"   # 21/00

# 텐페(FC 0E/00). 촌장(대화 02C)과 신부(대화 029). 신부는 처음에는 옮긴 교회 그대로이고, 촌장에게 「예」 한 뒤에는
# 묻는 대화로 바뀐다. 「예」 하면 신부 자리의 스크립트가 바구니 이벤트를 걸어 제단 앞으로 옮긴다(FC 1C 이벤트 01)
TEMPE = '3D/03'
CHIEF = (0x15 * 2, 0x25 * 2 + 1)
PRIEST = (0x0C * 2, 0x18 * 2 + 1)
FC_CHIEF, FC_PRIEST = 0x02C, 0x029
ALTAR_CELL = (0x16 * 2, 0x0F * 2 + 1)      # 제단(FC (15~18,0D)) 두 칸 아래
NIGHT = 0x00F8

# 왕의 방(FC 01/02): FC 는 (0D,04)에서 오른쪽을 보고 しらべる 하면 판자로 막은 벽 (0E,04)를 걷어찬다(1E:$B8AD).
# DQ5 의 しらべる 는 앞의 인물을 부르지 않아(실측), 그 칸에서 오른쪽을 보면 보이지 않는 인물이 묻는다
BEDROOM = '3D/02'
CASTLE = '3D/00'
CARPENTER = (0x0D * 2, 0x04 * 2 + 1)    # FC 01/02 인물 1(대화 01D): 벽 앞 칸에 서 있는 수리공
GATE = ((0x0E * 2, 0x19 * 2 + 1), (0x0F * 2, 0x19 * 2 + 1))   # FC 01/00 성문 병사(대화 021·022)
BREY_AT = (THRONE, (0x0D * 2, 0x0D * 2 + 1))                # FC 01/01 인물(대화 01F)
KIRYL_AT = (CASTLE, (0x1A * 2, 0x0A * 2 + 1))               # FC 01/00 인물(대화 023)
WALL_STAND = (0x0D * 2, 0x04 * 2 + 2)   # 주인공이 서는 셀(실측: 벽 앞에서 7E:3020·3080 = 26,10)
FACE_RIGHT = 0x10                        # 7E:31E0 위 니블
WALL = (0x0E * 2, 0x04 * 2 + 1)          # 판자 벽 블록의 왼쪽 위 셀(셀 버퍼 실측: 28~29 열)
WALL_FLOOR_DX = -4                       # 같은 줄 FC 두 칸 왼쪽(FC (0C,04) 바닥 04)
KICK_STEPS = 4                           # 구멍 너머로 걸어 나가는 셀 수. 그 뒤 필드로(이벤트 91)

# 필드 걸음(00:8290 의 시간 올리기 앞 00:82CB)에서 걷어찬 뒤 걸음을 세어, FC 처럼 네 걸음째에 두 사람이 따라온다
STEP_HOOK_AT = 0x0082CB
STEP_HOOK_ORIG = bytes.fromhex('af90217e')         # LDA $7E2190
STEP_COUNT = 0x7E1C0A                              # 7E:1BBE~1C0C 는 DQ5 가 쓰지 않는 자리
JOIN_STEPS = 4
JOIN_RECORDS_AT = 0x7E2040 + 42                    # 일행 기록 1·2
SET_NEXT_EXP = 0x21805A                            # A = 일행 번호: 다음 레벨 경험치를 다시 셈

CODE_AT = 0x5EF000             # 1장 사건 코드(5E:D000~) 뒤
ALENA_PICTURE = 0x30           # 2장 동안 주인공 그림: DQ5 ビアンカ(인물 04) 그림을 대역으로
HERO_PICTURE_AT = 0x05D9A1     # 05:D98F 의 주인공 갈래(그림 2E·2D·3A 를 고름). JSL + RTS 로 덮는다
HERO_PICTURE_ORIG = bytes.fromhex('000b4000d003a92e60000b202ed003a93a60a92d60')

PARTY_AT = 0x7E2040            # 일행 기록 0(42바이트)
NAME_AT = 0x7E2001             # 주인공 이름 8바이트(음절마다 2바이트, 01 로 끝남)
GOLD_AT = 0x7E2019
# 1장 주인공(라이안) 기록과 이름 입력값을 맡겨 두는 곳: 사람 동료 칸(7E:294A, 32바이트 × 5)의 칸 2~4. 이 해킹은 칸을
# 쓰는 장면(ルイーダ·결혼식·석상)이 없다. 칸 첫 바이트 bit7 이 찬 칸 표시라 칸마다 +1 부터 둔다(기록은 31 + 11 바이트로 나눔)
SLOT_SIZE = 0x20
RYAN_RECORD_AT = (0x7E298B, 0x7E29AB)
RYAN_NAME_AT = 0x7E29CB
TIME_AT = 0x7E075E             # 필드 시간(0050 이 아침, F0 이상이 밤)
MORNING = 0x0050

ALENA_NAME = '아리나'
# FC 1장 시작 기록 7(ひめ): HP 16, MP 0, ちから 12, すばやさ 7, たいりょく 8, かしこさ 4, うんのよさ 1, Eきぬのローブ.
# DQ5 기록 +6 이 すばやさ, +7~+A 가 ちから·みのまもり·かしこさ·うんのよさ. たいりょく 는 1장처럼 みのまもり 자리에 둔다
ALENA_STATS = {'hp': 16, 'mp': 0, 'agility': 7, 'stats': (12, 8, 4, 1)}
SILK_ROBE = 0x62               # DQ5 きぬのローブ
GOLD = 100
# 두 사람은 DQ5 사람 기록을 빌린다(인물 번호가 이름 표 0·그림 표를 고름, 이름은 dq4groupbuild.PERSON_NAMES).
# 값은 FC 처음 기록 1(しんかん)·4(まほうつかい), 물건은 DQ5 こんぼう 02·たびびとのふく 43, ひのきのぼう 00·ぬののふく 42
RECRUITS = (
    {'name': '크리프트', 'person': 0x09, 'hp': 18, 'mp': 7, 'agility': 5, 'stats': (3, 9, 7, 2), 'items': (0x02, 0x43)},
    {'name': '브라이', 'person': 0x05, 'hp': 16, 'mp': 10, 'agility': 5, 'stats': (3, 7, 8, 2), 'items': (0x00, 0x42)},
)
PERSON_TABLE = 0x23C014        # 사람 기록 표(칸 = 인물 번호 & 3F, 42바이트)


def level_one(template, s, items):
    """사람 기록 틀(42바이트)을 FC 처음 값 s 의 1레벨로: 경험치 0, 물건은 items 를 앞 칸부터 모두 장비, 배운 주문 없음."""
    r = bytearray(template)
    r[2:4] = r[0xE:0x10] = s['hp'].to_bytes(2, 'little')
    r[4:6] = r[0x10:0x12] = s['mp'].to_bytes(2, 'little')
    r[6] = s['agility']
    r[7:0xB] = bytes(s['stats'])
    r[0xB:0xE] = bytes(3)
    r[0x12] = 1
    r[0x14:0x16] = ((1 << len(items)) - 1).to_bytes(2, 'little')
    r[0x16:0x22] = bytes(items) + b'\xff' * (12 - len(items))
    r[0x23:0x26] = bytes(3)
    return bytes(r)


def alena_record(hero):
    """원래 롬의 주인공 기록 틀(23:C014 칸 0, 42바이트)을 아리나 1레벨로 고친 것."""
    return level_one(hero, ALENA_STATS, (SILK_ROBE,))


def person_record(data, person):
    o = ch1.lorom(PERSON_TABLE + (person & 0x3F) * 42)
    return data[o:o + 42]


def recruit_records(data):
    return [level_one(person_record(data, r['person']), r, r['items']) for r in RECRUITS]


def name_bytes(name):
    import dq4nameentry as ne
    return b''.join(ne.code_bytes(ne.GLYPHS.index(ch)) for ch in name).ljust(8, b'\x01')


def _al(a):
    return bytes((a & 0xFF, a >> 8 & 0xFF, a >> 16))


def _mvn(src, dst, n):
    """n 바이트 복사. M·X 16 에서."""
    return bytes((0xA2, *(src & 0xFFFF).to_bytes(2, 'little'), 0xA0, *(dst & 0xFFFF).to_bytes(2, 'little'),
                  0xA9, *(n - 1).to_bytes(2, 'little'), 0x54, dst >> 16, src >> 16))


def _flag_or(flag):
    a = 0x7E2190 + flag[0]
    return bytes((0xAF,)) + _al(a) + bytes((0x09, flag[1], 0x8F)) + _al(a)


def _transfer(record_at, name_at, event_at):
    """1장 끝에서 부른다: 라이안 기록·이름을 맡기고, 일행을 아리나 하나로, 금화 100, 아침으로 두고, 2장 깃발을 켠 뒤
    3D/01 로 옮기는 이벤트를 건다."""
    import dq4prologue
    body = bytearray(bytes((0xC2, 0x30)))
    head = SLOT_SIZE - 1
    body += (_mvn(PARTY_AT, RYAN_RECORD_AT[0], head) + _mvn(PARTY_AT + head, RYAN_RECORD_AT[1], 42 - head) +
             _mvn(NAME_AT, RYAN_NAME_AT, 8))
    body += _mvn(record_at, PARTY_AT, 42) + _mvn(name_at, NAME_AT, 8)
    body += bytes((0xA9, *MORNING.to_bytes(2, 'little'), 0x8F)) + _al(TIME_AT)
    body += bytes((0xA9, *(GOLD & 0xFFFF).to_bytes(2, 'little'), 0x8F)) + _al(GOLD_AT)
    body += bytes((0xE2, 0x20, 0xA9, GOLD >> 16, 0x8F)) + _al(GOLD_AT + 2)
    # 일행 수·걷는 수와 사본 1, 순서 0, 마차 없음
    for a in (0x7E201D, 0x7E201E, 0x7E201F):
        body += bytes((0xA9, 0x01, 0x8F)) + _al(a)
    for a in (0x7E2020, 0x7E2028):
        body += bytes((0xA9, 0x00, 0x8F)) + _al(a)
    body += bytes((0xAF,)) + _al(0x7E201C) + bytes((0x29, 0x7F, 0x8F)) + _al(0x7E201C)
    body += _flag_or(CHAPTER2) + _flag_or(OPENING)
    body += DB0                                         # MVN 이 DB 를 7E 로 두었다. 이벤트 걸기는 DB 0 의 절대 주소
    start = dq4prologue._event_start(event_at)[len(ENTER):-len(LEAVE)]
    return ENTER + bytes(body) + start + LEAVE


def _skip_song():
    """맵을 불러올 때 곡을 바꾸지 않게(dq4chapterbox.SKIP_SONG): 제목 상자·서술 동안 곡이 없다. 맵 밝히기가 끈다."""
    import dq4chapterbox as box
    addr, bit = box.SKIP_SONG
    return ENTER + bytes((0xAF,)) + _al(addr) + bytes((0x09, bit, 0x8F)) + _al(addr) + LEAVE


def _hero_picture():
    """05:D9A1 대신: 2장 동안이면 아리나 대역 그림, 아니면 원래처럼 2190 bit6 꺼짐 2E, 21BE bit5 켜짐 2D, 아니면 3A.
    M 8 에서 부르고 A 에 그림 번호를 둔 채 돌아간다(부른 곳의 RTS 가 05:D98F 를 끝냄)."""
    flag = 0x7E2190 + CHAPTER2[0]
    return bytes((0xAF,)) + _al(flag) + bytes((0x29, CHAPTER2[1], 0xF0, 0x03, 0xA9, ALENA_PICTURE, 0x6B,
                                              0xAF)) + _al(0x7E2190) + bytes((0x29, 0x40, 0xD0, 0x03,
                                              0xA9, 0x2E, 0x6B, 0xAF)) + _al(0x7E21BE) + bytes((
                                              0x29, 0x20, 0xF0, 0x03, 0xA9, 0x2D, 0x6B, 0xA9, 0x3A, 0x6B))


def _hero_at_wall(away=False):
    """인물 명령 05: 주인공(슬롯 0)이 WALL_STAND 에서 오른쪽을 보면 A = 0, 아니면 1(away 면 반대)."""
    near = bytes((0xC2, 0x30, 0xA9, int(away), 0x00, 0x28, 0x6B))
    far = bytes((0xC2, 0x30, 0xA9, int(not away), 0x00, 0x28, 0x6B))
    # 인물 표 X·Y 의 bit7 은 자리 값이 아니라 지운다(dq4prologue._inside 와 같음)
    checks = [bytes((0xAF, 0x20, 0x30, 0x7E, 0x29, 0x7F, 0xC9, WALL_STAND[0], 0xD0)),
              bytes((0xAF, 0x80, 0x30, 0x7E, 0x29, 0x7F, 0xC9, WALL_STAND[1], 0xD0)),
              bytes((0xAF, 0xE0, 0x31, 0x7E, 0x29, 0xF0, 0xC9, FACE_RIGHT, 0xD0))]
    out = bytearray((0x08, 0xE2, 0x20))
    for k, c in enumerate(checks):
        rest = sum(len(x) + 1 for x in checks[k + 1:]) + len(near)
        out += c + bytes((rest,))
    return bytes(out) + near + far


def _open_wall():
    """판자 벽 2×2 셀을 같은 줄 바닥 셀의 +1~+7 로 덮고(+0 의 구역·차지 비트는 둠) 다시 그린다(1장 철창 열기와 같은 꼴)."""
    import dq4ch1event as e
    x0, y0 = WALL
    body = bytearray((0xE2, 0x30)) + e.DP_SAVE
    for y in range(y0, y0 + 2):
        for x in range(x0, x0 + 2):
            body += bytes((0xA2, x + WALL_FLOOR_DX, 0xA0, y, 0x22)) + _al(e.CELL_AT)
            body += bytes((0xA0, 0x07, 0xB7, 0x00, 0xBB, 0x9F)) + _al(e.SCRATCH) + bytes((0x88, 0xD0, 0xF6))
            body += bytes((0xA2, x, 0xA0, y, 0x22)) + _al(e.CELL_AT)
            body += bytes((0xA0, 0x07, 0xBB, 0xBF)) + _al(e.SCRATCH) + bytes((0x97, 0x00, 0x88, 0xD0, 0xF6))
    body += bytes((0xA9, 0x02, 0x8D, 0x82, 0x1E, 0x8D, 0x83, 0x1E))                  # 크기 2×2
    for redraw in (e.REDRAW_LOWER, e.REDRAW_UPPER):
        body += bytes((0xA2, x0, 0xA0, y0, 0x22)) + _al(redraw)
    body += bytes((0xE2, 0x30)) + e.DP_RESTORE
    return ENTER + bytes(body) + LEAVE


def _event_call(event_at, before=b''):
    """인물 스크립트(명령 37)에서 이벤트 스크립트를 건다. before 는 그 앞에 할 일(M 8, DB 0)."""
    import dq4prologue
    return ENTER + before + dq4prologue._event_start(event_at)[len(ENTER):]


def _join(records_at):
    """일행 기록 1·2 에 두 사람을 넣고 일행 수 3, 순서 0 1 2 로. 다음 레벨 경험치를 다시 센다."""
    n = len(RECRUITS)
    body = bytearray(bytes((0xC2, 0x30)) + _mvn(records_at, JOIN_RECORDS_AT, 42 * n) + DB0 + bytes((0xE2, 0x30)))
    for a in (0x7E201D, 0x7E201E, 0x7E201F):
        body += bytes((0xA9, 1 + n, 0x8F)) + _al(a)
    for k in range(1 + n):
        for a in (0x7E2020, 0x7E2028):
            body += bytes((0xA9, k, 0x8F)) + _al(a + k)
    for k in range(1, 1 + n):
        body += bytes((0xA9, k, 0x22)) + _al(SET_NEXT_EXP)
    import dq4ch1event
    body += dq4ch1event.REFRESH                          # 걷는 일행 그림을 다시 세운다(1장 합류와 같음)
    return ENTER + bytes(body) + LEAVE


def _step(join_event):
    """00:82CB 의 LDA $7E2190 대신: 2장에 벽을 걷어찼고 아직 합류 전이면 필드 걸음을 세어, JOIN_STEPS 걸음째에 합류
    깃발을 켜고 합류 이벤트를 건다. 끝에 원래 명령을 하고 돌아간다(M 8)."""
    import dq4prologue
    def flag(f):
        return 0x7E2190 + f[0]
    start = dq4prologue._event_start(join_event)[len(ENTER):-len(LEAVE)]
    count = (bytes((0xAF,)) + _al(STEP_COUNT) + bytes((0x1A, 0x8F)) + _al(STEP_COUNT) +
             bytes((0xC9, JOIN_STEPS, 0x90, len(_flag_or(JOINED)) + len(start))) + _flag_or(JOINED) + start)
    tests = [bytes((0xAF,)) + _al(flag(CHAPTER2)) + bytes((0x29, CHAPTER2[1], 0xF0)),
             bytes((0xAF,)) + _al(flag(KICKED)) + bytes((0x29, KICKED[1], 0xF0)),
             bytes((0xAF,)) + _al(flag(JOINED)) + bytes((0x29, JOINED[1], 0xD0))]
    body = bytearray()
    for k, t in enumerate(tests):
        rest = sum(len(x) + 1 for x in tests[k + 1:]) + len(count)
        body += t + bytes((rest,))
    body += count
    return ENTER + bytes(body) + LEAVE[:-1] + bytes((0xAF,)) + _al(0x7E2190) + bytes((0x6B,))


def native(data=None):
    """(바이트, {이름: 주소}). data: 원래 롬(기록 틀을 읽음). 없으면 0 으로 채워 주소만 센다."""
    hero = person_record(data, 0) if data is not None else bytes(42)
    out = bytearray(alena_record(hero) if data is not None else bytes(42))
    at = {'record': CODE_AT, 'name': CODE_AT + len(out)}
    out += name_bytes(ALENA_NAME)
    at['recruits'] = CODE_AT + len(out)
    out += b''.join(recruit_records(data)) if data is not None else bytes(42 * len(RECRUITS))
    g, n = (int(v, 16) for v in THRONE.split('/'))

    def put(name, code):
        at[name] = CODE_AT + len(out)
        out.extend(code)
    put('skip_song', _skip_song())
    put('event', bytes((0xA0, *_al(at['skip_song']), 0x90, g, n, *START_CELL, 0x01, 0x80, 0xFF)))
    put('transfer', _transfer(at['record'], at['name'], at['event']))
    put('hero_picture', _hero_picture())
    import dq4prologue
    put('talk_slot', dq4prologue._talk_slot())
    put('talk_event', bytes((0xA0, *_al(at['talk_slot']), 0xFF)))
    put('talk_here', dq4prologue._talk_here(at['talk_event']))
    put('at_wall', _hero_at_wall())
    put('away_wall', _hero_at_wall(away=True))
    put('open_wall', _open_wall())
    put('kick_walk', bytes((0x01, KICK_STEPS, 0x91, 0xFF)))
    # 걸음 수를 0 으로 두고 구멍 너머로 걸어 나가 필드로
    put('kick', _event_call(at['kick_walk'], bytes((0xA9, 0x00, 0x8F)) + _al(STEP_COUNT)))
    put('join', _join(at['recruits']))
    return bytes(out), at


def join_event(first_message, at):
    """합류 이벤트 토큰(dq4msgwait 가 메시지 끝 코드를 고를 때도 봄): 메시지 → 두 사람을 일행에."""
    m = message_ids(first_message)
    return [('msg', m['join']), bytes((0xA0, *_al(at['join']), 0xFF))]


def _event_bytes(tokens):
    return b''.join(bytes((0x60, t[1] & 0xFF, t[1] >> 8)) if isinstance(t, tuple) else t for t in tokens)


def altar_event(first_message):
    """바구니 이벤트 토큰: 신부·마을 사람의 배웅 → 서술 → 밤의 텐페 제단 앞으로(FC 1C 이벤트 01)."""
    m = message_ids(first_message)
    g, n = (int(v, 16) for v in TEMPE.split('/'))
    return [('msg', m['basket']), bytes((0x90, g, n, *ALTAR_CELL, 0x01, 0x80, 0xFF))]


def _night():
    """필드 시간을 밤으로(M 8). 맵을 다시 불러올 때 밤 목록·밤 색이 된다."""
    return bytes((0xA9, NIGHT & 0xFF, 0x8F)) + _al(TIME_AT) + bytes((0xA9, NIGHT >> 8, 0x8F)) + _al(TIME_AT + 1)


def tail_native(first_message, data=None):
    """native 뒤에 붙는 합류·바구니 이벤트와 걸음 훅. 메시지 번호가 이벤트 바이트에 들어가 native 와 따로 둔다."""
    code, at = native(data)
    base = CODE_AT + len(code)
    out = bytearray()
    tail = {}

    def put(name, b):
        tail[name] = base + len(out)
        out.extend(b)
    put('join_event', _event_bytes(join_event(first_message, at)))
    put('step', _step(tail['join_event']))
    put('altar_event', _event_bytes(altar_event(first_message)))
    put('altar_go', _event_call(tail['altar_event'], _night()))
    return bytes(out), tail


def _speaker_pages(name, *pages):
    """한 사람이 쪽마다 이름을 다시 달고 말한다(FC 「ブライ「」 처럼)."""
    out = []
    for text in pages:
        out += ch1.speak(name, text)[:-1] + [ch1.PAGE]
    return out[:-1] + [ch1.END]


def _join_pages():
    """FC 030A: 말하는 이가 쪽마다 바뀌고 끝에 서술."""
    out = []
    for name, text in (('브라이', '공주님! 혼자서/여행을 떠나시다니/당치도 않습니다!'),
                       ('브라이', '정 가시겠다면/이 할아범도/따라가겠습니다!'),
                       ('크리프트', '미력하나마 저도/공주님을 모시겠습니다!/자, 가시지요.')):
        out += ch1.speak(name, text)[:-1] + [ch1.PAGE]
    return out + ch1.narrate('브라이와 크리프트가/동료가 되었다!')


# 메시지 차례가 곧 번호 차례다(1장 사건 메시지 뒤 k 번째). NDS 2장 대사(MESS b0002)를 옮긴다
MESSAGES = {
    # NDS 2002·2003(FC 0305 첫 두 쪽). 서술은 해라체
    'opening': ch1.narrate('옛날 옛적 어느 곳에/아리나 공주라는/아주아주 말괄량이/공주님이 있었다고 한다.',
                           '그 나라 임금님은/공주의 말괄량이 짓에/머리를 싸매는/나날이었다.',
                           '어느 날 아침/임금님은 공주를/불러들였다……'),
    # NDS 2004(FC 0305 끝 쪽)
    'call': ch1.say('공주님! 아리나 공주님!/부왕께서 부르십니다!'),
    # NDS 2008~2011(FC 0306)
    'king': ch1.speak('왕', '오오, 아리나냐!?/할아범에게 들었다만/힘을 시험하는 여행을/떠나고 싶다고?',
                      '안 된다. 안 되고말고./너는 여자다./게다가 이 나라의/공주가 아니더냐.',
                      '마물들이 사는/바깥 세상으로/힘을 시험하러 나가다니/이 아비가 허락 못 한다!',
                      '알겠느냐!?/이 성에서 나가서는/안 된다./그럼 물러가도 좋다……'),
    # NDS 2052~2054(FC 0308)
    'wall_ask': ch1.narrate('아리나는 벽을/조사했다!', '판자로 수리해 놓았을/뿐이라 걷어차면/부서질 것 같다.',
                            '벽을 걷어차겠습니까?'),
    # FC 0390
    'wall_kick': ch1.narrate('아리나는 벽을/걷어찼다!'),
    # FC 030A
    'join': _join_pages(),
    # FC 07B1(NDS 2062)·07B2(2070): 성문 병사 둘
    'gate': ch1.say('임금님의 명령으로/이곳을 지나가시게/할 수는 없습니다.'),
    'gate2': ch1.say('부디 방으로/돌아가 주십시오.'),
    # FC 0322: 벽으로 나간 뒤 돌아오면 비켜서 있다
    'gate_back': ch1.say('어이쿠!/잘 돌아오셨습니다.'),
    # FC 07AA(NDS 2030~2032)
    'brey': _speaker_pages('브라이', '공주님! 조금은/여자다워지셔야지요.', '돌아가신 왕비님은/무척 기품 있는/분이셨는데.',
                           '공주님의 교육을/맡은 이 할아범은/임금님을 뵐 낯이/없사옵니다.'),
    # FC 060D(NDS 2080~2082)
    'kiryl': _speaker_pages('크리프트', '브라이 님께/들었습니다만,/공주님께서 혼자/여행을 떠나신다고요.',
                            '부디 그런 무모한/일은 하지/마십시오!',
                            '공주님께 만에 하나/무슨 일이 생기면/이 크리프트……/아니, 임금님께서!'),
    # FC 07A0 → 예 07A1 / 아니요 07A2(NDS 2016~2018)
    'king_ask': ch1.speak('왕', '어찌 그러느냐, 아리나?/아직도 밖에 나가고/싶다는 게냐?'),
    'king_yes': ch1.speak('왕', '안 된다, 안 돼!/어째서 너는 그리도/말괄량이란/말이냐……'),
    'king_no': ch1.speak('왕', '오오! 알아들었구나!/그래야 내 귀여운/딸이지./자, 방에서 쉬거라.'),
    # 텐페 촌장 FC 07C2 → 예 07C3 / 아니요 07C4(NDS 3534~3539), 들은 뒤 NDS 3541·3542
    'chief_ask': ch1.say('마을을 위해 딸 니나를/제물로 바쳐야만/합니다.',
                         '오오! 어디 괴물을/물리쳐 줄 만한/강한 분이/안 계실까?'),
    'chief_yes': ch1.say('아니, 당신들이!?', '보아하니 그리 강해/보이지는……/아니, 지금은 지푸라기라도/잡고 싶은 심정!',
                         '그게 정말이라면/꼭 신부님을/만나 주십시오!'),
    'chief_no': ch1.say('그렇겠지요……'),
    'chief_after': ch1.say('괴물 퇴치를/맡아 주시다니/참으로 마음씨 고운/분들이시군요!',
                           '자세한 것은 교회/신부님이 알고/계십니다.', '꼭 신부님을/만나 주십시오!'),
    # 텐페 신부 FC 07C5 → 예 07C6 / 아니요 07C7(NDS 3548~3554), 대신 가기로 한 뒤 FC 0347(NDS 4006)
    'priest_ask': ch1.say('뭐라, 괴물 퇴치를!?/하지만 괴물이/모습을 보이는 것은/제물을 바칠 때뿐……',
                          '아니면 그대가/제물의 대역이/되어도 좋다고/말하는 겐가?'),
    'priest_yes': ch1.say('오오, 그게 정말인가!?/참으로 고마운/일이로다!',
                          '그럼 잠시/기다리시게./제물의 바구니가/곧 올 걸세.'),
    'priest_no': ch1.say('그렇겠지./누구라도 제 목숨은/아까운 법.', '그건 그렇다 치고……'),
    'priest_basket': ch1.say('자, 어서 저/바구니 안으로……'),
    # 바구니 이벤트: NDS 4006·4012·4014, 끝 서술은 FC 1C 이벤트 01 의 자리 옮김을 말로
    'basket': (ch1.speak('신부', '자, 어서 저/바구니 안으로……')[:-1] + [ch1.PAGE] +
               ch1.speak('상인', '부디 몸조심하시게!')[:-1] + [ch1.PAGE] +
               ch1.speak('남자', '이 은혜는 평생/잊지 않겠습니다!')[:-1] + [ch1.PAGE] +
               ch1.narrate('아리나 일행을 태운/바구니는 마을 북쪽/제단으로 옮겨졌다.', '그리고 밤이 되었다……')),
}


def message_ids(first):
    return {name: first + k for k, name in enumerate(MESSAGES)}


def texts(first):
    return {first + k: parts for k, parts in enumerate(MESSAGES.values())}


TALKS = ('wall', 'gate', 'gate2', 'brey', 'kiryl', 'king', 'gate_back', 'chief', 'priest')


def talk_numbers(first_talk):
    """{이름: 대화 번호}. first_talk 는 1장 사건 대화 다음 번호."""
    return {name: first_talk + k for k, name in enumerate(TALKS)}


# FC 대화 번호: 2장 대화 스크립트로 바꾼 인물
FC_GATE, FC_GATE2, FC_BREY, FC_KIRYL, FC_KING = 0x021, 0x022, 0x01F, 0x023, 0x01A


def start_messages(first_message):
    """{(map, FC talk, night or None for both): first message} of the people this module gives chapter-2 talks
    (dq4npccheck --chapter1). The king's talk is the day one; at night he sleeps in the bedroom."""
    m = message_ids(first_message)
    return {(CASTLE, FC_GATE, None): m['gate'], (CASTLE, FC_GATE2, None): m['gate2'],
            (BREY_AT[0], FC_BREY, None): m['brey'], (KIRYL_AT[0], FC_KIRYL, None): m['kiryl'],
            (THRONE, FC_KING, False): m['king_ask'], (TEMPE, FC_CHIEF, None): m['chief_ask']}


def _flag_on(flag):
    return {"op": "flag-on", "index": flag[0], "mask": flag[1]}


def _if_flag(flag, then):
    return {"op": "if", "cond": {"code": "1B", "index": flag[0], "mask": flag[1]}, "then": then}


def _talked(flag):
    """이야기 깃발을 켜고, 셋 다 켜졌으면 READY 를 켠다."""
    ready = _flag_on(READY)
    for f in (TALKED_GATE, TALKED_BREY, TALKED_KIRYL):
        ready = _if_flag(f, ready if ready["op"] != "if" else [ready])
    return [_flag_on(flag), ready]


def talk_scripts(first_message):
    """dq5talk/1 의 scripts 에 TALKS 차례로 더할 본문. 벽: 예면 걷어참 깃발. 어느 쪽이든 대답 깃발을 켠다."""
    m = message_ids(first_message)
    msg = lambda k: {"op": "msg", "id": f"{m[k]:03X}"}  # noqa: E731
    return [
        [msg('wall_ask'), {"op": "if", "cond": {"code": "05"},
                           "then": [msg('wall_kick'), _flag_on(KICKED), _flag_on(ANSWERED)],
                           "else": _flag_on(ANSWERED)}],
        [msg('gate')] + _talked(TALKED_GATE),
        [msg('gate2')],
        [msg('brey')] + _talked(TALKED_BREY),
        [msg('kiryl')] + _talked(TALKED_KIRYL),
        [msg('king_ask'), {"op": "if", "cond": {"code": "05"}, "then": msg('king_yes'), "else": msg('king_no')}],
        [msg('gate_back')],
        [{"op": "if", "cond": _if_flag(TEMPE_HEARD, [])["cond"], "then": msg('chief_after'),
          "else": [msg('chief_ask'), {"op": "if", "cond": {"code": "05"},
                                      "then": [msg('chief_yes'), _flag_on(TEMPE_HEARD)], "else": msg('chief_no')}]}],
        # 「예」 하면 신부 자리의 스크립트가 바구니 이벤트를 건다. 촌장에게 듣기 전과 「아니요」 뒤는 DQ5 교회
        [{"op": "if", "cond": _if_flag(TEMPE_GONE, [])["cond"], "then": msg('priest_basket'),
          "else": [{"op": "if", "cond": _if_flag(TEMPE_HEARD, [])["cond"],
                    "then": [msg('priest_ask'), {"op": "if", "cond": {"code": "05"},
                                                 "then": [msg('priest_yes'), _flag_on(TEMPE_GONE)],
                                                 "else": [msg('priest_no'), CHURCH]}],
                    "else": CHURCH}]}],
    ]


# DQ5 교회 처리기(특수 대화 05, 06:DBDB 표). 대화 스크립트의 00 명령으로 부른다
CHURCH = {"op": "call", "target": "E03E"}


def _cmd(op, *args):
    return {"op": op, "args": list(args)}


def scripts(first_message, native_points):
    """인물 스크립트. native_points: dq4chapterbox.entry_points 의 {이름: 주소}(box2·reveal)."""
    m = message_ids(first_message)
    _, at = native()
    lo, hi = lambda v: v & 0xFF, lambda v: v >> 8
    msg = lambda k: _cmd('21', lo(m[k]), hi(m[k]))  # noqa: E731
    call = lambda k: _cmd('37', *_al(at[k]))  # noqa: E731
    return [
        {"address": KING_SCRIPT, "commands": [
            _cmd('3F'), _cmd('37', *_al(native_points['box2'])), msg('opening'),
            _cmd('37', *_al(native_points['reveal'])), msg('call'), msg('king'),
            _cmd('11', OPENING[0], ~OPENING[1] & 0xFF), _cmd('40'), _cmd('16')]},
        # 벽 앞에서 오른쪽을 보면 묻는다. 아니요면 그 자리를 떠났다가 다시 오면 또 묻는다
        {"address": ASKER_SCRIPT, "commands": [
            _cmd('28'), _cmd('52'), _cmd('09', 0x80 | CHAPTER2[0], CHAPTER2[1]),
            {**_cmd('05', *_al(at['at_wall'])), "label": "wait"}, call('talk_here'),
            _cmd('09', 0x80 | ANSWERED[0], ANSWERED[1]), _cmd('11', ANSWERED[0], ~ANSWERED[1] & 0xFF),
            {**_cmd('06', KICKED[0], KICKED[1]), "target": "kick"},
            _cmd('05', *_al(at['away_wall'])), {"op": "03", "args": [], "target": "wait"},
            {**_cmd('3F'), "label": "kick"}, call('open_wall'), call('kick'), _cmd('16')]},
        # 걷어찬 뒤 다시 들어오면 구멍을 연다
        {"address": OPENER_SCRIPT, "commands": [_cmd('28'), _cmd('52'), call('open_wall'), _cmd('16')]},
        # 텐페 신부: 대신 가겠다고 하면 제단 깃발을 켜고 바구니 이벤트를 건다. 옮긴 뒤의 목록에는 이 스크립트가 없다
        {"address": PRIEST_SCRIPT, "commands": [
            _cmd('09', 0x80 | TEMPE_GONE[0], TEMPE_GONE[1]), _cmd('10', *TEMPE_ALTAR),
            _cmd('37', *_al(tail_native(first_message)[1]['altar_go'])), _cmd('16')]},
    ]


def _invisible(src, talk):
    """스크립트만 돌리는 보이지 않는 인물(낮·밤 하나씩). 빌린 원본의 이동 간격이 0 이면 스크립트가 돌지 않아(실측) 1 을 준다."""
    e = {"from": src, "fields": {"x": 0, "y": 1, "facing": "down", "talk": talk, "gfx": 0x01, "layer": 0,
                                 "interval": 1}}
    return [{**e, "time": "day"}, {**e, "time": "night"}]


def npc_lists(ported, first_talk):
    """(ported, new_lists, overrides). 첫머리를 기다리는 동안의 3D/01 은 옮긴 목록에서 왕만 연출 인물로 바꾸고,
    왕의 방에는 벽을 묻는 보이지 않는 인물을 더하며, 벽을 걷어찬 뒤의 왕의 방은 구멍을 여는 인물이 있는 목록이다."""
    t = talk_numbers(first_talk)
    lists = {lst["map"]: lst for lst in ported if "map" in lst}

    def retalk(mp, cell, talk, time=None):
        hit = 0
        for e in lists[mp]["entries"]:
            if (e["fields"]["x"], e["fields"]["y"]) == cell and time in (None, e["time"]):
                e["fields"] = {**e["fields"], "talk": talk}
                hit += 1
        if not hit:
            raise SystemExit(f'{mp} {cell}: 2장 대화를 줄 인물이 없음')
    retalk(CASTLE, GATE[0], t['gate'])
    retalk(CASTLE, GATE[1], t['gate2'])
    # FC 문지기는 문간 두 칸을 막고 선다. 옮긴 인물은 걸어 다녀 틈이 생겼다(실측)
    for e in lists[CASTLE]["entries"]:
        if (e["fields"]["x"], e["fields"]["y"]) in GATE:
            e["fields"] = {**e["fields"], "interval": 0}
    retalk(*BREY_AT, t['brey'])
    retalk(*KIRYL_AT, t['kiryl'])
    retalk(THRONE, KING_CELL, t['king'], 'day')
    retalk(TEMPE, CHIEF, t['chief'])
    retalk(TEMPE, PRIEST, t['priest'])
    # 제단으로 옮긴 뒤의 신부는 스크립트 없이 대화만. 그 앞의 신부는 대신 감 flag 를 기다려 바구니 이벤트를 거는
    # 스크립트를 빌린다
    altar = list(lists[TEMPE]["entries"])
    # 빌린 원본의 이동 간격이 0 이면 스크립트가 돌지 않아(실측) 1 이상으로 둔다
    lists[TEMPE]["entries"] = [
        {**e, "from": PRIEST_SRC, "fields": {**e["fields"], "interval": max(1, e["fields"].get("interval", 1))}}
        if (e["fields"]["x"], e["fields"]["y"]) == PRIEST else e for e in altar]
    opening = []
    for e in lists[THRONE]["entries"]:
        f = e["fields"]
        if (f["x"], f["y"]) == KING_CELL and e["time"] == "day":
            e = {**e, "from": KING_SRC, "fields": {**f, "interval": max(1, f.get("interval", 1))}}
        opening.append(e)

    def stand_aside(e):
        """합류 뒤 문지기는 FC 한 칸 바깥으로 비켜서 돌아온 공주를 맞는다."""
        cell = (e["fields"]["x"], e["fields"]["y"])
        if cell not in GATE:
            return e
        dx = -2 if cell == GATE[0] else 2
        return {**e, "fields": {**e["fields"], "x": cell[0] + dx, "talk": t['gate_back']}}

    def without(mp, cell):
        return [e for e in lists[mp]["entries"] if (e["fields"]["x"], e["fields"]["y"]) != cell]
    room = list(lists[BEDROOM]["entries"])
    # 낮의 벽 앞에는 수리공이 서 있다(FC). 옮긴 수리공은 주인공과 한 셀 어긋나 칸을 막지 못해(실측), 셋과 이야기하기
    # 전에는 묻는 인물을 밤에만 둔다
    lists[BEDROOM]["entries"] = room + _invisible(ASKER_SRC, t['wall'])[1:]
    clear = [e for e in room if (e["fields"]["x"], e["fields"]["y"]) != CARPENTER]
    on = lambda mp, flag, name: {"map": mp, "flag": flag[0], "when": "on", "mask": flag[1], "list": f"new:{name}"}  # noqa: E731
    over = [on(THRONE, OPENING, 'ch2_opening'), on(THRONE, JOINED, 'ch2_throne_joined'),
            on(CASTLE, JOINED, 'ch2_castle_joined'),
            on(BEDROOM, KICKED, 'ch2_kicked'), on(BEDROOM, READY, 'ch2_ready'),
            on(TEMPE, TEMPE_ALTAR, 'ch2_tempe_altar')]
    new = [{"name": "ch2_opening", "entries": opening},
           {"name": "ch2_throne_joined", "entries": without(*BREY_AT)},
           {"name": "ch2_castle_joined", "entries": [stand_aside(e) for e in without(*KIRYL_AT)]},
           {"name": "ch2_kicked", "entries": clear + _invisible(OPENER_SRC, t['wall'])},
           {"name": "ch2_ready", "entries": clear + _invisible(ASKER_SRC, t['wall'])},
           {"name": "ch2_tempe_altar", "entries": altar}]
    return ported, new, over


def apply(data, original, first_message):
    """original: 원래 롬(기록 틀 23:C014 를 읽음). first_message: 2장 메시지 첫 번호(합류 이벤트에 들어감)."""
    d = bytearray(data)
    code, _ = native(original)
    more, tail = tail_native(first_message, original)
    code += more
    o = ch1.lorom(CODE_AT)
    if any(d[o:o + len(code)]):
        raise SystemExit(f'{CODE_AT:06X}: 비어 있지 않은 자리')
    if (CODE_AT & 0xFFFF) + len(code) > 0x10000:
        raise SystemExit('2장 네이티브가 뱅크를 넘음')
    d[o:o + len(code)] = code
    _, at = native()
    for addr, orig, new in ((HERO_PICTURE_AT, HERO_PICTURE_ORIG, bytes((0x22, *_al(at['hero_picture']), 0x60))),
                            (STEP_HOOK_AT, STEP_HOOK_ORIG, bytes((0x22, *_al(tail['step']))))):
        o = ch1.lorom(addr)
        if bytes(d[o:o + len(orig)]) != orig:
            raise SystemExit(f'{addr:06X}: 원래 바이트가 아님 {d[o:o + len(orig)].hex()}')
        d[o:o + len(new)] = new
    return bytes(d)
