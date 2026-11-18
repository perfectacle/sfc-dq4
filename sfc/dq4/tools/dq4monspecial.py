"""DQ5 에 짝이 없는 FC 몬스터 행동 다섯을 비어 있는 DQ5 행동 번호 C6~CA 에 옮긴다.

DQ5 는 행동 번호마다 첫 메시지(26:8565), MP·범위·적 쪽(26:8765), 실행 루틴(26:8865), 처리 루틴(20:B7F9), 연출
(26:8C75), AI 조건(21:BB42)을 따로 가지므로 FC 행동 하나에 번호 하나를 준다. C6~D4 는 원래 롬에서 앞의 네 표가 모두
빈 값이다(dq5spellgrow 와 같은 범위). 형식: sfc/dq4/docs/dq4-sprite-format.md 「행동」.

  C6 やくそう(FC 5F, 행동 ID 70)    같은 편 하나, 양 88~112(27:8071 칸 06), AI 조건 0E(같은 편 HP 절반 미만)
  C7 ピオリム(FC 1E, 행동 ID 23)    같은 편 모두의 민첩 + 기록 민첩(255 에서 멈춤), MP 는 FC 값
  C8 みをまもる+たすけ(FC 49, 5A)   자기 방어(상태 3E) 뒤 같은 몬스터 부르기, AI 조건: 살아 있는 몬스터가 8 미만
  C9 マホステ(FC 1B, 행동 ID 1D)    자기에게 상태 44, 다른 쪽이 건 주문은 「…에게는 주문이 닿지 않는다!」 로 막음
  CA ブーメラン(FC 64, 행동 ID 75)  첫 메시지만 다르고 たたかう(73)와 같음(FC 11:$B16C 가 보통 공격 11:$96CB 하나)
"""
import json
from pathlib import Path

FIRST = 0xC6
# dq4monport 의 부르기 칸(같은 몬스터 B5, ホイミスライム B4)과 FC ホイミスライム 번호. dq4monport 가 이 모듈을 부르므로 값을 둔다
SUMMON_SAME, SUMMON_FIXED, SUMMON_FIXED_FC = 0xB5, 0xB4, 0x14
HERB, PIORIMU, GUARD, MAHOSTE, BOOMERANG = range(FIRST, FIRST + 5)
LAST = BOOMERANG
FC_ACTIONS = {0x5F: HERB, 0x1E: PIORIMU, 0x49: GUARD, 0x1B: MAHOSTE, 0x64: BOOMERANG}
FC_SPELL_IDS = {PIORIMU: 0x23, MAHOSTE: 0x1D}       # MP 를 읽는 FC 주문 ID(dq4data.spell_mp)

FLAGS, EXECUTOR, INTRO, HANDLER = 0x268765, 0x268865, 0x268565, 0x20B7F9
FX_MONSTER = 0x268C75
BLANK = {'flags': 0x1F, 'executor': 0xDB0C, 'intro': 0x0070, 'handler': 0xAF27}
# 26:8565 는 첫 메시지 번호다(AF 를 고르자 26:8565[AF] = 049「なかまを よんだ」 뒤 부르기). 1A3~1A7 은 원래 롬에서 쓰이지 않는
# 전투 글 번호(dq4battlemsg.UNUSED)로, 한글은 dq4battletexts.SOURCE 에 둔다
MSG_HERB, MSG_PIORIMU, MSG_MAHOSTE, MSG_BOOMERANG, MSG_BLOCKED = 0x1A3, 0x1A4, 0x1A5, 0x1A6, 0x1A7
MSG_GUARD, MSG_HELP, MSG_SUMMONED, MSG_MIST, MSG_SPEED = 0x030, 0x04D, 0x04B, 0x09B, 0x0F4
ATTACK, DEFEND, MONSTER_SCALA = 0x73, 0x71, 0x57
EXEC_ALLY_ONE = 0x9824
HERB_AMOUNT = 0x06                  # 27:8071 칸 06 = 바탕 88, 폭 25(FC やくそう 13:$B573 의 88~112 와 같음)
STATUS_ALIVE, STATUS_DEFEND, STATUS_MAHOSTE = 0x29, 0x3E, 0x44
# 상태 44 는 몬스터의 상태를 모두 지우는 20:FBF4(20:FC8E)만 끄고 켜거나 보는 곳이 없다(롬 정적 검색)

