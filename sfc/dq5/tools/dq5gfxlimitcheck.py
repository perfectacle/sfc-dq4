"""필드 타일 1,024개 늘리기·세계 0 의 2·3번 줄 벌 늘리기·실내 BG 팔레트 세트 늘리기를 MesenCE 에서 확인한다.

시험 롬(원본에서 만듦)
  tiles   타일 512~1023 을 타일 0~511 의 비트 반전으로, 니블을 0~511 니블의 bit0 반전으로 두고(dq5fieldgfxwrite
          --worlds-at 34:8000 --extra-at 60:8000), 그 롬으로 만든 dq5fieldtables 패치로 블록 511개 두 층의 칸 타일
          번호에 512 를 더함(위층 타일 0 은 그대로). 블록에서 그린 필드 칸이 모두 늘린 타일을 써야 맞다
  nibs    tiles 와 같되 세계 1·2 의 늘린 타일 니블만 bit1·bit2 를 더 뒤집음(worlds 로 니블만 다르게 줌. 00:BBAC 가
          $1949 로 세계마다 타일맵 워드 표를 고름)
  wall-XX tiles 와 같되 늘린 타일을 35:8000 에 두고, 타일 512~1023 의 속성(00:BCA8 이 읽는 표)을 모두 XX(80·82·95·45·00)로.
          원래 속성 그대로인 tiles 롬과 45·00 에서는
          걷고, 80·82·95 에서는 못 걸어야 늘린 속성 표를 읽는 것이다. 걷기 앞 VRAM 으로 35:8000·60:8000 자리도 견준다
  fieldpal  세계 0 의 2·3번 줄 벌을 12개로(8~11 은 새 색), 시간대 표를 12항목으로(새 벌을 0·1·0100·0180 에), 밤 인물
          팔레트 시작을 벌 10 으로(dq5fieldgfxwrite --palettes-at 36:8000)
  indoor  실내 BG 팔레트 세트를 70개로(새 세트 69 의 낮 목록은 새 목록, 밤 목록은 세트 0 의 것), 01/01 을 세트 69 로
          (dq5mapgfxwrite --sets-at 37:8000, 그 롬으로 만든 dq5palsetwrite 패치)
장면
  nibs: 세계 0 (341,56)·세계 1·2 (50,28) 에 서서 늘린 타일로 그린 칸의 팔레트가 그 세계에 준 니블인지.
        세계를 오가는 장면(ルーラ 로 세계 0 → 1·2, 1 → 0, 1C/00·30/00 에서 걸어 나가 세계 2)도 nibs·tiles·원본 게임을
        함께 돌려, 내린 뒤 같은 것을 보고 타일 번호·CGRAM·$1949 쓰기·00:BBAC 호출 기록(lua/dq5worldlog.lua)을 tiles 롬과 견준다.
  tiles: 세계 0 (341,56) 에 서기, 걷고 명령 창을 여닫은 뒤, 이벤트 전투(スライム 하나)를 이기고 돌아온 뒤, 세계 1·2 (50,28).
         01:A4A7 뒤 00:A788 앞에 VRAM 워드 4000~5FFF 를 지우고 다시 오는지(lua/dq5vramwipe.lua, 01:B4D5 를 원본으로
         되돌린 대조 롬은 비어 있어야 함), キメラのつばさ·ルーラ 앞뒤(그 사이 01:A4A7 실행 기록, 첫 칸 00 대조는 실패해야 함), 마법 융단을 펴고 탄 채 걷기.
         VRAM 워드 2000~3FFF·4000~5FFF 의 타일과 BG1·2 타일맵의 채운 칸을 디코더(dq5field)와 견준다
        세계를 오가는 장면은 ルーラ 1 → 2, キメラのつばさ(세계 2 → 0 → 2), 天空城 이륙(06/08, 02:9779), 52/50 석상
        이벤트(30/00 에서 걸어 나가 세계 2), 27/00 에서 $1949 = FF 를 쓴 뒤 ルーラ·FF 를 가진 채 1C/00 에서 걸어 나가기도 있다.
  ending: 엔딩 필드 비행(02:B9D8)에서 원본·tiles 롬의 $1949·BG3 글자 기준·VRAM 워드 4000~5FFF(스태프 롤이 지움)
  clock: 원본·nibs 롬. 세계 0 밤에 ルーラ 로 세계 1·2 에 내려 걷고 ラナルータ, 세계 0 으로 돌아와 걷고 ラナルータ.
         $075E 쓰기(lua/dq5worldlog.lua 의 WATCHW)와 덤프마다 2·3번 줄
  fieldpal: (341,56) 에서 $075E 를 여섯 값으로 두고 2·3번 줄 색 1~13 과 11·12번 줄(낮·밤 인물 팔레트)
  indoor: 01/01 과 세트를 그대로 둔 맵 셋(원본 게임과도 견줌)에서 BG 1~7번 줄. 01/01 은 밤에도(새 세트의 밤 목록),
          06/00 은 플래그 팔레트 세트(2A:8690, 7E:21D4 bit2 → 세트 36 을 10:DDCF 로)와 그 항목을 새 세트 69 로 바꾼 낮·밤

  MESENCE=… python sfc/dq5/tools/dq5gfxlimitcheck.py rom/dq5.sfc --state work/state/ship.mss --out work/gfxlimitcheck
"""
import argparse
import concurrent.futures
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import dq5fieldgfxcheck as fgc  # noqa: E402
import dq5fieldgfxwrite as fgw  # noqa: E402
import dq5gfxwritecheck as gwc  # noqa: E402
import dq5map  # noqa: E402
from dq5field import tile_word  # noqa: E402
from dq5map import Rom, lorom, map_pointer  # noqa: E402

require, command = fgc.require, fgc.command
SETTLE_FRAME = 900
# 이벤트 전투는 dq5fieldgrowcheck 와 같다. 1,000프레임은 전투 중, 1,990프레임은 돌아와 선 뒤.
BATTLE = {'FIELD': '341,56', 'BATTLE': '00:1', 'SETTLE': '300', 'MAXF': '2100', 'DUMPF': '1000,1990',
          'TEST': 'wait:100,' + ','.join(['a:4,wait:30'] * 60) + ',wait:600'}
IN_BATTLE, AFTER_BATTLE = 1000, 1990
# 다시 그리기 시험: 01/00 에서 걸어 나와 01:A4A7(439프레임)이 늘린 타일을 보낸 뒤, 화면 다시 그리기 00:A771 의
# JSL $01B4D5(00:A788, 462프레임) 앞인 450프레임에 VRAM 워드 4000~5FFF 를 지운다. 01:B4D5 훅이 다시 보내면 470프레임에 돌아와 있다.
# 대조로 01:B4D5 만 원본 4바이트로 되돌린 롬(redraw-control)도 돌려, 470프레임에도 비어 있어야 한다.
WIPE = {'FIELD': '341,56', 'SETTLE': '500', 'MAXF': '1000', 'DUMPF': '455,470', 'WIPEF': '450', 'WIPE': '8000-BFFF',
        'EXECLOG': '01A4A7,00A788'}
