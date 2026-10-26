"""FC DQ4 서곡(곡 02)의 악보를 DQ5 SPC 시퀀스로 편곡해 타이틀 곡(시퀀스 10)에 넣는다.

NDS 서곡은 PCM 스트림이라 악보가 없다(nds/dq4/docs/sound-format.md). 그래서 음은 FC 악보에서 가져오고,
빠르기는 NDS 녹음과 맞춘 템포 지도(NDS_TEMPO)를 쓰고, 악기 배치와 스네어 리듬은 같은 행진이 들어 있는
DQ5 시퀀스 15 를 따른다.
형식은 sfc/dq4/docs/dq4-overture-format.md.

  python sfc/dq4/tools/dq4overture.py text --nes rom/dq4.nes --rom rom/dq5.sfc                # 시퀀스 글(dq5song.py 꼴)
  python sfc/dq4/tools/dq4overture.py build --nes rom/dq4.nes --rom rom/dq5.sfc \\
      --title work/title/dq4-title-baseline.sfc --out work/overture/dq4-title-overture.sfc
  python sfc/dq4/tools/dq4overture.py tempo-map --nes rom/dq4.nes --fs work/nds/jp   # NDS 녹음으로 템포 지도 다시 재기
  python sfc/dq4/tools/dq4overture.py render work/overture/run   # lua/dq4overturespc.lua 결과 → .spc·.wav
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(HERE), str(ROOT / 'sfc' / 'dq5' / 'tools'), str(ROOT / 'fc' / 'dq4' / 'tools')]

from dq4romassets import SOURCE_SHA1, differences, set_checksum  # noqa: E402
from dq5map import Rom  # noqa: E402
from dq5song import GATES, assemble, header, patch_reloc, play  # noqa: E402
from dq5spc import SONG_SETS  # noqa: E402

SONG = 0x10                 # DQ5 타이틀 곡. 타이틀 패치가 타이틀에 들어올 때 01 10 을 보낸다
FC_SONG = 0x02
TITLE_SIZE = 0x200000
OUT_SIZE = 0x400000         # patch_reloc 은 뱅크 70(파일 0x380000)을 쓴다
FC_FPS = 60.0988

# 악기 배치는 DQ5 시퀀스 15(장면 미확인)를 따른다. 15 의 행진(틱 1488~7488)은 FC 서곡 행진(틱 751~3751)과 선율이 음마다
# 같아, 같은 행진을 SFC 음원으로 나눈 예로 보고 트랙마다 샘플·음량·팬·릴리스를 가져왔다. 화성은 FC 와 달라(베이스 음
# 이름 일치 47%) 음이 있는 파트는 쓰지 않고, 음높이 없는 스네어 리듬만 빌드할 때 롬에서 읽어 쓴다(REF_*).
# 시퀀스 10 은 DQ5 원래 타이틀 곡과 서곡을 갈래(곡 변수)로 함께 담는다. 타이틀은 0C 10 01 로 서곡을, 메뉴는 원래대로
# 01 10 으로 원래 곡을 튼다. 타이틀 화면은 첫 음과 함께 밝아지므로(곡 자료가 다 갈 때까지 기다림), 곡 묶음 10 은 팡파르가
# 쓰는 금관 둘·팀파니만 곡보다 먼저 보내 기다림을 줄이고 나머지는 곡이 흐르는 동안 보낸다. 늦게 오는 샘플을 쓰는 트랙은
# 그 샘플이 닿은 뒤에 악기를 고른다(overture 의 entries). 원래 곡의 악기 번호는 이 순서로 다시 매긴다(original_listing).
ORIGINAL_SAMPLES = [0x0A, 0x1A, 0x12, 0x14, 0x15, 0x13]
SAMPLES = [0x1C, 0x0B, 0x15, 0x18, 0x16, 0x13, 0x0A, 0x1A, 0x12, 0x14]
TRUMPET, LOW_BRASS, TIMPANI, STRINGS, BASS, SNARE = range(6)
SEND_FIRST = 3
OVERTURE_FLAG = 0x01
SPC_SET_TABLE, SPC_SAMPLE_AREA = 0x28EC, 0x2A5D     # 곡 묶음 표가 올라가는 SPC 자리와 그 뒤 샘플 자리의 시작
# 곡 묶음 표는 드라이버 IPL 전송의 마지막 블록([길이 2][SPC 주소 2][자료], SPC 28E7~) 끝에 있고, 바로 뒤에 끝 표시
# [길이 0000][실행 주소 0200] 이 온다. 표를 늘리면 블록 길이를 고치고 끝 표시를 뒤로 옮겨야 드라이버가 올라간다
IPL_BLOCK = 0x2BE676
IPL_END = bytes.fromhex('00 00 00 02')
TITLE_CALL = 0x18001C       # 30:801C, 타이틀 코드의 LDA #$10 / JSL $24FE9A
MENU_CALL = 0x002709        # 00:A709, 원래 STA $2100 / BRK 0F 10(메뉴 곡). 타이틀 패치가 BRK 를 NOP 으로 막아 둔 자리
TITLE_STUB, MENU_STUB = 0x70FF00, 0x70FF20
# 타이틀 FadeOut 첫 명령 LDX #$000F(30:81AA). 바로 뒤 30:81AD 는 밝기 반복의 분기 대상이라 3바이트만 바꿀 수 있어
# 같은 뱅크 JMP 로 30:FF00 에 간다. 30:9000~ 은 빌드가 원본 뱅크 20~2F 를 거울로 채운 자리로 읽는 코드가 없다
FADE_CALL, FADE_STUB = 0x30_81AA, 0x30_FF00
FADE_SPEED = 0x40           # 명령 04 의 X. 20 은 메뉴(약 80프레임 뒤)까지 30% 가 남았다
MIDI_OFFSET = 23            # 음 번호 n = MIDI - 23. 샘플 머리의 음높이가 샘플마다 이 약속에 맞춘다
TIMPANI_NOTE = {'G': 0x27, 'C': 0x20}    # 15 는 음 번호 n 이 약 MIDI n + 16 으로 울림(G3·C3 언저리)
REF_SONG, REF_SNARE_TRACK = 0x15, 6
REF_MARCH = (1488, 7488)    # 시퀀스 15 의 틱. 이 곡의 틱(song_tick)으로는 +12
FC_MARCH = (751, 3751)
RING_RELEASE = 0x0E         # 끝 화음의 릴리스. NDS 는 끝 화음을 113~117초에 걸쳐 잦아들게 한다
RING_TICKS = 72             # 그동안 곡을 끝내지 않을 FC 틱(템포 60 에서 약 3초). 트랙이 끝나면 소리가 끊긴다

# NDS 녹음(STRM_OVERTURE32_8)과 FC 악보를 크로마 DTW 로 맞춰 잰 템포 지도: (FC 틱, FC 템포 단위).
# 팡파르는 96틱, 끝은 48틱 블록마다 잰 값이고, 행진(775~3751)은 직선 하나로 맞춘 값이다(tempo-map 출력을 반올림).
# 4423 은 블록이 아니라 마지막 화음: NDS 는 이 화음을 약 1.5초 세게 끈 뒤 잔향으로 줄어 FC 의 36틱을 그 길이로 늘린다.
NDS_TEMPO = [
    (0, 106), (97, 62), (193, 84), (289, 85), (385, 90), (481, 82), (577, 85), (673, 93), (751, 110),
    (775, 121), (3751, 101), (3775, 61), (3823, 63), (3871, 65), (3919, 62), (3967, 82), (4015, 55),
    (4063, 68), (4111, 53), (4159, 33), (4207, 70), (4255, 88), (4303, 51), (4351, 88), (4423, 60),
]


def fc_score(nes):
    """FC 롬에서 곡 02 의 중간 형식(fc/dq4/docs/dq4-sound-format.md 「중간 형식」)."""
    import dq4sound
    prg = dq4sound.load(nes)
    return dq4sound.song_json(prg, dq4sound.Run(prg, FC_SONG, max_frames=40000))


def parts(score):
    """채널마다 [(시작 틱, 길이, MIDI 또는 None, 소리 틱 또는 None(끝까지), 세기 0~1)]. 붙임은 앞 음에 합친다.
    마지막 쉼은 곡 끝(end_tick) + RING_TICKS 까지 늘린다. 쉼은 키를 떼지 않으므로 끝 화음이 그동안 릴리스로 줄어든다."""
    out = {}
    for ch in ('pulse1', 'pulse2', 'triangle'):
        evs, cur = [], None
        for e in (e for e in score['timeline'] if e['ch'] == ch):
            if e['op'] == 'end':
                break
            if cur and cur[0] + cur[1] != e['tick']:
                raise ValueError(f'{ch}: gap at tick {e["tick"]}')
            if e['op'] == 'tie' and cur and cur[2] is not None:
                gate = None if not e['gate'] or e['gate'] >= e['len'] else cur[1] + e['gate']
                cur = (cur[0], cur[1] + e['len'], cur[2], gate, cur[4])
                evs[-1] = cur
                continue
            if ch == 'triangle':
                # 삼각파의 게이트는 소리 길이가 아니라 음량(0 이면 0F)이다
                level, gate = (e['gate'] or 15) / 15, None
            else:
                level = e['ch_vol'] / 15
                gate = None if not e['gate'] or e['gate'] >= e['len'] else e['gate']
            cur = (e['tick'], e['len'], round(e['midi']) if e['op'] == 'note' else None, gate, level)
            evs.append(cur)
        tail = evs[-1][0] + evs[-1][1]
        evs.append((tail, score['end_tick'] + RING_TICKS - tail, None, None, 0))
        out[ch] = evs
    return out


def gate_preset(ratio):
    """소리 길이 비율(0~1)에 가장 가까운 A0~B3 표 값(FE·FF·00 은 따로 씀)."""
    return min(GATES[:20], key=lambda g: abs(g / 256 - ratio))


class Writer:
    """dq5song.py 꼴 글을 쓴다. 길이는 이 곡의 틱(FC 틱 x 2, DQ5 템포 T = FC 템포 단위면 같은 빠르기)."""

    def __init__(self):
        self.lines, self.dur, self.gate, self.vol2 = [], None, None, None

    def emit(self, text):
        self.lines.append('  ' + text)

    def volume2(self, v):
        if v != self.vol2:
            self.emit(f'volume2 {v:02X}')
            self.vol2 = v

    def put(self, n, ticks, gate):
        """음 n(0 = 쉼)을 ticks 동안. gate 는 표 값. 길이 바이트를 넘으면 끌기(00)와 붙임으로 이어 붙인다."""
        first = True
        while ticks:
            d = min(ticks, 0xF0)
            g = gate if d == ticks else 0x00
            if n and g != self.gate:
                self.emit(f'gate_preset {g:02X}')
                self.gate = g
            word = 'rest' if not n else 'tie' if not first else f'note {n:02X}'
            self.emit(f'{word} len {d:02X}' if d != self.dur else word)
            self.dur, ticks, first = d, ticks - d, False


def melodic(writer, evs, volume, labels=None):
    """labels 는 {FC 틱: 이름}. 그 틱의 음 앞에 이름을 두어 다른 트랙이 몸통 중간부터 부를 수 있게 한다. 그 트랙은 앞 상태가
    다르므로 이름 뒤에서는 길이·게이트·음량2 를 다시 쓴다."""
    labels = labels or {}
    last = max(i for i, e in enumerate(evs) if e[2] is not None)
    for i, (start, length, midi, gate, level) in enumerate(evs):
        if start in labels:
            writer.lines.append(f'{labels[start]}:')
            writer.dur = writer.gate = writer.vol2 = None
        if midi is None:
            writer.put(0, length * 2, writer.gate)
            continue
        writer.volume2(volume(level))
        if i == last:
            writer.emit(f'release {RING_RELEASE:02X}')
        ratio = 0xFE if gate is None else gate_preset(gate / length)
        writer.put(midi - MIDI_OFFSET, length * 2, ratio)


def song_tick(fc_tick):
    """FC 틱 → 이 곡의 틱. FC 악보는 틱 1 에서 시작하고 이 곡은 0 에서 시작하며, 길이는 2배다."""
    return max(0, 2 * (fc_tick - 1))


def tempo_at(tick):
    return [t for k, t in NDS_TEMPO if k <= tick][-1]


def track_notes(seq, index, flag=0, limit=12000):
    """시퀀스 트랙 하나를 dq5song.play 처럼 따라가며 [(틱, 음 번호, 길이, 음량2)]. 음량2(F6)를 함께 본다."""
    _, offs = header(seq)
    events = play(seq, limit, flag)[index]
    # play 는 음량을 내지 않으므로 같은 흐름을 한 번 더 걸어 음표마다 그 앞의 F6 를 붙인다
    from dq5song import step
    pc, vol2, out, stack, c1, c2 = offs[index], None, [], [], 0, 0
    notes = iter(events)
    dur = 0
    while pc < len(seq) and len(out) < len(events):
        b = seq[pc]
        nxt, _, target, _ = step(seq, pc)
        if b < 0xA0:
            if b >= 0x50:
                dur = seq[pc + 1]
            tick, n, _, _ = next(notes)
            if isinstance(n, int):
                out.append((tick, n, dur, vol2))
            else:
                out.append((tick, None, dur, vol2))
        elif b == 0xFF:
            break
        elif b == 0xF6:
            vol2 = seq[pc + 1]
        elif b == 0xDC:
            c1 = (c1 or 2) - 1
            nxt = target if c1 else nxt
        elif b == 0xDB:
            nxt = target if c1 else nxt
        elif b in (0xF4, 0xF5):
            c2 = (c2 or (2 if b == 0xF4 else seq[pc + 1])) - 1
            nxt = target if c2 else nxt
        elif b == 0xE0:
            nxt = target if seq[pc + 3] == flag else nxt
        elif b == 0xEA:
            nxt = target
        elif b == 0xF8:
            stack.append(nxt)
            nxt = target
        elif b == 0xF9 and stack:
            nxt = stack.pop()
        pc = nxt
    return out


def reference_snare(rom):
    """DQ5 시퀀스 15 의 행진 스네어를 이 곡의 틱으로 옮긴 [(틱, 음 번호, 음량2)]."""
    from dq5spc import body, sequences
    _, addr, n = sequences(rom)[REF_SONG]
    seq = bytes(body(rom, addr, n))
    shift = song_tick(FC_MARCH[0]) - REF_MARCH[0]
    return [(t + shift, x, v) for t, x, _, v in track_notes(seq, REF_SNARE_TRACK)
            if x is not None and REF_MARCH[0] <= t < REF_MARCH[1]]


def percussion(p, snare):
    """타악 트랙(지휘 트랙을 겸함)의 [(틱, 악기, 음 번호, 음량2 또는 None)], 끝 틱, 롤 {첫 틱: (목표 음량2, 틱 수)}.
    틱은 이 곡의 틱(song_tick)."""
    hits = [(t, SNARE, n, v or 0x80) for t, n, v in snare]
    lead = [e for e in p['pulse1'] if e[2] is not None]
    for start, length, midi, gate, level in lead:
        if start < FC_MARCH[0]:
            hits.append((song_tick(start), TIMPANI, TIMPANI_NOTE['G'], 0xC0 if length >= 12 else 0x90))
    # 팡파르의 긴 음 넷(97·289·481·673)에는 팀파니를 굴림. 세기는 첫 타에 두고 volume2_slide 로 키운다(타마다
    # 음량을 주면 롤마다 글이 달라져 묶이지 않는다). None 은 음량을 그대로 둔다는 뜻
    rolls = {}
    for start, length, midi, gate, level in lead:
        if start < FC_MARCH[0] and length >= 96:
            ticks = list(range(start + 6, start + length - 12, 3))
            rolls[song_tick(ticks[0])] = (0xA0, song_tick(ticks[-1]) - song_tick(ticks[0]))
            hits += [(song_tick(t), TIMPANI, TIMPANI_NOTE['G'], 0x50 if t == ticks[0] else None) for t in ticks]
    # 끝: 리타르단도 뒤 선율이 칠 때마다 팀파니, 마지막 화음은 굴림
    tail = [e for e in lead if e[0] >= 4015]
    for start, length, midi, gate, level in tail:
        hits.append((song_tick(start), TIMPANI, TIMPANI_NOTE['C'] if midi % 12 == 0 else TIMPANI_NOTE['G'], 0xB0))
    last = tail[-1]
    ticks = list(range(last[0] + 3, last[0] + last[1] - 6, 3))
    hits += [(song_tick(t), TIMPANI, TIMPANI_NOTE['C'], 0x70 if t == ticks[0] else None) for t in ticks]
    end = song_tick(max(s + n for ch in p.values() for s, n, *_ in ch))
    return sorted(set(hits), key=lambda h: (h[0], h[1], h[2], h[3] is None, h[3] or 0)), end, rolls


def perc_track(writer, hits, end, rolls):
    changes = {song_tick(k): t for k, t in NDS_TEMPO}
    marks = sorted(set([h[0] for h in hits] + list(changes) + [end]))
    by_tick = {}
    for h in hits:
        by_tick.setdefault(h[0], h)
    ins = None
    tick = 0
    writer.emit(f'tempo {changes[0]:02X}')
    for nxt in marks:
        if nxt > tick:
            writer.put(0, nxt - tick, writer.gate)
            tick = nxt
        if tick in changes and tick:
            writer.emit(f'tempo {changes[tick]:02X}')
        if tick in by_tick and tick < end:
            _, i, n, vol = by_tick[tick]
            if i != ins:
                # 악기를 고르면 샘플 머리의 ADSR 로 돌아가므로 릴리스를 다시 준다
                writer.emit(f'instrument {i:02X}')
                writer.emit('release 14')
                ins = i
            if vol is not None:
                writer.volume2(vol)
            if tick in rolls:
                target, span = rolls[tick]
                writer.emit(f'volume2_slide {target:02X} {span:02X}')
                writer.vol2 = None   # 미끄럼 뒤의 음량은 글로 알 수 없으므로 다음 volume2 는 늘 쓴다
            stop = min(m for m in marks if m > tick)
            writer.put(n, stop - tick, 0xFE)
            tick = stop


FACTOR_LENGTHS = (96, 64, 48, 40, 32, 28, 24, 20, 16, 14, 12, 10, 8, 6, 5, 4)   # 찾아볼 덩어리 길이(줄)


def factor(lines, prefix, depth=1):
    """되풀이되는 줄 덩어리를 서브루틴(call/ret)으로 묶는다 → (줄, 서브루틴 줄). call·ret 는 틱도 트랙 상태도 바꾸지
    않으므로 같은 바이트를 제자리에서 읽든 서브루틴에서 읽든 같게 울린다. 이름·점프·부르기·돌아가기가 든 덩어리는
    묶지 않는다. depth 는 더 쌓을 수 있는 부르기 단 수다(드라이버는 3단까지). 서브루틴 안의 되풀이도 depth 만큼 다시 묶는다."""
    from dq5song import _encode_line
    size = lambda ln: len(_encode_line(ln.split(), 0, None))
    barrier = lambda ln: ln.endswith(':') or ln.split()[0] in ('call', 'jump', 'ret', 'end')
    subs, k = [], 0
    while True:
        ids = {}
        code = [ids.setdefault(ln, len(ids)) for ln in lines]
        bad = [barrier(ln) for ln in lines]
        best = None
        for n in FACTOR_LENGTHS:
            seen = {}
            run = 0
            for i in range(len(lines)):
                run = 0 if bad[i] else run + 1
                if run >= n:
                    j = i - n + 1
                    seen.setdefault(tuple(code[j:i + 1]), []).append(j)
            for pos in seen.values():
                chosen, last = [], -n
                for j in pos:
                    if j >= last + n:
                        chosen.append(j)
                        last = j
                if len(chosen) < 2:
                    continue
                b = sum(size(ln) for ln in lines[chosen[0]:chosen[0] + n])
                save = len(chosen) * (b - 3) - b - 1
                if save > 0 and (best is None or save > best[0]):
                    best = (save, n, chosen)
        if best is None:
            if depth > 1 and subs:
                subs, inner = factor(subs, f'{prefix}S', depth - 1)
                subs += inner
            return lines, subs
        _, n, chosen = best
        name = f'{prefix}{k}'
        k += 1
        subs += [f'{name}:'] + lines[chosen[0]:chosen[0] + n] + ['  ret']
        for j in reversed(chosen):
            lines = lines[:j] + [f'  call -> {name}'] + lines[j + n:]


def overture(score, snare):
    """서곡 7트랙의 글(머리 없음, 트랙 이름 LT0~LT6). 트랙마다 끝에서 처음으로 돌아가 되풀이한다."""
    p = parts(score)
    hits, end, rolls = percussion(p, snare)
    level = lambda base: (lambda x: max(0x30, min(0xFF, round(base * x))))
    bodies = []
    # 늦게 오는 샘플(현·베이스)을 쓰는 트랙은 몸통 중간의 이름부터 시작한다. 샘플이 아직 없을 때 악기를 고르면 그 트랙은
    # 끝까지 KON 을 내지 않는다(DQ5 곡 17 과 같은 일). 현은 행진부터 선율을 겹치고, 삼각파 선율은 첫 쉼 뒤부터다
    low_start = next(e[0] for e in p['triangle'] if e[2] is not None)
    entries = {'pulse1': {FC_MARCH[0]: 'LMEL2'}, 'pulse2': {}, 'triangle': {low_start: 'LLOW2'}}
    for name, ch, base in (('LMEL', 'pulse1', 0xFF), ('LHAR', 'pulse2', 0xF0), ('LLOW', 'triangle', 0xDC)):
        w = Writer()
        melodic(w, p[ch], level(base), entries[ch])
        lines, subs = factor(w.lines, f'{name}S', 2)     # 트랙 → 몸통 → 서브루틴 → 서브루틴
        bodies.append((name, lines + ['  ret'] + subs))
    # 음량·팬·릴리스는 시퀀스 15 행진의 같은 역할 트랙 값(트럼펫 32/E2/14, 금관 화음 28/CE/14, 저음 금관 28/32/14,
    # 현 28/D8·28/15, 베이스 28/00/17, 스네어 28/F1/14). 현이 선율을 겹치는 것만 FC 에 대선율이 없어 새로 둔 것
    def wait(fc_tick):
        w = Writer()
        w.put(0, song_tick(fc_tick), None)
        return [ln.strip() for ln in w.lines]
    tracks = [
        ('LT0', ['fe 16', 'volume 32', f'instrument {TRUMPET:02X}', 'release 14', 'pan E2', 'call -> LMEL']),
        ('LT1', ['volume 28', f'instrument {TRUMPET:02X}', 'release 14', 'pan CE', 'call -> LHAR']),
        ('LT2', ['volume 28', f'instrument {LOW_BRASS:02X}', 'release 14', 'pan 32', 'transpose F4', 'call -> LHAR']),
        ('LT3', ['volume 1E', 'pan D8', *wait(FC_MARCH[0]), f'instrument {STRINGS:02X}', 'release 15', 'call -> LMEL2']),
        ('LT4', ['volume 28', 'pan 28', *wait(low_start), f'instrument {STRINGS:02X}', 'release 15', 'call -> LLOW2']),
        ('LT5', ['volume 28', 'pan 00', 'transpose F4', *wait(low_start), f'instrument {BASS:02X}', 'release 17',
                 'call -> LLOW2']),
    ]
    out = []
    for t, cmds in tracks:
        out += [f'{t}:'] + [f'  {c}' for c in cmds] + [f'  jump -> {t}']
    w = Writer()
    perc_track(w, hits, end, rolls)
    lines, subs = factor(w.lines, 'LT6S', 3)
    out += ['LT6:', '  volume 28', '  pan F1'] + lines + ['  jump -> LT6'] + subs
    for name, lines in bodies:
        out += [f'{name}:'] + lines
    return out


def arrange(score, snare, original):
    """시퀀스 10 의 글. original 은 원래 시퀀스 10 의 listing(). 트랙마다 머리에서 곡 변수가 01 이면 서곡으로 간다.
    곡 변수는 첫 틱이 끝나면 0 으로 돌아가므로 모든 트랙이 첫 틱에 고른다(DQ5 동굴 전투 곡과 같은 꼴)."""
    head = [ln for ln in original if ln and not ln[0].isspace() and not ln.endswith(':')]
    body = original[len(head):]
    starts = [ln.split()[1] for ln in head[1:]]
    out = [head[0]] + [f'track LS{i}' for i in range(7)]
    for i in range(7):
        out += [f'LS{i}:', f'  if_flag {OVERTURE_FLAG:02X} -> LT{i}']
        out += [f'  jump -> {starts[i]}'] if i < len(starts) else ['  end']
    return out + body + overture(score, snare)


def set_table(rom):
    """곡 묶음 표(2B:E67F, 레코드 0x47개) 전체를 곡 10 의 레코드만 늘려 다시 쓴 바이트와 원래 길이."""
    from dq5spc import SEQUENCE_COUNT
    a, recs = SONG_SETS, []
    for _ in range(SEQUENCE_COUNT):
        n = rom.u8(a) + 2
        recs.append(bytes(rom.d[rom_off(a):rom_off(a) + n]))
        a += n
    old = recs[SONG]
    if list(old[2:]) != ORIGINAL_SAMPLES:
        raise ValueError(f'song set {SONG:02X} is {old.hex(" ")}, expected the original title samples')
    # 둘째 바이트 = 곡을 틀기 전에 보낼 샘플 수
    recs[SONG] = bytes([len(SAMPLES), SEND_FIRST] + SAMPLES)
    table = b''.join(recs)
    if SPC_SET_TABLE + len(table) > SPC_SAMPLE_AREA:
        raise ValueError('song set table would overlap the SPC sample area')
    return table, a - SONG_SETS


def rom_off(addr):
    return (addr >> 16 & 0x7F) * 0x8000 + (addr & 0x7FFF)


def original_listing(rom):
    """원래 시퀀스 10 의 글. 악기 번호(F0)를 SAMPLES 순서로 다시 매긴다."""
    from dq5song import listing
    from dq5spc import body, sequences
    _, addr, n = sequences(rom)[SONG]
    out = []
    for ln in listing(bytes(body(rom, addr, n))):
        w = ln.split()
        if w and w[0] == 'instrument':
            ln = f'  instrument {SAMPLES.index(ORIGINAL_SAMPLES[int(w[1], 16)]):02X}'
        out.append(ln)
    return out


def cycle_ticks(score):
    return song_tick(score['end_tick'] + RING_TICKS)


def check_sequence(seq, score):
    """싼 시퀀스를 갈래 0·01 로 돌려 트랙마다 음 수를 낸다. 서곡은 한 바퀴(cycle_ticks) 안의 음만 센다."""
    tempo, offs = header(seq)
    cycle = cycle_ticks(score)
    report = {}
    for flag in (0, OVERTURE_FLAG):
        events = play(seq, cycle * 2 if flag else 20000, flag)
        report[f'flag_{flag:02X}'] = [sum(1 for t, n, _, _ in ev if isinstance(n, int) and (not flag or t < cycle))
                                      for ev in events]
    return {'bytes': len(seq), 'tracks': len(offs), 'tempo': tempo, 'cycle_ticks': cycle, 'notes': report}


def build(nes, rom_path, title_path, out):
    original = Path(rom_path).read_bytes()
    if hashlib.sha1(original).hexdigest() != SOURCE_SHA1:
        raise ValueError('source ROM SHA-1 mismatch')
    title = Path(title_path).read_bytes()
    if len(title) != TITLE_SIZE:
        raise ValueError('title ROM must be the 2MB layered title build')
    score = fc_score(nes)
    rom = Rom(original)
    lines = arrange(score, reference_snare(rom), original_listing(rom))
    seq = assemble(lines)
    doc = patch_reloc(rom, {SONG: seq})
    data = bytearray(title) + bytes(OUT_SIZE - TITLE_SIZE)
    data[0x7FD7] = 0x0C

    def put(off, new, orig=None):
        if orig is not None and data[off:off + len(orig)] != orig:
            raise ValueError(f'{off:06X}: expected {orig.hex(" ")}, found {data[off:off + len(orig)].hex(" ")}')
        data[off:off + len(new)] = new
    for w in doc['writes']:
        bank, addr = (int(x, 16) for x in w['at'].split(':'))
        put(rom_off(bank << 16 | addr), bytes.fromhex(w['hex']), bytes.fromhex(w['orig']) if 'orig' in w else None)
    if rom_off(0x708600) + len(doc['writes'][-1]['hex'].split()) > rom_off(TITLE_STUB):
        raise ValueError('relocated sequence reaches the title stub')
    table, old_len = set_table(rom)
    block = int.from_bytes(original[rom_off(IPL_BLOCK):rom_off(IPL_BLOCK) + 2], 'little')
    put(rom_off(IPL_BLOCK), (block + len(table) - old_len).to_bytes(2, 'little'), (block).to_bytes(2, 'little'))
    tail = rom_off(SONG_SETS) + old_len
    if original[tail:tail + 4] != IPL_END or any(original[tail + 4:tail + 4 + len(table) - old_len]):
        raise ValueError('unexpected bytes after the song set table')
    put(rom_off(SONG_SETS), table + IPL_END, bytes(original[rom_off(SONG_SETS):tail + 4]))
    # 타이틀: 01 10 대신 0C 10 01(갈래 01 = 서곡). 24:FEAC 는 A 를 곡, X 를 스크립트로 대기열에 넣는다
    stub = bytes.fromhex('08 C2 10 DA A2 01 00 E2 20 A9 10 22 AC FE 24 FA 28 6B')
    stub = stub[:5] + bytes([OVERTURE_FLAG]) + stub[6:]
    put(rom_off(TITLE_STUB), stub, bytes(len(stub)))
    put(TITLE_CALL, bytes([0x22, TITLE_STUB & 0xFF, TITLE_STUB >> 8 & 0xFF, TITLE_STUB >> 16, 0xEA, 0xEA]),
        bytes.fromhex('A9 10 22 9A FE 24'))
    # 타이틀을 나갈 때 화면과 함께 서곡을 줄인다(04 10, X = FADE_SPEED)
    fade = bytes.fromhex('08 5A E2 20 A9 10 A2') + bytes([FADE_SPEED, 0]) + bytes.fromhex('22 C7 FE 24 7A 28 A2 0F 00 4C')
    fade += (FADE_CALL + 3 & 0xFFFF).to_bytes(2, 'little')
    put(rom_off(FADE_STUB), fade, data[rom_off(FADE_STUB):rom_off(FADE_STUB) + len(fade)])
    put(rom_off(FADE_CALL), bytes([0x4C]) + (FADE_STUB & 0xFFFF).to_bytes(2, 'little'), bytes.fromhex('A2 0F 00'))
    # 메뉴: 원래의 BRK 0F 10 자리. 같은 곡 10 이 울리는 중에 01 10 만 보내면 드라이버가 다시 틀지 않으므로
    # 02 10(멈춤) 뒤 01 10(갈래 0 = 원래 곡)을 보내고, BRK 0F 처럼 대기열이 빌 때까지 기다린다
    menu = bytes.fromhex('8D 00 21 08 E2 20 A9 10 22 BE FE 24 A9 10 22 9A FE 24 22 44 FE 24 28 6B')
    put(rom_off(MENU_STUB), menu, bytes(len(menu)))
    put(MENU_CALL, bytes([0x22, MENU_STUB & 0xFF, MENU_STUB >> 8 & 0xFF, MENU_STUB >> 16, 0xEA, 0xEA]),
        bytes.fromhex('8D 00 21 EA EA EA'))
    rom_out = set_checksum(bytes(data))
    # 늘린 2MB 의 대부분이 0 이라 RLE 레코드를 쓰는 dq5build 의 IPS 로 만든다
    from dq5build import make_ips
    from kr_patch import ips
    patch = make_ips(original, rom_out)
    if ips.apply(original, patch) != rom_out:
        raise ValueError('IPS application mismatch')
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(rom_out)
    out.with_suffix('.ips').write_bytes(patch)
    out.with_suffix('.txt').write_text('\n'.join(lines) + '\n')
    report = {'kind': 'dq4_title_overture', 'source_sha1': SOURCE_SHA1,
              'title_sha1': hashlib.sha1(title).hexdigest(), 'rom_sha1': hashlib.sha1(rom_out).hexdigest(),
              'fc_song': f'{FC_SONG:02X}', 'dq5_sequence': f'{SONG:02X}', 'samples': [f'{s:02X}' for s in SAMPLES],
              'sequence': check_sequence(seq, score), 'tempo_map': NDS_TEMPO,
              'changed_ranges': [{'file_offset': f'{s:06X}', 'bytes': len(d)} for s, d in differences(original, rom_out)]}
    out.with_suffix('.json').write_text(json.dumps(report, indent=1) + '\n')
    return report


def tempo_map(nes, fs, hop=0.05):
    """NDS 녹음과 FC 악보를 크로마 DTW 로 맞춰 NDS_TEMPO 꼴 표를 다시 잰다."""
    import numpy as np
    sys.path.insert(0, str(ROOT / 'nds' / 'dq4' / 'tools'))
    import ndssound
    score = fc_score(nes)
    tc = [[0, score['tempo']]] + score['tempo_changes']

    def tsec(t):
        s = 0.0
        for i, (t0, tp) in enumerate(tc):
            t1 = tc[i + 1][0] if i + 1 < len(tc) else 1e9
            if t <= t0:
                break
            s += (min(t, t1) - t0) / (FC_FPS * tp / 150)
        return s
    n1 = int((tsec(score['end_tick']) + 1) / hop) + 1
    fc = np.zeros((n1, 12))
    for e in score['timeline']:
        if e['op'] == 'note':
            a, b = int(tsec(e['tick']) / hop), int(tsec(e['tick'] + e['len']) / hop)
            fc[a:max(b, a + 1), round(e['midi']) % 12] += 0.7 if e['ch'] == 'triangle' else 1.0
    sd = ndssound.load_sdat(fs)
    info = next(sd.strm_info(i) for i in range(sd.count('strm')) if sd.strm_info(i))
    pcm, rate, _, _ = ndssound.strm_decode(sd.file(info['file']))
    x = pcm.mean(axis=1)
    step, size = int(rate * hop), 8192
    win, f = np.hanning(size), np.fft.rfftfreq(size, 1 / rate)
    band = (f > 55) & (f < 2000)
    pc = ((np.round(12 * np.log2(f[band] / 440)) + 69) % 12).astype(int)
    nds = np.array([np.bincount(pc, np.abs(np.fft.rfft(x[i:i + size] * win))[band] ** 2, 12)
                    for i in range(0, len(x) - size, step)])
    unit = lambda c: c / (np.linalg.norm(c, axis=1, keepdims=True) + 1e-9)
    cost = 1 - unit(fc) @ unit(np.sqrt(nds)).T
    n, m = cost.shape
    big = 1e18
    acc = np.full((n, m), big)
    back = np.zeros((n, m), np.int8)
    acc[0, 0] = cost[0, 0]
    # 걸음: (1,1)(1,2)(2,1)(1,3)(1,4). 페르마타는 NDS 쪽이 3배 넘게 늘어나므로 (1,3)·(1,4) 가 필요하다
    for i in range(1, n):
        c = np.full((5, m), big)
        c[0, 1:] = acc[i - 1, :-1]
        c[1, 2:] = acc[i - 1, :-2] + cost[i, 1:-1]
        if i >= 2:
            c[2, 1:] = acc[i - 2, :-1] + cost[i - 1, 1:]
        c[3, 3:] = acc[i - 1, :-3] + cost[i, 2:-1] + cost[i, 1:-2]
        c[4, 4:] = acc[i - 1, :-4] + cost[i, 3:-1] + cost[i, 2:-2] + cost[i, 1:-3]
        k = c.argmin(0)
        acc[i] = cost[i] + c[k, np.arange(m)]
        back[i] = k
    moves = [(1, 1), (1, 2), (2, 1), (1, 3), (1, 4)]
    i, j, path = n - 1, m - 1, [(n - 1, m - 1)]
    while i > 0 and j > 0:
        di, dj = moves[back[i, j]]
        i, j = i - di, j - dj
        path.append((i, j))
    path = np.array(path[::-1], float)
    when = lambda t: np.interp(tsec(t) / hop, path[:, 0], path[:, 1]) * hop
    k = FC_FPS / 150
    rows = []
    edges = list(range(1, 751, 96)) + [751, 775]
    rows += [(a, (b - a) / (when(b) - when(a)) / k) for a, b in zip(edges, edges[1:])]
    ts = np.arange(775, 3752, 12)
    slope = np.polyfit(ts, [when(t) for t in ts], 1)[0]
    rows.append((775, 1 / slope / k))
    edges = [3751] + list(range(3775, score['end_tick'], 48)) + [score['end_tick']]
    rows += [(a, (b - a) / (when(b) - when(a)) / k) for a, b in zip(edges, edges[1:])]
    return {'nds_seconds': len(x) / rate, 'fc_seconds': tsec(score['end_tick']),
            'mean_cost': float(acc[n - 1, m - 1] / len(path)), 'rows': [(int(a), round(float(t), 1)) for a, t in rows]}


def render(run, seconds=122):
    """lua/dq4overturespc.lua 의 결과 폴더를 overture.spc 로 묶고 libgme 로 overture.wav 를 굽는다."""
    import dq5spcfile
    run = Path(run)
    ram, dsp = (run / 'spc.bin').read_bytes(), (run / 'dsp.bin').read_bytes()
    spc = run / 'overture.spc'
    spc.write_bytes(dq5spcfile.pack(ram, dsp, dq5spcfile.regs(run / 'regs.txt'), 'DQ4 overture (DQ5 engine)',
                                    seconds=seconds, comment='FC song 02 score, NDS tempo map'))
    dq5spcfile.render(str(spc), str(run / 'overture.wav'), seconds, fade=2)
    return spc


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    s = sub.add_parser('text')
    s.add_argument('--nes', default='rom/dq4.nes')
    s.add_argument('--rom', default='rom/dq5.sfc')
    s = sub.add_parser('build')
    s.add_argument('--nes', default='rom/dq4.nes')
    s.add_argument('--rom', default='rom/dq5.sfc')
    s.add_argument('--title', required=True, help='dq4titlelayerpatch.py 가 만든 2MB 타이틀 롬')
    s.add_argument('--out', required=True)
    s = sub.add_parser('tempo-map')
    s.add_argument('--nes', default='rom/dq4.nes')
    s.add_argument('--fs', default=os.environ.get('NDS_FS', 'work/nds/jp'), help='NDS 롬을 푼 파일 시스템')
    s = sub.add_parser('render', help='GME_LIB(libgme) 가 필요')
    s.add_argument('run', help='lua/dq4overturespc.lua 의 OUT 폴더')
    a = ap.parse_args()
    if a.cmd == 'text':
        rom = Rom(Path(a.rom).read_bytes())
        print('\n'.join(arrange(fc_score(a.nes), reference_snare(rom), original_listing(rom))))
    elif a.cmd == 'render':
        print(render(a.run))
    elif a.cmd == 'build':
        r = build(a.nes, a.rom, a.title, a.out)
        print(json.dumps({'rom_sha1': r['rom_sha1'], 'sequence': r['sequence']}, indent=1))
    else:
        print(json.dumps(tempo_map(a.nes, a.fs), indent=1))


if __name__ == '__main__':
    main()
