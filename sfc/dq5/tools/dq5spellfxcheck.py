"""dq5spellfx.py 로 고친 처리 루틴 연결·첫머리 값·필드 주문을 MesenCE 에서 원래 롬과 견준다.

  papas   파파스가 슬라임 셋에게 メラ(행동 01). 첫머리 B0E5 의 양 번호 01 → 02(メラミ 70~90),
          내성 칸 50 → 5B(슬라임 단계 3), 행동 01 의 처리 루틴 B0E5 → B136(ヒャド 25~35)
  sleep   슬라임의 행동 여섯을 ラリホー(4B)로. 첫머리 B410 의 성공 값 3 → 0
  heal    주인공이 전투에서 ホイミ(HP 5). 첫머리 B2C0 의 양 번호 13 → 14(ベホイミ 75~95)
  field   주인공이 필드에서 ホイミ(HP 5/200, MP 100). 처리기 84FA 의 MP 3 → 9, 회복 30+0~10 → 100+0,
          주문 27 의 처리기 84FA → 85DC(ベホマ)
  ranar   필드 주문 목록 첫 칸을 ラナルータ 로 두고 외움. 처리기 826F(11:8048 꼴)의 MP 4 → 12
  슬라임 행동 여섯이나 파파스 행동 여섯을 한 행동으로 두고 첫머리 값을 바꾼다(우리 쪽이 맞는 값은 슬라임, 몬스터가
  맞는 값은 파파스가 쓰는 장면):
  sweet·psweet    あまいいき(95, B718 → AEC6). 성공 값 3 → 0, 내성 칸 57 → 5B
  sleepm·psleepm  ラリホーマ(4C, B419 → AEFF). 성공 값 6 → 0, 내성 칸 57 → 5B
  flame·pflame    かえんのいき(8F, B6E2 → B657). 양 번호 2A → 29(ひのいき 6~10), 내성 칸 51 → 5B
  pmera           몬스터 メラ(39, B301 이 JMP 없이 B307 로 이어짐). 양 번호 16 → 02, 내성 칸 50 → 5B

장면 준비용 ROMPATCH(전투로 순간이동, 슬라임 HP·행동, 파파스 행동, 주인공 필드 목록 첫 칸)는 확인하는 자리를 덮지 않는다.
원본 롬·선실 상태는 읽기만 하고 출력은 --out 의 새 하위 폴더에 둔다.
  MESENCE=… python sfc/dq5/tools/dq5spellfxcheck.py rom/dq5.sfc --state work/state/ship.mss
"""
import argparse
import concurrent.futures
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from dq5progresscheck import command, environment, require, run, save_json
from dq5spellfx import FORMAT
from dq5tablecheck import PAPAS, SLOT_HP

HERE = Path(__file__).resolve().parent
EDITS = {
    'amount': {'battle_handlers': [{'handler': 'B0E5', 'amount': '02'}]},
    'resist': {'battle_handlers': [{'handler': 'B0E5', 'resist': '5B'}]},
    'slot': {'battle_slots': [{'action': '01', 'handler': 'B136'}]},
    'chance': {'battle_handlers': [{'handler': 'B410', 'chance': 0}]},
    'heal': {'battle_handlers': [{'handler': 'B2C0', 'amount': '14'}]},
    'fmp': {'field_handlers': [{'handler': '84FA', 'mp': 9}]},
    'fheal': {'field_handlers': [{'handler': '84FA', 'heal': {'base': 100, 'spread': 1}}]},
    'fslot': {'field_slots': [{'spell': '27', 'handler': '85DC'}]},
    'fmp2': {'field_handlers': [{'handler': '826F', 'mp': 12}]},
    'sweetchance': {'battle_handlers': [{'handler': 'B718', 'chance': 0}]},
    'sweetresist': {'battle_handlers': [{'handler': 'B718', 'resist': '5B'}]},
    'sleepmchance': {'battle_handlers': [{'handler': 'B419', 'chance': 0}]},
    'sleepmresist': {'battle_handlers': [{'handler': 'B419', 'resist': '5B'}]},
    'flameamount': {'battle_handlers': [{'handler': 'B6E2', 'amount': '29'}]},
    'flameresist': {'battle_handlers': [{'handler': 'B6E2', 'resist': '5B'}]},
    'meraamount': {'battle_handlers': [{'handler': 'B301', 'amount': '02'}]},
    'meraresist': {'battle_handlers': [{'handler': 'B301', 'resist': '5B'}]},
}
PAPAS_SCENE = dict(PAPAS, READS='20B7FB')
# 파파스 행동은 그대로 두고 슬라임(파일 118000~)의 MP 를 99, 행동 여섯을 ラリホー 로.
SLEEP = dict(PAPAS, ROMPATCH='156FF5=E0253C0103;118004=63;118011=4B4B4B4B4B4B;118003=C8', READS='', MAXF='2400')
CAST = {'LEARNED': '010100', 'MAXF': '650', 'LOOP': 'wait:500', 'PEEK': '7E2040:42'}
FIELD = dict(CAST, MODE='field', PRE='b:4,wait:40,a:4,wait:30,right:4,wait:20,a:4,wait:40,a:4,wait:40,a:4,wait:200',
             READS='')
