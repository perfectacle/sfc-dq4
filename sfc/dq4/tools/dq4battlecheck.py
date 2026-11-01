"""1장 롬에서 정한 곳·정한 무리로 걸음 전투를 붙여 이기고 맵으로 돌아오는지 보는 검사(MesenCE 헤드리스).

조우 루틴 23:E7C2(부르는 곳은 00:82B4 의 JSL 하나)를 「무리를 7E:1001~100C 에 쓰고 carry 를 켜 돌아옴」으로 덮어,
맵에 조우율이 있으면 첫 걸음에 그 무리와 싸운다(force_patch). 무리의 몬스터는 HP 1·수비 0 으로 덮고 주인공 HP 를
999 로 묶어, A 를 누르기만 하면 이긴다. 장면마다 1장 걷기 검사(dq4ch1walkcheck.py)의 서장 끝 세이브스테이트에서
순간이동·걷기로 자리를 잡고(조우 없음), 난수 7E:075B~075D·시각을 정한 값으로 둔 뒤 lua/dq4battle.lua 로 한 걸음
내딛는다. 본다:
  - 전투가 걸린 때(01:860D)의 7E:1001~1008 이 정한 무리
  - 이긴 뒤 금화가 무리 몬스터 금화의 합(몬스터 표 23:8000 의 바이트7 + 바이트8 bit2-3)을 dq4balance.reward 로 고친
    만큼 늚. 도망(필드에서 명령 창 아래 → A)은 금화가 그대로
  - 전투가 끝나(00:82BE) 돌아온 맵·$BE·칸(필드면 필드 좌표)·곡($1D8B)이 전투가 걸린 때와 같음
  - 돌아온 화면이 전투가 걸린 때의 맵 화면과 픽셀 90% 이상 같음, 그 뒤 걸으면 자리가 바뀜(전투가 끝나면 조우
    루틴을 CLC/RTL 로 되돌려 다시 걸리지 않게 함)
  - --repeat 2 면 같은 장면을 두 번 돌려 battle.txt 가 바이트째 같음

  MESENCE=… LIBDIR=… python sfc/dq4/tools/dq4battlecheck.py --rom work/ch1/dq4-ch1-full.sfc --out work/battlecheck \\
      [--base work/ch1walk/prologue/end.mss] [--repeat 2] [--seed N | --seeds 0,5,9] [--no-state-cache]
  --base 가 없으면 서장 끝 상태를 dq4ch1walkcheck.prologue 로 얻는다(롬 SHA-1 별 캐시 work/cache/states/prologue, 서장은 시드 0).
  시드는 자리 잡기와 전투 시작의 난수(dq4ch1walkcheck.rng_for)만 바꾼다. 여러 시드면 seed-N/ 아래에 장면 폴더.
형식은 sfc/dq4/docs/dq4-chapter1-format.md 「검증」.
"""
import argparse
import concurrent.futures
import hashlib
import json
import os
import re
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import dq4balance  # noqa: E402
import dq4ch1walkcheck as wc  # noqa: E402

BATTLE = HERE / 'lua' / 'dq4battle.lua'
ENCOUNTER = 0x11E7C2        # 23:E7C2 파일 오프셋
GROUP = 0x7E1001
# 장면: 자리 잡기(dq4ch1walkcheck 구간 꼴), 내딛는 쪽, 무리 [(몬스터, 마릿수)], 돌아온 뒤 걸어 볼 쪽,
# 전투(이름: 전투 동안 차례로 누를 버튼). win 은 A 만 눌러 이기고, flee 는 명령 창에서 아래 → A(にげる).
# 필드는 성 마을 아래 끝으로 걸어 나간 곳(조우 구역은 지형으로), 탑 39/01 은 FC 던전 구역(dq4dungeonrate 훅 자리).
# 자리 잡기 앞에는 1장 걷기 검사가 그 구간에 이르렀을 때의 깃발·동료·물건을 둔다(dq4ch1walkcheck.setup, 'after')
SCENES = {
    'field': {'after': 'shoes', 'prep': [('castle_town', 'warp', '36/00,16,72', {'map': '36/00'}),
                                         ('field', 'walk', '16,71;28,71;28,81;down:120', {'field': True})],
              'step': 'down', 'group': [(0x00, 2)], 'move': 'up', 'battles': {'win': 'a', 'flee': 'down,a'}},
    'tower': {'after': 'kidnap', 'prep': [('tower', 'warp', '39/01,20,16', {'map': '39/01'})],
              'step': 'down', 'group': [(0x12, 1), (0x1E, 1)], 'move': 'up', 'battles': {'win': 'a'}},
}


