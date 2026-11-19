"""DQ5 에 없는 FC 물건의 동작: 빌린 자리(dq4itemport.BORROWED·EVENT_ITEMS)의 쓰기 처리기를 FC 효과로 바꾼다.

ラックのたね 는 DQ5 まもりのたね 자리(AE)를 빌린다. DQ5 まもりのたね 는 みのまもり 를 4 올리는데(필드 11:89A4, 전투
20:BCCA), FC ラックのたね 는 うんのよさ 를 1~3 올린다(필드 12:$B022 rand(3)+1, 전투 13:$B5E4). DQ5 의 다른 씨앗처럼
1~3 을 고르는 몸통(필드 11:898D, 전투 20:BCF7)에 운 칸을 넘긴다. 운 칸 번호는 DQ5 필드 설명자(21:8D96)의 22(읽기)·
23(더하기)이고, 전투는 다른 씨앗처럼 Y = 더하기, X = 읽기다. 메시지 1BC(필드)·C9(전투)는 まもりのたね 만 부른다.
"""

LUCK_SEED = 0xAE
LUCK_READ, LUCK_ADD = 0x22, 0x23

# 필드: LDX #$0023 / JSR $898D(1~3 을 $F6 에, 칸 X 에 더함) / BRK 98 BC / RTS. 원래는 LDX #$001F / LDA #$04 / JSR $8994
FIELD_AT = 0x1189A4
FIELD_ORIG = bytes.fromhex("a2 1f 00 a9 04 20 94 89 00 98 bc 60")
FIELD_NEW = bytes((0xA2, LUCK_ADD, 0x00, 0x20, 0x8D, 0x89, 0x00, 0x98, 0xBC, 0x60, 0xEA, 0xEA))
# 전투: LDY #$23 / LDX #$22 / JSR $BCF7(1~3) / BRK A7 C9 / SEC / RTS. 원래는 LDY #$1F / LDX #$1E / LDA #$04 / JSR $BCFE
BATTLE_AT = 0x20BCCA
BATTLE_ORIG = bytes.fromhex("a0 1f a2 1e a9 04 20 fe bc 00 a7 c9 38 60")
BATTLE_NEW = bytes((0xA0, LUCK_ADD, 0xA2, LUCK_READ, 0x20, 0xF7, 0xBC, 0x00, 0xA7, 0xC9, 0x38, 0x60, 0xEA, 0xEA))


def _cpu(addr):
    return f"{addr >> 16:02X}:{addr & 0xFFFF:04X}"


def _patch(rom, at, orig, new, note):
    got = bytes(rom.u8(at + k) for k in range(len(orig)))
    if got != orig:
        raise ValueError(f"{_cpu(at)}: {got.hex(' ')} 이지 {orig.hex(' ')} 가 아님")
    return {"at": _cpu(at), "hex": new.hex(" ").upper(), "orig": orig.hex(" ").upper(), "note": note}


def writes(rom):
    return [_patch(rom, FIELD_AT, FIELD_ORIG, FIELD_NEW, "ラックのたね 필드에서 쓰기: 운 1~3"),
            _patch(rom, BATTLE_AT, BATTLE_ORIG, BATTLE_NEW, "ラックのたね 전투에서 쓰기: 운 1~3")]
