"""새 행동 번호(C6 = ホイミ, C7 = メラ 를 베낀 새 주문)를 배우고 필드·전투에서 쓰는 것을 MesenCE 에서 확인한다.

형식은 sfc/dq5/docs/dq5-build-format.md 의 「행동 번호 늘리기」. 롬 세 벌을 만든다.
  spell  dq5spellgrow.py(C6·C7, class spell) + dq5namewrite.py --append(표 3 의 AB~C5 빈 이름과 C6·C7 이름) + 주인공 습득 레벨 2
         + 주인공 필드 목록 첫 칸 C6, 전투 목록 첫 두 칸 C6·C7(dq5learnwrite.py --spells-from)
  skill  위와 같고 class 만 skill(66 경계를 그대로 둠)
  base   목록만 바꾼 대조 롬
원본 롬과도 견준다(전투 목록 첫 칸 ホイミ 그대로). 원본 롬·선실 상태는 읽기만 한다.

  MESENCE=… python sfc/dq5/tools/dq5spellgrowcheck.py rom/dq5.sfc --state work/state/ship.mss
"""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

from dq5learnwrite import FORMAT as LEARN_FORMAT, dump as learn_dump
from dq5map import Rom
from dq5namewrite import read_tables
from dq5progresscheck import command, environment, require, run, save_json
from dq5spellgrow import FIELD_STUB, FX, FX_COUNT, MENU_MP, WIDE

HERE = Path(__file__).resolve().parent
AT = '6E:8000'
NAMES_AT = '6F:8000'
NEW = (0xC6, 0xC7)
COPY = (0x27, 0x01)
FIELD_USE = 'b:4,wait:40,a:4,wait:30,right:4,wait:20,a:4,wait:40,a:4,wait:40,a:4,wait:200'
BATTLE_USE = 'a:4,wait:30,down:4,wait:20,a:4,wait:40,a:4,wait:40,a:4,wait:200'
ITEM_USE = 'a:4,wait:30,down:4,wait:10,down:4,wait:10,a:4,wait:40,down:4,wait:20,a:4,wait:40,a:4,wait:40,a:4,wait:200'
BATTLE_SECOND = 'a:4,wait:30,down:4,wait:20,a:4,wait:40,right:4,wait:20,a:4,wait:40,a:4,wait:40,a:4,wait:200'
# 주인공 상태: 7E:0765 bit4 マホトーン(주문 봉인), 7E:0768 bit2 저주(장비).
SEALED, CURSED = '7E0765=10', '7E0768=04'


def build(original, out):
    data = original.read_bytes()
    names = read_tables(data)[3]
    # 21:955D 는 n 번 건너뛰므로 C6 앞의 AB~C5 에도 (빈) 이름 칸이 있어야 한다.
    blank = [{'id': n, 'bytes': []} for n in range(0xAB, NEW[0])]
    save_json(out / 'names.json', {'format': 'dq5names/1', 'tables': [{'table': 3, 'names': blank + [
        {'id': n, 'bytes': names[c] + names[c][-1:]} for n, c in zip(NEW, COPY)]}]})
    command('dq5namewrite.py', original, 'check', out / 'names.json', '--at', NAMES_AT, '--append')
    command('dq5namewrite.py', original, 'patch', out / 'names.json', '--at', NAMES_AT, '--append', '-o', out / 'names.patch.json')
    for kind in ('spell', 'skill'):
        source = out / f'grow-{kind}.json'
        save_json(source, {'format': 'dq5spellgrow/1', 'spells': [
            {'id': f'{n:02X}', 'copy': f'{c:02X}', 'class': kind} for n, c in zip(NEW, COPY)]})
        command('dq5spellgrow.py', original, 'check', source, '--at', AT)
        command('dq5spellgrow.py', original, 'patch', source, '--at', AT, '-o', out / f'grow-{kind}.patch.json')
    # 습득 목록에 새 번호를 넣으려면 dq5learnwrite.py 가 늘린 롬에서 받는 범위를 읽는다.
    command('dq5build.py', original, 'build', out / 'grow-spell.patch.json', '-o', out / 'spells.sfc')
    hero = learn_dump(Rom(data))['characters'][0]
    hero['learn'][0]['level'] = 2
    hero['field'][0] = NEW[0]
    hero['battle'][:2] = list(NEW)
    save_json(out / 'learn.json', {'format': LEARN_FORMAT, 'characters': [hero]})
    command('dq5learnwrite.py', original, 'check', out / 'learn.json', '--spells-from', out / 'spells.sfc')
    command('dq5learnwrite.py', original, 'patch', out / 'learn.json', '-o', out / 'learn.patch.json',
            '--spells-from', out / 'spells.sfc')
    for kind in ('spell', 'skill'):
        command('dq5build.py', original, 'build', *[out / f'{p}.patch.json' for p in ('learn', f'grow-{kind}', 'names')],
                '-o', out / f'{kind}.sfc', '--ips', out / f'{kind}.ips')
    command('dq5build.py', original, 'build', out / 'learn.patch.json', '-o', out / 'base.sfc', '--ips', out / 'base.ips')


