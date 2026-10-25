"""DQ4(FC) 곡·효과음을 롬에서 풀어 악보 텍스트·MIDI·APU 쓰기 기록으로 낸다. 형식은 fc/dq4/docs/dq4-sound-format.md.

사용:
  python fc/dq4/tools/dq4sound.py rom/dq4.nes songs              곡 표(번호, 데이터 뱅크, 채널 주소, 템포, 길이·되풀이)
  python fc/dq4/tools/dq4sound.py rom/dq4.nes sfx                효과음 표(번호 80~C8, 쓰는 채널, 주소, 길이)
  python fc/dq4/tools/dq4sound.py rom/dq4.nes score N            곡 N(16진, 80 이상은 효과음)의 채널별 악보 텍스트
  python fc/dq4/tools/dq4sound.py rom/dq4.nes notes N            드라이버를 돌려 얻은 음 사건(틱, 채널, 음높이, 길이, 게이트)
  python fc/dq4/tools/dq4sound.py rom/dq4.nes apu N [--frames F]  드라이버를 돌려 프레임마다 APU($4000~$4017) 쓰기
  python fc/dq4/tools/dq4sound.py rom/dq4.nes compare N DIR      lua/soundlog.lua 기록(DIR/sound.txt)과 위 apu 를 프레임마다 견줌
  python fc/dq4/tools/dq4sound.py rom/dq4.nes maps               맵·필드·탈것 → 곡(19:$803B 를 따라 롬 표에서)
  python fc/dq4/tools/dq4sound.py rom/dq4.nes calls              롬에서 곡·효과음을 부르는 자리(LDA #n 뒤 소리 입구, BRK n FB, 대사 EE n)
  python fc/dq4/tools/dq4sound.py rom/dq4.nes export [OUT]       곡·효과음 전부를 OUT(기본 work/dq4-sound)에 .mid·.txt 로

음원 결과물(.mid·.txt)은 롬에서 뽑은 저작권 데이터라 공개 저장소에 두지 않는다(work/ 나 비공개 에셋 저장소에만).

근거 루틴(고정 뱅크 1F): 입구 표 $C01C(초기화 $F088)·$C01F(곡·효과음 시작 $EF59)·$C022(페이드아웃 $F055)·
$C025(페이드인 시작 $F05C)·$C028(주 음량 $EED3)·$C02B(곡 끝 기다림 $F0B2), NMI 마다 $C019 → $E685.
악보 해석 $E77A(바이트 $E7DA, 명령 표 $E810, 음 $E9A8), 음높이 출력 $EAFA(주기 표 $EC83), 음량 $ED67(엔벨로프 19:$8337).
곡 표 19:$814E(곡마다 채널 4개 주소 8바이트), 곡 데이터 뱅크 19:$82FE, 효과음 표 19:$A16B, 비브라토 표 19:$8842.
"""
import argparse
import json
import math
import os
import struct
import sys

import dq4bank
from dq4cpu import CPU

SONG_TABLE, SONG_BANKS, NSONGS = 0x814E, 0x82FE, 0x36
SFX_TABLE, NSFX = 0xA16B, 0x38    # 표는 첫 효과음 자료($A1DB) 바로 앞에서 끝남. B2 는 0000(빈 칸)
ENV_TABLE, VIB_TABLE = 0x8337, 0x8842
PERIODS = 0xEC83            # 1F: 주기 표(워드 99개)
CMD_TABLE = 0xE810
INIT, PLAY, TICK = 0xF088, 0xEF59, 0xE685
APU_CLOCK, FPS = 1789773, 60.0988
CH_NAMES = ['pulse1', 'pulse2', 'triangle', 'noise', 'sfx']
NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']

# 명령 바이트 → (이름, 인자 바이트 수). $E810 표를 읽은 뜻.
COMMANDS = {
    0xFF: ('tempo', 1), 0xFE: ('jump', 2), 0xFD: ('return', 0), 0xFC: ('end-flag', 0),
    0xFB: ('transpose', 1), 0xFA: ('loop', 2), 0xF9: ('loop2', 1), 0xF8: ('follow-off', 0),
    0xF7: ('follow-on', 0), 0xF6: ('master-vol', 1), 0xF5: ('master-vol+', 0), 0xF4: ('master-vol-', 0),
    0xF3: ('rhythm', 2), 0xF2: ('sweep', 1), 0xF1: ('detune', 1), 0xF0: ('vibrato', 1),
    0xEF: ('fade-out', 0), 0xEE: ('ch-vol', 1), 0xED: ('fixed-vol', 1), 0xEC: ('rhythm-off', 0),
    0xEB: ('sync', 0), 0xEA: ('ch-vol+', 0), 0xE9: ('ch-vol-', 0), 0xE8: ('transpose+', 1),
    0xE1: ('envelope', 1),
}


