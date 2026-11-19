"""사건 연출이 도는 동안 인물의 공용 OBJ 팔레트 줄이 덮이거나 인물 밖 OBJ 가 그 줄을 쓰는지 본다(MesenCE 헤드리스).

걷기 검사(1장 dq4ch1walkcheck.py --units, 2장 dq4ch2walkcheck.py, 3장 dq4ch3walkcheck.py)를 그대로 돌리되, 걷기 구간마다 프레임 표본을 남기는
Lua(lua/dq4peoplesample.lua)를 얹는다. 표본은 구간 폴더의 lines.bin(4프레임마다 CGRAM OBJ 절반·OAM·맵 번호)과 full-<프레임>.bin(120프레임마다 WRAM
앞쪽·OBJ VRAM)이다.

  색    실내 맵($BE bit7)의 표본마다 공용 줄(dq4people.SHARED_LINES) 가운데 롬이 그 맵에서 덮는 줄의 색이 롬 표
        (dq5objpalette.run_lines)와 같은지. 다른 표본은 갈래를 붙인다: 모든 색이 표 색의 회색과 같으면 「회색」
        (dq4ch3bonmalmo.grey, 촌장 장면의 번쩍임), 모든 색이 표보다 어둡거나 같으면 「어두움」
        (화면을 어둡게 하는 연출), 밝거나 같으면 「밝음」, 그 밖은 「다름」. 맵이 바뀌거나 전투가 끝난 뒤 SETTLE
        프레임 안의 표본은 맵을 싣는 중이라 세지 않는다. 전투(JSL $208001 에 들어가 그 호출이 돌아올
        때까지)의 표본은 전투가 OBJ 팔레트를 제 색으로 덮으므로 빼고, 끝난 뒤의 표본으로 줄이 되돌아왔는지 본다
  OBJ   무거운 표본마다 인물 슬롯을 dq4peoplecheck.judge 로 판정하고, 화면 안 OAM 가운데 공용 줄을 쓰면서 판정한
        슬롯의 타일이 아닌 것을 센다

걷기 검사가 실패하거나(못 간 구간은 표본이 없어 판정에서 빠지므로), 「다름」 표본이나 인물 밖 OAM 이 있거나 표본이 하나도
없는 구간이 있으면 실패다. 「회색」·「어두움」·「밝음」 은 구간마다 세어 보고만 한다.

  MESENCE=… LIBDIR=… python sfc/dq4/tools/dq4peopleeventcheck.py --chapter 2 --rom work/ch2/dq4-ch1-full.sfc \\
      --out work/peopleevent2 [--jobs 6] [--only 구간,…] [--json OUT]

--chapter 1 의 롬은 dq4build.py 의 1장 롬, --chapter 2 는 dq4build.py --chapter2, --chapter 3 은 dq4build.py --chapter3
의 롬이다.
"""
import argparse
import json
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DQ5_TOOLS = HERE.parents[1] / 'dq5' / 'tools'
sys.path[:0] = [str(HERE), str(DQ5_TOOLS)]

import dq4ch2walkcheck as ch2walk  # noqa: E402
import dq4people  # noqa: E402
import dq4peoplecheck as people  # noqa: E402
import dq5objpalette  # noqa: E402

SAMPLE = HERE / 'lua' / 'dq4peoplesample.lua'
RECORD = 8 + 0x100 + 0x220
SETTLE = 120                    # 맵이 바뀌거나 전투가 끝난 뒤 이 프레임 안의 표본은 맵을 싣는 중으로 본다
FULL_WRAM, FULL_VRAM = 0xA000, 0x4000


def records(blob):
    """lines.bin → [(프레임, BC, BD, BE, 전투 중, CGRAM OBJ 절반, OAM)]."""
    out = []
    for o in range(0, len(blob) - RECORD + 1, RECORD):
        frame, bc, bd, be, battle = struct.unpack_from('<I4B', blob, o)
        out.append((frame, bc, bd, be, battle, blob[o + 8:o + 0x108], blob[o + 0x108:o + RECORD]))
    return out


def row(cgram_obj, line):
    """OBJ 팔레트 한 줄의 15색(BGR555)."""
    return [cgram_obj[line * 32 + k * 2] | cgram_obj[line * 32 + k * 2 + 1] << 8 for k in range(1, 16)]


def kind(got, want):
    """표와 다른 줄의 갈래: '회색'(모든 색이 표 색의 회색과 같음, 여우 마을 촌장 장면의 번쩍임), '어두움'(모든 채널이
    표 이하), '밝음'(모든 채널이 표 이상), '다름'."""
    import dq4ch3bonmalmo
    if got == [dq4ch3bonmalmo.grey(w) for w in want]:
        return '회색'
    ch = lambda c: (c & 31, c >> 5 & 31, c >> 10 & 31)  # noqa: E731
    pairs = [(g, w) for a, b in zip(got, want) for g, w in zip(ch(a), ch(b))]
    if all(g <= w for g, w in pairs):
        return '어두움'
    if all(g >= w for g, w in pairs):
        return '밝음'
    return '다름'


def line_report(recs, want_of):
    """{갈래: {줄: [프레임…]}}. want_of(bc, bd) 는 그 맵에서 롬이 덮는 CGRAM 사본(없는 줄은 0)."""
    out = {}
    since, last = None, None
    for frame, bc, bd, be, battle, cg, _ in recs:
        # 맵 번호는 실내로 들어서기 전에 먼저 바뀔 수 있다(날아다니는 신발: 필드 위에서 39/00, 120프레임 뒤 실내)
        if (bc, bd, battle, be & 0x80) != last:
            since, last = frame, (bc, bd, battle, be & 0x80)
        if battle or not be & 0x80 or frame - since < SETTLE:
            continue
        want = want_of(bc, bd)[0x100:0x200]
        for n in dq4people.SHARED_LINES:
            w, g = row(want, n), row(cg, n)
            if any(w) and g != w:
                out.setdefault(kind(g, w), {}).setdefault(n, []).append(frame)
    return out


