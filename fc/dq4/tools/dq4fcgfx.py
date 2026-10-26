"""DQ4(FC) 원작 그래픽 렌더러: 마을·던전 맵 279개, 필드, 블록·CHR·폰트 시트, MesenCE 덤프 화면. 쓰는 법은 fc/dq4/docs/dq4-fcgfx.md.

사용:
  python fc/dq4/tools/dq4fcgfx.py rom/dq4.nes all OUT                맵·필드·gfx 를 OUT/{maps,field,gfx} 에, 갤러리를 OUT/gallery 에
  python fc/dq4/tools/dq4fcgfx.py rom/dq4.nes maps|field|gfx OUT     하나만
  python fc/dq4/tools/dq4fcgfx.py rom/dq4.nes map G K OUT.png [--night|--annot]  맵 하나
  python fc/dq4/tools/dq4fcgfx.py rom/dq4.nes screen DIR OUT.png     seq.lua·warp.lua 의 end.nt·chr·pal 로 nametable 두 장(512×240)
  python fc/dq4/tools/dq4fcgfx.py rom/dq4.nes scenes OUT SPEC.json    fcgfxscene.lua 덤프 목록([{name, title, prefix}])을 OUT/gfx/screens 에(있는 목록에 더함)
      항목에 ppulog(fcgfxscroll.lua 의 ppulog.txt)·mirror(v|h)·frame 을 주면 그 프레임의 줄 스크롤로 화면을 그려 견줌
  python fc/dq4/tools/dq4fcgfx.py rom/dq4.nes verify DIR... [--mask-sprites]  롬만으로 그린 화면과 end.png 를 픽셀로 비교
  python fc/dq4/tools/dq4fcgfx.py rom/dq4.nes gallery OUT            OUT/gallery/index.html 만 다시

출력은 롬 그래픽이라 공개 저장소에 커밋하지 않는다(비공개 에셋 저장소나 work/ 에만).
맵은 칸마다 제 블록으로 그린다(게임은 주인공과 다른 구역을 블록 20·21 로 가리지만 참고용 그림에서는 다 보이게).
색은 MesenCE 화면에서 잰 값(MESEN_RGB, fc/dq4/tools/lua/fcgfxpal.lua)이다.
"""
import hashlib
import html
import json
import os
import re
import subprocess
import sys
from collections import deque
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

# NES 색 번호 00~3F → MesenCE 기본 팔레트의 화면 RGB. fc/dq4/tools/lua/fcgfxpal.lua 로 색마다 화면 전체를 칠해 잰 값.
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
FIELDS = dq4field.FIELDS     # $65 에 쓰이는 필드. 2 는 줄 포인터가 롬 밖을 가리키는 빈 자리
FIELD_NOTE = {3: '용암·물 팔레트가 돌아감. 그림은 롬의 첫 팔레트'}
FONT_AT, FONT_N = (0x18, 0xB840), 141   # 글자 바이트 00~8C 의 1비트 타일(fc/dq4/docs/dq4-text-format.md)


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


def field_block(m, x, y, sparkle=False):
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
        return 0x19 if sparkle else 0x18
    return b


def cell_block(m, x, y):
    return field_block(m, x, y) if m.buf is None else m.cell(x, y) & 0x1F


def map_palette(m, night=False):
    clock = NIGHT if night else 0
    if m.buf is None:
        return dq4block.palette(m.prg, 0, clock=FIELD_NIGHT if night else 0, field=m.f)
    return dq4block.palette(m.prg, m.t, m.g, m.k, clock)


def render(m, night=False):
    """맵·필드 전체(칸마다 제 블록, 구역 가리기 없음) 1배 그림. 필드는 좌표 (0,0)부터 줄 데이터가 있는 데까지
    (dq4field.extent: 폭·높이 +3, 필드 3 은 62×54)라 그림의 칸 자리가 곧 $42/$43 이다."""
    p = Painter(m, map_palette(m, night))
    w, h = dq4field.extent(m.prg, m.f) if m.buf is None else (m.w, m.h)
    im = Image.new('RGB', (w * 16, h * 16))
    for y in range(h):
        for x in range(w):
            im.paste(p.block(cell_block(m, x, y)), (x * 16, y * 16))
    return im


# ---- 장소 이름 ----

PLACE_NOUN = r'(むら|まち|おしろ|しろ|ほこら|どうくつ|とう|さと|いえ|しま|くに|ドック|みやこ)'
COPULA = r'(なるぞ|だよ|です|だ|じゃ|よ|ね)$'