WIPED, REDRAWN = 455, 470
# 속성 시험: 서서 네 방향으로 32프레임씩 걷는다. dq5warp.lua 가 좌표가 바뀌었는지 warp.txt 에 moved= 로 적는다.
# 필드를 다시 불러오는 장면(01:A4A7 → 00:A788): キメラのつばさ(물건 A4)를 どうぐ → つかう, ルーラ(이동 주문, MP 99)를
# じゅもん 일곱째로. 둘 다 960·1047프레임쯤 다시 불러온다. 앞뒤 프레임의 늘린 타일 자리를 견주고, 그 사이에 01:A4A7 이
# 돌았는지 실행 기록(lua/dq5vramwipe.lua 의 EXECLOG)으로 본다. 물건·주문이 실패해 아무 일도 없으면 타일만으로는 가를 수 없다.
# 마법 융단(물건 CC)은 같은 입력으로 펴고 융단에 탄 채 걷는다. 필드를 다시 불러오지 않으므로 마지막 덤프의 $1954 = 80(융단)과
# 걸었는지를 본다. 대조(empty)는 첫 칸을 00 으로 두고 キメラのつばさ 와 같은 입력을 넣는다. 쓸 물건이 없어 다시 불러오지 않으므로
# 「다시 불러옴」으로 검사하면 실패해야 한다.
ITEM_MENU = 'a:8,wait:60,right:8,wait:40,down:8,wait:40,a:8,wait:80,a:8,wait:80,a:8,'
# 이름 → (환경, 덤프 프레임, 기대: reload 다시 불러옴 · carpet 융단에 탐 · empty 아무 일 없음)
ITEM_SCENES = {
    'chimera': ({'SET': '2056=A4', 'TEST': ITEM_MENU + 'wait:600'}, (900, 1000, 1300), 'reload'),
    'rula': ({'SET': '2063=FF;2044=63;2050=63',
              'TEST': 'a:8,wait:60,right:8,wait:40,a:8,wait:80,' + 'down:6,wait:12,' * 6 + 'a:8,wait:80,a:8,wait:600'},
             (1000, 1100, 1300), 'reload'),
    'carpet': ({'SET': '2056=CC', 'TEST': ITEM_MENU + 'wait:300,left:32,up:32,right:32,wait:300'}, (700, 1100, 1500),
               'carpet'),
    'empty': ({'SET': '2056=00', 'TEST': ITEM_MENU + 'wait:600'}, (900, 1000, 1300), 'empty'),
}
CARPET = 0x80
# 세계를 오가는 장면(nibs 롬, 같은 니블인 tiles 롬, 원본 게임에서 함께 돌림). ルーラ 목적지 목록은 7E:2030~2032 의 비트이고
# FIELD 로 01/00 을 지나면 bit0(ラインハット)이 켜지므로, 한 비트만 더 켜 두면 목록 둘째(down 한 번)가 그 목적지다.
# 1C/00·30/00 은 아래로 걸어 나가 세계 2 필드에 선다. 이름 → (환경, [(덤프 프레임, 그때 세계)], $1949 를 써야 하는 PC).
# 쓰는 PC 는 lua/dq5worldlog.lua 가 잡는 다음 명령 자리다(2A:FEEC → 2AFEEF, 11:819A → 11819D, 02:9779 → 02977C,
# 02:B9D8 → 02B9DB, 03:C684 → 03C687).
RULA = 'a:8,wait:60,right:8,wait:40,a:8,wait:80,' + 'down:6,wait:12,' * 6 + 'a:8,wait:80,'
RULA_SET = '2063=FF;2044=63;2050=63;2030=00;2032=00;2031='
DIALOG = 'a:4,wait:60,' * 20
WORLD_SCENES = {
    'rula-world1': ({'FIELD': '310,60', 'SET': RULA_SET + '20', 'MAXF': '1900',
                     'TEST': RULA + 'down:6,wait:20,a:8,wait:700'}, [(1600, 1)], {'2AFEEF', '11819D'}),
    'rula-world2': ({'FIELD': '310,60', 'SET': RULA_SET + '80', 'MAXF': '1900',
                     'TEST': RULA + 'down:6,wait:20,a:8,wait:700'}, [(1600, 2)], {'2AFEEF', '11819D'}),
    'walk-1C00': ({'TO': '1C/00,33,74,1', 'MAXF': '1500', 'TEST': 'down:60,wait:900'}, [(1400, 2)], {'2AFEEF'}),
    'walk-3000': ({'TO': '30/00,13,25,1', 'MAXF': '1500', 'TEST': 'down:60,wait:900'}, [(1400, 2)], {'2AFEEF'}),
    'rula-back': ({'FIELD': '310,60', 'SET': RULA_SET + '20', 'MAXF': '3000',
                   'TEST': RULA + 'down:6,wait:20,a:8,wait:500,' + RULA + 'a:8,wait:700'}, [(1600, 1), (2500, 0)],
                  {'2AFEEF', '11819D'}),
    # ルーラ 로 세계 1(22) 에 내린 뒤 다시 ルーラ 로 세계 2(1C, 목록 셋째).
    'rula-1to2': ({'FIELD': '310,60', 'SET': RULA_SET + 'A0', 'MAXF': '2700',
                   'TEST': RULA + 'down:6,wait:20,a:8,wait:500,' + RULA + 'down:6,wait:20,down:6,wait:20,a:8,wait:700'},
                  [(1600, 1), (2500, 2)], {'2AFEEF', '11819D'}),
    # 1C/00 에서 걸어 나가 세계 2, ルーラ 로 ラインハット(세계 0), キメラのつばさ 로 마지막에 들른 1C(세계 2). 7E:2194 bit7 은
    # ラインハット 필드에 내릴 때 첫 필드 이벤트 전투가 붙지 않게 켠다.
    'chimera-cross': ({'TO': '1C/00,33,74,1', 'MAXF': '3600',
                       'SET': '2056=A4;2063=FF;2044=63;2050=63;2030=01;2031=00;2032=00;2194|80',
                       'TEST': 'down:60,wait:600,' + RULA + 'a:8,wait:700,' + ITEM_MENU + 'wait:900'},
                      [(1000, 2), (2200, 0), (3300, 2)], {'2AFEEF', '11819D'}),
    # 06/08(天空城 조종 방) (24,9) 에 서면 맵별 루틴 02:9754 가 7E:21D4 bit2(성이 뭍에 앉음)를 보고 02:9779 에서 $1949 = 0,
    # $1954 = 81 로 두고 필드로 날아오른다. 7E:21DB·21DD 는 성의 필드 자리. (341,56) 은 첫 필드 이벤트 자리라 7E:2194 bit7 로 끈다.
    'castle-0608': ({'TO': '06/08,24,9,1', 'SET': '21D4|04;21DB=55;21DC=01;21DD=38;21DE=00;2194|80', 'MAXF': '1400',
                     'TEST': 'wait:800'}, [(700, 0)], {'02977C'}),
    # 52/50 석상 이벤트(세 반지)로 30/00 (13,12) 에 간 뒤 대화를 넘기고 아래로 걸어 나가 세계 2 필드. 52/50 바닥은 층 2.
    'statue-5250': ({'TO': '52/50,24,17,2', 'SET': '2190|40;21D8=01;21D9=01;21DA=01', 'MAXF': '4600',
                     'TEST': 'wait:20,up:80,wait:200,' + DIALOG + 'down:200,wait:100,' + 'a:4,wait:60,' * 10
                             + 'b:4,wait:30,b:4,wait:30,down:400,wait:600'}, [(3900, 2)], {'2AFEEF'}),
    # 27/00(그룹 27, 세계 FF): X 로 지도를 여는 00:8134 의 $1954 bit7 갈래(BMI)를 BRA 로 바꿔 실내에서 03:C688 을 부르면
    # 03:C684 가 $1949 = FF 를 쓴다. 그 뒤 ルーラ 로 세계 1 에 내린다.
    'ship27-ff': ({'TO': '27/00,12,7,1', 'ROMPATCH': '000137=80', 'SET': RULA_SET + '20', 'MAXF': '2400',
                   'TEST': 'wait:20,x:12,wait:300,b:4,wait:60,b:4,wait:60,b:4,wait:60,' + RULA
                           + 'down:6,wait:20,a:8,wait:700'}, [(2000, 1)], {'03C687', '11819D'}),
    # $1949 = FF 를 가진 채 실내(1C/00)에서 걸어 나가기.
    'walk-1C00-ff': ({'TO': '1C/00,33,74,1', 'SET': '1949=FF', 'MAXF': '1500', 'TEST': 'down:60,wait:900'},
                     [(1400, 2)], {'2AFEEF'}),
}
# 엔딩 준비 02:F974 를 02/06 인물 스크립트 첫머리(10:9B89)에 걸어 7E:21EA bit7 을 켜면, 맵을 나갈 때 00:CBFA 가
# 02:B9C3 으로 필드 (399,387)·$1949 = 0 에 둔다(02:B9D8 의 STZ). 01:A4A7 이 필드를 불러 늘린 타일도 보내지만, 그 뒤
# 스태프 롤 준비 02:FA86 이 BG3 글자 자리 VRAM 워드 4000~5FFF 를 DMA 로 지우고 BG3 글자 기준을 4000 에 둔다. 원본 롬과
# tiles 롬으로 돌려 그 충돌을 잰다.
ENDING = {'TO': '02/06,39,9,1', 'SET': '2190|80', 'ROMPATCH': '081B89=3774F902', 'MAXF': '1100', 'TEST': 'wait:900',
          'READPC': '00BBAC,01A4A7', 'DUMPF': '1000'}
