"""FC APU(2A03) 의 펄스 2·삼각파·노이즈를 프레임마다의 레지스터 쓰기로 합성해 PCM 으로 낸다.

dq4sound.py 의 Run.frames(프레임마다 [(주소, 값)…], 드라이버를 그대로 돌린 APU 쓰기)를 받아 쓴다. DQ4 는 DMC 를 쓰지 않으므로
DMC 는 없다. 한 프레임의 쓰기는 프레임이 시작하고 WRITE_AT 클록 뒤(NMI 안의 드라이버)에 한꺼번에 일어난 것으로 둔다.

- 프레임 카운터: $4017 bit7 = 1(5단계, DQ4 드라이버의 초기화 값)이면 37282 클록마다 1/4 프레임 4번(7457·14913·22371·37281),
  1/2 프레임 2번(14913·37281). 0 이면 29830 클록에 4번(7457·14913·22371·29829), 1/2 은 14913·29829.
- 펄스: 듀티 4가지 × 8단계, 타이머 주기 t 에서 2(t+1) 클록마다 한 단계. t < 8 이거나 스윕 목표가 7FF 를 넘으면 소리 없음.
  스윕은 펄스 1 이 1의 보수(−c−1), 펄스 2 가 2의 보수(−c).
- 삼각파: 32단계(15→0→15), t+1 클록마다 한 단계. 선형 카운터나 길이 카운터가 0 이면 그 자리 값을 그대로 둠.
- 노이즈: 15비트 LFSR(긴 꼴 bit0^bit1, 짧은 꼴 bit0^bit6), NTSC 주기 표.
- 섞기: NESdev 위키의 비선형 식(펄스 95.88/(8128/(p1+p2)+100), 삼각·노이즈 159.79/(1/(t/8227+n/12241)+100)).
- 4배로 뽑아 평균 내 줄이고, FC 본체의 1차 고역 90Hz·440Hz, 저역 14kHz 를 건다.
"""
import wave

import numpy as np

CPU = 1789773
FRAME = CPU / 60.0988          # NMI 사이 클록 수(약 29780.6)
# 프레임 끝(MesenCE 의 endFrame)에서 드라이버가 APU 를 쓰기까지의 클록. NMI 가 화면 일을 먼저 하므로 늦다.
# 스윕을 쓰는 효과음 A8·B1·92 의 MesenCE 채널 상태와 견줘 1000~2000 이면 모두 맞아 그 가운데로 둔다
WRITE_AT = 1500
LENGTHS = [10, 254, 20, 2, 40, 4, 80, 6, 160, 8, 60, 10, 14, 12, 26, 14,
           12, 16, 24, 18, 48, 20, 96, 22, 192, 24, 72, 26, 16, 28, 32, 30]
NOISE_PERIODS = [4, 8, 16, 32, 64, 96, 128, 160, 202, 254, 380, 508, 762, 1016, 2034, 4068]
DUTIES = np.array([[0, 1, 0, 0, 0, 0, 0, 0], [0, 1, 1, 0, 0, 0, 0, 0],
                   [0, 1, 1, 1, 1, 0, 0, 0], [1, 0, 0, 1, 1, 1, 1, 1]], dtype=np.float64)
TRIANGLE = np.array(list(range(15, -1, -1)) + list(range(16)), dtype=np.float64)
OVER = 4


def _lfsr(short):
    s, out = 1, []
    for _ in range(93 if short else 32767):
        out.append(0.0 if s & 1 else 1.0)
        fb = (s ^ (s >> (6 if short else 1))) & 1
        s = (s >> 1) | (fb << 14)
    return np.array(out)


NOISE_SEQ = (_lfsr(False), _lfsr(True))


class Envelope:
    def __init__(self):
        self.start = False
        self.divider = self.decay = 0
        self.loop = self.const = False
        self.vol = 0

    def write(self, v):
        self.loop, self.const, self.vol = bool(v & 0x20), bool(v & 0x10), v & 0x0F

    def clock(self):
        if self.start:
            self.start, self.decay, self.divider = False, 15, self.vol
        elif self.divider == 0:
            self.divider = self.vol
            if self.decay:
                self.decay -= 1
            elif self.loop:
                self.decay = 15
        else:
            self.divider -= 1

    def out(self):
        return self.vol if self.const else self.decay


