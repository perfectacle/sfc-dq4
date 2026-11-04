"""전투 큰 그림 길($0DF3 ≠ 0)이 주문·공격 연출 동안 얼마나 이어지는지, 그때 창 글자 대기열에 항목이 있는지 재는 검사
(MesenCE 헤드리스). 형식은 sfc/dq4/docs/dq4-window-text-format.md 「NMI 작업마다 걸기」.

전투 NMI 작업 00:8952 는 $0DF3 이 0 이 아니면 큰 그림 길(00:895D)로 가 그 NMI 에 큰 그림 하나를 보내고 $0DF3 을 지운다.
이 길에는 WqNmiEntry 를 걸지 않았으므로(dq4windowname) 그동안 대기열 항목은 보통 길 NMI 까지 기다린다. 큰 그림 길
NMI 가 잇달아 이어진 길이가 곧 대기열이 늦어지는 NMI 수의 상한이다.

장면마다 dq4battlecheck 와 같이 서장 끝 상태에서 자리를 잡고(1장 걷기 검사의 깃발·동료) 조우 루틴을 정한 무리로 덮어
걸음 전투를 붙인다. 몬스터 능력치는 고치지 않아(주문을 쓰도록) 주인공 HP 만 묶고 A 를 눌러 싸운다. lua/dq4bigpic.lua 가
NMI 마다 작업·$0DF3·대기열 항목 수와 전투 메시지 번호를 남기고 lua/dq4battle.lua 를 그대로 돌린다. 같은 상태·난수로
REPEAT 번 돌려 기록이 같아야 한다.

큰 그림 길 NMI 에 대기열이 비어 있으면 항목 하나를 넣어(INJECT 번까지) 몇 NMI 뒤에 나가는지도 잰다.

통과 조건: 큰 그림 길이 이어진 길이와 넣은 항목이 나가기까지의 NMI 수가 모두 LIMIT 이하이고, 넣은 항목이 모두 나감.
게임이 큰 그림 길 NMI 에 대기열 항목을 두고 있었으면 그 덩어리를 보고에 적는다.

  MESENCE=… LIBDIR=… python sfc/dq4/tools/dq4bigpiccheck.py --rom work/ch1/dq4-ch1-full.sfc --out work/bigpic
"""
import argparse
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[1] / 'dq5' / 'tools')]

import dq4battlecheck as bc  # noqa: E402
import dq4ch1walkcheck as wc  # noqa: E402

PROBE = HERE / 'lua' / 'dq4bigpic.lua'
BATTLE_TASK = 0x8952
LIMIT = 8
REPEAT = 2
INJECT = 40
# 무리: まほうつかい(12, メラ)·ホイミスライム(1E, ホイミ)·スカルサーペント(0B)·おばけキノコ(30)·バブルスライム(09).
# 탑 장면은 호이민이 일행에 든 뒤라 호이민의 ホイミ 도 나온다
SCENES = {
    'tower': {'after': 'kidnap', 'prep': [('tower', 'warp', '39/01,20,16', {'map': '39/01'})], 'step': 'down',
              'group': [(0x12, 1), (0x1E, 1)]},
    'field': {'after': 'shoes', 'prep': bc.FIELD_PREP, 'step': 'down', 'group': [(0x12, 1), (0x0B, 1), (0x30, 1)]},
    'slimes': {'after': 'shoes', 'prep': bc.FIELD_PREP, 'step': 'down', 'group': [(0x09, 1), (0x1E, 1)]},
}


def parse(text):
    """nmi.txt → ([(프레임, 0DF3, 항목 수)] 전투 작업 NMI 만, [(프레임, 메시지)], [(넣은 NMI, 나간 NMI)])."""
    nmis, msgs, injects = [], [], []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) == 3 and parts[1] == 'msg':
            msgs.append((int(parts[0]), int(parts[2], 16)))
        elif len(parts) == 4 and parts[1] == 'inj':
            injects.append((int(parts[2]), int(parts[3])))
        elif len(parts) == 4 and int(parts[1], 16) == BATTLE_TASK:
            nmis.append((int(parts[0]), int(parts[2], 16), int(parts[3])))
    return nmis, msgs, injects


def runs(nmis, msgs):
    """큰 그림 길이 이어진 덩어리마다 {첫 프레임, 길이, 0DF3 값들, 대기열 항목이 있던 NMI 수, 바로 앞 메시지}."""
    out, cur = [], None
    for frame, kind, count in nmis + [(None, 0, 0)]:
        if kind:
            if cur is None:
                before = [m for f, m in msgs if f <= frame]
                cur = {'frame': frame, 'length': 0, 'kinds': [], 'queued': 0,
                       'message': f'{before[-1]:03X}' if before else None}
            cur['length'] += 1
            cur['kinds'].append(f'{kind:02X}')
            cur['queued'] += count > 0          # -1 은 검사가 넣은 항목이 있는 동안
        elif cur is not None:
            out.append(cur)
            cur = None
    return out


def judge(found, injects):
    """(가장 긴 덩어리, 가장 긴 기다림, 문제). 기다림 = 나간 NMI − 넣은 NMI(다음 NMI 에 나가면 1)."""
    longest = max((r['length'] for r in found), default=0)
    waits = [b - a for a, b in injects]
    problems = [f'큰 그림 길 {r["length"]} NMI 이어짐(프레임 {r["frame"]}, 앞 메시지 {r["message"]})'
                for r in found if r['length'] > LIMIT]
    problems += [f'넣은 항목이 {w} NMI 뒤에 나감' for w in waits if w > LIMIT]
    if len(injects) < INJECT:
        problems.append(f'넣은 항목이 나간 것 {len(injects)}번(기대 {INJECT})')
    return longest, max(waits, default=0), problems


