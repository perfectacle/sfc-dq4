"""세계마다 움직이는 타일 벌(타일 454~459, dq5fieldgfxwrite 의 anim_files)과 움직이는 바다를 MesenCE 에서 확인한다.

시험 롬(원본에서 만듦)
  aw  움직이는 타일 벌: 세계 0 원래, 세계 1 은 비트 반전, 세계 2 는 XOR F0(--anim-worlds-at 36:8000).
      움직이는 바다 원본: 세계 0 비트 반전, 세계 1 XOR 0F, 세계 2 XOR F0(--water-at 35:8000)
장면
  stand-wN   aw·원본 롬으로 세계 N 에 서서 FROM~TO 매 프레임 VRAM 을 덤프한다(dq5watercheck 와 같은 자리).
             - aw 의 VRAM 워드 3C60(타일 454~459, 192바이트)이 매 프레임 그 세계의 8벌 가운데 하나이고, 8벌이 모두 차례로 보인다.
               바다 타일 4·5·20·21 은 그 세계 원본의 16벌 가운데 하나다.
             - 원본 게임과 같은 프레임의 VRAM 0000~7FFF 가 그 두 자리만 다르다(세계 0 은 움직이는 타일도 같다).
  dq5gfxlimitcheck 의 세계를 오가는 장면(ルーラ 0→1·0→2·1→0·1→2, 1C/00·30/00 에서 걸어 나가기, キメラのつばさ,
  天空城 이륙, 52/50 석상, $1949 = FF 뒤의 ルーラ·걸어 나가기)을 aw 롬으로 돌려, 덤프 프레임마다 $1949 가 기대한 세계이고
  움직이는 타일과 바다 타일이 그 세계의 벌 가운데 하나인지 본다.

  MESENCE=… python sfc/dq5/tools/dq5animworldcheck.py rom/dq5.sfc --state work/state/ship.mss --out work/animworldcheck
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
sys.path.insert(0, str(HERE))
import dq5fieldgfxcheck as fgc  # noqa: E402
import dq5fieldgfxwrite as fgw  # noqa: E402
import dq5gfxwritecheck as gwc  # noqa: E402
from dq5gfx import water_frames  # noqa: E402
from dq5gfxlimitcheck import WORLD_SCENES  # noqa: E402
from dq5map import Rom  # noqa: E402
from dq5watercheck import FROM, SCENES, TO, VRAM_SITES, frame, water_vram  # noqa: E402

require, command = fgc.require, fgc.command
ANIM_VRAM = 0x3C60 * 2


def anim_vram(vram):
    return vram[ANIM_VRAM:ANIM_VRAM + fgw.ANIM_SET]


def make_rom(original, out):
    rom = Rom(original.read_bytes())
    src = out / 'src'
    doc = fgw.dump(rom, src)
    anim, water = (src / 'anim.bin').read_bytes(), (src / 'water.bin').read_bytes()
    for name, xor in (('inv', 0xFF), ('x0f', 0x0F), ('xf0', 0xF0)):
        (src / f'anim-{name}.bin').write_bytes(bytes(b ^ xor for b in anim))
        (src / f'water-{name}.bin').write_bytes(bytes(b ^ xor for b in water))
    doc['anim_files'] = {'world1': 'anim-inv.bin', 'world2': 'anim-xf0.bin'}
    doc['water_files'] = {'world0': 'water-inv.bin', 'world1': 'water-x0f.bin', 'world2': 'water-xf0.bin'}
    (src / 'aw.json').write_text(json.dumps(doc), encoding='utf-8')
    command('dq5fieldgfxwrite.py', original, 'patch', src / 'aw.json', '-o', out / 'aw-patch.json',
            '--anim-worlds-at', '36:8000', '--water-at', '35:8000')
    command('dq5build.py', original, 'build', out / 'aw-patch.json', '--size', '4', '-o', out / 'aw.sfc',
            '--ips', out / 'aw.ips')
    return out / 'aw.sfc'


def world_sets(rom_path):
    now = fgw.current(Rom(rom_path.read_bytes()))
    return ({w: now['anim_worlds'][f'world{w}'] for w in range(3)},
            {w: water_frames(now['water'][f'world{w}'], w) for w in range(3)})


def check_stand(world, aw, dirs, sets, waters, orig_sets):
    name, dump, odump = f'stand-w{world}', dirs[f'aw-w{world}'], dirs[f'orig-w{world}']
    w = frame(dump, FROM, 'wram')
    require(w[0x1949] == world and not w[0xBE] & 0x80, f'{name}: 세계 {world} 필드에 서지 않음')
    order = []
    for n in range(FROM, TO + 1):
        v, ov = frame(dump, n, 'vram'), frame(odump, n, 'vram')
        shown = anim_vram(v)
        require(shown in sets[world], f'{name}: {n}프레임 타일 454~459 가 세계 {world} 의 벌 어디와도 다름')
        k = sets[world].index(shown)
        if not order or order[-1] != k:
            order.append(k)
        require(water_vram(v) in waters[world], f'{name}: {n}프레임 바다 타일이 세계 {world} 의 16벌 어디와도 다름')
        if world:
            require(anim_vram(ov) in orig_sets and shown not in orig_sets, f'{name}: {n}프레임 원본 게임과 벌이 겹침')
        a, b = bytearray(v[:0x8000]), bytearray(ov[:0x8000])
        for at, size in ((ANIM_VRAM, fgw.ANIM_SET), *((x, 64) for x in VRAM_SITES)):
            a[at:at + size] = b[at:at + size] = bytes(size)
        require(a == b, f'{name}: {n}프레임 VRAM 0000~7FFF 가 움직이는 타일·바다 타일 밖에서 원본 게임과 다름')
        if not world:
            require(shown == anim_vram(ov), f'{name}: {n}프레임 세계 0 의 움직이는 타일이 원본 게임과 다름')
    n = len(sets[world])
    require(len(set(order)) == n and all((b - a) % n == 1 for a, b in zip(order, order[1:])),
            f'{name}: 벌 차례 {order}')
    return {'case': name, 'anim_sets_seen': len(set(order)), 'frames': TO - FROM + 1}


def check_scene(name, dump, frames, sets, waters):
    seen = []
    for n, world in frames:
        w, v = frame(dump, n, 'wram'), frame(dump, n, 'vram')
        require(w[0x1949] == world and not w[0xBE] & 0x80, f'{name}: {n}프레임이 세계 {world} 필드가 아님'
                f'($1949={w[0x1949]:02X}, $BE={w[0xBE]:02X})')
        shown = anim_vram(v)
        require(shown in sets[world], f'{name}: {n}프레임 타일 454~459 가 세계 {world} 의 벌이 아님'
                + ''.join(f'(세계 {k} 의 벌)' for k in range(3) if shown in sets[k]))
        require(water_vram(v) in waters[world], f'{name}: {n}프레임 바다 타일이 세계 {world} 의 벌이 아님'
                + ''.join(f'(세계 {k} 의 벌)' for k in range(3) if water_vram(v) in waters[k]))
        seen.append(f'{n}:{world}')
    return {'case': name, 'frames': seen}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('rom', type=Path)
    ap.add_argument('--state', type=Path, required=True)
    ap.add_argument('--mesence', default=os.environ.get('MESENCE'))
    ap.add_argument('--out', type=Path, default=Path('work/animworldcheck'))
    args = ap.parse_args()
    if not args.mesence:
        ap.error('--mesence 또는 MESENCE 가 필요함')
    try:
        original, state, mesence = args.rom.resolve(), args.state.resolve(), Path(args.mesence).resolve()
        for path in (original, state, mesence):
            require(path.is_file(), f'파일 없음: {path}')
        args.out.mkdir(parents=True, exist_ok=True)
        out = Path(tempfile.mkdtemp(prefix='run-', dir=args.out.resolve()))
        print(f'실행 출력: {out}', flush=True)
        aw = make_rom(original, out)
        sets, waters = world_sets(aw)
        orig_sets = world_sets(original)[0][0]
        require(sets[0] == orig_sets and all(sets[w] != orig_sets for w in (1, 2)), 'aw 롬의 세계마다 벌이 입력과 다름')
        krlua = Path(subprocess.run(['krpatch', 'sfc', 'lua'], capture_output=True, text=True, check=True,
                                    timeout=30).stdout.strip())
        libdir = out / 'lib'
        shutil.copytree(krlua, libdir)
        shutil.copyfile(HERE / 'lua/dq5warp.lua', libdir / 'boot.lua')
        gfx = HERE / 'lua/dq5gfxdump.lua'
        stand = {w: {k: v for k, v in SCENES[w].items() if k != 'TEST'} | {'TEST': 'wait:600'} for w in range(3)}
        cases = [(f'{r}-w{w}', path, gfx, stand[w]) for r, path in (('aw', aw), ('orig', original)) for w in range(3)]
        cases += [(k, aw, gfx, dict(env, SETTLE='60', DUMPF=','.join(str(n) for n, _ in frames)))
                  for k, (env, frames, _) in WORLD_SCENES.items()]
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            dirs = dict(zip([c[0] for c in cases], pool.map(
                lambda c: gwc.run(mesence, c[1], c[2], c[3], out / c[0], libdir, state), cases)))
        results = [check_stand(w, aw, dirs, sets, waters, orig_sets) for w in range(3)]
        failed = []
        for k, (_, frames, _) in WORLD_SCENES.items():
            try:
                results.append(check_scene(k, dirs[k], frames, sets, waters))
            except ValueError as error:
                failed.append(str(error))
        (out / 'results.json').write_text(json.dumps({'results': results, 'failed': failed}, ensure_ascii=False,
                                                     indent=1) + '\n', encoding='utf-8')
        for r in results:
            print(json.dumps(r, ensure_ascii=False))
        for f in failed:
            print(f'불일치: {f}')
        require(not failed, f'{len(failed)}개 장면 불일치')
        print(f'{len(results)}/{len(results)} 통과')
        return 0
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.SubprocessError) as error:
        print(f'오류: {error}', file=sys.stderr)
        if isinstance(error, subprocess.CalledProcessError) and error.stderr:
            print(error.stderr, file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
