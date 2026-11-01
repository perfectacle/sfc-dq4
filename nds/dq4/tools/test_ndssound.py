"""SDAT(SYMB·INFO·FAT)·SWAR·SBNK·SWAV·STRM 읽기, 시퀀서·악보 검산·MIDI·WAV·합성, DQ4 표 읽기, 2SF 고침을 롬 없이 검사한다.

입력은 모두 테스트 안에서 조립한 작은 합성 파일이다.
"""
import contextlib
import io
import json
import math
import struct
import tempfile
import types
import unittest
import wave
import zlib
from pathlib import Path

import numpy as np

import ndssound as ns
from test_ndsscript import obj_head, script


# --- 합성 파일 조립 -----------------------------------------------------------------------------

def pad4(b):
    b += b"\0" * (-len(b) % 4)
    return b


def info_block(lists):
    """INFO: 종류마다 u32 개수 + 레코드 위치(INFO 기준, 0 은 빈 칸)."""
    b = bytearray(b"INFO" + bytes(4 + 32))
    for k, kind in enumerate(ns.INFO_KINDS):
        recs = lists.get(kind, [])
        struct.pack_into("<I", b, 8 + 4 * k, len(b))
        at = len(b)
        b += struct.pack("<I", len(recs)) + bytes(4 * len(recs))
        for i, r in enumerate(recs):
            if r is None:
                continue
            struct.pack_into("<I", b, at + 4 + 4 * i, len(b))
            b += r
            pad4(b)
    struct.pack_into("<I", b, 4, len(b))
    return bytes(b)


def symb_block(names):
    """SYMB: 종류마다 이름 위치 목록. seqarc 는 (이름, 안쪽 이름 목록 위치) 쌍."""
    b = bytearray(b"SYMB" + bytes(4 + 32))

    def cstr(s):
        if s is None:
            return 0
        at = len(b)
        b.extend(s.encode("ascii") + b"\0")
        pad4(b)
        return at

    for k, kind in enumerate(ns.INFO_KINDS):
        lst = names.get(kind, [])
        struct.pack_into("<I", b, 8 + 4 * k, len(b))
        at = len(b)
        if kind == "seqarc":
            b += struct.pack("<I", len(lst)) + bytes(8 * len(lst))
            for i, (name, subs) in enumerate(lst):
                sub_at = len(b)
                b += struct.pack("<I", len(subs)) + bytes(4 * len(subs))
                for j, s in enumerate(subs):
                    struct.pack_into("<I", b, sub_at + 4 + 4 * j, cstr(s))
                struct.pack_into("<II", b, at + 4 + 8 * i, cstr(name), sub_at)
        else:
            b += struct.pack("<I", len(lst)) + bytes(4 * len(lst))
            for i, s in enumerate(lst):
                struct.pack_into("<I", b, at + 4 + 4 * i, cstr(s))
    struct.pack_into("<I", b, 4, len(b))
    return bytes(b)


def build_sdat(records, files, names=None):
    head = 0x40
    symb = symb_block(names) if names is not None else b""
    info = info_block(records)
    fat_at = head + len(symb) + len(info)
    fat_size = 12 + 16 * len(files)
    file_at = fat_at + fat_size
    body, fat = bytearray(b"FILE" + bytes(4)), bytearray(b"FAT " + struct.pack("<II", fat_size, len(files)))
    for f in files:
        start = file_at + len(body)
        fat += struct.pack("<IIII", start, len(f), 0, 0)
        body += f
        pad4(body)
    struct.pack_into("<I", body, 4, len(body))
    h = bytearray(b"SDAT" + bytes(head - 4))
    symb_at = head if symb else 0
    struct.pack_into("<8I", h, 0x10, symb_at, len(symb), head + len(symb), len(info), fat_at, fat_size, file_at,
                     len(body))
    return bytes(h + symb + info + fat + body)


def swav(kind, rate, body, loop=False, loop_start=0):
    words = len(body) // 4
    return struct.pack("<BBHHHI", kind, int(loop), rate, 0, loop_start, words - loop_start) + body


def swar(waves):
    """SWAR: 0x38 개수, 0x3C 위치 표. 빈 칸(None)은 위치 0."""
    head = 0x3C + 4 * len(waves)
    out, offs = bytearray(), []
    for w in waves:
        offs.append(0 if w is None else head + len(out))
        out += w or b""
    b = bytearray(b"SWAR" + bytes(0x34)) + struct.pack("<I", len(waves)) + struct.pack(f"<{len(waves)}I", *offs)
    return bytes(b + out)


def region(swav_i=0, swar_i=0, base=60, a=127, d=127, s=127, r=127, pan=64):
    return struct.pack("<HHBBBBBB", swav_i, swar_i, base, a, d, s, r, pan)


def sbnk(insts):
    """insts: [(종류, 자료)] — 자료는 종류에 맞게 조립한 바이트(1~4 는 region 하나)."""
    head = 0x3C + 4 * len(insts)
    out, table = bytearray(), bytearray()
    for t, data in insts:
        table += bytes([t]) + struct.pack("<H", head + len(out) if data else 0) + b"\0"
        out += data or b""
    return bytes(b"SBNK" + bytes(0x34) + struct.pack("<I", len(insts)) + table + out)


def asm(items, base):
    """시퀀스 조립: 바이트열, ("label", 이름), (명령, 이름) — 명령은 0x93 n·0x94·0x95 이고 목적지는 base 기준 u24."""
    labels, size = {}, 0
    for it in items:
        if isinstance(it, tuple) and it[0] == "label":
            labels[it[1]] = size
        elif isinstance(it, tuple):
            size += 5 if it[0] == 0x93 else 4
        else:
            size += len(it)
    out = bytearray()
    for it in items:
        if isinstance(it, tuple) and it[0] == "label":
            continue
        if isinstance(it, tuple):
            op = it[0]
            dest = labels[it[-1]] + base
            dest_rel = dest - base
            out += bytes([op]) + (bytes([it[1]]) if op == 0x93 else b"") + dest_rel.to_bytes(3, "little")
        else:
            out += it
    return bytes(out), {k: v + base for k, v in labels.items()}


SEQ_START = 0x1C


def sseq(body):
    return b"SSEQ" + bytes(0x14) + struct.pack("<I", SEQ_START) + body


def note(key, vel, dur):
    assert dur < 0x80
    return bytes([key, vel, dur])


# 트랙 0: 할당·트랙 1 열기·템포 240(프레임마다 1틱)·악기 0, LOOP 에서 음 → 2회 되풀이 → 부르기 → LOOP 로 뛰기.
# 트랙 1: 음량 → 3틱 쉼 → 음 하나 → 끝.
SONG = [
    b"\xFE\x03\x00", (0x93, 1, "T1"), b"\xE1" + struct.pack("<H", 240), b"\x81\x00",
    ("label", "LOOP"), note(60, 100, 4),
    b"\xD4\x02", note(62, 90, 2), b"\xFC",
    (0x95, "SUB"), (0x94, "LOOP"),
    ("label", "SUB"), b"\xC3\x0C", note(60, 80, 1), b"\xC3\x00", b"\xFD",
    ("label", "T1"), b"\xC1\x64", b"\x80\x03", note(48, 70, 6), b"\xFF",
]


def song_bytes():
    body, labels = asm(SONG, SEQ_START)
    return sseq(body), labels


def ssar(seqs, bank=0, vol=100, player=0):
    """SSAR: 0x18 자료 시작, 0x1C 칸 수, 0x20 부터 12바이트 칸. seqs 의 None 은 빈 칸(FFFFFFFF)."""
    n = len(seqs)
    base = 0x20 + 12 * n
    data, offs = bytearray(), []
    for s in seqs:
        offs.append(0xFFFFFFFF if s is None else len(data))
        data += s or b""
    head = bytearray(b"SSAR" + bytes(0x14)) + struct.pack("<II", base, n)
    for o in offs:
        head += struct.pack("<IHBBBBxx", o, bank, vol, 64, 32, player)
    return bytes(head + data)


