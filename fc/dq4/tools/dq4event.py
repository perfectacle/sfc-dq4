"""DQ4(FC) 저장 데이터(SRAM)·이벤트 플래그·장 시작 표. 형식은 fc/dq4/docs/dq4-save-format.md.

사용:
  python fc/dq4/tools/dq4event.py rom/dq4.nes sram end.sram       작업 영역과 모험의 서 3칸: 체크섬, 장, 골드, 일행, 인물 8명
  python fc/dq4/tools/dq4event.py rom/dq4.nes flags end.sram      이벤트 플래그 영역 $627B~$62EE 의 0 아닌 바이트
  python fc/dq4/tools/dq4event.py rom/dq4.nes chapters            장(1~5) 시작 표: 자리, 선두, 골드, 귀환 자리
  python fc/dq4/tools/dq4event.py rom/dq4.nes chars [--compare end.sram]   인물 8명의 첫 레코드(장 시작 루틴이 쓰는 값).
                                                   --compare 는 덤프의 장($615A)에서 초기화되는 인물만 대조
  python fc/dq4/tools/dq4event.py rom/dq4.nes places              귀환 자리 표($6290 번호 → 장소·좌표), ルーラ 행선지($6165 비트
                                                   → 마을 레코드 → 도착 자리)
  python fc/dq4/tools/dq4event.py rom/dq4.nes flags --xref [NN] [--all]   플래그 바이트·비트마다 쓰는 곳·검사하는 곳(BRK 플래그
                                                   명령, 절대 주소 명령, 대화 스크립트, 인물 블록, 맵 인물 목록 표).
                                                   --all 은 데이터로 보이는 모양도 같이
  python fc/dq4/tools/dq4event.py rom/dq4.nes flags --meaning      한 비트 플래그마다 뜻: 확인한 것은 [확인], 나머지는 쓰는 곳의
                                                   맵·장소 이름과 대사 첫 줄로 [추정]
  python fc/dq4/tools/dq4event.py rom/dq4.nes ending              5장 끝(1A:$B8C2)에서 도는 엔딩 장면 목록(1A:$9E76)
  python fc/dq4/tools/dq4event.py rom/dq4.nes events              인물 블록의 이벤트 명령(88~8A n → 1D:$B639)과 맵 이벤트 표
  python fc/dq4/tools/dq4event.py rom/dq4.nes ops [--flag NN]      롬에서 BRK 플래그 명령(00 NN CB/DB/EB MM) 모양 찾기.
                                                   바이트 모양만 보므로 데이터가 섞인다

근거 루틴: 12:$ACA2(체크섬), 1F:$C8AD(CRC 한 바이트), 12:$ACF8(빈 칸 검사), 12:$8EAE(장 시작 초기화,
BRK 12 함수 17), 1E:$A578(시작 자리), 1E:$A73F(귀환 자리 번호 정하기), 10:$9513(ルーラ 목록), 1F:$D884(인물 블록 실행),
1C:$987F(맵 인물 목록 고르기), 1A:$B815(장 끝 검사).
"""
import sys

from kr_patch.fc import ines

import dq4data
import dq4flags
import dq4map
import dq4npcblock
import dq4talk
import dq4text

WORK, WORK_LEN = 0x6001, 0x2EE        # 게임이 쓰는 저장 대상 영역. 칸에는 이 영역이 그대로 복사된다
SLOTS = (0x62EF, 0x65DF, 0x68CF)      # 모험의 서 3칸: CRC 2바이트(아래, 위) + 작업 영역 사본
CRC_INIT, CRC_POLY = 0x3A3A, 0x1021
EMPTY = 0x4B                          # 칸 앞 5바이트가 모두 이 값이면 빈 칸(12:$ACF8)
REC, REC_LEN, CHARS = 0x6001, 0x1E, 8  # 인물 레코드. 번호 = 직업 이름 목록 순번(0 주인공 ~ 7 アリーナ)
GOLD, CHAPTER, HERO_NAME, PARTY = 0x6157, 0x615A, 0x615D, 0x616A
PLACE_NO, START_DONE = 0x6290, 0x6291
FLAGS, FLAGS_END = 0x627B, 0x62EE

