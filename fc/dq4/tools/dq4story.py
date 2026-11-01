"""DQ4(FC) 이야기 진행: 플래그를 켜는 장면의 실측, 장마다 진행 순서, 블록 이벤트 루틴의 정적 표.
형식은 fc/dq4/docs/dq4-story-format.md.

사용:
  python fc/dq4/tools/dq4story.py rom/dq4.nes events             인물 블록 이벤트(1D:$B639) 138개가 보는 것과 하는 것
  python fc/dq4/tools/dq4story.py rom/dq4.nes jobs READY OUT     [추정] 플래그를 켜는 곳마다 실험 시나리오(OUT 에 한 줄씩)
  python fc/dq4/tools/dq4story.py rom/dq4.nes run JOBS RUNS [-j N]   시나리오를 MesenCE 로 돌림(환경 변수 MESENCE, LIBDIR)
  python fc/dq4/tools/dq4story.py rom/dq4.nes confirm RUNS... [--json OUT]   실행 기록(RUNS/*/sweep.txt)에서 비트마다 켜고 끈 장면
  python fc/dq4/tools/dq4story.py rom/dq4.nes story [N]          장마다 진행 순서 → 플래그 표(dq4flags.STORY)

READY 는 장마다 조작할 수 있는 세이브스테이트 chN.mss 와 그 SRAM 덤프 chN.sram 이 있는 폴더.
근거 루틴: 1F:$DED8(블록 이벤트 명령) → 1D:$989F → 1D:$B639 표, 1C:$A035(슬롯 숨김), 1C:$A04A(슬롯 옮김),
1F:$C4A1(BRK 플래그 명령). 맵에 들어갈 때 인물을 숨기는 장소별 루틴(1C:$A010)은 dq4shop.py hidden.
"""
import collections
import json
import os
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from kr_patch.fc import ines
from kr_patch.fc.dis6502 import OPS, SIZE

import dq4bank
import dq4block
import dq4event
import dq4field
import dq4flags
import dq4map
import dq4npcblock
import dq4talk
import dq4text

sys.path.append(str(Path(__file__).resolve().parents[3] / 'sfc' / 'dq4' / 'tools'))
import dq4mesen  # noqa: E402

HIDE = 0xA035                      # 슬롯 X+6 을 (80,80) 으로(1C:$A037)
PUT = 0xA04A                       # 슬롯 X+6 을 (A, Y) 로
FLAGS = dq4event.FLAGS


def rd(prg, bank, a):
    return prg[(0x1F if a >= 0xC000 else bank) * 0x4000 + (a & 0x3FFF)]