def load(path):
    with open(path, 'rb') as f:
        data = f.read()
    return data[16:16 + 0x80000]


def rd(prg, bank, addr):
    return prg[dq4bank.prg_offset(bank, addr)]


def rd16(prg, bank, addr):
    return rd(prg, bank, addr) | rd(prg, bank, addr + 1) << 8


def song_entry(prg, n):
    """곡 n 의 (데이터 뱅크, [채널 주소 4개], 표 값). 뱅크가 있으면 표 값은 그 뱅크 $8000 표의 번호이고($C3CE),
    그 표에서는 세 채널만 읽어 노이즈는 늘 19:$8335(빈 채널)다($EF9D~$EFB6)."""
    bank = rd(prg, 0x19, SONG_BANKS + n)
    raw = [rd16(prg, 0x19, SONG_TABLE + 8 * n + 2 * i) for i in range(4)]
    if bank == 0:
        return 0x19, raw, raw
    return bank, [rd16(prg, bank, 0x8000 + 2 * (v & 0xFF)) for v in raw[:3]] + [EMPTY], raw


EMPTY = 0x8335


def song_unused(prg, n):
    """채널이 모두 빈 채널이거나 주소가 RAM($0000)인 곡: 표에 자리만 있음."""
    _, ptrs, _ = song_entry(prg, n)
    return all(p in (0x8334, EMPTY) or p < 0x8000 for p in ptrs)


def chan_bank(bank, y):
    return 0x19 if y == 3 else bank


def sfx_entry(prg, i):
    """효과음 0x80+i 의 (채널, 주소). 표 워드 bit15 가 0 이면 노이즈 채널을 쓴다($EF25)."""
    w = rd16(prg, 0x19, SFX_TABLE + 2 * i)
    return ('noise' if w < 0x8000 else 'pulse2'), w | 0x8000


def period(prg, idx):
    return rd16(prg, 0x1F, PERIODS + 2 * idx)


def midi_of_period(p, tri=False):
    f = APU_CLOCK / ((32 if tri else 16) * (p + 1))
    return 69 + 12 * math.log2(f / 440.0)


def note_name(m):
    m = round(m)
    return f'{NOTE_NAMES[m % 12]}{m // 12 - 1}'


def tick_rate(tempo, frames=30000):
    """템포 → 프레임마다 평균 틱 수. $E6BE~$E6F4 를 그대로 따른다: $BD += 템포가 넘치면 $96 을 빼며 틱을 돌고,
    $BD < $6A 면 받아올림 없이($97) 한 번 더 뺀다. 그래서 150 이하는 템포/150 이고, 그 위는 조금 빠르다."""
    bd, ticks = 0xFF, 0
    for _ in range(frames):
        v = bd + tempo
        bd = v & 0xFF
        if v < 0x100:
            continue
        borrow = 0
        while True:
            v = bd - 0x96 - borrow
            bd = v & 0xFF
            ticks += 1
            if bd >= 0x6A:
                break
            borrow = 1
    return ticks / frames


def pitch_index(n, tr, tri):
    """$ED49: 음 번호 + 3 + 이조, 삼각파는 39 이상을 4E 부터의 표로."""
    i = (n + 3 + tr) & 0xFF
    if tri and i >= 0x39:
        i = i - 0x39 + 0x4E
    return i


# --- 드라이버 실행 ---------------------------------------------------------------

class SoundCPU(CPU):
    def __init__(self, prg):
        super().__init__(prg, 0x19)
        self.apu = []
        self.hooks[0xFF94] = self._bank
        self.stubs.add(0xFF94)

    def _bank(self, cpu):
        self.bank = self.a & 0x1F

    def wr(self, addr, v):
        addr &= 0xFFFF
        if 0x4000 <= addr <= 0x4017:
            self.apu.append((addr, v & 0xFF))
        super().wr(addr, v)