INIT = 0x12                            # 장 시작 초기화가 있는 뱅크
CHAR_CHAPTER = 0x9136                  # 인물마다 처음 나오는 장(0~4)
LEADER = 0x913E                        # 장마다 $616A 에 쓰는 선두
STAT_PTRS, STAT_OFFS = 0x9151, 0x915D  # 능력치 6개: 표 포인터, 레코드 안 자리
CHAR_ITEMS = 0x9192                    # 인물마다 소지품 8바이트
CHAPTER_6165 = 0x9179                  # 장마다 $6165~$6169 에 쓰는 5바이트
CHAPTER_GOLD = 0x91D9
CHAR_HP = 0xA296
START = (0x1E, 0xA599)                 # 장마다 시작 (그룹, 순번, X, Y)
CHAPTER_PLACE = (0x1E, 0xA75E)         # 장마다 처음 $6290
PLACES = (0x1E, 0xA76D)                # 귀환 자리 5바이트: 그룹, 순번, X, Y, 방향(아래 2비트)·$AEFE 레코드 번호(위 6비트)
PLACE_COUNT = 22
TOWN_PTR = (0x1E, 0xAEFE)              # 마을 레코드 7바이트 표의 포인터($AF00): 필드(bit7 = 맵), X, Y, 바이트 3~6
TOWN_BANK = 0x10                       # ルーラ·キメラのつばさ 행선지(10:$9513 목록, 10:$95C1 가 본 마을 비트 켜기)
TOWN_GROUPS = (0x95EB, 0x95FA)         # $6165~ 비트 순번 → 맵 그룹. 1~4장 / 5장($615A ≥ 4), FF 로 끝
TOWN_RECORD = 0x9612                   # 비트 순번 → 마을 레코드 번호. 5장은 +0F 부터
VISITED = 0x6165

FIELDS = (('HP', 0x01, 2), ('MP', 0x03, 2), ('레벨', 0x05, 1), ('ちから', 0x06, 1), ('すばやさ', 0x07, 1),
          ('たいりょく', 0x08, 1), ('かしこさ', 0x09, 1), ('うんのよさ', 0x0A, 1), ('최대HP', 0x0C, 2),
          ('최대MP', 0x0E, 2), ('경험치', 0x10, 3))


def rd(prg, bank, addr):
    return prg[bank * 0x4000 + (addr & 0x3FFF)]


def crc(data):
    """1F:$C8AD: CRC-16(다항식 1021, 위 비트부터, 시작값 3A3A, 마지막 XOR 없음)."""
    c = CRC_INIT
    for b in data:
        c ^= b << 8
        for _ in range(8):
            c = ((c << 1) ^ CRC_POLY if c & 0x8000 else c << 1) & 0xFFFF
    return c


def at(sram, addr, n=1):
    v = 0
    for k in range(n):
        v |= sram[addr - 0x6000 + k] << 8 * k
    return v


def slots(sram):
    """칸마다 (주소, 빈 칸인지, 적힌 CRC, 계산한 CRC, 사본 바이트)."""
    out = []
    for a in SLOTS:
        o = a - 0x6000
        body = sram[o + 2:o + 2 + WORK_LEN]
        out.append((a, all(b == EMPTY for b in sram[o:o + 5]), sram[o] | sram[o + 1] << 8, crc(body), body))
    return out


def as_sram(body):
    """사본 바이트를 SRAM 모양(작업 영역 자리)으로 놓아 같은 함수로 읽게 한다."""
    s = bytearray(0x300)
    s[WORK - 0x6000:WORK - 0x6000 + WORK_LEN] = body
    return bytes(s)


def names(prg):
    item = {i: n for i, n, *_ in dq4data.items(prg)}
    cls = [dq4text.text(n) for n in dq4data.name_list(prg, 'class')[1:]]
    return item, cls


def item_list(item, bs):
    return ' '.join(('E' if b & 0x80 else '') + item.get(b & 0x7F, f'[{b:02X}]') for b in bs if b != 0xFF)


def show_state(prg, s, indent=''):
    item, cls = names(prg)
    party = [at(s, PARTY + k) for k in range(14)]
    name = [at(s, HERO_NAME + k) for k in range(4)]
    print(f'{indent}장 {at(s, CHAPTER) + 1}($615A={at(s, CHAPTER):02X})  골드 {at(s, GOLD, 3)}  '
          f'주인공 이름 {dq4text.text(name).rstrip("　")}({bytes(name).hex(" ")})  '
          f'귀환 자리 {at(s, PLACE_NO):02X}  $6291={at(s, START_DONE):02X}')
    print(f'{indent}일행 $616A: ' + ' '.join(f'{b:02X}' for b in party[:4]) + '  그 밖 $6172: '
          + ' '.join(f'{b:02X}' for b in party[8:]))
    for i in range(CHARS):
        r = REC + REC_LEN * i
        if not at(s, r) & 0x80:
            continue
        v = {nm: at(s, r + o, n) for nm, o, n in FIELDS}
        print(f'{indent}  {i} {cls[i]:<8} ' + ' '.join(f'{k} {x}' for k, x in v.items()))
        print(f'{indent}      소지품 {item_list(item, [at(s, r + 0x13 + k) for k in range(8)])}'
              f'  +0B={at(s, r + 0x0B):02X} +1B~1D={at(s, r + 0x1B, 3):06X}')


def cmd_sram(prg, s):
    print(f'== 작업 영역 ${WORK:04X}~${WORK + WORK_LEN - 1:04X}')
    show_state(prg, s)
    for k, (a, empty, stored, calc, body) in enumerate(slots(s)):
        if empty:
            print(f'== 모험의 서 {k + 1} ${a:04X}: 빈 칸')
            continue
        same = body == s[WORK - 0x6000:WORK - 0x6000 + WORK_LEN]
        print(f'== 모험의 서 {k + 1} ${a:04X}: CRC {stored:04X} 계산 {calc:04X} '
              f'{"맞음" if stored == calc else "다름"}  작업 영역과 {"같음" if same else "다름"}')
        show_state(prg, as_sram(body), '  ')
    return 0


