"""DQ4(FC) 원작 그래픽 렌더러: 마을·던전 맵 279개, 필드, 블록·CHR·폰트 시트, MesenCE 덤프 화면. 쓰는 법은 docs/dq4-fcgfx.md.

사용:
  python tools/dq4fcgfx.py rom/dq4.nes all OUT                맵·필드·gfx 를 OUT/{maps,field,gfx} 에, 갤러리를 OUT/gallery 에
  python tools/dq4fcgfx.py rom/dq4.nes maps|field|gfx OUT     하나만
  python tools/dq4fcgfx.py rom/dq4.nes map G K OUT.png [--night|--annot]  맵 하나
  python tools/dq4fcgfx.py rom/dq4.nes screen DIR OUT.png     seq.lua·warp.lua 의 end.nt·chr·pal 로 nametable 두 장(512×240)
  python tools/dq4fcgfx.py rom/dq4.nes scenes OUT SPEC.json    fcgfxscene.lua 덤프 목록([{name, title, prefix}])을 OUT/gfx/screens 에
  python tools/dq4fcgfx.py rom/dq4.nes verify DIR... [--mask-sprites]  롬만으로 그린 화면과 end.png 를 픽셀로 비교
  python tools/dq4fcgfx.py rom/dq4.nes gallery OUT            OUT/gallery/index.html 만 다시

출력은 롬 그래픽이라 공개 저장소에 커밋하지 않는다(비공개 에셋 저장소나 work/ 에만).
맵은 칸마다 제 블록으로 그린다(게임은 주인공과 다른 구역을 블록 20·21 로 가리지만 참고용 그림에서는 다 보이게).
색은 MesenCE 화면에서 잰 값(MESEN_RGB, tools/lua/fc/fcgfxpal.lua)이다.
"""
import hashlib
import html
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFont
from kr_patch.fc import ines

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dq4block  # noqa: E402
import dq4chest  # noqa: E402
import dq4data  # noqa: E402
import dq4field  # noqa: E402
import dq4map  # noqa: E402
import dq4talk  # noqa: E402
import dq4text  # noqa: E402

# dq4map.maps 는 마지막 그룹 48(맵 10개)을 빼먹는다. dq4block.Map 이 쓰는 dq4map.load 를 이 프로세스 안에서만
# dq4chest.load(마지막 그룹까지 푸는 판)로 바꾸고, 맵 목록은 dq4chest.all_maps(279개)를 쓴다.
dq4map.load = dq4chest.load
all_maps = dq4chest.all_maps

# NES 색 번호 00~3F → MesenCE 기본 팔레트의 화면 RGB. tools/lua/fc/fcgfxpal.lua 로 색마다 화면 전체를 칠해 잰 값.
MESEN_RGB = [
    (102, 102, 102), (0, 42, 136), (20, 18, 167), (59, 0, 164), (92, 0, 126), (110, 0, 64), (108, 6, 0), (86, 29, 0),
    (51, 53, 0), (11, 72, 0), (0, 82, 0), (0, 79, 8), (0, 64, 77), (0, 0, 0), (0, 0, 0), (0, 0, 0),
    (173, 173, 173), (21, 95, 217), (66, 64, 255), (117, 39, 254), (160, 26, 204), (183, 30, 123), (181, 49, 32), (153, 78, 0),
    (107, 109, 0), (56, 135, 0), (12, 147, 0), (0, 143, 50), (0, 124, 141), (0, 0, 0), (0, 0, 0), (0, 0, 0),
    (255, 254, 255), (100, 176, 255), (146, 144, 255), (198, 118, 255), (243, 106, 255), (254, 110, 204), (254, 129, 112), (234, 158, 34),
    (188, 190, 0), (136, 216, 0), (92, 228, 48), (69, 224, 130), (72, 205, 222), (79, 79, 79), (0, 0, 0), (0, 0, 0),
    (255, 254, 255), (192, 223, 255), (211, 210, 255), (232, 200, 255), (251, 194, 255), (254, 196, 234), (254, 204, 197), (247, 216, 165),
    (228, 229, 148), (207, 239, 150), (189, 244, 171), (179, 243, 204), (181, 235, 242), (184, 184, 184), (0, 0, 0), (0, 0, 0),
]
GRAY = [(0, 0, 0), (85, 85, 85), (170, 170, 170), (255, 255, 255)]
NIGHT = 0x78                 # 맵: $62ED 가 이 값 이상이면 밤(0E:$BB55)
FIELD_NIGHT = 0x84           # 필드: 1E:$A2DB 경계 8개 중 가장 어두운 단계(84~BF)
FIELDS = (0, 1, 2, 3)        # $65. 크기는 0F:$D2D6/$D2D9
# 필드 2 는 입구 표에 없고, 워프로 들어간 화면이 이 렌더링과 다르다(docs/dq4-fcgfx.md 「남은 것」).
FIELD_NOTE = {2: '입구 없음. 워프 화면과 다름(확인 안 됨)', 3: '용암·물 팔레트가 돌아감. 그림은 롬의 첫 팔레트'}
FONT_AT, FONT_N = (0x18, 0xB840), 141   # 글자 바이트 00~8C 의 1비트 타일(docs/dq4-text-format.md)


def tile(data, colors):
    """2bpp 16바이트 → 8×8 RGB 그림."""
    im = Image.new('RGB', (8, 8))
    im.putdata([colors[(data[r] >> (7 - c) & 1) | (data[r + 8] >> (7 - c) & 1) << 1] for r in range(8) for c in range(8)])
    return im


def pal_rgb(pal12):
    """BG 팔레트 12바이트(색 1~3 × 4) → 팔레트마다 RGB 4개. 색 0 은 0F($05FC)."""
    return [[MESEN_RGB[0x0F]] + [MESEN_RGB[pal12[3 * i + j] & 0x3F] for j in range(3)] for i in range(4)]


