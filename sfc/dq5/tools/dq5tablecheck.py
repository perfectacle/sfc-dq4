"""dq5tables.py 로 고친 물건 플래그·주문 필드·피해량·동료 몬스터 표를 실제 게임에서 확인한다.

형식은 sfc/dq5/docs/dq5-build-format.md 의 「게임 데이터 표」. 고친 롬마다 원래 롬으로 같은 장면을 돌려,
원래 롬과 다른 결과가 나오는지 본다.

  상점    물건 06 どうのつるぎ 의 장비사람(주인공 비트 끔)·칸(0 → 1). 장비 검사 21:A561 의 AND 값, 칸 읽기
  전투    파파스가 슬라임 셋에게 メラ 를 건다. 주문 01 의 대상루틴 975F → 97BC 이면 한 번에 셋,
          피해량 01 의 바탕 12·폭 4 → 40·1 이면 피해가 늘 40
  동료    슬라임(동료 종류 02)을 들인다. 레벨·HP·MP 를 1·8·0 → 7·99·42

원본 롬·선실 상태는 읽기만 하고 입력 JSON부터 롬·실행 로그까지 --out 의 새 폴더에 둔다. 장면 준비용
ROMPATCH·POKE(상점 장면, 전투로 순간이동, 슬라임 HP 200, 파파스 행동, 동료 조건과 확률)는 확인하는 표를 덮지 않는다.
로그의 PC 는 MesenCE 읽기 콜백이 주는 값이라 읽은 명령의 다음 명령 주소다.

  MESENCE=… python sfc/dq5/tools/dq5tablecheck.py rom/dq5.sfc --state work/state/ship.mss
"""
import argparse
import concurrent.futures
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

from dq5progresscheck import command, environment, require, run, save_json

HERE = Path(__file__).resolve().parent

EDITS = {
    'equip': {'items': [{'id': '06', '장비사람': '00100110'}]},
    'slot': {'items': [{'id': '06', '칸': 1}]},
    'target': {'spells': [{'id': '01', '대상루틴': '97BC'}]},
    'amount': {'amounts': [{'id': '01', '바탕': 40, '폭': 1}]},
    'companion': {'companions': [{'id': '02', '레벨': 7, 'HP': 99, 'MP': 42}]},
}
SHOP = {'MAXF': '800', 'POKE': '7E36EB=01;7E370B=00', 'ROMPATCH': '35C37=A901',
        'PRE': 'b:4,wait:40,up:3,wait:20,a:4,wait:30,a:4,wait:150,a:4,wait:80,a:4,wait:80',
        'READS': '23B231-23B308,23B591-23B668', 'EXECS': '21A561'}
# 사다리 출구를 첫 필드 이벤트 자리로 덮고, 슬라임(몬스터 00) HP 를 200, 파파스(몬스터 DC) 행동 여섯을 모두 メラ 로.
PAPAS = {'MAXF': '3000', 'PRE': 'b:4,wait:40,b:4,wait:40', 'PEEK': '7E07C0:64',
         'WAYPOINTS': '3,11;3,24;7,24;7,22;37,66;37,72;down:90',
         'ROMPATCH': '156FF5=E0253C0103;11958D=010101010101;118003=C8', 'READS': '268867,278073'}
# 동료 조건 7E:21B1 bit6·$1010 bit7 을 주고, 동료 확률 27:8162 의 등급 7(슬라임)을 1/1 로.
JOIN = {'MAXF': '1400', 'LOOP': 'a:4,wait:20', 'POKE': '7E21B1=40;7E1010=80', 'ROMPATCH': '138170=0100',
        'READS': '23AED1-23AF6A'}
# 장면: (드라이버, 환경, 고친 롬 이름들)
SCENES = {'shop': ('dq5msg.lua', SHOP, ('equip', 'slot')),
          'papas': ('dq5battle.lua', PAPAS, ('target', 'amount')),
          'join': ('dq5battle.lua', JOIN, ('companion',))}
SLOT_HP = [0x7C0 + slot * 16 + 2 for slot in range(3)]


