"""상자·서랍·발밑·두 칸 앞·아래층 상자·필드 보상 쓰기를 원본/패치 롬의 실제 조사 명령으로 비교한다.

sfc/dq5/docs/dq5-map-format.md의 보물상자 형식. 입력 JSON→dq5patch→롬/IPS를 만들고,
선실에서 걸어가거나 dq5warp.lua 로 그 자리에 내려선 뒤 컨트롤러로 조사한다. 금화·조회된 보상·열림 비트·
기존 비트 보존을 확인한다. 원본 롬/세이브는 읽기만 하고 --out 아래 새 폴더에 저장한다.
past_* 사례는 상자 194개·상자 맵 연결과 아래층 상자 표를 뱅크 3F 로 옮긴 롬에서 열기·들어갈 때 그리기·기록과 불러오기를 본다.
wide_* 사례는 상자 번호 16비트 훅(dq5chestreloc.py --wide-at)으로 상자를 301개 둔 롬에서 상자 300 을 같은 셋으로 본다.
wideitem_open 은 같은 롬에서 상자 300 의 보상만 물건으로 바꿔, 물건 길로 12:F839 에 가는지 본다.
widelock_open·widefull_open 은 상자 300 을 잠긴 상자·가방이 가득한 물건으로 바꾼 롬에서 두 번 열어, 12:F839 를 지나지
않은 보상이 남긴 넘길 마스크(7E:291B)를 다음 열기가 지우는지 본다(패치 롬만).
widenum_* 은 상자를 576개까지 놓은 롬에서 19/00 의 (12,45) 를 상자 256·263·264·421·575 로 두고 열어 비트 자리·다른 바이트
보존·다시 들어갈 때 그리기를, widemon_*·widemon2_* 는 상자 300 을 상자 몬스터(FFFD·FFFE)로 바꿔 이기거나 전멸한 뒤의 비트와
291B 를 본다. 전멸은 교회 기록의 SRAM 과, 리셋해 불러온 뒤 다른 상자를 여는 것까지 본다(패치 롬만).
edge_leave 는 상자 576개 롬의 01/02 상자 256 을 열고 실제로 다른 맵에 갔다가 돌아와 다시 그리기를, edgelock_other·edgefull_other 는
그 상자를 잠긴 상자·가득 찬 가방으로 연 뒤 다른 맵을 거쳐 다른 상자를 열 때 291B 를 지우는지 본다(패치 롬만).
new_* 사례는 원래 롬에 없는 새 그룹 맵 36/00(선실 17/00 에 상자 블록을 놓은 레코드)에 상자·タンス·두 칸 앞 항목을
dq5chestreloc.py --new-map·--with-patch 로 넣은 롬을, 같은 새 맵 패치만 붙인 대조 롬과 견준다.
blocks_* 사례는 --env 로 준 DQ4 환경 패치 폴더(sfc/dq4/tools/dq4environmentrom.py 출력)로 새 맵 36/00 을 만든다. 그 맵은
환경 패치의 01:936E 훅이 블록 표를 바꾸는 맵이다. 그 맵에만 놓인 환경 블록을 상자 블록 꼴로 바꾼 사본으로 빌드해 상자를 연다.
--audit 은 원본 롬에서 상자 맵 연결·아래층 상자 표의 DB(1E) 창을 연 동안 실행한 명령을 모아(lua/dq5dbread.lua),
DB 로 롬(8000~)에 닿는 명령이 표 읽기 자리뿐인지 본다.

  MESENCE=… python sfc/dq5/tools/dq5chestcheck.py rom/dq5.sfc --state work/state/ship.mss [--audit] [--env work/env]
"""
import argparse
import concurrent.futures
import copy
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

from kr_patch.sfc.dis65816 import decode
from kr_patch.sfc.mapper import LoROM

from dq5chestreloc import ABS, WIDE_BITS, WIDE_PENDING
from dq5chestwrite import FORMAT
from dq5exitcheck import DB_ABS, DB_INDIRECT, warp_exit
from dq5chest import chests
from dq5map import Rom, block_hook, block_table
from dq5mapcompile import compile_places, extract
from dq5mapwrite import all_maps, dumps

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
INPUT = ('up:8,wait:30,a:8,wait:60,down:6,wait:25,down:6,wait:25,down:6,wait:25,'
         'right:6,wait:25,a:8,wait:200,a:4,wait:150,a:4,wait:150,b:4,wait:220')
CASES = {
    'chest': ({'chests': [{'index': 2, 'reward': 0x241}]}, 321, 0x2210, 0x20, 0x2210, 0x20, 0x33, 0x131),
    # 2230 & 80 은 서랍 32 가 쓰므로 빈 2237 & 80 으로 옮긴다
    'search': ({'search': [{'index': 31, 'reward': 0x2B0, 'flag_index': 0x0B, 'mask': 0x80}]},
               432, 0x2237, 0x80, 0x222F, 1, 0xA1, 0x12F),
    'foot': ({'foot': [{'index': 0, 'group': 0x17, 'map': 0, 'x': 3, 'y': 5, 'layer': 1,
                       'reward': 0x31F, 'flag_index': 3, 'mask': 0x40}]},
             543, 0x2243, 0x40, 0x222F, 1, 0xA1, 0x12B),
    # 항목 11(03/04)의 비트 223D & 08 은 12:AE9C 가 직접 보므로 보상만 바꾼다
    'ahead': ({'ahead': [{'index': 11, 'reward': 0x38E}]}, 654, 0x223D, 0x08, 0x223D, 0x08, 0x5F, 0x12B),
    'lower': ({'lower': [{'index': 3, 'reward': 0x3FD, 'flag_index': 0x19, 'mask': 0x08}]},
              765, 0x2229, 0x08, 0x2228, 0x08, 0xB1, 0x131),
    'field': ({'field': [{'index': 0, 'reward': 0x46C}]}, 876, 0x21B3, 0x10, 0x21B3, 0x10, 0xCA, 0x12B),
    # 원본은 이 칸에 보상이 없다(old_reward None)
    'field_move': ({'field': [{'index': 0, 'x': 24, 'y': 168, 'reward': 0x46C, 'flag_index': 0x22, 'mask': 0x04}]},
                   876, 0x21B2, 0x04, 0x21B3, 0x10, None, 0x12B),
}
# 세계 1·2 필드의 같은 칸. 들어서면 $075E 가 0 이라 밤이 오지 않아 원본·패치 모두 빛도 보상도 없다(마스크 0 = 비트를
# 켜지 않음). 밤으로 고정하면 세계 0 과 같이 빛을 놓고 보상을 준다
for _world in (1, 2):
    CASES[f'field_world{_world}'] = CASES['field']
    CASES[f'field_world{_world}_day'] = ({'field': [{'index': 0, 'reward': 0x46C}]}, None, 0x21B3, 0, 0x21B3, 0x10,
                                         None, 0x12B)


def grow_chests(doc):
    # 표에 없는 상자 칸 26개의 맵을 뒤에 붙임. 19/00 이 마지막이라 (6,45) 가 상자 185(7E:2227 & 40)
    for group, map_number, count in ((0x00, 0x0C, 2), (0x02, 0x01, 3), (0x19, 0x02, 3), (0x1D, 0x03, 2),
                                     (0x1F, 0x00, 2), (0x20, 0x00, 2), (0x20, 0x01, 7), (0x19, 0x00, 5)):
        doc['chest_maps'].append({'group': group, 'map': map_number, 'count': count})
        doc['chests'] += [{'reward': 0xFFFF}] * count
    doc['chests'][185] = {'reward': 0x100 + 987}


def grow_search(doc):
    doc['search'].append({'group': 0x17, 'map': 0, 'x': 2, 'y': 4, 'unused': 1, 'reward': 0x100 + 111,
                          'flag_index': 0x0B, 'mask': 0x01})


def grow_foot(doc):
    doc['foot'].append({'group': 0x17, 'map': 0, 'x': 3, 'y': 5, 'layer': 1, 'reward': 0x100 + 222,
                        'flag_index': 3, 'mask': 0x20})


def grow_ahead(doc):
    doc['ahead'].append({'group': 0x17, 'map': 0, 'x': 9, 'y': 9, 'reward': 0x100 + 333,
                         'flag_index': 0x2E, 'mask': 0x04})


def move_lower(doc):
    doc['lower'][3].update(reward=0x100 + 444, flag_index=0x19, mask=0x10)


# dq5chestreloc.py 로 표 전체를 다시 쓰는 사례: (문서 고치기, 자리, 금화, 새 비트, 마스크, 원래 비트, 마스크,
# 원본 보상 또는 None, 패치 메시지, 원본이 못 찾을 때의 메시지). 자리는 시험용으로 고른 빈 곳이다
RELOC = {
    'grow_chests': (grow_chests, {'chests': '3F:8000', 'chest-maps': '1E:EE4E'}, 987, 0x2227, 0x40, 0x2227, 0x40,
                    None, 0x131, 0x12C),
    'grow_search': (grow_search, {'search': '3F:9000'}, 111, 0x2237, 0x01, 0x2237, 0x01, None, 0x12F, 0x130),
    'grow_foot': (grow_foot, {'foot': '3F:A000'}, 222, 0x2243, 0x20, 0x222F, 0x01, 0xA1, 0x12B, None),
    'grow_ahead': (grow_ahead, {'ahead': '3F:B000'}, 333, 0x223E, 0x04, 0x223E, 0x04, None, 0x12B, 0x12C),
    'move_lower': (move_lower, {'ahead': '3F:B000', 'lower': '1E:F435'}, 444, 0x2229, 0x10, 0x2228, 0x08, 0xB1,
                   0x131, None),
}
# 원본이 그 자리에서 아무것도 찾지 못할 때의 첫 메시지가 패치와 다른 사례(상자로 보지 않아 12B)
ORIGINAL_KIND = {'grow_chests': 0x12B, 'place_chest': 0x12B, 'place_furniture': 0x12B, 'place_jar': 0x12F,
                 'place_unlisted': 0x12B}
for _name, (_edit, _at, *_rest) in RELOC.items():
    CASES[_name] = (None, *_rest[:-1])
# dq5chestplace.py 로 01/02 에 상자 블록 384 를 (36,26) 에 놓는 사례. 새 상자 칸 (37,27) 이 맵의 첫 상자(번호 2)가 되어
# 원래 상자 (35,29) 는 번호 3 으로 밀리고, 내용물은 좌표를 따라간다
PLACE_DOC = {'format': 'dq5chestplace/1', 'maps': [{'map': '01/02', 'chests': [
    {'x': 36, 'y': 26, 'block': 384, 'reward': 0x100 + 954}]}]}
PLACE_AT = ('--map-at', '3E:8000', '--chests-at', '3F:8000')
# 01/02 의 (40,24) 에 タンス 블록 204(2×3)를 놓으면 오른쪽 아래 (41,26) 이 가구 칸(+4 = 93)이 된다
FURNITURE_DOC = {'format': 'dq5chestplace/1', 'maps': [{'map': '01/02', 'furniture': [
    {'x': 40, 'y': 24, 'block': 204, 'reward': 0x100 + 765, 'flag_index': 0x0B, 'mask': 0x02}]}]}
