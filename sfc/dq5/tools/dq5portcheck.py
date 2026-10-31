"""dq5portbuild.py 로 만든 통합 롬을 MesenCE 에서 검사한다. 보고(report.json)의 작업마다 기존 검사 도구의 장면을
통합 롬에 다시 돌리고, DQ4 타이틀·메뉴는 고정 롬과 같은 입력으로 돌려 메모리 덤프를 견준다.

  title  고정 롬과 통합 롬의 타이틀 대기·A 입력 뒤 메뉴 복귀(dq4titleintegrationcheck.lua)의 VRAM·OAM·CGRAM 과 사건 기록
  dq4    DQ4 트랙 검사 dq4nameentrycheck·dq4namecursorcheck·dq4namegamecheck 를 통합 롬으로 실행(--symbols 필요)
  text   고친 보행 메시지와 고치지 않은 메시지 하나를 디코더 반환 64코드로(dq5textcheck 의 장면)
  field  세계마다 필드에 서서 WRAM 지도 72KB 를 입력 지도와(dq5fieldtablecheck 의 장면)
  npc    인물 표 23칸·스크립트 포인터(dq5npcrelocatecheck 의 장면), 입력이 긴 스크립트 시험과 같으면 실행 5건
  map    고친 맵에 들어가 속성 패스 끝 01:BA4C 의 셀 버퍼를 롬 디코더와(dq5map --compare 와 같은 비교)
  event  번호 표·이벤트 표 조회로 새 스크립트를 실행(dq5scriptcheck 의 장면, 호출 틀은 실행 때만 ROMPATCH)
  patch  쓰기가 통합 롬에 그대로 있는지. dq5tablecheck 의 고친 값(칸·피해량)이 들어 있으면 그 장면을 통합 롬에서
npc 작업에 records 가 있으면 원래 롬에 레코드 패치만 넣은 롬으로 인물 표를 예측한다. 그 문서가 dq5npcrecordcheck 의
문서면 옮긴 인물이 낮에 새 대화 번호로 서고 말을 걸면 그 메시지가 뜨는지도 통합 롬에서 돌린다.

  MESENCE=… python sfc/dq5/tools/dq5portcheck.py rom/dq5.sfc work/port/build/report.json \\
      --state work/state/ship.mss --symbols work/menu/name-entry.sym --out work/port/check

원본 롬·고정 롬·세이브스테이트는 읽기만 한다. 롬 사본·덤프·결과는 --out 아래 새 실행 폴더에 쓴다.
"""
import argparse
import concurrent.futures
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
from dq5build import parse_at  # noqa: E402
from dq5fieldtablecheck import SCENES as FIELD_SCENES, read_dump  # noqa: E402
from dq5fieldwrite import read_grid, split  # noqa: E402
from dq5hangul import DECODER, DECODER_END  # noqa: E402
from dq5map import Decoder, Rom, map_pointer  # noqa: E402
from dq5mapmusic import entry_cells  # noqa: E402
import dq5npcrecordcheck as recordcheck  # noqa: E402
import dq5npcrelocatecheck as npccheck  # noqa: E402
import dq5scriptcheck as scriptcheck  # noqa: E402
from dq5textcheck import decoder_codes  # noqa: E402
from dq5textwrite import decoded_messages, relocated  # noqa: E402

DQ4 = HERE.parents[1] / 'dq4' / 'tools'
TITLE_RUNS = {'idle': {'MAXF': '1280', 'FROM': '300', 'EVERY': '64', 'SEQ': ''},
              'menu': {'MAXF': '700', 'FROM': '580', 'EVERY': '20', 'SEQ': 'a@420:2'}}
# 이벤트 호출 틀: 선실 인물 스크립트 첫머리를 네이티브 호출(37)로 바꾸고, 빈 자리에 LDA #번호 / JSL 표 조회 / RTL.
STUB = {'number': 'A90722F4E2236B', 'event': 'A908229AE2236B'}
UNCHANGED_MESSAGE = 0x742


def require(condition, message):
    if not condition:
        raise ValueError(message)