def build(original, out):
    for name, edit in EDITS.items():
        source, patch = out / f'{name}.json', out / f'{name}.patch.json'
        save_json(source, {'format': 'dq5tables/1', **edit})
        command('dq5tables.py', original, 'patch', source, '-o', patch)
        command('dq5build.py', original, 'build', patch, '-o', out / f'{name}.sfc', '--ips', out / f'{name}.ips')


def prepare_join(original, state, out, mesence, libdir):
    dest = out / 'join-state'
    env = environment(libdir, state, dest)
    env.update(FIELD='341,56', BATTLE='00:1', SETTLE='300', SAVE='battle.mss', MAXF='1800')
    run(mesence, original, HERE / 'lua/dq5warp.lua', dest, env)
    require((dest / 'battle.mss').is_file(), '동료 전투 상태가 저장되지 않음')
    return dest / 'battle.mss'


def run_case(scene, case, rom, state, out, mesence, libdir):
    driver, options, _ = SCENES[scene]
    dest = out / f'{scene}-{case}'
    env = environment(libdir, state, dest)
    env.update(options, DRIVER=str(HERE / 'lua' / driver))
    run(mesence, rom, HERE / 'lua/dq5tablecheck.lua', dest, env)
    require((dest / 'observed.txt').is_file(), f'{dest.name}: 관측 기록이 없음')
    return dest


def observed(out, name):
    text = (out / name / 'observed.txt').read_text()
    require('truncated' not in text, f'{name}: 관측 기록이 상한에서 잘림')
    return text


def casts(out, name):
    """파파스의 メラ(메시지 070)마다 뒤따르는 피해 메시지(069)에서 줄어든 (슬롯, HP) 목록. 끝에서 잘린 것은 뺀다."""
    rows = []
    for line in (out / name / 'battle.txt').read_text().splitlines():
        found = re.match(r'f\d+ msg ([0-9A-F]{3}) 7E07C0=([0-9A-F]+)', line)
        if found:
            ram = bytes.fromhex(found[2])
            rows.append((found[1], [int.from_bytes(ram[a - 0x7C0:a - 0x7C0 + 2], 'little') for a in SLOT_HP]))
    result = []
    for i, (msg, _) in enumerate(rows):
        if msg != '070':
            continue
        hits, j = [], i + 1
        while j < len(rows) and rows[j][0] == '069':
            hits += [(slot, before - after) for slot, (before, after) in
                     enumerate(zip(rows[j - 1][1], rows[j][1])) if before != after]
            j += 1
        if j < len(rows):
            result.append(hits)
    return result


def member(out, name):
    ram = (out / name / 'final.wram').read_bytes()
    for n in range(8):
        r = ram[0x2040 + n * 42:0x2040 + (n + 1) * 42]
        if r[0] == 0x82:
            return {'레벨': r[0x12], '최대레벨': r[0x13], 'HP': int.from_bytes(r[2:4], 'little'),
                    '최대HP': int.from_bytes(r[0xE:0x10], 'little'), 'MP': int.from_bytes(r[4:6], 'little'),
                    '최대MP': int.from_bytes(r[0x10:0x12], 'little')}
    raise ValueError(f'{name}: 일행에 슬라임(82)이 없음')