def places():
    """새 번호 칸의 CPU 주소. 256칸 표와 주문 목록 MP 는 제자리, 연출 표 둘은 AT 부터 D5 칸씩."""
    bank, low = (int(v, 16) for v in AT.split(':'))
    at = bank << 16 | low
    out = {name: [base + n * size for n in NEW] for name, (base, size, _) in WIDE.items()}
    out['menu_mp'] = [MENU_MP + n for n in NEW]
    for k, name in enumerate(FX):
        out[name] = [at + k * FX_COUNT + n for n in NEW]
    return out


def scene(name, rom, state, out, mesence, libdir, mode, driver, **options):
    dest = out / name
    env = environment(libdir, state, dest)
    env.update(MODE=mode, DRIVER=str(HERE / 'lua' / driver), **options,
               READS=','.join(f'{a:06X}' for addrs in places().values() for a in addrs),
               EXECS=f'{FIELD_STUB:06X},248C39,248BAF,20A7C5')
    run(mesence, rom, HERE / 'lua/dq5spellgrowcheck.lua', dest, env)
    text = (dest / 'observed.txt').read_text()
    require('truncated' not in text, f'{name}: 관측 기록이 잘림')
    return text, (dest / 'final.wram').read_bytes()


def said(text):
    return re.findall(r'pc=248C39 A=0([0-9A-F]{3})', text)


