"""2장 사건 세션의 자원 예약표(정본). 형식 문서 sfc/dq4/docs/dq4-chapter2-format.md 「사건 등록과 자원 예약」.

2장 사건은 세션마다 새 모듈(dq4ch2event.EVENTS 에 한 줄로 등록)로 만든다. 모듈끼리 덮어쓰지 않게 롬·WRAM 자원을
여기서 미리 나눈다. 모듈은 자기 몫만 쓰고, 모자라면 이 표를 먼저 고치는 작은 PR 을 올린다.
test_dq4ch2slots 가 등록된 모듈이 몫 안에 있는지 본다.

메시지·대화 번호·대체 목록은 번호를 미리 나누지 않는다. 번호는 EVENTS 차례로 이어 붙여 자동으로 매기고(빈 번호가 없어야
해서), 대체 목록은 이름 앞머리로 나눈다. 대신 메시지 덩어리·대화 스크립트·대체 목록 자리의 바이트 몫을 적는다.
"""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Slot:
    name: str
    module: str                    # dq4ch2event.EVENTS 에 넣을 모듈 이름
    code: tuple                    # (시작, 끝) 사건 네이티브 코드 자리. 끝은 들지 않음
    flags: tuple                   # 쓸 수 있는 flag 바이트(7E:2190 + 번호의 번호). 바이트째 몫
    byte_flags: tuple = ()         # 그 가운데 바이트 값으로 쓰는 것(단계 수 따위)
    groups: tuple = ()             # 이벤트 무리 번호(23:D757 표)
    monsters: tuple = ()           # 덮어쓸 DQ5 몬스터 번호
    battles: tuple = ()            # 대화 스크립트에서 부르는 전투 입구(dq4ch2battle.STUBS 의 칸)
    scripts: tuple = ()            # 빌릴 DQ5 인물 스크립트: ((목록, (칸, ...)), ...)
    lists: str = ''                # 새 대체 목록 이름 앞머리
    message_bytes: int = 0         # 메시지 덩어리 몫(부호화한 바이트)
    talk_bytes: int = 0            # 대화 스크립트 자리 몫
    list_bytes: int = 0            # 대체 목록 자리 몫
    notes: tuple = field(default=())


# 7E:21F0~220C 는 DQ5 가 색인 쓰기로만 덮는 자리다: 02:E053 STA $21EF,X(15/01 수수께끼 맵의 맵 루틴), 05:DF2A·E31D·E324
# 의 $21FA,X·$21FB,X(31/07 바위 맵), 23:E20E·E214 의 $21F5,X·$21F6,X(02:9BC0 파파스가 쓰러지는 장면만 부름). 이 해킹의
# 맵 그룹은 36~47 이라 세 장면은 돌지 않는다. 이미 2장 flag(2208)가 같은 근거로 이 자리를 쓴다. 21F5·21F6·21F8~21FB 는
# 고정 주소로도 쓰여 뺀다. 그 앞 21C2~21EE 에 남은 비트는 배 X·Y(21DB~21DE)의 16비트 쓰기 따위에 휩쓸려 쓰지 않는다
SLOTS = {
    'E1': Slot('텐페 뒤 절반', 'dq4ch2tempe', (0x5FA000, 0x5FB000), flags=(0x60,),
               groups=(0x31,), monsters=(0xA3, 0x53), battles=(0,),
               scripts=(('05:9C2B', tuple(range(14))),), lists='ch2_tempe2_',
               message_bytes=2048, talk_bytes=1024, list_bytes=2048),
    'E2': Slot('프레놀 가짜 공주·남쪽 동굴', 'dq4ch2frenol', (0x5FB000, 0x5FC000), flags=(0x61,),
               scripts=(('05:CD73', tuple(range(11))),), lists='ch2_frenol_',
               message_bytes=3072, talk_bytes=1536, list_bytes=3072),
    'E3': Slot('바자·왕 병·서쪽 탑·왕 회복·여행의 문 사당', 'dq4ch2king', (0x5FC000, 0x5FD000), flags=(0x62, 0x63),
               scripts=(('10:98AE', tuple(range(17))),), lists='ch2_king_',
               message_bytes=4096, talk_bytes=2048, list_bytes=4096),
    'E4': Slot('엔돌 무술 대회', 'dq4ch2endor', (0x5FD000, 0x5FE800), flags=(0x64, 0x67), byte_flags=(0x67,),
               groups=(0x32, 0x33, 0x34, 0x35, 0x36), monsters=(0xAA, 0xA4, 0x8E, 0x68, 0x72), battles=(1, 2, 3),
               scripts=(('10:A732', tuple(range(11))), ('10:9A2F', tuple(range(2, 12)))), lists='ch2_endor_',
               message_bytes=4096, talk_bytes=2048, list_bytes=8192),
    'E5': Slot('빈 산트하임·2장 끝·마을 사람 진행별 대사', 'dq4ch2ending', (0x5FE800, 0x5FF800), flags=(0x6C,),
               scripts=(('10:8414', (2, 3, 7, 8, 9, 10, 11, 12, 13, 14)), ('10:CB92', tuple(range(9)))),
               lists='ch2_ending_', message_bytes=8192, talk_bytes=8192, list_bytes=8192),
    'P': Slot('동료 대화(はなす)', 'dq4ch2partytalk', (0x5C8000, 0x5CC000), flags=(0x6D, 0x6E), byte_flags=(0x6E,),
              scripts=(('10:DA05', tuple(range(8))),), lists='ch2_party_',
              message_bytes=4096, talk_bytes=1024, list_bytes=0,
              notes=('대사 몫이 모자라면 메시지 덩어리 셋째 자리를 예약표 PR 로 먼저 잡는다',)),
}

# 모든 사건이 함께 쓰는 것(dq4ch2battle): 마지막으로 건 사건 전투를 이겼는지. 전투마다 다시 쓴다
BATTLE_WON = (0x78, 0x80)      # 7E:2208 bit7
# 아직 아무에게도 주지 않은 몫. 쓰려면 이 표를 고치는 PR 을 먼저 올린다
SPARE = {
    'flags': (0x6F, 0x70, 0x71, 0x72, 0x73, 0x74, 0x75, 0x76, 0x77, 0x79, 0x7A, 0x7B, 0x7C),
    'flag_bits': ((0x78, 0x08), (0x78, 0x20)),          # 2208 bit3·bit5
    'groups': (0x37, 0x38, 0x39, 0x3A),
    'monsters': (0xC5, 0xB6, 0x9D, 0xA5, 0xE3, 0x3D),
    'battles': (4,),
    'code': ((0x5FF800, 0x600000), (0x5CC000, 0x5D0000)),
}
# 2장 첫머리·성·텐페 앞 절반(dq4ch2event)이 이미 쓰는 것. 새 모듈은 쓰지 않는다
BASE_CODE = (0x5EF000, 0x5F0000)


def flag_bytes(slot):
    return set(slot.flags)


def owner_of_flag(index):
    """flag 바이트 번호의 주인 세션 키(없으면 None)."""
    return next((k for k, s in SLOTS.items() if index in s.flags), None)


def script_lists():
    """{DQ5 목록 주소: 세션 키}."""
    return {lst: k for k, s in SLOTS.items() for lst, _ in s.scripts}
