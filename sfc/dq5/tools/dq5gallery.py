"""DQ5(SFC) 그래픽 갤러리. 롬에서 그림을 뽑아 work/gallery/index.html 하나로 훑어보게 한다.

스프라이트를 새로 그릴 때 원작 그림을 찾아보는 용도다. 그림은 다른 도구의 내보내기 함수가 만든다.
  dq5gfx.export_all      맵·CHR·필드·전투 몬스터·폰트·창 타일·움직이는 타일
  dq5battlebg            전투 배경(있으면)
  dq5sprite.export_all   필드 인물 스프라이트(있으면)
없는 모듈은 건너뛴다. index.html 은 상대 경로로만 그림을 가리키므로 폴더째 옮겨도 열린다.
롬에서 뽑은 그림이므로 저장소에 커밋하지 않는다(work/ 는 .gitignore).

사용:
  python sfc/dq5/tools/dq5gallery.py rom/dq5.sfc [--out work/gallery] [--only maps,field]
      [--gfx 폴더] [--sprites 폴더]
--gfx 는 dq5gfx·전투 배경 그림을 쓸 곳(기본 OUT/gfx), --sprites 는 인물 스프라이트 폴더(기본 OUT/sprites).
--sprites 폴더에 index.json 이 이미 있으면 다시 뽑지 않고 그 목록을 그대로 링크한다.
index.html 은 이 폴더들을 OUT 기준 상대 경로로 가리킨다. 예: 에셋 저장소에서 --out sfc/dq5/gallery --gfx sfc/dq5/gfx
--sprites sfc/dq5/sprites 로 돌리면 ../gfx/·../sprites/ 로 링크한다.
"""
import argparse
import glob
import html
import importlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from dq5map import Rom  # noqa: E402

# 갤러리 분류: (cat, 제목). 내보내기 함수가 준 cat 이 여기 없으면 끝에 그대로 붙는다.
CATEGORIES = (
    ('maps', '실내 맵'), ('maps-attr', '맵 속성'), ('map-blocks', '맵 블록'), ('chr', '실내 CHR'),
    ('field', '필드'), ('field-blocks', '필드 블록·타일'), ('anim', '움직이는 타일'),
    ('sprites', '인물 스프라이트'), ('monsters', '전투 몬스터'), ('battlebg', '전투 배경'),
    ('font', '폰트'), ('ui', '창·메뉴'),
)


def optional(name):
    try:
        return importlib.import_module(name)
    except ImportError:
        return None


def globbed(outdir, cat):
    items = []
    for p in sorted(glob.glob(os.path.join(outdir, '**', '*.png'), recursive=True)):
        rel = os.path.relpath(p, outdir)
        items.append({'cat': cat, 'group': os.path.dirname(rel), 'title': os.path.splitext(os.path.basename(rel))[0],
                      'path': rel})
    return items


def run_module(mod, rom, outdir, cat):
    items = mod.export_all(rom, outdir)
    return items if items else globbed(outdir, cat)


def battle_backgrounds(mod, rom, outdir):
    """dq5battlebg 에 export_all 이 없을 때: 배경 번호마다 시대($1949) 0·1·2."""
    items = []
    os.makedirs(outdir, exist_ok=True)
    for n in range(mod.COUNT):
        for era in (0, 1, 2):
            img = mod.render(rom, n, era)
            rel = f'{n:02X}-era{era}.png'
            img.save(os.path.join(outdir, rel))
            items.append({'cat': 'battlebg', 'group': f'시대 {era}', 'title': f'{n:02X} ($1949={era})', 'path': rel,
                          'w': img.width, 'h': img.height, 'note': '레코드 밖 팔레트 색은 자홍'})
    return items


def collect(rom, out, only, gfx_dir=None, sprite_dir=None):
    items = []
    gfx = importlib.import_module('dq5gfx')
    gfx_dir = gfx_dir or os.path.join(out, 'gfx')
    rel = os.path.relpath(gfx_dir, out)
    got = gfx.export_all(rom, gfx_dir, only)
    items += [dict(i, path=f'{rel}/' + i['path']) for i in got]
    dirs = {'battlebg': os.path.join(gfx_dir, 'battlebg'), 'sprites': sprite_dir or os.path.join(out, 'sprites')}
    for name, cat in (('dq5battlebg', 'battlebg'), ('dq5sprite', 'sprites')):
        if only and cat not in only:
            continue
        sub = dirs[cat]
        index = os.path.join(sub, 'index.json')
        if cat == 'sprites' and sprite_dir and os.path.exists(index):
            with open(index) as f:
                part = json.load(f)
            print(f'{name}: {index} 의 {len(part)}개를 링크')
        else:
            mod = optional(name)
            if mod is None:
                print(f'{name}: 모듈 없음, 건너뜀')
                continue
            if hasattr(mod, 'export_all'):
                part = run_module(mod, rom, sub, cat)
            elif cat == 'battlebg' and hasattr(mod, 'render'):
                part = battle_backgrounds(mod, rom, sub)
            else:
                print(f'{name}: export_all 없음, 건너뜀')
                continue
            print(f'{name}: {len(part)}')
        if cat == 'battlebg':
            got += [dict(i, path='battlebg/' + i['path']) for i in part]
        rel = os.path.relpath(sub, out)
        items += [dict(i, cat=i.get('cat', cat), path=f'{rel}/' + i['path']) for i in part]
    gfx.write_index(got, gfx_dir)
    return items