def cmd_flags(s):
    for a in range(FLAGS, FLAGS_END + 1):
        if at(s, a):
            print(f'${a:04X} 번호 {a - FLAGS:02X} = {at(s, a):02X}  {at(s, a):08b}')
    return 0


def start_table(prg):
    """장마다 (시작 그룹, 순번, X, Y, 선두 $616A, 골드, $6165~$6169, 처음 $6290)."""
    out = []
    for c in range(5):
        g, k, x, y = (rd(prg, START[0], START[1] + 4 * c + j) for j in range(4))
        out.append((g, k, x, y, rd(prg, INIT, LEADER + c), rd(prg, INIT, CHAPTER_GOLD + c),
                    bytes(rd(prg, INIT, CHAPTER_6165 + 5 * c + j) for j in range(5)),
                    rd(prg, CHAPTER_PLACE[0], CHAPTER_PLACE[1] + c)))
    return out


def cmd_chapters(prg):
    _, cls = names(prg)
    for c, (g, k, x, y, lead, gold, b6165, place) in enumerate(start_table(prg)):
        who = [cls[i] for i in range(CHARS) if rd(prg, INIT, CHAR_CHAPTER + i) == c]
        print(f'{c + 1}장 시작 {g:02X}/{k:02X} ({x:02X},{y:02X})  선두 {lead:02X}({cls[lead & 0x7F]})  골드 {gold}  '
              f'$6165={b6165.hex(" ")}  귀환 자리 {place:02X}  초기화 인물 {", ".join(who)}')
    return 0


def init_record(prg, i):
    """12:$8EFF~$9010 이 인물 i 에 쓰는 바이트(레코드 안 자리 → 값). 주문 비트(BRK 38 0F)는 빼고."""
    w = {}
    hp = rd(prg, INIT, CHAR_HP + i)
    stats = {}
    for s in range(6):
        p = rd(prg, INIT, STAT_PTRS + 2 * s) | rd(prg, INIT, STAT_PTRS + 2 * s + 1) << 8
        # 능력치 하나는 표의 6바이트 단위 중 앞 5바이트 bit7 을 모은 5비트 값(앞 바이트가 아래 비트)
        stats[rd(prg, INIT, STAT_OFFS + s)] = sum((rd(prg, INIT, p + 6 * i + k) >> 7 & 1) << k for k in range(5))
    if i >= 6:
        stats[0x0E] = 0
    w.update({0x00: 0x80, 0x01: hp, 0x02: 0, 0x05: 1, 0x0C: hp, 0x0D: 0, 0x04: 0})
    w.update(stats)
    w[0x03] = stats[0x0E]
    for k in range(8):
        w[0x13 + k] = rd(prg, INIT, CHAR_ITEMS + 8 * i + k)
    return w


def cmd_chars(prg, compare):
    item, cls = names(prg)
    bad = 0
    s = open(compare, 'rb').read() if compare else None
    for i in range(CHARS):
        w = init_record(prg, i)
        stats = ' '.join(f'{nm} {w.get(o, 0) | (w.get(o + 1, 0) << 8 if n == 2 else 0)}'
                         for nm, o, n in FIELDS if o in w)
        print(f'{i} {cls[i]:<8} {rd(prg, INIT, CHAR_CHAPTER + i) + 1}장  {stats}')
        print(f'      소지품 {item_list(item, [w[0x13 + k] for k in range(8)])}')
        if s is not None and rd(prg, INIT, CHAR_CHAPTER + i) == at(s, CHAPTER):
            diff = [o for o, v in w.items() if at(s, REC + REC_LEN * i + o) != v]
            bad += len(diff)
            print('      비교: ' + ('같음' if not diff else '다름 ' + ' '.join(f'+{o:02X}' for o in diff)))
    return 1 if bad else 0


def town_record(prg, r):
    base = rd(prg, *TOWN_PTR) | rd(prg, TOWN_PTR[0], TOWN_PTR[1] + 1) << 8
    return [rd(prg, TOWN_PTR[0], base + 7 * r + j) for j in range(7)]


def towns(prg, ch5):
    """ルーラ 행선지: (비트 순번, 맵 그룹, 마을 레코드 번호, 레코드 7바이트)."""
    out, lst = [], TOWN_GROUPS[1 if ch5 else 0]
    while (g := rd(prg, TOWN_BANK, lst + len(out))) != 0xFF:
        r = rd(prg, TOWN_BANK, TOWN_RECORD + (0x0F if ch5 else 0) + len(out))
        out.append((len(out), g, r, town_record(prg, r)))
    return out


def town_dest(rec):
    """레코드 0~2 바이트: 필드 f 의 (X, Y). f bit7 이면 맵 (바이트 3, 4) 의 (X, Y)."""
    f, x, y = rec[:3]
    return f'맵 {rec[3]:02X}/{rec[4]:02X} ({x:02X},{y:02X})' if f & 0x80 else f'필드 {f} ({x:02X},{y:02X})'


