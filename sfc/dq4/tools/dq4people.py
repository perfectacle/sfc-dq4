"""서장·1장 인물 필드 그림: NDS 인물 시트를 DQ5 세트로 줄여 넣고, 같은 그림 번호를 쓰는 인물을 맵 그룹으로 가른다.

NDS 시트(자원 저장소 nds/dq4/chr/field/hNNN.png)는 방향마다 24x32 프레임 3장이다. 8방향(128x256)은 줄 0 뒤,
2 오른쪽 보기, 4 앞, 6 왼쪽 보기, 4방향(128x128)은 0 뒤, 1 왼쪽 보기, 2 앞, 3 오른쪽 보기다. 모든 인물을 같은
배율(NDS 28줄 → 22줄, DQ5 성인 NPC 세트 00 의 16x22)로 BOX 축소해 발을 21행에 두고, 16칸을 넘는 양끝을 자른다.
사람의 둘째·셋째 프레임은 다리가 같은 팔 동작이라 첫 프레임만 쓰고 걸음은 DQ5 처럼 다리만 바꾼다(앞·뒤는
1장째 오른발, 2장째 왼발을 1칸 들고, 옆은 발 3행을 1장째 보는 쪽, 2장째 반대쪽으로 1칸). 몬스터·동물은 NDS
첫 두 프레임이 그대로 걸음이다.

세트: 장 주인공은 새 세트 70·71, 1장 인물은 그 그림 번호의 원래 세트를 그 자리에서 바꾼다(8타일 세트는 머리
16x16 + 몸 16x16 배치). 서장에서만 다른 인물과 원래 세트가 모자란 주요 인물은 DQ4 가 쓰지 않는 그림 번호(spare)의
세트를 그 자리에서 바꿔 쓴다. 새 세트 레코드 자리(1F:FE30~, 8개)와 늘린 뱅크의 빈 자리를 아끼려는 것이다.
그림 번호 → 세트를 읽는 두 곳(1F:CF45, 03:D202 의 LDA $2586D0,X)을 JSL 로 돌려, 표의 (그림 번호, 맵 그룹 $BC) 가
맞으면 그 세트를, 아니면 원래 표를 읽는다.

색: 장 주인공·호이민은 OBJ 팔레트 한 줄씩(7·6·5), 나머지는 0·1·2·4 네 줄을 나눠 쓴다. 인물마다 NDS 색(15색
이내) 그대로 시작해, 줄에 묶을 때 색 거리 합이 가장 작게 늘어나는 줄로 넣고 줄마다 15색으로 줄인다(주요 인물은
가중 4배). 3 은 DQ5 가 맵마다 덮어 피한다.

  python sfc/dq4/tools/dq4people.py --base work/ch1/dq4-ch1-sound.sfc --assets "$DQ4_ASSETS" --out work/ch1/dq4-ch1-full.sfc
  python sfc/dq4/tools/dq4people.py --plan --assets "$DQ4_ASSETS"     인물마다 타일 수·한도·팔레트 줄
"""
import argparse
import json
import math
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
DQ5_TOOLS = HERE.parents[1] / 'dq5' / 'tools'
sys.path[:0] = [str(HERE), str(DQ5_TOOLS)]

import dq4chapterbox  # noqa: E402
from dq4ch2event import ALENA_PICTURE, BREY_PICTURE, CHAPTER2, KIRYL_PICTURE  # noqa: E402
from dq4chapter1 import apply_writes, lorom  # noqa: E402
from dq4romassets import set_checksum  # noqa: E402
import dq5npcrecord  # noqa: E402
import dq5objpalette  # noqa: E402
import dq5sprite as S  # noqa: E402
import dq5spritewrite  # noqa: E402
from dq5map import Rom  # noqa: E402

FIELD = Path('nds') / 'dq4' / 'chr' / 'field'
ROWS8 = (('down', 4), ('left', 6), ('right', 2), ('up', 0))
ROWS4 = (('down', 2), ('left', 3), ('right', 1), ('up', 0))   # 4줄 시트는 1줄이 오른쪽(얼굴 살색이 오른쪽에 몰림)
SCALE, BOTTOM, WIDTH = 22 / 28, 22, 16
DARK_L, DARK_SHARE = 15, 0.34                    # Lab 밝기 15 아래를 눈·외곽선으로 봄(더 느슨하면 얼굴 그늘까지 검어짐)
PROLOGUE = dq4chapterbox.PROLOGUE.where[0]       # 서장 마을(FC 14/00, 5장 첫머리도 같은 마을)
COMPANION_PICTURES = '05:D9D5'                     # 사람 동료 그림 표(인물 번호 → 그림)
LEADER_PICTURES = (0x2B, 0x2E)                     # 일행 0번: 실내 02:CA5A, 바깥 05:D98F


def mirror_sides(cells):
    """왼쪽 보기를 오른쪽 보기의 좌우 반전으로(DQ5 칸의 반전 비트로 타일을 나눠 씀)."""
    cells['left'] = [c.transpose(Image.Transpose.FLIP_LEFT_RIGHT) for c in cells['right']]


def still(cells, names):
    for name in names:
        cells[name] = [cells[name][0], cells[name][0].copy()]


# 타일 한도를 넘을 때 차례로 낮추는 단계(주요 인물은 새 세트로 한도를 넓히고 낮추지 않는다)
DEGRADE = (
    ('왼쪽=오른쪽 반전', mirror_sides),
    ('위 걸음 멈춤', lambda c: still(c, ('up',))),
    ('앞 걸음 멈춤', lambda c: still(c, ('down',))),
    ('모든 걸음 멈춤', lambda c: still(c, ('down', 'left', 'right', 'up'))),
)


