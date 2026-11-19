"""DQ5 에 없는 FC 물건의 동작: 빌린 자리(dq4itemport.BORROWED·EVENT_ITEMS)의 쓰기 처리기를 FC 효과로 바꾼다.

ラックのたね 는 DQ5 まもりのたね 자리(AE)를 빌린다. DQ5 まもりのたね 는 みのまもり 를 4 올리는데(필드 11:89A4, 전투
20:BCCA), FC ラックのたね 는 うんのよさ 를 1~3 올린다(필드 12:$B022 rand(3)+1, 전투 13:$B5E4). DQ5 의 다른 씨앗처럼
1~3 을 고르는 몸통(필드 11:898D, 전투 20:BCF7)에 운 칸을 넘긴다. 운 칸 번호는 DQ5 필드 설명자(21:8D96)의 22(읽기)·
23(더하기)이고, 전투는 다른 씨앗처럼 Y = 더하기, X = 읽기다. 메시지 1BC(필드)·C9(전투)는 まもりのたね 만 부른다.

열쇠 물건 자리(dq4itemport.EVENT_ITEMS): 필드 쓰기·기록은 dq4itemport 가 둔다(FC 필드 효과 비트가 꺼진 것은 「しかし
なにも おこらなかった。」 와 같은 글 18E 를 띄우는 いのちのいし 처리기 11:8BB9). 여기서는 전투 도구 표(27:819A, 같은 차례의
처리기 20:C162)를 고친다. 그 자리의 DQ5 물건이 표에 있으면 DQ5 효과(ばくだんいし 의 폭발, ファイトいっぱつ 의 힘, すず 의
깨움, ドラム 의 공격력, まもののエサ)가 나므로:
- おべんとう(BB): FC 는 やくそう 와 같은 행동 94 라 やくそう 처리기를 그 칸에(BATTLE_AS).
- 나머지(てつのきんこ BC·ぎんのめがみぞう BD·じょうせんけん C1·せいじゃくのたま C4): 칸의 물건을 이 해킹에서 얻을 수 없는 번호로
  바꿔 표에서 뺀다. FC 는 넷 다 「つかった！」 뒤 아무 일 없다(행동 7F). 다만 FC せいじゃくのたま 는 마호톤(행동 9D,
  11:$9C9D 가 バルザック 에게만 따로 한 번 더 부름)이라 4장을 옮길 때 맞출 몫으로 남는다.
- うまのふん(C2, いのちのいし)·おうごんのうでわ 등 나머지 자리는 DQ5 에서도 표에 없다.
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


SILENCE_ORB, SHIP_TICKET, HORSE_DUNG, BENTO, HERB = 0xC4, 0xC1, 0xC2, 0xBB, 0xA1
BATTLE_ITEMS, BATTLE_HANDLERS, BATTLE_COUNT = 0x27819A, 0x20C162, 53
# 전투에서 다른 DQ5 물건의 처리기를 쓰는 사건 물건
BATTLE_AS = {BENTO: HERB}
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


def _word(rom, at, value, note):
    return {"at": _cpu(at), "hex": f"{value & 0xFF:02X} {value >> 8:02X}",
            "orig": f"{rom.u8(at):02X} {rom.u8(at + 1):02X}", "note": note}


def writes(rom, event_items):
    """event_items: dq4itemport.EVENT_ITEMS {DQ5 slot: FC name}."""
    out = [_patch(rom, FIELD_AT, FIELD_ORIG, FIELD_NEW, "ラックのたね 필드에서 쓰기: 운 1~3"),
           _patch(rom, BATTLE_AT, BATTLE_ORIG, BATTLE_NEW, "ラックのたね 전투에서 쓰기: 운 1~3")]
    if battle_slot(rom, NEVER_HELD) is not None:
        raise ValueError("전투 도구 표가 DQ5 원래 것과 다름")
    for item, name in sorted(event_items.items()):
        slot = battle_slot(rom, item)
        if slot is None:
            continue
        if item in BATTLE_AS:
            src = BATTLE_HANDLERS + 2 * battle_slot(rom, BATTLE_AS[item])
            out.append(_word(rom, BATTLE_HANDLERS + 2 * slot, rom.u16(src),
                             f"{name} 전투에서 쓰기: {BATTLE_AS[item]:02X} 처리기"))
        else:
            out.append(_byte(rom, BATTLE_ITEMS + slot, NEVER_HELD, f"{name}: 전투 도구 표에서 뺌(DQ5 효과 없음)"))
    return out
