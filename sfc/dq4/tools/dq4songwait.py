"""곡이 끝나기를 기다리는 자리와 그 자리의 곡이 되풀이하지 않는지(롬 바이트만, 에뮬레이터 없음).

DQ5 의 `24:FF0F` 는 명령 `09 n`(곡 n 이 아직 울리는지)을 보내고 대답 `7E:08D2` 가 `7F` 가 될 때까지 돈다.
`25:FD00` 은 `1A`·`01 n` 뒤 대기열을 비우고 `24:FF0F` 로 기다린 다음 맵 곡으로 돌아간다. 그래서 되풀이하는 곡을
이 자리에 두면 게임이 그 자리에서 멈춘다(교회 치료 뒤 「…주소서!」). 형식은
sfc/dq4/docs/dq4-sound-port-format.md 「곡 끝을 기다리는 자리」.

  uv run --locked python sfc/dq4/tools/dq4songwait.py --rom work/ch1/dq4-ch1-full.sfc

곡이 되풀이하는지는 롬의 시퀀스(뱅크 70 재배치 표, 없으면 원래 시퀀스 묶음)를 트랙마다 따라가 본다. 판정:
  - 즉값(또는 표)으로 곡을 주는 자리는 그 곡이 끝나야 한다(효과음도)
  - 곡 번호가 즉값이 아닌 자리(INDIRECT)는 24:FF0F 의 반복 곡 가드(dq4soundpatch.wait_guard_code)가 있고 가드의
    표가 롬 시퀀스와 맞아야 한다. 가드는 되풀이하는 곡이면 기다리지 않고 돌아오므로 어떤 곡이 와도 멈추지 않는다
  - 입구를 부르는 바이트(JSR·JMP·JSL·JML)는 모두 어느 자리로 분류되어야 한다
"""
import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[1] / 'dq5' / 'tools')]