class Painter:
    """dq4block.Map 의 블록을 16×16 그림으로(블록마다 한 번만 만든다). 필드는 물가 블록 20~2F 도 그린다."""

    def __init__(self, m, pal12):
        self.m, self.colors, self.cache = m, pal_rgb(pal12), {}
        self.shore = shore_defs(m.prg) if m.buf is None else {}

    def block(self, b):
        if b not in self.cache:
            im = Image.new('RGB', (16, 16), MESEN_RGB[0x0F])
            if b in self.shore:
                d = self.shore[b]
                quads = [(d['bank'], a) for a in d['addrs']]
                cs = self.colors[d['pal']]
            else:
                chr_ = self.m.blocks['chr']
                quads = [chr_.get(tn) for tn in self.m.tiles(b)]
                cs = self.colors[self.m.blocks['pal'].get(b, 0)]
            for q, src in enumerate(quads):
                if src:
                    o = src[0] * 0x4000 + (src[1] & 0x3FFF)
                    im.paste(tile(self.m.prg[o:o + 16], cs), ((q & 1) * 8, (q >> 1) * 8))
            self.cache[b] = im
        return self.cache[b]


SHORE_PTR = 0x80C2          # 08:$80B7: 필드면 블록 20~2F 의 2바이트 정의를 이 포인터(08:$8ABB)부터 차례로 올린다
WATERY = (0x00, 0x16, 0x0A)  # 0F:$D4CC: 물가 판정에서 물로 치는 필드 블록


def shore_defs(prg):
    p = dq4block.wd(prg, 0x08, SHORE_PTR)
    return {0x20 + i: dq4block.entry(prg, dq4block.rd(prg, 0x08, p + 2 * i), dq4block.rd(prg, 0x08, p + 2 * i + 1))
            for i in range(16)}


def field_block(m, x, y):
    """0F:$D478: 필드 블록 00(물)은 네 이웃이 물(WATERY)인지로 블록 20~2F 를 고른다(0F:$D4A8: 왼쪽·아래·오른쪽·위 순서로
    물이 아니면 1 을 밀어 넣어 bit3 왼쪽, bit2 아래, bit1 오른쪽, bit0 위). 필드 3 의 블록 01 은 난수가 FA 미만이면 18,
    아니면 19(반짝임)라 그림에는 18 을 쓴다."""
    b = m.cell(x, y) & 0x1F
    if b == 0:
        n = 0
        for dx, dy in ((-1, 0), (0, 1), (1, 0), (0, -1)):
            n = n << 1 | (m.cell((x + dx) & 0xFF, (y + dy) & 0xFF) & 0x1F not in WATERY)
        return 0x20 + n
    if b == 1 and m.f == 3:
        return 0x18
    return b


def field_map(prg, f):
    """dq4block.Map(필드)에 줄 끝까지(256칸)·아래로 세 줄 더 푼 격자를 넣는다. 0F:$D2AA 는 폭·높이 +2 칸까지 원래 좌표로
    찾으므로, 가장자리 칸의 물가를 고를 때 맵 밖 세 칸도 롬의 줄 데이터를 그대로 읽는다."""
    m = dq4block.Map(prg, field=f)
    m.field = [dq4field.decode_row(prg, f, y)[0] for y in range(m.h + 3)]
    return m


def cell_block(m, x, y):
    return field_block(m, x, y) if m.buf is None else m.cell(x, y) & 0x1F


def map_palette(m, night=False):
    clock = NIGHT if night else 0
    if m.buf is None:
        return dq4block.palette(m.prg, 0, clock=FIELD_NIGHT if night else 0, field=m.f)
    return dq4block.palette(m.prg, m.t, m.g, m.k, clock)


def render(m, night=False):
    """맵·필드 전체(칸마다 제 블록, 구역 가리기 없음) 1배 그림."""
    p = Painter(m, map_palette(m, night))
    im = Image.new('RGB', (m.w * 16, m.h * 16))
    for y in range(m.h):
        for x in range(m.w):
            im.paste(p.block(cell_block(m, x, y)), (x * 16, y * 16))
    return im


# ---- 장소 이름 ----

def place_names(prg, data):
    """그룹마다 이름. 롬에 그룹 → 이름 표가 없어서, 그 그룹 인물 대사에서 「ここは」「ようこそ」 뒤 30글자 안에
    장소 이름표(0B:$B634, ルーラ 목적지로 보이는 28개)의 이름이 처음 나온 것을 쓴다. 그 뒤에 「ほこら」「どうくつ」가
    이어지면 붙인다(예: 「ここは エンドールに つうじる たびのほこら」). 못 찾은 그룹은 빈 문자열."""
    rom = dq4text.Rom(data)
    names = place_list(prg)
    text = {}
    for g, k, *_ in all_maps(prg):
        for night in (False, True):
            for r in dq4talk.npc_list(prg, g, k, night):
                for msg in talk_msgs(prg, dq4talk.talk_id(r, night)):
                    text.setdefault(g, []).append(msg_text(rom, msg))
    out = {}
    for g in sorted(text):
        out[g] = ''
        for t in text[g]:
            t = t.replace('　', '').replace(' ', '').replace('\n', '')
            for m in re.finditer(r'(ここは|ようこそ)([^。！？]{0,30})', t):
                hit = [(m.group(2).find(n), n) for n in names if n in m.group(2)]
                if hit:
                    pos, n = min(hit)
                    rest = m.group(2)[pos + len(n):]
                    sub = next((s for s in ('ほこら', 'どうくつ') if s in rest), '')
                    out[g] = n + ('の' + sub if sub else '')
                    break
            if out[g]:
                break
    return out


def place_list(prg):
    return [dq4text.text(n) for n in dq4data.name_list(prg, 'place')[1:]]


def talk_msgs(prg, tid):
    """대화 번호 하나가 낼 수 있는 메시지 번호(조건 갈래 모두)."""
    c = dq4talk.classify(prg, tid)
    if c[0] == 'msg':
        return [c[1]]
    if c[0] == 'yesno':
        return list(c[1:4])
    if c[0] == 'service':
        return []
    return dq4talk.messages(c[2])


def msg_text(rom, msg):
    return dq4text.text(dq4text.shown(dq4text.message_bytes(rom, msg)))


def safe(name):
    return re.sub(r'[\\/:*?"<>| ]', '_', name)


# ---- 맵 ----

def map_records(prg, names):
    out = []
    for g, k, mid, bank, ptr in all_maps(prg):
        name = names.get(g, '')
        stem = f'{g:02X}-{k:02X}' + (f'-{safe(name)}' if name else '')
        out.append({'g': g, 'k': k, 'type': mid & 0x3F, 'code': mid, 'name': name, 'stem': stem})
    return out