def force_patch(group):
    """23:E7C2 를 PHP / REP #$20 / (LDA #w / STA $7E:1001+2k) × 6 / PLP / SEC / RTL 로 덮는 ROMPATCH.
    1001~1004 몬스터(빈 자리 FF), 1005~1008 마릿수, 1009~100C 무리 값 0."""
    if not 1 <= len(group) <= 4:
        raise ValueError('무리는 1~4종')
    monsters = [m for m, _ in group] + [0xFF] * (4 - len(group))
    counts = [c for _, c in group] + [0] * (4 - len(group))
    data = monsters + counts + [0] * 4
    code = bytearray((0x08, 0xC2, 0x20))
    for k in range(6):
        addr = GROUP + 2 * k
        code += bytes((0xA9, data[2 * k], data[2 * k + 1], 0x8F, addr & 0xFF, addr >> 8 & 0xFF, addr >> 16))
    code += bytes((0x28, 0x38, 0x6B))
    return f'{ENCOUNTER:X}={code.hex().upper()}'


def weak_patch(rom, monsters):
    """몬스터들을 HP 1·수비 0 으로 덮는 ROMPATCH(dq4ch1walkcheck.boss_patch 와 같은 바이트)."""
    out = []
    for n in sorted(set(monsters)):
        base = wc.MONSTERS + n * 25
        out += [f'{base + 2:X}=00', f'{base + 3:X}=01', f'{base + 8:X}={rom[base + 8] & ~0x40 & 0xFF:02X}',
                f'{base + 10:X}={rom[base + 10] & ~0x07 & 0xFF:02X}']
    return ';'.join(out)


def gold(rom, group):
    """무리를 다 쓰러뜨리면 받는 금화: 몬스터마다 바이트7 + 바이트8 bit2-3 << 8 을 마릿수만큼 더하고,
    승리 처리 훅(dq4balance.reward)이 4/3 배로 고친 값."""
    total = 0
    for n, count in group:
        base = wc.MONSTERS + n * 25
        total += (rom[base + 7] | (rom[base + 8] >> 2 & 3) << 8) * count
    return dq4balance.reward(total)


def parse(text):
    """battle.txt 의 단계 줄을 {단계: {키: 값}} 으로."""
    out = {}
    for line in text.splitlines():
        what, *rest = line.split(' ')
        out[what] = dict(kv.split('=', 1) for kv in rest if '=' in kv)
    return out


def group_bytes(group):
    monsters = [m for m, _ in group] + [0xFF] * (4 - len(group))
    counts = [c for _, c in group] + [0] * (4 - len(group))
    return bytes(monsters).hex().upper(), bytes(counts).hex().upper()


