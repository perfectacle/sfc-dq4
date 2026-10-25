"""DQ5(SFC) 그래픽 갤러리. 롬에서 그림을 뽑아 ROOT/gallery/index.html·sprites.html 로 훑어보게 한다.

스프라이트를 새로 그릴 때 원작 그림을 찾아보는 용도다. 그림은 dq5gfx.export_all 이 ROOT 아래 분류 폴더
(maps/ field/ monsters/ battlebg/ gfx/…)에 쓰고, 인물 스프라이트는 ROOT/sprites/index.json 이 있으면 그것을 링크한다
(없으면 dq5sprite.export_all 로 ROOT/sprites 에 뽑는다). 쪽 구성은 에셋 저장소 fc/dq4/gallery 와 같다.
페이지는 그림을 ../<분류>/ 상대 경로로만 가리키므로 ROOT 폴더째 옮겨도 열린다.
롬에서 뽑은 그림이므로 공개 저장소에 커밋하지 않는다.

사용:
  python sfc/dq5/tools/dq5gallery.py rom/dq5.sfc [--out work/dq5gfx] [--only maps,field]
에셋 저장소에서는 --out <sfc-dq4-assets>/sfc/dq5 로 돌린다.
"""
import argparse
import hashlib
import html
import importlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from dq5map import Rom  # noqa: E402

COMMAND = 'uv run --locked python sfc/dq5/tools/dq5gallery.py rom/dq5.sfc --out $OUT'

STYLE = '''
:root { color-scheme: light dark; --bg: #f6f6f4; --fg: #1d1d1b; --mut: #6b6b66; --card: #ffffff; --line: #ddd; }
@media (prefers-color-scheme: dark) { :root { --bg: #161615; --fg: #e8e8e4; --mut: #9a9a94; --card: #22221f; --line: #3a3a36; } }
body { margin: 0; padding: 16px; background: var(--bg); color: var(--fg); font: 14px/1.5 system-ui, sans-serif; }
h1 { font-size: 20px; } h2 { font-size: 17px; margin-top: 28px; border-bottom: 1px solid var(--line); }
nav a { margin-right: 12px; }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 10px; }
.card { background: var(--card); border: 1px solid var(--line); border-radius: 6px; padding: 6px; }
.card img { width: 100%; height: 150px; object-fit: contain; image-rendering: pixelated; background: #000; }
.card .t { font-weight: 600; } .card .s { color: var(--mut); font-size: 12px; }
'''


def esc(s):
    return html.escape(str(s))


def card(src, title, subs, links=()):
    out = (f'<div class="card"><a href="{esc(src)}"><img loading="lazy" src="{esc(src)}" alt=""></a>'
           f'<div class="t">{esc(title)}</div>')
    for s in subs:
        if s:
            out += f'<div class="s">{esc(s)}</div>'
    if links:
        out += '<div class="s">' + ' '.join(f'<a href="{esc(h)}">{esc(t)}</a>' for t, h in links) + '</div>'
    return out + '</div>'


def page(title, nav, intro, sections):
    body = ['<!doctype html><html lang="ko"><head><meta charset="utf-8">',
            '<meta name="viewport" content="width=device-width, initial-scale=1">',
            f'<title>{esc(title)}</title><style>{STYLE}</style></head><body>', f'<h1>{esc(title)}</h1>',
            '<nav>' + ''.join(f'<a href="{esc(h)}">{esc(t)}</a>' for t, h in nav) + '</nav>', f'<p>{esc(intro)}</p>']
    for sid, h2, cards in sections:
        body.append(f'<h2 id="{sid}">{esc(h2)}</h2><div class="grid">')
        body += cards
        body.append('</div>')
    return '\n'.join(body) + '\n</body></html>\n'


def rel(p):
    return '../' + p


def maps_cards(items):
    gifs = {i['stem']: i['path'] for i in items if i['cat'] == 'anim' and i.get('stem')}
    by = {}
    for it in items:
        if it['cat'] == 'maps':
            by.setdefault(it['stem'], []).append(it)
    cards = []
    for stem, its in by.items():
        day = next(i for i in its if i['variant'] == '낮')
        links = [(i['variant'], rel(i['path'])) for i in its]
        links.append(('블록', rel(f'gfx/blocks/maps/{stem}.png')))
        if stem in gifs:
            links.append(('움직임', rel(gifs[stem])))
        note = next((i['note'] for i in its if i.get('note')), '')
        cards.append(card(rel(day['path']), day['title'],
                          [f'{day["size"]} 셀 · 블록 {day["blocks"]} · 인물 {day["npcs"]} · 출구 {day["exits"]} · '
                           f'상자 {day["chests"]} · 물체 {day.get("doors", 0)} · 레코드 {day["addr"]}', note], links))
    return cards


def simple_cards(items, cat, sub=lambda i: i.get('note', '')):
    return [card(rel(i['path']), i['title'] + (f' ({i["variant"]})' if i.get('variant') else ''),
                 [f'{i["w"]}×{i["h"]}' if 'w' in i else '', sub(i)]) for i in items if i['cat'] == cat]


