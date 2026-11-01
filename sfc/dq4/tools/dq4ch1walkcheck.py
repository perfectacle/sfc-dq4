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

구간마다 시작할 때 난수 상태(7E:075B~075D)와 시각(7E:075E·075F)을 한 번 정한 값으로 둔다. 앞 구간이 남긴 난수·시각이
롬의 상관없는 바이트 때문에 달라져도 구간 결과가 운에 기대지 않게 하려는 것이다.

  MESENCE=… LIBDIR=… python sfc/dq4/tools/dq4ch1walkcheck.py --rom work/ch1/dq4-ch1.sfc --out work/ch1walk [--chapter2]
  (--from 구간 --states 앞 출력 폴더 로 그 구간부터 다시 걷는다)
  --units --jobs 6: 서장만 이어 걷고, 나머지는 순간이동으로 나눈 묶음(units)마다 서장 끝 세이브스테이트에서 따로
  시작한다. 묶음 앞 구간들이 켰을 깃발·호이민·물건을 SET·PARTY 로 직접 두므로 묶음끼리 기다리지 않고 함께 돈다.
  --base 는 서장 끝 세이브스테이트를 주어 서장을 건너뛴다(같은 롬으로 만든 것만), --only 는 그 묶음만 돈다.
형식은 sfc/dq4/docs/dq4-chapter1-format.md 「검증」.
"""
import argparse
import concurrent.futures
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
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
# 구간 시작에 한 번 두는 값(SET 꼴, 7E 뱅크 하위 16비트). 난수 00:9878 은 075B·075C 를 밀고 섞은 뒤 075D 를 하나 올려
# 075B + 075D 를 낸다. NMI(00:8897)가 075B 를 프레임마다 하나 올리므로 세 바이트를 모두 둔다
RNG = '075B=00;075C=00;075D=00'
DAY_SET = '075E=50;075F=00'
NIGHT_SET = '075E=F0;075F=00'
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


# 묶음(units)으로 나눠 걸을 때, 이름 붙은 깃발 말고 앞 구간이 기록(7E:2000~2A9F)에 남기는 것.
# 호이민 합류: dq5warp.lua PARTY 의 동료 기록에 손님 bit6(dq4ch1event.GUEST)과 쓴 이름 비트(7E:29EA + 종류)를 더한다.
# 우물 상자: 주인공 셋째 칸 7E:2058 의 そらとぶくつ 와 연 상자 비트 7E:2223 bit3.
# 보스 전투의 경험치·레벨은 옮기지 않는다(왕 구간은 레벨업 줄이 늘어도 맵이 바뀔 때까지 A 를 누른다)
EFFECTS = {
    'hoimin': {'party': '05', 'set': '206A|40;29EF|01'},
    'shoes': {'set': '2058=CD;2223|08'},
}


# 서장 끝 세이브스테이트(왕좌의 방 36/01)와 같은 맵으로 순간이동하는 묶음이 먼저 들르는 곳
HOPS = {'36/01': '36/00,16,72'}


def pins(opt):
    """구간 시작에 두는 난수·시각. 밤을 묶는 구간은 밤, 나머지는 낮."""
    return f"{RNG};{NIGHT_SET if NIGHT in opt.get('poke', '') else DAY_SET}"


def units(segments):
    """구간 차례를 묶음으로 나눈다. 첫 구간(서장)은 홀로, 그 뒤는 순간이동 구간마다 새 묶음."""
    out = [[0]]
    for i in range(1, len(segments)):
        if segments[i][1] == 'warp' or len(out) == 1:
            out.append([i])
        else:
            out[-1].append(i)
    return out


def setup(segments, first):
    """first 번째 구간 앞까지 걸었다면 켜져 있을 깃발·물건(SET 문자열)과 동료(PARTY)."""
    on = set()
    sets, party = [], []
    for name, _, _, opt in segments[:first]:
        on |= set(opt.get('want', ()))
        on -= set(opt.get('off', ()))
        effect = EFFECTS.get(name, {})
        if 'set' in effect:
            sets.append(effect['set'])
        if 'party' in effect:
            party.append(effect['party'])
    flags = [f'{FLAGS[k][0] & 0xFFFF:04X}|{FLAGS[k][1]:02X}' for k in FLAGS if k in on]
    return ';'.join(flags + sets), ','.join(party)


def trace_text(name, text):
    """구간 기록에서 견줄 부분. dq5warp.lua 는 emu.stop 뒤 한 프레임이 더 돌면 끝 기록(end map·flags 두 줄)을
    한 번 더 붙이므로, warp.txt 는 첫 flags 줄까지만 본다."""
    if name != 'warp.txt':
        return text
    lines = text.splitlines(keepends=True)
    end = next((i for i, line in enumerate(lines) if line.startswith('flags ')), len(lines) - 1)
    return ''.join(lines[:end + 1])


def digest(path):
    """구간 기록(walk.txt·warp.txt·msg.txt)의 SHA-1 앞 12자리. 같은 입력이면 같아야 한다."""
    if not path.exists():
        return None
    return hashlib.sha1(trace_text(path.name, path.read_text(encoding='utf-8')).encode()).hexdigest()[:12]


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
    # 병사가 갈라서고 왕 앞까지 저절로 걸어가 칭찬·선물·레벨업 줄·작별 뒤 성 앞에 들어선다.
    # 레벨업 줄 수는 보스 전투로 오른 레벨에 따라 달라지므로 A 는 넉넉히 두고 맵이 바뀌면 끝낸다
    ('king', 'walk', '30,51;' + taps(200, 60), {'changes': 1, 'after': 60, 'map': '36/00',
                                                 'want': ['REPORTED'], 'off': ['CHAPTER2', 'OPENING']}),
    # 끝맺음 서술 둘을 넘기고 끝 상자에서 누르면 리셋된다
    ('ending', 'ending', None, {}),
]
# --chapter2 롬: 성 앞에서 1장 끝 서술 → 2장 왕좌의 방
CHAPTER2_END = [
    ('king', 'walk', '30,51;' + taps(200, 60), {'changes': 2, 'after': 150, 'map': '3D/01',
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
    run(mesence, rom, MSG, dest, {'STATE': str(state), 'PRE': ENDING_PRE, 'MAXF': '2400', 'SET': RNG,
                                  'CALLS': ','.join(f'{a:06X}' for a in calls)}, 200)
    text = (dest / 'msg.txt').read_text(encoding='utf-8') if (dest / 'msg.txt').exists() else ''
    # 견주는 것은 지난 PC 와 그 프레임뿐이다. 리셋 뒤 X 는 소리 CPU 가 포트에 둔 값이라 앞서 걸은 길에 따라 다르다
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
            'trace': hashlib.sha1(repr(seen).encode()).hexdigest()[:12], 'frames': {'box': shown, 'reset': reset, 'after_sound': first(AFTER_SOUND, reset or 0) if reset else None}}


def segment(mesence, rom, state, dest, seg, patch, extra='', party=''):
    """한 구간을 걷는다. extra 는 시작에 더 둘 SET(묶음 첫 구간의 깃발·물건), party 는 dq5warp.lua PARTY."""
    name, how, arg, opt = seg
    if how == 'ending':
        return ending(mesence, rom, state, dest)
    poke = opt.get('poke', '')
    start = ';'.join(v for v in (pins(opt), extra) if v)
    if how == 'warp':
        # 도착해 조작이 풀린 첫 프레임에 난수를 다시 둔다. 어디서 떠났느냐에 따라 도착 프레임까지 굴린 수가 다르다
        run(mesence, rom, WARP, dest, {'STATE': str(state), 'TO': arg, 'SAVE': 'end.mss', 'SETTLE': '120',
                                       'MAXF': '1500', 'WARPEXIT': f'{warp_exit(rom):X}', 'ANYWHERE': '1',
                                       'ROMPATCH': patch, 'SET': start, 'LATESET': pins(opt),
                                       **({'POKE': poke} if poke else {}), **({'PARTY': party} if party else {})}, 300)
        log = dest / 'warp.txt'
        text = log.read_text(encoding='utf-8') if log.exists() else ''
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
                                             'WATCH': watch_flags(), 'ROMPATCH': patch, 'SET': start,
                                             **({'POKE': poke} if poke else {})}, maxf // 40 + 120)
        log = dest / 'walk.txt'
        text = log.read_text(encoding='utf-8') if log.exists() else ''
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
            'trace': digest(log), 'messages': messages, 'flags': [k for k, v in flags.items() if v],
            'items': ' '.join(f'{v:02X}' for v in items)}


def prologue_start(mesence, rom, out):
    """전원부터 새 게임 첫 장면까지 걸어 서장 시작 세이브스테이트를 만든다."""
    seq = ','.join(f'y@{f}:2' for f in range(900, 1600, 150))
    pc.run(mesence, rom, pc.MKSTATE, out / 'start',
           {'SAVEAT': str(pc.START_AT), 'STATE': 'start.mss', 'MAXF': str(pc.START_AT + 10), 'EVERY': '0',
            'PERIOD': '40', 'TAP': 'a', 'TAPUNTIL': str(pc.TAP_UNTIL), 'SEQ': seq}, 200)
    state = out / 'start' / 'start.mss'
    if not state.exists():
        raise SystemExit('세이브스테이트를 만들지 못함')
    return state


def walk_unit(mesence, rom, data, out, segments, unit, base):
    """한 묶음을 base 에서 시작해 차례로 걷는다. 첫 구간에 앞 구간들의 깃발·물건·동료를 둔다."""
    extra, party = setup(segments, unit[0])
    state, results = base, []
    name, how, arg, _ = segments[unit[0]]
    if how == 'warp' and arg.split(',')[0] == segments[0][3]['map']:
        # dq5warp.lua 는 같은 맵 안의 순간이동이면 목적지 칸에 꼭 맞게 서야 도착으로 본다. 이웃 맵을 거친다
        hop = HOPS[arg.split(',')[0]]
        r = segment(mesence, rom, state, out / f'{name}-hop', (f'{name}-hop', 'warp', hop, {'map': hop[:5]}),
                    NO_ENCOUNTERS, extra, party)
        if r['status'] != 'passed':
            return [r]
        state, extra, party = out / f'{name}-hop' / 'end.mss', '', ''
    for k, i in enumerate(unit):
        seg = segments[i]
        patch = NO_ENCOUNTERS + (';' + boss_patch(data) if seg[3].get('boss') else '')
        r = segment(mesence, rom, state, out / seg[0], seg, patch, *((extra, party) if k == 0 else ()))
        results.append(r)
        if r['status'] != 'passed':
            break
        state = out / seg[0] / 'end.mss'
    return results


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--rom', required=True, type=Path)
    ap.add_argument('--out', required=True, type=Path)
    ap.add_argument('--from', dest='start', help='이 구간부터(앞 구간의 end.mss 는 --states 에서)')
    ap.add_argument('--until', help='이 구간까지만')
    ap.add_argument('--states', type=Path, help='앞서 걸은 출력 폴더')
    ap.add_argument('--chapter2', action='store_true', help='1장 끝에서 2장으로 넘어가는 롬(dq4build.py --chapter2)')
    ap.add_argument('--units', action='store_true', help='서장 뒤를 묶음마다 따로(함께) 걷는다')
    ap.add_argument('--jobs', type=int, default=6, help='--units 에서 함께 띄울 MesenCE 수')
    ap.add_argument('--base', type=Path, help='--units: 서장 끝 세이브스테이트(같은 롬으로 만든 것). 주면 서장을 건너뜀')
    ap.add_argument('--only', help='--units: 이 구간으로 시작하는 묶음만(쉼표로 여럿)')
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
    began = time.monotonic()
    names = [s[0] for s in segments]
    if args.units:
        groups = units(segments)
        if args.only:
            wanted = args.only.split(',')
            groups = [u for u in groups if names[u[0]] in wanted]
        results = []
        if args.base:
            base = args.base.resolve()
            groups = [u for u in groups if u[0] != 0]
        else:
            base = out / names[0] / 'end.mss'
            if groups and groups[0][0] == 0:
                results += walk_unit(mesence, rom, data, out, segments, groups.pop(0), prologue_start(mesence, rom, out))
                print(json.dumps(results[-1], ensure_ascii=False), flush=True)
        if all(r['status'] == 'passed' for r in results):
            with concurrent.futures.ThreadPoolExecutor(args.jobs) as pool:
                jobs = [pool.submit(walk_unit, mesence, rom, data, out, segments, u, base) for u in groups]
                for job in concurrent.futures.as_completed(jobs):
                    for r in job.result():
                        print(json.dumps(r, ensure_ascii=False), flush=True)
            for job in jobs:
                results += job.result()
        expected = sum(len(u) for u in groups) + (0 if args.base or args.only else 1)
        ok = len(results) == expected and all(r['status'] == 'passed' for r in results)
    else:
        first = names.index(args.start) if args.start else 0
        if first:
            state = (args.states or out).resolve() / names[first - 1] / 'end.mss'
        else:
            state = prologue_start(mesence, rom, out)
        results = []
        last = names.index(args.until) if args.until else len(segments) - 1
        for seg in segments[first:last + 1]:
            boss = seg[3].get('boss')
            r = segment(mesence, rom, state, out / seg[0], seg,
                        NO_ENCOUNTERS + (';' + boss_patch(data) if boss else ''))
            results.append(r)
            print(json.dumps(r, ensure_ascii=False), flush=True)
            if r['status'] != 'passed':
                break
            state = out / seg[0] / 'end.mss'
        ok = len(results) == last + 1 - first and all(r['status'] == 'passed' for r in results)
    report = {'status': 'passed' if ok else 'failed', 'mode': 'units' if args.units else 'chain',
              'seconds': round(time.monotonic() - began), 'segments': results}
    (out / 'results.json').write_text(json.dumps(report, ensure_ascii=False, indent=1) + '\n')
    print(json.dumps({'status': report['status'], 'seconds': report['seconds']}, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