HEAL = dict(CAST, MODE='battle', PRE='a:4,wait:30,down:4,wait:20,a:4,wait:40,a:4,wait:40,a:4,wait:200')
# 주인공 필드 주문 목록(23:BE27 = [개수][주문 …])의 첫 칸을 ラナルータ 로. 표는 dq5learnwrite.py 의 것이라 확인 대상이 아니다.
RANAR = dict(FIELD, ROMPATCH='11BE28=37', PRE='b:4,wait:40,a:4,wait:30,right:4,wait:20,a:4,wait:40,a:4,wait:200')


def acting(actor, action):
    """슬라임(23:8011~, MP 99) 또는 파파스(23:958D~)의 행동 여섯을 action 으로 둔 장면."""
    six = f'{action:02X}' * 6
    patch = (f'156FF5=E0253C0103;118004=63;118011={six};118003=C8' if actor == 'slime'
             else f'156FF5=E0253C0103;11958D={six};118003=C8')
    return dict(PAPAS, ROMPATCH=patch, READS='', MAXF='2400' if actor == 'slime' else '2700',
                PEEK='7E07C0:64,7E2040:42')


# 장면: (관측 lua, 드라이버, 환경, 시작 상태 이름, 고친 롬들)
SCENES = {'papas': ('dq5tablecheck.lua', 'dq5battle.lua', PAPAS_SCENE, 'ship', ('amount', 'resist', 'slot')),
          'sleep': ('dq5tablecheck.lua', 'dq5battle.lua', SLEEP, 'ship', ('chance',)),
          'heal': ('dq5learncheck.lua', 'dq5battle.lua', HEAL, 'battle', ('heal',)),
          'field': ('dq5learncheck.lua', 'dq5msg.lua', FIELD, 'ship', ('fmp', 'fheal', 'fslot')),
          'ranar': ('dq5learncheck.lua', 'dq5msg.lua', RANAR, 'ship', ('fmp2',)),
          'sweet': ('dq5tablecheck.lua', 'dq5battle.lua', acting('slime', 0x95), 'ship', ('sweetchance',)),
          'psweet': ('dq5tablecheck.lua', 'dq5battle.lua', acting('papas', 0x95), 'ship', ('sweetresist',)),
          'sleepm': ('dq5tablecheck.lua', 'dq5battle.lua', acting('slime', 0x4C), 'ship', ('sleepmchance',)),
          'psleepm': ('dq5tablecheck.lua', 'dq5battle.lua', acting('papas', 0x4C), 'ship', ('sleepmresist',)),
          'flame': ('dq5tablecheck.lua', 'dq5battle.lua', acting('slime', 0x8F), 'ship', ('flameamount',)),
          'pflame': ('dq5tablecheck.lua', 'dq5battle.lua', acting('papas', 0x8F), 'ship', ('flameresist',)),
          'pmera': ('dq5tablecheck.lua', 'dq5battle.lua', acting('papas', 0x39), 'ship', ('meraamount', 'meraresist'))}
# 잠(우리 쪽 03E·몬스터 082), 잠들지 않음(03F), 「きかなかった」(079), パパス 합류(002), 숨(037).
SLEPT, RESISTED = '03E', '079'
MSLEPT, AWAKE, JOINED, BREATH = '082', '03F', '002', '037'


