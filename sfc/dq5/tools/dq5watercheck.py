"""움직이는 바다 원본(타일 4·5·20·21, dq5fieldgfxwrite 의 water_files)을 MesenCE 에서 확인한다.

시험 롬(원본에서 만듦)
  sea    세계 0 만 원본을 비트 반전으로(세계 1·2 는 원래 원본, --water-at 35:8000 의 고르기 훅)
  sea3   세계 0 은 비트 반전, 세계 1 은 바이트마다 XOR 0F, 세계 2 는 XOR F0(세 세계 모두 새 원본, 훅)
  same   세 세계 모두 비트 반전(훅 없이 01:A719 에 제자리)
장면
  세계 0 (341,56)·세계 1 (50,28) 에 서기, 세계 2 바다 (62,64) 에서 왼쪽 해안까지 밀기. 프레임마다 $7F·$BE·좌표를
  적고(lua/dq5framelog.lua) FROM~TO 동안 매 프레임 VRAM 을 덤프한다. sea 롬은 이벤트 전투(スライム 하나)를 이기고
  돌아온 뒤도 본다.
  - 매 프레임 VRAM 워드 2040·2140(타일 4·5·20·21)이 그 세계 원본으로 셈한 16벌(dq5gfx.water_frames) 가운데 하나이고,
    창 안에 16벌이 모두 보인다. 끝 프레임 7E:C000~C7FF 가 16벌과 같다.
  - 원본을 그대로 둔 세계는 원본 게임과 같은 프레임의 VRAM 0000~7FFF 가 바이트마다 같다. 바꾼 세계는 그 네 타일만 다르다.
  - 필드 불러오기의 마지막 멈춘 구간($7F·$BE 가 그대로인 프레임)과 세계 2 의 첫걸음이 원본 게임과 같다.

  MESENCE=… python sfc/dq5/tools/dq5watercheck.py rom/dq5.sfc --state work/state/ship.mss --out work/watercheck
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
import dq5fieldgfxcheck as fgc  # noqa: E402
import dq5fieldgfxwrite as fgw  # noqa: E402
import dq5gfxwritecheck as gwc  # noqa: E402
from dq5gfx import water_frames  # noqa: E402
from dq5map import Rom  # noqa: E402

require, command = fgc.require, fgc.command
WATER_AT = '35:8000'
# VRAM 바이트 자리: 타일 4·5(워드 2040), 20·21(워드 2140)
VRAM_SITES = (0x4080, 0x4280)
FROM, TO = 880, 1015
STAND = {'SETTLE': '300', 'TEST': 'wait:600', 'EVERY': '1', 'FROM': str(FROM), 'TO': str(TO), 'MAXF': '1100'}
SCENES = {0: dict(STAND, FIELD='341,56'),
          1: dict(STAND, FIELD='50,28', POKE='7E1949=01'),
          # 세계 2 (50,28) 은 배가 뭍에 있어 걷지 못한다. 첫걸음은 바다 (62,64) 에서 왼쪽으로 민다(dq5blockgrowcheck 와 같음)
          2: dict(STAND, FIELD='62,64', POKE='7E1949=02', TEST='wait:60,left:120,wait:600')}
# 이벤트 전투를 A 로 이겨 1,790프레임쯤 돌아온다. 이벤트 대사 동안(~2077)은 $7F 가 서 있어 벌이 멈추고, 2,160프레임쯤
# 무작위 전투가 붙으므로 그 사이에 다시 도는 벌을 BATTLE_NEED 벌 넘게 본다.
BATTLE = {'FIELD': '341,56', 'BATTLE': '00:1', 'SETTLE': '300', 'MAXF': '2200', 'EVERY': '1', 'FROM': '1975', 'TO': '2140',
          'TEST': 'wait:100,' + ','.join(['a:4,wait:30'] * 60) + ',wait:600'}
BATTLE_NEED = 8
LOAD_BEFORE = 700           # 이 프레임 앞에서 끝나는 멈춘 구간 가운데 마지막이 필드 불러오기
STEP_AFTER = 600            # 세계 2 의 첫걸음은 이 프레임 뒤 $B6 이 처음 바뀐 프레임


def make_roms(original, out):
    rom = Rom(original.read_bytes())
    src = out / 'water-src'
    doc = fgw.dump(rom, src)
    water = (src / 'water.bin').read_bytes()
    for name, xor in (('inv', 0xFF), ('x0f', 0x0F), ('xf0', 0xF0)):
        (src / f'water-{name}.bin').write_bytes(bytes(b ^ xor for b in water))
    roms = {'sea': ({'world0': 'water-inv.bin'}, ('--water-at', WATER_AT)),
            'sea3': ({'world0': 'water-inv.bin', 'world1': 'water-x0f.bin', 'world2': 'water-xf0.bin'},
                     ('--water-at', WATER_AT)),
            'same': ({k: 'water-inv.bin' for k in fgw.WORLDS}, ())}
    for name, (files, opts) in roms.items():
        doc['water_files'] = files
        (src / f'{name}.json').write_text(json.dumps(doc), encoding='utf-8')
        command('dq5fieldgfxwrite.py', original, 'patch', src / f'{name}.json', '-o', out / f'{name}-patch.json', *opts)
        command('dq5build.py', original, 'build', out / f'{name}-patch.json', '--size', '4',
                '-o', out / f'{name}.sfc', '--ips', out / f'{name}.ips')
    return {name: out / f'{name}.sfc' for name in roms}


def frame(dump, n, ext):
    return (dump / f'f{n:05d}.{ext}').read_bytes()


def water_vram(vram):
    return b''.join(vram[a:a + 64] for a in VRAM_SITES)


def stall_and_step(dump):
    """(마지막 멈춘 구간 (첫 프레임, 끝 프레임), STEP_AFTER 뒤 $B6 이 처음 바뀐 프레임)."""
    rows = [line.split() for line in (dump / 'frames.txt').read_text().splitlines() if line]
    runs, start = [], None
    for a, b in zip(rows, rows[1:]):
        same, n = a[1:3] == b[1:3], int(b[0])
        if same and start is None:
            start = n
        if not same and start is not None:
            runs.append((start, n - 1))
            start = None
    runs = [r for r in runs if r[1] < LOAD_BEFORE and r[1] - r[0] >= 5]
    require(runs, f'{dump.name}: 필드 불러오기 멈춘 구간이 없음')
    x0 = rows[STEP_AFTER][3]
    step = next((int(r[0]) for r in rows[STEP_AFTER:] if r[3] != x0), None)
    return runs[-1], step


def check_cycle(name, dump, window, frames, need=16):
    """window 의 매 프레임 VRAM 바다 타일이 frames(16벌) 가운데 하나이고 need 벌 넘게 차례로 보이는지. 본 차례를 돌려준다."""
    order = []
    for n in window:
        shown = water_vram(frame(dump, n, 'vram'))
        require(shown in frames, f'{name}: {n}프레임 VRAM 타일 4·5·20·21 이 16벌 어디와도 다름')
        k = frames.index(shown)
        if not order or order[-1] != k:
            order.append(k)
    require(len(set(order)) >= need and all((b - a) % 16 == 1 for a, b in zip(order, order[1:])),
            f'{name}: 16벌 차례 {order}')
    return order


def check_world(name, rom_path, dump, orig, world):
    """orig 는 (원본 롬, 원본 게임 덤프) 또는 None."""
    frames = water_frames(fgw.current(Rom(rom_path.read_bytes()))['water'][f'world{world}'], world)
    w = frame(dump, FROM, 'wram')
    require(w[0x1949] == world and not w[0xBE] & 0x80, f'{name}: 세계 {world} 필드에 서지 않음')
    final = (dump / 'final.wram').read_bytes()
    require([final[0xC000 + k * 0x80:0xC080 + k * 0x80] for k in range(16)] == frames,
            f'{name}: 7E:C000~C7FF 가 원본으로 셈한 16벌과 다름')
    order = check_cycle(name, dump, range(FROM, TO + 1), frames)
    out = {'case': name, 'world': world, 'sets_seen': len(set(order))}
    load, step = stall_and_step(dump)
    out['load_stall'] = f'{load[0]}~{load[1]}'
    if world == 2:
        out['first_step'] = step
    if orig is not None:
        orom, orig_dump = orig
        oload, ostep = stall_and_step(orig_dump)
        require(load == oload, f'{name}: 필드 불러오기 멈춘 구간 {load} 이 원본 게임 {oload} 과 다름')
        require(world != 2 or step == ostep, f'{name}: 첫걸음 {step} 이 원본 게임 {ostep} 과 다름')
        changed = frames != water_frames(fgw.original(orom)['water'], world)
        diff_frames = 0
        for n in range(FROM, TO + 1):
            v, ov = frame(dump, n, 'vram')[:0x8000], frame(orig_dump, n, 'vram')[:0x8000]
            if changed:
                require(water_vram(v) != water_vram(ov), f'{name}: {n}프레임 바다 타일이 원본 게임과 같음')
                v, ov = (bytearray(x) for x in (v, ov))
                for a in VRAM_SITES:
                    v[a:a + 64] = ov[a:a + 64] = bytes(64)
            if v != ov:
                diff_frames += 1
        require(not diff_frames, f'{name}: {diff_frames}프레임의 VRAM 0000~7FFF 가 원본 게임과 다름'
                + ('(바다 타일 빼고)' if changed else ''))
        out['vs_original'] = (f'{TO - FROM + 1}프레임 VRAM 0000~7FFF 가 '
                              + ('바다 타일 넷만 다르고 같음' if changed else '바이트마다 같음'))
        out['source'] = 'new' if changed else 'original'
    return out


def check_battle(name, rom_path, dump):
    frames = water_frames(fgw.current(Rom(rom_path.read_bytes()))['water']['world0'], 0)
    w = frame(dump, 1975, 'wram')
    require(w[0x1001] != 0 and not w[0xBE] & 0x80, f'{name}: 1975프레임에 전투 뒤 필드가 아님')
    order = check_cycle(name, dump, range(1975, 2141), frames, BATTLE_NEED)
    return {'case': name, 'window': '1975~2140', 'sets_seen': len(set(order))}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('rom', type=Path)
    ap.add_argument('--state', type=Path, required=True)
    ap.add_argument('--mesence', default=os.environ.get('MESENCE'))
    ap.add_argument('--out', type=Path, default=Path('work/watercheck'))
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
        roms = {'orig': original, **make_roms(original, out)}
        krlua = Path(subprocess.run(['krpatch', 'sfc', 'lua'], capture_output=True, text=True, check=True,
                                    timeout=30).stdout.strip())
        libdir = out / 'lib'
        shutil.copytree(krlua, libdir)
        shutil.copyfile(HERE / 'lua/dq5warp.lua', libdir / 'boot.lua')
        gfx, log = HERE / 'lua/dq5gfxdump.lua', HERE / 'lua/dq5framelog.lua'
        cases = [(f'{k}-w{w}', r, log, dict(SCENES[w], NEXT=str(gfx))) for k, r in roms.items() for w in range(3)]
        cases.append(('sea-battle', roms['sea'], gfx, BATTLE))
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            dirs = dict(zip([c[0] for c in cases], pool.map(
                lambda c: gwc.run(mesence, c[1], c[2], c[3], out / c[0], libdir, state), cases)))
        orom = Rom(original.read_bytes())
        results = [check_world(f'orig-w{w}', original, dirs[f'orig-w{w}'], None, w) for w in range(3)]
        for k in ('sea', 'sea3', 'same'):
            results += [check_world(f'{k}-w{w}', roms[k], dirs[f'{k}-w{w}'], (orom, dirs[f'orig-w{w}']), w)
                        for w in range(3)]
        want = {'sea': ('new', 'original', 'original'), 'sea3': ('new',) * 3, 'same': ('new',) * 3}
        for r in results[3:]:
            require(r['source'] == want[r['case'].split('-')[0]][r['world']], f'{r["case"]}: 원본이 {r["source"]}')
        results.append(check_battle('sea-battle', roms['sea'], dirs['sea-battle']))
        (out / 'results.json').write_text(json.dumps(results, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
        print(f'{len(results)}/{len(results)} 통과')
        print(json.dumps(results, ensure_ascii=False))
        return 0
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.SubprocessError) as error:
        print(f'오류: {error}', file=sys.stderr)
        if isinstance(error, subprocess.CalledProcessError) and error.stderr:
            print(error.stderr, file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