def mesence_run(mesence, rom, lua, env, dest, timeout=180):
    with (dest / 'mesen.log').open('w', encoding='utf-8') as log:
        subprocess.run([str(mesence), '--testrunner', str(rom), str(lua), '--Snes.RamPowerOnState=AllZeros',
                        '--Snes.DisableFrameSkipping=true'], env=env, stdout=log, stderr=subprocess.STDOUT,
                       check=True, timeout=timeout)


def check_title(report, port, out, mesence):
    """같은 입력으로 고정 롬과 통합 롬을 돌려 덤프가 바이트까지 같은지. 롬은 이름을 바꿔 SRAM 을 새로 쓴다."""
    require(report['fixed'], '비교할 고정 롬이 보고에 없음')
    fixed = Path(report['fixed'][0]['rom'])
    results = []
    for run, settings in TITLE_RUNS.items():
        dumps = {}
        for label, rom in (('fixed', fixed), ('port', port)):
            dest = out / f'title-{run}-{label}'
            dest.mkdir()
            copy = dest / f'{label}-{run}-{out.name}.sfc'
            shutil.copyfile(rom, copy)
            env = dict(os.environ, OUT=str(dest), **settings)
            mesence_run(mesence, copy, DQ4 / 'lua/dq4titleintegrationcheck.lua', env, dest)
            dumps[label] = dest
        names = sorted(p.name for p in dumps['fixed'].glob('[voc]*.bin'))
        require(names, f'title {run}: 덤프가 없음')
        bad = [n for n in names if (dumps['fixed'] / n).read_bytes() != (dumps['port'] / n).read_bytes()]
        events = [(dumps[k] / 'events.txt').read_text(encoding='utf-8') for k in ('fixed', 'port')]
        require(not bad, f'title {run}: 덤프 {len(bad)}개가 다름 {bad[:6]}')
        require(events[0] == events[1], f'title {run}: 사건 기록이 다름')
        results.append({'case': f'title-{run}', 'dumps_equal': len(names), 'events_equal': len(events[0].splitlines()),
                        'frames': sorted({n[1:5] for n in names})})
    return results


def check_dq4(port, symbols, state, out):
    results = []
    runs = [('dq4nameentrycheck.py', ['--rom', port, '--symbols', symbols, '--out', out / 'dq4-entry']),
            ('dq4namecursorcheck.py', ['--rom', port, '--symbols', symbols, '--out', out / 'dq4-cursor']),
            ('dq4namegamecheck.py', ['--rom', port, '--state', state, '--out', out / 'dq4-game'])]

    def run(item):
        tool, args = item
        r = subprocess.run([sys.executable, str(DQ4 / tool), *map(str, args)], capture_output=True, text=True,
                           timeout=1800)
        (out / f'{tool}.log').write_text(r.stdout + r.stderr, encoding='utf-8')
        lines = r.stdout.splitlines()
        passed, failed = sum(ln.startswith('PASS') for ln in lines), sum(ln.startswith('FAIL') for ln in lines)
        require(r.returncode == 0 and failed == 0 and passed, f'{tool}: 실패(종료값 {r.returncode}, FAIL {failed})')
        return {'case': tool, 'pass': passed, 'last': lines[-1] if lines else ''}

    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        results += list(pool.map(run, runs))
    return results


def check_text(report, port, out, state, mesence, libdir):
    data = port.read_bytes()
    decoder, _ = relocated(data)
    ret = f'{decoder + DECODER_END - DECODER - 1:06X}'
    messages = decoded_messages(data)
    jobs = [j for j in report['jobs_input'] if j['kind'] == 'text']
    results = []
    for job in jobs:
        ids = [row['id'] for row in json.loads(Path(job['input']).read_text(encoding='utf-8'))['messages']]
        for msg in dict.fromkeys(ids + [UNCHANGED_MESSAGE]):
            stream, actual = decoder_codes(port, msg, ret, out / f'text-{msg:03X}', state, mesence, libdir)
            expected = [code for row in messages[msg:] for code in row][:64]
            require(actual == expected, f'text {msg:03X}: 코드 불일치 {actual[:12]}, 기대 {expected[:12]}')
            results.append({'case': f'text-{msg:03X}', 'stream': f'{stream:06X}', 'codes_equal': len(actual)})
    return results