def scan(prg, bank, start, depth=3):
    """bank 안의 루틴을 갈래·JSR(같은 뱅크)까지 따라가며 보는 것과 하는 것을 모은다(코드 읽기).
    돌려주는 것: {'test': [(n, m)], 'set': [...], 'clear': [...], 'pos': [($44/$45, 값)], 'chapter': [값],
    'msg': [번호], 'battle': [n], 'hide': [슬롯], 'put': [슬롯], 'ev1C': [n], 'night': [값], 'pad'·'dir': 패드($14)·일행 방향($3D)을
    읽음, 'item': [뱅크 10 일행 루틴], 'addrs': 닿은 주소}. 같은 자리를 되풀이하는 고리는 첫 바퀴의 X 만 본다."""
    out = collections.defaultdict(list)
    seen = set()
    todo = [(start, 0, None, None, None)]
    while todo:
        a, d, acc, x, last = todo.pop()
        lo = None
        while 0x8000 <= a < 0xC000 and (a, acc, x) not in seen:
            seen.add((a, acc, x))
            out['addrs'].append(a)
            op = rd(prg, bank, a)
            if op == 0x00:
                b1, b2 = rd(prg, bank, a + 1), rd(prg, bank, a + 2)
                c = dq4bank.call(prg, a, bank)
                k = c['kind']
                if k in ('flag-set', 'flag-clear', 'flag-test'):
                    out[{'flag-set': 'set', 'flag-clear': 'clear', 'flag-test': 'test'}[k]].append((c['flag'] - FLAGS, c['mask']))
                elif k == 'message':
                    out['msg'].append(c['msg'])
                elif (b1, b2) == (0x01, 0x8F) and acc is not None:
                    out['battle'].append(acc)
                elif (b1, b2) == (0x07, 0xCF) and acc is not None:
                    out['ev1C'].append(acc)
                elif b2 == 0x73 and b1 in dq4talk.ITEM_CODES:
                    out['item'].append(b1)
                a += dq4talk.brk_len(b1, b2)
                acc = None
                continue
            if op not in OPS:
                break
            mn, md = OPS[op]
            n = 1 + SIZE[md]
            arg = (rd(prg, bank, a + 1) | (rd(prg, bank, a + 2) << 8 if n == 3 else 0)) if n > 1 else 0
            if mn == 'LDA':
                acc = arg if md == 'imm' else None
                last = arg if md in ('zp', 'abs') else None
            elif mn == 'LDX':
                x = arg if md == 'imm' else None
            if mn == 'LDA' and md == 'abs' and FLAGS <= arg <= dq4event.FLAGS_END:
                out['read'].append(abs_read(prg, bank, a + 3, arg))
            if mn in ('LDA', 'LDX', 'LDY', 'CMP', 'BIT', 'AND', 'ORA') and md in ('zp', 'abs', 'abx', 'aby'):
                w = looks(arg)
                if w:
                    out['look'].append(w)
            if mn == 'LDA' and md == 'zp' and arg in (0x14, 0x3D):
                out['pad' if arg == 0x14 else 'dir'].append(True)
            if mn == 'CMP' and md == 'imm' and last in (0x44, 0x45):
                out['pos'].append((last, arg))
            elif mn == 'CMP' and md == 'imm' and last == 0x615A:
                out['chapter'].append(arg + 1)
            elif mn == 'CMP' and md == 'imm' and last == 0x62ED:
                out['night'].append(arg)
            elif mn == 'STA' and arg == 0x0589:
                lo = acc
            elif mn == 'STA' and arg == 0x058A and lo is not None and acc is not None:
                out['msg'].append(acc << 8 | lo)
            elif mn in dq4talk.A_WRITERS:
                acc = None
            if mn in ('JSR', 'JMP') and md == 'abs':
                if arg == HIDE and x is not None:
                    out['hide'].append(x + 6)
                elif arg == PUT and x is not None:
                    out['put'].append(x + 6)
                elif 0x8000 <= arg < 0xC000:
                    if mn == 'JMP':
                        a = arg
                        continue
                    if d < depth:
                        todo.append((arg, d + 1, None, None, None))
                if mn == 'JMP':
                    break
                acc = x = None
            if mn in ('RTS', 'RTI') or (mn == 'JMP' and md == 'ind'):
                break
            if md == 'rel':
                todo.append(((a + 2 + (arg - 256 if arg & 0x80 else arg)) & 0xFFFF, d, acc, x, last))
            a += n
    return out


NPC_COLS = {0x6F60: 'X', 0x6F80: 'Y', 0x6FA0: '이전 X', 0x6FC0: '이전 Y', 0x6FE0: '그림', 0x7000: '방향', 0x7020: '숨음', 0x7040: '간격', 0x7060: '블록 주소',
            0x7080: '블록 주소', 0x70E0: '상태', 0x7140: '발밑 칸'}


def looks(a):
    """루틴이 읽는 RAM 중 조건으로 쓰일 만한 것의 이름."""
    if 0x6F60 <= a < 0x7200:
        col = a - (a - 0x6F60) % 0x20
        return f'인물 {NPC_COLS.get(col, f"${col:04X}")}'
    if 0x0530 <= a <= 0x0533:
        return '일행 움직임 패턴'
    if a in (0x63, 0x64):
        return '맵'
    if 0x616A <= a <= 0x6177:
        return '일행'
    if a == 0x0527:
        return '메시지 창'
    return None