def strm(kind, chans, rate, block_samples, loop=None):
    """STRM: 블록마다 채널 순서로 자료. chans: 채널마다 원래 바이트(형식 그대로)."""
    nch = len(chans)
    bps = {0: 1, 1: 2}[kind]
    blen = block_samples * bps
    total = len(chans[0]) // bps
    nblocks = -(-len(chans[0]) // blen)
    lastlen = len(chans[0]) - blen * (nblocks - 1)
    data = bytearray()
    for b in range(nblocks):
        for c in chans:
            data += c[b * blen:b * blen + (blen if b < nblocks - 1 else lastlen)]
    h = bytearray(b"STRM" + bytes(0x14)) + bytes([kind, int(loop is not None), nch, 0]) + struct.pack("<HH", rate, 0)
    data_off = 0x40
    h += struct.pack("<8I", loop or 0, total, data_off, nblocks, blen, block_samples, lastlen, lastlen // bps)
    h += bytes(data_off - len(h))
    return bytes(h + data)


def ima_encode(samples, pred=0, idx=0):
    """IMA-ADPCM 인코더(검산용, 디코더와 따로 짬). → (니블 바이트, 끝 예측값)."""
    nibs = []
    for x in samples:
        step = ns.IMA_STEP[idx]
        diff = int(x) - pred
        nib = 0
        if diff < 0:
            nib, diff = 8, -diff
        q = 0
        if diff >= step:
            q |= 4
            diff -= step
        if diff >= step >> 1:
            q |= 2
            diff -= step >> 1
        if diff >= step >> 2:
            q |= 1
        nib |= q
        d = step >> 3
        if q & 1:
            d += step >> 2
        if q & 2:
            d += step >> 1
        if q & 4:
            d += step
        pred = max(-32768, min(32767, pred - d if nib & 8 else pred + d))
        idx = max(0, min(88, idx + ns.IMA_INDEX[q]))
        nibs.append(nib)
    if len(nibs) % 2:
        nibs.append(0)
    return bytes(nibs[i] | nibs[i + 1] << 4 for i in range(0, len(nibs), 2))


def seq_rec(fid, bank, vol=100, player=0):
    return struct.pack("<HHHBBBB", fid, 0, bank, vol, 64, 32, player)


def bank_rec(fid, arcs):
    return struct.pack("<HH4H", fid, 0, *(list(arcs) + [0xFFFF] * (4 - len(arcs))))


PCM8 = bytes((i * 16) & 0xFF for i in range(64))


def song_sdat():
    """파일: 0 SSEQ, 1 SBNK, 2 SWAR, 3 SSAR, 4 STRM. 레코드: SEQ 0 은 빈 칸, SEQ 1 이 곡."""
    seq, _ = song_bytes()
    bank = sbnk([(1, region(base=60)), (2, region(swav_i=3, base=69)), (0, None)])
    arc = swar([swav(0, 8000, PCM8, loop=True, loop_start=4)])
    sfx = asm([b"\xE1\xF0\x00", note(70, 120, 3), b"\xFF"], 0)[0]
    ar = ssar([sfx, None, sfx])
    st = strm(1, [struct.pack("<4h", 1, 2, 3, 4), struct.pack("<4h", -1, -2, -3, -4)], 22050, 3)
    records = {
        "seq": [None, seq_rec(0, 0)],
        "seqarc": [struct.pack("<HH", 3, 0)],
        "bank": [bank_rec(1, [0])],
        "wavearc": [struct.pack("<I", 2 | 0xAB000000)],
        "player": [struct.pack("<BBHI", 1, 0, 0b101, 0x1000)],
        "group": [struct.pack("<I", 2) + struct.pack("<BBHI", 0, 1, 0, 1) + struct.pack("<BBHI", 9, 2, 0, 7)],
        "player2": [bytes([3, 4, 5, 6]) + bytes(13)],
        "strm": [struct.pack("<HHBBB", 4, 0, 90, 1, 0) + bytes(3)],
    }
    names = {"seq": [None, "SND_BGM_M01_TEST"], "seqarc": [("SE_ARC", ["SND_SE_M_A", None, "SND_SE_M_C"])],
             "bank": ["BANK0"], "wavearc": ["WAVE0"], "player": ["PL0"], "group": ["G0"], "player2": ["P2"],
             "strm": ["STRM0"]}
    return build_sdat(records, [seq, bank, arc, ar, st], names)


# --- 테스트 -------------------------------------------------------------------------------------

class SdatTests(unittest.TestCase):
    def setUp(self):
        self.sd = ns.Sdat(song_sdat())

    def test_rejects_other_magic(self):
        with self.assertRaises(ValueError):
            ns.Sdat(b"XXXX" + bytes(0x40))

    def test_records_and_empty_slots(self):
        sd = self.sd
        self.assertEqual(sd.count("seq"), 2)
        self.assertIsNone(sd.record("seq", 0))
        self.assertIsNone(sd.seq_info(0))
        self.assertIsNone(sd.record("seq", 5))     # 개수 밖
        self.assertEqual(sd.seq_info(1), {"file": 0, "bank": 0, "volume": 100, "channel_priority": 64,
                                          "player_priority": 32, "player": 0})
        self.assertEqual(sd.bank_info(0), {"file": 1, "wavearcs": [0]})   # FFFF 칸은 뺀다
        self.assertEqual(sd.wavearc_info(0), {"file": 2})                 # 위 바이트(플래그)는 파일 번호가 아님
        self.assertEqual(sd.player_info(0), {"max_seq": 1, "channels": [0, 2], "heap": 0x1000})
        self.assertEqual(sd.group_info(0), [{"kind": "seq", "load_flags": 1, "index": 1},
                                            {"kind": 9, "load_flags": 2, "index": 7}])
        self.assertEqual(sd.player2_info(0), {"channels": [4, 5, 6]})
        self.assertEqual(sd.strm_info(0), {"file": 4, "volume": 90, "priority": 1, "player": 0})
        self.assertEqual(sd.seqarc_info(0), {"file": 3})
        for f in ("seqarc", "bank", "wavearc", "player", "group", "player2", "strm"):
            self.assertIsNone(getattr(sd, f + "_info")(3))

    def test_fat_gives_exact_file_bytes(self):
        seq, _ = song_bytes()
        self.assertEqual(self.sd.file(0), seq)
        self.assertEqual(self.sd.file(2)[:4], b"SWAR")
        self.assertEqual(ns.fat_entry(self.sd, 0)["size"], len(seq))

    def test_symbol_names(self):
        sd = self.sd
        self.assertEqual(sd.name("seq", 1), "SND_BGM_M01_TEST")
        self.assertIsNone(sd.name("seq", 0))
        self.assertIsNone(sd.name("seq", 9))
        self.assertEqual(sd.name("seqarc", 0), "SE_ARC")
        self.assertIsNone(sd.name("seqarc", 4))
        self.assertEqual(sd.names["seqarc"][0][1], ["SND_SE_M_A", None, "SND_SE_M_C"])

    def test_no_symb_block(self):
        sd = ns.Sdat(build_sdat({"seq": [seq_rec(0, 0)]}, [b"x"]))
        self.assertEqual(sd.names, {})
        self.assertIsNone(sd.name("seq", 0))

    def test_summary_lists_every_present_record(self):
        text = ns.summary(self.sd)
        self.assertIn("[seq] 칸 2, 레코드 1", text)
        self.assertIn("시퀀스 2", text)          # SSAR 의 빈 칸(FFFFFFFF)은 세지 않는다
        self.assertIn("PCM16 채널 2 22050Hz 샘플 4", text)
        self.assertIn("악기 칸 3", text)


class WaveTests(unittest.TestCase):
    def test_ima_hand_computed(self):
        # 니블 7(step 7): 0 + 1 + 3 + 7 = 11, 색인 0 → 8. 니블 F(step 16): -(2 + 4 + 8 + 16) = -30
        out = ns.decode_ima(bytes([0xF7]), 0, 0)
        self.assertEqual((out * 32768).round().tolist(), [11, -19])

    def test_ima_header_and_clamp(self):
        out = ns.decode_ima(struct.pack("<hH", 32760, 88) + bytes([0x77]))
        self.assertEqual(out[0] * 32768, 32767)     # 위로 넘치면 잘린다
        out = ns.decode_ima(struct.pack("<hH", 0, 0) + bytes([0x88] * 4))
        self.assertTrue(all(o <= 0 for o in out))   # 색인은 0 아래로 내려가지 않는다(step 7 유지)

    def test_ima_round_trip(self):
        x = (np.sin(np.arange(400) / 9) * 12000).astype(np.int64)
        raw = ima_encode(x)
        y = ns.decode_ima(raw, 0, 0)[:len(x)] * 32768
        self.assertLess(float(np.abs(y[50:] - x[50:]).max()), 1200)

    def test_swav_loop_units(self):
        w = ns.decode_swav(swav(0, 8000, PCM8, True, 4))
        self.assertEqual((w["format"], w["rate"], w["loop"], w["loop_start"]), ("PCM8", 8000, True, 16))
        self.assertEqual(len(w["pcm"]), 64)
        self.assertAlmostEqual(float(w["pcm"][1]), 16 / 128)
        w = ns.decode_swav(swav(1, 11025, struct.pack("<8h", *range(8)), False, 2))
        self.assertEqual((w["format"], w["loop_start"], len(w["pcm"])), ("PCM16", 4, 8))
        ima = struct.pack("<hH", 0, 0) + bytes(12)
        w = ns.decode_swav(swav(2, 16000, ima, True, 2))
        self.assertEqual((w["format"], w["loop_start"], len(w["pcm"])), ("IMA-ADPCM", 8, 24))   # 머리 워드는 뺀다

    def test_swav_ignores_bytes_after_loop_end(self):
        raw = swav(0, 8000, PCM8, False, 0) + b"\x7F" * 16
        self.assertEqual(len(ns.decode_swav(raw)["pcm"]), 64)

    def test_swar_slices_by_sorted_offsets(self):
        a, b = swav(0, 1, bytes(8)), swav(0, 2, bytes(16))
        waves = ns.swar_waves(swar([a, None, b]))
        self.assertEqual(waves, [a, b"", b])
        with self.assertRaises(ValueError):
            ns.swar_waves(b"SBNK" + bytes(0x40))

    def test_sbnk_kinds(self):
        drum = bytes([36, 38])
        for k in range(3):
            drum += struct.pack("<H", 1) + region(swav_i=k, base=36 + k)
        split = bytes([40, 80, 0, 0, 0, 0, 0, 0])
        split += struct.pack("<H", 1) + region(swav_i=5) + struct.pack("<H", 2) + region(swav_i=6)
        insts = ns.sbnk_instruments(sbnk([(1, region(swav_i=9, pan=10)), (0x10, drum), (0x11, split), (0, None)]))
        self.assertEqual(insts[0]["regions"][0] | {}, insts[0]["regions"][0])
        self.assertEqual((insts[0]["regions"][0]["swav"], insts[0]["regions"][0]["pan"],
                          insts[0]["regions"][0]["lo"], insts[0]["regions"][0]["hi"]), (9, 10, 0, 127))
        self.assertEqual([(r["lo"], r["hi"], r["swav"]) for r in insts[1]["regions"]], [(36, 36, 0), (37, 37, 1),
                                                                                        (38, 38, 2)])
        self.assertEqual([(r["lo"], r["hi"], r["type"]) for r in insts[2]["regions"]], [(0, 40, 1), (41, 80, 2)])
        self.assertEqual(insts[3], {"type": 0, "regions": []})
        with self.assertRaises(ValueError):
            ns.sbnk_instruments(b"SWAR" + bytes(0x40))

    def test_strm_interleaved_blocks(self):
        left, right = struct.pack("<5h", 1, 2, 3, 4, 5), struct.pack("<5h", -1, -2, -3, -4, -5)
        pcm, rate, loop, fmt = ns.strm_decode(strm(1, [left, right], 32000, 2, loop=3))
        self.assertEqual((rate, loop, fmt, pcm.shape), (32000, 3, "PCM16", (5, 2)))
        self.assertEqual((pcm[:, 0] * 32768).tolist(), [1, 2, 3, 4, 5])
        self.assertEqual((pcm[:, 1] * 32768).tolist(), [-1, -2, -3, -4, -5])
        pcm, _, loop, fmt = ns.strm_decode(strm(0, [bytes([1, 2, 3])], 8000, 2))
        self.assertEqual((loop, fmt, (pcm[:, 0] * 128).tolist()), (None, "PCM8", [1, 2, 3]))
        with self.assertRaises(ValueError):
            ns.strm_decode(b"SSEQ" + bytes(0x40))

    def test_strm_ima_block_has_own_header(self):
        blk = struct.pack("<hH", 100, 0) + bytes([0x00])   # 니블 0 두 개: +0 씩(step 7 >> 3 = 0)
        data = bytearray(strm(0, [bytes(len(blk) * 2)], 8000, len(blk)))
        data[0x18] = 2
        struct.pack_into("<I", data, 0x24, 4)
        data[0x40:] = blk + blk
        pcm, _, _, fmt = ns.strm_decode(bytes(data))
        self.assertEqual(fmt, "IMA-ADPCM")
        self.assertEqual((pcm[:, 0] * 32768).tolist(), [100, 100, 100, 100])


class SmallFunctionTests(unittest.TestCase):
    def test_db_and_envelope_rates(self):
        self.assertEqual(ns.db_square(127), 0)
        self.assertEqual(ns.db_square(0), -32768)
        self.assertEqual(ns.db_square(1), -723)
        self.assertEqual(ns.db_square(500), 0)
        self.assertEqual(ns.cnv_attack(127), 0)
        self.assertEqual(ns.cnv_attack(0), 0xFF)
        self.assertEqual([ns.cnv_fall(f) for f in (0x7F, 0x7E, 0, 0x31, 0x32)], [0xFFFF, 0x3C00, 1, 99, 0x1E00 // 0x4C])
        self.assertEqual(ns.amplitude(-723), 0.0)
        self.assertAlmostEqual(ns.amplitude(-200), 0.1)

    def test_sin_idx_quarters(self):
        self.assertEqual([ns.sin_idx(i) for i in (0, 32, 64, 96, 128)], [0, 127, 0, -127, 0])
        self.assertEqual(ns.sin_idx(16), -ns.sin_idx(80))

    def test_noise_table_is_one_lfsr_period(self):
        t = ns.noise_table()
        self.assertEqual(len(t), 32767)
        self.assertEqual(set(np.unique(t).tolist()), {-1.0, 1.0})

    def test_names(self):
        self.assertEqual(ns.note_name(60), "C4")
        self.assertEqual(ns.note_name(61), "C#4")
        self.assertEqual(ns.stem(0x1A, "a/b"), "1A-a／b")
        self.assertEqual(ns.stem(5, None, 3), "005")
        self.assertEqual(ns.short("SND_BGM_M01_X"), "M01_X")
        self.assertEqual(ns.short("SND_SE_M_CURSOR"), "CURSOR")
        self.assertIsNone(ns.short(None))
        self.assertEqual(ns.song_word(7), struct.pack("<I", 0xE3A04007))
        self.assertEqual(ns.rom_offset(0x02000010), 0x4010)


class FakeBank:
    def __init__(self, typ=1, rate=8000):
        self.typ = typ
        self.w = {"pcm": np.ones(64, np.float32), "rate": rate, "loop": False, "loop_start": 0}

    def region(self, prog, key):
        return {"type": self.typ, "base": 60, "attack": 127, "decay": 127, "sustain": 127, "release": 127,
                "pan": 64, "swav": 3}

    def wave(self, r):
        return self.w


def run_song(loops=2):
    data, labels = song_bytes()
    seq = ns.Sequencer(data, SEQ_START, FakeBank())
    frames, loop, stop = ns.run_sequence(seq, loops=loops, fade_seconds=0.0)
    return seq, loop, stop, labels


class SequencerTests(unittest.TestCase):
    def test_song_events_loop_and_tracks(self):
        seq, loop, stop, labels = run_song()
        self.assertEqual((loop["start_tick"], loop["end_tick"]), (0, 9))
        self.assertEqual(stop, 18)                  # 루프 끝 + (2 - 1) × 루프 길이
        self.assertEqual([t.start for t in seq.tracks], [SEQ_START, labels["T1"]])
        self.assertEqual([t.number for t in seq.tracks], [0, 1])
        notes = [e for e in seq.events if e[2] == "note" and e[0] <= 9]
        self.assertEqual(notes, [(0, 0, "note", 60, 100, 4), (4, 0, "note", 62, 90, 2), (4, 1, "note", 48, 70, 6),
                                 (6, 0, "note", 62, 90, 2), (8, 0, "note", 72, 80, 1), (9, 0, "note", 60, 100, 4)])
        self.assertIn((0, 0, "tempo", 240), seq.events)
        self.assertIn((1, 1, "cc", 7, 0x64), seq.events)   # 연 트랙은 다음 틱부터 돈다
        self.assertTrue(seq.tracks[1].done)
        self.assertLessEqual(loop["start_frame"], loop["end_frame"])

    def test_conditions_variables_and_random(self):
        prog = (b"\xC7\x00" + b"\xB0\x00" + struct.pack("<h", 5) + b"\xB8\x00" + struct.pack("<h", 5)
                + b"\xA2" + note(64, 100, 1) + b"\xB8\x00" + struct.pack("<h", 6) + b"\xA2" + note(65, 100, 1)
                + b"\xA1\x80\x00" + b"\xA0" + bytes([67, 100]) + struct.pack("<hh", 3, 3) + b"\xFF")
        seq = ns.Sequencer(prog, 0, FakeBank())
        ns.run_sequence(seq, max_seconds=2)
        notes = [e for e in seq.events if e[2] == "note"]
        self.assertEqual(notes, [(0, 0, "note", 64, 100, 1), (5, 0, "note", 67, 100, 3)])

    def test_var_ops_clamp_and_divide_by_zero(self):
        seq = ns.Sequencer(b"\xFF", 0, FakeBank())
        t = seq.tracks[0]
        seq.var_op(t, 0xB0, 1, 30000)
        seq.var_op(t, 0xB1, 1, 30000)
        self.assertEqual(seq.vars[1], 32767)
        seq.var_op(t, 0xB4, 1, 0)
        self.assertEqual(seq.vars[1], 32767)
        seq.var_op(t, 0xB0, 2, -7)
        seq.var_op(t, 0xB4, 2, 2)
        self.assertEqual(seq.vars[2], -3)           # 0 쪽으로 버림
        seq.var_op(t, 0xB5, 2, -1)
        self.assertEqual(seq.vars[2], -2)
        seq.var_op(t, 0xB0, 3, 3)
        seq.var_op(t, 0xB5, 3, 2)
        seq.var_op(t, 0xB2, 3, 2)
        seq.var_op(t, 0xB3, 3, 3)
        self.assertEqual(seq.vars[3], 30)
        for c, want in ((0xB9, True), (0xBA, False), (0xBB, True), (0xBC, False), (0xBD, False)):
            seq.var_op(t, c, 3, 30)
            self.assertEqual(t.cond, want, hex(c))
        seq.var_op(t, 0xB6, 4, 10)
        self.assertTrue(0 <= seq.vars[4] <= 10)
        seq.var_op(t, 0xB6, 4, -10)
        self.assertTrue(-10 <= seq.vars[4] <= 0)

    def test_unknown_command_raises(self):
        seq = ns.Sequencer(b"\xF0", 0, FakeBank())
        with self.assertRaises(ValueError):
            seq.step_track(0, seq.tracks[0])

    def test_voice_stealing_by_priority(self):
        seq = ns.Sequencer(b"\xFF", 0, FakeBank(), max_voices=1)
        a, b, c = ns.Track(0), ns.Track(0), ns.Track(0)
        a.prio, b.prio, c.prio = 64, 32, 100
        seq.note(0, a, 60, 100, 10)
        seq.note(1, b, 62, 100, 10)                 # 더 낮은 우선순위는 버려진다
        self.assertEqual([v.t for v in seq.voices], [a])
        seq.note(2, c, 64, 100, 10)                 # 더 높은 우선순위는 뺏는다
        self.assertTrue(seq.voices[0].dead)
        self.assertIs(seq.voices[-1].t, c)

    def test_tie_reuses_voice(self):
        seq = ns.Sequencer(b"\xFF", 0, FakeBank())
        t = ns.Track(0)
        seq.control(0, t, 0xC8, 1)
        seq.note(0, t, 60, 100, 4)
        seq.note(0, t, 64, 90, 4)
        self.assertEqual(len(seq.voices), 1)
        self.assertEqual((seq.voices[0].key, seq.voices[0].vel, seq.voices[0].left), (64, 90, None))
        seq.control(0, t, 0xC8, 0)                  # 묶음을 풀면 놓는다
        self.assertEqual(seq.voices[0].state, "release")

    def test_controls_and_sweep(self):
        seq = ns.Sequencer(b"\xFF", 0, FakeBank())
        t = ns.Track(0)
        for c, v in ((0xC0, 10), (0xC2, 90), (0xC3, -2), (0xC4, 5), (0xC5, 12), (0xC6, 70), (0xC7, 0),
                     (0xC9, 50), (0xCA, 3), (0xCB, 20), (0xCC, 1), (0xCD, 2), (0xCF, 4), (0xD0, 100), (0xD5, 80)):
            seq.control(0, t, c, v)
        self.assertEqual((t.pan, seq.seq_vol, t.transpose, t.bend, t.bend_range, t.prio, t.note_wait),
                         (10, 90, -2, 5, 12, 70, False))
        self.assertEqual((t.porta_key, t.porta_on, t.porta_time, t.adsr[0], t.expr), (48, True, 4, 100, 80))
        self.assertEqual(t.mod, {"depth": 3, "speed": 20, "type": 1, "range": 2, "delay": 0})
        seq.note(0, t, 60, 100, 8)
        v = seq.voices[0]
        self.assertEqual(v.key, 58)                 # 전치 -2
        self.assertEqual(v.sweep_from, (48 - 58) << 6)
        self.assertEqual(v.sweep_len, (4 * 4 * abs(v.sweep_from)) >> 11)
        self.assertEqual(v.attack, ns.cnv_attack(100))   # 트랙 ADSR 가 악기 값을 덮는다
        seq.control(0, t, 0xCE, 0)
        t.sweep = 64
        seq.note(0, t, 60, 100, 8)
        self.assertEqual((seq.voices[1].sweep_from, seq.voices[1].sweep_len), (64, round(8 * 240 / 120)))

    def test_voice_envelope_states(self):
        t = ns.Track(0)
        r = FakeBank().region(0, 0) | {"attack": 120, "sustain": 100, "decay": 0x7E, "release": 0x7E}
        v = ns.Voice(t, r, None, 60, 100, 2, 0)
        states = []
        for _ in range(50):
            if not v.envelope():
                break
            states.append(v.state)
        self.assertEqual(states[0], "attack")
        self.assertIn("sustain", states)
        self.assertEqual(v.amp, v.sust)
        v.release()
        self.assertFalse(all(v.envelope() for _ in range(100)))

    def test_voice_out_pitch_pan_and_lfo(self):
        seq = ns.Sequencer(b"\xFF", 0, FakeBank(rate=8000))
        t = ns.Track(0)
        t.pan = 0
        seq.note(0, t, 72, 127, 4)
        v = seq.voices[0]
        v.amp = 0
        gl, gr, rate = seq.voice_out(v)
        self.assertAlmostEqual(rate, 16000)         # 한 옥타브 위 = 두 배
        self.assertEqual(gr, 0.0)
        self.assertGreater(gl, 0.9)
        t.mod.update(depth=10, speed=64, range=1, type=2)
        for _ in range(30):
            seq.voice_out(v)
        self.assertGreater(v.mod_count, 0)
        psg = ns.Sequencer(b"\xFF", 0, FakeBank(typ=2))
        psg.note(0, ns.Track(0), 60, 127, 1)
        self.assertAlmostEqual(psg.voice_out(psg.voices[0])[2], ns.PSG_BASE_HZ * 8 * 2 ** (-0 / 768))

    def test_frame_step_releases_after_length(self):
        seq = ns.Sequencer(b"\xFF", 0, FakeBank())
        seq.tempo = 240
        t = ns.Track(0)
        seq.note(0, t, 60, 100, 2)
        for _ in range(3):
            seq.frame_step()
        self.assertTrue(all(v.state == "release" for v in seq.voices + seq.finished))

    def test_no_loop_runs_until_quiet(self):
        seq = ns.Sequencer(b"\xE1\xF0\x00" + note(60, 100, 2) + b"\xFF", 0, FakeBank())
        frames, loop, stop = ns.run_sequence(seq, max_seconds=5, tail_seconds=0.5)
        self.assertIsNone(loop)
        self.assertEqual(stop, seq.ticks)
        self.assertLess(frames, 5 * ns.FRAME_RATE)


class ScoreTests(unittest.TestCase):
    def test_items_rerun_matches_sequencer(self):
        """악보 json 의 items 만으로 돌린 사건이 시퀀서 사건과 같아야 한다(score_check 의 검산)."""
        seq, loop, stop, labels = run_song()
        doc, texts = ns.score_doc(seq, "01", "song", stop, loop, SEQ_START, {"name": "x"})
        events, ntracks = ns.score_events(doc)
        self.assertEqual(ntracks, 2)
        mine = sorted(e for e in events if e[2] == "note")
        ref = sorted(e for e in seq.events if e[2] == "note" and e[0] <= stop)
        self.assertEqual(mine, ref)
        names = {c["name"]: i for i, c in enumerate(doc["channels"])}
        tl = sorted((e["tick"], names[e["ch"]], e["note"], e["velocity"], e["gate"]) for e in doc["timeline"])
        self.assertEqual(tl, [(e[0], e[1], e[3], e[4], e[5]) for e in ref])
        self.assertEqual((doc["tempo"], doc["loop_start"], doc["loop_len"], doc["end_tick"]), (240, 0, 9, 18))
        items = {it["addr"]: it for it in doc["channels"][0]["items"]}
        loop_end = [it for it in items.values() if it["op"] == "loop-end"][0]
        loop_start = [a for a, it in items.items() if it["op"] == "loop-start"][0]
        self.assertEqual(loop_end["target"], int(loop_start, 16) + 2)   # 되풀이 끝은 시작 명령 바로 뒤로
        jump = [it for it in items.values() if it["op"] == "jump"][0]
        self.assertEqual(jump["target"], labels["LOOP"])
        text = ns.score_text(doc, "머리", texts)
        self.assertIn("되풀이: 0틱부터 9틱", text)
        self.assertIn("끝: 18틱", text)

    def test_tempo_changes_skip_repeats(self):
        prog = b"\xE1\x78\x00" + note(60, 1, 2) + b"\xE1\x78\x00" + note(60, 1, 2) + b"\xE1\xF0\x00" + b"\xFF"
        seq = ns.Sequencer(prog, 0, FakeBank())
        _, loop, stop = ns.run_sequence(seq, max_seconds=2)
        doc, _ = ns.score_doc(seq, "x", "sfx", stop, loop, 0, {})
        self.assertEqual(doc["tempo"], 120)
        self.assertEqual(doc["tempo_changes"], [[4, 240]])

    def test_decode_cmd_prefixes_and_errors(self):
        size, item, text = ns.decode_cmd(b"\xA0\x80" + struct.pack("<hh", 1, 9), 0, 0)
        self.assertEqual((size, item["prefix"], item["len"]), (6, "random", [1, 9]))
        size, item, _ = ns.decode_cmd(b"\xA1\xC1\x05", 0, 0)
        self.assertEqual((size, item["args"]), (3, [{"var": 5}]))
        size, item, text = ns.decode_cmd(b"\xFE\x05\x00", 0, 0)
        self.assertEqual(item["args"], [5])
        self.assertIn("트랙 0,2", text)
        size, item, text = ns.decode_cmd(b"\xD4\x00", 0, 0)
        self.assertEqual(item["count"], 0)
        self.assertIn("∞", text)
        size, item, _ = ns.decode_cmd(b"\xB1\x03" + struct.pack("<h", -4), 0, 0)
        self.assertEqual((size, item["op"], item["args"]), (4, "var-B1", [3, -4]))
        size, item, _ = ns.decode_cmd(b"\x00\x00\x93\x02\x10\x00\x00", 2, 0x100)
        self.assertEqual((size, item["target"], item["track"]), (5, 0x110, 2))
        with self.assertRaises(ValueError):
            ns.decode_cmd(b"\xF0", 0, 0)

    def test_score_events_refuses_prefixed_items(self):
        doc = {"end_tick": 1, "channels": [{"start": "0000", "track": 0, "items": [
            {"addr": "0000", "bytes": "A0 80 00 00 00 00", "op": "rest", "prefix": "random"}]}]}
        with self.assertRaises(ValueError):
            ns.score_events(doc)

    def test_score_events_rejects_track_order_mismatch(self):
        seq, loop, stop, _ = run_song()
        doc, _ = ns.score_doc(seq, "01", "song", stop, loop, SEQ_START, {})
        doc["channels"][1]["start"] = "0000"
        with self.assertRaises(ValueError):
            ns.score_events(doc)


class MidiWavTests(unittest.TestCase):
    def test_midi_round_trip(self):
        seq, loop, stop, _ = run_song()
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "x.mid"
            ns.write_midi(path, seq.events, stop, loop, len(seq.tracks), "テスト")
            data = path.read_bytes()
        self.assertEqual(data[:4], b"MThd")
        self.assertEqual(struct.unpack(">HHH", data[8:14]), (1, 3, 48))
        self.assertIn(b"loopStart", data)
        notes, tempos = ns.midi_notes(data)
        self.assertEqual(tempos, [(0, round(60_000_000 / 240))])
        want = sorted((ti + 1, t, min(t + max(d, 1), stop), k, v)
                      for t, ti, kind, k, v, d in (e for e in seq.events if e[2] == "note") if t < stop)
        self.assertEqual(sorted(n for n in notes if n[1] is not None and n[2] is not None), want)

    def test_midi_other_events(self):
        events = [(0, 0, "prog", 130), (0, 0, "cc", 7, 200), (1, 0, "bend", -200), (1, 0, "range", 12),
                  (2, 0, "note", 60, 0, 0), (9, 0, "note", 61, 10, 1), (2, 5, "note", 62, 10, 1)]
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "y.mid"
            ns.write_midi(path, events, 5, None, 1, "t")
            data = path.read_bytes()
        self.assertIn(bytes([0xB0, 0, 1, 0, 0xC0, 2]), data)   # 뱅크 = 프로그램 >> 7, 프로그램 & 7F
        self.assertIn(bytes([0xB0, 7, 127]), data)               # 127 로 자름
        self.assertIn(bytes([0xE0, 0, 0]), data)                 # 벤드는 0 아래로 내려가지 않음
        notes, _ = ns.midi_notes(data)
        self.assertEqual([n[1:] for n in notes], [(2, 3, 60, 1)])   # 끊는 틱 뒤·없는 트랙 사건은 뺀다

    def test_wav_with_smpl_chunk(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "a.wav"
            ns.write_wav(p, np.array([0.0, 0.5, -2.0], np.float32), 8000, loop=(1, 3))
            data = p.read_bytes()
            with wave.open(str(p)) as w:
                self.assertEqual((w.getnchannels(), w.getframerate(), w.getnframes()), (1, 8000, 3))
                self.assertEqual(struct.unpack("<3h", w.readframes(3)), (0, 16383, -32767))
        self.assertEqual(struct.unpack_from("<I", data, 4)[0], len(data) - 8)
        at = data.index(b"smpl")
        self.assertEqual(struct.unpack_from("<II", data, at + 8 + 36 + 8), (1, 2))   # 끝은 포함(끝 - 1)

    def test_finish_audio_normalizes_and_fades(self):
        y = np.ones((10, 2), np.float32) * 0.5
        out, peak = ns.finish_audio(y, 8000, fade_from=5)
        self.assertEqual(peak, 0.5)
        self.assertAlmostEqual(float(out[0, 0]), 10 ** (-1 / 20), 5)
        self.assertEqual(float(out[-1, 0]), 0.0)
        out, peak = ns.finish_audio(np.zeros((0, 2), np.float32), 8000)
        self.assertEqual(peak, 0)


def fake_voice(pcm, loop, loop_start, rate, frames, typ=1, start=0):
    return types.SimpleNamespace(frames=[(1.0, 0.0, rate)] * frames, start=start, r={"type": typ, "swav": 3},
                                 w={"pcm": np.asarray(pcm, np.float32), "loop": loop, "loop_start": loop_start})


class RenderTests(unittest.TestCase):
    RATE = 32768

    def test_pcm_loop_wraps_to_loop_start(self):
        pcm = np.arange(8) / 8
        out = ns.render_voices([fake_voice(pcm, True, 4, self.RATE, 1)], self.RATE, 1)
        want = [pcm[k] if k < 8 else pcm[4 + (k - 4) % 4] for k in range(16)]
        np.testing.assert_allclose(out[:16, 0], want, atol=1e-6)
        self.assertEqual(float(np.abs(out[:, 1]).max()), 0.0)

    def test_pcm_without_loop_stops(self):
        out = ns.render_voices([fake_voice(np.ones(8), False, 0, self.RATE, 1)], self.RATE, 1)
        self.assertEqual(out[:7, 0].tolist(), [1.0] * 7)
        self.assertEqual(float(np.abs(out[7:, 0]).max()), 0.0)

    def test_voice_starts_at_its_frame_and_is_cut_at_total(self):
        edges = np.floor(np.arange(5) * self.RATE / ns.FRAME_RATE).astype(np.int64)
        out = ns.render_voices([fake_voice(np.ones(5000), False, 0, self.RATE, 10, start=2)], self.RATE, 3)
        self.assertEqual(float(np.abs(out[:edges[2], 0]).max()), 0.0)
        self.assertEqual(float(out[edges[2], 0]), 1.0)
        self.assertEqual(float(np.abs(out[edges[3]:, 0]).max()), 0.0)

    def test_psg_and_noise(self):
        sq = fake_voice([0], False, 0, self.RATE, 1, typ=2)     # swav 3 → 듀티 4/8
        out = ns.render_voices([sq], self.RATE, 1)
        self.assertEqual(out[:8, 0].tolist(), [0.5] * 4 + [-0.5] * 4)
        nz = fake_voice([0], False, 0, self.RATE, 1, typ=3)
        out = ns.render_voices([nz], self.RATE, 1)
        self.assertEqual(set(np.unique(out[:100, 0]).tolist()), {-0.5, 0.5})
        empty = types.SimpleNamespace(frames=[], start=0)
        short = fake_voice([1.0], False, 0, self.RATE, 1)
        self.assertEqual(float(np.abs(ns.render_voices([empty, short], self.RATE, 1)).max()), 0.0)


class SdatRenderTests(unittest.TestCase):
    def setUp(self):
        self.sd = ns.Sdat(song_sdat())

    def test_bank_regions_and_wave_cache(self):
        bank = ns.Bank(self.sd, 0)
        self.assertEqual(bank.region(0, 60)["swav"], 0)
        self.assertEqual(bank.region(1, 10)["type"], 2)
        self.assertIsNone(bank.region(2, 60))        # 빈 악기
        self.assertIsNone(bank.region(9, 60))
        w = bank.wave(bank.region(0, 60))
        self.assertIs(bank.wave(bank.region(0, 61)), w)
        self.assertEqual(w["rate"], 8000)

    def test_render_sseq(self):
        y, info, events, stop, ntracks, seq, loop = ns.render_sseq(self.sd, 1, 8000, loops=2, fade=0.1,
                                                                    audio_loops=1)
        self.assertEqual((info["name"], info["tracks"], info["loopStartTick"], info["loopEndTick"]),
                         ("SND_BGM_M01_TEST", 2, 0, 9))
        self.assertEqual(stop, 18)
        self.assertEqual(len(y), info["loopEndSample"] + int(0.1 * 8000))
        self.assertAlmostEqual(float(np.abs(y).max()), 10 ** (-1 / 20), 4)
        self.assertEqual(ns.seq_channels(self.sd, 0), 2)
        self.assertEqual(ns.seq_channels(self.sd, None), 16)

    def test_seqarc_entries(self):
        self.assertEqual(ns.seqarc_entries(self.sd, 0), [0, 2])
        self.assertIsNone(ns.render_seqarc_entry(self.sd, 0, 1))
        self.assertIsNone(ns.render_seqarc_entry(self.sd, 0, 5))
        y, info, seq, loop, stop = ns.render_seqarc_entry(self.sd, 0, 2, 8000)
        self.assertEqual((info["index"], info["loop"], info["silent"]), (2, False, False))
        self.assertEqual([e[3] for e in seq.events if e[2] == "note"], [70])
        self.assertGreater(len(y), 1)

    def test_bank_doc(self):
        bank, insts = ns.bank_doc(self.sd, 0, {0, 1, 2, 7})
        self.assertEqual(bank, {"id": 0, "name": "BANK0", "wavearcs": [0]})
        self.assertEqual(insts["0"]["regions"][0]["sample"], "00-00.wav")
        self.assertEqual(insts["1"]["type"], "PSG")
        self.assertIsNone(insts["2"])
        self.assertIsNone(insts["7"])


def write_fs(root, sdat):
    """풀어 둔 롬 폴더 꼴(SOUND·DEBUG·MAP·arm9.bin)."""
    d = Path(root) / "data" / "data"
    (d / "SOUND").mkdir(parents=True)
    (d / "DEBUG").mkdir()
    (d / "MAP").mkdir()
    (d / "SCRIPT").mkdir()
    (Path(root) / ns.SDAT_PATH).write_bytes(sdat)
    (Path(root) / ns.SOUNDLIST).write_text("BGM,1,はじまり\n#BGM,2,おわり\nSE,0,カーソル\nbad line\n", "shift_jis")
    (Path(root) / ns.SADL_PATH).write_text("#define SND_BGM_A 1\n#define X\n// c\n#define SND_SE_B 300\n",
                                           "ascii")
    (d / "DEBUG" / "fieldsymbol.dat").write_text(
        "1,HA(CA)ミナト町＆城\n2,zz\n3,KUモリノ\nnone\n4,AB(XY)村ABあいう\n", "shift_jis")
    names = ["caf1", "dab1"]
    (d / "MAP" / "_list.txt").write_text("".join(f"{i},x,{n}\n" for i, n in enumerate(names)) + "end\n",
                                         "shift_jis")
    a9 = bytearray(0xC0000)
    for i, n in enumerate(names):
        o = ns.MAP_TABLE - 0x02000000 + i * ns.MAP_ENTRY
        a9[o + 6], a9[o + 7] = 5 + i, 9
        a9[o + 8:o + 8 + len(n)] = n.encode()
    o = ns.BATTLE_TABLE - 0x02000000
    struct.pack_into("<H", a9, o + 3 * 0x28, 21)
    struct.pack_into("<H", a9, o + 10 * 0x28, 21)
    (Path(root) / "arm9.bin").write_bytes(bytes(a9))


class Dq4TableTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.fs = self.tmp.name
        write_fs(self.fs, song_sdat())

    def tearDown(self):
        self.tmp.cleanup()

    def test_text_tables(self):
        self.assertEqual(ns.soundlist(self.fs), {("BGM", 1): "はじまり", ("BGM", 2): "おわり", ("SE", 0): "カーソル"})
        self.assertEqual(ns.sadl(self.fs), {"SND_BGM_A": 1, "SND_SE_B": 300})
        names = ns.place_names(self.fs)
        self.assertEqual((names["ha"], names["ca"], names["ku"]), ("ミナト町＆城", "ミナト町＆城",
                                                                   "モリノ"))
        self.assertEqual((names["ab"], names["xy"]), ("村ABあいう", "村ABあいう"))
        self.assertNotIn("zz", names)

    def test_arm9_tables(self):
        self.assertEqual(ns.map_songs(self.fs), [("caf1", 5, 9), ("dab1", 6, 9)])
        self.assertEqual(ns.battle_songs(self.fs), {3: 21, 10: 21})
        a9 = bytearray(Path(self.fs, "arm9.bin").read_bytes())
        a9[ns.MAP_TABLE - 0x02000000 + 8] = ord("z")
        Path(self.fs, "arm9.bin").write_bytes(bytes(a9))
        with self.assertRaises(ValueError):          # 표가 밀리면 엉뚱한 곡을 붙이지 않는다
            ns.map_songs(self.fs)

    def test_export_jobs_and_score_check(self):
        out = Path(self.fs) / "out"
        (out / "songs").mkdir(parents=True)
        (out / "sfx").mkdir()
        info = ns._song_job((self.fs, str(out), 1, "テスト"))
        self.assertEqual((info["kind"], info["wav"], info["sseq"]), ("SSEQ", "01-テスト.wav", "01-テスト.sseq"))
        self.assertEqual((out / "songs" / info["sseq"]).read_bytes(), song_bytes()[0])
        doc = json.loads((out / "songs" / info["score"]).read_text(encoding="utf-8"))
        self.assertEqual(doc["instruments"]["0"]["regions"][0]["sample"], "00-00.wav")
        self.assertIsNone(ns._sfx_job((self.fs, str(out), 1, None)))
        sfx = ns._sfx_job((self.fs, str(out), 2, None))
        self.assertEqual(sfx["sdat"]["seqOffset"], 0x20 + 12 * 3 + 7)    # 자료 시작 + 칸 0 시퀀스(7바이트) 뒤
        with contextlib.redirect_stdout(io.StringIO()) as buf:
            bad = ns.score_check(out)
        self.assertEqual(bad, 0, buf.getvalue())
        self.assertIn("MIDI 바이트 같음", buf.getvalue())

    def test_export_songs_and_stream(self):
        out = Path(self.fs) / "out"
        with contextlib.redirect_stdout(io.StringIO()):
            ns.export(out, self.fs, only=["songs", "sfx"], jobs=1)
        songs = json.loads((out / "songs" / "index.json").read_text(encoding="utf-8"))
        self.assertEqual(sorted(songs), ["01"])      # STRM 은 BGM 1 칸에 든다(실제 롬은 SEQ 1 이 비어 겹치지 않음)
        self.assertEqual((songs["01"]["kind"], songs["01"]["channels"], songs["01"]["title"]), ("STRM", 2, "はじまり"))
        with wave.open(str(out / "songs" / "01-はじまり.wav")) as w:
            self.assertEqual((w.getnchannels(), w.getframerate(), w.getnframes()), (2, 22050, 4))
        sfx = json.loads((out / "sfx" / "index.json").read_text(encoding="utf-8"))
        self.assertEqual(sorted(sfx), ["000", "002"])
        self.assertEqual((sfx["000"]["name"], sfx["002"]["name"], sfx["000"]["title"]),
                         ("SND_SE_M_A", "SND_SE_M_C", "カーソル"))

    def test_export_samples(self):
        out = Path(self.fs) / "out"
        with contextlib.redirect_stdout(io.StringIO()):
            ns.export(out, self.fs, only=["samples"])
        idx = json.loads((out / "samples" / "index.json").read_text(encoding="utf-8"))
        self.assertEqual(idx["wavearcs"]["00"]["waves"]["00"]["loopStart"], 16)
        self.assertEqual(idx["banks"]["00"]["instruments"][1]["type"], "PSG")
        self.assertEqual(len(idx["banks"]["00"]["instruments"]), 2)       # 빈 악기는 뺀다
        with wave.open(str(out / "samples" / "00-00.wav")) as w:
            self.assertEqual(w.getnframes(), 64)

    def test_gallery(self):
        out = Path(self.fs) / "out"
        for sub, doc in (("songs", {"01": {"index": 1, "kind": "STRM", "duration": 1, "format": "PCM16", "rate": 1,
                                           "title": "<a>", "name": None, "wav": "01.wav"},
                                    "02": {"index": 2, "kind": "SSEQ", "duration": 2, "loopStart": 0, "loopEnd": 1,
                                           "midi": "02.mid", "sseq": "02.sseq", "name": "N", "wav": "02.wav"}}),
                         ("sfx", {"000": {"index": 0, "wav": "a.wav", "duration": 1, "loop": True, "bank": 0,
                                          "player": 0}})):
            (out / sub).mkdir(parents=True)
            ns.write_index(out / sub / "index.json", doc)
        scenes = Path(self.fs) / "s.json"
        scenes.write_text(json.dumps({"bgm": {"2": ["필드 <1>"]}, "se": {}}), encoding="utf-8")
        ns.gallery(out, scenes)
        page = (out / "gallery" / "index.html").read_text(encoding="utf-8")
        self.assertIn("&lt;a&gt;", page)
        self.assertIn("필드 &lt;1&gt;", page)
        self.assertIn("곡 (2)", page)
        self.assertEqual(json.loads((out / "songs" / "index.json").read_text())["02"]["scenes"], ["필드 <1>"])

    def test_summarize(self):
        scene = {"maps": [{"entered": True, "table": 5, "bgm": [], "cur": 5, "scene": "hac1", "time": 2},
                          {"entered": True, "table": 5, "bgm": [5], "cur": 0, "scene": "kua1", "time": 4},
                          {"entered": True, "table": 7, "bgm": [8], "cur": 0, "scene": "x", "time": 2},
                          {"entered": False, "table": 7, "bgm": [], "cur": 0, "scene": "y", "time": 2}],
                 "fields": [{"bgm": [11], "scene": "ch1"}, {"bgm": [12], "scene": "s", "leader": 3}, {"bgm": []}],
                 "events": [{"bgm": [13], "pick": 0, "scene": "장 끝", "se": [300]}],
                 "vehicles": [{"bgm": [14], "vehicle": 2}],
                 "battles": [{"bgm": [21], "record": 3, "se": [301]}, {"bgm": [22], "record": 0, "se": []},
                             {"bgm": [23], "scene": "ch2 전투 테스트", "se": []}, {"bgm": []}]}
        f = Path(self.fs) / "scene.json"
        f.write_text(json.dumps(scene))
        bin_ = script([(obj_head(1, 0, 0, 0, 0), [(0, [0x86, 30]), (0, [0x86, 0]), (0, [0x62 | 1 << 16, 302])],
                        [(0, [0x13A, 31, 0, 0]), (0, [0x147])], [])])
        (Path(self.fs) / "data/data/SCRIPT/kua1.bin").write_bytes(bin_)
        self.assertEqual(ns.script_sounds(self.fs), [("kua1", 0x86, 30), ("kua1", 0x86, 0), ("kua1", 0x62, 302),
                                                     ("kua1", 0x13A, 31)])   # 인자 없는 명령은 뺀다
        r = ns.summarize([f], self.fs)
        self.assertEqual(r["bgm"]["30"], ["이벤트(곡) モリノ"])
        self.assertEqual(r["bgm"]["31"], ["이벤트(ME) モリノ"])
        self.assertEqual(r["se"]["302"], ["이벤트 モリノ"])
        self.assertNotIn("0", r["bgm"])             # 곡 0(멈춤)은 장면으로 치지 않는다
        self.assertEqual(r["maps"], {"agree": 2, "disagree": 1})
        self.assertEqual(r["bgm"]["5"], ["맵: ミナト町＆城 (1맵)", "맵 밤: モリノ (1맵)"])
        self.assertEqual(r["bgm"]["12"], [f"필드 6장 선두 {ns.CHARACTERS[3]}"])
        self.assertEqual(r["bgm"]["14"], ["필드 배"])
        self.assertEqual(r["bgm"]["21"], ["고정 전투(조우 레코드 3·10)"])
        self.assertEqual(r["bgm"]["22"], ["보통 전투(던전 조우)"])
        self.assertEqual(r["bgm"]["23"], ["2장 전투 테스트"])
        self.assertEqual(r["measured_se"], [300, 301])
        self.assertEqual(r["measured_bgm"], [5, 11, 12, 13, 14, 21, 22, 23])


class HookTests(unittest.TestCase):
    @staticmethod
    def b_target(at, word):
        off = word & 0xFFFFFF
        return at + 8 + ((off - (1 << 24)) if off & 0x800000 else off) * 4

    def test_branches_and_literals_resolve(self):
        code, patch = ns.hook_code()
        words = struct.unpack(f"<{len(code) // 4}I", code)

        def at(i):
            return ns.HOOK_BASE + 4 * i
        self.assertEqual(self.b_target(ns.START_SEQ, patch[ns.START_SEQ]), ns.HOOK_BASE)
        self.assertEqual(self.b_target(ns.START_SEQARC, patch[ns.START_SEQARC]), ns.HOOK_BASE + 12)
        self.assertEqual(patch[ns.START_SEQ] >> 24, 0xEA)
        common = 6
        self.assertEqual(self.b_target(at(2), words[2]), at(common))
        self.assertEqual(self.b_target(at(5), words[5]), at(common))
        loads = {}
        for i, w in enumerate(words[:-3]):
            if w & 0xFFFF0000 in (0xE59F0000, 0xE59F3000, 0xE59FF000):
                lit = at(i) + 8 + (w & 0xFFF)
                loads[(w >> 12) & 15] = loads.get((w >> 12) & 15, []) + [words[(lit - ns.HOOK_BASE) // 4]]
        self.assertEqual(loads[3], [ns.HOOK_LOG])
        self.assertEqual(loads[15], [ns.START_SEQARC + 4, ns.START_SEQ + 4])
        beq = [i for i, w in enumerate(words) if w >> 24 == 0x0A]
        self.assertEqual(len(beq), 1)
        self.assertEqual(words[(self.b_target(at(beq[0]), words[beq[0]]) - ns.HOOK_BASE) // 4], 0xE92D4038)


class FakePlayer:
    def __init__(self):
        self.mem = {}
        self.frame = 0
        self.ran = 0

    def write(self, a, data):
        for k, b in enumerate(data):
            self.mem[a + k] = b

    def read(self, a, n):
        return bytes(self.mem.get(a + k, 0) for k in range(n))

    def w32(self, a, v):
        self.write(a, struct.pack("<I", v & 0xFFFFFFFF))

    def u32(self, a):
        return struct.unpack("<I", self.read(a, 4))[0]

    def run(self, n=1):
        self.frame += n
        self.ran += n


class RecorderTests(unittest.TestCase):
    def test_install_and_poll(self):
        p = FakePlayer()
        rec = ns.Recorder(p)
        rec.install(override=7)
        code, patch = ns.hook_code()
        self.assertEqual(p.read(ns.HOOK_BASE, len(code)), code)
        self.assertEqual(p.u32(ns.HOOK_LOG - 4), 7)
        for a, v in patch.items():
            self.assertEqual(p.u32(a), v)

        def log(i, kind, a1, a2, lr, lr2):
            p.write(ns.HOOK_LOG + 32 + 32 * (i & 0xFF), struct.pack("<6I", kind, 0, a1, a2, lr, lr2))
            p.w32(ns.HOOK_LOG, i + 1)
        log(0, 1, 5, 0, 0x100, 0)
        log(1, 2, 0, 300, 0, 0x200)
        p.run(1)                                     # Recorder 가 run 을 감싸 프레임마다 모은다
        self.assertEqual(rec.bgm(), [5])
        self.assertEqual(rec.se(), [300])
        self.assertEqual(rec.log[1], (1, "se", 300, 0x200))
        for i in range(2, 258):
            log(i, 1, i, 0, 0, 0)
            p.run(1)
        self.assertEqual(rec.bgm()[-1], 257)        # 기록은 256 칸을 돌아 쓴다
        self.assertEqual(p.ran, 257)


class BootSongTests(unittest.TestCase):
    def test_boot_patches_and_waits_for_song(self):
        p = FakePlayer()
        for addr, old, _new in ns.BOOT_TO_SONG:
            p.write(addr, old)
        p.w32(ns.SONG_ARG, ns.SONG_ARG_ORIG)
        run = p.run

        def game(n=1):
            run(n)
            if p.frame == 5:
                p.w32(ns.SOUND_MGR + 4, 9)
        p.run = game
        self.assertEqual(ns.boot_song(p, 9), 5)
        self.assertEqual(p.read(ns.SONG_ARG, 4), ns.song_word(9))
        for addr, _old, new in ns.BOOT_TO_SONG:
            self.assertEqual(p.read(addr, len(new)), new)
        q = FakePlayer()
        for addr, old, _new in ns.BOOT_TO_SONG:
            q.write(addr, old)
        q.w32(ns.SONG_ARG, ns.SONG_ARG_ORIG)
        self.assertIsNone(ns.boot_song(q, 9, maxf=3))
        with self.assertRaises(AssertionError):     # 이미 고친 RAM 에 다시 걸지 않는다
            ns.boot_song(q, 9, maxf=1)

    def test_audio_tap_collects_stereo_batches(self):
        import ctypes as C
        core = types.SimpleNamespace(cb=None)
        core.retro_set_audio_sample_batch = lambda cb: setattr(core, "cb", cb)
        tap = ns.AudioTap(types.SimpleNamespace(core=core))
        buf = C.create_string_buffer(struct.pack("<4h", 16384, -16384, 0, 32767))
        self.assertEqual(core.cb(C.cast(buf, C.c_void_p), 2), 2)
        self.assertEqual(core.cb(None, 3), 3)
        y = tap.take()
        self.assertEqual(y.shape, (2, 2))
        self.assertEqual(y[0].tolist(), [0.5, -0.5])
        self.assertEqual(tap.take().shape, (0, 2))   # take 는 비운다


class SpectrumTests(unittest.TestCase):
    def test_match_finds_offset(self):
        rate = 8000
        t = np.arange(rate * 4) / rate
        freq = 220 * 2 ** (np.floor(t * 4) % 12 / 12)
        ref = np.sin(2 * np.pi * np.cumsum(freq) / rate).astype(np.float32)
        rec = ref[rate:rate * 2]
        score, at = ns.spectrum_match(rec, rate, ref, rate)
        self.assertAlmostEqual(at, 1.0, delta=0.05)
        self.assertGreater(score, 0.5)
        self.assertEqual(ns.spectrum_match(np.zeros(10), rate, ref, rate), (0.0, 0.0))
        spec, power = ns.band_spectrum(np.stack([ref, ref], 1), rate)
        self.assertEqual(spec.shape[1], 72)
        self.assertEqual(len(power), len(spec))


def nds_rom(files, overlays=1):
    """FNT·FAT·오버레이 표가 있는 작은 NDS 롬. files: {경로: 바이트}."""
    tree = {}
    for path in files:
        node = tree
        parts = path.split("/")
        for p in parts[:-1]:
            node = node.setdefault(p, {})
        node[parts[-1]] = path
    dirs, order = [], []

    def collect(node):
        did = 0xF000 + len(dirs)
        dirs.append([node, did, None])
        for name in sorted(node):
            if isinstance(node[name], dict):
                collect(node[name])
        return did
    collect(tree)
    first = overlays
    entries = []
    fid = first
    subtables = []
    for node, did, _ in dirs:
        st = bytearray()
        start_fid = fid
        for name in sorted(node):
            if isinstance(node[name], dict):
                child = [x for x in dirs if x[0] is node[name]][0][1]
                st += bytes([0x80 | len(name)]) + name.encode() + struct.pack("<H", child)
        for name in sorted(node):
            if not isinstance(node[name], dict):
                st += bytes([len(name)]) + name.encode()
                entries.append(node[name])
                fid += 1
        # walk 는 파일 칸을 이름 순서대로 세므로 디렉터리 이름을 앞에 둔 순서를 그대로 쓴다
        subtables.append((start_fid, bytes(st) + b"\0"))
    # walk 는 같은 순서로 번호를 붙이도록, 디렉터리와 파일이 섞이면 이름 순서 그대로 둔다(테스트는 섞지 않음)
    fnt = bytearray(8 * len(dirs))
    for k, (start_fid, st) in enumerate(subtables):
        struct.pack_into("<IH", fnt, 8 * k, len(fnt), start_fid)
        fnt += st
    rom = bytearray(0x90000)
    ovt_at, fnt_at = 0x200, 0x1000
    fat_at = fnt_at + len(fnt) + 16
    data_at = 0x70000
    rom[fnt_at:fnt_at + len(fnt)] = fnt
    ranges = [(data_at, data_at + 4)] * overlays
    pos = data_at + 0x100
    for path in entries:
        ranges.append((pos, pos + len(files[path])))
        rom[pos:pos + len(files[path])] = files[path]
        pos += len(files[path]) + 4
    for i, (a, b) in enumerate(ranges):
        struct.pack_into("<II", rom, fat_at + 8 * i, a, b)
    for i in range(overlays):
        struct.pack_into("<I", rom, ovt_at + 32 * i + 24, i)
    struct.pack_into("<IIII", rom, 0x40, fnt_at, len(fnt), fat_at, 8 * len(ranges))
    struct.pack_into("<II", rom, 0x50, ovt_at, 32 * overlays)
    return rom, {p: r for p, r in zip(entries, ranges[overlays:])}


def lib_rom():
    """2sflib 을 만들 수 있는 롬: LIB_FILES 와 쓰이지 않는 파일 하나, 부팅 고침 자리의 원래 바이트."""
    files = {"data/" + f: bytes([0x5A]) * 8 for f in ns.LIB_FILES}
    files["data/OTHER.bin"] = b"\x77" * 8
    rom, ranges = nds_rom(files)
    struct.pack_into("<IIII", rom, 0x20, 0x4000, 0, 0x02000000, 0x60000)
    struct.pack_into("<I", rom, 0x30, 0x3F000)
    struct.pack_into("<I", rom, 0x3C, 0x10)
    for addr, old, _new in ns.BOOT_TO_SONG + [ns.NO_BACKUP_CHECK]:
        o = ns.rom_offset(addr)
        rom[o:o + len(old)] = old
    o = ns.rom_offset(ns.SONG_ARG)
    rom[o:o + 4] = struct.pack("<I", ns.SONG_ARG_ORIG)
    rom[0x3000:0x3004] = b"JUNK"                    # 남길 구간 밖
    return rom, ranges


class RomTests(unittest.TestCase):
    def test_rom_files_walks_subdirectories(self):
        files = {"data/a/x.bin": b"AAAA", "data/a/y.bin": b"BB", "data/z.dat": b"C", "top.txt": b"DDD"}
        rom, want = nds_rom(files)
        got, overlays = ns.rom_files(rom)
        self.assertEqual(got, want)
        for path, (a, b) in got.items():
            self.assertEqual(bytes(rom[a:b]), files[path])
        self.assertEqual(len(overlays), 1)

    def test_song_lib_patches_and_trims(self):
        rom, ranges = lib_rom()
        lib = ns.song_lib(bytes(rom))
        for addr, _old, new in ns.BOOT_TO_SONG + [ns.NO_BACKUP_CHECK]:
            self.assertEqual(lib[ns.rom_offset(addr):ns.rom_offset(addr) + len(new)], new)
        self.assertEqual(lib[ns.rom_offset(ns.SONG_ARG):][:4], ns.song_word(2))
        self.assertEqual(lib[0x3000:0x3004], bytes(4))
        a, b = ranges["data/OTHER.bin"]
        self.assertEqual(lib[a:b], bytes(b - a))   # 2SF 에 쓰이지 않는 파일은 지운다
        a, b = ranges["data/SOUND/sound_data.sdat"]
        self.assertEqual(lib[a:b], b"\x5A" * 8)
        bad = bytearray(rom)
        bad[ns.rom_offset(ns.SONG_ARG)] ^= 1
        with self.assertRaises(AssertionError):
            ns.song_lib(bytes(bad))

    def test_mini2sf_overwrites_only_song_word(self):
        rom, _ = lib_rom()
        with tempfile.TemporaryDirectory() as d:
            write_fs(d, song_sdat())
            Path(d, "dq4ds.nds").write_bytes(bytes(rom))
            rows = ns.mini2sf(Path(d) / "out", d, rom=Path(d, "dq4ds.nds"), songs=[1])
            raw = (Path(d) / "out" / rows[0]["file"]).read_bytes()
            idx = json.loads((Path(d) / "out" / "index.json").read_text(encoding="utf-8"))
        self.assertEqual(rows[0]["title"], "はじまり")
        self.assertTrue(rows[0]["loop"])
        size = struct.unpack_from("<I", raw, 8)[0]
        prog = zlib.decompress(raw[16:16 + size])
        self.assertEqual(prog, struct.pack("<II", ns.rom_offset(ns.SONG_ARG), 4) + ns.song_word(1))
        self.assertIn(b"_lib=dq4ds.2sflib", raw)
        self.assertEqual(idx["lib"], "dq4ds.2sflib")

    def test_psf_container(self):
        raw = ns.psf(b"program", {"title": "곡", "_lib": "x.2sflib"})
        self.assertEqual(raw[:4], b"PSF\x24")
        _res, size, crc = struct.unpack_from("<III", raw, 4)
        z = raw[16:16 + size]
        self.assertEqual(zlib.crc32(z), crc)
        self.assertEqual(zlib.decompress(z), b"program")
        self.assertEqual(raw[16 + size:], "[TAG]title=곡\n_lib=x.2sflib\n".encode())


class CliTests(unittest.TestCase):
    def test_info_and_maps(self):
        with tempfile.TemporaryDirectory() as fs:
            write_fs(fs, song_sdat())
            with contextlib.redirect_stdout(io.StringIO()) as buf:
                ns.main(["info", "--fs", fs])
                ns.main(["maps", "--fs", fs])
            self.assertIn("[strm] 칸 1, 레코드 1", buf.getvalue())
            self.assertIn("caf1", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