def gfx_scene(port, name, env_extra, out, state, mesence, libdir):
    dest = out / name
    dest.mkdir()
    env = os.environ.copy()
    for key in ('ADULT', 'ANYWHERE', 'BATTLE', 'FIELD', 'GROUP', 'LATESET', 'PARTY', 'POKE', 'ROMPATCH',
                'SAVE', 'SET', 'TEST', 'TO', 'WAGON', 'EVERY', 'FROM', 'AT'):
        env.pop(key, None)
    env.update(LIBDIR=str(libdir), STATE=str(state), SHOT_DIR=str(dest), MAXF='1800', SETTLE='900', DUMPF='900')
    env.update(env_extra)
    return dest, env


def check_field(report, port, out, state, mesence, libdir):
    jobs = [j for j in report['jobs_input'] if j['kind'] == 'field']

    def run(job):
        w = job['world']
        name = f'world{w}'
        dest, env = gfx_scene(port, name, FIELD_SCENES[name], out, state, mesence, libdir)
        mesence_run(mesence, port, HERE / 'lua/dq5gfxdump.lua', env, dest)
        ram, _, _ = read_dump(out, name)
        low, high = split(read_grid(job['input']))
        require(ram[0x1949] == w and ram[0xBE] & 0x80 == 0, f'세계 {w}: 필드에 서지 않음')
        diff = sum(a != b for a, b in zip(low + high, ram[0x10000:] + ram[0xE000:0x10000]))
        require(diff == 0, f'세계 {w}: 지도 {diff}바이트 다름')
        return {'case': name, 'bytes': len(low) + len(high), 'differences': diff}

    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        return list(pool.map(run, jobs))


def check_npc(report, original_path, port, out, state, mesence, libdir, bootdir):
    original = Rom(original_path.read_bytes())
    results = []
    for job in [j for j in report['jobs_input'] if j['kind'] == 'npc']:
        layout = json.loads(Path(job['layout']).read_text(encoding='utf-8'))
        model = records_model(job, original_path, out) if 'records' in job else None
        cases = [(bc, bd, night, '') for bc, bd in ((0x17, 0), (2, 6), (1, 5)) for night in (False, True)]
        cases += [(2, 6, night, ';7E21AD=10') for night in (False, True)]
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            results += list(pool.map(lambda c: npccheck.compare_case(c, out, original_path, port, original, layout,
                                                                     state, mesence, libdir, model), cases))
        source = json.loads(Path(job['input']).read_text(encoding='utf-8'))
        if source == npccheck.MUTATION_SOURCE:
            results += npccheck.run_mutations(out, port, layout, state, mesence, libdir, 4)
        if model is not None and json.loads(Path(job['records']).read_text(encoding='utf-8')) == RECORD_SOURCE:
            results.append(check_records(port, model, out, state, mesence, bootdir))
    return results


# dq5npcrecordcheck 의 레코드 문서. 이 문서면 그 도구의 장면을 통합 롬에서 돌린다.
RECORD_SOURCE = {'format': 'dq5npcrecord/1', 'entries': recordcheck.ENTRIES}


def records_model(job, original_path, out):
    """원래 롬에 인물 레코드 패치만 넣은 롬. 재배치 롬의 인물 표는 이 롬의 목록·필드와 같아야 한다."""
    dest = out / f'{job["name"]}-records'
    dest.mkdir()
    recordcheck.command('dq5npcrecord.py', original_path, 'patch', job['records'], '-o', dest / 'records.dq5patch.json')
    recordcheck.command('dq5build.py', original_path, 'build', dest / 'records.dq5patch.json', '-o',
                        dest / 'records.sfc', '--ips', dest / 'records.ips')
    return Rom((dest / 'records.sfc').read_bytes())