# 블록 없는 항목. 선실 17/00 은 タンス (4,4) 가 서랍 표에 있고 (2,4) 는 없다. 가구만 적으면 (2,4) 를 서랍 표 끝에 붙인다
JAR_DOC = {'format': 'dq5chestplace/1', 'maps': [{'map': '17/00', 'furniture': [
    {'x': 2, 'y': 4, 'reward': 0x100 + 345, 'flag_index': 0x0B, 'mask': 0x01}]}]}
# 상자 표에 없는 19/00 의 상자 칸 다섯((6,43)·(9,43)·(12,43)·(6,45)·(12,45))을 모두 적는다. 맵 연결을 끝에 붙이므로
# (6,45) 는 넷째 칸, 상자 164(7E:2224 & 08)다
UNLISTED_CELLS = ((6, 43), (9, 43), (12, 43), (6, 45), (12, 45))
UNLISTED_DOC = {'format': 'dq5chestplace/1', 'maps': [{'map': '19/00', 'chests': [
    {'x': x, 'y': y, 'reward': 0x100 + 786 + k} for k, (x, y) in enumerate(UNLISTED_CELLS)]}]}
UNLISTED_AT = ('--chests-at', '3F:8000', '--chest-maps-at', '3F:C000')
PLACE_INPUTS = {'place_chest': (PLACE_DOC, PLACE_AT), 'place_shift': (PLACE_DOC, PLACE_AT),
                'place_furniture': (FURNITURE_DOC, ('--map-at', '3E:8000', '--search-at', '3F:9000')),
                'place_jar': (JAR_DOC, ('--search-at', '3F:9000')),
                'place_unlisted': (UNLISTED_DOC, UNLISTED_AT), 'place_unlisted_entry': (UNLISTED_DOC, UNLISTED_AT)}
PLACE = {'place_chest': (954, 0x2210, 0x20, 0x2210, 0x20, None, 0x131),
         'place_furniture': (765, 0x2237, 0x02, 0x2237, 0x02, None, 0x12F),
         # 패치 롬에서도 금화가 아니라 원래 물건 33 을 얻으므로 금화 대신 보상 값을 적는다
         'place_shift': (None, 0x2210, 0x10, 0x2210, 0x20, 0x33, 0x131),
         'place_jar': (345, 0x2237, 0x01, 0x2237, 0x01, None, 0x12F),
         'place_unlisted': (789, 0x2224, 0x08, 0x2224, 0x08, None, 0x131)}
# 원래 롬이 그 칸에서 아무것도 찾지 못할 때의 다음 메시지(기본 12C)
NONE_MESSAGE = {'place_jar': 0x130}
CASES.update({name: (None, *values) for name, values in PLACE.items()})
# 상자를 192개 넘게 쓰는 롬. 표에 없는 맵 8곳의 26칸을 붙이고(grow_chests) 01/02 에 상자 블록 7개를 놓아 194개가 된다.
# 19/00 의 (6,45) 가 상자 192(7E:2228 & 80)다. 원래 아래층 상자 비트 2228~2229 와 겹치므로 아래층 상자의 flag_index 를
# 하나씩 올려 2229~222A 로 옮긴다. 상자 맵 연결·아래층 상자 표는 DB 즉값을 바꿔 뱅크 1E 밖(3F)으로 보낸다
GROW_DOC = {'format': 'dq5chestplace/1', 'maps': [{'map': '01/02', 'chests': [
    {'x': x, 'y': 22, 'block': 384, 'reward': 0x100 + 500 + x} for x in range(30, 44, 2)]}]}
GROW_AT = ('--map-at', '3E:8000', '--chests-at', '3F:8000', '--chest-maps-at', '3F:C000', '--lower-at', '3F:D000')


def grow_base(doc):
    grow_chests(doc)
    for row in doc['lower']:
        row['flag_index'] += 1


# 상자 256개 롬. 01/02 에 상자 블록 69개를 더 놓아 상자 비트 2210~222F 를 다 쓴다. 19/00 의 마지막 칸 (12,45) 가
# 상자 255(7E:222F & 01)다. 아래층 상자는 2243~2244 로, 2228~222F 를 쓰던 서랍 32항목은 빈 2237·2239~223B 로 옮긴다
# (2238 은 21:8C2F 가 읽음)
FULL_DOC = {'format': 'dq5chestplace/1', 'maps': [{'map': '01/02', 'chests': [
    {'x': x, 'y': y, 'block': 384, 'reward': 0x100 + 600 + k} for k, (x, y) in enumerate(
        [(x, y) for y in (14, 16, 18) for x in range(20, 60, 2)] + [(x, 20) for x in range(20, 38, 2)])]}]}
FULL_AT = GROW_AT + ('--search-at', '3F:A000')


def full_base(doc):
    grow_chests(doc)
    doc['chests'][186] = {'reward': 0x100 + 255}
    for row in doc['lower']:
        row['flag_index'] += 0x33 - 0x18
    moved = {0: 0x0B, 1: 0x0D, 2: 0x0E, 3: 0x0F}
    for row in doc['search']:
        row['flag_index'] = moved.get(row['flag_index'], row['flag_index'])


# 상자 번호 16비트 롬(dq5chestreloc --wide-at). 상자 256개 롬에 01/02 의 (16~90, 8)·(16~28, 10) 블록 45개를 더 놓아 301개다.
# 19/00 의 첫 칸이 상자 296 이고 마지막 칸 (12,45) 가 상자 300(7E:28F3 + 44/8 = 28F8 & 08)이다. 300 의 아래 8비트 44 는
# 원래 상자 44(7E:2215 & 08)와 같다
WIDE_DOC = {'format': 'dq5chestplace/1', 'maps': [{'map': '01/02', 'chests': FULL_DOC['maps'][0]['chests'] + [
    {'x': x, 'y': y, 'block': 384, 'reward': 0x100 + 700 + k} for k, (x, y) in enumerate(
        [(x, 8) for x in range(16, 92, 2)] + [(x, 10) for x in range(16, 30, 2)])]}]}
WIDE_AT = FULL_AT + ('--wide-at', '3F:E000')
WIDE_FLAG = (0x28F8, 0x08)
# 상자 300 을 열거나 기록해도 바뀌지 않아야 하는 원래 상자 1·44 의 바이트
WIDE_KEEP = (0x2210, 0x2215)


def wide_base(doc):
    full_base(doc)
    doc['chests'][186] = {'reward': 0x100 + 300}


# 상자 300 의 보상을 물건 33 으로. 금화(12:F490 의 BRL)와 달리 물건은 12:F6E4 를 지나 12:F70C 의 BRL 로 12:F839 에 간다
WIDE_ITEM = 0x33


def wideitem_base(doc):
    wide_base(doc)
    doc['chests'][186] = {'reward': WIDE_ITEM}


def widelock_base(doc):
    wide_base(doc)
    doc['chests'][186] = {'reward': 0xFFFC}


# 상자 몬스터. FFFD 는 이벤트 전투 무리 0D(ひとくいばこ 하나), FFFE 는 0C(ミミック 하나). 이기는 사례는 만든 롬에서 그
# 무리의 몬스터 칸(23:D757 + 무리 × 13 + 1)을 スライム(00)으로 바꾼다. 상자를 연 뒤 12:F4A4 → 01:868B → 12:F4A8 의 길은 같다
# (빌드, 보상, 무리, (몬스터 칸의 파일 위치, 원래 몬스터, 바꿀 몬스터))
MON_KINDS = {'widemon': (0xFFFD, 0x0D, (0x11D801, 0x36, 0x00)), 'widemon2': (0xFFFE, 0x0C, (0x11D7F4, 0x5D, 0x00))}


def widemon_base(doc, reward=0xFFFD):
    wide_base(doc)
    doc['chests'][186] = {'reward': reward}


# 상자 576개 롬. 상자 301개 롬의 블록 뒤에 01/02 의 (0~90, 24~38) 블록 139개(맵 상자 255개, 맵 연결 count 한도)와
# 16/00 의 (0~126, 30~34) 블록 136개를 더 놓는다. 01/02 의 원래 상자 (35,29)·(39,29) 를 덮는 (34,28)·(38,28) 은 뺀다.
# 두 맵 모두 맵 연결 표에서 19/00 보다 앞이라, 블록을 앞에서 K개만 놓으면 19/00 의 (12,45) 가 상자 186 + K 다
NUM_PLACES = [('01/02', x, y) for y in range(24, 40, 2) for x in range(0, 92, 2) if (x, y) not in ((34, 28), (38, 28))][:139] + \
    [('16/00', x, y) for y in (30, 32, 34) for x in range(0, 128, 2)][:136]
# 첫 번호, 바이트 28F3 의 끝 비트와 다음 바이트 28F4 의 첫 비트, 가운데(2907 & 04), 마지막(291A & 01)
NUMBERS = (256, 263, 264, 421, 575)


def number_bit(n):
    return WIDE_BITS + (n - 256) // 8, 0x80 >> (n & 7)


def number_build(n):
    rows = [('01/02', row) for row in WIDE_DOC['maps'][0]['chests']] + [
        (key, {'x': x, 'y': y, 'block': 384, 'reward': 0x100 + 800 + k}) for k, (key, x, y) in enumerate(NUM_PLACES)]
    maps = {}
    for key, row in rows[:n - 186]:
        maps.setdefault(key, []).append(row)

    def edit(doc):
        full_base(doc)
        doc['chests'][186] = {'reward': 0x100 + n}
    return {'format': 'dq5chestplace/1', 'maps': [{'map': key, 'chests': rows} for key, rows in maps.items()]}, edit, WIDE_AT


# 상자 576개 롬의 01/02 마지막 상자 칸 (5,31)(블록 (4,30))은 상자 256(7E:28F3 & 80)이다. 아래 칸 (4,33) 에 서서 위를 보고
# 열고, 19/00 의 계산대 안과 달리 dq5warp.lua 로 걸어 나갈 수 있다. 금화는 NUM_PLACES 의 차례로 938
EDGE_BLOCK = ('01/02', 4, 30)
EDGE = (256, '01/02,4,33', 0x28F3, 0x80, 938)
# 다른 상자는 01/02 의 원래 상자 (35,29)(물건 33, 256 미만). 선실이 아닌 곳에서 dq5warp.lua 로 오면 한 칸 아래 (34,32) 에
# 서므로 INPUT 의 up 이 (34,31) 로 걸어 올라간다(widemon_lose 와 같은 길)
EDGE_NEXT = ('01/02,34,31', 0x33)
AWAY = '19/00,5,46'


def edge_build(reward):
    doc, edit, at = number_build(575)
    doc = copy.deepcopy(doc)
    for group in doc['maps']:
        for row in group['chests']:
            if (group['map'], row['x'], row['y']) == EDGE_BLOCK:
                row['reward'] = reward
    return doc, edit, at


