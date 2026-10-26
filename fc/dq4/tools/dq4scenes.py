"""DQ4(FC) 장면 화면 25개의 덤프를 롬만으로 뜬다(에뮬레이터·세이브스테이트 없이). 쓰는 법은 fc/dq4/docs/dq4-fcgfx.md.

사용:
  python fc/dq4/tools/dq4scenes.py rom/dq4.nes DIR            DIR 에 장면마다 fNNNNN.nt·chr·pal·oam·oam2·ram·ppu·png, DIR/scenes.json
  python fc/dq4/tools/dq4scenes.py rom/dq4.nes DIR --sheet S  S 단계(boot·name·…)를 EVERY 프레임마다 떠서 확인용 시트로

dq4nes.NES 로 전원을 켜서 정해 둔 입력을 준다. 1장은 새로 시작해 이름(「あ」)·성별·메시지 속도를 고르고,
2·5장은 그 자리에서 디버그 장 고르기(고정 뱅크 $C000 bit3, 메모리 위 롬만 바꿈)로, 장 끝·엔딩은 조건 플래그를 쓰고
fc/dq4/tools/lua/warp.lua 와 같은 방법(출구 표 $05A0 에 목적지를 넣고 한 걸음)으로 그 맵에 들어간다.
fNNNNN.png 는 그 프레임의 nametable·스크롤(보이는 줄의 $2005 가로 스크롤 포함)·OAM 으로 그린 화면이다.
결과는 dq4fcgfx.py scenes 가 읽는다. 롬 그래픽이라 커밋하지 않는다(work/ 나 비공개 에셋 저장소에만).
"""
import json
import sys
from pathlib import Path

from PIL import Image
from kr_patch.fc import ines

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dq4fcgfx  # noqa: E402
import dq4nes  # noqa: E402
from dq4nes import pad_bits  # noqa: E402

DEBUG_PRG = (0x3C000, 0x7C000)   # 고정 뱅크 0F·1F 의 $C000. bit3 을 끄면 장 고르기 창


def scroll_of(e):
    """이 프레임의 맨 위 스크롤 (x, y, nametable)과 $2001(보이는 줄이 시작할 때), 보이는 줄의 $2005 첫 쓰기 [(scanline, dot, x)]."""
    scroll, mask = e.top
    splits = [(sl, dot, v) for sl, dot, reg, v, w in e.log if reg == 0x2005 and w == 1 and 0 <= sl < 240]
    return scroll, mask, splits


def screen(e):
    """그 프레임 화면(256×240): BG 는 dq4fcgfx.line_screen, 그 위에 OAM 스프라이트(낮은 번호가 위, 뒤 우선은 BG 색 0 자리에만)."""
    nt, chr_, pal = e.nametables(), bytes(e.vram[:0x2000]), bytes(e.vram[0x3F00:0x3F20])
    scroll, mask, splits = scroll_of(e)
    back = dq4fcgfx.MESEN_RGB[pal[0] & 0x3F]
    if mask & 0x08:
        mirror = 'h' if e.mmc[0] & 3 == 3 else 'v'
        scr = dq4fcgfx.line_screen(nt, chr_, pal, 0x1000 if e.ctrl & 0x10 else 0, mirror, scroll, mask, splits)
    else:
        scr = Image.new('RGB', (256, 240), back)
    if not mask & 0x10:
        return scr
    px = scr.load()
    tall = bool(e.ctrl & 0x20)
    base = 0 if tall else (0x1000 if e.ctrl & 0x08 else 0)
    for i in range(63, -1, -1):
        y, t, a, x = e.oam[4 * i:4 * i + 4]
        if y >= 0xEF:
            continue
        colors = [None] + [dq4fcgfx.MESEN_RGB[pal[0x10 + 4 * (a & 3) + j] & 0x3F] for j in (1, 2, 3)]
        h = 16 if tall else 8
        for r in range(h):
            rr = h - 1 - r if a & 0x80 else r
            if tall:
                tb = (t & 1) * 0x1000 + (t & 0xFE) * 16 + (16 if rr >= 8 else 0)
            else:
                tb = base + t * 16
            lo, hi = chr_[tb + rr % 8], chr_[tb + rr % 8 + 8]
            sy = y + 1 + r
            if sy >= 240:
                break
            for c in range(8):
                cc = c if a & 0x40 else 7 - c
                v = (lo >> cc & 1) | (hi >> cc & 1) << 1
                sx = x + c
                if not v or sx >= 256 or (sx < 8 and not mask & 4):
                    continue
                if a & 0x20 and px[sx, sy] != back:
                    continue
                px[sx, sy] = colors[v]
    return scr


