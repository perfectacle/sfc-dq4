"""검사 하나 안에서 서로 기다릴 것이 없는 장면·맵·사례를 함께 돌린다.

띄우는 에뮬레이터 수는 어차피 머신 전체의 자리(tools/headless_slots, HEADLESS_SLOTS)가 묶는다. 그래서 함께 돌리는 일
수의 기본값도 그 자리 수로 두어, 자리를 기다리기만 하는 스레드를 늘리지 않는다. 결과는 끝난 순서와 상관없이 넣은 순서로
돌려주어, 기록 파일과 판정이 샤드 순서에 따라 달라지지 않게 한다.

  jobs = dq4shards.jobs()                       # 기본 병렬 수
  results = dq4shards.pmap(fn, items, jobs)     # items 순서대로의 fn(item)
"""
import concurrent.futures
import os
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
