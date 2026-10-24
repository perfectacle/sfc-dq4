"""DQ4(FC) 저장 데이터(SRAM)·이벤트 플래그·장 시작 표. 형식은 docs/dq4-save-format.md.

사용:
  python tools/dq4event.py rom/dq4.nes sram end.sram       작업 영역과 모험의 서 3칸: 체크섬, 장, 골드, 일행, 인물 8명
  python tools/dq4event.py rom/dq4.nes flags end.sram      이벤트 플래그 영역 $627B~$62EE 의 0 아닌 바이트
  python tools/dq4event.py rom/dq4.nes chapters            장(1~5) 시작 표: 자리, 선두, 골드, 귀환 자리
  python tools/dq4event.py rom/dq4.nes chars [--compare end.sram]   인물 8명의 첫 레코드(장 시작 루틴이 쓰는 값).
                                                   --compare 는 덤프의 장($615A)에서 초기화되는 인물만 대조
  python tools/dq4event.py rom/dq4.nes places              귀환 자리 표($6290 번호 → 장소·좌표)
  python tools/dq4event.py rom/dq4.nes ops [--flag NN]      롬에서 BRK 플래그 명령(00 NN CB/DB/EB MM) 모양 찾기.
                                                   바이트 모양만 보므로 데이터가 섞인다

근거 루틴: 12:$ACA2(체크섬), 1F:$C8AD(CRC 한 바이트), 12:$ACF8(빈 칸 검사), 12:$8EAE(장 시작 초기화,
BRK 12 함수 17), 1E:$A578(시작 자리), 1E:$A73F(귀환 자리 번호 정하기).
"""
import sys

from kr_patch.fc import ines

import dq4data
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


def cmd_places(prg):
    for i in range(PLACE_COUNT):
        g, k, x, y, d = (rd(prg, PLACES[0], PLACES[1] + 5 * i + j) for j in range(5))
        print(f'{i:02X} {g:02X}/{k:02X} ({x:02X},{y:02X}) 방향 {d & 3}  $AEFE 레코드 {d >> 2:02X}')
    return 0


FLAG_OPS = {0xCB: '켜기 |=', 0xDB: '끄기 &=', 0xEB: '검사 &'}


def flag_ops(prg):
    """(PRG 오프셋, 번호, 명령, 마스크). 1F:$C4AE~$C4EF 가 푸는 BRK 특수 형식."""
    out = []
    for p in range(len(prg) - 3):
        if prg[p] == 0 and prg[p + 2] in FLAG_OPS and prg[p + 1] <= FLAGS_END - FLAGS:
            out.append((p, prg[p + 1], prg[p + 2], prg[p + 3]))
    return out


def cmd_ops(prg, only):
    for p, n, op, m in flag_ops(prg):
        if only is not None and n != only:
            continue
        bank, base = p // 0x4000, 0xC000 if p // 0x4000 in (0x0F, 0x1F) else 0x8000
        print(f'{bank:02X}:${base + p % 0x4000:04X}  ${FLAGS + n:04X}(번호 {n:02X}) {FLAG_OPS[op]} {m:02X}')
    return 0


def main():
    prg = ines.prg(open(sys.argv[1], 'rb').read())
    cmd = sys.argv[2]
    if cmd == 'sram':
        return cmd_sram(prg, open(sys.argv[3], 'rb').read())
    if cmd == 'flags':
        return cmd_flags(open(sys.argv[3], 'rb').read())
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