class Run:
    """곡 n 을 드라이버 그대로 돌린다. 틱·음 사건·템포 바뀜·되풀이 지점을 모은다."""

    def __init__(self, prg, n, max_frames=40000, loop=True, stop=True):
        self.prg, self.n = prg, n
        c = self.cpu = SoundCPU(prg)
        c.a = 0
        c.call(INIT)
        # 초기화가 건 효과음 80(멈춤)은 첫 NMI 에서 끝난다. 게임 중에는 이미 끝나 있으므로 한 번 돌려 둔다.
        c.call(TICK)
        # 곡 0 은 채널마다 음을 쓰지 않으므로 「소리 없음」(FF)으로 둔다. 효과음이 끝날 때 펄스2 를 되돌리는 $EC57 이 이 값을 본다
        for y in range(5):
            c.ram[0x0646 + y] = 0xFF
        c.apu.clear()
        self.tick = 0
        self.events = []       # (틱, 채널 Y, 음 번호 A2, 길이, 게이트, 엔벨로프, 이조, 고정 음량, 주소)
        self.tempos = [(0, None)]
        self.frames = []       # 프레임마다 [(주소, 값)…]
        self.ticks_at = []     # 프레임 끝의 틱 수
        self.loop_start = self.loop_len = None
        c.hooks[0xE6CB] = self._tick
        c.hooks[0xEABB] = self._note
        c.hooks[0xE96B] = self._tempo
        self._seen = {}
        self.sfx = n >= 0x80
        c.a = n
        c.call(PLAY)
        # 효과음 채널은 템포와 상관없이 프레임마다 한 틱이다(템포 150 과 같음)
        self.tempos[0] = (0, 150 if self.sfx else c.ram[0xBC])
        self.frames.append(list(c.apu))
        c.apu.clear()
        for _ in range(max_frames):
            if self.sfx:
                # 효과음은 채널 4($0628)만 틱마다가 아니라 프레임마다 돈다
                self._sfx_tick()
            c.steps = 0
            c.call(TICK)
            self.frames.append(list(c.apu))
            c.apu.clear()
            self.ticks_at.append(self.tick)
            if stop and self.ended() or loop and self.loop_start is not None:
                break

    def ended(self):
        r = self.cpu.ram
        if self.sfx:
            return r[0x0628] == 0
        return all(r[0x0620 + 2 * y] == 0 for y in range(4))

    def _state(self):
        r, w = self.cpu.ram, self.cpu.wram
        key = [w[0x6BFC - 0x6000], r[0xBC], r[0xB0] & 0x0F]
        for y in range(4):
            x = 2 * y
            key += [r[0xA6 + x], r[0xA7 + x], r[0x0620 + x], r[0x0621 + x], r[0x064B + y],
                    r[0x0634 + x], r[0x0635 + x], w[0x6BFE + x - 0x6000], r[0xB1 + y] if y < 3 else 0,
                    w[0x6C09 + y - 0x6000] if y < 3 else 0]
        return tuple(key)

    def _sfx_tick(self):
        self.tick += 1
        if self.loop_start is not None:
            return
        r = self.cpu.ram
        k = (r[0xAE], r[0xAF], r[0x0628], r[0x0629], r[0x064F], r[0xBB] & 0x20)
        if k in self._seen:
            self.loop_start = self._seen[k]
            self.loop_len = self.tick - self._seen[k]
        else:
            self._seen[k] = self.tick

    def _tick(self, cpu):
        if self.sfx:
            return
        self.tick += 1
        if self.loop_start is not None:
            return
        k = self._state()
        if k in self._seen:
            self.loop_start = self._seen[k]
            self.loop_len = self.tick - self._seen[k]
        else:
            self._seen[k] = self.tick

    def _tempo(self, cpu):
        self.tempos.append((self.tick, cpu.ram[0xBC]))

    def _note(self, cpu):
        r, w = cpu.ram, cpu.wram
        y, x = r[0xA4], r[0xA5]
        ptr = r[0xA6 + x] | r[0xA7 + x] << 8
        tr = w[0x6BFE + x - 0x6000] if x < 8 else 0
        fixed = w[0x6BFA + y - 0x6000] if y < 4 else 0xFF
        t = self.tick
        self.events.append((t, y, r[0xA2], r[0x0620 + x], r[0x062B + x], r[0x063D + x], tr, fixed, ptr,
                            len(self.frames)))


def notes(run):
    """음 사건 → [(채널, 시작 틱, 길이, MIDI 음높이 실수, 음 번호, 게이트)]. 49 는 쉼, 4A 는 앞 음 잇기."""
    prg = run.prg
    out, last = [], {}
    sfx_ch = (3 if sfx_entry(prg, run.n - 0x80)[0] == 'noise' else 1) if run.sfx else None
    for t, y, n, dur, gate, env, tr, fixed, ptr, frame in run.events:
        if dur == 0:
            continue
        ch = sfx_ch if run.sfx else y
        if n == 0x4A and ch in last:
            i = last[ch]
            c, s, _, m, nn, g = out[i]
            out[i] = (c, s, t + dur - s, m, nn, g)
            continue
        if n == 0x49:
            last.pop(ch, None)
            continue
        if ch == 3:
            m = None
        else:
            idx = pitch_index(n, tr, ch == 2 and not run.sfx)
            m = midi_of_period(period(prg, idx), ch == 2)
        out.append((ch, t, dur, m, n, gate))
        last[ch] = len(out) - 1
    return out