PAGE = r'''<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>DQ5 그래픽</title>
<style>
:root { --bg:#16161c; --fg:#e8e8ee; --dim:#9a9aa8; --card:#22222c; --line:#34343f; --acc:#f2c14e; }
* { box-sizing:border-box; }
body { margin:0; background:var(--bg); color:var(--fg); font:14px/1.45 system-ui, sans-serif; }
header { position:sticky; top:0; z-index:5; background:var(--bg); border-bottom:1px solid var(--line); padding:10px 16px; }
h1 { font-size:17px; margin:0 0 8px; }
nav { display:flex; flex-wrap:wrap; gap:6px; }
nav button, .ctl button { background:var(--card); color:var(--fg); border:1px solid var(--line); border-radius:6px; padding:4px 10px; cursor:pointer; font:inherit; }
nav button.on, .ctl button.on { border-color:var(--acc); color:var(--acc); }
.bar { display:flex; flex-wrap:wrap; gap:8px; margin-top:8px; align-items:center; }
.bar input, .bar select { background:var(--card); color:var(--fg); border:1px solid var(--line); border-radius:6px; padding:4px 8px; font:inherit; }
.count { color:var(--dim); }
main { padding:16px; display:grid; grid-template-columns:repeat(auto-fill, minmax(220px, 1fr)); gap:12px; }
.card { background:var(--card); border:1px solid var(--line); border-radius:8px; overflow:hidden; cursor:zoom-in; display:flex; flex-direction:column; }
.thumb { height:180px; display:flex; align-items:center; justify-content:center; background:#000 repeating-conic-gradient(#1c1c1c 0 25%, #262626 0 50%) 0 0/16px 16px; }
.thumb img { max-width:100%; max-height:100%; image-rendering:pixelated; }
.cap { padding:6px 8px; }
.cap b { display:block; font-weight:600; }
.cap span { color:var(--dim); font-size:12px; }
#view { position:fixed; inset:0; z-index:10; background:rgba(8,8,12,.97); display:none; flex-direction:column; }
#view.open { display:flex; }
.ctl { display:flex; flex-wrap:wrap; gap:6px; align-items:center; padding:8px 16px; border-bottom:1px solid var(--line); }
.ctl .meta { color:var(--dim); margin-left:8px; font-size:12px; }
#stage { flex:1; overflow:auto; }
#stage img { image-rendering:pixelated; display:block; margin:16px; }
</style></head><body>
<header>
<h1>DQ5(SFC) 그래픽 — 롬에서 뽑은 그림</h1>
<nav id="cats"></nav>
<div class="bar"><select id="group"></select><input id="q" type="search" placeholder="제목 찾기 (예: 02/06, 슬라임, 01:A24D)"><span class="count" id="count"></span></div>
</header>
<main id="grid"></main>
<div id="view"><div class="ctl"><button data-z="fit">맞춤</button><button data-z="1">1x</button><button data-z="2">2x</button><button data-z="3">3x</button><button data-z="4">4x</button><button data-z="8">8x</button>
<button id="prev">◀</button><button id="next">▶</button><a id="raw" target="_blank" style="color:var(--acc)">원본</a><span class="meta" id="meta"></span><button id="close" style="margin-left:auto">닫기 (Esc)</button></div>
<div id="stage"><img id="big" alt=""></div></div>
<script>
const ITEMS = __ITEMS__;
const CATS = __CATS__;
let cat = null, shown = [], cur = -1, zoom = 'fit';
const $ = id => document.getElementById(id);
function esc(s) { return String(s).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c])); }
function metaText(it) {
  return Object.entries(it).filter(([k]) => !['cat','group','title','path','big'].includes(k)).map(([k, v]) => k + ': ' + v).join(' · ');
}
function buildCats() {
  const nav = $('cats'); nav.innerHTML = '';
  for (const [c, name] of CATS) {
    const n = ITEMS.filter(i => i.cat === c).length; if (!n) continue;
    const b = document.createElement('button'); b.textContent = name + ' ' + n; b.onclick = () => pick(c);
    b.dataset.c = c; nav.appendChild(b);
    if (cat === null) cat = c;
  }
}
function pick(c) {
  cat = c;
  for (const b of $('cats').children) b.classList.toggle('on', b.dataset.c === c);
  const groups = [...new Set(ITEMS.filter(i => i.cat === c).map(i => i.group || ''))];
  $('group').innerHTML = '<option value="">전체</option>' + groups.map(g => '<option>' + esc(g) + '</option>').join('');
  $('group').style.display = groups.length > 1 ? '' : 'none';
  render();
}
function render() {
  const g = $('group').value, q = $('q').value.trim().toLowerCase();
  shown = ITEMS.filter(i => i.cat === cat && (!g || (i.group || '') === g)
    && (!q || (i.title + ' ' + metaText(i)).toLowerCase().includes(q)));
  $('count').textContent = shown.length + '개';
  $('grid').innerHTML = shown.map((it, k) =>
    '<div class="card" data-k="' + k + '"><div class="thumb"><img loading="lazy" src="' + esc(it.path) + '" alt=""></div>' +
    '<div class="cap"><b>' + esc(it.title) + '</b><span>' + esc(it.w ? it.w + 'x' + it.h : '') + (it.note ? ' · ' + esc(it.note) : '') + '</span></div></div>').join('');
  for (const el of $('grid').children) el.onclick = () => open(+el.dataset.k);
}
function applyZoom() {
  const img = $('big'), it = shown[cur];
  for (const b of document.querySelectorAll('[data-z]')) b.classList.toggle('on', b.dataset.z === String(zoom));
  if (!it || !img.naturalWidth) return;
  let z = zoom;
  if (z === 'fit') {
    const st = $('stage');
    z = Math.min((st.clientWidth - 32) / img.naturalWidth, (st.clientHeight - 32) / img.naturalHeight);
    z = z >= 1 ? Math.floor(z) : z;
  }
  img.style.width = img.naturalWidth * z + 'px'; img.style.height = img.naturalHeight * z + 'px';
}
function open(k) {
  cur = (k + shown.length) % shown.length; const it = shown[cur];
  $('view').classList.add('open'); $('big').src = it.path; $('raw').href = it.path;
  $('meta').textContent = it.title + ' — ' + metaText(it);
}
$('big').onload = applyZoom;
for (const b of document.querySelectorAll('[data-z]')) b.onclick = () => { zoom = b.dataset.z === 'fit' ? 'fit' : +b.dataset.z; applyZoom(); };
$('close').onclick = () => $('view').classList.remove('open');
$('prev').onclick = () => open(cur - 1); $('next').onclick = () => open(cur + 1);
document.addEventListener('keydown', e => {
  if (!$('view').classList.contains('open')) return;
  if (e.key === 'Escape') $('close').onclick();
  else if (e.key === 'ArrowLeft') open(cur - 1);
  else if (e.key === 'ArrowRight') open(cur + 1);
  else if ('123468'.includes(e.key)) { zoom = +e.key; applyZoom(); }
  else if (e.key === '0') { zoom = 'fit'; applyZoom(); }
});
window.addEventListener('resize', () => { if (zoom === 'fit') applyZoom(); });
$('group').onchange = render; $('q').oninput = render;
buildCats(); pick(cat);
</script></body></html>
'''