def build(original, out):
    for name, edit in EDITS.items():
        source, manifest = out / f'{name}.json', out / f'{name}.patch.json'
        save_json(source, {'format': FORMAT, **edit})
        command('dq5spellfx.py', original, 'patch', source, '-o', manifest)
        command('dq5spellfx.py', original, 'check', source)
        command('dq5build.py', original, 'build', manifest, '-o', out / f'{name}.sfc', '--ips', out / f'{name}.ips')


def prepare_battle(original, state, out, mesence, libdir):
    dest = out / 'battle-state'
    env = environment(libdir, state, dest)
    env.update(FIELD='341,56', BATTLE='00:1', SETTLE='300', SAVE='battle.mss', MAXF='1800')
    run(mesence, original, HERE / 'lua/dq5warp.lua', dest, env)
    require((dest / 'battle.mss').is_file(), '전투 상태가 저장되지 않음')
    return dest / 'battle.mss'


def run_case(scene, case, rom, state, out, mesence, libdir):
    probe, driver, options, _, _ = SCENES[scene]
    dest = out / f'{scene}-{case}'
    env = environment(libdir, state, dest)
    env.update(options, DRIVER=str(HERE / 'lua' / driver))
    run(mesence, rom, HERE / 'lua' / probe, dest, env)
    require((dest / 'observed.txt').is_file(), f'{dest.name}: 관측 기록이 없음')
    return dest


def casts(out, name):
    """파파스의 メラ(메시지 070)마다 뒤따르는 피해 메시지(069)에서 (슬롯, 피해) 목록. 끝에서 잘린 것과,
    맞은 쪽 HP 가 0 이 되어 피해가 남은 HP 로 잘린 것은 뺀다."""
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
        hits, killed, j = [], False, i + 1
        while j < len(rows) and rows[j][0] == '069':
            for slot, (before, after) in enumerate(zip(rows[j - 1][1], rows[j][1])):
                if before != after:
                    hits.append((slot, before - after))
                    killed |= after == 0
            j += 1
        if j < len(rows) and not killed:
            result.append(hits)
    return result


def timeline(out, name):
    """메시지마다 (번호, 슬라임 HP 셋, 주인공 HP)."""
    rows = []
    for line in (out / name / 'battle.txt').read_text().splitlines():
        found = re.match(r'f\d+ msg ([0-9A-F]{3}) 7E07C0=([0-9A-F]+) 7E2040=([0-9A-F]+)', line)
        if found:
            slots, party = bytes.fromhex(found[2]), bytes.fromhex(found[3])
            rows.append((found[1], [int.from_bytes(slots[a - 0x7C0:a - 0x7C0 + 2], 'little') for a in SLOT_HP],
                         int.from_bytes(party[2:4], 'little')))
    return rows


def after_join(out, name):
    codes = messages(out, name)
    require(JOINED in codes, f'{name}: パパス 가 합류하지 않음')
    return codes[codes.index(JOINED):]


def breath_hits(out, name):
    """숨(037) 뒤 슬라임마다 피해(069) 또는 079, 끝에서 잘린 숨은 뺀다."""
    rows = timeline(out, name)
    result = []
    for i, (msg, _, _) in enumerate(rows):
        if msg != BREATH:
            continue
        hits, j = [], i + 1
        while j < len(rows) and rows[j][0] in ('069', RESISTED):
            hits.append(RESISTED if rows[j][0] == RESISTED else
                        sum(b - a for a, b in zip(rows[j][1], rows[j - 1][1])))
            j += 1
        if j < len(rows):
            result.append(hits)
    return result


def messages(out, name):
    return [m[1] for m in re.finditer(r'f\d+ msg ([0-9A-F]{3})', (out / name / 'battle.txt').read_text())]


