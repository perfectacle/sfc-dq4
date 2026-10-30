"""전투 메시지 창(18·25) 자리·크기 쓰기를 MesenCE 전투에서 VRAM BG3 타일맵과 화면으로 확인한다.

dq5windowwrite.py 로 고친 롬과 원래 롬을 같은 입력으로 돌린다. 경우는 다섯이다. left·right 는 두 창의 X 만 0·4 로,
wide 는 (0,21) 31 × 7(글자 29칸), tall 은 (2,17) 28 × 11(글자 5줄), both 는 (1,15) 31 × 13(29칸 6줄)이다. 모양을 바꾸는
셋은 --message-at 의 새 코드(기본 16:FE10)로 글자 격자를 옮긴다. 장면은 셋이다. one 은 スライム 하나와 싸우며 공격
메시지 05E 를 긴 메시지 006·118·191 로, 피해 069 를 006 으로 바꾸고, 20:C62B 의 BRK A4 를 BRK 9E 로 바꿔(파일 오프셋
10462C, 모든 롬) 셋째 줄 다음에 줄을 올리게 한다. 주인공의 공격 효과(BG3 효과 층)가 창이 떠 있는 동안 돈다. four 는
무리 넷(00·01·02·03)이 나타나 창 25 가 한 줄 올라가고 두 줄 늘어나는 갈래(04:A070)를 탄다. 이 둘은 메시지 속도
7E:2035 = 7 로 두어 ▼ 를 띄우고 기다리게 한다(24:A519·24:A523). field 는 바꾸지 않은 スライム 전투를 끝내고 필드로
돌아온 뒤까지 돈다.

- X 만 옮긴 경우: 원래 롬에서 메시지 창(맨 위 줄 21, 무리 넷이면 20 의 (2,줄)·(29,줄) 이 모서리 8B·8C)이 떠 있는
  프레임마다, 고친 롬의 옮긴 자리 사각형이 원래 사각형과 워드(타일·속성)째 같고 원래 모서리 자리에는 모서리가 없는지
  본다. 화면에서도 창 사각형 픽셀이 원래 롬 화면의 원래 자리와 같은지 본다.
- 모양을 바꾼 경우: 줄 수·줄 올리기 때가 달라 원래 화면과 견줄 수 없으므로 셋을 본다. (1) 24:A4A4 에 들어온 글자 열이
  원래 롬과 메시지째 같다(기다림이 달라 난수가 갈리기 전까지, 세 메시지 이상). 모든 글자 칸·줄이 새 격자 안이다. (2) WRAM 창 버퍼 7E:5000 에 창이
  있는 프레임마다 VRAM 창 사각형이 앞 여덟 프레임 가운데 한 프레임의 버퍼와 같다(효과 층이 창을 덮으면 여러
  프레임이 이어 다름). 원래 롬도 같은 잣대로 본다. (3) 접근 카운터로 옛 격자 7E:1DD5~1E70 에 쓰기가 없고 새 격자를 쓴다.
- field: 전투가 끝나고 필드 메시지(파파스)의 40번째 글자(24:9E94)에서 맵·필드 좌표와 7E:1E71~1EFF(필드 변수)가
  원래 롬과 같다.
원래 롬과 선실 상태는 읽기만 하며 롬·기록은 --out 의 새 폴더에 쓴다.
  MESENCE=… python sfc/dq5/tools/dq5msgwindowcheck.py rom/dq5.sfc --state work/state/ship.mss
"""
import argparse
import concurrent.futures
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from dq5windowwrite import GRID, GRID_SIZE  # noqa: E402

LEFT, TOP = 2, 21
WIDTH, HEIGHT = 28, 7
CORNERS = (0x8B, 0x8C)
CASES = {'left': {'x': 0}, 'right': {'x': 4}, 'wide': {'x': 0, 'w': 31}, 'tall': {'h': 11},
         'both': {'x': 1, 'w': 31, 'h': 13}}
