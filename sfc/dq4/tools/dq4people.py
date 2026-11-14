"""서장·1장 인물 필드 그림: NDS 인물 시트를 DQ5 세트로 줄여 넣고, 같은 그림 번호를 쓰는 인물을 맵 그룹으로 가른다.

NDS 시트(자원 저장소 nds/dq4/chr/field/hNNN.png)는 방향마다 24x32 프레임 3장이다. 8방향(128x256)은 줄 0 뒤,
2 오른쪽 보기, 4 앞, 6 왼쪽 보기, 4방향(128x128)은 0 뒤, 1 왼쪽 보기, 2 앞, 3 오른쪽 보기다. 사람은 상자 16x24 를
다 써 발을 맨 아랫줄에 두고(배율은 NDS 28줄 → 22줄을 넘지 않게, 가장 큰 프레임이 24줄에 들어가는 값), 칸마다
겹치는 NDS 점 가운데 가장 많은 색을 고른다. 방향마다 프레임 셋은 걸음·서기·걸음이라 첫째·셋째를 걸음 두 장으로
쓰되, 둘째 장은 첫 장의 STEP_TOP 줄부터만 바꾼다(DQ5 처럼 머리 타일을 함께 써야 타일 한도에 든다). 눈은 INK 1x2 와
흰자 1x2 로 다시 찍는다. 몬스터·동물은 22줄 배율로 발을 21행에 두고 NDS 첫 두 프레임이 그대로 걸음이다.

세트: 장 주인공은 새 세트 70·71, 1장 인물은 그 그림 번호의 원래 세트를 그 자리에서 바꾼다(8타일 세트는 머리
16x16 + 몸 16x16 배치). 서장에서만 다른 인물과 원래 세트가 모자란 주요 인물은 DQ4 가 쓰지 않는 그림 번호(spare)의
세트를 그 자리에서 바꿔 쓴다. 새 세트 레코드 자리(1F:FE30~, 8개)와 늘린 뱅크의 빈 자리를 아끼려는 것이다.
그림 번호 → 세트를 읽는 두 곳(1F:CF45, 03:D202 의 LDA $2586D0,X)을 JSL 로 돌려, 표의 (그림 번호, 맵 그룹 $BC) 가
맞으면 그 세트를, 아니면 원래 표를 읽는다.

색: 장 주인공·호이민은 OBJ 팔레트 한 줄씩(7·6·5), 나머지는 0·1·2·3·4 다섯 줄과 그 맵 그룹에서 일행이 쓰지 않는
일행 줄(LENT_LINES)을 나눠 쓴다. 살색·눈·흰자(COMMON)는 모든 인물이 같은 값이라 줄마다 다섯 칸을 함께 쓴다.
주요·상징 인물은 무겁게 세고(KEY_WEIGHT) 서로 다른 줄로 흩어, 마을 사람과 한 줄을 써도 제 색이 남게 한다.

  python sfc/dq4/tools/dq4people.py --base work/ch1/dq4-ch1-sound.sfc --assets "$DQ4_ASSETS" --out work/ch1/dq4-ch1-full.sfc
  python sfc/dq4/tools/dq4people.py --plan --assets "$DQ4_ASSETS"     인물마다 타일 수·한도·팔레트 줄
"""
import argparse
import json
import math
import subprocess
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
DQ5_TOOLS = HERE.parents[1] / 'dq5' / 'tools'
sys.path[:0] = [str(HERE), str(DQ5_TOOLS)]

import dq4chapterbox  # noqa: E402
from dq4ch2event import ALENA_PICTURE, BREY_PICTURE, CHAPTER2, KIRYL_PICTURE  # noqa: E402
from dq4chapter1 import apply_writes, lorom  # noqa: E402
from dq4romassets import set_checksum  # noqa: E402
import dq5npcrecord  # noqa: E402
import dq5objpalette  # noqa: E402
import dq5sprite as S  # noqa: E402
import dq5spritewrite  # noqa: E402
from dq5map import Rom  # noqa: E402

FIELD = Path('nds') / 'dq4' / 'chr' / 'field'
ROWS8 = (('down', 4), ('left', 6), ('right', 2), ('up', 0))
ROWS4 = (('down', 2), ('left', 3), ('right', 1), ('up', 0))   # 4줄 시트는 1줄이 오른쪽(얼굴 살색이 오른쪽에 몰림)
SCALE, BOTTOM, WIDTH = 22 / 28, 22, 16
# 사람은 상자 24줄을 다 쓴다. 22줄에 맞추면 모자·투구가 있는 인물은 위가 잘리거나(납작한 모자), 온몸을 더 줄여야
# 해서 얼굴이 작아진다. 발이 DQ5 인물보다 두 줄 아래에 놓인다
TALL = 24
INK = (32, 32, 16)                               # DQ5 인물의 눈·윤곽 색 (4,4,2)
SKIN_WEIGHT = 6                                  # 얼굴 몇 칸뿐인 살색·흰자가 공용 줄에서 옷 색에 합쳐지지 않게 무겁게 센다
# NDS 사람은 거의 같은 살색 세 톤(밝은 곳·살·그늘)을 쓴다. 조금씩 다른 값을 이 셋으로 모아, 15색 한 줄을 나눠 쓰는
# 인물들이 살색 칸을 함께 쓰게 한다(따로 두면 옷 색에 밀려 얼굴이 어두워진다)
SKIN = ((231, 214, 189), (222, 173, 140), (181, 115, 74))
WHITE = (248, 248, 248)                          # 눈 흰자. 인물마다 조금씩 다른 흰색을 이 값으로 모아 줄마다 한 칸을 함께 쓴다
COMMON = SKIN + (INK, WHITE)
LOAD_SLACK = 9                                   # 맵 그룹의 줄 색 수가 가장 적은 줄보다 이만큼 많은 줄까지 후보로 둔다
SKIN_NEAR = 9                                    # 이 Lab 거리 안이면 같은 살색으로 본다
INK_WEIGHT = 30                                  # 눈 몇 칸뿐인 INK 가 공용 줄에서 갈색에 합쳐지지 않게 무겁게 센다
ACCENT_SHARE = 0.06                               # 주요·상징 인물의 색마다 그 인물 옷 색 무게의 이 몫을 바닥으로 준다
TOWN_WEIGHT = 4                                   # 맵 그룹마다 서 있는 상인은 조금 무겁게 센다. 1 이면 초록 셋이 한 칸에 합쳐져 윗옷·바지·모자가 한 덩어리가 된다
KEY_WEIGHT = 16                                  # 주요·상징 인물은 줄 색을 정할 때 이만큼 무겁게 센다. 마을 사람과 한 줄을 써도 제 색이 남는다
SLIME = 'h180'                                   # 사람이 아니지만 눈을 찍는 시트
STEP_TOP = 16                                    # 걸음 두 장은 이 줄부터만 다르다(DQ5 실측, 머리 타일을 함께 쓴다)
DARK_L, DARK_SHARE = 15, 0.34                    # Lab 밝기 15 아래를 눈·외곽선으로 봄(더 느슨하면 얼굴 그늘까지 검어짐)
PROLOGUE = dq4chapterbox.PROLOGUE.where[0]       # 서장 마을(FC 14/00, 5장 첫머리도 같은 마을)
COMPANION_PICTURES = '05:D9D5'                     # 사람 동료 그림 표(인물 번호 → 그림)
LEADER_PICTURES = (0x2B, 0x2E)                     # 일행 0번: 실내 02:CA5A, 바깥 05:D98F


def mirror_sides(cells):
    """왼쪽 보기를 오른쪽 보기의 좌우 반전으로(DQ5 칸의 반전 비트로 타일을 나눠 씀)."""
    cells['left'] = [c.transpose(Image.Transpose.FLIP_LEFT_RIGHT) for c in cells['right']]


def still(cells, names):
    for name in names:
        cells[name] = [cells[name][0], cells[name][0].copy()]


# 타일 한도를 넘을 때 차례로 낮추는 단계(주요 인물은 새 세트로 한도를 넓히고 낮추지 않는다)
DEGRADE = (
    ('왼쪽=오른쪽 반전', mirror_sides),
    ('위 걸음 멈춤', lambda c: still(c, ('up',))),
    ('앞 걸음 멈춤', lambda c: still(c, ('down',))),
    ('모든 걸음 멈춤', lambda c: still(c, ('down', 'left', 'right', 'up'))),
)


class Person:
    def __init__(self, pictures, group, sheet, role, anim='legs', main=False, palette=None, new_set=None, spare=None,
                 allow=None, outline=False, flag=None, leader=False, seen=None, face=False, weight=None, glasses=False, brows=False, copy=None, touch=None, whites=(),
                 line=None):
        self.pictures, self.group, self.sheet, self.role = pictures, group, sheet, role
        # seen: 사건이 놓는 인물처럼 롬의 인물 목록에 없는 그림이 나올 맵 그룹들. 그 그룹의 줄 색에만 넣는다
        # (목록에서 찾지 못한 그림은 모든 그룹으로 세어 다른 그룹의 색을 흐린다)
        self.seen = frozenset(seen) if seen is not None else None
        self.anim, self.main, self.palette, self.new_set, self.spare = anim, main, palette, new_set, spare
        # flag = (7E:2190 바이트, 마스크): 그 깃발이 켜져 있을 때만 전용 팔레트 줄을 이 인물의 색으로 덮는다
        self.outline, self.flag, self.face = outline, flag, face
        # touch: {방향: [(x, y, 무엇)]}. 줄인 16x24 그림의 칸 하나를 손본다. 무엇은 'ink'(눈 색), 'white', 또는 색을
        # 베낄 칸 (x, y). 눈 자리·모자 무늬처럼 규칙으로는 원작 인상이 안 나오는 몇 칸에만 쓴다
        self.touch = touch or {}
        # line: 공용 줄을 이 번호로 못박는다. 세트 팔레트 표를 거치지 않고 그려지는 인물은 엔진이 쓰는 줄과 다른
        # 줄에 넣으면 색이 깨진다
        self.line = line
        self.whites = whites                           # 흰자를 규칙 대신 touch 로 직접 찍는 방향들(눈 자리를 옮긴 얼굴)
        self.copy = copy                               # (베낄 쪽, 받을 쪽): 한쪽 옆모습만 잘 나오는 인물은 그쪽을 뒤집어 쓴다
        self.brows = brows                             # 눈 위의 눈썹을 지우지 않고 갈색으로 둔다(눈썹이 인상인 인물)
        self.glasses = glasses                         # 눈 옆 흰 점(안경알)을 지우지 않는다
        # 공용 팔레트 줄에서 이 인물의 색을 얼마나 무겁게 셀지
        self.weight = weight if weight is not None else (KEY_WEIGHT if main else 1)
        # leader: 깃발이 켜져 있으면 일행 0번 그림(2B·2E)도 이 인물의 세트로(실내는 02:CA5A 가 늘 2B 를 둔다)
        self.leader = leader
        # 타일이 모자랄 때 낮춰도 되는 단계(이름). 주요 인물은 기본으로 낮추지 않고 큰 세트로 옮긴다
        self.allow = allow if allow is not None else (() if main else tuple(n for n, _ in DEGRADE))