class Pulse:
    def __init__(self, ones):
        self.ones = ones
        self.env = Envelope()
        self.duty = 0
        self.timer = 0
        self.length = 0
        self.enabled = False
        self.sweep = 0
        self.sweep_div = 0
        self.sweep_reload = False
        self.phase = 0.0

    def write(self, r, v):
        if r == 0:
            self.duty = v >> 6
            self.env.write(v)
        elif r == 1:
            self.sweep, self.sweep_reload = v, True
        elif r == 2:
            self.timer = (self.timer & 0x700) | v
        else:
            self.timer = (self.timer & 0xFF) | (v & 7) << 8
            if self.enabled:
                self.length = LENGTHS[v >> 3]
            self.env.start = True
            self.phase = 0.0

    def target(self):
        c = self.timer >> (self.sweep & 7)
        if self.sweep & 0x08:
            return self.timer - c - (1 if self.ones else 0)
        return self.timer + c

    def muted(self):
        return self.timer < 8 or (not self.sweep & 0x08 and self.target() > 0x7FF)

    def half(self):
        if self.length and not self.env.loop:
            self.length -= 1
        if self.sweep_div == 0 and self.sweep & 0x80 and self.sweep & 7 and not self.muted():
            self.timer = max(0, self.target())
        if self.sweep_div == 0 or self.sweep_reload:
            self.sweep_div, self.sweep_reload = (self.sweep >> 4) & 7, False
        else:
            self.sweep_div -= 1

    def level(self):
        return 0 if self.length == 0 or self.muted() else self.env.out()

    def render(self, n, cyc):
        step = cyc / (2 * (self.timer + 1))
        pos = self.phase + step * np.arange(n)
        self.phase = (self.phase + step * n) % 8
        lv = self.level()
        if lv == 0:
            return np.zeros(n)
        return DUTIES[self.duty][pos.astype(np.int64) % 8] * lv


class Triangle:
    def __init__(self):
        self.control = False
        self.reload_value = 0
        self.linear = 0
        self.reload = False
        self.timer = 0
        self.length = 0
        self.enabled = False
        self.phase = 0.0

    def write(self, r, v):
        if r == 0:
            self.control, self.reload_value = bool(v & 0x80), v & 0x7F
        elif r == 2:
            self.timer = (self.timer & 0x700) | v
        elif r == 3:
            self.timer = (self.timer & 0xFF) | (v & 7) << 8
            if self.enabled:
                self.length = LENGTHS[v >> 3]
            self.reload = True

    def quarter(self):
        if self.reload:
            self.linear = self.reload_value
        elif self.linear:
            self.linear -= 1
        if not self.control:
            self.reload = False

    def half(self):
        if self.length and not self.control:
            self.length -= 1

    def render(self, n, cyc):
        # 주기 0·1 은 초음파라 실기에서도 거의 들리지 않는다. 그 자리 값을 둔다
        if self.linear and self.length and self.timer >= 2:
            step = cyc / (self.timer + 1)
            pos = self.phase + step * np.arange(n)
            self.phase = (self.phase + step * n) % 32
            return TRIANGLE[pos.astype(np.int64) % 32]
        return np.full(n, TRIANGLE[int(self.phase) % 32])


class Noise:
    def __init__(self):
        self.env = Envelope()
        self.short = False
        self.period = NOISE_PERIODS[0]
        self.length = 0
        self.enabled = False
        self.phase = [0.0, 0.0]

    def write(self, r, v):
        if r == 0:
            self.env.write(v)
        elif r == 2:
            self.short, self.period = bool(v & 0x80), NOISE_PERIODS[v & 0x0F]
        elif r == 3:
            if self.enabled:
                self.length = LENGTHS[v >> 3]
            self.env.start = True

    def half(self):
        if self.length and not self.env.loop:
            self.length -= 1

    def render(self, n, cyc):
        k = 1 if self.short else 0
        seq = NOISE_SEQ[k]
        step = cyc / self.period
        pos = self.phase[k] + step * np.arange(n)
        self.phase[k] = (self.phase[k] + step * n) % len(seq)
        lv = 0 if self.length == 0 else self.env.out()
        if lv == 0:
            return np.zeros(n)
        return seq[pos.astype(np.int64) % len(seq)] * lv


