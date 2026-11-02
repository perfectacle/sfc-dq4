"""곡이 끝나기를 기다리는 자리와 그 자리의 곡이 되풀이하지 않는지(롬 바이트만, 에뮬레이터 없음).

DQ5 의 `24:FF0F` 는 명령 `09 n`(곡 n 이 아직 울리는지)을 보내고 대답 `7E:08D2` 가 `7F` 가 될 때까지 돈다.
`25:FD00` 은 `1A`·`01 n` 뒤 대기열을 비우고 `24:FF0F` 로 기다린 다음 맵 곡으로 돌아간다. 그래서 되풀이하는 곡을
이 자리에 두면 게임이 그 자리에서 멈춘다(교회 치료 뒤 「…주소서!」). 형식은
sfc/dq4/docs/dq4-sound-port-format.md 「곡 끝을 기다리는 자리」.

  uv run --locked python sfc/dq4/tools/dq4songwait.py --rom work/ch1/dq4-ch1-full.sfc --sound work/ch1/dq4-ch1-sound.json

곡이 되풀이하는지는 소리 빌드 보고(dq4soundset 의 conversion.loop_start)로, 보고에 없는 곡(DQ5 곡 그대로)은
원래 롬의 시퀀스를 따라가 본다. 효과음(32~46)은 보지 않는다.
"""
import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[1] / 'dq5' / 'tools')]

WAIT = 0x24FF0F
JINGLE = 0x25FD00
# SEP #20 / LDA #n / BRA FD00
WRAPPERS = {0x25FCF0: 0x2E, 0x25FCF6: 0x22, 0x25FCFC: 0x24}
# 같은 뱅크 안에서 LDA #n / JSR 로 부르는 기다림 루틴(JSL 24:FE9A / JSL 24:FF0F)
LOCAL = {0x23E53A: 0x23}
# 곡 번호를 표에서 읽는 기다림: 슬롯이 맞았을 때 받은 코인으로 고르는 곡(23:FEEC LDA $FF0A,X → 23:FEFC)
TABLES = {0x23FEFC: (0x23FF0A, 4)}
# 곡 번호가 즉값이 아닌 자리. 새로 생기면 여기 근거를 적는다(곡을 알 수 없어 반복 여부를 보지 못함)
INDIRECT = {
    0x02D286: '앞에서 A 를 정하지 않음(JSL 00:E9CE / BRK 08 뒤), 장면 미확인',
    0x038EA8: 'LDA $03(직접 페이지 값), 장면 미확인',
    0x12F354: 'STZ $224C 뒤, A 는 앞 갈래가 정함, 장면 미확인',
    0x23E53E: 'LOCAL 23:E53A 의 몸통(부르는 곳마다 곡을 셈)',
    0x23FEFC: 'TABLES 로 셈',
    0x25FD0F: '25:FD00 의 몸통(부르는 곳마다 곡을 셈)',
}
# 되풀이하는 곡이 들었지만 이 롬에서 그 자리에 닿는지 확인하지 않은 자리. 닿게 되면 대응표를 고치고 여기서 지운다
UNREACHED = {
    0x02B7B0: '1C 동료가 됨(DQ5). 1장 합류는 dq4ch1event 의 곡 26',
    0x05F015: '1C 「…が 仲間に くわわった！」(DQ5 메시지 5D9)',
    0x06B491: '1C DQ5 대화 24D 의 네이티브',
    0x06CFD4: '1C DQ5 대화 네이티브',
    0x06B64E: '22 물건을 받음(DQ5 대화 네이티브)',
    0x06B682: '22 물건을 받음(DQ5 대화 139 의 ゴールドオーブ)',
    0x06B8D4: '22 물건을 받음(DQ5 대화 네이티브)',
    0x06BC53: '22 물건을 받음(DQ5 대화 네이티브)',
    0x06CA3C: '22 물건을 받음(DQ5 대화 네이티브)',
    0x06F803: '22 물건을 받음(DQ5 대화 네이티브)',
    0x12F527: '22 25:FCF6 를 부르는 DQ5 이벤트 루틴(25:FCF0 의 2E 를 부르는 12:F5B0 과 같은 묶음)',
    0x12F6F2: '22 25:FCF6 를 부르는 DQ5 이벤트 루틴(같은 묶음)',
    0x05DE06: '23 저주받은 장비를 장비함(05:DDFF, k2 bit3). 1장 가게·상자에 그런 물건이 있는지 미확인',
    0x06C97A: '23 DQ5 대화 네이티브',
    0x06FC4A: '23 DQ5 대화 네이티브',
    0x06FC55: '23 DQ5 대화 네이티브',
    0x06FC62: '23 DQ5 대화 네이티브',
}
EFFECTS = range(0x32, 0x47)


def offset(addr):
    return (addr >> 16) * 0x8000 + (addr & 0x7FFF)


