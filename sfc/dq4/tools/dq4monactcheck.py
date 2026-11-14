"""2장 전투 몬스터(dq4monport 의 PORT·EVENT 번호)가 빌드 롬의 행동마다 그 행동을 쓰고도 전투가 멈추지 않는지 보는 검사.
형식 문서 sfc/dq4/docs/dq4-sprite-format.md 「2장 전투 몬스터 능력치」.

FC 주문을 일행 주문 번호로 옮기면 몬스터가 쓸 때 전투가 멈추므로(dq4monport.FC_ACTIONS), 몬스터마다 롬 레코드의 행동
여섯 가운데 서로 다른 것 하나씩을 행동 여섯 칸 모두에 두고(롬 치트) 한 마리 무리로 붙여 싸운다. dq4monartcheck 처럼
저장 기록으로 이어 해 탑 39/01 에 서고 조우 루틴 23:E7C2 를 덮는다. 시드는 dq4ch1walkcheck.rng_for(0), 주인공은 레벨 20·
HP 999 로 매 차례 방어하고(회복 행동 HEALS 는 첫 차례에 몬스터 HP 를 HURT 로 줄임), 몬스터는 HP 만 2000 으로(능력치·MP 는 롬 그대로) 둔다.
판정: 행동하는 쪽 7E:10F5 가 몬스터(bit7)이고 행동 7E:10F7 이 그 행동인 프레임이 나온 뒤(쓴 것), 다음 차례 창·맵 명령 창
(도망 등으로 끝남)·그 행동의 둘째 사용(주인공이 잠들어 차례 창이 오지 않을 때) 가운데 하나가 PROGRESS 프레임 안에 와야
한다. 쓰지 않은 채 USE_LIMIT 를 넘기면 「안 씀」 으로 실패, 쓴 뒤 멈추면 「멈춤」 으로 실패다. 몬스터가 행동을 거르는
조건(MP, 필드 68 의 조건 표)에 걸려 쓰지 못하는 행동은 ALLOWED_UNUSED 에 까닭과 함께 둔다.

  python sfc/dq4/tools/dq4cores.py
  python sfc/dq4/tools/dq4monactcheck.py --rom work/ch1/dq4-ch1-full.sfc --out work/monactcheck
결과: OUT/results.json, 실패한 전투의 화면 OUT/<번호>-<행동>.png.
"""
import argparse
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[1] / 'dq5' / 'tools')]

import dq4monport  # noqa: E402

CORE = 'snes9x'
SCENE = 'monact'
SEED = 0
ACTOR, ACTION = 0x7E10F5, 0x7E10F7
MONSTER_ACTOR = 0x80
ACTIONS_AT = 17                   # 레코드 +17~+22: 행동 여섯(dq5tables.MONSTER_FIELDS)
USE_LIMIT = 6000                  # 전투가 걸린 뒤 그 행동을 쓰기까지
PROGRESS = 3000                   # 쓴 뒤 다음 차례 창·끝·둘째 사용까지
# 몬스터는 HP 가 최대(레코드)의 1/4 아래인 편이 없으면 회복 주문을 고르지 않으므로(21:BB42 조건 0E), 이 행동은 첫 차례 창에서
# 슬롯 HP(7E:07C0 + 16k + 2)를 HURT 로 둔다
HEALS = range(0x5A, 0x62)         # ホイミ ~ ベホマズン(몬스터용)
HURT = 100
# 쓰지 못해도 되는 (DQ5 번호, 행동): 까닭
ALLOWED_UNUSED = {}


def plan(rom):
    """[(DQ5 번호, 행동)]: PORT·EVENT 번호(dq4monport.LATER 밖)마다 롬 레코드의 서로 다른 행동."""
    import dq4ch1walkcheck as wc
    out = []
    for m in [*dq4monport.PORT.values(), *dq4monport.EVENT.values()]:
        if m in dq4monport.LATER:
            continue
        base = wc.MONSTERS + m * 25 + ACTIONS_AT
        for a in dict.fromkeys(rom[base:base + 6]):
            out.append((m, a))
    return out


def judge(events):
    """events: [(전투 프레임, 종류)], 종류는 'use'·'turn'·'field'. (결과 'ok'·'unused'·'stuck', 처음 쓴 프레임)."""
    uses = [f for f, k in events if k == 'use']
    if not uses:
        return 'unused', None
    first = uses[0]
    after = [f for f, _ in events if f > first]
    return ('ok' if after and after[0] - first <= PROGRESS else 'stuck'), first


