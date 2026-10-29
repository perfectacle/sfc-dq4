"""Place original environment art on the FC maps' measured block grids."""

import hashlib
import sys
from collections import Counter
from pathlib import Path

from PIL import Image
from kr_patch.fc import ines

FC_TOOLS = Path(__file__).resolve().parents[3] / "fc" / "dq4" / "tools"
if str(FC_TOOLS) not in sys.path:
    sys.path.insert(0, str(FC_TOOLS))

import dq4block  # noqa: E402
import dq4field  # noqa: E402
from dq4environmentart import palette_variant  # noqa: E402


# IDs address the eight-column FC block sheets, not the art sheet's order.
BLOCK_ART = {
    0x0A: {
        0x00: ("grass", "잔디"),
        0x01: ("water0", "물"),
        0x02: ("tree16", "나무"),
        0x03: ("bush", "풀밭"),
        0x04: ("flowers", "꽃"),
        0x05: ("red_paving", "붉은 바닥・실내와 길 공용"),
        0x06: ("stone_wall_top", "석벽 윗줄"),
        0x07: ("stone_wall", "석벽 가운데"),
        0x08: ("castle_wall", "성 몸체 석벽"),
        0x09: ("tower_cap_left", "성탑 상단 왼쪽"),
        0x0A: ("tower_cap_right", "성탑 상단 오른쪽"),
        0x0B: ("tower_left", "성탑 벽 왼쪽"),
        0x0C: ("tower_right", "성탑 벽 오른쪽"),
        0x0D: ("gold_door16", "문"),
        0x0E: ("sign_church", "교회 표식"),
        0x0F: ("sign_inn", "여관 표식"),
        0x10: ("gate_top_left", "성문 상단 왼쪽"),
        0x11: ("gate_top_right", "성문 상단 오른쪽"),
        0x12: ("chest_closed", "보물상자"),
        0x13: ("dirt", "모래 바닥"),
        0x14: ("gate_bottom_left", "성문 하단 왼쪽"),
        0x15: ("gate_bottom_right", "성문 하단 오른쪽"),
        0x16: ("stairs_down", "아래 계단"),
        0x17: ("statue", "석상"),
        0x18: ("counter", "카운터"),
        0x19: ("stairs_up", "위 계단"),
        0x1A: ("well", "우물"),
        0x1B: ("chair", "의자"),
        0x1C: ("bed_left", "침대 발치"),
        0x1D: ("bed_right", "침대 머리맡"),
        0x1E: ("window16", "창문"),
        0x1F: ("round_table", "둥근 탁자"),
    },
    0x0E: {
        0x00: ("grass", "잔디"),
        0x01: ("water0", "물"),
        0x02: ("tree16", "나무"),
        0x03: ("flowers", "꽃"),
        0x04: ("carpet", "실내 바닥"),
        0x05: ("cobble", "길"),
        0x06: ("stone_wall_top", "벽 윗줄"),
        0x07: ("stone_wall", "벽 가운데"),
        0x08: ("stone_wall", "벽 아랫줄"),
        0x09: ("gold_door16", "문"),
        0x0A: ("sign_church", "교회 표식"),
        0x0B: ("sign_weapon", "무기점 표식"),
        0x0C: ("sign_armour", "방어구점 표식"),
        0x0D: ("sign_shop", "도구점 표식・장화 모양 해석은 미확인"),
        0x0E: ("sign_inn", "여관 표식"),
        0x0F: ("counter", "카운터"),
        0x10: ("chest_closed", "보물상자"),
        0x11: ("chest_closed", "보물상자"),
        0x12: ("stairs_up", "위 계단"),
        0x13: ("stairs_down", "아래 계단"),
        0x14: ("washbasin", "수반 모양 장식・뜻 미확인"),
        0x15: ("bed_left", "침대 발치"),
        0x16: ("bed_right", "침대 머리맡"),
        0x17: ("round_table", "둥근 탁자"),
        0x18: ("chair", "의자"),
        0x19: ("barrel", "둥근 목재 가구"),
        0x1A: ("wardrobe", "옷장"),
        0x1B: ("washbasin", "수반 모양 장식・뜻 미확인"),
        0x1C: ("chimney", "원통형 석재 장식・뜻 미확인"),
        0x1D: ("statue", "석재 장식"),
        0x1E: ("dark_void", "빈 검정 영역"),
        0x1F: ("dirt", "모래 바닥"),
    },
}

