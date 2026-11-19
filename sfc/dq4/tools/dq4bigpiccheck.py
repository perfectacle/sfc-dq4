"""전투 큰 그림 길($0DF3 ≠ 0)이 주문·공격 연출 동안 얼마나 이어지는지, 그때 창 글자 대기열에 항목이 있는지 재는 검사
(MesenCE 헤드리스). 형식은 sfc/dq4/docs/dq4-window-text-format.md 「NMI 작업마다 걸기」.

전투 NMI 작업 00:8952 는 $0DF3 이 0 이 아니면 큰 그림 길(00:895D)로 가 그 NMI 에 큰 그림 하나를 보내고 $0DF3 을 지운다.
이 길에는 WqNmiEntry 를 걸지 않았으므로(dq4windowname) 그동안 대기열 항목은 보통 길 NMI 까지 기다린다. 큰 그림 길
NMI 가 잇달아 이어진 길이가 곧 대기열이 늦어지는 NMI 수의 상한이다.

장면마다 dq4battlecheck 와 같이 서장 끝 상태에서 자리를 잡고(1장 걷기 검사의 깃발·동료) 조우 루틴을 정한 무리로 덮어
걸음 전투를 붙인다. 몬스터 능력치는 고치지 않아(주문을 쓰도록) 주인공 HP 만 묶고 A 를 눌러 싸우다가, FINISH_AT 프레임부터 몬스터 HP 를 1 로
묶어 전투를 끝낸다. lua/dq4bigpic.lua 가
NMI 마다 작업·$0DF3·대기열 항목 수와 전투 메시지 번호를 남기고 lua/dq4battle.lua 를 그대로 돌린다. 같은 상태·난수로
REPEAT 번 돌려 기록이 같아야 한다.

큰 그림 길 NMI 에 대기열이 비어 있으면 항목 하나를 넣어(INJECT 번까지) 몇 NMI 뒤에 나가는지도 잰다.

공격 효과는 22:EA2A 가 무기($0DA7)·회심($0DA8)으로 고른 하위 스크립트 번호($9E74)대로 큰 그림을 요청한다. 원본 DQ5 와
같은 바이트코드라 그 길이는 엔진이 정한 것이고 하위 스크립트마다 다르다(원본 실측 2~20 NMI). 그래서 하위 스크립트를 고른 뒤
첫 전투 메시지까지 시작한 큰 그림 길은 원본 DQ5 에서 같은 하위 스크립트가 낸 가장 긴 길(ORIG_TABLE)과 견주고, 그 밖의
길(전투 시작·주문·회복 등)만 LIMIT 와 견준다.

통과 조건(장면마다): 하위 스크립트의 길은 원본 길이 이하, 그 밖의 길은 LIMIT 이하, 넣은 항목은 넣은 길이 끝난 뒤
AFTER NMI 안에 나감(길 동안의 기다림은 그 길의 남은 길이만 받음), 넣은 항목이 INJECT 개
모두 나감(넣기 전 VRAM 이 그 그림과 달랐다가 항목 수가 0 이 된 때 같음), 모든 실행이 전투를 끝내 맵으로 돌아옴(battle.txt 의
after), REPEAT 번 돌린 기록(nmi.txt) 전체가 같음. 게임이 큰 그림 길 NMI 에 대기열 항목을 두고 있었으면 그 덩어리를 보고에
적는다.

--subscripts 는 장면 대신 들판 전투의 첫 공격에서 하위 스크립트를 SUBSCRIPTS 하나씩으로 바꿔(lua SUBSCRIPT) 그 효과만 돌리고,
가장 긴 길이 원본 길이와 같아야 통과한다(결정적: 무기·회심·난수와 상관없이 모든 하위 스크립트를 밟음). 원본 길이 표는
--measure-original 이 원본 DQ5 롬과 전투 중 세이브스테이트로 같은 강제를 걸어 다시 재고, 표와 다르면 실패한다(--write 면 표를
고쳐 씀). 원본 롬·상태는 CI 에 없어 이 명령은 로컬에서만 돈다.

  MESENCE=… LIBDIR=… python sfc/dq4/tools/dq4bigpiccheck.py --rom work/ch1/dq4-ch1-full.sfc --out work/bigpic
  MESENCE=… LIBDIR=… python sfc/dq4/tools/dq4bigpiccheck.py --rom work/ch1/dq4-ch1-full.sfc --out work/bigpic-sub --subscripts
  MESENCE=… LIBDIR=… python sfc/dq4/tools/dq4bigpiccheck.py --measure-original --dq5-rom rom/dq5.sfc \
      --dq5-state <원본 DQ5 전투 중 .mss> --out work/bigpic-orig
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tomllib

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[1] / 'dq5' / 'tools')]

import dq4battlecheck as bc  # noqa: E402
import dq4ch1walkcheck as wc  # noqa: E402
import dq4shards  # noqa: E402

PROBE = HERE / 'lua' / 'dq4bigpic.lua'
ORIG_DRIVER = HERE / 'lua' / 'dq4bigpicorig.lua'
ORIG_TABLE = HERE.parent / 'bigpic-orig.toml'
BATTLE_TASK = 0x8952
# 하위 스크립트 밖의 길(전투 시작·주문·회복)의 실측 최댓값이라 여유가 없다. 넘으면 기준을 올리기 전에 어느 연출이
# 길어졌는지 본다
LIMIT = 8
# 넣은 항목은 보통 넣은 큰 그림 길이 끝난 뒤 첫 보통 길 NMI 에 나간다. 그 NMI 에 전투 메시지가 뜨기 시작하면 하나,
# 전투 첫머리(탑·들판·슬라임 모두 프레임 120~143 의 한 NMI 길 뒤)에는 셋 늦게 나갔다(실측 최댓값, 여유 없음).
# 그보다 늦으면 대기열 게이트가 길 뒤의 보통 길 NMI 를 놓친 것
AFTER = 3
# 무기 표 24:F8BD 의 값(짝수)과 회심(+2)으로 나올 수 있는 하위 스크립트 번호 전부
SUBSCRIPTS = tuple(range(0x00, 0x34, 2))
SUB_MAXF = 2400
# 맞는 몬스터의 그림에 따라 요청 수가 달라 원본과 맞대어 비교할 수 없는 하위 스크립트(해킹 롬은 몬스터 그림이 바뀜).
# 이 길은 LIMIT 와 견주고, 결과에 미측정으로 까닭과 함께 찍는다
UNMATCHED = {0x32: '맞는 몬스터 그림에 따라 요청 수가 달라짐(해킹 롬 들판 0B·1E 7, 09 9, 30 11, 원본 전투 상태 5 NMI)'}
REPEAT = 2
INJECT = 40
# 이 프레임부터 몬스터 HP 를 1 로 묶어(lua/dq4bigpic.lua FINISH_AT) 전투를 몇 턴 안에 끝낸다. 회복 주문을 쓰는 무리와의
# 전투 길이는 난수 걸음이라, 전투와 상관없는 롬 변화로 난수 소비가 바뀌기만 해도 MAXF 를 넘을 수 있다(같은 롬이면 늘 같음).
# FINISH_AT 은 넣은 항목이 다 나간 뒤로 넉넉히, MAXF 는 묶은 뒤 남은 몬스터를 다 쓰러뜨릴 만큼 그 뒤로 둔다
FINISH_AT = 10000
MAXF = 20000
# 무리: まほうつかい(12, メラ)·ホイミスライム(1E, ホイミ)·スカルサーペント(0B)·おばけキノコ(30)·バブルスライム(09).
# 탑 장면은 호이민이 일행에 든 뒤라 호이민의 ホイミ 도 나온다
SCENES = {
    'tower': {'after': 'kidnap', 'prep': [('tower', 'warp', '39/01,20,16', {'map': '39/01'})], 'step': 'down',
              'group': [(0x12, 1), (0x1E, 1)]},
    'field': {'after': 'shoes', 'prep': bc.FIELD_PREP, 'step': 'down', 'group': [(0x12, 1), (0x0B, 1), (0x30, 1)]},
    'slimes': {'after': 'shoes', 'prep': bc.FIELD_PREP, 'step': 'down', 'group': [(0x09, 1), (0x1E, 1)]},
}
# 하위 스크립트를 강제하는 들판 전투. 몬스터마다 되풀이하는 하위 스크립트(30 등)가 있어 원본 상태와 같이 한 마리로 둔다
SUB_SCENE = dict(SCENES['field'], group=[(0x12, 1)])


def parse(text):
    """nmi.txt → ([(프레임, 0DF3, 항목 수)] 전투 작업 NMI 만, [(프레임, 메시지)],
    [(넣은 NMI, 나간 NMI, 넣기 전 VRAM 같음, 나간 뒤 VRAM 같음, 넣은 프레임)], [(프레임, 하위 스크립트)])."""
    nmis, msgs, injects, subs = [], [], [], []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) == 3 and parts[1] == 'msg':
            msgs.append((int(parts[0]), int(parts[2], 16)))
        elif len(parts) == 3 and parts[1] == 'sub':
            subs.append((int(parts[0]), int(parts[2], 16)))
        elif len(parts) == 10 and parts[1] == 'inj':
            injects.append((int(parts[2]), int(parts[3]), parts[5] == 'same', parts[7] == 'same', int(parts[9])))
        elif len(parts) == 4 and int(parts[1], 16) == BATTLE_TASK:
            nmis.append((int(parts[0]), int(parts[2], 16), int(parts[3])))
    return nmis, msgs, injects, subs


def effect_of(frame, msgs, subs):
    """frame 에 도는 공격 효과의 하위 스크립트 번호: 그 앞에 고른 하위 스크립트가 있고 그 뒤로 전투 메시지가 아직 없으면."""
    chosen = [(f, v) for f, v in subs if f <= frame]
    if not chosen:
        return None
    f0, v = chosen[-1]
    return None if any(f0 < f <= frame for f, _ in msgs) else v


def runs(nmis, msgs, subs=()):
    """큰 그림 길이 이어진 덩어리마다 {첫 프레임, 프레임들, 길이, 0DF3 값들, 대기열 항목이 있던 NMI 수, 바로 앞 메시지,
    하위 스크립트(공격 효과 밖이면 None)}."""
    out, cur = [], None
    for frame, kind, count in nmis + [(None, 0, 0)]:
        if kind:
            if cur is None:
                before = [m for f, m in msgs if f <= frame]
                cur = {'frame': frame, 'frames': [], 'length': 0, 'kinds': [], 'queued': 0,
                       'message': f'{before[-1]:03X}' if before else None, 'sub': effect_of(frame, msgs, subs)}
            cur['frames'].append(frame)
            cur['length'] += 1
            cur['kinds'].append(f'{kind:02X}')
            cur['queued'] += count > 0          # -1 은 검사가 넣은 항목이 있는 동안
        elif cur is not None:
            out.append(cur)
            cur = None
    return out


def load_orig(path=ORIG_TABLE):
    """원본 DQ5 하위 스크립트마다 {번호: (가장 긴 큰 그림 길, 효과 동안 큰 그림 NMI 합)}."""
    data = tomllib.loads(path.read_text(encoding='utf-8'))
    return {int(k, 16): (v, data['total'][k]) for k, v in data['longest'].items()}


def run_limit(run, orig):
    if run['sub'] is None or run['sub'] in UNMATCHED:
        return LIMIT
    return orig.get(run['sub'], (None,))[0]


def judge(found, injects, orig, inject_count=INJECT):
    """(가장 긴 덩어리, 가장 긴 기다림, 문제). 기다림 = 나간 NMI − 넣은 NMI. 넣은 항목은 넣은 길의 남은 NMI(넣은 NMI 포함)
    다음 보통 길 NMI 에 나가면 기다림이 남은 길이와 같다. 항목 수가 0 이 된 것만으로는 나갔다고 보지 않고, 넣기 전 VRAM 이
    그 그림과 달랐다가 나간 뒤 같아야 한다."""
    longest = max((r['length'] for r in found), default=0)
    problems = []
    for r in found:
        limit = run_limit(r, orig)
        where = f'프레임 {r["frame"]}, 앞 메시지 {r["message"]}'
        if limit is None:
            problems.append(f'하위 스크립트 {r["sub"]:02X} 의 원본 길이가 표에 없음({where})')
        elif r['length'] > limit:
            what = '' if r['sub'] is None else f', 하위 스크립트 {r["sub"]:02X} 원본 {limit}'
            problems.append(f'큰 그림 길 {r["length"]} NMI 이어짐({where}{what})')
    for a, b, before, after, at in injects:
        run = next((r for r in found if at in r['frames']), None)
        if run is None:
            problems.append(f'프레임 {at} 에 넣은 항목: 그 프레임이 큰 그림 길이 아님')
            continue
        remaining = len([f for f in run['frames'] if f >= at])
        if b - a > remaining + AFTER:
            problems.append(f'프레임 {at} 에 넣은 항목이 {b - a} NMI 뒤에 나감(길의 남은 NMI {remaining} + {AFTER})')
        if before:
            problems.append(f'NMI {a} 에 넣은 항목: 넣기 전부터 VRAM 이 그 그림과 같음')
        elif not after:
            problems.append(f'NMI {a} 에 넣은 항목: 항목 수는 0 이지만 VRAM 이 그 그림이 아님')
    if inject_count and len(injects) < inject_count:
        problems.append(f'넣은 항목이 나간 것 {len(injects)}번(기대 {inject_count})')
    return longest, max((i[1] - i[0] for i in injects), default=0), problems


def effect_runs(found, sub):
    return [r for r in found if r['sub'] == sub]


def prepare(mesence, rom, base, dest, scene, seed):
    """서장 끝 상태에서 장면 자리를 잡은 세이브스테이트 경로, 또는 실패 글."""
    state = base
    names = [s[0] for s in wc.SEGMENTS]
    extra, party = wc.setup(wc.SEGMENTS, names.index(scene['after']) + 1)
    for k, seg in enumerate(scene['prep']):
        r = wc.segment(mesence, rom, state, dest / seg[0], seg, wc.NO_ENCOUNTERS,
                       *((extra, party) if k == 0 else ('', '')), seed, readset=True)
        if r['status'] != 'passed':
            return None, f'자리 잡기 {seg[0]}: {r["problems"]}'
        state = dest / seg[0] / 'end.mss'
    return state, None


def battle_env(state, scene, seed, maxf):
    return {'NEXT': str(bc.BATTLE), 'STATE': str(state), 'ROMPATCH': bc.force_patch(scene['group']),
            'AFTERPATCH': wc.NO_ENCOUNTERS, 'SET': f'{wc.rng_for(seed)};{wc.DAY_SET}',
            'POKE': f'{wc.HERO_HP};{wc.rng_hold(seed)}', 'STEP': scene['step'], 'KEYS': 'a', 'MOVE': 'up',
            'MAXF': str(maxf), 'KANATABLE': bc.kana_range()}


def read_runs(run_dirs):
    """실행 폴더들의 nmi.txt → (기록들, 첫 실행의 (nmis, msgs, injects, subs))."""
    texts = [(d / 'nmi.txt').read_text() if (d / 'nmi.txt').exists() else '' for d in run_dirs]
    return texts, parse(texts[0])


def same_traces(texts, problems):
    traces = [hashlib.sha1(t.encode()).hexdigest()[:12] for t in texts]
    if len(set(traces)) > 1:
        problems.append('같은 입력의 실행끼리 기록이 다름: ' + ', '.join(traces))
    return traces


def run_scene(mesence, rom, data, base, out, name, scene, seed, orig, jobs=REPEAT):
    dest = out / name
    state, why = prepare(mesence, rom, base, dest, scene, seed)
    if why:
        return {'name': name, 'status': 'failed', 'problems': [why]}
    env = battle_env(state, scene, seed, MAXF) | {'INJECT': str(INJECT), 'FINISH_AT': str(FINISH_AT)}
    run_dirs = [dest / f'run{i + 1}' for i in range(REPEAT)]
    # 같은 입력을 되풀이하는 실행끼리는 서로 기다릴 것이 없으므로 함께 띄우고, 판정은 실행 번호 순서로 한다
    dq4shards.pmap(lambda d: wc.run(mesence, rom, PROBE, d, env, 1500), run_dirs, jobs)
    texts, (nmis, msgs, injects, subs) = read_runs(run_dirs)
    ended = [(d / 'battle.txt').exists() and 'after' in bc.parse((d / 'battle.txt').read_text(encoding='utf-8'))
             for d in run_dirs]
    found = runs(nmis, msgs, subs)
    longest, waited, problems = judge(found, injects, orig)
    if not nmis:
        problems.append('전투 NMI 기록이 없음')
    if not all(ended):
        problems.append(f'전투가 끝나 맵으로 돌아오지 않은 실행: {[i + 1 for i, e in enumerate(ended) if not e]}')
    # 실행은 전투가 끝난 뒤 같은 프레임에 멈추므로(dq4battle.lua) 기록 전체가 같아야 한다
    traces = same_traces(texts, problems)
    return {'name': name, 'status': 'failed' if problems else 'passed', 'problems': problems, 'battle_nmis': len(nmis),
            'messages': len(msgs), 'longest': longest, 'runs': len(found), 'injected': len(injects),
            'longest_wait': waited, 'waits': sorted({i[1] - i[0] for i in injects}),
            'subscripts': sorted({f'{v:02X}' for _, v in subs}),
            'queued_runs': [r for r in found if r['queued']], 'lengths': sorted({r['length'] for r in found}),
            'traces': traces, 'detail': found}


def effect_shape(found, sub):
    """(가장 긴 길, 큰 그림 NMI 합): 효과가 낸 큰 그림 요청 수는 합으로, 대기열이 가장 오래 막히는 때는 가장 긴 길로 본다."""
    mine = effect_runs(found, sub)
    return max((r['length'] for r in mine), default=0), sum(r['length'] for r in mine)


def judge_effect(sub, nmis, msgs, injects, subs, orig):
    """하위 스크립트 하나를 강제한 실행: ((가장 긴 길, 합), 문제). 원본과 요청 수(합)가 같고 가장 긴 길이 원본 이하여야
    한다. 해킹 롬은 효과 첫머리에 요청 없는 NMI 가 하나 끼어 길이 둘로 나뉠 수 있어(하위 스크립트 28·2A) 가장 긴 길은 같음이
    아니라 이하로 본다."""
    found = runs(nmis, msgs, subs)
    _, _, problems = judge(found, injects, orig, inject_count=0)
    shape = effect_shape(found, sub)
    want = orig.get(sub)
    if not [v for _, v in subs if v == sub]:
        problems.append(f'하위 스크립트 {sub:02X} 를 고른 자리(22:EA46)에 오지 않음')
    elif sub in UNMATCHED:
        pass
    elif want is None:
        problems.append(f'하위 스크립트 {sub:02X} 의 원본 길이가 표에 없음')
    elif shape[1] != want[1] or shape[0] > want[0]:
        problems.append(f'하위 스크립트 {sub:02X}: 가장 긴 길·합 {shape[0]}·{shape[1]} NMI, 원본 {want[0]}·{want[1]}')
    if not [i for i in injects if any(i[4] in r['frames'] for r in effect_runs(found, sub))]:
        problems.append(f'하위 스크립트 {sub:02X} 의 큰 그림 길에 항목을 넣지 못함')
    return shape, problems


def run_subscripts(mesence, rom, base, out, seed, orig, subs_wanted, jobs):
    """들판 전투의 첫 공격에서 하위 스크립트를 하나씩 강제해 원본 길이와 견준다."""
    scene = SUB_SCENE
    state, why = prepare(mesence, rom, base, out / 'prep', scene, seed)
    if why:
        return [{'sub': None, 'status': 'failed', 'problems': [why]}]
    base_env = battle_env(state, scene, seed, SUB_MAXF) | {'INJECT': '99', 'EFFECT_STOP': '1'}

    def one(sub):
        dirs = [out / f'sub{sub:02X}' / f'run{i + 1}' for i in range(REPEAT)]
        env = base_env | {'SUBSCRIPT': f'{sub:02X}'}
        for d in dirs:
            wc.run(mesence, rom, PROBE, d, env, 600)
        texts, (nmis, msgs, injects, subs) = read_runs(dirs)
        shape, problems = judge_effect(sub, nmis, msgs, injects, subs, orig)
        traces = same_traces(texts, problems)
        return {'sub': f'{sub:02X}', 'status': 'failed' if problems else 'passed', 'problems': problems,
                'shape': shape, 'orig': orig.get(sub), 'unmeasured': UNMATCHED.get(sub),
                'waits': sorted({i[1] - i[0] for i in injects}), 'traces': traces}
    return dq4shards.pmap(one, subs_wanted, jobs)


def measure_original(mesence, dq5_rom, dq5_state, out, subs_wanted, jobs):
    """원본 DQ5 에서 하위 스크립트마다 [(번호, (가장 긴 길, 합), 문제)]."""
    rom = out / 'dq5.sfc'
    shutil.copyfile(dq5_rom.resolve(), rom)
    env = {'NEXT': str(ORIG_DRIVER), 'STATE': str(dq5_state.resolve()), 'EFFECT_STOP': '1', 'MAXF': str(SUB_MAXF)}

    def one(sub):
        d = out / f'sub{sub:02X}'
        wc.run(mesence, rom, PROBE, d, env | {'SUBSCRIPT': f'{sub:02X}'}, 600)
        _, (nmis, msgs, injects, subs) = read_runs([d])
        shape = effect_shape(runs(nmis, msgs, subs), sub)
        problems = [] if shape[1] else [f'하위 스크립트 {sub:02X} 의 큰 그림 길을 못 봄']
        return sub, shape, problems
    return dq4shards.pmap(one, subs_wanted, jobs)


def write_orig(shapes, path=ORIG_TABLE):
    head = ('# 원본 DQ5 에서 공격 효과 하위 스크립트($9E74)마다 전투 큰 그림 길(NMI). longest 는 가장 긴 길, total 은 효과\n'
            '# 동안 큰 그림 NMI 합(요청 수). 몬스터 한 마리 전투. dq4bigpiccheck.py 가 해킹 롬의 같은 하위 스크립트와 견준다.\n'
            '# 고쳐 쓰기: dq4bigpiccheck.py --measure-original --write(원본 롬·전투 중 세이브스테이트 필요)\n')
    longest = ''.join(f'"{k:02X}" = {v[0]}\n' for k, v in sorted(shapes.items()))
    total = ''.join(f'"{k:02X}" = {v[1]}\n' for k, v in sorted(shapes.items()))
    path.write_text(head + '\n[longest]\n' + longest + '\n[total]\n' + total, encoding='utf-8')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--rom', type=Path, help='1장 롬(--measure-original 밖에서 필요)')
    ap.add_argument('--out', required=True, type=Path)
    ap.add_argument('--base', type=Path, help='서장 끝 세이브스테이트(같은 롬). 없으면 만든다(캐시)')
    ap.add_argument('--scenes', help='쉼표로 고른 장면만')
    ap.add_argument('--subscripts', nargs='?', const='all',
                    help='장면 대신 하위 스크립트를 하나씩 강제해 원본 길이와 견줌(쉼표로 고른 16진 번호, 없으면 전부)')
    ap.add_argument('--measure-original', action='store_true', help='원본 DQ5 로 하위 스크립트 길이 표를 다시 재 견줌')
    ap.add_argument('--dq5-rom', type=Path)
    ap.add_argument('--dq5-state', type=Path, help='원본 DQ5 롬의 전투 중 세이브스테이트(주인공이 곧 공격할 수 있는)')
    ap.add_argument('--write', action='store_true', help='--measure-original 결과로 표를 고쳐 씀')
    ap.add_argument('--seed', type=int, default=0)
    ap.add_argument('--jobs', type=int, default=dq4shards.jobs(), help='함께 띄우는 일 수(기본 HEADLESS_SLOTS, dq4shards.jobs)')
    args = ap.parse_args()
    mesence = Path(os.environ['MESENCE'])
    out = args.out.resolve()
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f'{out} is not empty')
    out.mkdir(parents=True, exist_ok=True)
    wanted = (SUBSCRIPTS if args.subscripts in (None, 'all')
              else tuple(int(v, 16) for v in args.subscripts.split(',')))
    if args.measure_original:
        if not (args.dq5_rom and args.dq5_state):
            raise SystemExit('--measure-original 은 --dq5-rom 과 --dq5-state 가 필요하다')
        measured = measure_original(mesence, args.dq5_rom, args.dq5_state, out, wanted, args.jobs)
        orig = load_orig() if ORIG_TABLE.exists() else {}
        problems = [p for _, _, ps in measured for p in ps]
        problems += [f'하위 스크립트 {s:02X}: 원본 {n} NMI, 표 {orig.get(s)}' for s, n, ps in measured
                     if not ps and orig.get(s) != n and not args.write]
        if args.write and not [p for _, _, ps in measured for p in ps]:
            write_orig({s: n for s, n, _ in measured} | {k: v for k, v in orig.items() if k not in wanted})
        for s, n, ps in measured:
            print(f'{s:02X} {n} 표 {orig.get(s)}' + (f' {ps}' if ps else ''))
        print('통과' if not problems else '실패: ' + '; '.join(problems))
        return 0 if not problems else 1
    if not args.rom:
        raise SystemExit('--rom 이 필요하다')
    rom = out / 'c.sfc'
    shutil.copyfile(args.rom.resolve(), rom)
    data = rom.read_bytes()
    if args.base:
        base = args.base.resolve()
    else:
        # 서장은 읽은 바이트 캐시(dq4readset) 없이 걷는다. 상태 캐시(StateCache)는 쓴다. 롬 SHA-1 의 서장 캐시가 없을 때
        # readset=True 로 걸으면 서장 걷기가 출력(walk.txt·end.mss) 없이 끝나 서장 실패가 난다(뒤 자리 잡기는 readset=True 로 됨)
        base, pro = wc.prologue(mesence, rom, data, out, wc.SEGMENTS, wc.StateCache(data), readset=False)
        if pro['status'] != 'passed':
            raise SystemExit(f'서장 실패: {pro["problems"]}')
    orig = load_orig()
    if args.subscripts:
        results = run_subscripts(mesence, rom, base, out, args.seed, orig, wanted, args.jobs)
    else:
        names = args.scenes.split(',') if args.scenes else list(SCENES)
        results = dq4shards.pmap(lambda n: run_scene(mesence, rom, data, base, out, n, SCENES[n], args.seed, orig),
                                 names, args.jobs)
    ok = all(r['status'] == 'passed' for r in results)
    report = {'status': 'passed' if ok else 'failed', 'limit': LIMIT, 'after': AFTER, 'rom': str(args.rom),
              'scenes': results}
    (out / 'results.json').write_text(json.dumps(report, ensure_ascii=False, indent=1) + '\n')
    for r in results:
        print(json.dumps({k: v for k, v in r.items() if k != 'detail'}, ensure_ascii=False))
    if args.subscripts:
        unmeasured = [r['sub'] for r in results if r.get('unmeasured')]
        print(f'미측정 {len(unmeasured)}개: ' + ', '.join(f'{s} — {UNMATCHED[int(s, 16)]}' for s in unmeasured))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