def cpu(off):
    return (off // 0x8000) << 16 | 0x8000 | off % 0x8000


def fmt(addr):
    return f'{addr >> 16:02X}:{addr & 0xFFFF:04X}'


def inn_wait_entry():
    """여관 징글 기다림 코드(dq4soundpatch.inn_jingle_code 의 둘째)의 첫 주소와 끝. 06:E422 LDA #1D 뒤 JSL 로 불린다."""
    import dq4soundpatch as patch
    fade, wait = patch.inn_jingle_code()
    start = patch.INN_JINGLE + len(fade)
    return start, start + len(wait)


def _far(addr):
    return bytes((addr & 0xFF, addr >> 8 & 0xFF, addr >> 16))


def sites(rom, entries=None, bodies=()):
    """[(자리, 곡 또는 None, 입구)]. entries 는 A 의 곡을 기다리는 입구(JSL·JML 대상), bodies 는 입구 몸통 범위
    [(시작, 끝)] 으로 그 안의 부르기는 따로 세지 않는다."""
    entries = set(entries or (WAIT, JINGLE))
    out = []
    for entry in sorted(entries):
        for op in (0x22, 0x5C):
            pat = bytes([op]) + _far(entry)
            i = rom.find(pat)
            while i >= 0:
                at = cpu(i)
                if not any(s <= at < e for s, e in bodies):
                    song = rom[i - 1] if i >= 2 and rom[i - 2] == 0xA9 else None
                    out.append((at, song, entry))
                i = rom.find(pat, i + 1)
    for entry, song in WRAPPERS.items():
        pat = b'\x22' + _far(entry)
        i = rom.find(pat)
        while i >= 0:
            out.append((cpu(i), song, entry))
            i = rom.find(pat, i + 1)
    for entry, bank in LOCAL.items():
        lo = offset(bank << 16 | 0x8000)
        pat = b'\x20' + bytes((entry & 0xFF, entry >> 8 & 0xFF))
        i = rom.find(pat, lo, lo + 0x8000)
        while i >= 0:
            out.append((cpu(i), rom[i - 1] if rom[i - 2] == 0xA9 else None, entry))
            i = rom.find(pat, i + 1, lo + 0x8000)
    for at, (table, n) in TABLES.items():
        o = offset(table)
        for song in sorted(set(rom[o:o + n])):
            out.append((at, song, table))
    return sorted(out, key=lambda r: (r[0], -1 if r[1] is None else r[1]))


def dq5_loops(dq5, song):
    """원래 DQ5 시퀀스 song 의 트랙 가운데 끝(FF)에 닿지 않고 되도는 것이 있으면 True."""
    from dq5map import Rom
    from dq5song import header, step
    from dq5spc import body, sequences
    rom = Rom(dq5)
    _, a, n = sequences(rom)[song]
    seq = body(rom, a, n)
    for pc in header(seq)[1]:
        stack, seen = (), set()
        while (pc, stack) not in seen:
            seen.add((pc, stack))
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


def song_loops(song, sound, dq5):
    """(되풀이하는지, 출처 글)."""
    item = sound.get('songs', {}).get(f'{song:02X}')
    if item is not None:
        return item['conversion'].get('loop_start') is not None, f"NDS {item['nds_song']}"
    return dq5_loops(dq5, song), 'DQ5'


def check(rom, dq5, sound):
    """(행 [(자리, 곡, 출처, 판정)], [문제]). 판정은 '끝남'·'되풀이(미확인 자리)'·'효과음'·'곡 모름'."""
    inn = inn_wait_entry()
    rows, bad = [], []
    for at, song, entry in sites(rom, (WAIT, JINGLE, inn[0]), bodies=[inn]):
        where = fmt(at)
        if song is None:
            if at not in INDIRECT:
                bad.append(f'{where}: 곡이 끝나기를 기다리는데 곡 번호가 즉값이 아님(dq4songwait.INDIRECT 에 근거를 적을 것)')
            rows.append((at, None, '', '곡 모름'))
            continue
        if song in EFFECTS:
            rows.append((at, song, '', '효과음'))
            continue
        loops, source = song_loops(song, sound, dq5)
        if not loops:
            rows.append((at, song, source, '끝남'))
        elif at in UNREACHED:
            rows.append((at, song, source, '되풀이(미확인 자리)'))
        else:
            rows.append((at, song, source, '되풀이'))
            bad.append(f'{where}: 곡 {song:02X}({source})이 끝나기를 기다리는데 그 곡은 되풀이함 — 그 자리에서 멈춤')
    for at in sorted(set(INDIRECT) | set(UNREACHED)):
        if all(r[0] != at for r in rows) and at not in TABLES:
            bad.append(f'{fmt(at)}: 목록에 있는 자리에 기다림 부르기가 없음(목록을 고칠 것)')
    return rows, bad


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--rom', type=Path, required=True)
    ap.add_argument('--sound', type=Path, required=True, help='dq4soundset 보고(dq4-ch1-sound.json)')
    ap.add_argument('--dq5', type=Path, default=Path('rom/dq5.sfc'))
    args = ap.parse_args()
    rows, bad = check(args.rom.read_bytes(), args.dq5.read_bytes(),
                      json.loads(args.sound.read_text(encoding='utf-8')))
    for at, song, source, verdict in rows:
        name = '' if song is None else f'{song:02X}'
        note = INDIRECT.get(at) or UNREACHED.get(at) or ''
        print(f'{fmt(at)}  {name:2}  {source:7}  {verdict}  {note}'.rstrip())
    for p in bad:
        print(f'실패: {p}')
    print('통과' if not bad else f'실패 {len(bad)}개')
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