WAIT = 0x24FF0F
JINGLE = 0x25FD00
# 같은 뱅크 안에서 LDA #n / JSR 로 부르는 기다림 루틴과 그 첫 바이트(JSL 24:FE9A / JSL 24:FF0F)
LOCAL = {0x23E53A: bytes.fromhex('22 9A FE 24 22 0F FF 24')}
# 곡 번호를 표에서 읽는 기다림: 슬롯이 맞았을 때 받은 코인으로 고르는 곡(23:FEEC LDA $FF0A,X … 23:FEFC JSL FF0F)
TABLES = {0x23FEFC: (0x23FEEC, bytes.fromhex('BD 0A FF'), 0x23FF0A, 4)}
# 곡 번호가 즉값이 아닌 DQ5 자리(코드 읽기). 가드가 있어야 통과한다
INDIRECT = {
    0x02D286: 'JSL 00:E9CE(레지스터를 지킴) / BRK 08 뒤라 A 는 앞 고리의 02:D295 결과. 그 앞에서 BRK 19 24 를 냄',
    0x038EA8: 'LDA #$0001 / JSL 03:A518(팔레트 페이드, A 를 바꿈) 뒤',
    0x12F354: 'LDA $1E73 / CMP #$054C 가 같은 갈래라 A 낮은 바이트는 4C 로 보임(BRK 0B·19·9C 가 A 를 지키는지 미확인)',
}
SONG_LIMIT = 0x64
# 원본 DQ5 의 기다림 자리(부르는 바이트 자리 → (곡, 곡을 주는 LDA 자리), 곡 None 은 INDIRECT). 원본 롬 훑기와 같은지 불변식이 본다.
# 포팅이 기다리는 곡은 여기에 dq4sound-game.args 의 --song-call 을 더한 것과 PORT_SONGS(단위 테스트가 대응표와 견줌)
DQ5_SITES = {
    0x02B7B0: (0x1C, 0x02B7AE), 0x02D286: (None, None), 0x038EA8: (None, None), 0x03BB57: (0x35, 0x03BB55),
    0x03BDD5: (0x2E, 0x03BDD3), 0x03FC42: (0x1D, 0x03FC40), 0x03FD5E: (0x1E, 0x03FD5C), 0x03FD84: (0x1E, 0x03FD82),
    0x03FDA9: (0x1E, 0x03FDA7), 0x05DE06: (0x23, 0x05DE04), 0x05F015: (0x1C, 0x05F013), 0x05F2D6: (0x1D, 0x05F2D4),
    0x05F3B8: (0x34, 0x05F3B6), 0x05F3F7: (0x1D, 0x05F3F5), 0x05F640: (0x1D, 0x05F63E), 0x05F8E3: (0x1D, 0x05F8E1),
    0x05F94D: (0x41, 0x05F94B), 0x05FA43: (0x1D, 0x05FA41), 0x05FAC3: (0x1E, 0x05FAC1), 0x05FBFA: (0x1D, 0x05FBF8),
    0x05FD31: (0x1D, 0x05FD2F), 0x06B491: (0x1C, 0x06B48F), 0x06B64E: (0x22, 0x06B64C), 0x06B682: (0x22, 0x06B680),
    0x06B8D4: (0x22, 0x06B8D2), 0x06BC53: (0x22, 0x06BC51), 0x06BE88: (0x1D, 0x06BE86), 0x06BFC7: (0x1D, 0x06BFC5),
    0x06C0BE: (0x3F, 0x06C0BC), 0x06C208: (0x1D, 0x06C206), 0x06C2AE: (0x1D, 0x06C2AC), 0x06C49B: (0x1D, 0x06C499),
    0x06C74E: (0x1D, 0x06C74C), 0x06C78C: (0x1D, 0x06C78A), 0x06C97A: (0x23, 0x06C978), 0x06CA3C: (0x22, 0x06CA3A),
    0x06CB17: (0x1D, 0x06CB15), 0x06CEA8: (0x1D, 0x06CEA6), 0x06CFD4: (0x1C, 0x06CFD2), 0x06D2E5: (0x1D, 0x06D2E3),
    0x06E110: (0x20, 0x06E10E), 0x06E17E: (0x1E, 0x06E17C), 0x06E29C: (0x1E, 0x06E29A), 0x06E30A: (0x1E, 0x06E308),
    0x06E424: (0x1D, 0x06E422), 0x06F757: (0x1D, 0x06F755), 0x06F79F: (0x24, 0x06F79D), 0x06F803: (0x22, 0x06F801),
    0x06F8ED: (0x1D, 0x06F8EB), 0x06F978: (0x1D, 0x06F976), 0x06FA9E: (0x1D, 0x06FA9C), 0x06FAFE: (0x1D, 0x06FAFC),
    0x06FC4A: (0x23, 0x06FC48), 0x06FC55: (0x23, 0x06FC53), 0x06FC62: (0x23, 0x06FC60), 0x06FD1C: (0x37, 0x06FD1A),
    0x06FD36: (0x38, 0x06FD34), 0x0FD936: (0x42, 0x0FD934), 0x0FFC42: (0x35, 0x0FFC40), 0x118BE0: (0x29, 0x118BDE),
    0x118DD6: (0x2B, 0x118DD4), 0x11B4F1: (0x3B, 0x11B4EF), 0x12EA59: (0x24, 0x25FCFE), 0x12F354: (None, None),
    0x12F3FF: (0x24, 0x12F3FD), 0x12F527: (0x22, 0x25FCF8), 0x12F5B0: (0x2E, 0x25FCF2), 0x12F646: (0x2E, 0x25FCF2),
    0x12F6B6: (0x2E, 0x25FCF2), 0x12F6E9: (0x24, 0x25FCFE), 0x12F6F2: (0x22, 0x25FCF8), 0x1EE12C: (0x24, 0x1EE12A),
    0x2080F2: (0x1F, 0x2080F0), 0x20BFBA: (0x29, 0x20BFB8), 0x20BFD3: (0x2B, 0x20BFD1), 0x23E4F2: (0x2D, 0x23E4F0),
    0x23E52C: (0x25, 0x23E52A), 0x23E534: (0x27, 0x23E532), 0x24847C: (0x33, 0x24847A), 0x258B26: (0x21, 0x258B24),
    0x25FF26: (0x1D, 0x25FF24), 0x25FF88: (0x1D, 0x25FF86), 0x2980F8: (0x1E, 0x2980F6),
}
# 포팅 코드가 기다리는 곡: 여관 징글(dq4soundpatch.INN_SONG), 레벨 업(dq4ch1event.LEVEL_SONG), 합류(JOIN_SONG)
PORT_SONGS = {0x1D: '여관 징글', 0x21: '1장 필드 레벨 업', 0x26: '1장 합류 팡파르'}


