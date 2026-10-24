"""DQ4(FC) 인물 블록(움직임·자동 이벤트 스크립트) 디코더. 형식은 fc/dq4/docs/dq4-npcblock-format.md.

사용:
  python fc/dq4/tools/dq4npcblock.py rom/dq4.nes G K [--night]   맵 (그룹, 순번) 의 인물마다 블록을 명령 단위로
  python fc/dq4/tools/dq4npcblock.py rom/dq4.nes alt              이벤트 목록(1C:$9D0E 표)의 인물 블록
  python fc/dq4/tools/dq4npcblock.py rom/dq4.nes check            롬 전체 블록(맵 목록·이벤트 목록, 블록1·2)을 풀어
                                                   명령 수·못 읽은 명령·블록 밖으로 넘친 명령·점프 대상을 센다
  python fc/dq4/tools/dq4npcblock.py rom/dq4.nes stats            명령마다 쓰인 수
  python fc/dq4/tools/dq4npcblock.py rom/dq4.nes patterns         명령 22 의 일행 움직임 패턴(1C:$8014 표)
  python fc/dq4/tools/dq4npcblock.py rom/dq4.nes trace npcblock.txt   fc/dq4/tools/lua/npcblock.lua 기록을 디코더와 대조

근거 루틴: 1F:$D884(한 명령 실행), 1F:$DEF5(명령 00~30 처리기 표), 1F:$DF57(80~8A), 1F:$DDCD~$DDD6(포인터
4·3·2·1 바이트 넘김), 1F:$DDE3(이 프레임 끝), 1F:$D5F1·$D5FA(슬롯마다 부름), 1C:$9B71(레코드 길이).
"""
import sys

from kr_patch.fc import ines

import dq4map

NPC_BANK, ALT_BANK = 0x05, 0x1C
FLAGS, FLAGS_END = 0x627B, 0x62EE
EVENTS, EVENT_COUNT = (0x1D, 0xB639), 0x8A

# 명령: (길이, 이름, 다음 명령으로 가는지). 길이는 처리기가 포인터를 넘기는 바이트 수(1F:$DDCD 4, $DDD0 3, $DDD3 2,
# $DDD6 1). 「머묾」 은 포인터를 넘기지 않고 이 프레임을 끝내 같은 명령을 다음에 다시 하는 것.
# 31~7F 는 처리기가 00 으로 바꿔 실행한다(1F:$D898).
CMDS = {
    0x00: (1, '멈춤 표시 끔($70E0 bit7) 뒤 쉼'),
    0x01: (1, '멈춤 표시 켬($70E0 bit7) 뒤 쉼'),
    0x02: (1, '아무 방향 한 걸음(되돌아가는 방향은 세 번까지 다시 고름)'),
    0x03: (1, '목표 자리로 한 걸음(닿으면 다음 명령)'),
    0x04: (1, '목표 자리에서 멀어지는 한 걸음'),
    0x05: (1, '오른쪽으로 돎(방향 +1)'),
    0x06: (1, '왼쪽으로 돎(방향 −1)'),
    0x07: (1, '숨음($7020 bit7)'),
    0x08: (1, '숨고 맵에서 뺌(X·Y = 81)'),
    0x09: (1, '깜박이며 사라짐'),
    0x0A: (1, '깜박이며 사라지고 맵에서 뺌'),
    0x0B: (1, '나타남($7020 bit7 끔)'),
    0x0C: (1, '깜박이며 나타남'),
    0x0D: (1, '일행이 걸으면 일행 방향으로 함께 걸음(머묾)'),
    0x0E: (1, '$70E0 bit3 켬'),
    0x0F: (1, '멈춤 표시 켬(쉬지 않음)'),
    0x10: (1, '멈춤 표시 끔(쉬지 않음)'),
    0x11: (1, '간격 1, $70E0 bit6 켬(대화 중에도 움직임)'),
    0x21: (2, '특수 전투 n(BRK 18 함수 01)'),
    0x22: (2, '일행 움직임 패턴 n(1C:$8014 표)'),
    0x23: (2, '방향 = n & 3, n bit7 이 꺼져 있으면 그림 칸 = (n >> 2 & F) + 4($6FE0)'),
    0x24: (3, '목표 자리 (x, y). x bit7 이면 일행'),
    0x25: (3, '자리 옮김 (x, y)'),
    0x26: (3, '메시지 hi:lo'),
    0x27: (4, '[hi:lo] |= m'),
    0x28: (4, '[hi:lo] &= m'),
    0x29: (4, '[hi:lo] = v'),
    0x2A: (1, '멈춤 표시 켜고 쉼(머묾)'),
    0x2B: (1, '아무 방향 한 걸음(머묾)'),
    0x2C: (4, 'BRK 1E 함수 09 (X, A, Y) = 인자 1, 2, 3'),
    0x2D: (2, '범위 n 안에서 아무 방향 한 걸음(머묾)'),
    0x2E: (4, '일행이 (x, y) 에 설 때까지 명령 c'),
    0x2F: (1, '멈춤 표시 끄고 쉼(머묾)'),
    0x30: (2, 'BRK 19 함수 03 (A = n)'),
    0x80: (1, '되돌아감(저장한 주소로)'),
    0x81: (1, '횟수를 하나 줄여 0 이 아니면 되돌아감'),
    0x82: (2, '횟수 n, 다음 명령 주소를 저장'),
    0x83: (2, '상대 점프 d'),
    0x84: (3, '점프 hi:lo'),
    0x85: (3, '부름 hi:lo(돌아올 주소를 저장)'),
    0x86: (3, '갈래 n'),
    0x87: (3, '일행 쪽(또는 반대쪽)을 보고 섬'),
    0x88: (2, '이벤트 n'),
    0x89: (2, '이벤트 n'),
    0x8A: (2, '이벤트 n'),
}
for _c in range(0x12, 0x21):
    CMDS[_c] = (1, f'간격 {_c - 0x11:X}, $70E0 bit6 끔')
