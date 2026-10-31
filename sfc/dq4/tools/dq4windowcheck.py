"""MesenCE 로 창 글자가 깨지거나 메시지 창에 비치는 화면을 찾는다.

형식은 sfc/dq4/docs/dq4-window-text-format.md 「창 글자 깨짐 검사」. 장면마다 정한 프레임에 VRAM 과 슬롯 키·나이
(7E:3D70·3D14), BG3SC 그림자($0725), NMI 작업($1944)을 덤프해 BG3 타일맵의 칸을 두 규칙으로 본다.

  가나: 칸이 가나 타일(010~078)을 가리키는데 그 그림이 롬 가나(04:E528)와 다르고, 우리 슬롯이 그린 자리(키의 글자 줄과
        그 위 줄)가 아니다. 필드에서 가나 칸 슬롯과 겹친 원래 가나 글자다.
  비침: 필드에서 칸이 살아 있는 캔버스 안 슬롯(096~17F)의 그림을 가리키는데 우리 자리가 아니다. 메시지 창이 우리 그림을 보인다.
  덮임: 캔버스 밖 1D0~ 을 빌린 슬롯이 화면에 보이는데(키 자리가 그 슬롯 첫 칸), 같은 키·나이로 앞서 본 그림과 VRAM 이 다르다.
        다시 그리지 않은 빌린 글자를 명령 창·가게 창 전용 칸 문구가 덮었다.

걸린 프레임은 화면에 빨간 네모를 그려 sheet-*.png 로 모은다.

  MESENCE=... uv run --locked python sfc/dq4/tools/dq4windowcheck.py --rom 롬 --symbols wn.sym \\
      --ship work/state/ship.mss --party 일행셋.mss --out 새폴더
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import random
import re
import subprocess

import dq4mesen as mesen

HERE = Path(__file__).resolve().parent
PROBE = HERE.parents[1] / 'dq5' / 'tools' / 'lua' / 'dq5msg.lua'
KANA_ROM = 0x26528                  # 04:E528, 칸 01 부터 1bpp 8바이트
KANA = range(0x010, 0x079)
CANVAS = range(0x096, 0x180)
BUFFER = 0x5000                     # 창 타일맵 버퍼 7E:5000(32 × 32 칸)
KEYS, AGES = 0x3D70, 0x3D14         # dq4windowname.asm 의 !wt_keys·!wt_ages(슬롯마다 워드)
KANA_ENTRIES, KBASE = 12, 0x3DD8    # !wt_nkana, !wt_kbase(첫 칸 12바이트, 이어서 칸 수 12바이트)
SHARED_JP = 0x60B400                # 맵을 불러올 때 7E:1AC0 으로 복사되는 원래 공용 창 레코드(dq4menupatch.SHARED_JP)
TALK = 'b:4,wait:40,up:3,wait:20,a:4,wait:30,' + ','.join(['a:6,wait:40,down:4,wait:10,a:6,wait:40'] * 10)
# 도구점(선실 대화 02)에서 팔기를 골라 메시지와 목록을 함께 띄운다. 가진 물건 12칸(7E:2056~)을 1장에서 갖출 만한 것(철 장비
# 넷, 약초 둘, 키메라의 날개, 하늘을 나는 구두, 성수, 해독초, 생명의 나무 열매, 힘의 씨앗)으로 채우면 이름이 가나 칸을
# 넘쳐 캔버스 슬롯으로 간다
SELL = 'b:4,wait:40,up:3,wait:20,a:4,wait:30,a:6,wait:60,down:4,wait:20,a:6,wait:80,a:6,wait:80,down:4,wait:30,a:6,wait:80'
FULL_BAG = (0x01, 0x50, 0x78, 0x8A, 0xA1, 0xA1, 0xA4, 0xCD, 0xA3, 0xA2, 0xB1, 0xAD)
# 주인공 이름 7E:2001 에 넣는 「크리프트」 한글 표시 바이트. 세이브스테이트의 가나 이름은 가나 칸 슬롯과 겹쳐 깨진다.
# 09/00 의 몬스터 동료 이름(이름 표 0A, DQ5 데이터)은 가나라 필드 상태 창에서 「가나」 로 걸린다
NAME = '97338C3799299827'


def fuzz(seed):
    r = random.Random(seed)
    o = ['wait:30', 'a:20', 'wait:50', 'down:6', 'wait:20', 'a:20', 'wait:40']
    for _ in range(260):
        o.append(r.choice(['a:20'] * 4 + ['b:20', 'up:6', 'down:6', 'down:6', 'left:6', 'right:6'])
                 + f',wait:{r.choice([5, 10, 20, 40])}')
    return ','.join(o)


# 1장 이무르 방어구점 카운터 앞(일행 둘)에서 대화 → 사기 → 첫 물건 → 「누가」 창. 누가 창과 소지품 창이 물건 목록·메시지와 함께 뜬다
SHOP_WHO = ('wait:30,up:6,wait:30,a:4,wait:30,a:4,wait:90,a:4,wait:60,a:4,wait:60,' + 'a:4,wait:80,' * 3
            + 'a:4,wait:200,a:4,wait:300,' + 'a:4,wait:120,' * 4 + 'b:4,wait:120')


# 09/00 크리프트 소지품 12칸을 긴 이름으로 채우고 도구 → 크리프트 → 셋째 물건. 목록이 가나 칸을 넘쳐 「어떻게 할까」 제목이
# 1D0~ 을 빌리고, 「어떻게 할까」 를 열 때 게임이 뒤의 명령 창을 다시 그린다
PARTY_ITEMS = ';'.join(f'7E{0x2056 + i:04X}={0x0C + i * 3:02X}' for i in range(12))
PARTY_ITEMS_PRE = ('wait:150,a:6,wait:60,right:4,wait:30,down:4,wait:30,a:6,wait:90,a:6,wait:150,a:6,wait:150,'
                   'b:6,wait:90,b:6,wait:90')


def scenes(ship, party, shop=None):
    """(이름, 세이브스테이트, POKE, ROMPATCH, PRE, 프레임)."""
    out = []
    if shop:
        out.append(('shopwho', shop, '', '', SHOP_WHO, range(100, 1900, 30)))
    for n in range(0x40):
        # 선실 파파스의 대화 번호를 바꿔 가게·교회·여관 등을 연다(35C37 = A901 은 대화를 그 번호로 고정)
        out.append((f'talk{n:02X}', ship, f'7E36EB={n:02X};7E370B=00', '35C37=A901', TALK, range(60, 1500, 30)))
    bag = ';'.join(f'7E{0x2056 + i:04X}={b:02X}' for i, b in enumerate(FULL_BAG))
    out.append(('talk02-full', ship, f'7E36EB=02;7E370B=00;{bag}', '35C37=A901', SELL, range(60, 700, 10)))
    for seed in (1, 2, 3, 4):
        out.append((f'ship{seed}', ship, '', '', fuzz(seed), range(100, 8000, 50)))
    out.append(('partyitems', party, PARTY_ITEMS, '', PARTY_ITEMS_PRE, range(60, 900, 30)))
    for seed in (21, 22):
        out.append((f'party{seed}', party, '', '', fuzz(seed), range(100, 8000, 50)))
    for seed in (11, 12):
        # 8523 = FF 는 걸을 때마다 조우
        out.append((f'battle{seed}', party, '', '8523=FF', fuzz(seed), range(100, 8000, 50)))
    return out


def lorom(addr):
    return ((addr >> 16) & 0x7F) * 0x8000 + (addr & 0x7FFF)


def symbols(path):
    out = {}
    for line in path.read_text().splitlines():
        m = re.match(r'([0-9A-Fa-f]{2}):([0-9A-Fa-f]{4}) (\S+)', line)
        if m:
            out[m.group(3)] = int(m.group(1), 16) << 16 | int(m.group(2), 16)
    return out


def slot_table(rom, sym):
    """(전투, 필드). 전투는 [(첫 칸, 칸 수, 필드 전용)], 필드는 [(글자 줄 첫 칸, 위 줄 첫 칸, 열 수)]. 슬롯 수는 WtClass 가
    WtSlot 바로 뒤라는 데서 센다."""
    def words(name, n):
        o = lorom(sym[name])
        return [int.from_bytes(rom[o + 2 * i:o + 2 * i + 2], 'little') for i in range(n)]
    n = (lorom(sym['WtClass']) - lorom(sym['WtSlot'])) // 2
    battle = [(t, (8, 14, 20, 0)[min(c & 0x0F, 3)], c >= 0x10) for t, c in zip(words('WtSlot', n), words('WtClass', n))]
    # 캔버스 밖 슬롯(등급 $20)은 위 줄이 글자 줄 바로 뒤라 WtUpperF 가 0
    field = [(lo, up or lo + cols, cols) for lo, up, c in zip(words('WtSlotF', n), words('WtUpperF', n), words('WtClassF', n))
             for cols in [(4, 7, 10, 0)[min(c & 0x0F, 3)]]]
    return battle, field


def run(mesence, libdir, rom_path, rom, folder, scene):
    name, state, poke, patch, pre, frames = scene
    folder.mkdir(parents=True)
    o = lorom(SHARED_JP)
    # 선실 세이브스테이트는 BG3 타일맵을 옮기기 전 것이라 실내 자리(3C)로 맞춘다. 일행 세이브스테이트는 필드에 서 있어
    # 그대로 둔다(3C 로 두면 타일맵이 필드 그림 자리에 놓여 화면 위쪽이 깨진다)
    sets = ['7E0725=3C'] if name.startswith(('talk', 'ship')) else []
    sets += [f'{0x7E1AC0 + i:X}={b:02X}' for i, b in enumerate(rom[o:o + 48])]
    sets += [f'{0x7E2001 + i:X}={NAME[2 * i:2 * i + 2]}' for i in range(8)]
    fs = ','.join(map(str, frames))
    dump = ','.join(f'{f}:7E{KEYS:04X}:60,{f}:7E{AGES:04X}:60,{f}:7E{KBASE:04X}:24,{f}:7E0725:1,{f}:7E1944:2'
                    for f in frames)
    env = dict(os.environ, LIBDIR=libdir, SHOT_DIR=str(folder), STATE=str(state), PRE=pre, SHOTS=fs, VRAMDUMP=fs,
               DUMP=dump, SET=','.join(sets), MAXF=str(frames[-1] + 10))
    if poke:
        env['POKE'] = poke
    if patch:
        env['ROMPATCH'] = patch
    with (folder / 'log.txt').open('w') as log:
        mesen.run(mesence, rom_path, PROBE, folder=folder, tag='windowcheck', extra=(), env=env, check=False,
                  timeout=1800, stdout=log, stderr=subprocess.STDOUT)


def dumps(folder):
    out = {}
    for line in (folder / 'msg.txt').read_text().splitlines():
        m = re.match(r'(\d+) dump (7E[0-9A-F]{4}) (.*)', line)
        if m:
            out.setdefault(int(m.group(1)), {})[int(m.group(2), 16) & 0xFFFF] = bytes.fromhex(m.group(3))
    return out


def check(folder, rom, slots):
    """[(프레임, [(줄, 열, 규칙, 타일)])] 걸린 프레임만."""
    kana = {t: bytes(x for b in rom[KANA_ROM + (t - 1) * 8:KANA_ROM + t * 8] for x in (b, 0xFF)) for t in KANA}
    out, seen = [], {}
    for frame, d in sorted(dumps(folder).items()):
        vram_path = folder / f'v{frame:05d}.bin'
        if not vram_path.exists() or len(d) < 5:
            continue
        vram = vram_path.read_bytes()
        keys, ages = d[KEYS], d[AGES]
        battle = int.from_bytes(d[0x1944], 'little') == 0x8952
        mine, live = set(), {}
        kb = d[KBASE]
        battle_slots, field_slots = slots
        if battle:
            canvas = [range(t, t + size) for t, size, field_only in battle_slots]
        else:
            canvas = [list(range(lo, lo + n)) + list(range(up, up + n)) for lo, up, n in field_slots]
        cells = [range(kb[i], kb[i] + kb[KANA_ENTRIES + i]) for i in range(KANA_ENTRIES)] + canvas[KANA_ENTRIES:]
        for i, tiles in enumerate(cells):
            key = int.from_bytes(keys[2 * i:2 * i + 2], 'little')
            age = int.from_bytes(ages[2 * i:2 * i + 2], 'little')
            if not key or not age:
                continue
            c = (key - BUFFER) // 2
            mine |= {c + j for j in range(10)} | {c - 32 + j for j in range(10)}
            if not (battle and (i < KANA_ENTRIES or battle_slots[i][2])):
                live.update({t: i for t in tiles})
        tilemap = (d[0x0725][0] & 0xFC) << 8
        bad = []
        # 캔버스 밖 1D0~1FF 슬롯은 필드 표에서 위 줄이 글자 줄 바로 뒤라 열 수 × 2 칸이 이어진다
        lent = [] if battle else [(i, lo, 2 * n) for i, (lo, up, n) in enumerate(field_slots) if lo >= 0x1D0]
        for i, tile, size in lent:
            key = int.from_bytes(keys[2 * i:2 * i + 2], 'little')
            age = int.from_bytes(ages[2 * i:2 * i + 2], 'little')
            if not key or not age:
                continue
            c = (key - BUFFER) // 2
            if not 0 <= c < 32 * 28:
                continue
            if int.from_bytes(vram[(tilemap + c) * 2:(tilemap + c) * 2 + 2], 'little') & 0x3FF != tile:
                continue
            art = vram[(0x1000 + tile * 8) * 2:(0x1000 + (tile + size) * 8) * 2]
            if seen.setdefault((i, key, age), art) != art:
                bad += [(c // 32, c % 32 + j, '덮임', tile + j) for j in range(size // 2)]
        for cell in range(32 * 28):         # 화면은 28줄(224점)
            if cell in mine:
                continue
            t = int.from_bytes(vram[(tilemap + cell) * 2:(tilemap + cell) * 2 + 2], 'little') & 0x3FF
            if t in KANA and vram[(0x1000 + t * 8) * 2:(0x1000 + t * 8) * 2 + 16] != kana[t]:
                bad.append((cell // 32, cell % 32, '가나', t))
            elif not battle and t in CANVAS and t in live:
                bad.append((cell // 32, cell % 32, '비침', t))
        if bad:
            out.append((frame, bad))
    return out


def sheet(folder, hits, path):
    from PIL import Image, ImageDraw
    shots = []
    for frame, bad in hits[:12]:
        p = folder / f's{frame:05d}.png'
        if not p.exists():
            continue
        im = Image.open(p).convert('RGB')
        dr = ImageDraw.Draw(im)
        for r, c, _, _ in bad:
            dr.rectangle((c * 8, r * 8, c * 8 + 7, r * 8 + 7), outline=(255, 0, 0))
        shots.append(im)
    if not shots:
        return
    w, h = shots[0].size
    out = Image.new('RGB', (w * 4, h * ((len(shots) + 3) // 4)))
    for i, im in enumerate(shots):
        out.paste(im, ((i % 4) * w, (i // 4) * h))
    out.save(path)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--rom', type=Path, required=True)
    ap.add_argument('--symbols', type=Path, required=True, help='DQ4_WINDOWNAME_SYMBOLS 로 남긴 심볼 파일')
    ap.add_argument('--ship', type=Path, required=True, help='선실 세이브스테이트')
    ap.add_argument('--party', type=Path, required=True, help='일행 셋 세이브스테이트(09/00)')
    ap.add_argument('--shop', type=Path, help='1장 롬으로 이무르 37/00 의 셀 34,9(방어구점 카운터 앞)에 일행 둘로 선 세이브스테이트')
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--only', help='이 글자가 이름에 든 장면만')
    ap.add_argument('--jobs', type=int, default=8)
    a = ap.parse_args()
    mesence = os.environ.get('MESENCE')
    if not mesence:
        ap.error('MESENCE 에 MesenCE 실행 파일을 주세요')
    out = a.out.resolve()
    if out.exists():
        ap.error('--out 은 아직 없는 폴더를 주세요')
    rom = a.rom.read_bytes()
    slots = slot_table(rom, symbols(a.symbols))
    libdir = os.environ.get('LIBDIR') or subprocess.check_output(
        ['uv', 'run', '--locked', 'krpatch', 'sfc', 'lua'], text=True).strip()
    todo = [s for s in scenes(a.ship.resolve(), a.party.resolve(), a.shop and a.shop.resolve()) if not a.only or a.only in s[0]]
    with ThreadPoolExecutor(a.jobs) as pool:
        list(pool.map(lambda s: run(mesence, libdir, a.rom, rom, out / s[0], s), todo))
    flagged = 0
    for s in todo:
        folder = out / s[0]
        hits = check(folder, rom, slots)
        frames = len(list(folder.glob('v*.bin')))
        if hits:
            flagged += 1
            sheet(folder, hits, out / f'sheet-{s[0]}.png')
            first = ', '.join(f'{f}:{len(b)}칸({b[0][2]} {b[0][3]:03X})' for f, b in hits[:4])
            print(f'FAIL {s[0]} {len(hits)}/{frames} 프레임  {first}')
        else:
            print(f'PASS {s[0]} {frames} 프레임')
    if flagged:
        raise SystemExit(f'{flagged}개 장면에서 깨진 칸')


if __name__ == '__main__':
    main()
