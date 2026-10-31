"""메시지마다 눌러야 하는 A 가 그 메시지의 쪽 수를 넘지 않는지 보는 검사(MesenCE 헤드리스).

서장 걷기 검사의 길과 1장 걷기 검사의 왕 구간(칭찬·레벨업 줄·작별)을 lua/dq4msgcount.lua 로 감싸 걷는다. 메시지 루틴
24:8BAF 에 들어선 뒤 다음 메시지까지의 ▼ 대기(24:841F)와 닫기 대기(00:982B) 수가 그 메시지에서 받은 A 다. 이것이 쪽 수
(쪽 나눔 1002 의 수 + 1)보다 크면 같은 쪽에서 A 를 두 번 받은 것이라 실패. 글 없이 ▼ 만 기다리는 메시지(dq4ch1event.pauses)
는 한 쪽으로 센다. 닫기 대기의 횟수 $11 이 0 이 아니면(시간이 지나면 저절로 넘어감) 그 대기는 세지 않는다.

  MESENCE=… LIBDIR=… python sfc/dq4/tools/dq4msgcountcheck.py --rom work/ch1/dq4-ch1.sfc \\
      --messages work/ch1/messages.json --states work/ch1walk --out work/msgcount
--states 는 dq4ch1walkcheck.py 의 출력 폴더(왕 구간 앞 castle 구간의 끝 세이브스테이트를 씀).
형식은 sfc/dq4/docs/dq4-prologue-format.md 「메시지 끝」.
"""
import argparse
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[1] / 'dq5' / 'tools')]

import dq4ch1event as ev  # noqa: E402
import dq4ch2event as ch2  # noqa: E402
import dq4ch1walkcheck as walk  # noqa: E402
import dq4mesen as mesen  # noqa: E402
import dq4npcport  # noqa: E402
import dq4prologuecheck as pc  # noqa: E402

PROBE = HERE / 'lua' / 'dq4msgcount.lua'
PAGE = 0x1002


def counts(text):
    """msgcount.txt → [(번호, 받은 A)]. 번호가 같은 메시지가 여러 번 뜨면 따로 센다."""
    out = []
    for line in text.splitlines():
        _, kind, *rest = line.split()
        if kind == 'msg':
            out.append([int(rest[0], 16), 0])
        elif out and (kind == 'wait' or (kind == 'close' and rest[0] == '00')):
            out[-1][1] += 1
    return [tuple(x) for x in out]


def pages(messages, pauses):
    return {int(k, 16): (1 if int(k, 16) in pauses else parts.count(PAGE) + 1) for k, parts in messages.items()}


def judge(seen, page_of):
    """쪽 수를 넘은 메시지 [(번호, 받은 A, 쪽 수)]. 쪽 수를 모르는 메시지(DQ5 원래 메시지 등)는 보지 않는다."""
    return [(m, a, page_of[m]) for m, a in seen if m in page_of and a > page_of[m]]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--rom', required=True, type=Path)
    ap.add_argument('--messages', required=True, type=Path)
    ap.add_argument('--states', required=True, type=Path)
    ap.add_argument('--out', required=True, type=Path)
    args = ap.parse_args()
    mesence = Path(os.environ['MESENCE'])
    out = args.out.resolve()
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f'{out} is not empty')
    rom = args.rom.resolve()
    messages = json.loads(args.messages.read_text(encoding='utf-8'))['messages']
    # 덧붙인 메시지는 옮긴 일본어 메시지, 1장 사건, 2장 사건 차례라 1장 사건의 첫 번호를 뒤에서 센다
    added = sum(1 for k in messages if int(k, 16) >= dq4npcport.FIRST_MESSAGE)
    first = dq4npcport.FIRST_MESSAGE + added - len(ev.MESSAGES) - len(ch2.texts(0))
    page_of = pages(messages, ev.pauses(first))
    seq = ','.join(f'y@{f}:2' for f in range(900, 1600, 150))
    pc.run(mesence, rom, pc.MKSTATE, out / 'start', {'SAVEAT': str(pc.START_AT), 'STATE': 'start.mss',
                                                      'MAXF': str(pc.START_AT + 10), 'EVERY': '0', 'PERIOD': '40',
                                                      'TAP': 'a', 'TAPUNTIL': str(pc.TAP_UNTIL), 'SEQ': seq}, 200)
    pc.run(mesence, rom, PROBE, out / 'prologue', {'STATE': str(out / 'start' / 'start.mss'), 'WALKLUA': str(pc.WALK),
                                                    'WAYPOINTS': ';'.join(w for _, w in pc.ROUTE), 'MAXF': '16000',
                                                    'CHANGES': str(len(pc.MAPS) + 8)}, 600)
    # 왕 구간은 걷기 검사의 구간 실행을 그대로 쓰고 걷기 프로브만 감싼다
    os.environ['WALKLUA'] = str(walk.WALK_STATE)
    walk.WALK_STATE = PROBE
    sys.argv = ['dq4ch1walkcheck', '--rom', str(rom), '--out', str(out / 'king'), '--from', 'king', '--until', 'king',
                '--states', str(args.states.resolve())]
    walk.main()
    report = {'status': 'passed', 'scenes': {}}
    for scene, path in (('prologue', out / 'prologue' / 'msgcount.txt'),
                        ('king', next((out / 'king').rglob('msgcount.txt'), None))):
        if not path or not path.exists():
            report['status'] = 'failed'
            report['scenes'][scene] = '기록 없음'
            continue
        seen = counts(path.read_text())
        bad = judge(seen, page_of)
        report['scenes'][scene] = {'messages': len(seen), 'over': [f'{m:03X} A{a} > {p}쪽' for m, a, p in bad]}
        if bad or not seen:
            report['status'] = 'failed'
    (out / 'results.json').write_text(json.dumps(report, ensure_ascii=False, indent=1) + '\n')
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report['status'] == 'passed' else 1


if __name__ == '__main__':
    sys.exit(main())
