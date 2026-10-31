"""전투 메시지 창(18·25) 자리·크기 쓰기를 MesenCE 전투에서 VRAM BG3 타일맵과 화면으로 확인한다.

dq5windowwrite.py 로 고친 롬과 원래 롬을 같은 입력으로 돌린다. 경우는 여섯이다. left·right 는 두 창의 X 만 0·4 로,
wide 는 (0,21) 31 × 7(글자 29칸), h9 는 (2,19) 28 × 9, tall 은 (2,17) 28 × 11(글자 5줄), both 는 (1,15) 31 × 13(29칸 6줄)이다. 모양을 바꾸는
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
- event·party·papasNN·monNN·fxNN: 이벤트 전투(무리 1E ジャミ), 동료 ホイミン·マーリン 과 ラリホー 슬라임, 손님 파파스(무리 01
  둘째 판)가 주문 NN(PAPAS_SPELLS)만 거는 전투, 같은 전투에서 슬라임이 몬스터용 주문 NN(MONSTER_SPELLS)만 거는 전투, 파파스의
  メラ 를 연출 NN(EFFECT_SWAPS)으로 바꾼 전투. papasNN·monNN·fxNN 은 난수를 고정하고(FIXED_RNG), 모든 롬에서
  그 연출 NN 이 돌았는지 본다(NO_EFFECT 는 파파스가 그 주문을 건 것). 모양을 바꾼 롬은 위 (1)~(3)에 더해 00:FDA1
  전송 크기(효과 층 1CE0 만 (Y - 7) × 64), 스크린샷의 창 테두리·창 안 다른 색 점(모든 롬에서 0 이어야 함), 원래 롬의 효과 층
  줄·OBJ 상자 아래 끝, 연출 시작을 맞춘 창 위 화면(effect_above, 세기만 함)을 적는다. --hlog 는 원래 롬 실행에서 연출마다
  줄마다 쓰는 PPU 레지스터와 원래 창 맨 위 줄에 닿는 168줄부터의 줄:값을 모은다. --shot-every 로 스크린샷 간격을 줄인다.
원래 롬과 선실 상태는 읽기만 하며 롬·기록은 --out 의 새 폴더에 쓴다.
  MESENCE=… python sfc/dq5/tools/dq5msgwindowcheck.py rom/dq5.sfc --state work/state/ship.mss
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

from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from dq5windowwrite import GRID, GRID_SIZE  # noqa: E402

LEFT, TOP = 2, 21
WIDTH, HEIGHT = 28, 7
CORNERS = (0x8B, 0x8C)
BORDER_SIDE, BORDER_BOTTOM = 0x8E, 0x97
CASES = {'left': {'x': 0}, 'right': {'x': 4}, 'wide': {'x': 0, 'w': 31}, 'h9': {'h': 9}, 'tall': {'h': 11},
         'both': {'x': 1, 'w': 31, 'h': 13}}
# 손님 파파스의 행동 여섯 칸(파일 오프셋 11958D)에 넣는 주문. 연출(22:D73C)이 BG3·HDMA·색 더하기를 쓰는 것과 쓰지 않는
# 보조·회복 주문을 고루 둔다. ミナデイン·スカラ 는 이 장면에서 파파스가 걸지 않아 뺐다(fxNN 으로 띄움).
# 8비트 난수(00:9878)를 늘 80 으로(파일 1878). 연출 그림(マヒャド 얼음 기둥 자리 등)은 난수와 CPU 시간에 따라 갈려,
# 고친 롬과 원래 롬의 연출을 프레임째 견주려면 난수를 고정해야 한다.
FIXED_RNG = '1878=08E220A98028;187E=60'
PAPAS_SPELLS = ('01', '03', '04', '06', '09', '0B', '0C', '0D', '0F', '10', '11', '1F', '22', '2A')
# 몬스터용 주문(39~65) 가운데 party 장면이 거는 ラリホー(4B)를 뺀 것. 같은 장면의 슬라임이 그 주문만 걸게 MP(118004)를
# 255 로 두고 행동 평가 조건(118008 bit0-1)을 끄며, 파파스는 회복(2A)만 걸어 일행이 버티게 한다.
MONSTER_SPELLS = tuple(f'{n:02X}' for n in range(0x39, 0x66) if n != 0x4B)
# 연출(22:D73C)을 띄우지 않는 파파스 주문. 원래 롬에서 「となえた」(070)는 나오나 FXID 줄이 없어, 파파스가 그 주문을
# 건 것만 본다. 070 의 인자 대기열은 $F5 = 행동자(bit7 이면 몬스터 무리, 아니면 일행 칸), $F6 = 주문 번호다. 일행 칸은
# 전투마다 바뀌어(주인공이 쓰러지면 파파스가 00) 이름을 찍은 글자(24:A4A4, 「パパス」)로 행동자를 가린다.
NO_EFFECT = ('22', '2A')
CAST = '070'
PAPAS_GLYPHS = ('83', '5B', '83', '5B', '4E')
# 파파스가 걸지 않는 ミナデイン(12)·スカラ(21)은 파파스의 メラ(01) 연출 번호(우리 편 표 26:8BE0, 파일 130BE1)를 바꿔 띄운다.
EFFECT_SWAPS = ('12', '21')
TAPS = ','.join(['wait:400'] + ['a:8,wait:24'] * 110)
SCENES = {
    'one': {'BATTLE': '00:1', 'SWAP': '05E:006,118,191;069:006', 'ROMPATCH': '10462C=9E', 'SET': '2035=07', 'MAXF': '3400'},
    'four': {'BATTLE': '00:1,01:1,02:1,03:1', 'SET': '2035=07', 'MAXF': '3400'},
    'field': {'BATTLE': '00:1', 'MAXF': '3000', 'FIELDSNAP': '40'},
    'event': {'GROUP': '1E', 'SET': '2035=07', 'MAXF': '3400'},
    'party': {'BATTLE': '00:3', 'PARTY': '05,04', 'SET': '2035=07;2073=63;209D=63;208E=FF;20B8=FF;2034=00;2042=02',
              'ROMPATCH': '118003=C8;118004=63;118011=4B4B4B4B4B4B', 'MAXF': '3400'},
    **{f'papas{a}': {'GROUP': '01', 'SET': '2035=07;101A=01', 'ROMPATCH': f'118003=C8;11958D={a * 6};{FIXED_RNG}',
                     'MAXF': '3400'}
       for a in PAPAS_SPELLS},
    **{f'mon{a}': {'GROUP': '01', 'SET': '2035=07;101A=01',
                   'ROMPATCH': f'118003=C8;118004=FF;118008=00;118011={a * 6};11958D={"2A" * 6};{FIXED_RNG}', 'MAXF': '3400'}
       for a in MONSTER_SPELLS},
    **{f'fx{a}': {'GROUP': '01', 'SET': '2035=07;101A=01', 'ROMPATCH': f'118003=C8;11958D={"01" * 6};130BE1={a};{FIXED_RNG}',
                  'MAXF': '3400'}
       for a in EFFECT_SWAPS},
}
# 견주는 구간에서 지나야 하는 곳: 메시지·FD ▼·줄 올리기·셋째 줄 끝 ▼·효과 층 전송, 무리 넷이면 넷째 줄 끝 ▼.
# 모양을 바꾼 롬은 줄이 늘어 줄 올리기·▼ 때가 달라, 지나야 하는 곳만 따로 둔다.
# 새 장면(이벤트·동료·주문)은 메시지와 글자만 지나면 된다. 주문 효과는 FX 기록으로 따로 센다.
COVER = {'one': {'248C39', '24880A', '24A569', '24A519', 'EFF'}, 'four': {'248C39', '24A519', '24A523'}}
SHAPED_COVER = {'one': {'248C39', '24A4A4', '24A569', 'EFF'}, 'four': {'248C39', '24A519', '24A523'}}
for _scene in SCENES:
    COVER.setdefault(_scene, {'248C39'})
    SHAPED_COVER.setdefault(_scene, {'248C39', '24A4A4'})
EFFECT_TOP, EFFECT_DEST = 7, 0x1CE0
COVER_TOPS = (21, 19, 17, 15)
# OBSEL 위 3비트 → (작은 OBJ, 큰 OBJ) 점 수
OBJ_SIZES = {0: (8, 16), 1: (8, 32), 2: (8, 64), 3: (16, 32), 4: (16, 64), 5: (32, 64), 6: (16, 32), 7: (16, 32)}
SHOT_SHIFT = 7
WINDOW_GRAY, WINDOW_WHITE = (49, 49, 41), (247, 247, 239)
# 원래 장면(one·four)은 메시지 열이 앞에서부터 같아야 한다.
PREFIX_SCENES = ('one', 'four')
NUMBER_MISS = 3
OLD_GRID, FIELD_VARS = '1DD5-1E70', (0x1E71, 0x1EFF)
NEW_GRID = f'{GRID & 0xFFFF:04X}-{(GRID & 0xFFFF) + GRID_SIZE - 1:04X}'
ACC = f'{OLD_GRID},{FIELD_VARS[0]:04X}-{FIELD_VARS[1]:04X},{NEW_GRID}'
FROM, STEP, SHOTEVERY = 560, 1, 16
LAG = 8
RETRIES = 3
# 원래 창 위 테두리(스크린샷 y = TOP × 8 - SHOT_SHIFT = 161)에 닿는 HDMA 쓰기 줄. HDMA 로 줄 S 에 쓴 값은 다음 줄부터
# 보여 스크린샷 y = S - 7 부터 적용된다(マヒャド 의 $2132 쓰기 줄과 매 프레임 스크린샷으로 잼).
HLOG_TAIL = TOP * 8 - SHOT_SHIFT + 7


def require(condition, message):
    if not condition:
        raise ValueError(message)


def same_until(calls, moved):
    """두 롬의 실행 기록이 처음 갈리는 프레임. 같은 입력이라도 몇 턴 뒤 갈릴 수 있어 그 앞까지만 견준다.
    한쪽 기록이 먼저 끝나면 긴 기록에만 있는 첫 줄의 프레임에서 갈린 것으로 본다."""
    calls, moved = [line for line in calls if line], [line for line in moved if line]
    for a, b in zip(calls, moved):
        if a != b:
            return min(int(a.split()[0]), int(b.split()[0]))
    if len(calls) != len(moved):
        short, long = sorted((calls, moved), key=len)
        return int(long[len(short)].split()[0])
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


def chunks(data, size=0x800):
    return [data[i:i + size] for i in range(0, len(data), size)]


def effect_log(calls):
    """실행 기록의 FX 줄 → [(프레임, VRAM 자리, 크기, 그림이 있는 첫 줄, 끝 줄, 그 앞 마지막 연출 번호)]. 줄은 그림이 없으면 None."""
    out, fxid = [], None
    for line in calls:
        parts = line.split()
        if len(parts) == 3 and parts[1] == 'FXID':
            fxid = parts[2]
        elif len(parts) >= 5 and parts[1] == 'FX':
            rows = (int(parts[4]), int(parts[5])) if parts[4] != '-' else (None, None)
            out.append((int(parts[0]), int(parts[2], 16), int(parts[3], 16), *rows, fxid))
    return out


def transfer_sizes(scene, name, y, calls):
    """00:FDA1 에 닿은 전송마다 크기가 그 롬에서 와야 할 값인지 본다. 창이 21줄보다 위면 BG3 효과 층(1CE0)만
    (Y - 7) × 64, 나머지 자리(BG1·BG2 전투 배경, 18E0 글자 자리)와 원래 높이는 0x380."""
    rows = effect_log(calls)
    want_effect = (y - EFFECT_TOP) * 64 if y < TOP else 0x380
    bad = [(f, d, n) for f, d, n, *_ in rows if n != (want_effect if d == EFFECT_DEST else 0x380)]
    require(not bad, f'{scene}/{name}: 전송 크기가 다름 {bad[:3]}')
    dests = {}
    for _, d, *_ in rows:
        dests[f'{d:04X}'] = dests.get(f'{d:04X}', 0) + 1
    return {'transfers': dests, 'effect_size': want_effect, 'fxid': sorted({r[5] for r in rows if r[5]})}


def obj_boxes(oam):
    """OAM 544바이트 + 크기 모드 1바이트 → 보이는 OBJ 의 (x, y, 크기). y 가 E0 이상인 OBJ 는 화면 밖으로 본다."""
    small, large = OBJ_SIZES[oam[0x220]]
    out = []
    for i in range(128):
        x, y = oam[i * 4], oam[i * 4 + 1]
        hi = oam[0x200 + i // 4] >> (i % 4 * 2) & 3
        x |= (hi & 1) << 8
        size = large if hi & 2 else small
        if y >= 0xE0 or 256 <= x < 512 - size:
            continue
        out.append((x - 512 if x >= 256 else x, y, size))
    return out


def hdma_ranges(calls, text):
    """HLOG 기록(hdma.txt) → {연출 번호: {레지스터: [첫 줄, 끝 줄, HLOGTAIL 줄부터 쓴 값]}}. 연출 시작(FXID)부터 그 뒤 둘째
    메시지까지를 그 연출의 구간으로 보고, 연출 밖 전투 프레임에서도 같은 범위로 쓰는 레지스터(전투 배경 BG1·BG2 세로
    스크롤 등)는 뺀다. 연출 밖 전투 프레임이 없는 장면(one·event)은 그런 레지스터도 남는다."""
    starts, messages = [], []
    for line in calls:
        parts = line.split()
        if len(parts) == 3 and parts[1] == 'FXID':
            starts.append((int(parts[0]), parts[2]))
        elif len(parts) == 3 and parts[1] == '248C39':
            messages.append(int(parts[0]))
    spans = []
    for frame, number in starts:
        later = [m for m in messages if m > frame]
        spans.append((frame, later[1] if len(later) > 1 else frame + 200, number))
    battle = min((m for m in messages), default=0)
    base, per, tails = {}, {}, {}
    for line in text.split('\n'):
        if not line:
            continue
        frame, reg, first, last, _, *rest = line.split()
        frame, first, last = int(frame), int(first), int(last)
        if frame < battle:
            continue
        owner = next((number for a, b, number in spans if a <= frame < b), None)
        table = base if owner is None else per.setdefault(owner, {})
        lo, hi = table.get(reg, (first, last))
        table[reg] = (min(lo, first), max(hi, last))
        if owner is not None and rest and rest[0] != '-':
            tails.setdefault((owner, reg), set()).update(rest[0].split(','))
    return {number: {reg: [*r, ','.join(sorted(tails.get((number, reg), ()))) or '-']
                     for reg, r in sorted(regs.items()) if base.get(reg) != r}
            for number, regs in sorted(per.items())}


def cast_log(calls):
    """실행 기록 → 「となえた」(CAST) 메시지마다 (행동자 $F5, 주문 번호 $F6, 찍힌 글자 목록)."""
    out, current = [], None
    for line in calls:
        parts = line.split()
        if len(parts) < 2:
            continue
        if parts[1] == '248C39':
            current = None
            if parts[2] == CAST:
                current = [None, None, []]
                out.append(current)
        elif parts[1] == 'ARG' and current and current[0] is None:
            current[0], current[1] = int(parts[2], 16), parts[3]
        elif len(parts) == 5 and parts[1] == '24A4A4' and current:
            current[2].append(parts[2])
    return [tuple(c) for c in out if c[0] is not None]


def spell_ran(scene, name, calls):
    """papasNN·monNN·fxNN 장면에서 그 주문의 연출(FXID NN)이 실제로 돌았는지 본다. 몬스터 행동 조건·MP 나 연출 번호
    표(130BE1)를 잘못 읽어 연출이 돌지 않으면 창이 깨진 장 0 이 거저 나오므로 막는다. 연출을 띄우지 않는 파파스
    주문(NO_EFFECT)은 파파스가 그 주문으로 「となえた」(CAST)를 냈는지 본다. 다른 장면은 None."""
    prefix = next((p for p in ('papas', 'mon', 'fx') if scene.startswith(p)), None)
    if prefix is None:
        return None
    number = scene[len(prefix):]
    if prefix == 'papas' and number in NO_EFFECT:
        log = cast_log(calls)
        casts = sum(spell == number and slot < 0x80 and glyphs[:len(PAPAS_GLYPHS)] == list(PAPAS_GLYPHS)
                    for slot, spell, glyphs in log)
        # 이름 글자가 바뀌어 못 맞춘 것인지 가릴 수 있게, 외친 070 마다 행동자·주문·첫 글자를 함께 찍는다.
        seen = [f'{slot:02X}/{spell}/{" ".join(glyphs[:len(PAPAS_GLYPHS)])}' for slot, spell, glyphs in log[:3]]
        require(casts, f'{scene}/{name}: 파파스가 주문 {number} 를 걸지 않음({CAST} {len(log)}번: {", ".join(seen) or "-"})')
        return {'casts': casts}
    runs = sum(line.split()[1:] == ['FXID', number] for line in calls if line)
    require(runs, f'{scene}/{name}: 연출 {number} 가 돌지 않음')
    return {'runs': runs}


def coverage(scene, seen):
    """원래 롬에서 창 18·25 의 맨 위 줄을 Y 로 올렸다면 무엇이 그 아래에 들어가는지 잰다. BG3 효과 층은 1CE0 전송마다
    그림이 있는 줄로 (아래쪽이 Y 줄 이상인 전송, 모두 Y 줄 이상인 전송), OBJ(몬스터)는 메시지 창이 떠 있는 덤프마다 OBJ
    상자 아래 끝이 Y 줄 위 점을 넘는 덤프 수와 가장 많이 넘은 점 수. OBJ 상자는 투명한 점을 포함한다."""
    dumps, _, calls, _, _, oams, hlog = seen[('original', scene)]
    effects = [r for r in effect_log(calls) if r[1] == EFFECT_DEST and r[3] is not None]
    out = {'effect_transfers': len(effects), 'effect_rows': sorted({(r[3], r[4]) for r in effects}),
           'effect_fxid': sorted({r[5] for r in effects if r[5]})}
    frames, bottoms = 0, []
    for k, (dump, oam) in enumerate(zip(dumps, oams)):
        if not (word(dump, LEFT, TOP) & 0xFF in CORNERS and word(dump, LEFT + WIDTH - 1, TOP) & 0xFF in CORNERS):
            continue
        frames += 1
        boxes = [b for b in obj_boxes(oam) if b[0] + b[2] > LEFT * 8 and b[0] < (LEFT + WIDTH) * 8]
        bottoms.append(max((b[1] + b[2] for b in boxes), default=0))
    if hlog:
        out['hdma'] = hdma_ranges(calls, hlog)
    out['window_dumps'] = frames
    out['obj_bottom'] = max(bottoms, default=0)
    for top in COVER_TOPS:
        out[f'y{top}'] = {'effect_part': sum(r[4] >= top for r in effects),
                          'effect_all': sum(r[3] >= top for r in effects),
                          'obj_dumps': sum(b > top * 8 for b in bottoms),
                          'obj_rows': max((b - top * 8 for b in bottoms), default=0)}
    return out


def complete(dump, x, y, w, h):
    """VRAM 에 창 테두리 양옆 세로줄이 위 모서리·세로 테두리·아래 모서리로 다 있는지. 창이 열리거나 닫히는 동안은 줄이 빈다."""
    for col in (x, x + w - 1):
        tiles = [word(dump, col, r) & 0xFF for r in range(y, y + h)]
        if tiles[0] not in CORNERS or tiles[-1] != BORDER_BOTTOM or any(t != BORDER_SIDE for t in tiles[1:-1]):
            return False
    return True


def border_rows(y, h):
    """화면 창 왼쪽 테두리 세로줄에서 보는 줄(위 테두리 아래부터 아래 테두리까지)의 스크린샷 y 범위."""
    return range(y * 8 - SHOT_SHIFT + 2, min(224, (y + h - 1) * 8 - SHOT_SHIFT + 2))


def border_gaps(image, x, y, h):
    """화면 창 왼쪽 테두리 세로줄(점 x × 8 + 1)에서 흰 점이 아닌 줄 수. 피해 흔들림은 화면 전체를 1~2점 좌우로
    옮기므로(원래 롬도 같음) 세로줄 전체를 같은 d(-2~2)만큼 옮겨 본 것 가운데 가장 적은 수를 낸다. 줄마다 다르게 밀리는
    물결(BG3 가로 스크롤)은 어느 d 로도 다 맞지 않아 그대로 센다."""
    return min(sum(image.getpixel((x * 8 + 1 + d, row)) != WINDOW_WHITE for row in border_rows(y, h))
               for d in range(-2, 3) if 0 <= x * 8 + 1 + d < 256)


def safe(screen):
    """screen_window 결과에서 창이 화면에서 깨진 스크린샷(어두워지는 화면·피해 흔들림 말고)과 창 안 다른 색 점이 없는지."""
    return screen['border_broken'] == 0 and screen['foreign_shots'] == 0


def synced_until(calls, other):
    """메시지 번호·연출 시작·행동 결정 기록이 처음 갈리는 프레임. 모양을 바꾼 롬은 전송 크기(FX) 줄이 늘 달라 뺀다."""
    keep = ('248C39', 'FXID', 'ACT')
    return same_until([line for line in calls if len(line.split()) > 1 and line.split()[1] in keep],
                      [line for line in other if len(line.split()) > 1 and line.split()[1] in keep])


def above_window(scene, name, shape, seen, out):
    """창을 21줄 위로 올린 롬과 원래 롬의 같은 프레임 스크린샷에서 창 위가 같은지. 창 타일은 흰 테두리(스크린샷
    y × 8 - SHOT_SHIFT) 한 줄 위의 어두운 줄부터다. 두 롬의 메시지·연출·행동 기록이 갈리기 전 프레임만 본다.
    → (견준 장, 다른 장, 처음 다른 프레임)."""
    limit = synced_until(seen[('original', scene)][2], seen[(name, scene)][2])
    top = shape['y'] * 8 - SHOT_SHIFT - 3
    frames = differ = 0
    first = None
    for shot in sorted((out / scene / name).glob('f*.png')):
        frame = int(shot.stem[1:])
        other = out / scene / 'original' / shot.name
        if frame >= limit or not other.is_file():
            continue
        frames += 1
        a = Image.open(shot).convert('RGB').crop((0, 0, 256, top))
        b = Image.open(other).convert('RGB').crop((0, 0, 256, top))
        if a.tobytes() != b.tobytes():
            differ += 1
            first = first or frame
    return {'until': limit, 'shots': frames, 'differ': differ, 'first': first}


def effect_spans(calls):
    """실행 기록 → [(연출 번호, 시작 프레임, 끝 프레임)]. 연출 시작(FXID)부터 그 뒤 둘째 메시지까지."""
    starts, messages = [], []
    for line in calls:
        parts = line.split()
        if len(parts) == 3 and parts[1] == 'FXID':
            starts.append((parts[2], int(parts[0])))
        elif len(parts) == 3 and parts[1] == '248C39':
            messages.append(int(parts[0]))
    out = []
    for number, frame in starts:
        later = [m for m in messages if m > frame]
        out.append((number, frame, later[1] if len(later) > 1 else frame + 200))
    return out


def effect_above(scene, name, shape, seen, out):
    """연출마다 시작 프레임을 맞춰, 창을 21줄 위로 올린 롬과 원래 롬의 창 위 화면이 같은지 본다. 창 크기에 따라 메시지
    때가 달라져 두 롬의 같은 프레임 번호는 다른 장면일 수 있다. k 번째 연출을 원래 롬의 그 연출 구간 동안 견준다.
    피해 흔들림은 화면 전체(창 포함)를 2점까지 위로 올리므로(원래 롬도 같음) 창 위 두 줄은 빼고 본다.
    → (견준 장, 다른 장, 처음 다른 (연출, 시작에서 프레임))."""
    top = shape['y'] * 8 - SHOT_SHIFT - 3
    frames = differ = 0
    first = None
    for (number, start, end), (other, moved, _) in zip(effect_spans(seen[('original', scene)][2]),
                                                        effect_spans(seen[(name, scene)][2])):
        if number != other:
            break
        for d in range(end - start):
            a, b = out / scene / 'original' / f'f{start + d:05d}.png', out / scene / name / f'f{moved + d:05d}.png'
            if not (a.is_file() and b.is_file()):
                continue
            frames += 1
            if Image.open(a).convert('RGB').crop((0, 0, 256, top)).tobytes() != \
                    Image.open(b).convert('RGB').crop((0, 0, 256, top)).tobytes():
                differ += 1
                first = first or (number, d)
    return {'shots': frames, 'differ': differ, 'first': first}


def screen_window(scene, name, shape, seen, out):
    """스크린샷이 있는 프레임 가운데 VRAM 에 창 테두리가 그 프레임과 앞 두 덤프 내리 다 있는 때, 화면 창 왼쪽 테두리
    세로줄(점 x × 8 + 1)이 창 높이 내내 흰 점인지와, 창 안쪽에 창 바탕·글자 색이 아닌 점(앞으로 나온 OBJ·효과)이 몇 개인지
    센다. 스크린샷 y 는 BG3 타일맵 점 y 보다 SHOT_SHIFT 위다. 화면이 어두워지는 장면 전환에도 테두리가 흰색이 아니게 된다.
    창을 21줄 위로 올리면 주문 연출이 줄마다 바꾸는 BG3 가로 스크롤·색 더하기와 앞으로 올린 몬스터 OBJ 가 창에 닿는다."""
    dumps = seen[(name, scene)][0]
    x, y, w, h = shape['x'], shape['y'], shape['w'], shape['h']
    frames = broken = faded = worst = foreign = foreign_shots = 0
    first = None
    for k in range(2, len(dumps)):
        frame = FROM + k * STEP
        shot = out / scene / name / f'f{frame:05d}.png'
        if not shot.is_file():
            continue
        if not all(complete(dumps[j], x, y, w, h) for j in (k - 2, k - 1, k)):
            continue
        frames += 1
        image = Image.open(shot).convert('RGB')
        gaps = border_gaps(image, x, y, h)
        # 전투가 끝나 어두워지는 화면은 테두리 전체가 흰색이 아니다(원래 롬도 같으나 롬마다 때가 어긋남).
        if gaps >= len(border_rows(y, h)):
            faded += 1
            continue
        # 피해 흔들림은 화면 전체를 1~2점 위아래로 옮겨 테두리 끝 두 줄까지만 빈다(원래 롬도 같음).
        if gaps > 2:
            broken += 1
            worst = max(worst, gaps)
            first = first or frame
            continue
        top, bottom = y * 8 - SHOT_SHIFT, min(224, (y + h - 1) * 8 - SHOT_SHIFT + 2)
        inside = image.crop((x * 8 + 4, top + 4, (x + w) * 8 - 4, bottom - 3)).get_flattened_data()
        count = sum(p not in (WINDOW_GRAY, WINDOW_WHITE) for p in inside)
        foreign += count
        foreign_shots += count > 0
    return {'shots': frames, 'faded': faded, 'border_broken': broken, 'worst_gap': worst, 'first_broken': first,
            'foreign_pixels': foreign, 'foreign_shots': foreign_shots}


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
        # 전투가 끝나 어두워지는 동안과 피해 흔들림(화면이 1~2점 위아래로)은 원래 롬 창의 왼쪽 테두리가 제자리에서 희지 않다.
        if border_gaps(before, LEFT, top, h) > 0:
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


def number_matches(runs, original_runs):
    """이벤트·동료 장면은 창이 커지면 「あらわれた」의 ▼ 기다림부터 난수가 갈려 첫 턴 메시지부터 다를 수 있다.
    그래서 메시지 번호가 같은 첫 메시지끼리 글자를 견준다. → (글자까지 같은 수, 견준 수). 피해 수·대상이 든 메시지는
    난수에 따라 다를 수 있어, 견준 것의 1/NUMBER_MISS 까지는 달라도 된다."""
    firsts = {}
    for number, text in original_runs:
        firsts.setdefault(number, [c for c, _, _ in text])
    by_number = {}
    for number, text in runs:
        if number in firsts and number not in by_number:
            by_number[number] = [c for c, _, _ in text] == firsts[number]
    return sum(by_number.values()), len(by_number)


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
    same_number, compared = number_matches(runs, original_runs)
    for _, text in runs:
        for c, line, col in text:
            require(line < (h - 1) // 2 and col < w - 2, f'{scene}/{name}: 글자 {c} 가 격자 밖({line}줄 {col}칸)')
    if scene in PREFIX_SCENES:
        require(same >= 3, f'{scene}/{name}: 원래 롬과 글자까지 같은 메시지가 {same}개뿐')
    else:
        require(same_number >= 3 and compared - same_number <= compared // NUMBER_MISS,
                f'{scene}/{name}: 원래 롬과 번호가 같은 메시지 {compared}개 중 글자까지 같은 것이 {same_number}개')
    frames, differ, longest, first = consistency(dumps, bufs, x, y, w, h)
    require(frames and longest <= 1, f'{scene}/{name}: VRAM 창이 버퍼와 {longest}덤프 이어 다름(f{first}부터)')
    kinds = {line.split()[1] for line in calls if line}
    require(kinds >= SHAPED_COVER[scene], f'{scene}/{name}: {sorted(SHAPED_COVER[scene] - kinds)} 를 지나지 않음')
    effects = sum(line.endswith(' EFF') for line in calls)
    require(acc[OLD_GRID][1] == 0 and acc[NEW_GRID][1] > 0 and original_acc[OLD_GRID][1] > 0,
            f'{scene}/{name}: 옛 격자 쓰기 {acc[OLD_GRID][1]}, 새 격자 쓰기 {acc[NEW_GRID][1]}, '
            f'원래 롬 옛 격자 쓰기 {original_acc[OLD_GRID][1]}')
    return {'messages': common, 'same_text': same, 'same_number': f'{same_number}/{compared}', 'chars': chars, 'frames': frames, 'differ': differ, 'longest': longest,
            'effects': effects, 'old_grid_writes': acc[OLD_GRID][1], 'grid_writes': acc[NEW_GRID][1],
            'calls': sorted(kinds)}


def compare_field(name, seen):
    """field 장면: 필드로 돌아온 뒤의 맵·좌표와 필드 변수 7E:1E71~1EFF 가 원래 롬과 같은지."""
    original, moved = seen[('original', 'field')][4], seen[(name, 'field')][4]
    require(original and moved, f'field/{name}: 필드로 돌아오지 않음')
    require(original.split('\n')[1:] == moved.split('\n')[1:] and original.split(' ', 1)[1] == moved.split(' ', 1)[1],
            f'field/{name}: 필드로 돌아온 뒤 자리·7E:{FIELD_VARS[0]:04X}~{FIELD_VARS[1]:04X} 가 원래 롬과 다름')
    return {'field': moved.split('\n')[0], 'acc': seen[(name, 'field')][3]}


def with_retries(launch, dest, name, retries=RETRIES):
    """MesenCE 를 여럿 함께 띄우면 가끔 시작하자마자 255 로 끝나거나, 선실 상태에서 순간이동하지 못하고 느리게 돌아 전투
    메시지가 하나도 없다. 같은 입력을 혼자 다시 돌리면 늘 전투가 붙으므로 그런 실행만 dest 를 비우고 다시 돌린다.
    launch() 는 종료 코드를 돌려준다. → 다시 돌린 횟수."""
    for attempt in range(retries):
        code = launch()
        calls = (dest / 'exec.txt').read_text() if (dest / 'exec.txt').is_file() else ''
        if code == 0 and ' 248C39 ' in calls:
            return attempt
        require(attempt + 1 < retries, f'{name}: MesenCE {code}, 전투 메시지 없음({retries}번)')
        print(f'{name}: MesenCE {code}, 전투 메시지 없음 — 다시 돌림({attempt + 2}/{retries})', file=sys.stderr, flush=True)
        shutil.rmtree(dest)
        dest.mkdir(parents=True)
    return retries


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('rom', type=Path)
    ap.add_argument('--state', type=Path, required=True)
    ap.add_argument('--mesence', default=os.environ.get('MESENCE'))
    ap.add_argument('--out', type=Path, default='work/msgwindowcheck')
    ap.add_argument('--message-at', default='16:FE10', help='모양을 바꾸는 경우의 새 코드 자리')
    ap.add_argument('--effects-at', default='3F:F000', help='창을 21줄 위로 올리는 경우의 연출 막기 코드 자리')
    ap.add_argument('--cases', default=','.join(CASES))
    ap.add_argument('--scenes', default=','.join(SCENES))
    ap.add_argument('--jobs', type=int, default=4)
    ap.add_argument('--shot-every', type=int, default=SHOTEVERY, help='스크린샷 간격(프레임)')
    ap.add_argument('--hlog', action='store_true', help='원래 롬 실행에서 보이는 줄의 PPU 레지스터 쓰기를 모은다(느림)')
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
            if shape['y'] < TOP:
                write += ['--effects-at', args.effects_at]
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

        retried = []

        def run(job):
            rom, scene = job
            dest = out / scene / rom
            dest.mkdir(parents=True)
            env = os.environ.copy()
            for key in ('PARTY', 'SET', 'POKE', 'ROMPATCH', 'TO', 'LATESET', 'SWAP', 'GROUP', 'BATTLE', 'FIELDSNAP'):
                env.pop(key, None)
            env.update(LIBDIR=libdir, STATE=str(state), SHOT_DIR=str(dest), DRIVER=str(HERE / 'lua/dq5warp.lua'),
                       FIELD='341,56', TEST=TAPS, FROM=str(FROM), STEP=str(STEP), SHOTEVERY=str(args.shot_every), ACC=ACC,
                       HLOG='1' if args.hlog and rom == 'original' else '0', HLOGTAIL=str(HLOG_TAIL), **SCENES[scene])
            def launch():
                with (dest / 'mesen.log').open('w') as log:
                    return subprocess.run([str(mesence), '--testrunner', str(roms[rom]),
                                           str(HERE / 'lua/dq5msgwindowcheck.lua'), '--Snes.DisableFrameSkipping=true',
                                           '--timeout=900'], env=env, stdout=log, stderr=subprocess.STDOUT,
                                          timeout=1000).returncode

            retried.extend(f'{scene}/{rom}' for _ in range(with_retries(launch, dest, f'{scene}/{rom}')))
            acc = {}
            for line in (dest / 'acc.txt').read_text().split('\n'):
                if line:
                    key, reads, writes = line.split()
                    acc[key] = (int(reads), int(writes))
            field = (dest / 'field.txt').read_text() if (dest / 'field.txt').is_file() else ''
            return (chunks((dest / 'bg3.bin').read_bytes()), chunks((dest / 'buf.bin').read_bytes()),
                    (dest / 'exec.txt').read_text().split('\n'), acc, field,
                    chunks((dest / 'oam.bin').read_bytes(), 0x221),
                    (dest / 'hdma.txt').read_text() if (dest / 'hdma.txt').is_file() else '')

        jobs = [(rom, scene) for scene in scenes for rom in roms]
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
            seen = dict(zip(jobs, pool.map(run, jobs)))
        results = []
        for scene in scenes:
            if scene != 'field':
                frames, differ, longest, first = consistency(*seen[('original', scene)][:2], LEFT, TOP, WIDTH, HEIGHT)
                original_shape = {'x': LEFT, 'y': TOP, 'w': WIDTH, 'h': HEIGHT}
                original_screen = screen_window(scene, 'original', original_shape, seen, out)
                results.append({'scene': scene, 'case': 'original', 'frames': frames, 'differ': differ,
                                'longest': longest, **transfer_sizes(scene, 'original', TOP, seen[('original', scene)][2]),
                                'spell': spell_ran(scene, 'original', seen[('original', scene)][2]),
                                'screen': original_screen, 'cover': coverage(scene, seen)})
                require(safe(original_screen), f'{scene}/original: 화면 창이 깨짐 {original_screen}')
                require(frames and longest <= 1, f'{scene}/original: VRAM 창이 버퍼와 {longest}덤프 이어 다름(f{first}부터)')
            for name, row in cases.items():
                if scene == 'field':
                    result = compare_field(name, seen)
                elif name in shapes:
                    result = {**compare_shaped(scene, name, shapes[name], seen),
                              **transfer_sizes(scene, name, shapes[name]['y'], seen[(name, scene)][2]),
                              'screen': screen_window(scene, name, shapes[name], seen, out),
                              'above': above_window(scene, name, shapes[name], seen, out),
                              'effect_above': effect_above(scene, name, shapes[name], seen, out)}
                    # 창은 화면에서 깨지지 않아야 한다. 연출 동안 창 위 화면(effect_above)은 세기만 한다: 창을 높이기만
                    # 해도(효과 층을 창 위 줄까지만 올림) 원래 롬과 다른 프레임이 있다.
                    require(safe(result['screen']), f'{scene}/{name}: 화면 창이 깨짐 {result["screen"]}')
                else:
                    result = {**compare_moved(scene, name, row['x'], seen, out),
                              **transfer_sizes(scene, name, TOP, seen[(name, scene)][2])}
                if scene != 'field':
                    result['spell'] = spell_ran(scene, name, seen[(name, scene)][2])
                results.append({'scene': scene, 'case': name, **result})
        results.append({'retried': retried})
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