# 2장 사건이 놓는 인물(이름, 그림 번호, NDS 시트, 나오는 맵 그룹, 걸음). 그림 번호는 DQ4 인물 목록·PEOPLE·엔진이 쓰지 않고
# 말 걸기에서 건너뛰지 않는(05:862F) 그림이라, 그 그림의 세트를 그 자리에서 바꾸고 훅 줄을 두지 않는다. 사건 모듈은
# 이 번호를 인물 목록 엔트리의 그림으로 쓴다. 시트는 같은 장면의 NDS 오브젝트 모습 번호와 화자 이름(대회 상대는 그
# 오브젝트가 부르는 전투 번호)으로 골랐다
EVENT_PEOPLE = (
    ('검은 망토', 0x16, 'h041', 0x3D, 'legs'),      # 프레놀 mdout 黒マント男
    ('무희 메이', 0x77, 'h026', 0x3D, 'legs'),      # 프레놀 mdout 踊り子（にせアリーナ）
    ('가짜 크리프트', 0x02, 'h023', 0x3D, 'legs'),  # 프레놀 여관 mdy1f2 神官男（にせクリフト）
    ('카멜레온 맨', 0x10, 'h155', 0x3D, 'frames'),  # 텐페 제단 mcout2 전투 9E 의 가운데
    ('날뛰는 석상', 0x31, 'h178', 0x3D, 'frames'),  # 같은 장면의 양옆 둘
    ('엘프', 0x37, 'h043', 0x45, 'legs'),           # 서쪽 탑 tbf5 エルフ
    ('미스터 한', 0x60, 'h032', 0x40, 'legs'),      # 엔돌 투기장 cccf2 전투 9F (FC 특수 전투 07)
    ('라고스', 0x89, 'h019', 0x40, 'legs'),         # 전투 A0 (FC 08)
    ('비비안', 0x1C, 'h085', 0x40, 'legs'),         # 전투 A1 (FC 09)
    ('사이몬', 0x1D, 'h191', 0x40, 'frames'),         # 전투 A2 (FC 0A)
    ('베로린맨', 0x34, 'h187', 0x40, 'frames'),     # 전투 A3 (FC 0B)
)
EVENT_PICTURES = {role: pic for role, pic, *_ in EVENT_PEOPLE}
# 고르게 줄이면 이마 선(M 자)이 뭉개지는 사건 인물. 얼굴 줄을 지키는 솎기로 줄인다
FACE_KEPT = frozenset({'미스터 한'})
# 사건 인물 가운데 색이 틀어지면 딴 인물로 보이는 것. 줄 색을 정할 때 주요 인물처럼 무겁게 센다
KEY_EVENT = frozenset({'엘프', '검은 망토', '카멜레온 맨', '비비안'})


# NDS 시트는 같은 맵의 NDS 스크립트 오브젝트 모습 번호(+04)와 그 대사의 화자 이름으로 골랐다
# (nds/dq4/tools/ndsscript.py dump, 서장·1장 그룹). 1장 그림 번호는 dq4npcport.PICTURES 와 dq4chapter1·dq4prologue 의 것
PEOPLE = (
    # 옆모습 눈 뒤쪽에 남는 초록 한 칸(눈동자의 초록) 자리에 흰자를 찍는다
    Person(LEADER_PICTURES, PROLOGUE, 'h100', '천공의 용사', main=True, palette=7, new_set=0x70, whites=('left', 'right'),
           touch={'left': [(5, 8, 'white'), (5, 9, 'white')], 'right': [(9, 8, 'white'), (9, 9, 'white')]}),
    Person(LEADER_PICTURES, None, 'h106', '라이언', main=True, palette=6, new_set=0x71, face=True),
    Person((0x5B,), None, 'h130', '호이민', anim='frames', main=True, palette=5, spare=0x58),
    Person((0x14,), None, 'h036', '왕', main=True, spare=0x18),
    Person((0x01,), None, 'h034', '대신', main=True, brows=True),
    Person((0x04,), None, 'h038', '귀부인', main=True, spare=0x72),
    # 원래 세트들이 모자라 주요 인물은 원래 타일이 큰, 쓰지 않는 그림 번호의 새 세트로 잇는다. 피사로의 부하는
    # 46타일이라 그런 자리가 없어 옆을 반전으로 나눠 쓴다(몬스터라 좌우 차이가 작다)
    Person((0x9B,), None, 'h153', '피사로의 부하', anim='frames', main=True, spare=0x6F,
           allow=('왼쪽=오른쪽 반전',)),
    Person((0x0E,), PROLOGUE, 'h143', '신시아', main=True, spare=0x2D),
    # 개구리는 서장에만 나오고 그림 50 은 다른 그룹에서 슬라임이라, 개구리는 쓰지 않는 그림 93 의 세트를 빌린다
    Person((0x50,), PROLOGUE, 'h174', '개구리', anim='frames', main=True, outline=True, spare=0x93),  # 풀·나뭇잎과 같은 초록이라
    # 지하 수련의 검사는 스크립트가 붙은 엔트리(dq4prologue.MASTER_SRC)라 세트 팔레트 표와 상관없이 OBJ 팔레트 0 으로
    # 그려진다(수련 장면의 OAM 실측)
    Person((0x08,), PROLOGUE, 'h019', '검사', main=True, spare=0x90, line=0),
    # 줄 1: 색 거리만 재면 신시아가 쓰는 빌린 줄에 들어, 윗옷 노랑이 신시아의 색에 밀려 살색으로 실린다
    Person((0x17,), PROLOGUE, 'h003', '어머니', spare=0x39, line=1),
    Person((0x09,), PROLOGUE, 'h002', '아버지', spare=0x8D),
    Person((0x1F,), PROLOGUE, 'h039', '장로', main=True, spare=0x9C, brows=True, copy=('left', 'right')),
    Person((0x06,), None, 'h015', '병사', weight=KEY_WEIGHT),
    Person((0x67,), None, 'h017', '위병', weight=KEY_WEIGHT),
    # 투구 코 가리개 때문에 두 눈이 네 칸 떨어져 찍히고 가리개 자국이 눈 사이에 남는다. 오른쪽 눈을 한 칸 안으로
    # 옮기고 눈 사이를 살색으로 둔다. 오른쪽 보기는 투구에 눈이 가려 왼쪽을 뒤집어 쓴다
    Person((0x08,), None, 'h018', '전사', copy=('left', 'right'), whites=('down',),
           touch={'down': [(10, 7, 'white'), (10, 8, 'white'), (11, 7, (11, 9)), (11, 8, (11, 9)),
                           (9, 7, 'ink'), (9, 8, 'ink'), (8, 7, (7, 7)), (8, 8, (7, 8)),
                           (5, 7, 'white'), (5, 8, 'white'), (9, 6, (8, 6))]}),
    # 두 눈 사이에 그늘 살색이 세로로 석 줄 이어져 앞머리가 얼굴 가운데로 내려온 것처럼 보인다. 밝은 살색으로 둔다.
    # 왼쪽 눈 위로 내려온 어두운 머리 두 칸은 옆 머리 색으로 고른다
    Person((0x0B,), None, 'h007', '남자아이',
           touch={'down': [(5, 9, (4, 9)), (6, 9, (7, 9)), (7, 10, (6, 10)), (7, 11, (6, 10)), (7, 12, (6, 10))]}),
    # NDS 는 흰자 바깥에 어두운 테두리 한 칸과 머리카락이 있고, 눈 아래 볼이 눈과 같은 폭(여섯 칸)이다. 줄이면
    # 화면 왼쪽의 테두리와 볼 한 칸이 빠져, 흰자가 밝은 머리카락에 붙고 턱이 눈보다 좁아진다. 오른쪽과 같게 채운다
    Person((0x17,), None, 'h001', '여자',
           # 턱: NDS 는 볼 아래에 턱 줄(그늘·살·살·그늘)이 있고 그 밑을 어두운 줄이 받친다. 줄이면 그 어두운 줄이
           # 살색 그늘로 바뀌어 턱 아래로 얼굴이 이어져 보인다. 턱 양끝을 그늘로, 그 밑 줄을 어두운 색으로 둔다
           touch={'down': [(2, 5, (11, 5)), (2, 6, (11, 6)), (3, 5, (10, 5)), (3, 6, (10, 6)), (4, 7, (5, 7)),
                           (5, 8, (6, 9)), (8, 8, (6, 9)), (6, 9, (5, 9)), (7, 9, (5, 9)), (8, 9, (5, 9))]}),
    Person((0x03,), None, 'h000', '남자'),
    Person((0x09,), None, 'h005', '노인'),
    Person((0x29,), None, 'h030', '농부'),
    Person((0x38,), None, 'h002', '아저씨'),
    Person((0x15,), None, 'h021', '신부'),
    # 얼굴이 흰 두건에 싸여 있어 눈 흰자가 두건과 한 덩어리가 된다. 흰자 옆과 위의 두건 칸을 두건의 그늘 색으로
    # 두어 흰자가 따로 보이게 한다
    Person((0x05,), None, 'h022', '수녀',
           touch={'down': [(4, 8, (3, 8)), (5, 7, (3, 8)), (10, 7, (3, 8)), (11, 9, (11, 8))],
                  'right': [(8, 8, (7, 8)), (9, 7, (6, 7)), (8, 7, (6, 7))]}),
    Person((0x1F,), None, 'h033', '학자', glasses=True),
    Person((0x20,), None, 'h044', '개', anim='frames', spare=0x75),
    Person((0x19,), None, 'h003', '아주머니'),
    Person((0x07,), None, 'h011', '거친 남자'),
    Person((0x82,), None, 'h029', '하녀', spare=0x5D),
    Person((0x0C,), None, 'h031', '시인', spare=0x92),
    Person((0x40,), None, 'h009', '상인', weight=TOWN_WEIGHT),
    # 줄 0: 상인을 무겁게 센 배정에서 다른 줄에 두면 몸의 파랑이 보라로 실린다(줄마다 넣어 본 결과)
    Person((0x50,), None, 'h180', '슬라임', anim='frames', weight=KEY_WEIGHT, line=0),
    # FC 그림 25 의 고양이(「にゃーん」). NDS 이무르 may1f2 의 ネコ 가 모습 2F(h047). DQ5 에 고양이 그림이 없어 쓰지 않는
    # 그림 24 의 세트에 싣는다
    Person((0x24,), None, 'h047', '고양이', anim='frames'),
    # 2장 일행. 크리프트·브라이는 사람 동료 그림 표(COMPANION_PICTURES)의 인물 09·05 칸이 그림을 고른다
    # 얼굴이 다섯 칸이라 규칙은 눈 사이를 한 칸만 띄운다. 오른쪽 눈을 한 칸 밖으로 옮기고 그 옆 그늘을 살색으로
    Person((ALENA_PICTURE,), None, 'h109', '아리나', main=True, palette=7, flag=CHAPTER2, leader=True, whites=('down',),
           touch={'down': [(8, 7, (7, 7)), (8, 8, (7, 8)), (9, 7, 'ink'), (9, 8, 'ink'), (9, 6, (7, 8)),
                           (5, 7, 'white'), (5, 8, 'white'), (10, 7, 'white'), (10, 8, 'white')]}),
    # 얼굴이 여섯 칸 x 네 줄뿐이다. 앞모습은 눈을 모자 띠 바로 아래 줄부터 두 칸 높이로 올려 눈 아래에 살색 두
    # 줄을 남긴다. 오른쪽 눈은 얼굴 가장자리에서 한 칸 안으로 옮기고, 모자 띠로 내려온 장식은 띠 색으로, 띠 아래
    # 이마의 앞머리 두 칸은 살색으로 둔다. 옆모습은 올리면 눈이 옆머리에 붙어 안 보이므로 규칙이 찍은 자리 그대로다
    Person((KIRYL_PICTURE,), None, 'h112', '크리프트', main=True, palette=6, flag=CHAPTER2, whites=('down',),
           touch={'down': [(11, 8, (9, 8)), (11, 9, (9, 9)), (8, 9, (9, 9)), (8, 6, (7, 6)),
                           (9, 7, (9, 9)),
                           (8, 7, 'ink'), (8, 8, 'ink'), (10, 7, 'ink'), (10, 8, 'ink'),
                           (7, 7, 'white'), (7, 8, 'white'), (11, 7, 'white'), (11, 8, 'white')]}),
    # 흰 눈썹이 눈을 감싸는 얼굴이다: 눈은 한 칸 높이로 한 칸씩 왼쪽에 찍고, 바깥쪽 옆을 흰색으로 둔다
    Person((BREY_PICTURE,), None, 'h115', '브라이', main=True, palette=5, flag=CHAPTER2, whites=('down',),
           touch={'down': [(7, 9, (8, 9)), (7, 10, (8, 10)), (10, 9, 'white'), (10, 10, (8, 10)),
                           (6, 9, 'ink'), (9, 9, 'ink'), (5, 9, 'white')]},
           copy=('left', 'right')),                   # 오른쪽 보기는 흰 눈썹에 눈이 가려 왼쪽을 뒤집어 쓴다
    # 2장 그룹(3D·45)의 인물. 시트는 NDS 스크립트 오브젝트의 모습 번호(= 시트 번호)와 그 대사의 화자 이름으로 골랐다
    Person((0x0E,), None, 'h035', '공주', main=True),
    Person((0x3D,), None, 'h013', '죄수', spare=0x9E),
    Person((0x45,), None, 'h071', '호빗'),
    Person((0x1A,), None, 'h009', '초록 모자 상인', spare=0x70, weight=TOWN_WEIGHT),
    Person((0x26,), None, 'h048', '말', anim='frames', spare=0x5E),
    *(Person((pic,), None, sheet, role, anim=anim, spare=pic, seen=(group,), face=role in FACE_KEPT,
             weight=KEY_WEIGHT if role in KEY_EVENT else None)
      for role, pic, sheet, group, anim in EVENT_PEOPLE),
)
SHARED_LINES = (0, 1, 2, 3, 4)
# 일행 줄(5·6·7) 가운데 그 맵 그룹에서 일행이 쓰지 않는 줄. 서장에는 용사(7)뿐이고, 1장 그룹에는 라이언(6)과
# 호이민(5)뿐이다. 나오는 그룹이 모두 여기 드는 인물은 그 줄도 쓴다(그 그룹의 줄 색을 맵 팔레트로 덮는다).
# 2장 그룹은 세 줄 모두 2장 일행이 쓴다
LENT_LINES = {PROLOGUE: (5, 6), **{g: (7,) for g in range(0x36, 0x3C)}}
HOOK_SITES = ('1F:CF45', '03:D202')
LOAD_SET = bytes.fromhex('bf d0 86 25')                  # LDA $2586D0,X
MAP_GROUP = 0x7E00BC
DQ4_GROUPS = frozenset(range(0x36, 0x46))            # dq4groupbuild 가 만드는 DQ4 맵 그룹
# 원래 자리에 들어가지 않는 타일 자료를 나눠 담는 곳(뱅크 3F 이하여야 레코드가 가리킴). 곡 롬의 0 끝 줄 안. 3F 는 앞쪽을
# 인물 목록(dq4chapter1.NPC_BANK, 인라인 스크립트 포함)이 쓰므로 그 끝과 겹치지 않게 띄운다
# 3C:F040~ 는 그룹 빌드(3A~3F)가 채운 뒤 남는 끝자리. 36·37 은 대화 스크립트·대체 목록(dq4chapter1.TALK_BANK·NPC_ALT)이라 쓰지 않는다.
# 39 도 레코드 자리의 마지막이지만 레코드는 앞(8000)부터 차므로 끝 4KB 만 쓴다. 레코드가 거기까지 자라면 tile_areas 가
# 쓰인 끝 뒤로 미루고, 자리가 모자라면 멈춘다
TILE_AREAS = (('3E:D700', 0xFC00 - 0xD700), ('3F:EB80', 0x10000 - 0xEB80), ('3C:F040', 0xFE00 - 0xF040),
              ('39:F000', 0x10000 - 0xF000))