def offset(addr):
    return (addr >> 16) * 0x8000 + (addr & 0x7FFF)


def cpu(off):
    return (off // 0x8000) << 16 | 0x8000 | off % 0x8000


def fmt(addr):
    return f'{addr >> 16:02X}:{addr & 0xFFFF:04X}'


def _far(addr):
    return bytes((addr & 0xFF, addr >> 8 & 0xFF, addr >> 16))


def inn_wait_entry():
    """여관 징글 기다림 코드(dq4soundpatch.inn_jingle_code 의 둘째)의 (첫 주소, 끝). 06:E422 LDA #1D 뒤 JSL 로 불린다."""
    import dq4soundpatch as patch
    fade, wait = patch.inn_jingle_code()
    start = patch.INN_JINGLE + len(fade)
    return start, start + len(wait)


def guard_span():
    import dq4soundpatch as patch
    return patch.WAIT_GUARD, patch.WAIT_GUARD + len(patch.wait_guard_code())


def wrappers(rom):
    """뱅크 25 의 `(SEP #20 /) LDA #n / BRA 25:FD00` 꼴과 25:FD00 바로 앞에서 흘러드는 `LDA #n`:
    {입구: (곡, LDA 자리)}. 곡 번호는 롬 바이트에서 읽는다."""
    out, lo = {}, offset(0x258000)
    i = offset(JINGLE) - 2
    if rom[i] == 0xA9:
        entry = cpu(i - 2) if rom[i - 2:i] == b'\xE2\x20' else cpu(i)
        out[entry] = (rom[i + 1], cpu(i))
    for i in range(lo, lo + 0x8000 - 3):
        if rom[i] == 0xA9 and rom[i + 2] == 0x80:
            target = cpu(i + 4) + (rom[i + 3] - 0x100 if rom[i + 3] & 0x80 else rom[i + 3])
            if target == JINGLE:
                entry = cpu(i - 2) if rom[i - 2:i] == b'\xE2\x20' else cpu(i)
                out[entry] = (rom[i + 1], cpu(i))
    return out


def call_hits(rom, entry):
    """입구를 부르는 바이트 자리 [(자리, 명령)]: 어디서나 JSL·JML(22·5C + 긴 주소), 같은 뱅크 안의 JSR·JMP(20·4C)."""
    hits = []
    for op in (0x22, 0x5C):
        pat = bytes([op]) + _far(entry)
        i = rom.find(pat)
        while i >= 0:
            hits.append((cpu(i), op))
            i = rom.find(pat, i + 1)
    lo = offset(entry & 0xFF0000 | 0x8000)
    for op in (0x20, 0x4C):
        pat = bytes((op, entry & 0xFF, entry >> 8 & 0xFF))
        i = rom.find(pat, lo, lo + 0x8000)
        while i >= 0:
            hits.append((cpu(i), op))
            i = rom.find(pat, i + 1, lo + 0x8000)
    return sorted(hits)


def sites(rom, port=True):
    """([(자리, 곡 또는 None, 입구, 곡을 주는 LDA 자리)], [분류하지 못한 부르기]). port 면 포팅이 넣은 입구(여관 기다림)와
    가드 몸통도 본다."""
    entries, bodies = [WAIT, JINGLE], [(JINGLE, JINGLE + 0x19)]
    if port:
        inn = inn_wait_entry()
        entries.append(inn[0])
        bodies += [inn, guard_span()]
    wraps = wrappers(rom)
    bodies += [(entry, lda + 4) for entry, (_, lda) in wraps.items()]
    bodies += [(entry, entry + len(body)) for entry, body in LOCAL.items()]
    out, loose, hits = [], [], 0
    for entry in entries + list(wraps) + list(LOCAL):
        for at, op in call_hits(rom, entry):
            hits += 1
            if any(s <= at < e for s, e in bodies):
                out.append((at, None, 'body', None))
                continue
            o = offset(at)
            if entry in wraps:
                out.append((at, wraps[entry][0], entry, wraps[entry][1]))
            elif rom[o - 2] == 0xA9:
                out.append((at, rom[o - 1], entry, at - 2))
            elif at in TABLES:
                code, want, table, n = TABLES[at]
                if bytes(rom[offset(code):offset(code) + len(want)]) != want:
                    loose.append(f'{fmt(at)}: 표 읽기 {fmt(code)} 의 바이트가 다름')
                songs = sorted(set(rom[offset(table):offset(table) + n]))
                out += [(at, song, table, None) for song in songs[:1]]
                out += [(at, song, 'table+', None) for song in songs[1:]]
            else:
                out.append((at, None, entry, None))
                if at not in INDIRECT:
                    loose.append(f'{fmt(at)}: {op:02X} {fmt(entry)} 앞에 곡 번호 즉값이 없음(dq4songwait.INDIRECT 에 근거를 적을 것)')
    for entry, body in LOCAL.items():
        if bytes(rom[offset(entry):offset(entry) + len(body)]) != body:
            loose.append(f'{fmt(entry)}: 기다림 루틴 바이트가 다름')
    calls = sum(1 for r in out if r[2] != 'table+')
    if calls != hits:
        loose.append(f'입구를 부르는 바이트 {hits}개 가운데 {calls}개만 분류됨')
    out = [r for r in out if r[2] != 'body']
    return sorted(out, key=lambda r: (r[0], -1 if r[1] is None else r[1])), loose


def _chain_pairs(rom):
    import dq4soundpatch as patch
    o = offset(patch.CHAIN_PAIRS)
    return bytes(rom[o:o + SONG_LIMIT]) if len(rom) >= o + SONG_LIMIT else bytes(SONG_LIMIT)


def _has_chain_handler(rom):
    import dq4soundpatch as patch
    o = offset(patch.DRIVER_BLOCK) + 4 + patch.CHAIN_TABLE_ENTRY - 0x0750
    return bytes(rom[o:o + 2]) == patch.CHAIN_HANDLER.to_bytes(2, 'little')


def sequence(rom, n):
    """시퀀스 n 의 바이트(재배치 표 70:8100 의 [길이 2][자료], 0 이면 원래 묶음 2E:E2E4). 없으면 b''."""
    from dq5map import Rom
    from dq5song import RELOC_SEQ_TABLE
    from dq5spc import SEQUENCE_COUNT, body, sequences
    t = offset(RELOC_SEQ_TABLE) + n * 3
    ptr = int.from_bytes(rom[t:t + 3], 'little') if len(rom) >= t + 3 else 0
    if ptr:
        pos = offset(ptr)
        return bytes(rom[pos + 2:pos + 2 + int.from_bytes(rom[pos:pos + 2], 'little')])
    if n >= SEQUENCE_COUNT:
        return b''
    r = Rom(bytes(rom))
    _, a, ln = sequences(r)[n]
    return body(r, a, ln)


def seq_loops(seq, f7_args=0):
    """트랙 가운데 끝(FF)에 닿지 않고 무조건 점프(EA)로 되도는 것이 있으면 True. 조건 갈래(if_flag E0, 횟수 F5)는
    지나간다고 본다. f7_args 는 F7 의 인자 수(나눈 곡 처리기가 있으면 2, DQ5 는 0)."""
    from dq5song import header, step
    if len(seq) < 2:
        return False
    for pc in header(seq)[1]:
        stack, seen = (), set()
        while (pc, stack) not in seen:
            seen.add((pc, stack))
            if not 0 <= pc < len(seq):
                break
            if seq[pc] == 0xF7:
                pc += 1 + f7_args
                continue
            nxt, _, target, flow = step(seq, pc)
            if flow == 'end':
                break
            if seq[pc] == 0xF8:
                stack, pc = stack + (nxt,), target
            elif flow == 'ret':
                pc, stack = (stack[-1], stack[:-1]) if stack else (nxt, stack)
            elif flow == 'jump':
                pc = target
            else:
                pc = nxt
        else:
            return True
    return False


def loop_table(rom):
    """곡 번호 0~63 마다 되풀이하면 1. 나눈 곡의 앞부분(본체가 오기를 기다리며 되돎)도 1."""
    pairs, f7 = _chain_pairs(rom), 2 if _has_chain_handler(rom) else 0
    return bytes(int(bool(pairs[n]) or seq_loops(sequence(rom, n), f7)) for n in range(SONG_LIMIT))


def guard_problems(rom):
    """24:FF0F 의 반복 곡 가드가 있고 그 표가 롬 시퀀스와 같은지. 문제 목록."""
    import dq4soundpatch as patch
    o = offset(WAIT)
    if bytes(rom[o:o + 4]) != bytes([0x5C]) + _far(patch.WAIT_GUARD):
        return ['24:FF0F 에 반복 곡 가드가 없음(dq4soundset --wait-guard)']
    g, code = offset(patch.WAIT_GUARD), patch.wait_guard_code()
    if bytes(rom[g:g + len(code)]) != code:
        return ['반복 곡 가드 코드가 dq4soundpatch.wait_guard_code 와 다름']
    t = offset(patch.LOOP_TABLE)
    got, want = bytes(rom[t:t + SONG_LIMIT]), loop_table(rom)
    bad = [f'{n:02X}' for n in range(SONG_LIMIT) if got[n] != want[n]]
    return [f'가드 표가 롬 시퀀스와 다른 곡 {", ".join(bad)}'] if bad else []


def original_sites(dq5):
    found, _ = sites(dq5, port=False)
    return {at: (song, lda) for at, song, _, lda in found if at not in TABLES}


def check(rom, dq5):
    """(행 [(자리, 곡, 판정)], [문제]). 판정은 '끝남'·'되풀이'·'가드'·'곡 모름'."""
    rows, bad = [], []
    found, loose = sites(rom)
    bad += loose
    guard = guard_problems(rom)
    bad += guard
    loops = loop_table(rom)
    original = original_sites(dq5)
    if original != DQ5_SITES:
        diff = sorted(set(original.items()) ^ set(DQ5_SITES.items()), key=lambda r: r[0])
        bad.append(f'원본 DQ5 기다림 자리가 DQ5_SITES 와 다름: {[(fmt(a), s) for a, s in diff][:6]}')
    for at, song, _, _ in found:
        if song is None:
            rows.append((at, None, '곡 모름' if guard else '가드'))
            continue
        if at not in original and at not in TABLES and song not in PORT_SONGS:
            bad.append(f'{fmt(at)}: 포팅 코드가 곡 {song:02X} 를 기다림(dq4songwait.PORT_SONGS 에 없음)')
        if song < SONG_LIMIT and loops[song]:
            rows.append((at, song, '되풀이'))
            bad.append(f'{fmt(at)}: 곡 {song:02X} 이 끝나기를 기다리는데 그 곡은 되풀이함')
        else:
            rows.append((at, song, '끝남'))
    return rows, bad


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--rom', type=Path, required=True)
    ap.add_argument('--dq5', type=Path, default=Path('rom/dq5.sfc'))
    args = ap.parse_args()
    rows, bad = check(args.rom.read_bytes(), args.dq5.read_bytes())
    for at, song, verdict in rows:
        name = '' if song is None else f'{song:02X}'
        print(f'{fmt(at)}  {name:2}  {verdict}  {INDIRECT.get(at, "")}'.rstrip())
    for p in bad:
        print(f'실패: {p}')
    print('통과' if not bad else f'실패 {len(bad)}개')
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