def same_pixels(a, b, shift=8):
    """두 그림에서 RGB 가 같은 픽셀의 비율. 전투가 걸린 프레임(01:860D)은 걸음이 몇 픽셀 남은 때라, b 를 가로나
    세로로 shift 픽셀 안에서 밀어 가장 잘 맞는 비율을 낸다(가장자리 shift 픽셀은 빼고 견줌)."""
    from PIL import Image
    x, y = Image.open(a).convert('RGB'), Image.open(b).convert('RGB')
    if x.size != y.size:
        return 0.0
    w, h = x.size
    inner = x.crop((shift, shift, w - shift, h - shift)).tobytes()
    best = 0.0
    for dx, dy in {(d, 0) for d in range(-shift, shift + 1)} | {(0, d) for d in range(-shift, shift + 1)}:
        moved = y.crop((shift + dx, shift + dy, w - shift + dx, h - shift + dy)).tobytes()
        same = sum(inner[i:i + 3] == moved[i:i + 3] for i in range(0, len(inner), 3))
        best = max(best, same / (len(inner) // 3))
    return best


def judge(rom, scene, stages, dest, kind='win'):
    """kind 가 win 이면 금화가 무리 금화만큼, flee 면 그대로여야 한다."""
    problems = []
    start, after, moved = stages.get('start'), stages.get('after'), stages.get('moved')
    if start is None:
        return ['전투가 걸리지 않음']
    want_group, want_count = group_bytes(scene['group'])
    if (start['group'], start['count']) != (want_group, want_count):
        problems.append(f"무리 {start['group']}/{start['count']}, 기대 {want_group}/{want_count}")
    if after is None:
        return problems + ['전투에서 돌아오지 않음']
    earned = int.from_bytes(bytes.fromhex(after['gold']), 'little') - int.from_bytes(bytes.fromhex(start['gold']), 'little')
    want = gold(rom, scene['group']) if kind == 'win' else 0
    if earned != want:
        problems.append(f'금화 +{earned}, 기대 +{want}')
    keys = ('map', 'BE', 'song') + (('cell',) if int(start['BE'], 16) & 0x80 else ('field',))
    for k in keys:
        if after[k] != start[k]:
            problems.append(f'돌아온 {k} {after[k]}, 전투 전 {start[k]}')
    ratio = same_pixels(dest / 'start.png', dest / 'after.png')
    if ratio < 0.9:
        problems.append(f'돌아온 화면이 전투 전과 {ratio:.0%} 만 같음')
    if moved is None or all(moved[k] == after[k] for k in keys[3:]):
        problems.append('돌아온 뒤 걷지 못함')
    return problems


def run_scene(mesence, rom, data, base, out, name, scene, rounds, seed=0):
    """자리를 잡고(조우 없음) 그 세이브스테이트에서 전투마다 rounds 번 돌린다."""
    dest = out / name
    state = base
    names = [s[0] for s in wc.SEGMENTS]
    extra, party = wc.setup(wc.SEGMENTS, names.index(scene['after']) + 1)
    for k, seg in enumerate(scene['prep']):
        r = wc.segment(mesence, rom, state, dest / seg[0], seg, wc.NO_ENCOUNTERS,
                       *((extra, party) if k == 0 else ('', '')), seed)
        if r['status'] != 'passed':
            return [{'name': name, 'seed': seed, 'status': 'failed', 'problems': [f'자리 잡기 {seg[0]}: {r["problems"]}']}]
        state = dest / seg[0] / 'end.mss'
    patch = ';'.join((force_patch(scene['group']), weak_patch(data, [m for m, _ in scene['group']])))
    results = []
    for kind, keys in scene['battles'].items():
        runs = []
        for i in range(rounds):
            run_dir = dest / f'{kind}{i + 1}'
            wc.run(mesence, rom, BATTLE, run_dir, {'STATE': str(state), 'ROMPATCH': patch, 'AFTERPATCH': wc.NO_ENCOUNTERS,
                                                    'SET': f'{wc.rng_for(seed)};{wc.DAY_SET}', 'POKE': wc.HERO_HP,
                                                    'STEP': scene['step'], 'KEYS': keys, 'MOVE': scene['move'],
                                                    'MAXF': '6000'}, 300)
            log = run_dir / 'battle.txt'
            text = log.read_text(encoding='utf-8') if log.exists() else ''
            stages = parse(text)
            runs.append({'trace': hashlib.sha1(text.encode()).hexdigest()[:12], 'stages': stages,
                         'problems': judge(data, scene, stages, run_dir, kind)})
        problems = [p for r in runs for p in r['problems']]
        if len({r['trace'] for r in runs}) > 1:
            problems.append('같은 입력의 실행끼리 다름: ' + ', '.join(r['trace'] for r in runs))
        first = runs[0]['stages']
        frames = int(first['after']['f']) - int(first['start']['f']) if 'after' in first and 'start' in first else None
        results.append({'name': f'{name}-{kind}', 'seed': seed, 'status': 'failed' if problems else 'passed', 'problems': problems,
                        'traces': [r['trace'] for r in runs], 'start': first.get('start'), 'after': first.get('after'),
                        'battle_frames': frames})
    return results


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--rom', required=True, type=Path)
    ap.add_argument('--out', required=True, type=Path)
    ap.add_argument('--base', type=Path, help='서장 끝 세이브스테이트(같은 롬의 dq4ch1walkcheck.py prologue/end.mss). 없으면 만든다')
    ap.add_argument('--repeat', type=int, default=2, help='장면마다 전투를 같은 세이브스테이트에서 몇 번 돌릴지')
    ap.add_argument('--scenes', help='쉼표로 고른 장면만')
    ap.add_argument('--jobs', type=int, default=4)
    wc.add_seed_args(ap)
    args = ap.parse_args()
    seeds = wc.seeds_of(args)
    mesence = Path(os.environ['MESENCE'])
    out = args.out.resolve()
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f'{out} is not empty')
    out.mkdir(parents=True, exist_ok=True)
    rom = out / 'c.sfc'
    shutil.copyfile(args.rom.resolve(), rom)
    data = rom.read_bytes()
    pro = None
    if args.base:
        base = args.base.resolve()
    else:
        cache = None if args.no_state_cache else wc.StateCache(data)
        base, pro = wc.prologue(mesence, rom, data, out, wc.SEGMENTS, cache)
        if pro['status'] != 'passed':
            raise SystemExit(f'서장 실패: {pro["problems"]}')
    names = args.scenes.split(',') if args.scenes else list(SCENES)
    work = [(s, n) for s in seeds for n in names]
    with concurrent.futures.ThreadPoolExecutor(args.jobs) as pool:
        results = [r for rs in pool.map(lambda w: run_scene(mesence, rom, data, base, wc.seed_dir(out, w[0], seeds), w[1],
                                                            SCENES[w[1]], args.repeat, w[0]), work) for r in rs]
    for r in results:
        print(json.dumps(r, ensure_ascii=False))
    per_seed = [{'seed': s, 'rng': wc.rng_for(s),
                 'status': 'passed' if all(r['status'] == 'passed' for r in results if r['seed'] == s) else 'failed',
                 'scenes': [r for r in results if r['seed'] == s]} for s in seeds]
    ok = all(r['status'] == 'passed' for r in per_seed)
    report = {'status': 'passed' if ok else 'failed',
              'state_cache': 'off' if pro is None or args.no_state_cache else 'hit' if pro.get('cached') else 'miss',
              'seeds': per_seed}
    if len(seeds) == 1:
        report.update(seed=seeds[0], rng=per_seed[0]['rng'], scenes=per_seed[0]['scenes'])
    (out / 'results.json').write_text(json.dumps(report, ensure_ascii=False, indent=1) + '\n')
    print(json.dumps({'status': report['status'], 'seeds': {r['seed']: r['status'] for r in per_seed}}))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