def place_table(prg, data):
    """그룹마다 {'name', 'src'}. 롬에 그룹 → 이름 표는 없어서 여러 군데서 차례로 찾는다.
    1. 'rula': ルーラ 목적지 레코드(dq4field.places)가 이름표(0B:$B634)의 순번과 같은 순서이고, 필드 자리가 입구 표의
       한 그룹과 2칸 안에 있거나 맵 레코드가 그룹을 바로 적는다.
    2. 'talk': 그 그룹 인물 대사(낮·밤, 조건 갈래 전부)에서 「ここは」「ようこそ」 뒤 30글자 안에 이름표의 이름이 처음
       나온 것. 뒤에 「ほこら」「どうくつ」가 이어지면 붙인다(예: 「ここは エンドールに つうじる たびのほこら」).
    3. 'talk-phrase': 「ここは X」의 X(끝의 だ·です 따위를 떼고)가 장소 이름씨(PLACE_NOUN)로 끝나거나 가타카나가 든
       8글자 이하이면 그중 가장 짧은 것(예: 13 「サラン」, 20 「きこりのいえ」).
    4. 'talk-kind': 「この とう」「この どうくつ」처럼 그 장소를 가리키는 말만 있으면 그 말(이름이 아니라 갈래).
    4.5 'talk-dir': 다른 그룹 대사의 「きたの どうくつ」처럼 방위로 가리키는 말을 필드 자리로 이어 붙인다(dir_names).
    5. 'link': 남은 그룹이 필드를 거치지 않는 출구(place_links)로 1~3 의 이름이 붙은 그룹과 이어져 있으면 가장 가까운
       그룹의 이름. 거리가 같은데 이름이 다른 그룹이 있으면 붙이지 않는다. 'via' 에 거쳐 간 출구를 적는다
       (예: 2C 「てんくうじょう」 ← 2C/10 (03,05) → 2D/00). 4 는 갈래라 퍼뜨리지 않는다.
    6. 'near': 그래도 남은 그룹은 이름이 아니라 자리 표시다. 필드 입구(dq4field.entrances)가 있으면 같은 필드에서
       1~3 의 이름이 붙은 그룹 입구 중 가장 가까운(맨해튼 거리) 것의 이름에 「ちかく」를 붙이고 'near' 에
       (필드, X, Y, 거리, 그 그룹)을 적는다. 가장 가까운 것이 둘 이상이고 이름이 다르면 붙이지 않는다.
    7. 'link': 필드 입구가 없는 그룹은 5 와 같이 출구로 이어진 가장 가까운 6 의 그룹 이름을 받는다.
    6·7 은 게임 속 이름이 아니라서 'label' 을 켜 두고, 파일 이름에는 쓰지 않는다(에셋 저장소 규칙).
    못 찾은 그룹은 넣지 않는다."""
    rom = dq4text.Rom(data)
    names = place_list(prg)
    text, said = {}, {}
    for g, k, *_ in all_maps(prg):
        for night in (False, True):
            for r in dq4talk.npc_list(prg, g, k, night):
                for msg in talk_msgs(prg, dq4talk.talk_id(r, night)):
                    t = msg_text(rom, msg).replace('　', '').replace(' ', '').replace('\n', '')
                    text.setdefault(g, []).append(t)
                    said.setdefault(g, {}).setdefault(msg, t)
    out = {}
    for e in dq4field.places(prg):
        if e['name'] and e['group'] is not None:
            out.setdefault(e['group'], {'name': e['name'], 'src': 'rula'})
    for g in sorted(text):
        if g in out:
            continue
        for t in text[g]:
            for m in re.finditer(r'(ここは|ようこそ)([^。！？]{0,30})', t):
                hit = [(m.group(2).find(n), n) for n in names if n in m.group(2)]
                if hit:
                    pos, n = min(hit)
                    rest = m.group(2)[pos + len(n):]
                    sub = next((s for s in ('ほこら', 'どうくつ') if s in rest), '')
                    out[g] = {'name': n + ('の' + sub if sub else ''), 'src': 'talk'}
                    break
            if g in out:
                break
        if g in out:
            continue
        phrases = set()
        for t in text[g]:
            for m in re.finditer(r'ここは([^。！？…]{1,24})', t):
                x = re.sub(COPULA, '', m.group(1))
                if re.search(PLACE_NOUN + '$', x) or (re.search(r'[ァ-ヴ]', x) and len(x) <= 8):
                    phrases.add(x)
        if phrases:
            out[g] = {'name': min(phrases, key=lambda x: (len(x), x)), 'src': 'talk-phrase'}
            continue
        kinds = {m.group(1) for t in text[g] for m in re.finditer(r'この(とうだい|とう|どうくつ|ほこら)', t)}
        if kinds:
            out[g] = {'name': min(kinds, key=lambda x: (len(x), x)), 'src': 'talk-kind'}
    out.update(dir_names(prg, said, out))
    out.update(link_names(prg, out))
    out.update(near_names(prg, out))
    out.update({g: v | {'label': True} for g, v in link_names(prg, out, ('near',)).items()})
    return out


DIRS = {'ひがし': (1, 0), 'にし': (-1, 0), 'みなみ': (0, 1), 'きた': (0, -1)}
DIR_RE = re.compile(r'(ひがし|にし|みなみ|きた)(?:に|の)(?:ある|あるという)?(とうだい|とう|どうくつ|ほこら)')


