"""그림 번호 표 늘리기(dq5picturegrow.py)를 MesenCE 에서 원본과 견준다.

02/06 의 밤 인물을 낮으로 옮겨 주인공 두 칸 위에 세우고(dq5npcrecord.py, dq5npcrecordcheck.py 와 같은 장면),
그 인물의 그림 번호를 바꾼 롬 넷을 돌린다.

  ref     그림 18(세트 04). 원래 그림 표 안
  base    그림 A9. 그림 표는 원래대로(A9 는 표 밖, 1E:DC67 이 A2 이상을 물체로)
  grown   그림 A9 + 그림 표를 늘려 A9 → 세트 04, 물체 아님
  object  그림 A9 + 같은 표에서 A9 를 물체로
  skip    그림 A9 + 같은 표에서 A9 를 말 걸기 목록(05:862F 를 옮긴 것)에 넣음. 물체는 아님

인물 목록을 다 놓은 직후(12:803C)의 7E:33A0 bit3(말을 걸 수 없음)·7E:3200(칸 목록 번호)과,
위를 보고 A 를 눌렀을 때 메시지 루틴이 받은 번호를 본다.
  MESENCE=… python sfc/dq5/tools/dq5picturegrowcheck.py rom/dq5.sfc --state work/state/ship.mss
"""
import argparse
import concurrent.futures
import copy
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from dq5npcrecordcheck import ENTRIES, MESSAGE, MOVED, REDRAWN, TALK_TEST, command, require, run, slots

HERE = Path(__file__).resolve().parent
AT = '0B:FBB0'
PICTURES = {'grown': {'object': False}, 'object': {'object': True}, 'skip': {'talk_skip': True}}


def entries(gfx):
    out = copy.deepcopy(ENTRIES)
    out[0]['fields']['gfx'] = gfx
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('rom', type=Path)
    ap.add_argument('--state', required=True, type=Path)
    ap.add_argument('--mesence', default=os.environ.get('MESENCE'))
    ap.add_argument('--out', type=Path, default='work/picturegrowcheck')
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
        manifests = {}
        for key, gfx in (('ref', 0x18), ('a9', 0xA9)):
            source = out / f'npc-{key}.json'
            source.write_text(json.dumps({'format': 'dq5npcrecord/1', 'entries': entries(gfx)}, ensure_ascii=False,
                                         indent=2) + '\n', encoding='utf-8')
            command('dq5npcrecord.py', original, 'patch', source, '-o', out / f'npc-{key}.dq5patch.json')
            manifests[key] = out / f'npc-{key}.dq5patch.json'
        for key, flags in PICTURES.items():
            source = out / f'pictures-{key}.json'
            source.write_text(json.dumps({'format': 'dq5pictures/1', 'pictures': [
                {'picture': 'A9', 'set': '04', **flags}]}, indent=2) + '\n', encoding='utf-8')
            command('dq5picturegrow.py', original, 'check', source, '--at', AT)
            command('dq5picturegrow.py', original, 'patch', source, '--at', AT, '-o', out / f'pictures-{key}.dq5patch.json')
        roms = {}
        for name, parts in (('ref', ['ref']), ('base', ['a9']), ('grown', ['a9', 'grown']), ('object', ['a9', 'object']),
                            ('skip', ['a9', 'skip'])):
            files = [manifests[p] if p in manifests else out / f'pictures-{p}.dq5patch.json' for p in parts]
            roms[name] = out / f'{name}.sfc'
            command('dq5build.py', original, 'build', *files, '-o', roms[name], '--ips', out / f'{name}.ips')
        krlua = Path(subprocess.run(['krpatch', 'sfc', 'lua'], capture_output=True, text=True,
                                    check=True, timeout=30).stdout.strip())
        libdir = out / 'lib'
        shutil.copytree(krlua, libdir)
        shutil.copyfile(HERE / 'lua/dq5warp.lua', libdir / 'boot.lua')
        cases = [(name, name, False, TALK_TEST) for name in roms]
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            seen = dict(zip(roms, pool.map(lambda case: run(case, roms, state, out, mesence, libdir), cases)))
        from dq5map import Rom
        results = {}
        for name, (wram, messages) in seen.items():
            _, placed, _ = slots(Rom(roms[name].read_bytes()), wram, 2, 6, False)
            order = [at for at, _ in placed]
            require(MOVED in order and REDRAWN in order, f'{name}: 두 인물이 놓이지 않음')
            moved, redrawn = 8 + order.index(MOVED), 8 + order.index(REDRAWN)
            results[name] = {'gfx': wram[0x3220 + moved], 'no_talk': bool(wram[0x33A0 + moved] & 0x08),
                             'list': wram[0x3200 + moved], 'list_18': wram[0x3200 + redrawn],
                             'talked': MESSAGE in messages, 'messages': [f'{m:03X}' for m in messages]}
        r = results
        checks = {
            'ref': r['ref']['gfx'] == 0x18 and not r['ref']['no_talk'] and r['ref']['talked'],
            'base': r['base']['gfx'] == 0xA9 and r['base']['no_talk'] and not r['base']['talked'],
            'grown': r['grown']['gfx'] == 0xA9 and not r['grown']['no_talk'] and r['grown']['talked']
            and r['grown']['list'] == r['grown']['list_18'],
            'object': r['object']['gfx'] == 0xA9 and r['object']['no_talk'] and not r['object']['talked'],
            'skip': r['skip']['gfx'] == 0xA9 and not r['skip']['no_talk'] and not r['skip']['talked']
            and r['skip']['list'] == r['skip']['list_18'],
        }
        (out / 'results.json').write_text(json.dumps({'cases': results, 'checks': checks}, ensure_ascii=False,
                                                     indent=2) + '\n', encoding='utf-8')
        for name, v in results.items():
            print(f'{name}: 그림 {v["gfx"]:02X} 말 막힘 {v["no_talk"]} 칸 목록 {v["list"]:02X}(그림 18 인물 '
                  f'{v["list_18"]:02X}) 메시지 {",".join(v["messages"]) or "-"} {"통과" if checks[name] else "불일치"}')
        require(all(checks.values()), '불일치: ' + ', '.join(k for k, ok in checks.items() if not ok))
        print(f'{len(checks)}장면 통과')
        return 0
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        print(f'오류: {error}', file=sys.stderr)
        if isinstance(error, subprocess.CalledProcessError) and error.stderr:
            print(error.stderr, file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
