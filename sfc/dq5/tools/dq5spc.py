"""DQ5(SFC) 사운드 드라이버 자료. 형식은 sfc/dq5/docs/dq5-sound-format.md.

롬에는 [길이 2바이트][자료] 가 이어 붙은 묶음이 둘 있다. 샘플 0x26개(2B:EB00~)와 시퀀스 0x47개(2E:E2E4~)이고,
뱅크를 넘어도 LoROM 파일 오프셋으로는 이어진다. 곡 n 을 틀면(명령 01·03·0C) 2B 뱅크가 시퀀스 n 과 곡 묶음
2B:E67F 의 n 번째 레코드에 적힌 샘플을 SPC 로 보낸다(이미 SPC 에 있으면 참조 수만 올림).

사용:
  python sfc/dq5/tools/dq5spc.py rom/dq5.sfc                 # 샘플·시퀀스·곡 묶음 표
  python sfc/dq5/tools/dq5spc.py rom/dq5.sfc --check spc.bin
      # dq5sndlog.lua 의 SPCDUMP 덤프(커밋 금지)에 올라 있는 샘플·시퀀스가 롬 자료와 같은지
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from dq5map import Rom, lorom  # noqa: E402

SAMPLES, SAMPLE_COUNT = 0x2BEB00, 0x26  # 2B:C391
SEQUENCES, SEQUENCE_COUNT = 0x2EE2E4, 0x47  # 2B:C39E
SONG_SETS = 0x2BE67F  # 2B:C3CB. [샘플 수 L][한 바이트][샘플 번호 L개]
RESIDENT_SAMPLES = 0x2BC422  # 명령 8B 가 0B 로 보내는 목록(FF 끝)
RESIDENT_SEQUENCES = 0x2BC429  # 명령 93 이 13 으로 보내는 목록(FF 끝)
HANDLERS = 0x2BC43B  # 대기열 명령 & 3F 의 처리 루틴(2B 뱅크 16비트)

# SPC RAM. 드라이버는 직접 페이지 1 을 쓴다($8A = $018A).
SPC_SAMPLE_SLOTS = 0x0535  # 8바이트 x 0x14: [BRR 길이 2][ADSR1][ADSR2][GAIN][음높이 2][플래그]
SPC_SEQUENCE_SLOTS = 0x05D5  # 6바이트 x 0x14: [FF][주소 2][길이 2][플래그]
SPC_SAMPLE_INDEX = 0x03FF  # 샘플 번호 -> 칸(FF 면 없음)
SPC_SEQUENCE_INDEX = 0x04C7  # 시퀀스 번호 -> 칸
SPC_DIR = 0x0700  # DSP DIR = 07. 칸마다 [시작 2][반복 2]


def chain(rom, start, count):
    """[(번호, 주소, 길이)]. 주소는 길이 2바이트 앞, 자료는 그 뒤."""
    out, o = [], lorom(start)
    for i in range(count):
        n = rom.d[o] | rom.d[o + 1] << 8
        out.append((i, _cpu(o), n))
        o += n + 2
    return out


def _cpu(o):
    return (o // 0x8000) << 16 | 0x8000 | (o % 0x8000)


def body(rom, addr, n):
    o = lorom(addr) + 2
    return rom.d[o:o + n]


def samples(rom):
    return chain(rom, SAMPLES, SAMPLE_COUNT)


def sequences(rom):
    return chain(rom, SEQUENCES, SEQUENCE_COUNT)


def song_sets(rom, count=SEQUENCE_COUNT):
    """[(곡 번호, 둘째 바이트, [샘플 번호])]."""
    out, a = [], SONG_SETS
    for i in range(count):
        n = rom.u8(a)
        out.append((i, rom.u8(a + 1), [rom.u8(a + 2 + k) for k in range(n)]))
        a += n + 2
    return out


def ff_list(rom, a):
    out = []
    while rom.u8(a) != 0xFF:
        out.append(rom.u8(a))
        a += 1
    return out


def check(rom, spc):
    """SPC RAM 의 칸 표에 올라 있는 샘플·시퀀스를 롬과 견준다. [(종류, 번호, 칸, 맞음)]."""
    out = []
    seqs = sequences(rom)
    for sid in range(0x100):
        slot = spc[SPC_SEQUENCE_INDEX + sid]
        if slot == 0xFF or sid >= SEQUENCE_COUNT:
            continue
        e = spc[SPC_SEQUENCE_SLOTS + slot * 6:SPC_SEQUENCE_SLOTS + slot * 6 + 6]
        addr, n = e[1] | e[2] << 8, e[3] | e[4] << 8
        _, a, ln = seqs[sid]
        out.append(("seq", sid, slot, n == ln and spc[addr:addr + n] == body(rom, a, ln)))
    smps = samples(rom)
    for sid in range(SAMPLE_COUNT):
        slot = spc[SPC_SAMPLE_INDEX + sid]
        if slot == 0xFF:
            continue
        e = spc[SPC_SAMPLE_SLOTS + slot * 8:SPC_SAMPLE_SLOTS + slot * 8 + 8]
        start = spc[SPC_DIR + slot * 4] | spc[SPC_DIR + slot * 4 + 1] << 8
        loop = spc[SPC_DIR + slot * 4 + 2] | spc[SPC_DIR + slot * 4 + 3] << 8
        _, a, ln = smps[sid]
        b = body(rom, a, ln)
        brr = e[0] | e[1] << 8
        ok = (brr == ln - 7 and bytes(e[2:7]) == b[2:7] and loop - start == (b[0] | b[1] << 8)
              and spc[start:start + brr] == b[7:])
        out.append(("sample", sid, slot, ok))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("rom")
    ap.add_argument("--check", metavar="SPC", help="SPC RAM 덤프 64KB")
    args = ap.parse_args()
    rom = Rom(open(args.rom, "rb").read())
    if args.check:
        res = check(rom, open(args.check, "rb").read())
        for kind, sid, slot, ok in res:
            print(f"{kind:6} {sid:02X} slot {slot:02X} {'ok' if ok else 'DIFF'}")
        bad = sum(not r[3] for r in res)
        print(f"{len(res)} loaded, {bad} differ")
        sys.exit(1 if bad else 0)
    print("samples (2B:EB00): [loop offset 2][ADSR1][ADSR2][GAIN][pitch 2][BRR]")
    for i, a, n in samples(rom):
        b = body(rom, a, n)
        print(f"  {i:02X} {a:06X} len {n:04X} loop {b[0] | b[1] << 8:04X} adsr {b[2]:02X} {b[3]:02X} gain {b[4]:02X}"
              f" pitch {b[5]:02X}{b[6]:02X}")
    print("sequences (2E:E2E4)  set: [second byte] samples")
    sets = song_sets(rom)
    for (i, a, n), (_, x, smp) in zip(sequences(rom), sets):
        print(f"  {i:02X} {a:06X} len {n:04X}  set {x:02X} [{' '.join(f'{s:02X}' for s in smp)}]")
    print("resident samples (8B):", " ".join(f"{s:02X}" for s in ff_list(rom, RESIDENT_SAMPLES)))
    print("resident sequences (93):", " ".join(f"{s:02X}" for s in ff_list(rom, RESIDENT_SEQUENCES)))


if __name__ == "__main__":
    main()