def abs_read(prg, bank, a, addr):
    """LDA $62xx 뒤의 EOR #m·AND #m·ASL 들로 보는 비트를 짐작한다: (번호, 마스크 또는 None, 뒤집음)."""
    neg, mask, asl = False, None, 0
    for _ in range(6):
        op = rd(prg, bank, a)
        mn, md = OPS.get(op, ('?', 'imp'))
        if mn == 'EOR' and md == 'imm':
            neg = not neg
        elif mn == 'AND' and md == 'imm':
            mask = rd(prg, bank, a + 1)
            break
        elif mn == 'ASL' and md in ('acc', 'imp'):
            asl += 1
        else:
            break
        a += 1 + SIZE[md]
    if mask is None and asl:
        mask = 1 << (8 - asl)
    return addr - FLAGS, mask, neg


def flag_text(fs):
    return ' '.join(f'${FLAGS + n:04X}&{m:02X}' for n, m in dict.fromkeys(fs))


def summary(s):
    parts = []
    if s['pos']:
        xs = sorted({v for a, v in s['pos'] if a == 0x44})
        ys = sorted({v for a, v in s['pos'] if a == 0x45})
        parts.append('자리 ' + ('X ' + ','.join(f'{v:02X}' for v in xs) if xs else '')
                     + (' ' if xs and ys else '') + ('Y ' + ','.join(f'{v:02X}' for v in ys) if ys else ''))
    if s['chapter']:
        parts.append('장 ' + ','.join(str(v) for v in sorted(set(s['chapter']))))
    if s['night']:
        parts.append('시간')
    if s['look']:
        parts.append('읽음 ' + ','.join(dict.fromkeys(s['look'])))
    if s['pad']:
        parts.append('패드')
    if s['dir']:
        parts.append('일행 방향')
    if s['item']:
        parts.append('아이템(' + ','.join({0x2E: '주기', 0x30: '빼기', 0x66: '찾기'}[v] for v in dict.fromkeys(s['item'])) + ')')
    if s['test']:
        parts.append('봄 ' + flag_text(s['test']))
    if s['read']:
        parts.append('플래그 읽음 ' + ' '.join(f'{"!" if neg else ""}${FLAGS + n:04X}' + ('' if m is None else f'&{m:02X}')
                                         for n, m, neg in dict.fromkeys(s['read'])))
    if s['set']:
        parts.append('켬 ' + flag_text(s['set']))
    if s['clear']:
        parts.append('끔 ' + ' '.join(f'${FLAGS + n:04X}&{m:02X}' for n, m in dict.fromkeys(s['clear'])))
    if s['msg']:
        parts.append('메시지 ' + ' '.join(f'{m:04X}' for m in dict.fromkeys(s['msg'])))
    if s['battle']:
        parts.append('전투 ' + ' '.join(f'{v:02X}' for v in dict.fromkeys(s['battle'])))
    if s['ev1C']:
        parts.append('1C 이벤트 ' + ' '.join(f'{v:02X}' for v in dict.fromkeys(s['ev1C'])))
    if s['hide']:
        parts.append('숨김 ' + ' '.join(f'{v:02X}' for v in sorted(set(s['hide']))))
    if s['put']:
        parts.append('옮김 ' + ' '.join(f'{v:02X}' for v in sorted(set(s['put']))))
    return '; '.join(parts) or '-'


def cmd_events(prg, rom):
    users = collections.defaultdict(list)
    for kind, label, g, k, slot, n, *_ in dq4event.block_uses(prg):
        if kind == 'event':
            users[n].append(f'{label}{g:02X}/{k:02X}:{slot:02X}')
    print('번호 주소      쓰는 블록 | 보는 것·하는 것(코드 읽기)')
    for n in range(dq4event.EVENT_COUNT):
        a = dq4event.event_addr(prg, n)
        u = list(dict.fromkeys(users[n]))
        who = ' '.join(u[:3]) + (f' 외 {len(u) - 3}' if len(u) > 3 else '') if u else '(블록에서 안 씀)'
        print(f'{n:02X}   1D:${a:04X} {who} | {summary(scan(prg, 0x1D, a))}')
    return 0


