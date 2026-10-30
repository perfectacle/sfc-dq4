"""DQ5(SFC) 필드(세계 지도) 그림 쓰기. 타일(512~1,024개)·타일 팔레트 니블·타일 속성·필드 팔레트 2·3번 줄·물결 색·
움직이는 타일 벌·세계 0 낮밤 인물 팔레트(11·12번 줄)를 내보내고 고친 것을 넣는다. 블록 정의(2A:A32C·AD27)는 dq5fieldtables.py,
지도는 dq5fieldwrite.py 가 쓴다. 형식은 sfc/dq5/docs/dq5-field-format.md 의 「타일 그래픽과 팔레트」「팔레트」, 입력은
sfc/dq5/docs/dq5-build-format.md 「필드 그림 `dq5fieldgfx/1`」.

  dump   롬 → 폴더(-o). fieldgfx.json, tiles.bin(4bpp SNES 타일 512개), anim.bin(움직이는 타일 6개 × 8벌)
  patch  fieldgfx.json → 패치 목록(-o). 바뀐 것이 없으면 쓰기 0개. 다시 싼 RLE 가 원래보다 길면
         --tiles-at·--anim-at BB:AAAA(30~3F, 한 뱅크 안)로 옮긴다. 움직이는 타일 벌을 16개로 늘리면 --anim-at,
         세계 1·2 의 타일 벌(worlds)을 주면 --worlds-at 이 필요하다. 타일을 512개 넘게 쓰면 --worlds-at 과
         --extra-at(늘린 타일, 30~7D), 세계 0 의 2·3번 줄 벌 수·시간대 표·밤 시작이나 세계 1·2 의 벌 수·시간대 표를
         바꾸면 --palettes-at(30~3F)
  check  두 RLE 를 다시 싸서 풀기, 내보낸 그대로 patch 하면 쓰기 0개인지

타일: 12:B1A8 의 RLE(01:A4A7 이 뱅크, 01:A4AE 가 주소 즉값)를 7E:C000 에 풀면 평면 0~3 이 4KB 씩.
움직이는 타일: 1E:D0FF 의 RLE(2B:8006 뱅크, 2B:8016 주소)를 7E:C800 에 1,536바이트. 둘 다 DB 를 자료 뱅크로 두고
DMA 레지스터를 절대 주소로 쓰는 루틴(01:A64F·2B:8039)이 읽으므로 30~3F 의 한 뱅크 안에만 옮긴다.
벌은 02:ACD5 가 $1C31 로 02:AD89 의 WRAM 주소 표를 골라 넘기고 02:ACE7 의 AND #$07 로 돈다.
세계마다 타일 벌: 01:A4A7(10바이트)을 JSL 로 바꿔 $1949 로 [주소][뱅크] 표를 고르고, 니블을 읽는 00:BBB4·BBBE·BBDA·BBE4 의
LDA $2AD712,X 를 세계마다 256바이트 표를 읽는 JSL 로 바꾼다.
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(__file__))
from dq5field import (BLOCK_LOWER, BLOCK_UPPER, FIELD_CHR, TILE_PALETTE, block_count, block_tiles,  # noqa: E402
                      nibble_table, rle)
from dq5gfx import FIELD_ANIM as ANIM, FIELD_ANIM_COUNT, FIELD_ANIM_SETS, FIELD_ANIM_TILE  # noqa: E402
from dq5fieldwrite import TILE_BITS  # noqa: E402
from dq5map import Rom, lorom  # noqa: E402

FORMAT = 'dq5fieldgfx/1'
BANK = 0x8000
TILES = 512
ANIM_BYTES = FIELD_ANIM_COUNT * FIELD_ANIM_SETS * 32
# 이 타일들은 움직이는 타일 벌이 늘 덮으므로 tiles.bin 에서 고쳐도 보이지 않는다.
ANIM_SLOTS = range(FIELD_ANIM_TILE, FIELD_ANIM_TILE + FIELD_ANIM_COUNT)
# 2·3번 줄 색 1~15 를 차례로 60바이트. 세계 0 은 시간대 8벌(01:A132 가 고름), 세계 1·2 는 한 벌.
PALETTE_SETS = {'world1': [0x01A199], 'world0': [0x01A1D5 + k * 60 for k in range(8)], 'world2': [0x01A3B5]}
WAVE, WAVE_STEPS = 0x01A0F6, 10        # 세계 0 의 4번 줄 색 1~3, $1961 단계마다 6바이트
# 2·3번 줄 색 14·15(30색 목록의 13·14·28·29번)는 02:ABEF~ABFE 가 몇 프레임마다 두 값으로 덮으므로 고칠 수 없다.
CYCLED = (13, 14, 28, 29)
SITES = {'tiles': ((0x01A4A8, b'\x12'), (0x01A4AF, b'\xa8\xb1')), 'anim': ((0x2B8007, b'\x1e'), (0x2B8017, b'\xff\xd0'))}
SOURCES = {'tiles': FIELD_CHR, 'anim': ANIM}
# 세계 0 의 인물 팔레트: 01:A132 가 고른 시간대 색인이 0C 이상($075E 00F1~01FD)이면 01:A422, 아니면 01:A45E 를
# 01:A3F1 이 11·12번 줄 색 1~15 에 옮긴다(30색, 60바이트).
PERSON = {'day': 0x01A45E, 'night': 0x01A422}
# 움직이는 타일 벌: 2B:8000 이 7E:C800 에 풀고, 02:ACD5 가 $1C31 로 02:AD89 의 WRAM 주소 표를 골라 $1C13 에 둔다.
# 필드에서 7E:CE00~DFFF 는 타일을 올린 뒤 읽고 쓰는 코드가 없어(실측) 벌은 D400 까지, 16벌까지 늘린다.
ANIM_SET = FIELD_ANIM_COUNT * 32
ANIM_WRAM = 0xC800
ANIM_COUNTS = (1, 2, 4, 8, 16)
ANIM_TABLE = 0x02AD89
ANIM_SITES = {'table': (0x02ACD5, b'\xbf\x89\xad\x02'), 'table_hi': (0x02ACDC, b'\xbf\x8a\xad\x02'),
              'mask': (0x02ACE7, b'\x29\x07')}
# 세계마다 타일 벌. 01:A4A7 의 LDA #$12 / STA $4374 / PHA / PLB / LDX #$B1A8 을 JSL 과 BRA 로 바꾸고,
# 니블 읽기 넷(LDA $2AD712,X)을 JSL 로 바꾼다.
LOAD_SITE, LOAD_ORIG = 0x01A4A7, bytes.fromhex('a9128d744348aba2a8b1')
NIB_SITES = (0x00BBB4, 0x00BBBE, 0x00BBDA, 0x00BBE4)
NIB_ORIG = bytes.fromhex('bf12d72a')
WORLDS = ('world0', 'world1', 'world2')


def cpu(a):
    return f'{a >> 16:02X}:{a & 0xFFFF:04X}'


def check_sites(rom):
    sites = [(at, want, kind) for kind, ss in SITES.items() for at, want in ss]
    sites += [(at, want, 'anim') for at, want in ANIM_SITES.values()]
    sites += [(LOAD_SITE, LOAD_ORIG, 'tiles'), *((at, NIB_ORIG, 'tile_palettes') for at in NIB_SITES)]
    sites += [(BLOCK_READ, BLOCK_READ_ORIG, 'blocks'), (PALETTE_READ, PALETTE_READ_ORIG, 'tile_palettes')]
    sites += [(REDRAW_SITE, REDRAW_ORIG, 'redraw')]
    sites += [(at, want, 'palettes') for at, want in (SEARCH_SITE, PTR_SITE, NIGHT_SITE, PAL_BANK_SITE, WAVE_SITE)]
    sites += [(at, want, 'tile_attributes') for at, want in ATTR_SITES.items()] + [(REDRAW_RTL, b'\x6b', 'redraw')]
    sites += [(at, want, 'palettes') for pair in W12_LOAD.values() for at, want in pair] + [(*REFRESH_SITE, 'palettes')]
    for at, want, kind in sites:
        if rom.d[lorom(at):lorom(at) + len(want)] != want:
            raise ValueError(f'{cpu(at)}: 원래 롬의 {kind} 코드가 아님; 원본 롬으로 만들어야 함')


def long_addr(a):
    return bytes([a & 0xFF, a >> 8 & 0xFF, a >> 16])


def load_hook(table):
    """01:A4A7 대신. $1949(세계, & 3)로 table 의 4바이트 [주소 16비트][뱅크][0] 을 골라 $4374·DB 를 뱅크로, X 를 주소로.
    원래 코드처럼 STA $4374 는 들어온 DB 로 쓴다. A 8비트, X 16비트, D = 0(01:A4A3 의 TDC 가 기대함).
    나갈 때 A 의 윗바이트는 원래처럼 0 으로 둔다."""
    return (b'\x7b' + b'\xaf\x49\x19\x7e' + b'\x29\x03' + b'\x0a\x0a' + b'\xaa'
            + b'\xbf' + long_addr(table + 2) + b'\x8d\x74\x43' + b'\x48'
            + b'\xc2\x20' + b'\xbf' + long_addr(table) + b'\xaa' + b'\x7b' + b'\xe2\x20' + b'\xab' + b'\x6b')


def nib_hook(tables, wide=False):
    """LDA $2AD712,X 대신. X(16비트)와 A 의 윗바이트를 지키고 tables + 세계*256 + X 를 읽는다.
    00:BBC9 가 XBA 로 윗바이트를 타일맵 워드의 아랫바이트에 넣으므로 윗바이트가 바뀌면 타일 번호가 어긋난다.
    부른 곳은 바로 AND 로 플래그를 다시 정한다. wide 면 CLC 자리에 ASL A 를 두어 세계*512 로 읽는다
    (세계*256 은 0300 이하라 ASL 뒤 C 가 늘 0 이다). 또 wide 면 윗바이트를 0 으로 돌려준다. 부른 곳의 윗바이트는
    LDA $94 / LSR A 가 남긴 (타일 >> 1) >> 8 이라 타일 512 이상이면 1 이 되어, XBA·ORA 뒤 타일 번호 bit0 이 켜진다.
    원래 롬은 타일이 512 미만이라 늘 0 이었다."""
    return (b'\xda' + b'\xeb' + b'\x48' + b'\xc2\x20' + b'\xaf\x49\x19\x7e' + b'\x29\x03\x00' + b'\xeb'
            + (b'\x0a' if wide else b'\x18') + b'\x63\x02' + b'\xaa' + b'\xe2\x20' + b'\x68' + b'\xeb'
            + b'\xbf' + long_addr(tables) + b'\xfa' + (b'\xeb\x29\x00\xeb' if wide else b'') + b'\x6b')


LOAD_LEN, NIB_LEN = len(load_hook(0)), len(nib_hook(0))

# 세계 0 의 2·3번 줄 벌 늘리기(--palettes-at). 01:A132 가 [하한 16비트][색인] 10항목(01:A16B)을 뒤에서부터 보아
# $075E 이상인 첫 항목의 색인(벌 번호 × 2)으로 01:A189 의 포인터를 고르고, 01:A090 이 그 벌을 DMA 로(뱅크 즉값 01:A0B1)
# 옮긴다. 같은 DMA 뱅크로 물결 색(01:A0E3 의 즉값 A0F6)도 옮기므로 벌을 옮기면 물결 표도 함께 옮긴다.
# 색인이 0C 이상(01:A145 의 CPX 즉값)이면 밤 인물 팔레트다. X 는 8비트라 항목 86개·벌 128개까지.
TIMES, TIME_COUNT, TIME_PTRS = 0x01A16B, 10, 0x01A189
NIGHT_FROM = 6
FIELD_PAL_MAX, TIME_MAX = 128, 86
SEARCH_SITE = (0x01A132, bytes.fromhex('a01bad5e07d96ba1b005888888 80f6be6da1'.replace(' ', '')))
PTR_SITE = (0x01A166, bytes.fromhex('bd89a1a8'))
NIGHT_SITE, PAL_BANK_SITE, WAVE_SITE = (0x01A145, b'\x0c'), (0x01A0B1, b'\x01'), (0x01A0E3, b'\xf6\xa0')


def search_hook(times, n):
    """01:A132 대신(M 16비트, X 8비트, DB = 01). 시간대 표 times 의 n항목을 뒤에서부터 보아 $075E 이상인 첫 항목의
    색인을 X 에 둔다. 첫 항목의 하한은 0 이라 늘 멈춘다."""
    return (bytes([0xA2, (n - 1) * 3]) + b'\xaf\x5e\x07\x7e' + b'\xdf' + long_addr(times) + b'\xb0\x05'
            + b'\xca\xca\xca' + b'\x80\xf5' + b'\xbf' + long_addr(times + 2) + b'\x29\xff\x00' + b'\xaa' + b'\x6b')


def ptr_hook(ptrs):
    """01:A166 의 LDA $A189,X / TAY 대신(M·X 16비트). 옮긴 포인터 표를 읽는다."""
    return b'\xbf' + long_addr(ptrs) + b'\xa8' + b'\x6b'


SEARCH_LEN, PTR_LEN = len(search_hook(0, 1)), len(ptr_hook(0))

# 세계 1·2 의 2·3번 줄 벌 늘리기(--palettes-at). 원래는 01:9F86·9FA0 이 $075E 를 0 으로 두고 LDX #벌 / LDA #뱅크(01) 로
# 한 벌을 01:A6A3 에 넘기며, 몇 프레임마다 다시 옮기는 02:AD38 은 세계 0 일 때만 01:A055 를 부른다. 시계(00:82C6)도 세계 0 에서만
# 돌아 두 세계는 늘 $075E = 0 이다. 늘리면 불러올 때는 시간대 표 첫 항목(하한 0)의 벌을 넘기고, 02:AD38 을 훅으로 바꿔
# 세계 1·2 에서도 $075E 로 시간대 표를 찾아 그 벌을 7E:3956·3976(2·3번 줄 색 1~15)에 MVN 으로 옮긴다. $075E 를 0 으로 두는 것과
# 시계는 바꾸지 않으므로, 벌은 이벤트 등이 $075E 를 바꿀 때만 바뀐다.
W12_LOAD = {1: ((0x019F8C, b'\xa2\x99\xa1'), (0x019F91, b'\xa9\x01')),
            2: ((0x019FA6, b'\xa2\xb5\xa3'), (0x019FAB, b'\xa9\x01'))}
REFRESH_SITE = (0x02AD38, bytes.fromhex('ad4919d0042255a001'))
W12_DEFAULT_TIMES = [[0, 0]]


def world_refresh(times, n, ptrs, bank):
    """세계 1·2 하나의 갈래(M·X 16비트, PHP 를 한 뒤). 시간대 표 n항목을 뒤에서부터 보아 $075E 이상인 첫 항목의 벌을 옮긴다."""
    mvn = b'\x54\x7e' + bytes([bank])
    return (b'\xa2' + ((n - 1) * 3).to_bytes(2, 'little') + b'\xaf\x5e\x07\x7e' + b'\xdf' + long_addr(times)
            + b'\xb0\x05' + b'\xca\xca\xca' + b'\x80\xf5' + b'\xbf' + long_addr(times + 2) + b'\x29\xff\x00' + b'\xaa'
            + b'\xbf' + long_addr(ptrs) + b'\xaa' + b'\x8b' + b'\xa0\x56\x39' + b'\xa9\x1d\x00' + mvn
            + b'\xa0\x76\x39' + b'\xa9\x1d\x00' + mvn + b'\xab' + b'\x28\x6b')


def refresh_hook(worlds, bank):
    """02:AD38 의 LDA $1949 / BNE / JSL $01A055 대신(JSL). 세계 0 이면 원래처럼 01:A055 를 부르고, 세계 1·2 는 옮긴 벌이
    있으면 world_refresh 로 옮긴다. worlds 는 {1: (시간대 표, 항목 수, 포인터 표) 또는 None, 2: …}. 머리는 BRA 로 건너뛰는
    [세계 1 시간대 표 24비트][항목 수][세계 2 …](없으면 0)."""
    head = b''.join(long_addr(w[0]) + bytes([w[1]]) if w else bytes(4) for w in (worlds[1], worlds[2]))
    arms = [world_refresh(*worlds[k], bank) if worlds[k] else b'\x28\x6b' for k in (1, 2)]
    pick = b'\xc9\x01\x00\xf0' + bytes([7]) + b'\xc9\x02\x00\xf0' + bytes([2 + len(arms[0])]) + b'\x28\x6b'
    return (b'\x80\x08' + head + b'\x08\xe2\x20\xaf\x49\x19\x7e\xd0\x06\x22\x55\xa0\x01\x28\x6b'
            + b'\xc2\x30\x29\x03\x00' + pick + arms[0] + arms[1])


def read_world12(rom):
    """세계 1·2 의 (벌 목록, 시간대 표). 02:AD38 훅이 없으면 원래 한 벌과 [[0, 0]]."""
    out = {k: ([colors(rom, PALETTE_SETS[f'world{k}'][0], 30)], [list(t) for t in W12_DEFAULT_TIMES]) for k in (1, 2)}
    if rom.u8(REFRESH_SITE[0]) != 0x22:
        return out
    hook = rom.u24(REFRESH_SITE[0] + 1)
    for k in (1, 2):
        times, n = rom.u24(hook + 2 + (k - 1) * 4), rom.u8(hook + 5 + (k - 1) * 4)
        if not times:
            continue
        ptrs = times + n * 3
        count = (rom.u16(ptrs) - (ptrs & 0xFFFF)) // 2           # 벌이 포인터 표 바로 뒤에 붙어 있다
        bank = (times >> 16) << 16
        out[k] = ([colors(rom, bank | rom.u16(ptrs + i * 2), 30) for i in range(count)],
                  [[rom.u16(times + i * 3), rom.u8(times + i * 3 + 2) // 2] for i in range(n)])
    return out


def worlds_layout(at):
    """--worlds-at 자리의 (불러오기 훅, 니블 훅, 고르기 표 16바이트, 니블 표 4 × 256바이트, 그 뒤 RLE)."""
    nib = at + LOAD_LEN
    table = nib + NIB_LEN
    tables = table + 16
    return at, nib, table, tables, tables + 0x400


# 타일 늘리기(512개 넘게). 필드에서 BG1·2 글자 기준이 VRAM 워드 2000 이라 타일 512~1023 은 워드 4000~5FFF 이고,
# 필드에 선 동안 이 자리에 쓰는 코드는 없다(실측). 전투가 이 자리를 배경 그림으로 덮으므로, 필드에 들어갈 때(01:A4A7)와
# 화면을 끈 동안 타일맵을 CPU 로 다시 쓰는 01:B4D5 에서 늘린 타일을 DMA 채널 7 로 다시 보낸다. 01:B4D5 를 부르는 곳은
# 전투 뒤 맵 화면을 되살리는 01:8A87(01:8AA8)과 화면 다시 그리기 00:A771(00:A788) 둘이라 부르는 곳이 아닌 01:B4D5 를 훅으로 둔다. 블록의 10번째 비트는 상위 비트 바이트의 하위 니블(원래 롬에서 모두 0)이다.
MAX_TILES = 1024
EXTRA_VRAM = 0x4000
# 블록 표 읽기 00:BC6D~BC9B(PHB / PHK / PLB 부터 RTS 까지)와 타일에 팔레트 비트를 붙이는 00:BBAC~BBF6. 필드를 불러올 때
# 화면 칸마다 하나씩 불려, 칸마다 몇 사이클만 길어도 불러오기가 프레임 단위로 늦어진다. 그래서 훅으로 빼지 않고 제자리에서
# 같은 길이 안에 바꾼다(block_read·palette_fast).
BLOCK_READ = 0x00BC6D
BLOCK_READ_ORIG = bytes.fromhex('8b4babe220bf2ca32a8594bf27ad2a8596a602bf30a32a399cbcf002a9018595'
                                'bf2bad2a399cbcf002a9018597ab60')
PALETTE_READ = 0x00BBAC
PALETTE_READ_ORIG = bytes.fromhex('a5964aaae220b00abf12d72a29f04a4a8008bf12d72a290f0a0a186908c220eb059605c68596'
                                  'a5944aaae220b00abf12d72a29704a4a8008bf12d72a29070a0a186908c220eb0594859460')
# 01:B4D5 는 JSR $B50A / RTL 이다. 4바이트 JML 이 그 RTL 까지 덮으므로, 훅은 끝에 뱅크 01 의 다른 RTL(01:8A87 의 끝
# 01:8ABA)을 돌아올 자리로 PEA 하고 JML $01B50A 로 간다. B50A 의 RTS 가 그 RTL 로 가서 부른 곳에 돌아간다.
REDRAW_SITE, REDRAW_ORIG = 0x01B4D5, bytes.fromhex('200ab56b')
REDRAW_BODY, REDRAW_RTL = 0x01B50A, 0x018ABA
# 타일 속성: 00:BCA8 이 블록 위층 타일(0 이면 아래층)을 AND #$01FF 로 잘라 2A:D512 의 512바이트 표를 읽는다(00:C82C·C83B·
# E32E·01:8192·2B:81E9·81F6 이 부름). 늘리면 AND 둘을 #$03FF 로, 표 읽기를 1,024바이트 표로 바꾼다.
TILE_ATTR = 0x2AD512
ATTR_SITES = {0x00BCB0: b'\x29\xff\x01', 0x00BCB7: b'\x29\xff\x01', 0x00BCBD: bytes.fromhex('bf12d52a')}


def dma_sub(table):
    """M·X 16비트로 X = 세계 × 8 을 받아 table 항목의 [늘린 타일 뱅크][주소][크기]를 VRAM 워드 4000 에 DMA 로 보낸다.
    크기가 0 이면 아무것도 하지 않는다. DB 와 상관없이 긴 주소로 쓴다. VRAM 주소는 시작 바로 앞에 둔다
    (NMI 가 그 사이에 VRAM 주소를 바꿀 틈을 줄이려고)."""
    def sta(reg):
        return b'\x8f' + reg.to_bytes(2, 'little') + b'\x00'
    body = (b'\xbf' + long_addr(table + 4) + sta(0x4372)
            + b'\xa9\x01\x18' + sta(0x4370)
            + b'\xe2\x20' + b'\xbf' + long_addr(table + 3) + sta(0x4374)
            + b'\xa9\x80' + sta(0x2115)
            + b'\xc2\x20' + b'\xa9' + EXTRA_VRAM.to_bytes(2, 'little') + sta(0x2116)
            + b'\xe2\x20' + b'\xa9\x80' + sta(0x420B) + b'\xc2\x20')
    return b'\xbf' + long_addr(table + 6) + b'\xf0' + bytes([len(body) + 4]) + sta(0x4375) + body + b'\x60'


def grow_load_hook(table, dma):
    """01:A4A7 대신(늘린 타일). 세계 항목(8바이트)을 골라 늘린 타일을 보내고, load_hook 과 같이 RLE 뱅크·주소를 둔다."""
    return (b'\x7b' + b'\xaf\x49\x19\x7e' + b'\x29\x03' + b'\x0a\x0a\x0a' + b'\xaa'
            + b'\xc2\x20' + b'\x20' + (dma & 0xFFFF).to_bytes(2, 'little') + b'\xe2\x20'
            + b'\xbf' + long_addr(table + 2) + b'\x8d\x74\x43' + b'\x48'
            + b'\xc2\x20' + b'\xbf' + long_addr(table) + b'\xaa' + b'\x7b' + b'\xe2\x20' + b'\xab' + b'\x6b')


def redraw_hook(dma):
    """01:B4D5 대신(JML 로 들어옴). 필드($BE bit7 = 0)이면 그 세계의 늘린 타일을 다시 보내고, 레지스터·P 를 되돌린 뒤
    원래처럼 01:B50A 를 부른 다음 01:8ABA 의 RTL 로 부른 곳에 돌아간다."""
    body = b'\xaf\x49\x19\x7e' + b'\x29\x03\x00' + b'\x0a\x0a\x0a' + b'\xaa' + b'\x20' + (dma & 0xFFFF).to_bytes(2, 'little')
    return (b'\x08' + b'\xc2\x30' + b'\x48' + b'\xda' + b'\xaf\xbe\x00\x7e' + b'\x29\x80\x00'
            + b'\xd0' + bytes([len(body)]) + body + b'\xfa' + b'\x68' + b'\x28'
            + b'\xf4' + (REDRAW_RTL - 1 & 0xFFFF).to_bytes(2, 'little') + b'\x5c' + long_addr(REDRAW_BODY))


def block_read(bits):
    """00:BC6D 대신(M·X 16비트, X = 번호 × 5 + 칸, Y = 칸, $02 = 번호 × 5). 원래처럼 $94·$96 에 두 층 타일의 하위
    8비트를 두고, $95·$97 에는 상위 비트 바이트의 그 칸 9·10번째 비트(00:BC9C 의 80>>칸, 00:BCA4 의 08>>칸)를
    TILE_BITS(bits) 한 번으로 읽어 둔다. 칸을 A 윗바이트에 두고 상위 비트 바이트를 아랫바이트로 읽어 TAX 하면 그 표의
    색인이 된다. 긴 주소로만 읽어 DB 를 바꾸지 않는다. 원래보다 짧아 00:BC9B 앞에서 RTS 한다."""
    def bits_of(table, dp):
        return b'\xa6\x02\xbf' + long_addr(table + 4) + b'\xaa\xbf' + long_addr(bits) + bytes([0x85, dp])
    return (b'\xe2\x20' + b'\xbf' + long_addr(BLOCK_LOWER) + b'\x85\x94' + b'\xbf' + long_addr(BLOCK_UPPER) + b'\x85\x96'
            + b'\x98\xeb' + bits_of(BLOCK_LOWER, 0x95) + bits_of(BLOCK_UPPER, 0x97) + b'\x60')


def palette_fast(upper, lower):
    """00:BBAC~BBF6 대신(M·X 16비트, 원래보다 짧아 BBF6 앞에서 RTS). 원래는 위층 $96·아래층 $94 타일을 >> 1 해 니블
    (짝수 타일은 위 니블)을 고르고 (니블 × 4 + 8)을 타일맵 워드 윗바이트에 붙인다(위층 니블 4비트·아래층 3비트, 위층에만
    $C6 을 ORA). 여기서는 그 윗바이트를 타일마다 1바이트 표(upper·lower, 1,024바이트씩)에서 타일 번호로 바로 읽어
    $97·$95 에 ORA 한다. 나갈 때 A 는 원래처럼 $94 다(00:B769·B7B5 가 그대로 타일맵에 씀).
    원래 롬은 LSR 뒤 A 윗바이트(타일 >> 9)가 XBA 로 타일맵 워드의 아랫바이트에 섞이는데 타일이 512 미만이라 늘 0 이었다."""
    def layer(dp, table):
        return bytes([0xA5, dp]) + b'\xaa\xe2\x20\xbf' + long_addr(table) + bytes([0x05, dp + 1, 0x85, dp + 1]) + b'\xc2\x20'
    return layer(0x96, upper) + b'\xa5\x96\x05\xc6\x85\x96' + layer(0x94, lower) + b'\xa5\x94\x60'


def palette_bytes(nib):
    """palette_fast 의 (위층 표, 아래층 표). nib 는 타일마다 니블."""
    nib = list(nib) + [0] * (MAX_TILES - len(nib))
    return bytes(((n & 15) << 2) + 8 for n in nib), bytes(((n & 7) << 2) + 8 for n in nib)


GROW_LOAD_LEN = len(grow_load_hook(0, 0))
DMA_LEN, REDRAW_LEN = len(dma_sub(0)), len(redraw_hook(0))
GROW_ENTRY = 8
# 블록 표 읽기를 제자리에서 바꾸기 전 판은 00:BC80·BC8D 를 JSL 훅 둘(25바이트씩, LDA long 으로 시작)로 바꾸고 그 훅을
# 니블 훅 바로 뒤에 두었으며 칸 비트 표·팔레트 표가 없었다. 그렇게 만든 롬도 읽는다.
OLD_BLOCK_HOOK_LEN = 25


def grow_layout(at, block_hooks=False):
    """타일 늘리기 --worlds-at 자리. 이름 → 주소: 불러오기 훅·니블 훅·다시 그리기 훅·DMA·고르기 표(세계 넷 × 8바이트:
    [RLE 주소 16][RLE 뱅크][늘린 타일 뱅크][주소 16][크기 16])·니블 표(4 × 512바이트)·타일 속성(1,024바이트)·
    블록 칸 9·10번째 비트 표(TILE_BITS)·palette_fast 의 위층·아래층 표(1,024바이트씩)·그 뒤 세계 1·2 RLE.
    block_hooks 면 예전 판: 니블 훅 뒤에 블록 훅 둘(block_lower·block_upper)이 있고 칸 비트 표·팔레트 표가 없다."""
    hooks = (('block_lower', OLD_BLOCK_HOOK_LEN), ('block_upper', OLD_BLOCK_HOOK_LEN)) if block_hooks else ()
    tail = () if block_hooks else (('tile_bits', len(TILE_BITS)), ('palettes', MAX_TILES * 2))
    out, a = {}, at
    for name, n in (('load', GROW_LOAD_LEN), ('nib', len(nib_hook(0, wide=True))), *hooks,
                    ('redraw', REDRAW_LEN), ('dma', DMA_LEN), ('table', GROW_ENTRY * 4), ('tables', 0x800),
                    ('attrs', MAX_TILES), *tail):
        out[name] = a
        a += n
    out['rles'] = a
    return out


def rom_layout(rom):
    """01:A4A7 의 JSL 이 가리키는 타일 늘리기 자리(grow_layout). 니블 훅 바로 뒤가 LDA long(BF)이면 예전 블록 훅 판이다
    (지금 판은 그 자리가 다시 그리기 훅의 PHP(08))."""
    at = rom.u24(LOAD_SITE + 1)
    return grow_layout(at, block_hooks=rom.u8(at + GROW_LOAD_LEN + len(nib_hook(0, wide=True))) == 0xBF)


def tile_counts(rom):
    """세계 0·1·2 가 VRAM 에 올리는 타일 수. 타일 늘리기 훅이 없으면 모두 512."""
    if rom.u8(LOAD_SITE) != 0x22 or not is_grow_hook(rom, rom.u24(LOAD_SITE + 1)):
        return [TILES] * 3
    table = rom_layout(rom)['table']
    return [TILES + rom.u16(table + w * GROW_ENTRY + 6) // 32 for w in range(3)]


def is_grow_hook(rom, at):
    """01:A4A7 의 JSL 이 가리키는 훅이 타일 늘리기 꼴인지(ASL 셋)."""
    return rom.d[lorom(at):lorom(at) + 10] == grow_load_hook(0, 0)[:10]


def planar_to_tiles(planes):
    """평면 0~3 이 4KB 씩인 16KB → SNES 4bpp 타일 512개(01:A4CE 가 VRAM 에 올리는 순서)."""
    c, d, e, f = (planes[i * 0x1000:(i + 1) * 0x1000] for i in range(4))
    out = bytearray()
    for i in range(TILES):
        for r in range(8):
            out += bytes([c[i * 8 + r], d[i * 8 + r]])
        for r in range(8):
            out += bytes([e[i * 8 + r], f[i * 8 + r]])
    return bytes(out)


def tiles_to_planar(tiles):
    planes = [bytearray(0x1000) for _ in range(4)]
    for i in range(TILES):
        t = tiles[i * 32:i * 32 + 32]
        for r in range(8):
            planes[0][i * 8 + r], planes[1][i * 8 + r] = t[r * 2], t[r * 2 + 1]
            planes[2][i * 8 + r], planes[3][i * 8 + r] = t[16 + r * 2], t[17 + r * 2]
    return b''.join(bytes(p) for p in planes)


def encode_rle(data):
    """01:A64F 가 푸는 RLE 를 가장 짧게. 글자 그대로 1~128바이트는 [n-1][바이트…], 같은 값 2~128번은 [80|n-1][값], 끝은 80.
    dq5fieldwrite.encode_rle(3번 이상만 반복)보다 짧아 원래 자리에 다시 들어갈 여지가 크다."""
    n = len(data)
    INF = float('inf')
    cost = [0] + [INF] * n
    choice = [None] * (n + 1)
    for i in range(n):
        if cost[i] == INF:
            continue
        for k in range(1, min(128, n - i) + 1):
            if cost[i] + 1 + k < cost[i + k]:
                cost[i + k], choice[i + k] = cost[i] + 1 + k, (i, 'lit')
        k = 1
        while i + k < n and k < 128 and data[i + k] == data[i]:
            k += 1
            if cost[i] + 2 < cost[i + k]:
                cost[i + k], choice[i + k] = cost[i] + 2, (i, 'run')
    parts, j = [], n
    while j:
        i, kind = choice[j]
        parts.append(bytes([0x80 | (j - i - 1), data[i]]) if kind == 'run' else bytes([j - i - 1]) + data[i:j])
        j = i
    return b''.join(reversed(parts)) + b'\x80'


def colors(rom, a, n):
    return [rom.u16(a + i * 2) for i in range(n)]


def nibbles(rom, a, n=TILES):
    return [rom.u8(a + i // 2) >> (0 if i & 1 else 4) & 15 for i in range(n)]


def original(rom):
    check_sites(rom)
    planes, tiles_end = rle(rom, FIELD_CHR)
    anim, anim_end = rle(rom, ANIM)
    if len(planes) != 0x4000 or len(anim) != ANIM_BYTES:
        raise ValueError('원래 롬의 필드 타일·움직이는 타일 RLE 크기가 다름')
    if [rom.u16(ANIM_TABLE + k * 2) for k in range(FIELD_ANIM_SETS)] != \
            [ANIM_WRAM + k * ANIM_SET for k in range(FIELD_ANIM_SETS)]:
        raise ValueError(f'{cpu(ANIM_TABLE)}: 원래 롬의 움직이는 타일 벌 표가 아님')
    return {'tiles': planar_to_tiles(planes), 'anim': anim,
            'rle': {'tiles': rom.d[lorom(FIELD_CHR):lorom(tiles_end)], 'anim': rom.d[lorom(ANIM):lorom(anim_end)]},
            'tile_palettes': nibbles(rom, TILE_PALETTE),
            'palettes': {k: [colors(rom, a, 30) for a in v] for k, v in PALETTE_SETS.items()},
            'wave': [colors(rom, WAVE + i * 6, 3) for i in range(WAVE_STEPS)],
            'person_palettes': {k: colors(rom, a, 30) for k, a in PERSON.items()},
            'world0_times': [[rom.u16(TIMES + i * 3), rom.u8(TIMES + i * 3 + 2) // 2] for i in range(TIME_COUNT)],
            'world0_night_from': NIGHT_FROM,
            'tile_attributes': list(rom.d[lorom(TILE_ATTR):lorom(TILE_ATTR) + TILES])}


def current(rom):
    """패치한 롬에서 지금 읽히는 것. 검사 도구가 쓴다. worlds 는 세계마다 (타일, 니블),
    anim_sets 는 $1C31 이 0 부터 도는 차례대로 DMA 로 올리는 192바이트."""
    out = {}
    extras, tables = [b''] * 3, None
    if rom.d[lorom(LOAD_SITE)] == 0x22 and is_grow_hook(rom, rom.u24(LOAD_SITE + 1)):
        # 타일 늘리기는 니블 훅 대신 00:BBAC 를 바꿨을 수도 있어(palette_fast) 니블 표를 자리로 읽는다
        table, tables = (rom_layout(rom)[k] for k in ('table', 'tables'))
        entries = [table + w * GROW_ENTRY for w in range(3)]
        srcs = [rom.u8(e + 2) << 16 | rom.u16(e) for e in entries]
        extras = [bytes(rom.d[lorom(rom.u8(e + 3) << 16 | rom.u16(e + 4)):][:rom.u16(e + 6)]) for e in entries]
    elif rom.d[lorom(LOAD_SITE)] == 0x22:
        _, _, table, _, _ = worlds_layout(rom.u24(LOAD_SITE + 1))
        srcs = [rom.u8(table + w * 4 + 2) << 16 | rom.u16(table + w * 4) for w in range(3)]
    else:
        (bank_site, _), (addr_site, _) = SITES['tiles']
        srcs = [rom.u8(bank_site) << 16 | rom.u16(addr_site)] * 3
    counts = [TILES + len(e) // 32 for e in extras]
    nibs = [nibbles(rom, tables + w * 0x200 if tables else nibble_table(rom, w), counts[w]) for w in range(3)]
    out['worlds'] = {k: (planar_to_tiles(rle(rom, srcs[w])[0]) + extras[w], nibs[w]) for w, k in enumerate(WORLDS)}
    out['tiles'], out['tile_palettes'] = out['worlds']['world0']
    (bank_site, _), (addr_site, _) = SITES['anim']
    out['anim'] = rle(rom, rom.u8(bank_site) << 16 | rom.u16(addr_site))[0]
    table_site, _ = ANIM_SITES['table']
    mask_site, _ = ANIM_SITES['mask']
    table = rom.u24(table_site + 1)
    out['anim_sets'] = []
    for k in range(rom.u8(mask_site + 1) + 1):
        o = rom.u16(table + k * 2) - ANIM_WRAM
        out['anim_sets'].append(out['anim'][o:o + ANIM_SET])
    out['palettes'] = {k: [colors(rom, a, 30) for a in v] for k, v in PALETTE_SETS.items()}
    out['wave'] = [colors(rom, WAVE + i * 6, 3) for i in range(WAVE_STEPS)]
    out['person_palettes'] = {k: colors(rom, a, 30) for k, a in PERSON.items()}
    out['world0_times'] = [[rom.u16(TIMES + i * 3), rom.u8(TIMES + i * 3 + 2) // 2] for i in range(TIME_COUNT)]
    out['world0_night_from'] = NIGHT_FROM
    attrs = rom.u24(0x00BCBE) if rom.u8(0x00BCB1) == 0xFF and rom.u8(0x00BCB2) == 0x03 else TILE_ATTR
    out['tile_attributes'] = list(rom.d[lorom(attrs):lorom(attrs) + (MAX_TILES if attrs != TILE_ATTR else TILES)])
    if rom.u8(SEARCH_SITE[0]) == 0x22:
        hook = rom.u24(SEARCH_SITE[0] + 1)
        n, times = rom.u8(hook + 1) // 3 + 1, rom.u24(hook + 7)
        ptrs, bank = rom.u24(rom.u24(PTR_SITE[0] + 1) + 1), rom.u8(PAL_BANK_SITE[0]) << 16
        out['world0_times'] = [[rom.u16(times + i * 3), rom.u8(times + i * 3 + 2) // 2] for i in range(n)]
        count = (rom.u16(ptrs) - (ptrs & 0xFFFF)) // 2           # 벌이 포인터 표 바로 뒤에 붙어 있다
        out['palettes']['world0'] = [colors(rom, bank | rom.u16(ptrs + k * 2), 30) for k in range(count)]
        out['wave'] = [colors(rom, bank | rom.u16(WAVE_SITE[0]) + i * 6, 3) for i in range(WAVE_STEPS)]
        out['world0_night_from'] = rom.u8(NIGHT_SITE[0]) // 2
    for k, (sets, times) in read_world12(rom).items():
        out['palettes'][f'world{k}'], out[f'world{k}_times'] = sets, times
    return out


def dump(rom, out):
    o = original(rom)
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, 'tiles.bin'), 'wb') as f:
        f.write(o['tiles'])
    with open(os.path.join(out, 'anim.bin'), 'wb') as f:
        f.write(o['anim'])
    doc = {'format': FORMAT, 'tiles_file': 'tiles.bin', 'anim_file': 'anim.bin',
           'tile_palettes': o['tile_palettes'], 'palettes': o['palettes'], 'wave': o['wave'],
           'person_palettes': o['person_palettes'], 'world0_times': o['world0_times'],
           'world0_night_from': o['world0_night_from'], 'tile_attributes': o['tile_attributes']}
    with open(os.path.join(out, 'fieldgfx.json'), 'w', encoding='utf-8') as f:
        json.dump(doc, f, separators=(',', ':'))
        f.write('\n')
    return doc


def color_list(v, n, name):
    if not isinstance(v, list) or len(v) != n or any(type(c) is not int or not 0 <= c <= 0x7FFF for c in v):
        raise ValueError(f'{name}: 15비트 색 {n}개')
    return v


def read_file(folder, name, key):
    if not isinstance(name, str):
        raise ValueError(f'{key} 는 파일 이름 문자열')
    with open(os.path.join(folder, name), 'rb') as f:
        return f.read()


def nibble_list(v, name, n=TILES):
    if not isinstance(v, list) or len(v) != n or any(type(c) is not int or not 0 <= c <= 15 for c in v):
        raise ValueError(f'{name} 는 0~15 {n}개(타일 수와 같게)')
    return v


def tile_count(raw, name):
    n, rest = divmod(len(raw), 32)
    if rest or not TILES <= n <= MAX_TILES:
        raise ValueError(f'{name}: 타일 {TILES}~{MAX_TILES}개(32바이트씩)여야 함({len(raw)}바이트)')
    return n


def warn_anim_slots(tiles, orig, name):
    changed = [t for t in ANIM_SLOTS if tiles[t * 32:t * 32 + 32] != orig[t * 32:t * 32 + 32]]
    if changed:
        print(f'경고: {name} 타일 {changed} 은 움직이는 타일 벌이 늘 덮어 보이지 않음(anim.bin 을 고칠 것)',
              file=sys.stderr)


def place_in(at, size, option, placed):
    bank, low = at >> 16, at & 0xFFFF
    if not 0x30 <= bank <= 0x3F or low < 0x8000 or low + size > 0x10000:
        raise ValueError(f'{option} 은 30~3F 의 한 뱅크 안({size}바이트)')
    if any(at < e and lo < at + size for lo, e, _ in placed):
        raise ValueError(f'{option} 자리가 {[n for lo, e, n in placed if at < e and lo < at + size]} 와 겹침')
    placed.append((at, at + size, option))


def patch(rom, doc, folder, tiles_at=None, anim_at=None, name='field-gfx', worlds_at=None, extra_at=None,
          palettes_at=None):
    o = original(rom)
    keys = {'format', 'tiles_file', 'anim_file', 'tile_palettes', 'palettes', 'wave', 'person_palettes', 'worlds',
            'world0_times', 'world0_night_from', 'tile_attributes', 'world1_times', 'world2_times'}
    if not isinstance(doc, dict) or doc.get('format') != FORMAT or set(doc) - keys:
        raise ValueError(f'format={FORMAT} 와 {sorted(keys - {"format"})} 만')
    data = {'tiles': read_file(folder, doc.get('tiles_file'), 'tiles_file'),
            'anim': read_file(folder, doc.get('anim_file'), 'anim_file')}
    count0 = tile_count(data['tiles'], doc['tiles_file'])
    full0, data['tiles'] = data['tiles'], data['tiles'][:TILES * 32]
    sets, rest = divmod(len(data['anim']), ANIM_SET)
    if rest or sets not in ANIM_COUNTS:
        raise ValueError(f'{doc["anim_file"]}: {ANIM_SET}바이트 벌 {ANIM_COUNTS} 개여야 함({len(data["anim"])}바이트)')
    if sets > FIELD_ANIM_SETS and anim_at is None:
        raise ValueError(f'움직이는 타일 벌을 {sets} 개로 늘리려면 --anim-at 이 필요함(벌 주소 표를 그 뒤에 둠)')
    nib_full = nibble_list(doc.get('tile_palettes'), 'tile_palettes', count0)
    nib = nib_full[:TILES]
    pals = doc.get('palettes')
    if not isinstance(pals, dict) or set(pals) != set(PALETTE_SETS) or \
            any(not isinstance(pals[k], list) or not 1 <= len(pals[k]) <= FIELD_PAL_MAX for k in PALETTE_SETS):
        raise ValueError(f'palettes 는 {sorted(PALETTE_SETS)} 마다 벌 목록(1~{FIELD_PAL_MAX}벌)')
    w12 = {k: time_table(doc.get(f'world{k}_times', W12_DEFAULT_TIMES), len(pals[f'world{k}']), f'world{k}_times')
           for k in (1, 2)}
    move12 = {k: len(pals[f'world{k}']) != 1 or w12[k] != W12_DEFAULT_TIMES for k in (1, 2)}
    times = doc.get('world0_times', o['world0_times'])
    night = doc.get('world0_night_from', o['world0_night_from'])
    if not isinstance(times, list) or not 1 <= len(times) <= TIME_MAX or any(
            not isinstance(t, list) or len(t) != 2 or any(type(v) is not int for v in t) for t in times) or \
            times[0][0] != 0 or any(not 0 <= f <= 0xFFFF for f, _ in times) or \
            any(a[0] >= b[0] for a, b in zip(times, times[1:])) or \
            any(not 0 <= k < len(pals['world0']) for _, k in times):
        raise ValueError(f'world0_times 는 [$075E 하한, 벌 번호] 1~{TIME_MAX}개, 첫 하한 0, 하한이 커지는 차례, '
                         '벌 번호는 palettes.world0 안')
    if type(night) is not int or not 0 <= night <= FIELD_PAL_MAX:
        raise ValueError(f'world0_night_from 은 밤 인물 팔레트를 쓰는 첫 벌 번호(0~{FIELD_PAL_MAX})')
    move_pals = len(pals['world0']) != len(PALETTE_SETS['world0']) or times != o['world0_times'] or \
        night != o['world0_night_from']
    if (move_pals or any(move12.values())) and palettes_at is None:
        raise ValueError('세계 0 의 2·3번 줄 벌 수·시간대 표·밤 시작이나 세계 1·2 의 벌 수·시간대 표를 바꾸려면 '
                         '--palettes-at 이 필요함(뱅크 01 이 참)')
    if palettes_at is not None and not move_pals and not any(move12.values()):
        raise ValueError('--palettes-at 은 세계 0 의 벌 수·world0_times·world0_night_from, 세계 1·2 의 벌 수·시간대 표를 '
                         '바꿀 때만')
    wave = doc.get('wave')
    if not isinstance(wave, list) or len(wave) != WAVE_STEPS:
        raise ValueError(f'wave 는 {WAVE_STEPS}단계')
    person = doc.get('person_palettes', o['person_palettes'])
    if not isinstance(person, dict) or set(person) != set(PERSON):
        raise ValueError(f'person_palettes 는 {sorted(PERSON)} 의 30색씩')
    worlds = doc.get('worlds', {})
    if not isinstance(worlds, dict) or set(worlds) - {'world1', 'world2'} or \
            any(not isinstance(v, dict) or set(v) != {'tiles_file', 'tile_palettes'} for v in worlds.values()):
        raise ValueError('worlds 는 world1·world2 마다 {tiles_file, tile_palettes}')
    world_data = {}
    for key, v in sorted(worlds.items()):
        tiles = read_file(folder, v['tiles_file'], f'worlds.{key}.tiles_file')
        n = tile_count(tiles, v['tiles_file'])
        warn_anim_slots(tiles, o['tiles'], key)
        world_data[key] = (tiles, nibble_list(v['tile_palettes'], f'worlds.{key}.tile_palettes', n))
    grow = count0 > TILES or any(len(t) > TILES * 32 for t, _ in world_data.values())
    if grow and (worlds_at is None or extra_at is None):
        raise ValueError(f'타일을 {TILES}개 넘게 쓰려면 --worlds-at(훅·니블 표)과 --extra-at(늘린 타일)이 필요함')
    if extra_at is not None and not grow:
        raise ValueError(f'--extra-at 은 타일이 {TILES}개를 넘을 때만')
    attrs = doc.get('tile_attributes', o['tile_attributes'])
    if grow and 'tile_attributes' not in doc:
        attrs = attrs * 2                         # 늘린 타일 t 는 타일 t - 512 의 속성(원래 AND #$01FF 와 같음)
    n_attr = MAX_TILES if grow else TILES
    if not isinstance(attrs, list) or len(attrs) not in (TILES, n_attr) or \
            any(type(v) is not int or not 0 <= v <= 255 for v in attrs):
        raise ValueError(f'tile_attributes 는 0~255 {TILES}개(타일을 늘리면 {MAX_TILES}개까지)')
    attrs = attrs + attrs[:TILES] * (n_attr // len(attrs) - 1)
    if worlds and worlds_at is None:
        raise ValueError('worlds(세계마다 타일 벌)에는 --worlds-at 이 필요함')
    if worlds_at is not None and not worlds and not grow:
        raise ValueError('--worlds-at 은 worlds 와 함께만')
    warn_anim_slots(data['tiles'], o['tiles'], 'world0')
    writes = []

    def write(addr, raw, note, orig=True):
        w = {'at': cpu(addr), 'hex': raw.hex(' '), 'note': note}
        if orig:
            off = lorom(addr)
            w['orig'] = rom.d[off:off + len(raw)].hex(' ')
        writes.append(w)

    placed = []
    world0_at = FIELD_CHR
    for kind, at in (('tiles', tiles_at), ('anim', anim_at)):
        if data[kind] == o[kind] and at is None:
            continue
        raw = tiles_to_planar(data[kind]) if kind == 'tiles' else data[kind]
        packed = encode_rle(raw)
        if at is None:
            if len(packed) > len(o['rle'][kind]):
                raise ValueError(f'{kind} RLE {len(packed)}바이트가 원래 {len(o["rle"][kind])}바이트보다 김: '
                                 f'--{kind}-at 으로 옮겨야 함')
            write(SOURCES[kind], packed, f'{kind} RLE')
            continue
        table = encode_anim_table(sets) if kind == 'anim' and sets > FIELD_ANIM_SETS else b''
        place_in(at, len(packed) + len(table), f'--{kind}-at', placed)
        write(at, packed, f'{kind} RLE', orig=False)
        if kind == 'tiles':
            world0_at = at
        if kind == 'tiles' and worlds_at is not None:
            continue                                  # 즉값 자리는 세계 훅이 덮는다
        (bank_site, _), (addr_site, _) = SITES[kind]
        write(bank_site, bytes([at >> 16]), f'{kind} 뱅크')
        write(addr_site, (at & 0xFFFF).to_bytes(2, 'little'), f'{kind} 주소')
        if table:
            t = at + len(packed)
            write(t, table, f'움직이는 타일 벌 {sets}개의 WRAM 주소 표', orig=False)
            write(ANIM_SITES['table'][0] + 1, long_addr(t), '벌 주소 표(하위 바이트)')
            write(ANIM_SITES['table_hi'][0] + 1, long_addr(t + 1), '벌 주소 표(상위 바이트)')
    if sets != FIELD_ANIM_SETS:
        # 8벌보다 적으면 원래 표 02:AD89 의 앞 칸이 그대로 맞아 AND 만 바꾼다.
        write(ANIM_SITES['mask'][0] + 1, bytes([sets - 1]), f'벌 돌리기 AND #${sets - 1:02X}')
    nib_bytes = bytes(nib[i] << 4 | nib[i + 1] for i in range(0, TILES, 2))
    old = rom.d[lorom(TILE_PALETTE):lorom(TILE_PALETTE) + len(nib_bytes)]
    for i in range(len(nib_bytes)):
        if nib_bytes[i] != old[i]:
            write(TILE_PALETTE + i, bytes([nib_bytes[i]]), f'타일 팔레트 니블 {i * 2:03X}')
    if not grow:
        for i, v in enumerate(attrs):
            if v != o['tile_attributes'][i]:
                write(TILE_ATTR + i, bytes([v]), f'타일 속성 {i:03X}')
    if grow:
        write_grow(rom, worlds_at, extra_at, world0_at, full0, nib_full, world_data, placed, write, bytes(attrs))
    elif worlds:
        write_worlds(worlds_at, world0_at, data['tiles'], nib, world_data, placed, write)
    for key in PALETTE_SETS:
        for k, new in enumerate(pals[key]):
            new = color_list(new, 30, f'palettes.{key}[{k}]')
            # 늘린 벌의 그 자리는 원래 값이 없고 게임이 덮어 보이지 않으므로 묻지 않는다.
            ref = o['palettes'][key][k] if k < len(o['palettes'][key]) else new
            bad = [i for i in CYCLED if new[i] != ref[i]]
            if bad:
                raise ValueError(f'palettes.{key}[{k}] 의 {bad}번은 2·3번 줄 색 14·15 라 게임이 덮어씀')
            moved = move_pals if key == 'world0' else move12[int(key[-1])]
            if not moved and new != o['palettes'][key][k]:
                write(PALETTE_SETS[key][k], b''.join(c.to_bytes(2, 'little') for c in new), f'필드 팔레트 {key} {k}')
    waves = [color_list(wave[i], 3, f'wave[{i}]') for i in range(WAVE_STEPS)]
    end = palettes_at
    if move_pals:
        end = write_field_palettes(palettes_at, pals['world0'], times, night, waves, placed, write)
    if any(move12.values()):
        write_world12(end, {k: (pals[f'world{k}'], w12[k]) if move12[k] else None for k in (1, 2)}, placed, write)
    for i, new in enumerate(waves):
        if not move_pals and new != o['wave'][i]:
            write(WAVE + i * 6, b''.join(c.to_bytes(2, 'little') for c in new), f'물결 색 {i}')
    for key, a in PERSON.items():
        new = color_list(person[key], 30, f'person_palettes.{key}')
        if new != o['person_palettes'][key]:
            write(a, b''.join(c.to_bytes(2, 'little') for c in new), f'세계 0 {key} 인물 팔레트(11·12번 줄)')
    manifest = {'format': 'dq5patch/1', 'name': name, 'writes': writes}
    if placed:
        end = max(lorom(e - 1) + 1 for _, e, _ in placed)
        manifest['rom_size'] = 4 if end > 0x300000 else 3 if end > 0x200000 else 2
    return manifest


def encode_anim_table(sets):
    return b''.join((ANIM_WRAM + k * ANIM_SET).to_bytes(2, 'little') for k in range(sets))


def write_worlds(at, world0_at, tiles0, nib0, world_data, placed, write):
    """세계 훅 둘·고르기 표·니블 표 넷(넷째는 세계 0 과 같게)·세계 1·2 RLE 를 at 에 차례로 둔다.
    세계 0 과 같은 타일이면 RLE 를 따로 두지 않고 세계 0 의 것을 가리킨다."""
    load, nib, table, tables, rles = worlds_layout(at)
    srcs, nibs, blob = [world0_at], [nib0], bytearray()
    for key in WORLDS[1:]:
        tiles, n = world_data.get(key, (tiles0, nib0))
        nibs.append(n)
        if tiles == tiles0:
            srcs.append(world0_at)
            continue
        srcs.append(rles + len(blob))
        blob += encode_rle(tiles_to_planar(tiles))
    srcs.append(world0_at)
    nibs.append(nib0)
    code = load_hook(table) + nib_hook(tables)
    body = code + b''.join(long_addr(a) + b'\x00' for a in srcs) + \
        b''.join(bytes(n[i] << 4 | n[i + 1] for i in range(0, TILES, 2)) for n in nibs) + bytes(blob)
    place_in(at, len(body), '--worlds-at', placed)
    write(at, body, '세계마다 타일 벌: 불러오기 훅·니블 훅·고르기 표·니블 표 넷·세계 1·2 RLE', orig=False)
    write(LOAD_SITE, b'\x22' + long_addr(load) + b'\x80\x04' + b'\xea' * 4, '타일 불러오기를 세계 훅으로')
    for site in NIB_SITES:
        write(site, b'\x22' + long_addr(nib), '타일 팔레트 니블 읽기를 세계 훅으로')


def write_field_palettes(at, sets, times, night, waves, placed, write):
    """세계 0 의 2·3번 줄 벌을 at 에 [시간대 표][포인터 표][벌 60바이트씩][물결 60바이트][찾기 훅][포인터 훅] 으로 두고
    01:A132·A166 을 훅으로, DMA 뱅크·물결 주소·밤 시작 즉값을 바꾼다. 포인터·물결 주소가 16비트라 한 뱅크 안에 둔다."""
    ptrs = at + len(times) * 3
    first = ptrs + len(sets) * 2
    wave = first + len(sets) * 60
    search = wave + WAVE_STEPS * 6
    data = (b''.join(f.to_bytes(2, 'little') + bytes([k * 2]) for f, k in times)
            + b''.join(((first + k * 60) & 0xFFFF).to_bytes(2, 'little') for k in range(len(sets)))
            + b''.join(c.to_bytes(2, 'little') for row in sets for c in row)
            + b''.join(c.to_bytes(2, 'little') for row in waves for c in row)
            + search_hook(at, len(times)) + ptr_hook(ptrs))
    place_in(at, len(data), '--palettes-at', placed)
    write(at, data, f'세계 0 의 2·3번 줄 벌 {len(sets)}개·시간대 {len(times)}항목·물결 색과 훅 둘', orig=False)
    write(SEARCH_SITE[0], b'\x22' + long_addr(search) + b'\xea' * (len(SEARCH_SITE[1]) - 4), '시간대 찾기를 훅으로')
    write(PTR_SITE[0], b'\x22' + long_addr(search + SEARCH_LEN), '벌 포인터 읽기를 훅으로')
    write(NIGHT_SITE[0], bytes([min(night * 2, 0xFF)]), f'밤 인물 팔레트 시작 벌 {night}')
    write(PAL_BANK_SITE[0], bytes([at >> 16]), '2·3번 줄·물결 DMA 뱅크')
    write(WAVE_SITE[0], (wave & 0xFFFF).to_bytes(2, 'little'), '물결 색 주소')
    return at + len(data)


def time_table(times, sets, name):
    """[$075E 하한, 벌 번호] 목록 검사(세계 0 의 world0_times 와 같은 규칙)."""
    if not isinstance(times, list) or not 1 <= len(times) <= TIME_MAX or any(
            not isinstance(t, list) or len(t) != 2 or any(type(v) is not int for v in t) for t in times) or \
            times[0][0] != 0 or any(not 0 <= f <= 0xFFFF for f, _ in times) or \
            any(a[0] >= b[0] for a, b in zip(times, times[1:])) or any(not 0 <= k < sets for _, k in times):
        raise ValueError(f'{name} 는 [$075E 하한, 벌 번호] 1~{TIME_MAX}개, 첫 하한 0, 하한이 커지는 차례, '
                         '벌 번호는 그 세계 벌 안')
    return times


def write_world12(at, worlds, placed, write):
    """세계 1·2 의 벌을 at 에 세계마다 [시간대 표][포인터 표][벌 60바이트씩] 으로, 그 뒤 02:AD38 훅을 둔다.
    불러오기(01:9F86·9FA0)의 LDX #벌 / LDA #뱅크 를 시간대 표 첫 항목의 벌로 바꾼다($075E 를 0 으로 둔 바로 뒤라)."""
    data, refs, a = b'', {1: None, 2: None}, at
    for k in (1, 2):
        if worlds[k] is None:
            continue
        sets, times = worlds[k]
        ptrs = a + len(times) * 3
        first = ptrs + len(sets) * 2
        block = (b''.join(f.to_bytes(2, 'little') + bytes([i * 2]) for f, i in times)
                 + b''.join(((first + i * 60) & 0xFFFF).to_bytes(2, 'little') for i in range(len(sets)))
                 + b''.join(c.to_bytes(2, 'little') for row in sets for c in row))
        refs[k] = (a, len(times), ptrs)
        (ldx, _), (lda, _) = W12_LOAD[k]
        write(ldx, b'\xa2' + ((first + times[0][1] * 60) & 0xFFFF).to_bytes(2, 'little'), f'세계 {k} 불러올 때의 벌')
        write(lda, b'\xa9' + bytes([at >> 16]), f'세계 {k} 벌 뱅크')
        data += block
        a += len(block)
    hook = refresh_hook(refs, at >> 16)
    place_in(at, len(data) + len(hook), '--palettes-at', placed)
    write(at, data + hook, '세계 1·2 의 2·3번 줄 벌·시간대 표와 02:AD38 훅', orig=False)
    write(REFRESH_SITE[0], b'\x22' + long_addr(a) + b'\xea' * (len(REFRESH_SITE[1]) - 4),
          '몇 프레임마다 2·3번 줄 다시 옮기기를 세계 1·2 도 하는 훅으로')


