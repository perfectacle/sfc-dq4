"""NDS 편곡 시퀀스를 DQ5 곡 자리에 넣고 선택한 맵 전환에 페이드를 건다.

기존 서곡의 70 뱅크 재배치 표를 보존한다. 명령·곡 묶음 형식은
sfc/dq5/docs/dq5-sound-format.md, 기존 타이틀 훅은 dq4-overture-format.md 참조.
생성 롬과 IPS는 로컬 work/에만 둔다.
"""
import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(HERE), str(ROOT / 'sfc/dq5/tools')]
from dq4romassets import set_checksum  # noqa: E402
from dq5map import Rom, lorom  # noqa: E402
from dq5song import (RELOC_CODE, RELOC_SEQ_TABLE, RELOC_SMP_TABLE,  # noqa: E402
                    _asm, header, reloc_code, step)
from dq5spc import (SONG_SETS, SEQUENCE_COUNT, RESIDENT_SAMPLES,  # noqa: E402
                   RESIDENT_SEQUENCES, samples, sequences)

IPL_BLOCK = 0x2BE676
IPL_END = bytes.fromhex('00 00 00 02')
TABLE_CAPACITY = 0x2A5D - 0x28EC
HEAP_START = 0x2BE67A  # IPL 블록 첫 2바이트 = SPC $28E7, 드라이버 22F4 가 읽는 샘플·시퀀스 자리 시작
SPC_END = 0xD700
CODE = 0x718000
# 70 은 재배치 표, 71 은 훅 코드, 65~69 는 DQ4 메뉴 메시지. 곡 50개의 시퀀스·샘플은 약 0.5MB 라 72~7D 만으로는 모자란다.
DATA_BANKS = (*range(0x6A, 0x70), *range(0x72, 0x7E))
MAP_CLEANUP, MAP_START = 0x00CEB1, 0x00CEA2
FADE_OUT, FADE_IN = 0x40, 0x30
SPC_CAPACITY = SPC_END - 0x2A5D
# 2B:BFDF 의 LDA $2BC422,X 가 늘 두는 샘플 목록(명령 8B, 켤 때 한 번)을 읽는다. 목록은 7바이트라 늘리려면 옮긴다.
RESIDENT_SAMPLE_LOAD = 0x2BBFDF
RESIDENT_SAMPLE_LIST = CODE + 0x200
SAMPLE_SLOTS = 0x14
# 드라이버 코드 IPL 블록(SPC 0750~28E6). 1046 은 자료 받기 상태(80)의 처리, 곡 묶음 표 블록 뒤에 붙이는 빠른 받기 코드는
# 메아리 버퍼(D700~FEFF) 뒤 FF00 에 올린다. 샘플 자리가 아니라 자리 정리(0A)에 덮이지 않는다.
DRIVER_BLOCK = 0x2BC4DB
DRIVER_RECEIVE = 0x1046
FAST_RECEIVE = 0xFF00
FAST_RECEIVE_TRIPLETS = 4
FAST_RECEIVE_POLLS = 32
# 나눈 곡(앞부분 → 본체): 드라이버 명령 F7(표 07CD, 원래 아무것도 안 함)을 CHAIN 처리기로, 본체는 시퀀스 번호 47~,
# 짝 표 71:8300(곡 → 본체, 00 없음), 2B:C1C1(곡이 시작한 뒤 곡 뒤 샘플 보내기 JSR C1DB)을 발판 2B:B780 으로.
CHAIN_HANDLER = 0xFF54
CHAIN_TABLE_ENTRY = 0x07CD
# 새 곡 번호: 47~4B 는 바꿔 넣는 곡(시나리오가 부를 고정 번호), 4C~ 은 나눈 곡의 본체. SPC 색인 표(04C7)는 0x64칸이고,
# 그 뒤 052B~ 는 드라이버가 계산한 주소로 쓰여 색인을 늘리면 샘플 칸이 깨졌다(보스 곡까지 나눈 빌드의 미리듣기).
# 드라이버와 2B 는 「32 이상은 효과음」으로 보므로 47 이상을 곡으로 보는 범위 검사로 바꾼다(song_range_code).
NEW_SONG_FIRST, NEW_SONG_LAST = SEQUENCE_COUNT, 0x4B
FIRST_CHAIN_SONG = 0x4C
SONG_LIMIT = 0x64
RECORD_COUNT = CODE + 0x3F0         # 곡 묶음 레코드 수(47 넘게 늘렸을 때만, 0 이면 원래 47개)
# SPC 의 곡/효과음 판정(CMP A,$28EB, 문턱 32) 자리. 뒤는 모두 C 만 본다(1C5F 는 POP A / RET 로 C 를 돌려줌)
SPC_EFFECT_COMPARES = (0x0AE8, 0x0B52, 0x0C45, 0x11D6, 0x130F, 0x1683, 0x1A2D, 0x1C5F)
SPC_EFFECT_HELPER = bytes.fromhex('68 47 B0 03 68 32 6F 60 6F')  # C=1 ⇔ 32 <= A < 47
# 2B 의 「지금 곡」($1D8B) 판정: BF5A(8비트, 곡이면 저장)·BFB4(16비트, C 판정). 도우미는 NMI 선점 범위(B741~B804) 안
SONG_STORE_HELPER = 0x2BB770
SONG_TEST_HELPER = 0x2BB7F8
CHAIN_PAIRS = CODE + 0x300
CHAIN_STEP = 0x2BB780
# 본체를 곡 뒤 샘플 다음에 보낼 곡(순서 표 71:8380 = 1)은 샘플 보내기 고리 끝(2B:C20C, PLA·PLX·RTS)의 발판 2B:B7A0 에서
CHAIN_ORDER = CODE + 0x380
CHAIN_LATE_STEP = 0x2BB7A0
# 곡 붙들기(F7 FE 샘플 / F7 FF X): 그 샘플을 X x 256 바이트 받을 때까지 곡의 연주기를 템포 0 처럼 건너뛰고, 받는 중인
# 그 샘플을 instrument(182E)가 있는 것으로 본다. 변수 FF4F~FF53, 연주기 판정 FFC0~(IPL ROM 이 꺼져 있어 RAM),
# instrument 판정·받기 끝 정리는 빠른 받기로 쓰지 않게 된 1049~106A 에 둔다.
HOLD_VARS = 0xFF4F
HOLD_PLAYER, HOLD_SAMPLE, HOLD_BYTES, HOLD_TICKS, HOLD_PARTIAL = range(HOLD_VARS, HOLD_VARS + 5)
HOLD_CHECK = 0xFFC0
HOLD_SPARE = 0x1049
HOLD_TICK_SITE = 0x146C
HOLD_INSTRUMENT_SITE = 0x1861
HOLD_END_SITE = 0x103A


@dataclass(frozen=True)
class Replacement:
    sequence: bytes
    samples: tuple[int, ...]
    send_first: int | None = None  # 곡을 틀기 전에 보낼 앞쪽 샘플 수 k. None 이면 모두


def read_sets(data):
    pos, records = lorom(SONG_SETS), []
    at = lorom(RECORD_COUNT)
    count = data[at] if at < len(data) else 0  # 2MB 롬에는 그 뱅크가 없다
    if count:
        # 표 뒤에는 SPC 판정 도우미와 FF00~ 블록이 붙는다
        for _ in range(count):
            size = data[pos] + 2
            records.append(bytes(data[pos:pos + size]))
            pos += size
        return records
    for _ in range(SEQUENCE_COUNT):
        size = data[pos] + 2
        records.append(bytes(data[pos:pos + size]))
        pos += size
    # 나눈 곡의 본체 레코드(47~)가 뒤에 이어질 수 있다. 그 뒤 SPC FF00~ 으로 올라가는 블록(빠른 받기·CHAIN)은 건너뛴다.
    while data[pos:pos + 4] != IPL_END and data[pos + 3] != 0xFF:
        size = data[pos] + 2
        records.append(bytes(data[pos:pos + size]))
        pos += size
    while data[pos:pos + 4] != IPL_END and data[pos + 3] == 0xFF:
        pos += 4 + int.from_bytes(data[pos:pos + 2], 'little')
    if data[pos:pos + 4] != IPL_END:
        raise ValueError('song set table has no IPL end marker')
    return records


def sequence_bytes(data, song):
    ptr = int.from_bytes(data[lorom(RELOC_SEQ_TABLE) + song * 3:lorom(RELOC_SEQ_TABLE) + song * 3 + 3], 'little')
    if ptr:
        pos = lorom(ptr)
        size = int.from_bytes(data[pos:pos + 2], 'little')
        return bytes(data[pos + 2:pos + size + 2])
    _, addr, size = sequences(Rom(data))[song]
    return bytes(data[lorom(addr) + 2:lorom(addr) + size + 2])


def validate_replacement(item):
    seq = item.sequence
    if len(seq) < 4 or not 1 <= seq[1] <= 7:
        raise ValueError('BGM needs 1..7 voices, leaving a voice for effects')
    _, offsets = header(seq)
    if len(set(item.samples)) != len(item.samples) or any(not 0 <= x < 0xC8 for x in item.samples):
        raise ValueError('sample IDs must be distinct DQ5 sample-table indices')
    if item.send_first is not None and not 0 <= item.send_first <= len(item.samples):
        raise ValueError('send_first must be between 0 and the sample count')
    pending, seen = list(offsets), set()
    while pending:
        pc = pending.pop()
        while pc not in seen:
            if not 2 + 2 * seq[1] <= pc < len(seq):
                raise ValueError('sequence target outside track data')
            seen.add(pc)
            try:
                nxt, _, target, flow = step(seq, pc)
            except (IndexError, KeyError) as exc:
                raise ValueError('invalid sequence command') from exc
            if nxt > len(seq):
                raise ValueError('truncated sequence command')
            if seq[pc] == 0xF0 and seq[pc + 1] >= len(item.samples):
                raise ValueError('instrument index outside song sample set')
            if target is not None:
                pending.append(target)
            if flow in ('end', 'ret', 'jump'):
                break
            pc = nxt