# --- 정적 악보 --------------------------------------------------------------------

def decode_stream(prg, bank, start, stops=()):
    """채널 바이트열을 주소 순으로 풀어 [(주소, 바이트들, 뜻)] 를 낸다. jump 의 목적지가 return 으로 끝나면 이어 읽는다.
    다른 채널의 시작 주소(stops)에 닿으면 멈춘다: 드라이버는 그대로 읽어 가지만 그 뒤는 그 채널의 악보다."""
    lines, seen = {}, set()

    def block(addr, depth=0):
        a = addr
        while a not in seen:
            if a in stops:
                lines[a] = (a, 0, f'(다른 채널 시작 ${a:04X} 로 이어 읽음)')
                return False
            seen.add(a)
            b = rd(prg, bank, a)
            if b in COMMANDS:
                name, n = COMMANDS[b]
                args = [rd(prg, bank, a + 1 + i) for i in range(n)]
                size = 1 + n
                text = name
                if b == 0xFE:
                    tgt = args[0] | args[1] << 8
                    text = f'jump ${tgt:04X}'
                    lines[a] = (a, size, text)
                    ret = depth < 4 and tgt not in seen and block(tgt, depth + 1)
                    if ret is not True:
                        return False
                    a += size
                    continue
                if b == 0xFD:
                    lines[a] = (a, size, 'return')
                    return True
                if b == 0xFA:
                    tgt = a + 3 + args[1] - 0x100
                    text = f'loop x{args[0]} → ${tgt:04X}'
                elif b == 0xF9:
                    tgt = a + 2 + args[0] - 0x100
                    text = f'loop x2 → ${tgt:04X}'
                elif b == 0xF3:
                    text = f'rhythm ${args[0] | args[1] << 8:04X}'
                elif b == 0xE1:
                    text = f'envelope {args[0]:02X}'
                elif b == 0xFF:
                    text = f'tempo {args[0]} ({tick_rate(args[0]) * FPS:.1f} 틱/초)'
                elif n:
                    text = name + ' ' + ' '.join(f'{v:02X}' for v in args)
                lines[a] = (a, size, text)
                a += size
                continue
            grp, n = divmod(b, 75)
            size, extra = 1, ''
            if grp == 1:
                d = rd(prg, bank, a + 1)
                size = 2
                extra = f' len={d & 0x7F}'
                if d & 0x80:
                    extra += f' gate={rd(prg, bank, a + 2) & 0x7F}'
                    size = 3
                if d & 0x7F == 0:
                    lines[a] = (a, size, ('rest' if n == 0x49 else f'note {n:02X}') + extra + ' (끝)')
                    return False
            elif grp >= 2:
                extra = f' gate={rd(prg, bank, a + 1) & 0x7F}'
                size = 2
            if n == 0x49:
                text = 'rest'
            elif n == 0x4A:
                text = 'tie'
            else:
                text = f'note {n:02X}'
            lines[a] = (a, size, text + extra)
            a += size
        lines.setdefault(a, (a, 0, f'(→ ${a:04X} 로 되돌아감)'))
        return False

    block(start)
    out = []
    for a in sorted(lines):
        a, size, text = lines[a]
        raw = ' '.join(f'{rd(prg, bank, a + i):02X}' for i in range(size))
        out.append((a, raw, text))
    return out


def score_text(prg, n):
    lines = []
    if n >= 0x80:
        ch, addr = sfx_entry(prg, n - 0x80)
        lines.append(f'효과음 {n:02X}: {ch}, 19:${addr:04X}')
        chans = [('sfx', 0x19, addr)]
    else:
        bank, ptrs, raw = song_entry(prg, n)
        lines.append(f'곡 {n:02X}: 뱅크 {bank:02X}, 채널 ' + ' '.join(f'${p:04X}' for p in ptrs))
        chans = [(CH_NAMES[i], chan_bank(bank, i), p) for i, p in enumerate(ptrs)]
    for name, bank, p in chans:
        lines.append(f'\n[{name}] {bank:02X}:${p:04X}')
        if p == EMPTY and bank == 0x19:
            lines.append('  (빈 채널)')
            continue
        stops = {q for _, b, q in chans if b == bank and q != p}
        start = p
        if name == 'pulse1':
            # 곡의 첫 바이트는 템포($EFEB → $BC)
            t = rd(prg, bank, p)
            lines.append(f'  {p:04X}  {t:02X}        tempo {t} ({tick_rate(t) * FPS:.1f} 틱/초)')
            start = p + 1
        for a, raw, text in decode_stream(prg, bank, start, stops):
            lines.append(f'  {a:04X}  {raw:<9} {text}')
    return '\n'.join(lines)


# --- MIDI --------------------------------------------------------------------------