BUILDS = {'past': (GROW_DOC, grow_base, GROW_AT), 'full': (FULL_DOC, full_base, FULL_AT),
          'wide': (WIDE_DOC, wide_base, WIDE_AT), 'wideitem': (WIDE_DOC, wideitem_base, WIDE_AT),
          'widelock': (WIDE_DOC, widelock_base, WIDE_AT), 'widefull': (WIDE_DOC, wideitem_base, WIDE_AT),
          **{kind: (WIDE_DOC, lambda doc, r=reward: widemon_base(doc, r), WIDE_AT)
             for kind, (reward, _, _) in MON_KINDS.items()},
          **{f'widenum{n}': number_build(n) for n in NUMBERS},
          'edgelock': edge_build(0xFFFC), 'edgefull': edge_build(WIDE_ITEM)}
GROW = {'past_open': (987, 0x2228, 0x80, 0x2228, 0x80, None, 0x131),
        # 아래층 상자 51/51 (19,35). 원본은 2228 & 08, 패치는 옮긴 표의 2229 & 08 을 켠다
        'past_lower': (None, 0x2229, 0x08, 0x2228, 0x08, 0xB1, 0x131),
        'full_open': (255, 0x222F, 0x01, 0x222F, 0x01, None, 0x131),
        'wide_open': (300, *WIDE_FLAG, *WIDE_FLAG, None, 0x131),
        # 상자 1·44 를 연 채로 상자 300 을 연다. 8비트로 읽었다면 300 이 44 로 보여 이미 열린 상자가 된다
        'wide_alias': (300, *WIDE_FLAG, *WIDE_FLAG, None, 0x131),
        'wideitem_open': (None, *WIDE_FLAG, *WIDE_FLAG, None, 0x131)}
CASES.update({name: (None, *values) for name, values in GROW.items()})
# 새 그룹 맵 36/00: 선실 17/00 의 레코드에 상자 블록 384 를 (6,4) 에 놓아 상자 칸 (7,5) 를 만든다. タンス 칸 (4,4) 와
# 두 칸 앞 자리 (9,9) 는 선실과 같다. 들어가는 곳 표·문 표·새 레코드·출구는 새 맵 도구들이, 상자 표 넷은 뱅크 3B 로 옮긴다.
# 대조 롬은 상자 패치 없이 같은 새 맵 패치만 붙인다
NEWMAP_DOC = {'format': 'dq5newmap/1', 'groups': [{'group': '36', 'entrance': {'copy': '17'}}],
              'maps': [{'map': '36/00', 'record': {'source': 'cabin-chest.dq5map.json'}, 'attrs': {'copy': '17/00'}}]}
NEWMAP_AT = ('--entrance-table-at', '3E:C000', '--door-bank', '3D', '--records-at', '3A:8000')
NEWMAP_EXITS = ('--exits-at', '2A:D812', '--records-at', '3F:8000')
NEWMAP_CHEST_AT = ('--chests-at', '3B:8000', '--chest-maps-at', '3B:9000', '--search-at', '3B:A000',
                   '--ahead-at', '3B:B000')
NEW_MAP = ('--new-map', '36/00')


def grow_newmap(doc):
    # 상자 161 은 7E:2224 & 40. タンス·두 칸 앞은 grow_search·grow_ahead 와 같은 빈 비트
    doc['chest_maps'].append({'group': 0x36, 'map': 0, 'count': 1})
    doc['chests'].append({'reward': 0x100 + 456})
    doc['search'].append({'group': 0x36, 'map': 0, 'x': 4, 'y': 4, 'unused': 1, 'reward': 0x100 + 567,
                          'flag_index': 0x0B, 'mask': 0x01})
    doc['ahead'].append({'group': 0x36, 'map': 0, 'x': 9, 'y': 9, 'reward': 0x100 + 678,
                         'flag_index': 0x2E, 'mask': 0x04})


# (금화, 열림 비트, 마스크, 패치 메시지, 대조 롬이 못 찾을 때의 첫 메시지·다음 메시지)
NEWMAP = {'new_chest': (456, 0x2224, 0x40, 0x131, 0x12B, 0x12C),
          'new_search': (567, 0x2237, 0x01, 0x12F, 0x12F, 0x130),
          'new_ahead': (678, 0x223E, 0x04, 0x12B, 0x12B, 0x12C)}
# DQ4 환경 패치의 새 맵 36/00(burland). 2×2 환경 블록 21 은 목록의 다른 맵(롬에 있는 것)에는 놓이지 않고 36/00 에만
# (68,40)·(8,68) 두 번 놓인다. 그 머리를 상자 블록 384 와 같은 49 24 04 로 바꾸면 오른쪽 아래 (69,41)·(9,69) 가 상자 칸
# (상자 0·1)이 되고, 다른 맵의 칸은 바뀌지 않는다. 새 맵 패치의 자리는 sfc/dq4/tools/dq4groupbuild.py 와 같다
BLOCKS_MAP, BLOCKS_BLOCK, BLOCKS_HEAD = (0x36, 0), 21, bytes((0x49, 0x24, 0x04))
BLOCKS_CELLS = [(69, 41), (9, 69)]
BLOCKS_NEWMAP_AT = ('--entrance-table-at', '3C:C000', '--records-at', '34:8000', '--door-bank', '3B',
                    '--attr-table-at', '3C:D000')
BLOCKS_EXITS = ('--exits-at', '2A:D812', '--records-at', '3C:A000')
BLOCKS_CHEST_AT = ('--chests-at', '36:8000', '--chest-maps-at', '36:9000')
NEWMAP['blocks_chest'] = (246, 0x2210, 0x80, 0x131, 0x12B, 0x12C)
for _name, (_amount, _flag, _mask, _message, _kind, _none) in NEWMAP.items():
    CASES[_name] = (None, _amount, _flag, _mask, _flag, _mask, None, _message)
    ORIGINAL_KIND[_name] = _kind
PATCHED_REWARD = {'place_shift': 0x33, 'wideitem_open': WIDE_ITEM, 'past_lower': 0xB1, 'field_world1_day': None,
                  'field_world2_day': None}
ORIGINAL_KIND.update(past_open=0x12B, full_open=0x12B, wide_open=0x12B, wide_alias=0x12B, wideitem_open=0x12B)
# 맵에 들어갈 때 열린 상자를 그리는 사례: (장면, 미리 켤 비트). 원본은 그 비트를 상자로 보지 않아 그대로 두고,
# 패치는 1F:FC50 이 옮긴 표에서 그 상자를 찾아 열린 상자 타일(9E·9F)로 바꾼다
ENTRY = {'past_entry': ({'TO': '19/00,5,46'}, '2228|80'), 'past_entry_lower': ({'TO': '51/51,18,37,2'}, '2229|08'),
         'full_entry': ({'TO': '19/00,11,46'}, '222F|01'), 'wide_entry': ({'TO': '19/00,11,46'}, '28F8|08'), 'new_entry': ({'TO': '36/00,6,7'}, '2224|40'),
         'place_unlisted_entry': ({'TO': '19/00,5,46'}, '2224|08'), 'blocks_entry': ({'TO': '36/00,68,44'}, '2210|80')}
# 열림 비트를 켠 채 교회에 기록하고 리셋해 불러오는 사례(dq5cdlsweep.py 의 church-save-load 와 같은 입력).
# SRAM 칸 1 은 7E:2000~ 을 70:0012~ 에 그대로 담는다(25:83CE)
SAVES = {'past_save': {0x2228: 0x80, 0x2229: 0x08}, 'wide_save': {WIDE_FLAG[0]: WIDE_FLAG[1]}}
SAVE_SLOT = 0x700012
# 12:F839 를 지나지 않는 보상: 잠긴 상자(FFFC)와, 물건 12칸이 가득한데(7E:2056~2061 = A1) 버리기를 いいえ 로 거절한 물건.
# 상자 300 을 두 번 연다. 19/00 의 (11,46) 은 가게 계산대 안이라 다른 상자로 걸어갈 수 없다. 첫 번째가 남긴 넘길 마스크
# 291B 를 두 번째 열기 훅이 맵 안 순서를 세기(2A:F224) 전에 지우는지 본다. (보상, 장면에서 미리 고칠 WRAM, 상자 300 의
# 메시지, 한 번 열 때의 입력). 버리기 물음(13D)에 B 를 누르면 いいえ 로 14B 가 나온다. 패치 롬만 돌린다
STALE = {'widelock_open': (0xFFFC, '', [0x14E], INPUT),
         'widefull_open': (WIDE_ITEM, ';'.join(f'{a:04X}=A1' for a in range(0x2056, 0x2062)), [0x12E, 0x14A, 0x13D, 0x14B],
                           INPUT + ',wait:60,b:4,wait:300,b:4,wait:200')}
SAVE_FRAMES = {'saved': 2600, 'reset': 2710, 'loaded': 6400}
# 상자 번호 256~575 의 비트. 상자를 열고, 연 뒤의 비트로 19/00 에 다시 들어온다. 8비트 번호(n & FF)의 원래 상자 비트를
# 미리 켜 둔다(패치 롬만)
NUMBER = {f'widenum_{n}': n for n in NUMBERS}
# 상자 몬스터. 이김: 12:F4A8 로 돌아와 12:F839 에서 비트를 켬. 전멸: 교회에서 되살아나 기록까지 하고(A 를 거듭 누름),
# 01/02 의 상자 2 (35,29) 를 열어 다음 열기가 남은 291B 를 지우는지 본다
# 전멸 사례는 끝에 SRAM 도 남겨 교회 기록 칸 1 의 291B(70:0012 + 091B)를 본다
MONSTER = {f'{kind}_{end}': buttons for kind in MON_KINDS for end, buttons in (
    ('win', INPUT + ',' + ','.join(['a:4,wait:40'] * 60)),
    ('lose', INPUT + ',' + ','.join(['a:4,wait:40'] * 45) + ',wait:200,a:4,wait:400'))}