class APU:
    def __init__(self, rate=44100):
        self.rate = rate
        self.p = [Pulse(True), Pulse(False)]
        self.t = Triangle()
        self.n = Noise()
        self.five = False
        self.fc = 0.0           # 프레임 카운터 안의 클록
        self.clock = 0.0        # 전체 클록
        self.sample = 0         # 지금까지 뽑은 표본 수(OVER 배)

    def write(self, addr, v):
        if 0x4000 <= addr <= 0x4007:
            self.p[(addr >> 2) & 1].write(addr & 3, v)
        elif 0x4008 <= addr <= 0x400B:
            self.t.write(addr & 3, v)
        elif 0x400C <= addr <= 0x400F:
            self.n.write(addr & 3, v)
        elif addr == 0x4015:
            for ch, bit in ((self.p[0], 1), (self.p[1], 2), (self.t, 4), (self.n, 8)):
                ch.enabled = bool(v & bit)
                if not ch.enabled:
                    ch.length = 0
        elif addr == 0x4017:
            self.five, self.fc = bool(v & 0x80), 0.0
            if self.five:
                self._quarter()
                self._half()

    def _quarter(self):
        self.p[0].env.clock()
        self.p[1].env.clock()
        self.n.env.clock()
        self.t.quarter()

    def _half(self):
        self.p[0].half()
        self.p[1].half()
        self.t.half()
        self.n.half()

    def _steps(self):
        if self.five:
            return [(7457, 'q'), (14913, 'h'), (22371, 'q'), (37281, 'h')], 37282
        return [(7457, 'q'), (14913, 'h'), (22371, 'q'), (29829, 'h')], 29830

    def _render(self, cycles):
        """지금 레지스터 그대로 cycles 클록만큼 뽑는다."""
        end = self.clock + cycles
        last = int(end * self.rate * OVER / CPU)
        n = last - self.sample
        self.clock = end
        if n <= 0:
            return np.zeros(0)
        self.sample = last
        cyc = CPU / (self.rate * OVER)
        p = self.p[0].render(n, cyc) + self.p[1].render(n, cyc)
        t = self.t.render(n, cyc)
        z = self.n.render(n, cyc)
        with np.errstate(divide='ignore'):
            pulse = np.where(p > 0, 95.88 / (8128.0 / np.maximum(p, 1e-9) + 100), 0.0)
            tnd_in = t / 8227 + z / 12241
            tnd = np.where(tnd_in > 0, 159.79 / (1 / np.maximum(tnd_in, 1e-12) + 100), 0.0)
        return pulse + tnd

    def run(self, cycles):
        out = []
        while cycles > 0:
            steps, total = self._steps()
            nxt = next((c for c, _ in steps if c > self.fc), total)
            span = min(cycles, nxt - self.fc)
            out.append(self._render(span))
            self.fc += span
            cycles -= span
            for c, kind in steps:
                if abs(self.fc - c) < 1e-6:
                    self._quarter()
                    if kind == 'h':
                        self._half()
            if self.fc >= total - 1e-6:
                self.fc = 0.0
        return np.concatenate(out) if out else np.zeros(0)


def render(frames, rate=44100, tail=0):
    """프레임마다의 APU 쓰기 → float 표본(−1~1). tail 은 마지막 쓰기 뒤 더 돌릴 프레임 수."""
    apu = APU(rate)
    # DQ4 드라이버의 초기화($F088)가 남기는 상태
    apu.write(0x4015, 0x0F)
    apu.write(0x4017, 0x80)
    apu.write(0x4001, 0x88)
    apu.write(0x4005, 0x88)
    chunks = []
    for ws in list(frames) + [[]] * tail:
        chunks.append(apu.run(WRITE_AT))
        for a, v in ws:
            apu.write(a, v)
        chunks.append(apu.run(FRAME - WRITE_AT))
    x = np.concatenate(chunks)
    x = x[:len(x) // OVER * OVER].reshape(-1, OVER).mean(axis=1)
    return filters(x, rate)


def _one_pole(x, rate, fc, high):
    a = np.exp(-2 * np.pi * fc / rate)
    y = np.empty_like(x)
    prev_x = prev_y = 0.0
    for i, v in enumerate(x):
        prev_y = a * (prev_y + v - prev_x) if high else (1 - a) * v + a * prev_y
        prev_x = v
        y[i] = prev_y
    return y


def filters(x, rate, taps=8192, block=1 << 16):
    """1차 고역 90Hz·440Hz, 저역 14kHz 를 차례로 건 것과 같은 임펄스 응답(taps 길이에서 1e-12 아래로 줄어듦)을
    FFT 겹쳐 더하기로 곱한다. 파이썬 반복으로 표본마다 거르면 엔딩 곡(약 10분)에 너무 오래 걸린다."""
    h = np.zeros(taps)
    h[0] = 1.0
    for fc, high in ((90, True), (440, True), (14000, False)):
        h = _one_pole(h, rate, fc, high)
    size = 1 << int(np.ceil(np.log2(block + taps - 1)))
    hf = np.fft.rfft(h, size)
    y = np.zeros(len(x) + taps - 1)
    for i in range(0, len(x), block):
        seg = np.fft.irfft(np.fft.rfft(x[i:i + block], size) * hf, size)
        m = min(len(x) - i, block) + taps - 1
        y[i:i + m] += seg[:m]
    return y[:len(x)]


def write_wav(path, x, rate=44100):
    """float 표본을 16비트 모노 WAV 로. 곡마다 맞추지 않고 모두 2.8배 해(곡끼리 음량이 같게) 쓴다.
    DQ4 곡·효과음에서 가장 큰 봉우리(곡 30)가 약 0.91 이 된다."""
    pcm = np.clip(x * 2.8, -1, 1)
    data = (pcm * 32767).astype('<i2').tobytes()
    with wave.open(path, 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(data)