def cmd_places(prg):
    print(f'== 귀환 자리 {PLACES[0]:02X}:${PLACES[1]:04X} ($6290 번호)')
    for i in range(PLACE_COUNT):
        g, k, x, y, d = (rd(prg, PLACES[0], PLACES[1] + 5 * i + j) for j in range(5))
        rec = town_record(prg, d >> 2)
        print(f'{i:02X} {g:02X}/{k:02X} ({x:02X},{y:02X}) 방향 {d & 3}  마을 레코드 {d >> 2:02X} '
              f'→ $6195~$6198 = {bytes(rec[3:]).hex(" ")}')
    for ch5 in (False, True):
        print(f'== ルーラ 행선지 {"5장" if ch5 else "1~4장"} (${VISITED:04X} 비트 → 맵 그룹 → 마을 레코드 → 도착)')
        for i, g, r, rec in towns(prg, ch5):
            print(f'  비트 {i:02X} (${VISITED + i // 8:04X} {1 << i % 8:02X})  그룹 {g:02X}  레코드 {r:02X}  {town_dest(rec)}')
    return 0


FLAG_OPS = {0xCB: '켜기 |=', 0xDB: '끄기 &=', 0xEB: '검사 &'}


def flag_ops(prg):
    """(PRG 오프셋, 번호, 명령, 마스크). 1F:$C4AE~$C4EF 가 푸는 BRK 특수 형식."""
    out = []
    for p in range(len(prg) - 3):
        if prg[p] == 0 and prg[p + 2] in FLAG_OPS and prg[p + 1] <= FLAGS_END - FLAGS:
            out.append((p, prg[p + 1], prg[p + 2], prg[p + 3]))
    return out


def cpu_addr(p):
    bank = p // 0x4000
    return bank, (0xC000 if bank in (0x0F, 0x1F) else 0x8000) + p % 0x4000


# 대사(00~04)·인물 목록(05)·맵(09~0B) 등 실행된 적이 없는 데이터 뱅크(dq4-bank-format.md)
DATA_BANKS = set(range(0x08)) | {0x09, 0x0A, 0x0B}


def likely_code(p, op=None, m=None):
    """모양만 맞는 데이터를 거르는 기준: 데이터 뱅크가 아니고, 켜기·검사는 한 비트, 끄기는 한 비트를 뺀
    마스크나 00."""
    if p // 0x4000 in DATA_BANKS:
        return False
    if op is None:
        return True
    ones = m.bit_count()
    return ones == 1 if op in (0xCB, 0xEB) else ones == 7 or m == 0


# $627B~ 를 절대 주소로 읽고 쓰는 명령(3바이트). 값은 (이름, 쓰기인지)
ABS_OPS = {0xAD: ('LDA', 0), 0xAE: ('LDX', 0), 0xAC: ('LDY', 0), 0x2D: ('AND', 0), 0x0D: ('ORA', 0),
           0x4D: ('EOR', 0), 0xCD: ('CMP', 0), 0xEC: ('CPX', 0), 0xCC: ('CPY', 0), 0x2C: ('BIT', 0),
           0x6D: ('ADC', 0), 0xED: ('SBC', 0), 0x8D: ('STA', 1), 0x8E: ('STX', 1), 0x8C: ('STY', 1),
           0xEE: ('INC', 1), 0xCE: ('DEC', 1), 0x0E: ('ASL', 1), 0x4E: ('LSR', 1), 0x2E: ('ROL', 1),
           0x6E: ('ROR', 1)}
NEAR = 0x30                           # 플래그 명령 앞뒤로 맵 비교·메시지를 찾을 바이트 수


def near_map(prg, p):
    """명령 앞 NEAR 바이트 안의 LDA $63 / CMP #g, LDA $64 / CMP #k(코드 근처에서 맵을 고르는 모양)."""
    g = k = None
    for q in range(max(0, p - NEAR), p - 3):
        if prg[q] == 0xA5 and prg[q + 2] == 0xC9:
            if prg[q + 1] == 0x63:
                g = prg[q + 3]
            elif prg[q + 1] == 0x64:
                k = prg[q + 3]
    return g, k


def near_msg(prg, p):
    """명령 뒤 NEAR 바이트 안의 첫 메시지 BRK(00 lo hB, hB < CB: 16[04] X=h, A=lo)."""
    for q in range(p + 4, min(len(prg) - 2, p + 4 + NEAR)):
        if prg[q] == 0 and prg[q + 2] & 0x0F == 0x0B and prg[q + 2] < 0xCB:
            return (prg[q + 2] >> 4) << 8 | prg[q + 1]
    return None