# Blocks of the other sheets whose graphics are not in BLOCK_ART. Each entry names
# the first sheet block showing that graphic; every block with the same CHR and colours follows it.
EXAMPLES = {
    (0x03, 0x02): ("wood_floor", "나무 바닥"),
    (0x03, 0x06): ("gold_door16", "문(とうぞくのカギ)"),
    (0x03, 0x07): ("iron_door", "쇠창살 문(さいごのカギ)"),
    (0x03, 0x08): ("red_paving_cracked", "갈라진 붉은 바닥"),
    (0x03, 0x0E): ("cloth_table", "천 덮인 탁자"),
    (0x03, 0x0F): ("counter", "카운터 끝"),
    (0x03, 0x10): ("potted_plant", "화분"),
    (0x03, 0x14): ("chair", "등받이 의자"),
    (0x03, 0x15): ("pot", "항아리"),
    (0x03, 0x18): ("counter", "카운터"),
    (0x03, 0x19): ("bookshelf", "책장"),
    (0x03, 0x1A): ("sky", "하늘・떨어지는 칸"),
    (0x03, 0x1B): ("gold_door16", "문(まほうのカギ)"),
    (0x03, 0x1E): ("brick_paving", "벽돌 바닥"),
    (0x04, 0x06): ("cabin_slats_left", "통나무집 창살 왼쪽"),
    (0x04, 0x07): ("cabin_slats", "통나무집 창살"),
    (0x04, 0x08): ("cabin_planks_right", "통나무집 벽 오른쪽 기둥"),
    (0x04, 0x09): ("cabin_slats_post", "통나무집 창살 기둥"),
    (0x04, 0x0A): ("cabin_planks_post", "통나무집 벽 기둥"),
    (0x04, 0x0B): ("cabin_slats_right", "통나무집 창살 오른쪽"),
    (0x04, 0x0D): ("stump", "그루터기"),
    (0x04, 0x0F): ("log_pile", "장작"),
    (0x04, 0x10): ("crops", "채소밭"),
    (0x04, 0x11): ("signboard", "팻말"),
    (0x04, 0x12): ("grave", "묘비"),
    (0x04, 0x14): ("stairs_up", "위 계단"),
    (0x04, 0x15): ("stairs_down", "아래 계단"),
    (0x04, 0x1F): ("pot", "항아리"),
    (0x05, 0x0C): ("stone_ledge", "바위 턱"),
    (0x05, 0x18): ("stone_floor", "흰 바닥"),
    (0x05, 0x1E): ("lion_statue", "사자상"),
    (0x06, 0x05): ("swamp", "독늪"),
    (0x06, 0x10): ("travel_door", "여행의 문"),
    (0x07, 0x0A): ("rock_wall", "바위벽"),
    (0x07, 0x0B): ("rock_wall_dark", "어두운 바위벽"),
    (0x07, 0x1D): ("blue_tile", "청백 타일"),
    (0x08, 0x0D): ("stone_wall_cracked", "금 간 석벽"),
    (0x08, 0x0E): ("stone_wall_cracked", "금 간 석벽"),
    (0x08, 0x0F): ("log_pile", "장작"),
    (0x09, 0x0C): ("stone_band", "무늬 판석 띠"),
    (0x09, 0x17): ("altar", "금 제단"),
    (0x09, 0x18): ("curtain", "휘장 문간"),
    (0x09, 0x19): ("valance", "푸른 휘장"),
    (0x09, 0x1A): ("pillar_top", "기둥 머리"),
    (0x09, 0x1B): ("pillar", "기둥"),
    (0x09, 0x1C): ("dais_left", "왕좌 뒤 장식 왼쪽"),
    (0x09, 0x1D): ("dais_middle", "왕좌 뒤 장식 가운데"),
    (0x09, 0x1E): ("dais_right", "왕좌 뒤 장식 오른쪽"),
    (0x09, 0x1F): ("throne", "옥좌"),
    (0x0B, 0x12): ("archway_left", "아치 통로 왼쪽"),
    (0x0B, 0x13): ("archway_right", "아치 통로 오른쪽"),
    (0x0B, 0x1C): ("bridge", "다리"),
    (0x0B, 0x1F): ("dark_void", "어둠"),
    (0x0C, 0x06): ("barrier", "결계"),
    (0x0C, 0x19): ("pew", "긴 의자"),
    (0x0D, 0x18): ("counter", "카운터 왼쪽"),
    (0x0D, 0x19): ("counter", "카운터 오른쪽"),
    (0x01, 0x15): ("quay_nw", "석축 북서 모서리"),
    (0x01, 0x16): ("quay_n", "석축 북쪽 끝"),
    (0x01, 0x17): ("quay_ne", "석축 북동 모서리"),
    (0x01, 0x18): ("quay_inner_sw", "석축 안쪽 모서리(물이 남서)"),
    (0x01, 0x19): ("quay_w", "석축 서쪽"),
    (0x01, 0x1A): ("quay_stairs", "물가 계단"),
    (0x01, 0x1B): ("quay_e", "석축 동쪽"),
    (0x01, 0x1C): ("quay_inner_se", "석축 안쪽 모서리(물이 남동)"),
    (0x01, 0x1D): ("quay_sw", "석축 남서 모서리"),
    (0x01, 0x1E): ("quay_s", "석축 남쪽"),
    (0x01, 0x1F): ("quay_se", "석축 남동 모서리"),
    (0x27, 0x06): ("red_paving", "붉은 바닥"),
    (0x27, 0x14): ("dark_void", "떨어지는 검은 칸"),
    (0x27, 0x19): ("stairs_up", "위 계단"),
    (0x2C, 0x0D): ("audience_pink", "관객"),
    (0x2C, 0x0E): ("audience_green", "관객"),
    (0x2C, 0x19): ("audience_green", "관객"),
    (0x2C, 0x1B): ("audience_pink", "관객"),
    # Dungeon and tower sheets: only blocks whose property fallback would hide what they show.
    (0x10, 0x04): ("mine_beam", "광산 들보"),
    (0x10, 0x05): ("rock_pile", "바위 더미"),
    (0x10, 0x06): ("mine_beam", "광산 들보"),
    (0x10, 0x07): ("mine_beam", "광산 들보"),
    (0x10, 0x09): ("washbasin", "돌 함지"),
    (0x10, 0x0B): ("grave", "묘비"),
    (0x10, 0x0C): ("ladder", "사다리(입구·출구)"),
    (0x10, 0x0D): ("pit", "구덩이(입구·출구)"),
    (0x10, 0x0E): ("counter", "돌 카운터"),
    (0x10, 0x11): ("grate", "창살 바닥"),
    (0x10, 0x14): ("statue", "얼굴 조각"),
    (0x10, 0x15): ("grate", "격자 바닥"),
    (0x10, 0x18): ("rock_pile", "바위"),
    (0x10, 0x1B): ("stump", "그루터기"),
    (0x12, 0x03): ("grass", "덤불 바닥"),
    (0x12, 0x04): ("rock_pile", "흙 바위"),
    (0x12, 0x05): ("rock_pile", "회색 바위"),
    (0x12, 0x0B): ("water0", "징검돌 물"),
    (0x12, 0x0C): ("grass", "풀밭"),
    (0x13, 0x0A): ("sandstone", "벽돌"),
    (0x13, 0x0E): ("wood_wall", "판자 벽"),
    (0x13, 0x0F): ("wood_wall", "판자 벽"),
    (0x13, 0x12): ("cabin_slats", "세로 판자"),
    (0x13, 0x13): ("cabin_slats", "세로 판자"),
    (0x13, 0x14): ("statue", "석상"),
    (0x13, 0x16): ("wood_floor", "판자 바닥"),
    (0x13, 0x17): ("wood_floor", "판자 바닥"),
    (0x13, 0x18): ("washbasin", "샘"),
    (0x14, 0x13): ("stone_band", "문양 바닥"),
    (0x14, 0x17): ("statue", "석상"),
    (0x14, 0x18): ("washbasin", "샘"),
    (0x15, 0x0C): ("pillar", "기둥"),
    (0x15, 0x0E): ("statue", "괴수 석상"),
    (0x15, 0x0F): ("statue", "괴수 석상"),
    (0x15, 0x10): ("pillar", "기둥"),
    (0x15, 0x12): ("statue", "부조"),
    (0x15, 0x13): ("statue", "부조"),
    (0x15, 0x15): ("grate", "창살"),
    (0x15, 0x18): ("grate", "창살 바닥"),
    (0x15, 0x19): ("statue", "얼굴 조각"),
    (0x15, 0x1D): ("statue", "석상"),
    (0x16, 0x07): ("pillar_top", "기둥 머리"),
    (0x16, 0x08): ("statue", "괴수 석상"),
    (0x16, 0x09): ("statue", "괴수 석상"),
    (0x16, 0x0B): ("pillar", "기둥"),
    (0x16, 0x0C): ("statue", "부조"),
    (0x16, 0x0D): ("statue", "부조"),
    (0x16, 0x13): ("stone_floor", "판석"),
    (0x1B, 0x12): ("archway_left", "굴 입구 왼쪽"),
    (0x1B, 0x13): ("archway_right", "굴 입구 오른쪽"),
    (0x1C, 0x01): ("lion_statue", "금빛 석상"),
    (0x1C, 0x04): ("red_paving", "분홍 바닥"),
    (0x22, 0x06): ("brick_paving", "붉은 성 바닥"),
    (0x1E, 0x10): ("cave_rock_earth", "벼랑"),
    (0x1E, 0x11): ("cave_rock_earth", "벼랑"),
    (0x1E, 0x14): ("cave_rock_earth", "벼랑"),
    (0x1E, 0x15): ("cave_rock_earth", "벼랑"),
    (0x1E, 0x16): ("cave_rock_earth", "벼랑"),
    (0x1E, 0x17): ("cave_rock_earth", "벼랑"),
    (0x1E, 0x18): ("cave_rock_red", "아래의 붉은 땅"),
    (0x1E, 0x19): ("cave_rock_red", "아래의 붉은 땅"),
    (0x1E, 0x1A): ("cave_rock_red", "아래의 붉은 땅"),
    (0x1E, 0x1B): ("cave_rock_red", "아래의 붉은 땅"),
    (0x1E, 0x0E): ("water0", "먼 물결"),
    (0x1E, 0x0F): ("water0", "먼 물결"),
    (0x32, 0x15): ("cloud", "구름"),
    (0x32, 0x16): ("cloud", "구름"),
    (0x32, 0x17): ("cloud", "구름"),
    (0x32, 0x18): ("cloud", "구름"),
    (0x32, 0x19): ("cloud", "구름"),
    (0x32, 0x1A): ("cloud", "구름"),
    (0x32, 0x1B): ("cloud", "구름"),
    (0x32, 0x1C): ("cloud", "구름"),
    (0x32, 0x1D): ("cloud", "구름"),
    (0x1C, 0x02): ("altar", "금 제단"),
    (0x1C, 0x10): ("pot", "분홍 항아리"),
    (0x1E, 0x00): ("statue", "마물 석상"),
    (0x1E, 0x01): ("statue", "마물 석상"),
    (0x1E, 0x02): ("pillar", "기둥"),
    (0x1E, 0x03): ("pillar", "기둥"),
    (0x1E, 0x06): ("altar", "제단"),
    (0x1F, 0x14): ("stone_wall", "벽돌"),
    (0x1F, 0x15): ("stone_wall", "벽돌"),
    (0x1F, 0x16): ("stone_wall", "벽돌"),
    (0x1F, 0x18): ("archway_left", "굴 입구"),
    (0x22, 0x10): ("statue", "마물 석상"),
    (0x22, 0x11): ("statue", "마물 석상"),
    (0x23, 0x14): ("wood_wall", "나무껍질"),
    (0x23, 0x15): ("wood_wall", "나무껍질"),
    (0x23, 0x16): ("wood_wall", "나무껍질"),
    (0x23, 0x1A): ("ladder", "사다리(입구·출구)"),
    (0x23, 0x1B): ("pit", "구멍(입구·출구)"),
    (0x23, 0x1C): ("bush", "잎"),
    (0x23, 0x1D): ("bush", "잎"),
    (0x24, 0x07): ("pit", "구멍"),
    (0x24, 0x10): ("stump", "그루터기"),
    (0x24, 0x12): ("dirt", "모래"),
    (0x24, 0x13): ("tree16", "나무"),
    (0x24, 0x14): ("bush", "덤불"),
    (0x24, 0x15): ("grass", "풀밭"),
    (0x24, 0x19): ("wood_floor", "판자"),
    (0x25, 0x0B): ("pillar_top", "기둥 머리"),
    (0x25, 0x0C): ("statue", "괴수 석상"),
    (0x25, 0x0D): ("statue", "괴수 석상"),
    (0x25, 0x0F): ("pillar", "기둥"),
    (0x25, 0x10): ("statue", "부조"),
    (0x25, 0x11): ("statue", "부조"),
    (0x25, 0x12): ("grate", "창살 바닥"),
    (0x25, 0x16): ("statue", "석상"),
    (0x25, 0x1A): ("statue", "석상"),
    (0x2A, 0x03): ("statue", "얼굴 조각"),
    (0x2A, 0x06): ("rock_pile", "바위"),
    (0x2A, 0x07): ("rock_pile", "바위"),
    (0x2D, 0x0E): ("statue", "굳은 병사"),
    (0x2D, 0x0F): ("statue", "굳은 사람"),
    (0x2D, 0x10): ("statue", "굳은 사람"),
    (0x2D, 0x11): ("statue", "굳은 사람"),
    (0x2D, 0x12): ("statue", "굳은 사람"),
    (0x2D, 0x13): ("statue", "굳은 사람"),
    (0x2D, 0x14): ("statue", "굳은 사람"),
    (0x2D, 0x1F): ("statue", "굳은 병사"),
    (0x2F, 0x10): ("pot", "금 항아리"),
    (0x2F, 0x11): ("pot", "금 항아리"),
    (0x2F, 0x12): ("grate", "창살"),
    (0x2F, 0x14): ("pillar", "금 기둥"),
    (0x2F, 0x15): ("pillar", "금 기둥"),
    (0x2F, 0x18): ("pillar", "금 기둥"),
    (0x2F, 0x19): ("pillar", "금 기둥"),
    (0x30, 0x08): ("statue", "마물 석상"),
    (0x30, 0x0A): ("statue", "마물 석상"),
    (0x30, 0x0B): ("statue", "금빛 석상"),
    (0x31, 0x07): ("window16", "창"),
    (0x31, 0x10): ("tree16", "나무"),
    (0x31, 0x13): ("statue", "금빛 석상"),
    (0x32, 0x10): ("altar", "문장"),
}
# Dungeon and tower sheets: the wall and floor that every block without its own art falls back to,
# by whether its FC property blocks the way, and what a falling cell shows.
SHEET_STYLES = {
    0x10: ("cave_rock_earth", "cave_floor_earth"), 0x11: ("cave_rock_brown", "cave_floor_brown"),
    0x12: ("boulder_wall", "cave_floor_earth"), 0x13: ("boulder_wall", "cave_floor_earth"),
    0x14: ("boulder_wall", "cave_floor_earth"), 0x15: ("castle_wall", "stone_floor"),
    0x16: ("castle_wall", "red_paving"), 0x17: ("wood_wall", "cave_floor_brown"),
    0x18: ("boulder_wall", "stone_floor"), 0x19: ("ice_wall", "ice_floor"),
    0x1A: ("boulder_wall", "cave_floor_earth"), 0x1B: ("cave_rock_brown", "dirt"),
    0x1C: ("cave_rock_brown", "stone_floor", "sky"), 0x1D: ("cave_rock_brown", "cave_floor_brown"),
    0x1E: ("dark_void", "cave_floor_earth"), 0x1F: ("cave_rock_earth", "cave_floor_earth"),
    0x20: ("castle_wall", "stone_floor", "sky"), 0x21: ("castle_wall", "brick_paving", "sky"),
    0x22: ("castle_wall", "cloud", "sky"), 0x23: ("wood_grain", "wood_floor"), 0x24: ("wood_grain", "wood_floor"),
    0x25: ("castle_wall", "grass"), 0x26: ("castle_wall", "red_paving"), 0x28: ("castle_wall", "stone_floor"),
    0x29: ("cave_rock_moss", "cave_floor_earth"), 0x2A: ("cave_rock_red", "cave_floor_brown"),
    0x2B: ("castle_wall", "red_paving"), 0x2D: ("stone_wall", "dirt"), 0x2E: ("wood_wall", "wood_floor"),
    0x2F: ("sandstone", "dirt"), 0x30: ("castle_wall", "stone_floor"), 0x31: ("boulder_wall", "stone_floor"),
    0x32: ("castle_wall", "stone_floor", "sky"),
}
SHEET_PALETTES = {0x28: "purple", 0x30: "purple"}
# Sheets whose slow vertical cells (property 31) are wooden ladders rather than stone steps.
LADDER_SHEETS = {0x11, 0x17, 0x1B, 0x1C, 0x23, 0x24}
# Fallback art by FC block property, before the sheet's wall or floor.
PROPERTY_ART = {
    0x83: "water0", 0x08: "stairs_up", 0x09: "stairs_down", 0x04: "chest_closed", 0x31: "stone_steps",
    0x0A: "travel_door", 0x01: "swamp", 0x02: "barrier", 0x0F: "lift", 0x10: "arrow_up",
    0x11: "arrow_right", 0x12: "arrow_down", 0x13: "arrow_left", 0x94: "gold_door16", 0x96: "gold_door16",
    0x9C: "gold_door16", 0x9D: "gold_door16", 0xA0: "gold_door16", 0xAC: "iron_door", 0xA7: "counter",
    0xAB: "wardrobe", 0xAA: "pot",
}
FALLING = (0x05, 0x0B)
# Dungeon blocks whose shape matters: cliff tops, rock pillars, ledge and shore edges, tree-hollow rims.
# "trace" keeps the FC block's black outline pixels and paints its sky and void areas, with the rest in the
# sheet's wall or floor (or the asset after the colon). "slope" and "slope_r" are cave slopes that FC draws as
# a one-colour floor triangle beside dithered rock, with no outline: the floor is the upper-left or upper-right
# triangle.
SHAPES = {
    0x11: {0x02: "slope", 0x03: "slope_r", 0x16: "slope", 0x17: "slope_r"},
    0x13: {0x09: "trace"},
    0x17: {0x11: "trace"},
    0x18: {0x0C: "trace:water0", 0x0D: "trace:water0", 0x0E: "trace:water0", 0x10: "trace:water0",
           0x11: "trace:water0", 0x12: "trace:water0", 0x1B: "trace", 0x1D: "trace", 0x1E: "trace", 0x1F: "trace"},
    0x1B: {b: "trace" for b in (0x05, 0x06, 0x07, 0x08, 0x09, 0x0A, 0x0D, 0x0E, 0x10, 0x11, 0x14, 0x15, 0x16, 0x17,
                                0x18)},
    0x1C: {b: "trace" for b in (0x08, 0x0A, 0x0B, 0x0C, 0x0D, 0x0E, 0x11, 0x12, 0x13, 0x14, 0x15, 0x16, 0x17, 0x18,
                                0x1A, 0x1C, 0x1D)},
    0x1E: {b: "trace" for b in (0x07, 0x08, 0x09, 0x0A, 0x0B, 0x0C, 0x0D, 0x1C, 0x1D)},
    0x23: {b: "trace" for b in (0x08, 0x09, 0x0C, 0x0D, 0x0E, 0x0F, 0x10, 0x11)},
    0x24: {b: "trace" for b in (0x04, 0x05, 0x06, 0x09, 0x0A, 0x0B, 0x0C, 0x0D)},
    0x2A: {0x12: "slope", 0x13: "slope_r"},
    0x2D: {b: "trace" for b in (0x04, 0x05, 0x0B, 0x15, 0x19, 0x1A)},
}
# FC sky blues; the pale cyans 2C, 3C and 31 are cloud. A traced water base keeps these blues as its own
# water (sheet 18 draws deep water in 01, 11 and 21).
SKY = {0x01, 0x02, 0x11, 0x12, 0x21, 0x22}