# 전멸 뒤 기록한 상태에서 리셋하고 타이틀에서 그 기록을 불러오는 입력(dq5cdlsweep.py 의 church-save-load 와 같은 누름).
# 불러온 뒤 남은 창은 B 로 닫는다
LOAD_RESET = 20
LOAD_INPUT = 'wait:247,' + ','.join(['start:4,wait:200'] * 3 + ['a:4,wait:120'] * 12 + ['b:4,wait:60'] * 4) + ',wait:200'
# 상자 256 을 열고 다른 맵(AWAY)에 갔다가 돌아와, 게임이 연 상태로 다시 그리는지 본다
LEAVE = {'edge_leave'}
# 상자 256 을 잠긴 상자·가방이 가득한 물건으로 두고 한 번 연 뒤, 다른 맵을 거쳐 상자 255(256 미만)를 연다. (빌드, STALE 사례)
OTHER = {'edgelock_other': ('edgelock', 'widelock_open'), 'edgefull_other': ('edgefull', 'widefull_open')}
ALL = [*CASES, *ENTRY, *SAVES, *STALE, *NUMBER, *MONSTER, *LEAVE, *OTHER]
# 조사 뒤 세계 지도 버퍼의 블록(블록 좌표 x, y, 원본, 패치). 밤이라 빛 블록 A7 이 놓인 자리를 본다
# 필드에 들어갈 때 빛 블록을 놓으므로, 장면도 그 롬으로 만들어야 하는 사례
OWN_SCENE = {'field_move', 'place_chest', 'place_shift', 'place_furniture', *NEWMAP}
# 집은 뒤 12:EFB9 가 보상 값이 그 필드 조사의 것이면 빛 칸을 세계 0 의 지도 블록으로 되돌린다(세계 1·2 지도의 그 자리는 00).
# dq5chestwrite.py 가 그 비교값·칸·블록도 함께 쓰므로 금화로 바꾸거나 칸을 옮겨도 돌아간다
BLOCKS = {'field_move': ((11, 83, 0xA7, 0xCA), (12, 84, 0x178, 0x178)),
          'field': ((11, 83, 0xCA, 0xCA),), 'field_world1': ((11, 83, 0xCA, 0xCA),), 'field_world2': ((11, 83, 0xCA, 0xCA),),
          'field_world1_day': ((11, 83, 0x00, 0x00),), 'field_world2_day': ((11, 83, 0x00, 0x00),)}
# 장면 없이 --state 를 그대로 쓰는 사례
START = 'start'
# 장면: 원본 롬에서 dq5warp.lua 로 내려선 자리, 없으면 선실에서 걸어감.
# 필드는 밤(`$075E` = `0100` 으로 둠)이고 21AA.0 이 켜져 있어야 빛 블록 코드가 21A5.2 를 켠다
SCENES = {'chest': {'TO': '01/02,34,31'}, 'search': None, 'foot': None, 'ahead': {'TO': '03/04,10,10'},
          'lower': {'TO': '51/51,18,37,2'}, 'field': {'FIELD': '22,166', 'SET': '21AA|01;075E=00;075F=01'},
          'field_move': {'FIELD': '24,168', 'SET': '21AA|01;075E=00;075F=01'},
          'grow_chests': {'TO': '19/00,5,46'}, 'grow_search': {'WAYPOINTS': '1,5;up:8'}, 'grow_foot': None,
          'grow_ahead': START, 'move_lower': 'lower', 'place_chest': {'TO': '01/02,36,29'},
          'place_shift': {'TO': '01/02,34,31'}, 'place_furniture': {'TO': '01/02,40,27'},
          'place_jar': 'grow_search', 'place_unlisted': 'grow_chests',
          'past_open': 'grow_chests', 'past_lower': 'lower', 'full_open': {'TO': '19/00,11,46'}, 'wide_open': 'full_open',
          'wideitem_open': 'full_open',
          'wide_alias': {'TO': '19/00,11,46', 'SET': '2210|40;2215|08'},
          'blocks_chest': {'TO': '36/00,68,44'},
          'new_chest': {'TO': '36/00,6,7'}, 'new_search': {'TO': '36/00,3,5'}, 'new_ahead': {'TO': '36/00,9,12'}}
# 필드 조사는 선 자리를 보므로 걷지 않고 바로 명령 창을 연다
INPUTS = {name: INPUT.removeprefix('up:8,wait:30,') for name in CASES if name.startswith('field')}
for _world in (1, 2):
    SCENES[f'field_world{_world}'] = dict(SCENES['field'], POKE=f'7E1949={_world:02X};7E075E=00;7E075F=01')
    SCENES[f'field_world{_world}_day'] = dict(SCENES['field'], POKE=f'7E1949={_world:02X}')


def command(tool, *args):
    subprocess.run([sys.executable, str(HERE / tool), *map(str, args)], check=True,
                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=90)


def environment(libdir, state, dest):
    env = os.environ.copy()
    for key in ('ADULT', 'ANYWHERE', 'BATTLE', 'FIELD', 'GROUP', 'LATESET', 'PARTY', 'POKE', 'ROMPATCH', 'SAVE',
                'SET', 'TEST', 'TO', 'WAGON', 'PRE', 'LOOP', 'WAYPOINTS', 'PEEK', 'SHOTMSG', 'CALLS', 'WW',
                'WWRANGE', 'WRAMWATCH', 'COVER', 'ACCESS', 'VMADD', 'SHOTS', 'DUMP', 'VRAMDUMP', 'BG3FONT',
                'TRACE', 'LOG', 'RWATCH', 'WWATCH', 'LATE', 'PREPARE', 'WATCH', 'INPUT', 'FLAG', 'OLD_FLAG', 'NEXT',
                'RESETAT', 'CDLEVERY', 'ACCRANGE', 'SETTLE', 'MAXF', 'SRAM'):
        env.pop(key, None)
    env.update(LIBDIR=libdir, STATE=str(state), SHOT_DIR=str(dest))
    return env


def run(mesence, rom, script, dest, env, timeout=90):
    with (dest / 'mesen.log').open('w', encoding='utf-8') as log:
        subprocess.run([str(mesence), '--testrunner', str(rom), str(script), '--Snes.DisableFrameSkipping=true'],
                       env=env, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=timeout)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def prepare(name, original, state, out, mesence, libdir, label=None):
    dest = out / ((label or name) + '-scene')
    dest.mkdir()
    env = environment(libdir, state, dest)
    setup = SCENES.get(name) or {'WAYPOINTS': '3,5;up:8'}
    if 'WAYPOINTS' not in setup:
        env.update(setup, SETTLE='120', SAVE='scene.mss', MAXF='1500')
        if name in NEWMAP:
            # 새 맵 롬은 출구 표를 옮겼으므로 dq5warp.lua 가 덮을 배 사다리 출구 자리도 옮겨 간다
            env['WARPEXIT'] = f'{warp_exit(original):X}'
        script = HERE / 'lua/dq5warp.lua'
    else:
        env.update(PREPARE='1', DRIVER=str(ROOT / 'tools/lua/walk.lua'), PRE='b:4,wait:40',
                   WAYPOINTS=setup['WAYPOINTS'], MAXF='1200', CHANGES='99')
        script = HERE / 'lua/dq5chestcheck.lua'
    run(mesence, original, script, dest, env)
    result = dest / 'scene.mss'
    require(result.is_file(), f'{name}: 장면 세이브가 없음')
    return result


def scene(name):
    value = SCENES[name]
    if value == START:
        return START
    if isinstance(value, str):
        assert not isinstance(SCENES[value], str), value
        return scene(value)
    return name if value else 'ship'


def block(wram, x, y):
    i = y * 256 + x
    return wram[0x10000 + i] | (wram[0xE000 + (i >> 3)] >> (7 - (i & 7)) & 1) << 8


def gold(wram):
    return int.from_bytes(wram[0x2019:0x201C], 'little')


def compare(name, state, original, out, mesence, libdir, start):
    changes, amount, flag, mask, old_flag, old_mask, old_reward, message = CASES[name]
    dest = out / name
    dest.mkdir()
    source, manifest, patched = dest / 'input.json', dest / 'patch.json', dest / 'patched.sfc'
    none_message = NONE_MESSAGE.get(name, 0x12C)
    if name in NEWMAP:
        original, patched = newmap_roms(out, 'blocks' if name.startswith('blocks_') else 'newmap')
        none_message = NEWMAP[name][5]
    elif name in GROW:
        patched = grow_rom(original, dest, name.split('_')[0])
    elif name in PLACE:
        place_manifest(name, original, source, manifest)
    elif name in RELOC:
        edit, at, *_, none_message = RELOC[name]
        command('dq5chestreloc.py', original, 'dump', '-o', source)
        doc = json.loads(source.read_text(encoding='utf-8'))
        edit(doc)
        source.write_text(json.dumps(doc, indent=2) + '\n', encoding='utf-8')
        places = [arg for table, place in at.items() for arg in (f'--{table}-at', place)]
        command('dq5chestreloc.py', original, 'patch', source, '-o', manifest, *places)
        command('dq5chestreloc.py', original, 'check', source, *places)
    else:
        source.write_text(json.dumps({'format': FORMAT, **changes}, indent=2) + '\n', encoding='utf-8')
        command('dq5chestwrite.py', original, 'patch', source, '-o', manifest)
        command('dq5chestwrite.py', original, 'check', source)
    if name not in GROW and name not in NEWMAP:
        command('dq5build.py', original, 'build', manifest, '-o', patched, '--ips', dest / 'patched.ips')
    results = []
    for mode, rom in (('original', original), ('patched', patched)):
        run_dir = dest / mode
        run_dir.mkdir()
        run_state = prepare(name, rom, start, out, mesence, libdir, f'{name}-{mode}') if name in OWN_SCENE else state
        env = environment(libdir, run_state, run_dir)
        env.update(INPUT=INPUTS.get(name, INPUT), FLAG=f'7E{flag:04X}', OLD_FLAG=f'7E{old_flag:04X}')
        run(mesence, rom, HERE / 'lua/dq5chestcheck.lua', run_dir, env)
        before, after = [(run_dir / f'{when}.wram').read_bytes() for when in ('before', 'after')]
        require(len(before) == len(after) == 0x20000, f'{name}/{mode}: WRAM 크기가 다름')
        trace = (run_dir / 'trace.txt').read_text(encoding='utf-8')
        rewards = [int(v, 16) for v in re.findall(r'reward .* value=([0-9A-F]+)', trace)]
        changed = mode == 'patched'
        expected = (PATCHED_REWARD.get(name, 0x100 + (amount or 0)) if changed else old_reward)
        require(rewards == ([] if expected is None else [expected]),
                f'{name}/{mode}: 실제 조회 보상 {rewards} != {expected}')
        require(gold(before) == 100 and gold(after) == 100 + (amount if changed and amount else 0),
                f'{name}/{mode}: 금화 전후가 다름')
        wanted_message = message if changed or name not in ('foot', 'grow_foot') else 0x12F
        if expected is None:
            require(f'value={none_message:04X}' in trace, f'{name}/{mode}: 찾지 못함 메시지 {none_message:X} 가 없음')
            wanted_message = ORIGINAL_KIND.get(name, message)
        require(f'value={wanted_message:04X}' in trace, f'{name}/{mode}: 조사 종류 메시지가 다름')
        if changed:
            require(after[flag] == mask, f'{name}: 새 열림 비트가 다름')
            if old_flag != flag:
                require(after[old_flag] == 0, f'{name}: 원래 열림 비트까지 바뀜')
            if name.startswith('wide'):
                require(all(after[a] == before[a] for a in WIDE_KEEP), f'{name}: 원래 상자 1·44 의 비트가 바뀜')
                require(after[WIDE_PENDING] == 0, f'{name}: 넘길 마스크 칸이 0 으로 돌아오지 않음')
                # 12:F839 에 상자 300 의 바이트 번호(28F8 - 28F3)와 넘길 마스크를 들고 한 번 들어가야 한다
                sets = re.findall(r'set .* index=([0-9A-F]+) mask=([0-9A-F]+) pend=([0-9A-F]+)', trace)
                require(sets == [(f'{flag - WIDE_BITS:02X}', '00', f'{mask:02X}')], f'{name}: 12:F839 진입 {sets}')
        else:
            require(after[old_flag] == (0 if old_reward is None else old_mask), f'{name}: 원본 열림 비트가 다름')
            if old_flag != flag:
                require(after[flag] == 0, f'{name}: 원본 롬이 새 비트를 씀')
        blocks = {f'{x},{y}': block(after, x, y) for x, y, *_ in BLOCKS.get(name, ())}
        for x, y, *values in BLOCKS.get(name, ()):
            require(blocks[f'{x},{y}'] == values[changed], f'{name}/{mode}: 블록 ({x},{y}) = {blocks[f"{x},{y}"]:X}')
        results.append({'mode': mode, 'reward': expected, 'blocks': blocks, 'gold_before': gold(before), 'gold_after': gold(after),
                        'flag': f'7E:{flag:04X}', 'flag_value': after[flag],
                        'old_flag': f'7E:{old_flag:04X}', 'old_flag_value': after[old_flag], 'passed': True})
    return {'case': name, 'runs': results, 'passed': True}


