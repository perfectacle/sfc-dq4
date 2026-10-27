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
                   RESIDENT_SEQUENCES, ff_list, samples, sequences)

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


@dataclass(frozen=True)
class Replacement:
    sequence: bytes
    samples: tuple[int, ...]
    send_first: int | None = None  # 곡을 틀기 전에 보낼 앞쪽 샘플 수 k. None 이면 모두


def read_sets(data):
    pos, records = lorom(SONG_SETS), []
    for _ in range(SEQUENCE_COUNT):
        size = data[pos] + 2
        records.append(bytes(data[pos:pos + size]))
        pos += size
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


def sample_budget(data, song, sequence_size, extra_table=0):
    """곡 하나가 새 샘플에 쓸 수 있는 SPC 바이트. 늘 두는 샘플·시퀀스와 이 곡 시퀀스, 여유 512를 뺀다.

    extra_table 은 곡 묶음 표가 지금보다 늘어날 바이트로, 그만큼 샘플 자리 시작이 뒤로 밀린다.
    """
    rom = Rom(data)
    resident_samples = sum(sample_size(data, i) for i in set(ff_list(rom, RESIDENT_SAMPLES)))
    resident_sequences = sum(len(sequence_bytes(data, i)) for i in set(ff_list(rom, RESIDENT_SEQUENCES)) if i != song)
    capacity = SPC_END - max(heap_start(data), 0x28EC + sum(map(len, read_sets(data))) + extra_table)
    return capacity - resident_samples - resident_sequences - sequence_size - 512


def memory_budget(data, song, item):
    rom = Rom(data)
    resident_samples = set(ff_list(rom, RESIDENT_SAMPLES))
    resident_sequences = set(ff_list(rom, RESIDENT_SEQUENCES))
    used_samples = resident_samples | set(item.samples)
    used_sequences = resident_sequences | {song}
    sample_bytes = sum(sample_size(data, i) for i in used_samples)
    sequence_size = sum(len(sequence_bytes(data, i)) for i in used_sequences)
    # 슬롯 관리·정렬과 잔향 버퍼 사이에 여유를 둔다. 전환은 이전 곡 자료를 정리한 뒤 로드한다.
    required = sample_bytes + sequence_size + 512
    capacity = SPC_END - heap_start(data)
    if len(used_samples) > 20 or len(used_sequences) > 20 or required > capacity:
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


def install(base, replacements, *, sample_resources=None, map_fades=False, preview=None):
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
    records = read_sets(data)
    old_size = sum(map(len, records))
    unpinned = unpin_sequences(data, set(replacements))
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

    for song, item in sorted(replacements.items()):
        if not 0 <= song < SEQUENCE_COUNT or song == 0x10:
            raise ValueError('target song must be 00..46 except the protected title 10')
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
    table = b''.join(records)
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
    for allocation, (song, item) in zip(allocations, sorted(replacements.items())):
        allocation['spc_budget'] = memory_budget(data, song, item)
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
                    'map_fades': map_fades, 'preview': preview,
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