def write_page(items, out):
    known = [c for c, _ in CATEGORIES]
    cats = list(CATEGORIES) + [(c, c) for c in dict.fromkeys(i['cat'] for i in items) if c not in known]
    page = PAGE.replace('__ITEMS__', json.dumps(items, ensure_ascii=False)).replace(
        '__CATS__', json.dumps(cats, ensure_ascii=False))
    path = os.path.join(out, 'index.html')
    with open(path, 'w') as f:
        f.write(page)
    return path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('rom')
    ap.add_argument('--out', default='work/gallery')
    ap.add_argument('--only', help='쉼표로 내보낼 묶음만(dq5gfx 의 maps,chr,field,monsters,font,ui,anim, battlebg, sprites)')
    ap.add_argument('--gfx', help='dq5gfx·전투 배경 그림 폴더(기본 OUT/gfx)')
    ap.add_argument('--sprites', help='인물 스프라이트 폴더(기본 OUT/sprites). index.json 이 있으면 그대로 링크')
    args = ap.parse_args()
    rom = Rom(open(args.rom, 'rb').read())
    only = set(args.only.split(',')) if args.only else None
    os.makedirs(args.out, exist_ok=True)
    items = collect(rom, args.out, only, args.gfx, args.sprites)
    path = write_page(items, args.out)
    print(f'{len(items)} items -> {html.escape(path)}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