def verify(out):
    results = {}
    base, equip, slot = (observed(out, f'shop-{c}') for c in ('original', 'equip', 'slot'))
    require('read 23B597=A6 pc=21A55B' in base and 'pc=21A561 A=0080' in base, '원래 롬: どうのつるぎ 장비 비트 A6·AND 80 이 아님')
    require('read 23B597=26 pc=21A55B' in equip and 'pc=21A561 A=0000' in equip and 'A=0080' not in equip,
            '장비사람: 주인공 AND 가 0 이 아님')
    require('read 23B237=00 pc=21A43D' in base and 'read 23B237=01 pc=21A43D' in slot
            and '23B237=00' not in slot, '칸: 23:B237 읽기 값이 00/01 로 갈리지 않음')
    # 비교 창이 마지막으로 계산한 새 능력치가 $46 에 남는다(화면의 「13▶ 24」·「7▶ 16」 의 오른쪽).
    shown = [(out / f'shop-{c}/final.wram').read_bytes()[0x46] for c in ('original', 'slot')]
    require(shown == [24, 16], f'칸: 비교 창 새 능력치가 24/16 이 아님: {shown}')
    results['장비사람'] = {'원래': {'비트': 'A6', 'AND': '80'}, '고친': {'비트': '26', 'AND': '00'}}
    results['칸'] = {'원래': {'칸': 0, '새 능력치': 24}, '고친': {'칸': 1, '새 능력치': 16}}

    base, target, amount = (casts(out, f'papas-{c}') for c in ('original', 'target', 'amount'))
    for name, got in (('원래', base), ('대상루틴', target), ('피해량', amount)):
        require(len(got) >= 2, f'{name}: 끝까지 본 メラ 가 둘 미만 {got}')
    require(all(len(h) == 1 and 12 <= h[0][1] <= 15 for h in base), f'원래 롬 メラ 가 한 마리·12~15 가 아님: {base}')
    require(all(sorted(s for s, _ in h) == [0, 1, 2] and all(12 <= d <= 15 for _, d in h) for h in target),
            f'대상루틴: 한 번에 셋이 아님: {target}')
    require(all(len(h) == 1 and h[0][1] == 40 for h in amount), f'피해량: 한 마리·40 이 아님: {amount}')
    for name, want in (('original', ['268867=5F', '278073=0C']), ('target', ['268867=BC']), ('amount', ['278073=28'])):
        text = observed(out, f'papas-{name}')
        require(all(f'read {w}' in text for w in want), f'papas-{name}: 표 읽기 {want} 가 없음')
    results['대상루틴'] = {'원래': base, '고친': target}
    results['피해량'] = {'원래': base, '고친': amount}

    base, companion = member(out, 'join-original'), member(out, 'join-companion')
    require((base['레벨'], base['HP'], base['최대HP'], base['MP'], base['최대MP']) == (1, 8, 8, 0, 0),
            f'원래 롬 슬라임: {base}')
    require('read 23AEE3=01 pc=21814B' in observed(out, 'join-original'), '원래 롬: 동료 레벨을 21:814B 에서 읽지 않음')
    require((companion['레벨'], companion['HP'], companion['최대HP'], companion['MP'], companion['최대MP'])
            == (7, 99, 99, 42, 42), f'동료: {companion}')
    require('read 23AEE3=07 pc=21814B' in observed(out, 'join-companion'), '동료 레벨을 21:814B 에서 읽지 않음')
    results['동료'] = {'원래': base, '고친': companion}
    save_json(out / 'results.json', results)
    return results


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('rom', type=Path)
    ap.add_argument('--state', required=True, type=Path)
    ap.add_argument('--mesence', default=os.environ.get('MESENCE'))
    ap.add_argument('--out', type=Path, default='work/tablecheck')
    args = ap.parse_args()
    if not args.mesence:
        ap.error('--mesence 또는 MESENCE가 필요함')
    try:
        original, state, mesence = args.rom.resolve(), args.state.resolve(), Path(args.mesence).resolve()
        for path in (original, state, mesence):
            require(path.is_file(), f'파일 없음: {path}')
        args.out.mkdir(parents=True, exist_ok=True)
        out = Path(tempfile.mkdtemp(prefix='run-', dir=args.out.resolve()))
        print(f'실행 출력: {out}', flush=True)
        libdir = subprocess.run(['krpatch', 'sfc', 'lua'], capture_output=True, text=True,
                                check=True, timeout=30).stdout.strip()
        build(original, out)
        join_state = prepare_join(original, state, out, mesence, libdir)
        jobs = []
        for scene, (_, _, cases) in SCENES.items():
            start = join_state if scene == 'join' else state
            jobs.append((scene, 'original', original, start))
            jobs += [(scene, case, out / f'{case}.sfc', start) for case in cases]
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda job: run_case(*job, out, mesence, libdir), jobs))
        results = verify(out)
        print(f'{len(jobs) + 1}회 실행, 수정 {len(EDITS)}건(표 4종) 게임 검사 통과')
        print(json.dumps(results, ensure_ascii=False))
        return 0
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        print(f'오류: {error}', file=sys.stderr)
        if isinstance(error, subprocess.CalledProcessError) and error.output:
            print(error.output, file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