def sample_size(data, sample):
    pos = lorom(RELOC_SMP_TABLE) + sample * 3
    ptr = int.from_bytes(data[pos:pos + 3], 'little')
    if ptr:
        pos = lorom(ptr)
        return int.from_bytes(data[pos:pos + 2], 'little')
    if sample >= 0x26:
        raise ValueError(f'sample {sample:02X}: no resource supplied')
    return samples(Rom(data))[sample][2]


def heap_start(data):
    return int.from_bytes(data[lorom(HEAP_START):lorom(HEAP_START) + 2], 'little')


def resident_samples(data):
    """명령 8B 가 고정하는 샘플 목록. install 이 목록을 옮겼으면 옮긴 자리를 읽는다."""
    pos = lorom(RESIDENT_SAMPLE_LOAD)
    if data[pos] != 0xBF:
        raise ValueError('unexpected resident sample list load at 2B:BFDF')
    start = lorom(int.from_bytes(data[pos + 1:pos + 4], 'little'))
    return list(data[start:data.index(0xFF, start)])


def sample_budget(data, song, sequence_size, extra_table=0, resident=None, pinned=None):
    """곡 하나가 새 샘플에 쓸 수 있는 SPC 바이트. 늘 두는 샘플·시퀀스와 이 곡 시퀀스, 여유 512를 뺀다.

    extra_table 은 곡 묶음 표가 지금보다 늘어날 바이트로, 그만큼 샘플 자리 시작이 뒤로 밀린다.
    resident·pinned 는 넣은 뒤의 {늘 둘 샘플: 바이트}·{늘 둘 시퀀스: 바이트}. 주지 않으면 data 의 목록과 크기.
    """
    if resident is None:
        resident = {i: sample_size(data, i) for i in resident_samples(data)}
    if pinned is None:
        pinned = {i: len(sequence_bytes(data, i)) for i in pinned_sequences(data)}
    resident_bytes = sum(resident.values())
    resident_sequences = sum(size for i, size in pinned.items() if i != song)
    capacity = SPC_END - max(heap_start(data), 0x28EC + sum(map(len, read_sets(data))) + extra_table)
    return capacity - resident_bytes - resident_sequences - sequence_size - 512


def memory_budget(data, song, item, extra_sequences=()):
    resident = set(resident_samples(data))
    resident_sequences = set(pinned_sequences(data))
    used_samples = resident | set(item.samples)
    used_sequences = resident_sequences | {song} | set(extra_sequences)
    sample_bytes = sum(sample_size(data, i) for i in used_samples)
    sequence_size = sum(len(sequence_bytes(data, i)) for i in used_sequences)
    # 슬롯 관리·정렬과 잔향 버퍼 사이에 여유를 둔다. 전환은 이전 곡 자료를 정리한 뒤 로드한다.
    required = sample_bytes + sequence_size + 512
    capacity = SPC_END - heap_start(data)
    if len(used_samples) > SAMPLE_SLOTS or len(used_sequences) > 20 or required > capacity:
        raise ValueError(f'song {song:02X}: SPC budget exceeded ({required}/{capacity} bytes)')
    free = capacity - required + 512
    # 늘 두지 않는 효과음(3E~45 등)은 부를 때 시퀀스와 샘플을 올린다. 곡이 남긴 자리보다 크면 시퀀스 칸만 잡히고
    # 샘플이 오지 않아 소리가 나지 않는다(필드 곡 02 에서 0C 42 실측). 원래 DQ5 곡 자리에서는 울렸다.
    no_room = {}
    for effect in range(0x32, SEQUENCE_COUNT):
        if effect in resident_sequences:
            continue
        record = read_sets(data)[effect]
        need = len(sequence_bytes(data, effect)) + sum(sample_size(data, i) for i in set(record[2:]) - used_samples)
        if need > free:
            no_room[f'{effect:02X}'] = need
    return {'bytes_with_margin': required, 'capacity': capacity,
            'sample_slots': len(used_samples), 'sequence_slots': len(used_sequences),
            'streamed_while_playing': sorted(f'{x:02X}' for x in set(item.samples) - resident)
            if song in resident_sequences else [],
            'free_while_playing': free, 'effects_without_room': no_room}


def transition_code():
    """맵 곡이 바뀔 때 앞 곡은 검은 화면 동안 줄이고 새 곡은 키운다. 프레임을 기다리지 않는다.

    00:CEB1·CEA2 는 맵을 불러오는 중이라 NMI 가 꺼져 있다($4200 = 01). 프레임 기다림(00:969A)은
    NMI 가 $19 를 지워 줘야 끝나므로 여기서 부르면 멈춘다. 대기열을 처리하는 소리 일(2B:BECE)도
    프레임 기다림에서만 돌아 불러오기가 끝날 때까지 대기열이 그대로 남는다.
    그래서 앞 곡 줄이기(SPC 명령 04)는 2B:C169 와 같은 손잡기($08DC·$08DA, APU 포트만 폴링)로 직접 보낸다.
    소리 일이 명령을 보내는 도중일 수 있으니 대기열이 비었을 때만 보낸다(24:FE44 와 같은 판정).
    """
    h = bytes.fromhex
    speed_out, speed_in = bytes([FADE_OUT]), FADE_IN.to_bytes(2, 'little')
    cleanup = _asm([
        h('08 C2 30 48 DA 5A E2 30'),
        h('AF 93 1D 00 AA'),
        ('label', 'scan'), h('8A CF 91 1D 00'), ('b', 0xF0, 'idle'),
        h('BF 95 1D 00 C9 FF'), ('b', 0xF0, 'next'),
        h('29 40'), ('b', 0xF0, 'skip'),
        ('label', 'next'), h('E8 8A 29 0F AA'), ('b', 0x80, 'scan'),
        ('label', 'idle'), h('AF 8B 1D 00 C9 FF'), ('b', 0xF0, 'skip'),
        ('label', 'ready'), h('AF 40 21 00 CF 40 21 00'), ('b', 0xD0, 'ready'),
        h('4F DC 08 00'), ('b', 0x30, 'ready'),
        h('AF DC 08 00 49 80 8F DC 08 00'),
        h('A9 04 8F 41 21 00 AF 8B 1D 00 8F 42 21 00 A9') + speed_out + h('8F 43 21 00'),
        h('AF DA 08 00 49 01 8F 40 21 00 29 01 8F DA 08 00'),
        ('label', 'skip'), h('C2 30 7A FA 68 28 5C 91 FE 24'),
    ])
    start = _asm([
        h('08 E2 20 CF 8B 1D 00'), ('b', 0xF0, 'same'),
        h('C2 10 DA A2') + speed_in + h('22 A3 FE 24 FA 28 6B'),
        ('label', 'same'), h('28 5C 9A FE 24'),
    ])
    return cleanup, start


def fast_receive_code(triplets=FAST_RECEIVE_TRIPLETS, polls=FAST_RECEIVE_POLLS):
    """SPC 자료 받기(상태 80)를 3바이트 묶음 하나마다 대기 고리(0F6D)로 돌아가지 않고 triplets 개까지 이어 받는 코드.

    원래는 묶음마다 대기 고리·상태 비교·곡 처리(1091)를 거쳐 전원 미리듣기에서 프레임당 최대 71묶음이었다(88 로 늘어남).
    묶음을 받으면 1080 으로 답하고 $F4 bit0 이 바뀌기를 polls 번까지 기다린다. 256번(약 4ms)이면 그동안 곡 처리가
    밀려 미리듣기 시각 잔차가 커졌다(곡 28 2.91 → 3.47프레임). 오지 않거나 명령(bit7 꺼짐)이면
    CLRC·RET 으로 원래 고리로 돌아가 곡 처리를 한다. 길이가 다 차면 원래 끝 처리(103A)로 간다.
    """
    h = bytes.fromhex

    def store(port):
        return h(f'8D 00 E5 {port:02X} 00 D7 80 3A 80 1A 82')  # MOV Y,#0 / MOV A,!port / MOV [$80]+Y,A / INCW / DECW

    return _asm([
        h('CD') + bytes([triplets]),
        ('label', 'next'),
        store(0xF5), ('b', 0xF0, 'end'),
        store(0xF6), ('b', 0xF0, 'end'),
        store(0xF7), ('b', 0xF0, 'end'),
        h('3F 80 10 1D'), ('b', 0xF0, 'out'),       # CALL $1080 / DEC X / BEQ out
        h('8D') + bytes([polls & 0xFF]),            # MOV Y,#polls
        ('label', 'wait'),
        h('E5 F4 00 65 F4 00'), ('b', 0xD0, 'retry'),
        h('44 8E 28 01'), ('b', 0xD0, 'got'),       # EOR A,$8E / AND A,#1 / BNE got
        ('label', 'retry'),
        ('b', 0xFE, 'wait'),                        # DBNZ Y,wait
        ('b', 0x2F, 'out'),
        ('label', 'got'),
        h('E5 F4 00'), ('b', 0x10, 'out'),          # MOV A,$00F4 / BPL out
        ('b', 0x2F, 'next'),
        ('label', 'end'), h('5F 3A 10'),            # JMP $103A
        ('label', 'out'), h('60 6F'),               # CLRC / RET
    ])


