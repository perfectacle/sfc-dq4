"""16×24 색 번호 행렬이 얼마나 '평평한지' 재는 지표; sfc/dq4/docs/dq4-sprite-format.md.

면을 한 색으로 넓게 칠하면 SFC 인물처럼 보이지 않는다. 손으로 그린 시안을 잘 그린 참고 그림과 같은 지표로 견주려고 쓴다.
지표는 방향만 알려 줄 뿐 기준이 아니다. 수치를 억지로 맞추면 얼굴처럼 큰 면이 필요한 곳이 지저분해진다.

- maxrun / runs_ge4 / mean_run: 가로·세로로 같은 색(투명·윤곽 1 제외)이 이어지는 길이. 길수록 평평하다
- asym: 좌우 대칭 위치끼리 색이 다른 비율. 낮으면 좌우 반전처럼 보여 빛 방향이 없다
- edge_density: 이웃한 불투명 칸끼리 색이 바뀌는 횟수 / 불투명 칸 수. 낮으면 명암 단계가 적다

사용: uv run --locked python sfc/dq4/tools/dq4spritecheck.py <행렬 파일>...
행렬 파일은 한 줄에 16글자, `.` 투명. `#` 로 시작하는 줄은 건너뛴다. 24줄을 넘으면 앞 24줄만 본다.
"""

import re
import sys


def runs(rows: list[str]) -> list[int]:
    out = []
    columns = ["".join(r[c] for r in rows) for c in range(len(rows[0]))]
    for line in list(rows) + columns:
        out.extend(len(m.group(0)) for m in re.finditer(r"([^.1])\1*", line))
    return out


def stats(rows: list[str]) -> dict:
    width = len(rows[0])
    lengths = runs(rows)
    filled = sum(ch != "." for r in rows for ch in r)
    pairs = [(r[x], r[width - 1 - x]) for r in rows for x in range(width // 2)]
    shown = [p for p in pairs if p != (".", ".")]
    edges = sum(
        1
        for r in rows
        for x in range(width - 1)
        if r[x] != r[x + 1] and "." not in (r[x], r[x + 1])
    ) + sum(
        1
        for y in range(len(rows) - 1)
        for x in range(width)
        if rows[y][x] != rows[y + 1][x] and "." not in (rows[y][x], rows[y + 1][x])
    )
    return {
        "filled": filled,
        "maxrun": max(lengths),
        "runs_ge4": sum(1 for n in lengths if n >= 4),
        "mean_run": round(sum(lengths) / len(lengths), 2),
        "asym": round(sum(1 for a, b in shown if a != b) / max(1, len(shown)), 2),
        "edge_density": round(edges / max(1, filled), 2),
    }


def load(path: str) -> list[str]:
    with open(path, encoding="utf-8") as f:
        rows = [line.strip() for line in f if line.strip() and not line.startswith("#")]
    return rows[:24]


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    for path in sys.argv[1:]:
        print(path, stats(load(path)))