ENDING_FRAME, ENDING_WRITE = 1000, '02B9DB'
# $1949 에 3 이상을 써도 되는 장면과 그 PC. 00:BBAC 가 읽는 값은 이 장면에서도 0~2 여야 한다.
WORLD_FF = {'ship27-ff': '03C687'}
WORLD_ROMS = ('orig', 'tiles', 'nibs')
# nibs 롬: 세계마다 늘린 타일(512~1023) 니블을 tiles 롬의 것에서 더 뒤집는 비트. 아래층은 니블 3비트만 쓰므로
# bit0~2 를 고른다.
NIB_FLIPS = {'world1': 2, 'world2': 4}
# 세계 1·2 의 시계(원본 게임과 nibs 롬). 세계 0 에서 밤($075E = 0120, 시간 멈춤 7E:2190 bit1 끔)에 ルーラ 로 그 세계에 내려
# 걷고 ラナルータ 를 외운 뒤, ルーラ 로 ラインハット(세계 0)에 돌아와 걷고 다시 ラナルータ 를 외운다. ラナルータ 는 주인공 필드
# 주문 목록(23:BE28) 다섯째 칸(파일 오프셋 11BE2C)을 37 로 바꿔 외우게 한다. 걷는 동안 무작위 전투가 붙지 않게 조우 판정
# 23:E7C2(00:82B4 가 부름, carry 면 전투)를 CLC / RTL 로 둔다. 시계 00:82C6 은 그 뒤라 그대로 돈다.
LANA = 'a:8,wait:60,right:8,wait:40,a:8,wait:80,' + 'down:6,wait:12,' * 4 + 'a:8,wait:400,' + 'b:4,wait:30,' * 3 + 'wait:70,'
CLOCK_SCENES = {
    f'clock-world{w}': ({'FIELD': '310,60', 'SET': RULA_SET + f'{0x20 if w == 1 else 0x80:02X};075E=20;075F=01;2190&FD',
                         'ROMPATCH': '11BE2C=37;11E7C2=186B', 'MAXF': '4900', 'WATCHW': '075E,075F',
                         'READPC': '00BBAC,11826F,11829B', 'DUMPF': ','.join(str(n) for n in range(500, 4801, 100)),
                         'TEST': RULA + 'down:6,wait:20,a:8,wait:500,left:64,down:64,right:64,up:64,wait:60,' + LANA
                                 + RULA + 'a:8,wait:500,left:64,right:64,wait:60,' + LANA + 'wait:200'}, w)
    for w in (1, 2)}
CLOCK_ROMS = ('orig', 'nibs')
# 세계를 불러올 때 $075E 를 0 으로 두는 곳(01:9F86·9FA0 의 STX 다음 명령), 시계(00:82C6 갈래의 STA 다음), ラナルータ 가 쓰는 곳.
CLOCK_RESET = {1: '019F8C', 2: '019FA6'}
CLOCK_TICK, RANARUTA_WRITE, RANARUTA, RANARUTA_SET = '0082DF', '1182A7', '11826F', '11829B'
# 속성 값 → 걸을 수 있는지. 늘린 타일 자리(VRAM)도 걷기 앞(700프레임)에 견준다.
WALLS = {0x80: False, 0x82: False, 0x95: False, 0x45: True, 0x00: True}
MOVE = {'FIELD': '341,56', 'SETTLE': '300', 'MAXF': '1300', 'DUMPF': '700',
        'TEST': 'wait:60,left:32,up:32,right:32,down:32,wait:60'}
MOVE_FRAME = 700
# 명령 창을 열어 고르고 닫은 뒤 몇 걸음 걷는다(01:A4A7·전투 뒤 말고 늘린 타일 자리를 덮는 곳이 없는지).
# 오래 걸으면 무작위 전투가 붙으므로 짧게 걷고, 덤프 때 $1001 = 0(전투 전)을 본다.
WALK = {'FIELD': '341,56', 'SETTLE': '300', 'MAXF': '1600', 'DUMPF': '1450',
        'TEST': 'wait:100,a:4,wait:60,down:4,wait:30,a:4,wait:60,b:4,wait:30,b:4,wait:30,b:4,wait:60,'
                'left:32,up:32,a:4,wait:60,b:4,wait:300'}
WALK_FRAME = 1450
# 늘린 벌 8~11 과 시간대 표. 하한 0·1 은 새 벌 8·9, 0100·0180 은 새 벌 10·11(밤 시작), 나머지는 원래와 같다.
NEW_SETS = 4
TIMES = [[0, 8], [1, 9], [2, 2], [0xEE, 3], [0xEF, 4], [0xF0, 5], [0xF1, 6], [0xF2, 7], [0x100, 10], [0x180, 11],
         [0x1FD, 6], [0x1FE, 5]]
NIGHT_FROM = 10
# $075E 값 → 고르는 벌. 0050 은 원래 벌 2, 00F1 은 원래 밤이지만 이 롬에서는 낮(벌 6 < 10).
TIME_CASES = {0x0000: 8, 0x0001: 9, 0x0050: 2, 0x00F1: 6, 0x0120: 10, 0x01A0: 11}
NEW_MAP = (0x01, 0x01)      # 세트 표에 원래 맵 항목이 있어 표 크기가 그대로다
# 세트를 바꾸지 않은 맵: 옮긴 표에서도 원래 세트·목록을 읽는지(세트 46·6·5).
SAME_MAPS = [(0x01, 0x00), (0x02, 0x00), (0x21, 0x02)]
NEW_SET = 69
INDOOR_FRAME = 700
# 밤: $075E = 0120 으로 맵에 들어가면 10:DE47 의 JSL $218000 이 밤을 돌려줘 세트의 밤 목록을 읽는다.
NIGHT_SET = '075E=20;075F=01'
# 플래그 팔레트 세트 표 2A:8690 의 06/00 항목 [06][00][44][04][24]: 7E:21D4 bit2(天空城 이 뭍에 앉음)면 세트 36 을
# 10:DDCF 로 부르고 맵 → 세트 표(06/00 은 35)는 건너뛴다. ROMPATCH 로 이 항목의 세트를 새 세트로 바꿔 본다.
FLAG_MAP, FLAG_ENTRY, FLAG_SET = (0x06, 0x00), 0x2A86A4, 0x24
FLAG_ON = '21D4|04'


def make_roms(original, out):
    rom = Rom(original.read_bytes())
    src = out / 'tiles-src'
    doc = fgw.dump(rom, src)
    tiles = (src / 'tiles.bin').read_bytes()
    (src / 'tiles.bin').write_bytes(tiles + bytes(b ^ 0xFF for b in tiles))
    doc['tile_palettes'] = doc['tile_palettes'] + [n ^ 1 for n in doc['tile_palettes']]
    (src / 'fieldgfx.json').write_text(json.dumps(doc), encoding='utf-8')
    command('dq5fieldgfxwrite.py', original, 'patch', src / 'fieldgfx.json', '-o', out / 'tiles-gfx.json',
            '--worlds-at', '34:8000', '--extra-at', '60:8000')
    nib = doc['tile_palettes']
    doc['worlds'] = {k: {'tiles_file': 'tiles.bin', 'tile_palettes': nib[:fgw.TILES] + [n ^ x for n in nib[fgw.TILES:]]}
                     for k, x in NIB_FLIPS.items()}
    (src / 'nibs.json').write_text(json.dumps(doc), encoding='utf-8')
    command('dq5fieldgfxwrite.py', original, 'patch', src / 'nibs.json', '-o', out / 'nibs-gfx.json',
            '--worlds-at', '34:8000', '--extra-at', '60:8000')
    del doc['worlds']
    attrs = doc['tile_attributes']
    for v in WALLS:
        doc['tile_attributes'] = attrs + [v] * fgw.TILES
        (src / f'wall-{v:02x}.json').write_text(json.dumps(doc), encoding='utf-8')
        command('dq5fieldgfxwrite.py', original, 'patch', src / f'wall-{v:02x}.json',
                '-o', out / f'wall-{v:02x}-gfx.json', '--worlds-at', '34:8000', '--extra-at', '35:8000')
    command('dq5build.py', original, 'build', out / 'tiles-gfx.json', '--size', '4', '-o', out / 'tiles-step.sfc')
    command('dq5fieldtables.py', out / 'tiles-step.sfc', 'dump', '-o', out / 'tables.json')
    t = json.loads((out / 'tables.json').read_text(encoding='utf-8'))
    # 위층 타일 0 은 00:BCA8 이 「위층 없음」으로 보고 아래층 속성을 읽으므로 0 으로 둔다.
    blocks = [{'index': b['index'], 'lower': [v + 512 for v in b['lower']],
               'upper': [v and v + 512 for v in b['upper']]} for b in t['blocks']]
    (out / 'tables.json').write_text(json.dumps({'format': t['format'], 'blocks': blocks}), encoding='utf-8')
    command('dq5fieldtables.py', out / 'tiles-step.sfc', 'patch', out / 'tables.json', '-o', out / 'tiles-blocks.json')

    psrc = out / 'fieldpal-src'
    doc = fgw.dump(rom, psrc)
    base = doc['palettes']['world0'][0]
    for k in range(NEW_SETS):
        doc['palettes']['world0'].append([0x0421 * (k + 1) + i if i not in fgw.CYCLED else base[i] for i in range(30)])
    doc['world0_times'], doc['world0_night_from'] = TIMES, NIGHT_FROM
    (psrc / 'fieldgfx.json').write_text(json.dumps(doc), encoding='utf-8')
    command('dq5fieldgfxwrite.py', original, 'patch', psrc / 'fieldgfx.json', '-o', out / 'fieldpal.json',
            '--palettes-at', '36:8000')

    isrc = out / 'indoor-src'
    command('dq5mapgfxwrite.py', original, 'dump', '-o', isrc)
    m = json.loads((isrc / 'mapgfx.json').read_text(encoding='utf-8'))
    m['palette_lists']['0000'] = [52, 52, 60, 61, 62, 63, 64]
    m['palette_sets'].append(['0000', m['palette_sets'][0][1]])
    (isrc / 'mapgfx.json').write_text(json.dumps(m), encoding='utf-8')
    command('dq5mapgfxwrite.py', original, 'patch', isrc / 'mapgfx.json', '-o', out / 'indoor-sets.json',
            '--sets-at', '37:8000')
    command('dq5build.py', original, 'build', out / 'indoor-sets.json', '--size', '4', '-o', out / 'indoor-step.sfc')
    command('dq5palsetwrite.py', out / 'indoor-step.sfc', 'dump', '-o', out / 'palset.json')
    p = json.loads((out / 'palset.json').read_text(encoding='utf-8'))
    p['groups'] = [g for g in p['groups'] if g['group'] == f'{NEW_MAP[0]:02X}']
    g = p['groups'][0]
    for x in g['maps']:
        if x['map'] == f'{NEW_MAP[1]:02X}':
            x['set'] = NEW_SET
    (out / 'palset.json').write_text(json.dumps(p), encoding='utf-8')
    command('dq5palsetwrite.py', out / 'indoor-step.sfc', 'patch', out / 'palset.json', '-o', out / 'indoor-map.json')
    for name, lists in (('tiles', ['tiles-gfx.json', 'tiles-blocks.json']),
                        ('nibs', ['nibs-gfx.json', 'tiles-blocks.json']),
                        *((f'wall-{v:02x}', [f'wall-{v:02x}-gfx.json', 'tiles-blocks.json']) for v in WALLS),
                        ('fieldpal', ['fieldpal.json']),
                        ('indoor', ['indoor-sets.json', 'indoor-map.json'])):
        command('dq5build.py', original, 'build', *(out / x for x in lists), '--size', '4',
                '-o', out / f'{name}.sfc', '--ips', out / f'{name}.ips')


