"""NDS DQ4 소리(SDAT) 읽기·추출·장면 실측. 형식은 nds/dq4/docs/sound-format.md.

    uv run --locked python nds/dq4/tools/ndssound.py info [--fs DIR]                 SDAT 목록(곡·효과음·뱅크·파형·플레이어·그룹·스트림)
    uv run --locked python nds/dq4/tools/ndssound.py export OUT [--only songs,sfx,samples] [--seq 2,5] [--jobs N]
    uv run --locked python nds/dq4/tools/ndssound.py summary OUT.json SCENES.json...   장면 실측 + 정적 표 → 곡·효과음별 장면
    uv run --locked python nds/dq4/tools/ndssound.py gallery OUT [--scenes summary.json]
    uv run --locked python nds/dq4/tools/ndssound.py scorecheck OUT                   악보 json 으로 MIDI 를 다시 만들어 견줌
    uv run --locked python nds/dq4/tools/ndssound.py maps                             맵 정보 표의 낮·밤 곡(ARM9)
    uv run --locked python nds/dq4/tools/ndssound.py scenes OUT.json [--maps all|sample] 에뮬레이터로 곡·효과음 요청을 기록

export 는 곡마다 원본 .sseq, MIDI(루프 2회), 합성 WAV(도입 + 루프 1회 + 페이드)를(songs/), SSAR 효과음마다 합성 WAV 를
(sfx/), SWAR 샘플을 WAV(루프는 smpl 청크)로(samples/) 내고, 루프 지점·SDAT 위치·뱅크 정의는 폴더마다 index.json 에 둔다.
곡·효과음마다 FC 와 같은 꼴의 악보 .json(트랙별 명령·음 시간표)과 .txt(사람이 읽는 덤프)도 낸다.
결과는 비공개 에셋 저장소의 nds/dq4/sound/ 에만 둔다(롬에서 뽑은 소리).

이 파일의 앞부분(「SDAT 일반」)은 게임과 무관한 NitroSDK 형식 코드이고, 뒷부분(「DQ4」)만 이 게임에 묶여 있다.
"""
import argparse
import html
import json
import math
import os
import struct
import sys
import wave
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

# ============================================================== SDAT 일반 (게임과 무관)

ARM7_CLOCK = 33513982
FRAME_RATE = ARM7_CLOCK / (64 * 2728)    # 시퀀서·엔벨로프 갱신 주기(약 191.96Hz)
TIMER_CLOCK = ARM7_CLOCK / 2
PSG_BASE_HZ = TIMER_CLOCK / 0x1F46 / 8   # PSG 기준 음(기준 키)의 한 주기, 약 261.6Hz
AMP_MIN = -723 << 7
ATTACK_LUT = [0x00, 0x01, 0x05, 0x0E, 0x1A, 0x26, 0x33, 0x3F, 0x49, 0x54, 0x5C, 0x64, 0x6D, 0x74, 0x7B, 0x7F, 0x84,
              0x89, 0x8F]
IMA_INDEX = [-1, -1, -1, -1, 2, 4, 6, 8]
IMA_STEP = [7, 8, 9, 10, 11, 12, 13, 14, 16, 17, 19, 21, 23, 25, 28, 31, 34, 37, 41, 45, 50, 55, 60, 66, 73, 80, 88,
            97, 107, 118, 130, 143, 157, 173, 190, 209, 230, 253, 279, 307, 337, 371, 408, 449, 494, 544, 598, 658, 724,
            796, 876, 963, 1060, 1166, 1282, 1411, 1552, 1707, 1878, 2066, 2272, 2499, 2749, 3024, 3327, 3660, 4026,
            4428, 4871, 5358, 5894, 6484, 7132, 7845, 8630, 9493, 10442, 11487, 12635, 13899, 15289, 16818, 18500,
            20350, 22385, 24623, 27086, 29794, 32767]
INFO_KINDS = ["seq", "seqarc", "bank", "wavearc", "player", "group", "player2", "strm"]
WAVE_FORMATS = {0: "PCM8", 1: "PCM16", 2: "IMA-ADPCM"}
INST_TYPES = {0: "없음", 1: "PCM", 2: "PSG", 3: "잡음", 4: "직접 PCM", 5: "빈 칸", 0x10: "드럼 세트", 0x11: "키 분할"}


def u16(b, o):
    return struct.unpack_from("<H", b, o)[0]


def u32(b, o):
    return struct.unpack_from("<I", b, o)[0]


def cstr(b, o):
    return b[o:b.index(b"\0", o)].decode("ascii")


def db_square(v):
    """0–127 값 → 감쇠(0.1dB 단위). NitroSDK 의 SND_CalcDecibelSquare 표와 같은 값(진폭 ∝ v²)."""
    if v <= 0:
        return -32768
    return max(-723, round(400 * math.log10(min(v, 127) / 127)))


def cnv_attack(a):
    return ATTACK_LUT[0x7F - a] if a >= 0x6D else 0xFF - a


def cnv_fall(f):
    if f == 0x7F:
        return 0xFFFF
    if f == 0x7E:
        return 0x3C00
    if f < 0x32:
        return f * 2 + 1
    return 0x1E00 // (0x7E - f)


def amplitude(cb):
    """감쇠(0.1dB) → 진폭."""
    return 0.0 if cb <= -723 else 10 ** (cb / 200)


class Sdat:
    """SDAT 컨테이너: SYMB(이름)·INFO(레코드)·FAT(파일 위치)·FILE."""

    def __init__(self, data):
        self.d = data
        if data[:4] != b"SDAT":
            raise ValueError("SDAT 가 아님")
        self.symb, _, self.info, _, self.fat, _, self.file_block, _ = struct.unpack_from("<8I", data, 0x10)
        self.names = self._symbols() if self.symb else {}

    def _symbols(self):
        d, s = self.d, self.symb
        out = {}
        for k, kind in enumerate(INFO_KINDS):
            r = s + u32(d, s + 8 + 4 * k)
            n = u32(d, r)
            if kind == "seqarc":
                arcs = []
                for i in range(n):
                    a, sub = struct.unpack_from("<II", d, r + 4 + 8 * i)
                    sub += s
                    subs = [cstr(d, s + o) if o else None for o in struct.unpack_from(f"<{u32(d, sub)}I", d, sub + 4)]
                    arcs.append((cstr(d, s + a) if a else None, subs))
                out[kind] = arcs
            else:
                out[kind] = [cstr(d, s + o) if o else None for o in struct.unpack_from(f"<{n}I", d, r + 4)]
        return out

    def count(self, kind):
        r = self.info + u32(self.d, self.info + 8 + 4 * INFO_KINDS.index(kind))
        return u32(self.d, r)

    def record(self, kind, i):
        """INFO 레코드의 위치(없으면 None)."""
        r = self.info + u32(self.d, self.info + 8 + 4 * INFO_KINDS.index(kind))
        if i >= u32(self.d, r):
            return None
        o = u32(self.d, r + 4 + 4 * i)
        return self.info + o if o else None

    def file(self, fid):
        st, sz = struct.unpack_from("<II", self.d, self.fat + 12 + fid * 16)
        return self.d[st:st + sz]

    def name(self, kind, i):
        lst = self.names.get(kind, [])
        if kind == "seqarc":
            return lst[i][0] if i < len(lst) else None
        return lst[i] if i < len(lst) else None

    def seq_info(self, i):
        e = self.record("seq", i)
        if e is None:
            return None
        fid, _, bank, vol, cpr, ppr, player = struct.unpack_from("<HHHBBBB", self.d, e)
        return {"file": fid, "bank": bank, "volume": vol, "channel_priority": cpr, "player_priority": ppr,
                "player": player}

    def seqarc_info(self, i):
        e = self.record("seqarc", i)
        return None if e is None else {"file": u16(self.d, e)}

    def bank_info(self, i):
        e = self.record("bank", i)
        if e is None:
            return None
        fid = u16(self.d, e)
        return {"file": fid, "wavearcs": [w for w in struct.unpack_from("<4H", self.d, e + 4) if w != 0xFFFF]}

    def wavearc_info(self, i):
        e = self.record("wavearc", i)
        return None if e is None else {"file": u32(self.d, e) & 0xFFFFFF}

    def player_info(self, i):
        e = self.record("player", i)
        if e is None:
            return None
        maxseq, _, mask, heap = struct.unpack_from("<BBHI", self.d, e)
        return {"max_seq": maxseq, "channels": [c for c in range(16) if mask >> c & 1], "heap": heap}

    def group_info(self, i):
        e = self.record("group", i)
        if e is None:
            return None
        kinds = {0: "seq", 1: "bank", 2: "wavearc", 3: "seqarc"}
        out = []
        for k in range(u32(self.d, e)):
            t, flag, _, idx = struct.unpack_from("<BBHI", self.d, e + 4 + 8 * k)
            out.append({"kind": kinds.get(t, t), "load_flags": flag, "index": idx})
        return out

    def player2_info(self, i):
        e = self.record("player2", i)
        if e is None:
            return None
        n = self.d[e]
        return {"channels": list(self.d[e + 1:e + 1 + n])}

    def strm_info(self, i):
        e = self.record("strm", i)
        if e is None:
            return None
        fid, _, vol, pri, player = struct.unpack_from("<HHBBB", self.d, e)
        return {"file": fid, "volume": vol, "priority": pri, "player": player}


