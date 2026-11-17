"""맡기는 곳의 돌려받기 수수료(FC 15:$BBF0): 물건을 맡길 때 안내하고, 돌려받을 때 10골드를 받는다.

FC(코드 읽기, fc/dq4/docs/dq4-shop-format.md 「맡기는 곳」):
  맡기기    물건을 고르면 0240 「…ですね。おかえしするとき てすうりょうを 10ゴールド いただきます。かまいませんか？」
            예/아니요. 아니요면 0257 「おやめに なるのですね。」(15:$BCEC)
  돌려받기  물건을 고르면 024B 「…ですね。てすうりょうを 10ゴールド いただきます。よろしいですね。」 예/아니요(15:$BDF2).
            예인데 금화가 10 보다 적으면 024C 「おや？ おかねが たりませんね？ すみませんが しなものは おかえし できません。」,
            맡긴 돈이 있으면 024D 「おあずかりしている おかねを さきに おかえししましょうか？」 예/아니요 → 돈 돌려받기(15:$BE0C).
            돌려준 뒤 금화에서 10 을 뺀다(15:$BECC)

DQ5 맡기는 곳(대화 번호 04, 06:E4DE)에 훅 셋을 건다. 코드는 BRK(창·메시지)를 쓰므로 뱅크 40 아래의 빈 자리에 둔다
(BRK 처리기가 BRK 가 놓인 뱅크를 DB 로 두어, 그 뱅크에서 낮은 WRAM 이 보여야 함):
  06:E61C  BRK 95 00 / LDA $0F21 → JSL deposit:  맡길 물건($0F22)으로 NOTICE 와 예/아니요. 아니요면 06:E548(0E3 「그만두시는
           건가요?」). 예면 원래 명령
  06:E807  LDA $46 / STA $F5 / STA $0F22 → JSL withdraw:  돌려받을 물건으로 NOTICE 와 예/아니요(아니요면 06:E548). 금화가
           FEE 보다 적으면 SHORT 뒤, 맡긴 돈이 있으면 돈 돌려받기(06:E6C2), 없으면 06:E520(0E4 「그 밖에 다른 용무는」)
  06:E8A7  LDA $0F21 / STA $42 → JSL pay:  누가 가질지까지 정한 뒤 물건을 넘기기 직전 금화에서 FEE 를 뺀다

FC 의 024D 예/아니요는 DQ5 에 빈 메시지 자리가 둘(0AA·0C2)뿐이라 옮기지 않고, 맡긴 돈이 있으면 바로 돈 돌려받기의 얼마를
물음(0CD)으로 간다(취소하면 0E3). 0240 과 024B 는 한 메시지(NOTICE)로 같이 쓴다.
"""

import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from dq4environmentrom import _Asm  # noqa: E402

# 원래 롬 빈 자리 16:FE10~16:FFFF 가운데 앞(dq5build free, 이 해킹의 다른 도구가 쓰지 않음)
CODE_AT, CODE_END = 0x16FE10, 0x16FF00
FEE = 10
NOTICE, SHORT = 0x0AA, 0x0C2          # DQ5 원래 빈 메시지(dq4sysmsg.SPEECH 에 글)
GOLD = 0x7E2019                       # 금화 3바이트
CHOSEN, ITEM, NAME = 0x0F21, 0x0F22, 0xF5
YES_NO, CLOSE = 0x32, 0x00            # BRK 95 창: 예/아니요(06:E3C9 과 같음), 닫기
DEPOSIT_SITE, DEPOSIT_ORIG = 0x06E61C, bytes((0x00, 0x95, 0x00, 0xAD, 0x21, 0x0F))
WITHDRAW_SITE, WITHDRAW_ORIG = 0x06E807, bytes((0xA5, 0x46, 0x85, 0xF5, 0x8D, 0x22, 0x0F))
PAY_SITE, PAY_ORIG = 0x06E8A7, bytes((0xAD, 0x21, 0x0F, 0x85, 0x42))
CANCEL, OTHER, MONEY_BACK = 0x06E548, 0x06E520, 0x06E6C2
MONEY_OF = 0x97                       # BRK 88 97: 맡긴 돈($46·$47, 1000골드 단위)


def _long(v):
    return v.to_bytes(3, 'little')