def frame(dump, n, ext):
    return (dump / f'f{n:05d}.{ext}').read_bytes()


def vram_tiles(vram, n):
    return [vram[0x4000 + t * 32:0x4000 + t * 32 + 32] for t in range(n)]


def field_cells(rom, vram, world):
    """BG1·2 타일맵 칸마다 (층, 워드, 디코더 워드와 같은지). 0·2000 은 원본에서도 채우지 않는 칸이라 뺀다."""
    out = {}
    for base, upper in ((0, False), (0x1000, True)):
        for i in range(0x800):
            v = vram[base + i * 2] | vram[base + i * 2 + 1] << 8
            if v not in (0, 0x2000):
                out[base + i * 2] = (v, v & 0x1FFF == tile_word(rom, v & 0x3FF, upper, world) & 0x1FFF)
    return out


def check_tiles(name, rom_path, dump, n, orig, world=0, grown=True):
    """VRAM 타일이 그 세계 벌과 같고(움직이는 타일 제외), BG1·2 타일맵의 채운 칸이 모두 디코더 워드와 같은지.
    orig 는 같은 장면을 원본 롬으로 돌린 덤프(없으면 None). 시험 롬은 블록 칸 타일에 512 를 더했으므로(위층 0 빼고)
    두 덤프에서 값이 같은 칸은 늘린 타일로 그린 칸이 아니다(위층 0, 전투 뒤 남은 칸 등). 그 칸을 빼고, 남은 칸은 모두 같은 자리
    원본 게임 칸의 타일 + 512 여야 한다(grown). 워드만 보면 타일 번호가 다른 칸으로 바뀌어도 가를 수 없다."""
    rom = Rom(rom_path.read_bytes())
    tiles, _ = fgw.current(rom)['worlds'][f'world{world}']
    w, vram = frame(dump, n, 'wram'), frame(dump, n, 'vram')
    require(w[0x1949] == world and not w[0xBE] & 0x80, f'{name}: 세계 {world} 필드에 서지 않음')
    require(w[0x1001] == 0 or n == AFTER_BATTLE, f'{name}: {n}프레임에 전투가 붙음($1001 = {w[0x1001]:02X})')
    count = len(tiles) // 32
    got = vram_tiles(vram, count)
    bad = [t for t in range(count) if t not in fgc.ANIM_TILES and got[t] != tiles[t * 32:t * 32 + 32]]
    require(not bad, f'{name}: VRAM 타일 {len(bad)}개가 기대와 다름 {bad[:8]}')
    ov = frame(orig, n, 'vram') if orig else None
    cells = field_cells(rom, vram, world)
    stale = {a for a, (v, _) in cells.items() if ov and v == (ov[a] | ov[a + 1] << 8)}
    cells = {a: c for a, c in cells.items() if a not in stale}
    wrong = [a for a, (v, ok) in cells.items()
             if not ok or (ov and grown and v & 0x3FF != (ov[a] | ov[a + 1] << 8 & 0x300) + fgw.TILES)]
    high = sum((v & 0x3FF) >= fgw.TILES for v, _ in cells.values())
    require(cells and not wrong, f'{name}: 채운 칸 {len(cells)}개 가운데 {len(wrong)}개가 디코더 워드와 다름')
    require(high == (len(cells) if grown else 0), f'{name}: 타일 512 이상을 쓰는 칸 {high}/{len(cells)}')
    return {'case': name, 'frame': n, 'world': world, 'vram_tiles': count - len(fgc.ANIM_TILES),
            'tilemap_cells': len(cells), 'cells_using_512_up': high, 'same_as_original_game': len(stale)}


def nibble_cells(dump, nib, n=SETTLE_FRAME):
    """BG1·2 타일맵에서 늘린 타일(512 이상)로 그린 칸 수와, 그 가운데 팔레트 비트가 nib(위층 4비트·아래층 3비트)로
    셈한 값과 다른 칸 수."""
    vram = frame(dump, n, 'vram')
    cells, wrong = 0, 0
    for base, mask in ((0, 7), (0x1000, 15)):
        for i in range(0x800):
            v = vram[base + i * 2] | vram[base + i * 2 + 1] << 8
            t = v & 0x3FF
            if t >= fgw.TILES:
                cells += 1
                wrong += v >> 10 & 7 != ((nib[t] & mask) + 2) & 7
    return cells, wrong


def check_nibbles(name, dump, world, nib, n=SETTLE_FRAME):
    """늘린 타일 칸마다 팔레트 비트가 nib(그 세계에 준 니블)로 셈한 값인지. 디코더를 거치지 않고 입력과 바로 견준다."""
    w = frame(dump, n, 'wram')
    require(w[0x1949] == world and not w[0xBE] & 0x80, f'{name}: 세계 {world} 필드에 서지 않음')
    cells, wrong = nibble_cells(dump, nib, n)
    require(cells and not wrong, f'{name}: 늘린 타일 칸 {cells}개 가운데 {wrong}개 팔레트가 입력 니블과 다름')
    return {'case': name, 'world': world, 'cells_using_512_up': cells, 'palette_from_input_nibble': cells - wrong}


def world_log(dump):
    """lua/dq5worldlog.lua 의 world.txt: ($1949 쓰기 [(PC, 값, 첫 프레임, 횟수)], 00:BBAC 에 들어갈 때 [(값, 첫 프레임, 횟수)])."""
    rows = [x.split() for x in (dump / 'world.txt').read_text().splitlines() if x]
    writes = [(pc, int(v, 16), int(f), int(c)) for k, pc, v, f, c in rows if k == 'write']
    reads = [(int(v, 16), int(f), int(c)) for k, _, v, f, c in rows if k == 'read']
    return writes, reads