# ---- 실험 시나리오 ----

KEY = {1: 'down', 2: 'down', 3: 'down', 4: 'right', 5: 'down'}   # 장마다 READY 세이브스테이트에서 걸을 수 있는 쪽
# 맵 그룹 → 그 맵의 이야기가 주로 있는 장. 실험할 장의 순서를 정할 때만 쓴다(ルーラ 목록 10:$95EB 의 마을과 1장 탑).
HOME = {0x02: 1, 0x12: 1, 0x30: 1, 0x3A: 1, 0x01: 2, 0x0E: 2, 0x0F: 2, 0x0C: 2, 0x16: 3, 0x05: 3, 0x04: 3, 0x42: 3,
        0x15: 4, 0x17: 4, 0x00: 4, 0x11: 4, 0x38: 4}
PRESS_B = ','.join(['b:4,wait:40'] * 24)    # 대사 넘기기(예/아니오는 「いいえ」)
PRESS_A = ','.join(['a:4,wait:40'] * 30)    # 말 걸기(명령 창 → はなす)와 대사 넘기기(예/아니오는 「はい」)
BATTLE = bytes([0x00, 0x01, 0x8F])          # 특수 전투 18[01]. 시나리오에서는 메모리상 EA 로 바꿔 건너뛴다
GOLD = {0x6157: 0xFF, 0x6158: 0xFF}         # 값을 치르는 대화가 막히지 않게


def skip_battles(prg):
    """뱅크 1C·1D 의 BRK 01 8F 를 모두 NOP 로 바꾸는 PRGPOKE 문자열."""
    out = []
    for b in (0x1C, 0x1D):
        for o in range(b * 0x4000, (b + 1) * 0x4000 - 2):
            if prg[o:o + 3] == BATTLE:
                out.append(f'{o:05X}=EAEAEA')
    return ';'.join(out)


def chapter_order(g):
    h = HOME.get(g)
    return ([h] if h else []) + [c for c in (5, 1, 2, 3, 4) if c != h]


def arrivals(prg):
    """맵마다 들어오는 자리(필드 입구 도착 08:$B7F9, 맵 사이 출구의 도착 칸)."""
    out = collections.defaultdict(list)
    for g, fx, fy, k, x, y, d, fld in dq4field.entrances(prg):
        if k is not None:
            out[g, k].append((x, y, (d or 2) & 3))
    cache = {}
    for g, k, *_ in dq4map.maps(prg):
        try:
            links = dq4block.exit_links(prg, g, k, cache)
        except (KeyError, IndexError, ValueError):
            continue
        for e in links:
            t = e.get('to') or {}
            if 'index' in t and 'x' in t:
                out[t['group'], t['index']].append((t['x'], t['y'], (t.get('dir') or 2) & 3))
    return out


def path_to(tree, pred, conds=()):
    """대화 나무에서 pred 를 만족하는 문장까지 지나는 조건 [(op, 인자, 참이어야 하나)] 하나."""
    for s in tree:
        if pred(s):
            return list(conds)
        if s[0] == 'if':
            _, neg, op, args, then, other = s
            p = path_to(then, pred, conds + ((op, args, not neg),))
            if p is None and other:
                p = path_to(other, pred, conds + ((op, args, neg),))
            if p is not None:
                return p
    return None


def reach(prg, bank, start):
    return set(scan(prg, bank, start, depth=4)['addrs'])


