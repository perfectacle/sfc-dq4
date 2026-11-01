"""1장 통합 롬을 처음부터 만든다: 타이틀 레이어 → 타이틀 롬 → 서곡 → 메뉴 → 1장 첫머리 → 곡 묶음.

단계마다 dq4buildcache.run 으로 불러, 도구·입력이 바뀌지 않은 단계는 캐시에서 꺼낸다. 서로 기다릴 필요가 없는
타이틀 레이어와 1장 메시지는 함께 돌린다. ASAR·DQ4_GALMURI 가 필요하다(dq4menupatch.py).

곡 묶음은 1장 롬 위에 dq4soundset.py @dq4sound-game.args 로 얹는다. NDS 곡을 자원 저장소(--assets, 기본 DQ4_ASSETS)
에서 읽으므로 그것이 없으면 곡 없이 끝난다. 이 단계는 dq4buildcache 를 거치지 않는다: 키가 자원 저장소 전체를
해시하게 되고, dq4soundset 이 자원 저장소 안에 자기 캐시를 따로 둔다.

곡 롬 위에 서장·1장 인물 필드 그림(dq4people.py, 같은 자원 저장소의 NDS 인물 시트)을 얹어 dq4-ch1-full.sfc 로 끝낸다.
인물 시트가 없으면 곡 롬에서 끝난다.

끝나면 단계마다 바뀐 바이트 범위를 --out 의 ledger.json 에 적는다(dq4romledger.py, 검사는 dq4romledgercheck.py).

1장 끝은 기본으로 끝맺음 서술과 「다음에 계속」 상자 뒤 타이틀로 돌아간다(1장까지의 배포판). --chapter2 를 주면
2장으로 넘어간다.

  python sfc/dq4/tools/dq4build.py --out work/ch1 [--no-prologue] [--chapter2] [--assets 폴더 | --no-sound]
"""
import argparse
import hashlib
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import dq4buildcache  # noqa: E402
import dq4romledger  # noqa: E402


def step(tool, *args):
    # 표준 출력은 찍지 않는다: 캐시에서 나오면 처음 만든 워크트리의 경로가 들어 있다
    dq4buildcache.run(HERE / tool, *args, echo_stderr=True)


def build(out, dq5, dq4, prologue=True, assets=None, chapter2=False):
    out.mkdir(parents=True, exist_ok=True)
    stages = []

    def done(rom):
        dq4romledger.write(out / 'ledger.json', dq4romledger.build(Path(dq5).read_bytes(), stages))
        return rom

    def stage(name, rom):
        stages.append((name, Path(rom).read_bytes(), Path(rom).name))
    with ThreadPoolExecutor() as pool:
        layers = pool.submit(step, 'dq4titlelayers.py', '--out', out / 'title')
        messages = pool.submit(step, 'dq4chapter1.py', 'messages', '--dq5', dq5, '--dq4', dq4,
                               '-o', out / 'messages.json')
        layers.result()
        step('dq4titlelayerpatch.py', '--rom', dq5, '--input', out / 'title', '--out', out / 'title.sfc')
        stage('title', out / 'title.sfc')
        step('dq4overture.py', 'build', '--nes', dq4, '--rom', dq5, '--title', out / 'title.sfc',
             '--out', out / 'overture.sfc')
        stage('overture', out / 'overture.sfc')
        messages.result()
    step('dq4menupatch.py', 'build', '--rom', out / 'overture.sfc', '--messages', out / 'messages.json',
         '--out', out / 'menu.sfc')
    stage('menu', out / 'menu.sfc')
    step('dq4chapter1.py', 'build', '--rom', out / 'menu.sfc', '--dq5', dq5, '--dq4', dq4,
         '--out', out / 'dq4-ch1.sfc', *([] if prologue else ['--no-prologue']),
         *(['--chapter2'] if chapter2 else []))
    stage('chapter1', out / 'dq4-ch1.sfc')
    if assets is None:
        return done(out / 'dq4-ch1.sfc')
    subprocess.run([sys.executable, HERE / 'dq4soundset.py', '--base', out / 'dq4-ch1.sfc', '--assets', assets,
                    f'@{HERE / "dq4sound-game.args"}', '--out', out / 'dq4-ch1-sound.sfc'],
                   check=True, stdout=subprocess.DEVNULL)
    # 칼 효과가 같은 파일을 고쳐 쓰므로 곡 묶음만 얹은 롬은 여기서 따로 잡아 둔다
    stage('sound', out / 'dq4-ch1-sound.sfc')
    # 서장 수련의 칼 효과(NDS 화면에서 잡은 프레임)는 에셋 저장소에 있어 곡 롬에 얹는다. 없으면 효과음만 난다
    subprocess.run([sys.executable, HERE / 'dq4sparfx.py', 'apply', '--base', out / 'dq4-ch1-sound.sfc',
                    '--assets', assets, '--out', out / 'dq4-ch1-sound.sfc'], check=True, stdout=subprocess.DEVNULL)
    # 칼 효과는 체크섬을 다시 맞추지 않는다. 인물 그림 단계가 없으면 이 롬이 결과물이라 여기서 맞춘다
    from dq4romassets import set_checksum
    sound = out / 'dq4-ch1-sound.sfc'
    sound.write_bytes(set_checksum(sound.read_bytes()))
    stage('sparfx', sound)
    import dq4people
    if not (Path(assets) / dq4people.FIELD).is_dir():
        print(f'{Path(assets) / dq4people.FIELD} 이 없어 인물 그림 없이 곡 롬에서 끝낸다', file=sys.stderr)
        return done(out / 'dq4-ch1-sound.sfc')
    subprocess.run([sys.executable, HERE / 'dq4people.py', '--base', out / 'dq4-ch1-sound.sfc', '--dq5', dq5,
                    '--assets', assets, '--out', out / 'dq4-ch1-full.sfc', '--work', out / 'leader'],
                   check=True, stdout=subprocess.DEVNULL)
    stage('people', out / 'dq4-ch1-full.sfc')
    return done(out / 'dq4-ch1-full.sfc')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--out', required=True, type=Path, help='중간 롬과 dq4-ch1.sfc 를 둘 폴더')
    ap.add_argument('--dq5', default='rom/dq5.sfc', type=Path)
    ap.add_argument('--dq4', default='rom/dq4.nes', type=Path)
    ap.add_argument('--no-prologue', action='store_true', help='NDS 서장 없이 새 게임을 1장으로 시작')
    ap.add_argument('--chapter2', action='store_true', help='1장 끝에서 2장으로 넘어감(기본은 1장에서 끝냄)')
    ap.add_argument('--assets', type=Path, default=os.environ.get('DQ4_ASSETS'),
                    help='곡 묶음의 NDS 곡을 읽을 자원 저장소(기본 DQ4_ASSETS)')
    ap.add_argument('--no-sound', action='store_true', help='곡 묶음을 얹지 않음')
    args = ap.parse_args()
    assets = None if args.no_sound else args.assets
    if assets is None and not args.no_sound:
        print('자원 저장소(--assets, DQ4_ASSETS)가 없어 곡 묶음 없이 만든다', file=sys.stderr)
    rom = build(args.out, args.dq5, args.dq4, not args.no_prologue, assets, args.chapter2)
    print(f'{rom} sha1={hashlib.sha1(rom.read_bytes()).hexdigest()}')


if __name__ == '__main__':
    main()
