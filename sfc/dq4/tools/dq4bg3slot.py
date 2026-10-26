"""게임 안 BG3 타일맵을 VRAM 워드 1C00 에서 장면마다 빈 자리로 옮겨, BG3 글자 칸 180~1FF(128칸)를 비운다.
형식은 sfc/dq4/docs/dq4-window-text-format.md 「BG3 타일맵 옮기기」.

DQ5 엔진은 BG3SC 를 맵을 불러올 때만(2B:82BD → 2B:82C2 STA $2109) 그림자 $0725 와 함께 쓴다. DQ5 트랙의
실내 364맵 VRAM 칸 쓰기 실측과 전투 실측에 따라
  필드($BE bit7 = 0)          78
  3C00 을 쓰는 실내 맵 9개   48(전투를 시작하면 78)
  나머지 실내 맵              3C(전투도 3C00 을 쓰지 않아 그대로)
으로 BG3SC 를 고르고, 타일맵 VRAM 주소를 즉값 1C00~1FFF 로 쓰는 곳에서 그 값을 지금 자리 기준으로 다시 계산한다.
전투가 끝나면 맵을 다시 불러와 위 규칙으로 돌아간다. 21BF.5 갈래의 4C00 은 원래대로 둔다. 타이틀·메뉴는 맵을
불러오기 전이라 1C 그대로다.
"""
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[1] / 'dq5' / 'tools')]

from dq5map import lorom  # noqa: E402

CODE = 0x608300
MAP_CHOOSE = 0x608284                 # dq4menupatch 의 맵 훅 안 LDA #$1C / STA $0725 / RTL
BATTLE_START = 0x268030               # JSL $04E2A1(전투 글자 타일 올리기)
INTERIOR, SHARED, FIELD = 0x3C, 0x48, 0x78
# 3C00~3FFF 를 맵을 불러오며 쓰는 실내 맵(DQ5 트랙의 실내 364맵 VRAM 칸 쓰기 실측). 이 맵들만 48 로 둔다.
# 전투는 3C00 을 한 번도 쓰지 않아(09/00 전투 실측) 3C 맵에서는 전투 중에도 자리를 바꾸지 않는다.
USES_3C00 = ((0x00, 0x0A), (0x19, 0x00), (0x1A, 0x00), (0x1C, 0x00), (0x1F, 0x00), (0x20, 0x00), (0x21, 0x00),
             (0x21, 0x05), (0x32, 0x00))
SHADOW = 0x7E0725                     # 바라는 BG3SC(게임의 그림자)
SHOWN = 0x7E1ABC                      # 지금 $2109 에 든 BG3SC ^ 1C(0 이면 1C). 7E:1ABC~1ABF 는 메뉴 공용 창(1AC0~) 앞 빈자리
BUFFER = 0x7E5000                     # BG3 타일맵 버퍼(00:8E1F 가 통째로 보내는 곳)
# (자리, 원래 바이트). 16비트 A 의 VRAM 주소를 $2116 에 쓰는 곳.
FULL_SITE = 0x008E1F                  # LDA #$0400 / ASL 로 7E:5000 의 2KB 전체를 보냄(나머지 둘은 위·아래 줄만)
VMADD_SITES = ((0x008E1F, '8f162100'), (0x008E55, '8f162100'), (0x008E75, '8f162100'))
# 8비트 A(높은 바이트)를 $2117 에 쓰고 이어서 LDA #$80. 9849 는 BEQ 의 도착지라 그 자리부터 5바이트를 쓴다.
VMADD_HI_SITE = (0x049849, '8d1721a980')
# LDA #$1CE0 / STA $0F5E(전투 창 줄 주소, 00:FDA1 이 $2116 에 씀).
LINE_SITES = ((0x228B4D, 'a9e01c8d5e0f'), (0x228B6F, 'a9e01c8d5e0f'), (0x228BC6, 'a9e01c8d5e0f'))


def long(a):
    return bytes((a & 0xFF, a >> 8 & 0xFF, a >> 16))


def rebase16():
    """16비트 A 의 VRAM 워드 주소가 1C00~1FFF 면 ($0725 & FC) << 8 기준으로 바꿔 돌려준다. A 말고는 그대로."""
    swap = bytes((
        0xAF, *long(SHOWN),                    # LDA $7E1ABC
        0x49, 0x1C, 0x00,                      # EOR #$001C     지금 BG3SC
        0x29, 0xFC, 0x00,                      # AND #$00FC
        0xEB,                                  # XBA            기준 워드
        0x48,                                  # PHA            [원래][기준]
        0xA3, 0x03,                            # LDA 3,S
        0x29, 0xFF, 0x03,                      # AND #$03FF
        0x03, 0x01,                            # ORA 1,S
        0x83, 0x03,                            # STA 3,S
        0x68))                                 # PLA
    return bytes((
        0x48,                                  # PHA            [원래]
        0x29, 0x00, 0xFC,                      # AND #$FC00
        0xC9, 0x00, 0x1C,                      # CMP #$1C00
        0xD0, len(swap))) + swap + bytes((     # BNE 그대로
        0x68,                                  # PLA
        0x6B))                                 # RTL


