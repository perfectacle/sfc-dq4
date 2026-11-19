"""DQ5 에 없는 FC 물건의 동작: 빌린 자리(dq4itemport.BORROWED·EVENT_ITEMS)의 쓰기 처리기를 FC 효과로 바꾼다.

ラックのたね 는 DQ5 まもりのたね 자리(AE)를 빌린다. DQ5 まもりのたね 는 みのまもり 를 4 올리는데(필드 11:89A4, 전투
20:BCCA), FC ラックのたね 는 うんのよさ 를 1~3 올린다(필드 12:$B022 rand(3)+1, 전투 13:$B5E4). DQ5 의 다른 씨앗처럼
1~3 을 고르는 몸통(필드 11:898D, 전투 20:BCF7)에 운 칸을 넘긴다. 운 칸 번호는 DQ5 필드 설명자(21:8D96)의 22(읽기)·
23(더하기)이고, 전투는 다른 씨앗처럼 Y = 더하기, X = 읽기다. 메시지 1BC(필드)·C9(전투)는 まもりのたね 만 부른다.

열쇠 물건 자리를 빌린 셋(dq4itemport.EVENT_ITEMS): FC 는 셋 다 필드 효과 비트($8D1B bit7)가 꺼져 있어 필드에서 쓰면
「…は …をつかった！」(019E) 뒤 「しかし なにも おこらなかった。」(02C5)뿐이고 남는다. 필드 쓰기는 같은 뜻의 글 18E 를 띄우는
DQ5 いのちのいし 처리기 11:8BB9 이고(dq4itemport.USE_TEMPLATES), 기록은 dq4itemport 가 둔다.
- うまのふん(C2, いのちのいし 자리): FC 는 2G 에 팔고 버릴 수 있다. 값과 「쓰면 남음」(k1 bit5 끔)은 dq4itemport 가 둔다.
  いのちのいし 는 전투 도구 표(27:819A)에 없다.
- じょうせんけん(C1, てんしのすず 자리)·せいじゃくのたま(C4, たたかいのドラム 자리): 기록은 다른 사건 물건처럼
  ゴールドオーブ 것(못 팖·쓰면 남음). 두 DQ5 물건은 전투 도구 표에 있어, 그 칸을 이 해킹에서 얻을 수 없는 물건 번호로 바꿔
  DQ5 효과(すず 의 깨움, ドラム 의 공격력 올림)가 나지 않게 한다. FC じょうせんけん 은 전투에서 「つかった！」 뒤 아무 일도
  없다(행동 7F). FC せいじゃくのたま 는 전투에서 마호톤(행동 9D, 11:$9C9D 가 バルザック 에게만 따로 한 번 더 부름)이라 4장을
  옮길 때 맞출 몫으로 남는다.
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


SILENCE_ORB, SHIP_TICKET, HORSE_DUNG = 0xC4, 0xC1, 0xC2
BATTLE_ITEMS, BATTLE_COUNT = 0x27819A, 53
# 이 해킹에서 얻을 수 없는 DQ5 열쇠 물건(リュウのひだりめ): 전투 도구 표에서 빼는 칸을 채운다
NEVER_HELD = 0xD7
# FC 필드 쓰기의 「しかし なにも おこらなかった。」 와 같은 글(18E)을 띄우는 DQ5 いのちのいし 의 필드 처리기
NOTHING_USE = 0x118BB9


def _cpu(addr):
    return f"{addr >> 16:02X}:{addr & 0xFFFF:04X}"


def _patch(rom, at, orig, new, note):
    got = bytes(rom.u8(at + k) for k in range(len(orig)))
    if got != orig:
        raise ValueError(f"{_cpu(at)}: {got.hex(' ')} 이지 {orig.hex(' ')} 가 아님")
    return {"at": _cpu(at), "hex": new.hex(" ").upper(), "orig": orig.hex(" ").upper(), "note": note}


def _byte(rom, at, value, note):
    return {"at": _cpu(at), "hex": f"{value:02X}", "orig": f"{rom.u8(at):02X}", "note": note}


def battle_slot(rom, item):
    """전투 도구 표에서 item 의 차례(없으면 None)."""
    row = [rom.u8(BATTLE_ITEMS + k) for k in range(BATTLE_COUNT)]
    return row.index(item) if item in row else None


def writes(rom):
    out = [_patch(rom, FIELD_AT, FIELD_ORIG, FIELD_NEW, "ラックのたね 필드에서 쓰기: 운 1~3"),
           _patch(rom, BATTLE_AT, BATTLE_ORIG, BATTLE_NEW, "ラックのたね 전투에서 쓰기: 운 1~3")]
    slots = {item: battle_slot(rom, item) for item in (SILENCE_ORB, SHIP_TICKET)}
    if None in slots.values() or battle_slot(rom, NEVER_HELD) is not None or battle_slot(rom, HORSE_DUNG) is not None:
        raise ValueError("전투 도구 표가 DQ5 원래 것과 다름")
    for item, name in ((SHIP_TICKET, "じょうせんけん"), (SILENCE_ORB, "せいじゃくのたま")):
        out.append(_byte(rom, BATTLE_ITEMS + slots[item], NEVER_HELD, f"{name}: 전투 도구 표에서 뺌(DQ5 효과 없음)"))
    return out
