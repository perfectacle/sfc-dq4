"""SPC700 디스어셈블러. SPC RAM 덤프(64KB, 커밋 금지)의 드라이버 코드를 읽는 데 쓴다.

    uv run --locked python sfc/dq5/tools/spc700.py work/spc/spc00550.bin 0800 40
"""

from __future__ import annotations

import argparse
from pathlib import Path

# 피연산자 자리표: {d}=첫 바이트 직접 주소, {e}=둘째 바이트, {i}=첫 바이트 즉치, {w}=두 바이트 주소,
# {r}=끝 바이트 상대 분기, {m}=13비트 주소.비트, {u}=PCALL. 바이트 수는 표의 둘째 값.
_ALU = ["OR", "AND", "EOR", "CMP", "ADC", "SBC"]


def _table() -> list[tuple[str, int]]:
    t: list[tuple[str, int]] = [("?", 1)] * 256
    for n, op in enumerate(_ALU):
        hi = n * 0x20
        t[hi + 0x04] = (f"{op} A,${{d}}", 2)
        t[hi + 0x05] = (f"{op} A,${{w}}", 3)
        t[hi + 0x06] = (f"{op} A,(X)", 1)
        t[hi + 0x07] = (f"{op} A,[${{d}}+X]", 2)
        t[hi + 0x08] = (f"{op} A,#${{i}}", 2)
        t[hi + 0x09] = (f"{op} ${{e}},${{d}}", 3)
        t[hi + 0x14] = (f"{op} A,${{d}}+X", 2)
        t[hi + 0x15] = (f"{op} A,${{w}}+X", 3)
        t[hi + 0x16] = (f"{op} A,${{w}}+Y", 3)
        t[hi + 0x17] = (f"{op} A,[${{d}}]+Y", 2)
        t[hi + 0x18] = (f"{op} ${{e}},#${{i}}", 3)
        t[hi + 0x19] = (f"{op} (X),(Y)", 1)
    for n in range(16):
        t[n * 0x10 + 1] = (f"TCALL {n}", 1)
        bit = n >> 1
        if n % 2 == 0:
            t[n * 0x10 + 2] = (f"SET1 ${{d}}.{bit}", 2)
            t[n * 0x10 + 3] = (f"BBS ${{d}}.{bit},{{r}}", 3)
        else:
            t[n * 0x10 + 2] = (f"CLR1 ${{d}}.{bit}", 2)
            t[n * 0x10 + 3] = (f"BBC ${{d}}.{bit},{{r}}", 3)
    for code, br in zip(range(0x10, 0x100, 0x20), ["BPL", "BMI", "BVC", "BVS", "BCC", "BCS", "BNE", "BEQ"]):
        t[code] = (f"{br} {{r}}", 2)
    rest = {
        0x00: ("NOP", 1), 0x0A: ("OR1 C,{m}", 3), 0x0B: ("ASL ${d}", 2), 0x0C: ("ASL ${w}", 3),
        0x0D: ("PUSH PSW", 1), 0x0E: ("TSET1 ${w}", 3), 0x0F: ("BRK", 1),
        0x1A: ("DECW ${d}", 2), 0x1B: ("ASL ${d}+X", 2), 0x1C: ("ASL A", 1), 0x1D: ("DEC X", 1),
        0x1E: ("CMP X,${w}", 3), 0x1F: ("JMP [${w}+X]", 3),
        0x20: ("CLRP", 1), 0x2A: ("OR1 C,/{m}", 3), 0x2B: ("ROL ${d}", 2), 0x2C: ("ROL ${w}", 3),
        0x2D: ("PUSH A", 1), 0x2E: ("CBNE ${d},{r}", 3), 0x2F: ("BRA {r}", 2),
        0x3A: ("INCW ${d}", 2), 0x3B: ("ROL ${d}+X", 2), 0x3C: ("ROL A", 1), 0x3D: ("INC X", 1),
        0x3E: ("CMP X,${d}", 2), 0x3F: ("CALL ${w}", 3),
        0x40: ("SETP", 1), 0x4A: ("AND1 C,{m}", 3), 0x4B: ("LSR ${d}", 2), 0x4C: ("LSR ${w}", 3),
        0x4D: ("PUSH X", 1), 0x4E: ("TCLR1 ${w}", 3), 0x4F: ("PCALL ${u}", 2),
        0x5A: ("CMPW YA,${d}", 2), 0x5B: ("LSR ${d}+X", 2), 0x5C: ("LSR A", 1), 0x5D: ("MOV X,A", 1),
        0x5E: ("CMP Y,${w}", 3), 0x5F: ("JMP ${w}", 3),
        0x60: ("CLRC", 1), 0x6A: ("AND1 C,/{m}", 3), 0x6B: ("ROR ${d}", 2), 0x6C: ("ROR ${w}", 3),
        0x6D: ("PUSH Y", 1), 0x6E: ("DBNZ ${d},{r}", 3), 0x6F: ("RET", 1),
        0x7A: ("ADDW YA,${d}", 2), 0x7B: ("ROR ${d}+X", 2), 0x7C: ("ROR A", 1), 0x7D: ("MOV A,X", 1),
        0x7E: ("CMP Y,${d}", 2), 0x7F: ("RETI", 1),
        0x80: ("SETC", 1), 0x8A: ("EOR1 C,{m}", 3), 0x8B: ("DEC ${d}", 2), 0x8C: ("DEC ${w}", 3),
        0x8D: ("MOV Y,#${i}", 2), 0x8E: ("POP PSW", 1), 0x8F: ("MOV ${e},#${i}", 3),
        0x9A: ("SUBW YA,${d}", 2), 0x9B: ("DEC ${d}+X", 2), 0x9C: ("DEC A", 1), 0x9D: ("MOV X,SP", 1),
        0x9E: ("DIV YA,X", 1), 0x9F: ("XCN A", 1),
        0xA0: ("EI", 1), 0xAA: ("MOV1 C,{m}", 3), 0xAB: ("INC ${d}", 2), 0xAC: ("INC ${w}", 3),
        0xAD: ("CMP Y,#${i}", 2), 0xAE: ("POP A", 1), 0xAF: ("MOV (X)+,A", 1),
        0xBA: ("MOVW YA,${d}", 2), 0xBB: ("INC ${d}+X", 2), 0xBC: ("INC A", 1), 0xBD: ("MOV SP,X", 1),
        0xBE: ("DAS A", 1), 0xBF: ("MOV A,(X)+", 1),
        0xC0: ("DI", 1), 0xC4: ("MOV ${d},A", 2), 0xC5: ("MOV ${w},A", 3), 0xC6: ("MOV (X),A", 1),
        0xC7: ("MOV [${d}+X],A", 2), 0xC8: ("CMP X,#${i}", 2), 0xC9: ("MOV ${w},X", 3),
        0xCA: ("MOV1 {m},C", 3), 0xCB: ("MOV ${d},Y", 2), 0xCC: ("MOV ${w},Y", 3), 0xCD: ("MOV X,#${i}", 2),
        0xCE: ("POP X", 1), 0xCF: ("MUL YA", 1),
        0xD4: ("MOV ${d}+X,A", 2), 0xD5: ("MOV ${w}+X,A", 3), 0xD6: ("MOV ${w}+Y,A", 3),
        0xD7: ("MOV [${d}]+Y,A", 2), 0xD8: ("MOV ${d},X", 2), 0xD9: ("MOV ${d}+Y,X", 2),
        0xDA: ("MOVW ${d},YA", 2), 0xDB: ("MOV ${d}+X,Y", 2), 0xDC: ("DEC Y", 1), 0xDD: ("MOV A,Y", 1),
        0xDE: ("CBNE ${d}+X,{r}", 3), 0xDF: ("DAA A", 1),
        0xE0: ("CLRV", 1), 0xE4: ("MOV A,${d}", 2), 0xE5: ("MOV A,${w}", 3), 0xE6: ("MOV A,(X)", 1),
        0xE7: ("MOV A,[${d}+X]", 2), 0xE8: ("MOV A,#${i}", 2), 0xE9: ("MOV X,${w}", 3),
        0xEA: ("NOT1 {m}", 3), 0xEB: ("MOV Y,${d}", 2), 0xEC: ("MOV Y,${w}", 3), 0xED: ("NOTC", 1),
        0xEE: ("POP Y", 1), 0xEF: ("SLEEP", 1),
        0xF4: ("MOV A,${d}+X", 2), 0xF5: ("MOV A,${w}+X", 3), 0xF6: ("MOV A,${w}+Y", 3),
        0xF7: ("MOV A,[${d}]+Y", 2), 0xF8: ("MOV X,${d}", 2), 0xF9: ("MOV X,${d}+Y", 2),
        0xFA: ("MOV ${e},${d}", 3), 0xFB: ("MOV Y,${d}+X", 2), 0xFC: ("INC Y", 1), 0xFD: ("MOV Y,A", 1),
        0xFE: ("DBNZ Y,{r}", 2), 0xFF: ("STOP", 1),
    }
    for k, v in rest.items():
        t[k] = v
    return t


