"""DQ4(FC) 곡·효과음을 롬에서 풀어 악보 텍스트·MIDI·APU 쓰기 기록으로 낸다. 형식은 fc/dq4/docs/dq4-sound-format.md.

사용:
  python fc/dq4/tools/dq4sound.py rom/dq4.nes songs              곡 표(번호, 데이터 뱅크, 채널 주소, 템포, 길이·되풀이)
  python fc/dq4/tools/dq4sound.py rom/dq4.nes sfx                효과음 표(번호 80~C8, 쓰는 채널, 주소, 길이)
  python fc/dq4/tools/dq4sound.py rom/dq4.nes score N            곡 N(16진, 80 이상은 효과음)의 채널별 악보 텍스트
  python fc/dq4/tools/dq4sound.py rom/dq4.nes notes N            드라이버를 돌려 얻은 음 사건(틱, 채널, 음높이, 길이, 게이트)
  python fc/dq4/tools/dq4sound.py rom/dq4.nes apu N [--frames F]  드라이버를 돌려 프레임마다 APU($4000~$4017) 쓰기
  python fc/dq4/tools/dq4sound.py rom/dq4.nes compare N DIR      lua/soundlog.lua 기록(DIR/sound.txt)과 위 apu 를 프레임마다 견줌
  python fc/dq4/tools/dq4sound.py rom/dq4.nes maps               맵·필드·탈것 → 곡(19:$803B 를 따라 롬 표에서)
  python fc/dq4/tools/dq4sound.py rom/dq4.nes calls              롬에서 곡·효과음을 부르는 자리(LDA #n 뒤 소리 입구, BRK n FB, 인물 블록 30 n, 대사 EE n)
  python fc/dq4/tools/dq4sound.py rom/dq4.nes export [OUT] [--flac]  곡·효과음 전부를 OUT(기본 work/dq4-sound)에
      .txt·.mid·.json·.musicxml·악보 SVG(·.flac) 와 index.json, dq4.nsf 로

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
        self.events = []       # (틱, 채널 Y, 음 번호 A2, 길이, 게이트, 엔벨로프, 이조, 고정 음량, 주소, 프레임)
        self.extra = []        # 음 사건마다 채널 음량·미세 음높이·비브라토·주 음량
        self.tempos = [(0, None)]
        self.frames = []       # 프레임마다 [(주소, 값)…]
        self.ticks_at = []     # 프레임 끝의 틱 수
        self.loop_start = self.loop_len = None
        c.hooks[0xE6CB] = self._tick
        c.hooks[0xEABB] = self._note
        c.hooks[0xE96B] = self._tempo
        # 음량: 엔벨로프 값 × 채널·주 음량($ED67). 프레임마다 (틱, 채널 Y, 엔벨로프·고정 음량 값, 곱하는 쪽 음량 0~F)
        self.vols = []
        c.hooks[0xEE61] = lambda cpu: self.vols.append((self.tick, cpu.ram[0xA4], cpu.a & 0x0F, cpu.ram[0x10]))
        c.hooks[0xEDC7] = lambda cpu: self.vols.append((self.tick, cpu.ram[0xA4], cpu.a & 0x0F, cpu.ram[0xB0] & 0x0F))
        c.hooks[0xEE68] = lambda cpu: cpu.x == 8 and self.vols.append((self.tick, 4, cpu.a & 0x0F, 0x0F))
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
        self.extra.append({'ch_vol': r[0xB1 + y] >> 4 if y < 3 else None,
                           'detune': r[0xB1 + y] & 0x0F if y < 3 else None,
                           'vibrato': r[0xB5 + y] if y < 3 and r[0xB5 + y] != 0xFF else None,
                           'master_vol': r[0xB0] & 0x0F, 'bank': cpu.bank})


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
                lines[a] = (a, 0, f'(다른 채널 시작 ${a:04X} 로 이어 읽음)', {'op': 'falls-into', 'target': a})
                return False
            seen.add(a)
            b = rd(prg, bank, a)
            if b in COMMANDS:
                name, n = COMMANDS[b]
                args = [rd(prg, bank, a + 1 + i) for i in range(n)]
                size = 1 + n
                text = name
                item = {'op': name, 'args': args}
                if b == 0xFE:
                    tgt = args[0] | args[1] << 8
                    text = f'jump ${tgt:04X}'
                    lines[a] = (a, size, text, {'op': 'jump', 'target': tgt})
                    ret = depth < 4 and tgt not in seen and block(tgt, depth + 1)
                    if ret is not True:
                        return False
                    a += size
                    continue
                if b == 0xFD:
                    lines[a] = (a, size, 'return', {'op': 'return'})
                    return True
                if b == 0xFA:
                    tgt = a + 3 + args[1] - 0x100
                    text = f'loop x{args[0]} → ${tgt:04X}'
                    item = {'op': 'loop', 'count': args[0], 'target': tgt}
                elif b == 0xF9:
                    tgt = a + 2 + args[0] - 0x100
                    text = f'loop x2 → ${tgt:04X}'
                    item = {'op': 'loop', 'count': 2, 'target': tgt}
                elif b == 0xF3:
                    text = f'rhythm ${args[0] | args[1] << 8:04X}'
                    item = {'op': 'rhythm', 'target': args[0] | args[1] << 8,
                            'pattern': rhythm_pattern(prg, bank, args[0] | args[1] << 8)}
                elif b == 0xE1:
                    text = f'envelope {args[0]:02X}'
                elif b == 0xFF:
                    text = f'tempo {args[0]} ({tick_rate(args[0]) * FPS:.1f} 틱/초)'
                elif n:
                    text = name + ' ' + ' '.join(f'{v:02X}' for v in args)
                lines[a] = (a, size, text, item)
                a += size
                continue
            grp, n = divmod(b, 75)
            size, extra = 1, ''
            item = {'op': 'rest' if n == 0x49 else 'tie' if n == 0x4A else 'note'}
            if n < 0x49:
                item['note'] = n
            if grp == 1:
                d = rd(prg, bank, a + 1)
                size = 2
                extra = f' len={d & 0x7F}'
                item['len'] = d & 0x7F
                if d & 0x80:
                    item['gate'] = rd(prg, bank, a + 2) & 0x7F
                    extra += f' gate={item["gate"]}'
                    size = 3
                if d & 0x7F == 0:
                    item['end'] = True
                    lines[a] = (a, size, ('rest' if n == 0x49 else f'note {n:02X}') + extra + ' (끝)', item)
                    return False
            elif grp >= 2:
                item['gate'] = rd(prg, bank, a + 1) & 0x7F
                extra = f' gate={item["gate"]}'
                size = 2
            if n == 0x49:
                text = 'rest'
            elif n == 0x4A:
                text = 'tie'
            else:
                text = f'note {n:02X}'
            lines[a] = (a, size, text + extra, item)
            a += size
        lines.setdefault(a, (a, 0, f'(→ ${a:04X} 로 되돌아감)', {'op': 'goes-back', 'target': a}))
        return False

    block(start)
    out = []
    for a in sorted(lines):
        a, size, text, item = lines[a]
        raw = ' '.join(f'{rd(prg, bank, a + i):02X}' for i in range(size))
        out.append((a, raw, text, item))
    return out


def rhythm_pattern(prg, bank, addr):
    """리듬 꼴 (길이, 게이트 또는 None) 쌍. 길이 00 에서 처음으로 돌아간다($E9EF)."""
    out, a = [], addr
    while len(out) < 64:
        d = rd(prg, bank, a)
        if d == 0:
            break
        g = rd(prg, bank, a + 1)
        out.append([d, None if g & 0x80 else g])
        a += 2
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
        for a, raw, text, _ in decode_stream(prg, bank, start, stops):
            lines.append(f'  {a:04X}  {raw:<9} {text}')
    return '\n'.join(lines)


# --- 엔벨로프·비브라토 ---------------------------------------------------------------

DUTY = ['12.5%', '25%', '50%', '75%']


def envelope_steps(prg, k, start=0):
    """엔벨로프 k(짝수 오프셋)를 자리 start 부터 따라가 [(값, 프레임 수)] 와 되돌아가는 자리(없으면 None)를 낸다.
    값 바이트는 한 프레임, 머묾 바이트 n 은 앞 값을 n 프레임 더 둔다($EE28·$EE3D), C0 이상은 건너뜀."""
    base = rd16(prg, 0x19, ENV_TABLE + k)
    steps, pos, seen = [], start, set()
    while len(steps) < 256:
        if pos in seen:
            return steps, pos
        seen.add(pos)
        b = rd(prg, 0x19, base + pos)
        if b >= 0xC0:
            pos = b & 0x3F
            continue
        if b < 0x10:
            if steps:
                steps[-1] = (steps[-1][0], steps[-1][1] + b)
        else:
            steps.append((b, 1))
        pos += 1
    return steps, None


def steps_text(steps, limit=40):
    out = []
    if len(steps) > limit:
        return steps_text(steps[:limit]) + ' …'
    for v, n in steps:
        t = f'{v & 0x0F:X}'
        out.append(t if n == 1 else f'{t}×{n}')
    return ' '.join(out)


def envelope_info(prg, k):
    base = rd16(prg, 0x19, ENV_TABLE + k)
    attack, loop = envelope_steps(prg, k)
    # 떼기 자리는 바이트 1. 첫 바이트가 건너뜀(C0 이상)인 엔벨로프만 그 자리를 떼기로 비워 둔다
    rel = rd(prg, 0x19, base + 1) if rd(prg, 0x19, base) >= 0xC0 else None
    release, rloop = envelope_steps(prg, k, rel) if rel is not None else ([], None)
    duties = sorted({DUTY[v >> 6] for v, _ in attack + release})
    flags = sorted({f'{v & 0x30:02X}' for v, _ in attack + release})
    return {'id': f'{k:02X}', 'addr': f'19:{base:04X}', 'duty': duties, 'flags': flags,
            'attack': [[v, n] for v, n in attack], 'attack_loop': loop,
            'release_at': rel, 'release': [[v, n] for v, n in release], 'release_loop': rloop}


def used_envelopes(prg):
    """곡·효과음 악보에서 명령 E1 로 쓰는 엔벨로프 번호 → 쓰는 곡 번호들."""
    used = {}
    for n, chans in all_streams(prg):
        for bank, start, stops in chans:
            for _, _, _, item in decode_stream(prg, bank, start, stops):
                if item.get('op') == 'envelope':
                    used.setdefault(item['args'][0], set()).add(n)
    return used


def all_streams(prg):
    for n in range(NSONGS):
        if song_unused(prg, n):
            continue
        bank, ptrs, _ = song_entry(prg, n)
        chans = [(chan_bank(bank, y), p + (1 if y == 0 else 0)) for y, p in enumerate(ptrs)
                 if not (p == EMPTY and chan_bank(bank, y) == 0x19)]
        yield n, [(b, p, {q for b2, q in chans if b2 == b and q != p}) for b, p in chans]
    for i in range(NSFX):
        if not sfx_unused(prg, i):
            yield 0x80 + i, [(0x19, sfx_entry(prg, i)[1], set())]


def cmd_envelopes(prg, args):
    used = used_envelopes(prg)
    print('| 번호 | 주소 | 듀티 | 음량(×프레임, ↺ 마지막 값 유지·되풀이) | 떼기(게이트 뒤) | 쓰는 곡·효과음 |')
    print('| --- | --- | --- | --- | --- | --- |')
    for k in sorted(used):
        e = envelope_info(prg, k)
        att = steps_text(e['attack']) + (' ↺' if e['attack_loop'] is not None else '')
        if e['release_at'] is None:
            rel = '없음'
        else:
            rel = f'@{e["release_at"]}: ' + steps_text(e['release']) + (' ↺' if e['release_loop'] is not None else '')
        songs = ' '.join(f'{n:02X}' for n in sorted(used[k]))
        print(f'| `{k:02X}` | `{e["addr"]}` | {" ".join(e["duty"])} | {att} | {rel} | {songs} |')
    print('\n| 비브라토 | 주소 | 바이트(XX 더함, wn 기다림, →n 건너뜀) |')
    print('| --- | --- | --- |')
    for k in sorted(used_vibratos(prg)):
        print(f'| `{k:02X}` | `19:{rd16(prg, 0x19, VIB_TABLE + k):04X}` | {vibrato_text(prg, k)} |')


def used_vibratos(prg):
    used = set()
    for n, chans in all_streams(prg):
        for bank, start, stops in chans:
            for _, _, _, item in decode_stream(prg, bank, start, stops):
                if item.get('op') == 'vibrato' and not item['args'][0] & 1:
                    used.add(item['args'][0])
    return used


def vibrato_text(prg, k):
    """비브라토 바이트($EB53): 아래 두 비트 00 더함, 11 기다림, 01 건너뜀, 10 끝."""
    base, pos, out, seen = rd16(prg, 0x19, VIB_TABLE + k), 0, [], set()
    while pos not in seen and len(out) < 64:
        seen.add(pos)
        b = rd(prg, 0x19, base + pos)
        kind = b & 3
        if kind == 0:
            # 더하는 값: bit7 이 부호, 아래 4비트가 크기인 보정 값 A 에 그대로 더함
            out.append(f'{(b >> 2) | (0xC0 if b & 0x80 else 0):02X}')
            pos += 1
        elif kind == 3:
            out.append(f'w{(b >> 2) & 0x0F}')
            pos += 1
        elif kind == 1:
            out.append(f'→{b >> 2}')
            pos = b >> 2
        else:
            out.append('끝')
            break
    return ' '.join(out)


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


def frame_ticks(run):
    """프레임 k(0 은 곡을 건 순간)의 APU 쓰기가 일어난 틱."""
    return [0] + run.ticks_at


def pitch_bends(run, ns, ch, end):
    """APU 에 실제로 쓴 주기(비브라토·미세 음높이·이조가 모두 들어감)를 그 음의 MIDI 음높이에서 벗어난 만큼의
    음높이 휨(폭 ±2반음)으로. 바뀐 프레임에만 낸다."""
    base = 0x4000 + 4 * (1 if run.sfx else ch)
    tri = ch == 2 and not run.sfx
    starts = sorted((t, round(m)) for c, t, d, m, *_ in ns if c == ch and m is not None)
    out, per, last, i, key = [], None, None, 0, None
    for k, (ws, t) in enumerate(zip(run.frames, frame_ticks(run))):
        if t >= end:
            break
        for a, v in ws:
            if a == base + 2:
                per = ((per or 0) & 0x700) | v
            elif a == base + 3:
                per = ((per or 0) & 0xFF) | (v & 7) << 8
        while i < len(starts) and starts[i][0] <= t:
            key = starts[i][1]
            i += 1
        if per is None or key is None:
            continue
        bend = midi_of_period(per, tri) - key
        v = max(0, min(16383, 8192 + round(bend / 2 * 8192)))
        if v != last:
            out.append((t, 2.5, bytes([0xE0 | (9 if ch == 3 else ch), v & 0x7F, v >> 7])))
            last = v
    return out


def volume_events(run, ch, end):
    """CC7(채널 음량) = 곱하는 쪽 음량(주 음량 × 채널 음량, 0~F), CC11(표현) = 그 프레임의 엔벨로프·고정 음량 값(0~F).
    둘 다 127 × (값 + 1) / 16·127 × 값 / 15 로 바꿔 바뀔 때만 낸다. APU 에 쓰는 음량은 둘을 곱한 것($EE8A)."""
    mch = 9 if ch == 3 else ch
    y = 4 if run.sfx else ch
    out, last7, last11 = [], None, None
    for t, yy, v, scale in run.vols:
        if yy != y or t >= end:
            continue
        c7, c11 = round(127 * (scale + 1) / 16), round(127 * v / 15)
        if c7 != last7:
            out.append((t, 2.5, bytes([0xB0 | mch, 7, c7])))
            last7 = c7
        if c11 != last11:
            out.append((t, 2.5, bytes([0xB0 | mch, 11, c11])))
            last11 = c11
    return out


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
    sfx_ch = (3 if sfx_entry(run.prg, run.n - 0x80)[0] == 'noise' else 1) if run.sfx else None
    for ch in range(4):
        mch = 9 if ch == 3 else ch
        ev = [(0, 0, b'\xff\x03' + vlq(len(CH_NAMES[ch])) + CH_NAMES[ch].encode())]
        if sfx_ch is not None and ch != sfx_ch:
            tracks.append(track(ev))
            continue
        if ch != 3:
            ev.append((0, 1, bytes([0xC0 | mch, PROGRAMS[ch]])))
            # 음높이 휨 폭 ±2반음(RPN 0)
            ev += [(0, 1, bytes([0xB0 | mch, 101, 0])), (0, 1, bytes([0xB0 | mch, 100, 0])),
                   (0, 1, bytes([0xB0 | mch, 6, 2])), (0, 1, bytes([0xB0 | mch, 38, 0]))]
            ev += pitch_bends(run, ns, ch, end)
        if ch != 2:
            ev += volume_events(run, ch, end)
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


def song_json(prg, r):
    """곡·효과음 하나의 중간 형식: 채널별 악보 명령(주소 순, 건너뜀·되풀이 목적지 포함)과 드라이버를 돌린 음 시간표."""
    n = r.n
    if n >= 0x80:
        ch, addr = sfx_entry(prg, n - 0x80)
        chans = [(ch, 0x19, addr, addr)]
    else:
        bank, ptrs, _ = song_entry(prg, n)
        chans = [(CH_NAMES[y], chan_bank(bank, y), p, p + (1 if y == 0 else 0)) for y, p in enumerate(ptrs)]
    channels = []
    for name, bank, p, start in chans:
        if p == EMPTY and bank == 0x19:
            channels.append({'name': name, 'bank': f'{bank:02X}', 'start': f'{p:04X}', 'items': []})
            continue
        stops = {q for _, b, q, _ in chans if b == bank and q != p}
        items = [{'addr': f'{a:04X}', 'bytes': raw, **item}
                 for a, raw, _, item in decode_stream(prg, bank, start, stops)]
        channels.append({'name': name, 'bank': f'{bank:02X}', 'start': f'{p:04X}', 'items': items})
    sfx_ch = (3 if sfx_entry(prg, n - 0x80)[0] == 'noise' else 1) if n >= 0x80 else None
    timeline, envs = [], set()
    for (t, y, nn, dur, gate, env, tr, fixed, ptr, frame), ex in zip(r.events, r.extra):
        ch = sfx_ch if n >= 0x80 else y
        e = {'tick': t, 'frame': frame, 'ch': CH_NAMES[ch], 'op': 'rest' if nn == 0x49 else 'tie' if nn == 0x4A else 'note',
             'len': dur, 'gate': gate, 'envelope': env, 'transpose': tr - 256 if tr & 0x80 else tr,
             'fixed_vol': None if fixed == 0xFF else fixed, 'ch_vol': ex['ch_vol'], 'detune': ex['detune'],
             'vibrato': ex['vibrato'], 'master_vol': ex['master_vol']}
        if dur == 0:
            e['op'] = 'end'
        if nn < 0x49:
            e['note'] = nn
            if ch == 3:
                e['noise_period'] = nn & 0x0F
            else:
                e['midi'] = round(midi_of_period(period(prg, pitch_index(nn, tr if n < 0x80 else 0, ch == 2 and n < 0x80)),
                                                 ch == 2 and n < 0x80), 2)
            if ch < 2 or n >= 0x80:
                envs.add(env)
        timeline.append(e)
    return {'id': f'{n:02X}', 'kind': 'sfx' if n >= 0x80 else 'song',
            'tempo': r.tempos[0][1], 'ticks_per_second': round(tick_rate(r.tempos[0][1]) * FPS, 4),
            'tempo_changes': [[t, v] for t, v in r.tempos[1:]],
            'loop_start': r.loop_start, 'loop_len': r.loop_len, 'end_tick': r.tick,
            'channels': channels, 'timeline': timeline,
            'envelopes': {f'{k:02X}': envelope_info(prg, k) for k in sorted(envs) if k != 0xFF},
            'note_ref': '음 번호 n: 주기 표 번호 = n + 3 + 이조, 펄스 n=00 이 C2. midi 는 주기에서 계산한 음높이(실수)'}


def cmd_json(prg, args):
    r = Run(prg, args.n, max_frames=args.frames if args.n < 0x80 else 2000)
    print(json.dumps(song_json(prg, r), ensure_ascii=False, indent=1))


def cmd_score(prg, args):
    print(score_text(prg, args.n))


# 선율로 맞춘 NDS 사운드 테스트 이름(fc/dq4/docs/dq4-sound-format.md 「곡 목록」, ndsmatch). 장면으로만 붙인 것도 포함
NDS_NAMES = {
    0x01: 'レベルアップ', 0x02: '序曲', 0x03: '王宮のメヌエット', 0x04: '楽しいカジノ', 0x05: '戦士はひとり征く',
    0x06: '恐怖の洞窟', 0x07: '呪われし塔', 0x08: '不思議のほこら', 0x09: '海図を広げて', 0x0A: '謎の城',
    0x0B: 'ジプシーの旅', 0x0C: '街でのひととき', 0x0D: '栄光への戦い・生か死か', 0x0E: 'エレジー', 0x0F: '宿屋宿泊',
    0x10: '教会治療', 0x13: 'のどかな熱気球の旅', 0x15: 'コロシアム', 0x16: 'おてんば姫の行進', 0x17: '武器商人トルネコ',
    0x19: 'コロシアム', 0x1A: '仲間が加わった', 0x1B: 'コロシアムスタンド', 0x1C: '勇者の故郷', 0x1D: '馬車のマーチ',
    0x1E: '邪悪なるもの', 0x1F: 'インテルメッツォ', 0x20: 'ジプシーダンス', 0x25: 'エンディング第一章',
    0x26: 'エンディング第二章', 0x27: 'エンディング第三章', 0x28: 'エンディング第四章', 0x2B: '重要アイテム発見',
    0x2D: '病気回復', 0x2E: 'ファンファーレ小', 0x2F: 'ファンファーレ中', 0x30: 'ファンファーレ大',
    0x31: '終曲・導かれし者たち', 0x35: '悪の化身',
}


def cmd_export(prg, args):
    """곡·효과음마다 .txt·.mid·.json·.musicxml·-score-NN.svg(--no-svg 로 뺌)·.wav(--wav)·.flac(--flac, flac 명령),
    폴더마다 index.json, 그리고 OUT/dq4.nsf. 같은 롬·같은 도구면 같은 바이트가 나온다(flac 은 같은 판일 때)."""
    import subprocess
    import dq4apu
    import dq4score
    out = args.out
    os.makedirs(os.path.join(out, 'songs'), exist_ok=True)
    os.makedirs(os.path.join(out, 'sfx'), exist_ok=True)
    index = {'songs': [], 'sfx': []}
    for n in nsf_tracks(prg):
        sub = 'sfx' if n >= 0x80 else 'songs'
        r = Run(prg, n, max_frames=args.frames if n < 0x80 else 2000)
        base = os.path.join(out, sub, f'{n:02X}')
        title = f'DQ4 {"sfx" if n >= 0x80 else "song"} {n:02X}' + (f' {NDS_NAMES[n]}' if n in NDS_NAMES else '')
        files = [f'{n:02X}.mid', f'{n:02X}.txt', f'{n:02X}.json', f'{n:02X}.musicxml']
        with open(base + '.mid', 'wb') as f:
            f.write(midi_bytes(r, title))
        with open(base + '.txt', 'w') as f:
            f.write(score_text(prg, n) + '\n\n' + notes_text(r) + '\n')
        with open(base + '.json', 'w') as f:
            json.dump(song_json(prg, r), f, ensure_ascii=False, separators=(',', ':'))
        xml = song_musicxml(r, title)
        errs = score_check(r, xml)
        if errs:
            sys.exit(f'{n:02X} 악보가 MIDI 와 다름: ' + '; '.join(errs))
        with open(base + '.musicxml', 'w') as f:
            f.write(xml)
        if not args.no_svg:
            for i, page in enumerate(dq4score.svg_pages(xml)):
                name = f'{n:02X}-score-{i + 1:02d}.svg'
                with open(os.path.join(out, sub, name), 'w') as f:
                    f.write(page)
                files.append(name)
        if args.wav or args.flac:
            wav = base + '.wav'
            dq4apu.write_wav(wav, dq4apu.render(r.frames, 44100, tail=30))
            if args.flac:
                subprocess.run(['flac', '-s', '-8', '-f', '-o', base + '.flac', wav], check=True)
                if not args.wav:
                    os.unlink(wav)
                files.append(f'{n:02X}.flac')
            if args.wav:
                files.append(f'{n:02X}.wav')
        if n < 0x80:
            bank, ptrs, _ = song_entry(prg, n)
            where = [f'{chan_bank(bank, y):02X}:{p:04X}' for y, p in enumerate(ptrs)]
        else:
            ch, addr = sfx_entry(prg, n - 0x80)
            where = [f'19:{addr:04X} {ch}']
        index[sub].append({'id': f'{n:02X}', 'nsf_track': nsf_tracks(prg).index(n) + 1, 'name': NDS_NAMES.get(n),
                           'files': files, 'channels': where,
                           'tempo': r.tempos[0][1], 'notes': len(notes(r)), 'ticks': r.tick,
                           'loop_start': r.loop_start, 'loop_len': r.loop_len,
                           'seconds': round(len(r.frames) / FPS, 1)})
        print(base, len(files))
    for sub, items in index.items():
        with open(os.path.join(out, sub, 'index.json'), 'w') as f:
            json.dump(items, f, ensure_ascii=False, indent=1)
    data, _, _ = nsf_bytes(prg)
    with open(os.path.join(out, 'dq4.nsf'), 'wb') as f:
        f.write(data)
    print(out)


# --- 오선 악보 ------------------------------------------------------------------

def score_data(run):
    """곡·효과음의 오선 악보 재료: (파트 목록, 끝 틱, 마디 틱, 템포 목록, 되풀이). 틱은 첫 틱(1)을 0 으로 당긴다.
    박자는 롬에 없어 되풀이 길이로 정한다(96 의 배수면 4/4, 아니고 72 의 배수면 3/4, 되풀이가 없으면 4/4)."""
    ns = notes(run)
    end = max([t + d for _, t, d, *_ in ns] + [run.tick])
    loop = None
    if run.loop_start is not None:
        end = run.loop_start + run.loop_len
        loop = (run.loop_start - 1, end - 1)
    end -= 1
    bar = 96
    if run.loop_len and run.loop_len % 96 and not run.loop_len % 72:
        bar = 72
    sfx_ch = (3 if sfx_entry(run.prg, run.n - 0x80)[0] == 'noise' else 1) if run.sfx else None
    parts = []
    for ch in range(4):
        if sfx_ch is not None and ch != sfx_ch:
            continue
        evs = []
        for c, t, d, m, n, g in ns:
            if c != ch or t - 1 >= end:
                continue
            key = NOISE_DRUMS[n & 0x0F] if ch == 3 else max(0, min(127, round(m)))
            evs.append([t - 1, d, key])
        for a, b in zip(evs, evs[1:]):
            a[1] = min(a[1], b[0] - a[0])
        keys = [k for *_, k in evs]
        clef = 'perc' if ch == 3 else 'bass' if keys and sorted(keys)[len(keys) // 2] < 60 else 'treble'
        parts.append((CH_NAMES[ch], clef, [tuple(e) for e in evs]))
    tempos = [(max(0, t - 1), 60 * FPS * tick_rate(v) / PPQ) for t, v in run.tempos if v]
    return parts, end, bar, tempos, loop


def song_musicxml(run, title):
    import dq4score
    parts, end, bar, tempos, loop = score_data(run)
    return dq4score.musicxml(title, parts, end, PPQ, bar, tempos, loop,
                             subtitle='FC ドラゴンクエストIV — sfc-dq4 dq4sound.py 가 롬의 드라이버를 돌려 뽑음')


def score_check(run, xml):
    """MusicXML 과 같은 곡의 MIDI(midi_bytes)를 견준다: 파트마다 음 수(붙임줄로 이어진 조각은 하나), 음 시작 틱 목록,
    전체 길이(틱). 다르면 그 차이를 적은 문자열 목록을 돌려준다."""
    import xml.etree.ElementTree as ET
    import tempfile
    root = ET.fromstring(xml.split('\n', 2)[2])
    got = []
    for part in root.findall('part'):
        t, starts = 0, []
        for meas in part.findall('measure'):
            for note in meas.findall('note'):
                d = int(note.findtext('duration'))
                tie = {x.get('type') for x in note.findall('tie')}
                if note.find('rest') is None and 'stop' not in tie:
                    starts.append(t)
                t += d
        got.append((starts, t))
    with tempfile.NamedTemporaryFile(suffix='.mid', delete=False) as f:
        f.write(midi_bytes(run, 'check'))
    mid = read_midi_notes(f.name)
    os.unlink(f.name)
    parts, end, *_ = score_data(run)
    errs = []
    names = [p[0] for p in parts]
    for (starts, length), name in zip(got, names):
        ch = CH_NAMES.index(name)
        # MIDI 트랙 = 지휘 + 채널 4개. 노이즈는 채널 10 이라 read_midi_notes 가 빼므로 악보 재료와 견준다
        if ch == 3:
            want = [s for s, _, _ in parts[names.index(name)][2]]
        else:
            want = [round(t * PPQ) - 1 for t, _ in mid[1 + ch]]
        if starts != want:
            errs.append(f'{name}: 음 {len(starts)}개 / MIDI {len(want)}개')
        if length < end:
            errs.append(f'{name}: 길이 {length} < {end}')
    return errs


def cmd_scorecheck(prg, args):
    ids = [int(v, 16) for v in args.ids] if args.ids else nsf_tracks(prg)
    bad = 0
    for n in ids:
        r = Run(prg, n, max_frames=40000 if n < 0x80 else 2000)
        errs = score_check(r, song_musicxml(r, f'{n:02X}'))
        parts, end, *_ = score_data(r)
        print(f'{n:02X}  음 ' + ' '.join(f'{p[0]} {len(p[2])}' for p in parts) + f'  길이 {end}틱  ' + ('; '.join(errs) or '같음'))
        bad += bool(errs)
    sys.exit(1 if bad else 0)


# --- NSF ---------------------------------------------------------------------------

NSF_BANKS = [0x19, 0x10, 0x12, 0x13, 0x17, 0x18, 0x1F]   # NSF 4KB 쪽 4개씩 이 순서로 싣는다
NSF_FREE = 0xFE8C          # 1F 의 빈 자리 $FE8C~$FF73(232바이트, 모두 FF)
NSF_PLAY = 0xC019          # NMI 가 부르는 JMP $E685


def nsf_tracks(prg):
    return ([n for n in range(NSONGS) if not song_unused(prg, n)]
            + [0x80 + i for i in range(NSFX) if not sfx_unused(prg, i)])


def nsf_bytes(prg, start=1):
    """드라이버(1F)와 소리 데이터 뱅크 6개를 NSF(버전 1, 뱅크 전환)로 묶는다. 1F 는 두 곳만 고친다:
    $FF94(MMC1 뱅크 전환, A = 뱅크)를 NSF 뱅크 레지스터 $5FF8~$5FFB 쓰기로, 빈 자리 $FE8C 에 INIT·뱅크 표·곡 목록.
    INIT 은 게임과 같은 차례로 초기화($F088) → 한 틱($E685) → 채널 음 번호 FF → 곡 시작($EF59)을 하고,
    PLAY 는 NMI 와 같은 $C019 다. 곡 번호는 NSF 트랙 순서(nsf_tracks)이다."""
    tracks = nsf_tracks(prg)
    banks = {b: i * 4 for i, b in enumerate(NSF_BANKS)}
    fixed = bytearray(prg[0x1F * 0x4000:0x20 * 0x4000])

    def put(addr, code):
        fixed[addr - 0xC000:addr - 0xC000 + len(code)] = bytes(code)

    bankmap = NSF_FREE
    table = bankmap + 0x20
    init = table + len(tracks)
    assert all(v == 0xFF for v in fixed[NSF_FREE - 0xC000:0xFF74 - 0xC000])
    put(bankmap, [banks.get(b, 0) for b in range(0x20)])
    put(table, tracks)
    lo, hi = table & 0xFF, table >> 8
    code = [0xAA, 0xBD, lo, hi, 0x48,                   # TAX; LDA table,X; PHA
            0xA9, 0x00, 0x20, 0x88, 0xF0,               # LDA #0; JSR $F088
            0x20, 0x85, 0xE6,                           # JSR $E685
            0xA9, 0xFF]                                 # LDA #$FF
    for a in range(0x0646, 0x064B):
        code += [0x8D, a & 0xFF, a >> 8]                # STA $0646..$064A
    code += [0x68]                                      # PLA
    start_pc = init + len(code)
    code += [0x20, 0x59, 0xEF, 0x60]                    # JSR $EF59; RTS
    put(init, code)
    assert init + len(code) <= 0xFF74
    blo, bhi = bankmap & 0xFF, bankmap >> 8
    swap = [0x48, 0x8A, 0x48, 0xBA, 0xBD, 0x02, 0x01,   # PHA; TXA; PHA; TSX; LDA $0102,X
            0x29, 0x1F, 0xAA, 0xBD, blo, bhi,           # AND #$1F; TAX; LDA bankmap,X
            0x8D, 0xF8, 0x5F, 0x18, 0x69, 0x01,         # STA $5FF8; CLC; ADC #1
            0x8D, 0xF9, 0x5F, 0x69, 0x01,               # STA $5FF9; ADC #1
            0x8D, 0xFA, 0x5F, 0x69, 0x01,               # STA $5FFA; ADC #1
            0x8D, 0xFB, 0x5F,                           # STA $5FFB
            0x68, 0xAA, 0x68, 0x60]                     # PLA; TAX; PLA; RTS
    put(0xFF94, swap)
    data = b''.join(prg[b * 0x4000:(b + 1) * 0x4000] for b in NSF_BANKS[:-1]) + bytes(fixed)

    def text(t):
        return t.encode('ascii')[:31].ljust(32, b'\0')

    head = (b'NESM\x1a' + bytes([1, len(tracks), start]) + struct.pack('<HHH', 0x8000, init, NSF_PLAY)
            + text('Dragon Quest IV') + text('Koichi Sugiyama') + text('1990 Enix')
            + struct.pack('<H', round(1e6 / FPS)) + bytes([0, 1, 2, 3, 24, 25, 26, 27])
            + struct.pack('<H', 20000) + bytes([0, 0]) + bytes(4))
    assert len(head) == 0x80
    return head + data, tracks, start_pc


def cmd_nsf(prg, args):
    data, tracks, start_pc = nsf_bytes(prg, args.start)
    with open(args.out, 'wb') as f:
        f.write(data)
    print(f'{args.out}: 트랙 {len(tracks)}개, 곡 시작 자리 ${start_pc:04X}')
    print(' '.join(f'{i + 1}={n:02X}' for i, n in enumerate(tracks)))


def cmd_apucheck(prg, args):
    """lua/apustate.lua 의 apu.txt 에서 게임의 APU 쓰기(W)를 합성기(dq4apu)에 그대로 넣고, 프레임 끝마다 채널 상태가
    MesenCE 의 채널 상태(F)와 같은지 본다. 채널마다 음량 레지스터와 주기 상위 레지스터를 모두 쓴 프레임부터 견주고,
    F 줄에 프레임 카운터 클록이 있으면 첫 프레임에서 합성기의 프레임 카운터를 그 자리에 맞춘다(스윕·엔벨로프 시각)."""
    import dq4apu
    names = ['pulse1 주기', 'pulse1 음량', 'pulse1 듀티', 'pulse2 주기', 'pulse2 음량', 'pulse2 듀티',
             'triangle 주기', 'triangle 움직임', 'noise 주기', 'noise 음량', 'noise 짧은꼴']
    chan_of = [0, 0, 0, 1, 1, 1, 2, 2, 3, 3, 3]
    need = {0: {0x4000, 0x4003}, 1: {0x4004, 0x4007}, 2: {0x4008, 0x400B}, 3: {0x400C, 0x400F}}
    total_frames, total_bad = 0, 0
    for d in args.dirs:
        writes, states, fcs = {}, {}, {}
        with open(os.path.join(d, 'apu.txt')) as f:
            for line in f:
                p = line.split()
                if p[0] == 'W':
                    writes.setdefault(int(p[1]), []).append((int(p[2], 16), int(p[3], 16)))
                elif p[0] == 'F':
                    v = list(map(int, p[2:]))
                    if len(v) > 12:
                        fcs[int(p[1])] = v.pop()
                    del v[8]                       # 삼각파 단계(시작 자리가 달라 견주지 않음)
                    v[8] = dq4apu.NOISE_PERIODS.index(v[8] + 1)
                    states[int(p[1])] = v
        apu = dq4apu.APU()
        apu.write(0x4015, 0x0F)
        apu.write(0x4017, 0x80)
        live, bad, n, seen = set(), {}, 0, set()
        fs = sorted(states)
        if fs[0] in fcs:
            apu.fc = float(fcs[fs[0]])
        for fr in range(fs[0], fs[-1]):
            for a, v in writes.get(fr, []):
                apu.write(a, v)
                seen.add(a)
            live |= {c for c, regs in need.items() if regs <= seen}
            apu.run(dq4apu.FRAME)
            real = states.get(fr + 1)
            if real is None:
                continue
            p1, p2, t, z = apu.p[0], apu.p[1], apu.t, apu.n
            mine = [p1.timer, p1.level(), p1.duty, p2.timer, p2.level(), p2.duty, t.timer,
                    int(bool(t.linear and t.length)), dq4apu.NOISE_PERIODS.index(z.period),
                    0 if z.length == 0 else z.env.out(), int(z.short)]
            n += 1
            for i, (a, b) in enumerate(zip(mine, real)):
                if chan_of[i] in live and a != b:
                    bad.setdefault(names[i], []).append(fr + 1)
        nb = len({x for v in bad.values() for x in v})
        total_frames += n
        total_bad += nb
        print(f'{d}: 프레임 {n}개 중 다름 {nb}개' + ''.join(f' / {k} {len(v)}(처음 {v[0]})' for k, v in bad.items()))
    print(f'합계: 프레임 {total_frames}개 중 다름 {total_bad}개')
    sys.exit(1 if total_bad else 0)


def read_midi_notes(path):
    """SMF 의 트랙마다 [(4분음표 단위 시각, 음 번호)](음 켬, 세기 > 0, 채널 10 제외)."""
    with open(path, 'rb') as f:
        d = f.read()
    ntr, ppq = struct.unpack('>HH', d[10:14])
    p, tracks = 14, []

    def var(q):
        v = 0
        while True:
            b = d[q]
            q += 1
            v = (v << 7) | (b & 0x7F)
            if not b & 0x80:
                return v, q
    for _ in range(ntr):
        end = p + 8 + struct.unpack('>I', d[p + 4:p + 8])[0]
        q, t, run, out = p + 8, 0, 0, []
        while q < end:
            dt, q = var(q)
            t += dt
            st = d[q]
            if st & 0x80:
                q += 1
                if st < 0xF0:
                    run = st
            else:
                st = run
            if st == 0xFF:
                ln, q = var(q + 1)
                q += ln
            elif st in (0xF0, 0xF7):
                ln, q = var(q)
                q += ln
            else:
                n = 1 if st & 0xF0 in (0xC0, 0xD0) else 2
                if st & 0xF0 == 0x90 and d[q + 1] and st & 0x0F != 9:
                    out.append((t / ppq, d[q]))
                q += n
        tracks.append(out)
        p = end
    return tracks


def intervals(notes):
    """같은 16분음표 자리의 음은 가장 높은 것만 두고, 이어지는 두 음의 반음 차이 열(조 옮김과 무관)."""
    top = {}
    for t, n in notes:
        k = round(t * 4)
        top[k] = max(top.get(k, 0), n)
    seq = [top[k] for k in sorted(top)]
    return [b - a for a, b in zip(seq, seq[1:])]


def melody_score(a, b, k):
    """a 의 k 개짜리 음정 묶음 가운데 b 에도 있는 비율."""
    ga = {tuple(a[i:i + k]) for i in range(len(a) - k + 1)}
    gb = {tuple(b[i:i + k]) for i in range(len(b) - k + 1)}
    return len(ga & gb) / len(ga) if ga else 0.0


def cmd_ndsmatch(prg, args):
    """FC 곡마다 펄스 1·2·삼각파의 음정 열을 NDS 곡(비공개 에셋 nds/dq4/sound/songs/*.mid)의 트랙과 견줘
    가장 비슷한 셋을 찍는다. 음이 많은 곡은 5개 묶음, 적은 곡(음정 30개 미만)은 3개 묶음으로 센다."""
    nds = {}
    for name in sorted(os.listdir(args.dir)):
        if name.endswith('.mid'):
            nds[name[:-4]] = [intervals(t) for t in read_midi_notes(os.path.join(args.dir, name)) if len(t) > 2]
    for n in range(NSONGS):
        if song_unused(prg, n):
            continue
        r = Run(prg, n)
        end = r.loop_start + r.loop_len if r.loop_start is not None else r.tick
        fc = [intervals([(t / PPQ, round(m)) for c, t, d, m, *_ in notes(r) if c == ch and t < end]) for ch in range(3)]
        fc = [x for x in fc if len(x) >= 3]
        if not fc:
            print(f'{n:02X}  (음이 적음)')
            continue
        k = 5 if max(map(len, fc)) >= 30 else 3
        res = sorted(((max((melody_score(a, b, k) for a in fc for b in ts), default=0), name)
                      for name, ts in nds.items()), reverse=True)
        print(f'{n:02X}  k={k}  ' + ' | '.join(f'{name} {v:.2f}' for v, name in res[:3]))


# --- WAV ---------------------------------------------------------------------------

def song_audio(prg, n, rate=44100):
    """곡은 처음부터 첫 되풀이의 끝까지(되풀이가 없으면 끝까지), 효과음은 끝(또는 첫 되풀이)까지 합성한 표본."""
    import dq4apu
    r = Run(prg, n, max_frames=40000 if n < 0x80 else 2000)
    return r, dq4apu.render(r.frames, rate, tail=30)


def cmd_wav(prg, args):
    import dq4apu
    ids = [int(v, 16) for v in args.ids] if args.ids else nsf_tracks(prg)
    os.makedirs(args.out, exist_ok=True)
    for n in ids:
        r, x = song_audio(prg, n)
        path = os.path.join(args.out, f'{n:02X}.wav')
        dq4apu.write_wav(path, x)
        print(f'{path}  {len(x) / 44100:.1f}초  최대 {abs(x).max():.3f}')


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
    sub.add_parser('envelopes')
    s = sub.add_parser('json')
    s.add_argument('n', type=lambda v: int(v, 16))
    s.add_argument('--frames', type=int, default=40000)
    s = sub.add_parser('nsf')
    s.add_argument('out')
    s.add_argument('--start', type=int, default=1)
    s = sub.add_parser('apucheck')
    s.add_argument('dirs', nargs='+')
    s = sub.add_parser('ndsmatch')
    s.add_argument('dir')
    s = sub.add_parser('scorecheck')
    s.add_argument('ids', nargs='*')
    s = sub.add_parser('wav')
    s.add_argument('out')
    s.add_argument('ids', nargs='*')
    s = sub.add_parser('export')
    s.add_argument('out', nargs='?', default='work/dq4-sound')
    s.add_argument('--frames', type=int, default=40000)
    s.add_argument('--no-svg', action='store_true')
    s.add_argument('--wav', action='store_true')
    s.add_argument('--flac', action='store_true')
    args = ap.parse_args()
    prg = load(args.rom)
    {'songs': cmd_songs, 'sfx': cmd_sfx, 'score': cmd_score, 'notes': cmd_notes, 'apu': cmd_apu,
     'compare': cmd_compare, 'export': cmd_export, 'maps': cmd_maps, 'calls': cmd_calls,
     'envelopes': cmd_envelopes, 'json': cmd_json, 'nsf': cmd_nsf, 'wav': cmd_wav, 'apucheck': cmd_apucheck, 'ndsmatch': cmd_ndsmatch, 'scorecheck': cmd_scorecheck}[args.cmd](prg, args)


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
    # 첫 자리가 勇者(0)면 19:$804C 로 가서 걷는 일행 수(x3 62 63 41)를 본다. 곡 1C 는 $8055 의 즉치값
    print(f'    첫 자리가 勇者면 걷는 일행 수(x3 62 63 41)가 1 일 때 {b(0x8056):02X} 아니면 {b(CHAPTER_SONGS + 5):02X}')


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


def npc_calls(prg):
    """인물 블록 명령 30 n(1F:$DDBE, 소리 n): (블록 뱅크, 주소, 번호)."""
    import dq4npcblock
    out, seen = [], set()
    for _, bank, _, _, a, ln, _ in dq4npcblock.all_blocks(prg):
        for p, bs, _, _ in dq4npcblock.decode(prg, bank, a, ln):
            if bs[0] == 0x30 and (bank, p) not in seen:
                seen.add((bank, p))
                out.append((bank, p, bs[1]))
    return out


def cmd_calls(prg, args):
    by = {}
    for bank, addr, how, n in code_calls(prg):
        by.setdefault(n, []).append(f'{bank:02X}:{addr:04X}' + ('' if how == 'BRK n FB' else f'({how})'))
    for bank, addr, n in npc_calls(prg):
        by.setdefault(n, []).append(f'{bank:02X}:{addr:04X}(인물 블록 30)')
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
