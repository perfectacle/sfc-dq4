"""3장 사건 모듈의 자원 예약표(정본). 형식 문서 sfc/dq4/docs/dq4-chapter3-format.md 「사건 등록과 자원 예약」.

3장 사건은 모듈마다 파일 하나(SLOTS 의 module 이름)로 만든다. 등록은 파일이 생기는 것으로 끝난다: dq4ch3event.EVENTS 가
SLOTS 차례대로 있는 모듈 파일만 들인다. 그래서 여러 사건 PR 이 같은 등록 줄을 고치지 않는다. 모듈은 자기 몫만 쓰고,
모자라면 이 표의 자기 줄을 고친다. test_dq4ch3slots 가 몫끼리·2장 몫과 겹치지 않는지, 있는 모듈이 몫 안인지 본다.

메시지·대화 번호·대화 호출 번호는 미리 나누지 않는다. 2장처럼 등록 차례로 이어 붙여 자동으로 매긴다.
"""
from dataclasses import dataclass

from dq4ch2slots import Slot as _Slot


@dataclass(frozen=True)
class Slot(_Slot):
    vars: tuple = ()               # 변수 칸(VARS_AT + 오프셋)의 (시작, 끝) 오프셋. 끝은 들지 않음
    vars2: tuple = ()              # 둘째 변수 칸(VARS2_AT + 오프셋)의 (시작, 끝)
    far: tuple = ()                # 다른 뱅크의 코드 자리 (시작, 끝). 모듈의 far_native(ctx) 가 쓴다(JSL·RTL 로 부름)


# 저장되는 변수 칸: DQ5 맡긴 몬스터 칸(7E:2332, 26바이트 × 56)의 49번 칸 +1~+25. 3장 넘김이 50~55 에 아리나 일행을
# 맡기고(dq4ch3event.STASH_FIRST), 이 해킹은 몬스터를 맡기지 않아 칸은 비어 있다. 칸 첫 바이트 bit7 이 찬 칸 표시라
# +0 은 쓰지 않는다. 대화·인물 스크립트의 조건은 7E:2190 + 번호만 보므로, 여기에는 네이티브만 읽고 쓰는 값(날수·일삯·
# 재고·납품 수)을 둔다
VARS_SLOT = 49
VARS_AT = 0x7E2332 + VARS_SLOT * 26 + 1
VARS_SIZE = 25
# 둘째 변수 칸: 같은 꼴로 맡긴 몬스터 칸 48번 +1~+25(7E:2813~282B). 3장 출발 상태에서 0(헤드리스 실측), 저장 기록
# 7E:2000~2A9F 안
VARS2_SLOT = 48
VARS2_AT = 0x7E2332 + VARS2_SLOT * 26 + 1
VARS2_SIZE = 25

# 빌릴 인물 스크립트는 이 해킹이 가지 않는 DQ5 맵 목록에서 스크립트가 있고 한 시간대(낮 또는 밤)에만 놓이는 칸이다.
# 낮·밤 두 벌 레코드를 빌리면 dq5npcrelocate 가 받지 않는다.
# 사건 코드는 5C:D000~FFFF(3장 넘김·공용 장치 5C:C000~CFFF 뒤)와 5F:F800~FFFF. flag 는 2장 예비로 남았던 21FF~2207·
# 2209~220C(dq4ch2slots 「flag 자리」의 근거 그대로). 2208 은 여덟 비트를 모두 쓴다
SLOTS = {
    'L': Slot('레이크나바: 무기점 일·도시락·네네·톰 노인·톰 아들', 'dq4ch3lakanaba', (0x5CD000, 0x5CE000),
              flags=(0x70, 0x71), scripts=(('10:9B81', (0, 1, *range(8, 14))), ('10:A031', tuple(range(6)))), lists='ch3_lakanaba_',
              vars=(4, 10), vars2=(20, 21)),
    'S': Slot('북쪽 동굴과 금고, 여신상 동굴의 배', 'dq4ch3safe', (0x5CE000, 0x5CE800), flags=(0x72, 0x7A),
              scripts=(('10:C8FF', (0, 1, 4, 6, 7, 8, 9)),), lists='ch3_safe_', vars=(14, 25)),
    'B': Slot('본몰 왕자·감옥·여우 마을·다리·개 토마스', 'dq4ch3bonmalmo', (0x5CE800, 0x5CF000), flags=(0x73, 0x74),
              scripts=(('10:BEE5', (2, *range(4, 10))),), lists='ch3_bonmalmo_'),
    'E': Slot('엔돌: 편지·여신상 동굴·여신상 팔기·가게 사기·납품·용병', 'dq4ch3endor', (0x5CF000, 0x5CFC00),
              flags=(0x75, 0x76), scripts=(('10:8E0D', tuple(range(1, 8))), ('05:A8AE', (0, 1, 2, 3, 4, 6, 7))), lists='ch3_endor_', vars=(10, 14),
              vars2=(0, 20), far=(0x4EC000, 0x4ED000)),
    'T': Slot('굴 공사·개통·장 끝', 'dq4ch3tunnel', (0x5CFC00, 0x5D0000), flags=(0x77,),
              scripts=(('05:996C', (0, 1, 2, 3, 4, 5, 7, 14)),), lists='ch3_tunnel_'),
    'W': Slot('마을 사람 진행별 대사', 'dq4ch3towns', (0x5FF800, 0x600000), flags=(0x79,),
              scripts=(('10:B135', (3, 4, *range(6, 11))), ('10:CFF4', (2, 5, 7, 10, 11, 12))), lists='ch3_towns_'),
    # 코드·flag 없음: 줄은 2장 동료 대화(dq4ch2slots 'P')의 표에 합쳐 그 몫에 들어간다. 다른 모듈이 만든 목록에서 말 상대의
    # 대화 번호를 찾으므로 맨 끝 차례여야 한다
    'P': Slot('동료 대화(はなす) 3장 줄', 'dq4ch3partytalk', (), flags=(), lists='ch3_party_'),
}

