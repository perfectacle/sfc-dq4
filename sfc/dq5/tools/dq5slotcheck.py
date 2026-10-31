"""16x16 자리 사슬(7E:8400, 남은 수 $0D1F)의 끝과, 연출의 OBJ 그림이 몬스터 그림과 함께 쓰는 자리를 MesenCE 에서 잰다.

사슬 끝: 무리 7E 1 만의 전투(그림 43, 자리 14)에서 전투를 시작할 때 사슬 앞 칸을 CHAIN 개 채운다(dq5nmidma.lua 의 SLOTS).
  113 + 14 = 127 이면 그림이 풀리고 다음 자리($0D1D)가 사슬 안(127)에 남는지, 128 이면 풀린 뒤 다음 자리가 사슬 밖
  (조각 목록 사슬 7E:8480 쪽, 128 이상)으로 넘어가는지, 129 이면 할당(22:AC65)이 거절해 그림을 풀지 않는지 본다.

연출의 OBJ 그림은 22:BB3D 가 몬스터 그림과 같은 할당 22:AC79 로 자리·조각 목록 칸을 받는다. dq5scenes.py 의 연출 82가지
(FX_KINDS: 주인공 주문·몬스터 행동·동료 주문)를 같은 상태·롬 덮기로 돌리며 lua/dq5slotlog.lua 로 할당마다 남은 수를 적고,
연출마다 첫 할당 앞의 남은 수에서 가장 적게 남았을 때를 뺀 값(연출이 한꺼번에 쓴 자리·조각 칸)을 센다. 그 가장 큰 값이
dq5monlimits.EFFECT_SLOTS 안이어야 한다. 이 값은 도구 장면의 연출 82가지 안에서 잰 가장 큰 값일 뿐이다. がったいだ(6F)는 キングスライム 그림(51)을 같은 할당으로 풀므로 그 몫은 뺀다.
  MESENCE=… python sfc/dq5/tools/dq5slotcheck.py rom/dq5.sfc --state work/state/ship.mss
"""
import argparse
import os
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dq5monlimits as L  # noqa: E402
import dq5monnmicheck as C  # noqa: E402
import dq5scenes as S  # noqa: E402
from dq5map import Rom  # noqa: E402
from dq5progresscheck import require, save_json  # noqa: E402

HERE = Path(__file__).resolve().parent
EFFECT_PICTURES = range(0x80, 0x100)   # 연출의 OBJ 그림 번호($0D1A). 몬스터 그림은 00~71
CHAIN = (113, 114, 115)                # 그림 43 의 자리 14 를 더해 127·128·129


def chain_case(rom, state, mesence, lib, n, work):
    out = work / 'chain' / str(n)
    out.mkdir(parents=True)
    C.run(rom, out, state, mesence, lib, '7E:1', None, n)
    got, d = C.arrived(Rom(rom.read_bytes()), out)
    wram = (out / f'f{C.DUMP:05d}.wram').read_bytes()
    slots = L.Pictures(Rom(rom.read_bytes())).slots(C.WIDE)
    used = n + slots
    loaded = C.WIDE in wram[0x0D3D:0x0D4D]
    tiles = sum(len(p[3]) for p in d['pieces'] if not p[4])
    nxt = wram[0x0D1D]
    if used <= L.SLOT_LIMIT:
        ok = loaded and got == tiles and nxt < 0x80
    elif used == 0x80:
        ok = loaded and nxt >= 0x80
    else:
        ok = not loaded
    return {'filled': n, 'used': used, 'loaded': loaded, 'arrived': got, 'tiles': tiles, 'next': nxt,
            'left': wram[0x0D1F], 'ok': ok}


