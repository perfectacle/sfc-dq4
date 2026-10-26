"""DQ5(SFC) 에셋용 MesenCE 장면 만들기: 배 선실 세이브스테이트에서 dq5warp.lua 로 전투 상태를 만들고, 그 상태로
연출 덤프(lua/dq5fxdump.lua)와 몬스터 움직임 장면(lua/dq5monlog.lua 화면 버퍼)을 뜬다. dq5assets.py 가 부른다.
세이브스테이트는 dq5assets.py 가 전원부터 만든 것을 받는다.

연출 덤프(dq5fx.py --export 의 입력)는 네 갈래다. 형식은 sfc/dq5/docs/dq5-graphics-format.md 「연출 번호와 프레임 덤프」,
상태를 만드는 값의 근거는 sfc/dq5/journal/2026-10-25-182-fxframes.md.
  h   주인공이 주문 칸 8(23:BE31, 파일 오프셋 11BE31)의 주문을 건다. 슬라임 셋·ドラキー 둘, 몬스터 HP 200, 주인공 MP 99
  m   슬라임이 행동 여섯 칸(118011)의 행동을 쓴다. 슬라임 MP 255
  m2  m 에 행동 평가 조건(필드 68, 118008)을 0 으로. 회복·メガンテ·モシャス·がったいだ·マホトラ 처럼 m 에서 900프레임 안에
      고르지 않던 행동
  p   동료 둘(スラリン·ドラきち)과 MP 99 를 넣은 일행에서 ミナデイン(12)

몬스터 움직임(--motion)은 dq5monmotion.py 의 롬 그림(슬라임·ドラキー 칸 0·3 의 hit·die·hop)과 게임 화면 장면 GIF 14개다.
장면마다 전투 상태를 만들고(MOTION_STATES), 한 번 돌려 실마리 PC 를 처음 실행한 프레임을 찾은 뒤(EXEC), 같은 입력으로 다시
돌려 그 앞뒤 프레임의 화면 버퍼를 찍는다(SHOTS=1). 입력이 같으면 프레임도 같다. 근거는 일지 2026-10-25-180·185·192.
환경 변수 MESENCE(실행 파일)가 있어야 한다. 결과는 롬에서 나온 자료라 커밋하지 않는다.

  uv run --locked python sfc/dq5/tools/dq5scenes.py rom/dq5.sfc SHIP.mss --fx-dumps work/fx [--only h,m]
  uv run --locked python sfc/dq5/tools/dq5scenes.py rom/dq5.sfc SHIP.mss --motion $OUT/monsters/motion --work work/motion [--only entrance]
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

TOOLS = os.path.dirname(os.path.abspath(__file__))
LUA = os.path.join(TOOLS, 'lua')

FIELD_BATTLE = dict(FIELD='341,56', BATTLE='00:3,03:2', SETTLE='300')
HP200 = '118001=00;118003=C8;11804C=00;11804B=C8'
STATES = {
    'cast': dict(FIELD_BATTLE, ROMPATCH=HP200, SET='2064=01;2050=63;2044=63'),
    'castm': dict(FIELD_BATTLE, ROMPATCH=HP200 + ';118004=FF;11804D=FF'),
    'castp': dict(FIELD_BATTLE, ROMPATCH=HP200, PARTY='02,03',
                  SET='2064=01;2050=63;2044=63;206E=63;207A=63;2098=63;20A4=63'),
}
HERO_PRE = 'a:4,wait:60,down:8,wait:30,a:8,wait:60'
FX_KINDS = {
    'h': ('cast', [0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x09, 0x0A, 0x0B, 0x0C, 0x0D, 0x0E, 0x0F, 0x10,
                   0x11, 0x14, 0x15, 0x16, 0x17, 0x18, 0x1A, 0x1B, 0x1F, 0x20]),
    'm': ('castm', [0x39, 0x3A, 0x3B, 0x3C, 0x3D, 0x3E, 0x3F, 0x40, 0x41, 0x42, 0x43, 0x44, 0x45, 0x46, 0x47, 0x48,
                    0x49, 0x4B, 0x4C, 0x4D, 0x4E, 0x4F, 0x52, 0x53, 0x54, 0x55, 0x56, 0x57, 0x59, 0x65, 0x6F,
                    0x70, 0x8E, 0x8F, 0x90, 0x91, 0x92, 0x93, 0x94]),
    'm2': ('castm', [0x4A, 0x50, 0x51, 0x58, 0x5A, 0x5B, 0x5C, 0x5D, 0x5E, 0x5F, 0x60, 0x61, 0x62, 0x63, 0x64, 0x6F]),
    'p': ('castp', [0x12]),
}


def toolkit_lua():
    return subprocess.run(['uv', 'run', '--locked', 'krpatch', 'sfc', 'lua'], capture_output=True, text=True,
                          check=True).stdout.strip()


def driver_lib(root, driver):
    """lib.lua 와 driver 를 boot.lua 로 둔 LIBDIR(프로브가 끝에서 부르는 드라이버)."""
    os.makedirs(root, exist_ok=True)
    shutil.copy(os.path.join(toolkit_lua(), 'lib.lua'), os.path.join(root, 'lib.lua'))
    shutil.copy(os.path.join(LUA, driver), os.path.join(root, 'boot.lua'))
    return root


def mesen(rom, script, env, out, timeout=900):
    os.makedirs(out, exist_ok=True)
    subprocess.run([os.environ['MESENCE'], '--testrunner', os.path.abspath(rom), script],
                   env=dict(os.environ, SHOT_DIR=os.path.abspath(out), **env),
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=timeout, check=False)


def warp_state(rom, ship, out, name, env):
    """ship 에서 dq5warp.lua 로 env 장면에 가 out/name 세이브스테이트를 만든다. 경로를 돌려준다."""
    mesen(rom, os.path.join(LUA, 'dq5warp.lua'),
          dict(env, LIBDIR=toolkit_lua(), STATE=os.path.abspath(ship), SAVE=name), out)
    path = os.path.join(out, name)
    if not os.path.exists(path):
        raise RuntimeError(f'{name} 을 만들지 못함({out}/warp.txt)')
    return path


def fx_dump(rom, lib, state, kind, n, out):
    if kind in ('h', 'p'):
        env = dict(ROMPATCH=f'11BE31={n:02X}', PRE=HERO_PRE, MAXF='800')
    else:
        patch = f'118011={f"{n:02X}" * 6}' + (';118008=00' if kind == 'm2' else '')
        env = dict(ROMPATCH=patch, MAXF='900')
    mesen(rom, os.path.join(LUA, 'dq5fxdump.lua'),
          dict(env, LIBDIR=lib, STATE=os.path.abspath(state), LOOP='a:3,wait:40'), out)
    return out


def fx_dumps(rom, ship, work, kinds=None, jobs=6):
    """연출 덤프 네 갈래를 work/<갈래>/<행동>/ 에 뜬다. dq5fx.export_all 에 줄 폴더 목록을 돌려준다(이 차례로 먼저 찍힌
    연출을 쓴다)."""
    kinds = kinds or list(FX_KINDS)
    lib = driver_lib(os.path.join(work, 'blib'), 'dq5battle.lua')
    need = sorted({FX_KINDS[k][0] for k in kinds})
    with ThreadPoolExecutor(len(need)) as ex:
        states = dict(zip(need, ex.map(lambda s: warp_state(rom, ship, os.path.join(work, 'state', s), f'{s}.mss',
                                                            STATES[s]), need)))
    jobs_list = [(k, n) for k in kinds for n in FX_KINDS[k][1]]
    with ThreadPoolExecutor(jobs) as ex:
        list(ex.map(lambda t: fx_dump(rom, lib, states[FX_KINDS[t[0]][0]], t[0], t[1],
                                      os.path.join(work, t[0], f'{t[1]:02X}')), jobs_list))
    return [os.path.join(work, k) for k in kinds]


MONSTER_RECORD, MONSTER_SIZE = 0x118000, 25     # 23:8000 몬스터 레코드(파일 오프셋). +3·+10 하위 3비트 HP, +8 필드 68, +11 행동 6칸
HERO_HP = '7E2042=E7;7E2043=03'                 # 전투 중 주인공 지금 HP(일행 레코드 +2) 999
# 보스 HP 를 1 로: 전투 몬스터 칸 0(7E:07C0)의 +2 지금 HP. 레코드를 덮지 않는 것은 무리 2F 의 칸 HP 가 4500 으로
# 레코드의 11비트 HP(최대 2047)와 따로 정해져서다. 불러온 뒤 한 번만 쓴다(lua/dq5pokeonce.lua).
BOSS_HP1 = '7E07C2=01;7E07C3=00'
SHOT_SOURCE = '게임 화면 버퍼(dq5monlog SHOTS=1, emu.getScreenBuffer), 프레임 흔들림 없음'
SHEET_GROUPS = '00:3,03:2'


def record(mon, field):
    return MONSTER_RECORD + mon * MONSTER_SIZE + field


def actions(mon, act):
    """몬스터 mon 이 행동 act 만 고르게: 행동 6칸을 act 로, 행동 평가 조건(필드 68)을 0 으로."""
    return f'{record(mon, 0x11):06X}={f"{act:02X}" * 6};{record(mon, 8):06X}=00'


def motion_states():
    mp255 = HP200 + ';118004=FF;11804D=FF'
    states = {
        'castm': STATES['castm'],
        'party9': dict(FIELD_BATTLE, ROMPATCH=mp255, PARTY='09'),
        'slime3': dict(FIELD='341,56', BATTLE='00:3', SETTLE='300', ROMPATCH='118001=00;118003=C8',
                       SET='2064=01;2050=63;2044=63'),
        'slime8': dict(FIELD='341,56', BATTLE='00:8', SETTLE='300', ROMPATCH='118001=00;118003=C8;118004=FF'),
    }
    for g in ('20', '26', '2B', '2C', '2F'):
        states[f'boss{g}'] = dict(FIELD='341,56', GROUP=g, SETTLE='300')
    return states


# (이름, 제목, 상태, 드라이버 변수, 실마리 PC, 앞 프레임, 뒤 프레임, MAXF). 상태가 None 이면 배 선실에서 dq5warp.lua 로
# 전투에 들어가는 장면을 그대로 찍는다.
MOTION = [
    ('entrance', '전투 배경 열기 22:8BE8', None, dict(FIELD='341,56', BATTLE='00:3,03:2', SETTLE='300'),
     0x228BE8, 8, 48, 700),
    ('party-shake', '우리 편 맞음 BG3 흔들림 22:FC93', 'castm', dict(), 0x22FC93, 4, 40, 1500),
    ('summon-same', '부르기 AB(같은 몬스터) 22:D1A9+CE56', 'castm', dict(ROMPATCH=actions(0x00, 0xAB)),
     0x22D1A9, 8, 28, 1500),
    ('summon-new', '부르기 AE(몬스터 1E) 22:D2FE+CE56', 'castm', dict(ROMPATCH=actions(0x00, 0xAE)),
     0x22D2FE, 8, 32, 1500),
    ('summon-fadein-2B', 'ミルドラース 의 부르기 B7, 22:CEA5', 'boss2B', dict(ROMPATCH=actions(0xE7, 0xB7), POKE=HERO_HP),
     0x22CEA5, 8, 60, 2500),
    ('merge-6F', 'がったいだ 6F 끝 22:D2FE', 'slime8', dict(ROMPATCH=actions(0x00, 0x6F)), 0x22D2FE, 70, 22, 1500),
    ('mosyas-58', '몬스터 モシャス 58, 22:D3B9', 'party9', dict(ROMPATCH=actions(0x00, 0x58)), 0x22D3B9, 8, 34, 1500),
    ('parupunte-1A', 'パルプンテ 1A, 22:D45D', 'slime3',
     dict(ROMPATCH='11BE31=31;1040EF=A91AEAEA;1062AB=EAEA', PRE=HERO_PRE), 0x22D45D, 6, 22, 1500),
    ('self-ko-AA', 'たいあたり AA 뒤 22:CBC5', 'castm', dict(ROMPATCH=actions(0x00, 0xAA)), 0x22CBC5, 8, 26, 1500),
    ('boss-hit-20', '보스 전투(무리 20, $1014=1)에서 맞음 22:FD26', 'boss20', dict(POKE=HERO_HP, POKEONCE=BOSS_HP1), 0x22FD26, 4, 44, 2000),
    ('boss-sink-26', 'ブオーン(무리 26) 쓰러짐 22:CDA9', 'boss26', dict(POKE=HERO_HP, POKEONCE=BOSS_HP1), 0x22CDA9, 8, 250, 2500),
    ('boss-sink-2C', 'エスターク(무리 2C) 쓰러짐 22:CDA9', 'boss2C', dict(POKE=HERO_HP, POKEONCE=BOSS_HP1), 0x22CDA9, 8, 250, 2500),
    ('boss-fade-2B', 'ミルドラース(무리 2B) 쓰러짐 22:CC16', 'boss2B', dict(POKE=HERO_HP, POKEONCE=BOSS_HP1), 0x22CC16, 8, 140, 2500),
    ('boss-fade-2F', 'ミルドラース(무리 2F) 쓰러짐 22:CC16', 'boss2F', dict(POKE=HERO_HP, POKEONCE=BOSS_HP1), 0x22CC16, 8, 296, 2500),
]


def monlog(rom, lib, env, out, frm, to, shots):
    e = dict(env, LIBDIR=lib, FROM=str(frm), TO=str(to), MAXF=str(to + 2))
    if shots:
        e['SHOTS'] = '1'
    mesen(rom, os.path.join(LUA, 'dq5monlog.lua'), e, out, timeout=1800)


def motion_scene(rom, libs, states, ship, scene, work):
    """장면 하나를 찍어 (이름, 찍은 폴더, 처음, 끝) 또는 실마리를 못 찾으면 (이름, None, 0, 0)."""
    name, _, state, env, pc, pre, post, maxf = scene
    if state is None:
        lib, env = libs['warp'], dict(env, STATE=os.path.abspath(ship))
    else:
        lib, env = libs['battle'], dict(env, STATE=os.path.abspath(states[state]), LOOP='a:3,wait:40')
        if 'POKEONCE' in env:
            lib, env = libs['once'], dict(env, NEXT=os.path.join(libs['battle'], 'boot.lua'))
    probe = os.path.join(work, name, 'probe')
    monlog(rom, lib, dict(env, EXEC=f'{pc:06X}'), probe, 0, maxf, False)
    path = os.path.join(probe, 'exec.txt')
    hits = [int(line.split()[0]) for line in open(path) if line.strip()] if os.path.exists(path) else []
    shutil.rmtree(probe, ignore_errors=True)
    if not hits:
        return name, None, 0, 0
    first, last = max(1, hits[0] - pre), hits[0] + post
    shots = os.path.join(work, name, 'shots')
    monlog(rom, lib, env, shots, first, last, True)
    return name, shots, first, last


def motion(rom_path, ship, outdir, work, only=None, jobs=6):
    """몬스터 움직임 그림 전부를 outdir 에 쓰고 index.json 을 남긴다. 못 찍은 장면 이름 목록을 돌려준다."""
    sys.path.insert(0, TOOLS)
    import dq5monmotion
    import dq5text
    from dq5map import Rom
    data = open(rom_path, 'rb').read()
    rom = Rom(data)
    items = []
    if not only or 'sheets' in only:
        groups = [(int(m, 16), int(n)) for m, n in (g.split(':') for g in SHEET_GROUPS.split(','))]
        names = {m: dq5text.text(dq5text.string_codes(rom, dq5text.string(rom, 4, m))) for m, _ in groups}
        stem0 = '-'.join(f'{m:02X}' for m, _ in groups)
        for target in (0, 3):
            for kind, frames in dq5monmotion.motions(rom, groups, target).items():
                for it in dq5monmotion.save(frames, outdir, f'{stem0}-{target}-{kind}',
                                            f'{"·".join(names.values())} 칸 {target} {kind}'):
                    items.append(dict(it, groups=SHEET_GROUPS, cat='motion'))
    scenes = [sc for sc in MOTION if not only or sc[0] in only]
    if scenes:
        libs = {'warp': driver_lib(os.path.join(work, 'wlib'), 'dq5warp.lua'),
                'battle': driver_lib(os.path.join(work, 'blib'), 'dq5battle.lua'),
                'once': driver_lib(os.path.join(work, 'olib'), 'dq5pokeonce.lua')}
        table = motion_states()
        need = sorted({sc[2] for sc in scenes if sc[2]})
        with ThreadPoolExecutor(jobs) as ex:
            states = dict(zip(need, ex.map(lambda s: warp_state(rom_path, ship, os.path.join(work, 'state', s),
                                                                f'{s}.mss', table[s]), need)))
        with ThreadPoolExecutor(jobs) as ex:
            got = list(ex.map(lambda sc: motion_scene(rom_path, libs, states, ship, sc, work), scenes))
    else:
        got = []
    missing = []
    titles = {sc[0]: sc[1] for sc in MOTION}
    for name, shots, first, last in got:
        if not shots:
            missing.append(name)
            print(f'{name}: 실마리 PC 를 실행하지 않음')
            continue
        for it in dq5monmotion.shots_anim(shots, first, last, outdir, name, titles[name]):
            items.append(dict(it, source=SHOT_SOURCE, cat='motion'))
        print(f'{name}: {first}~{last}')
    os.makedirs(outdir, exist_ok=True)
    with open(os.path.join(outdir, 'index.json'), 'w', encoding='utf-8') as f:
        json.dump(items, f, ensure_ascii=False, indent=1)
        f.write('\n')
    return missing


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('rom')
    ap.add_argument('ship', help='배 선실 세이브스테이트')
    ap.add_argument('--fx-dumps', metavar='DIR', help='연출 덤프를 뜰 폴더')
    ap.add_argument('--motion', metavar='DIR', help='몬스터 움직임 그림을 쓸 폴더')
    ap.add_argument('--work', default='work/dq5scenes', help='--motion 의 세이브스테이트·화면 버퍼를 둘 곳')
    ap.add_argument('--only', help='쉼표로 갈래(h,m,m2,p) 또는 장면 이름(sheets, entrance, …)')
    ap.add_argument('--jobs', type=int, default=6)
    a = ap.parse_args()
    if not os.environ.get('MESENCE'):
        print('MESENCE 환경 변수가 필요함', file=sys.stderr)
        return 1
    if a.fx_dumps:
        for d in fx_dumps(a.rom, a.ship, os.path.abspath(a.fx_dumps), a.only and a.only.split(','), a.jobs):
            got = sum(1 for s in os.listdir(d) if os.path.exists(os.path.join(d, s, 'fx.txt')))
            print(f'{d}: 덤프 {got}개')
    if a.motion:
        missing = motion(a.rom, a.ship, os.path.abspath(a.motion), os.path.abspath(a.work),
                         a.only and a.only.split(','), a.jobs)
        if missing:
            print(f'못 찍은 장면: {",".join(missing)}', file=sys.stderr)
            return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