def chain_code():
    """SPC 명령 F7 m t: 시퀀스 m 이 SPC 에 있으면 이 트랙의 읽기 자리($00+X)를 m 의 t 번째 트랙 머리로 옮긴다.

    11CA 처럼 04C7+m → 칸 → 05D5+칸*6 의 [주소 2] 로 시퀀스 첫 바이트를 찾는다. 없으면 t 만 읽고 돌아가며, 앞부분은
    그 뒤에 1틱 쉼과 F7 로 돌아가는 점프를 두어 다음 틱에 다시 시도한다. 처리기는 트랙 처리 중(CLRP)에 불린다.
    """
    h = bytes.fromhex
    return _asm([
        h('3F BD 19 68 80'), ('b', 0xB0, 'hold'),               # CALL $19BD / CMP #$80 / BCS hold
        # 드라이버는 받기를 시작할 때 칸(04C7+m)을 먼저 쓰므로, m 을 받는 중($018A = 80, $0185 = m)이면 없는 것으로 본다
        h('FD E5 8A 01 68 80'), ('b', 0xD0, 'have'), h('5E 85 01'), ('b', 0xF0, 'miss'),
        ('label', 'have'), h('F6 C7 04 68 FF'), ('b', 0xF0, 'miss'),  # MOV A,$04C7+Y / CMP #$FF
        h('8F D5 A0 8F 05 A1 8D 06 CF 7A A0 DA A0'),           # $A0 = 05D5 + 칸 x 6
        h('8D 01 F7 A0 2D FC F7 A0 C4 A1 AE C4 A0'),           # $A0 = 시퀀스 주소
        h('3F BD 19 1C 60 88 02 FD'),                          # Y = 2 + 2t
        h('F7 A0 2D FC F7 A0 FD AE 7A A0'),                    # YA = 주소 + 오프셋
        h('D4 00 DB 01 6F'),                                   # MOV $00+X,A / MOV $01+X,Y / RET
        ('label', 'miss'), h('3F BD 19 6F'),
        # F7 FE n: 붙들 샘플 n. F7 FF x: 문턱 x(256바이트 단위)를 두고 이 트랙의 연주기를 붙든다(255틱 = 1.27초 뒤엔 놓음)
        ('label', 'hold'), h('FD 3F BD 19 AD FE'), ('b', 0xD0, 'arm'),
        h('C5') + _abs(HOLD_SAMPLE) + h('6F'),
        ('label', 'arm'), h('C5') + _abs(HOLD_BYTES),
        h('E8 FF C5') + _abs(HOLD_TICKS),
        h('F5 A3 02 C5') + _abs(HOLD_PLAYER) + h('6F'),
    ])


def _abs(addr):
    return addr.to_bytes(2, 'little')


def hold_check_code():
    """1458 의 연주기 고리에서 MOV A,$03B7+X(템포)를 대신한다. 붙든 연주기면 샘플이 문턱만큼 올 때까지 0 을 돌려준다.

    받은 바이트는 쓸 주소($0180)와 DIR 시작(0700+칸*4)의 위 바이트 차라 실제보다 255바이트까지 많게 잡힌다. 다 받았거나
    (받는 중이 아님) 255틱이 지나면 놓는다. 받는 중에 문턱을 넘으면 그 샘플을 HOLD_PARTIAL 에 적어 instrument 가 쓰게 한다.
    """
    h = bytes.fromhex
    return _asm([
        h('1E') + _abs(HOLD_PLAYER), ('b', 0xD0, 'norm'),
        h('E5') + _abs(HOLD_SAMPLE) + h('FD F6 FF 03 68 FF'), ('b', 0xF0, 'wait'),
        h('5E 84 01'), ('b', 0xD0, 'ready'),                  # CMP Y,$0184: 받는 중이 아니면 다 받음
        h('1C 1C FD E5 81 01 80 B6 01 07 65') + _abs(HOLD_BYTES), ('b', 0x90, 'wait'),
        h('E5') + _abs(HOLD_SAMPLE) + h('C5') + _abs(HOLD_PARTIAL),
        ('label', 'ready'), h('E8 FF C5') + _abs(HOLD_PLAYER),
        ('label', 'norm'), h('F5 B7 03 6F'),
        ('label', 'wait'), h('8C') + _abs(HOLD_TICKS), ('b', 0xF0, 'ready'),
        h('E8 00 6F'),
    ])


def hold_spare_code():
    """(instrument 판정, 받기 끝 정리). 판정은 182E 의 CMP A,$0184 를 대신해, 받는 중인 샘플이 HOLD_PARTIAL 이면 Z=0
    (있음)을 낸다. 받기 끝(103A)은 원래 일 뒤에 HOLD_PARTIAL 을 지워, 같은 샘플을 나중에 다시 받을 때 처음부터
    있는 것으로 보지 않게 한다."""
    h = bytes.fromhex
    check = _asm([
        h('65 84 01'), ('b', 0xD0, 'out'),
        h('65') + _abs(HOLD_PARTIAL), ('b', 0xD0, 'absent'),
        h('68 FF 6F'),                                         # 샘플 번호는 FF 가 아니므로 Z=0
        ('label', 'absent'), h('65 84 01'),
        ('label', 'out'), h('6F'),
    ])
    end = h('8F 00 8A 8F FF 84 2D E8 FF C5') + _abs(HOLD_PARTIAL) + h('AE 5F 35 10')
    return check, end


def chain_step_code():
    """2B:C1C1(곡이 시작한 뒤 JSR C1DB)을 대신해, 짝 표에 본체가 있으면 C22C 로 본체 시퀀스를 먼저 보낸 뒤 C1DB 로 간다.

    대기열 01 처리기는 시퀀스가 없으면 그 칸을 미루고 다음 칸을 먼저 처리하므로, 본체를 대기열(94)로 넣으면 앞부분보다
    먼저 올라갔다. 스택 깊이는 원래 JSR C1DB 와 같다(C1DB 의 C20F 가 스택으로 대기열 칸을 읽음).
    """
    h = bytes.fromhex
    return _asm([
        h('DA 48 AA BF') + CHAIN_ORDER.to_bytes(3, 'little'),  # PHX / PHA / TAX / LDA 순서,X
        h('29 FF 00'), ('b', 0xD0, 'skip'),                   # 나중에 보낼 곡이면 건너뜀
        h('BF') + CHAIN_PAIRS.to_bytes(3, 'little'),          # LDA 짝,X
        h('29 FF 00'), ('b', 0xF0, 'skip'),
        h('20 2C C2'),                                         # JSR $C22C(시퀀스 보내기, A = 번호)
        ('label', 'skip'), h('68 FA 4C DB C1'),                # PLA / PLX / JMP $C1DB
    ])


def chained_song(data, song):
    """나눈 곡이면 본체 시퀀스 번호, 아니면 None(2B:C1C1 이 발판을 부를 때만 짝 표를 본다)."""
    hook = data[lorom(0x2BC1C1):lorom(0x2BC1C1) + 3]
    if hook != bytes([0x20]) + (CHAIN_STEP & 0xFFFF).to_bytes(2, 'little'):
        return None
    number = data[lorom(CHAIN_PAIRS) + song]
    return number or None


def chain_late_step_code():
    """2B:C20C(샘플 보내기 고리 끝 PLA·PLX·RTS)를 대신해, 곡 뒤 단계(대기열 칸 bit6)이고 순서 표가 1 인 곡이면 본체를
    보낸 뒤 돌아간다. 곡 앞 샘플 고리(C1C8)도 같은 끝을 지나지만 그때 칸은 bit6 이 꺼져 있다.

    곡이 바뀌어 1A 가 그 칸을 지웠으면(FF) 보내지 않는다. FF 도 bit6 이 켜져 있어, 떠난 맵의 본체가 정리 뒤에 올라와
    SPC 에 남고 다음 곡의 본체가 자리를 얻지 못했다(성에서 필드로 나가면 필드 곡이 앞부분 뒤 멈춤).
    응답 판정(LOAD_POLL)이 바로 뒤라 48바이트 안에 넣는다: 스택의 곡(1,S)·칸(3,S)을 바로 읽는다."""
    h = bytes.fromhex
    return _asm([
        h('A3 03 AA'),                                         # LDA 3,S / TAX(대기열 칸)
        h('BD 95 1D 29 FF 00 C9 FF 00'), ('b', 0xF0, 'done'), # 칸이 지워졌으면(FF) 그만
        h('29 40 00'), ('b', 0xF0, 'done'),                   # 곡 뒤 단계(bit6)가 아니면 그만
        h('A3 01 AA BF') + CHAIN_ORDER.to_bytes(3, 'little'), # LDA 1,S / TAX(곡) / LDA 순서,X
        h('29 FF 00'), ('b', 0xF0, 'done'),
        h('BF') + CHAIN_PAIRS.to_bytes(3, 'little'),
        h('29 FF 00'), ('b', 0xF0, 'done'),
        h('20 2C C2'),                                         # JSR $C22C
        ('label', 'done'), h('68 FA 60'),                      # PLA / PLX / RTS
    ])


# 출구를 밟아 페이드 아웃하기 전에 목적지 맵 곡을 요청한다(early_song_code). 맵 불러오기 동안은 NMI 가 꺼져 대기열이
# 멈추므로, 페이드 아웃 16프레임 동안 곡 앞 자료를 보내 둔다. 맵 불러오기의 곡 요청은 같은 곡이라 건너뛴다.
EARLY_SONG = CODE + 0x400
EARLY_SONG_SITE = 0x00CD3F        # 출구 처리기들이 부르는 페이드 아웃(JSL 00:CE49 / RTS)
EARLY_SONG_CALLER = 0xCA41        # 계단·문 출구(00:C99E)의 JSR CD3F 가 남기는 돌아갈 주소
EXIT_INDEX_STUB = 0x2AFFE6        # JSR 2A:FC16(출구 번호) / RTL


def _asm_far(items, base):
    """_asm 에 ('jmp', 이름)(같은 뱅크 JMP 절대)과 ('jsr', 이름)을 더한 것. base 는 코드가 놓일 롬 주소."""
    for final in (False, True):
        out, now = bytearray(), {}
        for it in items:
            if isinstance(it, bytes):
                out += it
            elif it[0] == 'label':
                now[it[1]] = len(out)
            elif it[0] in ('jmp', 'jsr'):
                target = (base + labels[it[1]]) & 0xFFFF if final else 0
                out += bytes([0x4C if it[0] == 'jmp' else 0x20]) + target.to_bytes(2, 'little')
            else:
                rel = (labels[it[2]] - (len(out) + 2)) if final else 0
                if final and not -128 <= rel <= 127:
                    raise ValueError(f'branch to {it[2]} out of range')
                out += bytes([it[1], rel & 0xFF])
        labels = now
    return bytes(out)