def rebase8():
    """8비트 A(높은 바이트)가 1C~1F 면 ($0725 & FC) | (A & 03) 으로."""
    swap = bytes((
        0xAF, *long(SHOWN), 0x49, 0x1C, 0x29, 0xFC,   # LDA $7E1ABC / EOR #$1C / AND #$FC
        0x48,                                  # PHA
        0xA3, 0x02, 0x29, 0x03, 0x03, 0x01,    # LDA 2,S / AND #$03 / ORA 1,S
        0x83, 0x02, 0x68))                     # STA 2,S / PLA
    return bytes((0x48, 0x29, 0xFC, 0xC9, 0x1C, 0xD0, len(swap))) + swap + bytes((0x68, 0x6B))   # … / PLA / RTL


def clear_code():
    """8비트 A = 새 BG3SC. 이전 값과 다르면 타일맵 버퍼 7E:5000 2KB 를 DMA 7 로 새 자리에 올린 뒤 $0725 에 쓴다.
    A·P 를 그대로 둔다. 맵을 불러올 때 타일맵 지우기(04:983E)는 BG3SC 를 고르기 전에 옛 자리에서 일어나고,
    맵에 따라서는 그 뒤 타일맵 전체를 다시 올리지 않으므로, 새 자리는 옛 자리와 같은 버퍼 내용으로 채워 둔다."""
    dma = bytes((
        0xA9, 0x80, 0x8F, 0x15, 0x21, 0x00,            # LDA #$80 / STA $2115(워드 단위로 올림)
        0xA3, 0x01, 0x29, 0xFC, 0x8F, 0x17, 0x21, 0x00,  # LDA 1,S / AND #$FC / STA $2117
        0xA9, 0x00, 0x8F, 0x16, 0x21, 0x00,            # LDA #0 / STA $2116
        0xA9, 0x01, 0x8F, 0x70, 0x43, 0x00,            # LDA #$01 / STA $4370(두 레지스터 워드)
        0xA9, 0x18, 0x8F, 0x71, 0x43, 0x00,            # LDA #$18 / STA $4371($2118)
        0xA9, BUFFER & 0xFF, 0x8F, 0x72, 0x43, 0x00,
        0xA9, BUFFER >> 8 & 0xFF, 0x8F, 0x73, 0x43, 0x00,
        0xA9, BUFFER >> 16, 0x8F, 0x74, 0x43, 0x00,
        0xA9, 0x00, 0x8F, 0x75, 0x43, 0x00,            # 바이트 수 0800
        0xA9, 0x08, 0x8F, 0x76, 0x43, 0x00,
        0xA9, 0x80, 0x8F, 0x0B, 0x42, 0x00))           # LDA #$80 / STA $420B
    return bytes((
        0x08, 0xE2, 0x20, 0x48,                        # PHP / SEP #$20 / PHA
        0x49, 0x1C, 0xCF, *long(SHOWN),                # EOR #$1C / CMP $7E1ABC
        0xF0, len(dma))) + dma + bytes((               # BEQ 같음
        0x68, 0x8F, *long(SHADOW),                     # PLA / STA $7E0725
        0x49, 0x1C, 0x8F, *long(SHOWN), 0x49, 0x1C,    # EOR #$1C / STA $7E1ABC / EOR #$1C
        0x28, 0x6B))                                   # PLP / RTL