PPQ = 24
PROGRAMS = [80, 81, 33, 0]


def vlq(v):
    out = [v & 0x7F]
    v >>= 7
    while v:
        out.append(0x80 | (v & 0x7F))
        v >>= 7
    return bytes(reversed(out))


def track(events):
    events.sort(key=lambda e: (e[0], e[1]))
    out, t0 = bytearray(), 0
    for t, _, data in events:
        out += vlq(t - t0) + data
        t0 = t
    out += vlq(0) + b'\xff\x2f\x00'
    return b'MTrk' + struct.pack('>I', len(out)) + bytes(out)


NOISE_DRUMS = [42] * 4 + [38] * 5 + [36] * 7


def midi_bytes(run, title):
    ns = notes(run)
    end = max([t + d for _, t, d, *_ in ns] + [run.tick])
    if run.loop_start is not None:
        end = run.loop_start + run.loop_len
    conductor = [(0, 0, b'\xff\x03' + vlq(len(title.encode())) + title.encode())]
    for t, tempo in run.tempos:
        if tempo:
            us = round(PPQ / (FPS * tick_rate(tempo)) * 1e6)
            conductor.append((t, 1, b'\xff\x51\x03' + us.to_bytes(3, 'big')))
    if run.loop_start is not None:
        conductor.append((run.loop_start, 2, b'\xff\x06\x09loopStart'))
        conductor.append((end, 2, b'\xff\x06\x07loopEnd'))
    tracks = [track(conductor)]
    for ch in range(4):
        mch = 9 if ch == 3 else ch
        ev = [(0, 0, b'\xff\x03' + vlq(len(CH_NAMES[ch])) + CH_NAMES[ch].encode())]
        if ch != 3:
            ev.append((0, 1, bytes([0xC0 | mch, PROGRAMS[ch]])))
        for c, t, d, m, n, g in ns:
            if c != ch or t >= end:
                continue
            key = NOISE_DRUMS[n & 0x0F] if ch == 3 else max(0, min(127, round(m)))
            # 펄스는 게이트가 끝나면 엔벨로프의 떼기 쪽으로 넘어가므로($E783) 게이트를 음 길이로 둔다
            length = min(g if ch < 2 and 0 < g < d else d, end - t)
            ev.append((t, 3, bytes([0x90 | mch, key, 100])))
            ev.append((t + max(1, length), 2, bytes([0x80 | mch, key, 0])))
        tracks.append(track(ev))
    return b'MThd' + struct.pack('>IHHH', 6, 1, len(tracks), PPQ) + b''.join(tracks)


# --- 표 ---------------------------------------------------------------------------

def cmd_songs(prg, args):
    for n in range(NSONGS):
        bank, ptrs, _ = song_entry(prg, n)
        if song_unused(prg, n):
            print(f'{n:02X}  (빈 곡)')
            continue
        r = Run(prg, n, max_frames=args.frames)
        tempo = r.tempos[0][1]
        loop = f'되풀이 {r.loop_start}+{r.loop_len}틱' if r.loop_start is not None else f'끝 {r.tick}틱'
        secs = len(r.frames) / FPS
        print(f'{n:02X}  뱅크 {bank:02X}  ' + ' '.join(f'{p:04X}' for p in ptrs)
              + f'  템포 {tempo:3d}  음 {len(notes(r)):4d}  {loop}  ({secs:.1f}초)')


def sfx_unused(prg, i):
    return rd16(prg, 0x19, SFX_TABLE + 2 * i) == 0


def cmd_sfx(prg, args):
    for i in range(NSFX):
        if sfx_unused(prg, i):
            print(f'{0x80 + i:02X}  (빈 칸)')
            continue
        ch, addr = sfx_entry(prg, i)
        r = Run(prg, 0x80 + i, max_frames=2000)
        how = f'되풀이 {r.loop_start}+{r.loop_len}프레임' if r.loop_start is not None else f'{len(r.frames) - 1}프레임'
        print(f'{0x80 + i:02X}  {ch:6s} 19:${addr:04X}  음 {len(notes(r)):3d}  {how}')


def notes_text(r):
    lines = [f'음 사건(드라이버 실행, 템포 {r.tempos[0][1]} 에서 초당 {tick_rate(r.tempos[0][1]) * FPS:.2f}틱)']
    for c, t, d, m, n, g in notes(r):
        name = f'noise {n & 0x0F:X}' if m is None else f'{note_name(m)} ({m:.2f})'
        lines.append(f'{t:6d} {CH_NAMES[c]:8s} {name:16s} len={d:3d} gate={g:3d} n={n:02X}')
    for t, tempo in r.tempos[1:]:
        lines.append(f'템포 바뀜 {t}틱: {tempo}')
    if r.loop_start is not None:
        lines.append(f'되풀이: {r.loop_start}틱부터 {r.loop_len}틱')
    else:
        lines.append(f'끝: {r.tick}틱')
    return '\n'.join(lines)