def dump(e, d, name):
    d.mkdir(parents=True, exist_ok=True)
    p = d / name
    for ext, data in (('nt', e.nametables()), ('chr', e.vram[:0x2000]), ('pal', e.vram[0x3F00:0x3F20]),
                      ('oam', e.oam), ('oam2', e.oam), ('ram', e.ram), ('ppu', bytes([e.ctrl]))):
        Path(f'{p}.{ext}').write_bytes(bytes(data))
    screen(e).save(f'{p}.png')


def ppulog(e, path):
    """dq4fcgfx.frame_scroll 이 읽는 꼴(프레임, scanline, dot, 레지스터=값, w)로 이 프레임의 PPU 쓰기를 더한다."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'a') as f:
        for sl, dot, reg, v, w in e.log:
            f.write(f'{e.frame} {sl} {dot} {reg:04X}={v:02X} - w={w}\n')


class Run:
    """한 갈래의 실행. at 의 프레임(이 갈래를 시작한 뒤 센 수)에 덤프를 뜬다."""

    def __init__(self, e, d, at=(), log=()):
        self.e, self.d, self.n = e, d, 0
        self.at, self.log = set(at), set(log)
        self.e.frame = 0

    def frames(self, k, buttons=0):
        for _ in range(k):
            self.e.pad = buttons
            self.e.run_frame()
            self.n += 1
            if self.n in self.log:
                ppulog(self.e, self.d / 'ppulog.txt')
            if self.n in self.at:
                dump(self.e, self.d, f'f{self.n:05d}')

    def seq(self, spec):
        """seq.lua 꼴: 'a:6,wait:40,up+b:3'."""
        for tok in filter(None, spec.split(',')):
            b, k = tok.split(':')
            self.frames(int(k), 0 if b == 'wait' else pad_bits(b))

    def go(self, key, done, limit=600):
        """key 를 누르고 있다가 done(e) 이 참이면 멈춘다. 다른 인물이 막으면 기다렸다 다시 누른다."""
        for _ in range(limit):
            if done(self.e):
                self.frames(16)
                return
            self.frames(1, pad_bits(key))
        raise RuntimeError(f'{key} 로 가지 못함')

    def presses(self, spec, until):
        """boot.lua 꼴: 'a@300:4,start@400:4' 를 until 프레임까지."""
        hold = {}
        for tok in spec.split(','):
            b, rest = tok.split('@')
            f, k = map(int, rest.split(':'))
            for i in range(f, f + k):
                hold[i] = hold.get(i, 0) | pad_bits(b)
        while self.n < until:
            self.frames(1, hold.get(self.n + 1, 0))


def walks(e, key='down'):
    """사본에서 key 로 걸어 맵 좌표($44/$45)가 바뀌면 조작할 수 있는 상태."""
    t = e.snapshot()
    xy = t.ram[0x44], t.ram[0x45]
    t.run(20, pad_bits(key))
    t.run(20)
    return (t.ram[0x44], t.ram[0x45]) != xy


def advance(e, step, start=0, limit=120, close='b:6,wait:40,b:6,wait:40', key='down'):
    """step(대사 넘기기 A 따위)을 되풀이하다가, close(창 닫기)를 한 사본이 걸을 수 있게 되면 그 사본을 돌려준다.
    입력이 먹는 프레임은 실기와 조금 달라, 정해 둔 횟수 대신 상태를 보고 멈춘다."""
    r = Run(e, Path('.'))
    for i in range(limit):
        if i >= start:
            c = Run(e.snapshot(), Path('.'))
            c.seq(close)
            if walks(c.e, key):
                return c.e
        r.seq(step)
    raise RuntimeError('조작할 수 있는 상태가 되지 않음')


def rep(n, s):
    return ','.join([s] * n)


def warp(e, d, sets, g, k, x, y, key='down', wait=60):
    """fc/dq4/tools/lua/warp.lua 의 맵 갈래: sets 를 쓰고, 주인공 둘레 네 칸을 목적지 출구로 $05A0 에 넣고 key 로 걷는다.
    1B:$8024(장소 쓰기)를 지나면 wait 프레임 뒤의 상태를 돌려준다."""
    e = e.snapshot()
    for a, v in sets:
        e.wr(a, v)
    px, py = e.rd(0x6F60), e.rd(0x6F80)
    for i, (cx, cy) in enumerate(((px, py - 1), (px + 1, py), (px, py + 1), (px - 1, py))):
        for j, v in enumerate((cx & 0xFF, cy & 0xFF, g, k, x, y, 0x80 | 2)):
            e.wr(0x05A0 + 7 * i + j, v)
    e.wr(0x05A0 + 28, 0xFF)
    hit = []
    e.hooks[0x8024] = lambda c: hit.append(1) if c.bank == 0x1B else None
    for _ in range(240):
        e.pad = pad_bits(key)
        e.run_frame()
        if hit:
            break
    del e.hooks[0x8024]
    if not hit:
        raise RuntimeError(f'워프 실패: {g:02X}/{k:02X}')
    e.run(wait)
    assert (e.ram[0x63], e.ram[0x64]) == (g, k), (d, e.ram[0x63], e.ram[0x64])
    return e


def pokes(spec):
    out = []
    for item in spec.split(';'):
        a, v = item.split('=')
        a = int(a, 16)
        for i in range(0, len(v), 2):
            out.append((a + i // 2, int(v[i:i + 2], 16)))
    return out


SCENES = [
    # (이름, 제목, 덤프 폴더/프레임[, 줄 스크롤]). 프레임은 장면 시트(--sheet)로 보고 골랐다.
    # 바다 장면은 줄 스크롤 루틴 1F:$FE36 이 돈 프레임이어야 한다(처리가 밀린 프레임에는 돌지 않아 띠가 안 갈라짐)
    ('credits', '부팅 제작진 화면(760프레임)', 'boot/f00760'),
    ('logo-iv', 'IV 로고(1040프레임)', 'boot/f01040'),
    ('title', '타이틀(2440프레임)', 'boot/f02440'),
    ('adventure-book', '모험의 서 창(전원 켜고 400프레임)', 'name/f00400'),
    ('name-entry', '이름 입력 창(740프레임)', 'name/f00740'),
    ('status-window', '1장 시작, 상태 창', 'ch1/f00180'),
    ('command-window', '5장 시작, 명령 창·대사 창', 'ch5/f01900'),
    ('battle', '1장 첫 전투(150프레임)', 'battle/f00150'),
    ('battle2', '1장 첫 전투(240프레임)', 'battle/f00240'),
    ('chapter1-title', '1장 제목(第一章 王宮の戦士たち, 새로 시작)', 'ch1t/f00240'),
    ('chapter1-end', '1장 끝(第一章 王宮の戦士たち 完)', 'ce1/f00120'),
    ('chapter2-title', '2장 제목(第二章 おてんば姫の冒険)', 'ce1/f00750'),
    ('chapter2-end', '2장 끝(完)', 'ce2/f00360'),
    ('chapter3-title', '3장 제목(第三章 武器屋トルネコ)', 'ce2/f01050'),
    ('chapter3-end', '3장 끝(完)', 'ce3/f00660'),
    ('chapter4-title', '4장 제목(第四章 モンバーバラの姉妹)', 'ce3/f01230'),
    ('chapter4-end', '4장 끝(完)', 'ce4/f00360'),
    ('chapter5-title', '5장 제목(第五章 導かれし者たち)', 'ce4/f01350'),
    ('ending-dawn1', '엔딩: 바다 위 天空城, 동트기 전(줄 스크롤)', 'sea/f01201', True),
    ('ending-dawn2', '엔딩: 바다 위 天空城, 동튼 뒤(줄 스크롤)', 'sea/f02001', True),
    ('ending-cloud', '엔딩: 구름 위 天空城과 열기구', 'ed/f03600'),
    ('ending-staff1', '엔딩 스태프 롤 첫머리', 'ed/f32000'),
    ('ending-staff2', '엔딩 스태프 롤', 'ed/f35600'),
    ('ending-staff3', '엔딩 스태프 롤', 'ed/f40400'),
    ('ending-the-end', '엔딩 마지막(The End)', 'ed/f45200'),
]


def at_of(sub):
    return [int(p.split('/f')[1]) for _, _, p, *_ in SCENES if p.split('/')[0] == sub]


def build(prg, out, only=None, every=0, span=None):
    """only 가 있으면 그 갈래만 every 프레임마다 떠서 시트 확인용으로."""
    out = Path(out)

    def runner(e, sub, log=(), last=None):
        at = at_of(sub)
        if only == sub:
            lo, hi = span or (every, last or max(at))
            at = range(lo, hi + 1, every)
            last = hi
        return Run(e, out / sub, at if (only in (None, sub)) else (), log)

    # 전원 켜기. 처음 몇 프레임 동안 화면이 안정되기 전 차이로 MesenCE(boot.lua) 프레임과 6프레임 어긋나,
    # 입력은 그만큼 앞당겨 준다(fc/dq4/tools/dq4state.sh 의 이름 입력 입력 그대로).
    if only in (None, 'boot'):
        r = runner(dq4nes.NES(prg), 'boot')
        r.frames(max(at_of('boot')))
    r = runner(dq4nes.NES(prg), 'name')
    r.presses('a@294:4,a@314:4,a@334:4,a@354:4,start@394:4,a@434:4,a@554:4,a@694:4', 744)
    name = r.e
    # 커서를 「おわり」로(아래 5칸, 오른쪽 9칸)
    r = Run(name.snapshot(), out / 'x')
    r.seq('wait:10,' + rep(5, 'down:10,wait:10') + ',' + rep(9, 'right:10,wait:10') + ',wait:15')
    owari = r.e

    r = runner(owari.snapshot(), 'ch1t')
    r.seq(rep(8, 'a:4,wait:46'))
    # 이름 확정 뒤 대사를 A 로 넘기고 B 로 창을 닫으면 1장 왕좌의 방(상태 창이 뜬 채 조작 가능)
    throne = advance(owari.snapshot(), 'a:6,wait:44', start=25)
    r = runner(throne.snapshot(), 'ch1', last=600)
    r.frames(max(r.at) if r.at else 0)
    # 성 밖 → 마을 서쪽 끝 필드 → 오가다 전투
    r = Run(throne.snapshot(), out / 'x')
    r.seq('down:150,left:16,down:300,wait:200')
    r.go('down', lambda e: e.ram[0x45] >= 0x1C)
    r.go('left', lambda e: e.ram[0x28] == 0)
    r.seq('wait:200,left:16,up:64')
    for _ in range(60):
        if r.e.wram[0xE49]:
            break
        r.seq('up:48,down:48')
    if not r.e.wram[0xE49]:
        raise RuntimeError('전투가 나지 않음')
    r.seq('wait:10')
    r = runner(r.e.snapshot(), 'battle', last=600)
    r.frames(max(r.at) if r.at else 0)

    # 디버그 장 고르기: 성별·메시지 속도 다음에 「シナリオ」 창
    dbg = bytearray(prg)
    for a in DEBUG_PRG:
        dbg[a] &= 0xF7
    sel = owari.snapshot()
    sel.prg = bytes(dbg)
    pick = 'wait:10,a:6,wait:60,a:6,wait:60,a:6,wait:120,'
    r = Run(sel.snapshot(), out / 'x')
    r.seq(pick + 'right:4,wait:20,a:6,wait:200')
    ch2 = advance(r.e, 'a:4,wait:46', start=5)
    ch2.prg = prg
    if only in (None, 'ch5'):
        r = runner(sel.snapshot(), 'ch5', last=4000)
        r.seq(pick + rep(4, 'right:4,wait:20') + ',a:6,wait:200,' + rep(60, 'a:4,wait:46'))

    # 장 끝(fc/dq4/docs/dq4-save-format.md 의 장 끝 표): 조건을 쓰고 그 맵으로 들어가 60프레임마다 A
    ends = [('ce1', throne, '6283=80;6285=04', 0x02, 0x00, 0x12, 0x0B),
            ('ce2', ch2, '6287=18', 0x01, 0x00, 0x0E, 0x1A),
            ('ce3', ch2, '615A=02;6282=C0', 0x42, 0x01, 0x1F, 0x08),
            ('ce4', ch2, '615A=03;6282=E0;628A=10', 0x04, 0x00, 0x0B, 0x1C)]
    for sub, st, s, g, k, x, y in ends:
        if only not in (None, sub):
            continue
        r = runner(warp(st, sub, pokes(s), g, k, x, y), sub, last=1500)
        r.seq('wait:56,' + rep(25, 'a:4,wait:56'))

    # 엔딩: 5장 끝 조건으로 天空城. 바다 장면은 줄 스크롤 기록과 함께
    if only in (None, 'sea', 'ed'):
        end = warp(ch2, 'ed', pokes('615A=04;6282=F0;62A1=20'), 0x2D, 0x00, 0x0C, 0x07)
        if only in (None, 'sea'):
            r = runner(end.snapshot(), 'sea', log=at_of('sea'), last=2000)
            r.frames(max(r.at))
        if only in (None, 'ed'):
            r = runner(end, 'ed', last=52000)
            r.frames(max(r.at) if r.at else 0)

    spec = []
    for name_, title, p, *line in SCENES:
        x = {'name': name_, 'title': title, 'prefix': str(out / p),
             'source': '롬을 fc/dq4/tools/dq4nes.py 로 돌린 덤프(fc/dq4/tools/dq4scenes.py). 화면(-shot)도 그 덤프로 그린 것'}
        if line:
            x.update({'ppulog': str(out / p.split('/')[0] / 'ppulog.txt'), 'mirror': 'h'})
        spec.append(x)
    (out / 'scenes.json').write_text(json.dumps(spec, ensure_ascii=False, indent=1))


def sheet(d, path, cols=8):
    fs = sorted(Path(d).glob('f*.png'))
    im = Image.new('RGB', (cols * 128, (len(fs) + cols - 1) // cols * 132), 'gray')
    from PIL import ImageDraw
    dr = ImageDraw.Draw(im)
    for i, f in enumerate(fs):
        im.paste(Image.open(f).resize((128, 120)), (i % cols * 128, i // cols * 132))
        dr.text((i % cols * 128 + 2, i // cols * 132 + 120), f.stem, fill='yellow')
    im.save(path)


def main():
    a = sys.argv
    if len(a) < 3:
        print(__doc__)
        sys.exit(2)
    prg = ines.prg(Path(a[1]).read_bytes())
    if '--sheet' in a:
        sub = a[a.index('--sheet') + 1]
        every = int(a[a.index('--every') + 1]) if '--every' in a else 60
        span = tuple(map(int, a[a.index('--range') + 1].split('-'))) if '--range' in a else None
        build(prg, a[2], only=sub, every=every, span=span)
        sheet(Path(a[2]) / sub, Path(a[2]) / f'{sub}.png')
        return
    build(prg, a[2])


if __name__ == '__main__':
    main()