def grow_rom(original, dest, kind='past'):
    """BUILDS 의 상자 194개(past)·256개(full) 롬을 dest 에 만든다. 열림 비트를 옮긴 표를 바탕(--tables)으로 놓는다."""
    place_doc, edit, at = BUILDS[kind]
    base, source, manifest, patched = dest / 'base.json', dest / 'input.json', dest / 'patch.json', dest / 'patched.sfc'
    command('dq5chestreloc.py', original, 'dump', '-o', base)
    doc = json.loads(base.read_text(encoding='utf-8'))
    edit(doc)
    base.write_text(json.dumps(doc, indent=2) + '\n', encoding='utf-8')
    source.write_text(json.dumps(place_doc, indent=2) + '\n', encoding='utf-8')
    command('dq5chestplace.py', original, 'patch', source, '-o', manifest, '--tables', base, *at)
    command('dq5chestplace.py', original, 'check', source, '--tables', base, *at)
    command('dq5build.py', original, 'build', manifest, '-o', patched, '--ips', dest / 'patched.ips')
    return patched


def newmap_roms(out, folder='newmap'):
    return out / folder / 'control.sfc', out / folder / 'patched.sfc'


def build_blocks(original, env, out):
    """blocks_* 사례의 대조·패치 롬을 out/blocks 에 만든다. env 는 dq4environmentrom.py 출력 폴더(읽기만)."""
    dest = out / 'blocks'
    dest.mkdir()
    doc = json.loads((env / 'dq4-environment.dq5patch.json').read_text(encoding='utf-8'))
    for w in doc['writes']:
        if 'file' in w:
            w['hex'] = (env / w.pop('file')).read_bytes().hex(' ')
    base = dest / 'env.dq5patch.json'
    base.write_text(json.dumps(doc) + '\n', encoding='utf-8')
    env_rom = dest / 'env.sfc'
    command('dq5build.py', original, 'build', base, '--size', 4, '-o', env_rom)
    # 블록 표는 그 맵의 훅 표(dq5map.block_table)에서 찾고, 그 블록 바이트를 쓰는 환경 패치 쓰기만 고친다
    at = block_table(Rom(env_rom.read_bytes()), key=BLOCKS_MAP)[BLOCKS_BLOCK]
    hit = [w for w in doc['writes'] if w['at'][:2] == f'{at >> 16:02X}'
           and 0 <= (at & 0xFFFF) - int(w['at'][3:], 16) < len(bytes.fromhex(w['hex']))]
    require(len(hit) == 1, f'블록 {BLOCKS_BLOCK} 를 쓰는 환경 패치 쓰기가 하나가 아님')
    data = bytearray(bytes.fromhex(hit[0]['hex']))
    k = (at & 0xFFFF) - int(hit[0]['at'][3:], 16)
    require(data[k] & 0x3F == 0x09, f'블록 {BLOCKS_BLOCK} 가 2×2 가 아님')
    # 머리를 바꾼 블록이 목록의 다른 맵에도 놓이면 그 맵에 가짜 상자 칸이 생긴다
    env_view = Rom(env_rom.read_bytes())
    elsewhere = [key for key in block_hook(env_view)[0] if key != BLOCKS_MAP and key in set(all_maps(env_view))
                 and any(b == BLOCKS_BLOCK for _, _, b in extract(env_view, *key)['placements'])]
    require(not elsewhere, f'블록 {BLOCKS_BLOCK} 가 목록의 다른 맵 {elsewhere} 에도 놓임')
    data[k:k + 3] = BLOCKS_HEAD
    hit[0]['hex'] = data.hex(' ')
    base.write_text(json.dumps(doc) + '\n', encoding='utf-8')
    command('dq5build.py', original, 'build', base, '--size', 4, '-o', env_rom)
    (dest / 'burland.dq5map.json').write_bytes((env / 'burland.dq5map.json').read_bytes())
    newmap = dest / 'newmap.json'
    newmap.write_text(json.dumps({'format': 'dq5newmap/1', 'groups': [{'group': '36', 'entrance': {'copy': '03'}}],
                                  'maps': [{'map': '36/00', 'record': {'source': 'burland.dq5map.json'},
                                            'attrs': {'copy': '03/00'}}]}) + '\n', encoding='utf-8')
    manifests = [base, dest / 'newmap.dq5patch.json', dest / 'npc.dq5patch.json', dest / 'exits.dq5patch.json']
    # dq4groupbuild.py 와 같이 새 맵 패치는 환경 롬에서 만든다
    command('dq5newmap.py', env_rom, 'patch', newmap, '-o', manifests[1], *BLOCKS_NEWMAP_AT)
    (dest / 'npc.json').write_text(json.dumps({'format': 'dq5npcrelocate/1', 'scripts': []}) + '\n', encoding='utf-8')
    command('dq5npcrelocate.py', original, 'patch', dest / 'npc.json', '-o', manifests[2], *NEW_MAP)
    command('dq5exitreloc.py', original, 'dump', '-o', dest / 'exits.json', *NEW_MAP)
    command('dq5exitreloc.py', original, 'patch', dest / 'exits.json', '-o', manifests[3], *NEW_MAP, *BLOCKS_EXITS)
    control, patched = newmap_roms(out, 'blocks')
    command('dq5build.py', original, 'build', *manifests, '--size', 4, '-o', control)
    cells = chests(Rom(control.read_bytes()), *BLOCKS_MAP, 0)
    require([xy for _, xy, _ in cells] == BLOCKS_CELLS, f'36/00 의 상자 칸이 {BLOCKS_CELLS} 가 아님: {cells}')
    command('dq5chestreloc.py', original, 'dump', '-o', dest / 'chest.json')
    tables = json.loads((dest / 'chest.json').read_text(encoding='utf-8'))
    # 환경 패치가 레코드를 바꾼 맵은 원래 상자 칸이 없어져(15곳 모두 0개) 원래 맵 연결과 칸 수가 맞지 않는다.
    # 그 연결과 내용물을 뺀다
    view, rows, rewards, start = Rom(control.read_bytes()), [], [], 0
    for row in tables['chest_maps']:
        if len(chests(view, row['group'], row['map'], 0)) == row['count']:
            rows.append(row)
            rewards += tables['chests'][start:start + row['count']]
        start += row['count']
    tables['chest_maps'], tables['chests'] = rows, rewards
    # 뺀 연결 수에 상관없이 번호가 정해지게 맨 앞에 둔다(상자 0, 7E:2210 & 80)
    tables['chest_maps'].insert(0, {'group': BLOCKS_MAP[0], 'map': BLOCKS_MAP[1], 'count': len(BLOCKS_CELLS)})
    tables['chests'][:0] = [{'reward': 0x100 + 246 + k} for k in range(len(BLOCKS_CELLS))]
    (dest / 'chest.json').write_text(json.dumps(tables) + '\n', encoding='utf-8')
    places = (*BLOCKS_CHEST_AT, *NEW_MAP, *(arg for m in manifests for arg in ('--with-patch', m)))
    command('dq5chestreloc.py', original, 'patch', dest / 'chest.json', '-o', dest / 'chest.dq5patch.json', *places)
    command('dq5chestreloc.py', original, 'check', dest / 'chest.json', *places)
    command('dq5build.py', original, 'build', *manifests, dest / 'chest.dq5patch.json', '--size', 4, '-o', patched)


def build_newmap(original, out):
    """new_* 사례의 대조 롬과 패치 롬을 out/newmap 에 만든다. 상자 표는 원래 롬에서 --new-map·--with-patch 로 만든다."""
    dest = out / 'newmap'
    dest.mkdir()
    rom = Rom(original.read_bytes())
    src = extract(rom, 0x17, 0)
    src['placements'].append([6, 4, 384])
    record = compile_places(src, rom, False)
    record['map'] = '36/00'
    (dest / 'cabin-chest.dq5map.json').write_text(dumps(record) + '\n', encoding='utf-8')
    manifests = []

    def step(tool, name, doc, *args, check=True):
        source, manifest = dest / f'{name}.json', dest / f'{name}.dq5patch.json'
        source.write_text(json.dumps(doc, indent=1) + '\n', encoding='utf-8')
        command(tool, original, 'patch', source, '-o', manifest, *args)
        if check:
            command(tool, original, 'check', source, *args)
        return manifest

    manifests.append(step('dq5newmap.py', 'newmap', NEWMAP_DOC, *NEWMAP_AT, check=False))
    manifests.append(step('dq5npcrelocate.py', 'npc', {'format': 'dq5npcrelocate/1', 'scripts': []}, *NEW_MAP,
                          check=False))
    command('dq5exitreloc.py', original, 'dump', '-o', dest / 'exits-orig.json', *NEW_MAP)
    exits = json.loads((dest / 'exits-orig.json').read_text(encoding='utf-8'))
    manifests.append(step('dq5exitreloc.py', 'exits', exits, *NEW_MAP, *NEWMAP_EXITS))
    control, patched = newmap_roms(out)
    command('dq5build.py', original, 'build', *manifests, '-o', control)
    # dq5newmap.py 의 check 는 만든 롬에서 돈다
    command('dq5newmap.py', control, 'check', dest / 'newmap.json', *NEWMAP_AT)
    command('dq5chestreloc.py', original, 'dump', '-o', dest / 'chest-orig.json')
    tables = json.loads((dest / 'chest-orig.json').read_text(encoding='utf-8'))
    grow_newmap(tables)
    with_patch = [arg for manifest in manifests for arg in ('--with-patch', manifest)]
    chest = step('dq5chestreloc.py', 'chest', tables, *NEWMAP_CHEST_AT, *NEW_MAP, *with_patch)
    command('dq5build.py', original, 'build', *manifests, chest, '-o', patched, '--ips', dest / 'patched.ips')