def cmd_notes(prg, args):
    print(notes_text(Run(prg, args.n, max_frames=args.frames)))


def cmd_apu(prg, args):
    r = Run(prg, args.n, max_frames=args.frames, loop=False)
    for f, ws in enumerate(r.frames):
        if ws:
            print(f'{f:5d} ' + ' '.join(f'{a & 0xFF:02X}={v:02X}' for a, v in ws))


def read_log(path):
    """lua/soundlog.lua 의 sound.txt: 'S 프레임 A A′' 시작, 'N 프레임' NMI 소리 틱, 'W 프레임 주소 값' APU 쓰기.
    첫 S 의 A′ 부터, 다른 번호의 S 가 나오기 전까지를 NMI 마다 묶는다."""
    groups, start, cur = [], None, None
    with open(path) as f:
        for line in f:
            p = line.split()
            if not p:
                continue
            if p[0] == 'S' and start is None:
                start = int(p[3], 16)
                cur = []
                groups.append(cur)
            elif p[0] == 'S' and int(p[3], 16) != start:
                # 다른 소리가 새로 시작되면 거기까지만 견준다
                break
            elif p[0] == 'N' and start is not None:
                cur = []
                groups.append(cur)
            elif p[0] == 'W' and cur is not None:
                cur.append((int(p[2], 16), int(p[3], 16)))
    return start, groups


REG_CH = {0: 0, 1: 0, 2: 0, 3: 0, 4: 1, 5: 1, 6: 1, 7: 1, 8: 2, 0xA: 2, 0xB: 2, 0xC: 3, 0xE: 3, 0xF: 3}


def cmd_compare(prg, args):
    start, groups = read_log(os.path.join(args.dir, 'sound.txt'))
    if start is None:
        sys.exit('sound.txt 에 시작(S)이 없음')
    n = args.n if args.n is not None else start
    r = Run(prg, n, max_frames=len(groups) + 1, loop=False, stop=n >= 0x80)
    chans = [int(c) for c in args.channels.split(',')]
    if n >= 0x80:
        # 효과음이 끝난 프레임부터는 게임에서 울리던 곡이 채널을 되찾으므로 거기까지만 견준다
        groups = groups[:len(r.frames) - 1]
        chans = [3 if sfx_entry(prg, n - 0x80)[0] == 'noise' else 1]
    total = bad = 0
    first = None
    for f, real in enumerate(groups):
        emu = r.frames[f] if f < len(r.frames) else []
        a = [(x, v) for x, v in real if REG_CH.get(x & 0x1F) in chans]
        b = [(x, v) for x, v in emu if REG_CH.get(x & 0x1F) in chans]
        total += 1
        if a != b:
            bad += 1
            if first is None:
                first = (f, a, b)
    kind = '효과음' if n >= 0x80 else '곡'
    print(f'{kind} {n:02X}: 프레임 {total}개 중 다름 {bad}개 (채널 {",".join(CH_NAMES[c] for c in chans)})')
    ok, miss = check_notes(r, groups, chans)
    print(f'해독한 음 {ok + len(miss)}개 중 시작 프레임의 실측 주기·노이즈 값이 맞은 것 {ok}개')
    for m in miss[:5]:
        print('  안 맞음', m)
    bad += len(miss)
    if first:
        f, a, b = first
        print(f'처음 다른 프레임 {f}:\n  실측 ' + ' '.join(f'{x & 0xFF:02X}={v:02X}' for x, v in a)
              + '\n  해독 ' + ' '.join(f'{x & 0xFF:02X}={v:02X}' for x, v in b))
    sys.exit(1 if bad else 0)


def check_notes(run, groups, chans):
    """해독한 음마다 시작 프레임의 실측 APU 쓰기에 그 음의 주기(펄스·삼각) 또는 노이즈 주기 값이 있는지 본다."""
    ok, miss = 0, []
    for t, y, n, dur, gate, env, tr, fixed, ptr, frame in run.events:
        if run.sfx:
            y = 3 if sfx_entry(run.prg, run.n - 0x80)[0] == 'noise' else 1
        if dur == 0 or n in (0x49, 0x4A) or y not in chans or frame >= len(groups):
            continue
        real = groups[frame]
        if y == 3:
            vals = [v for a, v in real if a == 0x400E]
            good = (n & 0x0F) in [v & 0x0F for v in vals]
            want = f'noise {n & 0x0F:X}'
        else:
            base = 0x4000 + 4 * y
            p = period(run.prg, pitch_index(n, tr, y == 2 and not run.sfx))
            lo = [v for a, v in real if a == base + 2]
            hi = [v for a, v in real if a == base + 3]
            good = bool(lo) and lo[-1] == p & 0xFF and (not hi or hi[-1] & 7 == p >> 8)
            want = f'주기 {p:03X}'
        if good:
            ok += 1
        else:
            miss.append((frame, CH_NAMES[y], f'n={n:02X}', want,
                         ' '.join(f'{a & 0xFF:02X}={v:02X}' for a, v in real)))
    return ok, miss