FONT = None


def font():
    global FONT
    if FONT is None:
        FONT = ImageFont.load_default(9)
    return FONT


def mark(dr, x, y, color, label, inset=1):
    x0, y0 = x * 16 + inset, y * 16 + inset
    dr.rectangle([x0, y0, x0 + 15 - 2 * inset, y0 + 15 - 2 * inset], outline=color, width=2)
    if label:
        dr.text((x0 + 3, y0 + 2), label, fill=color, font=font(), stroke_width=1, stroke_fill=(0, 0, 0))


def cell_features(prg, m):
    """칸마다 블록 속성의 뜻(dq4block.terrain)에서 주석판에 그릴 것: 문(잠금 단계), 계단·출구 검사, 떨어지는 칸(목적지),
    리프트, 旅の扉, 움직이는 바닥, 데미지 바닥, タンス·つぼ(dq4block.pots 의 내용물), 팻말(dq4block.signs 의 메시지)."""
    g, k = m.g, m.k
    pots = {(p['x'], p['y']): p for p in dq4block.pots(prg) if (p['group'], p['index']) == (g, k)}
    signs = {}
    for sg in dq4block.signs(prg):
        signs.setdefault((sg['x'], sg['y']), []).append(sg)
    lifts = {}
    for lf in dq4block.lifts(prg):
        if lf['group'] != g:
            continue
        for here, there in ((lf['a'], lf['b']), (lf['b'], lf['a'])):
            if here['index'] == k:
                lifts[(here['x'], here['y'])] = there
    out, cache = [], {}
    for y in range(m.h):
        for x in range(m.w):
            prop = m.blocks['prop'].get(m.cell(x, y) & 0x1F, 0)
            if prop not in cache:
                cache[prop] = dq4block.terrain(prg, prop)
            t = cache[prop]
            f = {'x': x, 'y': y, 'prop': prop}
            eff = t.get('effect')
            if 'door' in t:
                f.update(kind='door', lock=t['door']['lock'])
            elif eff == 'exit':
                f['kind'] = 'exit'
            elif eff == 'fall':
                f.update(kind='fall', to=dq4block.fall(prg, g, k, x, y))
            elif eff == 'lift':
                f.update(kind='lift', to=lifts.get((x, y)))
            elif eff == 'travel_door':
                f['kind'] = 'travel_door'
            elif eff == 'conveyor':
                f.update(kind='conveyor', dir=t['dir'])
            elif eff == 'damage':
                f.update(kind='damage', hp=t['hp'])
            elif t.get('facing') in ('dresser', 'pot'):
                p = pots.get((x, y))
                f.update(kind=t['facing'], item=None if p is None else p['item'],
                         item_name=None if p is None else dq4chest.content_name(prg, p['item'], set()))
            elif t.get('facing') == 'sign':
                f.update(kind='sign', msg=[mm for sg in signs.get((x, y), []) for mm in sg['msg']])
            else:
                continue
            out.append(f)
    return out


def annotations(prg, g, k, m=None):
    """주석판에 그리는 것: 인물(낮·밤), 출구, 보물상자, 발밑 숨은 물건, 칸 속성으로 정해지는 것(cell_features)."""
    m = m or dq4block.Map(prg, g, k)
    day = [{'n': i, 'x': x, 'y': y, 'look': dq4talk.look(r), 'talk': dq4talk.talk_id(r)}
           for i, r in enumerate(dq4talk.npc_list(prg, g, k)) for x, y in [dq4talk.pos(r)]]
    night = [{'n': i, 'x': x, 'y': y, 'look': dq4talk.look(r, True), 'talk': dq4talk.talk_id(r, True)}
             for i, r in enumerate(dq4talk.npc_list(prg, g, k, True)) for x, y in [dq4talk.pos(r, True)]]
    exits = [{'x': e[0], 'y': e[1], 'to': f'{e[2]:02X}/{e[3]:02X}', 'at': [e[4], e[5]], 'flag': e[6]}
             for e in dq4map.exits(prg, g, k)]
    chests = [{'n': n, 'x': x, 'y': y, 'content': c, 'desc': d} for n, x, y, c, d in dq4chest.chests(prg, g, k) if x is not None]
    feet = [{'x': x, 'y': y, 'content': c, 'desc': d} for fg, fk, x, y, c, d, _ in dq4chest.feet_items(prg) if (fg, fk) == (g, k)]
    cells, falls = [], {}
    for c in cell_features(prg, m):
        if c['kind'] == 'fall':        # 탑 바깥처럼 넓게 깔리는 일이 많아 목적지마다 칸을 묶는다
            falls.setdefault(json.dumps(c['to'], sort_keys=True), []).append([c['x'], c['y']])
        else:
            cells.append(c)
    falls = [{'to': json.loads(t), 'cells': xy} for t, xy in falls.items()]
    return {'npcs': day, 'npcs_night': night, 'exits': exits, 'chests': chests, 'feet': feet, 'cells': cells, 'falls': falls}


# 칸 속성 주석: (색, 글자). 문은 D 뒤에 잠금 단계(0 열쇠 없음, 1~3 은 とうぞく·まほう·さいご の かぎ 이상)
CELL_MARK = {
    'door': ((255, 150, 0), 'D'), 'exit': ((0, 255, 120), 'S'), 'fall': ((255, 60, 160), 'H'), 'lift': ((120, 255, 255), 'L'),
    'travel_door': ((255, 255, 255), 'W'), 'damage': ((200, 255, 0), '!'), 'dresser': ((255, 200, 120), 'P'),
    'pot': ((255, 200, 120), 'P'), 'sign': ((220, 220, 255), 'N'), 'conveyor': ((150, 200, 255), ''),
}
ARROW = {'up': '^', 'right': '>', 'down': 'v', 'left': '<'}