def code_uses(prg):
    """롬 코드 쪽: (번호, 마스크, 종류, 위치, 근처 맵, 근처 메시지, 한 비트 모양인지)."""
    out = []
    for p, n, op, m in flag_ops(prg):
        kind = {0xCB: 'set', 0xDB: 'clear', 0xEB: 'test'}[op]
        bank, addr = cpu_addr(p)
        out.append((n, m, kind, f'BRK {bank:02X}:${addr:04X}', near_map(prg, p), near_msg(prg, p),
                    likely_code(p, op, m)))
    for p in range(len(prg) - 2):
        a = prg[p + 1] | prg[p + 2] << 8
        if prg[p] in ABS_OPS and FLAGS <= a <= FLAGS_END:
            name, w = ABS_OPS[prg[p]]
            bank, addr = cpu_addr(p)
            out.append((a - FLAGS, None, 'write' if w else 'read', f'{name} {bank:02X}:${addr:04X}',
                        near_map(prg, p), None, likely_code(p)))
    return out


# 인물 블록(움직임 스크립트, 1F:$D884 가 한 명령씩 실행) 중 플래그·이벤트를 다루는 명령. 명령 단위로 푸는 것은
# fc/dq4/tools/dq4npcblock.py(fc/dq4/docs/dq4-npcblock-format.md).
BLOCK_FLAG_OPS = {0x27: 'npc|=', 0x28: 'npc&=', 0x29: 'npc='}
BLOCK_EVENT_OPS = (0x88, 0x89, 0x8A)
EVENTS = dq4npcblock.EVENTS           # 이벤트 n → 루틴 주소 워드(1D:$989F)
EVENT_COUNT = dq4npcblock.EVENT_COUNT


def npc_lists(prg):
    """인물 목록마다 (이름, 그룹, 순번, 밤인지, 슬롯 6~ 순서의 레코드): 맵의 낮·밤 목록과 이벤트 목록(1C:$9D0E 표)."""
    for g, k, *_ in dq4map.maps(prg):
        yield '', g, k, False, dq4talk.npc_list(prg, g, k)
        yield '밤 ', g, k, True, dq4talk.npc_list(prg, g, k, night=True)
    for g, k, _, _, a in dq4map.event_entries(prg):
        yield f'목록 1C:${a:04X} ', g, k, False, [r for r in dq4map.records_at(prg, 0x1C, a)[0] if r[0] & 0x10]


def block_uses(prg):
    """인물 블록(맵 목록·이벤트 목록, 낮 블록1·밤 블록2)을 명령 단위로 풀어 (종류, 목록 이름, 그룹, 순번, 슬롯, 값,
    블록 안 자리, 메시지). 플래그는 27~29 중 주소가 플래그 영역인 것, 이벤트는 88~8A n. 메시지는 같은 블록에서
    그 명령 앞의 가장 가까운 26 명령(없으면 뒤의 첫 26)."""
    out = []
    for name, bank, i, j, a, ln, slot in dq4npcblock.all_blocks(prg):
        g, k = (int(x, 16) for x in name[:5].split('/'))
        label = ('' if ' 목록 ' not in name else name[6:] + ' ') + ('밤 ' if j == 2 else '')
        cmds = dq4npcblock.decode(prg, bank, a, ln)
        msgs = [(p, bs[2] << 8 | bs[1]) for p, bs, *_ in cmds if bs[0] == 0x26]
        for p, bs, *_ in cmds:
            before = [m for q, m in msgs if q < p]
            after = [m for q, m in msgs if q > p]
            msg = before[-1] if before else (after[0] if after else None)
            if bs[0] in BLOCK_FLAG_OPS:
                at = bs[2] | bs[3] << 8
                if FLAGS <= at <= FLAGS_END:
                    out.append((BLOCK_FLAG_OPS[bs[0]], label, g, k, slot, (at - FLAGS, bs[1]), p - a, msg))
            elif bs[0] in BLOCK_EVENT_OPS and bs[1] < EVENT_COUNT:
                out.append(('event', label, g, k, slot, bs[1], p - a, msg))
    return out


def event_addr(prg, n):
    return rd(prg, EVENTS[0], EVENTS[1] + 2 * n) | rd(prg, EVENTS[0], EVENTS[1] + 2 * n + 1) << 8


# 맵을 실을 때(1C:$987F) 인물 목록을 고르는 표 두 개. 둘 다 (그룹, 순번) 이 같고 $627B+n & m 이 0 이 아니면 쓰인다.
NPC_CLEAR = (0x1C, 0x9E61)            # 4바이트 (그룹, 순번, m, n): 인물 목록을 싣지 않음(1C:$9C28 이 C 를 세움)
NPC_ALT_PTR = (0x1C, 0x9D0E)          # 6바이트 표의 포인터: (그룹, 순번, m, n, 목록 주소): 그 주소의 인물 목록(1C:$9CC1)