def map_palette(name, sheet):
    return MAP_PALETTES.get(name, SHEET_PALETTES.get(sheet, "normal"))


# The floor under transparent fixtures, as on the FC sheet.
SHEET_FLOORS = {0x04: "dirt", 0x0E: "carpet"}
BACKGROUNDS = {(0x08, 0x0F): "grass", **{(0x2D, b): "grass" for b in (0x0E, 0x0F, 0x10, 0x11, 0x12, 0x13, 0x14, 0x1F)}}
SHEETS = (0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x09, 0x0B, 0x0C, 0x0D, 0x0F, 0x27, 0x2C) + tuple(SHEET_STYLES)

# FC interior maps drawn with block sheets 0A and 0E, by name; their FC palettes are the same set
# except アッテムト, which uses a darker set.
MAPS = (
    (0x02, 0, 0x0A, "burland"), (0x08, 0, 0x0A, "gardenburg"), (0x09, 0, 0x0A, "stancia"),
    (0x09, 3, 0x0A, "stancia-03"), (0x09, 6, 0x0A, "stancia-06"), (0x0D, 0, 0x0A, "mintos"),
    (0x12, 0, 0x0E, "imuru"), (0x13, 4, 0x0A, "saran-04"), (0x19, 0, 0x0E, "seaside"),
    (0x19, 1, 0x0E, "seaside-01"), (0x1B, 0, 0x0A, "rosaryhill"), (0x1B, 1, 0x0A, "rosaryhill-01"),
    (0x2A, 0, 0x0A, "shrine-2a"), (0x32, 6, 0x0E, "konenbery-06"), (0x34, 5, 0x0E, "attemut-05"),
    (0x34, 7, 0x0E, "attemut-07"),
)
# Maps whose FC palette is darker than their sheet's: アッテムト, and the night or cursed variants
# 34/06, 34/09, 3C/09 and 46/01-03 (one NES brightness step down in some or all colours).
MAP_PALETTES = {"attemut-05": "dim", "attemut-07": "dim", "34-06": "dim", "34-09": "dim", "3C-09": "dim",
                "46-01": "dim", "46-02": "dim", "46-03": "dim"}


