"""장 제목 상자 게임 장면 판정(보고만): 맵이 있는 장 첫머리 상자를 MesenCE 헤드리스로 띄워 dq4boxjudge.judge 에 돌린다.

  MESENCE=… LIBDIR=… uv run --locked python sfc/dq4/tools/dq4boxplay.py --rom work/ch3/dq4-ch1.sfc --out work/boxplay.noindex
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
PLAY_FRAMES = 600              # 들어간 뒤 기다리는 프레임(상자 밝히기·버티기·지우기가 이 안)
MAX_FRAMES = PLAY_FRAMES + 1200  # 워프(배에서 사다리까지 걷기)를 더한 끝
SHOT_LUA = Path(__file__).resolve().parent / 'lua' / 'dq4shotwarp.lua'
SHOT_EVERY = 6


def starts():
    """{장면 이름: (맵, X, Y)}: 그 장이 시작하는 칸(장 모듈의 시작 칸)."""
    import dq4ch2event
    import dq4ch3event
    import dq4chapter1
    import dq4prologue
    return {'box0': dq4prologue.START, 'box': dq4chapter1.START,
            'box2': (dq4ch2event.THRONE, *dq4ch2event.START_CELL), 'box3': (dq4ch3event.HOUSE, *dq4ch3event.START_CELL)}


def play_cases():
    """[(이름, 'GG/MM,X,Y', SET)]: 맵이 있는 상자 장면. 시작 칸이 그 장면의 맵이 아니면 멈춘다."""
    import dq4chapterbox as cb
    cells = starts()
    out = []
    for s in cb.GAME_SCENES:
        if s.where is None:
            continue
        where, x, y = cells[s.name]
        if where != f'{s.where[0]:02X}/{s.where[1]:02X}':
            raise SystemExit(f'{s.name}: 시작 칸 {where} 이 상자 맵과 다름')
        sets = []
        if s.flag:
            sets.append(f'{s.flag[0] & 0xFFFF:04X}&{0xFF ^ s.flag[1]:02X}')
        if s.since:
            sets.append(f'{s.since[0] & 0xFFFF:04X}|{s.since[1]:02X}')
        out.append((s.name, f'{where},{x},{y}', ';'.join(sets)))
    return out


def frames(path):
    """box.rgb → [(프레임, PIL 화면 256x224)]. 화면이 넓으면(하이레스) 가로 두 점에 하나만 둔다."""
    import struct
    from PIL import Image
    data = path.read_bytes() if path.is_file() else b''
    out, at = [], 0
    while at + 12 <= len(data):
        n, w, h = struct.unpack_from('<III', data, at)
        at += 12
        im = Image.frombytes('RGB', (w, h), data[at:at + w * h * 3])
        at += w * h * 3
        if w >= 2 * bj.SCREEN_W:
            im = im.resize((w // 2, h), Image.NEAREST)
        out.append((n, im.crop((0, 0, bj.SCREEN_W, bj.SCREEN_H))))
    return out


def play(mesence, rom, out, only=None):
    """장면마다 그 맵으로 워프해 상자(금색)가 보이는 화면을 메모리에서 판정한다. 파일로는 걸린 화면과 장면마다 대표 한
    장(rep.png)만 남기고 원시 화면(box.rgb)은 지운다."""
    import dq4chapterbox as cb
    import dq4groupcheck
    import dq4readset
    import dq4windowcheck as wc
    data = Path(rom).read_bytes()
    states = wc.make_states(mesence, Path(rom), data, out / 'states')
    gold = '%02X%02X%02X' % cb.GOLD
    results = {}
    for name, where, sets in play_cases():
        if only and name != only:
            continue
        dest = out / name
        env = dq4groupcheck.environment(os.environ['LIBDIR'], states['shop'], dest)
        dest.mkdir(parents=True)
        env.update(TO=where, SET=sets, ANYWHERE='1', SETTLE=str(PLAY_FRAMES), MAXF=str(MAX_FRAMES),
                   WARPLUA=str(dq4groupcheck.WARP), EVERY=str(SHOT_EVERY), GOLD=gold,
                   WARPEXIT=f'{dq4groupcheck.warp_exit(Path(rom)):X}', DP86OK=dq4groupcheck.dp86_allowed(Path(rom)))
        dq4readset.run(mesence, Path(rom), SHOT_LUA, dest, env, timeout=300)
        raw = dest / 'box.rgb'
        seen, found = frames(raw), []
        for n, im in seen:
            problems = bj.judge(im)
            if problems:
                im.save(dest / f'f{n:05d}.png')
            found += [(f'f{n:05d}', kind, text) for kind, text in problems]
        if seen:
            seen[len(seen) // 2][1].save(dest / 'rep.png')
        raw.unlink(missing_ok=True)
        results[name] = {'box': len(seen), 'found': found}
    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--rom', required=True, type=Path)
    ap.add_argument('--out', required=True, type=Path)
    ap.add_argument('--only', help='이 장면(box0·box·box2·box3)만')
    args = ap.parse_args()
    if not args.out.name.endswith('.noindex'):
        ap.error('--out 은 .noindex 로 끝나는 폴더(macOS 색인이 건너뜀)')
    results = play(os.environ['MESENCE'], args.rom, args.out, args.only)
    for name, r in results.items():
        print(f'{name}: 상자 화면 {r["box"]}장, 걸림 {len(r["found"])}건'
              + ('' if r['box'] else ' — 상자가 뜨지 않음'))
        for shot, kind, text in r['found']:
            print(f'  {shot} {kind}: {text}')
    (args.out / f'results{"-" + args.only if args.only else ""}.json').write_text(json.dumps(results, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print(f'게임 화면 판정: 장면 {len(results)}개, 걸림 {sum(len(r["found"]) for r in results.values())}건')
    return 0                    # 보고만


if __name__ == '__main__':
    sys.exit(main())