def npc_tables(prg):
    """(종류, 그룹, 순번, n, m, 대체 목록 주소)."""
    out, a = [], NPC_CLEAR[1]
    while (g := rd(prg, NPC_CLEAR[0], a)) != 0xFF:
        k, m, n = (rd(prg, NPC_CLEAR[0], a + i) for i in (1, 2, 3))
        out.append(('clear', g, k, n, m, None))
        a += 4
    a = rd(prg, *NPC_ALT_PTR) | rd(prg, NPC_ALT_PTR[0], NPC_ALT_PTR[1] + 1) << 8
    while (g := rd(prg, NPC_ALT_PTR[0], a)) != 0xFF:
        k, m, n, lo, hi = (rd(prg, NPC_ALT_PTR[0], a + i) for i in range(1, 6))
        out.append(('alt', g, k, n, m, hi << 8 | lo))
        a += 6
    return out


def talk_uses(prg):
    """대화 스크립트 쪽: 맵의 낮·밤 목록과 이벤트 목록 인물(슬롯 순서)의 대화 번호를 풀어 17/18/19 문장과 1A/1B/1C 조건을 모은다.
    대사는 켜기·끄기면 같은 블록의 첫 메시지, 조건이면 then 갈래의 첫 메시지.
    돌려주는 것: (번호, 마스크, 종류, 대화 번호, 대사) 목록과 대화 번호 → 그 대화를 쓰는 (맵, 슬롯) 목록."""
    who, out = {}, []

    def walk(tree, tid):
        msgs = dq4talk.messages(tree)
        for s in tree:
            if s[0] in ('flag|=', 'flag&=', 'flag='):
                kind = {'flag|=': 'set', 'flag&=': 'clear', 'flag=': 'store'}[s[0]]
                out.append((s[1][0], s[1][1], kind, tid, msgs[0] if msgs else None))
            elif s[0] == 'if':
                _, neg, op, args, then, other = s
                if op in (0x1A, 0x1B, 0x1C):
                    sub = dq4talk.messages(then)
                    kind = {0x1A: 'talk!=', 0x1B: 'talk&', 0x1C: 'talk|'}[op] + ('!' if neg else '')
                    out.append((args[0], args[1], kind, tid, sub[0] if sub else None))
                walk(then, tid)
                if other:
                    walk(other, tid)

    for name, g, k, night, recs in npc_lists(prg):
        for i, r in enumerate(recs):
            tid = dq4talk.talk_id(r, night)
            c = dq4talk.classify(prg, tid)
            if c[0] != 'script':
                continue
            if tid not in who:
                walk(c[2], tid)
            who.setdefault(tid, []).append((name, g, k, i + 6))
    return out, who


def flag_xref(prg, all_shapes=False):
    """번호 → [(마스크, 종류, 어디, 메시지)]. 종류: set/clear/test(BRK), read/write(절대 주소), talk…(대화)."""
    rows = {}

    def add(n, row):
        if row not in rows.setdefault(n, []):
            rows[n].append(row)

    for n, m, kind, where, (g, k), msg, ok in code_uses(prg):
        if not ok and not all_shapes:
            continue
        mp = '' if g is None else f' 맵 {g:02X}/' + ('??' if k is None else f'{k:02X}')
        add(n, (m, kind, where + mp + ('' if ok else ' (모양만)'), msg))
    talk, who = talk_uses(prg)
    for n, m, kind, tid, msg in talk:
        name, g, k, slot = who[tid][0]
        more = f' 외 {len(who[tid]) - 1}명' if len(who[tid]) > 1 else ''
        add(n, (m, kind, f'대화 {tid:03X} {name}{g:02X}/{k:02X} 슬롯 {slot:02X}{more}', msg))
    for kind, g, k, n, m, ptr in npc_tables(prg):
        what = '인물 목록 비움' if kind == 'clear' else f'인물 목록 1C:${ptr:04X} 로 바꿈'
        add(n, (m, 'test', f'맵 표 {g:02X}/{k:02X} {what}', None))
    for kind, name, g, k, slot, (n, m), _, msg in (u for u in block_uses(prg) if u[0] != 'event'):
        add(n, (m, {'npc|=': 'set', 'npc&=': 'clear', 'npc=': 'store'}[kind],
                f'인물 블록 {name}{g:02X}/{k:02X} 슬롯 {slot:02X}', msg))
    return rows


def bit_of(m, kind):
    """끄기(&=)는 마스크를 뒤집어 다루는 비트로 바꾼다. 절대 주소 접근은 비트를 모르므로 None."""
    if m is None:
        return None
    return ~m & 0xFF if kind == 'clear' else m


WRITERS = ('set', 'store', 'clear', 'write')


def cmd_xref(prg, rom, only, all_shapes):
    rows = flag_xref(prg, all_shapes)
    order = {'set': 0, 'store': 0, 'clear': 1, 'write': 2}
    bits = {}
    for n in sorted(rows):
        for m, kind, *_ in rows[n]:
            b = bit_of(m, kind)
            if b is not None and b.bit_count() == 1:
                bits.setdefault((n, b), set()).add('w' if kind in WRITERS else 'r')
        if only is not None and n != only:
            continue
        print(f'== ${FLAGS + n:04X} 번호 {n:02X}')
        for m, kind, where, msg in sorted(rows[n], key=lambda r: (r[0] is None, bit_of(r[0], r[1]) or 0,
                                                                  order.get(r[1], 3), r[2])):
            mask = '  ' if m is None else f'{m:02X}'
            line = '' if msg is None else f'  {msg:04X} {dq4talk.first_line(rom, msg)[:30]}'
            print(f'  {mask} {kind:<7} {where}{line}')
    if only is None:
        both = sum(v == {'w', 'r'} for v in bits.values())
        w = sum(v == {'w'} for v in bits.values())
        print(f'한 비트 {len(bits)}개: 쓰고 검사하는 곳이 다 있음 {both}, 쓰기만 {w}, 검사만 {len(bits) - both - w}')
    return 0