def all_maps(prg):
    """MAPS plus every FC map of SHEETS as (group, number, sheet, name)."""
    yield from MAPS
    for _, source in dq4block.all_maps(prg):
        if source.buf is not None and source.t in SHEETS:
            yield source.g, source.k, source.t, f"{source.g:02X}-{source.k:02X}"


def _graphic(prg, t, block):
    d = dq4block.defs(prg, t).get(block)
    if d is None:
        return None
    colours = dq4block.palette(prg, t)[3 * d["pal"]:3 * d["pal"] + 3]
    return d["bank"], tuple(d["addrs"]), bytes(colours)


def sheet_art(prg, t):
    """{block: (asset, role)} for every block of sheet t that has a BLOCK_ART or EXAMPLES graphic."""
    known = {}
    for (sheet, block), art in [((s, b), a) for s, arts in BLOCK_ART.items() for b, a in arts.items()] + list(EXAMPLES.items()):
        known.setdefault(_graphic(prg, sheet, block), art)
    out = dict(BLOCK_ART.get(t, {}))
    style = SHEET_STYLES.get(t)
    for block in range(32):
        if block in out:
            continue
        graphic = _graphic(prg, t, block)
        if graphic in known:
            out[block] = known[graphic]
        elif style:
            d = dq4block.defs(prg, t).get(block)
            prop = UNDEFINED if d is None else d["prop"]
            if prop in FALLING:
                out[block] = (style[2] if len(style) > 2 else "dark_void", "떨어지는 칸(시트 기본)")
            elif prop == 0x31 and t in LADDER_SHEETS:
                out[block] = ("ladder", "사다리(속성 기본)")
            elif prop in PROPERTY_ART:
                out[block] = (PROPERTY_ART[prop], f"{dq4block.kind_name(prop)}(속성 기본)")
            else:
                out[block] = (style[0], "벽(시트 기본)") if prop & 0x80 else (style[1], "바닥(시트 기본)")
    for block, shape in SHAPES.get(t, {}).items():
        if not out[block][1].endswith("(시트 기본)"):
            raise ValueError(f"{t:02X}/{block:02X}: SHAPES would replace {out[block][0]}")
        kind, _, base = shape.partition(":")
        base = base or out[block][0]
        out[block] = (f"{kind}:{base}", "벼랑·비탈(FC 모양)")
    return out