def dir_names(prg, said, names):
    """place_table 4.5 단계 'talk-dir': 그룹 H 인물 대사의 「きたの どうくつ」처럼 방위 + 장소 이름씨를 H 의 필드 입구에서
    그 방위 45도 안(앞으로 간 거리 ≥ 옆 거리)에 입구가 있는 그룹 중 맨해튼 거리가 가장 가까운 것에 붙인다. 후보는 이름이
    없는 그룹과, 'talk-kind' 가 같은 이름씨인 그룹뿐이다(마을·성은 이름씨가 달라 뺀다). 가장 가까운 것이 둘이거나, 한 그룹에
    다른 이름이 둘 모이면 붙이지 않는다. 'dir' 에 (H, 메시지, dx, dy)를 적는다."""
    ents = dq4field.entrances(prg)
    pos = {}
    for e in ents:
        pos.setdefault(e[0], []).append((e[7] or 0, e[1], e[2]))
    hits = {}
    for h in sorted(said):
        if h not in pos:
            continue
        f, hx, hy = pos[h][0]
        for msg, t in sorted(said[h].items()):
            for m in DIR_RE.finditer(t):
                (ux, uy), noun = DIRS[m.group(1)], m.group(2)
                cand = []
                for g, es in pos.items():
                    v = names.get(g)
                    if g == h or (v and not (v['src'] == 'talk-kind' and v['name'] == noun)):
                        continue
                    for ff, x, y in es:
                        dx, dy = x - hx, y - hy
                        along, side = dx * ux + dy * uy, abs(dx * uy - dy * ux)
                        if ff == f and along > 0 and side <= along:
                            cand.append((abs(dx) + abs(dy), g, dx, dy))
                cand.sort()
                if not cand or (len(cand) > 1 and cand[1][0] == cand[0][0] and cand[1][1] != cand[0][1]):
                    continue
                _, g, dx, dy = cand[0]
                hits.setdefault(g, {}).setdefault(m.group(1) + 'の' + noun, (h, msg, dx, dy))
    return {g: {'name': n, 'src': 'talk-dir', 'dir': v} for g, d in hits.items() if len(d) == 1 for n, v in d.items()}


def near_names(prg, names):
    """place_table 6 단계: 이름 없는 그룹의 필드 입구마다 가장 가까운 1~3 단계 그룹 입구."""
    ents = dq4field.entrances(prg)
    out = {}
    for g in sorted({e[0] for e in ents}):
        if g in names:
            continue
        best = []
        for e in (e for e in ents if e[0] == g):
            f = e[7] or 0
            for h in dq4field.entrances_on(ents, f):
                if names.get(h[0], {}).get('src') in NAMED:
                    best.append((abs(h[1] - e[1]) + abs(h[2] - e[2]), names[h[0]]['name'], f, h[1], h[2], h[0]))
        if not best:
            continue
        best.sort()
        if len({b[1] for b in best if b[0] == best[0][0]}) != 1:
            continue
        d, n, f, x, y, h = best[0]
        out[g] = {'name': n + 'ちかく', 'src': 'near', 'near': (f, x, y, d, h), 'label': True}
    return out


def place_links(prg):
    """필드를 거치지 않고 그룹끼리 잇는 출구: {그룹: {이웃 그룹: [(그룹, 순번, X, Y, 그룹, 순번, 표)]}}, 방향 없이.
    연결 표(1B:$8223, dq4map.links)와 계단 칸 표(08:$B22E, dq4block.exit_links)를 함께 본다. 필드로 나가는 칸과
    필드 도착 자리(08:$B7F9)로 보내는 칸은 필드를 거치는 것이라 뺀다."""
    adj = {}

    def add(g1, k1, x, y, g2, k2, src):
        if g1 != g2:
            e = (g1, k1, x, y, g2, k2, src)
            adj.setdefault(g1, {}).setdefault(g2, []).append(e)
            adj.setdefault(g2, {}).setdefault(g1, []).append(e)
    for a, b in dq4map.links(prg):
        add(a[0], a[1], a[2], a[3], b[0], b[1], '1B:$8223')
    cache = {}
    for g, k, *_ in all_maps(prg):
        for e in dq4block.exit_links(prg, g, k, cache):
            t = e['to']
            if t and 'group' in t and 'field' not in t and not t.get('invalid'):
                add(g, k, e['x'], e['y'], t['group'], t['index'], '08:$B22E')
    return adj


NAMED = ('rula', 'talk', 'talk-phrase')