def early_song_code(base=EARLY_SONG):
    """(코드, 들어가는 자리). 00:CD3F 의 JSL CE49 대신 불린다. 계단·문 출구에서만, 맵 불러오기의 목적지 계산(2A:F6FD:
    2A:ED61 표를 지금 BC 로 찾고 BD·출구 번호만큼 건너뜀)을 읽기만 하는 꼴로 따라 해 목적지 BC/BD 를 구하고, 01:83F0 처럼
    23:FD6A 맵 머리의 곡 번호(+5)를 읽는다. $194B 를 잠시 그 곡으로 두고 맵 곡 루틴 00:CE61 을 불러 앞 곡 정리·새 곡
    요청을 원래와 같은 판정(이벤트 깃발·배)으로 한다. 필드로 나가는 출구(종류 00), BC 50 이상(필드 쪽 계산), BC 04
    (01:8460 의 깃발 예외)는 그대로 둔다. 쓰는 직접 페이지($00~$0B·$84·$A5~$A7)는 되돌린다.
    """
    h = bytes.fromhex
    saved = (0x00, 0x02, 0x04, 0x06, 0x08, 0x0A, 0x84, 0xA5, 0xA7)
    tail = h('AB 7A FA 68 28 5C 49 CE 00')                     # PLB / PLY / PLX / PLA / PLP / JML 00:CE49
    items = [
        # 2A:FBA9 와 같음: 표 칸 종류(A)만큼 $84 를 넘김
        ('label', 'skip_entry'), h('29 60'), ('b', 0xF0, 'one'), h('C9 20'), ('b', 0xF0, 'three'),
        h('C9 40'), ('b', 0xF0, 'two'), h('A9 05'), ('b', 0x80, 'add'),
        ('label', 'one'), h('A9 01'), ('b', 0x80, 'add'),
        ('label', 'two'), h('A9 02'), ('b', 0x80, 'add'),
        ('label', 'three'), h('A9 03'),
        ('label', 'add'), h('18 65 84 85 84'), ('b', 0x90, 'added'), h('E6 85'),
        ('label', 'added'), h('60'),
        ('label', 'entry'),
        h('08 C2 30 48 DA 5A 8B A3 0C C9') + EARLY_SONG_CALLER.to_bytes(2, 'little'), ('b', 0xF0, 'go'),
        tail,
        ('label', 'go'),
        b''.join(h(f'A5 {a:02X} 48') for a in saved),
        h('E2 30 22') + EXIT_INDEX_STUB.to_bytes(3, 'little') + h('AA A9 2A 48 AB'),
        h('A9 61 85 84 A9 ED 85 85'),
        ('label', 'scan'), h('B2 84 C9 FF'), ('b', 0xD0, 'scan2'), ('jmp', 'bail'),
        ('label', 'scan2'), h('C5 BC'), ('b', 0xF0, 'found'),
        ('label', 'skip'), h('B2 84 E6 84'), ('b', 0xD0, 'skip2'), h('E6 85'),
        ('label', 'skip2'), h('C9 FF'), ('b', 0xD0, 'skip'), ('b', 0x80, 'scan'),
        ('label', 'found'), h('E6 84'), ('b', 0xD0, 'found2'), h('E6 85'),
        ('label', 'found2'), h('A5 BD'), ('b', 0xF0, 'index'), h('85 01'),
        ('label', 'floor'), h('B2 84 48'), ('jsr', 'skip_entry'), h('68'), ('b', 0x30, 'floor_end'), ('b', 0x80, 'floor'),
        ('label', 'floor_end'), h('C6 01'), ('b', 0xD0, 'floor'),
        ('label', 'index'), h('E0 00'), ('b', 0xF0, 'got'),
        ('label', 'next'), h('B2 84'), ('jsr', 'skip_entry'), h('CA'), ('b', 0xD0, 'next'),
        ('label', 'got'), h('B2 84 85 01 29 1F 85 03 A5 01 29 60'),
        h('C9 60'), ('b', 0xD0, 't40'), h('A0 04 B1 84 85 02'), ('b', 0x80, 'have'),
        ('label', 't40'), h('C9 40'), ('b', 0xD0, 't20'), h('A5 BC 85 02'), ('b', 0x80, 'have'),
        ('label', 't20'), h('C9 20'), ('b', 0xF0, 't20b'), ('jmp', 'bail'),
        ('label', 't20b'), h('A0 02 B1 84 85 02'),
        ('label', 'have'), h('A5 02 C9 50'), ('b', 0xB0, 'bail_near'), h('C9 04'), ('b', 0xF0, 'bail_near'),
        h('C2 30 A5 02 29 FF 00 0A AA BF 6A FD 23 85 A5'),        # $A5 = 23:FD6A[BC]
        h('A5 03 29 FF 00 0A 85 00 0A 18 65 00 18 65 A5 85 A5'),  # + BD x 6
        h('E2 30 A9 23 85 A7 A0 05 B7 A5'),                       # 곡 번호
        h('EB AF 4B 19 7E 48 EB 8F 4B 19 7E'),                    # 옛 $194B 를 쌓고 곡 번호를 둠
        h('A9 00 48 AB 22 61 CE 00'),                             # DB=00 / JSL 00:CE61
        h('68 8F 4B 19 7E'),
        ('label', 'bail_near'),
        ('label', 'bail'), h('C2 30'),
        b''.join(h(f'68 85 {a:02X}') for a in reversed(saved)),
        tail,
    ]
    code = _asm_far(items, base)
    entry = base + _asm_far(items[:items.index(('label', 'entry'))], base).__len__()
    return code, entry


EARLY_SONG_SKIP = CODE + 0x560    # 맵 불러오기의 앞 곡 정리(MAP_CLEANUP)·곡 요청(MAP_START) 대신, 둘에 하나씩


def early_skip_code(original):
    """맵 곡 루틴의 정리·요청(JSL original, A = 곡) 대신 불린다. 대기열에 같은 곡의 01(보내는 중 81·곡 뒤 단계 41 포함)이 남아 있으면
    아무것도 하지 않는다. 출구에서 미리 요청한 곡을 보내는 중이면 원래 판정($1D8B = 지금 곡)은 아직 다른 곡이라, 두 번째
    01 이 앞 곡 정리(1A)와 함께 들어가 처음부터 다시 보냈다."""
    h = bytes.fromhex
    jml = bytes([0x5C]) + original.to_bytes(3, 'little')
    return _asm([
        h('08 E2 30 DA 48 AF 93 1D 7E AA'),
        ('label', 'loop'), h('8A CF 91 1D 7E'), ('b', 0xF0, 'none'),
        h('BF 95 1D 7E 29 3F C9 01'), ('b', 0xD0, 'next'),
        h('BF A5 1D 7E C3 01'), ('b', 0xF0, 'found'),
        ('label', 'next'), h('E8 8A 29 0F AA'), ('b', 0x80, 'loop'),
        ('label', 'none'), h('68 FA 28') + jml,
        ('label', 'found'), h('68 FA 28 6B'),
    ])


# 맵 불러오기처럼 NMI 를 끈 동안에도 소리 일(2B:BECE 코루틴)을 돌린다(load_pump). 원래는 NMI 가 꺼지면 코루틴이 멈춰
# 불러오기 70프레임 동안 전송이 0 이었다. NMI 를 끌 때 V-IRQ 를 켜 LOAD_LINES 줄마다 다시 걸고, IRQ 처리기가 SPC 가 받을 준비가 됐을 때만
# 코루틴을 잠깐 돌린다. 코루틴은 2B:C292 응답 기다림에서 준비가 안 됐으면 NMI 의 선점과 같은 꼴로 바로 양보한다.
LOAD_IRQ = CODE + 0x600            # IRQ 처리기
LOAD_NMI_OFF = CODE + 0x780        # 00:9691 STA $4200(NMI 끔) 대신: V-IRQ 를 함께 켬
LOAD_EXIT_CLI = CODE + 0x7C0       # 00:CD5B(출구 뒤 NMI 끄는 루틴 CD48 안 JSL 03AADA) 대신
LOAD_NMI_ON = CODE + 0x7A0         # 00:9676 STA $4200(NMI 켬) 대신: 걸려 있는 IRQ 를 지움
LOAD_GATE = 0x2BB741               # C169(SPC 명령 보내기) 첫머리 대신: NMI 가 꺼져 있으면 곡 틀기(01)를 미룬다
LOAD_POLL = 0x2BB7D0               # C298 의 응답 판정. NMI 선점 범위(00:8004 발판)에 든다
LOAD_STUB = 0x008000               # IRQ 벡터 받침(JML LOAD_IRQ)과 NMI 선점 범위 발판. 원래 0 이고 부르는 곳 없음
LOAD_FRAME_ENTER = 0x0085E5        # 원래 코드 JSR 969A / RTL: 코루틴으로 넘어갔다가 양보하면 돌아옴
LOAD_LINES = 8                     # IRQ 사이 줄 수. 줄마다 걸면 코루틴 전환이 끝나기 전에 다음 IRQ 가 와 늘 취소됐고, 3줄이면 처리기가 CPU 를 절반 먹어 검은 화면이 75프레임 늘었다.
                                   # 8줄은 12줄보다 성 곡이 7프레임 일찍 울리고 검은 화면은 성만 7·나머지 1프레임 늘었다


NMI_RANGE_STUB = LOAD_STUB + 4


# マスタードラゴン 에서 내리기(01:C213)는 1A 와 맵 곡 01 을 보낸다. 타는 동안 필드 곡이 그대로 울리므로 같은 곡을
# 정리했다 다시 보내게 되어, 곡 앞 샘플이 많은 옮긴 필드 곡은 명령 뒤 +87프레임 조용했다(원본 +37).
VEHICLE_SONG = CODE + 0x800
VEHICLE_SONG_SITE = 0x01C213


def vehicle_song_code():
    """01:C213 의 JSL 24:FE91(1A) / LDA $194B / JSL 24:FE9A(01) 대신 불린다(8비트 A). 지금 곡($1D8B)이 맵 곡($194B)이면
    둘 다 건너뛰어 울리던 곡을 잇고, 다르면 원래대로 보낸다."""
    h = bytes.fromhex
    return _asm([
        h('48 AD 8B 1D CD 4B 19'), ('b', 0xF0, 'same'),       # PHA / LDA $1D8B / CMP $194B
        h('68 22 91 FE 24 AD 4B 19 22 9A FE 24 6B'),          # PLA / JSL 1A / LDA $194B / JSL 01 / RTL
        ('label', 'same'), h('68 6B'),                         # PLA / RTL
    ])


