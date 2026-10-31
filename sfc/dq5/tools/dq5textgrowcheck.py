"""3200 이상에 덧붙인 보행 메시지를 MesenCE 에서 부르는 길마다 띄워, 디코더가 푼 첫 64코드를 입력과 견준다.

덧붙인 롬은 3200~1FFF(4,992개)를 붙여 38:8000 에 둔다. C80·CC5·CE8·13C5·1FFF 만 글자가 있고 나머지는 {1001} 이다.
  대화 번호: 선실 파파스의 대화 번호를 POKE 로 8BA·8FF·FFF 로 바꿔(메시지 T + 3C6) 말을 건다
  대화 스크립트: dq5talkwrite 로 012(파파스)를 msg C80, msg 1FFF 로 바꿔 말을 건다
  이벤트 명령 60·인물 인라인 21·30·31·32: dq5scriptcheck.py 와 같은 17/00 인물(05:A84F)이 이벤트 번호 7 을 부르거나
    인라인 명령을 실행
  덧붙인 스크립트와 함께: dq5talkwrite --extra-at 으로 대화 900~921 을 덧붙인 롬에서 900·921(스크립트가 C80·1FFF)과
    끝 뒤 922·FFF(메시지 CE8·13C5), 900 앞 8FF(CC5)를 같은 파파스 길로 건다
원래 메시지 633·742·C7F 는 원본 롬과 덧붙인 롬에서 같은 64코드인지 본다.
원본 롬·선실 상태는 읽기만 하고 출력은 --out 의 새 하위 폴더에 둔다.
  MESENCE=… python sfc/dq5/tools/dq5textgrowcheck.py rom/dq5.sfc --state work/state/ship.mss
"""
import argparse
import concurrent.futures
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
from dq5text import CHARS  # noqa: E402
from dq5textwrite import FORMAT, overrides, read_messages  # noqa: E402

LAST = 0x1FFF
TEXTS = {0xC80: 'あいうえお', 0xCC5: 'かきくけこ', 0xCE8: 'なにぬねの', 0x13C5: 'さしすせそ', 0x1FFF: 'たちつてと'}
TALK = 'b:4,wait:40,up:3,wait:20,a:4,wait:30,a:4,wait:150' + ',a:4,wait:100' * 3
DIRECT = {0x8BA: 0xC80, 0x8FF: 0xCC5, 0xFFF: 0x13C5, 0x26D: 0x633, 0x37C: 0x742, 0x8B9: 0xC7F}
ORIGINAL = (0x26D, 0x37C, 0x8B9)
RETURN = {'original': '249E46', 'grown': '388044'}
# 대화 900~921(묶음 둘, 끝 922). 900·921 만 덧붙인 메시지를 띄우고 나머지는 원래 메시지 129.
EXTRA_SCRIPTS = {0x900: 'C80', 0x921: '1FFF'}
EXTRA = ['--extra-at', '3F:8000', '--hook-at', '06:FE10']
EXTRA_TALK = {0x900: 0xC80, 0x921: 0x1FFF, 0x922: 0xCE8, 0xFFF: 0x13C5, 0x8FF: 0xCC5}
INLINE = {'30': 0xC80, '31': 0xCC5, '32': 0x1FFF}


def tool(name, *args):
    subprocess.run([sys.executable, str(HERE / name), *map(str, args)], check=True, capture_output=True,
                   text=True, timeout=120)


def write_json(path, doc):
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    return path


def text_doc():
    rows = []
    for n in range(3200, LAST + 1):
        codes = [0x1006, *(CHARS.index(c) for c in TEXTS[n]), 0x1001] if n in TEXTS else [0x1001]
        rows.append({'id': n, 'codes': codes})
    return {'format': FORMAT, 'messages': rows}


def event_patches(rom, out, name, message):
    """dq5scriptcheck.py 의 번호 갈래: 17/00 인물이 61:8000 을 불러 이벤트 번호 7 을 표로 찾아 실행한다."""
    event = write_json(out / f'{name}.json', {
        'format': 'dq5event/1', 'binding': {'kind': 'number', 'index': 7},
        'commands': [{'op': '60', 'args': [message & 0xFF, message >> 8]}, {'op': 'FF'}]})
    tool('dq5eventwrite.py', rom, 'patch', event, '--at', '60:8000', '-o', out / f'{name}.dq5patch.json')
    stub = write_json(out / f'{name}-stub.dq5patch.json', {
        'format': 'dq5patch/1', 'name': 'table-call', 'rom_size': 4,
        'writes': [{'at': '61:8000', 'hex': 'A90722F4E2236B'}]})
    return [out / f'{name}.dq5patch.json', stub, npc_patch(rom, out, name, [{'op': '37', 'args': [0, 128, 97]}])]