class Person:
    def __init__(self, pictures, group, sheet, role, anim='legs', main=False, palette=None, new_set=None, spare=None,
                 allow=None, outline=False, flag=None, leader=False):
        self.pictures, self.group, self.sheet, self.role = pictures, group, sheet, role
        self.anim, self.main, self.palette, self.new_set, self.spare = anim, main, palette, new_set, spare
        # flag = (7E:2190 바이트, 마스크): 그 깃발이 켜져 있을 때만 전용 팔레트 줄을 이 인물의 색으로 덮는다
        self.outline, self.flag = outline, flag
        # leader: 깃발이 켜져 있으면 일행 0번 그림(2B·2E)도 이 인물의 세트로(실내는 02:CA5A 가 늘 2B 를 둔다)
        self.leader = leader
        # 타일이 모자랄 때 낮춰도 되는 단계(이름). 주요 인물은 기본으로 낮추지 않고 큰 세트로 옮긴다
        self.allow = allow if allow is not None else (() if main else tuple(n for n, _ in DEGRADE))


# NDS 시트는 같은 맵의 NDS 스크립트 오브젝트 모습 번호(+04)와 그 대사의 화자 이름으로 골랐다
# (nds/dq4/tools/ndsscript.py dump, 서장·1장 그룹). 1장 그림 번호는 dq4npcport.PICTURES 와 dq4chapter1·dq4prologue 의 것
PEOPLE = (
    Person(LEADER_PICTURES, PROLOGUE, 'h101', '천공의 용사', main=True, palette=7, new_set=0x70),
    Person(LEADER_PICTURES, None, 'h106', '라이언', main=True, palette=6, new_set=0x71),
    Person((0x5B,), None, 'h130', '호이민', anim='frames', main=True, palette=5, spare=0x58),
    Person((0x14,), None, 'h036', '왕', main=True, spare=0x18),
    Person((0x01,), None, 'h034', '대신', main=True),
    Person((0x04,), None, 'h038', '귀부인', main=True, spare=0x72),
    # 원래 세트들이 모자라 주요 인물은 원래 타일이 큰, 쓰지 않는 그림 번호의 새 세트로 잇는다. 피사로의 부하는
    # 46타일이라 그런 자리가 없어 옆을 반전으로 나눠 쓴다(몬스터라 좌우 차이가 작다)
    Person((0x9B,), None, 'h153', '피사로의 부하', anim='frames', main=True, spare=0x6F,
           allow=('왼쪽=오른쪽 반전',)),
    Person((0x0E,), PROLOGUE, 'h143', '신시아', main=True, spare=0x2D),
    Person((0x50,), None, 'h174', '개구리', anim='frames', main=True, outline=True),  # 풀·나뭇잎과 같은 초록이라
    Person((0x08,), PROLOGUE, 'h019', '검사', main=True, spare=0x90),
    Person((0x17,), PROLOGUE, 'h003', '어머니', spare=0x39),
    Person((0x09,), PROLOGUE, 'h002', '아버지', spare=0x8D),
    Person((0x1F,), PROLOGUE, 'h039', '장로', main=True, spare=0x9C),
    Person((0x06,), None, 'h015', '병사'),
    Person((0x67,), None, 'h017', '위병'),
    Person((0x08,), None, 'h018', '전사'),
    Person((0x0B,), None, 'h007', '남자아이'),
    Person((0x17,), None, 'h001', '여자'),
    Person((0x03,), None, 'h000', '남자'),
    Person((0x09,), None, 'h005', '노인'),
    Person((0x29,), None, 'h030', '농부'),
    Person((0x38,), None, 'h002', '아저씨'),
    Person((0x15,), None, 'h021', '신부'),
    Person((0x05,), None, 'h022', '수녀'),
    Person((0x1F,), None, 'h033', '학자'),
    Person((0x42,), None, 'h010', '여행 상인'),
    Person((0x20,), None, 'h044', '개', anim='frames'),
    Person((0x19,), None, 'h003', '아주머니'),
    Person((0x07,), None, 'h011', '거친 남자'),
    Person((0x82,), None, 'h029', '하녀'),
    Person((0x0C,), None, 'h031', '시인'),
    Person((0x40,), None, 'h009', '상인'),
    # 2장 일행. 크리프트·브라이는 사람 동료 그림 표(COMPANION_PICTURES)의 인물 09·05 칸이 그림을 고른다
    Person((ALENA_PICTURE,), None, 'h109', '아리나', main=True, palette=7, flag=CHAPTER2, leader=True),
    Person((KIRYL_PICTURE,), None, 'h112', '크리프트', main=True, palette=6, flag=CHAPTER2),
    Person((BREY_PICTURE,), None, 'h115', '브라이', main=True, palette=5, flag=CHAPTER2),
    # 2장 그룹(3D·45)의 인물. 시트는 NDS 스크립트 오브젝트의 모습 번호(= 시트 번호)와 그 대사의 화자 이름으로 골랐다
    Person((0x0E,), None, 'h035', '공주', main=True),
    Person((0x3D,), None, 'h013', '죄수'),
    Person((0x45,), None, 'h071', '호빗'),
    Person((0x1A,), None, 'h009', '초록 모자 상인'),
    Person((0x26,), None, 'h048', '말', anim='frames'),
)
SHARED_LINES = (0, 1, 2, 4)
HOOK_SITES = ('1F:CF45', '03:D202')
LOAD_SET = bytes.fromhex('bf d0 86 25')                  # LDA $2586D0,X
MAP_GROUP = 0x7E00BC
DQ4_GROUPS = frozenset(range(0x36, 0x46))            # dq4groupbuild 가 만드는 DQ4 맵 그룹
# 원래 자리에 들어가지 않는 타일 자료를 나눠 담는 곳(뱅크 3F 이하여야 레코드가 가리킴). 곡 롬의 0 끝 줄 안. 3F 는 앞쪽을
# 인물 목록(dq4chapter1.NPC_BANK, 인라인 스크립트 포함)이 쓰므로 그 끝과 겹치지 않게 띄운다
# 3C:F040~ 는 그룹 빌드(3A~3F)가 채운 뒤 남는 끝자리. 37·39·36:9E00~ 는 맵 레코드 자리(dq4chapter1.RECORDS_AT)라 쓰지 않는다
# 3D:FA80~FD90 은 맵 팔레트 표(MAP_PALETTES_AT) 뒤의 남는 자리. 표가 자라 겹치면 apply_writes 가 멈춘다
TILE_AREAS = (('3E:D700', 0xFC00 - 0xD700), ('3F:EB80', 0x10000 - 0xEB80), ('3C:F040', 0xFE00 - 0xF040),
              ('3D:FA80', 0xFD90 - 0xFA80))
