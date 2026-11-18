"""독늪에서 쓰러짐(FC 처럼). 형식은 sfc/dq4/docs/dq4-field-format.md 「독늪에서 쓰러짐」.

FC 독늪(1E:$99E1)은 HP 를 0 까지 깎는다. 한 사람이 쓰러지면 「…は しんでしまった！」 뒤 관이 따라오고 금화는 그대로,
걷는 일행이 모두 쓰러지면 전투 전멸과 같은 길(금화 반, 저장 교회)이다. DQ5 독늪 피해(06:8087~)는 HP 1 이면 깎지 않는다
(06:80A3 CMP #1 / BEQ RTL). 그 뒤 HP 를 깎는 06:80B6(BRK 89 88 02)은 동료는 0 으로 깎아 「{1008}は 死んでしまった！」(586)을
띄우지만 주인공(레코드 0)은 깎지 않았고, 걷는 일행이 모두 살아 있음 bit 가 꺼지면 DQ5 걸음 처리가 「…は 全滅した！」(585)
뒤 01:88ED(전멸 처리)를 부르나 금화는 줄이지 않았다(실측).

  06:80A1  LDA $46 / CMP #1 / BEQ → JML check:  HP($46)가 1 이고 피해($43)가 1(독늪)일 때만 갈래, 그 밖은 원래대로.
    동료(레코드 $42 ≥ 1)  06:80B6 으로 깎게 둔다(DQ5 가 586·쓰러짐, 모두면 585·전멸). 그 앞에서 살아 있는 일행 기록
                         (7E:2040 + n × 42 의 +1 bit7, n < 7E:201D)이 이 사람 하나뿐이면 halve, 아니면 그림 다시 세우기
                         스크립트(redraw: 05:D89D, 쓰러진 칸이 관 그림)를 건다
    주인공(레코드 0)     HP 를 0 으로 두고 칸 X 를 WHO 에 둔 뒤 메시지 스크립트를 건다($19B3~$19B5·$19AE bit7, 3장 떠돌이
                         상인과 같은 길). 이미 걸려 있으면 메시지 없이 바로 쓰러짐으로 표시
  스크립트  prep($F5 = WHO) / 메시지 586 / after: WHO 의 레코드 +1 bit7 을 끄고 그림을 다시 세운다. 살아 있는 기록이 없으면
           halve 하고 스크립트 표시를 끈 뒤 JSL 01:88ED(표시를 끄지 않으면 교회에서 이 스크립트가 다시 돌았다, 실측)
  halve    금화를 반으로 내림(FC 12:$ADC2: 남는 쪽을 내림, 1001 → 500). 3장에 일행 기록 0~3 의 소지품에 철 금고가 있으면
           그대로(dq4ch3safe 의 전투 전멸 훅과 같은 판정)
"""
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from dq4environmentrom import _Asm  # noqa: E402

# 독늪 훅 묶음(dq4fieldencounter.ch3_code, 4E:8000~)의 몫 끝 뒤. dq4fieldencounter.CH3_CODE_END 가 이 앞에서 끝난다
CODE_AT, CODE_END = 0x4EBC00, 0x4EC000
SITE, ORIG = 0x0680A1, bytes((0xA5, 0x46, 0xC9, 0x01, 0xF0, 0x15))   # LDA $46 / CMP #1 / BEQ $80BC
AFTER_ONE, NO_DAMAGE, SUBTRACT = 0x0680A7, 0x0680BC, 0x0680B6         # 80A7 CMP #8 …, 80BC RTL, 80B6 HP 에서 $43 을 뺌
RECORD_OF = 0x02C654                                  # X = 칸 → X = 레코드 번호(06:808F 가 부름)
PARTY_OBJECTS = 0x05D89D                              # 걷는 일행 그림을 일행 기록대로 다시 세움(dq4ch1event.REFRESH)
WIPE = 0x0188ED
RECORDS, RECORD_SIZE, ALIVE = 0x7E2041, 42, 0x80      # 레코드 +1 bit7 = 살아 있음, +2·+3 = HP
PARTY_ITEMS, PARTY_COUNT = 0x7E2040 + 0x16, 0x7E201D
EVENT_SCRIPT, EVENT_FLAG = 0x7E19B3, 0x7E19AE
WHO = 0x7E1ABD                                         # dq4lowwram 'dq4swampdeath'
GOLD = 0x7E2019
CHAPTER3 = (0x7E2208, 0x08)                            # dq4ch3event.CHAPTER3
NAME = 0xF5
# DQ5 필드 쓰러짐·전멸 메시지. dq4sysmsg.SOURCE 가 한글로 덮는다
DIED, WIPED = 0x586, 0x585
MAX_RECORDS = 8