def npc_patch(rom, out, name, commands):
    source = write_json(out / f'{name}-npc.json', {
        'format': 'dq5npcscript/1', 'address': '05:A84F', 'length': 23, 'commands': [*commands, {'op': '16'}]})
    tool('dq5npcwrite.py', rom, 'patch', source, '-o', out / f'{name}-npc.dq5patch.json')
    return out / f'{name}-npc.dq5patch.json'


def run(name, rom, out, mesence, libdir, state, inner, ret, **extra):
    dest = out / name
    dest.mkdir()
    env = {k: v for k, v in os.environ.items() if k not in ('ROMPATCH', 'SET', 'POKE', 'CALLS', 'DUMP', 'SHOTS', 'LOG')}
    env.update(LIBDIR=libdir, STATE=str(state), SHOT_DIR=str(dest), INNER=str(inner), RETURN_PC=ret, **extra)
    with (dest / 'mesen.log').open('w', encoding='utf-8') as log:
        subprocess.run([str(mesence), '--testrunner', str(rom), str(HERE / 'lua/dq5textgrowcheck.lua'),
                        '--Snes.DisableFrameSkipping=true'], env=env, stdout=log, stderr=subprocess.STDOUT,
                       check=True, timeout=150)
    rows = []
    for line in (dest / 'decoded.txt').read_text(encoding='utf-8').split('\n'):
        if line:
            n, stream, *codes = line.split()
            rows.append((int(n, 16), stream, [int(c, 16) for c in codes]))
    return rows


def papas(name, rom, talk, out, mesence, libdir, state, ret):
    return run(name, rom, out, mesence, libdir, state, HERE / 'lua/dq5msg.lua', ret, MAXF='900', PRE=TALK,
               POKE=f'7E36EB={talk & 0xFF:02X};7E370B={talk >> 8:02X}')


def walk(name, rom, out, mesence, libdir, state, ret):
    """dq5scriptcheck.py 와 같은 길로 17/00 에 가서 05:A84F 인물의 스크립트가 돌게 한다."""
    return run(name, rom, out, mesence, libdir, state, HERE / 'lua/dq5scriptcheck.lua', ret,
               DRIVER=str(ROOT / 'tools/lua/walk.lua'), PRE='b:4,wait:40', WAYPOINTS='3,11;3,24;7,24;up:10',
               ROMPATCH='156FF5=E0090B0117', CHANGES='99', MAXF='1000', AFTER='120', HOLD='90')