STAY = {0x0D, 0x2A, 0x2B, 0x2D, 0x2F}         # 포인터를 넘기지 않고 같은 명령을 되풀이
JUMPS = {0x80, 0x83, 0x84}                    # 다음 바이트로 이어지지 않음(81 은 횟수가 끝나면 이어짐)


PATTERN_PTR = (0x1C, 0x8014)          # 1F:$DAB9: 워드 둘 = 패턴 본문 시작($804E), 패턴마다 길이 바이트 표($802C)
PAD_DIRS = ((0x10, '위'), (0x20, '아래'), (0x40, '왼쪽'), (0x80, '오른쪽'))


def pad_text(b):
    """일행 움직임 바이트(1F:$DB0B): 위 4비트 = 패드 방향($14 bit4~7), 아래 4비트 = 그 입력을 낼 횟수."""
    d = '+'.join(t for m, t in PAD_DIRS if b & m) or '멈춤'
    return f'{d}×{b & 0x0F:X}'


def patterns(prg):
    """명령 22 n 의 일행 움직임 패턴. n 번째 = 본문 시작 + 길이[0..n−1] 합부터 길이[n] 바이트. 길이 표는 본문 바로
    앞에서 끝난다."""
    w = lambda a: rd(prg, PATTERN_PTR[0], a) | rd(prg, PATTERN_PTR[0], a + 1) << 8
    body, lens = w(PATTERN_PTR[1]), w(PATTERN_PTR[1] + 2)
    out, a = [], body
    for i in range(body - lens):
        n = rd(prg, PATTERN_PTR[0], lens + i)
        out.append((a, [rd(prg, PATTERN_PTR[0], a + j) for j in range(n)]))
        a += n
    return out


def rd(prg, bank, a):
    return prg[bank * 0x4000 + (a & 0x3FFF)]


def record_len(prg, bank, a):
    """1C:$9B71: 머리 7바이트(+ F bit4·bit3 이 다 켜져 있으면 덧붙은 바이트) + 블록 (길이 바이트 + 본문) 0~2개."""
    f = rd(prg, bank, a)
    n = 7
    if f & 0x10 and f & 0x08:
        n += (0 if f & 1 else 1) + (0 if f & 2 else 1) + (0 if f & 4 else 2)
    blocks = []
    for bit in (0x10, 0x08):
        if f & bit:
            ln = rd(prg, bank, a + n)
            blocks.append((a + n + 1, ln))
            n += 1 + ln
    return n, blocks


def records(prg, bank, a):
    """a 부터 첫 바이트 00 까지 레코드마다 (주소, F, [(본문 주소, 길이)] 블록1·2)."""
    out = []
    while (f := rd(prg, bank, a)) != 0:
        n, blocks = record_len(prg, bank, a)
        out.append((a, f, blocks))
        a += n
    return out, a + 1


def map_lists(prg):
    """맵 (그룹, 순번) 마다 뱅크 05 의 레코드 목록(dq4map.npc_records 와 같은 순서)."""
    have = {}
    for g, k, *_ in dq4map.maps(prg):
        have.setdefault(g, set()).add(k)
    for g in sorted(have):
        a = rd(prg, NPC_BANK, 0x8000 + 2 * g) | rd(prg, NPC_BANK, 0x8001 + 2 * g) << 8
        for k in range(max(have[g]) + 1):
            recs, a = records(prg, NPC_BANK, a)
            if k in have[g]:
                yield f'{g:02X}/{k:02X}', NPC_BANK, recs