# 뱅크 20 에 빈 자리가 없어 쓰지 않는 부르기 처리기 둘(20:D9D6 + 4 × (행동 − AE), LDA #몬스터 / BRA 20:DA4B)을 먼
# 코드로 가는 JML 로 쓴다. AF·B1 은 이 해킹의 DQ5 몬스터가 쓰지 않는다(test_dq4monspecial)
EXEC_GATE, HANDLER_GATE = 0x20D9DA, 0x20D9E2
# 메시지 BRK 는 부른 뱅크를 데이터 뱅크로 쓰므로 WRAM 낮은 거울이 있는 뱅크(00~3F)에 둔다. 0B:FBB0~ 는 원래 롬 빈 자리
CODE_AT = 0x0BFC00
COND_AT = 0x21FFC2                  # 뱅크 21 끝 빈 자리(62바이트). AI 조건 루틴(21:B4AD 등)을 JSR 로 부른다
RTL_20 = 0x20FF05                   # 뱅크 20 의 RTL 한 바이트: 먼 코드가 RTS 로 끝나는 뱅크 20 루틴을 부를 때 돌아올 곳
WAIT = 0x209DD6                     # 메시지 기다림(RTS)
CLC_RTS, SEC_RTS = 0x20CC24, 0x20A776   # CLC / RTS, SEC / RTS
AMOUNT = 0x20AB70                   # A = 양 칸, 27:8071 에서 $10EC 로(ホイミ 20:B533 이 JMP 로 감)
# 훅 자리: (자리, 원래 바이트)
HOOK_FX = (0x268B64, bytes.fromhex('e0 d5 b0 1f'))         # CPX #$D5 / BCS 8B87: D5 밑만 연출 표를 읽음
FX_READ, FX_SHOW, FX_NONE = 0x268B68, 0x268B78, 0x268B87
HOOK_BLOCK = (0x20A782, bytes.fromhex('ad f6 10 30'))      # 대상 검사(A76E → A77F·A778 둘 다 여기로)
BLOCK_PARTY, BLOCK_MONSTER, BLOCK_RTS = 0x20A787, 0x20A789, 0x20A7B3
HOOK_HELP = (0x20DAEA, bytes.fromhex('00 a7 4b 38'))       # 부르기 성공 메시지 BRK A7 4B / SEC
HELP_RTS = 0x20DAEE
HOOK_COND = (0x21B3F0, bytes.fromhex('ad f7 10'))          # LDA $10F7(조건 표 찾기의 첫 줄)
COND_ORIG, COND_RESET, COND_HEAL, COND_FINISH, COND_DONE = 0x21B3F3, 0x21B4AD, 0x21B8E9, 0x21B4BB, 0x21B42B
MONSTER_SLOT_A = 0x7E07CA           # 몬스터 칸 +A: bit7 있는 칸, bit6 살아 있음
# 전투 그림 칸: 그림 칸마다 몬스터 번호 넷, 쓴 칸 수, 쓴 너비, 칸마다 상태·너비(22:D1A9 가 읽는 것)
PICTURES, USED_CELLS, USED_WIDTH, PIC_STATE, PIC_WIDTH = 0x7E117C, 0x7E0D0C, 0x7E0D0D, 0x7E0C24, 0x7E0C29
PIC_COUNT, PIC_USED = 0x7E0D0E, 0x7E0C1A          # 그림 칸 수, 칸마다 쓰는 수(22:D322·D32B)
PIC_TILES, TILE_COUNT, TILE_KIND = 0x0C3D, 0x0D13, 0x0D1B      # DB 7E 로 읽고 쓰는 abs 자리
TILE_FREE, RTL_22 = 0x22D62E, 0x22D1F3  # 빈 타일 자리 찾기(RTS), 뱅크 22 의 RTL 한 바이트
TILE_SAVED, TILE_DP = (0x7E0D13, 0x7E0D1B, 0x7E0CA3), (0x60, 0x61, 0x62, 0x63, 0x64, 0x65)