# 1A 는 앞 곡을 줄인 뒤 16(참조 수 지움)·0A(참조 없는 샘플·시퀀스 버림)를 보내, 다음 곡과 함께 쓰는 샘플도 버렸다가
# 다시 받았다. 배에서 내리면 배 곡과 필드 곡이 함께 쓰는 샘플까지 다시 받아 원본보다 오래 조용했다.
# 곡 뒤 단계를 끝까지 마친 곡을 KEEP_SONG 에 적어 두고, 16 과 0A 사이에서 그 곡과 다음 곡이 함께 쓰는 샘플을
# 2B:C21E(샘플 하나 보내기: 있으면 참조 수만 올림)로 다시 표시해 0A 에서 살린다.
KEEP_CODE = 0x2BEA50               # 2B 의 빈 자리 끝 쪽. 앞(~EA01)은 IPL 꼬리라 빌드가 커지면 뒤로 는다
KEEP_SONG = 0x1A96                 # 낮은 WRAM. 전원부터 선실·배·융단·전투·마을까지 7E:1A86~1A97 에 접근 없음. 0 = 없음
KEEP_DONE_SITE = 0x2BC1C5          # 곡 뒤 단계 끝의 JMP C184(칸 비우기)
KEEP_MARK_SITE = 0x2BC0AD          # 1A 끝의 JSR C32F(16 의 대답) / LDA #0A / JSR C112
COROUTINE_EXTRA = KEEP_CODE & 0xFFFF   # 2B:EA50~FFFF 도 코루틴 코드로 본다(EB00~ 는 샘플 자료라 주 스레드 코드가 없음)


def keep_samples_code():
    """(곡 뒤 단계 끝 코드, 1A 의 표시 코드). 둘 다 16비트 A·X 문맥이고, 표시 코드는 C0A3 이 쌓은 1A 의 칸 번호를
    스택에서 읽는다. 표시는 C21E 가 첫머리 C32F 로 앞 명령의 대답을 소비하므로 16 의 대답을 기다리기 전에 들어간다.
    적은 곡이 다 실려 있지 않아도(다른 길로 16·0A 가 지나감) C21E 는 없는 샘플을 보내므로 결과는 원래와 같다."""
    h = bytes.fromhex
    song = KEEP_SONG.to_bytes(2, 'little')
    done = _asm([
        h('08 C2 30 BD 95 1D 29 FF 00 C9 FF 00'), ('b', 0xF0, 'skip'),   # 칸이 지워졌으면(1A 가 끊음) 적지 않음
        h('BD A5 1D 29 FF 00 8D') + song,
        ('label', 'skip'), h('28 4C 84 C1'),                              # PLP / JMP $C184
    ])
    mark = _asm([
        h('08 C2 30 AD') + song + h('29 FF 00'), ('b', 0xF0, 'done'),
        h('A3 04'),                                                       # 1A 의 칸
        ('label', 'scan'), h('1A 29 0F 00 AA E2 20 CD 91 1D C2 20'), ('b', 0xF0, 'done'),
        h('BD 95 1D 29 FF 00 C9 01 00'), ('b', 0xF0, 'found'),            # 아직 시작하지 않은 01·03·0C
        h('C9 03 00'), ('b', 0xF0, 'found'),
        h('C9 0C 00'), ('b', 0xF0, 'found'),
        h('8A'), ('b', 0x80, 'scan'),
        ('label', 'found'), h('BD A5 1D 29 FF 00 20 CB C3'),             # 다음 곡의 레코드
        h('BF 7D E6 2B 29 FF 00'), ('b', 0xF0, 'done'),
        h('A8'),
        ('label', 'new'), h('5A DA BF 7F E6 2B 29 FF 00 C9 80 00'), ('b', 0xB0, 'next'),   # 고정 샘플은 건너뜀
        h('48 AD') + song + h('29 FF 00 20 CB C3 BF 7D E6 2B 29 FF 00 A8'), ('b', 0xF0, 'miss'),
        ('label', 'old'), h('BF 7F E6 2B 29 FF 00 C3 01'), ('b', 0xF0, 'hit'),
        h('E8 88'), ('b', 0xD0, 'old'),
        ('label', 'miss'), h('68'), ('b', 0x80, 'next'),
        ('label', 'hit'), h('68 20 1E C2'),                              # JSR $C21E
        ('label', 'next'), h('FA 7A E8 88'), ('b', 0xD0, 'new'),
        ('label', 'done'), h('9C') + song,                              # 0A 뒤에는 다 실려 있지 않다
        h('28 20 2F C3 A9 0A 00 4C 12 C1'),                               # PLP / JSR C32F / LDA #0A / JMP C112
    ])
    return done, mark


def nmi_range_code():
    """NMI 선점(00:88E2)이 2B:B741~B804(우리 코루틴 코드: 응답 판정·곡 틀기 문·나눈 곡 발판·곡 번호 도우미)도
    코루틴으로 보게 하는 00:8004 발판. 빠뜨리면 그 안에서 NMI 가 와도 코루틴이 멈추지 않아 게임이 한 프레임 밀린다."""
    h = bytes.fromhex
    stub = _asm([
        h('C9 CE BE'), ('b', 0xB0, 'high'),
        h('C9 41 B7'), ('b', 0x90, 'norm'),
        h('C9 05 B8'), ('b', 0xB0, 'norm'),
        ('label', 'co'), h('4C EC 88'),
        ('label', 'high'), h('C9 22 C4'), ('b', 0x90, 'co'),
        ('label', 'norm'), h('4C 1E 89'),
    ])
    if len(stub) > 0x1C:
        raise ValueError('NMI range stub overflows 00:8004-801F')
    # 88E2 에서 먼저 COROUTINE_EXTRA 위를 코루틴으로 보고, 나머지는 발판이 판정한다(88E7 의 C422 판정은 발판이 대신함)
    entry = (h('C9') + COROUTINE_EXTRA.to_bytes(2, 'little') + h('B0 05 4C') + (NMI_RANGE_STUB & 0xFFFF).to_bytes(2, 'little')
             + h('EA EA'))
    return {NMI_RANGE_STUB: (stub, None),
            0x0088E2: (entry, h('C9 CE BE 90 37 C9 22 C4 B0 32'))}


def song_store_helper():
    """2B:BF5A(8비트, A = 곡 번호) 대신: 32~46(효과음)이 아니면 $1D8B(지금 곡)에 둔다."""
    return bytes.fromhex('C9 47 B0 04 C9 32 B0 03 8D 8B 1D 60')


def song_test_helper():
    """2B:BFB4(16비트 CMP #$0032 → BCS) 대신: C=1 ⇔ 32 <= A < 47."""
    return bytes.fromhex('C9 47 00 B0 04 C9 32 00 60 18 60')