def cmd_score(prg, args):
    print(score_text(prg, args.n))


def cmd_export(prg, args):
    out = args.out
    os.makedirs(os.path.join(out, 'songs'), exist_ok=True)
    os.makedirs(os.path.join(out, 'sfx'), exist_ok=True)
    index = {'songs': [], 'sfx': []}
    for n in list(range(NSONGS)) + [0x80 + i for i in range(NSFX)]:
        sub = 'sfx' if n >= 0x80 else 'songs'
        if n < 0x80 and song_unused(prg, n) or n >= 0x80 and sfx_unused(prg, n - 0x80):
            continue
        r = Run(prg, n, max_frames=args.frames if n < 0x80 else 2000)
        base = os.path.join(out, sub, f'{n:02X}')
        with open(base + '.mid', 'wb') as f:
            f.write(midi_bytes(r, f'DQ4 {"sfx" if n >= 0x80 else "song"} {n:02X}'))
        with open(base + '.txt', 'w') as f:
            f.write(score_text(prg, n) + '\n\n' + notes_text(r) + '\n')
        if n < 0x80:
            bank, ptrs, _ = song_entry(prg, n)
            where = [f'{chan_bank(bank, y):02X}:{p:04X}' for y, p in enumerate(ptrs)]
        else:
            ch, addr = sfx_entry(prg, n - 0x80)
            where = [f'19:{addr:04X} {ch}']
        index[sub].append({'id': f'{n:02X}', 'files': [f'{n:02X}.mid', f'{n:02X}.txt'], 'channels': where,
                           'tempo': r.tempos[0][1], 'notes': len(notes(r)), 'ticks': r.tick,
                           'loop_start': r.loop_start, 'loop_len': r.loop_len,
                           'seconds': round(len(r.frames) / FPS, 1)})
    for sub, items in index.items():
        with open(os.path.join(out, sub, 'index.json'), 'w') as f:
            json.dump(items, f, ensure_ascii=False, indent=1)
    print(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('rom')
    sub = ap.add_subparsers(dest='cmd', required=True)
    s = sub.add_parser('songs')
    s.add_argument('--frames', type=int, default=40000)
    sub.add_parser('sfx')
    for name in ('score', 'notes', 'apu'):
        s = sub.add_parser(name)
        s.add_argument('n', type=lambda v: int(v, 16))
        s.add_argument('--frames', type=int, default=40000 if name == 'notes' else 600)
    s = sub.add_parser('compare')
    s.add_argument('n', type=lambda v: int(v, 16), nargs='?')
    s.add_argument('dir')
    s.add_argument('--channels', default='0,1,2,3')
    sub.add_parser('maps')
    sub.add_parser('calls')
    s = sub.add_parser('export')
    s.add_argument('out', nargs='?', default='work/dq4-sound')
    s.add_argument('--frames', type=int, default=40000)
    args = ap.parse_args()
    prg = load(args.rom)
    {'songs': cmd_songs, 'sfx': cmd_sfx, 'score': cmd_score, 'notes': cmd_notes, 'apu': cmd_apu,
     'compare': cmd_compare, 'export': cmd_export, 'maps': cmd_maps, 'calls': cmd_calls}[args.cmd](prg, args)


# 19:$803B(맵 곡 고르기)가 읽는 표
LEAD_SONGS, FIELD_SONGS, CHAPTER_SONGS, TYPE_SONGS, MAP_SONGS = 0x810B, 0x8112, 0x8116, 0x811C, 0x8124
PERSONS = ['勇者', 'クリフト', 'ミネア', 'マーニャ', 'ブライ', 'トルネコ', 'ライアン', 'アリーナ']
# 맵 레코드 순번(표 안 오프셋 / 3)마다 $803B 가 따로 보는 조건
MAP_SPECIAL = {
    0x00: '3장($615A=2)이고 $6287 bit7 이 꺼져 있으면 맵 갈래 곡',
    0x05: '5장($615A≥4)이고 플래그 $6295&02 가 켜져 있으면 04',
    0x09: '$62AA bit0 이 꺼져 있으면 0C',
    0x0B: '5장이면 03, 아니면 플래그 $6284&40 이 켜져 있을 때만 이 곡(꺼져 있으면 03)',
    0x0C: '5장이면 03, 아니면 플래그 $6284&40 이 켜져 있을 때만 이 곡(꺼져 있으면 03)',
    0x0D: '5장이면 03, 아니면 플래그 $6284&40 이 켜져 있을 때만 이 곡(꺼져 있으면 03)',
}


def cmd_maps(prg, args):
    b = lambda a: rd(prg, 0x19, a)
    print('맵 안($41 bit7)')
    print('  $6285 bit3 이 켜져 있으면 어디서나 0E')
    for i in range(14):
        g, k, song = (b(MAP_SONGS + 3 * i + j) for j in range(3))
        if g == 0xFE:
            continue
        where = f'{g:02X}/{"**" if k == 0xFF else f"{k:02X}"}'
        note = MAP_SPECIAL.get(i, '')
        print(f'  {where}  → {song:02X}' + (f'  ({note})' if note else ''))
    print('  그 밖: 맵 갈래 $07BA & 7F 로 ' + ', '.join(f'{t} → {b(TYPE_SONGS + t):02X}' for t in range(8)))
    print('탈것($0515 ≠ 0): 1 → 09, 그 밖 → 13')
    print('필드($65 ≠ 0): ' + ', '.join(f'필드 {f} → {b(FIELD_SONGS + f):02X}' for f in (1, 2, 3)))
    print('필드 0: 1~4장 ' + ', '.join(f'{c + 1}장 → {b(CHAPTER_SONGS + c):02X}' for c in range(4)))
    print(f'  5장, $6292 ≠ FF → {b(CHAPTER_SONGS + 4):02X}')
    print('  5장, $6292 = FF: 일행 첫 자리 인물(x3 2B 63 41)의 곡 '
          + ', '.join(f'{PERSONS[i]} {b(LEAD_SONGS + i):02X}' for i in range(1, 8)))
    print(f'    첫 자리가 勇者면 x3 62 63 41 이 1 일 때 {b(LEAD_SONGS):02X} 아니면 {b(CHAPTER_SONGS + 5):02X}')


def code_calls(prg):
    """(뱅크, 주소, 방식, 번호) — LDA #n 바로 뒤 소리 입구, BRK n FB."""
    out = []
    pats = {bytes([0x20, 0x1F, 0xC0]): 'JSR $C01F', bytes([0x4C, 0x1F, 0xC0]): 'JMP $C01F',
            bytes([0x20, 0x25, 0xC0]): 'JSR $C025', bytes([0x00, 0x03, 0x9F]): 'BRK 03 9F',
            bytes([0x00, 0x05, 0x9F]): 'BRK 05 9F'}
    for bank in range(0x20):
        base = bank * 0x4000
        lo = 0xC000 if bank in (0x0F, 0x1F) else 0x8000
        seg = prg[base:base + 0x4000]
        for i in range(len(seg) - 4):
            if seg[i] == 0xA9 and bytes(seg[i + 2:i + 5]) in pats:
                out.append((bank, lo + i, pats[bytes(seg[i + 2:i + 5])], seg[i + 1]))
            if seg[i] == 0x00 and seg[i + 2] == 0xFB:
                out.append((bank, lo + i, 'BRK n FB', seg[i + 1]))
    return out


def message_calls(rom_bytes):
    import dq4text
    rom = dq4text.Rom(rom_bytes)
    out = []
    for m in dq4text.valid_messages(rom):
        bs = dq4text.message_bytes(rom, m)
        for i in range(len(bs) - 1):
            if bs[i] == 0xEE:
                n = bs[i + 1]
                out.append((m, n if n < 0x40 else n + 0x40))
    return out


def cmd_calls(prg, args):
    by = {}
    for bank, addr, how, n in code_calls(prg):
        by.setdefault(n, []).append(f'{bank:02X}:{addr:04X}' + ('' if how == 'BRK n FB' else f'({how})'))
    msgs = {}
    with open(args.rom, 'rb') as f:
        for m, n in message_calls(f.read()):
            msgs.setdefault(n, []).append(f'{m:04X}')
    for n in sorted(set(by) | set(msgs)):
        if n >= 0x80 + NSFX and n not in msgs:
            continue
        parts = []
        if n in by:
            parts.append(f'코드 {len(by[n])}곳 ' + ' '.join(by[n][:8]) + (' …' if len(by[n]) > 8 else ''))
        if n in msgs:
            parts.append(f'대사 {len(msgs[n])}개 ' + ' '.join(msgs[n][:6]) + (' …' if len(msgs[n]) > 6 else ''))
        print(f'{n:02X}  ' + ' / '.join(parts))


if __name__ == '__main__':
    main()