def code(at=CODE_AT):
    """(바이트, 라벨). 세 진입점 모두 M 8비트·X 16비트, DB 06. 들어오면 DB 를 이 뱅크로 두고(BRK 처리기가 놓인 뱅크를 DB
    로 쓰므로 맞춰 둠) 나갈 때 되돌린다."""
    a = _Asm(at)

    def enter():
        a.b(0x8B, 0x4B, 0xAB)                                                # PHB / PHK / PLB

    def ask():
        """$F5 의 물건 이름으로 NOTICE 를 띄우고 예/아니요. 아니요(취소 포함)면 cancel 로."""
        a.b(0x00, 0x97, NOTICE, 0x00, 0x95, YES_NO, 0xA5, 0xE8).rel(0xD0, 'cancel')
    # 06:E61C 에서
    a.label('deposit')
    enter()
    a.b(0x00, 0x95, CLOSE, 0xAD, *ITEM.to_bytes(2, 'little'), 0x85, NAME)   # 원래 BRK 95 00 / $F5 = 맡길 물건
    ask()
    a.b(0x00, 0x95, CLOSE, 0xAB, 0xAD, *CHOSEN.to_bytes(2, 'little'), 0x6B)  # BRK 95 00 / PLB / 원래 LDA $0F21 / RTL
    # 06:E807 에서
    a.label('withdraw')
    enter()
    a.b(0xA5, 0x46, 0x85, NAME, 0x8D, *ITEM.to_bytes(2, 'little'))          # 원래 세 명령
    ask()
    a.b(0x00, 0x95, CLOSE)
    a.b(0xAF, *_long(GOLD + 1), 0x0F, *_long(GOLD + 2)).rel(0xD0, 'enough')  # 위 두 바이트가 0 이 아니면 넉넉
    a.b(0xAF, *_long(GOLD), 0xC9, FEE).rel(0xB0, 'enough')                   # LDA 금화 / CMP #10 / BCS
    a.b(0x00, 0x97, SHORT, 0x00, 0x88, MONEY_OF)                             # BRK 97 SHORT / 맡긴 돈
    a.b(0xAB, 0x68, 0x68, 0x68, 0xA5, 0x46, 0x05, 0x47).rel(0xF0, 'other')   # PLB / 돌아갈 곳 버림 / 맡긴 돈이 없으면
    a.b(0x5C, *_long(MONEY_BACK))                                            # JML 돈 돌려받기
    a.label('other').b(0x5C, *_long(OTHER))
    a.label('enough').b(0xAB, 0xAD, *ITEM.to_bytes(2, 'little'), 0x6B)       # PLB / A = 물건(원래 명령 뒤와 같음) / RTL
    a.label('cancel').b(0xAB, 0x68, 0x68, 0x68, 0x5C, *_long(CANCEL))        # PLB / 돌아갈 곳 버림 / JML 0E3
    # 06:E8A7 에서: 금화 -= FEE(24비트)
    a.label('pay').b(0xC2, 0x20, 0xAF, *_long(GOLD), 0x38, 0xE9, FEE, 0x00, 0x8F, *_long(GOLD))
    a.b(0xE2, 0x20, 0xAF, *_long(GOLD + 2), 0xE9, 0x00, 0x8F, *_long(GOLD + 2))
    a.b(0xAF, *_long(0x7E0000 | CHOSEN), 0x85, 0x42, 0x6B)                  # 원래 LDA $0F21 / STA $42 / RTL
    return a.assemble()


def writes(at=CODE_AT):
    """dq5patch/1 쓰기: 코드와 JSL 셋."""
    data, labels = code(at)
    if at + len(data) > CODE_END:
        raise ValueError(f'맡기는 곳 수수료 코드 {len(data)}바이트가 {at:06X}~{CODE_END - 1:06X} 를 넘음')

    def jsl(site, label, orig, note):
        new = bytes((0x22, *_long(labels[label]))) + b'\xEA' * (len(orig) - 4)
        return {'at': _cpu(site), 'hex': new.hex(' ').upper(), 'orig': orig.hex(' ').upper(), 'note': note}
    return [{'at': _cpu(at), 'hex': data.hex(' ').upper(), 'note': '맡기는 곳 돌려받기 수수료(FC 10골드)'},
            jsl(DEPOSIT_SITE, 'deposit', DEPOSIT_ORIG, '맡길 물건을 고르면 수수료 안내와 예/아니요'),
            jsl(WITHDRAW_SITE, 'withdraw', WITHDRAW_ORIG, '돌려받을 물건을 고르면 수수료 확인, 금화가 모자라면 돌려주지 않음'),
            jsl(PAY_SITE, 'pay', PAY_ORIG, '물건을 넘기기 직전 금화에서 수수료를 뺌')]


def _cpu(addr):
    return f'{addr >> 16:02X}:{addr & 0xFFFF:04X}'
