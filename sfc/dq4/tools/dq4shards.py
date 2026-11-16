"""검사 하나 안에서 서로 기다릴 것이 없는 장면·맵·사례를 함께 돌린다.

띄우는 에뮬레이터 수는 어차피 머신 전체의 자리(tools/headless_slots, HEADLESS_SLOTS)가 묶는다. 그래서 함께 돌리는 일
수의 기본값도 그 자리 수로 두어, 자리를 기다리기만 하는 스레드를 늘리지 않는다. 결과는 끝난 순서와 상관없이 넣은 순서로
돌려주어, 기록 파일과 판정이 샤드 순서에 따라 달라지지 않게 한다.

  jobs = dq4shards.jobs()                       # 기본 병렬 수
  results = dq4shards.pmap(fn, items, jobs)     # items 순서대로의 fn(item)

긴 검사는 장면 목록을 하위 조각으로 나눠 CI 러너 여러 대에서 따로 돈다(guards.toml 의 parts, tools/guards.py --shard).
guards.py 는 하위 조각마다 DQ4_GUARD_PART=k/n 을 주고, 검사 도구는 그 몫의 장면만 돈다.

  dq4shards.add_part_arg(ap)                    # --part k/n(기본 DQ4_GUARD_PART)
  mine = dq4shards.part_of(units, a.part, key=lambda u: u.name)   # k 번째 몫(원래 순서), part 가 None 이면 전부

n 은 늘 guards.toml 의 parts 다. CI 조각이 n 보다 적으면 한 조각이 몫 여럿을 한 번에 돈다(DQ4_GUARD_PART=1,3/4: 1 번과
3 번 몫의 합). 몫의 경계가 조각 수에 따라 바뀌지 않아, 몫마다 남긴 통과 기록·캐시를 조각 수가 다른 실행이 그대로 쓴다.
"""
import argparse
import concurrent.futures
import os
import re
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[3] / 'tools'))
import headless_slots  # noqa: E402


def jobs():
    """기본 병렬 수: HEADLESS_SLOTS. 제한이 없으면(0, flock 이 없는 Windows) CPU 수의 절반."""
    return headless_slots.limit() or max(1, (os.cpu_count() or 2) // 2)


def pmap(fn, items, n=None):
    """fn(item) 을 n 개(기본 jobs())까지 함께 돌려 items 순서대로 돌려준다. 하나라도 예외를 내면 그 예외를 다시 낸다."""
    items = list(items)
    with concurrent.futures.ThreadPoolExecutor(max(1, min(n or jobs(), len(items) or 1))) as pool:
        return list(pool.map(fn, items))


PART_ENV = 'DQ4_GUARD_PART'


class Parts(tuple):
    """몫 번호 여럿(차례대로, 겹침 없음). 글자로는 「1,3」 이라 도구들이 찍는 f'{k}/{n}' 이 「1,3/4」 가 된다."""

    def __format__(self, spec):
        return format(','.join(map(str, self)), spec)

    __str__ = __format__


def parse_part(text):
    """'k/n' → (k, n), 1 ≤ k ≤ n. 'k1,k2,…/n' → (Parts((k1, k2, …)), n): 그 몫들의 합. 빈 값·None 은 None(나누지 않음)."""
    if not text:
        return None
    m = re.fullmatch(r'(\d+(?:,\d+)*)/(\d+)', text)
    ks = [int(x) for x in m[1].split(',')] if m else []
    if not m or not all(1 <= k <= int(m[2]) for k in ks) or len(set(ks)) != len(ks):
        raise argparse.ArgumentTypeError(f'--part 는 k/n 또는 k1,k2/n(1 ≤ k ≤ n, 겹침 없음): {text!r}')
    return (ks[0] if len(ks) == 1 else Parts(sorted(ks))), int(m[2])


def part_numbers(part):
    """part 의 몫 번호 집합."""
    return set(part[0]) if isinstance(part[0], tuple) else {part[0]}


def add_part_arg(ap):
    """--part k/n 을 더한다. 기본값은 DQ4_GUARD_PART 이고, 읽은 뒤 환경에서 지운다: 이 도구가 띄우는 다른 검사 도구가
    같은 값을 받아 제 장면을 또 나누면 몫이 겹치거나 빈다. 몫을 넘길 때는 그 도구에 --part 로 직접 준다."""
    env = os.environ.pop(PART_ENV, '')
    try:
        default = parse_part(env)
    except argparse.ArgumentTypeError as e:
        ap.error(f'{PART_ENV}: {e}')
    ap.add_argument('--part', type=parse_part, default=default, metavar='k/n',
                    help=f'장면 목록을 n 몫으로 나눠 k 번째만 돈다(기본 {PART_ENV}, CI 가드 하위 조각)')


def part_of(items, part, key=str, weight=None):
    """items 를 n 몫으로 나눈 k 번째(part=(k, n), k 가 Parts 면 그 몫들의 합) 를 원래 순서대로. part 가 None 이면 전부. 무게(weight(item), 기본 1)가
    큰 것부터, 같으면 key 차례로 가장 가벼운 몫에 넣는다(같으면 앞 몫). 같은 items 면 어디서든 같은 몫이 나오고, 몫을
    모두 모으면 겹침 없이 items 와 같다. key 는 서로 달라야 한다."""
    items = list(items)
    if part is None:
        return items
    k, n = part
    keys = [key(x) for x in items]
    if len(set(keys)) != len(keys):
        raise ValueError(f'part_of: 겹치는 key {sorted({x for x in keys if keys.count(x) > 1})}')
    w = [float(weight(x)) if weight else 1.0 for x in items]
    loads, owner = [0.0] * n, {}
    for i in sorted(range(len(items)), key=lambda i: (-w[i], keys[i])):
        j = loads.index(min(loads))
        owner[i] = j
        loads[j] += w[i]
    ks = part_numbers(part)
    mine = [x for i, x in enumerate(items) if owner[i] + 1 in ks]
    print(f'[part] {k}/{n}: {len(mine)}/{len(items)}개', file=sys.stderr, flush=True)
    return mine
