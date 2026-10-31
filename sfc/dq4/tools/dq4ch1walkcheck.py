"""새 게임부터 1장 끝(2장 제목 상자)까지 깃발을 두지 않고 이어 걷는 검사(MesenCE 헤드리스).

서장 검사(dq4prologuecheck.py)의 길로 1장 왕좌의 방에 들어온 뒤, 구간마다 앞 구간이 끝난 세이브스테이트에서
시작한다. 맵 사이는 dq5warp.lua 의 「어디서나」 순간이동으로 옮기고, 맵 안에서는 dq4walkstate.lua(walk.lua)로
걷고 말을 건다. 사건 깃발은 사건이 켠 것을 그대로 이어 받는다. 검사를 위해 바꾸는 것은 넷뿐이다.
  - 밤 장면은 시각 7E:075E 를 F0 으로, 낮 장면은 50 으로 묶는다.
  - 돌아다니는 이무르 밤의 아이를 제자리에 묶는다.
  - 조우 판정 23:E7C2(파일 11E7C2, 부르는 곳은 00:82B4 의 JSL 하나)를 CLC/RTL 로 덮어 걸음 전투를 없앤다.
    계수 표(23:EA44)만 0 으로 두면 FC 던전 구역은 dq4dungeonrate 훅(23:E8B7)이 자기 확률을 써서 전투가 남는다.
  - 탑 위 보스 두 마리(몬스터 E2·52)를 HP 1·수비 0 으로 덮고, 보스 구간만 주인공 HP 를 999 로 묶는다.
구간마다 끝 맵·깃발·물건을 보고, 마지막은 1장 끝이다. 1장에서 끝내는 롬(기본 빌드)은 성 앞에서 끝맺음 서술과
끝 상자를 지나 버튼으로 리셋되고, 드라이버를 다시 올리지 않고 다시 시작해 리셋 루틴이 소리 켜기 뒤로 이어지는지
본다. --chapter2 롬(dq4build.py --chapter2)은 1장 끝 서술 뒤 2장 왕좌의 방에 들어가 제목 상자를 기다리는지 본다.

  MESENCE=… LIBDIR=… python sfc/dq4/tools/dq4ch1walkcheck.py --rom work/ch1/dq4-ch1.sfc --out work/ch1walk [--chapter2]
  (--from 구간 --states 앞 출력 폴더 로 그 구간부터 다시 걷는다)
형식은 sfc/dq4/docs/dq4-chapter1-format.md 「검증」.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
DQ5_TOOLS = HERE.parents[1] / 'dq5' / 'tools'
sys.path[:0] = [str(HERE), str(DQ5_TOOLS)]

import dq4mesen as mesen  # noqa: E402
import dq4ch1event as ev  # noqa: E402
import dq4ch2event as ch2  # noqa: E402
import dq4chapterbox as box  # noqa: E402
import dq4prologuecheck as pc  # noqa: E402
from dq5exitcheck import warp_exit  # noqa: E402

WALK = ROOT / 'tools' / 'lua' / 'walk.lua'
WALK_STATE = HERE / 'lua' / 'dq4walkstate.lua'
WARP = DQ5_TOOLS / 'lua' / 'dq5warp.lua'
NIGHT = '7E075E=F0;7E075F=00'
DAY = '7E075E=50;7E075F=00'
NO_ENCOUNTERS = '11E7C2=186B'
MONSTERS = 0x118000                 # 몬스터 표 23:8000(파일 오프셋), 25바이트씩. dq5tables.MONSTER_FIELDS
# 돌아다니는 이무르 밤의 아이(물체 슬롯 16)의 걸음 간격을 0 으로 묶어 제자리에 세운다
HOLD_CHILD = '7E3310=00'
HERO_HP = '7E2042=E7;7E2043=03'     # 일행 레코드 0 의 지금 HP(+2)


def flag(pair):
    index, mask = pair
    return 0x7E2190 + index, mask


FLAGS = {
    'CHAPTER1': box.CHAPTER1.flag,
    'NIGHT_TOLD': flag(ev.NIGHT_TOLD),
    'FLARE': flag(ev.FLARE_FOLLOWS),
    'REUNITED': flag(ev.REUNITED),
    'HOIMIN': flag(ev.HOIMIN),
    'KIDNAPPED': flag(ev.KIDNAPPED),
    'BOSS_WON': flag(ev.BOSS_WON),
    'KIDS_FOLLOW': flag(ev.KIDS_FOLLOW),
    'SOLDIER': flag(ev.SOLDIER_LEFT),
    'REPORTED': flag(ev.REPORTED),
    'CHAPTER2': flag(ch2.CHAPTER2),
    'OPENING': flag(ch2.OPENING),
}


def boss_patch(rom):
    """두 보스 몬스터를 HP 1·수비 0 으로 덮는 ROMPATCH. HP 는 바이트3 + 바이트10 아래 3비트, 수비는 바이트2 + 바이트8 bit6."""
    out = []
    for n in ev.BOSS_MONSTERS:
        base = MONSTERS + n * 25
        out += [f'{base + 2:X}=00', f'{base + 3:X}=01', f'{base + 8:X}={rom[base + 8] & ~0x40 & 0xFF:02X}',
                f'{base + 10:X}={rom[base + 10] & ~0x07 & 0xFF:02X}']
    return ';'.join(out)


# 명령 창 → しらべる(dq4chestcheck.SEARCH 와 같은 줄)
SEARCH = 'a:8;wait:60;down:6;wait:25;down:6;wait:25;down:6;wait:25;right:6;wait:25;a:8;wait:200'
SHOES = 0xCD     # DQ5 ソラトブクツ
# 명령 창 → どうぐ → 주인공 → 셋째 칸(そらとぶくつ) → つかう. 목록에 들어간 뒤 첫 아래 키는 먹히지 않아 셋을 누른다
USE_SHOES = ('a:8;wait:60;down:8;wait:30;right:8;wait:30;a:8;wait:80;a:8;wait:80;'
             'down:8;wait:40;down:8;wait:40;down:8;wait:40;a:8;wait:60;a:8')


def taps(n, gap=50):
    return ';'.join([f'a:8;wait:{gap}'] * n)


def talk(face, n=8):
    """그 쪽을 보고 명령 창 → 「이야기하기」, 그 뒤 A 로 대사를 넘긴다. 남은 A 가 연 명령 창은 B 로 닫는다."""
    return f'{face}:8;wait:30;a:8;wait:60;a:8;wait:60;{taps(n)};{pc.CLOSE}'


# (이름, 방법, 인자, 선택). 방법 warp 는 TO(맵,x,y), walk 는 웨이포인트(walk.lua).
# 선택: poke(매 프레임 묶음), boss(보스 패치), maxf, changes(맵이 바뀔 횟수, 그 뒤 after 프레임에 끝), after,
# want·off(끝에 켜져·꺼져 있을 깃발), map(끝 맵), field(끝에 필드인지), items(가진 물건)
SEGMENTS = [
    # 저녁 대사를 넘기는 A 가 왕좌의 방 연출(장 제목·서술·왕의 연설)까지 넘긴다
    ('prologue', 'walk', ';'.join(w for _, w in pc.ROUTE),
     {'maxf': 20000, 'changes': len(pc.MAPS), 'after': 2500, 'want': ['CHAPTER1'], 'map': '36/01'}),
    ('throne_out', 'walk', '32,70;down:60', {'changes': 1, 'map': '36/00'}),
    ('imuru_night', 'warp', '37/00,4,30', {'poke': NIGHT + ';' + HOLD_CHILD, 'map': '37/00'}),
    ('night_child', 'walk', talk('up') + ';6,31', {'poke': NIGHT + ';' + HOLD_CHILD, 'want': ['NIGHT_TOLD']}),
    ('castle_day', 'warp', '36/00,16,72', {'poke': DAY, 'map': '36/00'}),
    ('flare', 'walk', talk('up'), {'poke': DAY, 'want': ['FLARE']}),
    ('jail', 'warp', '37/02,12,6', {'map': '37/02'}),
    ('reunion', 'walk', 'wait:300;' + taps(30, 60) + ';' + pc.CLOSE, {'want': ['REUNITED']}),
    ('well', 'warp', '3B/00,46,5', {'map': '3B/00'}),
    ('hoimin_side', 'warp', '3B/03,6,28', {'map': '3B/03'}),
    ('hoimin', 'walk', talk('left', 12) + ';wait:300;' + taps(4) + ';' + pc.CLOSE, {'want': ['HOIMIN']}),
    # 같은 맵 안의 순간이동은 dq5warp.lua 가 도착을 알아보지 못해 이웃 맵을 거친다
    ('well_hole', 'warp', '3B/02,10,15', {'map': '3B/02'}),
    ('shoes_chest', 'warp', '3B/03,14,14', {'map': '3B/03'}),
    ('shoes', 'walk', 'up:8;wait:30;' + SEARCH + ';' + taps(4) + ';' + pc.CLOSE, {'items': [SHOES]}),
    ('castle_town', 'warp', '36/00,16,72', {'map': '36/00'}),
    ('field', 'walk', '16,71;28,71;28,81;down:120', {'field': True}),
    ('fly', 'walk', USE_SHOES + ';wait:600;' + taps(4), {'changes': 1, 'after': 300, 'map': '39/00'}),
    ('kidnap', 'walk', '18,19;' + taps(6) + ';' + pc.CLOSE, {'want': ['KIDNAPPED']}),
    ('tower_top', 'warp', '39/04,46,40', {'map': '39/04'}),
    # 잡힌 아이가 (46,35)까지 걸어와 그 줄을 막으므로 한 칸 옆 열로 오른다
    ('boss', 'walk', '44,41;44,37;' + taps(4) + ';' + pc.CLOSE + ';44,25;46,25;46,23;' + talk('up', 4) + ';' +
     taps(110, 40) + ';wait:600;' + taps(10) + ';' + pc.CLOSE,
     {'boss': True, 'poke': HERO_HP, 'want': ['BOSS_WON', 'KIDS_FOLLOW']}),
    ('tower_soldier', 'warp', '39/01,36,50', {'map': '39/01'}),
    ('soldier', 'walk', talk('up', 6) + ';wait:300', {'want': ['SOLDIER']}),
    ('imuru', 'warp', '37/00,28,49', {'poke': DAY, 'map': '37/00'}),
    ('homecoming', 'walk', '28,45;' + taps(6) + ';' + pc.CLOSE, {'poke': DAY, 'off': ['KIDS_FOLLOW']}),
    ('castle', 'warp', '36/01,30,66', {'map': '36/01'}),
    # 병사가 갈라서고 왕 앞까지 저절로 걸어가 칭찬·선물·레벨업 줄·작별 뒤 성 앞에 들어선다
    ('king', 'walk', '30,51;' + taps(120, 60), {'changes': 1, 'after': 60, 'map': '36/00',
                                                 'want': ['REPORTED'], 'off': ['CHAPTER2', 'OPENING']}),
    # 끝맺음 서술 둘을 넘기고 끝 상자에서 누르면 리셋된다
    ('ending', 'ending', None, {}),
]
# --chapter2 롬: 성 앞에서 1장 끝 서술 → 2장 왕좌의 방
CHAPTER2_END = [
    ('king', 'walk', '30,51;' + taps(120, 60), {'changes': 2, 'after': 150, 'map': '3D/01',
                                                 'want': ['REPORTED', 'CHAPTER2', 'OPENING']}),
]
MSG = DQ5_TOOLS / 'lua' / 'dq5msg.lua'
ENDING_PRE = ','.join(['wait:52', 'a:8'] * 14) + ',wait:900'
RESET = 0x008639
DRIVER_UPLOAD = box.DRIVER_UPLOAD
DRIVER_HELLO = 0x24FDF9          # 24:FD6E 가 드라이버를 올린 뒤 부르는 인사(Chun → SOFT)
AFTER_SOUND = 0x008680           # 리셋 루틴에서 24:FD6E(소리 켜기)를 부른 JSL(00:867C) 다음


def frames(waypoints):
    """웨이포인트를 다 걷고 남을 만큼의 프레임: 누르기·쉬기는 그 수, 좌표 하나는 400."""
    total = 300
    for tok in waypoints.split(';'):
        found = re.fullmatch(r'\w+:(\d+)', tok)
        total += int(found[1]) if found else 400
    return total


def run(mesence, rom, script, dest, env, timeout):
    dest.mkdir(parents=True, exist_ok=True)
    full = {k: v for k, v in os.environ.items()
            if k not in ('ADULT', 'ANYWHERE', 'BATTLE', 'FIELD', 'GROUP', 'LATESET', 'PARTY', 'POKE', 'ROMPATCH',
                         'SAVE', 'SET', 'WAGON', 'TEST', 'TO', 'PRE', 'WAYPOINTS', 'WATCH', 'CHANGES', 'AFTER')}
    full.update(env, SHOT_DIR=str(dest))
    with (dest / 'mesen.log').open('w', encoding='utf-8') as log:
        try:
            mesen.run(mesence, rom, script, cwd=dest, env=full, stdout=log, stderr=subprocess.STDOUT,
                      timeout=timeout, check=False)
        except subprocess.TimeoutExpired:
            pass


ITEMS = 0x7E2056     # 일행 레코드 0 의 물건 12칸(+16~+21)


def watch_flags():
    return ';'.join(f'{k}=7E{a & 0xFFFF:04X}:1' for k, (a, _) in FLAGS.items()) + f';ITEMS0={ITEMS:X}:6;ITEMS1={ITEMS + 6:X}:6;BE=7E00BE:1'


def ending(mesence, rom, state, dest):
    """끝 상자에서 버튼을 눌러 리셋한 뒤의 호출 차례를 본다."""
    import dq4chapter1
    scenes = dq4chapter1.scenes(True)
    end_box = box.entry_points(scenes)['end']
    acked = box.boot_points(scenes)['acked']
    calls = [end_box, RESET, acked, DRIVER_UPLOAD, DRIVER_HELLO, AFTER_SOUND]
    run(mesence, rom, MSG, dest, {'STATE': str(state), 'PRE': ENDING_PRE, 'MAXF': '2400',
                                  'CALLS': ','.join(f'{a:06X}' for a in calls)}, 200)
    text = (dest / 'msg.txt').read_text(encoding='utf-8') if (dest / 'msg.txt').exists() else ''
    seen = [(int(f), int(pc, 16)) for f, pc in re.findall(r'^(\d+) (\w{6}) ', text, re.M)]
    def first(addr, after=0):
        return next((f for f, pc in seen if pc == addr and f >= after), None)
    problems = []
    shown = first(end_box)
    reset = first(RESET, shown or 0) if shown is not None else None
    if shown is None:
        problems.append('끝 상자가 불리지 않음')
    elif reset is None:
        problems.append('끝 상자 뒤 리셋되지 않음')
    else:
        if first(acked, reset) is None:
            problems.append('드라이버가 다시 시작 명령을 받지 않음')
        if first(DRIVER_UPLOAD, reset) is not None:
            problems.append('리셋 뒤 드라이버를 IPL 로 다시 올리려 함')
        if first(DRIVER_HELLO, reset) is None or first(AFTER_SOUND, reset) is None:
            problems.append('리셋 루틴이 소리 켜기에서 이어지지 않음')
    return {'name': 'ending', 'status': 'failed' if problems else 'passed', 'problems': problems,
            'frames': {'box': shown, 'reset': reset, 'after_sound': first(AFTER_SOUND, reset or 0) if reset else None}}


def segment(mesence, rom, state, dest, seg, patch):
    name, how, arg, opt = seg
    if how == 'ending':
        return ending(mesence, rom, state, dest)
    poke = opt.get('poke', '')
    if how == 'warp':
        run(mesence, rom, WARP, dest, {'STATE': str(state), 'TO': arg, 'SAVE': 'end.mss', 'SETTLE': '120',
                                       'MAXF': '1500', 'WARPEXIT': f'{warp_exit(rom):X}', 'ANYWHERE': '1',
                                       'ROMPATCH': patch, **({'POKE': poke} if poke else {})}, 300)
        text = (dest / 'warp.txt').read_text(encoding='utf-8') if (dest / 'warp.txt').exists() else ''
        found = re.search(r'arrived map (\w\w/\w\w)', text)
        maps = [found[1]] if found else []
        wram = (dest / 'final.wram').read_bytes() if (dest / 'final.wram').exists() else bytes(0x20000)
        seen = {k: wram[a & 0xFFFF] for k, (a, _) in FLAGS.items()}
        items = list(wram[ITEMS & 0xFFFF:(ITEMS & 0xFFFF) + 12])
        messages = []
    else:
        maxf = opt.get('maxf', frames(arg))
        # PRE: 앞 구간이 끝날 때 남은 A 가 연 명령 창을 닫는다. 창이 없을 때의 B 는 아무것도 열지 않는다
        run(mesence, rom, WALK_STATE, dest, {'STATE': str(state), 'WALK': str(WALK), 'WAYPOINTS': arg,
                                             'PRE': pc.CLOSE.replace(';', ','),
                                             'SAVE': 'end.mss', 'MAXF': str(maxf),
                                             'CHANGES': str(opt.get('changes', 99)), 'AFTER': str(opt.get('after', 120)),
                                             'WATCH': watch_flags(), 'ROMPATCH': patch,
                                             **({'POKE': poke} if poke else {})}, maxf // 40 + 120)
        text = (dest / 'walk.txt').read_text(encoding='utf-8') if (dest / 'walk.txt').exists() else ''
        maps = re.findall(r'map \w\w/\w\w -> (\w\w/\w\w)', text)
        seen = {k: int(v, 16) for k, v in re.findall(r'^(\w+)=([0-9A-F]+)$', text, re.M)}
        # walk.lua 는 여러 바이트를 높은 주소부터 찍는다
        items = [b for k in ('ITEMS0', 'ITEMS1') for b in seen.get(k, 0).to_bytes(6, 'little')]
        found = re.search(r'^messages (.*)$', text, re.M)
        messages = [v.split('@')[0] for v in found[1].split(',') if v] if found else []
        end = re.search(r'end map (\w\w/\w\w)', text)
        if end:
            maps = maps or [end[1]]
    flags = {k: bool(seen.get(k, 0) & m) for k, (_, m) in FLAGS.items()}
    end_map = maps[-1] if maps else None
    problems = []
    if not (dest / 'end.mss').exists():
        problems.append('세이브스테이트 없음')
    if 'map' in opt and end_map != opt['map']:
        problems.append(f'끝 맵 {end_map}, 기대 {opt["map"]}')
    for k in opt.get('want', []):
        if not flags[k]:
            problems.append(f'깃발 {k} 꺼짐')
    for k in opt.get('off', []):
        if flags[k]:
            problems.append(f'깃발 {k} 켜짐')
    if 'field' in opt and bool(seen.get('BE', 0x80) & 0x80) == opt['field']:
        problems.append('필드가 아님' if opt['field'] else '필드에 있음')
    for want in opt.get('items', []):
        if want not in items:
            problems.append(f'물건 {want:02X} 없음')
    return {'name': name, 'status': 'failed' if problems else 'passed', 'problems': problems, 'maps': maps,
            'messages': messages, 'flags': [k for k, v in flags.items() if v],
            'items': ' '.join(f'{v:02X}' for v in items)}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--rom', required=True, type=Path)
    ap.add_argument('--out', required=True, type=Path)
    ap.add_argument('--from', dest='start', help='이 구간부터(앞 구간의 end.mss 는 --states 에서)')
    ap.add_argument('--until', help='이 구간까지만')
    ap.add_argument('--states', type=Path, help='앞서 걸은 출력 폴더')
    ap.add_argument('--chapter2', action='store_true', help='1장 끝에서 2장으로 넘어가는 롬(dq4build.py --chapter2)')
    args = ap.parse_args()
    segments = SEGMENTS[:-2] + CHAPTER2_END if args.chapter2 else SEGMENTS
    mesence = Path(os.environ['MESENCE'])
    out = args.out.resolve()
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f'{out} is not empty')
    out.mkdir(parents=True, exist_ok=True)
    rom = out / 'c.sfc'
    shutil.copyfile(args.rom.resolve(), rom)
    data = rom.read_bytes()
    patch = NO_ENCOUNTERS
    names = [s[0] for s in segments]
    first = names.index(args.start) if args.start else 0
    if first:
        state = (args.states or out).resolve() / names[first - 1] / 'end.mss'
    else:
        seq = ','.join(f'y@{f}:2' for f in range(900, 1600, 150))
        pc.run(mesence, rom, pc.MKSTATE, out / 'start',
               {'SAVEAT': str(pc.START_AT), 'STATE': 'start.mss', 'MAXF': str(pc.START_AT + 10), 'EVERY': '0',
                'PERIOD': '40', 'TAP': 'a', 'TAPUNTIL': str(pc.TAP_UNTIL), 'SEQ': seq}, 200)
        state = out / 'start' / 'start.mss'
        if not state.exists():
            raise SystemExit('세이브스테이트를 만들지 못함')
    results = []
    last = names.index(args.until) if args.until else len(segments) - 1
    for seg in segments[first:last + 1]:
        boss = seg[3].get('boss')
        r = segment(mesence, rom, state, out / seg[0], seg,
                    patch + (';' + boss_patch(data) if boss else ''))
        results.append(r)
        print(json.dumps(r, ensure_ascii=False), flush=True)
        if r['status'] != 'passed':
            break
        state = out / seg[0] / 'end.mss'
    ok = len(results) == last + 1 - first and all(r['status'] == 'passed' for r in results)
    report = {'status': 'passed' if ok else 'failed', 'segments': results}
    (out / 'results.json').write_text(json.dumps(report, ensure_ascii=False, indent=1) + '\n')
    print(json.dumps({'status': report['status']}, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