def check_world(name, roms, dirs, frames, nibs, start=None, writers=(), ff=None):
    """세계를 옮긴 뒤 nibs 롬의 늘린 타일 칸 팔레트가 그 세계 입력 니블과 같고(다른 세계 니블과는 모두 다름), 타일 번호·CGRAM 은
    같은 니블 롬과 같은지. 두 롬과 원본 게임의 $1949 쓰기·00:BBAC 호출 기록과 걸은 결과도 견준다.
    roms·dirs 는 WORLD_ROMS 이름 → 롬·덤프, frames 는 [(프레임, 세계)], nibs 는 세계 → 입력 니블,
    start 는 장면을 시작할 때 서는 필드 세계(실내에서 시작하면 None), writers 는 $1949 를 써야 하는 PC 들,
    ff 는 3 이상을 써도 되는 PC(쓰기는 있어야 함). 00:BBAC 가 읽는 값은 늘 0~2 다."""
    logs = {r: world_log(dirs[r]) for r in WORLD_ROMS}
    walks = {r: next(x for x in (dirs[r] / 'warp.txt').read_text().splitlines() if ' test ' in x) for r in WORLD_ROMS}
    require(logs['tiles'] == logs['nibs'], f'{name}: $1949·00:BBAC 기록이 같은 니블 롬과 다름')
    require(len(set(walks.values())) == 1, f'{name}: 걸은 결과가 롬마다 다름 {walks}')
    want = {w for _, w in frames} | ({start} if start is not None else set())
    for r, (writes, reads) in logs.items():
        require({v for v, _, _ in reads} == want,
                f'{name} {r}: 00:BBAC 의 $1949 가 {sorted({v for v, _, _ in reads})}(기대 {sorted(want)})')
        high = {pc for pc, v, _, _ in writes if v > 2}
        require(high == ({ff} if ff else set()), f'{name} {r}: $1949 에 3 이상을 쓴 PC {sorted(high)}(기대 {ff})')
        missing = set(writers) - {pc for pc, _, _, _ in writes}
        require(not missing, f'{name} {r}: $1949 를 쓰지 않은 PC {sorted(missing)}')
    out = []
    for n, w in frames:
        tiles = check_tiles(f'{name}-tiles', roms['tiles'], dirs['tiles'], n, dirs['orig'], w)
        res = check_tiles(name, roms['nibs'], dirs['nibs'], n, dirs['orig'], w)
        pal = check_nibbles(name, dirs['nibs'], w, nibs[w], n)
        other = {k: nibble_cells(dirs['nibs'], nibs[k], n)[1] for k in nibs.keys() - {w}}
        require(all(v == pal['cells_using_512_up'] for v in other.values()),
                f'{name}: 세계 {w} 칸이 다른 세계 니블과도 맞음 {other}')
        tv, nv = frame(dirs['tiles'], n, 'vram'), frame(dirs['nibs'], n, 'vram')
        moved = sum(nv[i:i + 2] != tv[i:i + 2] for i in range(0, 0x2000, 2)
                    if (nv[i] | nv[i + 1] << 8) & 0x3FF != (tv[i] | tv[i + 1] << 8) & 0x3FF)
        require(not moved, f'{name}: 타일 번호가 같은 니블 롬과 다른 칸 {moved}')
        require(frame(dirs['tiles'], n, 'cgram') == frame(dirs['nibs'], n, 'cgram'), f'{name}: CGRAM 이 같은 니블 롬과 다름')
        palette_diff = sum(nv[i:i + 2] != tv[i:i + 2] for i in range(0, 0x2000, 2))
        require(palette_diff == (0 if w == 0 else pal['cells_using_512_up']),
                f'{name}: 같은 니블 롬과 팔레트가 다른 칸 {palette_diff}')
        out.append({'case': name, 'frame': n, 'world': w, 'cells_using_512_up': res['cells_using_512_up'],
                    'palette_from_input_nibble': pal['palette_from_input_nibble'], 'other_world_mismatch': other,
                    'tiles_rom_cells': tiles['cells_using_512_up'], 'palette_differs_from_tiles_rom': palette_diff})
    return {'case': name, 'walk': walks['nibs'].split(' test ')[1], 'world_writes': logs['nibs'][0],
            'bbac': logs['nibs'][1], 'orig_bbac': logs['orig'][1], 'frames': out}


def time_set(times, t):
    """세계 0 시간대 표([[하한, 벌], …], 하한 차례)에서 $075E = t 가 고르는 벌."""
    return [k for low, k in times if low <= t][-1]


def check_clock(name, rom_path, dumps, world):
    """세계 world 에 들어가면 $075E 가 0 이 되고 걸어도 ラナルータ 를 외워도 그대로이며 2·3번 줄이 그 세계 한 벌인지,
    세계 0 으로 돌아오면 0 에서 시계가 다시 가고 ラナルータ 가 듣는지. dumps 는 CLOCK_ROMS 이름 → 덤프."""
    rom = Rom(rom_path.read_bytes())
    cur = fgw.current(rom)
    rows = {r: [x.split() for x in (d / 'world.txt').read_text().splitlines() if x] for r, d in dumps.items()}
    clock = {r: [x for x in v if x[0] in ('w075E', 'w075F')] for r, v in rows.items()}
    require(clock['orig'] == clock['nibs'], f'{name}: $075E 쓰기가 원본 게임과 다름')
    log = rows['orig']
    resets = {(x[1], x[2]) for x in log if x[0] == 'w075E' and x[1] == CLOCK_RESET[world]}
    require(resets == {(CLOCK_RESET[world], '00')}, f'{name}: 세계 {world} 불러오기의 $075E = 0 쓰기가 없음')
    casts = {int(x[2], 16) for x in log if x[0] == 'read' and x[1] == RANARUTA}
    sets = {int(x[2], 16) for x in log if x[0] == 'read' and x[1] == RANARUTA_SET}
    require(casts == {world, 0} and sets == {0}, f'{name}: ラナルータ 가 세계 {sorted(casts)} 에서 돌고 {sorted(sets)} 에서 바꿈')
    writers = {x[1] for x in log if x[0] == 'w075E'}
    require(writers == {CLOCK_RESET[world], CLOCK_TICK, RANARUTA_WRITE},
            f'{name}: $075E 를 쓴 곳 {sorted(writers)}')
    d = dumps['orig']
    seen = {0: [], world: []}
    for f in sorted(d.glob('f[0-9]*.wram')):
        w = f.read_bytes()
        n = int(f.stem[1:])
        # 화면이 어두운 프레임(불러오기·ラナルータ 의 페이드)은 팔레트를 옮기는 도중일 수 있어 뺀다.
        ppu = dict(x.split('=', 1) for x in (d / f'f{n:05d}.ppu.txt').read_text().split())
        if w[0xBE] & 0x80 or w[0x1001] or w[0x1949] not in seen or ppu['ppu.screenBrightness'] != '15':
            continue
        t = w[0x75E] | w[0x75F] << 8
        got = rows23(frame(d, n, 'cgram'))
        if w[0x1949] == world:
            want = cur['palettes'][f'world{world}'][0]
            require(t == 0, f'{name}: {n}프레임 세계 {world} 에서 $075E = {t:04X}')
        else:
            want = cur['palettes']['world0'][time_set(cur['world0_times'], t)]
        require(got == [want[i] for i in range(30) if i % 15 < 13], f'{name}: {n}프레임 2·3번 줄이 $075E {t:04X} 벌과 다름')
        seen[w[0x1949]].append((n, t, w[0xB6] | w[0xB7] << 8, w[0xB8] | w[0xB9] << 8))
    there = seen[world]
    require(len({(x, y) for _, _, x, y in there}) > 1, f'{name}: 세계 {world} 에서 걸은 덤프가 없음')
    times0 = [t for _, t, _, _ in seen[0]]
    require(times0[0] == 0x0120 and times0[-1] == 0x0190 and len(set(times0)) > 3,
            f'{name}: 세계 0 의 $075E 가 {[f"{t:04X}" for t in times0]}')
    return {'case': name, 'world': world, 'dumps_in_world': len(there),
            'positions_in_world': len({(x, y) for _, _, x, y in there}),
            'world0_075E': [f'{t:04X}' for t in dict.fromkeys(times0)], '075E_writers': sorted(writers),
            'ranaruta_in_world': sorted(casts), 'ranaruta_changed_in': sorted(sets)}