def alt_lists(prg):
    for g, k, m, n, a in dq4map.event_entries(prg):
        yield f'{g:02X}/{k:02X} 목록 1C:${a:04X}', ALT_BANK, records(prg, ALT_BANK, a)[0]


def all_blocks(prg):
    """(목록 이름, 뱅크, 레코드 순번, 블록 번호 1·2, 본문 주소, 길이, 슬롯). 블록1 은 낮(F bit4), 블록2 는 밤(F bit3)
    목록에 들어가는 레코드이고, 슬롯은 그 목록에서 6 부터 센 인물 표 자리(1C:$9798)."""
    for gen in (map_lists(prg), alt_lists(prg)):
        for name, bank, recs in gen:
            slot = {0x10: 6, 0x08: 6}
            for i, (_, f, blocks) in enumerate(recs):
                for j, ((a, ln), bit) in enumerate(zip(blocks, [b for b in (0x10, 0x08) if f & b])):
                    yield name, bank, i, 1 if bit == 0x10 else 2, a, ln, slot[bit]
                for bit in (0x10, 0x08):
                    if f & bit:
                        slot[bit] += 1


def decode(prg, bank, a, ln):
    """본문 [a, a+ln) 을 명령 단위로: (주소, 바이트, 설명, 문제). 문제는 None·'모름'·'넘침'."""
    out, p, end = [], a, a + ln
    while p < end:
        c = rd(prg, bank, p)
        key = 0x00 if 0x31 <= c < 0x80 else c
        if key not in CMDS:
            out.append((p, bytes([c]), '모르는 명령', '모름'))
            p += 1
            continue
        size, text = CMDS[key]
        bs = bytes(rd(prg, bank, p + i) for i in range(size))
        out.append((p, bs, describe(prg, c, bs, p, text), '넘침' if p + size > end else None))
        p += size
    return out


def describe(prg, c, bs, p, text):
    if c in (0x27, 0x28, 0x29):
        a = bs[2] | bs[3] << 8
        where = f'${a:04X}' + (f'(플래그 {a - FLAGS:02X})' if FLAGS <= a <= FLAGS_END else '')
        return {0x27: f'{where} |= {bs[1]:02X}', 0x28: f'{where} &= {bs[1]:02X}', 0x29: f'{where} = {bs[1]:02X}'}[c]
    if c == 0x26:
        return f'메시지 {bs[2]:02X}{bs[1]:02X}'
    if c in (0x88, 0x89, 0x8A):
        n = bs[1]
        if n < EVENT_COUNT:
            t = rd(prg, EVENTS[0], EVENTS[1] + 2 * n) | rd(prg, EVENTS[0], EVENTS[1] + 2 * n + 1) << 8
            return f'이벤트 {n:02X} → 1D:${t:04X}'
        return f'이벤트 {n:02X}(표 밖)'
    if c == 0x24:
        return '목표 = 일행' if bs[1] & 0x80 else f'목표 ({bs[1]:02X},{bs[2]:02X})'
    if c == 0x25:
        return f'자리 ({bs[1]:02X},{bs[2]:02X})'
    if c == 0x23:
        return f'방향 {bs[1] & 3}' + ('' if bs[1] & 0x80 else f', 그림 칸 {(bs[1] >> 2 & 0xF) + 4:X}')
    if c == 0x22:
        pats = patterns(prg)
        body = ' '.join(pad_text(b) for b in pats[bs[1]][1]) if bs[1] < len(pats) else '표 밖'
        return f'일행 움직임 패턴 {bs[1]:02X}: {body}'
    if c in (0x21, 0x30):
        return text.replace(' n', f' {bs[1]:02X}')
    if c == 0x2D:
        return f'범위 {bs[1]:02X} 안에서 아무 방향(머묾)'
    if c == 0x2E:
        return f'일행이 ({bs[1]:02X},{bs[2]:02X}) 에 설 때까지 명령 {bs[3]:02X}'
    if c == 0x2C:
        return f'BRK 1E 함수 09 X={bs[1]:02X} A={bs[2]:02X} Y={bs[3]:02X}'
    if c == 0x82:
        return f'횟수 {bs[1]:02X}, 되돌아갈 자리 저장'
    if c == 0x83:
        d = bs[1] - 0x100 if bs[1] & 0x80 else bs[1]
        return f'상대 점프 {d:+d} → ${(p + d) & 0xFFFF:04X}'
    if c in (0x84, 0x85):
        return ('점프' if c == 0x84 else '부름') + f' ${bs[2]:02X}{bs[1]:02X}'
    if c == 0x86:
        if bs[1] == 0:
            return f'일행이 (0A,1E) 에 서면 상대 점프 +{bs[2]:02X}, 아니면 머묾'
        return f'갈래 {bs[1]:02X}(처리기 표 1F:$DE98)'
    if 0x31 <= c < 0x80:
        return f'{c:02X} = 00: {CMDS[0][1]}'
    return text