def entries(prg):
    """BRK 플래그 명령이 있는 주소 → 그곳에 닿는 진입점(대화 호출 15, 대화 이벤트 1C, 블록 이벤트 1D)과 시나리오 씨앗."""
    calls = dq4talk.call_sites(prg)
    evc = dq4talk.event_callers(prg)
    bu = dq4event.block_uses(prg)
    ent = [(0x15, a, [('tid', t) for b, t, _ in calls if b == a]) for a in sorted({a for a, *_ in calls})]
    ent += [(0x1C, a, [('tid', int(t, 16)) for t in evc.get(i, ()) if ':' not in t])
            for i, a in enumerate(dq4talk.event_table(prg))]
    ent += [(0x1D, dq4event.event_addr(prg, i), [('block', lab, g, k, s) for kind, lab, g, k, s, v, *_ in bu
                                                  if kind == 'event' and v == i]) for i in range(dq4event.EVENT_COUNT)]
    out = collections.defaultdict(list)
    for bank, a, seeds in ent:
        for x in reach(prg, bank, a):
            out[bank, x].append((a, seeds))
    return out


def unconfirmed(prg):
    """한 비트로 다루는 (번호, 비트) 중 dq4flags.CONFIRMED 에 없는 것과 그 쓰는 곳."""
    rows = dq4event.flag_xref(prg)
    bits = {}
    for n in rows:
        for m, kind, where, msg in rows[n]:
            b = dq4event.bit_of(m, kind)
            if b is not None and b.bit_count() == 1 and kind in dq4event.WRITERS:
                bits.setdefault((n, b), []).append((kind, where, msg))
    return {k: v for k, v in bits.items()
            if k not in dq4event.KNOWN and k not in dq4flags.CONFIRMED and k not in dq4flags.UNUSED}