def check_palset(name, rom_path, dump, bcbd, s, alt, orig_dump=None, same=None):
    """맵에 선 뒤 BG 1~7번 줄이 세트 s 의 낮(alt 면 밤) 목록이고, 그 세트의 다른 쪽 목록·맵 → 세트 표의 세트와는 다른지.
    orig_dump 를 주면 원본 게임과 같은지(same) 다른지도 본다."""
    rom = Rom(rom_path.read_bytes())
    w, cg = frame(dump, INDOOR_FRAME, 'wram'), frame(dump, INDOOR_FRAME, 'cgram')
    require(w[0xBC:0xBE] == bytes(bcbd) and w[0xBE] & 0x80, f'{name}: 맵이 {w[0xBC]:02X}/{w[0xBD]:02X}')
    want = dq5map.set_cgram(rom, s, alt)[0x20:0x100]
    require(cg[0x20:0x100] == want, f'{name}: BG 1~7번 줄이 세트 {s} 의 {"밤" if alt else "낮"} 목록과 다름')
    other = dq5map.set_cgram(rom, s, not alt)[0x20:0x100]
    table = dq5map.palette_set(rom, *bcbd)
    require(other != want or s == table, f'{name}: 세트 {s} 의 낮·밤 목록이 같아 가를 수 없음')
    if s != table:
        require(dq5map.set_cgram(rom, table, alt)[0x20:0x100] != want, f'{name}: 맵 표의 세트 {table} 와 같아 가를 수 없음')
    out = {'case': name, 'map': f'{bcbd[0]:02X}/{bcbd[1]:02X}', 'set': s, 'night': alt, 'map_table_set': table,
           '075E': f'{w[0x75E] | w[0x75F] << 8:04X}'}
    if orig_dump is not None:
        eq = cg[0x20:0x100] == frame(orig_dump, INDOOR_FRAME, 'cgram')[0x20:0x100]
        require(eq == same, f'{name}: 원본 게임과 {"같음" if eq else "다름"}')
        out['same_as_original'] = eq
    return out


def check_ending(name, roms, dirs):
    """엔딩의 필드 비행: 원본·tiles 롬 모두 02:B9D8 이 $1949 = 0 을 쓰고 01:A4A7 로 필드를 불러오며, BG3 글자 기준이 VRAM
    워드 4000 이고 4000~5FFF 가 비어 있는지. tiles 롬은 블록이 늘린 타일을 쓰므로 그 칸이 빈 타일로 보인다(충돌).
    알려진 문제를 그대로 확인하는 검사다. 엔딩 비행에서 늘린 타일을 지키게 고치면 이 검사를 바꿀 것."""
    out = {'case': name, 'known_issue': '엔딩 스태프 롤 준비(02:FA86)가 VRAM 4000~5FFF 를 지워 늘린 타일 칸이 빈 타일로 보임'}
    for r in ('orig', 'tiles'):
        d = dirs[r]
        writes, reads = world_log(d)
        require({(pc, v) for pc, v, _, _ in writes} == {('2AFEEF', 0), (ENDING_WRITE, 0)} or
                {(pc, v) for pc, v, _, _ in writes} == {(ENDING_WRITE, 0)}, f'{name} {r}: $1949 쓰기 {writes}')
        w, vram = frame(d, ENDING_FRAME, 'wram'), frame(d, ENDING_FRAME, 'vram')
        ppu = dict(x.split('=', 1) for x in (d / f'f{ENDING_FRAME:05d}.ppu.txt').read_text().split())
        require(w[0x21EA] & 0x80 and not w[0xBE] & 0x80 and w[0x1949] == 0, f'{name} {r}: 엔딩 필드가 아님')
        require(ppu['ppu.layers[2].chrAddress'] == str(0x4000), f'{name} {r}: BG3 글자 기준 {ppu["ppu.layers[2].chrAddress"]}')
        require(not any(vram[0x8000:0xC000]), f'{name} {r}: VRAM 워드 4000~5FFF 가 비어 있지 않음')
        cells = sum((vram[i] | vram[i + 1] << 8) & 0x3FF >= fgw.TILES for i in range(0, 0x2000, 2))
        out[r] = {'1949_writes': [x[:2] for x in writes], 'bbac': reads, 'bg3_chr': '4000',
                  'cells_using_512_up': cells}
    loads = [x for x in (dirs['tiles'] / 'world.txt').read_text().split('\n') if x.startswith('read 01A4A7')]
    require(loads, f'{name}: tiles 롬에서 01:A4A7 이 돌지 않음')
    require(out['orig']['cells_using_512_up'] == 0 and out['tiles']['cells_using_512_up'],
            f'{name}: 늘린 타일 칸 원본 {out["orig"]["cells_using_512_up"]}·tiles {out["tiles"]["cells_using_512_up"]}')
    return out