def targets(prg, bank, a, cmds):
    """점프·부름 대상 주소(83·84·85·86)."""
    out = []
    for p, bs, _, _ in cmds:
        c = bs[0]
        if c == 0x83:
            out.append((p, (p + (bs[1] - 0x100 if bs[1] & 0x80 else bs[1])) & 0xFFFF))
        elif c in (0x84, 0x85):
            out.append((p, bs[1] | bs[2] << 8))
        elif c == 0x86 and bs[1] == 0:
            out.append((p, p + bs[2]))
    return out


def show_list(prg, name, bank, recs):
    print(f'== {name}')
    for i, (ra, f, blocks) in enumerate(recs):
        for j, (a, ln) in enumerate(blocks):
            print(f'  레코드 {i:02d} {bank:02X}:${ra:04X} F={f:02X} 블록{j + 1} {bank:02X}:${a:04X} 길이 {ln}')
            for p, bs, text, bad in decode(prg, bank, a, ln):
                mark = f'  <{bad}>' if bad else ''
                print(f'    +{p - a:02X} {bs.hex(" "):12s} {text}{mark}')


def cmd_map(prg, g, k):
    for name, bank, recs in map_lists(prg):
        if name == f'{g:02X}/{k:02X}':
            show_list(prg, name, bank, recs)
            return 0
    print('그런 맵이 없음')
    return 1


def cmd_alt(prg):
    for name, bank, recs in alt_lists(prg):
        show_list(prg, name, bank, recs)
    return 0


def cmd_check(prg):
    n_blocks = n_cmds = 0
    unknown, over, outside, inside = [], [], [], 0
    seen = set()
    for name, bank, i, j, a, ln, _ in all_blocks(prg):
        n_blocks += 1
        if (bank, a) in seen:
            continue
        seen.add((bank, a))
        cmds = decode(prg, bank, a, ln)
        n_cmds += len(cmds)
        starts = {p for p, *_ in cmds}
        for p, bs, text, bad in cmds:
            if bad == '모름':
                unknown.append((name, i, j, p, bs))
            elif bad == '넘침':
                over.append((name, i, j, p, bs))
        for p, t in targets(prg, bank, a, cmds):
            if t in starts:
                inside += 1
            else:
                outside.append((name, i, j, p, t))
    print(f'블록 {n_blocks}개(본문 주소가 다른 것 {len(seen)}개), 명령 {n_cmds}개')
    print(f'못 읽은 명령 {len(unknown)}개, 블록 끝을 넘는 명령 {len(over)}개')
    print(f'점프·부름 대상: 블록 안 명령 머리 {inside}곳, 그 밖 {len(outside)}곳')
    for name, i, j, p, bs in unknown + over:
        print(f'  {name} 레코드 {i} 블록{j} ${p:04X} {bs.hex(" ")}')
    for name, i, j, p, t in outside:
        print(f'  {name} 레코드 {i} 블록{j} ${p:04X} → ${t:04X}')
    return 0 if not unknown and not over else 1


def cmd_patterns(prg):
    for i, (a, bs) in enumerate(patterns(prg)):
        print(f'{i:02X} 1C:${a:04X} ' + ' '.join(pad_text(b) for b in bs))
    return 0


def cmd_stats(prg):
    count, seen = {}, set()
    for name, bank, i, j, a, ln, _ in all_blocks(prg):
        if (bank, a) in seen:
            continue
        seen.add((bank, a))
        for p, bs, _, bad in decode(prg, bank, a, ln):
            if not bad:
                count[bs[0]] = count.get(bs[0], 0) + 1
    for c in sorted(count):
        key = 0x00 if 0x31 <= c < 0x80 else c
        print(f'{c:02X}  {count[c]:5d}  {CMDS[key][1]}')
    return 0