def fc_pixels(prg, t, block):
    """FC block as 16 rows of NES colours (colour 0 is 0F in every map, dq4block.palette)."""
    bank, addrs, colours = _graphic(prg, t, block)
    colours = (0x0F, *colours)
    rows = [[0] * 16 for _ in range(16)]
    for quarter, addr in enumerate(addrs):
        o = bank * 0x4000 + (addr & 0x3FFF)
        data = prg[o:o + 16]
        for r in range(8):
            for c in range(8):
                rows[quarter // 2 * 8 + r][quarter % 2 * 8 + c] = colours[
                    (data[r] >> (7 - c) & 1) | (data[r + 8] >> (7 - c) & 1) << 1]
    return rows


def _shape_classes(prg, t, block, kind, base):
    """16 rows of A (the base), S (sky), V (void), O (outline) and F (floor, slopes only)."""
    if kind == "slope":
        return [["F" if x + y < 15 else "O" if x + y == 15 else "A" for x in range(16)] for y in range(16)]
    if kind == "slope_r":
        return [["F" if x > y else "O" if x == y else "A" for x in range(16)] for y in range(16)]
    if kind != "trace":
        raise ValueError(f"{t:02X}/{block:02X}: unknown shape {kind}")
    rows = fc_pixels(prg, t, block)
    out = []
    for y in range(16):
        row = []
        for x in range(16):
            c = rows[y][x]
            if c in SKY and not base.startswith("water"):
                row.append("S")
            elif c in SKY:
                row.append("A")
            elif c == 0x0F:
                around = [rows[yy][xx] for yy in range(max(0, y - 1), min(16, y + 2))
                          for xx in range(max(0, x - 1), min(16, x + 2))]
                # A black pixel inside a black area is the void around a cliff, not its outline.
                row.append("V" if all(v == 0x0F for v in around) else "O")
            else:
                row.append("A")
        out.append(row)
    return out


