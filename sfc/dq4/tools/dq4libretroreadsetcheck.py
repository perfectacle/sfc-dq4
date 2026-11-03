"""libretro bsnes 의 읽은 롬 바이트 비트맵(dq4cores 가 얹는 romtrace 패치)이 결과에 닿는 롬 읽기를 빠뜨리지 않는지 본다.
형식은 sfc/dq4/docs/dq4-readset-format.md 「libretro bsnes」.

장면 두 개(전원부터 정한 입력으로 1500프레임, 저장 기록으로 이무르에서 이어 하기 뒤 걷기)마다:

  결정성  같은 장면을 두 번 돌리면 화면·WRAM·읽은 집합이 같다
  밖      읽은 집합과 롬 머리($7FB0~$7FFF, 체크섬 빼고) 밖 바이트를 모두 뒤집은 롬(체크섬도 뒤집음)으로 돌려도
          화면·WRAM·읽은 집합이 같다
  안      읽은 집합 안 바이트 하나를 바꾼 롬은 읽은 바이트 해시가 달라진다(캐시가 빗나감)

장면은 실행마다 따로 프로세스로 돌린다(한 프로세스의 Core 는 dylib 전역 상태를 나눠 쓴다). 저장 기록은 원래 롬으로 한 번
만든 것을 모든 실행에 같이 넣는다.

  uv run --locked python sfc/dq4/tools/dq4libretroreadsetcheck.py --rom work/ch1/dq4-ch1-full.sfc --out work/lrreadset
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import dq4readset as rs  # noqa: E402

BOOT_FRAMES = 1500
WALK = ['right'] * 40 + [None] * 20 + ['down'] * 40 + [None] * 20 + ['a'] * 4 + [None] * 60 + ['b'] * 4 + [None] * 60


def boot_input(n):
    """전원 장면의 n 프레임째 단추: 타이틀·이름 입력을 START·A 로 넘기고 아래를 누른다."""
    if 900 < n < 1000:
        return ('down',)
    if n > 200 and n % 60 < 4:
        return ('a',) if (n // 60) % 3 else ('start',)
    return ()


def run_scene(scene, core_path, rom, out, sram, goal):
    """한 프로세스 안에서 장면 하나. 결과(화면·WRAM 해시, 읽은 구간)를 out/result.json 에."""
    import dq4libretro
    import dq4savefixture as fx
    out.mkdir(parents=True, exist_ok=True)
    if scene == 'boot':
        core = dq4libretro.Core(str(core_path), str(rom), str(out / 'sys'), trace=True)
        for n in range(BOOT_FRAMES):
            core.run(boot_input(n))
    else:
        # SRAM 을 맞춰 보는 직렬화도 코어를 돌리므로 비트맵은 열 때부터 켠다
        core = fx.open_core(core_path, rom, out / 'sys', sram, trace=True)
        if fx.boot(core, goal) is None:
            raise SystemExit('이어 하기로 자리에 서지 못함')
        for b in WALK:
            core.run((b,) if b else ())
    result = {'frame': hashlib.sha256(core.frame.tobytes()).hexdigest(),
              'wram': hashlib.sha256(bytes(core.wram())).hexdigest(), 'ranges': core.trace_ranges()}
    (out / 'result.json').write_text(json.dumps(result), encoding='utf-8')


def go(scene, core_path, rom, out, sram, goal):
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    srm = out / 'start.srm'
    srm.write_bytes(sram)
    r = subprocess.run([sys.executable, __file__, '--scene', scene, '--core', str(core_path), '--rom', str(rom),
                        '--out', str(out), '--sram', str(srm), '--goal', ','.join(map(str, goal))],
                       capture_output=True, text=True, timeout=900)
    if r.returncode:
        raise SystemExit(f'{scene} {out.name}: 종료 코드 {r.returncode}\n{r.stdout[-800:]}{r.stderr[-800:]}')
    return json.loads((out / 'result.json').read_text(encoding='utf-8'))


def check(scene, core_path, rom_path, out, sram, goal):
    data = Path(rom_path).read_bytes()
    problems = []
    a = go(scene, core_path, rom_path, out / f'{scene}-a', sram, goal)
    b = go(scene, core_path, rom_path, out / f'{scene}-b', sram, goal)
    same = ('frame', 'wram', 'ranges')
    if any(a[k] != b[k] for k in same):
        problems.append('결정성: 같은 장면 두 번이 다름 ' + ','.join(k for k in same if a[k] != b[k]))
    ranges = [tuple(r) for r in a['ranges']]
    if not ranges:
        return {'name': scene, 'status': 'failed', 'problems': ['읽은 집합이 비었음']}
    keep = bytearray(len(data))
    for s, n in ranges:
        keep[s:s + n] = b'\1' * n
    for h in rs.HEADER:
        keep[h] = b'\1' * len(keep[h])
    flipped = bytes(x ^ 0xFF if not k else x for x, k in zip(data, keep))
    outside_rom = out / f'{scene}-outside.sfc'
    outside_rom.write_bytes(flipped)
    c = go(scene, core_path, outside_rom, out / f'{scene}-outside', sram, goal)
    if any(a[k] != c[k] for k in same):
        problems.append('밖: 읽은 집합 밖을 뒤집은 롬에서 다름 ' + ','.join(k for k in same if a[k] != c[k]))
    outside_rom.unlink()
    inside = bytearray(data)
    s, n = max(ranges, key=lambda r: r[1])
    inside[s + n // 2] ^= 0x01
    if rs.digest(bytes(inside), ranges) == rs.digest(data, ranges):
        problems.append('안: 읽은 집합 안 바이트를 바꿨는데 읽은 바이트 해시가 같음')
    return {'name': scene, 'status': 'failed' if problems else 'passed', 'problems': problems,
            'readset': sum(n for _, n in ranges), 'ranges': len(ranges),
            'flipped': len(data) - sum(keep), 'checksum_flipped': all(not keep[i] for i in rs.CHECKSUM)}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--rom', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--scene', help=argparse.SUPPRESS)
    ap.add_argument('--core', type=Path, help=argparse.SUPPRESS)
    ap.add_argument('--sram', type=Path, help=argparse.SUPPRESS)
    ap.add_argument('--goal', help=argparse.SUPPRESS)
    a = ap.parse_args()
    if a.scene:
        run_scene(a.scene, a.core, a.rom.resolve(), a.out.resolve(), a.sram.read_bytes(),
                  tuple(int(v) for v in a.goal.split(',')))
        return 0
    import dq4cores
    import dq4savefixture as fx
    core_path = dq4cores.core_path('bsnes')
    if not core_path.exists():
        raise SystemExit(f'{core_path} 가 없음: sfc/dq4/tools/dq4cores.py 로 빌드')
    out = a.out.resolve()
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    rom = a.rom.resolve()
    # 저장 기록과 이어 할 자리는 원래 롬으로 한 번 만든다(뒤집은 롬으로 다시 만들면 출발이 달라진다)
    slot = fx.SaveSlot.new_game(rom)
    slot.place = 'imuru'
    sram, goal = slot.to_sram(), slot.goal
    results = []
    for scene in ('boot', 'continue'):
        r = check(scene, core_path, rom, out, sram, goal)
        results.append(r)
        print(json.dumps(r, ensure_ascii=False), flush=True)
    ok = all(r['status'] == 'passed' for r in results)
    print(json.dumps({'status': 'passed' if ok else 'failed'}, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