TAPS = ','.join(['wait:400'] + ['a:8,wait:24'] * 110)
SCENES = {
    'one': {'BATTLE': '00:1', 'SWAP': '05E:006,118,191;069:006', 'ROMPATCH': '10462C=9E', 'SET': '2035=07', 'MAXF': '3400'},
    'four': {'BATTLE': '00:1,01:1,02:1,03:1', 'SET': '2035=07', 'MAXF': '3400'},
    'field': {'BATTLE': '00:1', 'MAXF': '3000', 'FIELDSNAP': '40'},
}
# 견주는 구간에서 지나야 하는 곳: 메시지·FD ▼·줄 올리기·셋째 줄 끝 ▼·효과 층 전송, 무리 넷이면 넷째 줄 끝 ▼.
# 모양을 바꾼 롬은 줄이 늘어 줄 올리기·▼ 때가 달라, 지나야 하는 곳만 따로 둔다.
COVER = {'one': {'248C39', '24880A', '24A569', '24A519', 'EFF'}, 'four': {'248C39', '24A519', '24A523'}}
SHAPED_COVER = {'one': {'248C39', '24A4A4', '24A569', 'EFF'}, 'four': {'248C39', '24A519', '24A523'}}
OLD_GRID, FIELD_VARS = '1DD5-1E70', (0x1E71, 0x1EFF)
NEW_GRID = f'{GRID & 0xFFFF:04X}-{(GRID & 0xFFFF) + GRID_SIZE - 1:04X}'
ACC = f'{OLD_GRID},{FIELD_VARS[0]:04X}-{FIELD_VARS[1]:04X},{NEW_GRID}'
FROM, STEP, SHOTEVERY = 560, 1, 16
LAG = 8


def require(condition, message):
    if not condition:
        raise ValueError(message)


def same_until(calls, moved):
    """두 롬의 실행 기록이 처음 갈리는 프레임. 같은 입력이라도 몇 턴 뒤 갈릴 수 있어 그 앞까지만 견준다.
    한쪽 기록이 먼저 끝나면 그 뒤는 견줄 수 없어 짧은 기록의 마지막 프레임까지로 한다."""
    calls, moved = [line for line in calls if line], [line for line in moved if line]
    for a, b in zip(calls, moved):
        if a != b:
            return min(int(a.split()[0]), int(b.split()[0]))
    if len(calls) != len(moved):
        short = min(calls, moved, key=len)
        return int(short[-1].split()[0]) if short else 0
    return 1 << 30


def text_runs(calls):
    """실행 기록 → [(메시지 번호, [(글자, 줄, 칸), …])]. 첫 메시지 앞의 글자는 버린다."""
    out = []
    for line in calls:
        parts = line.split()
        if len(parts) == 3 and parts[1] == '248C39':
            out.append((parts[2], []))
        elif len(parts) == 5 and parts[1] == '24A4A4' and out:
            out[-1][1].append((parts[2], int(parts[3]), int(parts[4])))
    return out


def word(dump, x, y):
    at = (y * 32 + x) * 2
    return dump[at] | dump[at + 1] << 8


def window(dump, x, y, h, w=WIDTH):
    return [[word(dump, x + c, y + r) for c in range(w)] for r in range(h)]


def chunks(data):
    return [data[i:i + 0x800] for i in range(0, len(data), 0x800)]