# 공용 장치(dq4ch3event)의 몫: flag 바이트 6F(대화 호출 결과·동행 비트), 변수 칸 +0~+3(날수 둘·시계)
COMMON_FLAGS = (0x6F,)
COMMON_VARS = (0, 4)
# 아직 아무에게도 주지 않은 몫. 쓰려면 이 표를 고친다. 이벤트 무리·DQ5 몬스터는 FC 3장에 사건 전투가 없어(fc/dq4/docs/
# dq4-chapter3-format.md 「사건 차례」) 나누지 않고 2장 예비(dq4ch2slots.SPARE)에 둔다
SPARE = {
    'flags': (0x7B, 0x7C),
    'vars': (),
    'vars2': (21, 25),
    'code': (),
}
# 엔돌 카지노 FC 슬롯(dq4fcslot: 코드·화면·무늬·릴 띠). 4E 라 BRK 없이 JSL 만 쓴다
CASINO_CODE = (0x4ED000, 0x4F0000)
# 여신상 동굴의 배(dq4raft, S 가 hooks 로 둠). S 몫 코드 자리가 차서 따로 둔다. 5D:8000~ 은 dq4windowtext 몬스터 자료
RAFT_CODE = (0x5DF000, 0x5DF800)
# 뱅크 4E 의 몫: 3장 몬스터·떠돌이 상인(dq4fieldencounter.CH3_CODE_AT 부터, 사건 모듈 밖), 엔돌(E 의 far), 나머지 예비(SPARE).
# 4E 처럼 40 이상 뱅크의 코드는 BRK 를 바로 쓰지 못한다: BRK 처리기가 놓인 뱅크를 DB 로 두어 낮은 WRAM 대신 롬을 읽는다
# (실측: 4E 에서 BRK 95 34 가 04:DADA 에서 끝없이 돎). 낮은 뱅크 받침(LOW_STUBS 같은 BRK … / RTL)으로 부른다
MONSTERS_CODE = (0x4E8000, 0x4EC000)
# 엔돌(E) 몫의 낮은 뱅크 BRK 받침(dq4neneshop.BRKS). 원래 롬 빈 자리(dq5build free) 가운데 아무 도구도 쓰지 않던 곳
LOW_STUBS = (0x29FF80, 0x29FFF0)
# 본몰(B) 몫의 낮은 뱅크 BRK 받침(dq4ch3bonmalmo.LOW_BRKS). 같은 빈 자리의 끝
BONMALMO_STUBS = (0x29FFF0, 0x2A0000)
# 3장 넘김·공용 장치 코드(dq4ch3event.CODE_AT~TABLE_AT)와 대화 호출 표(TABLE_AT~CODE_END)
BASE_CODE = (0x5CC000, 0x5CD000)


def owner_of_flag(index):
    """flag 바이트 번호의 주인 키(공용이면 'common', 없으면 None)."""
    if index in COMMON_FLAGS:
        return 'common'
    return next((k for k, s in SLOTS.items() if index in s.flags), None)


def script_lists():
    """{DQ5 목록 주소: 키}."""
    return {lst: k for k, s in SLOTS.items() for lst, _ in s.scripts}
