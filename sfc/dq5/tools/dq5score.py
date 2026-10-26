"""DQ5(SFC) 곡·효과음 시퀀스를 악보로: 다시 쌀 수 있는 글(.txt), MIDI(.mid), MusicXML(.musicxml).
형식은 sfc/dq5/docs/dq5-sound-format.md 의 「시퀀스 형식」·「악보 내보내기」. 롬만 읽는다(에뮬레이터·세이브스테이트 없음).

시퀀스 0x47개 전부를 낸다. 곡(00~31)은 <번호>(곡 변수 0)와 갈래가 있으면 <번호>-<갈래>, 효과음(32~)은 갈래마다
<번호>-<갈래> 다(dq5spcfile.py 와 같은 이름). 결과는 롬에서 나온 자료라 커밋하지 않는다(비공개 에셋 저장소로).

  python sfc/dq5/tools/dq5score.py rom/dq5.sfc --out work/sound            # songs/·sfx/ 에 .txt·.mid·.musicxml, index.json 에 score
  python sfc/dq5/tools/dq5score.py rom/dq5.sfc --out work/sound --only 02,33
  python sfc/dq5/tools/dq5score.py rom/dq5.sfc --kon dspw.txt --seq 02 --start 500   # KON 기록과 음표 시각·음 차이 견주기

연주 규칙(드라이버를 따름):
  틱  드라이버 1틱 = MIDI 1틱, 4분음표 = 48틱. 템포 바이트 t 는 200Hz 타이머마다 t 를 더해 250 을 넘을 때 1틱(146C)이라
      1초 = 0.8t 틱, 곧 BPM = t. 명령 EB 가 바꾼다.
  음  음 번호 n + 조옮김(FA) + 23 이 MIDI 음(n = 25h → 가운데 C). 샘플 머리의 음높이는 샘플마다 음 번호의 뜻을 맞추는
      값이라 더하지 않는다(더하면 동시에 울리는 음끼리의 불협 음정이 30곡 평균 0.21 → 0.28 로 늘었다). 절대 옥타브는 약속값이다.
      잡음(E3) 트랙은 음 번호 하위 5비트(잡음 주파수)를 36 에 더한 음으로 둔다.
  길이  붙임(4F)은 앞 음에 이어 하나의 음으로 친다. 소리 길이는 길이 비율(A0~B5·EC, 처음 CC): 00 이면 길이 그대로,
      FE 면 길이 - 1, 나머지는 길이 x 비율 / 256(15A1). 따르기(F1·F2)는 앞 트랙의 길이·비율을 가져온다.
  되풀이  DB·DC·F4·F5·F8·F9 는 펼친다. 뒤로 가는 점프(EA)는 끝없는 되풀이라 트랙마다 LOOPS 번째(기본 2) 되돌아갈 때 그 트랙을 멈추고,
      모든 트랙이 멈추거나 끝(FF)난 틱에서 곡을 끝낸다.
  곡 변수  E0 은 갈래 값과 같으면 뛰고, 처음 읽은 틱이 끝나면 0 이 된다(14BC).
  MusicXML 은 4/4 박자로 보고 마디를 자른다(롬에 박자 정보는 없다). 음 길이는 온음표~128분 셋잇단을 이어 붙여 나타낸다.
"""
import argparse
import json
import math
import os
import struct
import sys
from xml.sax.saxutils import escape

sys.path.insert(0, os.path.dirname(__file__))
from dq5map import Rom, lorom  # noqa: E402
from dq5spc import body, sequences, song_sets  # noqa: E402
from dq5song import GATES, header, listing, step  # noqa: E402

PPQ = 48
SFX_FROM = 0x32
GATE0 = 0xCC                      # 1273~12AE: 곡을 틀 때 비율 CC
LOOPS = 2
MAX_TICKS = 40000
MIDI_BASE = 23
NOISE_BASE = 36


def variants(seq):
    """흐름을 따라 닿는 E0 의 값으로 갈래 수(가장 큰 값 + 1)."""
    from dq5song import walk
    vals = set()
    for st in header(seq)[1]:
        seen, _ = walk(seq, st)
        vals |= {seq[pc + 3] for pc in seen if seq[pc] == 0xE0}
    return max(vals) + 1 if vals else 1


def targets(rom):
    """[(시퀀스, 갈래 또는 None, 줄기, 폴더)] 시퀀스 0x47개 전부."""
    out = []
    for n, a, ln in sequences(rom):
        seq = bytes(body(rom, a, ln))
        var = variants(seq)
        if n < SFX_FROM:
            out.append((n, None, f'{n:02X}', 'songs'))
            out += [(n, x, f'{n:02X}-{x:02X}', 'songs') for x in range(1, var)]
        else:
            out += [(n, x, f'{n:02X}-{x:02X}', 'sfx') for x in range(var)]
    return out