def compare_moved(scene, name, x, seen, out):
    """X 만 옮긴 롬: 원래 롬의 창 사각형과 워드째, 화면은 픽셀째."""
    dumps, _, calls = seen[('original', scene)][:3]
    moved, _, moved_calls = seen[(name, scene)][:3]
    limit = same_until(calls, moved_calls)
    frames = mismatched = screens = 0
    for k, (a, b) in enumerate(zip(dumps, moved)):
        frame = FROM + k * STEP
        if frame >= limit:
            break
        top = next((r for r in (21, 20) if word(a, LEFT, r) & 0xFF in CORNERS
                    and word(a, LEFT + WIDTH - 1, r) & 0xFF in CORNERS), None)
        if top is None:
            continue
        h = HEIGHT + 2 * (top == 20)
        frames += 1
        if window(b, x, top, h) != window(a, LEFT, top, h) or any(
                word(b, c, top) & 0xFF in CORNERS for c in (LEFT, LEFT + WIDTH - 1)):
            mismatched += 1
            continue
        shot = out / scene / 'original' / f'f{frame:05d}.png'
        # 화면은 덤프보다 한두 프레임 늦게 찍힐 수 있어, 두 롬 모두 창이 세 덤프 내리 같은 때만 견준다.
        if not shot.is_file() or k < 2 or any(window(dumps[j], LEFT, top, h) != window(a, LEFT, top, h)
                                              or window(moved[j], x, top, h) != window(b, x, top, h)
                                              for j in (k - 1, k - 2)):
            continue
        before = Image.open(shot).convert('RGB')
        after = Image.open(out / scene / name / f'f{frame:05d}.png').convert('RGB')
        # 화면의 BG3 는 타일맵보다 몇 점 위로 밀려 있고 아래 테두리 아래로는 뒤 배경이 비치므로,
        # 아래 테두리 위 줄의 4점 위에서 끊는다.
        box = (LEFT * 8, top * 8, (LEFT + WIDTH) * 8, min(224, (top + h - 1) * 8 - 4))
        moved_box = (x * 8, box[1], (x + WIDTH) * 8, box[3])
        # 턴이 바뀌는 몇 프레임은 화면에 BG3 가 나오지 않는다. 그때는 옮기기 전 자리의 두 화면이 같다.
        if before.crop(box).tobytes() == after.crop(box).tobytes():
            continue
        require(before.crop(box).tobytes() == after.crop(moved_box).tobytes(),
                f'{scene}/{name} f{frame}: 화면 창 사각형이 원래 롬과 다름')
        screens += 1
    kinds = {line.split()[1] for line in calls if line and int(line.split()[0]) < limit}
    require(frames and not mismatched, f'{scene}/{name}: 창 {frames}프레임 중 {mismatched}프레임이 다름')
    require(kinds >= COVER[scene], f'{scene}/{name}: {limit}프레임 전에 {sorted(COVER[scene] - kinds)} 를 지나지 않음')
    return {'until': limit, 'frames': frames, 'mismatched': mismatched, 'screens': screens, 'calls': sorted(kinds)}


def consistency(dumps, bufs, x, y, w, h):
    """버퍼에 창(맨 위 줄 y, 무리 넷이면 y - 1)이 있는 프레임마다 VRAM 창 사각형이 앞 LAG 프레임 가운데 한 프레임의
    버퍼와 같은지 본다. NMI 는 앞 프레임까지의 버퍼를 올리는데, 글자가 빨리 찍히는 동안은 부분 전송이 서너 프레임에
    한 번이라(메시지 118, 원래 롬) 그만큼 늦는다. → (창이 있던 프레임 수, 어느 버퍼와도 다른 프레임 수, 그런 프레임이
    가장 길게 이어진 수, 그때 첫 프레임)."""
    frames = differ = run = longest = 0
    first = None
    for k in range(LAG, min(len(dumps), len(bufs))):
        top = next((r for r in (y, y - 1) if word(bufs[k - 1], x, r) & 0xFF in CORNERS
                    and word(bufs[k - 1], x + w - 1, r) & 0xFF in CORNERS), None)
        if top is None:
            run = 0
            continue
        rows = min(h + 2 * (top < y), 28 - top)
        frames += 1
        seen = window(dumps[k], x, top, rows, w)
        if all(seen != window(bufs[k - j], x, top, rows, w) for j in range(1, LAG + 1)):
            differ += 1
            run += 1
            if run > longest:
                longest, first = run, FROM + (k - run + 1) * STEP
        else:
            run = 0
    return frames, differ, longest, first