def link_names(prg, names, srcs=NAMED):
    """place_table 5·7 단계: names 에 없는 그룹마다 너비 우선으로 src 가 srcs 인 가장 가까운 그룹을 찾는다."""
    adj = place_links(prg)
    out = {}
    for g in sorted(adj):
        if g in names:
            continue
        prev, q, found, best = {g: None}, deque([(g, 0)]), [], None
        while q:
            h, d = q.popleft()
            if best is not None and d > best:
                break
            if h != g and names.get(h, {}).get('src') in srcs:
                best = d
                found.append(h)
                continue
            for n in adj[h]:
                if n not in prev:
                    prev[n] = h
                    q.append((n, d + 1))
        if len({names[h]['name'] for h in found}) != 1:
            continue
        h, via = found[0], []
        while prev[h] is not None:
            a, b, x, y, c, k, src = adj[prev[h]][h][0]
            via.append(f'{a:02X}/{b:02X} ({x:02X},{y:02X}) → {c:02X}/{k:02X} {src}')
            h = prev[h]
        out[g] = {'name': names[found[0]]['name'], 'src': 'link', 'via': via[::-1]}
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
        name, src = names.get(g, {}).get('name', ''), names.get(g, {}).get('src', '')
        label = names.get(g, {}).get('label', False)
        stem = f'{g:02X}-{k:02X}' + (f'-{safe(name)}' if name and not label else '')
        rec = {'g': g, 'k': k, 'type': mid & 0x3F, 'code': mid, 'name': name, 'name_src': src, 'stem': stem}
        if 'via' in names.get(g, {}):
            rec['name_via'] = names[g]['via']
        if 'dir' in names.get(g, {}):
            h, msg, dx, dy = names[g]['dir']
            rec['name_dir'] = {'group': h, 'message': f'{msg:04X}', 'dx': dx, 'dy': dy}
        if 'near' in names.get(g, {}):
            f, x, y, d, h = names[g]['near']
            rec['name_near'] = {'field': f, 'x': x, 'y': y, 'distance': d, 'group': h}
        out.append(rec)
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
        m = dq4block.Map(prg, field=f)
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
        index.append({'field': f, 'w': m.w, 'h': m.h, 'image_cells': list(dq4field.extent(prg, f)), 'night': night, 'note': FIELD_NOTE.get(f, ''),
                      'entrances': [{'group': g, 'name': names.get(g, {}).get('name', ''), 'x': fx, 'y': fy,
                                     'to': None if k is None else f'{g:02X}/{k:02X}', 'at': None if k is None else [x, y]}
                                    for g, fx, fy, k, x, y, _, _ in here]})
    (d / 'index.json').write_text(json.dumps(index, ensure_ascii=False, indent=1))
    print(f'필드 {len(index)}개 → {d}')
    return index


# ---- gfx ----