def check_records(port, model, out, state, mesence, bootdir):
    """옮긴 밤 인물이 낮에 (24,12)에 그림 18·대화 300 으로 서고, 말을 걸면 메시지 300 + 3C6 이 뜨는지."""
    rows = {}
    for name, night, test in (('records-day', False, recordcheck.TALK_TEST), ('records-night', True, '')):
        wram, messages = recordcheck.run((name, 'port', night, test), {'port': port}, state, out, mesence, bootdir)
        source, placed, expected = recordcheck.slots(model, wram, 2, 6, night)
        bad = recordcheck.compare(wram, expected, (0x3480, 0x34A0))
        require(not bad, f'{name}: 인물 표 {bad[:6]}')
        rows[name] = (wram, messages, [at for at, _ in placed])
    wram, messages, placed = rows['records-day']
    require(recordcheck.MOVED in placed, '옮긴 인물이 낮 목록에 없음')
    at = 8 + placed.index(recordcheck.MOVED)
    cell = tuple(wram[c + at] for c in (0x3020, 0x3080, 0x3220, 0x36E0, 0x3700))
    want = (24, 12, 0x18, recordcheck.TALK & 0xFF, recordcheck.TALK >> 8)
    require(cell == want, f'옮긴 인물 칸·그림·대화 {cell} != {want}')
    require(recordcheck.MESSAGE in messages, f'말을 건 메시지에 {recordcheck.MESSAGE:03X} 없음: {messages}')
    require(rows['records-night'][2] == [recordcheck.NIGHT], f'밤 목록 {rows["records-night"][2]}')
    return {'case': 'records', 'moved': f'{recordcheck.MOVED:06X}', 'cell': list(cell),
            'messages': [f'{m:03X}' for m in messages], 'night': [f'{a:06X}' for a in rows['records-night'][2]]}


# dq5tablecheck 의 고친 값 가운데 통합 롬 하나에 함께 넣어도 서로의 장면을 바꾸지 않는 것.
TABLE_EDITS = ('slot', 'amount')


def check_patch(report, original_path, port, out, state, mesence, libdir):
    """patch 작업의 쓰기가 통합 롬에 그대로 있는지. dq5tablecheck 의 고친 값을 담고 있으면 그 장면을 통합 롬에서 돌린다."""
    from dq5build import load
    import dq5tablecheck as tablecheck
    data = port.read_bytes()
    results = []
    for job in [j for j in report['jobs_input'] if j['kind'] == 'patch']:
        _, _, writes = load(job['input'])
        bad = [where for off, payload, _, where in writes if data[off:off + len(payload)] != payload]
        require(not bad, f'{job["name"]}: 통합 롬에 없는 쓰기 {bad[:6]}')
        have = {(off, payload) for off, payload, _, _ in writes}
        found = []
        for name in TABLE_EDITS:
            source, manifest = out / f'table-{name}.json', out / f'table-{name}.dq5patch.json'
            source.write_text(json.dumps({'format': 'dq5tables/1', **tablecheck.EDITS[name]}, ensure_ascii=False),
                              encoding='utf-8')
            recordcheck.command('dq5tables.py', original_path, 'patch', source, '-o', manifest)
            if {(off, payload) for off, payload, _, _ in load(str(manifest))[2]} <= have:
                found.append(name)
        row = {'case': job['name'], 'writes': len(writes), 'in_rom': True, 'table_edits': found}
        if 'slot' in found:
            tablecheck.run_case('shop', 'port', port, state, out, mesence, libdir, {})
            text = tablecheck.observed(out, 'shop-port')
            require('read 23B237=01 pc=21A43D' in text and '23B237=00' not in text, '칸: 23:B237 을 01 로 읽지 않음')
            shown = tablecheck.wram(out, 'shop-port')[0x46]
            require(shown == 16, f'칸: 비교 창 새 능력치가 16 이 아님: {shown}')
            row['slot'] = {'read': '23B237=01', 'shown': shown}
        if 'amount' in found:
            tablecheck.run_case('papas', 'port', port, state, out, mesence, libdir, {})
            hits = tablecheck.casts(out, 'papas-port')
            require(len(hits) >= 2 and all(len(h) == 1 and h[0][1] == 40 for h in hits), f'피해량: {hits}')
            require('read 278073=28' in tablecheck.observed(out, 'papas-port'), '피해량: 27:8073 을 28 로 읽지 않음')
            row['amount'] = hits
        results.append(row)
    return results