def successors(prg, bank, p, saved):
    """p 의 명령 다음에 갈 수 있는 주소들과 새로 저장되는 주소(82·85, 1F:$70A0/$70C0)."""
    c = rd(prg, bank, p)
    key = 0x00 if 0x31 <= c < 0x80 else c
    size = CMDS[key][0]
    arg = [rd(prg, bank, p + i) for i in range(1, size)]
    if c == 0x80:
        return {saved}, saved
    if c == 0x81:
        return {saved, p + 1}, saved
    if c == 0x82:
        return {p + 2}, p + 2
    if c == 0x83:
        return {(p + (arg[0] - 0x100 if arg[0] & 0x80 else arg[0])) & 0xFFFF}, saved
    if c == 0x84:
        return {arg[0] | arg[1] << 8}, saved
    if c == 0x85:
        return {arg[0] | arg[1] << 8}, p + 3
    if c == 0x86:
        return {p + arg[1]}, saved
    return {p + size}, saved


def cmd_trace(prg, path):
    """npcblock.lua 의 기록을 디코더와 맞춘다: 실행된 명령 주소가 모두 디코드한 명령 머리인지, 슬롯마다 다음 명령이
    길이·점프로 예측한 주소인지, 03(목표로 걷기)을 마치고 넘어갈 때 인물이 24 로 정한 목표 칸에 서 있는지."""
    heads = {}
    for name, bank, i, j, a, ln, _ in all_blocks(prg):
        for p, *_ in decode(prg, bank, a, ln):
            heads.setdefault(bank, set()).add(p)
    prev, saved, goal, where = {}, {}, {}, {}
    n = head_ok = step_ok = steps = arrived = arrive_ok = 0
    bad = []
    for line in open(path):
        f = line.split()
        if len(f) == 3 and f[1] == 'map':
            prev, saved, goal = {}, {}, {}   # 맵이 바뀌면 슬롯마다 블록이 새로 실린다
            continue
        if len(f) == 6 and f[2] == 'pos':
            where[int(f[1], 16)] = tuple(int(x, 16) for x in f[3].split(','))
            continue
        if len(f) != 4:
            continue
        slot, (bank, p) = int(f[1], 16), (int(x, 16) for x in f[2].split(':'))
        n += 1
        if p in heads.get(bank, ()):
            head_ok += 1
        else:
            bad.append(f'명령 머리가 아님: {line.strip()}')
        if slot in prev and prev[slot][0] == bank:
            nxt, saved[slot] = successors(prg, bank, prev[slot][1], saved.get(slot))
            if None in nxt and p not in nxt:
                saved[slot] = p           # 세이브스테이트가 고리 안에서 시작해 되돌아갈 주소를 모름: 처음 되돌아간 곳으로 배움
                prev[slot] = (bank, p)
                continue
            steps += 1
            pb, pp = prev[slot]
            if rd(prg, pb, pp) == 0x03 and p == pp + 1 and goal.get(slot):
                arrived += 1
                if where.get(slot) == goal[slot]:
                    arrive_ok += 1
                else:
                    bad.append(f'목표 {goal[slot]} 가 아닌 {where.get(slot)} 에서 03 을 마침: {line.strip()}')
            if p in nxt:
                step_ok += 1
            else:
                bad.append(f'예측 {" ".join(f"${x:04X}" for x in nxt if x is not None)} 과 다름: {line.strip()}')
        if rd(prg, bank, p) == 0x24:
            x = rd(prg, bank, p + 1)
            goal[slot] = None if x & 0x80 else (x, rd(prg, bank, p + 2))
        prev[slot] = (bank, p)
    print(f'기록한 명령 {n}개 중 디코드한 명령 머리 {head_ok}개, 이어진 명령 {steps}번 중 예측과 같은 것 {step_ok}번, '
          f'목표 칸에 닿아 03 을 마친 것 {arrived}번 중 그 칸에 선 것 {arrive_ok}번')
    for b in bad:
        print(' ', b)
    return 0 if not bad else 1


def main():
    rom = open(sys.argv[1], 'rb').read()
    prg = ines.prg(rom)
    cmd = sys.argv[2] if len(sys.argv) > 2 else ''
    if cmd == 'trace':
        return cmd_trace(prg, sys.argv[3])
    if cmd == 'check':
        return cmd_check(prg)
    if cmd == 'stats':
        return cmd_stats(prg)
    if cmd == 'patterns':
        return cmd_patterns(prg)
    if cmd == 'alt':
        return cmd_alt(prg)
    if len(sys.argv) > 3:
        return cmd_map(prg, int(sys.argv[2], 16), int(sys.argv[3], 16))
    print(__doc__)
    return 2


if __name__ == '__main__':
    sys.exit(main())