def compare_shaped(scene, name, shape, seen):
    """모양을 바꾼 롬: 글자 열, VRAM 과 버퍼, 접근 카운터."""
    dumps, bufs, calls, acc = seen[(name, scene)][:4]
    original_calls, original_acc = seen[('original', scene)][2:4]
    x, y, w, h = shape['x'], shape['y'], shape['w'], shape['h']
    runs, original_runs = text_runs(calls), text_runs(original_calls)
    common = 0
    for (a, _), (b, _) in zip(runs, original_runs):
        if a != b:
            break
        common += 1
    # 줄이 늘면 기다림이 달라 난수가 갈리고, 피해 수·대상 이름부터 글자가 달라진다. 그 앞까지 같은 메시지 수를 센다.
    same = chars = 0
    for (_, text), (_, original_text) in zip(runs[:common - 1], original_runs[:common - 1]):
        if [c for c, _, _ in text] != [c for c, _, _ in original_text]:
            break
        same += 1
        chars += len(text)
    for _, text in runs:
        for c, line, col in text:
            require(line < (h - 1) // 2 and col < w - 2, f'{scene}/{name}: 글자 {c} 가 격자 밖({line}줄 {col}칸)')
    require(same >= 3, f'{scene}/{name}: 원래 롬과 글자까지 같은 메시지가 {same}개뿐')
    frames, differ, longest, first = consistency(dumps, bufs, x, y, w, h)
    require(frames and longest <= 1, f'{scene}/{name}: VRAM 창이 버퍼와 {longest}덤프 이어 다름(f{first}부터)')
    kinds = {line.split()[1] for line in calls if line}
    require(kinds >= SHAPED_COVER[scene], f'{scene}/{name}: {sorted(SHAPED_COVER[scene] - kinds)} 를 지나지 않음')
    effects = sum(line.endswith(' EFF') for line in calls)
    require(acc[OLD_GRID][1] == 0 and acc[NEW_GRID][1] > 0 and original_acc[OLD_GRID][1] > 0,
            f'{scene}/{name}: 옛 격자 쓰기 {acc[OLD_GRID][1]}, 새 격자 쓰기 {acc[NEW_GRID][1]}, '
            f'원래 롬 옛 격자 쓰기 {original_acc[OLD_GRID][1]}')
    return {'messages': common, 'same_text': same, 'chars': chars, 'frames': frames, 'differ': differ, 'longest': longest,
            'effects': effects, 'old_grid_writes': acc[OLD_GRID][1], 'grid_writes': acc[NEW_GRID][1],
            'calls': sorted(kinds)}


def compare_field(name, seen):
    """field 장면: 필드로 돌아온 뒤의 맵·좌표와 필드 변수 7E:1E71~1EFF 가 원래 롬과 같은지."""
    original, moved = seen[('original', 'field')][4], seen[(name, 'field')][4]
    require(original and moved, f'field/{name}: 필드로 돌아오지 않음')
    require(original.split('\n')[1:] == moved.split('\n')[1:] and original.split(' ', 1)[1] == moved.split(' ', 1)[1],
            f'field/{name}: 필드로 돌아온 뒤 자리·7E:{FIELD_VARS[0]:04X}~{FIELD_VARS[1]:04X} 가 원래 롬과 다름')
    return {'field': moved.split('\n')[0], 'acc': seen[(name, 'field')][3]}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('rom', type=Path)
    ap.add_argument('--state', type=Path, required=True)
    ap.add_argument('--mesence', default=os.environ.get('MESENCE'))
    ap.add_argument('--out', type=Path, default='work/msgwindowcheck')
    ap.add_argument('--message-at', default='16:FE10', help='모양을 바꾸는 경우의 새 코드 자리')
    ap.add_argument('--cases', default=','.join(CASES))
    ap.add_argument('--scenes', default=','.join(SCENES))
    ap.add_argument('--jobs', type=int, default=4)
    args = ap.parse_args()
    if not args.mesence:
        ap.error('--mesence 또는 MESENCE가 필요함')
    try:
        original, state, mesence = args.rom.resolve(), args.state.resolve(), Path(args.mesence).resolve()
        for path in (original, state, mesence):
            require(path.is_file(), f'파일 없음: {path}')
        cases = {name: CASES[name] for name in args.cases.split(',')}
        scenes = args.scenes.split(',')
        args.out.mkdir(parents=True, exist_ok=True)
        out = Path(tempfile.mkdtemp(prefix='run-', dir=args.out.resolve()))
        print(f'실행 출력: {out}', flush=True)
        roms, shapes = {'original': original}, {}
        for name, row in cases.items():
            doc = {'format': 'dq5windows/1', 'windows': [{'index': '25', **row}]}
            (out / f'{name}.json').write_text(json.dumps(doc) + '\n')
            shape = {'x': row.get('x', LEFT), 'w': row.get('w', WIDTH), 'h': row.get('h', HEIGHT)}
            shape['y'] = 28 - shape['h']
            write = ['patch', out / f'{name}.json', '-o', out / f'{name}.patch.json']
            if (shape['w'], shape['h']) != (WIDTH, HEIGHT):
                shapes[name] = shape
                write += ['--message-at', args.message_at]
            for tool, extra in (('dq5windowwrite.py', write),
                                ('dq5build.py', ['build', out / f'{name}.patch.json', '-o', out / f'{name}.sfc',
                                                 '--ips', out / f'{name}.ips'])):
                subprocess.run([sys.executable, str(HERE / tool), str(original), *map(str, extra)], check=True,
                               capture_output=True, text=True, timeout=120)
            check = subprocess.run([sys.executable, str(HERE / 'dq5windowwrite.py'), str(out / f'{name}.sfc'), 'check'],
                                   capture_output=True, text=True, timeout=120)
            require(check.returncode == 0, f'{name}: 만든 롬의 check 가 0 이 아님: {check.stdout}{check.stderr}')
            roms[name] = out / f'{name}.sfc'
        libdir = subprocess.run(['krpatch', 'sfc', 'lua'], check=True, capture_output=True, text=True,
                                timeout=30).stdout.strip()

        def run(job):
            rom, scene = job
            dest = out / scene / rom
            dest.mkdir(parents=True)
            env = os.environ.copy()
            for key in ('PARTY', 'SET', 'POKE', 'ROMPATCH', 'TO', 'LATESET', 'SWAP'):
                env.pop(key, None)
            env.update(LIBDIR=libdir, STATE=str(state), SHOT_DIR=str(dest), DRIVER=str(HERE / 'lua/dq5warp.lua'),
                       FIELD='341,56', TEST=TAPS, FROM=str(FROM), STEP=str(STEP), SHOTEVERY=str(SHOTEVERY), ACC=ACC,
                       **SCENES[scene])
            with (dest / 'mesen.log').open('w') as log:
                subprocess.run([str(mesence), '--testrunner', str(roms[rom]), str(HERE / 'lua/dq5msgwindowcheck.lua'),
                                '--Snes.DisableFrameSkipping=true', '--timeout=900'], env=env, stdout=log,
                               stderr=subprocess.STDOUT, check=True, timeout=1000)
            acc = {}
            for line in (dest / 'acc.txt').read_text().split('\n'):
                if line:
                    key, reads, writes = line.split()
                    acc[key] = (int(reads), int(writes))
            field = (dest / 'field.txt').read_text() if (dest / 'field.txt').is_file() else ''
            return (chunks((dest / 'bg3.bin').read_bytes()), chunks((dest / 'buf.bin').read_bytes()),
                    (dest / 'exec.txt').read_text().split('\n'), acc, field)

        jobs = [(rom, scene) for scene in scenes for rom in roms]
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
            seen = dict(zip(jobs, pool.map(run, jobs)))
        results = []
        for scene in scenes:
            if scene != 'field':
                frames, differ, longest, first = consistency(*seen[('original', scene)][:2], LEFT, TOP, WIDTH, HEIGHT)
                results.append({'scene': scene, 'case': 'original', 'frames': frames, 'differ': differ,
                                'longest': longest})
                require(frames and longest <= 1, f'{scene}/original: VRAM 창이 버퍼와 {longest}덤프 이어 다름(f{first}부터)')
            for name, row in cases.items():
                if scene == 'field':
                    result = compare_field(name, seen)
                elif name in shapes:
                    result = compare_shaped(scene, name, shapes[name], seen)
                else:
                    result = compare_moved(scene, name, row['x'], seen, out)
                results.append({'scene': scene, 'case': name, **result})
        (out / 'results.json').write_text(json.dumps(results, ensure_ascii=False, indent=2) + '\n')
        print(json.dumps(results, ensure_ascii=False))
        return 0
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        print(f'오류: {error}', file=sys.stderr)
        if isinstance(error, subprocess.CalledProcessError) and error.output:
            print(error.output, file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
