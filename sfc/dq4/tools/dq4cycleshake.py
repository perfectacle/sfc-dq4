"""시험용 롬 사본의 NMI 에 사이클을 더한다(배포 롬에는 쓰지 않음).

DQ5 난수(00:9878)는 075B·075C 를 밀어 섞는데, NMI(00:8897)가 그 도중에 075B 를 하나 올리면 결과가 바뀐다. 그래서 매 프레임
도는 코드의 사이클 수만 달라져도(다른 PR 이 소리·창 코드를 고침) 난수를 시작에 한 번만 둔 전투 장면은 다른 갈래로 간다.
이 도구는 NMI 첫머리 `INC $075B / INC $0993` 를 빈 뱅크 끝의 받침으로 돌려 NOP 를 nops 개 더한 사본을 만든다. 난수를
묶은 장면은 이 사본에서도 같은 결과가 나와야 한다.

  python sfc/dq4/tools/dq4cycleshake.py --rom work/ch3/dq4-ch1-full.sfc --out work/shake/ch3-40.sfc --nops 40
"""
import argparse
from pathlib import Path

NMI_AT = 0x0897                                   # 00:8897(LoROM 파일 위치)
NMI_BYTES = bytes.fromhex('EE5B07EE9309')         # INC $075B / INC $0993
NMI_BACK = 0x00889D                               # 그다음 INC $0994
BANK = 0x8000
STUB_ROOM = 0x200                                 # 받침이 쓸 뱅크 끝의 빈 바이트(00) 수
LAST_BANK = 0x7D                                  # 7E·7F 는 00~7F 쪽에서 WRAM 이다


def stub_bank(data, need):
    """끝에서 STUB_ROOM 바이트 이상이 00 인 마지막 뱅크와 받침을 둘 파일 위치."""
    for bank in range(min(LAST_BANK, len(data) // BANK - 1), 0, -1):
        seg = data[bank * BANK:(bank + 1) * BANK]
        if len(seg) - len(seg.rstrip(b'\x00')) >= max(STUB_ROOM, need + 0x10):
            return bank, (bank + 1) * BANK - max(STUB_ROOM, need + 0x10)
    raise ValueError('받침을 둘 빈 뱅크 끝이 없다')


def shake(data, nops):
    """NOP 를 nops 개 더한 롬 바이트. NMI 첫머리가 예상한 바이트가 아니면 ValueError."""
    if data[NMI_AT:NMI_AT + len(NMI_BYTES)] != NMI_BYTES:
        raise ValueError(f'00:8897 이 {data[NMI_AT:NMI_AT + 6].hex()} 이다(예상 {NMI_BYTES.hex()})')
    stub = b'\xEA' * nops + NMI_BYTES + b'\x5C' + NMI_BACK.to_bytes(3, 'little')
    bank, at = stub_bank(data, len(stub))
    addr = (bank << 16) | (0x8000 + at % BANK)
    out = bytearray(data)
    out[at:at + len(stub)] = stub
    out[NMI_AT:NMI_AT + len(NMI_BYTES)] = b'\x5C' + addr.to_bytes(3, 'little') + b'\xEA\xEA'
    return bytes(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--rom', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--nops', type=int, required=True)
    a = ap.parse_args()
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_bytes(shake(Path(a.rom).read_bytes(), a.nops))
    print(a.out)


if __name__ == '__main__':
    main()
