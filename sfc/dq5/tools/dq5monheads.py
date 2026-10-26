"""DQ5(SFC) 전투 몬스터 그림 머리 포인터 표의 빈 번호. 형식은 sfc/dq5/docs/dq5-graphics-format.md 의 「그림 머리 포인터」.

그림 번호 0~71 의 머리(22:9014 가 고르는 25:8C45·26:8F99·27:82E4 표)를 주소 순으로 늘어놓고, 머리마다 dq5mongfx.decode
가 읽어 낸 끝 주소, 그 머리를 가리키는 번호들, 번호마다 그 그림을 쓰는 몬스터(27:E5DC 레코드 +0)와 레코드가 비었는지
(23:8000 의 25바이트 능력치 레코드의 +00~+10 이 모두 00, 행동 6개와 떨어뜨리는 물건 +11~+17(16진) 이 모두 FF)를 찍는다. 앞 머리의 끝이 다음 머리와 같으면 그 사이에 다른
번호의 자료가 들어갈 자리가 없다.

사용:
  python sfc/dq5/tools/dq5monheads.py rom/dq5.sfc
"""
import argparse
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(__file__))
from dq5map import Rom  # noqa: E402
from dq5mongfx import COUNT, decode, head, monster  # noqa: E402
from dq5monster import record  # noqa: E402

PICTURES = 0x72


def empty_record(rom, m):
    r = record(rom, m)
    return r[:17] == [0] * 17 and r[17:24] == [0xFF] * 7


def table(rom):
    """[(머리, 끝, [(번호, [(몬스터, 빈 레코드)])])] 를 머리 주소 순으로."""
    users = defaultdict(list)
    for m in range(COUNT):
        users[monster(rom, m)[0]].append((m, empty_record(rom, m)))
    by_head = defaultdict(list)
    for g in range(PICTURES):
        by_head[head(rom, g)].append(g)
    return [(h, decode(rom, gs[0])['end'], [(g, users[g]) for g in gs]) for h, gs in sorted(by_head.items())]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('rom')
    args = ap.parse_args()
    rom = Rom(open(args.rom, 'rb').read())
    rows = table(rom)
    for i, (h, end, nums) in enumerate(rows):
        nxt = rows[i + 1][0] if i + 1 < len(rows) and rows[i + 1][0] >> 16 == h >> 16 else None
        gap = '' if nxt is None else ('' if nxt == end else f' 다음 머리까지 {nxt - end}바이트')
        desc = '  '.join(f'{g:02X}:' + (','.join(f'{m:02X}' + ('(빈)' if e else '') for m, e in us) or '-')
                         for g, us in nums)
        print(f'{h:06X}-{end:06X}{gap}  {desc}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