def check_battle(name, rom_path, dump, orig):
    """전투 중에는 VRAM 워드 4000~5FFF 가 늘린 타일과 다르고(전투가 덮음), 돌아온 뒤에는 다시 같은지."""
    rom = Rom(rom_path.read_bytes())
    tiles, _ = fgw.current(rom)['worlds']['world0']
    w = frame(dump, IN_BATTLE, 'wram')
    require(w[0x1001] == 0 and w[0xBE] & 0x80 == 0, f'{name}: {IN_BATTLE}프레임이 첫 전투 전 필드 자리 아님')
    inside = vram_tiles(frame(dump, IN_BATTLE, 'vram'), len(tiles) // 32)[fgw.TILES:]
    over = sum(a != tiles[(fgw.TILES + i) * 32:(fgw.TILES + i + 1) * 32] for i, a in enumerate(inside))
    require(over, f'{name}: 전투 중({IN_BATTLE}프레임)에도 늘린 타일이 그대로라 다시 보내기를 가를 수 없음')
    require(frame(dump, AFTER_BATTLE, 'wram')[0x1001] != 0, f'{name}: {AFTER_BATTLE}프레임에 전투를 마치지 않음')
    out = check_tiles(name, rom_path, dump, AFTER_BATTLE, orig)
    out['in_battle_overwritten'] = over
    return out


def check_redraw(name, rom_path, dump, restored=True):
    """WIPEF 와 REDRAWN 사이에 01:A4A7 이 돌지 않고 00:A788 만 돌았는지, 두 프레임 모두 세계 0 필드인지 본 뒤,
    restored 면 470프레임에 늘린 타일이 돌아왔는지, 아니면(대조) 아직 비어 있는지."""
    rom = Rom(rom_path.read_bytes())
    extra = fgw.current(rom)['worlds']['world0'][0][fgw.TILES * 32:]
    wiped, back = (frame(dump, n, 'vram')[0x8000:0x8000 + len(extra)] for n in (WIPED, REDRAWN))
    require(wiped == bytes(len(extra)), f'{name}: {WIPED}프레임에 늘린 타일 자리가 지워지지 않음')
    wipe = int(WIPE['WIPEF'])
    runs = [line.split() for line in (dump / 'exec.txt').read_text().splitlines() if line]
    between = {pc for pc, n in runs if wipe <= int(n) < REDRAWN}
    require(between == {'00A788'}, f'{name}: {wipe}~{REDRAWN}프레임에 돈 것이 {sorted(between)}(00:A788 만이어야 함)')
    for n in (WIPED, REDRAWN):
        w = frame(dump, n, 'wram')
        require(not w[0xBE] & 0x80 and w[0x1949] == 0, f'{name}: {n}프레임이 세계 0 필드가 아님')
    if restored:
        require(back == extra, f'{name}: {REDRAWN}프레임에 늘린 타일이 돌아오지 않음(00:A788 → 01:B4D5 훅)')
    else:
        require(back == bytes(len(extra)), f'{name}: 01:B4D5 를 원본으로 둔 대조 롬인데 {REDRAWN}프레임에 채워짐')
    return {'case': name, 'wiped_at': wipe, 'checked_at': REDRAWN, 'between': sorted(between),
            'restored': back == extra, 'tiles': len(extra) // 32}


def check_reload(name, rom_path, dump, frames, want='reload'):
    """frames 마다 필드에 서서 늘린 타일이 그대로인지. reload 면 첫·마지막 덤프 사이에 01:A4A7 이 돌았는지,
    carpet 이면 01:A4A7 없이 첫 덤프에는 걸어 다니다 마지막 덤프에는 융단에 타고($1954) 걸었는지,
    empty 면 「다시 불러옴」 검사가 01:A4A7 이 돌지 않음으로 실패하는지(대조)."""
    if want == 'empty':
        try:
            check_reload(name, rom_path, dump, frames)
        except ValueError as error:
            require('01:A4A7 이 돌지 않음' in str(error), f'{name}: 다른 까닭으로 실패 {error}')
            return {'case': name, 'frames': list(frames), 'rejected': str(error)}
        raise ValueError(f'{name}: 물건이 없는데 다시 불러오기 검사를 통과함')
    extra = fgw.current(Rom(rom_path.read_bytes()))['worlds']['world0'][0][fgw.TILES * 32:]
    for n in frames:
        w = frame(dump, n, 'wram')
        require(not w[0xBE] & 0x80 and w[0x1001] == 0, f'{name}: {n}프레임에 필드에 서지 않음')
        require(frame(dump, n, 'vram')[0x8000:0x8000 + len(extra)] == extra, f'{name}: {n}프레임 늘린 타일이 다름')
    log = dump / 'exec.txt'
    runs = [x.split() for x in log.read_text().splitlines() if x] if log.is_file() else []
    require(all(len(x) == 2 and x[1].isdigit() for x in runs), f'{name}: exec.txt 에 잘린 줄이 있음')
    loads = [int(n) for pc, n in runs if pc == '01A4A7' and frames[0] < int(n) <= frames[-1]]
    vehicle = [frame(dump, n, 'wram')[0x1954] for n in (frames[0], frames[-1])]
    line = next(x for x in (dump / 'warp.txt').read_text().splitlines() if ' test ' in x)
    if want == 'reload':
        require(loads, f'{name}: {frames[0]}~{frames[-1]}프레임에 01:A4A7 이 돌지 않음(필드를 다시 불러오지 않음)')
    else:
        require(not loads, f'{name}: 융단인데 01:A4A7 이 {loads}프레임에 돎')
        require(vehicle == [0, CARPET], f'{name}: $1954 가 {vehicle[0]:02X} → {vehicle[1]:02X}(00 → 80 이어야 함)')
        require('moved=yes' in line, f'{name}: 융단에 탄 채 걷지 않음 {line}')
    return {'case': name, 'frames': list(frames), 'reloaded_at': loads, 'vehicle': [f'{v:02X}' for v in vehicle],
            'walk': line.split(' test ')[1]}


def check_move(name, rom_path, dump, want):
    """걷기 앞 VRAM 의 늘린 타일이 그 롬(--extra-at 자리)의 것과 같고, 걸었는지가 want 와 같은지."""
    cur = fgw.current(Rom(rom_path.read_bytes()))
    extra = cur['worlds']['world0'][0][fgw.TILES * 32:]
    require(frame(dump, MOVE_FRAME, 'vram')[0x8000:0x8000 + len(extra)] == extra,
            f'{name}: {MOVE_FRAME}프레임 VRAM 워드 4000~ 이 늘린 타일과 다름')
    line = next(x for x in (dump / 'warp.txt').read_text().splitlines() if ' test ' in x)
    require(f'moved={"yes" if want else "no"}' in line, f'{name}: {line}')
    return {'case': name, 'extra_tiles': len(extra) // 32, 'attribute': f'{cur["tile_attributes"][fgw.TILES]:02X}',
            'walk': line.split(' test ')[1]}


def rows23(cg):
    return [fgc.cg_color(cg, row, c) for row in (2, 3) for c in range(1, 14)]


def check_fieldpal(name, rom_path, dumps, orig_dumps):
    rom = Rom(rom_path.read_bytes())
    cur = fgw.current(rom)
    out = []
    for t, k in TIME_CASES.items():
        d, od = dumps[t], orig_dumps[t]
        w, cg, ocg = frame(d, SETTLE_FRAME, 'wram'), frame(d, SETTLE_FRAME, 'cgram'), frame(od, SETTLE_FRAME, 'cgram')
        require(w[0x75E] | w[0x75F] << 8 == t and w[0x1949] == 0 and not w[0xBE] & 0x80,
                f'{name} {t:04X}: $075E·필드가 맞지 않음')
        want = cur['palettes']['world0'][k]
        got = rows23(cg)
        require(got == [want[i] for i in range(30) if i % 15 < 13], f'{name} {t:04X}: 2·3번 줄이 벌 {k} 와 다름')
        night = k >= NIGHT_FROM
        person = [fgc.cg_color(cg, row, c) for row in (11, 12) for c in range(1, 16)]
        require(person == cur['person_palettes']['night' if night else 'day'],
                f'{name} {t:04X}: 11·12번 줄이 {"밤" if night else "낮"} 인물 팔레트와 다름')
        out.append({'075E': f'{t:04X}', 'set': k, 'night': night, 'rows_2_3': 26,
                    'differs_from_original': rows23(ocg) != got or (person != [fgc.cg_color(ocg, r, c)
                                                                         for r in (11, 12) for c in range(1, 16)])})
    changed = [o['075E'] for o in out if o['differs_from_original']]
    require(changed == [f'{t:04X}' for t, k in TIME_CASES.items() if k >= 8 or t == 0x00F1],
            f'{name}: 원본 게임과 다른 시간대가 {changed}')
    return {'case': name, 'times': out}


def check_indoor(name, rom_path, dump, orig_dump, bcbd, new):
    """맵에 선 뒤 CGRAM BG 1~7번 줄이 dq5map.map_cgram(옮긴 표를 따라감)과 같은지. new 면 원본 게임과 달라야 하고,
    아니면 원본 게임과 같아야 한다."""
    rom = Rom(rom_path.read_bytes())
    w, cg = frame(dump, INDOOR_FRAME, 'wram'), frame(dump, INDOOR_FRAME, 'cgram')
    require(w[0xBC:0xBE] == bytes(bcbd) and w[0xBE] & 0x80, f'{name}: 맵이 {w[0xBC]:02X}/{w[0xBD]:02X}')
    want = dq5map.map_cgram(rom, *bcbd)
    s = dq5map.palette_set(rom, *bcbd)
    require(cg[0x20:0x100] == want[0x20:0x100], f'{name}: BG 1~7번 줄이 세트 {s} 의 낮 목록과 다름')
    same = cg[0x20:0x100] == frame(orig_dump, INDOOR_FRAME, 'cgram')[0x20:0x100]
    require(same != new, f'{name}: 원본 게임과 {"같음" if same else "다름"}')
    return {'case': name, 'map': f'{bcbd[0]:02X}/{bcbd[1]:02X}', 'set': s, 'rows': 7, 'same_as_original': same}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('rom', type=Path)
    ap.add_argument('--state', type=Path, required=True)
    ap.add_argument('--mesence', default=os.environ.get('MESENCE'))
    ap.add_argument('--out', type=Path, default=Path('work/gfxlimitcheck'))
    args = ap.parse_args()
    if not args.mesence:
        ap.error('--mesence 또는 MESENCE 가 필요함')
    try:
        original, state, mesence = args.rom.resolve(), args.state.resolve(), Path(args.mesence).resolve()
        for path in (original, state, mesence):
            require(path.is_file(), f'파일 없음: {path}')
        args.out.mkdir(parents=True, exist_ok=True)
        out = Path(tempfile.mkdtemp(prefix='run-', dir=args.out.resolve()))
        print(f'실행 출력: {out}', flush=True)
        make_roms(original, out)
        tiles, fieldpal, indoor = (out / f'{k}.sfc' for k in ('tiles', 'fieldpal', 'indoor'))
        krlua = Path(subprocess.run(['krpatch', 'sfc', 'lua'], capture_output=True, text=True, check=True,
                                    timeout=30).stdout.strip())
        libdir = out / 'lib'
        shutil.copytree(krlua, libdir)
        shutil.copyfile(HERE / 'lua/dq5warp.lua', libdir / 'boot.lua')
        gfx = HERE / 'lua/dq5gfxdump.lua'
        stand = {'FIELD': '341,56', 'SETTLE': str(SETTLE_FRAME), 'DUMPF': str(SETTLE_FRAME), 'MAXF': '1100'}
        world = {w: {'FIELD': '50,28', 'POKE': f'7E1949={w:02X}', 'SETTLE': str(SETTLE_FRAME),
                     'DUMPF': str(SETTLE_FRAME), 'MAXF': '1100'} for w in (1, 2)}
        scenes = {'stand': stand, 'walk': WALK, 'battle': BATTLE, 'world1': world[1], 'world2': world[2]}
        cases = [(f'tiles-{k}-{r}', path, env) for k, env in scenes.items()
                 for r, path in (('orig', original), ('grow', tiles))]
        nibs = out / 'nibs.sfc'
        cases += [(f'nibs-{k}', nibs, env) for k, env in (('stand', stand), ('world1', world[1]), ('world2', world[2]))]
        cases += [('move-tiles', tiles, MOVE), *((f'move-{v:02x}', out / f'wall-{v:02x}.sfc', MOVE) for v in WALLS)]
        control = out / 'redraw-control.sfc'
        data = bytearray(tiles.read_bytes())
        data[lorom(fgw.REDRAW_SITE):lorom(fgw.REDRAW_SITE) + 4] = fgw.REDRAW_ORIG
        control.write_bytes(bytes(data))
        luas = {k: HERE / 'lua/dq5vramwipe.lua'
                for k in ('redraw-tiles', 'redraw-control', *(f'reload-{r}' for r in ITEM_SCENES))}
        for k, (env, frames, _) in ITEM_SCENES.items():
            cases.append((f'reload-{k}', tiles, dict(env, FIELD='310,60', SETTLE='60', MAXF='2000', EXECLOG='01A4A7',
                                                     NEXT=str(gfx), DUMPF=','.join(map(str, frames)))))
        worldlog = HERE / 'lua/dq5worldlog.lua'
        world_roms = {'orig': original, 'tiles': tiles, 'nibs': nibs}
        for k, (env, frames, _) in WORLD_SCENES.items():
            for r in WORLD_ROMS:
                luas[f'{k}-{r}'] = worldlog
                cases.append((f'{k}-{r}', world_roms[r], dict(env, SETTLE='60', NEXT=str(gfx),
                                                                 DUMPF=','.join(str(n) for n, _ in frames))))
        for r in ('orig', 'tiles'):
            luas[f'ending-{r}'] = worldlog
            cases.append((f'ending-{r}', world_roms[r], dict(ENDING, SETTLE='60', NEXT=str(gfx))))
        for k, (env, _) in CLOCK_SCENES.items():
            for r in CLOCK_ROMS:
                luas[f'{k}-{r}'] = worldlog
                cases.append((f'{k}-{r}', world_roms[r], dict(env, SETTLE='60', NEXT=str(gfx))))
        cases += [('redraw-tiles', tiles, dict(WIPE, NEXT=str(gfx))),
                  ('redraw-control', control, dict(WIPE, NEXT=str(gfx)))]
        for t in TIME_CASES:
            env = dict(stand, SET=f'075E={t & 0xFF:02X};075F={t >> 8:02X}')
            cases += [(f'pal-{t:04X}-{k}', r, env) for k, r in (('orig', original), ('grow', fieldpal))]
        rom = Rom(original.read_bytes())
        for m in [NEW_MAP] + SAME_MAPS:
            a = map_pointer(rom, *m)
            env = {'TO': f'{m[0]:02X}/{m[1]:02X},{rom.u8(a + 1) // 2},{rom.u8(a + 2) // 2},1',
                   'DUMPF': str(INDOOR_FRAME), 'SETTLE': '400', 'MAXF': '1100'}
            cases += [(f'indoor-{m[0]:02X}{m[1]:02X}-{k}', r, env) for k, r in (('orig', original), ('grow', indoor))]
            if m == NEW_MAP:
                cases += [(f'night-{m[0]:02X}{m[1]:02X}-{k}', r, dict(env, SET=NIGHT_SET))
                          for k, r in (('orig', original), ('grow', indoor))]
        a = map_pointer(rom, *FLAG_MAP)
        require(rom.d[lorom(FLAG_ENTRY):lorom(FLAG_ENTRY) + 5] == bytes([*FLAG_MAP, 0x44, 0x04, FLAG_SET]),
                f'2A:8690 의 06/00 항목이 {rom.d[lorom(FLAG_ENTRY):lorom(FLAG_ENTRY) + 5].hex()}')
        flag = {'TO': f'{FLAG_MAP[0]:02X}/{FLAG_MAP[1]:02X},{rom.u8(a + 1) // 2},{rom.u8(a + 2) // 2},1',
                'DUMPF': str(INDOOR_FRAME), 'SETTLE': '400', 'MAXF': '1100', 'SET': FLAG_ON}
        newset = f'{lorom(FLAG_ENTRY + 4):X}={NEW_SET:02X}'
        cases += [('flag-orig', original, flag), ('flag-grow', indoor, flag),
                  ('flag-new', indoor, dict(flag, ROMPATCH=newset)),
                  ('flag-new-night', indoor, dict(flag, ROMPATCH=newset, SET=f'{FLAG_ON};{NIGHT_SET}'))]
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            dirs = dict(zip([c[0] for c in cases], pool.map(
                lambda c: gwc.run(mesence, c[1], luas.get(c[0], gfx), c[2], out / c[0], libdir, state), cases)))
        d = {k: (dirs[f'tiles-{k}-grow'], dirs[f'tiles-{k}-orig']) for k in scenes}
        results = [check_tiles('tiles-stand-orig', original, d['stand'][1], SETTLE_FRAME, None, grown=False),
                   check_tiles('tiles-stand', tiles, *d['stand'][:1], SETTLE_FRAME, d['stand'][1]),
                   check_tiles('tiles-walk', tiles, d['walk'][0], WALK_FRAME, d['walk'][1]),
                   check_battle('tiles-battle', tiles, *d['battle']),
                   *(check_tiles(f'tiles-world{w}', tiles, d[f'world{w}'][0], SETTLE_FRAME, d[f'world{w}'][1], w)
                     for w in (1, 2))]
        nib = json.loads((out / 'tiles-src' / 'nibs.json').read_text(encoding='utf-8'))
        for w, k in enumerate(('stand', 'world1', 'world2')):
            want = nib['worlds'][f'world{w}']['tile_palettes'] if w else nib['tile_palettes']
            results.append(check_tiles(f'nibs-world{w}', nibs, dirs[f'nibs-{k}'], SETTLE_FRAME, d[k][1], w))
            results.append(check_nibbles(f'nibs-world{w}-palette', dirs[f'nibs-{k}'], w, want))
        nibs_in = {w: nib['worlds'][f'world{w}']['tile_palettes'] if w else nib['tile_palettes'] for w in range(3)}
        for k, (env, frames, writers) in WORLD_SCENES.items():
            results.append(check_world(k, world_roms, {r: dirs[f'{k}-{r}'] for r in WORLD_ROMS}, frames, nibs_in,
                                       0 if 'FIELD' in env else None, writers, WORLD_FF.get(k)))
        results += [check_move('move-tiles', tiles, dirs['move-tiles'], True),
                    *(check_move(f'move-{v:02x}', out / f'wall-{v:02x}.sfc', dirs[f'move-{v:02x}'], ok)
                      for v, ok in WALLS.items()),
                    check_redraw('redraw-tiles', tiles, dirs['redraw-tiles']),
                    check_redraw('redraw-control', control, dirs['redraw-control'], restored=False),
                    *(check_reload(f'reload-{k}', tiles, dirs[f'reload-{k}'], f, r)
                      for k, (_, f, r) in ITEM_SCENES.items())]
        results.append(check_fieldpal('fieldpal', fieldpal, {t: dirs[f'pal-{t:04X}-grow'] for t in TIME_CASES},
                                      {t: dirs[f'pal-{t:04X}-orig'] for t in TIME_CASES}))
        for m in [NEW_MAP] + SAME_MAPS:
            key = f'indoor-{m[0]:02X}{m[1]:02X}'
            results.append(check_indoor(key, indoor, dirs[f'{key}-grow'], dirs[f'{key}-orig'], m, m == NEW_MAP))
        results.append(check_palset('night-0101-orig', original, dirs['night-0101-orig'], NEW_MAP,
                                    dq5map.palette_set(rom, *NEW_MAP), True))
        results.append(check_palset('night-0101', indoor, dirs['night-0101-grow'], NEW_MAP, NEW_SET, True,
                                    dirs['night-0101-orig'], False))
        results.append(check_palset('flag-orig', original, dirs['flag-orig'], FLAG_MAP, FLAG_SET, False))
        results.append(check_palset('flag', indoor, dirs['flag-grow'], FLAG_MAP, FLAG_SET, False, dirs['flag-orig'], True))
        results.append(check_palset('flag-new', indoor, dirs['flag-new'], FLAG_MAP, NEW_SET, False, dirs['flag-orig'],
                                    False))
        results.append(check_palset('flag-new-night', indoor, dirs['flag-new-night'], FLAG_MAP, NEW_SET, True))
        results.append(check_ending('ending', world_roms, {r: dirs[f'ending-{r}'] for r in ('orig', 'tiles')}))
        for k, (_, w) in CLOCK_SCENES.items():
            results.append(check_clock(k, original, {r: dirs[f'{k}-{r}'] for r in CLOCK_ROMS}, w))
        (out / 'results.json').write_text(json.dumps(results, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
        print(f'{len(results)}/{len(results)} 통과')
        print(json.dumps(results, ensure_ascii=False))
        return 0
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.SubprocessError) as error:
        print(f'오류: {error}', file=sys.stderr)
        if isinstance(error, subprocess.CalledProcessError) and error.stderr:
            print(error.stderr, file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