PALETTES_AT, HOOK_AT = '3D:EA00', '3E:FC00'
MAP_PALETTES_AT = '3D:EB60'                       # 맵 팔레트 줄 루틴·표를 옮길 곳(세트 팔레트 표 뒤 빈 자리)


def cpu(text):
    bank, addr = text.split(':')
    return int(bank, 16) << 16 | int(addr, 16)


def frames(sheet, anim, pick=(0, 1)):
    """방향마다 (프레임 0, 프레임 1) RGBA. 같은 방향의 두 장은 같은 상자로 잘라야 몸이 흔들리지 않는다."""
    im = Image.open(sheet).convert('RGBA')
    rows = ROWS8 if im.height == 256 else ROWS4
    out = {}
    for name, row in rows:
        strip = im.crop((0, row * 32, im.width, row * 32 + 32))
        on = [any(strip.getpixel((x, y))[3] for y in range(32)) for x in range(im.width)]
        runs, x = [], 0
        while x < im.width:
            if on[x]:
                start = x
                while x < im.width and on[x]:
                    x += 1
                runs.append((start, x))
            else:
                x += 1
        picked = [strip.crop((runs[k][0], 0, runs[k][1], 32)) for k in pick if k < len(runs)]
        if anim != 'frames' or len(picked) < 2:
            picked = picked[:1] * 2
        width = max(f.width for f in picked)
        boxes = [f.getbbox() for f in picked]
        top, bottom = min(b[1] for b in boxes), max(b[3] for b in boxes)
        pair = []
        for f in picked:
            c = Image.new('RGBA', (width, bottom - top))
            c.paste(f.crop((0, top, f.width, bottom)), ((width - f.width) // 2, 0))
            pair.append(c)
        out[name] = pair
    return out


def shrink(f, scale=SCALE):
    """BOX 축소한 RGBA. 칸마다 NDS 원래 색 가운데 가장 가까운 색으로 되돌리되, 칸에 어두운 점(눈·외곽선)이
    DARK_SHARE 이상이면 그 어두운 색을 남긴다. 평균만 내면 1~2픽셀 눈과 외곽선이 피부·배경색에 섞여 사라진다."""
    src = f.load()
    pal = sorted({p[:3] for p in f.get_flattened_data() if p[3]})
    w, h = max(1, round(f.width * scale)), max(1, round(f.height * scale))
    small = f.resize((w, h), Image.BOX)
    out = Image.new('RGBA', (w, h))
    for y in range(h):
        for x in range(w):
            p = small.getpixel((x, y))
            if p[3] < 128:
                continue
            box = [src[sx, sy] for sy in range(int(y / scale), min(f.height, math.ceil((y + 1) / scale)))
                   for sx in range(int(x / scale), min(f.width, math.ceil((x + 1) / scale)))]
            solid = [q[:3] for q in box if q[3]]
            dark = [q for q in solid if lab(q)[0] < DARK_L]
            if solid and len(dark) / len(solid) >= DARK_SHARE:
                out.putpixel((x, y), Counter(dark).most_common(1)[0][0] + (255,))
            else:
                out.putpixel((x, y), min(pal, key=lambda c: sum((a - b) ** 2 for a, b in zip(c, p[:3]))) + (255,))
    return out


def is_face(c):
    return 45 <= lab(c)[0] <= 90 and c[0] > c[2] and not is_white(c)


def is_white(c):
    return lab(c)[0] > 88 and max(c) - min(c) < 50


def find_eyes(f, side=False):
    """NDS 프레임의 눈동자: 머리 쪽(위 60%)에서 흰자 바로 옆의 어두운 점. 세로로 이어진 점을 한 눈으로 묶는다.
    [(x, 가운데 y, 색)]. NDS 인물 눈은 흰자 1칸 + 눈동자 1x2 꼴이다."""
    px = f.load()
    lit = lambda x, y: 0 <= x < f.width and px[x, y][3] and is_white(px[x, y][:3])  # noqa: E731
    pupils = {(x, y) for y in range(f.height * 3 // 5) for x in range(2, f.width - 2)
              if px[x, y][3] and lab(px[x, y][:3])[0] < 28}
    eyes = []
    for x in sorted({q[0] for q in pupils}):
        ys = sorted(y for q, y in pupils if q == x)
        runs = [[ys[0]]]
        for y in ys[1:]:
            (runs[-1].append(y) if y == runs[-1][-1] + 1 else runs.append([y]))
        for r in runs:
            if len(r) != 2 or r[0] == 0 or r[-1] + 1 >= f.height:
                continue
            if not any(lit(x - 1, y) or lit(x + 1, y) for y in r):
                continue
            if not (px[x, r[-1] + 1][3] and lab(px[x, r[-1] + 1][:3])[0] >= 45):
                continue
            lights = sum(lit(x + d, y) for d in (-1, 1) for y in r)
            eyes.append((x, sum(r) / len(r), Counter(px[x, y][:3] for y in r).most_common(1)[0][0], lights))
    # 옆모습은 흰자가 가장 많이 붙은 하나, 앞모습은 같은 높이에서 서로 가장 가까운 둘
    if side:
        return [max(eyes, key=lambda e: e[3])[:3]] if eyes else []
    pairs = [(abs(a[0] - b[0]), a, b) for i, a in enumerate(eyes) for b in eyes[i + 1:]
             if a[1] == b[1] and 2 <= abs(a[0] - b[0]) <= 5]
    return [e[:3] for e in min(pairs, key=lambda t: t[0])[1:]] if pairs else []


def pick_even(n, m, cost, keep=()):
    """n 칸에서 m 칸을 고르게 고른다. 버릴 칸은 그 자리 앞뒤 한 칸 가운데 옆 칸과 가장 비슷한(cost 가 작은)
    칸으로 옮긴다. 한 칸짜리 칼·지팡이 열이나 둥근 머리 꼭대기 줄이 통째로 빠지지 않게 한다."""
    if m >= n:
        return list(range(n))
    drop, keep = set(), set(keep)
    for k in range(n - m):
        d = min(n - 1, int((k + 0.5) * n / (n - m)))
        free = lambda i: 0 <= i < n and i not in drop and i not in keep  # noqa: E731
        near = [i for i in (d - 1, d, d + 1) if free(i)] or sorted((i for i in range(n) if free(i)), key=lambda i: abs(i - d))[:1]
        if near:
            drop.add(min(near, key=lambda i: (cost[i], abs(i - d))))
    return [i for i in range(n) if i not in drop]


def likeness(f, across):
    """열(across) 또는 줄마다 앞 열·줄과 다른 점의 수."""
    px = f.load()
    n, m = (f.width, f.height) if across else (f.height, f.width)
    at = (lambda i, j: px[i, j]) if across else (lambda i, j: px[j, i])
    cost = [sum(at(i, j) != at(i - 1, j) for j in range(m)) for i in range(1, n)]
    return [cost[0]] + cost


def thin_lines(f, scale, axis=None, rows=(), cols=()):
    """줄일 때 남길 (열, 줄). 평균을 내지 않고 줄·열을 솎아 NDS 도트와 색을 그대로 둔다. axis(앞·뒤 보기에서 몸
    가운데 열의 두 배)가 있으면 그 축에서 같은 거리의 열을 함께 버려 좌우가 어긋나지 않게 한다. 축은 두 눈의
    가운데다: 상자 가운데로 접으면 칼·지팡이를 든 쪽으로 축이 밀려 머리가 한쪽만 깎인다."""
    w, h = f.width, f.height
    ys = pick_even(h, max(1, round(h * scale)), likeness(f, False), rows)
    cost = likeness(f, True)
    keep = set(cols)
    drop = w - max(1, round(w * scale))
    if axis is None or drop <= 0:
        return pick_even(w, w - drop, cost, keep), ys
    left = [i for i in range(w) if i < axis - i < w]           # 짝이 있는 왼쪽 열
    alone = [i for i in range(w) if not 0 <= axis - i < w]     # 한쪽에만 있는 바깥 열
    pairs = min(len(left), round(drop * 2 * len(left) / w / 2))
    single = min(len(alone), drop - 2 * pairs)
    pairs = min(len(left), pairs + (drop - 2 * pairs - single) // 2)
    kept = pick_even(len(left), len(left) - pairs, [cost[i] + cost[axis - i] for i in left],
                     {k for k, i in enumerate(left) if i in keep or axis - i in keep})
    side = pick_even(len(alone), len(alone) - single, [cost[i] for i in alone], {k for k, i in enumerate(alone) if i in keep})
    xs = {left[k] for k in kept} | {axis - left[k] for k in kept} | {alone[k] for k in side}
    if axis % 2 == 0 and 0 <= axis // 2 < w:
        xs.add(axis // 2)
    return sorted(xs), ys


def thinned(f, xs, ys):
    """남긴 줄·열만 모은 그림. 남긴 칸이 비어 있으면 그 옆의 버린 칸을 쓴다: 뻗친 머리카락·옷자락 끝처럼 한 칸만
    튀어나온 곳이 버린 열에 걸리면 머리가 깎이고 숱이 준다."""
    out = Image.new('RGBA', (len(xs), len(ys)))
    px = f.load()

    def lost(kept, n):
        """남긴 칸마다 그 칸에 딸린 버린 칸들(뒤쪽, 맨 앞 칸은 앞쪽도)."""
        ends = kept[1:] + [n]
        return [list(range(a + 1, b)) + (list(range(kept[0])) if k == 0 else []) for k, (a, b) in enumerate(zip(kept, ends))]
    gone_x, gone_y = lost(list(xs), f.width), lost(list(ys), f.height)
    for j, y in enumerate(ys):
        for i, x in enumerate(xs):
            q = px[x, y]
            if not q[3]:
                q = next((px[u, y] for u in gone_x[i] if px[u, y][3]), None) or \
                    next((px[x, v] for v in gone_y[j] if px[x, v][3]), q)
            out.putpixel((i, j), q)
    return out


def resample(f, scale):
    """NDS 프레임을 고르게 줄인 그림과, 줄인 칸마다의 원래 가운데 (열들, 줄들).

    칸 나눔과 채움은 shrink 와 같다(넓이의 절반 넘게 덮인 칸을 채운다). 그래서 머리숱·옆머리·둥근 윗부분의
    모양이 그대로다. 색만 다르게 고른다: 평균에 가까운 색이 아니라 그 칸에 가장 많이 든 NDS 색 하나를 쓴다.
    평균을 내면 테두리와 속 색이 섞여 흐려진다."""
    src = f.load()
    pal = sorted({q[:3] for q in f.get_flattened_data() if q[3]})
    w, h = max(1, round(f.width * scale)), max(1, round(f.height * scale))
    small = f.resize((w, h), Image.BOX)
    out = Image.new('RGBA', (w, h))
    for y in range(h):
        for x in range(w):
            mean = small.getpixel((x, y))
            if mean[3] < 128:
                continue
            box = [src[sx, sy][:3] for sy in range(int(y / scale), min(f.height, math.ceil((y + 1) / scale)))
                   for sx in range(int(x / scale), min(f.width, math.ceil((x + 1) / scale))) if src[sx, sy][3]]
            count = Counter(box)
            color, top = count.most_common(1)[0]
            dark = [c for c in box if lab(c)[0] < DARK_L]
            if len(dark) / len(box) >= DARK_SHARE:
                # shrink 와 같은 규칙: 눈·수염·테두리 같은 어두운 점은 칸의 3분의 1 만 덮어도 남긴다
                color = Counter(dark).most_common(1)[0][0]
            else:
                # 절반을 넘는 색이 없는 칸(가는 무늬가 걸친 곳)은 shrink 처럼 평균에 가장 가까운 색으로. 어두운 색이
                # 절반을 넘어도 평균이 밝으면(어두운 바탕 위의 밝은 무늬: 모자의 십자, 옷의 선) 밝은 쪽을 남긴다
                blend = min(pal, key=lambda c: sum((u - v) ** 2 for u, v in zip(c, mean[:3])))
                if top * 2 <= len(box) or (lab(color)[0] < 45 and lab(blend)[0] >= 50):
                    color = blend
            out.putpixel((x, y), color + (255,))
    return out, [min(f.width - 1, int((x + 0.5) / scale)) for x in range(w)], \
        [min(f.height - 1, int((y + 0.5) / scale)) for y in range(h)]


def dot_eyes(eyes, s, xs, ys, whites=False, brows=False, facing=0, sclera=True):
    """줄인 얼굴에 NDS 눈동자 자리마다 INK 1x2 점을 찍는다. 눈 옆의 흰자와, 눈에 붙은 어두운 칸(눈썹·머리카락 끝)은
    살색으로 덮는다: 붙어 있으면 눈이 ㄱ 자가 되거나 머리카락과 이어져 눈이 안 보인다."""
    px = s.load()
    spots = []
    for x, y in eyes:
        i = min(range(len(xs)), key=lambda k: abs(xs[k] - x))
        j = min(min(range(len(ys)), key=lambda k: abs(ys[k] - y)), len(ys) - 2)
        spots.append((i, j))
    solid = lambda u, v: 0 <= u < s.width and 0 <= v < s.height and px[u, v][3]  # noqa: E731
    if len(spots) == 2 and abs(spots[0][0] - spots[1][0]) < 3:
        # 줄이면 두 눈이 한 칸 사이로 몰리거나 맞붙는다. 눈 줄의 얼굴(어둡지 않은 칸이 이어진 곳)이 여섯 칸
        # 넘게 넓으면 그 가운데에서 두 칸을 띄우고(DQ5 인물), 좁으면 한 칸을 띄운다
        (a, j), (b, _) = sorted(spots)
        light = lambda u: solid(u, j) and lab(px[u, j][:3])[0] >= 45  # noqa: E731
        lo, hi = a, b
        while light(lo - 1) or lo - 1 in (a, b):
            lo -= 1
        while light(hi + 1) or hi + 1 in (a, b):
            hi += 1
        gap = 3 if hi - lo + 1 >= 6 else 2
        a = (lo + hi + 1 - gap) // 2
        spots = [(a, j), (a + gap, j)]
    dots = {(i, j + d) for i, j in spots for d in (0, 1)}
    face = Counter(px[u, v][:3] for i, j in spots for v in range(j, min(s.height, j + 5)) for u in range(max(0, i - 2), min(s.width, i + 3))
                   if px[u, v][3] and is_face(px[u, v][:3]) and px[u, v][1] > px[u, v][2] + 15)
    tone = face.most_common(1)[0][0] if face else None
    dark = lambda u, v: solid(u, v) and (u, v) not in dots and lab(px[u, v][:3])[0] < 45  # noqa: E731
    for i, j in spots:
        if tone:
            for dy in (0, 1):
                for sign in (-1, 1):
                    # 눈에 이어 붙은 흰자만(한 칸, 이어지면 두 칸). 떨어진 흰 칸은 수염·눈썹·투구 장식이다
                    for dx in (sign, 2 * sign):
                        u, v = i + dx, j + dy
                        if not (solid(u, v) and (u, v) not in dots and not whites and is_white(px[u, v][:3])):
                            break
                        px[u, v] = tone + (255,)
                for dx in (-1, 1):
                    if dark(i + dx, j + dy):
                        px[i + dx, j + dy] = tone + (255,)
            # 눈 위와 그 대각선의 어두운 칸(머리카락 끝, 눈썹, 눈을 내릴 자리가 없던 챙)도 살색으로 떼어 낸다. 눈과
            # 대각선으로 이어진 눈썹은 앞모습에서 치켜뜬 눈처럼 보인다
            browns = [c for c in {q[:3] for q in s.get_flattened_data() if q[3]} if 28 <= lab(c)[0] <= 50 and c[0] > c[2]]
            # 눈썹을 남기는 인물은 대각선 위까지(사선 눈썹), 그 밖의 인물은 바로 위 한 칸만. 대각선까지 지우면 이마로
            # 내려온 앞머리가 통째로 사라져 이마가 벗겨진다
            for dx in ((-1, 0, 1) if brows else (0,)):
                # 눈 위가 검은 머리카락·챙이면 눈과 한 덩어리가 된다. 갈색 눈썹·앞머리(조금 밝은 색)는 검은 눈과
                # 구분되므로 둔다: 지우면 이마가 넓게 비고 눈만 남아 얼굴이 밋밋해진다
                if dark(i + dx, j - 1) and (brows or lab(px[i + dx, j - 1][:3])[0] < 28):
                    # 눈썹이 인상인 인물은 NDS 눈썹 모양(사선)을 그대로 두고 눈보다 밝은 갈색으로 바꾼다. 눈과 같은
                    # 색이면 눈과 이어져 치켜뜬 눈처럼 보인다. 그 밖의 인물은 살색으로 지운다
                    px[i + dx, j - 1] = (min(browns, key=lambda c: lab(c)[0]) if brows and browns else tone) + (255,)
        px[i, j] = px[i, j + 1] = INK + (255,)
    if sclera:
        # 눈동자 옆에 흰자 1x2 를 NDS 원작의 방향대로 찍는다. 실측: 앞모습은 두 눈의 바깥쪽(25쌍 중 22), 왼쪽 보기는
        # 눈동자 오른쪽(29 중 25), 오른쪽 보기는 왼쪽(28 중 24), 곧 옆모습은 얼굴 뒤쪽이다. 눈동자 앞쪽에는 찍지 않고,
        # 몸 밖이거나 살색보다 어두운 칸(머리카락)이면 찍지 않는다
        for (i, j), dx in zip(sorted(spots), [-facing] * len(spots) if facing else [-1, 1]):
            for v in (j, j + 1):
                if solid(i + dx, v) and (i + dx, v) not in dots and lab(px[i + dx, v][:3])[0] >= 45:
                    px[i + dx, v] = WHITE + (255,)
    if brows and tone and spots:
        browns = [c for c in {q[:3] for q in s.get_flattened_data() if q[3]} if 28 <= lab(c)[0] <= 50 and c[0] > c[2]]
        if browns and facing:
            # 옆모습은 줄이면서 눈썹이 빠진다. 눈 위에 뒤통수 쪽으로 두 칸을 그린다
            brown = min(browns, key=lambda c: lab(c)[0])
            for i, j in spots:
                for u in (i, i - facing):
                    if solid(u, j - 1) and (u, j - 1) not in dots:
                        px[u, j - 1] = brown + (255,)
        if not facing and len(spots) == 2:
            # 콧수염 사이에 남은 살색 한두 칸이 부리처럼 보인다. 양옆이 수염인 칸은 수염 색으로 메운다
            (a, j), (b, _) = sorted(spots)
            for v in range(j + 2, min(s.height, j + 5)):
                for u in range(a, b + 1):
                    if solid(u, v) and is_face(px[u, v][:3]) and dark(u - 1, v) and dark(u + 1, v):
                        px[u, v] = px[u - 1, v]


def eye_spots(f, side, skin=True, level=None):
    """눈동자 자리 [(x, 윗줄 y)]. find_eyes 가 못 찾는 얼굴까지: 흰자 바로 옆의 어두운 점(한두 칸)이고 그 아래가
    얼굴인 것. 앞모습은 가운데를 사이에 둔 같은 줄의 짝, 옆모습은 흰자가 가장 많이 붙은 하나."""
    # level: 앞모습 눈이 발에서 몇 줄 위인지. 옆모습 눈은 그 높이 둘레에서만 찾는다(모자 장식의 흰 점을 눈으로
    # 잡지 않게)
    ok = lambda y: level is None or abs((f.height - y) - level) <= 2  # noqa: E731
    found = [(x, int(y)) for x, y, _ in find_eyes(f, side) if ok(int(y))]
    if found:
        return found
    px = f.load()
    lit = lambda x, y: 0 <= x < f.width and 0 <= y < f.height and px[x, y][3] and is_white(px[x, y][:3])  # noqa: E731
    dark = lambda x, y: 0 <= y < f.height and px[x, y][3] and lab(px[x, y][:3])[0] < 45  # noqa: E731
    box = f.getbbox()
    cands = []
    for y in range(box[1] + 2, box[1] + (box[3] - box[1]) * (3 if skin else 4) // 5):
        for x in range(1, f.width - 1):
            if not ok(y) or not dark(x, y) or not (lit(x - 1, y) or lit(x + 1, y)):
                continue
            if dark(x, y - 1) and (lit(x - 1, y - 1) or lit(x + 1, y - 1)):
                continue                                   # 위 칸이 이미 같은 눈동자
            below = [px[x, y + d][:3] for d in (1, 2, 3) if y + d < f.height and px[x, y + d][3]]
            if skin and not any(is_face(c) for c in below):
                continue
            whites = sum(lit(x + d, y + e) for d in (-1, 1) for e in (0, 1))
            cands.append((x, y, whites))
    if side:
        return [max(cands, key=lambda e: e[2])[:2]] if cands else []
    mid = (box[0] + box[2] - 1) / 2
    # 가운데에 가까운 짝, 그다음 서로 가까운 짝(투구 볼가리개·귀걸이의 흰 점보다 안쪽이 눈이다)
    pairs = [((0, 0) if skin else (-(a[2] + b[2]), 0)) + (round(abs((a[0] + b[0]) / 2 - mid)), abs(a[0] - b[0]), -(a[2] + b[2]), a, b)
             for i, a in enumerate(cands) for b in cands[i + 1:]
             if a[1] == b[1] and 2 <= abs(a[0] - b[0]) <= 7 and abs((a[0] + b[0]) / 2 - mid) <= 2]
    return [e[:2] for e in min(pairs)[5:]] if pairs else []


def sharpen_eyes(f, s, name, wide=False, skin=True, known=None):
    """줄인 얼굴의 눈 줄에서 번진 흰자·눈동자를 살색으로 지우고, NDS 눈동자 자리마다 그림에서 가장 어두운 색으로
    1x2 점을 찍는다(DQ5 인물 눈 실측 1x2). 갈색 눈동자를 그대로 쓰면 22줄에서 흐려 보인다."""
    if name == 'up':
        return
    eyes = eye_spots(f, name != 'down', skin) if wide else [(x, y) for x, y, _ in find_eyes(f, side=name != 'down')]
    eyes = eyes or known or []
    if not eyes:
        return []
    px = s.load()
    sx, sy = s.width / f.width, s.height / f.height
    spots = [(min(s.width - 1, int((x + 0.5) * sx)), min(s.height - 2, int(y * sy))) for x, y in eyes]
    face = [px[x, y][:3] for y in range(s.height * 3 // 5) for x in range(s.width)
            if px[x, y][3] and lab(px[x, y][:3])[0] >= 45 and not is_white(px[x, y][:3])]
    ink = min((px[x, y][:3] for y in range(s.height) for x in range(s.width) if px[x, y][3]), key=lambda c: lab(c)[0])
    for x, y in spots:
        for cy in (y, y + 1):
            for cx in (x - 1, x + 1):
                if 0 < cx < s.width - 1 and px[cx, cy][3] and px[cx - 1, cy][3] and px[cx + 1, cy][3] \
                        and (cx, cy) not in spots and (cx, cy - 1) not in spots \
                        and (lab(px[cx, cy][:3])[0] < 35 or is_white(px[cx, cy][:3])):
                    near = [px[cx, cy + d][:3] for d in (-1, 2, -2) if 0 <= cy + d < s.height and px[cx, cy + d][3]]
                    near = [c for c in near if c in face] or face
                    if near:
                        px[cx, cy] = Counter(near).most_common(1)[0][0] + (255,)
        px[x, y] = px[x, y + 1] = (INK if wide else ink) + (255,)
    return eyes


def rgb_frames(person, assets, outlined=True):
    """{방향: [16x24 RGBA 걸음 0, 걸음 1]}. 걸음 규칙까지 들어간 것."""
    out = {}
    # 사람 시트는 방향마다 걸음 셋(왼발·선 자세·오른발)이다. 양쪽 걸음 두 장을 쓴다
    legs = person.anim == 'legs'
    sheet = frames(assets / FIELD / f'{person.sheet}.png', 'frames', (0, 2)) if legs else \
        frames(assets / FIELD / f'{person.sheet}.png', person.anim)
    scale = SCALE
    if legs:
        # 모자·투구가 상자를 넘으면 위가 잘려 납작해진다. 가장 큰 프레임이 상자에 들어가게 온몸을 그만큼 더 줄인다
        # 폭은 맞추지 않는다(날개·칼 끝이 16칸을 넘으면 양옆을 자른다). 맞추면 얼굴까지 작아진다
        scale = min(SCALE, TALL / max(f.height for pair in sheet.values() for f in pair))
    floor = TALL if legs else BOTTOM
    eyed = legs or person.sheet == SLIME
    axis = level = None
    for name, pair in sheet.items():
        cells, known = [], None
        lines = None
        if legs:
            # 눈 줄과 그 아래 한 줄은 버리지 않는다. face 인물(투구·수염으로 얼굴이 몇 줄뿐)은 눈 위 한 줄부터
            # 수염 줄까지와 눈 둘레 열도 남긴다
            spots = eye_spots(pair[0], name != 'down', level=None if name == 'down' else level) if name != 'up' else []
            if name == 'down' and spots:
                level = pair[0].height - spots[0][1]
            rows = {y + d for _, y in spots for d in (range(-1, 4) if person.face else range(0, 3))}
            cols = {x + d for x, _ in spots for d in (range(-2, 3) if person.face else range(-1, 2))}
            if name == 'down' and len(spots) == 2:
                axis = spots[0][0] + spots[1][0]
            lines = thin_lines(pair[0], scale, axis if name in ('down', 'up') else None, rows, cols)
        for f in pair:
            if legs and person.face:
                s = thinned(f, *lines)
                if name != 'up':
                    dot_eyes(spots, s, *lines, person.glasses, person.brows, {'left': -1, 'right': 1}.get(name, 0),
                             name not in person.whites)
            elif legs:
                s, xs, ys = resample(f, scale)
                if name != 'up':
                    dot_eyes(spots, s, xs, ys, person.glasses, person.brows, {'left': -1, 'right': 1}.get(name, 0),
                             name not in person.whites)
            else:
                s = shrink(f, scale)
                # 튀어 오르는 둘째 프레임에서 눈을 못 찾으면 첫 프레임의 자리에 찍는다(눈이 깜빡이듯 사라진다)
                known = sharpen_eyes(f, s, name, wide=eyed, skin=legs, known=known if cells else None)
            cut, ox = max(0, s.width - WIDTH) // 2, (WIDTH - min(WIDTH, s.width)) // 2
            c = Image.new('RGBA', (16, 24))
            c.paste(s.crop((cut, 0, cut + min(WIDTH, s.width), s.height)), (ox, floor - s.height))
            cells.append(c)
        if legs:
            # 세트의 타일 한도가 방향마다 머리·몸통 타일을 두 장이 함께 쓰는 크기다(DQ5 인물도 그렇다). 둘째 장은
            # STEP_TOP 줄부터만 NDS 둘째 걸음으로 바꾼다
            second = cells[0].copy()
            second.paste(cells[1].crop((0, STEP_TOP, 16, 24)), (0, STEP_TOP))
            cells[1] = second
        if outlined and legs:
            for c in cells:
                shade_edge(c)
        elif outlined and person.outline:
            for c in cells:
                outline(c)
        out[name] = cells
    if legs:
        common_skin(out)
    for name, edits in person.touch.items():
        for c in out[name]:
            for x, y, what in edits:
                color = INK if what == 'ink' else WHITE if what == 'white' else c.getpixel(what)[:3]
                c.putpixel((x, y), color + (255,))
    if person.copy:
        src, dst = person.copy
        out[dst] = [c.transpose(Image.Transpose.FLIP_LEFT_RIGHT) for c in out[src]]
    return out


def common_skin(cells):
    """SKIN 의 한 톤과 가까운 색을 그 톤으로 바꾼다."""
    tones = [lab(c) for c in SKIN]
    swap = {}
    for pair in cells.values():
        for c in pair:
            px = c.load()
            for y in range(c.height):
                for x in range(c.width):
                    q = px[x, y]
                    if not q[3] or q[:3] == INK:
                        continue
                    if q[:3] not in swap:
                        d = [math.dist(lab(q[:3]), t) for t in tones]
                        swap[q[:3]] = SKIN[d.index(min(d))] if min(d) <= SKIN_NEAR else \
                            WHITE if math.dist(lab(q[:3]), lab(WHITE)) <= SKIN_NEAR else q[:3]
                    px[x, y] = swap[q[:3]] + (255,)


def shade_edge(c):
    """가장자리의 밝은 칸을 그 그림 안의 같은 색 계열 어두운 색으로 바꾼다. NDS 그림은 옷자락·모자 끝이 밝은 색
    그대로라 풀밭·바닥에서 테두리가 없어 보인다. 한 칸 굵기(칼·창)와 이미 어두운 가장자리는 그대로 둔다."""
    px = c.load()
    solid = {(x, y) for y in range(c.height) for x in range(c.width) if px[x, y][3]}
    colors = {px[q][:3] for q in solid} - {INK}
    labs = {k: lab(k) for k in colors}
    bottom = max(y for _, y in solid)
    change = {}
    for x, y in solid:
        gone = [(x + dx, y + dy) not in solid for dx, dy in ((1, 0), (-1, 0), (0, -1), (0, 1))]
        if not (gone[0] or gone[1] or gone[2] or (y < bottom and gone[3])):
            continue
        if (gone[0] and gone[1]) or (gone[2] and gone[3]):
            continue
        col = px[x, y][:3]
        if col == INK or labs[col][0] < 55:
            continue
        if any((x + dx, y + dy) in solid and px[x + dx, y + dy][:3] == INK for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))):
            continue                                   # 눈 옆 칸을 어둡게 하면 눈이 윤곽과 이어진다
        deeper = [k for k in colors if 12 <= labs[col][0] - labs[k][0] <= 40 and math.dist(labs[k][1:], labs[col][1:]) < 30]
        if deeper:
            change[(x, y)] = min(deeper, key=lambda k: (math.dist(labs[k][1:], labs[col][1:]), labs[k][0]))
    for q, k in change.items():
        px[q] = k + (255,)


def outline(c):
    """실루엣 가장자리 픽셀을 그림에서 가장 어두운 색으로. 크기는 그대로 두고 배경과 같은 계열 색인 인물을 떼어 낸다."""
    px = c.load()
    solid = {(x, y) for y in range(c.height) for x in range(c.width) if px[x, y][3]}
    darkest = min((px[q] for q in solid), key=lambda q: lab(q[:3])[0])
    edge = [(x, y) for x, y in solid if any((x + dx, y + dy) not in solid
                                              for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)))]
    for q in edge:
        px[q] = darkest


def histogram(cells):
    count = Counter(p[:3] for pair in cells.values() for c in pair for p in c.get_flattened_data() if p[3])
    if INK in count:
        count[INK] *= INK_WEIGHT
    for c in SKIN + (WHITE,):
        if c in count:
            count[c] *= SKIN_WEIGHT
    return count


def accented(hist):
    """몇 칸뿐인 강조색(입·리본·문장·속옷)의 무게를 올린다. 넓이만으로 세면 줄을 함께 쓰는 인물의 넓은 색에 묻혀
    그 인물의 표지가 되는 색이 사라진다."""
    own = sum(w for c, w in hist.items() if c not in COMMON)
    return Counter({c: w if c in COMMON else max(w, own * ACCENT_SHARE) for c, w in hist.items()})


def histograms(cells):
    """{인물: 줄 배정에 쓰는 색 빈도}. 무겁게 세는 인물만 강조색을 올린다."""
    return {p: accented(histogram(c)) if p.weight > 1 else histogram(c) for p, c in cells.items()}


def lab(c):
    def lin(v):
        v /= 255
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (lin(v) for v in c)
    x, y, z = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.9505, 0.2126 * r + 0.7152 * g + 0.0722 * b, \
        (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.089
    f = lambda t: t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116  # noqa: E731
    return 116 * f(y) - 16, 500 * (f(x) - f(y)), 200 * (f(y) - f(z))


def reduce(hist, n=15):
    """색 빈도 → n 색. 가장 가까운 두 색 가운데 덜 쓴 색을 많이 쓴 색에 합치기를 되풀이해 NDS 색을 그대로 남긴다."""
    items = [[c, w, lab(c)] for c, w in hist.items()]
    while len(items) > n:
        best = None
        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                d = math.dist(items[i][2], items[j][2]) * min(items[i][1], items[j][1])
                if best is None or d < best[0]:
                    best = (d, i, j)
        _, i, j = best
        keep, drop = (i, j) if items[i][1] >= items[j][1] else (j, i)
        items[keep][1] += items[drop][1]
        del items[drop]
    return [c for c, _, _ in items]


def cost(hist, pal):
    lp = [lab(c) for c in pal]
    return sum(w * min(math.dist(lab(c), q) for q in lp) for c, w in hist.items())


def lines(people, hists, where=None):
    """공용 줄 배정: 주요 인물부터 넣을 때 늘어나는 색 거리 합이 가장 작은 줄로."""
    groups = defaultdict(Counter)
    seen = defaultdict(set)

    def open_lines(p):
        lent = [set(LENT_LINES.get(g, ())) for g in where[p]] if where else []
        return SHARED_LINES + tuple(sorted(set.intersection(*lent))) if lent else SHARED_LINES
    heavy = defaultdict(set)
    order = sorted((p for p in people if p.palette is None), key=lambda p: (p.weight <= 1, -len(hists[p])))
    assign = {}
    for p in order:
        h = Counter({c: w * p.weight for c, w in hists[p].items()})

        def growth(n):
            if not groups[n]:
                return 0
            # 모두가 함께 쓰는 살색·눈 색은 어느 줄에 가도 늘지 않으므로 빼고 잰다. 넣고 재면 그 무게 때문에 모든
            # 인물이 한 줄에 몰려 옷 색이 뭉개진다. 그 칸 수만큼 줄의 남는 칸도 줄여 잰다
            own = lambda g: Counter({c: w for c, w in g.items() if c not in COMMON})  # noqa: E731
            was, merged = own(groups[n]), own(groups[n] + h)
            room = 15 - len(COMMON)
            return cost(merged, reduce(merged, room)) - cost(was, reduce(was, room))
        mine = {c for c in hists[p] if c not in COMMON}
        if p.line is not None:
            best = p.line
        elif where:
            # 같은 맵에 함께 서는 인물끼리 한 줄에 몰리지 않게, 그 인물이 나오는 맵 그룹마다 줄에 모인 색 수가
            # 가장 적은 줄을 고른다(같으면 색 거리가 덜 느는 줄)
            load = {n: max((len(seen[(g, n)] | mine) for g in where[p]), default=0) for n in open_lines(p)}
            low = min(load.values())
            near = [n for n in load if load[n] <= low + LOAD_SLACK]
            if p.weight > 1:
                # 무겁게 세는 인물끼리 한 줄에 몰리면 서로의 색을 밀어낸다. 그 인물이 나오는 맵 그룹에서 무거운
                # 인물의 색이 가장 적게 모인 줄만 후보로 둔다
                crowd = {n: max(len(heavy[(g, n)] | mine) for g in where[p]) for n in load}
                least = min(crowd.values())
                near = [n for n in load if crowd[n] == least]
            best = min(near, key=growth)
        else:
            best = min(SHARED_LINES, key=growth)
        for g in (where[p] if where else ()):
            seen[(g, best)] |= mine
            if p.weight > 1:
                heavy[(g, best)] |= mine
        groups[best] += h
        assign[p] = best
    return assign, {n: reduce(g) for n, g in groups.items() if g}


ROUNDS = 6


def place(people, hists, where):
    """맵 그룹마다 줄 색을 따로 싣는다. 줄은 공용 배정(lines)을 따르고, 인물 색 → 칸 번호는 모든 그룹에서 같아야
    하므로 인물마다 하나로 둔다. 「그룹마다 칸 색 = 그 그룹에서 그 칸에 모인 색의 가중 평균」과 「인물 색마다 그
    인물이 나오는 그룹들의 칸 색과의 거리 합이 가장 작은 칸」을 번갈아 고친다(공용 줄 색에서 시작).
    끝에는 칸 색을 그 칸에 모인 NDS 원래 색 가운데 평균에 가장 가까운 것으로 둔다.
    반환: ({인물: (줄, {색: 칸})}, {(그룹, 줄): 15색})."""
    assign, shared = lines(people, hists, where)
    who = [p for p in people if p.palette is None]
    keys = {(g, assign[p]) for p in who for g in where[p]}
    centers = {key: [lab(c) for c in shared[key[1]]] for key in keys}
    mapping = {}
    for _ in range(ROUNDS):
        for p in who:
            rows = [centers[(g, assign[p])] for g in where[p]]
            mapping[p] = {c: min(range(len(rows[0])), key=lambda k: sum(math.dist(lab(c), r[k]) for r in rows))
                          for c in hists[p]}
        acc = {}
        for p in who:
            for c, w in hists[p].items():
                for g in where[p]:
                    acc.setdefault((g, assign[p], mapping[p][c]), Counter())[c] += w * p.weight
        for (g, line, k), cs in acc.items():
            total = sum(cs.values())
            centers[(g, line)][k] = tuple(sum(lab(c)[i] * w for c, w in cs.items()) / total for i in range(3))
    board = {}
    for g, line in keys:
        row = []
        for k, center in enumerate(centers[(g, line)]):
            cs = acc.get((g, line, k))
            row.append(min(cs, key=lambda c: math.dist(lab(c), center)) if cs else shared[line][k])
        board[(g, line)] = row
    return {p: (assign[p], mapping[p]) for p in who}, board


def index_image(cells, pal, layout):
    """색 번호 시트. simple 32x96(열 걸음 0·1), overlap 48x64(열 머리·몸 0·몸 1, 몸은 프레임의 8~23행).
    pal 이 {색: 칸} 이면 그대로 쓰고, 색 목록이면 가장 가까운 색의 칸으로."""
    mapping, pal = (pal, None) if isinstance(pal, dict) else (None, pal)
    lp = {k: lab(c) for k, c in enumerate(pal) if c is not None} if pal else {}
    near = {c: k + 1 for c, k in mapping.items()} if mapping else {}

    def idx(p):
        if not p[3]:
            return 0
        if p[:3] not in near:
            near[p[:3]] = min(lp, key=lambda k: math.dist(lab(p[:3]), lp[k])) + 1
        return near[p[:3]]
    if layout == 'simple':
        out = Image.new('P', (32, 96), 0)
        for r, (name, _) in enumerate(ROWS8):
            for col, c in enumerate(cells[name]):
                for y in range(24):
                    for x in range(16):
                        out.putpixel((col * 16 + x, r * 24 + y), idx(c.getpixel((x, y))))
    else:
        out = Image.new('P', (48, 64), 0)
        for r, (name, _) in enumerate(ROWS8):
            head = cells[name][0]
            for y in range(16):
                for x in range(16):
                    out.putpixel((x, r * 16 + y), idx(head.getpixel((x, y))))
            for col, c in enumerate(cells[name]):
                for y in range(16):
                    for x in range(16):
                        out.putpixel((16 + col * 16 + x, r * 16 + y), idx(c.getpixel((x, y + 8))))
    if mapping:
        pal = [None] * 15
        for c, k in mapping.items():
            pal[k] = pal[k] or c
    out.putpalette([0, 0, 0] + [v for c in pal for v in (c or (0, 0, 0))])
    return out


def hook(entries):
    """entries: [(그림 번호, 맵 그룹 또는 None, 세트)] 또는 [(그림, 그룹, 깃발 (바이트, 마스크) 또는 None, 세트)].
    맞는 첫 줄의 세트를, 없으면 원래 표를 싣는다. 부르는 곳의 A·X 폭이 달라 PHP·SEP #$30 … PLP 로 감싼다(두 곳
    모두 뒤에서 N·Z 를 보지 않는다). 줄이 많으면 끝까지의 BRA 가 127바이트를 넘으므로 줄마다 PLP·RTL 로 바로 돌아간다."""
    code = bytearray(b'\x08\xe2\x30')                                   # PHP / SEP #$30
    for entry in entries:
        picture, group, flag, s = entry if len(entry) == 4 else (entry[0], entry[1], None, entry[2])
        code += bytes((0xE0, picture, 0xD0, 0))                           # CPX #p / BNE 다음 줄
        skip = [len(code) - 1]
        if group is not None:
            a = MAP_GROUP
            code += bytes((0xAF, a & 0xFF, a >> 8 & 0xFF, a >> 16, 0xC9, group, 0xD0, 0))   # LDA $BC / CMP / BNE
            skip.append(len(code) - 1)
        if flag is not None:
            a = 0x7E2190 + flag[0]
            code += bytes((0xAF, a & 0xFF, a >> 8 & 0xFF, a >> 16, 0x29, flag[1], 0xF0, 0))  # LDA 깃발 / AND / BEQ
            skip.append(len(code) - 1)
        code += bytes((0xA9, s, 0x28, 0x6B))                              # LDA #세트 / PLP / RTL
        for off in skip:
            code[off] = len(code) - (off + 1)
    return bytes(code + LOAD_SET + b'\x28\x6b')                          # LDA $2586D0,X / PLP / RTL


def hook_entries(rom):
    """원래 표와 다른 세트를 쓰는 인물의 (그림 번호, 맵 그룹, 깃발, 세트). 깃발·맵 그룹을 보는 줄을 앞에 둔다."""
    out = []
    for p in PEOPLE:
        if p.flag is not None and p.leader:
            out += [(g, None, p.flag, target(p, rom)[0]) for g in LEADER_PICTURES]
    for p in sorted(PEOPLE, key=lambda p: p.group is None):
        # 그림 번호가 곧 빌린 그림이면 원래 표가 이미 바꾼 세트를 가리킨다
        if (p.new_set is not None or p.spare is not None) and p.pictures != (p.spare,):
            out += [(g, p.group, None, target(p, rom)[0]) for g in p.pictures]
    return out


def hook_patch(rom):
    at = cpu(HOOK_AT)
    writes = [{'at': HOOK_AT, 'hex': hook(hook_entries(Rom(rom))).hex(' '), 'note': '그림 번호 + 맵 그룹 → 세트'}]
    for site in HOOK_SITES:
        orig = rom[lorom(cpu(site)):lorom(cpu(site)) + 4]
        if orig != LOAD_SET:
            raise SystemExit(f'{site}: LDA $2586D0,X 가 아님 ({orig.hex(" ")})')
        writes.append({'at': site, 'hex': bytes((0x22, at & 0xFF, at >> 8 & 0xFF, at >> 16)).hex(' '),
                       'orig': orig.hex(' '), 'note': '그림 → 세트를 인물 훅으로(JSL)'})
    brey = cpu(COMPANION_PICTURES) + 5
    writes.append({'at': f'{brey >> 16:02X}:{brey & 0xFFFF:04X}', 'hex': f'{BREY_PICTURE:02x}',
                   'orig': f'{rom[lorom(brey)]:02x}', 'note': '사람 동료 그림 표 인물 05(브라이) → 2C'})
    # 일행 그림을 그 자리에서 다시 싣는 03:D2B9 는 레코드 +2 의 아래 4비트만 뱅크로 써서, TILE_AREAS(3C~3F)에 둔
    # 세트를 0C~0F 에서 읽는다(맵에 들어올 때의 1F:D2DB 는 6비트를 다 쓴다). 위 2비트는 팔레트라 3F 로 거른다
    mask = rom[lorom(BANK_MASK_SITE):lorom(BANK_MASK_SITE) + 2]
    if mask != b'\x29\x0f':
        raise SystemExit(f'03:D2C7: AND #$0F 가 아님 ({mask.hex(" ")})')
    writes.append({'at': '03:D2C7', 'hex': '29 3f', 'orig': '29 0f', 'note': '일행 그림 다시 싣기의 타일 자료 뱅크 6비트'})
    # 필드 맵을 불러올 때 DQ5 는 OBJ 반 더하기($2131 = 50)를 켠다(탈것 그림자용). 색 연산은 OBJ 팔레트 4~7 에만
    # 걸리므로 그 줄을 쓰는 장 주인공·동료가 필드에서 BG 와 반씩 섞인다. 필드 OBJ 색 연산을 끈다
    math = rom[lorom(FIELD_MATH_SITE):lorom(FIELD_MATH_SITE) + 2]
    if math != b'\xa9\x50':
        raise SystemExit(f'2B:82F7: LDA #$50 이 아님 ({math.hex(" ")})')
    writes.append({'at': '2B:82F7', 'hex': 'a9 00', 'orig': 'a9 50', 'note': '필드 $2131 OBJ 반 더하기 끔'})
    return {'format': 'dq5patch/1', 'name': 'people-hook', 'writes': writes, 'rom_size': 2}


BANK_MASK_SITE = 0x03D2C7
FIELD_MATH_SITE = 0x2B82F7                        # 필드 맵 불러오기의 LDA #$50 / STA $2131
SWAP_SITE = 0x03D24D
SWAP_HEAD = 29                                    # swap_routine 의 머리(PHX … PLB). 뒤는 A = 세트로 표를 찾는다


def swap_patch(rom):
    """그림을 바꿀 때의 팔레트 루틴(03:D24D → dq5objpalette.swap_routine)이 세트를 인물 훅으로 찾게 한다.
    그 루틴은 03:D202 의 LDA long 피연산자를 실행 중에 읽어 그림 표를 찾는데, 03:D202 가 인물 훅 JSL 이면
    훅 코드 바이트를 세트로 읽어 팔레트 비트가 틀어진다(일행이 바뀐 뒤 주인공·동료 그림이 다른 팔레트·타일 줄로 깨짐).
    머리를 「그림 번호 $1EC0 → X, JSL 인물 훅」으로 바꿔, 타일을 싣는 03:D202 와 같은 세트를 보게 한다."""
    import dq5objpalette
    site = lorom(SWAP_SITE)
    if rom[site] != 0x22:
        raise SystemExit('03:D24D: 세트 팔레트 훅(JSL)이 아님')
    at = rom[site + 1] | rom[site + 2] << 8 | rom[site + 3] << 16
    orig = dq5objpalette.swap_routine(0)[:SWAP_HEAD]
    if rom[lorom(at):lorom(at) + SWAP_HEAD] != orig:
        raise SystemExit(f'{at >> 16:02X}:{at & 0xFFFF:04X}: dq5objpalette.swap_routine 의 꼴이 아님')
    hook_at = cpu(HOOK_AT)
    head = (bytes.fromhex('da c2 20 af c0 1e 7e 29 ff 00 aa e2 20') +    # PHX / REP #$20 / LDA $7E1EC0 / AND #$FF / TAX / SEP #$20
            bytes((0x22, hook_at & 0xFF, hook_at >> 8 & 0xFF, hook_at >> 16)))  # JSL 인물 훅 → A = 세트
    head += b'\xea' * (SWAP_HEAD - len(head))
    return {'format': 'dq5patch/1', 'name': 'people-swap', 'rom_size': 2,
            'writes': [{'at': f'{at >> 16:02X}:{at & 0xFFFF:04X}', 'hex': head.hex(' '), 'orig': orig.hex(' '),
                        'note': '그림 바꾸기 팔레트 루틴의 세트 찾기를 인물 훅으로'}]}


def target(person, rom):
    """(세트, 배치, 타일 한도). 장 주인공은 새 6타일 세트(한도는 2B·2E 의 원래 세트 중 작은 쪽), 나머지는 그림
    번호(spare 가 있으면 spare)의 원래 세트를 그 자리에서 바꾸고 한도는 그 세트의 타일 수."""
    if person.pictures == LEADER_PICTURES:
        limit = min(S.set_record(rom, S.gfx_set(rom, g))['tiles'] for g in LEADER_PICTURES)
        return person.new_set, 'simple', limit
    s = S.gfx_set(rom, person.spare if person.spare is not None else person.pictures[0])
    return s, 'overlap' if s & 0x80 else 'simple', S.set_record(rom, s)['tiles']


def tiles(path, layout):
    cells = dq5spritewrite.cell_tiles(dq5spritewrite.image_grid(path, layout), layout)
    return len(dq5spritewrite.deduplicate(cells)[0])


def chapter_groups(chapter):
    import dq4groupbuild
    return sorted(g for g, maps in dq4groupbuild.LINKS.items() if any(m.get('chapter') == chapter for m in maps))


def usage(base):
    """{그림: 나오는 DQ4 맵 그룹들}. 곡 롬의 인물 목록에서 읽고, 대체 목록은 overrides 로 맵에 잇는다."""
    doc = dq5npcrecord.dump(base)
    maps = {}
    for o in doc['overrides']:
        maps.setdefault(o['list'], set()).add(o['map'])
    out = {}
    for e in doc['entries']:
        names = ({e['name']} if '/' in e['name'] else set()) | maps.get(e['list'], set())
        groups = {int(m.split('/')[0], 16) for m in names} & DQ4_GROUPS
        for part in (e.get('fields'), e.get('day'), e.get('night')):
            if part and groups:
                out.setdefault(part['gfx'], set()).update(groups)
    return out


def where(people, used):
    """{인물: 나오는 맵 그룹들}. 그룹을 정한 인물은 그 그룹과, 빌린 그림 번호(spare)를 그대로 쓰는 인물이 나오는 그룹.
    그룹을 정하지 않은 인물은 그 그림이 나오는 그룹에서, 그 그룹에서 같은 그림을 빌려 간 인물이 있으면 뺀다.
    목록에서 찾지 못한 그림(이벤트로만 바꾸는 그림 등)은 모든 그룹으로 본다."""
    out = {}
    for p in people:
        if p.seen is not None:
            out[p] = set(p.seen)
            continue
        if p.group is not None:
            # 빌린 그림 번호는 훅을 거치지 않고 바꿔 쓴 세트를 그대로 싣는다(다른 그룹에서 그 시트를 쓰려는 인물)
            out[p] = {p.group} | (used.get(p.spare, set()) if p.spare is not None else set())
            continue
        groups = set()
        for pic in p.pictures:
            groups |= used.get(pic, DQ4_GROUPS)
        groups -= {q.group for q in people if q.group is not None and set(q.pictures) & set(p.pictures)}
        out[p] = groups or set(DQ4_GROUPS)
    return out


def prepare(rom, assets, work, base=None, squeeze=False):
    """인물마다 시트를 만들어 타일 한도에 맞춘다. [(인물, 세트, 배치, 한도, 타일, 낮춘 단계, 줄, 줄 색)]."""
    cells = {p: rgb_frames(p, assets) for p in PEOPLE}
    hists = histograms(cells)
    used = usage(base) if base is not None else {}
    placed, board = place(PEOPLE, hists, where(PEOPLE, used))
    sets = [target(p, rom)[0] for p in PEOPLE]
    if len(set(sets)) != len(sets):
        raise SystemExit(f'두 인물이 같은 세트를 바꿈: {sorted(f"{s:02X}" for s in sets if sets.count(s) > 1)}')
    rows = []
    for p in PEOPLE:
        line, pal = (p.palette, reduce(hists[p])) if p.palette is not None else placed[p]
        s, layout, limit = target(p, rom)
        path = work / f'{s:02X}.png'
        index_image(cells[p], pal, layout).save(path)
        steps = []
        for name, fn in (d for d in DEGRADE if d[0] in p.allow):
            # squeeze: 타일 자료가 빈 자리에 다 안 들어갈 때, 주요 인물이 아니면 옆모습을 반전으로 나눠 쓴다
            if tiles(path, layout) <= limit and not (squeeze and not p.main and name == DEGRADE[0][0]):
                break
            fn(cells[p])
            index_image(cells[p], pal, layout).save(path)
            steps.append(name)
        rows.append((p, s, layout, limit, tiles(path, layout), steps, line, pal))
    return rows, board


def tile_areas(base):
    """TILE_AREAS 를 base 롬(곡 롬)에 맞춘다. 앞 단계가 그 뱅크 끝의 0 줄 안까지 자료를 늘렸으면 쓰인 끝 다음 16바이트
    경계부터 쓴다(1장 빌드의 인물 자료가 3F 끝을 향해 자란다)."""
    out = []
    for at, size in TILE_AREAS:
        start, end = cpu(at), cpu(at) + size
        o = lorom(start)
        used = [i for i in range(o, lorom(end - 1) + 1) if base[i]]
        if used:
            moved = (start + used[-1] - o + 0x10) & ~0xF
            if any(base[lorom(moved):lorom(end - 1) + 1]):
                raise SystemExit(f'{at}: 타일 자리 안에 0 이 아닌 자료가 흩어져 있음')
            start = moved
        out.append((f'{start >> 16:02X}:{start & 0xFFFF:04X}', end - start))
    return tuple(out)


def pack(items, room):
    """[(세트, 바이트)] 를 자리 room(바이트 목록)에 나눠 담는 배치(자리마다 세트 목록). 큰 것부터 넣되 자리가
    조각나면 되돌아가 다른 자리를 고른다(큰 것부터 가장 큰 자리에만 넣으면 남은 합이 넉넉해도 막혔다)."""
    room, bins = list(room), [[] for _ in room]
    # 합이 모자라면 되돌아가기가 끝나지 않는다(모든 배치를 다 해 본다)
    if sum(n for _, n in items) > sum(room):
        raise SystemExit(f'타일 자료 자리가 모자람: {sum(n for _, n in items)} > {sum(room)}')
    dead = set()

    def go(i):
        key = (i, tuple(sorted(room)))
        if key in dead:
            return False
        if i == len(items):
            return True
        s, n = items[i]
        tried = set()
        for k in sorted(range(len(room)), key=lambda k: room[k]):
            if room[k] >= n and room[k] not in tried:
                tried.add(room[k])
                room[k] -= n
                bins[k].append(s)
                if go(i + 1):
                    return True
                room[k] += n
                bins[k].pop()
        dead.add(key)
        return False
    if not go(0):
        raise SystemExit(f'타일 자료 자리가 모자람: 세트·바이트 {items}, 자리 {room}')
    return bins


def split_patches(rom, doc, base, areas=TILE_AREAS):
    """원래 자리에 들어가지 않는 세트를 areas 에 나눠 담는 dq5spritewrite 패치들. 한 번 돌려 어느 세트가
    얼마나 넘치는지 본 뒤, pack 으로 자리를 나누고 자리마다 다시 만든다."""
    first = cpu(areas[0][0])
    trial = dq5spritewrite.patch(rom, doc, base, first)
    size = Counter()
    for w in trial['writes']:
        at = cpu(w['at'])
        if at >= first and '타일' in w['note']:
            size[w['note'].split()[1]] += len(w['hex'].split())
    # 새 세트 레코드·그림 연결은 첫 패치만 실으므로 새 세트의 타일은 첫 자리에 둔다
    fresh = {r['set'] for r in doc['new_sets']}
    room = [n for _, n in areas]
    room[0] -= sum(n for s, n in size.items() if s in fresh)
    bins = pack(sorted(((s, n) for s, n in size.items() if s not in fresh), key=lambda t: -t[1]), room)
    bins[0] += sorted(fresh & set(size))
    out = []
    for k, (at, _) in enumerate(areas):
        if k == 0:
            # 첫 패치가 새 세트 레코드·그림 연결과 원래 자리에 들어가는 세트를 모두 맡는다
            part = {**doc, 'sets': [r for r in doc['sets'] if not any(r['set'] in b for b in bins[1:])]}
            part['new_sets'] = [r for r in doc['new_sets'] if not any(r['set'] in b for b in bins[1:])]
        else:
            part = {'format': doc['format'], 'sets': [r for r in doc['sets'] if r['set'] in bins[k]]}
        if part['sets'] or part.get('new_sets'):
            out.append(dq5spritewrite.patch(rom, part, base, cpu(at)))
    return out


def build(base, dq5, assets, out, work):
    try:
        return assemble(base, dq5, assets, out, work, squeeze=False)
    except SystemExit as e:
        if '타일 자료 자리가 모자람' not in str(e):
            raise
    return assemble(base, dq5, assets, out, work, squeeze=True)


def assemble(base, dq5, assets, out, work, squeeze):
    original = dq5.read_bytes()
    rows, board = prepare(Rom(original), assets, work, Rom(base.read_bytes()), squeeze)
    over = [f'{p.role} {n}>{limit}' for p, _, _, limit, n, _, _, _ in rows if n > limit]
    if over:
        raise SystemExit('타일 한도를 넘음: ' + ', '.join(over))
    doc = {'format': 'dq5sprite/1', 'sets': [], 'new_sets': [], 'gfx': []}
    leader_sets = []
    for p, s, _, _, _, _, _, _ in rows:
        if p.new_set is None:
            doc['sets'].append({'set': f'{s:02X}', 'image': f'{s:02X}.png'})
            continue
        doc['new_sets'].append({'set': f'{s:02X}', 'image': f'{s:02X}.png', 'palette': 0})
        leader_sets.append(s)
    # 장 주인공 두 세트는 그림 2B·2E 에 하나씩 잇는다(훅이 앞서므로 표 값은 쓰이지 않는다)
    doc['gfx'] += [{'gfx': f'{g:02X}', 'set': f'{s:02X}'} for g, s in zip(LEADER_PICTURES, leader_sets)]
    (work / 'sprite.json').write_text(json.dumps(doc, indent=1) + '\n')
    sprites = split_patches(Rom(original), doc, work, tile_areas(base.read_bytes()))
    for k, sprite in enumerate(sprites):
        (work / f'sprite{k}.dq5patch.json').write_text(json.dumps(sprite, ensure_ascii=False, indent=1) + '\n')
    subprocess.run([sys.executable, DQ5_TOOLS / 'dq5build.py', dq5, 'build',
                    *(work / f'sprite{k}.dq5patch.json' for k in range(len(sprites))),
                    '--size', '2', '-o', work / 'mid.sfc'], check=True, stdout=subprocess.DEVNULL)
    bgr = lambda pal: [0 if c is None else (c[2] >> 3) << 10 | (c[1] >> 3) << 5 | c[0] >> 3 for c in pal] + \
        [0] * (15 - len(pal))  # noqa: E731
    fixed = {line: pal for p, _, _, _, _, _, line, pal in rows if p.palette is not None and p.flag is None}
    # DQ4 그룹이 아닌 맵(필드 등)은 칸이 가장 많이 찬 그룹의 줄 색을 기본으로 둔다
    home = max({g for g, _ in board}, key=lambda g: sum(c is not None for (h, _), row in board.items() if h == g for c in row))
    base_lines = {line: board[(home, line)] for g, line in board if g == home}
    pal_doc = {'format': 'dq5objpalette/1',
               'palettes': [{'palette': n, 'colors': bgr(pal)} for n, pal in sorted({**base_lines, **fixed}.items())],
               'sets': [{'set': f'{s:02X}', 'palette': line} for _, s, _, _, _, _, line, _ in rows]}
    # 그룹 36~ 은 DQ4 롬에만 있으므로 맵 팔레트 줄은 곡 롬을 기준으로 따로 만든다
    map_doc = {'format': 'dq5objpalette/1',
               'new_map_palettes': [{'map': f'{g:02X}/FF', 'line': f'{0x08 + line:02X}', 'flag': 'FF', 'mask': '00',
                                     'colors': bgr(row)} for (g, line), row in sorted(board.items())]}
    # 깃발이 붙은 전용 줄(2장 일행)은 그 장의 그룹과 필드 세계 셋에서 그 깃발이 켜졌을 때 덮는다
    every = [f'{g:02X}/FF' for g in chapter_groups(2)] + [f'FE/{w:02X}' for w in range(3)]
    map_doc['new_map_palettes'] += [{'map': m, 'line': f'{0x08 + line:02X}', 'flag': f'{p.flag[0]:02X}',
                                     'mask': f'{p.flag[1]:02X}', 'colors': bgr(pal)}
                                    for p, _, _, _, _, _, line, pal in rows if p.flag is not None for m in every]
    maps = dq5objpalette.patch(Rom(base.read_bytes()), map_doc, MAP_PALETTES_AT)
    (work / 'maps.dq5patch.json').write_text(json.dumps(maps, ensure_ascii=False, indent=1) + '\n')
    palettes = dq5objpalette.patch(Rom((work / 'mid.sfc').read_bytes()), pal_doc, PALETTES_AT)
    (work / 'palette.dq5patch.json').write_text(json.dumps(palettes, ensure_ascii=False, indent=1) + '\n')
    (work / 'hook.dq5patch.json').write_text(json.dumps(hook_patch(original), indent=1) + '\n')
    names = [f'sprite{k}' for k in range(len(sprites))] + ['palette', 'maps', 'hook']
    rom = apply_writes(base.read_bytes(), original, [work / f'{n}.dq5patch.json' for n in names])
    # 팔레트 패치가 놓은 루틴을 고치므로 그 뒤에 얹는다
    (work / 'swap.dq5patch.json').write_text(json.dumps(swap_patch(rom), indent=1) + '\n')
    rom = apply_writes(rom, original, [work / 'swap.dq5patch.json'])
    out.write_bytes(set_checksum(rom))
    return rows


def report(rows):
    for p, s, layout, limit, n, steps, line, _ in rows:
        where = (f'그룹 {p.group:02X}' if p.group is not None else
                 '사건 ' + ','.join(f'{g:02X}' for g in sorted(p.seen)) if p.seen is not None else '어디나')
        pics = ','.join(f'{g:02X}' for g in p.pictures)
        print(f'{p.role:8s} 그림 {pics:5s} {where:6s} {p.sheet} 세트 {s:02X} {layout:7s} 타일 {n:2d}/{limit:2d}'
              f' 팔레트 {line} {" · ".join(steps)}')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--base', type=Path, help='얹을 1장 롬(곡 묶음까지 얹은 것)')
    ap.add_argument('--dq5', default='rom/dq5.sfc', type=Path)
    ap.add_argument('--assets', required=True, type=Path, help='NDS 인물 시트가 있는 자원 저장소')
    ap.add_argument('--out', type=Path)
    ap.add_argument('--work', type=Path, help='중간 시트·패치를 둘 폴더(기본 임시 폴더)')
    ap.add_argument('--plan', action='store_true', help='롬을 만들지 않고 인물마다 세트·타일·팔레트 줄만 찍음')
    args = ap.parse_args()
    if not args.plan and not (args.base and args.out):
        ap.error('--base 와 --out 이 필요함(--plan 이 아니면)')
    with tempfile.TemporaryDirectory() as tmp:
        work = args.work or Path(tmp)
        work.mkdir(parents=True, exist_ok=True)
        if args.plan:
            report(prepare(Rom(args.dq5.read_bytes()), args.assets, work,
                           Rom(args.base.read_bytes()) if args.base else None)[0])
            return
        report(build(args.base, args.dq5, args.assets, args.out, work))
    print(args.out)


if __name__ == '__main__':
    main()