def spans(frames, step):
    """프레임 목록을 이어진 구간 문자열로."""
    out, start, prev = [], None, None
    for f in frames:
        if start is None:
            start = prev = f
        elif f - prev <= step:
            prev = f
        else:
            out.append((start, prev))
            start = prev = f
    if start is not None:
        out.append((start, prev))
    return ', '.join(f'{a}' if a == b else f'{a}~{b}' for a, b in out)


def foreign_report(rom, dest, recs):
    """{프레임: {줄: 수}}. 무거운 표본마다 인물 밖 OAM."""
    oam_at = {r[0]: r[6] for r in recs if not r[4]}
    out, judged = {}, 0
    for path in sorted(dest.glob('full-*.bin')):
        frame = int(path.stem.split('-')[1])
        blob = path.read_bytes()
        if frame not in oam_at or len(blob) != FULL_WRAM + FULL_VRAM:
            continue
        wram = blob[:FULL_WRAM] + bytes(0x20000 - FULL_WRAM)
        vram = bytes(0xC000) + blob[FULL_WRAM:]
        slots = people.judge(rom, wram, vram)
        judged += len(slots)
        found = people.foreign_oam(oam_at[frame], slots)
        if found:
            out[frame] = found
    return out, judged


def analyse(rom, dest):
    recs = records((dest / 'lines.bin').read_bytes())
    cache = {}

    def want_of(bc, bd):
        if (bc, bd) not in cache:
            cache[(bc, bd)] = dq5objpalette.run_lines(rom, bc, bd, True, 0, dq5objpalette.MAP_LOADER)
        return cache[(bc, bd)]
    lines = line_report(recs, want_of)
    foreign, judged = foreign_report(rom, dest, recs)
    step = recs[1][0] - recs[0][0] if len(recs) > 1 else 1
    return {'name': dest.name, 'samples': len(recs), 'indoor': sum(1 for r in recs if r[3] & 0x80), 'battle': sum(1 for r in recs if r[4]),
            'maps': sorted({f'{r[1]:02X}/{r[2]:02X}' for r in recs}), 'slots': judged,
            'lines': {k: {str(n): spans(fs, step) for n, fs in v.items()} for k, v in lines.items()},
            'foreign': {str(f): v for f, v in foreign.items()},
            'ok': bool(recs) and '다름' not in lines and not foreign}


def sampled_run(run):
    """wc.run 을 감싸 걷기 구간(dq4walkstate.lua)에 표본 Lua 를 얹는다."""
    def wrapped(mesence, rom, script, dest, env, timeout, readset=False):
        if Path(script) == ch2walk.wc.WALK_STATE:
            # 읽은 집합 캐시에서 출력을 펼치면 구간이 돌지 않아 표본이 남지 않는다
            return run(mesence, rom, SAMPLE, dest, {**env, 'SAMPLE_NEXT': str(script)}, timeout * 2, False)
        return run(mesence, rom, script, dest, env, timeout, readset)
    return wrapped


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--chapter', type=int, choices=(1, 2, 3), default=2, help='걸을 장')
    ap.add_argument('--rom', required=True, type=Path)
    ap.add_argument('--out', required=True, type=Path)
    ap.add_argument('--jobs', type=int, default=6)
    ap.add_argument('--only', help='이 구간으로 시작하는 묶음만(쉼표로 여럿)')
    ap.add_argument('--json', type=Path)
    ap.add_argument('--analyse-only', action='store_true', help='걷지 않고 --out 에 남은 표본만 다시 판정')
    args = ap.parse_args()
    if not args.analyse_only:
        ch2walk.wc.run = sampled_run(ch2walk.wc.run)
        sys.argv = [sys.argv[0], '--rom', str(args.rom), '--out', str(args.out), '--jobs', str(args.jobs),
                    *(('--units',) if args.chapter == 1 else ()), *(('--only', args.only) if args.only else ())]
        walk = ch2walk.wc if args.chapter == 1 else ch2walk
        if args.chapter == 3:
            # 3장 검사는 2장 flag 표에 3장 것을 더하므로(dq4ch3opencheck) 3장일 때만 불러온다
            import dq4ch3walkcheck
            walk = dq4ch3walkcheck
        # 걷기가 실패하면 못 간 구간의 lines.bin 이 없어 남은 구간만 판정되므로, 걷기 실패는 이 검사의 실패다
        try:
            walk_rc = walk.main()
        except SystemExit as e:
            walk_rc = e.code
        if walk_rc:
            print(json.dumps({'status': 'failed', 'walk': f'걷기 종료 {walk_rc}'}, ensure_ascii=False))
            sys.exit(1)
    rom = args.rom.read_bytes()
    results = [analyse(rom, p.parent) for p in sorted(args.out.rglob('lines.bin'))]
    for r in results:
        print(json.dumps(r, ensure_ascii=False), flush=True)
    failed = [r['name'] for r in results if not r['ok']]
    summary = {'status': 'failed' if failed or not results else 'passed', 'segments': len(results),
               'samples': sum(r['samples'] for r in results), 'slots': sum(r['slots'] for r in results), 'failed': failed}
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps({**summary, 'results': results}, ensure_ascii=False, indent=1) + '\n')
    print(json.dumps(summary, ensure_ascii=False))
    sys.exit(1 if summary['status'] == 'failed' else 0)


if __name__ == '__main__':
    main()