def _long(v):
    return v & 0xFF, v >> 8 & 0xFF, v >> 16


def _record_x(a):
    """M·X 16비트로 A(레코드 번호, 아래 바이트) → X = 번호 × 42(= ×2 + ×8 + ×32)."""
    a.b(0x29, 0xFF, 0x00, 0x0A, 0x48, 0x0A, 0x0A, 0x48, 0x0A, 0x0A, 0x18, 0x63, 0x01, 0x63, 0x03, 0xAA, 0x68, 0x68)


def code(at=CODE_AT):
    """(바이트, 라벨)."""
    from dq4itemport import IRON_SAFE
    a = _Asm(at)
    # 06:80A1 에서 JML(M·X 8비트, DP 0). A 는 원래처럼 $46 을 들고 06:80A7(CMP #8)로 돌아간다
    a.label('check').b(0xA5, 0x46, 0xC9, 0x01).rel(0xF0, 'one').b(0x5C, *_long(AFTER_ONE))
    a.label('one').b(0xA5, 0x43, 0xC9, 0x01).rel(0xF0, 'die').b(0x5C, *_long(NO_DAMAGE))
    # 동료(레코드 1 이상)는 06:80B6 이 0 으로 깎아 스스로 586·쓰러짐(모두면 585·전멸)을 한다. 마지막 생존자면 그 앞에서 금화를
    # 반으로 하고, 아니면 그림 다시 세우기 스크립트만 건다. 주인공(레코드 0)은 80B6 이 깎지 않아 hero 로
    a.label('die').b(0xA5, 0x42).rel(0xD0, 'mate').b(0x4C).word(None, 'hero')        # BNE mate / JMP hero
    # 살아 있는 일행 기록 수를 Y 로(레코드 n 의 +1 = RECORDS + 42n). X·Y 는 지킨다(80B6 뒤는 Y 를 레코드 번호로 씀)
    a.label('mate').b(0xDA, 0x5A, 0xA0, 0x00)
    for n in range(MAX_RECORDS):
        a.b(0xAF, *_long(PARTY_COUNT), 0xC9, n + 1).rel(0x90, 'counted')
        a.b(0xAF, *_long(RECORDS + RECORD_SIZE * n)).rel(0x10, f'alive{n}').b(0xC8).label(f'alive{n}')
    a.label('counted').b(0xC0, 0x02, 0x7A, 0xFA).rel(0xB0, 'others')                  # CPY #2 / PLY / PLX
    a.b(0x20).word(None, 'halve')
    # 원래 06:80AB(LDA $43) → 80B6 처럼 A = 피해로 넘긴다
    a.label('subtract').b(0xA5, 0x43, 0x5C, *_long(SUBTRACT))
    a.label('others').b(0xAF, *_long(EVENT_FLAG)).rel(0x30, 'subtract')
    a.b(0xC2, 0x20).word(0xA9, 'redraw').b(0x20).word(None, 'arm').rel(0x80, 'subtract')
    # 주인공: HP 를 0 으로 두고(X·Y·P 는 지킴) 메시지 스크립트를 건다. 이미 걸려 있으면(한 걸음에 둘째) 바로 표시
    a.label('hero').b(0xDA, 0x5A, 0x08, 0xC2, 0x30, 0xA5, 0x42)
    _record_x(a)
    a.b(0xA9, 0x00, 0x00, 0x9F, *_long(RECORDS + 1), 0x28, 0x7A, 0xFA)
    a.b(0xAF, *_long(EVENT_FLAG)).rel(0x30, 'second')
    a.b(0x8A, 0x8F, *_long(WHO), 0xC2, 0x20).word(0xA9, 'script').b(0x20).word(None, 'arm')
    a.b(0x5C, *_long(NO_DAMAGE))
    a.label('second').b(0x20).word(None, 'kill').b(0x5C, *_long(NO_DAMAGE))
    # arm(JSR, M 16비트, A = 스크립트 주소 아래 16비트): $19B3~$19B5 에 두고 $19AE bit7. M 8비트로 돌아감
    a.label('arm').b(0x8F, *_long(EVENT_SCRIPT), 0xE2, 0x20, 0xA9, at >> 16, 0x8F, *_long(EVENT_SCRIPT + 2))
    a.b(0xAF, *_long(EVENT_FLAG), 0x09, 0x80, 0x8F, *_long(EVENT_FLAG), 0x60)
    # kill(JSR, M·X 8비트, X = 칸): 02:C654 가 칸 X 의 레코드 번호를 X 로. 그 레코드 +1 bit7 을 끈다. A·X·Y 를 지킨다
    a.label('kill').b(0x48, 0xDA, 0x5A, 0x08, 0x22, *_long(RECORD_OF), 0xC2, 0x30, 0x8A)
    _record_x(a)
    a.b(0xE2, 0x20, 0xBF, *_long(RECORDS), 0x29, 0xFF ^ ALIVE, 0x9F, *_long(RECORDS), 0x28, 0x7A, 0xFA, 0x68, 0x60)
    # 이벤트 스크립트: 네이티브(A0 긴 주소, 00:C046 이 M·X 8비트로 부름) / 메시지(60 번호) / 네이티브 / 끝
    a.label('script').long(0xA0, 'prep').b(0x60, DIED & 0xFF, DIED >> 8).long(0xA0, 'after').b(0xFF)
    a.label('prep').b(0xAF, *_long(WHO), 0x85, NAME, 0x6B)
    a.label('after').b(0xE2, 0x30, 0xAF, *_long(WHO), 0xAA, 0x20).word(None, 'kill')
    a.b(0xE2, 0x30, 0x22, *_long(PARTY_OBJECTS), 0xE2, 0x30)
    # 살아 있는 일행 기록이 하나라도 있으면 끝
    for n in range(MAX_RECORDS):
        a.b(0xAF, *_long(PARTY_COUNT), 0xC9, n + 1).rel(0x90, 'all')
        a.b(0xAF, *_long(RECORDS + RECORD_SIZE * n)).rel(0x10, f'dead{n}').b(0x6B).label(f'dead{n}')
    a.label('all').b(0x20).word(None, 'halve')
    a.b(0xAF, *_long(EVENT_FLAG), 0x29, 0x7F, 0x8F, *_long(EVENT_FLAG), 0x22, *_long(WIPE), 0x6B)
    # 그림만 다시 세우는 스크립트(동료가 쓰러졌을 때)
    a.label('redraw').long(0xA0, 'refresh').b(0xFF)
    a.label('refresh').b(0xE2, 0x30, 0x22, *_long(PARTY_OBJECTS), 0x6B)
    # halve(JSR, M·X 8비트): 3장에 일행 기록 0~3(일행 수까지)의 소지품 12칸에 철 금고가 있으면 그대로, 아니면 금화를 반으로
    # 내림(FC 는 남는 금화를 반으로 내림, 1001 → 500). X 를 지킨다
    flag, bit = CHAPTER3
    a.label('halve').b(0xDA, 0xAF, *_long(flag), 0x29, bit).rel(0xF0, 'half')
    for r in range(4):
        a.b(0xAF, *_long(PARTY_COUNT), 0xC9, r + 1).rel(0x90, 'half').b(0xA2, 0x00)
        a.label(f'slot{r}').b(0xBF, *_long(PARTY_ITEMS + RECORD_SIZE * r), 0xC9, IRON_SAFE).rel(0xF0, 'kept')
        a.b(0xE8, 0xE0, 12).rel(0x90, f'slot{r}')
    a.label('half').b(0xAF, *_long(GOLD + 2), 0x4A, 0x8F, *_long(GOLD + 2), 0xAF, *_long(GOLD + 1), 0x6A)
    a.b(0x8F, *_long(GOLD + 1), 0xAF, *_long(GOLD), 0x6A, 0x8F, *_long(GOLD))
    a.label('kept').b(0xFA, 0x60)
    data, labels = a.assemble()
    if at + len(data) > CODE_END:
        raise ValueError(f'독늪 쓰러짐 코드 {len(data)}바이트가 {at:06X}~{CODE_END - 1:06X} 를 넘음')
    return data, labels


def writes():
    """[(자리, 바이트, 원래 바이트 또는 None(빈 자리))]."""
    data, labels = code()
    return [(SITE, bytes((0x5C, *_long(labels['check']), 0xEA, 0xEA)), ORIG), (CODE_AT, data, None)]


def apply(rom):
    from dq5map import lorom
    d = bytearray(rom)
    for addr, payload, orig in writes():
        o = lorom(addr)
        if orig is not None and bytes(d[o:o + len(orig)]) != orig:
            raise SystemExit(f'{addr:06X}: 원래 바이트가 아님 {d[o:o + len(orig)].hex(" ")}')
        if orig is None and any(d[o:o + len(payload)]):
            raise SystemExit(f'{addr:06X}: 비어 있지 않은 자리')
        d[o:o + len(payload)] = payload
    return bytes(d)