PALETTES_AT, HOOK_AT = '3D:EA00', '3E:FC00'
MAP_PALETTES_AT = '3D:EB60'                       # 맵 팔레트 줄 루틴·표를 옮길 곳(세트 팔레트 표 뒤 빈 자리)


def cpu(text):
    bank, addr = text.split(':')
    return int(bank, 16) << 16 | int(addr, 16)


def frames(sheet, anim):
    """방향마다 (프레임 0, 프레임 1) RGBA. 같은 방향의 두 장은 같은 상자로 잘라야 몸이 흔들리지 않는다."""
    im = Image.open(sheet).convert('RGBA')
    rows = ROWS8 if im.height == 256 else ROWS4
    out = {}
    for name, row in rows:
        strip = im.crop((0, row * 32, im.width, row * 32 + 32))
        on = [any(strip.getpixel((x, y))[3] for y in range(32)) for x in range(im.width)]
        runs, x = [], 0
        while x < im.width:
            if on[x]:
                start = x
                while x < im.width and on[x]:
                    x += 1
                runs.append((start, x))
            else:
                x += 1
        picked = [strip.crop((a, 0, b, 32)) for a, b in runs[:2]]
        if anim != 'frames' or len(picked) < 2:
            picked = picked[:1] * 2
        width = max(f.width for f in picked)
        boxes = [f.getbbox() for f in picked]
        top, bottom = min(b[1] for b in boxes), max(b[3] for b in boxes)
        pair = []
        for f in picked:
            c = Image.new('RGBA', (width, bottom - top))
            c.paste(f.crop((0, top, f.width, bottom)), ((width - f.width) // 2, 0))
            pair.append(c)
        out[name] = pair
    return out


def shrink(f):
    """BOX 축소한 RGBA. 칸마다 NDS 원래 색 가운데 가장 가까운 색으로 되돌리되, 칸에 어두운 점(눈·외곽선)이
    DARK_SHARE 이상이면 그 어두운 색을 남긴다. 평균만 내면 1~2픽셀 눈과 외곽선이 피부·배경색에 섞여 사라진다."""
    src = f.load()
    pal = sorted({p[:3] for p in f.get_flattened_data() if p[3]})
    w, h = max(1, round(f.width * SCALE)), max(1, round(f.height * SCALE))
    small = f.resize((w, h), Image.BOX)
    out = Image.new('RGBA', (w, h))
    for y in range(h):
        for x in range(w):
            p = small.getpixel((x, y))
            if p[3] < 128:
                continue
            box = [src[sx, sy] for sy in range(int(y / SCALE), min(f.height, math.ceil((y + 1) / SCALE)))
                   for sx in range(int(x / SCALE), min(f.width, math.ceil((x + 1) / SCALE)))]
            solid = [q[:3] for q in box if q[3]]
            dark = [q for q in solid if lab(q)[0] < DARK_L]
            if solid and len(dark) / len(solid) >= DARK_SHARE:
                out.putpixel((x, y), Counter(dark).most_common(1)[0][0] + (255,))
            else:
                out.putpixel((x, y), min(pal, key=lambda c: sum((a - b) ** 2 for a, b in zip(c, p[:3]))) + (255,))
    return out


def is_face(c):
    return 45 <= lab(c)[0] <= 90 and c[0] > c[2] and not is_white(c)


def is_white(c):
    return lab(c)[0] > 88 and max(c) - min(c) < 50


def find_eyes(f, side=False):
    """NDS 프레임의 눈동자: 머리 쪽(위 60%)에서 흰자 바로 옆의 어두운 점. 세로로 이어진 점을 한 눈으로 묶는다.
    [(x, 가운데 y, 색)]. NDS 인물 눈은 흰자 1칸 + 눈동자 1x2 꼴이다."""
    px = f.load()
    lit = lambda x, y: 0 <= x < f.width and px[x, y][3] and is_white(px[x, y][:3])  # noqa: E731
    pupils = {(x, y) for y in range(f.height * 3 // 5) for x in range(2, f.width - 2)
              if px[x, y][3] and lab(px[x, y][:3])[0] < 28}
    eyes = []
    for x in sorted({q[0] for q in pupils}):
        ys = sorted(y for q, y in pupils if q == x)
        runs = [[ys[0]]]
        for y in ys[1:]:
            (runs[-1].append(y) if y == runs[-1][-1] + 1 else runs.append([y]))
        for r in runs:
            if len(r) != 2 or r[0] == 0 or r[-1] + 1 >= f.height:
                continue
            if not any(lit(x - 1, y) or lit(x + 1, y) for y in r):
                continue
            if not (px[x, r[-1] + 1][3] and lab(px[x, r[-1] + 1][:3])[0] >= 45):
                continue
            lights = sum(lit(x + d, y) for d in (-1, 1) for y in r)
            eyes.append((x, sum(r) / len(r), Counter(px[x, y][:3] for y in r).most_common(1)[0][0], lights))
    # 옆모습은 흰자가 가장 많이 붙은 하나, 앞모습은 같은 높이에서 서로 가장 가까운 둘
    if side:
        return [max(eyes, key=lambda e: e[3])[:3]] if eyes else []
    pairs = [(abs(a[0] - b[0]), a, b) for i, a in enumerate(eyes) for b in eyes[i + 1:]
             if a[1] == b[1] and 2 <= abs(a[0] - b[0]) <= 5]
    return [e[:3] for e in min(pairs, key=lambda t: t[0])[1:]] if pairs else []


def sharpen_eyes(f, s, name):
    """줄인 얼굴의 눈 줄에서 번진 흰자·눈동자를 살색으로 지우고, NDS 눈동자 자리마다 그림에서 가장 어두운 색으로
    1x2 점을 찍는다(DQ5 인물 눈 실측 1x2). 갈색 눈동자를 그대로 쓰면 22줄에서 흐려 보인다."""
    if name == 'up':
        return
    eyes = find_eyes(f, side=name != 'down')
    if not eyes:
        return
    px = s.load()
    sx, sy = s.width / f.width, s.height / f.height
    spots = [(min(s.width - 1, int((x + 0.5) * sx)), min(s.height - 2, int(y * sy))) for x, y, _ in eyes]
    face = [px[x, y][:3] for y in range(s.height * 3 // 5) for x in range(s.width)
            if px[x, y][3] and lab(px[x, y][:3])[0] >= 45 and not is_white(px[x, y][:3])]
    ink = min((px[x, y][:3] for y in range(s.height) for x in range(s.width) if px[x, y][3]), key=lambda c: lab(c)[0])
    for x, y in spots:
        for cy in (y, y + 1):
            for cx in (x - 1, x + 1):
                if 0 < cx < s.width - 1 and px[cx, cy][3] and px[cx - 1, cy][3] and px[cx + 1, cy][3] \
                        and (cx, cy) not in spots and (cx, cy - 1) not in spots \
                        and (lab(px[cx, cy][:3])[0] < 35 or is_white(px[cx, cy][:3])):
                    near = [px[cx, cy + d][:3] for d in (-1, 2, -2) if 0 <= cy + d < s.height and px[cx, cy + d][3]]
                    near = [c for c in near if c in face] or face
                    if near:
                        px[cx, cy] = Counter(near).most_common(1)[0][0] + (255,)
        px[x, y] = px[x, y + 1] = ink + (255,)


def rgb_frames(person, assets):
    """{방향: [16x24 RGBA 걸음 0, 걸음 1]}. 걸음 규칙까지 들어간 것."""
    out = {}
    for name, pair in frames(assets / FIELD / f'{person.sheet}.png', person.anim).items():
        cells = []
        for f in pair:
            s = shrink(f)
            sharpen_eyes(f, s, name)
            cut, ox = max(0, s.width - WIDTH) // 2, (WIDTH - min(WIDTH, s.width)) // 2
            c = Image.new('RGBA', (16, 24))
            c.paste(s.crop((cut, 0, cut + min(WIDTH, s.width), s.height)), (ox, BOTTOM - s.height))
            cells.append(c)
        if person.anim == 'legs':
            step(cells, name, s.height)
        if person.outline:
            for c in cells:
                outline(c)
        out[name] = cells
    return out


def outline(c):
    """실루엣 가장자리 픽셀을 그림에서 가장 어두운 색으로. 크기는 그대로 두고 배경과 같은 계열 색인 인물을 떼어 낸다."""
    px = c.load()
    solid = {(x, y) for y in range(c.height) for x in range(c.width) if px[x, y][3]}
    darkest = min((px[q] for q in solid), key=lambda q: lab(q[:3])[0])
    edge = [(x, y) for x, y in solid if any((x + dx, y + dy) not in solid
                                              for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)))]
    for q in edge:
        px[q] = darkest


def step(cells, name, height):
    legs = range(BOTTOM - max(3, round(height * 5 / 22)), BOTTOM)
    if name in ('down', 'up'):
        for c, xs in ((cells[0], range(8, 16)), (cells[1], range(0, 8))):
            for x in xs:
                for y in legs:
                    c.putpixel((x, y), c.getpixel((x, y + 1)) if y < BOTTOM - 1 else (0, 0, 0, 0))
        return
    ahead = -1 if name == 'left' else 1
    for c, d in ((cells[0], ahead), (cells[1], -ahead)):
        for y in range(BOTTOM - 3, BOTTOM):
            line = [c.getpixel((x, y)) for x in range(16)]
            moved = [(0, 0, 0, 0)] + line[:-1] if d > 0 else line[1:] + [(0, 0, 0, 0)]
            for x in range(16):
                c.putpixel((x, y), moved[x])




def histogram(cells):
    return Counter(p[:3] for pair in cells.values() for c in pair for p in c.get_flattened_data() if p[3])


def lab(c):
    def lin(v):
        v /= 255
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (lin(v) for v in c)
    x, y, z = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.9505, 0.2126 * r + 0.7152 * g + 0.0722 * b, \
        (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.089
    f = lambda t: t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116  # noqa: E731
    return 116 * f(y) - 16, 500 * (f(x) - f(y)), 200 * (f(y) - f(z))


def reduce(hist, n=15):
    """색 빈도 → n 색. 가장 가까운 두 색 가운데 덜 쓴 색을 많이 쓴 색에 합치기를 되풀이해 NDS 색을 그대로 남긴다."""
    items = [[c, w, lab(c)] for c, w in hist.items()]
    while len(items) > n:
        best = None
        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                d = math.dist(items[i][2], items[j][2]) * min(items[i][1], items[j][1])
                if best is None or d < best[0]:
                    best = (d, i, j)
        _, i, j = best
        keep, drop = (i, j) if items[i][1] >= items[j][1] else (j, i)
        items[keep][1] += items[drop][1]
        del items[drop]
    return [c for c, _, _ in items]


def cost(hist, pal):
    lp = [lab(c) for c in pal]
    return sum(w * min(math.dist(lab(c), q) for q in lp) for c, w in hist.items())


def lines(people, hists):
    """공용 줄 배정: 주요 인물부터 넣을 때 늘어나는 색 거리 합이 가장 작은 줄로."""
    groups = {n: Counter() for n in SHARED_LINES}
    order = sorted((p for p in people if p.palette is None), key=lambda p: (not p.main, -len(hists[p])))
    assign = {}
    for p in order:
        h = Counter({c: w * (4 if p.main else 1) for c, w in hists[p].items()})

        def growth(n):
            if not groups[n]:
                return 0
            merged = groups[n] + h
            return cost(merged, reduce(merged)) - cost(groups[n], reduce(groups[n]))
        best = min(SHARED_LINES, key=growth)
        groups[best] += h
        assign[p] = best
    return assign, {n: reduce(g) for n, g in groups.items() if g}


ROUNDS = 6


def place(people, hists, where):
    """맵 그룹마다 줄 색을 따로 싣는다. 줄은 공용 배정(lines)을 따르고, 인물 색 → 칸 번호는 모든 그룹에서 같아야
    하므로 인물마다 하나로 둔다. 「그룹마다 칸 색 = 그 그룹에서 그 칸에 모인 색의 가중 평균」과 「인물 색마다 그
    인물이 나오는 그룹들의 칸 색과의 거리 합이 가장 작은 칸」을 번갈아 고친다(공용 줄 색에서 시작).
    끝에는 칸 색을 그 칸에 모인 NDS 원래 색 가운데 평균에 가장 가까운 것으로 둔다.
    반환: ({인물: (줄, {색: 칸})}, {(그룹, 줄): 15색})."""
    assign, shared = lines(people, hists)
    who = [p for p in people if p.palette is None]
    keys = {(g, assign[p]) for p in who for g in where[p]}
    centers = {key: [lab(c) for c in shared[key[1]]] for key in keys}
    mapping = {}
    for _ in range(ROUNDS):
        for p in who:
            rows = [centers[(g, assign[p])] for g in where[p]]
            mapping[p] = {c: min(range(len(rows[0])), key=lambda k: sum(math.dist(lab(c), r[k]) for r in rows))
                          for c in hists[p]}
        acc = {}
        for p in who:
            for c, w in hists[p].items():
                for g in where[p]:
                    acc.setdefault((g, assign[p], mapping[p][c]), Counter())[c] += w * (4 if p.main else 1)
        for (g, line, k), cs in acc.items():
            total = sum(cs.values())
            centers[(g, line)][k] = tuple(sum(lab(c)[i] * w for c, w in cs.items()) / total for i in range(3))
    board = {}
    for g, line in keys:
        row = []
        for k, center in enumerate(centers[(g, line)]):
            cs = acc.get((g, line, k))
            row.append(min(cs, key=lambda c: math.dist(lab(c), center)) if cs else shared[line][k])
        board[(g, line)] = row
    return {p: (assign[p], mapping[p]) for p in who}, board


def index_image(cells, pal, layout):
    """색 번호 시트. simple 32x96(열 걸음 0·1), overlap 48x64(열 머리·몸 0·몸 1, 몸은 프레임의 8~23행).
    pal 이 {색: 칸} 이면 그대로 쓰고, 색 목록이면 가장 가까운 색의 칸으로."""
    mapping, pal = (pal, None) if isinstance(pal, dict) else (None, pal)
    lp = {k: lab(c) for k, c in enumerate(pal) if c is not None} if pal else {}
    near = {c: k + 1 for c, k in mapping.items()} if mapping else {}

    def idx(p):
        if not p[3]:
            return 0
        if p[:3] not in near:
            near[p[:3]] = min(lp, key=lambda k: math.dist(lab(p[:3]), lp[k])) + 1
        return near[p[:3]]
    if layout == 'simple':
        out = Image.new('P', (32, 96), 0)
        for r, (name, _) in enumerate(ROWS8):
            for col, c in enumerate(cells[name]):
                for y in range(24):
                    for x in range(16):
                        out.putpixel((col * 16 + x, r * 24 + y), idx(c.getpixel((x, y))))
    else:
        out = Image.new('P', (48, 64), 0)
        for r, (name, _) in enumerate(ROWS8):
            head = cells[name][0]
            for y in range(16):
                for x in range(16):
                    out.putpixel((x, r * 16 + y), idx(head.getpixel((x, y))))
            for col, c in enumerate(cells[name]):
                for y in range(16):
                    for x in range(16):
                        out.putpixel((16 + col * 16 + x, r * 16 + y), idx(c.getpixel((x, y + 8))))
    if mapping:
        pal = [None] * 15
        for c, k in mapping.items():
            pal[k] = pal[k] or c
    out.putpalette([0, 0, 0] + [v for c in pal for v in (c or (0, 0, 0))])
    return out


def hook(entries):
    """entries: [(그림 번호, 맵 그룹 또는 None, 세트)] 또는 [(그림, 그룹, 깃발 (바이트, 마스크) 또는 None, 세트)].
    맞는 첫 줄의 세트를, 없으면 원래 표를 싣는다. 부르는 곳의 A·X 폭이 달라 PHP·SEP #$30 … PLP 로 감싼다(두 곳
    모두 뒤에서 N·Z 를 보지 않는다). 줄이 많으면 끝까지의 BRA 가 127바이트를 넘으므로 줄마다 PLP·RTL 로 바로 돌아간다."""
    code = bytearray(b'\x08\xe2\x30')                                   # PHP / SEP #$30
    for entry in entries:
        picture, group, flag, s = entry if len(entry) == 4 else (entry[0], entry[1], None, entry[2])
        code += bytes((0xE0, picture, 0xD0, 0))                           # CPX #p / BNE 다음 줄
        skip = [len(code) - 1]
        if group is not None:
            a = MAP_GROUP
            code += bytes((0xAF, a & 0xFF, a >> 8 & 0xFF, a >> 16, 0xC9, group, 0xD0, 0))   # LDA $BC / CMP / BNE
            skip.append(len(code) - 1)
        if flag is not None:
            a = 0x7E2190 + flag[0]
            code += bytes((0xAF, a & 0xFF, a >> 8 & 0xFF, a >> 16, 0x29, flag[1], 0xF0, 0))  # LDA 깃발 / AND / BEQ
            skip.append(len(code) - 1)
        code += bytes((0xA9, s, 0x28, 0x6B))                              # LDA #세트 / PLP / RTL
        for off in skip:
            code[off] = len(code) - (off + 1)
    return bytes(code + LOAD_SET + b'\x28\x6b')                          # LDA $2586D0,X / PLP / RTL


def hook_entries(rom):
    """원래 표와 다른 세트를 쓰는 인물의 (그림 번호, 맵 그룹, 깃발, 세트). 깃발·맵 그룹을 보는 줄을 앞에 둔다."""
    out = []
    for p in PEOPLE:
        if p.flag is not None and p.leader:
            out += [(g, None, p.flag, target(p, rom)[0]) for g in LEADER_PICTURES]
    for p in sorted(PEOPLE, key=lambda p: p.group is None):
        if p.new_set is not None or p.spare is not None:
            out += [(g, p.group, None, target(p, rom)[0]) for g in p.pictures]
    return out


def hook_patch(rom):
    at = cpu(HOOK_AT)
    writes = [{'at': HOOK_AT, 'hex': hook(hook_entries(Rom(rom))).hex(' '), 'note': '그림 번호 + 맵 그룹 → 세트'}]
    for site in HOOK_SITES:
        orig = rom[lorom(cpu(site)):lorom(cpu(site)) + 4]
        if orig != LOAD_SET:
            raise SystemExit(f'{site}: LDA $2586D0,X 가 아님 ({orig.hex(" ")})')
        writes.append({'at': site, 'hex': bytes((0x22, at & 0xFF, at >> 8 & 0xFF, at >> 16)).hex(' '),
                       'orig': orig.hex(' '), 'note': '그림 → 세트를 인물 훅으로(JSL)'})
    brey = cpu(COMPANION_PICTURES) + 5
    writes.append({'at': f'{brey >> 16:02X}:{brey & 0xFFFF:04X}', 'hex': f'{BREY_PICTURE:02x}',
                   'orig': f'{rom[lorom(brey)]:02x}', 'note': '사람 동료 그림 표 인물 05(브라이) → 2C'})
    return {'format': 'dq5patch/1', 'name': 'people-hook', 'writes': writes, 'rom_size': 2}


def target(person, rom):
    """(세트, 배치, 타일 한도). 장 주인공은 새 6타일 세트(한도는 2B·2E 의 원래 세트 중 작은 쪽), 나머지는 그림
    번호(spare 가 있으면 spare)의 원래 세트를 그 자리에서 바꾸고 한도는 그 세트의 타일 수."""
    if person.pictures == LEADER_PICTURES:
        limit = min(S.set_record(rom, S.gfx_set(rom, g))['tiles'] for g in LEADER_PICTURES)
        return person.new_set, 'simple', limit
    s = S.gfx_set(rom, person.spare if person.spare is not None else person.pictures[0])
    return s, 'overlap' if s & 0x80 else 'simple', S.set_record(rom, s)['tiles']


def tiles(path, layout):
    cells = dq5spritewrite.cell_tiles(dq5spritewrite.image_grid(path, layout), layout)
    return len(dq5spritewrite.deduplicate(cells)[0])


def chapter_groups(chapter):
    import dq4groupbuild
    return sorted(g for g, maps in dq4groupbuild.LINKS.items() if any(m.get('chapter') == chapter for m in maps))


def usage(base):
    """{그림: 나오는 DQ4 맵 그룹들}. 곡 롬의 인물 목록에서 읽고, 대체 목록은 overrides 로 맵에 잇는다."""
    doc = dq5npcrecord.dump(base)
    maps = {}
    for o in doc['overrides']:
        maps.setdefault(o['list'], set()).add(o['map'])
    out = {}
    for e in doc['entries']:
        names = ({e['name']} if '/' in e['name'] else set()) | maps.get(e['list'], set())
        groups = {int(m.split('/')[0], 16) for m in names} & DQ4_GROUPS
        for part in (e.get('fields'), e.get('day'), e.get('night')):
            if part and groups:
                out.setdefault(part['gfx'], set()).update(groups)
    return out


def where(people, used):
    """{인물: 나오는 맵 그룹들}. 그룹을 정한 인물은 그 그룹만, 그 그룹에서 같은 그림을 빌려 간 인물이 있으면 뺀다.
    목록에서 찾지 못한 그림(이벤트로만 바꾸는 그림 등)은 모든 그룹으로 본다."""
    out = {}
    for p in people:
        if p.group is not None:
            out[p] = {p.group}
            continue
        groups = set()
        for pic in p.pictures:
            groups |= used.get(pic, DQ4_GROUPS)
        groups -= {q.group for q in people if q.group is not None and set(q.pictures) & set(p.pictures)}
        out[p] = groups or set(DQ4_GROUPS)
    return out


def prepare(rom, assets, work, base=None):
    """인물마다 시트를 만들어 타일 한도에 맞춘다. [(인물, 세트, 배치, 한도, 타일, 낮춘 단계, 줄, 줄 색)]."""
    cells = {p: rgb_frames(p, assets) for p in PEOPLE}
    hists = {p: histogram(cells[p]) for p in PEOPLE}
    used = usage(base) if base is not None else {}
    placed, board = place(PEOPLE, hists, where(PEOPLE, used))
    sets = [target(p, rom)[0] for p in PEOPLE]
    if len(set(sets)) != len(sets):
        raise SystemExit(f'두 인물이 같은 세트를 바꿈: {sorted(f"{s:02X}" for s in sets if sets.count(s) > 1)}')
    rows = []
    for p in PEOPLE:
        line, pal = (p.palette, reduce(hists[p])) if p.palette is not None else placed[p]
        s, layout, limit = target(p, rom)
        path = work / f'{s:02X}.png'
        index_image(cells[p], pal, layout).save(path)
        steps = []
        for name, fn in (d for d in DEGRADE if d[0] in p.allow):
            if tiles(path, layout) <= limit:
                break
            fn(cells[p])
            index_image(cells[p], pal, layout).save(path)
            steps.append(name)
        rows.append((p, s, layout, limit, tiles(path, layout), steps, line, pal))
    return rows, board


def tile_areas(base):
    """TILE_AREAS 를 base 롬(곡 롬)에 맞춘다. 앞 단계가 그 뱅크 끝의 0 줄 안까지 자료를 늘렸으면 쓰인 끝 다음 16바이트
    경계부터 쓴다(1장 빌드의 인물 자료가 3F 끝을 향해 자란다)."""
    out = []
    for at, size in TILE_AREAS:
        start, end = cpu(at), cpu(at) + size
        o = lorom(start)
        used = [i for i in range(o, lorom(end - 1) + 1) if base[i]]
        if used:
            moved = (start + used[-1] - o + 0x10) & ~0xF
            if any(base[lorom(moved):lorom(end - 1) + 1]):
                raise SystemExit(f'{at}: 타일 자리 안에 0 이 아닌 자료가 흩어져 있음')
            start = moved
        out.append((f'{start >> 16:02X}:{start & 0xFFFF:04X}', end - start))
    return tuple(out)


def pack(items, room):
    """[(세트, 바이트)] 를 자리 room(바이트 목록)에 나눠 담는 배치(자리마다 세트 목록). 큰 것부터 넣되 자리가
    조각나면 되돌아가 다른 자리를 고른다(큰 것부터 가장 큰 자리에만 넣으면 남은 합이 넉넉해도 막혔다)."""
    room, bins = list(room), [[] for _ in room]

    def go(i):
        if i == len(items):
            return True
        s, n = items[i]
        tried = set()
        for k in sorted(range(len(room)), key=lambda k: room[k]):
            if room[k] >= n and room[k] not in tried:
                tried.add(room[k])
                room[k] -= n
                bins[k].append(s)
                if go(i + 1):
                    return True
                room[k] += n
                bins[k].pop()
        return False
    if not go(0):
        raise SystemExit(f'타일 자료 자리가 모자람: 세트·바이트 {items}, 자리 {room}')
    return bins


def split_patches(rom, doc, base, areas=TILE_AREAS):
    """원래 자리에 들어가지 않는 세트를 areas 에 나눠 담는 dq5spritewrite 패치들. 한 번 돌려 어느 세트가
    얼마나 넘치는지 본 뒤, pack 으로 자리를 나누고 자리마다 다시 만든다."""
    first = cpu(areas[0][0])
    trial = dq5spritewrite.patch(rom, doc, base, first)
    size = Counter()
    for w in trial['writes']:
        at = cpu(w['at'])
        if at >= first and '타일' in w['note']:
            size[w['note'].split()[1]] += len(w['hex'].split())
    # 새 세트 레코드·그림 연결은 첫 패치만 실으므로 새 세트의 타일은 첫 자리에 둔다
    fresh = {r['set'] for r in doc['new_sets']}
    room = [n for _, n in areas]
    room[0] -= sum(n for s, n in size.items() if s in fresh)
    bins = pack(sorted(((s, n) for s, n in size.items() if s not in fresh), key=lambda t: -t[1]), room)
    bins[0] += sorted(fresh & set(size))
    out = []
    for k, (at, _) in enumerate(areas):
        if k == 0:
            # 첫 패치가 새 세트 레코드·그림 연결과 원래 자리에 들어가는 세트를 모두 맡는다
            part = {**doc, 'sets': [r for r in doc['sets'] if not any(r['set'] in b for b in bins[1:])]}
            part['new_sets'] = [r for r in doc['new_sets'] if not any(r['set'] in b for b in bins[1:])]
        else:
            part = {'format': doc['format'], 'sets': [r for r in doc['sets'] if r['set'] in bins[k]]}
        if part['sets'] or part.get('new_sets'):
            out.append(dq5spritewrite.patch(rom, part, base, cpu(at)))
    return out


def build(base, dq5, assets, out, work):
    original = dq5.read_bytes()
    rows, board = prepare(Rom(original), assets, work, Rom(base.read_bytes()))
    over = [f'{p.role} {n}>{limit}' for p, _, _, limit, n, _, _, _ in rows if n > limit]
    if over:
        raise SystemExit('타일 한도를 넘음: ' + ', '.join(over))
    doc = {'format': 'dq5sprite/1', 'sets': [], 'new_sets': [], 'gfx': []}
    leader_sets = []
    for p, s, _, _, _, _, _, _ in rows:
        if p.new_set is None:
            doc['sets'].append({'set': f'{s:02X}', 'image': f'{s:02X}.png'})
            continue
        doc['new_sets'].append({'set': f'{s:02X}', 'image': f'{s:02X}.png', 'palette': 0})
        leader_sets.append(s)
    # 장 주인공 두 세트는 그림 2B·2E 에 하나씩 잇는다(훅이 앞서므로 표 값은 쓰이지 않는다)
    doc['gfx'] += [{'gfx': f'{g:02X}', 'set': f'{s:02X}'} for g, s in zip(LEADER_PICTURES, leader_sets)]
    (work / 'sprite.json').write_text(json.dumps(doc, indent=1) + '\n')
    sprites = split_patches(Rom(original), doc, work, tile_areas(base.read_bytes()))
    for k, sprite in enumerate(sprites):
        (work / f'sprite{k}.dq5patch.json').write_text(json.dumps(sprite, ensure_ascii=False, indent=1) + '\n')
    subprocess.run([sys.executable, DQ5_TOOLS / 'dq5build.py', dq5, 'build',
                    *(work / f'sprite{k}.dq5patch.json' for k in range(len(sprites))),
                    '--size', '2', '-o', work / 'mid.sfc'], check=True, stdout=subprocess.DEVNULL)
    bgr = lambda pal: [0 if c is None else (c[2] >> 3) << 10 | (c[1] >> 3) << 5 | c[0] >> 3 for c in pal] + \
        [0] * (15 - len(pal))  # noqa: E731
    fixed = {line: pal for p, _, _, _, _, _, line, pal in rows if p.palette is not None and p.flag is None}
    # DQ4 그룹이 아닌 맵(필드 등)은 칸이 가장 많이 찬 그룹의 줄 색을 기본으로 둔다
    home = max({g for g, _ in board}, key=lambda g: sum(c is not None for (h, _), row in board.items() if h == g for c in row))
    base_lines = {line: board[(home, line)] for g, line in board if g == home}
    pal_doc = {'format': 'dq5objpalette/1',
               'palettes': [{'palette': n, 'colors': bgr(pal)} for n, pal in sorted({**base_lines, **fixed}.items())],
               'sets': [{'set': f'{s:02X}', 'palette': line} for _, s, _, _, _, _, line, _ in rows]}
    # 그룹 36~ 은 DQ4 롬에만 있으므로 맵 팔레트 줄은 곡 롬을 기준으로 따로 만든다
    map_doc = {'format': 'dq5objpalette/1',
               'new_map_palettes': [{'map': f'{g:02X}/FF', 'line': f'{0x08 + line:02X}', 'flag': 'FF', 'mask': '00',
                                     'colors': bgr(row)} for (g, line), row in sorted(board.items())]}
    # 깃발이 붙은 전용 줄(2장 일행)은 그 장의 그룹과 필드 세계 셋에서 그 깃발이 켜졌을 때 덮는다
    every = [f'{g:02X}/FF' for g in chapter_groups(2)] + [f'FE/{w:02X}' for w in range(3)]
    map_doc['new_map_palettes'] += [{'map': m, 'line': f'{0x08 + line:02X}', 'flag': f'{p.flag[0]:02X}',
                                     'mask': f'{p.flag[1]:02X}', 'colors': bgr(pal)}
                                    for p, _, _, _, _, _, line, pal in rows if p.flag is not None for m in every]
    maps = dq5objpalette.patch(Rom(base.read_bytes()), map_doc, MAP_PALETTES_AT)
    (work / 'maps.dq5patch.json').write_text(json.dumps(maps, ensure_ascii=False, indent=1) + '\n')
    palettes = dq5objpalette.patch(Rom((work / 'mid.sfc').read_bytes()), pal_doc, PALETTES_AT)
    (work / 'palette.dq5patch.json').write_text(json.dumps(palettes, ensure_ascii=False, indent=1) + '\n')
    (work / 'hook.dq5patch.json').write_text(json.dumps(hook_patch(original), indent=1) + '\n')
    names = [f'sprite{k}' for k in range(len(sprites))] + ['palette', 'maps', 'hook']
    rom = apply_writes(base.read_bytes(), original, [work / f'{n}.dq5patch.json' for n in names])
    out.write_bytes(set_checksum(rom))
    return rows


def report(rows):
    for p, s, layout, limit, n, steps, line, _ in rows:
        where = f'그룹 {p.group:02X}' if p.group is not None else '어디나'
        pics = ','.join(f'{g:02X}' for g in p.pictures)
        print(f'{p.role:8s} 그림 {pics:5s} {where:6s} {p.sheet} 세트 {s:02X} {layout:7s} 타일 {n:2d}/{limit:2d}'
              f' 팔레트 {line} {" · ".join(steps)}')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--base', type=Path, help='얹을 1장 롬(곡 묶음까지 얹은 것)')
    ap.add_argument('--dq5', default='rom/dq5.sfc', type=Path)
    ap.add_argument('--assets', required=True, type=Path, help='NDS 인물 시트가 있는 자원 저장소')
    ap.add_argument('--out', type=Path)
    ap.add_argument('--work', type=Path, help='중간 시트·패치를 둘 폴더(기본 임시 폴더)')
    ap.add_argument('--plan', action='store_true', help='롬을 만들지 않고 인물마다 세트·타일·팔레트 줄만 찍음')
    args = ap.parse_args()
    if not args.plan and not (args.base and args.out):
        ap.error('--base 와 --out 이 필요함(--plan 이 아니면)')
    with tempfile.TemporaryDirectory() as tmp:
        work = args.work or Path(tmp)
        work.mkdir(parents=True, exist_ok=True)
        if args.plan:
            report(prepare(Rom(args.dq5.read_bytes()), args.assets, work,
                           Rom(args.base.read_bytes()) if args.base else None)[0])
            return
        report(build(args.base, args.dq5, args.assets, args.out, work))
    print(args.out)


if __name__ == '__main__':
    main()