def load_pump_code(lines=LOAD_LINES):
    """{롬 주소: (바이트, 원래 바이트 또는 None=빈 자리)}. 

    NMI 선점(00:88A3)은 2B:BECE~C422 의 PC 만 코루틴으로 본다. 응답 판정을 둘 2B:B7D0 과 나눈 곡의 발판(B780·B7A0)도
    코루틴 코드이므로 00:88E2 를 발판으로 돌려 2B:B741~B804 도 선점 범위로 넣는다(B805~ 는 주 스레드 코드).
    """
    h = bytes.fromhex
    poll_cont = (LOAD_POLL & 0xFFFF) + 0  # 아래에서 채움
    poll_items = [
        ('b', 0xD0, 'not_ready'),                     # C295 CMP $2140 의 결과(JSR 은 플래그를 바꾸지 않음)
        h('4D DC 08'), ('b', 0x30, 'not_ready'),
        h('60'),
        ('label', 'not_ready'), h('A5 19'), ('b', 0x10, 'spin'),   # NMI 가 켜져 있으면 원래처럼 돈다
        h('4B F4 00 00'),                             # PHK / PEA cont (자리는 뒤에서 채움)
        h('08 C2 30 8B 0B 48 DA 5A A9 00 00 5B E2 20 48 AB 5C EC 88 00'),
        ('label', 'spin'), h('A9 80 60'),             # 다시 판정(N=1 → BMI C292)
    ]
    poll = bytearray(_asm(poll_items))
    cont = poll.index(h('A9 80 60'))
    pea = poll.index(h('4B F4 00 00')) + 2
    poll[pea:pea + 2] = ((LOAD_POLL & 0xFFFF) + cont).to_bytes(2, 'little')
    poll_cont = (LOAD_POLL & 0xFFFF) + cont
    # 곡 틀기는 자료를 다 올린 뒤 다시 보내는 01 이다. 불러오는 동안 보내면 화면이 밝아지기 전에 곡이 울렸다.
    yield_frame = h('08 C2 30 8B 0B 48 DA 5A A9 00 00 5B E2 20 48 AB 5C EC 88 00')
    gate_items = [
        ('label', 'top'), h('BD 95 1D 29 3F 00 C9 01 00'), ('b', 0xD0, 'done'),
        h('A5 19 29 80 00'), ('b', 0xF0, 'done'),
        h('4B F4 00 00') + yield_frame,
        ('label', 'cont'), ('b', 0x80, 'top'),
        ('label', 'done'), h('4C 2F C3'),
    ]
    gate = bytearray(_asm(gate_items))
    gate_cont_off = len(gate) - 5  # cont: BRA top(2) 뒤 done: JMP C32F(3)
    gate_cont = (LOAD_GATE & 0xFFFF) + gate_cont_off
    pea = gate.index(h('4B F4 00 00')) + 2
    gate[pea:pea + 2] = gate_cont.to_bytes(2, 'little')
    irq = _asm_far([
        h('C2 30 8B 0B 48 DA 5A A9 00 00 5B E2 20 48 AB AD 11 42'),
        # 다음 IRQ 를 지금 줄 + LOAD_LINES 에(262줄에서 돌아감)
        h('AD 3F 21 AD 37 21 AD 3D 21 EB AD 3D 21 29 01 EB C2 20 18 69') + lines.to_bytes(2, 'little'),
        h('C9 06 01'), ('b', 0x90, 'vt'), h('E9 06 01'),
        ('label', 'vt'), h('8D 09 42 E2 20'),
        h('A3 0D C9 2B'), ('b', 0xD0, 'not2b'),
        h('C2 20 A3 0B C9') + COROUTINE_EXTRA.to_bytes(2, 'little'), ('b', 0xB0, 'tonmi'),
        h('C9 41 B7'), ('b', 0x90, 'norm16'),
        h('C9 05 B8'), ('b', 0x90, 'tonmi'),
        h('C9 CE BE'), ('b', 0x90, 'norm16'),
        h('C9 B1 C4'), ('b', 0x90, 'tonmi'),
        ('b', 0x80, 'norm16'),
        ('label', 'tonmi'), h('5C A3 88 00'),               # 코루틴·전환 중이면 NMI 의 선점(저장하거나 전환 취소)
        ('label', 'exit'), h('C2 30 7A FA 68 2B AB 40'),
        # 주 스레드가 소리 대기열을 고치는 중(24:FE00~, 24:FF83 넣기 등)이면 코루틴을 돌리지 않는다
        ('label', 'not2b'), h('C9 24'), ('b', 0xD0, 'not24'),
        h('C2 20 A3 0B C9 00 FE E2 20'), ('b', 0xB0, 'exit'),
        ('label', 'not24'), h('C9 7F'), ('b', 0xF0, 'norm8'),
        h('C2 20 A3 0B C9 13 09'), ('b', 0xB0, 'norm16'), h('C9 EF 08'), ('b', 0xB0, 'tonmi'),
        ('label', 'norm16'), h('E2 20'),
        ('label', 'norm8'), h('A5 19'), ('b', 0x10, 'exit2'),
        # 대기열이 비었거나 지금 칸이 곡 뒤 단계(bit6, 곡이 이미 시작)면 IRQ 를 끈다. 곡 뒤 자료까지 불러오기 중에
        # 보내면 곡은 화면보다 40프레임 넘게 먼저 나오는데 검은 화면만 늘었다.
        h('AD 91 1D CD 93 1D'), ('b', 0xF0, 'stop'),
        # 곡 요청(01)이 아닌 칸에서 코루틴에 들어가면 NMI 가 꺼진 동안 돌아올 길이 없다(C32F 등은 양보하지 않음)
        h('C2 20 AD 93 1D 29 FF 00 AA E2 20 BD 95 1D 29 40'), ('b', 0xD0, 'stop'),
        h('BD 95 1D 29 3F C9 01'), ('b', 0xF0, 'pump'),
        ('label', 'stop'), h('A5 1E 8D 00 42'),
        ('label', 'exit2'), ('jmp', 'exit'),
        ('label', 'pump'),
        h('AD E0 08 C9 2B'), ('b', 0xD0, 'go'),
        h('C2 20 AD DE 08 C9') + gate_cont.to_bytes(2, 'little') + h('E2 20'), ('b', 0xF0, 'stop'),
        h('C2 20 AD DE 08 C9') + poll_cont.to_bytes(2, 'little') + h('E2 20'), ('b', 0xD0, 'go'),
        h('AD 40 21 CD 40 21'), ('b', 0xD0, 'exit2'), h('4D DC 08'), ('b', 0x30, 'exit2'),
        # 응답 판정에서 멈춘 코루틴의 고리(2B:C29F~C2FC) 한 바퀴를 저장된 Y(08E5)·X(08E3)로 대신 돈다. 코루틴으로
        # 넘어가면 전환만 수백 사이클이라 불러오기가 75% 늘었다. 고리가 끝나는 바퀴(X-3 < 0)와 묶음 사이의 대기열
        # 처리(BED5)는 코루틴에 맡긴다(불러오는 동안은 새 칸이 없다).
        h('C2 30 AD E3 08 38 E9 03 00'), ('b', 0x10, 'fast'),
        ('label', 'go16'), h('E2 20'),
        ('label', 'go'), h('22') + LOAD_FRAME_ENTER.to_bytes(3, 'little'), h('A5 19 29 FE 85 19'),
        ('jmp', 'exit'),
        ('label', 'fast'),
        h('E2 20 AD DC 08 49 80 8D DC 08 AC E5 08'),
        b''.join(h(f'B7 FB 8D {port:02X} 21 C8') + bytes([0xD0, 0x07]) + h('A0 00 80 64 FB E6 FD') for port in (0x41, 0x42, 0x43)),
        h('A9 80 0D DA 08 49 01 8D 40 21 29 01 8D DA 08 8C E5 08'),
        h('C2 20 AD E3 08 38 E9 03 00 8D E3 08 8D 8D 1D'),
        ('jmp', 'exit'),
    ], LOAD_IRQ)
    # $2137 로 줄 번호를 잡으려면 $4201 bit7 이 켜져 있어야 한다. 게임은 IRQ 를 쓰지 않아 I 를 켠 채로 돌므로
    # (불러오기 70프레임 가운데 54프레임), 00:967F 가 PLP 로 되돌릴 호출자의 P(스택 7번째)에서 I 를 끈다.
    # NMI 를 다시 켤 때(00:9664) 같은 자리의 I 를 켜 원래대로 둔다.
    nmi_off = h('09 20 8F 00 42 00 48 A9 FF 8F 01 42 00 A9 00 8F 09 42 00 8F 0A 42 00 A3 07 29 FB 83 07 68 6B')
    nmi_on = h('8F 00 42 00 48 AF 11 42 00 A3 07 09 04 83 07 68 6B')
    stub = h('5C') + LOAD_IRQ.to_bytes(3, 'little')
    # CD48 은 PHP·PHB 뒤 NMI 를 끄고 PLB·PLP 로 끝나 I 를 다시 켠다. 불러오기 루틴들은 이 뒤의 I 를 이어받는다.
    exit_cli = h('22 DA AA 03 A3 05 29 FB 83 05 6B')
    return {
        LOAD_EXIT_CLI: (exit_cli, None),
        0x00CD5B: (h('22') + LOAD_EXIT_CLI.to_bytes(3, 'little'), h('22 DA AA 03')),
        LOAD_POLL: (bytes(poll), None),
        LOAD_GATE: (bytes(gate), None),
        0x2BC169: (h('20') + (LOAD_GATE & 0xFFFF).to_bytes(2, 'little'), h('20 2F C3')),
        LOAD_IRQ: (irq, None),
        LOAD_NMI_OFF: (nmi_off, None),
        LOAD_NMI_ON: (nmi_on, None),
        LOAD_STUB: (stub, None),
        0x00FFEE: ((LOAD_STUB & 0xFFFF).to_bytes(2, 'little'), h('7F 8F')),
        **nmi_range_code(),
        0x2BC298: (h('20') + (LOAD_POLL & 0xFFFF).to_bytes(2, 'little') + h('30 F5 EA EA'), h('D0 F8 4D DC 08 30 F3')),
        0x009691: (h('22') + LOAD_NMI_OFF.to_bytes(3, 'little'), h('8F 00 42 00')),
        0x009676: (h('22') + LOAD_NMI_ON.to_bytes(3, 'little'), h('8F 00 42 00')),
    }


def pinned_sequences(data):
    pos = lorom(RESIDENT_SEQUENCES)
    end = data.index(0xFF, pos)
    return list(data[pos:end])


def unpin_sequences(data, songs):
    """늘 두는 시퀀스 목록(2B:C429, 켤 때 명령 93 으로 고정)에서 songs 를 빼고 FF 로 채운다.

    늘 두는 곡은 2B 로더가 곡 앞 전송(2B:C1AE)을 건너뛰어 곡 묶음의 「곡 앞」 샘플을 보내지 않고,
    시퀀스가 SPC 에 늘 남아 다른 모든 곡의 예산을 줄인다. 빼면 보통 곡처럼 틀 때마다 올라간다.
    """
    pos = lorom(RESIDENT_SEQUENCES)
    old = pinned_sequences(data)
    kept = [x for x in old if x not in songs]
    data[pos:pos + len(old) + 1] = bytes(kept) + b'\xff' * (len(old) - len(kept) + 1)
    return [x for x in old if x in songs]


def put(data, addr, payload, expected=None, empty=False):
    pos = lorom(addr)
    old = data[pos:pos + len(payload)]
    if expected is not None and old != expected:
        raise ValueError(f'{addr:06X}: incompatible base bytes')
    if empty and any(old):
        raise ValueError(f'{addr:06X}: output area already occupied')
    data[pos:pos + len(payload)] = payload


def write_preview(data, preview):
    """미리듣기에서만 타이틀·메뉴 곡을 preview 로 바꾼다(청취용). 게임용 빌드는 이 훅을 쓰지 않는다."""
    def write(addr, payload, expected=None, empty=False):
        put(data, addr, payload, expected, empty)

    call = data[lorom(0x30801C):lorom(0x30801C) + 6]
    if call != bytes.fromhex('22 00 FF 70 EA EA'):
        raise ValueError('preview needs the accepted overture title build')
    title = bytes.fromhex('08 E2 20 A9') + bytes([preview]) + bytes.fromhex('22 9A FE 24 28 6B')
    write(CODE + 0x100, title, empty=True)
    write(0x30801C, bytes.fromhex('22 00 81 71 EA EA'))
    write(0x30FF05, bytes([preview]), b'\x10')
    menu = bytes.fromhex('8D 00 21 08 E2 20 A9') + bytes([preview])
    menu += bytes.fromhex('22 BE FE 24 A9 10 22 9A FE 24 22 44 FE 24 28 6B')
    write(CODE + 0x140, menu, empty=True)
    write(0x00A709, bytes.fromhex('22 40 81 71 EA EA'), bytes.fromhex('22 20 FF 70 EA EA'))


def preview_rom(rom, preview):
    """install 로 만든 게임용 롬에 미리듣기 훅만 더한다. 곡이 많을 때 곡마다 다시 변환하지 않으려고 쓴다."""
    data = bytearray(rom)
    write_preview(data, preview)
    return set_checksum(bytes(data))


def write_resident_samples(data, ids):
    """늘 두는 샘플 목록을 71:8200 으로 옮겨 ids 로 바꾼다. 켤 때 명령 8B 가 이 순서로 보내고 고정한다.

    고정 샘플은 SPC 샘플 칸 0x14개 가운데 늘 자리를 차지하므로, 곡 하나가 쓸 수 있는 칸은 0x14 - 고정 수에서
    그 곡이 고정 샘플을 함께 쓰는 만큼 늘어난다.
    """
    if len(set(ids)) != len(ids) or any(not 0 <= x < 0xC8 for x in ids) or len(ids) >= SAMPLE_SLOTS:
        raise ValueError('resident samples must be distinct IDs and leave sample slots for songs')
    put(data, RESIDENT_SAMPLE_LIST, bytes(ids) + b'\xff', empty=True)
    put(data, RESIDENT_SAMPLE_LOAD, bytes([0xBF]) + RESIDENT_SAMPLE_LIST.to_bytes(3, 'little'),
        bytes([0xBF]) + RESIDENT_SAMPLES.to_bytes(3, 'little'))