def _nearest(palette, value, bank):
    rgb = palette[value * 3:value * 3 + 3]
    return min(range(bank * 16 + 1, bank * 16 + 16),
               key=lambda i: sum((palette[i * 3 + c] - rgb[c]) ** 2 for c in range(3)))


def _shape_tile(prg, assets, name, palette, t, block):
    """SHAPES art. Each 8x8 keeps the base's palette bank (one bank per SNES tile); sky, void and floor
    colours from other banks move to the nearest colour of that bank, and the outline is its darkest."""
    kind, base = name.split(":")
    style = SHEET_STYLES[t]
    layers = {"A": _tile(assets, base, palette, t, block)[0], "S": assets["sky"],
              "V": assets[style[2] if len(style) > 2 else "dark_void"], "F": _tile(assets, style[1], palette, t, block)[0]}
    classes = _shape_classes(prg, t, block, kind, base)
    result = layers["A"].copy()
    remapped = 0
    for qy in (0, 8):
        for qx in (0, 8):
            bank = layers["A"].getpixel((qx, qy)) >> 4
            dark = min(range(bank * 16 + 1, bank * 16 + 16), key=lambda i: sum(palette[i * 3:i * 3 + 3]))
            for y in range(qy, qy + 8):
                for x in range(qx, qx + 8):
                    k = classes[y][x]
                    value = dark if k == "O" else layers[k].getpixel((x, y))
                    if value >> 4 != bank:
                        value = _nearest(palette, value, bank)
                        remapped += 1
                    result.putpixel((x, y), value)
    return result, {"shape": kind, "background": None, "transparent_pixels_filled": 0,
                    "background_palette_remapped_pixels": remapped, "foreground_pixels_remapped": 0}