def fight(out, name):
    """전투 메시지마다 (번호, 주인공 HP, MP)."""
    rows = re.findall(r'msg ([0-9A-F]{3}) 7E2040=([0-9A-F]{84})', (out / name / 'battle.txt').read_text())
    return [(m, int.from_bytes(bytes.fromhex(r)[2:4], 'little'), int.from_bytes(bytes.fromhex(r)[4:6], 'little')) for m, r in rows]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('rom', type=Path)
    ap.add_argument('--state', required=True, type=Path)
    ap.add_argument('--mesence', default=os.environ.get('MESENCE'))
    ap.add_argument('--out', type=Path, default='work/spellgrowcheck')
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
        libdir = subprocess.run(['krpatch', 'sfc', 'lua'], capture_output=True, text=True, check=True, timeout=30).stdout.strip()
        build(original, out)
        prep = out / 'prepare'
        env = environment(libdir, state, prep)
        env.update(FIELD='341,56', BATTLE='00:1', SETTLE='300', SAVE='battle.mss', MAXF='1800')
        run(mesence, original, HERE / 'lua/dq5warp.lua', prep, env)
        battle = prep / 'battle.mss'
        require(battle.is_file(), '전투 상태 생성 실패')
        at = places()
        roms = {k: out / f'{k}.sfc' for k in ('spell', 'skill', 'base')} | {'original': original}
        results, runs = {}, 1

        for kind, message in (('spell', '0C7'), ('skill', '19F')):
            text, ram = scene(f'{kind}-level', roms[kind], battle, out, mesence, libdir, 'level', 'dq5battle.lua',
                              MAXF='1300', LOOP='a:4,wait:20', SHOTMSG=message)
            runs += 1
            require(ram[0x2052] == 2 and ram[0x2063:0x2066] == bytes([1, 1, 0]) and message in said(text),
                    f'{kind} 습득: 레벨 {ram[0x2052]}, 비트 {ram[0x2063:0x2066].hex()}, 메시지 {said(text)}')
            results[f'{kind} 습득'] = {'비트': '010100', '메시지': message}

        for rom in ('spell', 'base'):
            text, ram = scene(f'{rom}-field', roms[rom], state, out, mesence, libdir, 'field', 'dq5msg.lua',
                              LEARNED='010300', MAXF='650', PRE=FIELD_USE, SHOTS='160')
            runs += 1
            hp, mp = int.from_bytes(ram[0x2042:0x2044], 'little'), int.from_bytes(ram[0x2044:0x2046], 'little')
            if rom == 'spell':
                require(f'pc={FIELD_STUB:06X}' in text and f'read {at["menu_mp"][0]:06X}=03' in text and hp > 5 and mp == 97,
                        f'필드: 스텁·목록 MP 를 거치지 않거나 HP {hp}·MP {mp}')
            else:
                require(hp == 5 and mp == 100, f'base 필드: 외워짐 HP {hp}·MP {mp}')
            results[f'{rom} 필드'] = {'HP': [5, hp], 'MP': [100, mp]}

        # (이름, 롬, 입력, 상태, 기대: 주문 뒤 첫 메시지, MP)
        cases = [('spell-heal', 'spell', BATTLE_USE, None, '094', 97),
                 ('base-heal', 'base', BATTLE_USE, None, None, None),
                 ('spell-fire', 'spell', BATTLE_SECOND, None, '069', 98),
                 ('original-sealed', 'original', BATTLE_USE, SEALED, '076', 100),
                 ('spell-sealed', 'spell', BATTLE_USE, SEALED, '076', 100),
                 ('skill-sealed', 'skill', BATTLE_USE, SEALED, '076', 100),
                 ('original-cursed', 'original', BATTLE_USE, CURSED, '10F', 100),
                 ('spell-cursed', 'spell', BATTLE_USE, CURSED, '10F', 100),
                 ('skill-cursed', 'skill', BATTLE_USE, CURSED, '094', 97)]
        for name, rom, pre, poke, want, mp_want in cases:
            options = {'POKE': poke} if poke else {}
            text, _ = scene(name, roms[rom], battle, out, mesence, libdir, 'battle', 'dq5battle.lua',
                            LEARNED='000300', MAXF='650', PRE=pre, LOOP='wait:500', PEEK='7E2040:42', **options)
            runs += 1
            rows = fight(out, name)
            codes = [m for m, _, _ in rows]
            if want is None:
                require('094' not in codes, f'{name}: 회복함 {codes}')
                results[name] = {'메시지': codes}
                continue
            first = next((i for i, m in enumerate(codes) if m in ('070', '10F')), None)
            require(first is not None and (codes[first] == '10F' or first + 1 < len(codes)), f'{name}: 주문 메시지가 없음 {codes}')
            after = rows[first] if codes[first] == '10F' else rows[first + 1]
            require(after[0] == want and after[2] == mp_want, f'{name}: {after[0]}·MP {after[2]} 가 {want}·MP {mp_want} 가 아님 {codes}')
            results[name] = {'메시지': codes[first:first + 2], 'HP': after[1], 'MP': after[2]}
            if name.endswith('cursed'):
                # 20:A7C5(RTS) 의 A 가 저주 검사 결과. 66 밑이거나 새 주문이면 불리고 1, 특기면 불리지 않는다.
                called = re.search(r'pc=20A7C5 A=..(..)', text)
                require((called is not None and called[1] == '01') == (rom != 'skill'), f'{name}: 저주 검사 20:A7B4 경로가 다름')
            if name in ('spell-heal', 'spell-fire'):
                k = 0 if name == 'spell-heal' else 1
                require(all(f'read {at[t][k]:06X}' in text for t in ('flags', 'executor', 'handler')),
                        f'{name}: 새 번호의 MP·실행·처리 칸을 읽지 않음')
            if name == 'spell-fire':
                require(f'read {at["fx_party"][1]:06X}=' in text, 'C7: 옮긴 연출 표를 읽지 않음')
        # 전투 도구(행동 D5 이상)는 256칸 표의 원래 칸을 그대로 쓴다. やくそう 를 가진 물건 셋째 칸에 둔다.
        scene('spell-item', roms['spell'], battle, out, mesence, libdir, 'battle', 'dq5battle.lua', LEARNED='000000',
              MAXF='400', PRE=ITEM_USE, LOOP='wait:500', PEEK='7E2040:42', POKE='7E2058=A1')
        runs += 1
        codes = [m for m, _, _ in fight(out, 'spell-item')]
        require(codes[:2] == ['0D3', '094'], f'spell-item: やくそう 를 쓰지 못함 {codes}')
        results['spell-item'] = {'메시지': codes[:2]}
        save_json(out / 'results.json', results)
        print(f'{runs}회 실행, 새 행동 C6·C7 의 습득·필드·전투·주문 막기 게임 검사 통과')
        print(json.dumps(results, ensure_ascii=False))
        return 0
    except (OSError, ValueError, KeyError, StopIteration, subprocess.SubprocessError) as error:
        print(f'오류: {error}', file=sys.stderr)
        if isinstance(error, subprocess.CalledProcessError) and error.output:
            print(error.output, file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