# 화면·RAM 으로 확인한 비트의 뜻. (번호, 비트) → 뜻. 근거는 fc/dq4/docs/dq4-save-format.md 「플래그 비트의 뜻」.
# 장면을 돌려 켜지는 것을 본 비트는 dq4flags.CONFIRMED(fc/dq4/docs/dq4-story-format.md)에 있다.
KNOWN = {
    (0x00, 0x02): 'サントハイム 왕과 이야기함(2장). 성문 병사 대사가 바뀜',
    (0x07, 0x80): '1장을 끝냄',
    (0x08, 0x80): '1장 끝 조건의 하나($6283 & A0 = 80)', (0x0A, 0x04): '1장 끝 조건의 하나(02/00 에서)',
    (0x0D, 0x80): '엔딩 장면 중(1A:$9DC9 가 켬)',
    (0x2A, 0x80): '엔딩 장면 중(1A:$9DF3 가 켬). 켜져 있으면 인물 목록을 비우는 표 1C:$9E61 을 보지 않음', (0x07, 0x40): '2장을 끝냄', (0x07, 0x20): '3장을 끝냄', (0x07, 0x10): '4장을 끝냄',
    (0x09, 0x40): 'エンドール 무술 대회 뒤(2장). サントハイム 성 사람들이 사라짐',
    (0x0C, 0x08): '빈 サントハイム 성 왕좌의 방(01/01)에서 ブライ 대사를 봄(2장 끝 조건)',
    (0x0F, 0x10): '4장 끝 조건(그룹 04 에 들어가면 장 끝)',
    (0x16, 0x80): '이 장의 시작 처리를 했음',
    (0x26, 0x20): '5장 끝 조건(그룹 2D 에 들어가면 엔딩)',
}


def place_names(prg):
    """맵 그룹 → 장소 이름. ルーラ 목록의 마을 레코드 번호가 장소 이름 목록(0B:$B006)의 번호와 같다."""
    names = [dq4text.text(n) for n in dq4data.name_list(prg, 'place')[1:]]
    out = {}
    for ch5 in (False, True):
        for _, g, r, _ in towns(prg, ch5):
            if r < len(names):
                out.setdefault(g, names[r])
    return out


def cmd_meaning(prg, rom):
    """한 비트 플래그마다 뜻. KNOWN 에 있으면 그 뜻, 없으면 쓰는 곳(맵·장소 이름)과 그 대사 첫 줄로 짐작."""
    rows, place = flag_xref(prg), place_names(prg)
    bits = {}
    for n in rows:
        for m, kind, where, msg in rows[n]:
            b = bit_of(m, kind)
            if b is None or b.bit_count() != 1:
                continue
            e = bits.setdefault((n, b), {'w': [], 'r': []})
            e['w' if kind in WRITERS else 'r'].append((where, msg))
    print('번호 비트 주소     쓰기 검사  뜻')
    for (n, b), e in sorted(bits.items()):
        head = f'{n:02X}   {b:02X}   ${FLAGS + n:04X}  {len(e["w"]):3d}  {len(e["r"]):3d}  '
        known = KNOWN.get((n, b)) or dq4flags.CONFIRMED.get((n, b))
        if known:
            print(head + '[확인] ' + known)
            continue
        pick = sorted(e['w'] or e['r'], key=lambda x: x[1] is None)[0]
        where, msg = pick
        g = next((int(t[:2], 16) for t in where.split() if len(t) == 5 and t[2] == '/'), None)
        town = f' {place[g]}' if g in place else ''
        line = '' if msg is None else f' 「{dq4talk.first_line(rom, msg)[:24]}」'
        print(head + f'[추정] {"쓰는 곳" if e["w"] else "검사하는 곳"} {where}{town}{line}')
    return 0


ENDING = (0x1A, 0x9E74)               # 엔딩 장면 목록의 포인터(1A:$9DE4 가 $69/$6A 에 넣음, 1A:$9E17 이 읽음)
def ending_list(prg):
    """1A:$9E17: 바이트 bit7 이 꺼져 있으면 5바이트 장면(그룹, 순번, X, Y, 시간), 켜져 있으면 4바이트 일행 움직임
    (값 → $0530, 주소 lo·hi, 길이: 그 바이트들을 $7E00 에 복사해 패드 입력으로 씀). FF 로 끝."""
    a, out = rd(prg, *ENDING) | rd(prg, ENDING[0], ENDING[1] + 1) << 8, []
    while (b := rd(prg, ENDING[0], a)) != 0xFF:
        if b & 0x80:
            src, ln = rd(prg, ENDING[0], a + 1) | rd(prg, ENDING[0], a + 2) << 8, rd(prg, ENDING[0], a + 3)
            out.append(('pad', b, src, [rd(prg, ENDING[0], src + i) for i in range(ln)]))
            a += 4
        else:
            out.append(('scene', *(rd(prg, ENDING[0], a + i) for i in range(5))))
            a += 5
    return out


