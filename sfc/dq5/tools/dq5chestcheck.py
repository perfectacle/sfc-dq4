"""상자·서랍·발밑·두 칸 앞·아래층 상자·필드 보상 쓰기를 원본/패치 롬의 실제 조사 명령으로 비교한다.

sfc/dq5/docs/dq5-map-format.md의 보물상자 형식. 입력 JSON→dq5patch→롬/IPS를 만들고,
선실에서 걸어가거나 dq5warp.lua 로 그 자리에 내려선 뒤 컨트롤러로 조사한다. 금화·조회된 보상·열림 비트·
기존 비트 보존을 확인한다. 원본 롬/세이브는 읽기만 하고 --out 아래 새 폴더에 저장한다.
past_* 사례는 상자 194개·상자 맵 연결과 아래층 상자 표를 뱅크 3F 로 옮긴 롬에서 열기·들어갈 때 그리기·기록과 불러오기를 본다.
wide_* 사례는 상자 번호 16비트 훅(dq5chestreloc.py --wide-at)으로 상자를 301개 둔 롬에서 상자 300 을 같은 셋으로 본다.
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
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

from kr_patch.sfc.dis65816 import decode
from kr_patch.sfc.mapper import LoROM

from dq5chestreloc import ABS, WIDE_PENDING
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


BUILDS = {'past': (GROW_DOC, grow_base, GROW_AT), 'full': (FULL_DOC, full_base, FULL_AT),
          'wide': (WIDE_DOC, wide_base, WIDE_AT)}
GROW = {'past_open': (987, 0x2228, 0x80, 0x2228, 0x80, None, 0x131),
        # 아래층 상자 51/51 (19,35). 원본은 2228 & 08, 패치는 옮긴 표의 2229 & 08 을 켠다
        'past_lower': (None, 0x2229, 0x08, 0x2228, 0x08, 0xB1, 0x131),
        'full_open': (255, 0x222F, 0x01, 0x222F, 0x01, None, 0x131),
        'wide_open': (300, *WIDE_FLAG, *WIDE_FLAG, None, 0x131),
        # 상자 1·44 를 연 채로 상자 300 을 연다. 8비트로 읽었다면 300 이 44 로 보여 이미 열린 상자가 된다
        'wide_alias': (300, *WIDE_FLAG, *WIDE_FLAG, None, 0x131)}
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
PATCHED_REWARD = {'place_shift': 0x33, 'past_lower': 0xB1, 'field_world1_day': None, 'field_world2_day': None}
ORIGINAL_KIND.update(past_open=0x12B, full_open=0x12B, wide_open=0x12B, wide_alias=0x12B)
# 맵에 들어갈 때 열린 상자를 그리는 사례: (장면, 미리 켤 비트). 원본은 그 비트를 상자로 보지 않아 그대로 두고,
# 패치는 1F:FC50 이 옮긴 표에서 그 상자를 찾아 열린 상자 타일(9E·9F)로 바꾼다
ENTRY = {'past_entry': ({'TO': '19/00,5,46'}, '2228|80'), 'past_entry_lower': ({'TO': '51/51,18,37,2'}, '2229|08'),
         'full_entry': ({'TO': '19/00,11,46'}, '222F|01'), 'wide_entry': ({'TO': '19/00,11,46'}, '28F8|08'), 'new_entry': ({'TO': '36/00,6,7'}, '2224|40'),
         'place_unlisted_entry': ({'TO': '19/00,5,46'}, '2224|08'), 'blocks_entry': ({'TO': '36/00,68,44'}, '2210|80')}
# 열림 비트를 켠 채 교회에 기록하고 리셋해 불러오는 사례(dq5cdlsweep.py 의 church-save-load 와 같은 입력).
# SRAM 칸 1 은 7E:2000~ 을 70:0012~ 에 그대로 담는다(25:83CE)
SAVES = {'past_save': {0x2228: 0x80, 0x2229: 0x08}, 'wide_save': {WIDE_FLAG[0]: WIDE_FLAG[1]}}
SAVE_SLOT = 0x700012
SAVE_FRAMES = {'saved': 2600, 'reset': 2710, 'loaded': 6400}
ALL = [*CASES, *ENTRY, *SAVES]
# 조사 뒤 세계 지도 버퍼의 블록(블록 좌표 x, y, 원본, 패치). 밤이라 빛 블록 A7 이 놓인 자리를 본다
# 필드에 들어갈 때 빛 블록을 놓으므로, 장면도 그 롬으로 만들어야 하는 사례
OWN_SCENE = {'field_move', 'place_chest', 'place_shift', 'place_furniture', *NEWMAP}
BLOCKS = {'field_move': ((11, 83, 0xA7, 0xCA), (12, 84, 0x178, 0xA7)),
          # 원래 보상(물건)을 집으면 빛 블록이 세계 0 의 지도 블록 CA 로 돌아간다(세계 1·2 지도의 그 자리는 00).
          # 금화로 바꾸면 돌아가지 않는다. 01:A055 는 열림 플래그가 켜져 있으면 빛을 건드리지 않는다
          'field': ((11, 83, 0xCA, 0xA7),), 'field_world1': ((11, 83, 0xCA, 0xA7),), 'field_world2': ((11, 83, 0xCA, 0xA7),),
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
                'RESETAT', 'CDLEVERY', 'ACCRANGE', 'SETTLE', 'MAXF'):
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
            if name.startswith('wide_'):
                require(all(after[a] == before[a] for a in WIDE_KEEP), f'{name}: 원래 상자 1·44 의 비트가 바뀜')
                require(after[WIDE_PENDING] == 0, f'{name}: 넘길 마스크 칸이 0 으로 돌아오지 않음')
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
                                    save_compare(name, original, out, mesence, libdir, state), cases))
        (out / 'results.json').write_text(json.dumps(results, indent=2) + '\n', encoding='utf-8')
        pairs = [name for name in cases if name not in SAVES]
        saves = len(cases) - len(pairs)
        print(f'{len(pairs)}쌍/{2 * len(pairs)}실행 통과: 보상·금화·새 열림 비트·기존 비트 보존·들어갈 때 열린 상자'
              + (f', 기록·불러오기 {saves}실행 통과' if saves else ''))
        return 0
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        print(f'오류: {error}', file=sys.stderr)
        if isinstance(error, subprocess.CalledProcessError) and error.stdout:
            print(error.stdout, file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
