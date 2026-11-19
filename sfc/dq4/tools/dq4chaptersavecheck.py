"""장 끝 기록 물음(dq4ch2event.chapter_flow, FC 1A:$B943)을 libretro 코어(snes9x·bsnes)로 끝까지 돌려 본다.

장 끝 직전의 기록(dq4savefixture)을 그 장 끝 맵의 교회 칸으로 이어 하면 장 끝이 걸린다: 2장은 우승·브라이의 말 flag
로 이어 하자마자 산트하임 앞마당(3D/00)에서. 1장은 보고 flag 로 바트랜드 성 앞(36/00)에 들어설 때 걸리는데 이어 하기로 선
맵에서는 걸리지 않으므로, 이어 한 뒤 같은 칸으로 순간이동(dq4compatcheck.Walker.warp)해 맵에 다시 든다. 서술·「완」
상자는 A 를 띄엄띄엄 눌러 넘긴다. 기록 물음은 마지막으로 연 창(7E:0A00)이 예/아니요(32)이고 대답 flag(7E:21A3 bit0)가
꺼진 채 STABLE 프레임 이어지면 그때 대답을 넣는다(교회의 기록 물음도 창 32 라 장 끝 맵에 선 뒤의 것만 센다).

  yes     예 → 기록 칸 0 이 이어 할 칸 = 다음 장 FC 귀환 자리 칸, 다음 장 flag·첫머리 대기 flag 가 켜진 기록. 그 SRAM
          으로 코어를 새로 켜 이어 하면(타이틀 기록 목록이 그 칸 이름을 띄움) 다음 장 첫머리 맵의 시작 칸
          (dq4fieldtravel.CHAPTER_STARTS)에 서고, 주인공 소지품·장비·금화는 FC 장 시작 표(dq4ch1walkcheck.start_want)대로
  no-yes  아니요 → 03BF 예 → 기록 칸이 처음 기록 그대로, 다음 장 맵으로 넘어감
  no-no   아니요 → 03BF 아니요 → 다시 03BE(예/아니요가 세 번째로 뜸) → 예 → 장 시작 칸으로 기록

  uv run --locked python sfc/dq4/tools/dq4chaptersavecheck.py --rom work/ch3/dq4-ch1-full.sfc --out work/chaptersave

롬은 dq4build.py --chapter3 의 출력이어야 한다(1장 끝에서 2장, 2장 끝에서 3장으로 넘어감).
"""
import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[1] / 'dq5' / 'tools')]

import dq4ch1walkcheck as wc  # noqa: E402
import dq4ch2event as ch2  # noqa: E402
import dq4fieldtravel as travel  # noqa: E402

WINDOW, YES_NO = 0x7E0A00, 0x32
STABLE = 8
TAP_EVERY = 30
LIMIT = 9000                   # 장 끝부터 다음 장 맵까지 기다리는 상한(프레임)
ALENA, TORNEKO = 7, 5          # FC 인물 번호(12:$9192 장 시작 표의 차례)


def _flag_on(rec, flag):
    a = 0x2190 + flag[0]
    rec.poke(a, rec._get(a) | flag[1])


def records(rom):
    """{장: (장 끝 직전 기록, 다음 장 첫머리 (BC, BD, X, Y), 귀환 자리 칸, 다음 장 flag, 첫머리 flag, FC 인물 번호,
    다음 장)}."""
    import dq4ch2ending as ending
    import dq4ch3event as ch3
    import dq4savefixture as fx
    data = Path(rom).read_bytes()
    one = fx.SaveSlot.new_game(rom)
    one.place = 'batland'
    for name in ('CHAPTER1', 'NIGHT_TOLD', 'FLARE', 'REUNITED', 'HOIMIN', 'KIDNAPPED', 'BOSS_WON', 'SOLDIER',
                 'REPORTED'):
        one.flag(name)
    two = fx.SaveSlot.new_game(rom)
    two.place = 'santeem'
    two.apply_sets(wc.record_set(wc.chapter_hero(data, 2)))
    for flag in (ch2.CHAPTER2, ending.EMPTY, ending.SEEN_BREY):
        _flag_on(two, flag)
    (_, g2, n2, c2, r2, _), (_, g3, n3, c3, r3, _) = travel.CHAPTER_STARTS
    return {1: (one, (g2, n2, *c2), travel.slot_of_fc(r2), ch2.CHAPTER2, ch2.OPENING, ALENA, 2),
            2: (two, (g3, n3, *c3), travel.slot_of_fc(r3), ch3.CHAPTER3, ch3.OPENING, TORNEKO, 3)}


def play(core, step, answers, goal):
    """예/아니요 창마다 answers 의 대답(True 예)을 넣고 맵이 goal 이 될 때까지. (본 창 수, 다다른 프레임 또는 None)."""
    seen, stable, answered, start = 0, 0, False, core.n
    while core.n - start < LIMIT:
        here = (core.rd(0x7E00BC), core.rd(0x7E00BD))
        if here == goal[:2]:
            return seen, core.n
        w = core.rd(WINDOW)
        asking = w == YES_NO and not core.rd(0x7E2190 + ch2.ANSWERED[0]) & ch2.ANSWERED[1]
        stable = stable + 1 if asking else 0
        if w != YES_NO:
            answered = False
        if stable == STABLE and not answered:
            yes = answers[seen] if seen < len(answers) else True
            seen += 1
            answered = True
            if not yes:
                for b in ('down',) * 2 + ('wait',) * 10:
                    step(set() if b == 'wait' else {b})
            for b in ('a',) * 2 + ('wait',) * 4:
                step(set() if b == 'wait' else {b})
            continue
        tap = w != YES_NO and (core.n - start) % TAP_EVERY < 2
        step({'a'} if tap else set())
    return seen, None