def opened_tiles(before, after, span=(0x10000, 0x20000)):
    """맵 BG 버퍼(기본 7F 뱅크)에서 after 에만 있는 열린 상자 타일(아래 바이트 9E·9F) 수. 인물이 따로 움직인 자리 등 다른
    차이는 세지 않고, before 에만 있는 열린 상자 타일이 있으면 거부한다."""
    tile = {0x9E, 0x9F}
    gone = [i for i in range(*span) if before[i] in tile and after[i] not in tile]
    require(not gone, f'{0x7E + gone[0] // 0x10000 if gone else 0x7E:02X}:{gone[0] & 0xFFFF if gone else 0:04X} '
            '의 열린 상자 타일이 패치 롬에서 사라짐')
    return sum(1 for i in range(*span) if after[i] in tile and before[i] not in tile)


def place_manifest(name, original, source, manifest):
    place_doc, place_at = PLACE_INPUTS[name]
    source.write_text(json.dumps(place_doc, indent=2) + '\n', encoding='utf-8')
    command('dq5chestplace.py', original, 'patch', source, '-o', manifest, *place_at)
    command('dq5chestplace.py', original, 'check', source, *place_at)


def entry_compare(name, original, out, mesence, libdir, start):
    setup, bits = ENTRY[name]
    dest = out / name
    dest.mkdir()
    if name.startswith('new_') or name.startswith('blocks_'):
        original, patched = newmap_roms(out, 'blocks' if name.startswith('blocks_') else 'newmap')
    elif name in PLACE_INPUTS:
        patched = dest / 'patched.sfc'
        place_manifest(name, original, dest / 'input.json', dest / 'patch.json')
        command('dq5build.py', original, 'build', dest / 'patch.json', '-o', patched)
    else:
        patched = grow_rom(original, dest, name.split('_')[0])
    wram = {}
    for mode, rom in (('original', original), ('patched', patched)):
        run_dir = dest / mode
        run_dir.mkdir()
        env = environment(libdir, start, run_dir)
        env.update(setup, SET=bits, SETTLE='120', SAVE='scene.mss', MAXF='1500')
        if name.startswith('new_') or name.startswith('blocks_'):
            env['WARPEXIT'] = f'{warp_exit(rom):X}'
        run(mesence, rom, HERE / 'lua/dq5warp.lua', run_dir, env)
        require((run_dir / 'scene.mss').is_file(), f'{name}/{mode}: 장면 세이브가 없음')
        env = environment(libdir, run_dir / 'scene.mss', run_dir)
        env.update(INPUT='wait:3')
        run(mesence, rom, HERE / 'lua/dq5chestcheck.lua', run_dir, env)
        wram[mode] = (run_dir / 'before.wram').read_bytes()
        address, value = bits.split('|')
        require(wram[mode][int(address, 16)] & int(value, 16), f'{name}/{mode}: 미리 켠 비트가 꺼짐')
    # 선실 크기(16×32)의 맵은 BG 버퍼가 7E:C000~ 이다(36/00 에서 상자를 열 때 7E:C235 등이 9E·9F 로 바뀜)
    span = (0xC000, 0x10000) if name.startswith('new_') else (0xC000, 0x20000) if name.startswith('blocks_') else \
        (0x10000, 0x20000)
    words = opened_tiles(wram['original'], wram['patched'], span)
    require(words >= 2, f'{name}: 패치 롬이 열린 상자를 그리지 않음(바뀐 타일 {words}개)')
    return {'case': name, 'bits': bits, 'opened_tile_words': words, 'passed': True}


def save_compare(name, original, out, mesence, libdir, start):
    bits = SAVES[name]
    dest = out / name
    dest.mkdir()
    patched = grow_rom(original, dest, name.split('_')[0])
    talk = 'b:4,wait:40,up:3,wait:20,' + ','.join(['a:4,wait:60'] * 40)
    env = environment(libdir, start, dest)
    span = max(bits) - min(bits) + 1
    slot = SAVE_SLOT + min(bits) - 0x2000
    dumps = [f'{SAVE_FRAMES[k]}:7E{min(bits):04X}:{span}' for k in SAVE_FRAMES]
    dumps.append(f'{SAVE_FRAMES["saved"]}:{slot:06X}:{span}')
    env.update(NEXT=str(HERE / 'lua/dq5msg.lua'), POKE='7E36EB=05;7E370B=00', RESETAT=str(SAVE_FRAMES['reset'] - 10),
               PRE=talk + ',wait:300,' + ','.join(['start:4,wait:200'] * 3 + ['a:4,wait:120'] * 12),
               SET=';'.join(f'{a:04X}|{m:02X}' for a, m in bits.items()), DUMP=';'.join(dumps),
               MAXF=str(SAVE_FRAMES['loaded'] + 100))
    run(mesence, patched, HERE / 'lua/dq5cdldump.lua', dest, env, timeout=600)
    got = {}
    for line in (dest / 'msg.txt').read_text(encoding='utf-8').split('\n'):
        hit = re.match(r'(\d+) dump ([0-9A-F]{6}) (.*)', line)
        if hit:
            got[int(hit[1]), int(hit[2], 16)] = bytes.fromhex(hit[3])
    want = bytes(bits.get(min(bits) + k, 0) for k in range(span))
    wram = 0x7E0000 | min(bits)
    require(got.get((SAVE_FRAMES['saved'], slot)) == want, f'{name}: SRAM 칸 1 이 {want.hex()} 가 아님')
    require(got.get((SAVE_FRAMES['reset'], wram)) == bytes(span), f'{name}: 리셋 뒤 WRAM 이 지워지지 않음')
    require(got.get((SAVE_FRAMES['loaded'], wram)) == want, f'{name}: 불러온 뒤 열림 비트가 다름')
    return {'case': name, 'dumps': {f'{f}:{a:06X}': v.hex() for (f, a), v in sorted(got.items())},
            'passed': True}


def stale_compare(name, original, out, mesence, libdir, start):
    reward, bits, messages, buttons = STALE[name]
    dest = out / name
    dest.mkdir()
    patched = grow_rom(original, dest, name.split('_')[0])
    run_dir = dest / 'patched'
    run_dir.mkdir()
    env = environment(libdir, start, run_dir)
    env.update(TO='19/00,11,46', SET=bits, SETTLE='120', SAVE='scene.mss', MAXF='1500')
    run(mesence, patched, HERE / 'lua/dq5warp.lua', run_dir, env)
    require((run_dir / 'scene.mss').is_file(), f'{name}: 장면 세이브가 없음')
    env = environment(libdir, run_dir / 'scene.mss', run_dir)
    env.update(INPUT=f'{buttons},wait:30,{buttons}')
    run(mesence, patched, HERE / 'lua/dq5chestcheck.lua', run_dir, env)
    after = (run_dir / 'after.wram').read_bytes()
    trace = (run_dir / 'trace.txt').read_text(encoding='utf-8')
    opens = re.findall(r'open f=\d+ pend=([0-9A-F]+)', trace)
    counts = re.findall(r'count f=\d+ pend=([0-9A-F]+)', trace)
    rewards = [int(v, 16) for v in re.findall(r'reward .* value=([0-9A-F]+)', trace)]
    shown = [int(v, 16) for v in re.findall(r'message .* value=([0-9A-F]+)', trace)]
    # 잠긴 상자는 12:F43B 앞에서 끝나 보상 조회가 없다
    require(rewards == ([] if reward == 0xFFFC else [reward] * 2), f'{name}: 실제 조회 보상 {rewards}')
    require(all(shown.count(m) == 2 for m in messages), f'{name}: 상자 300 의 메시지 {messages} 가 두 번씩 없음({shown})')
    require(not re.search(r'^set ', trace, re.M), f'{name}: 12:F839 에 들어감')
    pend = f'{WIDE_FLAG[1]:02X}'
    require(opens == ['00', pend], f'{name}: 열기 훅에 들어올 때의 291B {opens}')
    require(counts == ['00', '00'], f'{name}: 2A:F224 를 부를 때의 291B {counts}')
    require((after[WIDE_FLAG[0]], after[WIDE_PENDING]) == (0, WIDE_FLAG[1]), f'{name}: 28F8·291B 가 다름')
    return {'case': name, 'opens': opens, 'counts': counts, 'messages': [f'{m:X}' for m in shown], 'passed': True}


def warp(rom, state, dest, to, mesence, libdir, bits=''):
    env = environment(libdir, state, dest)
    env.update(TO=to, SETTLE='120', SAVE='scene.mss', MAXF='2500')
    if bits:
        env['SET'] = bits
    run(mesence, rom, HERE / 'lua/dq5warp.lua', dest, env)
    require((dest / 'scene.mss').is_file(), f'{dest.name}: {to} 장면 세이브가 없음')
    return dest / 'scene.mss'


def open_chest(rom, state, dest, buttons, mesence, libdir, flag=None, sram=False, reset=None):
    """state 에서 buttons 를 눌러 dq5chestcheck.lua 로 열고 (전 WRAM, 뒤 WRAM, 기록). 끝 세이브는 dest/end.mss.
    sram 이면 끝의 70:0000~1FFF 를 dest/after.sram 에 남기고, reset 프레임에 리셋한다."""
    env = environment(libdir, state, dest)
    env.update(INPUT=buttons, SAVE='end.mss')
    if reset is not None:
        env['RESETAT'] = str(reset)
    if flag is not None:
        env['FLAG'] = f'7E{flag:04X}'
    if sram:
        env['SRAM'] = '1'
    run(mesence, rom, HERE / 'lua/dq5chestcheck.lua', dest, env, timeout=600)
    require((dest / 'end.mss').is_file(), f'{dest.name}: 끝 세이브가 없음')
    return [(dest / f'{when}.wram').read_bytes() for when in ('before', 'after')] + [
        (dest / 'trace.txt').read_text(encoding='utf-8')]


def sets_in(trace):
    return re.findall(r'set .* index=([0-9A-F]+) mask=([0-9A-F]+) pend=([0-9A-F]+) ret=([0-9A-F]+)', trace)


def saved_diff(before, after):
    return sorted(a for a in range(0x2000, 0x2AA0) if before[a] != after[a])