def cmd_ending(prg):
    place = place_names(prg)
    print('== 엔딩 장면 1A:$9E76 (5장 끝: $62A1 bit5 가 켜진 채 그룹 2D 에 들어가면 1A:$B8C2 → 1A:$9BFC)')
    for e in ending_list(prg):
        if e[0] == 'scene':
            _, g, k, x, y, t = e
            when = '밤' if t >= 0x78 else '낮'
            print(f'  맵 {g:02X}/{k:02X} ({x:02X},{y:02X}) {place.get(g, "")}  $62ED={t:02X}({when}) 머묾 {t & 0x7F:02X}')
        else:
            _, b, src, bs = e
            print(f'    일행 움직임 1A:${src:04X} $0530={b:02X}: ' + ' '.join(dq4npcblock.pad_text(x) for x in bs))
    return 0


ENTRY = (0x1D, 0xB8CA)                # 맵 이벤트 표(1D:$B74D = BRK 1D 함수 07): 6바이트, 그룹 FF 로 끝


def entry_table(prg):
    """(그룹, 순번, 셋째 바이트, 장, 넷째 바이트 아래 4비트, 다섯째, 여섯째)."""
    out, a = [], ENTRY[1]
    while (g := rd(prg, ENTRY[0], a)) != 0xFF:
        b = [rd(prg, ENTRY[0], a + i) for i in range(6)]
        out.append((g, b[1], b[2], b[3] >> 4, b[3] & 0x0F, b[4], b[5]))
        a += 6
    return out


def cmd_events(prg, rom):
    print('== 인물 블록의 이벤트 명령(88~8A n) → 1D:$B639 표의 루틴')
    for _, name, g, k, slot, n, j, _ in (u for u in block_uses(prg) if u[0] == 'event'):
        a = event_addr(prg, n)
        msg = near_msg(prg, 0x1D * 0x4000 + (a & 0x3FFF) - 4)
        line = '' if msg is None else f'  {msg:04X} {dq4talk.first_line(rom, msg)[:30]}'
        print(f'{name}{g:02X}/{k:02X} 슬롯 {slot:02X} 블록+{j:02X}  이벤트 {n:02X} → 1D:${a:04X}{line}')
    print('== 맵 이벤트 표 1D:$B8CA (그룹/순번, 장, 셋째 바이트, 넷째 아래 4비트, 다섯째, 여섯째)')
    for g, k, c, ch, lo, x, y in entry_table(prg):
        print(f'{g:02X}/{k:02X} {ch + 1}장  셋째 {c:02X}  넷째 아래 {lo:X}  {x:02X} {y:02X}')
    return 0


def cmd_ops(prg, only):
    for p, n, op, m in flag_ops(prg):
        if only is not None and n != only:
            continue
        bank, base = p // 0x4000, 0xC000 if p // 0x4000 in (0x0F, 0x1F) else 0x8000
        print(f'{bank:02X}:${base + p % 0x4000:04X}  ${FLAGS + n:04X}(번호 {n:02X}) {FLAG_OPS[op]} {m:02X}')
    return 0


def main():
    rom = open(sys.argv[1], 'rb').read()
    prg = ines.prg(rom)
    cmd = sys.argv[2]
    if cmd == 'sram':
        return cmd_sram(prg, open(sys.argv[3], 'rb').read())
    if cmd == 'flags' and '--meaning' in sys.argv:
        return cmd_meaning(prg, dq4text.Rom(rom))
    if cmd == 'flags' and '--xref' in sys.argv:
        rest = [a for a in sys.argv[3:] if not a.startswith('--')]
        return cmd_xref(prg, dq4text.Rom(rom), int(rest[0], 16) if rest else None, '--all' in sys.argv)
    if cmd == 'flags':
        return cmd_flags(open(sys.argv[3], 'rb').read())
    if cmd == 'events':
        return cmd_events(prg, dq4text.Rom(rom))
    if cmd == 'ending':
        return cmd_ending(prg)
    if cmd == 'chapters':
        return cmd_chapters(prg)
    if cmd == 'chars':
        return cmd_chars(prg, sys.argv[4] if len(sys.argv) > 4 and sys.argv[3] == '--compare' else None)
    if cmd == 'places':
        return cmd_places(prg)
    if cmd == 'ops':
        return cmd_ops(prg, int(sys.argv[4], 16) if len(sys.argv) > 4 and sys.argv[3] == '--flag' else None)
    print(__doc__)
    return 2


if __name__ == '__main__':
    sys.exit(main())