def _w(x):
    return (x & 0xFFFF).to_bytes(2, 'little')


def _l(x):
    return x.to_bytes(3, 'little')


def far_code(summon_same, at=CODE_AT):
    """(바이트, 라벨). summon_same 은 같은 몬스터 부르기 코드(dq4monport.summon_code 의 'same')."""
    import dq4fieldencounter
    from dq4environmentrom import _Asm
    hoimi = dq4fieldencounter.MONSTERS[SUMMON_FIXED_FC]
    a = _Asm(at)
    jml = lambda x: a.b(0x5C, *_l(x))  # noqa: E731
    brk = lambda *v: a.b(0x00, *v)  # noqa: E731

    def jump_if(value, name):
        a.b(0xC9, value).rel(0xD0, f'_{name}_{value:02X}').word(0x4C, name).label(f'_{name}_{value:02X}')

    # 실행 루틴(26:8865 = EXEC_GATE). M·X 8비트, $10F5 행동하는 쪽, $10F6 대상. 범위가 자기(26:8765 bit5-6 = 0)여도
    # $10F6 은 행동하는 쪽이 아닐 수 있다(세 무리 전투에서 81 의 행동에 $10F6 = 80, 실측)
    a.label('exec').b(0xE2, 0x30, 0xAD, 0xF7, 0x10)
    jump_if(PIORIMU, 'piorimu')
    jump_if(GUARD, 'guard')
    jump_if(MAHOSTE, 'mahoste')
    jml(CLC_RTS)

    # みをまもる: 상태 3E(20:AF85 가 피해를 절반으로) 뒤 같은 몬스터 부르기. FC 5A 는 턴 처음(11:$A9EC 는 41·42 만)이
    # 아니라 행동할 때 지키므로 20:9D55 의 턴 처음 목록에 넣지 않는다
    a.label('guard').b(0xAD, 0xF5, 0x10, 0x29, 0x0F, 0x85, 0x42, 0xA9, STATUS_DEFEND, 0x85, 0x43)
    brk(0x88, 0x7A)
    jml(summon_same)

    a.label('mahoste').b(0xAD, 0xF5, 0x10).rel(0x10, 'mahoste_done')
    a.b(0x29, 0x0F, 0x85, 0x42, 0xA9, STATUS_MAHOSTE, 0x85, 0x43)
    brk(0x88, 0x7A)
    a.b(0xAD, 0xF5, 0x10, 0x85, 0xF5)
    brk(0xA1, MSG_MIST)
    a.word(0x20, 'wait')
    a.label('mahoste_done')
    jml(SEC_RTS)

    # ピオリム: 행동하는 몬스터 쪽의 살아 있는 칸 0~F 마다 민첩(+5, 필드 5C 읽기·5D 쓰기)에 기록 민첩(필드 5F)을 더하고
    # 0F4. 255 를 넘지 않게 더하는 양을 줄인다(dq4party 의 일행 ピオリム 과 같은 식)
    a.label('piorimu').b(0xAD, 0xF5, 0x10).rel(0x30, 'p_monster')
    jml(CLC_RTS)
    a.label('p_monster').b(0xA2, 0x00)
    a.label('p_loop').b(0xDA, 0x86, 0x42, 0xA9, STATUS_ALIVE, 0x85, 0x43)
    brk(0x88, 0x79)
    a.b(0xFA, 0xA5, 0x49).rel(0xD0, 'p_alive').word(0x4C, 'p_next')
    a.label('p_alive').b(0x8A, 0x09, 0x80, 0xCD, 0xF5, 0x10).rel(0xF0, 'p_raise')
    a.b(0xDA, 0x86, 0x42, 0xA9, STATUS_MAHOSTE, 0x85, 0x43)
    brk(0x88, 0x79)
    a.b(0xFA, 0xA5, 0x49).rel(0xF0, 'p_raise')
    a.b(0xDA, 0x8A, 0x09, 0x80, 0x85, 0xF5)
    brk(0xA2, MSG_BLOCKED & 0xFF)
    a.word(0x20, 'wait').b(0xFA).word(0x4C, 'p_next')
    a.label('p_raise').b(0xDA, 0x86, 0x42, 0x64, 0x43, 0x64, 0x44)
    brk(0x88, 0x5F)
    a.b(0xA5, 0x46, 0x85, 0x71)                                       # $71 = 기록 민첩
    brk(0x88, 0x5C)
    a.b(0xA9, 0xFF, 0x38, 0xE5, 0x46, 0xC5, 0x71).rel(0xB0, 'p_add')  # 255 - 지금 < 기록 민첩이면 그만큼만
    a.b(0x85, 0x71)
    a.label('p_add').b(0xA5, 0x46, 0x18, 0x65, 0x71, 0x85, 0x43)
    brk(0x88, 0x5D)
    a.b(0xFA, 0xDA, 0x8A, 0x09, 0x80, 0x85, 0xF5, 0xA5, 0x71, 0x85, 0xF6, 0x64, 0xF7)
    brk(0xA4, MSG_SPEED)
    brk(0x16, 0x46, 0x04)
    a.word(0x20, 'wait').b(0xFA)
    a.label('p_next').b(0xE8, 0xE0, 0x10).rel(0xB0, 'p_end').word(0x4C, 'p_loop')
    a.label('p_end')
    jml(CLC_RTS)

    # 처리 루틴(20:B7F9 = HANDLER_GATE): やくそう 의 양
    a.label('handler').b(0xE2, 0x30, 0xA9, HERB_AMOUNT)
    jml(AMOUNT)

    # 26:8B64 에서: C6~CA 는 아래 표의 연출(FF 면 없음), 그 밖은 원래대로
    a.label('fx').b(0xE0, FIRST).rel(0x90, 'fx_orig').b(0xE0, LAST + 1).rel(0xB0, 'fx_orig')
    a.long(0xBF, 'fx_table', -FIRST).b(0xC9, 0xFF).rel(0xF0, 'fx_none')
    jml(FX_SHOW)
    a.label('fx_none')
    jml(FX_NONE)
    a.label('fx_orig').b(0xE0, 0xD5).rel(0xB0, 'fx_none')
    jml(FX_READ)
    a.label('fx_table').b(*[0xFF] * (LAST + 1 - FIRST))

    # 20:A782 에서(대상 검사): 몬스터 대상에 다른 쪽이 건 주문이고 그 몬스터에 상태 44 면 막는다. FC 11:$8D25 는
    # 대상이 외운 쪽 자신이면 막지 않는다(11:$8D09)
    a.label('block').b(0xAD, 0xF6, 0x10).rel(0x30, 'b_monster')
    jml(BLOCK_PARTY)
    a.label('b_monster').b(0xAD, 0xF7, 0x10, 0xC9, 0x66).rel(0x90, 'b_spell')
    a.b(0xC9, PIORIMU).rel(0xF0, 'b_spell').b(0xC9, MAHOSTE).rel(0xD0, 'b_pass')
    a.label('b_spell').b(0xAD, 0xF6, 0x10, 0xCD, 0xF5, 0x10).rel(0xF0, 'b_pass')
    a.b(0x29, 0x0F, 0x85, 0x42, 0xA9, STATUS_MAHOSTE, 0x85, 0x43)
    brk(0x88, 0x79)
    a.b(0xA5, 0x49).rel(0xF0, 'b_pass')
    a.b(0xAD, 0xF6, 0x10, 0x85, 0xF5)
    brk(0xA2, MSG_BLOCKED & 0xFF)
    a.b(0x38)
    jml(BLOCK_RTS)
    a.label('b_pass').b(0xAD, 0xF6, 0x10)
    jml(BLOCK_MONSTER)

    # 20:DAEA 에서(부르기 성공): みをまもる+たすけ 면 FC 002F 와 같은 「…이 도우러 나타났다!」
    a.label('help').b(0xAD, 0xF7, 0x10, 0xC9, GUARD).rel(0xD0, 'h_plain')
    brk(0xA7, MSG_HELP)
    a.b(0x38)
    jml(HELP_RTS)
    a.label('h_plain')
    brk(0xA7, MSG_SUMMONED)
    a.b(0x38)
    jml(HELP_RTS)

    # AI 조건(COND_AT 에서 JSL). 맞으면 $10F6 = 0·대상 마스크 FF, 아니면 $10F6 = FF·마스크 0(21:BA02·B9F6 과 같은 꼴)
    a.label('cond').b(0xAD, 0xF7, 0x10, 0xC9, GUARD).rel(0xF0, 'c_guard')
    a.b(0xC9, SUMMON_SAME).rel(0xF0, 'c_guard').b(0xC9, SUMMON_FIXED).rel(0xF0, 'c_guard')
    a.b(0x2C, 0x10, 0x11).rel(0x10, 'c_yes')                         # $1110 bit7: 행동하는 쪽이 몬스터
    a.b(0xAD, 0xF5, 0x10, 0x29, 0x0F, 0x85, 0x42, 0xA9, STATUS_MAHOSTE, 0x85, 0x43)
    brk(0x88, 0x79)
    a.b(0xA5, 0x49).rel(0xD0, 'c_no')
    a.label('c_yes').b(0x9C, 0xF6, 0x10, 0xA9, 0xFF, 0x8D, 0x0E, 0x11, 0x6B)
    a.label('c_no').b(0xA9, 0xFF, 0x8D, 0xF6, 0x10, 0x9C, 0x0E, 0x11, 0x9C, 0x0F, 0x11, 0x6B)
    a.label('c_guard').b(0xA0, 0x00, 0xA2, 0x00)                     # 살아 있는 몬스터 칸(+A bit6) 세기
    a.label('c_count').b(0xBF, *_l(MONSTER_SLOT_A), 0x29, 0x40).rel(0xF0, 'c_skip').b(0xC8)
    a.label('c_skip').b(0x8A, 0x18, 0x69, 0x10, 0xAA).rel(0xD0, 'c_count')
    a.b(0xC0, 0x08).rel(0x90, 'c_screen')
    a.label('c_far_no').word(0x4C, 'c_no')
    a.label('c_far_yes').word(0x4C, 'c_yes')
    a.label('c_screen')
    # 화면 자리: 부르기의 22:D1A9 는 자리가 있으면 그 자리를 잡아 버리므로(22:D226 INC $0D0C) 부르지 않고 같은 검사를
    # 따라 한다. 그림 칸(7E:117C 에서 행동하는 몬스터의 차례 X)마다 쓴 칸 수 $0D0C < 16, $0C24,X 가 0 이거나 음수,
    # 빈 타일 자리(22:D62E, $0D13·$0D1B 를 넣고 DB 7E 로), 100 − 쓴 너비 $0D0D − 그림 너비 $0C29,X ≥ 0(22:D1B6~D1E1).
    # D62E 가 쓰는 $60~$65·$0CA3·$0D13·$0D1B 는 되돌린다(7E:5C00 은 부를 때마다 새로 채우는 표). FC 도 그림 자리가
    # 없으면 고르지 않는다(10:$BC50)
    # 부를 몬스터: B4 는 ホイミスライム, 나머지는 행동하는 몬스터와 같은 몬스터
    a.b(0xAD, 0xF7, 0x10, 0xC9, SUMMON_FIXED).rel(0xD0, 'c_own').b(0xA9, hoimi).rel(0x80, 'c_find')
    a.label('c_own').b(0xAD, 0xF5, 0x10, 0x29, 0x0F, 0x0A, 0x0A, 0x0A, 0x0A, 0xAA, 0xBF, *_l(MONSTER_SLOT_A - 0x0A))
    a.label('c_find').b(0xA2, 0x00)
    a.label('c_pic').b(0xDF, *_l(PICTURES)).rel(0xF0, 'c_room').b(0xE8, 0xE0, 0x04).rel(0x90, 'c_pic')
    # 그림이 아직 없으면(B4) 새 그림 칸: 22:D2FE 처럼 쓴 칸 수 < 16, 그림 칸 $0D0E < 4 이거나 빈 그림 칸($0C1A,X = 0)이
    # 있어야 한다. 그 뒤의 타일 풀기(22:9088)·자리(22:D62E)는 그림을 실어야 알 수 있어 따라 하지 않는다
    a.b(0xAF, *_l(USED_CELLS), 0xC9, 0x10).rel(0xF0, 'c_far_no')
    a.b(0xAF, *_l(PIC_COUNT), 0xC9, 0x04).rel(0x90, 'c_far_yes').b(0xA2, 0x00)
    a.label('c_slot').b(0xBF, *_l(PIC_USED)).rel(0xF0, 'c_far_yes').b(0xE8, 0xE0, 0x04).rel(0x90, 'c_slot')
    a.rel(0x80, 'c_far_no')
    a.label('c_room').b(0xAF, *_l(USED_CELLS), 0xC9, 0x10).rel(0xD0, 'c_cells').rel(0x80, 'c_far_no')
    a.label('c_cells').b(0xBF, *_l(PIC_STATE)).rel(0xF0, 'c_tiles').rel(0x10, 'c_far_no')
    a.label('c_tiles')
    for at in TILE_SAVED:
        a.b(0xAF, *_l(at), 0x48)
    for dp in TILE_DP:
        a.b(0xA5, dp, 0x48)
    a.b(0x8B, 0xA9, 0x7E, 0x48, 0xAB, 0xDA)
    a.b(0xBD, *_w(PIC_TILES), 0x8D, *_w(TILE_COUNT), 0xBD, *_w(PIC_STATE), 0x8D, *_w(TILE_KIND))
    a.b(0x4B).word(0xF4, 'c_tiles_back', -1).b(0xF4, *_w(RTL_22 - 1))
    a.b(0x5C, *_l(TILE_FREE))
    a.label('c_tiles_back').b(0xFA, 0xAB)
    for dp in reversed(TILE_DP):
        a.b(0x68, 0x85, dp)
    for at in reversed(TILE_SAVED):
        a.b(0x68, 0x8F, *_l(at))
    a.rel(0x90, 'c_end_no')
    a.b(0xA9, 0x64, 0x38, 0xEF, *_l(USED_WIDTH), 0xFF, *_l(PIC_WIDTH)).rel(0x90, 'c_end_no')
    a.word(0x4C, 'c_yes')
    a.label('c_end_no').word(0x4C, 'c_no')

    # 뱅크 20 의 RTS 루틴 부르기: RTL_20 으로 돌아와 RTL 이 여기로
    a.label('wait').b(0x4B).word(0xF4, 'wait_back', -1).b(0xF4, *_w(RTL_20 - 1))
    jml(WAIT)
    a.label('wait_back').b(0x60)
    return a.assemble()