def number_compare(name, original, out, mesence, libdir, start):
    n = NUMBER[name]
    flag, mask = number_bit(n)
    alias = (0x2210 + ((n & 0xFF) >> 3), 0x80 >> (n & 7))
    dest = out / name
    dest.mkdir()
    patched = grow_rom(original, dest, f'widenum{n}')
    steps = {k: dest / k for k in ('scene', 'open', 'back', 'look')}
    for d in steps.values():
        d.mkdir()
    scene_state = warp(patched, start, steps['scene'], '19/00,11,46', mesence, libdir, f'{alias[0]:04X}|{alias[1]:02X}')
    before, after, trace = open_chest(patched, scene_state, steps['open'], INPUT, mesence, libdir, flag)
    rewards = [int(v, 16) for v in re.findall(r'reward .* value=([0-9A-F]+)', trace)]
    require(rewards == [0x100 + n], f'{name}: 실제 조회 보상 {rewards}')
    require(gold(after) == 100 + n, f'{name}: 금화 {gold(after)}')
    require(after[flag] == mask and after[WIDE_PENDING] == 0, f'{name}: 7E:{flag:04X} = {after[flag]:02X}, '
            f'291B = {after[WIDE_PENDING]:02X}')
    require(before[alias[0]] & alias[1] and after[alias[0]] == before[alias[0]], f'{name}: 8비트 번호의 비트가 바뀜')
    # 기록 범위에서 바뀐 것은 금화와 그 상자의 비트뿐이어야 한다
    changed = saved_diff(before, after)
    coins = {0x2019 + k for k in range(3) if (100 >> 8 * k) & 0xFF != (100 + n >> 8 * k) & 0xFF}
    require(changed == sorted(coins | {flag}), f'{name}: 기록 범위에서 바뀐 바이트 {[f"{a:04X}" for a in changed]}')
    sets = sets_in(trace)
    require([v[:3] for v in sets] == [(f'{flag - WIDE_BITS:02X}', '00', f'{mask:02X}')], f'{name}: 12:F839 진입 {sets}')
    # 다시 들어올 때 1F:FC50 이 상자 칸을 열린 상자 타일로 그리는지 본다. (11,46) 은 가게 계산대 안이라 걸어 나갈 수 없으므로
    # 연 뒤의 그 바이트를 선실에서 켜고 19/00 에 들어간다(wide_entry 와 같은 길)
    back = warp(patched, start, steps['back'], '19/00,11,46', mesence, libdir,
                f'{flag:04X}={after[flag]:02X};{alias[0]:04X}|{alias[1]:02X}')
    seen, _, _ = open_chest(patched, back, steps['look'], 'wait:3', mesence, libdir)
    require(seen[flag] == mask, f'{name}: 다시 들어온 뒤 비트가 꺼짐')
    words = opened_tiles(before, seen)
    require(words >= 2, f'{name}: 다시 들어왔을 때 열린 상자 타일 {words}개')
    return {'case': name, 'chest': n, 'flag': f'7E:{flag:04X}', 'mask': f'{mask:02X}', 'changed': [f'{a:04X}' for a in changed],
            'sets': sets, 'opened_tile_words': words, 'passed': True}