def check_map(report, original_path, port, out, state, mesence, libdir):
    """원본과 다른 맵(고친 맵)마다 들어가 01:BA4C 에서 WRAM 을 덤프하고 통합 롬의 디코더 결과와 견준다."""
    rom = Rom(port.read_bytes())
    original = Rom(original_path.read_bytes())
    from dq5mapwrite import encode, parse
    edited = []
    for job in [j for j in report['jobs_input'] if j['kind'] == 'map']:
        for path in job['inputs']:
            doc = json.loads(Path(path).read_text(encoding='utf-8'))
            bc, bd = (int(v, 16) for v in doc['map'].split('/'))
            if encode(doc) != encode(parse(original, map_pointer(original, bc, bd))[0]):
                edited.append(doc['map'])
    if not edited:
        return []
    cells = entry_cells(str(port), edited)
    libmap = out / 'maplib'
    results = []
    for name in edited:
        bc, bd = (int(v, 16) for v in name.split('/'))
        tag = f'map-{bc:02X}{bd:02X}'
        dest, env = gfx_scene(port, tag, {}, out, state, mesence, libdir)
        env.update(LIBDIR=str(libmap), AT='01BA4C', TO=f'{name},' + ','.join(str(v) for v in cells[name]),
                   MAXF='1500')
        mesence_run(mesence, port, ROOT / 'tools/lua/atpc.lua', env, dest)
        wram = (dest / 'at_01BA4C.bin').read_bytes()
        require(wram[0xBC] == bc and wram[0xBD] == bd, f'{tag}: 맵 번호가 {wram[0xBC]:02X}/{wram[0xBD]:02X}')
        dec = Decoder(rom, 0xBE, bc >= 0x50, (bc, bd))
        dec.preload(bc, bd)
        width, height, buf, _ = dec.decode(map_pointer(rom, bc, bd))
        diff = sum(a != b for a, b in zip(buf, wram[0xC000:0xC000 + len(buf)]))
        require(diff == 0, f'{tag}: 셀 버퍼 {diff}바이트 다름')
        old = Decoder(original, 0xBE, bc >= 0x50, (bc, bd))
        old.preload(bc, bd)
        before = old.decode(map_pointer(original, bc, bd))[2]
        changed = sum(buf[i:i + 8] != before[i:i + 8] for i in range(0, len(buf), 8))
        results.append({'case': tag, 'pointer': f'{map_pointer(rom, bc, bd):06X}', 'cells': width * height,
                        'bytes': len(buf), 'differences': diff, 'cells_changed_from_original': changed})
    return results


def check_event(report, port, out, state, mesence, libdir):
    """새 스크립트 주소를 보고에서 찾고, 실행 때만 선실 인물 스크립트를 호출 틀로 덮어 게임의 표 조회를 탄다."""
    if not any(j['kind'] == 'event' for j in report['jobs_input']):
        return []
    require(report.get('scratch'), '호출 틀을 덮을 빈 자리(scratch)가 보고에 없음')
    data = port.read_bytes()
    npc = [j for j in report['jobs_input'] if j['kind'] == 'npc']
    cabin = '05:A84F'
    if npc:
        layout = json.loads(Path(npc[0]['layout']).read_text(encoding='utf-8'))
        cabin = layout['scripts'][cabin]
    body = parse_at(cabin)[0] + 1
    stub = parse_at(report['scratch'])[0]
    require(not any(data[stub:stub + 7]), f'호출 틀 자리 {report["scratch"]} 가 비어 있지 않음')
    bank, low = stub // 0x8000, 0x8000 + stub % 0x8000
    call = f'37{low & 0xFF:02X}{low >> 8:02X}{bank:02X}16'
    results = []
    for job in [j for j in report['jobs_input'] if j['kind'] == 'event']:
        for path in job['inputs']:
            doc = json.loads(Path(path).read_text(encoding='utf-8'))
            mode = doc['binding']['kind']
            index = doc['binding']['index']
            require((mode, index, doc['commands']) == scriptcheck_case(mode),
                    f'{path}: dq5scriptcheck 의 {mode} 시험 스크립트가 아니라 실행 기대값이 없음')
            at = event_address(data, mode, index)
            case = (mode, None, (8, 9))
            res = scriptcheck.run_case(case, out, state, mesence, libdir, rom=port, at=at,
                                       rompatch=f'{body:X}={call};{stub:X}={STUB[mode]}')
            res['script'] = f'{at:06X}'
            results.append(res)
    return results