def _tile(assets, name, palette, map_type, block=None, background_name=None):
    if name not in assets:
        raise ValueError(f"Missing environment asset: {name}")
    tile = assets[name]
    if tile.mode != "P" or tile.size != (16, 16):
        raise ValueError(f"{name}: map block requires indexed 16x16 art, got {tile.mode} {tile.size}")
    if tile.getpalette() != palette:
        raise ValueError(f"{name}: palette differs from the shared environment palette")
    transparency = tile.info.get("transparency")
    if transparency not in (None, 0):
        raise ValueError(f"{name}: only transparent index zero is supported")
    pixels = tile.tobytes()
    transparent = pixels.count(0) if transparency == 0 and name != "dark_void" else 0
    if background_name is None:
        floor = SHEET_STYLES[map_type][1] if map_type in SHEET_STYLES else SHEET_FLOORS.get(map_type, "red_paving")
        background_name = BACKGROUNDS.get((map_type, block), floor)
    if name in {"tree16", "bush", "flowers", "crops"}:
        background_name = "grass"
    elif name in {"sign_church", "sign_weapon", "sign_armour", "sign_inn", "sign_shop", "window16"}:
        background_name = "stone_wall"
    background = assets[background_name]
    if background.mode != "P" or background.size != (16, 16) or background.getpalette() != palette:
        raise ValueError(f"{background_name}: incompatible background tile")
    result = tile.copy()
    result.info.pop("transparency", None)
    remapped = 0
    for y in (0, 8):
        for x in (0, 8):
            indices = tile.crop((x, y, x + 8, y + 8)).tobytes()
            banks = {v >> 4 for v in indices if v}
            if len(banks) > 1 or any(v >= 128 or (v and (v < 16 or v % 16 == 0)) for v in indices):
                raise ValueError(f"{name}: incompatible SFC palette banks at {x},{y}")
            if not transparent:
                continue
            bank = next(iter(banks), None)
            for dy in range(8):
                for dx in range(8):
                    if tile.getpixel((x + dx, y + dy)):
                        continue
                    value = background.getpixel((x + dx, y + dy))
                    if bank is not None and value >> 4 != bank:
                        value = _nearest(palette, value, bank)
                        remapped += 1
                    result.putpixel((x + dx, y + dy), value)
    return result, {
        "background": background_name if transparent else None,
        "transparent_pixels_filled": transparent,
        "background_palette_remapped_pixels": remapped,
        "foreground_pixels_remapped": 0,
    }


# Blocks without an FC definition (the black filler 0E/1E) have no property; treat them as walls.
UNDEFINED = 0x80


def block_prop(source, block):
    return source.blocks["prop"].get(block, UNDEFINED)


def prepare_maps(prg, assets, names=None):
    """Yield each FC map with its block counts and composited 16x16 block art."""
    if not assets:
        raise ValueError("Environment asset collection is empty")
    palette = next(iter(assets.values())).getpalette()
    if palette is None:
        raise ValueError("Environment palette is missing")
    arts = {}
    for group, number, expected_type, name in all_maps(prg) if names is None else [m for m in all_maps(prg) if m[3] in names]:
        source = dq4block.Map(prg, group, number)
        if source.t != expected_type:
            raise ValueError(f"{group:02X}/{number:02X}: expected map type {expected_type:02X}, got {source.t:02X}")
        counts = Counter(value & 31 for value in source.buf)
        mapping = arts.setdefault(source.t, sheet_art(prg, source.t))
        unsupported = sorted(set(counts) - mapping.keys())
        if unsupported:
            raise ValueError(f"{name}: unsupported source blocks {unsupported}")
        prepared = {block: _shape_tile(prg, assets, mapping[block][0], palette, source.t, block)
                    if ":" in mapping[block][0] else _tile(assets, mapping[block][0], palette, source.t, block)
                    for block in counts}
        yield group, number, name, source, counts, prepared, palette