def cond_code(far_cond, at=COND_AT):
    """뱅크 21 의 조건 스텁. 21:B3F0 의 JMP 로 들어온다."""
    from dq4environmentrom import _Asm
    a = _Asm(at)
    a.b(0xAD, 0xF7, 0x10, 0xC9, HERB).rel(0xF0, 'herb')
    for n in (GUARD, MAHOSTE, SUMMON_SAME, SUMMON_FIXED):
        a.b(0xC9, n).rel(0xF0, 'far')
    a.b(0x4C, *_w(COND_ORIG))
    a.label('herb').b(0x20, *_w(COND_RESET), 0x20, *_w(COND_HEAL)).rel(0x80, 'finish')
    a.label('far').b(0x20, *_w(COND_RESET), 0x22, *_l(far_cond))
    a.label('finish').b(0x20, *_w(COND_FINISH), 0x4C, *_w(COND_DONE))
    data, labels = a.assemble()
    if at + len(data) > 0x220000:
        raise ValueError('조건 스텁이 뱅크 21 끝을 넘음')
    return data, labels


def rows(prg):
    """행동 번호 → (MP·범위·적 쪽, 실행 루틴, 첫 메시지, 처리 루틴 또는 None(빈 값 그대로), 연출을 베낄 행동 또는 None)."""
    import dq4data
    mp = {n: dq4data.spell_mp(prg, fc)[0] for n, fc in FC_SPELL_IDS.items()}
    return {
        HERB: (0x3F, EXEC_ALLY_ONE, MSG_HERB, HANDLER_GATE, None),                    # MP 없음, 같은 편 하나
        PIORIMU: (mp[PIORIMU] | 3 << 5, EXEC_GATE, MSG_PIORIMU, None, MONSTER_SCALA),  # 같은 편 모두
        GUARD: (0x1F, EXEC_GATE, MSG_GUARD, None, DEFEND),                           # 자기
        MAHOSTE: (mp[MAHOSTE], EXEC_GATE, MSG_MAHOSTE, None, MONSTER_SCALA),          # 자기
        BOOMERANG: (None, None, MSG_BOOMERANG, None, ATTACK),                         # たたかう 그대로 베낌
    }