def build(base):
    """base 에 둘 코드와 (자리, 새 바이트, 원래 바이트) 목록."""
    code = bytearray()

    def add(b):
        a = base + len(code)
        code.extend(b)
        return a
    r16 = add(rebase16())
    r8 = add(rebase8())
    store16 = add(bytes((0x22, *long(r16), 0x8F, 0x16, 0x21, 0x00, 0x6B)))      # JSL r16 / STA $002116 / RTL
    # 타일맵 전체(2KB)를 보내는 vblank 의 DMA. 바라는 자리가 지금 자리와 다르면 이때 바꿔, 새 자리를 다 채우는 DMA 와
    # BG3SC 가 같은 vblank 에 들어가게 한다.
    switch = bytes((0x8F, *long(SHOWN), 0x49, 0x1C, 0x8F, 0x09, 0x21, 0x00))  # STA $7E1ABC / EOR #$1C / STA $002109
    full16 = add(bytes((0x48, 0x08, 0xE2, 0x20,                                 # PHA / PHP / SEP #$20
                        0xAF, *long(SHADOW), 0x49, 0x1C,                        # LDA $7E0725 / EOR #$1C
                        0xCF, *long(SHOWN), 0xF0, len(switch))) + switch + bytes((   # CMP $7E1ABC / BEQ
                        0x28, 0x68, 0x5C, *long(store16))))                     # PLP / PLA / JML store16
    store8 = add(bytes((0x22, *long(r8), 0x8F, 0x17, 0x21, 0x00,               # JSL r8 / STA $002117
                        0xA9, 0x80, 0x6B)))                                     # LDA #$80 / RTL
    line = add(bytes((0xC2, 0x20, 0xA9, 0xE0, 0x1C, 0x22, *long(r16),           # REP #$20 / LDA #$1CE0 / JSL r16
                      0x8F, 0x5E, 0x0F, 0x7E, 0x6B)))                          # STA $7E0F5E / RTL
    clear = add(clear_code())
    table = add(b''.join(bytes(p) for p in USES_3C00) + b'\xff')
    third = bytes((0xBF, *long(table + 1), 0xCF, *long(0x7E00BD)))             # LDA table+1,X / CMP $7E00BD
    step = bytes((0xE8, 0xE8))                                                  # INX / INX
    pick = bytes((0xA9, INTERIOR, 0x80, 0x02, 0xA9, SHARED))                    # 3C: LDA #$3C / BRA / 48: LDA #$48
    body = (bytes((0xCF, *long(0x7E00BC), 0xD0, len(third) + 2)) + third       # CMP $7E00BC / BNE 다음
            + bytes((0xF0, len(step) + 2 + 4)) + step)                          # BEQ 48
    head = bytes((0xBF, *long(table), 0xC9, 0xFF))                              # LDA table,X / CMP #$FF
    loop = head + bytes((0xF0, len(body) + 2)) + body                           # BEQ 3C
    loop += bytes((0x80, (-(len(loop) + 2)) & 0xFF))                            # BRA loop
    inner = bytes((0x08, 0xDA, 0xC2, 0x10, 0xA2, 0x00, 0x00)) + loop + pick + bytes((0xFA, 0x28))  # PHP/PHX/REP/LDX … PLX/PLP
    choose = add(bytes((0xAF, *long(0x7E00BE), 0x30, 0x04,                      # LDA $7E00BE / BMI 실내
                        0xA9, FIELD, 0x80, len(inner))) + inner + bytes((       # LDA #$78 / BRA 지우기로
                        0x22, *long(clear), 0x6B)))                             # JSL 새 자리 지우기 / RTL
    battle = add(bytes((0x08, 0xE2, 0x20, 0xAF, *long(SHADOW),                  # PHP / SEP #$20 / LDA $7E0725
                        0xC9, SHARED, 0xD0, 0x06,                               # CMP #$48 / BNE 그대로(3C·78 은 전투가 안 씀)
                        0xA9, FIELD, 0x8F, *long(SHADOW),                       # LDA #$78 / STA $7E0725
                        0x28, 0x5C, *long(0x04E2A1))))                          # PLP / JML $04E2A1
    sites = [(a, bytes((0x22, *long(full16 if a == FULL_SITE else store16))), old) for a, old in VMADD_SITES]
    sites.append((VMADD_HI_SITE[0], bytes((0x22, *long(store8), 0xEA)), VMADD_HI_SITE[1]))
    sites += [(a, bytes((0x22, *long(line), 0xEA, 0xEA)), old) for a, old in LINE_SITES]
    sites.append((MAP_CHOOSE, bytes((0x22, *long(choose), 0x6B, 0xEA)), 'a91c8d25076b'))
    sites.append((BATTLE_START, bytes((0x22, *long(battle))), '22a1e204'))
    return bytes(code), sites


def apply(data):
    d = bytearray(data)
    code, sites = build(CODE)
    o = lorom(CODE)
    if any(d[o:o + len(code)]):
        raise ValueError(f'{CODE:06X}~ 가 비어 있지 않음')
    d[o:o + len(code)] = code
    for addr, new, old in sites:
        p = lorom(addr)
        old = bytes.fromhex(old)
        if bytes(d[p:p + len(old)]) != old:
            raise ValueError(f'{addr:06X}: 예상한 원래 바이트가 아님')
        if len(new) > len(old):
            raise ValueError(f'{addr:06X}: 바꿀 바이트가 원래보다 김')
        d[p:p + len(new)] = new
    return bytes(d)