def annotate(im, ann):
    """인물 노랑(번호), 밤 인물 보라, 출구 하늘색(목적지 그룹), 상자 빨강 T, 발밑 분홍 F, 칸 속성은 CELL_MARK.
    떨어지는 칸은 글자 없이 가는 분홍 테두리만."""
    im = im.copy()
    dr = ImageDraw.Draw(im)
    exits = {(e['x'], e['y']) for e in ann['exits']}
    for fl in ann.get('falls', []):
        for x, y in fl['cells']:
            dr.rectangle([x * 16 + 2, y * 16 + 2, x * 16 + 13, y * 16 + 13], outline=CELL_MARK['fall'][0], width=1)
    for c in ann.get('cells', []):
        if c['kind'] == 'exit' and (c['x'], c['y']) in exits:
            continue
        color, label = CELL_MARK[c['kind']]
        if c['kind'] == 'door':
            label += str(c['lock'])
        elif c['kind'] == 'conveyor':
            label = ARROW[c['dir']]
        mark(dr, c['x'], c['y'], color, label, 2)
    for e in ann['exits']:
        mark(dr, e['x'], e['y'], (0, 230, 255), e['to'][:2], 0)
    for c in ann['chests']:
        mark(dr, c['x'], c['y'], (255, 40, 40), 'T')
    for f in ann['feet']:
        mark(dr, f['x'], f['y'], (255, 120, 220), 'F')
    for n in ann['npcs_night']:
        if not any((d['x'], d['y']) == (n['x'], n['y']) for d in ann['npcs']):
            mark(dr, n['x'], n['y'], (170, 110, 255), f"{n['n']}", 3)
    for n in ann['npcs']:
        mark(dr, n['x'], n['y'], (255, 230, 0), f"{n['n']}", 3)
    return im


def do_maps(prg, out, names):
    d = Path(out) / 'maps'
    d.mkdir(parents=True, exist_ok=True)
    index = []
    for rec in map_records(prg, names):
        g, k = rec['g'], rec['k']
        m = dq4block.Map(prg, g, k)
        day = render(m)
        day.save(d / f"{rec['stem']}.png")
        rec.update(w=m.w, h=m.h)
        rec['night'] = map_palette(m, True) != map_palette(m)
        if rec['night']:
            render(m, True).save(d / f"{rec['stem']}-night.png")
        ann = annotations(prg, g, k, m)
        annotate(day, ann).save(d / f"{rec['stem']}-annot.png")
        rec['annot'] = ann
        index.append(rec)
    (d / 'index.json').write_text(json.dumps(index, ensure_ascii=False, indent=1))
    print(f'맵 {len(index)}개, 밤 팔레트가 다른 맵 {sum(r["night"] for r in index)}개 → {d}')
    return index


def do_field(prg, out, names):
    d = Path(out) / 'field'
    d.mkdir(parents=True, exist_ok=True)
    ents = dq4field.entrances(prg)
    index = []
    for f in FIELDS:
        m = field_map(prg, f)
        im = render(m)
        im.save(d / f'field{f}.png')
        night = map_palette(m, True) != map_palette(m)
        if night:
            render(m, True).save(d / f'field{f}-night.png')
        # 입구 표의 필드 번호는 도착 레코드에만 있다(08:$B7F9 bit6-5). 도착 레코드가 없는 입구는 필드 0 으로 친다.
        here = [e for e in ents if (e[7] or 0) == f]
        dr = ImageDraw.Draw(im)
        for g, fx, fy, *_ in here:
            mark(dr, fx, fy, (255, 230, 0), f'{g:02X}', 0)
        im.save(d / f'field{f}-annot.png')
        index.append({'field': f, 'w': m.w, 'h': m.h, 'night': night, 'note': FIELD_NOTE.get(f, ''),
                      'entrances': [{'group': g, 'name': names.get(g, ''), 'x': fx, 'y': fy,
                                     'to': None if k is None else f'{g:02X}/{k:02X}', 'at': None if k is None else [x, y]}
                                    for g, fx, fy, k, x, y, _, _ in here]})
    (d / 'index.json').write_text(json.dumps(index, ensure_ascii=False, indent=1))
    print(f'필드 {len(index)}개 → {d}')
    return index


# ---- gfx ----

def scaled(im, n):
    return im.resize((im.width * n, im.height * n), Image.NEAREST)


def block_sheet(prg, t, g=None, k=None):
    """맵 종류 t 의 블록 00~21 을 2배로, 칸마다 블록 번호와 속성 값. 블록 표는 맵에 안 쓰인 것까지 다 올린다."""
    m = dq4block.Map(prg, g, k) if g is not None else dq4block.Map(prg, field=0)
    if g is not None:
        m.blocks = dq4block.load(prg, t)
        dq4block.patch_props(prg, m.blocks['prop'], g, k)
    p = Painter(m, map_palette(m))
    cols, cw, ch = 8, 40, 52
    im = Image.new('RGB', (cols * cw, 5 * ch), (32, 32, 32))
    dr = ImageDraw.Draw(im)
    rows = []
    for b in range(0x22):
        x, y = b % cols * cw, b // cols * ch
        im.paste(scaled(p.block(b), 2), (x + 4, y + 2))
        prop = m.blocks['prop'].get(b) if b < 0x20 else None
        dr.text((x + 4, y + 35), f'{b:02X}' + ('' if prop is None else f' {prop:02X}'), fill=(230, 230, 230), font=font())
        rows.append({'block': b, 'prop': prop, 'name': '' if prop is None else dq4block.kind_name(prop),
                     'pal': m.blocks['pal'].get(b), 'kind': m.blocks['kind'].get(b)})
    return im, rows