def install(base, replacements, *, sample_resources=None, map_fades=False, preview=None, pinned=(),
            resident=None, set_records=None, fast_receive=False, chains=None, chain_late=(), hold=False, early_song=False, load_pump=False,
            vehicle_song=False, keep_samples=False):
    """pinned 는 늘 두는 시퀀스 목록에 남길 바꾸는 곡(나머지 바꾸는 곡은 목록에서 뺌). resident 는 새 늘 두는 샘플 목록
    전체(주지 않으면 그대로). set_records 는 바꾸지 않는 곡의 곡 묶음 레코드 {곡: (k, 샘플…)}.
    fast_receive 는 SPC 자료 받기를 묶음 여러 개 이어 받게 바꾼다(fast_receive_code). chains 는 {곡: 본체 시퀀스} 로,
    곡의 시퀀스는 앞부분이고 본체를 47 부터 차례로 번호를 매겨 둔다(chain_code·chain_step_code). chain_late 의 곡은
    본체를 곡 뒤 샘플 다음에 보낸다(chain_late_step_code). hold 는 곡 붙들기(F7 FE·FF)를 드라이버에 넣는다(빠른 받기 필요).
    early_song 은 계단·문 출구에서 페이드 아웃 전에 목적지 맵 곡을 요청한다(early_song_code).
    load_pump 는 NMI 를 끈 동안(맵 불러오기)에도 IRQ 로 곡 앞 자료를 보낸다(load_pump_code, early_song 필요).
    vehicle_song 은 マスタードラゴン 에서 내릴 때 울리던 맵 곡을 다시 보내지 않고 잇는다(vehicle_song_code).
    keep_samples 는 1A 의 정리에서 앞 곡과 다음 곡이 함께 쓰는 샘플을 버리지 않는다(keep_samples_code, load_pump 필요).
    """
    if len(base) not in (0x180000, 0x200000, 0x400000):
        raise ValueError('base must be a headerless 1.5MB, 2MB or 4MB DQ5 build')
    if not replacements:
        raise ValueError('at least one replacement is required')
    data = bytearray(base) + bytes(0x400000 - len(base))
    allocations = []
    sample_resources = sample_resources or {}

    def write(addr, payload, expected=None, empty=False):
        put(data, addr, payload, expected, empty)

    hook = bytes.fromhex('22 10 80 70 60')
    actual = bytes(data[lorom(0x2BC3AB):lorom(0x2BC3AB) + 5])
    if actual == hook:
        if data[lorom(RELOC_CODE):lorom(RELOC_CODE) + len(reloc_code())] != reloc_code():
            raise ValueError('unknown relocation routine')
    elif actual == bytes.fromhex('48 DA 29 FF 00'):
        write(RELOC_CODE, reloc_code(), empty=True)
        write(RELOC_SEQ_TABLE, bytes(0x64 * 3), empty=True)
        write(RELOC_SMP_TABLE, bytes(0xC8 * 3), empty=True)
        write(0x2BC3AB, hook)
    else:
        raise ValueError('unsupported sequence relocation hook')
    drv = lorom(DRIVER_BLOCK) + 4 + DRIVER_RECEIVE - 0x0750
    if data[drv] == 0x5F:
        raise ValueError('base already has the fast receive patch; build from the ROM before it')
    records = read_sets(data)
    old_size = sum(map(len, records))
    if not set(pinned) <= set(replacements) or not set(pinned) <= set(pinned_sequences(data)):
        raise ValueError('pinned songs must be replaced songs already in the resident sequence list')
    unpinned = unpin_sequences(data, set(replacements) - set(pinned))
    if resident is not None:
        write_resident_samples(data, list(resident))
    for song, (first, *ids) in (set_records or {}).items():
        if song in replacements or not 0 <= first <= len(ids):
            raise ValueError(f'record override {song:02X} must be an unreplaced song with 0 <= k <= L')
        records[song] = bytes([len(ids), first, *ids])
    free = {bank: 0x8000 for bank in DATA_BANKS}

    def place(payload, what):
        # 첫 맞춤: 앞 뱅크의 남은 자리부터 채워 뱅크 끝에 버려지는 바이트를 줄인다.
        if len(payload) > 0x8000:
            raise ValueError(f'{what} exceeds a LoROM bank')
        for bank in DATA_BANKS:
            if free[bank] + len(payload) <= 0x10000:
                address = bank << 16 | free[bank]
                free[bank] += len(payload)
                return address
        raise ValueError(f'reserved sound banks exhausted placing {what} '
                         f'({sum(0x10000 - x for x in free.values())} bytes left in fragments)')

    chains = chains or {}
    expand = bool(chains) or any(song >= NEW_SONG_FIRST for song in replacements)
    if expand:
        if len(records) != SEQUENCE_COUNT:
            raise ValueError('base already has new song numbers; build from the ROM before them')
        top = max([FIRST_CHAIN_SONG + len(chains)] if chains else []
                  + [song + 1 for song in replacements if song >= NEW_SONG_FIRST])
        if top > SONG_LIMIT:
            raise ValueError('too many songs for the SPC sequence index')
        records += [bytes(2)] * (top - len(records))
    for song, item in sorted(replacements.items()):
        if not (0 <= song < SEQUENCE_COUNT or NEW_SONG_FIRST <= song <= NEW_SONG_LAST) or song == 0x10:
            raise ValueError('target song must be 00..46 or 47..4B, except the protected title 10')
        validate_replacement(item)
        payload = len(item.sequence).to_bytes(2, 'little') + item.sequence
        address = place(payload, f'sequence {song:02X}')
        write(address, payload, empty=True)
        write(RELOC_SEQ_TABLE + song * 3, address.to_bytes(3, 'little'))
        first = len(item.samples) if item.send_first is None else item.send_first
        records[song] = bytes([len(item.samples), first, *item.samples])
        allocations.append({'song': f'{song:02X}', 'at': f'{address:06X}', 'bytes': len(item.sequence),
                            'samples': list(item.samples), 'send_first': first})
    for sample, payload in sorted(sample_resources.items()):
        if not 0x26 <= sample < 0xC8:
            raise ValueError('custom samples must use free IDs 26..C7')
        if len(payload) < 18 or int.from_bytes(payload[:2], 'little') != len(payload) - 2:
            raise ValueError('sample resource must contain its 2-byte size header')
        address = place(payload, f'sample {sample:02X}')
        write(address, payload, empty=True)
        write(RELOC_SMP_TABLE + sample * 3, address.to_bytes(3, 'little'))
    chain_numbers = {}
    if chains:
        if not set(chains) <= set(replacements):
            raise ValueError('chained songs must be replaced songs')
        anchor = resident_samples(data)[0]
        pairs = bytearray(0x64)
        for number, (song, main) in enumerate(sorted(chains.items()), FIRST_CHAIN_SONG):
            if number >= 0x64:
                raise ValueError('too many chained songs for the SPC sequence index')
            payload = len(main).to_bytes(2, 'little') + main
            address = place(payload, f'chained sequence {number:02X}')
            write(address, payload, empty=True)
            write(RELOC_SEQ_TABLE + number * 3, address.to_bytes(3, 'little'))
            # 본체 레코드는 늘 두는 샘플 하나만(악기 번호는 앞부분 곡의 레코드를 씀)
            records[number] = bytes([1, 1, anchor])
            # 곡 뒤 샘플이 없으면 2B 가 곡 뒤 단계(C1BA)를 지나지 않아 본체를 보내지 않았다(곡 01·0C 가 앞부분만 울림).
            # 늘 두는 샘플 하나를 곡 뒤로 덧붙여 그 단계를 지나게 한다(이미 있어 보내지는 않음, 악기 번호는 그대로).
            size, first, *ids = records[song]
            if first == size:
                extra = next((x for x in resident_samples(data) if x not in ids), None)
                if extra is None:
                    raise ValueError(f'chained song {song:02X} uses every resident sample; nothing to append')
                records[song] = bytes([size + 1, first, *ids, extra])
            pairs[song] = number
            chain_numbers[song] = number
        write(CHAIN_PAIRS, bytes(pairs), empty=True)
        write(CHAIN_ORDER, bytes(int(x in chain_late) for x in range(0x64)), empty=True)
        step_code, late_code = chain_step_code(), chain_late_step_code()
        write(CHAIN_STEP, step_code, bytes(len(step_code)))
        write(CHAIN_LATE_STEP, late_code, bytes(len(late_code)))
        write(0x2BC1C1, bytes([0x20]) + (CHAIN_STEP & 0xFFFF).to_bytes(2, 'little'), bytes.fromhex('20 DB C1'))
        write(0x2BC20C, bytes([0x4C]) + (CHAIN_LATE_STEP & 0xFFFF).to_bytes(2, 'little'), bytes.fromhex('68 FA 60'))
    table = b''.join(records)
    if expand:
        # 판정 도우미는 표 바로 뒤(SPC 28EC + 표 길이)에 두고 자리 시작을 그만큼 민다
        helper_at = 0x28EC + len(table)
        table += SPC_EFFECT_HELPER
        for site in SPC_EFFECT_COMPARES:
            write(DRIVER_BLOCK + 4 + site - 0x0750, bytes([0x3F]) + helper_at.to_bytes(2, 'little'), bytes.fromhex('65 EB 28'))
        write(SONG_STORE_HELPER, song_store_helper(), empty=True)
        write(SONG_TEST_HELPER, song_test_helper(), empty=True)
        write(0x2BBF5A, bytes([0x20]) + (SONG_STORE_HELPER & 0xFFFF).to_bytes(2, 'little') + bytes([0xEA] * 4),
              bytes.fromhex('C9 32 B0 03 8D 8B 1D'))
        write(0x2BBFB4, bytes([0x20]) + (SONG_TEST_HELPER & 0xFFFF).to_bytes(2, 'little'), bytes.fromhex('C9 32 00'))
        write(RECORD_COUNT, bytes([len(records)]), empty=True)
        if not load_pump:
            for at, (payload, original) in nmi_range_code().items():
                write(at, payload, original, empty=original is None)
    if 0x28EC + len(table) > 0x3000:
        raise ValueError(f'song sample table too large: {len(table)} bytes')
    if not 0x2A5D <= heap_start(data) < 0x3000:
        raise ValueError('unexpected SPC heap start in IPL block')
    # 표가 원래 자리(28EC~2A5D)를 넘으면 샘플·시퀀스 자리 시작($28E7)을 표 끝으로 민다. 넘친 만큼 SPC 예산이 준다.
    write(HEAP_START, max(0x2A5D, 0x28EC + len(table)).to_bytes(2, 'little'))
    end = lorom(SONG_SETS) + old_size + 4
    if len(table) > old_size and any(data[end:end + len(table) - old_size]):
        raise ValueError('IPL expansion would overwrite nonzero ROM data')
    block_pos = lorom(IPL_BLOCK)
    block_size = int.from_bytes(data[block_pos:block_pos + 2], 'little')
    expected_size = lorom(SONG_SETS) + old_size - (block_pos + 4)
    if block_size != expected_size:
        raise ValueError('IPL block length does not end at song table boundary')
    write(IPL_BLOCK, (block_size + len(table) - old_size).to_bytes(2, 'little'))
    write(SONG_SETS, table + IPL_END + bytes(max(0, old_size - len(table))))
    blocks = []
    if fast_receive:
        blocks.append((FAST_RECEIVE, fast_receive_code()))
        write(DRIVER_BLOCK + 4 + DRIVER_RECEIVE - 0x0750, bytes([0x5F]) + FAST_RECEIVE.to_bytes(2, 'little'),
              bytes.fromhex('CD 00 E5'))
    if chains or hold:
        code = chain_code()
        blocks.append((CHAIN_HANDLER, code))
        write(DRIVER_BLOCK + 4 + CHAIN_TABLE_ENTRY - 0x0750, CHAIN_HANDLER.to_bytes(2, 'little'), bytes.fromhex('2D 19'))
    if hold:
        if not fast_receive:
            raise ValueError('hold needs fast_receive (its code reuses the replaced receive loop)')

        def driver(addr, payload, expected):
            write(DRIVER_BLOCK + 4 + addr - 0x0750, payload, bytes.fromhex(expected))

        spare_check, spare_end = hold_spare_code()
        driver(HOLD_SPARE, spare_check + spare_end, 'F5 00 C7 80 3A 80 1A 82 F0 E7 E5 F6 00 C7 80 3A 80 1A 82 F0 DC '
                                        'E5 F7 00 C7 80 3A 80 1A 82 D0 CC 2F')
        driver(HOLD_TICK_SITE, bytes([0x3F]) + _abs(HOLD_CHECK), 'F5 B7 03')
        driver(HOLD_INSTRUMENT_SITE, bytes([0x3F]) + _abs(HOLD_SPARE), '65 84 01')
        driver(HOLD_END_SITE, bytes([0x5F]) + _abs(HOLD_SPARE + len(spare_check)), '8F 00 8A')
        blocks.append((HOLD_VARS, bytes([0xFF, 0xFF, 0, 0, 0xFF])))
        blocks.append((HOLD_CHECK, hold_check_code()))
    if blocks:
        out = b''.join(len(c).to_bytes(2, 'little') + dest.to_bytes(2, 'little') + c for dest, c in blocks) + IPL_END
        at = lorom(SONG_SETS) + len(table)
        if any(data[max(at + 4, end):at + len(out)]):
            raise ValueError('SPC code blocks would overwrite nonzero ROM data')
        data[at:at + len(out)] = out
    for allocation, (song, item) in zip(allocations, sorted(replacements.items())):
        extra = (chain_numbers[song],) if song in chain_numbers else ()
        allocation['spc_budget'] = memory_budget(data, song, item, extra)
        if extra:
            allocation['chain_song'] = f'{extra[0]:02X}'
    if early_song:
        if map_fades:
            raise ValueError('early_song and map_fades both replace the map song calls')
        code, entry = early_song_code()
        write(EARLY_SONG, code, empty=True)
        write(EXIT_INDEX_STUB, bytes.fromhex('20 16 FC 6B'), empty=True)
        write(EARLY_SONG_SITE, bytes([0x22]) + entry.to_bytes(3, 'little'), bytes.fromhex('22 49 CE 00'))
        for at, original, site in ((EARLY_SONG_SKIP, 0x24FE91, MAP_CLEANUP), (EARLY_SONG_SKIP + 0x40, 0x24FE9A, MAP_START)):
            write(at, early_skip_code(original), empty=True)
            write(site, bytes([0x22]) + at.to_bytes(3, 'little'), bytes([0x22]) + original.to_bytes(3, 'little'))
    if load_pump:
        if not early_song:
            raise ValueError('load_pump needs early_song (the request must be queued before the map load)')
        for at, (payload, original) in load_pump_code().items():
            write(at, payload, original, empty=original is None)
    if keep_samples:
        if not load_pump:
            raise ValueError('keep_samples needs load_pump (its code is preempted through the NMI range stub)')
        done, mark = keep_samples_code()
        mark_at = KEEP_CODE + len(done)
        if (mark_at + len(mark)) & 0xFFFF > 0xEB00:
            raise ValueError('keep_samples code overflows 2B:EB00')
        write(KEEP_CODE, done + mark, empty=True)
        write(KEEP_DONE_SITE, bytes([0x4C]) + (KEEP_CODE & 0xFFFF).to_bytes(2, 'little'), bytes.fromhex('4C 84 C1'))
        write(KEEP_MARK_SITE, bytes([0x20]) + (mark_at & 0xFFFF).to_bytes(2, 'little') + bytes([0xEA] * 6),
              bytes.fromhex('20 2F C3 A9 0A 00 20 12 C1'))
    if vehicle_song:
        write(VEHICLE_SONG, vehicle_song_code(), empty=True)
        write(VEHICLE_SONG_SITE, bytes([0x22]) + VEHICLE_SONG.to_bytes(3, 'little') + bytes([0xEA] * 7),
              bytes.fromhex('22 91 FE 24 AD 4B 19 22 9A FE 24'))
    if map_fades:
        cleanup, start = transition_code()
        write(CODE, cleanup, empty=True)
        write(CODE + 0x80, start, empty=True)
        write(MAP_CLEANUP, bytes.fromhex('22 00 80 71'), bytes.fromhex('22 91 FE 24'))
        write(MAP_START, bytes.fromhex('22 80 80 71'), bytes.fromhex('22 9A FE 24'))
    if preview is not None:
        if preview not in replacements:
            raise ValueError('preview song must be one of the replacements')
        write_preview(data, preview)
    data[0x7FD7] = 0x0C
    result = set_checksum(bytes(data))
    return result, {'kind': 'dq4_sound_port', 'base_sha1': hashlib.sha1(base).hexdigest(),
                    'rom_sha1': hashlib.sha1(result).hexdigest(), 'songs': allocations,
                    'sample_table_bytes': len(table), 'sample_table_capacity': TABLE_CAPACITY,
                    'heap_start': f'{heap_start(result):04X}',
                    'sound_bank_bytes_left': {f'{bank:02X}': 0x10000 - at for bank, at in free.items() if at > 0x8000},
                    'unpinned_sequences': [f'{x:02X}' for x in unpinned],
                    'pinned_sequences': [f'{x:02X}' for x in pinned_sequences(result)],
                    'resident_samples': [f'{x:02X}' for x in resident_samples(result)],
                    'map_fades': map_fades, 'preview': preview, 'fast_receive': fast_receive, 'hold': hold, 'early_song': early_song, 'load_pump': load_pump,
                    'chains': {f'{k:02X}': f'{v:02X}' for k, v in sorted(chain_numbers.items())},
                    'song_records': len(read_sets(result)),
                    'chains_sent_after_samples': [f'{k:02X}' for k in sorted(chain_late)],
                    'limitations': ['Map fades apply only to the ordinary DQ5 map-song calls; battle and event timing is unchanged.',
                                    'The early fade-out is skipped when the sound queue is busy at load time; the original 1A cleanup still runs.',
                                    'SPC budget is a conservative static check, not a runtime allocation proof.',
                                    'Preview changes title music for audition only; it is not the production title.']}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--base', required=True)
    ap.add_argument('--replace', action='append', required=True, metavar='HEX_SLOT=SCORE_JSON')
    ap.add_argument('--out', required=True)
    ap.add_argument('--map-fades', action='store_true')
    ap.add_argument('--bank', help='dq4soundbank output directory containing program-map.json and sample .bin files')
    ap.add_argument('--preview', type=lambda x: int(x, 16))
    args = ap.parse_args()
    from dq4soundport import convert
    replacements, conversions = {}, {}
    resources, program_map = {}, None
    if args.bank:
        bank = Path(args.bank)
        program_map = {int(k): v for k, v in json.loads((bank / 'program-map.json').read_text()).items()}
        for resource in bank.glob('*.bin'):
            resources[int(resource.stem, 16)] = resource.read_bytes()
    for value in args.replace:
        key, path = value.split('=', 1)
        song = int(key, 16)
        if song in replacements:
            ap.error(f'duplicate slot {song:02X}')
        conversion = convert(json.loads(Path(path).read_text()), program_map=program_map)
        replacements[song] = Replacement(conversion.sequence, tuple(conversion.samples))
        conversions[f'{song:02X}'] = conversion.report
    base = Path(args.base).read_bytes()
    result, report = install(base, replacements, sample_resources=resources, map_fades=args.map_fades, preview=args.preview)
    from dq5build import make_ips
    from kr_patch import ips
    patch = make_ips(base, result)
    if ips.apply(base, patch) != result:
        raise ValueError('IPS round trip mismatch')
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(result)
    out.with_suffix('.ips').write_bytes(patch)
    report['conversions'] = conversions
    out.with_suffix('.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: v for k, v in report.items() if k != 'conversions'}, indent=2))


if __name__ == '__main__':
    main()