def judge(case, rows, wanted, messages):
    """wanted 번호가 처음 나온 줄의 코드가 messages[wanted:] 를 이은 앞부분과 같은지."""
    row = next((r for r in rows if r[0] == wanted), None)
    if row is None:
        return {'case': case, 'message': f'{wanted:03X}', 'seen': [f'{r[0]:03X}' for r in rows], 'passed': False}
    expected = [c for codes in messages[wanted:] for c in codes][:64]
    actual = row[2][:len(expected)]
    return {'case': case, 'message': f'{wanted:03X}', 'stream': row[1], 'codes': len(actual),
            'first': ' '.join(f'{c:03X}' for c in actual[:len(messages[wanted])]), 'passed': actual == expected}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('rom', type=Path)
    ap.add_argument('--state', required=True, type=Path)
    ap.add_argument('--mesence', default=os.environ.get('MESENCE'))
    ap.add_argument('--out', type=Path, default='work/textgrowcheck')
    args = ap.parse_args()
    if not args.mesence:
        ap.error('--mesence 또는 MESENCE가 필요함')
    try:
        original, state, mesence = args.rom.resolve(), args.state.resolve(), Path(args.mesence).resolve()
        for path in (original, state, mesence):
            if not path.is_file():
                raise ValueError(f'파일 없음: {path}')
        args.out.mkdir(parents=True, exist_ok=True)
        out = Path(tempfile.mkdtemp(prefix='run-', dir=args.out.resolve()))
        print(f'실행 출력: {out}', flush=True)
        source = original.read_bytes()
        doc = text_doc()
        before = read_messages(source)
        messages = overrides(before, doc)
        text = write_json(out / 'text.json', doc)
        tool('dq5textwrite.py', original, 'check', text)
        tool('dq5textwrite.py', original, 'patch', text, '-o', out / 'text.dq5patch.json')
        talk = write_json(out / 'talk.json', {'format': 'dq5talk/1', 'scripts': [
            {'talk': '012', 'body': [{'op': 'msg', 'id': 'C80'}, {'op': 'msg', 'id': '1FFF'}]}]})
        tool('dq5talkwrite.py', original, 'patch', talk, '-o', out / 'talk.dq5patch.json')
        extra = write_json(out / 'extra.json', {'format': 'dq5talk/1', 'scripts': [
            {'talk': f'{t:03X}', 'body': [{'op': 'msg', 'id': EXTRA_SCRIPTS.get(t, '129')}]}
            for t in range(0x900, 0x922)]})
        tool('dq5talkwrite.py', original, 'check', extra, *EXTRA)
        tool('dq5talkwrite.py', original, 'patch', extra, '-o', out / 'extra.dq5patch.json', *EXTRA)
        builds = {'grown': [], 'talk': [out / 'talk.dq5patch.json'],
                  'event-C80': event_patches(original, out, 'event-C80', 0xC80),
                  'event-1FFF': event_patches(original, out, 'event-1FFF', 0x1FFF),
                  'inline-1FFF': [npc_patch(original, out, 'inline-1FFF', [{'op': '21', 'args': [0xFF, 0x1F]}])],
                  'extra': [out / 'extra.dq5patch.json']}
        for op, n in INLINE.items():
            builds[f'inline{op}-{n:03X}'] = [npc_patch(original, out, f'inline{op}-{n:03X}',
                                                       [{'op': op, 'args': [n & 0xFF, n >> 8]}])]
        roms = {}
        for name, extra in builds.items():
            roms[name] = out / f'{name}.sfc'
            tool('dq5build.py', original, 'build', out / 'text.dq5patch.json', *extra, '--size', '4',
                 '-o', roms[name], '--ips', out / f'{name}.ips')
        libdir = subprocess.run(['krpatch', 'sfc', 'lua'], capture_output=True, text=True,
                                check=True, timeout=30).stdout.strip()
        common = (out, mesence, libdir, state)
        jobs = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            for t in DIRECT:
                jobs[f'grown-{t:03X}'] = pool.submit(papas, f'grown-{t:03X}', roms['grown'], t, *common,
                                                     RETURN['grown'])
            for t in ORIGINAL:
                jobs[f'original-{t:03X}'] = pool.submit(papas, f'original-{t:03X}', original, t, *common,
                                                        RETURN['original'])
            jobs['talk-012'] = pool.submit(papas, 'talk-012', roms['talk'], 0x012, *common, RETURN['grown'])
            for t in EXTRA_TALK:
                jobs[f'extra-{t:03X}'] = pool.submit(papas, f'extra-{t:03X}', roms['extra'], t, *common,
                                                     RETURN['grown'])
            inline = [f'inline{op}-{n:03X}' for op, n in INLINE.items()]
            for name in ('event-C80', 'event-1FFF', 'inline-1FFF', *inline):
                jobs[name] = pool.submit(walk, name, roms[name], *common, RETURN['grown'])
            got = {name: job.result() for name, job in jobs.items()}
        results = [judge(f'대화 번호 {t:03X}', got[f'grown-{t:03X}'], n, messages) for t, n in DIRECT.items()]
        results += [judge(f'원본 롬 대화 번호 {t:03X}', got[f'original-{t:03X}'], DIRECT[t], before) for t in ORIGINAL]
        results += [judge(f'대화 스크립트 012 ({n:03X})', got['talk-012'], n, messages) for n in (0xC80, 0x1FFF)]
        results += [judge('이벤트 명령 60 C80', got['event-C80'], 0xC80, messages),
                    judge('이벤트 명령 60 1FFF', got['event-1FFF'], 0x1FFF, messages),
                    judge('인물 인라인 21 1FFF', got['inline-1FFF'], 0x1FFF, messages)]
        results += [judge(f'인물 인라인 {op} {n:03X}', got[f'inline{op}-{n:03X}'], n, messages)
                    for op, n in INLINE.items()]
        results += [judge(f'덧붙인 스크립트 롬 대화 번호 {t:03X}', got[f'extra-{t:03X}'], n, messages)
                    for t, n in EXTRA_TALK.items()]
        for t in ORIGINAL:
            # C7F 뒤는 원본 롬에서는 메시지가 아니므로 원래 메시지 3,200개 안의 코드만 견준다.
            n = DIRECT[t]
            k = len([c for codes in before[n:] for c in codes][:64])
            a, b = ([r[2][:k] for r in got[f'{rom}-{t:03X}'] if r[0] == n][:1] for rom in ('grown', 'original'))
            results.append({'case': f'원래 메시지 {n:03X} 원본 롬과 같은 앞 {k}코드', 'passed': bool(a) and a == b})
        write_json(out / 'results.json', results)
        for r in results:
            detail = f'{r.get("stream", "")} {r.get("first", "")}'.strip()
            print(f'{r["case"]}: {detail}{"" if r["passed"] else " 불일치 " + str(r.get("seen", ""))}')
        failed = [r['case'] for r in results if not r['passed']]
        if failed:
            raise ValueError(f'불일치: {", ".join(failed)}')
        print(f'{len(results)}개 검사 통과')
        return 0
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(f'오류: {error}', file=sys.stderr)
        if isinstance(error, subprocess.CalledProcessError) and error.stderr:
            print(error.stderr, file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