def writes(original, prg, summon_same):
    """dq5patch/1 쓰기."""
    from dq5map import lorom
    rd = lambda a, n: original[lorom(a):lorom(a) + n]  # noqa: E731
    out = []

    def put(at, new, note, orig=None):
        w = {'at': f'{at >> 16:02X}:{at & 0xFFFF:04X}', 'hex': bytes(new).hex(' '), 'note': note}
        if orig is not None:
            w['orig'] = bytes(orig).hex(' ')
        out.append(w)

    def hook(site, target, note, pad=0):
        at, orig = site
        if rd(at, len(orig)) != orig:
            raise ValueError(f'{at:06X} 이 {rd(at, len(orig)).hex()}')
        put(at, bytes((0x5C, *_l(target))) + bytes((0xEA,) * pad), note, orig)

    data, labels = far_code(summon_same)
    cond, _ = cond_code(labels['cond'])
    table = rows(prg)
    fx = bytearray(data)
    at = labels['fx_table'] - CODE_AT
    for n, (_, _, _, _, src) in table.items():
        fx[at + n - FIRST] = 0xFF if src is None else rd(FX_MONSTER + src, 1)[0]
    put(CODE_AT, fx, 'FC 몬스터 행동 C6~CA: 실행·처리·연출·대상 검사·부르기 메시지·AI 조건')
    put(COND_AT, cond, 'AI 조건 스텁: C6 은 조건 0E, C8·C9 는 먼 코드')
    for n, (flags, executor, intro, handler, _) in sorted(table.items()):
        src = ATTACK if n == BOOMERANG else None
        flags = rd(FLAGS + src, 1)[0] if flags is None else flags
        executor = int.from_bytes(rd(EXECUTOR + 2 * src, 2), 'little') if executor is None else executor
        handler = int.from_bytes(rd(HANDLER + 2 * src, 2), 'little') if src is not None else handler
        cells = (('flags', FLAGS + n, 1, flags), ('executor', EXECUTOR + 2 * n, 2, executor),
                 ('intro', INTRO + 2 * n, 2, intro), ('handler', HANDLER + 2 * n, 2, handler))
        for name, addr, size, value in cells:
            orig = rd(addr, size)
            if int.from_bytes(orig, 'little') != BLANK[name]:
                raise ValueError(f'행동 {n:02X} 의 {name} 이 빈 값이 아님: {orig.hex()}')
            if value is not None:
                put(addr, (value & 0xFFFF).to_bytes(size, 'little'), f'행동 {n:02X} {name}', orig)
    for gate, label in ((EXEC_GATE, 'exec'), (HANDLER_GATE, 'handler')):
        orig = rd(gate, 4)
        if orig[0] != 0xA9 or orig[2] != 0x80:
            raise ValueError(f'{gate:06X} 이 부르기 처리기가 아님: {orig.hex()}')
        put(gate, bytes((0x5C, *_l(labels[label]))), f'쓰지 않는 부르기 처리기를 {label} 입구로', orig)
    hook(HOOK_FX, labels['fx'], '연출 표: C6~CA 는 먼 표')
    hook(HOOK_BLOCK, labels['block'], '대상 검사: マホステ 상태 44 면 주문을 막음')
    hook(HOOK_HELP, labels['help'], '부르기 성공 메시지: C8 이면 04D')
    at, orig = HOOK_COND
    if rd(at, len(orig)) != orig:
        raise ValueError(f'{at:06X} 이 {rd(at, len(orig)).hex()}')
    put(at, bytes((0x4C, *_w(COND_AT))), 'AI 조건 찾기를 스텁으로', orig)
    return out


def doc(original, prg, summon_same, path):
    Path(path).write_text(json.dumps({'format': 'dq5patch/1', 'name': 'dq4-monster-special',
                                      'writes': writes(original, prg, summon_same)}, ensure_ascii=False))
    return path