def sound_len(dur, gate):
    if gate == 0:
        return dur
    if gate == 0xFE:
        return max(1, dur - 1)
    return max(1, dur * gate // 256)


class Voice:
    def __init__(self, pc):
        self.pc, self.wait, self.dur, self.gate = pc, 1, 0, GATE0
        self.transpose, self.follow, self.instrument, self.noise = 0, False, 0, False
        self.c1 = self.c2 = 0
        self.stack, self.notes, self.ctl = [], [], []
        self.done, self.loops, self.stop_tick = False, 0, None
        self.last = None                  # 이어 붙일 수 있는 마지막 음(쉼 뒤면 None)
        self.strikes, self.hold = [], False  # KON 을 낸 (틱, 음 번호), 앞 음을 비율 00 으로 읽었는지
        self.env, self.fine, self.slide, self.echo = None, 0, None, False


def perform(seq, flag=0, loops=LOOPS, max_ticks=MAX_TICKS):
    """끝 틱을 먼저 정하고(트랙마다 loops 번째로 되돌아가는 틱의 가장 늦은 것), 모든 트랙을 그 틱까지 다시 연주한다."""
    first = _perform(seq, flag, loops, max_ticks)
    if not first['looped']:
        return first
    return _perform(seq, flag, None, first['end'])


def _perform(seq, flag, loops, max_ticks):
    """{'tempo': [(틱, 템포)], 'tracks': [{'notes': [...], 'ctl': [...]}], 'end': 끝 틱, 'looped': bool}.
    음은 {'tick','len','sound','n','instrument','noise'}(n 은 조옮김을 더한 음 번호), ctl 은 (틱, 'volume'|'pan', 값)."""
    tempo0, offs = header(seq)
    tempos = [(0, tempo0)]
    vs = [Voice(o) for o in offs]
    tick = 0
    for tick in range(max_ticks):
        if all(v.done or v.stop_tick is not None for v in vs):
            break
        flag_read = False
        for i, v in enumerate(vs):
            if v.done or v.stop_tick is not None:
                continue
            v.wait -= 1
            guard = 0
            while v.wait == 0 and not v.done and v.stop_tick is None and guard < 5000:
                guard += 1
                if not 0 <= v.pc < len(seq):
                    v.done = True
                    break
                b = seq[v.pc]
                nxt, _, target, _ = step(seq, v.pc)
                if b < 0xA0:
                    if v.follow and i > 0:
                        v.dur, v.gate = vs[i - 1].dur, vs[i - 1].gate
                    n = b - 0x50 if b >= 0x50 else b
                    if b >= 0x50:
                        v.dur = seq[v.pc + 1]
                    dur = v.dur or 0x100
                    # 1593: 앞 음을 비율 00 으로 읽었으면(15 = FF) KON 없이 음높이만 바뀜. 붙임도 다시 친다
                    if n and not v.hold:
                        v.strikes.append((tick, (n if n != 0x4F else (v.last or {}).get('n', 0) - v.transpose) + v.transpose))
                    v.hold = n != 0 and v.gate == 0     # 쉼 뒤의 음은 늘 다시 침(0A 트랙 6 의 KON 으로 확인)
                    if n == 0:
                        v.last = None
                    elif n == 0x4F:
                        if v.last is not None:
                            v.last['sound'] = v.last['len'] + sound_len(dur, v.gate)
                            v.last['len'] += dur
                    else:
                        v.last = {'tick': tick, 'len': dur, 'sound': sound_len(dur, v.gate), 'n': n + v.transpose,
                                  'instrument': v.instrument, 'noise': v.noise, 'env': v.env, 'fine': v.fine,
                                  'slide': v.slide}
                        v.slide = None
                        v.notes.append(v.last)
                    v.wait = dur
                elif b == 0xFF:
                    v.done = True
                elif b == 0xF0:
                    v.instrument = seq[v.pc + 1]
                elif b in (0xE3, 0xE4):
                    v.noise = b == 0xE3
                elif b == 0xFA:
                    a = seq[v.pc + 1]
                    v.transpose = a - 256 if a >= 0x80 else a
                elif b in (0xF1, 0xF2):
                    v.follow = True
                elif b == 0xF3:
                    v.follow = False
                elif 0xA0 <= b < 0xB6:
                    v.gate = GATES[b - 0xA0]
                elif b == 0xEC:
                    v.gate = seq[v.pc + 1]
                elif b == 0xEB:
                    tempos.append((tick, seq[v.pc + 1]))
                elif b == 0xE2:
                    v.env = None if seq[v.pc + 1] == 0xFF else seq[v.pc + 1]
                elif b == 0xE9:
                    a = seq[v.pc + 1]
                    v.fine = a - 256 if a >= 0x80 else a
                elif b == 0xFB:
                    a = seq[v.pc + 1]
                    v.slide = (a - 256 if a >= 0x80 else a, seq[v.pc + 2] or 0x100)
                elif b in (0xFC, 0xFD):
                    v.ctl.append((tick, 'echo', b == 0xFC))
                elif b == 0xED:
                    v.ctl.append((tick, 'volume', seq[v.pc + 1]))
                elif b == 0xEE:
                    a = seq[v.pc + 1]
                    v.ctl.append((tick, 'pan', a - 256 if a >= 0x80 else a))
                elif b == 0xDC:
                    v.c1 = (v.c1 or 2) - 1
                    nxt = target if v.c1 else nxt
                elif b == 0xDB:
                    nxt = target if v.c1 else nxt
                elif b in (0xF4, 0xF5):
                    v.c2 = (v.c2 or (2 if b == 0xF4 else seq[v.pc + 1])) - 1
                    nxt = target if v.c2 else nxt
                elif b == 0xE0:
                    nxt = target if seq[v.pc + 3] == flag else nxt
                    flag_read = True
                elif b == 0xEA:
                    if target <= v.pc and loops is not None:
                        v.loops += 1
                        if v.loops >= loops:
                            v.stop_tick = tick
                            break
                    nxt = target
                elif b == 0xF8:
                    v.stack.append(nxt)
                    nxt = target
                elif b == 0xF9 and v.stack:
                    nxt = v.stack.pop()
                v.pc = nxt
        if flag_read:
            flag = 0
    ends = [v.stop_tick if v.stop_tick is not None else
            max([nt['tick'] + nt['len'] for nt in v.notes], default=0) for v in vs]
    end = max(ends, default=0)
    looped = any(v.stop_tick is not None for v in vs)
    if looped:
        end = max(v.stop_tick for v in vs if v.stop_tick is not None)
    elif loops is None:
        end, looped = max_ticks, True
    for v in vs:
        v.notes = [nt for nt in v.notes if nt['tick'] < end]
        for nt in v.notes:
            nt['len'] = min(nt['len'], end - nt['tick'])
            nt['sound'] = min(nt['sound'], nt['len'])
    return {'tempo': [t for t in tempos if t[0] < max(end, 1)], 'end': end, 'looped': looped,
            'tracks': [{'notes': v.notes, 'ctl': [c for c in v.ctl if c[0] < max(end, 1)],
                        'strikes': [k for k in v.strikes if k[0] < max(end, 1)]} for v in vs]}


def instrument_tunes(rom, n):
    """[(샘플 번호, 0)] 곡 묶음 n 의 악기 순서대로(F0 i → i 번째 샘플)."""
    return [(s, 0) for s in song_sets(rom)[n][2]]


def midi_pitch(note, tunes=None):
    if note['noise']:
        return NOISE_BASE + (note['n'] & 0x1F)
    return max(0, min(127, note['n'] + MIDI_BASE))


# ---- 음높이 엔벨로프(E2)·미세 조정(E9)·미끄럼(FB) ----

ENV_PTRS = 0x2BC663              # SPC 08D4: 엔벨로프 표 포인터(SPC 주소). 08D4~09DF 가 롬에 그대로 있음
ENV_COUNT = 7                    # 시퀀스가 쓰는 표는 00~06
BEND_RANGE = 12                  # MIDI 피치 벤드 ±12 반음(RPN 0)
FINE_DIV = 128                   # 미세 음높이 128 = 1 반음


def env_tables(rom):
    """[[(틱, 미세 음높이)]] 의 원본 바이트. 표는 [되돌 자리][돌아갈 자리] 뒤 [미세 음높이][틱] 쌍, 80 이 끝."""
    base = lorom(ENV_PTRS) - 0x08D4
    out = []
    for i in range(ENV_COUNT):
        o = base + (rom.d[lorom(ENV_PTRS) + i * 2] | rom.d[lorom(ENV_PTRS) + i * 2 + 1] << 8)
        out.append(bytes(rom.d[o:o + 0x60]))
    return out


def env_steps(table, length):
    """[(음 시작에서의 틱, 미세 음높이)]. 읽는 자리가 「되돌 자리」에 닿으면 「돌아갈 자리」로 간다(1F04)."""
    out, p, t, guard = [], 2, 0, 0
    while t < length and guard < 4096:
        guard += 1
        if p == table[0]:
            p = table[1]
        if p + 1 >= len(table) or table[p] == 0x80:
            break
        f = table[p] - 256 if table[p] >= 0x80 else table[p]
        out.append((t, f))
        t += table[p + 1] or 0x100
        p += 2
    return out


def bend_curve(note, envs):
    """[(음 시작에서의 틱, 반음)] 소리 나는 동안의 음높이 차. 미세 음높이(8D, E9·E2 가 씀) 1 = 1/128 반음:
    곡 0D 트랙 1(E2 04, 피치 3375)에서 표 값 v 마다 피치가 1.5v 씩 바뀌었다(12 → +18 = 0.092 반음)."""
    length = note['sound']
    env = env_steps(envs[note['env']], length) if note.get('env') is not None and note['env'] < len(envs) else []
    out, last = [], None
    for k in range(length):
        e = [f for t, f in env if t <= k]
        semi = (note.get('fine', 0) + (e[-1] if e else 0)) / FINE_DIV
        if note.get('slide'):
            st, tk = note['slide']
            semi += st * min(k, tk) / tk
        if semi != last:
            out.append((k, semi))
            last = semi
    return out


# ---- MIDI ----

def _vlq(v):
    out = [v & 0x7F]
    v >>= 7
    while v:
        out.insert(0, 0x80 | (v & 0x7F))
        v >>= 7
    return bytes(out)


def _track(events):
    """events: [(틱, 바이트)] → MTrk."""
    data, last = bytearray(), 0
    for t, ev in sorted(events, key=lambda e: e[0]):
        data += _vlq(t - last) + ev
        last = t
    data += b'\x00\xff\x2f\x00'
    return b'MTrk' + struct.pack('>I', len(data)) + bytes(data)


def _bend(ch, semi):
    v = max(0, min(16383, 8192 + round(semi * 8192 / BEND_RANGE)))
    return bytes([0xE0 | ch, v & 0x7F, v >> 7])


def to_midi(perf, tunes, title, envs=(), beats=4):
    trks = []
    meta = [(0, b'\xff\x03' + _vlq(len(title.encode())) + title.encode())]
    for t, tempo in perf['tempo']:
        us = round(60_000_000 / max(tempo, 1))
        meta.append((t, b'\xff\x51\x03' + us.to_bytes(3, 'big')))
    meta.append((0, b'\xff\x58\x04' + bytes([beats]) + b'\x02\x18\x08'))
    trks.append(_track(meta))
    for i, tr in enumerate(perf['tracks']):
        ch = i if i < 9 else i + 1
        ev = []
        name = f'track {i}'
        ev.append((0, b'\xff\x03' + _vlq(len(name)) + name.encode()))
        # RPN 0: 피치 벤드 범위 ±BEND_RANGE 반음
        ev += [(0, bytes([0xB0 | ch, 101, 0])), (0, bytes([0xB0 | ch, 100, 0])), (0, bytes([0xB0 | ch, 6, BEND_RANGE])),
               (0, bytes([0xB0 | ch, 38, 0])), (0, bytes([0xB0 | ch, 91, 0]))]
        prog, bent = None, False
        for c in tr['ctl']:
            if c[1] == 'volume':
                ev.append((c[0], bytes([0xB0 | ch, 7, min(127, c[2] >> 1)])))
            elif c[1] == 'echo':
                ev.append((c[0], bytes([0xB0 | ch, 91, 100 if c[2] else 0])))
            else:
                ev.append((c[0], bytes([0xB0 | ch, 10, max(0, min(127, 64 + c[2] // 2))])))
        for nt in tr['notes']:
            s = tunes[nt['instrument']][0] if nt['instrument'] < len(tunes) else nt['instrument']
            if s != prog:
                ev.append((nt['tick'], bytes([0xC0 | ch, s & 0x7F])))
                prog = s
            p = midi_pitch(nt, tunes)
            curve = [] if nt['noise'] else bend_curve(nt, envs)
            if bent and (not curve or curve[0] != (0, 0.0)):
                ev.append((nt['tick'], _bend(ch, 0.0)))
                bent = False
            for k, semi in curve:
                if k == 0 and semi == 0 and not bent:
                    continue
                ev.append((nt['tick'] + k, _bend(ch, semi)))
                bent = semi != 0
            ev.append((nt['tick'], bytes([0x90 | ch, p, 100])))
            ev.append((nt['tick'] + nt['sound'], bytes([0x80 | ch, p, 0])))
        # 같은 틱이면 끄기 → 벤드·CC → 켜기
        ev.sort(key=lambda e: (e[0], {0xF0: -1, 0x80: 0, 0xE0: 1, 0xB0: 1, 0xC0: 1}.get(e[1][0] & 0xF0, 2)))
        trks.append(_track(ev))
    return b'MThd' + struct.pack('>IHHH', 6, 1, len(trks), PPQ) + b''.join(trks)


# ---- MusicXML ----

MEASURE = PPQ * 4
# (틱, 음표 이름, 점, 셋잇단). 128분 셋잇단 = 1틱
DURS = [(192, 'whole', 0, 0), (144, 'half', 1, 0), (96, 'half', 0, 0), (72, 'quarter', 1, 0), (48, 'quarter', 0, 0),
        (36, 'eighth', 1, 0), (32, 'half', 0, 1), (24, 'eighth', 0, 0), (18, '16th', 1, 0), (16, 'quarter', 0, 1),
        (12, '16th', 0, 0), (9, '32nd', 1, 0), (8, 'eighth', 0, 1), (6, '32nd', 0, 0), (4, '16th', 0, 1),
        (3, '64th', 0, 0), (2, '32nd', 0, 1), (1, '64th', 0, 1)]
STEPS = ['C', 'C', 'D', 'D', 'E', 'F', 'F', 'G', 'G', 'A', 'A', 'B']
ALTER = [0, 1, 0, 1, 0, 0, 1, 0, 1, 0, 1, 0]


def split(ticks):
    out = []
    for t, *rest in DURS:
        while ticks >= t:
            out.append((t, *rest))
            ticks -= t
    return out


def _note_xml(dur, pitch, tie_start, tie_stop):
    t, typ, dot, trip = dur
    x = ['<note>']
    if pitch is None:
        x.append('<rest/>')
    else:
        x.append(f'<pitch><step>{STEPS[pitch % 12]}</step>' + (f'<alter>{ALTER[pitch % 12]}</alter>' if ALTER[pitch % 12] else '')
                 + f'<octave>{pitch // 12 - 1}</octave></pitch>')
    x.append(f'<duration>{t}</duration>')
    if tie_stop:
        x.append('<tie type="stop"/>')
    if tie_start:
        x.append('<tie type="start"/>')
    x.append(f'<voice>1</voice><type>{typ}</type>' + ('<dot/>' * dot))
    if trip:
        x.append('<time-modification><actual-notes>3</actual-notes><normal-notes>2</normal-notes></time-modification>')
    if pitch is not None and (tie_start or tie_stop):
        x.append('<notations>' + ('<tied type="stop"/>' if tie_stop else '') + ('<tied type="start"/>' if tie_start else '')
                 + '</notations>')
    x.append('</note>')
    return ''.join(x)


def guess_meter(perf):
    """(박, 마디 틱, 못갖춘마디 틱) 추정. 롬에 박자 정보가 없어, 길이 24틱 이상 음(잡음 빼고)의 길이를 마디 첫 박에 놓인
    만큼 더한 비율 x 박 수로 3/4·4/4 를 견준다. 3/4 은 그 값이 1.3 이상이고 4/4 의 1.2배를 넘을 때만, 못갖춘마디는 0 보다
    1.2배 넘게 나을 때만 고른다."""
    notes = [nt for tr in perf['tracks'] for nt in tr['notes'] if not nt['noise'] and nt['len'] >= 24]
    tot = sum(nt['len'] for nt in notes) or 1

    def score(beats, bar, c):
        return sum(nt['len'] for nt in notes if (nt['tick'] - c) % bar == 0) / tot * beats
    best = {}
    for beats, bar in ((3, 144), (4, 192)):
        r0 = score(beats, bar, 0)
        rc, c = max((score(beats, bar, c), c) for c in range(0, bar, 12))
        best[beats] = (rc, c) if rc > 1.2 * r0 and rc > r0 else (r0, 0)
    beats = 3 if best[3][0] >= 1.3 and best[3][0] > 1.2 * best[4][0] else 4
    return beats, beats * PPQ, best[beats][1]


def to_musicxml(perf, tunes, title, meter=None):
    beats, bar, pickup = meter or (4, MEASURE, 0)
    end = perf['end']
    bounds = ([0] if pickup else []) + list(range(pickup, max(end, 1) + bar, bar))
    if bounds[-1] < end:
        bounds.append(bounds[-1] + bar)
    spans = [(a, b) for a, b in zip(bounds, bounds[1:])]
    total = spans[-1][1]
    parts, plist = [], []
    tempo_at = {t: v for t, v in perf['tempo']}
    for i, tr in enumerate(perf['tracks']):
        pid = f'P{i + 1}'
        plist.append(f'<score-part id="{pid}"><part-name>track {i}</part-name></score-part>')
        # (시작, 길이, 음) 을 쉼으로 채운 줄로
        segs, pos = [], 0
        for nt in tr['notes']:
            if nt['tick'] > pos:
                segs.append((pos, nt['tick'] - pos, None))
            ln = nt['len']
            nxt = nt['tick'] + ln
            segs.append((nt['tick'], ln, midi_pitch(nt, tunes)))
            pos = nxt
        if pos < total:
            segs.append((pos, total - pos, None))
        xs = []
        for m, (a, b) in enumerate(spans):
            num = m if pickup else m + 1
            x = [f'<measure number="{num}"' + (' implicit="yes">' if pickup and m == 0 else '>')]
            if m == 0:
                x.append(f'<attributes><divisions>{PPQ}</divisions><key><fifths>0</fifths></key>'
                         f'<time><beats>{beats}</beats><beat-type>4</beat-type></time><clef><sign>G</sign><line>2</line></clef>'
                         '</attributes>')
            if i == 0:
                for t, v in sorted(tempo_at.items()):
                    if a <= t < b:
                        x.append(f'<direction placement="above"><direction-type><metronome><beat-unit>quarter</beat-unit>'
                                 f'<per-minute>{v}</per-minute></metronome></direction-type><sound tempo="{v}"/></direction>')
            for s, ln, p in segs:
                lo, hi = max(s, a), min(s + ln, b)
                if lo >= hi:
                    continue
                parts_d = split(hi - lo)
                for k, d in enumerate(parts_d):
                    first = lo == s and k == 0
                    last = hi == s + ln and k == len(parts_d) - 1
                    x.append(_note_xml(d, p, p is not None and not last, p is not None and not first))
            x.append('</measure>')
            xs.append(''.join(x))
        parts.append(f'<part id="{pid}">' + ''.join(xs) + '</part>')
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 4.0 Partwise//EN" '
            '"http://www.musicxml.org/dtds/partwise.dtd">\n'
            f'<score-partwise version="4.0"><work><work-title>{escape(title)}</work-title></work>'
            f'<part-list>{"".join(plist)}</part-list>{"".join(parts)}</score-partwise>\n')


# ---- SVG(시간 비례 오선 악보) ----

LETTER = [0, 0, 1, 1, 2, 3, 3, 4, 4, 5, 5, 6]     # 반음 → 음이름 칸(C=0 … B=6)
SVG_X, SVG_BARS, SVG_LINE = 1.0, 4, 8             # 1틱 = 1px, 한 줄 마디 수, 오선 간격


def to_svg(perf, title, meter=None):
    """마디선·음표 머리·올림표·기둥·꼬리를 그리고 음 길이를 가는 가로줄로 보이는 시간 비례 악보. 트랙마다 한 오선,
    마디 SVG_BARS 개씩 줄을 바꾼다. 음 높이가 낮은 트랙(가운데 값 < 60)은 낮은음자리표."""
    beats, bar, pickup = meter or (4, MEASURE, 0)
    tracks = [tr for tr in perf['tracks']]
    end = max(perf['end'], 1)
    bounds = ([0] if pickup else []) + list(range(pickup, end + bar, bar))
    if bounds[-1] < end:
        bounds.append(bounds[-1] + bar)
    spans = list(zip(bounds, bounds[1:]))
    rows = [spans[i:i + SVG_BARS] for i in range(0, len(spans), SVG_BARS)]
    staff_h, gap, left = SVG_LINE * 4, 46, 60
    sys_h = len(tracks) * (staff_h + gap) + 24
    width = left + int(bar * SVG_BARS * SVG_X) + 20
    height = 50 + len(rows) * sys_h
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
           'font-family="sans-serif">', f'<rect width="{width}" height="{height}" fill="white"/>',
           f'<text x="{left}" y="22" font-size="15">{escape(title)}</text>',
           f'<text x="{left}" y="40" font-size="11" fill="#555">{beats}/4(추정) ♩={perf["tempo"][0][1]}  1px = 1틱</text>']
    clefs = []
    for tr in tracks:
        ps = sorted(midi_pitch(nt) for nt in tr['notes'] if not nt['noise'])
        clefs.append('F' if ps and ps[len(ps) // 2] < 60 else 'G')
    for r, row in enumerate(rows):
        y0 = 50 + r * sys_h
        a0 = row[0][0]
        for i, tr in enumerate(tracks):
            top = y0 + i * (staff_h + gap) + 16
            bottom = top + staff_h
            x1 = left + (row[-1][1] - a0) * SVG_X
            out.append(f'<text x="4" y="{top + 20}" font-size="10" fill="#555">t{i} {clefs[i]}</text>')
            for k in range(5):
                out.append(f'<line x1="{left}" y1="{top + k * SVG_LINE}" x2="{x1:.1f}" y2="{top + k * SVG_LINE}" '
                           'stroke="#999" stroke-width="0.6"/>')
            for a, b in row:
                xa = left + (a - a0) * SVG_X
                out.append(f'<line x1="{xa:.1f}" y1="{top}" x2="{xa:.1f}" y2="{bottom}" stroke="#333" stroke-width="0.8"/>')
                if i == 0:
                    num = bounds.index(a) + (0 if pickup else 1)
                    out.append(f'<text x="{xa + 2:.1f}" y="{top - 4}" font-size="8" fill="#777">{num}</text>')
            out.append(f'<line x1="{x1:.1f}" y1="{top}" x2="{x1:.1f}" y2="{bottom}" stroke="#333" stroke-width="0.8"/>')
            lo_d = 4 * 7 + 2 if clefs[i] == 'G' else 2 * 7 + 4      # 아래 줄: E4 / G2
            for nt in tr['notes']:
                if not (a0 <= nt['tick'] < row[-1][1]):
                    continue
                x = left + (nt['tick'] - a0) * SVG_X
                ln = min(nt['len'], row[-1][1] - nt['tick']) * SVG_X
                if nt['noise']:
                    yy = top + 2 * SVG_LINE
                    out.append(f'<text x="{x - 3:.1f}" y="{yy + 3:.1f}" font-size="9">x</text>')
                    continue
                p = midi_pitch(nt)
                d = (p // 12 - 1) * 7 + LETTER[p % 12]
                yy = bottom - (d - lo_d) * SVG_LINE / 2
                out.append(f'<line x1="{x:.1f}" y1="{yy:.1f}" x2="{x + ln:.1f}" y2="{yy:.1f}" stroke="#7aa6d8" stroke-width="2"/>')
                for ly in range(1, 40):
                    lyy = bottom + ly * SVG_LINE
                    if lyy > yy + 0.1:
                        break
                    out.append(f'<line x1="{x - 6:.1f}" y1="{lyy}" x2="{x + 6:.1f}" y2="{lyy}" stroke="#333" stroke-width="0.6"/>')
                for ly in range(1, 40):
                    lyy = top - ly * SVG_LINE
                    if lyy < yy - 0.1:
                        break
                    out.append(f'<line x1="{x - 6:.1f}" y1="{lyy}" x2="{x + 6:.1f}" y2="{lyy}" stroke="#333" stroke-width="0.6"/>')
                fill = 'white' if nt['len'] >= 96 else 'black'
                out.append(f'<ellipse cx="{x:.1f}" cy="{yy:.1f}" rx="4.4" ry="3.2" fill="{fill}" stroke="black" stroke-width="1" '
                           f'transform="rotate(-20 {x:.1f} {yy:.1f})"/>')
                if ALTER[p % 12]:
                    out.append(f'<text x="{x - 13:.1f}" y="{yy + 4:.1f}" font-size="11">♯</text>')
                if nt['len'] < 192:
                    up = yy > top + 2 * SVG_LINE
                    sx = x + 4 if up else x - 4
                    sy = yy - 26 if up else yy + 26
                    out.append(f'<line x1="{sx:.1f}" y1="{yy:.1f}" x2="{sx:.1f}" y2="{sy:.1f}" stroke="black" stroke-width="1"/>')
                    flags = 3 if nt['len'] <= 6 else 2 if nt['len'] <= 12 else 1 if nt['len'] <= 24 else 0
                    for f in range(flags):
                        fy = sy + (f * 5 if up else -f * 5)
                        out.append(f'<line x1="{sx:.1f}" y1="{fy:.1f}" x2="{sx + 7:.1f}" y2="{fy + (7 if up else -7):.1f}" '
                                   'stroke="black" stroke-width="1.4"/>')
    out.append('</svg>')
    return '\n'.join(out) + '\n'


# ---- KON 견주기 ----

def compare_kon(perf, kon, start, voice=0, count=40, from_tick=0):
    """트랙 i = 목소리 voice + i. 연주의 KON(음표·붙임, 비율 00 뒤는 뺌) 틱과 KON 기록 프레임을 첫 KON 에 맞춰 견준다.
    틱 → 프레임은 템포로 계산한다(프레임 속도 / (0.8 x 템포)). 음 차이는 이웃 KON 끼리의 반음 수(같은 악기·잡음 아님).
    [(트랙, 견준 KON 수, 최대 프레임 차, 음 차이 틀린 수)]."""
    fps = 21477272 / 4 / 89341.5        # NTSC SFC 프레임 속도(약 60.0988)
    ts = perf['tempo']

    def frames(t0, t1):
        f, t = 0.0, t0
        while t < t1:
            cur = [v for tt, v in ts if tt <= t][-1]
            nxt = min([tt for tt, _ in ts if tt > t] + [t1])
            f += (nxt - t) * fps / (0.8 * cur)
            t = nxt
        return f
    out = []
    for i, tr in enumerate(perf['tracks']):
        if voice + i >= 8:
            break
        st = [x for x in tr['strikes'] if x[0] >= from_tick]
        k = [x for x in kon[voice + i] if x[0] >= start]
        m = min(len(st), len(k), count)
        if m < 2:
            out.append((i, m, None, None))
            continue
        err = max(abs(k[j][0] - (k[0][0] + frames(st[0][0], st[j][0]))) for j in range(m))
        bad = sum(round(12 * math.log2(k[j][1] / k[j - 1][1])) != st[j][1] - st[j - 1][1]
                  for j in range(1, m) if k[j][1] and k[j - 1][1] and _same_instr(tr, st[j - 1][0], st[j][0]))
        out.append((i, m, err, bad))
    return out


def _same_instr(tr, t0, t1):
    a = [nt for nt in tr['notes'] if nt['tick'] <= t0]
    b = [nt for nt in tr['notes'] if nt['tick'] <= t1]
    if not a or not b:
        return False
    a, b = a[-1], b[-1]
    return a['instrument'] == b['instrument'] and not a['noise'] and not b['noise']


def export(rom, out, only=None):
    seqs = {n: bytes(body(rom, a, ln)) for n, a, ln in sequences(rom)}
    made = []
    envs = env_tables(rom)
    for n, x, stem, folder in targets(rom):
        if only and n not in only:
            continue
        seq = seqs[n]
        perf = perform(seq, x or 0)
        tunes = instrument_tunes(rom, n)
        d = os.path.join(out, folder)
        os.makedirs(d, exist_ok=True)
        title = f'DQ5 {"song" if folder == "songs" else "sfx"} {stem}'
        head = [f'# {title}: 시퀀스 {n:02X}' + ('' if x is None else f', 곡 변수 {x:02X}(갈래)'),
                '# dq5song.py 의 listing 꼴. 이 글을 dq5song.py --encode 로 다시 쌀 수 있다(# 뒤는 무시).',
                '# 악기(F0 i) → 샘플: ' + ' '.join(f'{i}={s:02X}' for i, (s, _) in enumerate(tunes))]
        with open(os.path.join(d, stem + '.txt'), 'w', encoding='utf-8') as f:
            f.write('\n'.join(head + listing(seq)) + '\n')
        meter = guess_meter(perf)
        perf['meter'] = meter
        with open(os.path.join(d, stem + '.mid'), 'wb') as f:
            f.write(to_midi(perf, tunes, title, envs, meter[0]))
        with open(os.path.join(d, stem + '.musicxml'), 'w', encoding='utf-8') as f:
            f.write(to_musicxml(perf, tunes, title, meter))
        with open(os.path.join(d, stem + '.svg'), 'w', encoding='utf-8') as f:
            f.write(to_svg(perf, title, meter))
        made.append((n, x, stem, folder, perf))
    return made


def update_index(rom, out, made):
    """index.json 의 항목에 score 를 넣고, .spc 가 없는 것은 새 항목으로 더한다."""
    try:
        from dq5spcfile import scene
    except ImportError:
        scene = None
    seqmeta = {n: (a, ln) for n, a, ln in sequences(rom)}
    for folder in ('songs', 'sfx'):
        path = os.path.join(out, folder, 'index.json')
        entries = json.load(open(path, encoding='utf-8')) if os.path.exists(path) else []
        by = {e['id']: e for e in entries}
        for n, x, stem, f, perf in made:
            if f != folder:
                continue
            e = by.get(stem)
            if e is None:
                a, ln = seqmeta[n]
                sc = scene(n, x, rom) if scene else None
                e = {'id': stem, 'sequence': f'{n:02X}', 'variant': None if x is None else f'{x:02X}', 'file': None,
                     'scene': sc or '쓰는 곳 미확인(소리 파일 없음)', 'sequence_rom': f'{a >> 16:02X}:{a & 0xFFFF:04X}',
                     'sequence_bytes': ln, 'samples': [f'{s:02X}' for s in song_sets(rom)[n][2]], 'maps': []}
                entries.append(e)
                by[stem] = e
            e['score'] = {'txt': stem + '.txt', 'mid': stem + '.mid', 'musicxml': stem + '.musicxml', 'svg': stem + '.svg',
                          'ticks': perf['end'], 'looped': perf['looped'],
                          'notes': sum(len(t['notes']) for t in perf['tracks']),
                          'meter': f'{perf["meter"][0]}/4(추정)', 'pickup': perf['meter'][2]}
        entries.sort(key=lambda e: (int(e['sequence'], 16), -1 if e.get('variant') is None else int(e['variant'], 16)))
        with open(path, 'w', encoding='utf-8') as fh:
            json.dump(entries, fh, ensure_ascii=False, indent=1)
            fh.write('\n')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('rom')
    ap.add_argument('--out')
    ap.add_argument('--only', help='시퀀스 번호 쉼표 목록(16진)')
    ap.add_argument('--kon', metavar='DSPW', help='lua/dq5dspw.lua 기록과 견줌(--seq 필요)')
    ap.add_argument('--seq', type=lambda s: int(s, 16))
    ap.add_argument('--flag', type=lambda s: int(s, 16), default=0)
    ap.add_argument('--start', type=int, default=0)
    ap.add_argument('--voice', type=int, default=0)
    ap.add_argument('--count', type=int, default=40)
    ap.add_argument('--from-tick', type=int, default=0, help='--kon 에서 이 틱부터의 KON 만(--start 는 그 틱 언저리 프레임으로)')
    a = ap.parse_args()
    rom = Rom(open(a.rom, 'rb').read())
    if a.kon:
        from dq5song import read_kon
        seq = bytes(body(rom, *[(ad, ln) for n, ad, ln in sequences(rom) if n == a.seq][0]))
        perf = perform(seq, a.flag)
        for i, m, err, bad in compare_kon(perf, read_kon(a.kon), a.start, a.voice, a.count, a.from_tick):
            print(f'track {i}: 음 {m}개' + ('' if err is None else f', 최대 {err:.2f} 프레임 차, 음 차이 틀림 {bad}'))
        return 0
    only = {int(v, 16) for v in a.only.split(',')} if a.only else None
    made = export(rom, a.out, only)
    update_index(rom, a.out, made)
    print(f'{len(made)}개: 곡 {sum(1 for m in made if m[3] == "songs")}, 효과음 {sum(1 for m in made if m[3] == "sfx")}, '
          f'시퀀스 {len({m[0] for m in made})}개')
    return 0


if __name__ == '__main__':
    sys.exit(main())