def decode_swav(w):
    """SWAV(머리 12바이트 + 자료) → {"pcm": float32 [-1, 1], "rate", "loop", "loop_start", "format"}."""
    kind, loop, rate, _timer, loop_start, loop_len = struct.unpack_from("<BBHHHI", w, 0)
    body = w[12:12 + (loop_start + loop_len) * 4]
    if kind == 0:
        pcm = np.frombuffer(body, np.int8).astype(np.float32) / 128
        ls = loop_start * 4
    elif kind == 1:
        pcm = np.frombuffer(body[:len(body) // 2 * 2], "<i2").astype(np.float32) / 32768
        ls = loop_start * 2
    else:
        pcm = decode_ima(body)
        ls = (loop_start * 4 - 4) * 2   # 머리말 한 워드를 뺀 니블 수
    return {"pcm": pcm, "rate": rate, "loop": bool(loop), "loop_start": ls, "format": WAVE_FORMATS.get(kind, kind)}


def decode_ima(body, pred=None, idx=None):
    """IMA-ADPCM(머리 4바이트: 예측값 s16, 색인 u16 — pred 를 주면 머리 없음) → float32."""
    if pred is None:
        pred, idx = struct.unpack_from("<hH", body, 0)
        body = body[4:]
    out = np.empty(len(body) * 2, np.float32)
    k = 0
    for b in body:
        for nib in (b & 15, b >> 4):
            step = IMA_STEP[idx]
            diff = step >> 3
            if nib & 1:
                diff += step >> 2
            if nib & 2:
                diff += step >> 1
            if nib & 4:
                diff += step
            pred = max(-32768, min(32767, pred - diff if nib & 8 else pred + diff))
            idx = max(0, min(88, idx + IMA_INDEX[nib & 7]))
            out[k] = pred
            k += 1
    return out / 32768


def swar_waves(data):
    """SWAR → [SWAV 바이트]."""
    if data[:4] != b"SWAR":
        raise ValueError("SWAR 가 아님")
    n = u32(data, 0x38)
    offs = struct.unpack_from(f"<{n}I", data, 0x3C)
    ends = sorted(set(offs)) + [len(data)]
    out = []
    for o in offs:
        out.append(data[o:ends[ends.index(o) + 1]] if o else b"")
    return out


def sbnk_instruments(data):
    """SBNK → [{"type", "regions": [{lo, hi, swav, swar, base, attack, decay, sustain, release, pan}]}]."""
    if data[:4] != b"SBNK":
        raise ValueError("SBNK 가 아님")
    n = u32(data, 0x38)
    out = []

    def region(o, lo, hi):
        swav, swar, base, a, d, s, r, pan = struct.unpack_from("<HHBBBBBB", data, o)
        return {"lo": lo, "hi": hi, "swav": swav, "swar": swar, "base": base, "attack": a, "decay": d, "sustain": s,
                "release": r, "pan": pan}

    for p in range(n):
        t = data[0x3C + p * 4]
        off = u16(data, 0x3C + p * 4 + 1)
        inst = {"type": t, "regions": []}
        if t in (1, 2, 3, 4):
            inst["regions"].append(region(off, 0, 127) | {"type": t})
        elif t == 0x10:
            lo, hi = data[off], data[off + 1]
            for k in range(hi - lo + 1):
                o = off + 2 + k * 12
                inst["regions"].append(region(o + 2, lo + k, lo + k) | {"type": u16(data, o)})
        elif t == 0x11:
            tops = data[off:off + 8]
            lo = 0
            for k, top in enumerate(tops):
                if not top:
                    break
                o = off + 8 + k * 12
                inst["regions"].append(region(o + 2, lo, top) | {"type": u16(data, o)})
                lo = top + 1
        out.append(inst)
    return out


def strm_decode(data):
    """STRM → (float32 [샘플, 채널], 표본율, 루프 시작 샘플 또는 None, 형식)."""
    if data[:4] != b"STRM":
        raise ValueError("STRM 이 아님")
    kind, loop, nch = data[0x18], data[0x19], data[0x1A]
    rate = u16(data, 0x1C)
    loop_off, total, data_off, nblocks, blen, bsamp, lastlen, lastsamp = struct.unpack_from("<8I", data, 0x20)
    chans = [[] for _ in range(nch)]
    o = data_off
    for b in range(nblocks):
        ln = lastlen if b == nblocks - 1 else blen
        for c in range(nch):
            raw = data[o:o + ln]
            o += ln
            if kind == 0:
                chans[c].append(np.frombuffer(raw, np.int8).astype(np.float32) / 128)
            elif kind == 1:
                chans[c].append(np.frombuffer(raw, "<i2").astype(np.float32) / 32768)
            else:
                chans[c].append(decode_ima(raw))
    pcm = np.stack([np.concatenate(ch)[:total] for ch in chans], 1)
    return pcm, rate, (loop_off if loop else None), WAVE_FORMATS.get(kind, kind)


class Bank:
    """SBNK 하나와 그것이 쓰는 SWAR(최대 4개). 파형은 처음 쓸 때 푼다."""

    def __init__(self, sdat, index):
        bi = sdat.bank_info(index)
        self.index = index
        self.insts = sbnk_instruments(sdat.file(bi["file"]))
        self.arcs = []
        for w in bi["wavearcs"]:
            self.arcs.append(swar_waves(sdat.file(sdat.wavearc_info(w)["file"])))
        self.cache = {}

    def region(self, prog, key):
        if prog >= len(self.insts):
            return None
        for r in self.insts[prog]["regions"]:
            if r["lo"] <= key <= r["hi"] and r["type"] in (1, 2, 3):
                return r
        return None

    def wave(self, r):
        key = (r["swar"], r["swav"])
        if key not in self.cache:
            self.cache[key] = decode_swav(self.arcs[r["swar"]][r["swav"]])
        return self.cache[key]


def noise_table():
    """DS 잡음 채널의 15비트 LFSR 출력(±1) 한 바퀴."""
    x, out = 0x7FFF, np.empty(32767, np.float32)
    for i in range(32767):
        if x & 1:
            x = (x >> 1) ^ 0x6000
            out[i] = -1
        else:
            x >>= 1
            out[i] = 1
    return out


SIN_TABLE = [round(127 * math.sin(math.pi / 2 * i / 32)) for i in range(33)]


def sin_idx(i):
    """NitroSDK SND_SinIdx: 0–127 한 주기, -127–127."""
    i &= 127
    if i < 32:
        return SIN_TABLE[i]
    if i < 64:
        return SIN_TABLE[64 - i]
    if i < 96:
        return -SIN_TABLE[i - 64]
    return -SIN_TABLE[128 - i]


class Track:
    def __init__(self, pc, number=0):
        self.pc, self.wait, self.stack, self.done = pc, 0, [], False
        self.start, self.number = pc, number
        self.prog, self.vol, self.expr, self.pan = 0, 127, 127, 64
        self.transpose, self.bend, self.bend_range, self.prio = 0, 0, 2, 64
        self.note_wait, self.tie = True, False
        self.porta_on, self.porta_key, self.porta_time, self.sweep = False, 60, 0, 0
        self.mod = {"depth": 0, "speed": 16, "type": 0, "range": 1, "delay": 0}
        self.adsr = [255, 255, 255, 255]
        self.cond = True
        self.visited = {}
        self.loop = None          # (처음 지난 틱, 되돌아간 틱) 첫 뒤로 뛰기
        self.tie_voice = None


class Voice:
    def __init__(self, track, region, wav, key, vel, length, frame):
        self.t, self.r, self.w = track, region, wav
        self.key, self.vel, self.left = key, vel, length
        a, d, s, rel = (track.adsr[i] if track.adsr[i] != 255 else region[k]
                        for i, k in enumerate(("attack", "decay", "sustain", "release")))
        self.attack, self.decay, self.sust, self.rel = cnv_attack(a), cnv_fall(d), db_square(s) << 7, cnv_fall(rel)
        self.amp, self.state = AMP_MIN, "attack"
        self.start = frame
        self.frames = []          # (왼쪽 이득, 오른쪽 이득, 재생 속도 Hz)
        self.mod_count, self.mod_delay = 0, 0
        self.sweep_from, self.sweep_len, self.sweep_count = 0, 0, 0
        self.dead = False

    def release(self):
        if self.state != "release":
            self.state = "release"

    def envelope(self):
        if self.state == "attack":
            self.amp = int(self.attack * self.amp / 256)   # 0 쪽으로 버림(아니면 -1 에 머묾)
            if self.amp == 0:
                self.state = "decay"
        elif self.state == "decay":
            self.amp -= self.decay
            if self.amp <= self.sust:
                self.amp, self.state = self.sust, "sustain"
        elif self.state == "release":
            self.amp -= self.rel
        return self.amp > AMP_MIN


class Sequencer:
    """SSEQ·SSAR 시퀀스를 DS 사운드 드라이버처럼 프레임마다 돌린다.

    음표마다 Voice 를 만들고 프레임마다 엔벨로프·LFO·휩쓸기를 갱신해 (이득, 속도)를 쌓는다. 같은 실행에서
    MIDI 로 옮길 사건(틱 단위)도 모은다. 트랙이 처음으로 뒤로 뛰는(0x94) 틱을 루프 끝으로 본다.
    """

    def __init__(self, data, start, bank, volume=127, max_voices=16, seed=1):
        self.s, self.bank, self.seq_vol = data, bank, volume
        self.base = start
        self.tracks = [Track(start)]
        self.voices, self.finished = [], []
        self.tempo, self.acc = 120, 0
        self.ticks, self.frame = 0, 0
        self.max_voices = max_voices
        self.vars = [0] * 32
        self.rng = seed
        self.events = []          # (틱, 트랙 번호, 종류, 값…)
        self.timeline = []        # 음마다 그때의 트랙 상태(악보 json)
        self.tick_frames = []     # 틱 n 이 처리된 프레임
        self.track_offset = None

    # --- 읽기 ---------------------------------------------------------------
    def varlen(self, t):
        v = 0
        while True:
            b = self.s[t.pc]
            t.pc += 1
            v = (v << 7) | (b & 0x7F)
            if not b & 0x80:
                return v

    def u24(self, p):
        return self.s[p] | self.s[p + 1] << 8 | self.s[p + 2] << 16

    def rand(self, lo, hi):
        self.rng = (self.rng * 1664525 + 1013904223) & 0xFFFFFFFF
        return lo + (self.rng >> 16) % (hi - lo + 1) if hi >= lo else lo

    def arg(self, t, kind, mode):
        """명령 인자. mode: None(보통), 'rand'(0xA0: s16 최소·최대), 'var'(0xA1: 변수 번호)."""
        if mode == "rand":
            lo, hi = struct.unpack_from("<hh", self.s, t.pc)
            t.pc += 4
            return self.rand(lo, hi)
        if mode == "var":
            v = self.vars[self.s[t.pc] & 31]
            t.pc += 1
            return v
        if kind == "u8":
            v = self.s[t.pc]
            t.pc += 1
            return v
        if kind == "s8":
            v = struct.unpack_from("<b", self.s, t.pc)[0]
            t.pc += 1
            return v
        if kind == "u16":
            v = u16(self.s, t.pc)
            t.pc += 2
            return v
        if kind == "s16":
            v = struct.unpack_from("<h", self.s, t.pc)[0]
            t.pc += 2
            return v
        return self.varlen(t)

    # --- 명령 ---------------------------------------------------------------
    def step_track(self, ti, t):
        s = self.s
        while t.wait == 0 and not t.done:
            if t.pc not in t.visited:
                t.visited[t.pc] = self.ticks
            c = s[t.pc]
            t.pc += 1
            mode = None
            run = True
            if c == 0xA0:
                mode, c = "rand", s[t.pc]
                t.pc += 1
            elif c == 0xA1:
                mode, c = "var", s[t.pc]
                t.pc += 1
            elif c == 0xA2:
                run, c = t.cond, s[t.pc]
                t.pc += 1
            if c < 0x80:
                at = t.pc - 1
                vel = s[t.pc]
                t.pc += 1
                dur = self.arg(t, "var", mode)
                if run:
                    self.note(ti, t, c, vel, dur, at)
                continue
            if c == 0x80:
                v = self.arg(t, "var", mode)
                if run:
                    t.wait = v
            elif c == 0x81:
                v = self.arg(t, "var", mode)
                if run:
                    t.prog = v
                    self.events.append((self.ticks, ti, "prog", v))
            elif c == 0x93:
                n, off = s[t.pc], self.u24(t.pc + 1)
                t.pc += 4
                if run:
                    self.tracks.append(Track(self.base_of(t) + off, n))
            elif c == 0x94:
                dest = self.base_of(t) + self.u24(t.pc)
                t.pc += 3
                if run:
                    if t.loop is None and dest in t.visited:
                        t.loop = (t.visited[dest], self.ticks)
                    t.pc = dest
            elif c == 0x95:
                dest = self.base_of(t) + self.u24(t.pc)
                t.pc += 3
                if run:
                    t.stack.append(("call", t.pc))
                    t.pc = dest
            elif 0xB0 <= c <= 0xBD:
                var = s[t.pc]
                t.pc += 1
                v = self.arg(t, "s16", mode)
                if run:
                    self.var_op(t, c, var & 31, v)
            elif 0xC0 <= c <= 0xDF:
                kind = "s8" if c in (0xC3, 0xC4) else "u8"
                v = self.arg(t, kind, mode)
                if run:
                    self.control(ti, t, c, v)
            elif c in (0xE0, 0xE1, 0xE3):
                v = self.arg(t, "s16" if c == 0xE3 else "u16", mode)
                if run:
                    if c == 0xE0:
                        t.mod["delay"] = v
                    elif c == 0xE1:
                        self.tempo = v
                        self.events.append((self.ticks, ti, "tempo", v))
                    else:
                        t.sweep = v
            elif c == 0xFC:
                if run and t.stack and t.stack[-1][0] == "loop":
                    _, pos, n = t.stack.pop()
                    if n != 1:
                        t.stack.append(("loop", pos, max(0, n - 1) if n else 0))
                        t.pc = pos
            elif c == 0xFD:
                if run:
                    while t.stack and t.stack[-1][0] != "call":
                        t.stack.pop()
                    if t.stack:
                        t.pc = t.stack.pop()[1]
                    else:
                        t.done = True
            elif c == 0xFE:
                t.pc += 2
            elif c == 0xFF:
                if run:
                    t.done = True
                    self.release_track(t)
            else:
                raise ValueError(f"알 수 없는 명령 {c:#x} @ {t.pc - 1:#x}")

    def base_of(self, t):
        return self.track_offset if self.track_offset is not None else self.base

    def var_op(self, t, c, var, v):
        x = self.vars[var]
        if c == 0xB0:
            x = v
        elif c == 0xB1:
            x += v
        elif c == 0xB2:
            x -= v
        elif c == 0xB3:
            x *= v
        elif c == 0xB4:
            x = int(x / v) if v else x
        elif c == 0xB5:
            x = x << v if v >= 0 else x >> -v
        elif c == 0xB6:
            x = self.rand(0, v) if v >= 0 else -self.rand(0, -v)
        else:
            t.cond = {0xB8: x == v, 0xB9: x >= v, 0xBA: x > v, 0xBB: x <= v, 0xBC: x < v, 0xBD: x != v}.get(c, t.cond)
            return
        self.vars[var] = max(-32768, min(32767, x))

    def control(self, ti, t, c, v):
        if c == 0xC0:
            t.pan = v
            self.events.append((self.ticks, ti, "cc", 10, v))
        elif c == 0xC1:
            t.vol = v
            self.events.append((self.ticks, ti, "cc", 7, v))
        elif c == 0xC2:
            self.seq_vol = v
        elif c == 0xC3:
            t.transpose = v
        elif c == 0xC4:
            t.bend = v
            self.events.append((self.ticks, ti, "bend", v))
        elif c == 0xC5:
            t.bend_range = v
            self.events.append((self.ticks, ti, "range", v))
        elif c == 0xC6:
            t.prio = v
        elif c == 0xC7:
            t.note_wait = bool(v)
        elif c == 0xC8:
            t.tie = bool(v)
            if not v:
                self.release_track(t)
        elif c == 0xC9:
            t.porta_key = v + t.transpose
            t.porta_on = True
        elif c == 0xCA:
            t.mod["depth"] = v
            self.events.append((self.ticks, ti, "cc", 1, v))
        elif c == 0xCB:
            t.mod["speed"] = v
        elif c == 0xCC:
            t.mod["type"] = v
        elif c == 0xCD:
            t.mod["range"] = v
        elif c == 0xCE:
            t.porta_on = bool(v)
        elif c == 0xCF:
            t.porta_time = v
        elif 0xD0 <= c <= 0xD3:
            t.adsr[c - 0xD0] = v
        elif c == 0xD4:
            t.stack.append(("loop", t.pc, v))
        elif c == 0xD5:
            t.expr = v
            self.events.append((self.ticks, ti, "cc", 11, v))
        # D6(변수 찍기)·그 밖은 무시

    def release_track(self, t):
        for v in self.voices:
            if v.t is t:
                v.release()
        t.tie_voice = None

    def note(self, ti, t, key, vel, dur, at=None):
        key = max(0, min(127, key + t.transpose))
        self.events.append((self.ticks, ti, "note", key, vel, dur))
        self.timeline.append({
            "tick": self.ticks, "frame": self.frame, "ch": ti, "addr": f"{at:04X}" if at is not None else None,
            "op": "note", "note": key, "velocity": vel, "len": dur if t.note_wait else 0, "gate": dur,
            "program": t.prog, "volume": t.vol, "expression": t.expr, "pan": t.pan, "transpose": t.transpose,
            "bend": t.bend, "bend_range": t.bend_range, "priority": t.prio, "tie": t.tie,
            "mod": dict(t.mod) if t.mod["depth"] else None,
            "adsr": [None if x == 255 else x for x in t.adsr], "sweep": t.sweep,
            "portamento": [t.porta_key, t.porta_time] if t.porta_on else None})
        if t.note_wait:
            t.wait = dur
        if t.tie and t.tie_voice is not None and not t.tie_voice.dead and t.tie_voice.state != "release":
            v = t.tie_voice
            self.set_sweep(t, v, key, dur)
            v.key, v.vel = key, vel
            t.porta_key = key
            return
        r = self.bank.region(t.prog, key)
        if r is None:
            t.porta_key = key
            return
        wav = self.bank.wave(r) if r["type"] == 1 else None
        v = Voice(t, r, wav, key, vel, None if t.tie or dur == 0 else dur, self.frame)
        self.set_sweep(t, v, key, dur)
        t.porta_key = key
        if t.tie:
            t.tie_voice = v
        live = [x for x in self.voices if not x.dead]
        if len(live) >= self.max_voices:
            # 우선순위가 낮은 것, 놓는 중인 것, 오래된 것 순으로 뺏는다
            victim = min(live, key=lambda x: (x.t.prio, x.state != "release", x.start))
            victim.dead = True
        self.voices.append(v)

    def set_sweep(self, t, v, key, dur):
        sweep = t.sweep
        length = 0
        if t.porta_on:
            sweep += (t.porta_key - key) << 6
            if t.porta_time:
                length = (t.porta_time * t.porta_time * abs(sweep)) >> 11
            else:
                length = round(dur * 240 / max(self.tempo, 1))
        elif sweep:
            length = round(dur * 240 / max(self.tempo, 1))
        v.sweep_from, v.sweep_len, v.sweep_count = sweep, length, 0

    # --- 프레임 -------------------------------------------------------------
    def frame_step(self):
        self.acc += self.tempo
        while self.acc >= 240:
            self.acc -= 240
            for i, t in enumerate(list(self.tracks)):
                self.step_track(i, t)
            for t in self.tracks:
                if t.wait:
                    t.wait -= 1
            for v in self.voices:
                if v.left is not None:
                    v.left -= 1
                    if v.left <= 0:
                        v.release()
            self.tick_frames.append(self.frame)
            self.ticks += 1
        alive = []
        for v in self.voices:
            if not v.dead and v.envelope():
                v.frames.append(self.voice_out(v))
                alive.append(v)
            else:
                v.dead = True
                self.finished.append(v)
        self.voices = alive
        self.frame += 1

    def voice_out(self, v):
        t, r = v.t, v.r
        m = t.mod
        lfo = 0
        if m["depth"]:
            if v.mod_delay < m["delay"]:
                v.mod_delay += 1
            else:
                v.mod_count = (v.mod_count + (m["speed"] << 6)) % 0x8000
                lfo = sin_idx(v.mod_count >> 8) * m["depth"] * m["range"]
        cb = (v.amp >> 7) + db_square(v.vel) + db_square(t.vol) + db_square(t.expr) + db_square(self.seq_vol)
        pitch = (v.key - r["base"]) * 64 + (t.bend * t.bend_range * 64) // 128
        if v.sweep_len and v.sweep_count < v.sweep_len:
            pitch += v.sweep_from * (v.sweep_len - v.sweep_count) // v.sweep_len
            v.sweep_count += 1
        pan = t.pan + r["pan"] - 64
        if lfo:
            if m["type"] == 0:
                pitch += (lfo << 6) >> 14
            elif m["type"] == 1:
                cb += (lfo * 60) >> 14
            else:
                pan += lfo >> 14
        g = amplitude(cb)
        pan = max(0, min(127, pan))
        rate = (v.w["rate"] if r["type"] == 1 else PSG_BASE_HZ * 8) * 2 ** (pitch / 768)
        return (g * (127 - pan) / 127, g * pan / 127, rate)

    def busy(self):
        return any(not t.done for t in self.tracks)


# --- 악보(json·txt) -----------------------------------------------------------
# 명령 이름은 FC 악보 json(fc/dq4/docs/dq4-sound-format.md 「중간 형식」)과 뜻이 같은 것은 같은 이름을 쓴다
SEQ_OPS = {
    0x80: ("rest", "var"), 0x81: ("program", "var"),
    0xC0: ("pan", "u8"), 0xC1: ("volume", "u8"), 0xC2: ("master-vol", "u8"), 0xC3: ("transpose", "s8"),
    0xC4: ("bend", "s8"), 0xC5: ("bend-range", "u8"), 0xC6: ("priority", "u8"), 0xC7: ("note-wait", "u8"),
    0xC8: ("tie-mode", "u8"), 0xC9: ("porta-key", "u8"), 0xCA: ("mod-depth", "u8"), 0xCB: ("mod-speed", "u8"),
    0xCC: ("mod-type", "u8"), 0xCD: ("mod-range", "u8"), 0xCE: ("porta", "u8"), 0xCF: ("porta-time", "u8"),
    0xD0: ("attack", "u8"), 0xD1: ("decay", "u8"), 0xD2: ("sustain", "u8"), 0xD3: ("release", "u8"),
    0xD4: ("loop-start", "u8"), 0xD5: ("expression", "u8"), 0xD6: ("print-var", "u8"),
    0xE0: ("mod-delay", "u16"), 0xE1: ("tempo", "u16"), 0xE3: ("sweep-pitch", "s16"),
    0xFC: ("loop-end", None), 0xFD: ("return", None), 0xFF: ("end", None),
}
MIDI_CC = {"pan": 10, "volume": 7, "mod-depth": 1, "expression": 11}   # Sequencer.control 이 MIDI 로 내는 것
NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def note_name(k):
    return f"{NOTE_NAMES[k % 12]}{k // 12 - 1}"


def decode_cmd(s, p, base):
    """시퀀스 명령 하나 → (크기, 악보 항목, 사람이 읽는 글). base 는 건너뛰기 목적지의 기준(SSEQ 자료 시작, SSAR 는 자료 시작)."""
    a = p
    c = s[p]
    p += 1
    item, prefix = {}, None
    if c in (0xA0, 0xA1, 0xA2):
        prefix, c = {0xA0: "random", 0xA1: "variable", 0xA2: "if"}[c], s[p]
        p += 1
        item["prefix"] = prefix

    def varlen():
        nonlocal p
        v = 0
        while True:
            b = s[p]
            p += 1
            v = (v << 7) | (b & 0x7F)
            if not b & 0x80:
                return v

    def value(kind):
        nonlocal p
        if prefix == "random":
            lo, hi = struct.unpack_from("<hh", s, p)
            p += 4
            return [lo, hi]
        if prefix == "variable":
            p += 1
            return {"var": s[p - 1]}
        if kind == "var":
            return varlen()
        size = {"u8": 1, "s8": 1, "u16": 2, "s16": 2}[kind]
        v = int.from_bytes(s[p:p + size], "little", signed=kind[0] == "s")
        p += size
        return v

    if c < 0x80:
        vel = s[p]
        p += 1
        dur = value("var")
        item |= {"op": "note", "note": c, "velocity": vel, "gate": dur}
        text = f"note {note_name(c)}({c:02X}) vel={vel} gate={dur}"
    elif c == 0x93:
        n, off = s[p], int.from_bytes(s[p + 1:p + 4], "little")
        p += 4
        item |= {"op": "open-track", "track": n, "target": base + off}
        text = f"open-track {n} → ${base + off:04X}"
    elif c in (0x94, 0x95):
        off = int.from_bytes(s[p:p + 3], "little")
        p += 3
        name = "jump" if c == 0x94 else "call"
        item |= {"op": name, "target": base + off}
        text = f"{name} ${base + off:04X}"
    elif c == 0xFE:
        mask = u16(s, p)
        p += 2
        item |= {"op": "track-alloc", "args": [mask]}
        text = f"track-alloc {mask:04X} (트랙 {','.join(str(i) for i in range(16) if mask >> i & 1)})"
    elif 0xB0 <= c <= 0xBD:
        var = s[p]
        p += 1
        item |= {"op": f"var-{c:02X}", "args": [var, value("s16")]}
        text = f"var-{c:02X} {item['args']}"
    elif c in SEQ_OPS:
        name, kind = SEQ_OPS[c]
        item["op"] = name
        if kind is None:
            text = name
        else:
            v = value(kind)
            if name == "rest":
                item["len"] = v
                text = f"rest len={v}"
            else:
                item["args"] = [v]
                text = f"{name} {v}"
                if name == "loop-start":
                    item["count"] = v
                    text = f"loop-start x{v or '∞'}"
                elif name == "tempo":
                    text = f"tempo {v} ({v / 240 * FRAME_RATE:.1f} 틱/초)"
    else:
        raise ValueError(f"알 수 없는 명령 {c:#x} @ {a:#x}")
    if prefix:
        text = f"[{prefix}] {text}"
    return p - a, item, text


def score_doc(seq, ident, kind, stop_tick, loop, base, extra):
    """시퀀서를 돌린 뒤의 Sequencer → 악보 json(FC 중간 형식 꼴). 트랙마다 실제로 지난 명령을 주소 순으로 푼다."""
    s = seq.s
    names = [f"track{t.number}" for t in seq.tracks]
    channels, texts = [], []
    for ti, t in enumerate(seq.tracks):
        items, lines = [], []
        loop_starts = []
        for a in sorted(t.visited):
            size, item, text = decode_cmd(s, a, base)
            if item["op"] == "loop-start":
                loop_starts.append(a + size)
            elif item["op"] == "loop-end" and loop_starts:
                item["target"] = loop_starts.pop()
                text += f" → ${item['target']:04X}"
            raw = " ".join(f"{b:02X}" for b in s[a:a + size])
            items.append({"addr": f"{a:04X}", "bytes": raw, **item})
            lines.append(f"  {a:04X}  {raw:<12s}  {text}")
        channels.append({"name": names[ti], "track": t.number, "start": f"{t.start:04X}",
                         "midi_track": ti + 1, "midi_channel": MIDI_CHANNELS[ti % 16],
                         "programs": sorted({e["program"] for e in seq.timeline if e["ch"] == ti}), "items": items})
        texts.append((f"[{names[ti]}] ${t.start:04X}", lines))
    by_tick = {}
    for ev in seq.events:
        if ev[2] == "tempo" and ev[0] <= stop_tick:
            by_tick[ev[0]] = ev[3]
    tempo = by_tick.pop(0, 120)
    changes, cur = [], tempo
    for tick in sorted(by_tick):
        if by_tick[tick] != cur:
            changes.append([tick, by_tick[tick]])
            cur = by_tick[tick]
    timeline = [e | {"ch": names[e["ch"]]} for e in seq.timeline if e["tick"] <= stop_tick]
    doc = {"id": ident, "kind": kind, "tempo": tempo, "ticks_per_second": round(tempo / 240 * FRAME_RATE, 4),
           "ticks_per_quarter": 48, "tempo_changes": changes,
           "loop_start": loop["start_tick"] if loop else None,
           "loop_len": loop["end_tick"] - loop["start_tick"] if loop else None, "end_tick": stop_tick,
           **extra, "channels": channels, "timeline": timeline,
           "note_ref": "items 의 note 는 전치(transpose) 전 MIDI 음 번호(60 = C4), timeline 의 note 는 전치 뒤. "
                       "gate 는 울리는 틱, len 은 다음 명령까지 기다리는 틱(note-wait 0 이면 0, 쉼은 rest 의 len). "
                       "addr·target 은 SSEQ(효과음은 SSAR) 파일 안 위치"}
    return doc, texts


def score_text(doc, head, texts):
    """악보 json → FC 의 NN.txt 꼴 텍스트."""
    out = [head, ""]
    for title, lines in texts:
        out += [title] + (lines or ["  (빈 트랙)"]) + [""]
    out.append(f"음 사건(시퀀서 실행, 템포 {doc['tempo']} 에서 초당 {doc['ticks_per_second']:.2f}틱, 4분음표 48틱)")
    for e in doc["timeline"]:
        out.append(f"{e['tick']:6d} {e['ch']:8s} {note_name(e['note']):4s} ({e['note']:3d})  vel={e['velocity']:3d} "
                   f"len={e['len']:4d} gate={e['gate']:4d} prog={e['program']:3d}")
    for tick, v in doc["tempo_changes"]:
        out.append(f"템포 바뀜 {tick}틱: {v}")
    if doc["loop_start"] is not None:
        out.append(f"되풀이: {doc['loop_start']}틱부터 {doc['loop_len']}틱")
    out.append(f"끝: {doc['end_tick']}틱")
    return "\n".join(out) + "\n"


def bank_doc(sdat, bank, programs):
    """뱅크 번호와, 악보가 쓰는 프로그램(악기)의 SBNK 정의. 파형은 samples/ 의 파일 이름(파형 묶음-파형)."""
    bi = sdat.bank_info(bank)
    insts = sbnk_instruments(sdat.file(bi["file"]))
    out = {}
    for p in sorted(programs):
        if p >= len(insts) or not insts[p]["type"]:
            out[str(p)] = None
            continue
        regs = []
        for r in insts[p]["regions"]:
            r = dict(r, type=INST_TYPES.get(r["type"], r["type"]))
            if r["type"] == "PCM":
                w = bi["wavearcs"][r["swar"]]
                r |= {"wavearc": w, "sample": f"{w:02X}-{r['swav']:02X}.wav"}
            regs.append(r)
        out[str(p)] = {"type": INST_TYPES.get(insts[p]["type"], insts[p]["type"]), "regions": regs}
    return {"id": bank, "name": sdat.name("bank", bank), "wavearcs": bi["wavearcs"]}, out


def score_events(doc, s=None):
    """악보 json 의 items 만으로 트랙을 돌려 Sequencer.events 와 같은 꼴의 사건을 낸다(시퀀서와 따로 짠 검산).
    틱마다 열린 순서대로 트랙을 돌리고 그 뒤 기다림을 하나 줄인다. 새로 연 트랙은 다음 틱부터 돈다."""
    chans = doc["channels"]
    progs = [{int(it["addr"], 16): it for it in c["items"]} for c in chans]
    tracks = [{"ci": 0, "pc": int(chans[0]["start"], 16), "wait": 0, "stack": [], "done": False,
               "transpose": 0, "note_wait": True}]
    events = []
    for tick in range(doc["end_tick"] + 1):
        for ti, t in enumerate(list(tracks)):
            prog = progs[t["ci"]]
            while t["wait"] == 0 and not t["done"]:
                it = prog[t["pc"]]
                if "prefix" in it:
                    raise ValueError(f"접두 명령은 검산하지 않음 {it}")
                op = it["op"]
                t["pc"] += len(it["bytes"].split())
                v = it.get("args", [None])[0]
                if op == "note":
                    key = max(0, min(127, it["note"] + t["transpose"]))
                    events.append((tick, ti, "note", key, it["velocity"], it["gate"]))
                    if t["note_wait"]:
                        t["wait"] = it["gate"]
                elif op == "rest":
                    t["wait"] = it["len"]
                elif op == "program":
                    events.append((tick, ti, "prog", v))
                elif op == "open-track":
                    ci = len(tracks)
                    if int(chans[ci]["start"], 16) != it["target"] or chans[ci]["track"] != it["track"]:
                        raise ValueError(f"트랙 순서가 다름 {ci} {it}")
                    tracks.append({"ci": ci, "pc": it["target"], "wait": 0, "stack": [], "done": False,
                                   "transpose": 0, "note_wait": True})
                elif op == "jump":
                    t["pc"] = it["target"]
                elif op == "call":
                    t["stack"].append(("call", t["pc"]))
                    t["pc"] = it["target"]
                elif op == "loop-start":
                    t["stack"].append(("loop", t["pc"], v))
                elif op == "loop-end":
                    if t["stack"] and t["stack"][-1][0] == "loop":
                        _, pos, n = t["stack"].pop()
                        if n != 1:
                            t["stack"].append(("loop", pos, max(0, n - 1) if n else 0))
                            t["pc"] = pos
                elif op == "return":
                    while t["stack"] and t["stack"][-1][0] != "call":
                        t["stack"].pop()
                    if t["stack"]:
                        t["pc"] = t["stack"].pop()[1]
                    else:
                        t["done"] = True
                elif op == "end":
                    t["done"] = True
                elif op == "tempo":
                    events.append((tick, ti, "tempo", v))
                elif op == "transpose":
                    t["transpose"] = v
                elif op == "note-wait":
                    t["note_wait"] = bool(v)
                elif op in MIDI_CC:
                    events.append((tick, ti, "cc", MIDI_CC[op], v))
                elif op == "bend":
                    events.append((tick, ti, "bend", v))
                elif op == "bend-range":
                    events.append((tick, ti, "range", v))
        for t in tracks:
            if t["wait"]:
                t["wait"] -= 1
    return events, len(tracks)



MIDI_CHANNELS = [c for c in range(16) if c != 9] + [9]   # 트랙 i → MIDI 채널(9 는 마지막에 씀)
NOISE = None


def render_voices(voices, out_rate, total_frames):
    """Voice 들의 프레임 기록을 표본으로 그려 더한다. → float32 [표본, 2]."""
    global NOISE
    edges = np.floor(np.arange(total_frames + 2) * out_rate / FRAME_RATE).astype(np.int64)
    out = np.zeros((edges[-1] + 1, 2), np.float32)
    for v in voices:
        if not v.frames:
            continue
        f = np.array(v.frames, np.float64)
        f0 = v.start
        f1 = min(f0 + len(f), total_frames)
        if f1 <= f0:
            continue
        f = f[:f1 - f0]
        counts = np.diff(edges[f0:f1 + 1])
        n = int(counts.sum())
        if n <= 0:
            continue
        gl = np.repeat(f[:, 0], counts).astype(np.float32)
        gr = np.repeat(f[:, 1], counts).astype(np.float32)
        step = np.repeat(f[:, 2] / out_rate, counts)
        pos = np.concatenate(([0.0], np.cumsum(step)[:-1]))
        typ = v.r["type"]
        if typ == 1:
            w = v.w
            pcm, length = w["pcm"], len(w["pcm"])
            if length < 2:
                continue
            if w["loop"] and length > w["loop_start"]:
                ls = w["loop_start"]
                idx = np.where(pos >= length, ls + np.mod(pos - ls, length - ls), pos)
                i0 = idx.astype(np.int64)
                i1 = np.where(i0 + 1 >= length, ls, i0 + 1)
                valid = 1.0
            else:
                valid = (pos < length - 1).astype(np.float32)
                i0 = np.minimum(pos.astype(np.int64), length - 1)
                i1 = np.minimum(i0 + 1, length - 1)
                idx = pos
            frac = (idx - np.floor(idx)).astype(np.float32)
            smp = (pcm[i0] * (1 - frac) + pcm[i1] * frac) * valid
        elif typ == 2:
            duty = (v.r["swav"] & 7) + 1
            phase = np.mod(pos, 8.0)
            smp = np.where(phase < duty, 1.0, -1.0).astype(np.float32) * (duty < 8) * 0.5
        else:
            if NOISE is None:
                NOISE = noise_table()
            smp = NOISE[pos.astype(np.int64) % len(NOISE)] * 0.5
        s0 = edges[f0]
        out[s0:s0 + n, 0] += smp * gl
        out[s0:s0 + n, 1] += smp * gr
    return out


def run_sequence(seq, loops=2, max_seconds=600, fade_seconds=0.0, tail_seconds=3.0):
    """시퀀서를 돌린다. 루프가 있으면 루프 끝을 loops 번 지난 뒤 fade_seconds 만큼 더, 없으면 끝나고 소리가 사라질 때까지.
    → (끝 프레임, 루프 정보 dict 또는 None, MIDI 를 끊을 틱)."""
    max_frames = int(max_seconds * FRAME_RATE)
    loop = None
    stop_tick = None
    end_frame = None
    idle_from = None
    while seq.frame < max_frames:
        seq.frame_step()
        if loop is None and seq.tracks and all(t.loop or t.done for t in seq.tracks) \
                and any(t.loop for t in seq.tracks):
            start, end = max((t.loop for t in seq.tracks if t.loop), key=lambda x: x[1] - x[0])
            loop = {"start_tick": start, "end_tick": end}
            stop_tick = end + (loops - 1) * (end - start)
        if stop_tick is not None and seq.ticks > stop_tick and end_frame is None:
            end_frame = seq.frame + int(fade_seconds * FRAME_RATE)
        if end_frame is not None and seq.frame >= end_frame:
            break
        if loop is None and not seq.busy():
            idle_from = seq.frame if idle_from is None else idle_from
            if not seq.voices or seq.frame - idle_from > tail_seconds * FRAME_RATE:
                break
    if loop is None:
        stop_tick = seq.ticks
        for v in seq.voices:
            v.release()
        extra = int(FRAME_RATE)
        while seq.voices and extra > 0:
            seq.frame_step()
            extra -= 1
    else:
        tf = seq.tick_frames
        loop["start_frame"] = tf[min(loop["start_tick"], len(tf) - 1)]
        loop["end_frame"] = tf[min(loop["end_tick"], len(tf) - 1)]
    return seq.frame, loop, stop_tick


def finish_audio(y, out_rate, fade_from=None):
    """정규화(-1dBFS)와 끝 페이드."""
    if fade_from is not None and fade_from < len(y):
        n = len(y) - fade_from
        y[fade_from:] *= np.linspace(1, 0, n, dtype=np.float32)[:, None]
    peak = float(np.abs(y).max()) if len(y) else 0
    if peak > 0:
        y = y / peak * 10 ** (-1 / 20)
    return y, peak


def write_wav(path, y, rate, loop=None):
    """16비트 WAV. loop=(시작, 끝) 표본이면 smpl 청크를 붙인다."""
    y = np.asarray(y, np.float32)
    ch = 1 if y.ndim == 1 else y.shape[1]
    pcm = (np.clip(y, -1, 1) * 32767).astype("<i2").tobytes()
    with wave.open(str(path), "wb") as w:
        w.setnchannels(ch)
        w.setsampwidth(2)
        w.setframerate(int(rate))
        w.writeframes(pcm)
    if loop:
        smpl = struct.pack("<9I", 0, 0, int(1e9 / rate), 60, 0, 0, 0, 1, 0)
        smpl += struct.pack("<6I", 0, 0, int(loop[0]), max(int(loop[0]), int(loop[1]) - 1), 0, 0)
        with open(path, "r+b") as f:
            f.seek(0, 2)
            f.write(b"smpl" + struct.pack("<I", len(smpl)) + smpl)
            size = f.tell()
            f.seek(4)
            f.write(struct.pack("<I", size - 8))


def write_midi(path, events, stop_tick, loop, ntracks, title):
    """SSEQ 사건 → SMF 형식 1, 시간 단위 48(4분음표). 트랙 i → 채널(9 는 마지막에 씀)."""
    chans = MIDI_CHANNELS

    def vlq(n):
        b = [n & 0x7F]
        n >>= 7
        while n:
            b.append(0x80 | (n & 0x7F))
            n >>= 7
        return bytes(reversed(b))

    per = [[] for _ in range(ntracks)]
    conductor = [(0, b"\xff\x03" + vlq(len(title.encode())) + title.encode())]
    if loop:
        conductor.append((loop["start_tick"], b"\xff\x06\x09loopStart"))
        conductor.append((loop["end_tick"], b"\xff\x06\x07loopEnd"))
    for ev in events:
        tick, ti = ev[0], ev[1]
        if tick > stop_tick or ti >= ntracks:
            continue
        ch = chans[ti % 16]
        kind = ev[2]
        if kind == "tempo":
            us = round(60_000_000 / max(ev[3], 1))
            conductor.append((tick, b"\xff\x51\x03" + us.to_bytes(3, "big")))
        elif kind == "prog":
            p = ev[3]
            per[ti].append((tick, bytes([0xB0 | ch, 0, (p >> 7) & 0x7F])))
            per[ti].append((tick, bytes([0xC0 | ch, p & 0x7F])))
        elif kind == "cc":
            per[ti].append((tick, bytes([0xB0 | ch, ev[3], min(127, ev[4])])))
        elif kind == "bend":
            b = max(0, min(16383, 8192 + ev[3] * 64))
            per[ti].append((tick, bytes([0xE0 | ch, b & 0x7F, b >> 7])))
        elif kind == "range":
            per[ti] += [(tick, bytes([0xB0 | ch, 101, 0])), (tick, bytes([0xB0 | ch, 100, 0])),
                        (tick, bytes([0xB0 | ch, 6, min(127, ev[3])]))]
        elif kind == "note":
            key, vel, dur = ev[3], ev[4], ev[5]
            per[ti].append((tick, bytes([0x90 | ch, key, max(1, vel)])))
            per[ti].append((min(tick + max(dur, 1), stop_tick), bytes([0x80 | ch, key, 0])))

    def chunk(evs):
        evs = sorted(evs, key=lambda e: (e[0], 0 if e[1][0] & 0xF0 == 0x80 else 1))
        out, last = bytearray(), 0
        for tick, data in evs:
            out += vlq(tick - last) + data
            last = tick
        out += vlq(max(0, stop_tick - last)) + b"\xff\x2f\x00"
        return b"MTrk" + struct.pack(">I", len(out)) + bytes(out)

    trks = [chunk(conductor)] + [chunk(e) for e in per]
    with open(path, "wb") as f:
        f.write(b"MThd" + struct.pack(">IHHH", 6, 1, len(trks), 48))
        for t in trks:
            f.write(t)


def midi_notes(data):
    """SMF → [(트랙, 켠 틱, 끈 틱, 음, 세기)] 와 템포 [(틱, 마이크로초)]. write_midi 가 낸 꼴만 읽는다."""
    notes, tempos = [], []
    o, ti = 14, 0
    while o < len(data):
        size = struct.unpack_from(">I", data, o + 4)[0]
        p, end, tick, run, on = o + 8, o + 8 + size, 0, 0, {}
        while p < end:
            d = 0
            while True:
                b = data[p]
                p += 1
                d = d << 7 | (b & 0x7F)
                if not b & 0x80:
                    break
            tick += d
            st = data[p]
            if st == 0xFF:
                kind, n = data[p + 1], data[p + 2]
                if kind == 0x51:
                    tempos.append((tick, int.from_bytes(data[p + 3:p + 6], "big")))
                p += 3 + n
                continue
            if st & 0x80:
                run, p = st, p + 1
            hi = run & 0xF0
            if hi in (0x80, 0x90):
                key, vel = data[p], data[p + 1]
                if hi == 0x90 and vel:
                    on.setdefault(key, []).append((tick, vel))
                elif on.get(key):
                    t0, v0 = on[key].pop(0)
                    notes.append((ti, t0, tick, key, v0))
                else:
                    # 끊는 틱에 켠 음은 끔(같은 틱에서 앞에 정렬됨)이 먼저 와 짝이 없다
                    notes.append((ti, None, tick, key, None))
            p += 1 if hi in (0xC0, 0xD0) else 2
        notes += [(ti, t0, None, key, v0) for key, lst in on.items() for t0, v0 in lst]
        o, ti = end, ti + 1
    return sorted(notes, key=lambda n: tuple(-1 if x is None else x for x in n)), tempos


def score_check(out):
    """OUT 의 songs/·sfx/ 악보 json 마다 items 만으로 사건을 다시 만든다. 곡은 그것으로 MIDI 를 써 .mid 와 바이트·음표를,
    효과음은 json 의 timeline 과 음표를 견준다. → 다른 것의 수."""
    import tempfile
    bad = 0
    tmp = Path(tempfile.mkdtemp())
    for sub in ("songs", "sfx"):
        files = sorted((Path(out) / sub).glob("*.json"))
        files = [f for f in files if f.name != "index.json"]
        same = notes = 0
        for f in files:
            doc = json.loads(f.read_text(encoding="utf-8"))
            events, ntracks = score_events(doc)
            mine = sorted((e[0], e[1], e[3], e[4], e[5]) for e in events if e[2] == "note")
            names = {c["name"]: i for i, c in enumerate(doc["channels"])}
            ref = sorted((e["tick"], names[e["ch"]], e["note"], e["velocity"], e["gate"]) for e in doc["timeline"])
            ok = mine == ref
            if sub == "songs":
                loop = ({"start_tick": doc["loop_start"], "end_tick": doc["loop_start"] + doc["loop_len"]}
                        if doc["loop_start"] is not None else None)
                write_midi(tmp / "x.mid", events, doc["end_tick"], loop, ntracks, doc["name"])
                a, b = (tmp / "x.mid").read_bytes(), f.with_suffix(".mid").read_bytes()
                na, nb = midi_notes(a), midi_notes(b)
                ok = ok and na == nb
                print(f"{f.stem}: 음표 {len(na[0])}/{len(nb[0])} 템포 {len(na[1])}/{len(nb[1])} "
                      f"{'MIDI 바이트 같음' if a == b else 'MIDI 바이트 다름'} {'일치' if ok else '불일치'}")
                ok = ok and a == b
                notes += len(nb[0])
            else:
                notes += len(ref)
                if not ok:
                    print(f"{f.stem}: items {len(mine)} timeline {len(ref)} 불일치")
            same += ok
            bad += not ok
        print(f"[{sub}] {len(files)}개 중 일치 {same}, 음표 {notes}")
    return bad


def seq_channels(sdat, player):
    pi = sdat.player_info(player) if player is not None else None
    return len(pi["channels"]) if pi and pi["channels"] else 16


def render_sseq(sdat, index, out_rate=32768, loops=2, fade=4.0, audio_loops=None):
    """SSEQ index → (float32 [표본, 2], 정보 dict, 사건, 끊을 틱, 트랙 수, Sequencer, 루프).
    사건(MIDI)은 루프 loops 회, 음원은 audio_loops 회(없으면 loops) 뒤 fade 초 페이드."""
    audio_loops = audio_loops or loops
    si = sdat.seq_info(index)
    data = sdat.file(si["file"])
    start = u32(data, 0x18)
    seq = Sequencer(data, start, Bank(sdat, si["bank"]), si["volume"], seq_channels(sdat, si["player"]))
    frames, loop, stop_tick = run_sequence(seq, loops=loops, fade_seconds=fade)
    y = render_voices(seq.finished + seq.voices, out_rate, frames)
    info = {"index": index, "name": sdat.name("seq", index), "bank": si["bank"], "volume": si["volume"],
            "player": si["player"], "tracks": len(seq.tracks), "sampleRate": out_rate}
    fade_from = None
    if loop:
        spf = out_rate / FRAME_RATE
        ls, le = round(loop["start_frame"] * spf), round(loop["end_frame"] * spf)
        info.update({"loopStart": round(ls / out_rate, 4), "loopEnd": round(le / out_rate, 4),
                     "loopStartSample": ls, "loopEndSample": le, "loopStartTick": loop["start_tick"],
                     "loopEndTick": loop["end_tick"], "loops": audio_loops, "midiLoops": loops,
                     "fadeSeconds": fade})
        fade_from = le + (audio_loops - 1) * (le - ls)
    y = y[:int(frames * out_rate / FRAME_RATE)]
    if fade_from is not None:
        y = y[:fade_from + int(fade * out_rate)]
    y, peak = finish_audio(y, out_rate, fade_from)
    info["duration"] = round(len(y) / out_rate, 3)
    info["peak"] = round(peak, 4)
    return y, info, seq.events, stop_tick, len(seq.tracks), seq, loop


def render_seqarc_entry(sdat, arc_index, k, out_rate=32768, max_seconds=30):
    """SSAR 의 시퀀스 k → (float32 [표본, 2], 정보, Sequencer, 루프, 끊을 틱) 또는 None."""
    data = sdat.file(sdat.seqarc_info(arc_index)["file"])
    base, n = u32(data, 0x18), u32(data, 0x1C)
    if k >= n:
        return None
    off, bank, vol, cpr, ppr, player = struct.unpack_from("<IHBBBB", data, 0x20 + 12 * k)
    if off == 0xFFFFFFFF:
        return None
    seq = Sequencer(data, base + off, Bank(sdat, bank), vol, seq_channels(sdat, player))
    seq.track_offset = base
    frames, loop, stop_tick = run_sequence(seq, loops=2, max_seconds=max_seconds, fade_seconds=0.5, tail_seconds=3)
    y = render_voices(seq.finished + seq.voices, out_rate, frames)[:int(frames * out_rate / FRAME_RATE) + 1]
    nz = np.nonzero(np.abs(y).max(1) > 1e-4)[0]
    y = y[:nz[-1] + 1] if len(nz) else y[:1]
    y, peak = finish_audio(y, out_rate)
    info = {"index": k, "bank": bank, "volume": vol, "player": player, "duration": round(len(y) / out_rate, 3),
            "loop": bool(loop), "silent": peak == 0}
    return y, info, seq, loop, stop_tick


def seqarc_entries(sdat, arc_index):
    data = sdat.file(sdat.seqarc_info(arc_index)["file"])
    n = u32(data, 0x1C)
    out = []
    for k in range(n):
        off, bank, vol, cpr, ppr, player = struct.unpack_from("<IHBBBB", data, 0x20 + 12 * k)
        if off != 0xFFFFFFFF:
            out.append(k)
    return out


def summary(sdat):
    """info 명령의 표."""
    lines = []
    for kind in INFO_KINDS:
        n = sdat.count(kind)
        present = [i for i in range(n) if sdat.record(kind, i) is not None]
        lines.append(f"[{kind}] 칸 {n}, 레코드 {len(present)}")
        for i in present:
            nm = sdat.name(kind, i) or "-"
            if kind == "seq":
                x = sdat.seq_info(i)
                lines.append(f"  {i:3d} {nm:32s} 파일 {x['file']:3d} 뱅크 {x['bank']:3d} 음량 {x['volume']:3d} "
                             f"플레이어 {x['player']} 우선 {x['channel_priority']}/{x['player_priority']}")
            elif kind == "seqarc":
                x = sdat.seqarc_info(i)
                ent = seqarc_entries(sdat, i)
                subs = sdat.names.get("seqarc", [(None, [])])[i][1]
                lines.append(f"  {i:3d} {nm:32s} 파일 {x['file']:3d} 칸 {len(subs)} 시퀀스 {len(ent)} "
                             f"이름 {sum(1 for s in subs if s)}")
            elif kind == "bank":
                x = sdat.bank_info(i)
                n_inst = len(sbnk_instruments(sdat.file(x["file"])))
                lines.append(f"  {i:3d} {nm:32s} 파일 {x['file']:3d} 파형 {x['wavearcs']} 악기 칸 {n_inst}")
            elif kind == "wavearc":
                x = sdat.wavearc_info(i)
                waves = swar_waves(sdat.file(x["file"]))
                lines.append(f"  {i:3d} {nm:32s} 파일 {x['file']:3d} 샘플 {len(waves)}")
            elif kind == "player":
                x = sdat.player_info(i)
                lines.append(f"  {i:3d} {nm:32s} 동시 {x['max_seq']} 채널 {x['channels']} 힙 {x['heap']:#x}")
            elif kind == "group":
                lines.append(f"  {i:3d} {nm:32s} {sdat.group_info(i)}")
            elif kind == "player2":
                lines.append(f"  {i:3d} {nm:32s} 채널 {sdat.player2_info(i)['channels']}")
            elif kind == "strm":
                x = sdat.strm_info(i)
                d = sdat.file(x["file"])
                lines.append(f"  {i:3d} {nm:32s} 파일 {x['file']:3d} 형식 {WAVE_FORMATS[d[0x18]]} 채널 {d[0x1A]} "
                             f"{u16(d, 0x1C)}Hz 샘플 {u32(d, 0x24)} 루프 {d[0x19]} 음량 {x['volume']}")
    return "\n".join(lines)


# ============================================================== DQ4

ROOT = Path(__file__).resolve().parents[3]
FS = ROOT / "work" / "nds" / "jp"
SDAT_PATH = Path("data/data/SOUND/sound_data.sdat")
SADL_PATH = Path("data/data/SOUND/sound_data.sadl")
SOUNDLIST = Path("data/data/DEBUG/soundlist.dat")
MAP_TABLE = 0x020A294A        # 맵 정보 표(0x2A 바이트 x 544, MAP/_list.txt 순서), +6 낮 곡, +7 밤 곡, +8 이름
MAP_ENTRY = 0x2A
BATTLE_TABLE = 0x0209B774     # 조우 레코드(0x28 바이트), +0 전투 곡(0 이면 보통 전투 곡)
BATTLE_COUNT = 245
SOUND_MGR = 0x02108200        # 음 관리자. +4 지금 BGM, +0x10 BGM 핸들 2개, +0x50 효과음 핸들 8개(0x20 씩)
GAME_SOUND = 0x020EAA70       # 게임 쪽 곡 상태. +8 지금 곡, +0xC 다음 곡, 0 이 아니면 전투 곡이 33
VEHICLE = 0x020ECE40          # 탈것: 1 기구, 2 배(필드 곡 함수가 봄)
PARTY = 0x020C5614            # 일행 순서(인물 번호 u32 x 13, 0 은 빈칸). 5·6장 필드 곡은 일행 첫 인물로 고름
OUT_RATE = 32768


def load_sdat(fs=FS):
    return Sdat((Path(fs) / SDAT_PATH).read_bytes())


def soundlist(fs=FS):
    """DEBUG/soundlist.dat: 사운드 테스트용 곡·효과음 이름. → {("BGM"|"SE", 번호): 이름}."""
    out = {}
    for line in (Path(fs) / SOUNDLIST).read_text("shift_jis").splitlines():
        # 「#BGM,34,終曲…」처럼 막힌 줄도 이름은 쓸 수 있다
        p = [x.strip() for x in line.lstrip("#").split(",", 2)]
        if len(p) == 3 and p[1].isdigit():
            out[(p[0], int(p[1]))] = p[2]
    return out


def sadl(fs=FS):
    """sound_data.sadl(SoundMaker 가 낸 C 헤더) → {이름: 번호}."""
    out = {}
    for line in (Path(fs) / SADL_PATH).read_text("ascii").splitlines():
        p = line.split()
        if len(p) == 3 and p[0] == "#define":
            out[p[1]] = int(p[2])
    return out


def place_names(fs=FS):
    """DEBUG/fieldsymbol.dat(필드 기호 → 장소)에서 맵 이름 앞 두 글자 → 장소 이름. 예: HA(CA)バトランド城下町＆城."""
    import re
    out = {}
    for line in (Path(fs) / "data/data/DEBUG/fieldsymbol.dat").read_text("shift_jis").splitlines():
        p = line.split(",", 1)
        if len(p) != 2:
            continue
        m = re.match(r"([A-Z]{2})(?:[(（]([A-Z]{2})[)）])?(.*)", p[1].strip())
        if not m:
            continue
        name = re.sub(r"[（(].*", "", m.group(3)).strip()
        for code in (m.group(1), m.group(2)):
            if code and code.lower() not in out:
                out[code.lower()] = name
        for code, sub in re.findall(r"([A-Z]{2})([^\x00-\x7f・（）]+)", m.group(3)):
            out.setdefault(code.lower(), sub.strip())
    return out


def map_songs(fs=FS):
    """ARM9 맵 정보 표 → [(맵 이름, 낮 곡, 밤 곡)]."""
    a9 = (Path(fs) / "arm9.bin").read_bytes()
    names = [line.split(",")[2].strip() for line in (Path(fs) / "data/data/MAP/_list.txt").read_text("shift_jis")
             .splitlines() if line.count(",") >= 2]
    out = []
    for i, n in enumerate(names):
        e = a9[MAP_TABLE - 0x02000000 + i * MAP_ENTRY:][:MAP_ENTRY]
        if e[8:8 + len(n)].decode("ascii") != n:
            raise ValueError(f"맵 표가 어긋남: {i} {n}")
        out.append((n, e[6], e[7]))
    return out


def battle_songs(fs=FS):
    """ARM9 조우 레코드 표 → {레코드 번호: 곡}(곡이 0 이 아닌 것만)."""
    a9 = (Path(fs) / "arm9.bin").read_bytes()
    o = BATTLE_TABLE - 0x02000000
    return {i: u16(a9, o + i * 0x28) for i in range(BATTLE_COUNT) if u16(a9, o + i * 0x28)}


def stem(number, title, width=2):
    """에셋 저장소 규칙의 파일 이름 줄기: 16진 번호와, 게임 속 일본어 이름(사운드 테스트 이름)을 알 때만 이름."""
    return f"{number:0{width}X}" + (f"-{title.replace('/', '／')}" if title else "")


def short(symb):
    """사운드 테스트 이름이 없을 때 파일 이름에 쓰는 SYMB 이름(SND_BGM_·SND_SE_M_ 를 뗌)."""
    return symb.replace("SND_BGM_", "").replace("SND_SE_M_", "") if symb else None


def fat_entry(sdat, fid):
    st, sz = struct.unpack_from("<II", sdat.d, sdat.fat + 12 + fid * 16)
    return {"file": fid, "offset": st, "size": sz}


def write_index(path, doc):
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")


def export(out, fs=FS, only=None, seqs=None, jobs=None):
    """OUT(에셋 저장소의 sound/)에 songs/·sfx/·samples/ 와 폴더마다 index.json 을 쓴다."""
    out = Path(out)
    sd = load_sdat(fs)
    titles = soundlist(fs)
    only = set(only or ["songs", "sfx", "samples"])
    jobs = jobs or os.cpu_count()
    if "songs" in only:
        d = out / "songs"
        d.mkdir(parents=True, exist_ok=True)
        idx = {}
        todo = seqs or [i for i in range(sd.count("seq")) if sd.record("seq", i) is not None]
        with ProcessPoolExecutor(jobs) as ex:
            args = [(str(fs), str(out), i, titles.get(("BGM", i)) or short(sd.name("seq", i))) for i in todo]
            for info in ex.map(_song_job, args):
                idx[f"{info['index']:02X}"] = info
                print(f"song {info['index']:3d} {info['name']} {info['duration']}s", flush=True)
        for s_ in range(sd.count("strm")):
            x = sd.strm_info(s_)
            if x is None:
                continue
            # 사운드 테스트 BGM 1(序曲)이 이 스트림이다. SEQ 칸 0·1 은 비어 있어 번호가 겹치지 않는다
            title = titles.get(("BGM", 1))
            pcm, rate, loop, fmt = strm_decode(sd.file(x["file"]))
            name = stem(1, title) + ".wav"
            write_wav(d / name, pcm, rate)
            idx["01"] = {"index": 1, "kind": "STRM", "name": sd.name("strm", s_), "title": title, "wav": name,
                         "rate": rate, "format": fmt, "channels": pcm.shape[1], "duration": round(len(pcm) / rate, 3),
                         "loopStart": loop, "sdat": fat_entry(sd, x["file"]), "score": None,
                         "scoreNote": "STRM(PCM 녹음)이라 악보(시퀀스)가 없음. 포팅은 FC 곡 02(序曲)의 악보를 쓴다",
                         "fcScore": "fc/dq4/sound/songs/02.json"}
            print(f"strm {s_} {len(pcm) / rate:.1f}s", flush=True)
        write_index(d / "index.json", idx)
    if "sfx" in only:
        d = out / "sfx"
        d.mkdir(parents=True, exist_ok=True)
        subs = sd.names["seqarc"][0][1]
        idx = {}
        with ProcessPoolExecutor(jobs) as ex:
            args = [(str(fs), str(out), k, titles.get(("SE", k)) or short(subs[k])) for k in seqarc_entries(sd, 0)]
            for info in ex.map(_sfx_job, args, chunksize=8):
                if info is not None:
                    info["name"] = subs[info["index"]] if info["index"] < len(subs) else None
                    idx[f"{info['index']:03X}"] = info
        write_index(d / "index.json", idx)
        print(f"sfx {len(idx)}", flush=True)
    if "samples" in only:
        d = out / "samples"
        d.mkdir(parents=True, exist_ok=True)
        idx = {"wavearcs": {}, "banks": {}}
        for w in range(sd.count("wavearc")):
            if sd.record("wavearc", w) is None:
                continue
            fid = sd.wavearc_info(w)["file"]
            raw_arc = sd.file(fid)
            rows = {}
            for k, raw in enumerate(swar_waves(raw_arc)):
                if not raw:
                    continue
                x = decode_swav(raw)
                loop = (x["loop_start"], len(x["pcm"])) if x["loop"] else None
                name = f"{stem(w, None)}-{stem(k, None)}.wav"
                write_wav(d / name, x["pcm"], x["rate"], loop)
                rows[f"{k:02X}"] = {"wav": name, "format": x["format"], "rate": x["rate"], "samples": len(x["pcm"]),
                                    "loop": x["loop"], "loopStart": x["loop_start"],
                                    "sdat": {"file": fid, "offsetInSwar": u32(raw_arc, 0x3C + 4 * k)}}
            idx["wavearcs"][f"{w:02X}"] = {"name": sd.name("wavearc", w), "sdat": fat_entry(sd, fid), "waves": rows}
            print(f"samples {sd.name('wavearc', w)} {len(rows)}", flush=True)
        for b in range(sd.count("bank")):
            bi = sd.bank_info(b)
            if bi is None:
                continue
            insts = sbnk_instruments(sd.file(bi["file"]))
            idx["banks"][f"{b:02X}"] = {
                "name": sd.name("bank", b), "wavearcs": bi["wavearcs"], "sdat": fat_entry(sd, bi["file"]),
                "instruments": [{"program": p, "type": INST_TYPES.get(i["type"], i["type"]), "regions": i["regions"]}
                                for p, i in enumerate(insts) if i["type"]]}
        write_index(d / "index.json", idx)
        print(f"banks {len(idx['banks'])}", flush=True)


def _song_job(args):
    fs, out, i, title = args
    sd = load_sdat(fs)
    y, info, events, stop_tick, ntracks, seq, loop = render_sseq(sd, i, OUT_RATE, loops=2, audio_loops=1)
    base = Path(out) / "songs" / stem(i, title)
    write_wav(base.with_suffix(".wav"), y, OUT_RATE)
    si = sd.seq_info(i)
    data = sd.file(si["file"])
    base.with_suffix(".sseq").write_bytes(data)
    write_midi(base.with_suffix(".mid"), events, stop_tick, loop, ntracks, info["name"])
    write_score(sd, base, seq, f"{i:02X}", "song", stop_tick, loop, u32(data, 0x18), title, info["name"], si,
                f"SSEQ 파일 {si['file']}")
    return info | {"kind": "SSEQ", "title": title, "wav": base.name + ".wav", "midi": base.name + ".mid",
                   "sseq": base.name + ".sseq", "score": base.name + ".json", "scoreText": base.name + ".txt",
                   "sdat": fat_entry(sd, si["file"])}


def write_score(sd, base, seq, ident, kind, stop_tick, loop, data_base, title, name, rec, where):
    """악보 json(base.json)과 txt(base.txt). rec 은 SEQ 레코드나 SSAR 칸(뱅크·음량·우선·플레이어)."""
    bank, insts = bank_doc(sd, rec["bank"], {e["program"] for e in seq.timeline})
    extra = {"name": name, "title": title, "bank": bank, "instruments": insts, "volume": rec["volume"],
             "channel_priority": rec["channel_priority"], "player_priority": rec["player_priority"],
             "player": rec["player"]}
    doc, texts = score_doc(seq, ident, kind, stop_tick, loop, data_base, extra)
    base.with_suffix(".json").write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")),
                                         encoding="utf-8")
    word = "곡" if kind == "song" else "효과음"
    starts = " ".join(f"{c['track']}:${c['start']}" for c in doc["channels"])
    head = (f"{word} {ident}: {title or '-'} ({name}), {where}, 뱅크 {bank['id']} {bank['name']}, 음량 {rec['volume']}, "
            f"플레이어 {rec['player']}, 트랙 {starts}")
    base.with_suffix(".txt").write_text(score_text(doc, head, texts), encoding="utf-8")


def _sfx_job(args):
    fs, out, k, title = args
    sd = load_sdat(fs)
    r = render_seqarc_entry(sd, 0, k, OUT_RATE)
    if r is None:
        return None
    y, info, seq, loop, stop_tick = r
    base = Path(out) / "sfx" / stem(k, title, 3)
    name = base.name + ".wav"
    write_wav(base.with_suffix(".wav"), y, OUT_RATE)
    fid = sd.seqarc_info(0)["file"]
    arc = sd.file(fid)
    _off, bank, vol, cpr, ppr, player = struct.unpack_from("<IHBBBB", arc, 0x20 + 12 * k)
    rec = {"bank": bank, "volume": vol, "channel_priority": cpr, "player_priority": ppr, "player": player}
    subs = sd.names["seqarc"][0][1]
    write_score(sd, base, seq, f"{k:03X}", "sfx", stop_tick, loop, u32(arc, 0x18), title,
                subs[k] if k < len(subs) else None, rec, f"SSAR 파일 {fid} 칸 {k}")
    return info | {"title": title, "wav": name, "score": base.name + ".json", "scoreText": base.name + ".txt",
                   "sdat": fat_entry(sd, fid) | {"seqOffset": u32(arc, 0x18) + u32(arc, 0x20 + 12 * k)}}


SCRIPT_SOUND_OPS = {0x86: "곡", 0x147: "곡, 필드 곡 자동 끔", 0x13A: "ME", 0x62: "효과음", 0x63: "효과음 2"}


def script_sounds(fs=FS):
    """이벤트 스크립트(SCRIPT/<맵>.bin)의 소리 명령 → [(맵, 명령, 번호)]. 명령 뜻은 처리기를 읽어 정함(형식 문서)."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import ndsscript
    out = []
    for f in sorted((Path(fs) / "data/data/SCRIPT").glob("*.bin")):
        for _name, _o, ins in ndsscript.functions(f.read_bytes()):
            for _depth, cmd in ins:
                op = cmd[0] & 0xFFFF
                if op in SCRIPT_SOUND_OPS and len(cmd) > 1:
                    out.append((f.stem, op, cmd[1]))
    return out


# 인물 번호 = 이름 표 MESS/ja/b1001000.mpt 의 색인 + 1
CHARACTERS = {1: "ソロ", 2: "ソフィア", 3: "ライアン", 4: "アリーナ", 5: "クリフト", 6: "ブライ", 7: "トルネコ", 8: "ミネア",
              9: "マーニャ", 23: "ドラン", 24: "ロザリー", 25: "ピサロ"}


def summarize(scene_files, fs=FS):
    """scenes 결과 json 들과 정적 표(맵·조우 레코드·스크립트)를 곡·효과음별 장면 목록으로 묶는다.
    → {"bgm": {곡: [문장]}, "se": {효과음: [문장]}, "measured_bgm": [곡], "measured_se": [효과음], "maps": 검사 결과}."""
    names = place_names(fs)
    rows = {"maps": [], "fields": [], "battles": [], "vehicles": []}
    for f in scene_files:
        r = json.loads(Path(f).read_text())
        for k in rows:
            rows[k] += r.get(k, [])
    bgm, se = {}, {}

    def add(d, k, text):
        d.setdefault(str(k), [])
        if text not in d[str(k)]:
            d[str(k)].append(text)

    def place(m):
        return names.get(m[:2], m[:2].upper())

    measured, measured_se = set(), set()
    agree = disagree = 0
    by = {}
    for r in rows["maps"]:
        if not r["entered"]:
            continue
        want = r["table"]
        # 곡 함수(0x02025B28)는 지금 곡과 같으면 요청하지 않으므로, 요청이 없을 때는 지금 곡을 본다
        got = r["bgm"][-1] if r["bgm"] else r["cur"]
        if want and got == want:
            agree += 1
            by.setdefault((want, r["time"] == 4), set()).add(r["scene"])
            measured.add(want)
        elif want:
            disagree += 1
    for (song, night), maps in sorted(by.items()):
        pl = sorted({place(m) for m in maps})
        add(bgm, song, f"맵{' 밤' if night else ''}: " + "·".join(pl) + f" ({len(maps)}맵)")
    leaders = {}
    for r in rows["fields"]:
        if not r["bgm"]:
            continue
        measured.add(r["bgm"][-1])
        if "leader" in r:
            leaders.setdefault(r["bgm"][-1], []).append(CHARACTERS.get(r["leader"], str(r["leader"])))
        else:
            add(bgm, r["bgm"][-1], "필드 " + r["scene"].replace("ch", "") + "장")
    for b, who in leaders.items():
        add(bgm, b, f"필드 6장 마차와 함께, 선두 {len(who)}명 모두({'·'.join(who)})")
    for r in rows["vehicles"]:
        if r["bgm"]:
            add(bgm, r["bgm"][-1], "필드 " + {1: "기구", 2: "배"}[r["vehicle"]])
            measured.add(r["bgm"][-1])
    table = battle_songs(fs)
    for r in rows["battles"]:
        if not r["bgm"]:
            continue
        b = r["bgm"][0]
        measured.add(b)
        if r.get("record"):
            add(bgm, b, "고정 전투(조우 레코드 " + "·".join(str(k) for k, v in table.items() if v == b) + ")")
        elif "record" in r:
            add(bgm, b, "보통 전투(던전 조우)")
        else:
            add(bgm, b, r["scene"].replace("ch", "").replace(" 전투 테스트", "장 전투 테스트"))
        for x in r["se"]:
            measured_se.add(x)
            add(se, x, "전투")
    for m, op, v in script_sounds(fs):
        kind = SCRIPT_SOUND_OPS[op]
        if op in (0x62, 0x63):
            add(se, v, f"이벤트 {place(m)}")
        elif v:
            add(bgm, v, f"이벤트({kind}) {place(m)}")
    return {"bgm": bgm, "se": se, "measured_bgm": sorted(measured), "measured_se": sorted(measured_se),
            "maps": {"agree": agree, "disagree": disagree}}


GALLERY_CSS = """
body{margin:0 16px;font:14px sans-serif;background:#1d1f24;color:#ddd}
a{color:#9cf} h2{margin-top:2em;border-bottom:1px solid #444} small{color:#888;font-weight:normal}
table{border-collapse:collapse;width:100%} td,th{border-bottom:1px solid #333;padding:3px 6px;text-align:left;
vertical-align:middle} th{color:#aaa;font-weight:normal} audio{height:28px;width:260px} td.n{color:#888}
nav{line-height:1.8} .s{color:#bbb;font-size:12px}
"""


def gallery(out, scenes=None):
    """폴더별 index.json(과 summary 결과)로 gallery/index.html. 소리는 audio 태그(preload=none)."""
    out = Path(out)

    def load(sub):
        p = out / sub / "index.json"
        return json.loads(p.read_text()) if p.exists() else {}

    songs, sfx, samples = load("songs"), load("sfx"), load("samples")
    sc = json.loads(Path(scenes).read_text()) if scenes else {}
    if sc:
        for sub, lst, kind in (("songs", songs, "bgm"), ("sfx", sfx, "se")):
            for v in lst.values():
                v["scenes"] = sc.get(kind, {}).get(str(v["index"]), [])
            write_index(out / sub / "index.json", lst)
    e = html.escape

    def audio(f):
        return f'<audio controls preload="none" src="../{e(f)}"></audio>'

    def where(kind, k):
        return "<br>".join(e(x) for x in sc.get(kind, {}).get(str(k), []))

    secs = []
    rows = []
    for k, b in sorted(songs.items(), key=lambda x: int(x[0], 16)):
        if b["kind"] == "STRM":
            info, links = f"{b['duration']}초, {b['format']} {b['rate']}Hz 스트림 · 오프닝·타이틀", ""
        else:
            loop = f"루프 {b['loopStart']}–{b['loopEnd']}초" if "loopStart" in b else "루프 없음"
            info = f"{b['duration']}초, {loop}"
            links = (f" · <a href=\"../songs/{e(b['midi'])}\">MIDI</a> · "
                     f"<a href=\"../songs/{e(b['sseq'])}\">SSEQ</a>")
        rows.append(f"<tr><td class=n>{k}<br><small>{b['index']}</small></td><td>{e(b.get('title') or '')}"
                    f"<br><small>{e(b['name'] or '')}</small></td><td>{audio('songs/' + b['wav'])}</td>"
                    f"<td class=s>{info}{links}<br>{where('bgm', b['index'])}</td></tr>")
    secs.append(("songs", f"곡 ({len(rows)})", "<table><tr><th>번호</th><th>이름</th><th>합성</th>"
                 "<th>길이·쓰는 장면</th></tr>" + "".join(rows) + "</table>"))
    rows = []
    for k, s_ in sorted(sfx.items(), key=lambda x: int(x[0], 16)):
        rows.append(f"<tr><td class=n>{k}<br><small>{s_['index']}</small></td><td>{e(s_.get('title') or '')}"
                    f"<br><small>{e(s_.get('name') or '')}</small></td><td>{audio('sfx/' + s_['wav'])}</td>"
                    f"<td class=s>{s_['duration']}초{' 루프' if s_['loop'] else ''}, 뱅크 {s_['bank']} "
                    f"플레이어 {s_['player']}<br>{where('se', s_['index'])}</td></tr>")
    secs.append(("sfx", f"효과음 ({len(rows)})", "<table><tr><th>번호</th><th>이름</th><th>합성</th>"
                 "<th>정보·쓰는 장면</th></tr>" + "".join(rows) + "</table>"))
    for w, arc in sorted(samples.get("wavearcs", {}).items()):
        rows = [f"<tr><td class=n>{k}</td><td>{audio('samples/' + x['wav'])}</td><td class=s>{x['format']} "
                f"{x['rate']}Hz {x['samples']}표본{' 루프 ' + str(x['loopStart']) if x['loop'] else ''}</td></tr>"
                for k, x in sorted(arc["waves"].items())]
        secs.append((f"samples-{w}", f"샘플 {w} {arc['name']} ({len(rows)})", "<table>" + "".join(rows) + "</table>"))
    rows = [f"<tr><td class=n>{k}</td><td>{e(b['name'] or '')}</td><td class=s>악기 {len(b['instruments'])}, "
            f"파형 묶음 {b['wavearcs']}</td></tr>" for k, b in sorted(samples.get("banks", {}).items())]
    secs.append(("banks", f"뱅크 ({len(rows)}, 정의는 samples/index.json)", "<table>" + "".join(rows) + "</table>"))
    nav = " · ".join(f'<a href="#{i}">{e(t)}</a>' for i, t, _ in secs)
    body = "".join(f'<h2 id="{i}">{e(t)}</h2>{c}' for i, t, c in secs)
    page = f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>NDS DQ4 소리</title><style>{GALLERY_CSS}</style></head><body>
<h1>NDS 「ドラゴンクエストIV 導かれし者たち」 소리</h1>
<p>참고용 추출본입니다. 배포하지 않습니다. 곡·효과음 WAV 는 SDAT 를 DS 사운드 드라이버 방식으로 근사 합성한 것이고(곡은 도입 +
루프 1회 + 4초 페이드, MIDI 는 루프 2회), 샘플은 SWAR 원본을 옮긴 것입니다. 이름은 사운드 테스트 표(DEBUG/soundlist.dat)와
SYMB 이름입니다. 만든 방법은 <a href="../SOURCE.txt">SOURCE.txt</a>.</p>
<nav>{nav}</nav>
{body}
</body></html>
"""
    (out / "gallery").mkdir(parents=True, exist_ok=True)
    (out / "gallery" / "index.html").write_text(page, encoding="utf-8")


# --- 장면 실측(에뮬레이터) -------------------------------------------------------------------

HOOK_BASE = 0x023F9000        # 장면 실측 때만 쓰는 빈 RAM(여러 장면 덤프에서 늘 0)
HOOK_LOG = 0x023F9100         # u32 기록 수 + 32바이트 기록 256개. 바로 앞 u32 는 곡 바꿔치기(0 이면 그대로)
START_SEQ = 0x0208420C        # (핸들, 곡 번호): 음 관리자 BGM 핸들로 곡 시작
START_SEQARC = 0x02084268     # (핸들, 묶음 번호, 효과음 번호): 효과음 핸들로 SSAR 시작


def hook_code():
    """두 함수 입구를 기록 루틴으로 돌리는 ARM 코드. 기록: 종류(1 곡, 2 효과음), r0, r1, r2, lr, 한 단계 위 lr."""
    def b(frm, to, cond=0xE):
        return (cond << 28) | (0xA << 24) | (((to - frm - 8) >> 2) & 0xFFFFFF)

    w = [0xE92D500F, 0xE3A0C001, None,             # push {r0-r3,r12,lr}; mov r12,#1; b common
         0xE92D500F, 0xE3A0C002, None]             # 효과음 쪽
    common = len(w)
    w += [None,                                    # ldr r3,=HOOK_LOG
          0xE5930000, 0xE20000FF, 0xE0830280, 0xE2800020, 0xE580C000,
          0xE59D1000, 0xE5801004, 0xE59D1004, 0xE5801008, 0xE59D1008, 0xE580100C,
          0xE59D1014, 0xE5801010, 0xE59D1034, 0xE5801014,
          0xE5931000, 0xE2811001, 0xE5831000,
          0xE35C0001, 0x1A000002, 0xE5131004, 0xE3510000, 0x158D1004,   # 곡이고 [HOOK_LOG-4] 가 0 이 아니면 r1 을 바꿈
          0xE35C0001, 0xE8BD500F,
          None,                                    # beq ret_seq
          0xE92D4070, None]                        # 원래 첫 명령(push {r4-r6,lr}); ldr pc,=START_SEQARC+4
    ret = len(w)
    w += [0xE92D4038, None]                        # 원래 첫 명령(push {r3-r5,lr}); ldr pc,=START_SEQ+4
    pool = len(w)
    w += [HOOK_LOG, START_SEQARC + 4, START_SEQ + 4]

    def a(i):
        return HOOK_BASE + 4 * i

    def ldr(rd, i, lit):
        return 0xE59F0000 | (rd << 12) | (a(pool + lit) - a(i) - 8)

    w[2], w[5] = b(a(2), a(common)), b(a(5), a(common))
    w[common] = ldr(3, common, 0)
    w[ret - 3] = b(a(ret - 3), a(ret), 0x0)
    w[ret - 1] = ldr(15, ret - 1, 1)
    w[ret + 1] = ldr(15, ret + 1, 2)
    code = b"".join(struct.pack("<I", x) for x in w)
    patch = {START_SEQ: b(START_SEQ, HOOK_BASE), START_SEQARC: b(START_SEQARC, HOOK_BASE + 12)}
    return code, patch


class Recorder:
    """ndsplay.Player 에 기록 훅을 걸고, 프레임마다 새 기록을 모은다."""

    def __init__(self, player):
        self.p = player
        self.code, self.patch = hook_code()
        self.seen = 0
        self.log = []
        self._run = player.run
        player.run = self.run

    def install(self, override=0):
        self.p.write(HOOK_BASE, self.code)
        self.p.w32(HOOK_LOG, 0)
        self.p.w32(HOOK_LOG - 4, override)
        for a, v in self.patch.items():
            self.p.w32(a, v)
        self.seen = 0
        self.log = []

    def poll(self):
        n = self.p.u32(HOOK_LOG)
        while self.seen < n:
            k, h, a1, a2, lr, lr2 = struct.unpack("<6I", self.p.read(HOOK_LOG + 32 + 32 * (self.seen & 0xFF), 24))
            if k == 1:
                self.log.append((self.p.frame, "bgm", a1, lr))
            else:
                self.log.append((self.p.frame, "se", a2, lr2))
            self.seen += 1

    def run(self, n=1):
        for _ in range(n):
            self._run(1)
            self.poll()

    def bgm(self):
        return [x[2] for x in self.log if x[1] == "bgm"]

    def se(self):
        return [x[2] for x in self.log if x[1] == "se"]


def scenes(out_json, fs=FS, rom=None, maps="sample", shard=(0, 1)):
    """장면마다 곡·효과음 요청을 기록해 json 으로. 세이브스테이트는 work/state/dq4ds-*.state(ndswarp chapters)."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import ndswarp as W
    from ndsplay import Player, core_path

    state = ROOT / "work" / "state"
    rom = rom or str(ROOT / "rom" / "dq4ds.nds")
    tmp = Path(out_json).with_suffix("")
    tmp.mkdir(parents=True, exist_ok=True)
    p = Player(core_path(), rom, str(tmp))
    rec = Recorder(p)
    res = {"maps": [], "fields": [], "battles": [], "events": [], "vehicles": []}

    def start(name):
        W.start(p, str(state / f"dq4ds-{name}.state") if not os.path.isabs(name) else name)
        rec.install()

    def note(kind, tag, **kw):
        row = {"scene": tag, "bgm": rec.bgm(), "se": rec.se(), "cur": p.u32(SOUND_MGR + 4)} | kw
        res[kind].append(row)
        print(kind, json.dumps(row, ensure_ascii=False), flush=True)

    table = map_songs(fs)
    picks = table if maps == "all" else []
    if maps != "all":
        done = set()
        for n, day, night in table:
            if (day, night) not in done:
                done.add((day, night))
                picks.append((n, day, night))
    base = str(tmp / "_ch6.state")
    start("ch6")
    p.save(base)
    for n, day, night in picks[shard[0]::shard[1]]:
        for t, want in ((2, day), (4, night)):
            if t == 4 and night == day:
                continue
            start(base)
            ok = W.enter(p, n, time=t, settle=400)
            note("maps", n, time=t, table=want, entered=ok)
    if shard[0]:
        Path(out_json).write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
        return
    for ch in ("ch1", "ch2", "ch3", "ch4", "ch5", "ch6"):
        start(ch)
        W.field(p, 200, 60)
        note("fields", ch, chapter=p.u32(W.CHAPTER))
    for leader in (1, 3, 4, 7, 8, 25):
        start("ch6")
        order = list(struct.unpack("<13I", p.read(PARTY, 52)))
        if leader in order:
            order.remove(leader)
        order.insert(0, leader)
        p.write(PARTY, struct.pack("<13I", *order[:13]))
        W.field(p, 200, 60)
        note("fields", f"ch6 선두 {leader}", leader=leader)
    for veh in (1, 2):
        start("ch6")
        p.w32(VEHICLE, veh)
        W.field(p, 200, 60)
        note("vehicles", f"ch6 탈것 {veh}", vehicle=veh)
    for ch in ("ch1", "ch4", "ch6"):
        start(ch)
        W.battle(p, [(1, 1)])
        note("battles", f"{ch} 전투 테스트")
    # 실제 조우: 1장 イムルへの洞くつ 에서 걸어 전투를 일으키고, 이길 때까지 A
    start("ch1")
    W.enter(p, "dab1", settle=300)
    fixed = sorted(set(battle_songs(fs)) | {0})
    p.save(str(tmp / "_dab1.state"))
    for idx in fixed:
        start(str(tmp / "_dab1.state"))
        p.frozen[0x020C4CE0] = struct.pack("<i", idx)
        steps = 0
        while p.u32(W.SCENE_CUR) != 0x0D and steps < 160:
            p.hold("left" if steps % 2 else "right", 16)
            steps += 1
        del p.frozen[0x020C4CE0]
        p.run(300)
        if idx == 0:
            for _ in range(120):
                if p.u32(W.SCENE_CUR) != 0x0D:
                    break
                p.press("a", 4, 26)
            p.run(300)
        note("battles", f"조우 레코드 {idx}", record=idx, steps=steps)
    Path(out_json).write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("info", help="SDAT 목록")
    s.add_argument("--fs", default=FS)
    e = sub.add_parser("export", help="소리를 파일로 내고 폴더마다 index.json 을 씀")
    e.add_argument("out")
    e.add_argument("--fs", default=FS)
    e.add_argument("--only", help="쉼표로 songs,sfx,samples")
    e.add_argument("--seq", help="곡 번호(쉼표)")
    e.add_argument("--jobs", type=int)
    g = sub.add_parser("gallery", help="index.json 들로 gallery/index.html")
    g.add_argument("out")
    g.add_argument("--scenes", help="summary 결과 json")
    y = sub.add_parser("summary", help="scenes 결과와 정적 표를 곡·효과음별 장면으로 묶어 json 으로")
    y.add_argument("out")
    y.add_argument("scenes", nargs="+")
    y.add_argument("--fs", default=FS)
    k = sub.add_parser("scorecheck", help="악보 json 의 items 로 MIDI·음표를 다시 만들어 export 결과와 견줌")
    k.add_argument("out")
    m = sub.add_parser("maps", help="맵 정보 표의 낮·밤 곡")
    m.add_argument("--fs", default=FS)
    c = sub.add_parser("scenes", help="에뮬레이터로 장면마다 곡·효과음 요청 기록(DESMUME_CORE 필요)")
    c.add_argument("out")
    c.add_argument("--fs", default=FS)
    c.add_argument("--maps", choices=["all", "sample"], default="sample")
    c.add_argument("--shard", default="0/1", help="맵을 나눠 돌릴 때 i/n(0 번만 필드·전투도 기록)")
    a = ap.parse_args(argv)
    if a.cmd == "info":
        print(summary(load_sdat(a.fs)))
    elif a.cmd == "export":
        export(a.out, a.fs, a.only.split(",") if a.only else None,
               [int(x) for x in a.seq.split(",")] if a.seq else None, a.jobs)
    elif a.cmd == "gallery":
        gallery(a.out, a.scenes)
    elif a.cmd == "summary":
        Path(a.out).write_text(json.dumps(summarize(a.scenes, a.fs), ensure_ascii=False, indent=1), encoding="utf-8")
    elif a.cmd == "scorecheck":
        sys.exit(1 if score_check(a.out) else 0)
    elif a.cmd == "maps":
        for n, day, night in map_songs(a.fs):
            print(f"{n:10s} {day:3d} {night:3d}")
    elif a.cmd == "scenes":
        scenes(a.out, a.fs, maps=a.maps, shard=tuple(int(x) for x in a.shard.split("/")))


if __name__ == "__main__":
    main()