def render_maps(rom_path, assets, names=None):
    """Return complete block-grid previews and their ROM-derived mapping evidence."""
    data = Path(rom_path).read_bytes()
    result = {}
    prg = ines.prg(data)
    for group, number, name, source, counts, prepared, palette in prepare_maps(prg, assets, names):
        mapping = sheet_art(prg, source.t)
        preview = Image.new("P", (source.w * 16, source.h * 16))
        preview.putpalette(palette_variant(map_palette(name, source.t)))
        for y in range(source.h):
            for x in range(source.w):
                block = source.cell(x, y) & 31
                preview.paste(prepared[block][0], (x * 16, y * 16))
        records = []
        for block, count in sorted(counts.items()):
            prop = block_prop(source, block)
            records.append({
                "source_block": f"{block:02X}",
                "asset": mapping[block][0],
                "visual_role": mapping[block][1],
                "property": prop,
                "functional_role": dq4block.kind_name(prop),
                "passable": not bool(prop & 0x80),
                "cells": count,
                "composition": prepared[block][1],
            })
        result[name] = (preview, {
            "map": f"{group:02X}/{number:02X}",
            "map_type": f"{source.t:02X}",
            "palette": map_palette(name, source.t),
            "size_blocks": [source.w, source.h],
            "source_rom_sha1": hashlib.sha1(data).hexdigest(),
            "source_layout_sha256": hashlib.sha256(bytes(source.buf)).hexdigest(),
            "source_sheet": f"fc/dq4/gfx/blocks/{source.t:02X}.png",
            "block_mappings": records,
            "unsupported_blocks": [],
            "source_cells": source.w * source.h,
            "rendered_cells": sum(counts.values()),
            "palette_remapped_pixels": sum(prepared[b][1]["background_palette_remapped_pixels"] * n for b, n in counts.items()),
            "foreground_pixels_remapped": 0,
            "layout_preserved": True,
            "region_visibility": "all regions exposed, matching the FC reference renderer",
            "characters_rendered": False,
            "engine_ready": False,
            "limitations": [
                "Static closed-door and first-water-frame preview; no events or animation are executed.",
                "Passability and functional roles are recorded, not installed into the DQ5 engine.",
                "Wall heights and roof overlays are not added to the FC block grid.",
                "Visual meanings marked unconfirmed remain hypotheses, independent of ROM properties.",
            ],
        })
    return result


# FC field blocks (sheet 00, fields 0, 1 and 3). The 2-wide cave mouths and castles use the
# same left and right halves as on the field.
FIELD_ART = {
    0x00: ("water0", "바다"), 0x01: ("hill", "언덕"), 0x02: ("grass", "초원"), 0x03: ("bush", "덤불"),
    0x04: ("forest", "숲"), 0x05: ("dirt", "사막"), 0x06: ("mountain", "산"), 0x07: ("swamp", "독늪"),
    0x08: ("cave_mouth", "동굴 입구 왼쪽"), 0x09: ("cave_mouth", "동굴 입구 오른쪽"), 0x0A: ("shoal", "암초"),
    0x0B: ("cave_mouth", "동굴 입구"), 0x0C: ("shrine", "사당"), 0x0D: ("tower_icon", "탑"),
    0x0E: ("rocky_path", "돌길"), 0x0F: ("rocky_path", "돌길"), 0x10: ("town_icon", "마을"),
    0x11: ("tower_icon", "탑"), 0x12: ("castle_icon_left", "성 왼쪽"), 0x13: ("castle_icon_right", "성 오른쪽"),
    0x14: ("rocky_path", "어두운 돌길"), 0x15: ("signboard", "팻말"), 0x16: ("bridge", "다리"),
    0x17: ("rocky_path", "돌길"), 0x1D: ("rocky_path", "어두운 돌길"), 0x1E: ("rocky_path", "어두운 돌길"),
}


def render_fields(rom_path, assets):
    """FC fields drawn with FIELD_ART: {"field0": (image, info), …}. Unused blocks stay unsupported."""
    prg = ines.prg(Path(rom_path).read_bytes())
    palette = next(iter(assets.values())).getpalette()
    result = {}
    for number in dq4field.FIELDS:
        source = dq4block.Map(prg, field=number)
        counts = Counter(source.cell(x, y) for y in range(source.dh) for x in range(source.dw))
        unsupported = sorted(set(counts) - FIELD_ART.keys())
        if unsupported:
            raise ValueError(f"field {number}: unsupported blocks {unsupported}")
        tiles = {}
        for block in counts:
            name = FIELD_ART[block][0]
            if name == "water0" or name == "shoal":
                tiles[block] = assets[name]
            else:
                tiles[block] = _tile(assets, name, palette, 0x0A, None, "grass")[0]
        image = Image.new("P", (source.dw * 16, source.dh * 16))
        image.putpalette(palette_variant("normal"))
        for y in range(source.dh):
            for x in range(source.dw):
                image.paste(tiles[source.cell(x, y)], (x * 16, y * 16))
        result[f"field{number}"] = (image, {
            "field": number, "size_blocks": [source.dw, source.dh],
            "block_mappings": [{"source_block": f"{b:02X}", "asset": FIELD_ART[b][0], "visual_role": FIELD_ART[b][1],
                                "cells": n} for b, n in sorted(counts.items())],
        })
    return result