def cmd_jobs(prg, ready, outpath):
    base = {c: Path(ready, f'ch{c}.sram').read_bytes() for c in range(1, 6)}
    arrive = arrivals(prg)
    talk, who = dq4event.talk_uses(prg)
    brk = entries(prg)
    blocks = {(name, slot): (bank, a, ln) for name, bank, i, j, a, ln, slot in dq4npcblock.all_blocks(prg)}
    jobs, seen = [], set()
    nop = skip_battles(prg)

    def fb(c, n):
        return base[c][FLAGS - 0x6000 + n]

    def list_ok(c, g, k, want, force):
        fl = bytearray(base[c][FLAGS - 0x6000:FLAGS - 0x6000 + 0x74])
        if force:
            fl[force[0]] |= force[1]
        return dq4map.pick_list(prg, g, k, lambda i: fl[i]) == want

    def job(jid, c, g, k, xy, sets, target, env):
        x, y, d = xy
        sets = dict(sets)
        n, b, kind = target
        a = FLAGS + n
        v = sets.get(a, fb(c, n))
        sets[a] = v | b if kind == 'clear' else v & ~b & 0xFF   # 켜는 곳을 보려면 먼저 끄고, 끄는 곳은 먼저 켠다
        jid = f'{jid}-c{c}-t{n:02X}{b:02X}'
        if jid in seen:
            return
        seen.add(jid)
        env = dict(env, PRGPOKE=nop, STATE=f'{ready}/ch{c}.mss', MAP=f'{g:02X}/{k:02X}', X=f'{x:02X}', Y=f'{y:02X}', DIR=str(d),
                   KEY=KEY[c], SET=';'.join(f'{a:04X}={v:02X}' for a, v in sorted(sets.items())))
        jobs.append((jid, env))

    def list_of(label, g, k):
        if '목록' not in label:
            return None, None
        a = int(label.split('$')[1][:4], 16)
        for eg, ek, m, i, aa in dq4map.event_entries(prg):
            if (eg, ek, aa) == (g, k, a):
                return a, (i, m)
        return a, None

    def talk_job(tid, pred, label, target):
        c0 = dq4talk.classify(prg, tid)
        conds = path_to(c0[2], pred) if c0[0] == 'script' else None
        if conds is None or not who.get(tid):
            return
        name, g, k, slot = who[tid][0]
        sets, yes, chs, night, items = {}, True, None, None, []
        for op, args, want in conds:
            if op == 0x1B:
                v = sets.get(FLAGS + args[0])
                sets[FLAGS + args[0]] = (args[1], 0, v) if v is None else v
                cur = sets[FLAGS + args[0]]
                sets[FLAGS + args[0]] = (cur[0] | args[1], cur[1], None) if want else (cur[0], cur[1] | args[1], None)
            elif op == 0x1A:
                sets[FLAGS + args[0]] = ((args[1] ^ 0xFF) if want else args[1], 0xFF, None)
            elif op == 0x05:
                yes = want
            elif op == 0x14:
                night = not want
            elif op == 0x16:
                chs = [args[0]] if want else [x for x in (chs or range(1, 6)) if x != args[0]]
            elif op == 0x11 and want:
                items.append(args[0])
        for c in (chs or chapter_order(g))[:1]:
            s = dict(GOLD)
            lead = base[c][0x16A] & 0x1F
            for i, it in enumerate(items[:4]):
                s[0x6001 + 30 * lead + 0x1A - i] = it
            for a, (on, off, _) in sets.items():
                s[a] = (fb(c, a - FLAGS) | on) & ~off & 0xFF if off != 0xFF else on
            if night is not None:
                s[0x62ED] = 0x90 if night else 0x10
            job(f'talk-{tid:03X}-{label}', c, g, k, (arrive.get((g, k)) or [(0x10, 0x10, 2)])[0], s, target,
                {'PIN': 'auto', 'TID': f'{tid:03X}', 'SEQ': 'a:4,wait:30,a:4,wait:60,' + (PRESS_A if yes else PRESS_B),
                 'TAIL': '60', 'MAXF': '1700'})

    def entry_jobs(jid, g, k, label, cands, target, night=False, tests=()):
        want, force = list_of(label, g, k)
        chs = [c for c in chapter_order(g) if list_ok(c, g, k, want, force)][:3]
        for c in chs:
            s = dict(GOLD)
            if force:
                s[FLAGS + force[0]] = fb(c, force[0]) | force[1]
            if night:
                s[0x62ED] = 0x90
            for i, xy in enumerate(cands[:4]):
                job(f'{jid}-p{i}', c, g, k, xy, s, target, {'SEQ': PRESS_B, 'TAIL': '200', 'MAXF': '1500'})
            if tests:
                # 루틴이 보는 플래그를 모두 켠 변형(그 비트가 켜져 있어야 진행하는 이벤트)
                s2 = dict(s)
                for n, m in tests:
                    s2[FLAGS + n] = s2.get(FLAGS + n, fb(c, n)) | m
                for i, xy in enumerate(cands[:2]):
                    job(f'{jid}-f{i}', c, g, k, xy, s2, target, {'SEQ': PRESS_B, 'TAIL': '200', 'MAXF': '1500'})

    for (n, b), sites in sorted(unconfirmed(prg).items()):
        for kind, where, msg in sites:
            target = (n, b, kind)
            w = where.split()
            if w[0] == '대화':
                op = {'set': 'flag|=', 'clear': 'flag&=', 'store': 'flag='}[kind]
                mask = b if kind != 'clear' else ~b & 0xFF
                talk_job(int(w[1], 16), lambda s, op=op, m=mask: s[0] == op and s[1][0] == n and
                         (s[1][1] == m if op == 'flag&=' else s[1][1] & m), f'f{n:02X}{b:02X}', target)
            elif w[0] == 'BRK':
                bank, addr = int(w[1][:2], 16), int(w[1][4:8], 16)
                for start, seeds in brk.get((bank, addr), []):
                    for sd in seeds:
                        if sd[0] == 'tid':
                            if bank == 0x15:
                                pred = lambda s, a=start: s[0] in ('call', 'call+2') and (s[1][1] << 8 | s[1][0]) == a
                            else:
                                pred = lambda s: s[0] in ('call', 'call+2')
                            talk_job(sd[1], pred, f'{bank:02X}{start:04X}', target)
                        else:
                            _, label, g, k, slot = sd
                            s = scan(prg, 0x1D, start)
                            xs = [v for a, v in s['pos'] if a == 0x44]
                            ys = [v for a, v in s['pos'] if a == 0x45]
                            cands = (arrive.get((g, k)) or [(0x10, 0x10, 2)])[:1]
                            cands += [(x, y, 2) for x in dict.fromkeys(xs) for y in dict.fromkeys(ys)][:3]
                            entry_jobs(f'blk-{g:02X}{k:02X}-{slot:02X}-{start:04X}', g, k, label, cands, target,
                                       tests=[t for t in s['test'] if t[1].bit_count() == 1])
            elif w[0] == '인물':
                rest = where.split('인물 블록 ')[1]
                gk = next(t for t in rest.split() if len(t) == 5 and t[2] == '/')
                g, k = int(gk[:2], 16), int(gk[3:], 16)
                slot = int(rest.split('슬롯 ')[1][:2], 16)
                label = rest if rest.startswith('목록') else ''
                cands = (arrive.get((g, k)) or [(0x10, 0x10, 2)])[:1]
                for (name, sl), (bank, a, ln) in blocks.items():
                    if sl == slot and name.startswith(gk) and ('목록' in name) == bool(label):
                        cands += [(bs[1], bs[2], 2) for p, bs, *_ in dq4npcblock.decode(prg, bank, a, ln) if bs[0] == 0x2E]
                entry_jobs(f'npc-{g:02X}{k:02X}-{slot:02X}', g, k, label, cands, target, night='밤 ' in rest)
    with open(outpath, 'w') as f:
        for jid, env in jobs:
            f.write(jid + '\t' + '\t'.join(f'{a}={v}' for a, v in env.items()) + '\n')
    print(f'시나리오 {len(jobs)}개 → {outpath}', collections.Counter(j.split('-')[0] for j, _ in jobs))
    return 0


