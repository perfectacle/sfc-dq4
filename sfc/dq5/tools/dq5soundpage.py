"""DQ5(SFC) 소리 들어 보기 페이지. ROOT/sound/{songs,sfx,samples}/index.json 을 읽어 ROOT/gallery/sound.html 을 쓴다.

곡·효과음·악기 샘플마다 <audio> 로 WAV 를 틀고 번호·쓰이는 장면·길이·악기(샘플) 목록을 보인다. 곡 이름을 붙이려고 듣는
사람이 칸마다 이름을 적을 수 있고, 적은 것은 그 브라우저에만 남으며 「JSON 복사」로 한꺼번에 가져갈 수 있다.
소리 파일은 dq5spcfile.py·dq5brr.py 가 만든다. 페이지는 ../sound/ 상대 경로만 쓰므로 ROOT 폴더째 옮겨도 열린다.
롬에서 뽑은 소리를 가리키는 페이지라 공개 저장소에 커밋하지 않는다(에셋 저장소에서 --root <sfc-dq4-assets>/sfc/dq5).

사용:
  python sfc/dq5/tools/dq5soundpage.py --root work/sound-root
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from dq5gallery import STYLE, esc  # noqa: E402

EXTRA = '''
table { border-collapse: collapse; width: 100%; } td, th { border-bottom: 1px solid var(--line); padding: 4px 6px;
  text-align: left; vertical-align: middle; } th { color: var(--mut); font-weight: 500; }
audio { height: 28px; width: 220px; max-width: 100%; } input { width: 12em; } .mut { color: var(--mut); }
@media (max-width: 640px) { .wide { display: none; } audio { width: 160px; } }
'''

SCRIPT = '''
const KEY = 'dq5-sound-names';
let names = {};
try { names = JSON.parse(localStorage.getItem(KEY) || '{}'); } catch (e) {}
for (const el of document.querySelectorAll('input[data-id]')) {
  el.value = names[el.dataset.id] || '';
  el.addEventListener('input', () => {
    names[el.dataset.id] = el.value;
    try { localStorage.setItem(KEY, JSON.stringify(names)); } catch (e) {}
  });
}
document.getElementById('copy').addEventListener('click', () => {
  const t = JSON.stringify(Object.fromEntries(Object.entries(names).filter(([, v]) => v)), null, 1);
  navigator.clipboard.writeText(t).then(() => { document.getElementById('copied').textContent = '복사함'; });
});
'''


def load(root, cat):
    path = os.path.join(root, 'sound', cat, 'index.json')
    return json.load(open(path, encoding='utf-8')) if os.path.exists(path) else []


def audio(cat, wav):
    return f'<audio controls preload="none" src="../sound/{cat}/{esc(wav)}"></audio>' if wav else ''


def rows_play(cat, entries):
    out = []
    for e in entries:
        smp = ' '.join(f'<a href="#s{s}">{s}</a>' for s in e.get('samples', []))
        maps = e.get('maps') or []
        mp = f'<details><summary>맵 {len(maps)}곳</summary>{" ".join(maps)}</details>' if maps else ''
        out.append(f'<tr id="{cat[:2]}{esc(e["id"])}"><td>{esc(e["id"])}</td><td>{esc(e.get("scene") or "")}</td>'
                   f'<td>{audio(cat, e.get("wav"))}</td><td class="wide">{e.get("wav_seconds", "")}초</td>'
                   f'<td class="wide">{smp}</td><td class="wide">{mp}</td><td class="wide mut">{esc(e.get("command", ""))}</td>'
                   f'<td><a href="../sound/{cat}/{esc(e["file"])}">.spc</a></td>'
                   f'<td><input data-id="{cat}/{esc(e["id"])}" placeholder="들어 보고 이름"></td></tr>')
    return out


def rows_samples(entries):
    out = []
    for e in entries:
        sec = e['samples'] / e['rate']
        loop = '반복 없음' if e.get('loop_start') is None else f'반복 {e["loop_start"]}~'
        out.append(f'<tr id="s{esc(e["id"])}"><td>{esc(e["id"])}</td><td>{audio("samples", e["file"])}</td>'
                   f'<td>{sec:.2f}초</td><td class="wide">{loop}</td>'
                   f'<td class="wide mut">ADSR {e["adsr1"]} {e["adsr2"]} 음높이 {e["pitch"]}</td>'
                   f'<td><input data-id="samples/{esc(e["id"])}" placeholder="악기 이름"></td></tr>')
    return out


def page(root):
    songs, sfx, smp = load(root, 'songs'), load(root, 'sfx'), load(root, 'samples')
    head = '<tr><th>번호</th><th>쓰이는 장면</th><th>듣기</th><th class="wide">길이</th><th class="wide">악기</th>' \
           '<th class="wide">쓰는 맵</th><th class="wide">명령</th><th>파일</th><th>이름</th></tr>'
    body = [f'<h2 id="songs">곡 {len(songs)}</h2><table>{head}', *rows_play('songs', songs), '</table>',
            f'<h2 id="sfx">효과음 {len(sfx)}</h2><table>{head}', *rows_play('sfx', sfx), '</table>',
            f'<h2 id="samples">악기 샘플 {len(smp)}</h2><table><tr><th>번호</th><th>듣기</th><th>길이</th>'
            '<th class="wide">반복</th><th class="wide">머리</th><th>이름</th></tr>', *rows_samples(smp), '</table>']
    intro = ('곡·효과음 WAV 는 들어 보기용 앞부분(곡 30초, 효과음 4초)입니다. 끝까지는 .spc 를 SPC 플레이어로 틉니다. '
             '「쓰이는 장면」은 게임에서 그 장면에 나가는 것을 확인한 것만 적었습니다. <번호>-<갈래> 는 곡 변수(명령 0C 의 X)로 '
             '갈라지는 소리입니다. 이름 칸에 적은 것은 이 브라우저에만 남습니다.')
    nav = ' '.join(f'<a href="{h}">{t}</a>' for t, h in (('곡', '#songs'), ('효과음', '#sfx'), ('악기 샘플', '#samples'),
                                                        ('맵·필드', 'index.html'), ('스프라이트·몬스터', 'sprites.html')))
    return ('<!doctype html><html lang="ko"><head><meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
            f'<title>DQ5(SFC) 소리</title><style>{STYLE}{EXTRA}</style></head><body>\n<h1>DQ5(SFC) 소리</h1>\n'
            f'<nav>{nav}</nav>\n<p>{intro}</p>\n<p><button id="copy">적은 이름 JSON 복사</button> '
            '<span id="copied" class="mut"></span></p>\n' + '\n'.join(body) + f'\n<script>{SCRIPT}</script>\n</body></html>\n')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--root', required=True)
    a = ap.parse_args()
    os.makedirs(os.path.join(a.root, 'gallery'), exist_ok=True)
    out = os.path.join(a.root, 'gallery', 'sound.html')
    with open(out, 'w', encoding='utf-8') as f:
        f.write(page(a.root))
    print(out)
    return 0


if __name__ == '__main__':
    sys.exit(main())