TABLE = _table()


def decode(mem: bytes, pc: int) -> tuple[int, str]:
    """pc 의 명령 하나를 풀어 (길이, 글) 로 돌려준다."""
    fmt, size = TABLE[mem[pc]]
    b = [mem[(pc + k) & 0xFFFF] for k in range(size)]
    b1 = b[1] if size > 1 else 0
    b2 = b[2] if size > 2 else 0
    w = b1 | b2 << 8
    rel = b[-1] - 256 if b[-1] >= 128 else b[-1]
    text = fmt.format(
        d=f"{b1:02X}", e=f"{b2:02X}", i=f"{b1:02X}", w=f"{w:04X}", u=f"FF{b1:02X}",
        r=f"${(pc + size + rel) & 0xFFFF:04X}", m=f"${w & 0x1FFF:04X}.{w >> 13}",
    )
    return size, text


def listing(mem: bytes, start: int, count: int) -> list[str]:
    out, pc = [], start
    for _ in range(count):
        size, text = decode(mem, pc)
        raw = " ".join(f"{mem[(pc + k) & 0xFFFF]:02x}" for k in range(size))
        out.append(f"{pc:04X}  {raw:<9} {text}")
        pc = (pc + size) & 0xFFFF
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("dump", type=Path)
    ap.add_argument("start", type=lambda s: int(s, 16))
    ap.add_argument("count", type=int, nargs="?", default=32)
    a = ap.parse_args()
    print("\n".join(listing(a.dump.read_bytes(), a.start, a.count)))


if __name__ == "__main__":
    main()