def monster_compare(name, original, out, mesence, libdir, start):
    dest = out / name
    dest.mkdir()
    kind = name.split('_')[0]
    reward, group, slot = MON_KINDS[kind]
    patched = grow_rom(original, dest, kind)
    win = name.endswith('_win')
    if win:
        data = bytearray(patched.read_bytes())
        at, old, new = slot
        require(data[at] == old, f'{name}: 무리 {group:02X} 의 몬스터 칸이 {old:02X} 가 아님')
        data[at] = new
        patched.write_bytes(data)
    steps = {k: dest / k for k in ('scene', 'open', 'load', 'next', 'reopen')}
    for d in steps.values():
        d.mkdir()
    scene_state = warp(patched, start, steps['scene'], '19/00,11,46', mesence, libdir)
    before, after, trace = open_chest(patched, scene_state, steps['open'], MONSTER[name], mesence, libdir, WIDE_FLAG[0],
                                      sram=not win)
    require(re.findall(r'reward .* value=([0-9A-F]+)', trace) == [f'{reward:04X}'], f'{name}: 보상 조회가 {reward:04X} 하나가 아님')
    require(re.findall(r'battle f=\d+ group=([0-9A-F]+)', trace) == [f'{group:02X}'], f'{name}: 전투 무리가 다름')
    backs = re.findall(r'back f=\d+ pend=([0-9A-F]+)', trace)
    sets = sets_in(trace)
    result = {'case': name, 'back': backs, 'sets': sets, 'gold': [gold(before), gold(after)],
              'after': {f'{a:04X}': f'{after[a]:02X}' for a in (WIDE_FLAG[0], WIDE_PENDING, 0x1E80, 0x1E81)}}
    if win:
        require(backs == [f'{WIDE_FLAG[1]:02X}'], f'{name}: 12:F4A8 로 돌아온 기록 {backs}')
        require(sets == [('05', '00', f'{WIDE_FLAG[1]:02X}', 'F4AA')], f'{name}: 12:F839 진입 {sets}')
        require((after[WIDE_FLAG[0]], after[WIDE_PENDING]) == (WIDE_FLAG[1], 0), f'{name}: 28F8·291B {result["after"]}')
        return result | {'passed': True}
    # 전멸하면 12:F4A8 로 돌아오지 않아 비트는 꺼진 채이고 넘길 마스크가 남는다. 금화는 반이 된다
    require(not backs and not sets, f'{name}: 전멸 뒤 12:F4A8·12:F839 에 들어감 {backs} {sets}')
    require(gold(after) == gold(before) // 2, f'{name}: 금화 {gold(before)} → {gold(after)}')
    require((after[WIDE_FLAG[0]], after[WIDE_PENDING], after[0x1E80], after[0x1E81]) == (0, WIDE_FLAG[1], 5, 0),
            f'{name}: 전멸 뒤 {result["after"]}')
    # 되살아난 뒤 교회에서 칸 1 에 기록했다. 기록 범위 7E:2000~ 이 70:0012~ 에 그대로 들어간다(금화로 그 칸인지 본다)
    sram = (steps['open'] / 'after.sram').read_bytes()
    slot = SAVE_SLOT & 0xFFFF
    require(sram[slot + 0x19:slot + 0x1C] == after[0x2019:0x201C], f'{name}: SRAM 칸 1 의 금화가 WRAM 과 다름')
    require((sram[slot + WIDE_FLAG[0] - 0x2000], sram[slot + WIDE_PENDING - 0x2000]) == (0, WIDE_FLAG[1]),
            f'{name}: SRAM 칸 1 의 28F8·291B')
    result['sram'] = {f'{SAVE_SLOT + a - 0x2000:06X}': f'{sram[slot + a - 0x2000]:02X}' for a in (WIDE_FLAG[0], WIDE_PENDING)}
    # 리셋하고 그 기록을 불러온 뒤에 다른 상자를 연다. 첫 프레임에 금화를 100 으로 둔 WRAM 은 리셋으로 사라진다
    _, loaded, _ = open_chest(patched, steps['open'] / 'end.mss', steps['load'], LOAD_INPUT, mesence, libdir,
                              reset=LOAD_RESET)
    require((loaded[0x00BC], loaded[0x00BD], gold(loaded)) == (0x19, 0, gold(after)), f'{name}: 불러온 맵·금화가 다름')
    require((loaded[WIDE_FLAG[0]], loaded[WIDE_PENDING]) == (0, WIDE_FLAG[1]), f'{name}: 불러온 뒤 28F8·291B')
    state = warp(patched, steps['load'] / 'end.mss', steps['next'], '01/02,34,31', mesence, libdir)
    _, again, trace = open_chest(patched, state, steps['reopen'], INPUT, mesence, libdir)
    opens = re.findall(r'open f=\d+ pend=([0-9A-F]+)', trace)
    counts = re.findall(r'count f=\d+ pend=([0-9A-F]+)', trace)
    reopen_sets = sets_in(trace)
    require(opens == [f'{WIDE_FLAG[1]:02X}'] and counts == ['00'], f'{name}: 다음 열기의 291B {opens} → {counts}')
    # 01/02 의 상자 2 는 256 미만이라 $1E81 에 마스크를 두고 원래 길로 켠다
    require(len(reopen_sets) == 1 and reopen_sets[0][1] != '00' and reopen_sets[0][2] == '00',
            f'{name}: 다음 열기의 12:F839 {reopen_sets}')
    require(again[WIDE_PENDING] == 0 and again[WIDE_FLAG[0]] == 0, f'{name}: 다음 열기 뒤 291B {again[WIDE_PENDING]:02X}')
    return result | {'reopen': {'opens': opens, 'counts': counts, 'sets': reopen_sets}, 'passed': True}


def leave_compare(name, original, out, mesence, libdir, start):
    n, to, flag, mask, amount = EDGE
    dest = out / name
    dest.mkdir()
    patched = grow_rom(original, dest, 'widenum575')
    steps = {k: dest / k for k in ('scene', 'open', 'away', 'back', 'look')}
    for d in steps.values():
        d.mkdir()
    scene_state = warp(patched, start, steps['scene'], to, mesence, libdir)
    before, after, trace = open_chest(patched, scene_state, steps['open'], INPUT, mesence, libdir, flag)
    rewards = [int(v, 16) for v in re.findall(r'reward .* value=([0-9A-F]+)', trace)]
    require(rewards == [0x100 + amount] and gold(after) == 100 + amount, f'{name}: 보상 {rewards}, 금화 {gold(after)}')
    require((after[flag], after[WIDE_PENDING]) == (mask, 0), f'{name}: 7E:{flag:04X} = {after[flag]:02X}')
    require([v[:3] for v in sets_in(trace)] == [(f'{flag - WIDE_BITS:02X}', '00', f'{mask:02X}')],
            f'{name}: 12:F839 진입 {sets_in(trace)}')
    # 연 자리에서 걸어 나가 다른 맵에 들어갔다가 다시 걸어 들어온다. 그동안 WRAM 은 게임이 연 그대로다
    away = warp(patched, steps['open'] / 'end.mss', steps['away'], AWAY, mesence, libdir)
    back = warp(patched, away, steps['back'], to, mesence, libdir)
    seen, _, _ = open_chest(patched, back, steps['look'], 'wait:3', mesence, libdir)
    require(seen[flag] == mask, f'{name}: 돌아온 뒤 비트가 꺼짐')
    words = opened_tiles(before, seen)
    require(words >= 2, f'{name}: 돌아왔을 때 열린 상자 타일 {words}개')
    return {'case': name, 'chest': n, 'flag': f'7E:{flag:04X}', 'opened_tile_words': words, 'passed': True}


def other_compare(name, original, out, mesence, libdir, start):
    kind, stale = OTHER[name]
    reward, bits, messages, buttons = STALE[stale]
    _, to, flag, mask, _ = EDGE
    next_to, next_reward = EDGE_NEXT
    dest = out / name
    dest.mkdir()
    patched = grow_rom(original, dest, kind)
    steps = {k: dest / k for k in ('scene', 'open', 'away', 'next', 'reopen')}
    for d in steps.values():
        d.mkdir()
    scene_state = warp(patched, start, steps['scene'], to, mesence, libdir, bits)
    _, after, trace = open_chest(patched, scene_state, steps['open'], buttons, mesence, libdir, flag)
    rewards = [int(v, 16) for v in re.findall(r'reward .* value=([0-9A-F]+)', trace)]
    shown = [int(v, 16) for v in re.findall(r'message .* value=([0-9A-F]+)', trace)]
    require(rewards == ([] if reward == 0xFFFC else [reward]), f'{name}: 실제 조회 보상 {rewards}')
    require(all(m in shown for m in messages), f'{name}: 상자 256 의 메시지 {messages} 가 없음({shown})')
    require(not sets_in(trace), f'{name}: 12:F839 에 들어감')
    require((after[flag], after[WIDE_PENDING]) == (0, mask), f'{name}: 첫 열기 뒤 28F3·291B 가 다름')
    away = warp(patched, steps['open'] / 'end.mss', steps['away'], AWAY, mesence, libdir)
    state = warp(patched, away, steps['next'], next_to, mesence, libdir)
    before, again, trace = open_chest(patched, state, steps['reopen'], INPUT, mesence, libdir)
    opens = re.findall(r'open f=\d+ pend=([0-9A-F]+)', trace)
    counts = re.findall(r'count f=\d+ pend=([0-9A-F]+)', trace)
    sets = sets_in(trace)
    rewards = [int(v, 16) for v in re.findall(r'reward .* value=([0-9A-F]+)', trace)]
    require(before[WIDE_PENDING] == mask, f'{name}: 다른 상자 앞에서 291B = {before[WIDE_PENDING]:02X}')
    require(opens == [f'{mask:02X}'] and counts == ['00'], f'{name}: 다른 상자를 열 때의 291B {opens} → {counts}')
    require(rewards == [next_reward], f'{name}: 다른 상자의 보상 {rewards}')
    if bits:
        # 가방이 그대로 가득하므로 다른 상자의 물건도 받지 못한다. 256 미만이라 291B 에는 아무것도 남지 않는다
        require(not sets and (again[flag], again[WIDE_PENDING]) == (0, 0), f'{name}: 다른 상자 {sets} 291B {again[WIDE_PENDING]:02X}')
        return {'case': name, 'opens': opens, 'counts': counts, 'sets': sets, 'passed': True}
    # 256 미만은 원래 길로 $1E80 = 80 | 바이트 번호, $1E81 = 마스크를 두고 켠다
    require(len(sets) == 1 and int(sets[0][0], 16) >= 0x80 and sets[0][1] != '00' and sets[0][2] == '00',
            f'{name}: 12:F839 진입 {sets}')
    bit = 0x2190 + int(sets[0][0], 16), int(sets[0][1], 16)
    require((again[bit[0]] & bit[1], again[flag], again[WIDE_PENDING]) == (bit[1], 0, 0),
            f'{name}: 다른 상자를 연 뒤 {again[bit[0]]:02X} {again[flag]:02X} {again[WIDE_PENDING]:02X}')
    return {'case': name, 'opens': opens, 'counts': counts, 'sets': sets, 'bit': f'7E:{bit[0]:04X} & {bit[1]:02X}',
            'passed': True}


# --audit 장면: (dq5warp.lua 변수, 미리 켤 비트). 상자 방 01/02 에 들어가 상자를 열고(닫힘·열림 둘 다),
# 그룹 50 이상 맵 51/51 에서 아래층 상자를 열고, 54/52 의 BRK 0B·0D 갈래(1F:FCCA)까지 지난다
AUDIT = {'chest': ({'TO': '01/02,34,31', 'TEST': INPUT}, ''),
         'chest-open': ({'TO': '01/02,34,31', 'TEST': INPUT}, '2210|FF;2211|FF;2212|FF'),
         'lower': ({'TO': '51/51,18,37,2', 'TEST': INPUT}, ''),
         'lower-open': ({'TO': '51/51,18,37,2', 'TEST': INPUT}, '2228|FF;2229|FF;222A|FF'),
         'lower-5452': ({'TO': '54/52,28,23,2'}, ''), 'lower-5452-flag': ({'TO': '54/52,28,23,2'}, '21E5|20')}
# DB 를 1E 로 둔 PLB 다음 명령(1F:FD18·FDD0·FC7B, 25:FAB0)
AUDIT_OPEN = '1FFD1E,1FFDDB,1FFC81,25FAB8'


def audit(original, out, mesence, libdir, start):
    """DB 창에서 실행한 명령 가운데 DB 로 롬에 닿는 명령이 표 읽기 자리(ABS)뿐인지 본다."""
    data, mapper, executed = original.read_bytes(), LoROM(), {}
    for name, (setup, bits) in AUDIT.items():
        dest = out / f'audit-{name}'
        dest.mkdir()
        env = environment(libdir, start, dest)
        env.update(setup, DRIVER=str(HERE / 'lua/dq5warp.lua'), DBWIN=AUDIT_OPEN, MAXF='2500' if 'TEST' in setup else '900')
        if bits:
            env['SET'] = bits
        run(mesence, original, HERE / 'lua/dq5dbread.lua', dest, env, timeout=300)
        for line in (dest / 'dbwin.txt').read_text(encoding='utf-8').split('\n'):
            if line:
                pc, p, count = line.split()
                key = int(pc, 16), int(p, 16)
                executed[key] = executed.get(key, 0) + int(count)
    sites = {site for name in ('chest_maps', 'lower') for site, _ in ABS[name]}
    rom_access, wram_access, unknown = [], [], []
    for (pc, p), count in sorted(executed.items()):
        op = decode(data, pc, m8=bool(p & 0x20), x8=bool(p & 0x10), mapper=mapper)[0][22:]
        hit = DB_ABS.match(op)
        if DB_INDIRECT.match(op):
            unknown.append(f'{pc >> 16:02X}:{pc & 0xFFFF:04X} {op}')
        elif hit and int(hit[1], 16) >= 0x8000:
            rom_access.append(pc)
        elif hit:
            wram_access.append(f'{pc >> 16:02X}:{pc & 0xFFFF:04X} {op}')
    require(executed, 'DB 창에서 실행한 명령이 없음')
    require(not unknown, f'DB 로 간접 주소를 읽는 명령: {unknown}')
    stray = sorted(f'{pc >> 16:02X}:{pc & 0xFFFF:04X}' for pc in set(rom_access) - sites)
    require(not stray, f'표 읽기 밖에서 DB 로 롬에 닿는 명령: {stray}')
    banks = sorted({f'{pc >> 16:02X}' for pc, _ in executed})
    print(f'DB 창 명령 {len(executed)}개(뱅크 {" ".join(banks)}), DB 로 롬을 읽는 명령 {len(set(rom_access))}개는 모두 표 자리, '
          f'WRAM abs {len(wram_access)}개: {", ".join(wram_access)}')
    return {'instructions': len(executed), 'table_sites': len(set(rom_access)), 'wram_abs': wram_access}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('rom', type=Path)
    p.add_argument('--state', type=Path, required=True)
    p.add_argument('--out', type=Path, default=Path('work/chest-check'))
    p.add_argument('--mesence', default=os.environ.get('MESENCE'))
    p.add_argument('--case', choices=ALL, action='append', help='이 사례만(여러 번 줄 수 있음)')
    p.add_argument('--audit', action='store_true', help='원본 롬의 DB 창 감사만 함')
    p.add_argument('--env', type=Path, help='blocks_* 사례의 DQ4 환경 패치 폴더(dq4environmentrom.py --out)')
    args = p.parse_args()
    if not args.mesence:
        p.error('MESENCE 또는 --mesence가 필요함')
    try:
        original, state, mesence = args.rom.resolve(), args.state.resolve(), Path(args.mesence).resolve()
        for path in (original, state, mesence):
            require(path.is_file(), f'파일 없음: {path}')
        args.out.mkdir(parents=True, exist_ok=True)
        out = Path(tempfile.mkdtemp(prefix='run-', dir=args.out.resolve()))
        libdir = subprocess.check_output(['krpatch', 'sfc', 'lua'], text=True, timeout=30).strip()
        print(f'출력 {out}', flush=True)
        if args.audit:
            result = audit(original, out, mesence, libdir, state)
            (out / 'audit.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
            return 0
        # blocks_* 는 --env 가 있을 때만 돈다
        cases = list(dict.fromkeys(args.case or [n for n in ALL if not n.startswith('blocks_') or args.env]))
        if any(name.startswith('new_') for name in cases):
            build_newmap(original, out)
        if any(name.startswith('blocks_') for name in cases):
            require(args.env and (args.env / 'dq4-environment.dq5patch.json').is_file(),
                    'blocks_* 사례는 --env 에 dq4environmentrom.py 출력 폴더가 필요함')
            build_blocks(original, args.env.resolve(), out)
        scenes = sorted({scene(name) for name in cases if name in CASES and name not in OWN_SCENE} - {START})
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            futures = {name: pool.submit(prepare, name, original, state, out, mesence, libdir)
                       for name in scenes}
            states = {name: future.result() for name, future in futures.items()} | {START: state}
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            results = list(pool.map(lambda name: compare(name, states.get(scene(name)), original, out, mesence, libdir,
                                                         state) if name in CASES else
                                    entry_compare(name, original, out, mesence, libdir, state) if name in ENTRY else
                                    stale_compare(name, original, out, mesence, libdir, state) if name in STALE else
                                    number_compare(name, original, out, mesence, libdir, state) if name in NUMBER else
                                    monster_compare(name, original, out, mesence, libdir, state) if name in MONSTER else
                                    leave_compare(name, original, out, mesence, libdir, state) if name in LEAVE else
                                    other_compare(name, original, out, mesence, libdir, state) if name in OTHER else
                                    save_compare(name, original, out, mesence, libdir, state), cases))
        (out / 'results.json').write_text(json.dumps(results, indent=2) + '\n', encoding='utf-8')
        pairs = [name for name in cases if name not in SAVES and name not in STALE and name not in NUMBER
                 and name not in MONSTER and name not in LEAVE and name not in OTHER]
        saves = sum(name in SAVES for name in cases)
        stale = sum(name in STALE for name in cases)
        numbers = sum(name in NUMBER for name in cases)
        monsters = sum(name in MONSTER for name in cases)
        leaves = sum(name in LEAVE for name in cases)
        others = sum(name in OTHER for name in cases)
        print((f'{len(pairs)}쌍/{2 * len(pairs)}실행 통과: 보상·금화·새 열림 비트·기존 비트 보존·들어갈 때 열린 상자'
               if pairs else '통과') + (f', 기록·불러오기 {saves}실행 통과' if saves else '')
              + (f', 넘길 마스크 지우기 {stale}실행 통과' if stale else '')
              + (f', 상자 번호 {numbers}개 열기·다시 들어오기 통과' if numbers else '')
              + (f', 상자 몬스터 {monsters}사례 통과' if monsters else '')
              + (f', 떠났다 돌아오기 {leaves}사례 통과' if leaves else '')
              + (f', 남은 마스크 뒤 다른 상자 {others}사례 통과' if others else ''))
        return 0
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        print(f'오류: {error}', file=sys.stderr)
        if isinstance(error, subprocess.CalledProcessError) and error.stdout:
            print(error.stdout, file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