def one(rom, lib, states, kind, n, work):
    if kind in ('h', 'p'):
        env = dict(ROMPATCH=f'11BE31={n:02X}', PRE=S.HERO_PRE, MAXF='800')
    else:
        env = dict(ROMPATCH=f'118011={f"{n:02X}" * 6}' + (';118008=00' if kind == 'm2' else ''), MAXF='900')
    out = work / kind / f'{n:02X}'
    S.mesen(rom, str(HERE / 'lua/dq5slotlog.lua'),
            dict(env, LIBDIR=lib, STATE=os.path.abspath(states[S.FX_KINDS[kind][0]]), LOOP='a:3,wait:40'), str(out))
    path = out / 'slots.txt'
    rows = [line.split() for line in path.read_text(encoding='utf-8').splitlines()] if path.exists() else []
    used = slots = pieces = 0
    start = None
    for i, r in enumerate(rows):
        if r[1] != 'alloc' or int(r[2], 16) not in EFFECT_PICTURES:
            continue
        if start is None:
            start = (int(r[5]), int(r[6]))
        if i + 1 < len(rows) and rows[i + 1][1] == 'ok':
            used += 1
            slots = max(slots, start[0] - int(rows[i + 1][2]))
            pieces = max(pieces, start[1] - int(rows[i + 1][3]))
    return f'{kind}/{n:02X}', {'allocs': used, 'slots': slots, 'pieces': pieces}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('rom', type=Path)
    ap.add_argument('--state', required=True, type=Path)
    ap.add_argument('--mesence', default=os.environ.get('MESENCE'))
    ap.add_argument('--out', type=Path, default='work/slotcheck')
    ap.add_argument('--jobs', type=int, default=6)
    args = ap.parse_args()
    if not args.mesence:
        ap.error('--mesence 또는 MESENCE가 필요함')
    try:
        rom, state = args.rom.resolve(), args.state.resolve()
        for path in (rom, state, Path(args.mesence)):
            require(path.is_file(), f'파일 없음: {path}')
        os.environ['MESENCE'] = str(Path(args.mesence).resolve())
        args.out.mkdir(parents=True, exist_ok=True)
        work = Path(tempfile.mkdtemp(prefix='run-', dir=args.out.resolve()))
        print(f'실행 출력: {work}', flush=True)
        lib = S.driver_lib(str(work / 'blib'), 'dq5battle.lua')
        wlib = Path(S.driver_lib(str(work / 'wlib'), 'dq5warp.lua'))
        with ThreadPoolExecutor(args.jobs) as ex:
            chain = list(ex.map(lambda n: chain_case(rom, state, Path(args.mesence).resolve(), wlib, n, work), CHAIN))
        need = sorted({k for k, _ in S.FX_KINDS.values()})
        states = {s: S.warp_state(str(rom), str(state), str(work / 'state' / s), f'{s}.mss', S.STATES[s]) for s in need}
        jobs = [(k, n) for k in S.FX_KINDS for n in S.FX_KINDS[k][1]]
        with ThreadPoolExecutor(args.jobs) as ex:
            seen = dict(ex.map(lambda t: one(str(rom), lib, states, t[0], t[1], work), jobs))
        users = {k: v for k, v in seen.items() if v['allocs']}
        most = max((v['slots'] for v in seen.values()), default=0)
        checks = {'ran': len(seen) == len(jobs), 'effect-slots': most <= L.EFFECT_SLOTS,
                  'chain': all(r['ok'] for r in chain)}
        save_json(work / 'results.json', {'chain': chain, 'effects': seen, 'checks': checks})
        for r in chain:
            print(f'사슬 앞 {r["filled"]} + 그림 43 = {r["used"]}칸: 풀림 {r["loaded"]}, 닿은 타일 {r["arrived"]}/{r["tiles"]}, '
                  f'다음 자리 {r["next"]}, 남은 수 {r["left"]} {"통과" if r["ok"] else "불일치"}')
        for k, v in users.items():
            print(f'{k}: 할당 {v["allocs"]}번, 한꺼번에 자리 {v["slots"]}개·조각 칸 {v["pieces"]}개')
        print(f'도구 장면의 연출 {len(seen)}가지 가운데 OBJ 그림을 푼 것 {len(users)}가지, 이 장면들에서 가장 많이 쓴 자리 '
              f'{most}개(EFFECT_SLOTS {L.EFFECT_SLOTS}, 장면 밖 연출은 재지 않음)')
        for key, ok in checks.items():
            print(f'{key}: {"통과" if ok else "불일치"}')
        require(all(checks.values()), '불일치: ' + ', '.join(k for k, ok in checks.items() if not ok))
        return 0
    except (OSError, ValueError, KeyError, RuntimeError) as error:
        print(f'오류: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
