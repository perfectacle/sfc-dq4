"""dq5tables.py 로 고친 물건 플래그·주문 필드·피해량·동료 몬스터 표를 실제 게임에서 확인한다.

형식은 sfc/dq5/docs/dq5-build-format.md 의 「게임 데이터 표」. 고친 롬마다 원래 롬으로 같은 장면을 돌려,
원래 롬과 다른 결과가 나오는지 본다.

  상점    물건 06 どうのつるぎ 의 장비사람(주인공 비트 끔)·칸(0 → 1). 장비 검사 21:A561 의 AND 값, 칸 읽기
  전투    파파스가 슬라임 셋에게 メラ 를 건다. 주문 01 의 대상루틴 975F → 97BC 이면 한 번에 셋,
          피해량 01 의 바탕 12·폭 4 → 40·1 이면 피해가 늘 40
  동료    슬라임(동료 종류 02)을 들인다. 레벨·HP·MP 를 1·8·0 → 7·99·42. 최대레벨 99 → 1 이면 다음 전투에서
          레벨이 오르지 않음. 일행에 슬라임을 넣은 상점에서 장비갈래 1 → 5 이면 どうのつるぎ 를 장비할 수 있음
  필드    やくそう(물건 A1)를 쓴다. 쓰면없어짐 1 → 0, 사용메시지없음 0 → 1, 일행 둘일 때 필드대상창 1 → 0
  インパス  주인공이 やくそう 에 インパス 를 건다. 인파스설명·종류·가격줄·횟수줄·장비줄로 설명 메시지가 바뀜
          どうのつるぎ 의 장비몬스터에 갈래 1 비트(4000)를 켜도 장비할 수 있음
  가득    가진 물건 12칸이 찬 채 슬라임이 やくそう 를 떨어뜨림. 가득창 0 → 1 이면 사람 고르기 창 4F → 6F
  설명    무기점에서 どうのつるぎ 를 고른다. 상점전투설명 0 → 1 이면 메시지 036 이 더 나옴
  팔기    やくそう 를 판다. 팔수없음 0 → 1 이면 메시지 052 대신 056
  장비    ひのきのぼう(물건 00)를 다시 장비한다. 저주 0 → 1 이면 25:FD00 을 A = 23 으로 부름
  전투    やくそう 를 쓴다. 적쪽 0 → 1 이면 적 그룹 창(4C), 전투대상창 1 → 0 이면 창 없음.
          주인공이 メラ 를 건다. 범위 1 → 3 이면 대상 창 없음, 적쪽 1 → 0 이면 우리 편 창(4A)

원본 롬·선실 상태는 읽기만 하고 입력 JSON부터 롬·실행 로그까지 --out 의 새 폴더에 둔다. 장면 준비용
ROMPATCH·POKE·SET(상점 장면, 전투로 순간이동, 슬라임 HP 200, 파파스 행동, 동료 조건과 확률, 일행에 슬라임 레코드,
가진 물건·HP·MP·주문 칸, 주인공 전투 주문 칸 23:BE31, 떨어뜨리기 확률을 건너뛰는 20:8000 bit5)는 확인하는 표를 덮지 않는다.
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
    'maxlevel': {'companions': [{'id': '02', '최대레벨': 1}]},
    'branch': {'companions': [{'id': '02', '장비갈래': 5}]},
    'monequip': {'items': [{'id': '06', '장비몬스터': '0100010100101001'}]},
    'keep': {'items': [{'id': 'A1', '쓰면없어짐': 0}]},
    'quiet': {'items': [{'id': 'A1', '사용메시지없음': 1}]},
    'fieldwin': {'items': [{'id': 'A1', '필드대상창': 0}]},
    'nosell': {'items': [{'id': 'A1', '팔수없음': 1}]},
    'curse': {'items': [{'id': '00', '저주': 1}]},
    'foe': {'items': [{'id': 'A1', '적쪽': 1}]},
    'battlewin': {'items': [{'id': 'A1', '전투대상창': 0}]},
    'full': {'items': [{'id': 'A1', '가득창': 1}]},
    'sdesc': {'items': [{'id': '06', '상점전투설명': 1}]},
    'idesc': {'items': [{'id': 'A1', '인파스설명': 13}]},
    'ikind': {'items': [{'id': 'A1', '인파스종류': 1}]},
    'iprice': {'items': [{'id': 'A1', '인파스가격줄': 0}]},
    'iuses': {'items': [{'id': 'A1', '인파스횟수줄': 0}]},
    'iequip': {'items': [{'id': 'A1', '인파스장비줄': 1}]},
    'range': {'spells': [{'id': '01', '범위': 3}]},
    'side': {'spells': [{'id': '01', '적쪽': 0}]},
}
# 슬라임을 들인 직후의 일행 레코드(동료 장면 실측). 상점·필드 장면에서 주인공 뒤 레코드 1 에 넣는다.
SLIME = bytes.fromhex('82800800000003080501030000000800000001630000ffffffffffffffffffffffff000000004b000002')
PARTY = ';'.join([f'{0x206A + i:04X}={b:02X}' for i, b in enumerate(SLIME)]
                 + ['201D=02', '201E=02', '201F=02', '2021=01', '2029=01'])
FIELD_USE = 'b:4,wait:40,a:4,wait:30,down:4,wait:10,right:4,wait:10,a:4,wait:40'
# 창 레코드 04:EB48[창]: 38 필드 대상(F197), 4A 우리 편(F2F6), 4C 적 그룹(F314). 04:9C52 의 A.
WINDOW = {'38': 'A=F197', '4A': 'A=F2F6', '4C': 'A=F314', '4F': 'A=F337', '6F': 'A=F99D'}
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
# 들인 슬라임(일행 레코드 2)의 다음 레벨 경험치(+26~+28)를 1 로 붙잡아 다음 전투에서 레벨이 오를 수 있게.
GROW = {**JOIN, 'MAXF': '6000', 'POKE': JOIN['POKE'] + ';7E20BA=01;7E20BB=00;7E20BC=00'}
SHOP_PARTY = {**SHOP, 'SET': PARTY, 'READS': '23AEEB,23B675'}
FIELD_ITEM = {'MAXF': '600', 'SET': '2058=A1;2042=05', 'EXECS': '248BAF,049C52', 'READS': '23B1FA',
              'PRE': FIELD_USE + ',a:4,wait:40,a:4,wait:60,a:4,wait:60,a:4,wait:100'}
FIELD_PARTY = {**FIELD_ITEM, 'MAXF': '700', 'SET': PARTY + ';2058=A1;2042=05',
               'PRE': FIELD_USE + ',a:4,wait:40,a:4,wait:60,a:4,wait:60,a:4,wait:100,a:4,wait:100'}
SELL = {**SHOP, 'MAXF': '520', 'SET': '2058=A1', 'EXECS': '248BAF', 'READS': '23B1FA',
        'PRE': 'b:4,wait:40,up:3,wait:20,a:4,wait:30,a:4,wait:150,down:4,wait:10,a:4,wait:60,a:4,wait:60,a:4,wait:80'}
EQUIP = {'MAXF': '520', 'EXECS': '25FD00', 'READS': '23B231',
         'PRE': 'b:4,wait:40,a:4,wait:30,down:4,wait:10,down:4,wait:10,a:4,wait:50,a:4,wait:50,a:4,wait:60,a:4,wait:60'}
BATTLE_ITEM = {'MAXF': '320', 'POKE': '7E2058=A1;7E2042=05', 'LOOP': 'wait:500', 'PEEK': '7E1037:1',
               'EXECS': '049C52', 'READS': '23B2D2',
               'PRE': 'a:4,wait:30,down:4,wait:10,down:4,wait:10,a:4,wait:40,down:4,wait:20,a:4,wait:40,a:4,wait:40,a:4,wait:200'}
# 가진 물건 12칸을 채우고, 20:8000 bit5(떨어뜨리기 확률을 건너뜀, 파일 오프셋 100000)를 켬(scene_patches).
FULL_BAG = {'MAXF': '1500', 'LOOP': 'a:4,wait:30', 'EXECS': '049C52', 'READS': '23B1FA',
            'POKE': ';'.join(f'7E{0x2056 + i:04X}={0x42 if i == 0 else 0x46:02X}' for i in range(12))}
SHOP_DESC = {**SHOP, 'MAXF': '900', 'POKE': SHOP['POKE'] + ';7E2019=FF;7E201A=FF', 'EXECS': '248BAF', 'READS': '23B237',
             'PRE': SHOP['PRE'] + ',' + ','.join(['a:4,wait:60'] * 6)}
# 주인공에게 필드 주문 칸 0~7 을 모두 주고(넷째가 インパス) やくそう 를 고름.
IMPAS = {'MAXF': '1100', 'SET': '2063=FF;2058=A1;2044=63', 'EXECS': '248BAF',
         'PRE': 'b:4,wait:40,a:4,wait:30,right:4,wait:20,a:4,wait:40,down:4,wait:10,down:4,wait:10,down:4,wait:10,'
                + ','.join(['a:4,wait:60'] * 12)}
# 주인공 전투 주문 칸 8(23:BE31)을 メラ 로 두고 그 칸을 켬.
HERO_SPELL = {'MAXF': '320', 'ROMPATCH': '11BE31=01', 'POKE': '7E2064=01;7E2044=63', 'LOOP': 'wait:500',
              'PEEK': '7E1037:1', 'EXECS': '049C52', 'READS': '268766',
              'PRE': 'a:4,wait:30,down:4,wait:20,a:4,wait:40,a:4,wait:40,a:4,wait:200'}
# 장면: (드라이버, 환경, 고친 롬 이름들, 시작 상태). 시작 상태 battle 은 첫 필드 이벤트 전투(슬라임 하나).
SCENES = {'shop': ('dq5msg.lua', SHOP, ('equip', 'slot'), 'ship'),
          'papas': ('dq5battle.lua', PAPAS, ('target', 'amount'), 'ship'),
          'join': ('dq5battle.lua', JOIN, ('companion',), 'battle'),
          'grow': ('dq5battle.lua', GROW, ('maxlevel',), 'battle'),
          'shopparty': ('dq5msg.lua', SHOP_PARTY, ('branch', 'monequip'), 'ship'),
          'field': ('dq5msg.lua', FIELD_ITEM, ('keep', 'quiet'), 'ship'),
          'fieldparty': ('dq5msg.lua', FIELD_PARTY, ('fieldwin',), 'ship'),
          'sell': ('dq5msg.lua', SELL, ('nosell',), 'ship'),
          'fullbag': ('dq5battle.lua', FULL_BAG, ('full',), 'battle'),
          'shopdesc': ('dq5msg.lua', SHOP_DESC, ('sdesc',), 'ship'),
          'impas': ('dq5msg.lua', IMPAS, ('idesc', 'ikind', 'iprice', 'iuses', 'iequip'), 'ship'),
          'equipmenu': ('dq5msg.lua', EQUIP, ('curse',), 'ship'),
          'battleitem': ('dq5battle.lua', BATTLE_ITEM, ('foe', 'battlewin'), 'battle'),
          'herospell': ('dq5battle.lua', HERO_SPELL, ('range', 'side'), 'battle')}
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


def scene_patches(original):
    """원래 롬 값에 기대는 장면 준비 덮기."""
    return {'fullbag': {'ROMPATCH': f'100000={original.read_bytes()[0x100000] | 0x20:02X}'}}


def run_case(scene, case, rom, state, out, mesence, libdir, extra):
    driver, options, _, _ = SCENES[scene]
    dest = out / f'{scene}-{case}'
    env = environment(libdir, state, dest)
    env.update(options, **extra.get(scene, {}), DRIVER=str(HERE / 'lua' / driver))
    run(mesence, rom, HERE / 'lua/dq5tablecheck.lua', dest, env)
    require((dest / 'observed.txt').is_file(), f'{dest.name}: 관측 기록이 없음')
    return dest


def observed(out, name):
    text = (out / name / 'observed.txt').read_text()
    require('truncated' not in text, f'{name}: 관측 기록이 상한에서 잘림')
    return text


def wram(out, name):
    return (out / name / 'final.wram').read_bytes()


def battle(out, name):
    """전투 메시지마다 (번호, PEEK 값)."""
    return [(m[1], m[2]) for m in re.finditer(r'msg ([0-9A-F]{3}) 7E1037=([0-9A-F]{2})',
                                                (out / name / 'battle.txt').read_text())]


def after_cast(rows):
    """첫 주문 메시지(070) 바로 뒤 메시지와 그때의 대상 바이트."""
    i = [m for m, _ in rows].index('070')
    return rows[i + 1] if i + 1 < len(rows) else None


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
    ram = wram(out, name)
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
    results.update(verify_more(out))
    save_json(out / 'results.json', results)
    return results


def verify_more(out):
    results = {}
    base, capped = member(out, 'grow-original'), member(out, 'grow-maxlevel')
    ups = [len(re.findall(r'msg 0BF', (out / f'grow-{c}' / 'battle.txt').read_text())) for c in ('original', 'maxlevel')]
    require(ups == [2, 1], f'최대레벨: 레벨업 메시지 0BF 수가 2/1 이 아님 {ups}')
    require(base['레벨'] >= 2 and base['최대레벨'] == 99, f'원래 롬: 슬라임 레벨이 오르지 않음 {base}')
    require(capped['레벨'] == 1 and capped['최대레벨'] == 1, f'최대레벨: 슬라임 레벨이 1 이 아님 {capped}')
    require('read 23AEE4=01 pc=218152' in observed(out, 'grow-maxlevel'), '최대레벨: 23:AEE4 를 읽지 않음')
    results['최대레벨'] = {'원래': {'레벨': base['레벨'], '0BF': ups[0]}, '고친': {'레벨': capped['레벨'], '0BF': ups[1]}}

    base, branch = observed(out, 'shopparty-original'), observed(out, 'shopparty-branch')
    require('read 23AEEB=01' in base and 'pc=21A561 A=0000 X=000C' in base, '원래 롬: スラリン 장비 AND 가 0 이 아님')
    require('read 23AEEB=05' in branch and 'pc=21A561 A=0400 X=000C' in branch, '장비갈래: スラリン AND 가 0400 이 아님')
    results['장비갈래'] = {'원래': {'갈래': 1, 'AND': '0000'}, '고친': {'갈래': 5, 'AND': '0400'}}
    monequip = observed(out, 'shopparty-monequip')
    # 21:A594 의 16비트 읽기는 낮은 바이트 주소 23:B675 로만 잡힌다.
    require('pc=21A594' in base and 'pc=21A594' in monequip and 'pc=21A561 A=4000 X=000C' in monequip,
            '장비몬스터: スラリン AND 가 4000 이 아님')
    results['장비몬스터'] = {'원래': {'값': '0529', 'AND': '0000'}, '고친': {'값': '4529', 'AND': '4000'}}

    base, keep, quiet = (observed(out, f'field-{c}') for c in ('original', 'keep', 'quiet'))
    left = {c: wram(out, f'field-{c}')[0x2058] for c in ('original', 'keep', 'quiet')}
    require('A=01A2' in base and 'A=018F' in base and left['original'] == 0xFF, f'원래 롬: やくそう 사용 결과가 다름 {left}')
    require('A=018F' in keep and left['keep'] == 0xA1, f'쓰면없어짐: やくそう 가 없어짐 {left}')
    require('A=01A2' not in quiet and 'A=018F' in quiet, '사용메시지없음: 메시지 1A2 가 나옴')
    results['쓰면없어짐'] = {'원래': {'셋째 칸': f'{left["original"]:02X}'}, '고친': {'셋째 칸': f'{left["keep"]:02X}'}}
    results['사용메시지없음'] = {'원래': ['1A2', '18F'], '고친': ['18F']}

    base, nowin = observed(out, 'fieldparty-original'), observed(out, 'fieldparty-fieldwin')
    require(WINDOW['38'] in base and WINDOW['38'] not in nowin and 'A=01A2' in nowin, '필드대상창: 창 38 이 갈리지 않음')
    results['필드대상창'] = {'원래': '창 38', '고친': '창 없음'}

    base, nosell = observed(out, 'sell-original'), observed(out, 'sell-nosell')
    require('pc=248BAF A=0052' in base and 'A=0056' not in base, '원래 롬: 메시지 052 가 아님')
    require('pc=248BAF A=0056' in nosell and 'A=0052' not in nosell, '팔수없음: 메시지 056 이 아님')
    results['팔수없음'] = {'원래': '052', '고친': '056'}

    said = {c: re.findall(r'pc=248BAF A=0([0-9A-F]{3})', observed(out, f'impas-{c}'))
            for c in ('original', 'idesc', 'ikind', 'iprice', 'iuses', 'iequip')}
    want = {'original': ['451', '49A', '457', '45F'], 'idesc': ['451', '49B', '457', '45F'],
            'ikind': ['451', '456', '49A', '457', '45F'], 'iprice': ['451', '49A', '457'],
            'iuses': ['451', '49A', '45F'], 'iequip': ['451', '49A', '457', '45E', '45F']}
    for case, messages in want.items():
        got = said[case][said[case].index('451'):] if '451' in said[case] else said[case]
        require(got == messages, f'impas-{case}: インパス 메시지 {got} 가 {messages} 가 아님')
    results['インパス'] = {case: said[case][-len(m):] for case, m in want.items()}

    base, full = observed(out, 'fullbag-original'), observed(out, 'fullbag-full')
    require('read 23B1FA=60' in base and WINDOW['4F'] in base and WINDOW['6F'] not in base, '원래 롬: 사람 고르기 창이 4F 가 아님')
    require('read 23B1FA=70' in full and WINDOW['6F'] in full and WINDOW['4F'] not in full, '가득창: 사람 고르기 창이 6F 가 아님')
    results['가득창'] = {'원래': '창 4F', '고친': '창 6F'}

    base, desc = observed(out, 'shopdesc-original'), observed(out, 'shopdesc-sdesc')
    require('A=003E' in base and 'A=0036' not in base and 'A=0036' in desc, '상점전투설명: 메시지 036 이 갈리지 않음')
    results['상점전투설명'] = {'원래': '없음', '고친': '036'}

    base, curse = observed(out, 'equipmenu-original'), observed(out, 'equipmenu-curse')
    require('25FD00' not in base and 'pc=25FD00 A=0023' in curse, '저주: 25:FD00 호출이 갈리지 않음')
    results['저주'] = {'원래': '부르지 않음', '고친': '25:FD00 A=23'}

    rows = {c: battle(out, f'battleitem-{c}') for c in ('original', 'foe', 'battlewin')}
    texts = {c: observed(out, f'battleitem-{c}') for c in rows}
    require(WINDOW['4A'] in texts['original'] and ('094', '03') in rows['original'], '원래 롬: やくそう 가 우리 편 창·대상 03 이 아님')
    require(WINDOW['4C'] in texts['foe'] and ('094', '83') in rows['foe'], '적쪽: 적 그룹 창·대상 83 이 아님')
    require(WINDOW['4A'] not in texts['battlewin'] and WINDOW['4C'] not in texts['battlewin']
            and ('094', '03') in rows['battlewin'], '전투대상창: 창 없이 쓰이지 않음')
    results['물건 적쪽'] = {'원래': ['창 4A', '대상 03'], '고친': ['창 4C', '대상 83']}
    results['전투대상창'] = {'원래': '창 4A', '고친': '창 없음'}

    rows = {c: battle(out, f'herospell-{c}') for c in ('original', 'range', 'side')}
    texts = {c: observed(out, f'herospell-{c}') for c in rows}
    require(WINDOW['4C'] in texts['original'] and after_cast(rows['original']) == ('069', '81'), '원래 롬: メラ 가 적 그룹 창·슬라임이 아님')
    require(WINDOW['4C'] not in texts['range'] and WINDOW['4A'] not in texts['range']
            and after_cast(rows['range']) == ('069', '81'), '범위: 창 없이 슬라임에게 걸리지 않음')
    require(WINDOW['4A'] in texts['side'] and after_cast(rows['side']) == ('06A', '01') and '069' not in [m for m, _ in rows['side']],
            '주문 적쪽: 우리 편 창·주인공 피해가 아님')
    for case, value in (('original', 'A2'), ('range', 'E2'), ('side', '22')):
        require(f'read 268766={value}' in texts[case], f'herospell-{case}: 26:8766 = {value} 를 읽지 않음')
    results['범위'] = {'원래': '창 4C', '고친': '창 없음'}
    results['주문 적쪽'] = {'원래': ['창 4C', '069'], '고친': ['창 4A', '06A']}
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
        for scene, (_, _, cases, start) in SCENES.items():
            start = join_state if start == 'battle' else state
            jobs.append((scene, 'original', original, start))
            jobs += [(scene, case, out / f'{case}.sfc', start) for case in cases]
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            extra = scene_patches(original)
            list(pool.map(lambda job: run_case(*job, out, mesence, libdir, extra), jobs))
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