def chr_sheet(prg, bank, colors):
    """PRG 뱅크 하나(16KB = 타일 1024개)를 32열로."""
    im = Image.new('RGB', (256, 256))
    o = bank * 0x4000
    for i in range(1024):
        im.paste(tile(prg[o + 16 * i:o + 16 * i + 16], colors), (i % 32 * 8, i // 32 * 8))
    return im


def bank_palette(prg, bank):
    """블록 정의에서 그 뱅크 그림을 가장 많이 쓰는 (맵 종류, 팔레트)의 색."""
    from collections import Counter
    cnt = Counter()
    types = sorted({m[2] & 0x3F for m in all_maps(prg)} | {0})
    for t in types:
        for d in dq4block.defs(prg, t).values():
            if d and d['bank'] == bank:
                cnt[(t, d['pal'])] += 1
    (t, p), _ = cnt.most_common(1)[0]
    rec = next((m for m in all_maps(prg) if m[2] & 0x3F == t), None)
    pal12 = dq4block.palette(prg, t, rec[0], rec[1]) if t and rec else dq4block.palette(prg, 0)
    return t, p, pal_rgb(pal12)[p]


def font_sheet(prg):
    """글자 바이트 00~8C 의 1비트 타일을 16열로(검은 바탕 흰 글자, 창과 같은 색)."""
    im = Image.new('RGB', (16 * 8, 9 * 8))
    o = FONT_AT[0] * 0x4000 + (FONT_AT[1] & 0x3FFF)
    for i in range(FONT_N):
        data = prg[o + 8 * i:o + 8 * i + 8] + bytes(8)
        im.paste(tile(data, [MESEN_RGB[0x0F], MESEN_RGB[0x30], MESEN_RGB[0x30], MESEN_RGB[0x30]]), (i % 16 * 8, i // 16 * 8))
    return im


def do_gfx(prg, out, maps_index=None):
    d = Path(out) / 'gfx'
    (d / 'blocks').mkdir(parents=True, exist_ok=True)
    maps_index = maps_index or [{'g': g, 'k': k, 'type': mid & 0x3F} for g, k, mid, *_ in all_maps(prg)]
    first = {}
    for r in maps_index:
        first.setdefault(r['type'], (r['g'], r['k']))
    sheets = {}
    im, rows = block_sheet(prg, 0)
    im.save(d / 'blocks' / 'type00-field.png')
    sheets['00'] = {'file': 'blocks/type00-field.png', 'map': 'field0', 'blocks': rows}
    for t in sorted(first):
        g, k = first[t]
        im, rows = block_sheet(prg, t, g, k)
        name = f'type{t:02X}.png'
        im.save(d / 'blocks' / name)
        sheets[f'{t:02X}'] = {'file': f'blocks/{name}', 'map': f'{g:02X}/{k:02X}', 'blocks': rows}
    (d / 'blocks' / 'index.json').write_text(json.dumps(sheets, ensure_ascii=False, indent=1))
    chrs = []
    for bank in (0x0C, 0x0D):
        scaled(chr_sheet(prg, bank, GRAY), 2).save(d / f'chr{bank:02X}-gray.png')
        t, p, cs = bank_palette(prg, bank)
        scaled(chr_sheet(prg, bank, cs), 2).save(d / f'chr{bank:02X}-color.png')
        chrs.append({'bank': f'{bank:02X}', 'gray': f'chr{bank:02X}-gray.png', 'color': f'chr{bank:02X}-color.png',
                     'palette': f'맵 종류 {t:02X} 팔레트 {p}'})
    scaled(font_sheet(prg), 4).save(d / 'font.png')
    (d / 'index.json').write_text(json.dumps({'chr': chrs, 'font': 'font.png'}, ensure_ascii=False, indent=1))
    print(f'블록 시트 {len(sheets)}장, CHR 뱅크 0C·0D, 폰트 {FONT_N}자 → {d}')


# ---- MesenCE 덤프 화면 ----

def dump_screen(d):
    """end.nt(2KB)·end.chr(8KB)·end.pal(32B)로 nametable 두 장(세로 미러링: 가로로 나란히)을 512×240 으로.
    BG 패턴 표는 .ppu($2000 값, fcgfxscene.lua)가 없으면 $1000(이 게임의 필드·창)으로 친다."""
    f = scene_files(os.path.join(d, 'end'))
    return nt_image(f['nt'], f['chr'], f['pal'], 0x1000 if f['ppu'] & 0x10 else 0)


def nt_image(nt, chr_, pal, base=0x1000):
    colors = [[MESEN_RGB[pal[0] & 0x3F]] + [MESEN_RGB[pal[4 * i + j] & 0x3F] for j in (1, 2, 3)] for i in range(4)]
    im = Image.new('RGB', (512, 240))
    for c in range(64):
        for r in range(30):
            tn = dq4block.nt_read(nt, c, r)
            p = dq4block.nt_pal(nt, c, r)
            im.paste(tile(chr_[base + 16 * tn:base + 16 * tn + 16], colors[p]), (c * 8, r * 8))
    return im


def rom_screen(prg, ram, wram, ppal=None):
    """RAM 의 장소·좌표·스크롤·구역·시각만 보고 롬에서 화면을 그린다(256×240). 0F:$EB23 처럼 화면의 (i, j) 번째 블록을
    nametable 의 (X/8 + 2i, Y/8 + 2j) 에 놓고 스크롤만큼 돌려 자른다. 돌려주는 것: 그림, 애니메이션 블록 자리 표시."""
    t = ram[0x28]
    m = field_map(prg, ram[0x65]) if t == 0 else dq4block.Map(prg, ram[0x63], ram[0x64])
    area = wram[0x1140] & 0xE0 if t else 0
    sx, sy = (ram[0x505] & 1) * 256 + ram[0x508], ram[0x509]
    pal12 = dq4block.palette(prg, t, ram[0x63], ram[0x64], wram[0x2ED], ram[0x65], wram[0x293])
    if ppal is not None:                 # 팔레트 순환(롬 팔레트와 덤프가 다른 맵)을 가려 보려고 덤프의 BG 팔레트를 씀
        pal12 = bytes(ppal[i] for i in range(16) if i & 3)
    p = Painter(m, pal12)
    anim = set(dq4block.anim_blocks(prg, t)) if t else set()
    full = Image.new('RGB', (512, 240), MESEN_RGB[0x0F])
    amask = Image.new('L', (512, 240), 0)
    for j in range(15):
        for i in range(16):
            x, y = (ram[0x7C] + i) & 0xFF, (ram[0x7B] + j) & 0xFF
            blk = field_block(m, x, y) if t == 0 else m.block(x, y, area, ram[0x7BA])
            c, r = (sx // 8 + 2 * i) % 64, (sy // 8 + 2 * j) % 30
            im = p.block(blk)
            for q in range(4):
                cc, rr = (c + (q & 1)) % 64, (r + (q >> 1)) % 30
                full.paste(im.crop(((q & 1) * 8, (q >> 1) * 8, (q & 1) * 8 + 8, (q >> 1) * 8 + 8)), (cc * 8, rr * 8))
                if blk in anim:
                    amask.paste(255, (cc * 8, rr * 8, cc * 8 + 8, rr * 8 + 8))

    def roll(src):
        h = Image.new(src.mode, (512, 240))
        h.paste(src.crop((sx, 0, 512, 240)), (0, 0))
        h.paste(src.crop((0, 0, sx, 240)), (512 - sx, 0))
        v = Image.new(src.mode, (512, 240))
        v.paste(h.crop((0, sy, 512, 240)), (0, 0))
        v.paste(h.crop((0, 0, 512, sy)), (0, 240 - sy))
        return v.crop((0, 0, 256, 240))
    return roll(full), roll(amask)


def sprite_mask(oam, tall=False):
    """OAM 64개 자리(tall 이면 8×16). Y 가 EF 이상이면 화면 밖. 이 게임은 $2000 bit5 가 0 이라 8×8 이다."""
    mask = Image.new('L', (256, 240), 0)
    dr = ImageDraw.Draw(mask)
    for i in range(64):
        y, x = oam[4 * i], oam[4 * i + 3]
        if y < 0xEF:
            dr.rectangle([x, y + 1, min(255, x + 7), min(239, y + (16 if tall else 8))], fill=255)
    return mask


def verify(prg, d, mask_sprites=False):
    """d 의 end.png(MesenCE 화면)와 롬만으로 그린 화면을 픽셀로 비교. 애니메이션 블록 자리는 뺀다.
    덤프는 MesenCE 에 --nes.disableSprites=true --nes.forceBackgroundFirstColumn=true 를 주고 뜬 것이어야 한다
    (스프라이트를 끄고 왼쪽 8픽셀도 BG 를 보이게). mask_sprites 면 OAM 자리를 빼고 비교한다(그 옵션 없이 뜬 덤프용).
    다르면 덤프의 BG 팔레트(end.pal)로 한 번 더 그려, 팔레트만 다른지(팔레트 순환) 따로 센다."""
    ram, wram, oam, ppal = (open(os.path.join(d, 'end.' + x), 'rb').read() for x in ('ram', 'sram', 'oam', 'pal'))
    shot = Image.open(os.path.join(d, 'end.png')).convert('RGB')
    smask = sprite_mask(oam) if mask_sprites else Image.new('L', (256, 240), 0)

    def count(mine, amask):
        sp, mp, ap, mk = shot.load(), mine.load(), amask.load(), smask.load()
        total = diff = skipped = 0
        first = None
        for y in range(240):
            for x in range(256):
                if mk[x, y] or ap[x, y]:
                    skipped += 1
                    continue
                total += 1
                if sp[x, y] != mp[x, y]:
                    diff += 1
                    first = first or (x, y)
        return total, diff, skipped, first
    mine, amask = rom_screen(prg, ram, wram)
    total, diff, skipped, first = count(mine, amask)
    where = f'{ram[0x63]:02X}/{ram[0x64]:02X}' if ram[0x28] else f'필드 {ram[0x65]}'
    msg = f'{d}: {where} 맵 종류 {ram[0x28]:02X}  비교 {total} 픽셀 중 {diff} 다름(뺀 것 {skipped})'
    if diff:
        mine.save(os.path.join(d, 'fcgfx-rom.png'))
        _, pdiff, _, _ = count(*rom_screen(prg, ram, wram, ppal))
        msg += f', 처음 {first}; 덤프 팔레트로 그리면 {pdiff} 다름'
    print(msg)
    return diff == 0


# ---- 갤러리 ----

GALLERY_CSS = """
:root { color-scheme: light dark; --bg: #f6f6f4; --fg: #1d1d1b; --mut: #6b6b66; --card: #ffffff; --line: #ddd; }
@media (prefers-color-scheme: dark) { :root { --bg: #161615; --fg: #e8e8e4; --mut: #9a9a94; --card: #22221f; --line: #3a3a36; } }
body { margin: 0; padding: 16px; background: var(--bg); color: var(--fg); font: 14px/1.5 system-ui, sans-serif; }
h1 { font-size: 20px; } h2 { font-size: 17px; margin-top: 28px; border-bottom: 1px solid var(--line); }
nav a { margin-right: 12px; }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 10px; }
.card { background: var(--card); border: 1px solid var(--line); border-radius: 6px; padding: 6px; }
.card img { width: 100%; height: 150px; object-fit: contain; image-rendering: pixelated; background: #000; }
.card .t { font-weight: 600; } .card .s { color: var(--mut); font-size: 12px; }
.wide img { max-width: 100%; image-rendering: pixelated; }
table { border-collapse: collapse; font-size: 12px; } td, th { border: 1px solid var(--line); padding: 2px 6px; }
details { margin: 6px 0; }
"""


def gallery(out):
    out = Path(out)
    maps = json.loads((out / 'maps' / 'index.json').read_text())
    fields = json.loads((out / 'field' / 'index.json').read_text())
    sheets = json.loads((out / 'gfx' / 'blocks' / 'index.json').read_text())
    gfx = json.loads((out / 'gfx' / 'index.json').read_text())
    screens = json.loads((out / 'gfx' / 'screens' / 'index.json').read_text()) if (out / 'gfx' / 'screens' / 'index.json').exists() else []
    e = html.escape
    h = ['<!doctype html><html lang="ko"><head><meta charset="utf-8">',
         '<meta name="viewport" content="width=device-width, initial-scale=1">',
         f'<title>DQ4 FC 그래픽</title><style>{GALLERY_CSS}</style></head><body>',
         '<h1>DQ4(FC) 원작 그래픽</h1>',
         '<nav><a href="#maps">맵</a><a href="#field">필드</a><a href="#blocks">블록</a><a href="#chr">CHR·폰트</a>'
         '<a href="#screens">화면</a><a href="sprites.html">스프라이트·몬스터</a></nav>',
         '<p>썸네일을 누르면 1배 원본이 열립니다. 주석판: 노랑 인물(번호), 보라 밤에만 있는 인물, 하늘색 출구(목적지 그룹), '
         '빨강 T 보물상자, 분홍 F 발밑 숨은 물건, 주황 D0~D3 문(잠금 단계: 0 열쇠 없음, 1 とうぞく, 2 まほう, 3 さいご), '
         '초록 S 계단·출구 검사 칸, 가는 분홍 테두리 떨어지는 칸, L 리프트, W 旅の扉, ! 데미지 바닥, ^&gt;v&lt; 움직이는 바닥, '
         'P タンス·つぼ, N 팻말. 목적지·내용물·메시지는 <a href="../maps/index.json">maps/index.json</a>.</p>',
         f'<h2 id="maps">마을·던전 맵 {len(maps)}개</h2><div class="grid">']
    for r in maps:
        base = f"../maps/{r['stem']}"
        links = [f'<a href="{e(base)}.png">낮</a>', f'<a href="{e(base)}-annot.png">주석</a>']
        if r['night']:
            links.append(f'<a href="{e(base)}-night.png">밤</a>')
        h.append(f'<div class="card"><a href="{e(base)}.png"><img loading="lazy" src="{e(base)}.png" alt=""></a>'
                 f'<div class="t">{r["g"]:02X}/{r["k"]:02X} {e(r["name"])}</div>'
                 f'<div class="s">맵 종류 {r["type"]:02X} · {r["w"]}×{r["h"]} · 인물 {len(r["annot"]["npcs"])} · '
                 f'출구 {len(r["annot"]["exits"])} · 상자 {len(r["annot"]["chests"])}</div><div class="s">{" ".join(links)}</div></div>')
    h.append('</div><h2 id="field">필드</h2>')
    for f in fields:
        base = f"../field/field{f['field']}"
        night = f' · <a href="{base}-night.png">밤</a>' if f['night'] else ''
        note = f' · {e(f["note"])}' if f.get('note') else ''
        h.append(f'<h3>필드 {f["field"]} ({f["w"]}×{f["h"]}) · <a href="{base}.png">원본</a> · <a href="{base}-annot.png">입구 주석</a>{night}{note}</h3>'
                 f'<div class="wide"><a href="{base}-annot.png"><img loading="lazy" src="{base}-annot.png" alt="" style="max-height:480px"></a></div>')
        if f['entrances']:
            h.append('<details><summary>입구 ' + str(len(f['entrances'])) + '곳</summary><table><tr><th>필드 칸</th><th>그룹</th><th>이름</th><th>도착</th></tr>')
            for en in f['entrances']:
                at = '' if en['at'] is None else f"{en['to']} ({en['at'][0]:02X},{en['at'][1]:02X})"
                h.append(f"<tr><td>({en['x']:02X},{en['y']:02X})</td><td>{en['group']:02X}</td><td>{e(en['name'])}</td><td>{at}</td></tr>")
            h.append('</table></details>')
    h.append(f'<h2 id="blocks">맵 종류별 블록 시트 {len(sheets)}장</h2><p>칸 아래 글자: 블록 번호, 속성(<code>$6F40</code>) 값. 블록 20·21 은 다른 구역을 가리는 블록.</p><div class="grid">')
    for t, s in sheets.items():
        h.append(f'<div class="card"><a href="../gfx/{s["file"]}"><img loading="lazy" src="../gfx/{s["file"]}" alt=""></a>'
                 f'<div class="t">맵 종류 {t}</div><div class="s">팔레트·속성은 {e(s["map"])} 기준</div>'
                 '<details><summary>속성</summary><table>'
                 + ''.join(f'<tr><td>{b["block"]:02X}</td><td>{"" if b["prop"] is None else format(b["prop"], "02X")}</td><td>{e(b["name"])}</td></tr>'
                           for b in s['blocks'] if b['prop'] is not None)
                 + '</table></details></div>')
    h.append('</div><h2 id="chr">CHR 뱅크·폰트</h2><div class="grid">')
    for c in gfx['chr']:
        for kind in ('gray', 'color'):
            h.append(f'<div class="card"><a href="../gfx/{c[kind]}"><img loading="lazy" src="../gfx/{c[kind]}" alt=""></a>'
                     f'<div class="t">뱅크 {c["bank"]} {"회색조" if kind == "gray" else "실제 팔레트"}</div>'
                     f'<div class="s">{"" if kind == "gray" else e(c["palette"])}</div></div>')
    h.append(f'<div class="card"><a href="../gfx/{gfx["font"]}"><img loading="lazy" src="../gfx/{gfx["font"]}" alt=""></a>'
             '<div class="t">폰트 141자</div><div class="s">18:$B840, 글자 바이트 00~8C. 창 테두리·커서(▶) 포함</div></div></div>')
    h.append('<h2 id="screens">장면 화면(MesenCE 덤프)</h2><p>롬에서 직접 푼 것이 아니라 MesenCE 의 nametable·CHR·팔레트 덤프를 그린 것. '
             '다른 픽셀은 스프라이트·움직이는 물결처럼 덤프와 화면 사이에 바뀐 것.</p><div class="grid">')
    for s in screens:
        h.append(f'<div class="card"><a href="../gfx/screens/{s["nt"]}"><img loading="lazy" src="../gfx/screens/{s["nt"]}" alt=""></a>'
                 f'<div class="t">{e(s["title"])}</div><div class="s">화면과 {s["diff"]} 픽셀 다름(스프라이트 자리 {s["masked"]} 뺌)</div>'
                 f'<div class="s"><a href="../gfx/screens/{s["nt"]}">nametable 512×240</a> · '
                 f'<a href="../gfx/screens/{s["bgchr"]}">BG 패턴</a> · <a href="../gfx/screens/{s["shot"]}">화면</a></div></div>')
    h.append('</div></body></html>')
    d = out / 'gallery'
    d.mkdir(parents=True, exist_ok=True)
    (d / 'index.html').write_text('\n'.join(h))
    print('갤러리 →', d / 'index.html')


def scene_files(prefix):
    """tools/lua/fc/fcgfxscene.lua 의 <prefix>.nt·chr·pal·oam·ppu·png, 또는 seq.lua 의 end.*(prefix = DIR/end)."""
    rd = {x: open(f'{prefix}.{x}', 'rb').read() for x in ('nt', 'chr', 'pal', 'oam', 'oam2') if os.path.exists(f'{prefix}.{x}')}
    rd['ppu'] = open(f'{prefix}.ppu', 'rb').read()[0] if os.path.exists(f'{prefix}.ppu') else 0x10
    return rd


def diff_count(a, b, mask=None):
    d = ImageChops.difference(a, b).convert('L').point(lambda v: 255 if v else 0)
    if mask is not None:
        d.paste(0, mask=mask)
    return d.histogram()[255]


def match_shot(full, shot, mask):
    """nametable 그림(512×240)에서 화면(256×240)과 가장 잘 맞는 스크롤 자리. 8픽셀 단위로 찾은 뒤 그 둘레를 1픽셀씩."""
    def crop(sx, sy):
        w = Image.new('RGB', (1024, 480))
        for dx in (0, 512):
            for dy in (0, 240):
                w.paste(full, (dx, dy))
        return w.crop((sx, sy, sx + 256, sy + 240))
    best = min((diff_count(crop(sx, sy), shot, mask), sx, sy) for sx in range(0, 512, 8) for sy in range(0, 240, 8))
    if best[0]:
        best = min([best] + [(diff_count(crop((best[1] + dx) % 512, (best[2] + dy) % 240), shot, mask), (best[1] + dx) % 512, (best[2] + dy) % 240)
                             for dx in range(-7, 8) for dy in range(-7, 8)])
    return best


def screens_from_dumps(out, dumps):
    """dumps = [(이름, 제목, prefix)]. nametable 두 장 그림, BG 패턴 표 시트, MesenCE 화면을 두고,
    화면과 nametable 그림을 스크롤 자리를 찾아 스프라이트 자리를 뺀 픽셀로 견준다."""
    d = Path(out) / 'gfx' / 'screens'
    d.mkdir(parents=True, exist_ok=True)
    idx = []
    for name, title, prefix in dumps:
        f = scene_files(prefix)
        base = 0x1000 if f['ppu'] & 0x10 else 0
        full = nt_image(f['nt'], f['chr'], f['pal'], base)
        full.save(d / f'{name}-nt.png')
        sheet = Image.new('RGB', (128, 128))
        colors = [MESEN_RGB[f['pal'][j] & 0x3F] for j in range(4)]
        for i in range(256):
            sheet.paste(tile(f['chr'][base + 16 * i:base + 16 * i + 16], colors), (i % 16 * 8, i // 16 * 8))
        scaled(sheet, 2).save(d / f'{name}-bgchr.png')
        shot = Image.open(f'{prefix}.png').convert('RGB')
        shot.save(d / f'{name}-shot.png')
        mask = None
        for o in ('oam', 'oam2'):
            if o in f:
                m = sprite_mask(f[o], tall=bool(f['ppu'] & 0x20))
                mask = m if mask is None else ImageChops.lighter(mask, m)
        n, sx, sy = match_shot(full, shot, mask)
        masked = 0 if mask is None else mask.histogram()[255]
        print(f'{name}: 화면 {256 * 240 - masked} 픽셀(스프라이트 자리 {masked} 뺌) 중 {n} 다름, 스크롤 ({sx},{sy})')
        idx.append({'name': name, 'title': title, 'nt': f'{name}-nt.png', 'bgchr': f'{name}-bgchr.png', 'shot': f'{name}-shot.png',
                    'scroll': [sx, sy], 'diff': n, 'masked': masked})
    (d / 'index.json').write_text(json.dumps(idx, ensure_ascii=False, indent=1))
    print(f'장면 {len(idx)}개 → {d}')


def source_txt(out, sub, cmd, rom, note=''):
    try:
        rev = subprocess.run(['git', 'rev-parse', 'HEAD'], capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        rev = '?'
    sha = hashlib.sha1(rom).hexdigest()
    (Path(out) / sub).mkdir(parents=True, exist_ok=True)
    (Path(out) / sub / 'SOURCE.txt').write_text(
        f'sfc-dq4 커밋: {rev}\n명령: {cmd}\n롬: FC 「ドラゴンクエストIV」 일본판 Rev A, SHA-1 {sha}\n' + (f'비고: {note}\n' if note else ''))


def main():
    a = sys.argv
    if len(a) < 4 and not (len(a) == 3 and a[2] == 'gallery'):
        print(__doc__)
        sys.exit(2)
    data = Path(a[1]).read_bytes()
    prg = ines.prg(data)
    cmd = a[2]
    if cmd == 'verify':
        dirs = [d for d in a[3:] if not d.startswith('--')]
        missing = [d for d in dirs if not os.path.exists(os.path.join(d, 'end.png'))]
        if missing:
            print('덤프 없음:', ' '.join(missing))
        ok = [verify(prg, d, '--mask-sprites' in a) for d in dirs if d not in missing]
        print(f'{len(ok)}개 중 {sum(ok)}개 같음')
        sys.exit(0 if all(ok) else 1)
    if cmd == 'screen':
        dump_screen(a[3]).save(a[4])
        return
    if cmd == 'scenes':
        spec = json.loads(Path(a[4]).read_text())
        screens_from_dumps(a[3], [(x['name'], x['title'], x['prefix']) for x in spec])
        source_txt(a[3], 'gfx/screens', 'uv run --locked python tools/dq4fcgfx.py rom/dq4.nes scenes $OUT ' + a[4], data,
                   note='MesenCE 덤프(tools/lua/fc/fcgfxscene.lua)를 렌더링한 것. 롬에서 직접 푼 것이 아님')
        return
    if cmd == 'map':
        m = dq4block.Map(prg, int(a[3], 16), int(a[4], 16))
        im = render(m, '--night' in a)
        if '--annot' in a:
            im = annotate(im, annotations(prg, m.g, m.k))
        im.save(a[5])
        return
    if cmd == 'gallery':
        gallery(a[3])
        source_txt(a[3], 'gallery', 'uv run --locked python tools/dq4fcgfx.py rom/dq4.nes gallery $OUT', data)
        return
    out = a[3]
    names = place_names(prg, data) if cmd in ('all', 'maps', 'field') else {}
    line = 'uv run --locked python tools/dq4fcgfx.py rom/dq4.nes ' + ' '.join(['$OUT' if x == out else x for x in a[2:]])
    idx = None
    if cmd in ('all', 'maps'):
        idx = do_maps(prg, out, names)
        source_txt(out, 'maps', line, data)
    if cmd in ('all', 'field'):
        do_field(prg, out, names)
        source_txt(out, 'field', line, data)
    if cmd in ('all', 'gfx'):
        do_gfx(prg, out, idx)
        source_txt(out, 'gfx', line, data)
    if cmd == 'all':
        gallery(out)
        source_txt(out, 'gallery', line, data)


if __name__ == '__main__':
    main()