def block_sheet(prg, t, g=None, k=None):
    """맵 종류 t 의 블록 00~21 을 1배로 8열(128×80). 블록 번호·속성 값은 그림에 쓰지 않고 rows 로 돌려준다.
    블록 표는 맵에 안 쓰인 것까지 다 올린다."""
    m = dq4block.Map(prg, g, k) if g is not None else dq4block.Map(prg, field=0)
    if g is not None:
        m.blocks = dq4block.load(prg, t)
        dq4block.patch_props(prg, m.blocks['prop'], g, k)
    p = Painter(m, map_palette(m))
    im = Image.new('RGB', (8 * 16, 5 * 16), MESEN_RGB[0x0F])
    rows = []
    for b in range(0x22):
        im.paste(p.block(b), (b % 8 * 16, b // 8 * 16))
        prop = m.blocks['prop'].get(b) if b < 0x20 else None
        rows.append({'block': b, 'x': b % 8 * 16, 'y': b // 8 * 16, 'prop': prop,
                     'name': '' if prop is None else dq4block.kind_name(prop),
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
    im.save(d / 'blocks' / '00.png')
    sheets['00'] = {'file': 'blocks/00.png', 'map': 'field0', 'blocks': rows}
    for t in sorted(first):
        g, k = first[t]
        im, rows = block_sheet(prg, t, g, k)
        name = f'{t:02X}.png'
        im.save(d / 'blocks' / name)
        sheets[f'{t:02X}'] = {'file': f'blocks/{name}', 'map': f'{g:02X}/{k:02X}', 'blocks': rows}
    (d / 'blocks' / 'index.json').write_text(json.dumps(sheets, ensure_ascii=False, indent=1))
    chrs = []
    for bank in (0x0C, 0x0D):
        chr_sheet(prg, bank, GRAY).save(d / 'blocks' / f'chr-{bank:02X}-gray.png')
        t, p, cs = bank_palette(prg, bank)
        chr_sheet(prg, bank, cs).save(d / 'blocks' / f'chr-{bank:02X}.png')
        chrs.append({'bank': f'{bank:02X}', 'gray': f'blocks/chr-{bank:02X}-gray.png', 'color': f'blocks/chr-{bank:02X}.png',
                     'palette': f'맵 종류 {t:02X} 팔레트 {p}', 'rom': f'{bank:02X}:$8000-$BFFF'})
    font_sheet(prg).save(d / 'font.png')
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


def field_cycle(pal12, f, n):
    """1D:$8B1E(1D 함수 0)가 필드에서 $3C(프레임 수)&0F 가 0F 일 때마다, 곧 16프레임마다 한 번 바꾸는 BG 팔레트를 n 번 돌린
    화면 쪽(PPU) 12바이트. 모든 필드에서 팔레트 0 의 색 2·3($05FE·$05FF, 물결)을 맞바꾸고, 필드 3 은 팔레트 3 의 색 1~3
    ($0606~$0608, 용암)을 $0606←$0608, $0608←$0607, $0607←$0606 으로 돌린다($8B87). 주기는 32·48프레임.
    $8B87 은 PPU $3F0D~$3F0F 에 $0606, $0608, $0607 순서로 써서, 한 번이라도 돌린 뒤의 화면 색은 RAM 순서와 다르다."""
    p = bytearray(pal12)
    for _ in range(n):
        p[1], p[2] = p[2], p[1]
        if f == 3:
            p[9], p[10], p[11] = p[11], p[9], p[10]
    if n and f == 3:
        p[10], p[11] = p[11], p[10]
    return bytes(p)


def falls_cycle(pal12, n):
    """맵 종류 18(폭포, 3B/00): 같은 1D:$8B1E 가 4프레임마다 팔레트 2 의 색 1~3($0603~$0605)을 $0605←$0604←$0603←$0605
    로 돌리고($8C18, 폭포가 흐르는 것), 16프레임마다 팔레트 1 의 색 1·2($0600·$0601)를 맞바꾼다($8BF3). 둘은 따로 돌므로
    n 을 (돌린 수 n%3, 맞바꿈 n//3) 조합으로 센다. 타일 그림·nametable 은 그대로다."""
    p = bytearray(pal12)
    for _ in range(n % 3):
        p[6], p[7], p[8] = p[8], p[6], p[7]
    if n // 3 % 2:
        p[3], p[4] = p[4], p[3]
    return bytes(p)


FIELD_PHASES = 6   # 필드: 물결 2단계 × 용암 3단계, 폭포: 흐름 3단계 × 물결 2단계
CYCLED = (0x00, 0x18)
GATE_SRC = (0x8929, 0x8D29)  # 1B:$889C: 성문 연출(1B:$870D) 그림의 시작. 1E:$8F42 가 맵 종류 32 면 뒤의 것을 고른다


def gate_chunks(prg, ram, wram):
    """성문 연출(1B:$870D)이 지금까지 BG CHR-RAM 에 쓴 $40 바이트 조각 [(PPU 주소, PRG 오프셋)](오래된 것부터),
    연출이 아직 도는지, 성문 블록 넷. 연출은 단계 $57(0~3, $56 = 8×단계)마다 조각 4개($55 = 1~4, 다음 단계 첫 조각
    전에는 0)를 $53/$54 에서 $0300 큐로 보내고(1B:$8871), 마지막 단계 뒤에는 $57 = 4, $55 = 4 로 멈춘다. PPU 주소는
    1B:$881D 가 성문 블록 $0540·$0541 로 만든 WRAM 표 $7700 의 (($55×2 + $56) & $0E) 번째다. 연출 밖에서도 $53~$57 은
    다른 데 쓰이므로, 그 넷이 이 단계표와 맞고 $53/$54 를 되짚은 시작이 1B:$889C 의 값일 때만 연출 중으로 본다.
    마지막 단계는 조각을 성문 블록의 원래 타일 자리에 쓰고 $7600 을 롬 정의로 되돌리므로, 연출이 끝나 $53~$57 이
    덮이고 $0540 이 FF 로 지워진 뒤에도(02/00) 그 맵을 나갈 때까지 CHR 에 열린 그림이 남는다. 그때는 롬 속성이
    A0·A2(성문)인 블록 넷의 속성($6F40 + 블록)이 1B:$885F 가 바꾼 80·80·24·24 이면 조각 16개를 모두 쓴 것으로 본다.
    02/00 에 들어올 때는 1E:$8F63 이 $0541 에 발밑 블록을 두고 화면을 일행 자리로 다시 그린 뒤에야 $0540 과
    $53~$57 을 정하므로, 그 사이(성문 속성이 아직 롬 값)와 첫 조각 전($57 = $55 = 0)도 조각 0개로 연출 중이다."""
    if not ram[0x28]:
        return [], False, ()
    step, n = ram[0x57], ram[0x55]
    done = min(4 * step + n, 16)
    base = (ram[0x53] | ram[0x54] << 8) - 0x40 * done
    running = (ram[0x540] != 0xFF and step <= 4 and n <= 4 and ram[0x56] == 8 * step and base in GATE_SRC)
    if running:
        gate = (ram[0x540], ram[0x540] + 1, ram[0x541], ram[0x541] + 1)
    else:
        prop = dq4block.Map(prg, ram[0x63], ram[0x64]).blocks['prop']
        gate = tuple(sorted(b for b, v in prop.items() if v in (0xA0, 0xA2)))
        if len(gate) != 4:
            return [], False, ()
        attr = [wram[0xF40 + b] for b in gate]
        if ram[0x540] == 0xFF and ram[0x541] in gate and attr == [prop[b] for b in gate]:
            return [], True, gate
        if attr != [0x80, 0x80, 0x24, 0x24]:
            return [], False, ()
        done, base = 16, GATE_SRC[ram[0x28] == 0x32]
    out = []
    for i in range(done):
        x = (i // 4 * 8 + i % 4 * 2) & 0x0E
        ppu = wram[0x1700 + x] | wram[0x1701 + x] << 8
        out.append((ppu, 0x1B * 0x4000 + base + 0x40 * i - 0x8000))
    return out, running, gate


def gate_map(m, wram, chunks, gate, shown=None):
    """성문 연출 중이거나 연 뒤의 맵: 조각이 덮어쓴 타일을 그 조각 그림으로, 성문 블록 넷의 타일을 1B:$8772 가 바꿔
    놓은 WRAM 블록 → 타일 표 $7600 의 값으로. 1B:$8772 는 단계 $57 의 bit0 으로 $7710 의 두 벌(16바이트씩) 중
    하나를 $7600 에 옮긴다. shown 이 있으면 $7600 대신 그 벌을 쓴다."""
    chr_, tiles = dict(m.blocks['chr']), dict(m.blocks['tiles'])
    for ppu, off in chunks:
        for t in range(4):
            o = off + 16 * t
            chr_[(ppu - 0x1000) // 16 + t] = (o // 0x4000, 0x8000 | o & 0x3FFF)
    for b in gate:
        tiles[b] = list(wram[0x1600 + 4 * b:0x1604 + 4 * b])
    if shown is not None:
        for i, b in enumerate(gate):
            tiles[b] = list(wram[0x1710 + 16 * shown + 4 * i:0x1714 + 16 * shown + 4 * i])
    m.blocks = dict(m.blocks, chr=chr_, tiles=tiles)


def rom_screen(prg, ram, wram, ppal=None, cycle=0, sparkle=False):
    """RAM 의 장소·좌표·스크롤·구역·시각만 보고 롬에서 화면을 그린다(256×240). 0F:$EB23 처럼 화면의 (i, j) 번째 블록을
    nametable 의 (X/8 + 2i, Y/8 + 2j) 에 놓고 스크롤만큼 돌려 자른다. 돌려주는 것: 그림, 애니메이션 블록 자리 표시."""
    t = ram[0x28]
    m = dq4block.Map(prg, field=ram[0x65]) if t == 0 else dq4block.Map(prg, ram[0x63], ram[0x64])
    left, top = ram[0x7C], ram[0x7B]
    chunks, running, gate = gate_chunks(prg, ram, wram)
    if chunks:
        # 단계의 넷째 조각을 보낸 프레임에 $0300 큐가 아직 안 비었으면($1F bit5) 화면은 앞 단계의 블록 → 타일 표다.
        stale = running and ram[0x57] < 4 and ram[0x55] == 4 and ram[0x1F] & 0x20
        gate_map(m, wram, chunks, gate, (ram[0x57] + 1) & 1 if stale else None)
    if running:
        # 연출 중에는 $7C/$7B 를 매 프레임 고치는 0F:$D542 가 돌지 않아 앞 맵의 값이 남는다.
        left, top = (wram[0xF60] - 8) & 0xFF, (wram[0xF80] - 7) & 0xFF
    area = wram[0x1140] & 0xE0 if t else 0
    sx, sy = (ram[0x505] & 1) * 256 + ram[0x508], ram[0x509]
    pal12 = dq4block.palette(prg, t, ram[0x63], ram[0x64], wram[0x2ED], ram[0x65], wram[0x293])
    if t == 0:
        pal12 = field_cycle(pal12, ram[0x65], cycle)
    elif t == 0x18:
        pal12 = falls_cycle(pal12, cycle)
    if ppal is not None:                 # 팔레트 순환(롬 팔레트와 덤프가 다른 맵)을 가려 보려고 덤프의 BG 팔레트를 씀
        pal12 = bytes(ppal[i] for i in range(16) if i & 3)
    p = Painter(m, pal12)
    anim = set(dq4block.anim_blocks(prg, t)) if t else set()
    full = Image.new('RGB', (512, 240), MESEN_RGB[0x0F])
    amask = Image.new('L', (512, 240), 0)
    for j in range(15):
        for i in range(16):
            x, y = (left + i) & 0xFF, (top + j) & 0xFF
            blk = field_block(m, x, y, sparkle) if t == 0 else m.block(x, y, area, ram[0x7BA])
            c, r = (sx // 16 * 2 + 2 * i) % 64, (sy // 16 * 2 + 2 * j) % 30
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

    def count(mine, amask, alt=None):
        sp, mp, ap, mk = shot.load(), mine.load(), amask.load(), smask.load()
        bp = alt.load() if alt else mp
        total = diff = skipped = 0
        first = None
        for y in range(240):
            for x in range(256):
                if mk[x, y] or ap[x, y]:
                    skipped += 1
                    continue
                total += 1
                if sp[x, y] != mp[x, y] and sp[x, y] != bp[x, y]:
                    diff += 1
                    first = first or (x, y)
        return total, diff, skipped, first
    # 필드·폭포는 팔레트가 몇 프레임마다 돌아가므로(field_cycle·falls_cycle) 롬 팔레트를 돌린 6단계 중 가장 잘 맞는 것을 쓴다.
    # 필드 3 의 블록 01 은 칸을 그릴 때마다 난수로 18·19 가 갈리므로(field_block) 둘 중 하나와 같으면 같은 것으로 친다.
    best = None
    f3 = ram[0x28] == 0 and ram[0x65] == 3
    for n in range(FIELD_PHASES if ram[0x28] in CYCLED else 1):
        mine, amask = rom_screen(prg, ram, wram, cycle=n)
        r = count(mine, amask, rom_screen(prg, ram, wram, cycle=n, sparkle=True)[0] if f3 else None)
        if best is None or r[1] < best[1][1]:
            best = (n, r, mine)
    phase, (total, diff, skipped, first), mine = best
    where = f'{ram[0x63]:02X}/{ram[0x64]:02X}' if ram[0x28] else f'필드 {ram[0x65]}'
    if ram[0x28] in CYCLED:
        where += f'(팔레트 {phase}단계)'
    chunks, running, _ = gate_chunks(prg, ram, wram)
    if chunks:
        where += f'(성문 {"연출" if running else "연출 뒤"} 조각 {len(chunks)}개)'
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
                 f'<a href="../gfx/screens/{s["bgchr"]}">BG 패턴</a> · <a href="../gfx/screens/{s["shot"]}">화면</a>'
                 + (f' · <a href="../gfx/screens/{s["screen"]}">줄 스크롤로 그린 화면</a>' if 'screen' in s else '') + '</div></div>')
    h.append('</div></body></html>')
    d = out / 'gallery'
    d.mkdir(parents=True, exist_ok=True)
    (d / 'index.html').write_text('\n'.join(h))
    print('갤러리 →', d / 'index.html')


def scene_files(prefix):
    """fc/dq4/tools/lua/fcgfxscene.lua 의 <prefix>.nt·chr·pal·oam·ppu·png, 또는 seq.lua 의 end.*(prefix = DIR/end)."""
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


def frame_scroll(log_path, frame):
    """fc/dq4/tools/lua/fcgfxscroll.lua 의 ppulog.txt 에서 그 프레임(화면을 찍은 endFrame 번호)의 스크롤.
    한 프레임 몫은 vblank(scanline 241 이후·-1)의 쓰기 다음에 그 화면의 보이는 줄(0~239) 쓰기가 온다.
    돌려주는 것: 맨 위 스크롤 (x, y, nametable 번호), $2001 값, 보이는 줄의 $2005 첫 쓰기 [(scanline, cycle, x)].
    보이는 줄의 $2005 둘째 쓰기(Y)는 다음 프레임에야 반영되므로 버린다. 보이는 줄의 $2000·$2006 쓰기는 다루지 않는다."""
    sx = sy = nt = 0
    mask = 0x1E
    splits = []
    for line in Path(log_path).read_text().split('\n'):
        m = re.match(r'(\d+)\s+(-?\d+)\s+(\d+) (20\d\d)=([0-9A-F]{2}) .* w=(\d)', line)
        if not m or int(m[1]) != frame:
            continue
        sl, cy, reg, v, w = int(m[2]), int(m[3]), m[4], int(m[5], 16), int(m[6])
        visible = 0 <= sl < 240
        if reg == '2000' and not visible:
            nt = v & 3
        elif reg == '2001' and not visible:
            mask = v
        elif reg == '2005':
            if visible:
                if w == 1:
                    splits.append((sl, cy, v))
            elif w == 1:
                sx = v
            else:
                sy = v
        elif visible:
            raise ValueError(f'보이는 줄의 {reg} 쓰기는 다루지 않음: {line}')
    return (sx, sy, nt), mask, splits


def line_screen(nt, chr_, pal, base, mirror, scroll, mask, splits):
    """덤프 nametable 을 줄마다 다른 가로 스크롤로 256×240 화면에. mirror 는 'v'(nametable 두 장이 가로로) 또는 'h'(세로로).
    줄 안에서 $2005 를 쓰면 fine X(아래 3비트)는 그 자리부터 바로, coarse X 는 cycle 257 의 가로 복사부터 바뀐다.
    MesenCE 에서 픽셀 x 가 새 fine X 를 쓰는 것은 x ≥ 쓴 cycle 이었다(엔딩 바다 장면 덤프 여섯 장). $2001 bit1 이 0 이면 왼쪽 8픽셀은 색 0."""
    a = nt_image(nt[:0x400] * 2, chr_, pal, base).crop((0, 0, 256, 240))
    b = nt_image(nt[0x400:] * 2, chr_, pal, base).crop((0, 0, 256, 240))
    world = Image.new('RGB', (512, 480))
    for i, im in enumerate((a, b, a, b) if mirror == 'v' else (a, a, b, b)):
        world.paste(im, (i % 2 * 256, i // 2 * 240))
    wp = world.load()
    scr = Image.new('RGB', (256, 240), MESEN_RGB[pal[0] & 0x3F])
    sp = scr.load()
    sx, sy, n = scroll
    at = {}
    for sl, cy, v in splits:
        at.setdefault(sl, []).append((cy, v))
    # 한 줄 끝(cycle 257)에 쓴 값의 coarse X 는 그다음 줄 끝에 옮겨지므로 한 줄 늦게 들어간다.
    coarse, fine, late = sx, sx, None
    for y in range(240):
        wy = (n // 2 * 240 + sy + y) % 480
        changes = sorted(at.get(y, []))
        for x in range(256):
            f = fine
            for cy, v in changes:
                if x >= cy:
                    f = v
            if x < 8 and not mask & 2:
                continue
            sp[x, y] = wp[(n % 2 * 256 + (coarse & ~7) + (f & 7) + x) % 512, wy]
        if late is not None:
            coarse, late = late, None
        for cy, v in changes:
            fine = v
            if cy < 257:
                coarse = v
            else:
                late = v
    return scr


def screens_from_dumps(out, dumps):
    """dumps = [(이름, 제목, prefix[, opts])]. nametable 두 장 그림, BG 패턴 표 시트, MesenCE 화면을 두고,
    화면과 nametable 그림을 스크롤 자리를 찾아 스프라이트 자리를 뺀 픽셀로 견준다.
    opts 에 'ppulog'(fcgfxscroll.lua 의 ppulog.txt)가 있으면 그 프레임('frame', 없으면 prefix 의 fNNNNN)의 줄 스크롤로
    화면을 그려 견주고, 'mirror'('v' 기본, 'h')로 nametable 배치를 정한다. 그때는 <이름>-screen.png 도 둔다."""
    d = Path(out) / 'gfx' / 'screens'
    d.mkdir(parents=True, exist_ok=True)
    idx = []
    for name, title, prefix, *rest in dumps:
        opts = rest[0] if rest else {}
        f = scene_files(prefix)
        base = 0x1000 if f['ppu'] & 0x10 else 0
        full = nt_image(f['nt'], f['chr'], f['pal'], base)
        full.save(d / f'{name}-nt.png')
        sheet = Image.new('RGB', (128, 128))
        colors = [MESEN_RGB[f['pal'][j] & 0x3F] for j in range(4)]
        for i in range(256):
            sheet.paste(tile(f['chr'][base + 16 * i:base + 16 * i + 16], colors), (i % 16 * 8, i // 16 * 8))
        sheet.save(d / f'{name}-bgchr.png')
        shot = Image.open(f'{prefix}.png').convert('RGB')
        shot.save(d / f'{name}-shot.png')
        mask = None
        for o in ('oam', 'oam2'):
            if o in f:
                m = sprite_mask(f[o], tall=bool(f['ppu'] & 0x20))
                mask = m if mask is None else ImageChops.lighter(mask, m)
        extra = {}
        if 'ppulog' in opts:
            frame = opts.get('frame') or int(re.search(r'f(\d+)$', prefix)[1])
            scroll, pmask, splits = frame_scroll(opts['ppulog'], frame)
            mirror = opts.get('mirror', 'v')
            scr = line_screen(f['nt'], f['chr'], f['pal'], base, mirror, scroll, pmask, splits)
            scr.save(d / f'{name}-screen.png')
            n, sx, sy = diff_count(scr, shot, mask), scroll[0] + scroll[2] % 2 * 256, scroll[1] + scroll[2] // 2 * 240
            extra = {'screen': f'{name}-screen.png', 'mirror': mirror, 'ppumask': pmask, 'lines': [list(s) for s in splits],
                     'source': 'MesenCE 덤프(fc/dq4/tools/lua/fcgfxscroll.lua) 렌더링, 롬에서 직접 푼 것이 아님'}
        else:
            n, sx, sy = match_shot(full, shot, mask)
        masked = 0 if mask is None else mask.histogram()[255]
        lines = f', 줄 스크롤 (scanline, cycle, X) {extra["lines"]}' if extra else ''
        print(f'{name}: 화면 {256 * 240 - masked} 픽셀(스프라이트 자리 {masked} 뺌) 중 {n} 다름, 스크롤 ({sx},{sy}){lines}')
        idx.append({'name': name, 'title': title, 'nt': f'{name}-nt.png', 'bgchr': f'{name}-bgchr.png', 'shot': f'{name}-shot.png',
                    'source': 'MesenCE 덤프(fc/dq4/tools/lua/fcgfxscene.lua) 렌더링, 롬에서 직접 푼 것이 아님', 'dump': prefix,
                    'scroll': [sx, sy], 'diff': n, 'masked': masked, **extra})
    # 이미 있는 장면 목록에 더한다(같은 이름은 바꿈). 장면 하나만 다시 뜬 덤프로 바꿀 때 쓴다.
    old = json.loads((d / 'index.json').read_text()) if (d / 'index.json').exists() else []
    names = {x['name'] for x in idx}
    idx = [x for x in old if x['name'] not in names] + idx
    (d / 'index.json').write_text(json.dumps(idx, ensure_ascii=False, indent=1))
    print(f'장면 {len(names)}개 넣음, 모두 {len(idx)}개 → {d}')


def source_txt(out, sub, cmd, rom):
    """비공개 에셋 저장소 규칙의 세 줄: 커밋, 명령, 롬."""
    try:
        rev = subprocess.run(['git', 'rev-parse', 'HEAD'], capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        rev = '?'
    sha = hashlib.sha1(rom).hexdigest()
    (Path(out) / sub).mkdir(parents=True, exist_ok=True)
    (Path(out) / sub / 'SOURCE.txt').write_text(
        f'sfc-dq4 커밋: {rev}\n명령: {cmd}\n롬: FC 「ドラゴンクエストIV」 일본판 Rev A, SHA-1 {sha}\n')


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
        screens_from_dumps(a[3], [(x['name'], x['title'], x['prefix'], {k: x[k] for k in ('ppulog', 'frame', 'mirror') if k in x})
                                  for x in spec])
        source_txt(a[3], 'gfx/screens', 'uv run --locked python fc/dq4/tools/dq4fcgfx.py rom/dq4.nes scenes $OUT ' + a[4], data)
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
        source_txt(a[3], 'gallery', 'uv run --locked python fc/dq4/tools/dq4fcgfx.py rom/dq4.nes gallery $OUT', data)
        return
    out = a[3]
    names = place_table(prg, data) if cmd in ('all', 'maps', 'field') else {}
    line = 'uv run --locked python fc/dq4/tools/dq4fcgfx.py rom/dq4.nes ' + ' '.join(['$OUT' if x == out else x for x in a[2:]])
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