def hero(out, name, battle=False):
    """주인공 (HP, MP). 전투는 회복 메시지(094) 때의 일행 레코드, 필드는 끝의 WRAM."""
    if battle:
        found = re.search(r'msg 094 7E2040=([0-9A-F]{84})', (out / name / 'battle.txt').read_text())
        require(found is not None, f'{name}: 회복 메시지가 없음')
        record = bytes.fromhex(found[1])
    else:
        record = (out / name / 'final.wram').read_bytes()[0x2040:0x206A]
    return int.from_bytes(record[2:4], 'little'), int.from_bytes(record[4:6], 'little')


def verify(out):
    results = {}
    seen = {c: casts(out, f'papas-{c}') for c in ('original', 'amount', 'resist', 'slot')}
    for case, got in seen.items():
        require(len(got) >= 2, f'papas-{case}: 끝까지 본 メラ 가 둘 미만 {got}')
    checks = {'original': lambda h: len(h) == 1 and 12 <= h[0][1] <= 15,
              'amount': lambda h: len(h) == 1 and 70 <= h[0][1] <= 90,
              'resist': lambda h: h == [],
              'slot': lambda h: len(h) == 1 and 25 <= h[0][1] <= 35}
    for case, ok in checks.items():
        require(all(ok(h) for h in seen[case]), f'papas-{case}: 피해가 예상과 다름 {seen[case]}')
    require(RESISTED in messages(out, 'papas-resist') and RESISTED not in messages(out, 'papas-original'),
            '내성 칸: 「きかなかった」 메시지가 갈리지 않음')
    reads = {c: (out / f'papas-{c}' / 'observed.txt').read_text() for c in ('original', 'slot')}
    require('read 20B7FB=E5' in reads['original'] and 'read 20B7FB=36' in reads['slot'], '처리 루틴 표 읽기가 다름')
    results['papas'] = seen

    sleeps = {c: messages(out, f'sleep-{c}') for c in ('original', 'chance')}
    require(SLEPT in sleeps['original'] and SLEPT not in sleeps['chance'], '성공 값: 잠 메시지가 갈리지 않음')
    require(sleeps['chance'].count(RESISTED) >= 2, '성공 값 0: 「きかなかった」 가 둘 미만')
    results['sleep'] = {c: {'잠': v.count(SLEPT), 'きかなかった': v.count(RESISTED)} for c, v in sleeps.items()}

    heal = {c: hero(out, f'heal-{c}', battle=True) for c in ('original', 'heal')}
    require(35 <= heal['original'][0] <= 45 and 80 <= heal['heal'][0] <= 100, f'전투 회복량: {heal}')
    results['heal'] = heal

    field = {c: hero(out, f'field-{c}') for c in ('original', 'fmp', 'fheal', 'fslot')}
    require(35 <= field['original'][0] <= 45 and field['original'][1] == 97, f'필드 원본: {field["original"]}')
    require(35 <= field['fmp'][0] <= 45 and field['fmp'][1] == 91, f'필드 MP: {field["fmp"]}')
    require(field['fheal'] == (105, 97), f'필드 회복량: {field["fheal"]}')
    require(field['fslot'] == (200, 93), f'필드 처리기: {field["fslot"]}')
    results['field'] = field

    ranar = {c: hero(out, f'ranar-{c}')[1] for c in ('original', 'fmp2')}
    require(ranar == {'original': 96, 'fmp2': 88}, f'ラナルータ MP: {ranar}')
    results['ranar'] = ranar
    hit = {c: messages(out, f'sweet-{c}') for c in ('original', 'sweetchance')}
    require(SLEPT in hit['original'] and SLEPT not in hit['sweetchance'] and hit['sweetchance'].count(AWAKE) >= 3,
            f'あまいいき 성공 값: {hit}')
    results['sweet'] = {c: {'잠': v.count(SLEPT), '잠들지 않음': v.count(AWAKE)} for c, v in hit.items()}
    hit = {c: after_join(out, f'psweet-{c}') for c in ('original', 'sweetresist')}
    require(SLEPT in hit['original'] and SLEPT not in hit['sweetresist'] and hit['sweetresist'].count(AWAKE) >= 2,
            f'あまいいき 내성 칸: {hit}')
    results['psweet'] = {c: {'잠': v.count(SLEPT), '잠들지 않음': v.count(AWAKE)} for c, v in hit.items()}

    hit = {c: messages(out, f'sleepm-{c}') for c in ('original', 'sleepmchance')}
    require(SLEPT in hit['original'] and SLEPT not in hit['sleepmchance'] and hit['sleepmchance'].count(RESISTED) >= 2,
            f'ラリホーマ 성공 값: {hit}')
    results['sleepm'] = {c: {'잠': v.count(SLEPT), 'きかなかった': v.count(RESISTED)} for c, v in hit.items()}
    hit = {c: after_join(out, f'psleepm-{c}') for c in ('original', 'sleepmresist')}
    require(MSLEPT in hit['original'] and MSLEPT not in hit['sleepmresist'] and hit['sleepmresist'].count(RESISTED) >= 2,
            f'ラリホーマ 내성 칸: {hit}')
    results['psleepm'] = {c: {'잠': v.count(MSLEPT), 'きかなかった': v.count(RESISTED)} for c, v in hit.items()}

    # 우리 쪽이 맞은 숨: 06A 마다 주인공 HP 가 줄어든 양. 0 이 된 것(남은 HP 로 잘림)은 뺀다.
    burns = {}
    for c in ('original', 'flameamount'):
        rows = timeline(out, f'flame-{c}')
        burns[c] = [(rows[i - 1][2] - r[2], r[2]) for i, r in enumerate(rows) if r[0] == '06A' and i > 0
                    and rows[i - 1][0] == BREATH]
    require(burns['original'] and burns['original'][0] == (24, 0), f'かえんのいき 원본: {burns["original"]}')
    shown = [d for d, hp in burns['flameamount'] if hp > 0]
    require(len(shown) >= 2 and all(6 <= d <= 10 for d in shown), f'かえんのいき 양 번호: {burns["flameamount"]}')
    results['flame'] = burns
    fire = {c: breath_hits(out, f'pflame-{c}') for c in ('original', 'flameresist')}
    flat = {c: [h for hits in v for h in hits] for c, v in fire.items()}
    require(len(flat['original']) >= 3 and all(isinstance(h, int) and 30 <= h <= 40 for h in flat['original']),
            f'かえんのいき 원본(몬스터): {fire["original"]}')
    require(len(flat['flameresist']) >= 3 and RESISTED in flat['flameresist']
            and all(h == RESISTED or h <= 1 for h in flat['flameresist']), f'かえんのいき 내성 칸: {fire["flameresist"]}')
    results['pflame'] = fire

    mera = {c: casts(out, f'pmera-{c}') for c in ('original', 'meraamount', 'meraresist')}
    require(len(mera['original']) >= 2 and all(len(h) == 1 and 7 <= h[0][1] <= 12 for h in mera['original']),
            f'몬스터 メラ 원본: {mera["original"]}')
    require(len(mera['meraamount']) >= 2 and all(len(h) == 1 and 70 <= h[0][1] <= 90 for h in mera['meraamount']),
            f'몬스터 メラ 양 번호: {mera["meraamount"]}')
    require(len(mera['meraresist']) >= 2 and all(h == [] for h in mera['meraresist'])
            and after_join(out, 'pmera-meraresist').count(RESISTED) >= 2, f'몬스터 メラ 내성 칸: {mera["meraresist"]}')
    results['pmera'] = mera
    save_json(out / 'results.json', results)
    return results


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('rom', type=Path)
    ap.add_argument('--state', required=True, type=Path)
    ap.add_argument('--mesence', default=os.environ.get('MESENCE'))
    ap.add_argument('--out', type=Path, default='work/spellfxcheck')
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
        starts = {'ship': state, 'battle': prepare_battle(original, state, out, mesence, libdir)}
        jobs = []
        for scene, (_, _, _, start, cases) in SCENES.items():
            jobs.append((scene, 'original', original, starts[start]))
            jobs += [(scene, case, out / f'{case}.sfc', starts[start]) for case in cases]
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda job: run_case(*job, out, mesence, libdir), jobs))
        results = verify(out)
        print(f'{len(jobs) + 1}회 실행, 수정 {len(EDITS)}건 게임 검사 통과')
        print(json.dumps(results, ensure_ascii=False))
        return 0
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        print(f'오류: {error}', file=sys.stderr)
        if isinstance(error, subprocess.CalledProcessError) and error.output:
            print(error.output, file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
