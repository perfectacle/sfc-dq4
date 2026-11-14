"""NDS 시트에서 줄인 인물의 눈과 롬 색을 본다(에뮬레이터 없음).

눈: 사람마다 앞모습에 눈 둘, 옆모습에 눈 하나가 INK 로 찍히고 눈 옆에 흰자가 붙었는지. 두건·투구로 눈이 가려진
인물(NO_EYES)은 뺀다.
색: 무겁게 세는 인물(주요·상징 인물)이 나오는 맵 그룹 가운데 가장 나쁜 곳에서, 옷·머리 색이 NDS 색에서 벗어난
거리(Lab, 점 수 가중 평균)가 LIMIT 아래인지. 줄 배정을 바꾸다 이 인물들의 색이 마을 사람 색에 밀리면 넘는다.

  python sfc/dq4/tools/dq4peoplecolorcheck.py --base work/ch1/dq4-ch1-sound.sfc --assets "$DQ4_ASSETS" [--json OUT]
"""
import argparse
import json
import math
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
DQ5_TOOLS = HERE.parents[1] / 'dq5' / 'tools'
for _p in (HERE, DQ5_TOOLS):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import dq4people as P  # noqa: E402
from dq5map import Rom  # noqa: E402

LIMIT = 13.0
NO_EYES = frozenset({'거친 남자', '검은 망토'})
VIEWS = {'down': 2, 'left': 1, 'right': 1}


def eyes(cell):
    """(눈 수, 흰자가 붙은 눈 수). 눈은 위 칸이 INK 가 아닌 INK 칸에서 시작하는 세로 점이다."""
    px = cell.load()
    ink = {(x, y) for y in range(cell.height) for x in range(cell.width) if px[x, y][3] and px[x, y][:3] == P.INK}
    tops = [q for q in ink if (q[0], q[1] - 1) not in ink]

    def white(x, y):
        return 0 <= x < cell.width and px[x, y][3] and px[x, y][:3] == P.WHITE
    return len(tops), sum(1 for x, y in tops if white(x - 1, y) or white(x + 1, y))


def eye_problems(person, cells):
    out = []
    for view, want in VIEWS.items():
        for step, cell in enumerate(cells[view]):
            count, whites = eyes(cell)
            if count != want or whites != want:
                out.append(f'{person.role} {view} {step}: 눈 {count}/{want}, 흰자 {whites}/{want}')
    return out


def drift(cells, row, slots):
    """옷·머리 색(COMMON 밖)이 롬 색에서 벗어난 Lab 거리의 점 수 가중 평균."""
    count = Counter(q[:3] for pair in cells.values() for q in pair[0].get_flattened_data() if q[3] and q[:3] not in P.COMMON)
    total = sum(count.values())
    return sum(w * math.dist(P.lab(c), P.lab(row[slots[c]])) for c, w in count.items()) / total if total else 0.0


def check(cells, placed, board, where):
    """(문제 목록, {역할: 가장 나쁜 맵 그룹에서의 색 거리})."""
    problems, worst = [], {}
    for p, c in cells.items():
        if p.anim == 'legs' and p.role not in NO_EYES:
            problems += eye_problems(p, c)
        if p in placed:
            line, slots = placed[p]
            worst[p.role] = max(drift(c, board[(g, line)], slots) for g in where[p])
            if p.weight > 1 and worst[p.role] > LIMIT:
                problems.append(f'{p.role}: 색 거리 {worst[p.role]:.1f} > {LIMIT}')
    return problems, worst


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--base', type=Path, required=True)
    ap.add_argument('--assets', type=Path, required=True)
    ap.add_argument('--json', type=Path)
    args = ap.parse_args(argv)
    cells = {p: P.rgb_frames(p, args.assets) for p in P.PEOPLE}
    where = P.where(P.PEOPLE, P.usage(Rom(args.base.read_bytes())))
    placed, board = P.place(P.PEOPLE, P.histograms(cells), where)
    problems, worst = check(cells, placed, board, where)
    report = {'status': 'failed' if problems else 'passed', 'problems': problems,
              'worst': {k: round(v, 1) for k, v in sorted(worst.items(), key=lambda kv: -kv[1])}}
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report, ensure_ascii=False, indent=1) + '\n')
    for line in problems:
        print(line)
    heavy = [p for p in placed if p.weight > 1]
    print(json.dumps({'status': report['status'], 'people': len(cells), 'problems': len(problems),
                      'heavy_worst': round(max(worst[p.role] for p in heavy), 1)}, ensure_ascii=False))
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main())
