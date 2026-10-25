"""한글 팬패치 폰트에서 「일본어 문자 코드 → 한글 음절」 표(nds/dq4/tables/kr-font.tsv)를 만들고 검사한다.

팬패치는 대사의 문자 코드를 그대로 두고 zen10·zen12.nftr 의 글리프 1400개만 한글로 바꿨다.
바뀐 코드 중 U+3300 이상 1342개는 코드 순서대로 KS X 1001 음절 순서의 부분열이고,
그 앞 58개(히라가나·키릴 자리)는 순서가 없다(자주 쓰는 음절). 자세한 것은
nds/dq4/docs/text-format.md 「한글 팬패치」.

표의 넷째 열: auto = draft 가 고른 값, eye = 글리프를 크게 그려 사람이 읽은 값.

사용:
  python nds/dq4/tools/ndskr.py check JPROOT KRROOT
      표 검사: 바뀐 코드 집합이 두 폰트에서 같고 표와 같음, U+3300 이상은 KS 순서로 늘어나기만 함,
      확인 단어(인물·지명 이름)가 기대한 한글로 읽힘.
  python nds/dq4/tools/ndskr.py draft JPROOT KRROOT OUT.tsv [--freq FREQ.json] [--lam 4]
      자동 판독을 다시 돌린다(numpy 필요). 기존 표의 eye 줄은 고정점으로 쓴다.
JPROOT/KRROOT 는 `krpatch nds unpack` 으로 푼 폴더.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ndstext  # noqa: E402
from kr_patch.nds.font import Font  # noqa: E402

FONT_PATH = ('data', 'data', 'G2D', 'FONT')
ORDERED_FROM = 0x3300
REF_FONT = os.environ.get('KR_REF_FONT', '/System/Library/Fonts/AppleSDGothicNeo.ttc')
# (파일, 일본어 이름, 기대하는 한글) — 판독 오류가 잘 나던 ㅡ·ㅢ·ㅚ·받침 글자를 고루 담았다.
EXPECT = [
    ('b1001000', 'クリフト', '크리프트'), ('b1001000', 'ブライ', '브라이'), ('b1001000', 'フレア', '프레아'),
    ('b1001000', 'ホフマン', '호프만'), ('b1001000', 'パノン', '파논'), ('b1001000', 'トルネコ', '톨네코'),
    ('b1007000', 'サントハイム', '산트하임'), ('b1007000', 'フレノール', '프레놀'),
    ('b1007000', 'さばくのバザー', '사막의 바자'), ('b1007000', 'アッテムト', '앗템트'),
    ('b1007000', 'コーミズ', '코미즈'), ('b1007000', 'ブランカ', '브랑카'),
    ('b1002000', 'メラ;ゴースト', '메라 ;고스트'), ('b1002000', 'おばけ;キノコ', '괴물 ;버섯'),
    ('b1000000', 'ぎんの;タロット', '은의 타롯'), ('b1000000', 'まじんの;かなづち', '마신의 ;쇠망치'),
    ('b1000000', 'りりょくの;つえ', '흑룡의 ;지팡이'), ('b1000000', 'せいぎの;そろばん', '정의의 ;주판'),
]


def ks_syllables():
    return [bytes([a, b]).decode('euc-kr') for a in range(0xB0, 0xC9) for b in range(0xA1, 0xFF)]


def fonts(root, name):
    return Font(open(os.path.join(root, *FONT_PATH, name + '.nftr'), 'rb').read())


def changed(jp, kr):
    return sorted(c for c in jp.cmap if jp.glyph_bytes(jp.cmap[c]) != kr.glyph_bytes(kr.cmap[c]))


def load(path=ndstext.TABLE):
    return [line.rstrip('\n').split('\t') for line in open(path, encoding='utf-8')]


def cmd_check(jp_root, kr_root):
    errors = []
    sets = {n: changed(fonts(jp_root, n), fonts(kr_root, n)) for n in ('zen10', 'zen12')}
    rows = load()
    codes = [int(r[0], 16) for r in rows]
    if sets['zen10'] != sets['zen12']:
        errors.append('zen10 과 zen12 의 바뀐 코드가 다름')
    if codes != sets['zen12']:
        errors.append(f'표 코드 {len(codes)}개가 폰트의 바뀐 코드 {len(sets["zen12"])}개와 다름')
    pos = {s: i for i, s in enumerate(ks_syllables())}
    seq = [(r[2], pos.get(r[2], -1)) for r in rows if int(r[0], 16) >= ORDERED_FROM]
    for (a, x), (b, y) in zip(seq, seq[1:]):
        if y <= x:
            errors.append(f'KS 순서 위반: {a} 다음 {b}')
    table = {chr(int(r[0], 16)): r[2] for r in rows}
    for f, ja, want in EXPECT:
        j = dict(ndstext.read(os.path.join(ndstext.mess(jp_root, 'ja'), f + '.mpt')))
        k = dict(ndstext.read(os.path.join(ndstext.mess(kr_root, 'ja'), f + '.mpt')))
        num = next(n for n, t in j.items() if t.strip('@1') == ja)
        got = ndstext.decode_kr(k[num], table).strip('@1')
        if got != want:
            errors.append(f'{ja}: {got} (기대 {want})')
    print(f'표 {len(rows)}자, 순서 구간 {len(seq)}자, 확인 단어 {len(EXPECT)}개')
    for e in errors:
        print('ERROR', e)
    print(f'{len(errors)} errors')
    return 1 if errors else 0


def cmd_draft(jp_root, kr_root, out, freq=None, lam=4.0):
    import json
    import math

    import numpy as np
    from PIL import Image, ImageDraw, ImageFilter, ImageFont

    jp, kr = fonts(jp_root, 'zen12'), fonts(kr_root, 'zen12')
    ch = changed(jp, kr)
    syl = ks_syllables()
    old = {r[0]: r for r in load()} if os.path.exists(ndstext.TABLE) else {}

    def bitmap(c):
        img = Image.new('L', (kr.cell_w, kr.cell_h))
        for y, row in enumerate(kr.glyph(kr.cmap[c])):
            for x, v in enumerate(row):
                if v:
                    img.putpixel((x, y), 255)
        return img

    # 1) 기준 폰트와 비교: 글자 상자를 가로·세로 따로 늘려 맞춘 뒤 흐린 코사인 유사도, 설정 4개 합.
    def vec(img, m, blur):
        img = img.crop(img.getbbox()).resize((m, m), Image.BILINEAR)
        o = Image.new('L', (m + 4, m + 4))
        o.paste(img, (2, 2))
        a = np.asarray(o.filter(ImageFilter.GaussianBlur(blur)), np.float32).ravel()
        a -= a.mean()
        return a / (np.linalg.norm(a) + 1e-6)

    total = 0
    big = [bitmap(c).resize((kr.cell_w * 4, kr.cell_h * 4), Image.NEAREST) for c in ch]
    for m, blur in ((24, 1.0), (28, 0.6), (32, 1.0), (20, 0.7)):
        g = np.stack([vec(b, m, blur) for b in big])
        best = None
        for idx in (0, 2, 4, 6):
            f = ImageFont.truetype(REF_FONT, 48, index=idx)
            cand = []
            for s in syl:
                im = Image.new('L', (80, 80))
                ImageDraw.Draw(im).text((10, 5), s, font=f, fill=255)
                cand.append(vec(im, m, blur))
            sm = g @ np.stack(cand).T
            best = sm if best is None else np.maximum(best, sm)
        total = total + (best - best.mean(1, keepdims=True)) / best.std(1, keepdims=True)

    ordered = [i for i, c in enumerate(ch) if c >= ORDERED_FROM]
    prior = np.zeros(len(syl), np.float32)
    if freq:
        fr = json.load(open(freq, encoding='utf-8'))
        prior = np.array([lam * math.log(fr.get(s, 0) + 1) for s in syl], np.float32)

    def align(score):
        t = score[ordered]
        n, m = t.shape
        prev, back = t[0].copy(), np.zeros((n, m), int)
        for i in range(1, n):
            run = np.maximum.accumulate(prev)
            arg = np.zeros(m, int)
            b = 0
            for j in range(m):
                if prev[j] > prev[b]:
                    b = j
                arg[j] = b
            cur = np.full(m, -1e18)
            cur[1:] = run[:-1] + t[i, 1:]
            back[i, 1:] = arg[:-1]
            prev = cur
        j, res = int(prev.argmax()), [0] * n
        for i in range(n - 1, -1, -1):
            res[i] = j
            j = back[i][j]
        return res

    def anchored(score):
        score = score.copy()
        for i, c in enumerate(ch):
            r = old.get(f'{c:04X}')
            if r and r[3] == 'eye':
                k = syl.index(r[2])
                score[i] = -1e9
                score[i, k] = 1e6
        return score

    labels = [old.get(f'{c:04X}', [None, None, syl[0]])[2] for c in ch]
    for i, k in zip(ordered, align(anchored(total + prior))):
        labels[i] = syl[k]

    # 2) 자모 조각 자기 학습: 지금 라벨로 초성·중성·종성 조각 비트맵(다수결)을 배워 후보를 합성하고 다시 정렬.
    G = np.stack([np.array(kr.glyph(kr.cmap[c]), bool).ravel() for c in ch]).astype(np.float32)
    vert, hor = {0, 1, 2, 3, 4, 5, 6, 7, 20}, {8, 12, 13, 17, 18}

    def keys(s):
        v = ord(s) - 0xAC00
        cho, jung, jong = v // 588, (v % 588) // 28, v % 28
        g = 0 if jung in vert else (1 if jung in hor else 2)
        ks = [('c', cho, g, jong > 0), ('v', jung, jong > 0, cho in (0, 15))]
        return ks + [('f', jong, g)] if jong else ks

    for _ in range(6):
        acc, cnt = {}, {}
        for i, s in enumerate(labels):
            for k in keys(s):
                acc[k] = acc.get(k, 0) + G[i]
                cnt[k] = cnt.get(k, 0) + 1
        comp = {k: acc[k] / cnt[k] for k in acc}
        cand, ok = [], []
        for j, s in enumerate(syl):
            parts = []
            for k in keys(s):
                if k not in comp:
                    alts = [a for a in comp if a[0] == k[0] and a[1] == k[1] and (a[2] == k[2] or a[3:] == k[3:])]
                    if not alts:
                        parts = None
                        break
                    k = max(alts, key=lambda a: (a[2] == k[2]) * 2 + (a[3:] == k[3:]))
                parts.append(comp[k])
            if parts:
                cand.append((np.max(np.stack(parts), 0) > 0.5).astype(np.float32))
                ok.append(j)
        C = np.stack(cand)
        full = np.full((len(ch), len(syl)), -1e6, np.float32)
        full[:, ok] = -np.abs(G[:, None, :] - C[None, :, :]).sum(2)
        new = labels[:]
        for i, k in zip(ordered, align(anchored(full + prior))):
            new[i] = syl[k]
        if new == labels:
            break
        labels = new

    with open(out, 'w', encoding='utf-8') as f:
        for c, s in zip(ch, labels):
            r = old.get(f'{c:04X}')
            how = 'eye' if r and r[3] == 'eye' else 'auto'
            f.write(f'{c:04X}\t{chr(c)}\t{s}\t{how}\n')
    print(f'{len(ch)} 자 → {out}')


def main(argv):
    if len(argv) < 3:
        raise SystemExit(__doc__)
    if argv[0] == 'check':
        raise SystemExit(cmd_check(argv[1], argv[2]))
    if argv[0] == 'draft':
        freq = argv[argv.index('--freq') + 1] if '--freq' in argv else None
        lam = float(argv[argv.index('--lam') + 1]) if '--lam' in argv else 4.0
        cmd_draft(argv[1], argv[2], argv[3], freq, lam)
        return
    raise SystemExit(__doc__)


if __name__ == '__main__':
    main(sys.argv[1:])