def write_pages(items, root, sprite_items):
    gallery = os.path.join(root, 'gallery')
    os.makedirs(gallery, exist_ok=True)
    nmaps = len({i['stem'] for i in items if i['cat'] == 'maps'})
    sections = [
        ('maps', f'마을·던전 맵 {nmaps}개', maps_cards(items)),
        ('field', '필드', simple_cards(items, 'field')),
        ('blocks', '필드 블록 시트', [card(rel(i['path']), i['title'], [i.get('note', '')]) for i in items
                                     if i['cat'] == 'blocks' and not i['path'].startswith('gfx/blocks/maps/')]),
        ('chr', 'CHR·폰트', simple_cards(items, 'chr') + simple_cards(items, 'font')),
        ('screens', '창·메뉴', simple_cards(items, 'screens')),
        ('anim', '움직이는 타일', simple_cards([i for i in items if not i.get('stem')], 'anim')),
        ('animmaps', '움직이는 맵(GIF)', simple_cards([i for i in items if i.get('stem')], 'anim')),
    ]
    nav = [('맵', '#maps'), ('필드', '#field'), ('블록', '#blocks'), ('CHR·폰트', '#chr'), ('창·메뉴', '#screens'),
           ('움직이는 타일', '#anim'), ('움직이는 맵', '#animmaps'), ('스프라이트·몬스터', 'sprites.html')]
    intro = ('썸네일을 누르면 원본이 열립니다(맵·지도는 1배). 주석판: 노랑 인물(번호, 낮 기본 목록), 하늘색 출구, '
             '빨강 T 보물상자, 분홍 S タンス·ツボ·タル, 분홍 F 발밑 숨은 물건, 주황 D 맵 위 물체(닫힌 문 등). 맵은 이야기 플래그가 모두 꺼진 상태. 맵 이름은 ルーラ 목적지 이름이 있는 그룹만 붙입니다.')
    with open(os.path.join(gallery, 'index.html'), 'w') as f:
        f.write(page('DQ5(SFC) 그래픽', nav, intro, sections))
    spr = [card(rel('sprites/' + i['path']), i.get('title', i['path']), [i.get('group', ''), i.get('note', '')])
           for i in sprite_items]
    sections = [('sprites', f'인물 스프라이트 {len(spr)}', spr),
                ('monsters', '전투 몬스터 236마리', simple_cards(items, 'monsters', lambda i: f'그림 {i["pic"]}')),
                ('battlebg', '전투 배경', simple_cards(items, 'battlebg'))]
    nav = [('스프라이트', '#sprites'), ('몬스터', '#monsters'), ('전투 배경', '#battlebg'), ('맵·필드', 'index.html')]
    with open(os.path.join(gallery, 'sprites.html'), 'w') as f:
        f.write(page('DQ5(SFC) 스프라이트·몬스터', nav, '인물 스프라이트는 sprites/index.json 그대로입니다.', sections))


def sprites(rom, root, only):
    if only and 'sprites' not in only:
        return []
    index = os.path.join(root, 'sprites', 'index.json')
    if os.path.exists(index):
        with open(index) as f:
            got = json.load(f)
        print(f'sprites: {index} 의 {len(got)}개를 링크')
    else:
        try:
            got = importlib.import_module('dq5sprite').export_all(rom, os.path.join(root, 'sprites'))
        except ImportError:
            print('dq5sprite: 모듈 없음, 건너뜀')
            return []
    if isinstance(got, dict):
        # 에셋 저장소 꼴(note·obj_palettes·sprites). 갤러리 카드에 쓸 path·title·group 으로 바꾼다.
        got = [dict(i, path=i['file'], title=' '.join(x for x in (f'{i["set"]:02X}' if 'set' in i else i.get('where', ''),
                                                                    i.get('label') or '') if x),
                    group=('탈것' if i.get('vehicle') is not None else '맵 OBJ 물체' if 'map_place' in i
                           else '누운 모양' if i.get('rotated')
                           else '맵 OBJ 타일' if 'map_object' in i else '인물'))
               for i in got['sprites']]
    return [i for i in got if str(i.get('path', '')).endswith('.png') and not i['path'].endswith('-index.png')]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('rom')
    ap.add_argument('--out', default='work/dq5gfx', help='분류 폴더와 gallery/ 를 만들 곳')
    ap.add_argument('--only', help='쉼표로 dq5gfx 묶음만(maps,chr,field,anim,monsters,battlebg,font,ui, sprites)')
    args = ap.parse_args()
    data = open(args.rom, 'rb').read()
    rom = Rom(data)
    only = set(args.only.split(',')) if args.only else None
    gfx = importlib.import_module('dq5gfx')
    sha = hashlib.sha1(data).hexdigest()
    items = gfx.export_all(rom, args.out, only, rom_sha=sha, command=COMMAND)
    write_pages(items, args.out, sprites(rom, args.out, only))
    with open(os.path.join(args.out, 'gallery', 'SOURCE.txt'), 'w') as f:
        f.write(gfx.source_text(COMMAND, sha))
    print(f'{len(items)} items -> {os.path.join(args.out, "gallery")}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