def scene(core_path, rom, out, chapter, answers):
    import dq4savefixture as fx
    rec, goal, church, flag, opening, who, nxt = records(rom)[chapter]
    before = rec.to_sram()
    name = f'ch{chapter}-' + '-'.join('yes' if a else 'no' for a in answers)
    import dq4compatcheck as cc
    wout = out / name
    wout.mkdir(parents=True, exist_ok=True)
    # Walker 는 wout/c.sfc 를 wout 을 저장 폴더로 연다: bsnes 가 읽을 c.srm 을 먼저 둔다
    (wout / 'c.srm').write_bytes(before)
    walker = cc.Walker(str(core_path), rom, wout)
    core = walker.c
    with fx.closing(core):
        fx.load_sram(core, before)
        at = fx.boot(core, rec.goal, step=walker.step)
        if at is not None and chapter == 1:
            walker.warp('{:02X}/{:02X},{},{}'.format(*rec.goal))
        seen, moved = play(core, walker.step, answers, goal) if at is not None else (0, None)
        sram = fx.read_sram(core)
        core.shot(wout / 'end.png')
    (wout / 'after.srm').write_bytes(sram)
    saved = sram[fx.SLOTS[0]:fx.SLOTS[0] + fx.SLOT_SIZE]
    old = before[fx.SLOTS[0]:fx.SLOTS[0] + fx.SLOT_SIZE]
    want_save = answers[0] or (len(answers) > 1 and not answers[1])
    problems = []
    if at is None:
        problems.append('장 끝 맵에 이어 하지 못함')
    if moved is None:
        problems.append(f'다음 장 맵 {goal[0]:02X}/{goal[1]:02X} 으로 넘어가지 않음')
    want_seen = 1 if answers[0] else (2 if answers[1] else 3)
    if seen != want_seen:
        problems.append(f'예/아니요 창 {seen}번(기대 {want_seen})')
    result = {'scene': name, 'arrived': at, 'moved': moved, 'asked': seen}
    if not want_save:
        if saved != old:
            problems.append('아니요인데 기록 칸이 바뀜')
    else:
        place = saved[fx.PLACE - 0x2000] & 0x7F
        f = saved[0x2190 + flag[0] - 0x2000] & flag[1]
        o = saved[0x2190 + opening[0] - 0x2000] & opening[1]
        if (place, bool(f), bool(o)) != (church, True, True):
            problems.append(f'기록: 이어 할 칸 {place:02X}(기대 {church:02X}), 다음 장 flag {bool(f)}, 첫머리 {bool(o)}')
        if not problems:
            result.update(resume(core_path, rom, out / f'{name}-continue', sram, goal, church, who, nxt, problems))
    result.update({'status': 'failed' if problems else 'passed', 'problems': problems})
    return result


def resume(core_path, rom, out, sram, goal, church, who, chapter, problems):
    """기록한 SRAM 으로 새로 켜 이어 하기: 다음 장 첫머리 맵의 시작 칸, 귀환 자리(church 칸), FC 장 시작 소지품·장비·금화."""
    import dq4savefixture as fx
    with fx.closing(fx.open_core(core_path, rom, out, sram)) as core:
        at = fx.boot(core, goal)
        ram = bytes(core.wram()[:0x20000])
        core.shot(out / 'end.png')
    if at is None:
        problems.append(f'이어 하기가 {goal[0]:02X}/{goal[1]:02X} ({goal[2]},{goal[3]}) 에 서지 않음')
        return {'resumed': None}
    if ram[fx.PLACE] & 0x7F != church:
        problems.append(f'이어 한 뒤 7E:2033 = {ram[fx.PLACE]:02X}(기대 {church:02X})')
    want = wc.start_want(who, chapter)
    got = {k: ram[a & 0xFFFF] for k, a in wc.START_BYTES.items()}
    diff = {k: (got[k], v) for k, v in want.items() if got[k] != v}
    if diff:
        problems.append(f'장 시작 표와 다름 {diff}')
    return {'resumed': at}


SCENES = ((1, (True,)), (1, (False, True)), (1, (False, False, True)), (2, (True,)), (2, (False, True)))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--rom', required=True, type=Path)
    ap.add_argument('--out', required=True, type=Path)
    ap.add_argument('--core', action='append', help='snes9x·bsnes(기본 둘 다)')
    args = ap.parse_args()
    import dq4compatcheck as cc
    import dq4cores
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    results = []
    for name in args.core or cc.CORES:
        path = dq4cores.core_path(name)
        for chapter, answers in SCENES:
            r = scene(path, args.rom.resolve(), out / name, chapter, answers)
            r['core'] = name
            results.append(r)
            print(json.dumps(r, ensure_ascii=False), flush=True)
    ok = all(r['status'] == 'passed' for r in results)
    (out / 'results.json').write_text(json.dumps({'status': 'passed' if ok else 'failed', 'scenes': results},
                                                 ensure_ascii=False, indent=1) + '\n')
    print('passed' if ok else 'failed')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