def cmd_run(jobsfile, runs, par):
    """시나리오마다 flagsweep.lua(드라이버 warp.lua)를 돌린다. RUNS/<id>/sweep.txt 가 이미 있으면 건너뜀."""
    here = Path(__file__).resolve().parent
    rom = Path('rom/dq4.nes').resolve()
    lines = [ln.rstrip('\n').split('\t') for ln in open(jobsfile) if ln.strip()]

    def go(parts):
        jid, *kv = parts
        out = Path(runs, jid).resolve()
        if (out / 'sweep.txt').exists():
            return
        out.mkdir(parents=True, exist_ok=True)
        env = dict(os.environ, SHOT_DIR=str(out), DRIVER=str(here / 'lua/warp.lua'))
        for x in kv:
            a, v = x.split('=', 1)
            env[a] = str(Path(v).resolve()) if a == 'STATE' else v
        dq4mesen.testrunner(os.environ['MESENCE'], '--nes.ramPowerOnState=AllZeros', str(rom),
                            str(here / 'lua/flagsweep.lua'), env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    with ThreadPoolExecutor(par) as ex:
        list(ex.map(go, lines))
    return 0


# ---- 실행 기록 ----

MAP_LOAD_PCS = {('08', 'B6BA'), ('08', 'B6C3')}     # 맵에 들어갈 때마다 08:$B6xx 가 쓰는 바이트($6289·$628B)


def observations(dirs):
    """RUNS/*/sweep.txt(폴더 여럿) → {(번호, 비트): [증거]}. 증거는 켜짐/꺼짐, 쓴 곳, 시나리오, 장, 맵, 앞뒤 메시지."""
    out = collections.defaultdict(list)
    for runs, jid in sorted((r, j) for r in dirs for j in os.listdir(r)):
        f = Path(runs, jid, 'sweep.txt')
        if not f.exists():
            continue
        m = re.search(r'-c(\d)', jid)
        ch = int(m.group(1)) if m else None
        evs = [(int(p[0]), p[1], p[2:]) for p in (ln.split() for ln in f.read_text(errors='replace').splitlines()) if len(p) > 1]
        mp, tid, msg = None, None, None
        for i, (fr, kind, rest) in enumerate(evs):
            if kind == 'map':
                mp = rest[0]
            elif kind == 'tid':
                tid = rest[0]
            elif kind == 'msg':
                msg = rest[0]
            elif kind == 'w':
                addr = int(rest[0], 16)
                if not FLAGS <= addr <= dq4event.FLAGS_END:
                    continue
                old, new = (int(x, 16) for x in rest[1].split('>'))
                kv = dict(x.split('=', 1) for x in rest[2:])
                if (kv['bank'], kv['pc']) in MAP_LOAD_PCS:
                    continue
                if kv['brk'] != '-':
                    by = 'BRK ' + kv['brk']
                elif kv['slot'] != '-':
                    by = f'블록 슬롯 {kv["slot"]}'
                elif kv['bank'] == '15':
                    by = f'대화 {tid}'
                else:
                    by = f'PC {kv["bank"]}:{kv["pc"]}'
                nxt = next((r[0] for _, k2, r in evs[i:] if k2 == 'msg'), None)
                for bit in range(8):
                    b = 1 << bit
                    if (new ^ old) & b:
                        out[addr - FLAGS, b].append({'dir': 'set' if new & b else 'clear', 'by': by, 'run': jid, 'ch': ch,
                                                     'map': mp, 'msg': msg, 'next': nxt, 'frame': fr})
    return out


def cmd_confirm(prg, rom, dirs, as_json=None):
    obs = observations(dirs)
    if as_json:
        json.dump({f'{n:02X}:{b:02X}': v for (n, b), v in obs.items()}, open(as_json, 'w'), ensure_ascii=False)
    todo = unconfirmed(prg)
    names = dq4event.place_names(prg)
    got = 0
    print('번호 비트 주소     켠 횟수  쓴 곳 | 장 맵 앞 메시지 → 뒤 메시지')
    for (n, b), es in sorted(obs.items()):
        sets = [e for e in es if e['dir'] == 'set']
        if not sets:
            continue
        mark = '*' if (n, b) in todo else ' '
        got += mark == '*'
        e = sets[0]
        g = int(e['map'][:2], 16) if e['map'] else None
        line = ' '.join(f'{x} {dq4talk.first_line(rom, int(x, 16))[:20]}' for x in (e['msg'], e['next']) if x)
        print(f'{mark}{n:02X}   {b:02X}   ${FLAGS + n:04X} {len(sets):4d}  {e["by"]} | {e["ch"]}장 {e["map"]} '
              f'{names.get(g, "")} {line}  [{e["run"]}]')
    print(f'남은 [추정] {len(todo)}개 중 켜는 장면을 본 것 {got}개(* 표시)')
    return 0


def cmd_story(prg, rom, only=None):
    for ch, rows in dq4flags.STORY.items():
        if only and ch != only:
            continue
        print(f'== {ch}장')
        for i, (what, bits) in enumerate(rows, 1):
            fl = ' '.join(f'${FLAGS + n:04X}&{b:02X}' for n, b in bits)
            print(f'{i:2d}. {what}  {fl}')
    return 0


def main():
    rom = open(sys.argv[1], 'rb').read()
    prg = ines.prg(rom)
    cmd, rest = sys.argv[2], sys.argv[3:]
    if cmd == 'events':
        return cmd_events(prg, dq4text.Rom(rom))
    if cmd == 'jobs':
        return cmd_jobs(prg, rest[0], rest[1])
    if cmd == 'run':
        par = int(rest[rest.index('-j') + 1]) if '-j' in rest else 6
        return cmd_run(rest[0], rest[1], par)
    if cmd == 'confirm':
        js = rest[rest.index('--json') + 1] if '--json' in rest else None
        return cmd_confirm(prg, dq4text.Rom(rom), [r for r in rest if not r.startswith('--') and r != js], js)
    if cmd == 'story':
        return cmd_story(prg, dq4text.Rom(rom), int(rest[0]) if rest else None)
    print(__doc__)
    return 2


if __name__ == '__main__':
    sys.exit(main())