class Battles:
    """snes9x 하나로 이어 하기 → 탑에 선 상태를 만들고, (번호, 행동)마다 그 상태에서 전투를 붙인다."""

    def __init__(self, rom_path, numbers, out):
        import dq4battlescene as B
        self.B = B
        B.SCENES[SCENE] = {'what': '2장 몬스터 행동', 'group': [(numbers[0], 1)], 'turn': 'defend',
                           'monsters': {m: {'hp': 2000, 'actions': None} for m in numbers},
                           'hero': {'level': 20, 'max_hp': 999, 'hp': 999}}
        (out / 'core').mkdir(parents=True, exist_ok=True)
        self.out = out
        self.run = B.Run(CORE, rom_path, SCENE, out / 'core')
        self.state = self.run.prepare()

    def close(self):
        import dq4savefixture as fx
        fx.close(self.run.c)

    def battle(self, m, action, probe=False):
        """한 판: {'result', 'used', 'frames', 'log'(probe 면 (프레임, 10F5, 10F6, 10F7) 바뀜)}."""
        import dq4ch1walkcheck as wc
        import dq4compatcheck as cc
        B, c, w = self.B, self.run.c, self.run.w
        group = [(m, 1)]
        c.load(self.state)
        w.cheat_key, w.rom_cheats = None, {}
        c.poke(cc.sets(wc.rng_for(SEED)))
        c.poke([(B.GROUP + i, 0) for i in range(8)])
        acts = {'acts': cc.rom_codes(wc.MONSTERS + m * 25 + ACTIONS_AT, bytes((action,)) * 6)}
        w.rom_cheats = {**acts, 'force': cc.rom_codes(B.ENCOUNTER, B.force_code(group, 0))}
        w.apply()
        sentinel = B.group_sentinel(group)
        t0 = c.n
        while bytes(c.rd(B.GROUP + i) for i in range(len(sentinel))) != sentinel:
            if c.n - t0 >= B.STEP_LIMIT:
                raise RuntimeError(f'{m:02X}: 전투가 걸리지 않음')
            w.step({'down'})
        w.rom_cheats = acts
        w.apply()
        start = c.n
        events, log = [], []
        last_window, turn_at, policy_until = c.rd(B.WINDOW), None, 0
        policy = B.TURNS['defend']
        acting, seen_window, buttons = False, False, set()
        used_at = None
        while True:
            f = c.n - start
            if used_at is None and f >= USE_LIMIT or used_at is not None and f - used_at > PROGRESS:
                break
            w.step(buttons)
            buttons = set()
            actor, act = c.rd(ACTOR), c.rd(ACTION)
            if probe and (not log or log[-1][1:] != (actor, c.rd(ACTOR + 1), act)):
                log.append((f, actor, c.rd(ACTOR + 1), act))
            now = bool(actor & MONSTER_ACTOR) and act == action
            if now and not acting:
                events.append((f, 'use'))
                if used_at is None:
                    used_at = f
            acting = now
            window = c.rd(B.WINDOW)
            seen_window = seen_window or window not in (0x00, 0xFF, B.FIELD_WINDOW)
            if last_window == 0xFF and window == B.TURN_WINDOW:
                if action in HEALS and not any(k == 'turn' for _, k in events):
                    c.poke([(B.MONSTER_SLOTS + 2, HURT & 0xFF), (B.MONSTER_SLOTS + 3, HURT >> 8)])
                events.append((f, 'turn'))
                turn_at = c.n
                policy_until = c.n + max(x for x, _ in policy) + 30
            last_window = window
            if window == B.FIELD_WINDOW and seen_window:
                events.append((f, 'field'))
                break
            if turn_at is not None and c.n < policy_until:
                buttons = self.run.press_for(policy, turn_at)
            elif window not in B.INPUT_WINDOWS and f % B.MASH < 4:
                buttons = {'a'}
            if used_at is not None and any(k != 'use' and x > used_at for x, k in events) or \
                    used_at is not None and sum(k == 'use' for _, k in events) > 1:
                break
        end = c.n - start
        result, used = judge(events)
        if result != 'ok':
            c.shot(self.out / f'{m:02X}-{action:02X}.png')
        return {'result': result, 'used': used, 'frames': end, 'events': events[:12],
                **({'log': log[:200]} if probe else {})}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--rom', type=Path, required=True, help='빌드 롬(dq4-ch1-full.sfc)')
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--only', help='번호:행동[,…] 만(16진)')
    ap.add_argument('--probe', action='store_true', help='10F5~10F7 바뀜을 결과에 남김')
    a = ap.parse_args(argv)
    t0 = time.time()
    a.out.mkdir(parents=True, exist_ok=True)
    rom = a.rom.read_bytes()
    rows = plan(rom)
    if a.only:
        want = {tuple(int(x, 16) for x in p.split(':')) for p in a.only.split(',')}
        rows = [r for r in rows if r in want]
    run = Battles(a.rom, sorted({m for m, _ in rows}), a.out)
    results, problems = {}, []
    try:
        for m, action in rows:
            key = f'{m:02X}:{action:02X}'
            r = run.battle(m, action, a.probe)
            results[key] = r
            print(f'{key} {r["result"]:6s} 씀 {r["used"]} 끝 {r["frames"]}', flush=True)
            if r['result'] == 'ok':
                continue
            why = ALLOWED_UNUSED.get((m, action))
            if r['result'] == 'unused' and why:
                r['allowed'] = why
                continue
            problems.append(f'{key}: {"안 씀" if r["result"] == "unused" else "멈춤"} ({r["frames"]}프레임)')
    finally:
        run.close()
    report = {'rom': a.rom.name, 'battles': results, 'problems': problems, 'seconds': round(time.time() - t0, 1)}
    (a.out / 'results.json').write_text(json.dumps(report, ensure_ascii=False, indent=1) + '\n')
    print(f'몬스터 {len({m for m, _ in rows})}종 행동 {len(rows)}판, 문제 {len(problems)}개; {report["seconds"]}초')
    for p in problems:
        print('  ' + p)
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main())