def place_extras(at, chunks, placed):
    """늘린 타일 덩어리(세계마다, 같은 것은 하나)를 at 부터 차례로 둔다. DMA 가 뱅크를 넘지 못하므로 덩어리가
    뱅크 끝을 넘으면 다음 뱅크 8000 으로 넘긴다. 덩어리 → 긴 주소."""
    out, a = {}, at
    for chunk in chunks:
        if not chunk or chunk in out:
            continue
        if (a & 0xFFFF) + len(chunk) > 0x10000:
            a = ((a >> 16) + 1) << 16 | 0x8000
        if not 0x30 <= a >> 16 <= 0x7D or a & 0xFFFF < 0x8000:
            raise ValueError('--extra-at 은 30~7D 뱅크의 8000~FFFF(늘린 타일이 그 안에 들어야 함)')
        place_in_any(a, len(chunk), '--extra-at', placed)
        out[chunk] = a
        a += len(chunk)
    return out


def place_in_any(at, size, option, placed):
    if any(at < e and lo < at + size for lo, e, _ in placed):
        raise ValueError(f'{option} 자리가 {[n for lo, e, n in placed if at < e and lo < at + size]} 와 겹침')
    placed.append((at, at + size, option))


def write_grow(rom, at, extra_at, world0_at, full0, nib0, world_data, placed, write, attrs):
    """타일 늘리기. 세계마다 (앞 512개 RLE, 512개 뒤 늘린 타일, 니블 표 512바이트)를 고르기 표에 두고,
    훅 셋(불러오기·니블·다시 그리기)과 DMA 루틴을 at 에 놓고, 블록 표 읽기를 제자리에서 바꾼다. 세계 0 과 같은 앞 512개는
    세계 0 RLE 를 쓴다. 세 세계의 니블이 같으면 니블 훅 대신 00:BBAC 를 제자리에서 바꿔(palette_fast) 타일마다 1바이트 표를
    읽는다."""
    lay = grow_layout(at)
    base0 = full0[:TILES * 32]
    worlds = [(full0, nib0)] + [world_data.get(k, (full0, nib0)) for k in WORLDS[1:]] + [(full0, nib0)]
    counts = [len(t) // 32 for t, _ in worlds[:3]]
    # 블록 표를 늘린 롬(dq5fieldtables --blocks-at)이면 번호 511 이상도 센다
    used = max(t for table in (BLOCK_LOWER, BLOCK_UPPER) for m in range(block_count(rom))
               for t in block_tiles(rom, table, m))
    if used >= min(counts):
        raise ValueError(f'블록은 세 세계가 함께 쓰므로 모든 세계에 그 타일을 둘 것(블록이 타일 {used} 을 쓰는데 '
                         f'세계 0·1·2 의 타일 수는 {counts})')
    if len(set(counts)) > 1:
        print(f'경고: 세계 0·1·2 의 타일 수가 {counts} 로 다름. 블록 표는 세 세계가 함께 쓰므로 블록 칸 타일은 '
              f'{min(counts) - 1} 까지만 쓸 것(dq5fieldtables.py 가 넘는 번호를 거부함)', file=sys.stderr)
    extras = place_extras(extra_at, [t[TILES * 32:] for t, _ in worlds], placed)
    blob, srcs = bytearray(), []
    for tiles, _ in worlds:
        base = tiles[:TILES * 32]
        if base == base0:
            srcs.append(world0_at)
            continue
        srcs.append(lay['rles'] + len(blob))
        blob += encode_rle(tiles_to_planar(base))
    table = b''
    for (tiles, _), src in zip(worlds, srcs):
        extra = tiles[TILES * 32:]
        e = extras.get(extra, 0)
        table += long_addr(src) + bytes([e >> 16]) + (e & 0xFFFF).to_bytes(2, 'little') + len(extra).to_bytes(2, 'little')
    nibs = b''
    for _, n in worlds:
        n = list(n) + [0] * (MAX_TILES - len(n))
        nibs += bytes(n[i] << 4 | n[i + 1] for i in range(0, MAX_TILES, 2))
    code = (grow_load_hook(lay['table'], lay['dma']) + nib_hook(lay['tables'], wide=True)
            + redraw_hook(lay['dma']) + dma_sub(lay['table']))
    shared = len({nibs[k:k + MAX_TILES // 2] for k in range(0, len(nibs), MAX_TILES // 2)}) == 1
    body = code + table + nibs + attrs + TILE_BITS + b''.join(palette_bytes(nib0)) + bytes(blob)
    place_in(at, len(body), '--worlds-at', placed)
    write(at, body, '타일 늘리기: 훅 셋·DMA·고르기 표·니블 표 넷·블록 칸 비트 표·팔레트 표 둘·세계 1·2 RLE', orig=False)
    for chunk, a in extras.items():
        write(a, chunk, f'늘린 타일 {len(chunk) // 32}개(VRAM 워드 {EXTRA_VRAM:04X}~)', orig=False)
    write(LOAD_SITE, b'\x22' + long_addr(lay['load']) + b'\x80\x04' + b'\xea' * 4, '타일 불러오기를 늘리기 훅으로')
    if shared:
        write(PALETTE_READ, palette_fast(lay['palettes'], lay['palettes'] + MAX_TILES),
              '타일 팔레트 니블 읽기를 타일마다 1바이트 표로')
    else:
        for site in NIB_SITES:
            write(site, b'\x22' + long_addr(lay['nib']), '타일 팔레트 니블 읽기를 세계마다 512바이트 훅으로')
    write(BLOCK_READ, block_read(lay['tile_bits']), '블록 칸 타일의 9·10번째 비트를 표로')
    write(REDRAW_SITE, b'\x5c' + long_addr(lay['redraw']), '타일맵 다시 그리기(전투 뒤·00:A771) 때 늘린 타일 다시 보내기')
    for site, orig in ATTR_SITES.items():
        if orig[0] == 0x29:
            write(site, b'\x29\xff\x03', '타일 속성 번호를 10비트로')
        else:
            write(site, b'\xbf' + long_addr(lay['attrs']), '타일 속성 표를 1,024바이트로')


def check(rom, folder):
    o = original(rom)
    bad = 0
    for kind, raw in (('tiles', tiles_to_planar(o['tiles'])), ('anim', o['anim'])):
        packed = encode_rle(raw)
        back, _ = rle(Rom(packed + bytes(BANK - len(packed) % BANK)), 0x8000)
        same = back == raw
        bad += not same
        print(f'{kind}: 원래 RLE {len(o["rle"][kind])}바이트, 다시 싸면 {len(packed)}바이트, 다시 풀면 같음 {same}')
    if tiles_to_planar(o['tiles']) != rle(rom, FIELD_CHR)[0]:
        bad += 1
        print('타일 ↔ 평면 바꾸기가 원래와 다름')
    doc = dump(rom, folder)
    manifest = patch(rom, doc, folder)
    print(f'내보낸 그대로 patch: 쓰기 {len(manifest["writes"])}개')
    return bool(bad or manifest['writes'])


def parse_at(v, name):
    if v is None:
        return None
    if not re.fullmatch(r'[0-9A-Fa-f]{2}:[0-9A-Fa-f]{4}', v):
        raise ValueError(f'{name} 은 BB:AAAA')
    return int(v.replace(':', ''), 16)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('rom')
    ap.add_argument('cmd', choices=('dump', 'patch', 'check'))
    ap.add_argument('source', nargs='?')
    ap.add_argument('-o', '--out')
    ap.add_argument('--tiles-at')
    ap.add_argument('--anim-at')
    ap.add_argument('--worlds-at')
    ap.add_argument('--extra-at')
    ap.add_argument('--palettes-at')
    ap.add_argument('--name', default='field-gfx')
    a = ap.parse_args()
    try:
        rom = Rom(open(a.rom, 'rb').read())
        if a.cmd == 'dump':
            if not a.out:
                raise ValueError('dump 에는 -o 폴더')
            dump(rom, a.out)
            print(f'타일 {TILES}개·움직이는 타일 {ANIM_BYTES}바이트 → {a.out}')
            return 0
        if a.cmd == 'check':
            import tempfile
            with tempfile.TemporaryDirectory() as tmp:
                return int(check(rom, tmp))
        if not a.source or not a.out:
            raise ValueError('patch 에는 fieldgfx.json 과 -o')
        with open(a.source, encoding='utf-8') as f:
            doc = json.load(f)
        manifest = patch(rom, doc, os.path.dirname(os.path.abspath(a.source)),
                         parse_at(a.tiles_at, '--tiles-at'), parse_at(a.anim_at, '--anim-at'), a.name,
                         parse_at(a.worlds_at, '--worlds-at'), parse_at(a.extra_at, '--extra-at'),
                         parse_at(a.palettes_at, '--palettes-at'))
        os.makedirs(os.path.dirname(a.out) or '.', exist_ok=True)
        with open(a.out, 'w', encoding='utf-8') as f:
            json.dump(manifest, f, ensure_ascii=False, indent=1)
            f.write('\n')
        print(f'쓰기 {len(manifest["writes"])}개 → {a.out}')
        return 0
    except (ValueError, OSError, KeyError, TypeError) as e:
        print(f'오류: {e}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
