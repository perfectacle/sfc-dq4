"""장 제목 상자 게임 장면 판정(보고만): 맵이 있는 장 첫머리 상자를 MesenCE 헤드리스로 띄워 dq4boxjudge.judge 에 돌린다.

  MESENCE=… LIBDIR=… uv run --locked python sfc/dq4/tools/dq4boxplay.py --rom work/ch3/dq4-ch1.sfc --out work/boxplay
형식은 sfc/dq4/docs/dq4-chapter1-format.md 「장 제목 상자 판정」.
"""
import argparse
import json
import os
import sys
from pathlib import Path

import dq4boxjudge as bj

# 게임 장면: 장 첫머리 상자는 그 맵(dq4chapterbox Scene.where)에 그 깃발이 꺼진 채(since 는 켠 채) 들어가면 뜬다.
# 끝 상자(Scene.where 없음)는 장 끝 사건이 부르므로 이 길로는 띄우지 못한다(미리보기 판정과 장 끝 사건 검사가 지난다)
PLAY_FRAMES = 600              # 들어간 뒤 찍는 프레임(상자 밝히기·버티기·지우기가 이 안)
SHOT_EVERY = 6


def play_cases():
    """[(이름, 'GG/MM,X,Y', SET)]: 맵이 있는 상자 장면. 도착 칸은 맵 들어가는 곳(dq4chapterbox 가 고른 맵의 0,0 은 쓰지 않고
    dq5warp.lua 가 정한 도착 칸)."""
    import dq4chapterbox as cb
    out = []
    for s in cb.GAME_SCENES:
        if s.where is None:
            continue
        sets = []
        if s.flag:
            sets.append(f'{s.flag[0] & 0xFFFF:04X}&{0xFF ^ s.flag[1]:02X}')
        if s.since:
            sets.append(f'{s.since[0] & 0xFFFF:04X}|{s.since[1]:02X}')
        out.append((s.name, f'{s.where[0]:02X}/{s.where[1]:02X}', ';'.join(sets)))
    return out


def play(mesence, rom, out):
    """장면마다 그 맵으로 워프해 상자가 뜨는 동안 화면을 찍고 판정한다. {장면: [(종류, 설명)] 또는 오류}."""
    import dq4groupcheck
    import dq4readset
    import dq4windowcheck as wc
    from PIL import Image
    data = Path(rom).read_bytes()
    states = wc.make_states(mesence, Path(rom), data, out / 'states')
    results = {}
    for name, where, sets in play_cases():
        dest = out / name
        env = dq4groupcheck.environment(os.environ['LIBDIR'], states['shop'], dest)
        dest.mkdir(parents=True)
        frames = range(SHOT_EVERY, PLAY_FRAMES, SHOT_EVERY)
        env.update(TO=where, SET=sets, ANYWHERE='1', SETTLE=str(PLAY_FRAMES), MAXF=str(PLAY_FRAMES + 1200),
                   SHOTS=','.join(map(str, frames)), WARPEXIT=f'{dq4groupcheck.warp_exit(Path(rom)):X}',
                   DP86OK=dq4groupcheck.dp86_allowed(Path(rom)))
        dq4readset.run(mesence, Path(rom), dq4groupcheck.WARP, dest, env, timeout=300)
        shots = sorted(dest.glob('*.png'))
        seen, found = 0, []
        for shot in shots:
            problems = bj.judge(Image.open(shot).convert('RGB').crop((0, 0, bj.SCREEN_W, bj.SCREEN_H)))
            if problems and problems[0][0] == '상자 없음':
                continue
            seen += 1
            found += [(shot.name, kind, text) for kind, text in problems]
        results[name] = {'shots': len(shots), 'box': seen, 'found': found}
    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--rom', required=True, type=Path)
    ap.add_argument('--out', required=True, type=Path)
    args = ap.parse_args()
    results = play(os.environ['MESENCE'], args.rom, args.out)
    for name, r in results.items():
        print(f'{name}: 화면 {r["shots"]}장, 상자 {r["box"]}장, 걸림 {len(r["found"])}건'
              + ('' if r['box'] else ' — 상자가 뜨지 않음'))
        for shot, kind, text in r['found']:
            print(f'  {shot} {kind}: {text}')
    (args.out / 'results.json').write_text(json.dumps(results, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print(f'게임 화면 판정: 장면 {len(results)}개, 걸림 {sum(len(r["found"]) for r in results.values())}건')
    return 0                    # 보고만


if __name__ == '__main__':
    sys.exit(main())