def scriptcheck_case(mode):
    commands = [{'op': '10', 'args': [127, 64]}, {'op': '01', 'args': [2]}, {'op': 'FF'}]
    return mode, 7 if mode == 'number' else 8, commands


def event_address(data, mode, index):
    from dq5eventwrite import EVENTS, NUMBERED
    rom = Rom(data)
    return rom.u24(EVENTS + index * 5 + 2) if mode == 'event' else rom.u24(NUMBERED + index * 3)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('rom', type=Path)
    ap.add_argument('report', type=Path)
    ap.add_argument('--state', type=Path, required=True)
    ap.add_argument('--symbols', type=Path, help='DQ4 이름 입력 빌드의 심볼 파일(dq4 검사)')
    ap.add_argument('--mesence', default=os.environ.get('MESENCE'))
    ap.add_argument('--out', type=Path, default=Path('work/port/check'))
    ap.add_argument('--only', help='쉼표로 고른 묶음(title,dq4,text,field,npc,map,event,patch)')
    args = ap.parse_args()
    if not args.mesence:
        ap.error('--mesence 또는 MESENCE 가 필요함')
    try:
        original, state, mesence = args.rom.resolve(), args.state.resolve(), Path(args.mesence).resolve()
        report = json.loads(args.report.read_text(encoding='utf-8'))
        port = Path(report['rom']).resolve()
        for path in (original, state, mesence, port):
            require(path.is_file(), f'파일 없음: {path}')
        args.out.mkdir(parents=True, exist_ok=True)
        out = Path(tempfile.mkdtemp(prefix='run-', dir=args.out.resolve()))
        print(f'실행 출력: {out}', flush=True)
        krlua = Path(subprocess.run(['krpatch', 'sfc', 'lua'], capture_output=True, text=True, check=True,
                                    timeout=30).stdout.strip())
        libdir = out / 'lib'
        shutil.copytree(krlua, libdir)
        shutil.copyfile(HERE / 'lua/dq5warp.lua', libdir / 'boot.lua')
        shutil.copytree(krlua, out / 'maplib')
        shutil.copyfile(HERE / 'lua/dq5warp.lua', out / 'maplib' / 'boot.lua')
        groups = (args.only or 'title,dq4,text,field,npc,map,event,patch').split(',')
        results = {}
        if 'title' in groups:
            results['title'] = check_title(report, port, out, mesence)
        if 'dq4' in groups:
            require(args.symbols, 'dq4 검사에는 --symbols 가 필요함')
            results['dq4'] = check_dq4(port, args.symbols.resolve(), state, out)
        if 'text' in groups:
            results['text'] = check_text(report, port, out, state, mesence, str(krlua))
        if 'field' in groups:
            results['field'] = check_field(report, port, out, state, mesence, libdir)
        if 'npc' in groups:
            results['npc'] = check_npc(report, original, port, out, state, mesence, str(krlua), libdir)
        if 'map' in groups:
            results['map'] = check_map(report, original, port, out, state, mesence, libdir)
        if 'event' in groups:
            results['event'] = check_event(report, port, out, state, mesence, str(krlua))
        if 'patch' in groups:
            results['patch'] = check_patch(report, original, port, out, state, mesence, str(krlua))
        (out / 'results.json').write_text(json.dumps(results, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
        for group, rows in results.items():
            print(f'{group}: {len(rows)}건 통과')
        print(json.dumps(results, ensure_ascii=False))
        return 0
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        print(f'오류: {error}', file=sys.stderr)
        if isinstance(error, subprocess.CalledProcessError) and error.output:
            print(error.output, file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