def same_prefix(texts):
    """실행마다 기록의 SHA-1 앞 12자리. 기록은 일정 프레임마다 다시 써 실행이 멈춘 때에 따라 끝이 잘리므로, 모든 실행이
    가진 마지막 프레임까지만 견준다."""
    def frames(text):
        return [(int(line.split()[0]), line) for line in text.splitlines() if line.split()]
    rows = [frames(t) for t in texts]
    last = min((r[-1][0] for r in rows if r), default=0)
    return [hashlib.sha1('\n'.join(line for f, line in r if f < last).encode()).hexdigest()[:12] for r in rows]


def run_scene(mesence, rom, data, base, out, name, scene, seed):
    dest = out / name
    state = base
    names = [s[0] for s in wc.SEGMENTS]
    extra, party = wc.setup(wc.SEGMENTS, names.index(scene['after']) + 1)
    for k, seg in enumerate(scene['prep']):
        r = wc.segment(mesence, rom, state, dest / seg[0], seg, wc.NO_ENCOUNTERS,
                       *((extra, party) if k == 0 else ('', '')), seed, readset=True)
        if r['status'] != 'passed':
            return {'name': name, 'status': 'failed', 'problems': [f'자리 잡기 {seg[0]}: {r["problems"]}']}
        state = dest / seg[0] / 'end.mss'
    texts, found, nmis_seen, msgs_seen = [], None, 0, 0
    for i in range(REPEAT):
        run_dir = dest / f'run{i + 1}'
        wc.run(mesence, rom, PROBE, run_dir, {
            'NEXT': str(bc.BATTLE), 'STATE': str(state), 'ROMPATCH': bc.force_patch(scene['group']),
            'AFTERPATCH': wc.NO_ENCOUNTERS, 'SET': f'{wc.rng_for(seed)};{wc.DAY_SET}', 'POKE': wc.HERO_HP,
            'STEP': scene['step'], 'KEYS': 'a', 'MOVE': 'up', 'MAXF': '20000', 'KANATABLE': bc.kana_range(),
            'INJECT': str(INJECT)}, 1500)
        text = (run_dir / 'nmi.txt').read_text() if (run_dir / 'nmi.txt').exists() else ''
        texts.append(text)
        if found is None:
            nmis, msgs, injects = parse(text)
            found, nmis_seen, msgs_seen = runs(nmis, msgs), len(nmis), len(msgs)
            ended = 'after' in bc.parse((run_dir / 'battle.txt').read_text(encoding='utf-8')) \
                if (run_dir / 'battle.txt').exists() else False
    longest, waited, problems = judge(found, injects)
    if not nmis_seen:
        problems.append('전투 NMI 기록이 없음')
    if not ended:
        problems.append('전투가 끝나 맵으로 돌아오지 않음')
    traces = same_prefix(texts)
    if len(set(traces)) > 1:
        problems.append('같은 입력의 실행끼리 기록이 다름: ' + ', '.join(traces))
    return {'name': name, 'status': 'failed' if problems else 'passed', 'problems': problems, 'battle_nmis': nmis_seen,
            'messages': msgs_seen, 'longest': longest, 'runs': len(found), 'injected': len(injects),
            'longest_wait': waited, 'waits': sorted({b - a for a, b in injects}),
            'queued_runs': [r for r in found if r['queued']], 'lengths': sorted({r['length'] for r in found}),
            'traces': traces, 'detail': found}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--rom', required=True, type=Path)
    ap.add_argument('--out', required=True, type=Path)
    ap.add_argument('--base', type=Path, help='서장 끝 세이브스테이트(같은 롬). 없으면 만든다(캐시)')
    ap.add_argument('--scenes', help='쉼표로 고른 장면만')
    ap.add_argument('--seed', type=int, default=0)
    ap.add_argument('--jobs', type=int, default=1)
    args = ap.parse_args()
    mesence = Path(os.environ['MESENCE'])
    out = args.out.resolve()
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f'{out} is not empty')
    out.mkdir(parents=True, exist_ok=True)
    rom = out / 'c.sfc'
    shutil.copyfile(args.rom.resolve(), rom)
    data = rom.read_bytes()
    if args.base:
        base = args.base.resolve()
    else:
        # 서장은 읽은 바이트 캐시를 거치지 않는다. 캐시를 거치면 서장 걷기의 출력(end.mss)이 남지 않아 실패한다(dq4readset)
        base, pro = wc.prologue(mesence, rom, data, out, wc.SEGMENTS, wc.StateCache(data), readset=False)
        if pro['status'] != 'passed':
            raise SystemExit(f'서장 실패: {pro["problems"]}')
    names = args.scenes.split(',') if args.scenes else list(SCENES)
    with concurrent.futures.ThreadPoolExecutor(args.jobs) as pool:
        results = list(pool.map(lambda n: run_scene(mesence, rom, data, base, out, n, SCENES[n], args.seed), names))
    ok = all(r['status'] == 'passed' for r in results)
    report = {'status': 'passed' if ok else 'failed', 'limit': LIMIT, 'rom': str(args.rom), 'scenes': results}
    (out / 'results.json').write_text(json.dumps(report, ensure_ascii=False, indent=1) + '\n')
    for r in results:
        print(json.dumps({k: v for k, v in r.items() if k != 'detail'}, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
