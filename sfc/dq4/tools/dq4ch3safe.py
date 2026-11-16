"""DQ4 3장 북쪽 동굴과 철 금고(dq4ch3slots 'S'): 동굴 단추 둘, 물이 빠진 층으로 가는 계단, 금고 되돌리기, 전멸 때 금화.

FC 그룹 3D(きたのどうくつ)는 SFC 그룹 3E 의 3E/03~09(FC 3D/00~06)에 옮겨져 있다(dq4groupbuild). FC 차례:
  1. 3D/01 의 수문 앞 두 칸 (14,0A)·(08,0E)에 서면(1D 이벤트 26, 표 1D:$A2EF) 「ボタンが あります おしてみますか？」(03B3).
     「はい」 면 수문이 열려 물살이 일행을 아래로 민다. (14,0A) 는 계단 (14,1B)까지 밀려 3D/00 (0A,19)로, (08,0E) 는
     통로 끝 구덩이 (08,25)까지 밀려 3D/03 (08,0F)로 떨어지며 $62AA bit7 이 켜진다(12:$B904). 「いいえ」 면 그 칸을 떠났다
     다시 서야 또 묻는다($6289 bit2).
  2. $62AA bit7 이 켜지면 3D/01 로 가는 출구가 모두 물이 빠진 3D/02 로 간다(08:$B397, 칸 번호 1~3 은 하나 뒤).
  3. 3D/06 (04,03) 상자에 てつのきんこ. 연 뒤 그 칸을 조사하면 바닥 글(0296)과 「てつのきんこを もとにもどしますか？」,
     「はい」 면 금고를 빼고 상자를 닫는다(1E:$B830, 037B).
  4. 전멸하면 3장에서는 일행 소지품에 금고가 있을 때 금화를 반으로 줄이지 않는다(12:$ADC2, 맡긴 물건은 보지 않음).

DQ5 의 しらべる 는 인물 대화를 부르지 않아, 금고 되돌리기는 연 상자 칸을 밟으면 묻는다(보이지 않는 인물). 물살은
그림 없이 주인공을 아래로 걷게 한 뒤 순간이동으로 옮긴다. 형식은 sfc/dq4/docs/dq4-chapter3-format.md 「북쪽 동굴과 금고」.
"""
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[1] / 'dq5' / 'tools')]

import dq4chapter1 as ch1  # noqa: E402
import dq4ch2event as ch2  # noqa: E402
from dq4chapterbox import ENTER, LEAVE  # noqa: E402
from dq4itemport import IRON_SAFE  # noqa: E402

IDX = 0x72                     # 7E:2202
DRAINED = (IDX, 0x01)          # 수문을 열어 구덩이로 떨어짐(FC $62AA&80). 3E/04 로 가는 출구가 3E/05 로
ANSWERED = (IDX, 0x02)         # 보이지 않는 인물의 물음에 대답함(대화가 켜고 인물 스크립트가 끔)
YES = (IDX, 0x04)              # 그 대답이 「예」(단추). 인물 스크립트가 보고 끔
FLAGS = (DRAINED, ANSWERED, YES)

GROUP = 0x3E
# FC 3D/0k 는 SFC 3E/(03+k). test_dq4ch3safe 가 dq4groupbuild.placement 와 견준다
ENTRY, GATES, DRY, PIT, VAULT = '3E/03', '3E/04', '3E/05', '3E/06', '3E/09'


def _map(name):
    return int(name.split('/')[1], 16)


def hero_rect(x0, y0, x1, y1):
    """FC 칸 사각형 → 주인공 셀 사각형(주인공은 FC 칸 (x, y) 에서 (2x 또는 2x+1, 2y+1 또는 2y+2) 에 선다)."""
    return (2 * x0, 2 * y0 + 1, 2 * x1 + 1, 2 * y1 + 2)


def cell(x, y):
    """FC 칸 → 순간이동·계단 도착 셀(dq4groupbuild 의 (2x, 2y+1))."""
    return (2 * x, 2 * y + 1)


# 수문 앞 칸(FC 1D:$A2EF), 물살이 멈추는 FC 줄, 옮겨 갈 자리
RIGHT = {'rect': hero_rect(0x14, 0x0A, 0x14, 0x0A), 'stop': 0x1A, 'to': (ENTRY, cell(0x0A, 0x19))}
LEFT = {'rect': hero_rect(0x08, 0x0E, 0x08, 0x0E), 'stop': 0x24, 'to': (PIT, cell(0x08, 0x0F))}
CHEST = hero_rect(0x04, 0x03, 0x04, 0x03)                  # 3E/09 의 금고 상자(FC 3D/06 (04,03))
DOWN = 0x04                                                 # 이벤트 걸음 명령: 아래

# 빌린 인물 스크립트(DQ5 20/04 대체 목록 10:C8FF, dq4ch3slots S 칸 0·1·4). 칸마다 스크립트 길이 바이트 주소
SCRIPT_LIST = '10:C8FF'
SCRIPTS = {'right': ('10:C906', 0), 'left': ('10:C922', 1), 'chest': ('10:C946', 4)}

# DQ5 출구 목적지 표의 종류 40(같은 그룹, 도착 맵의 출구 번호) 갈래 2A:F7AB: LDA $01 / STA $BD / INY / BRA $F7D6.
# F7D6 이 LDA ($84),Y 로 도착 출구 번호를 읽고 PLB/PLP/RTS 한다. 출구 표를 옮긴 롬(dq5exitreloc)은 F7D6 을 [$84],Y 로
# 바꾸므로 훅이 그 옵코드를 보고 같은 읽기를 한다
EXIT_SITE, EXIT_ORIG = 0x2AF7AB, bytes((0xA5, 0x01, 0x85, 0xBD, 0xC8, 0x80, 0x24))
EXIT_READ = 0x2AF7D6
EXIT_DONE = 0x2AF7D8

# 전멸 뒤 금화를 반으로: 20:815C BRK 9E 가 금화를 $46~$48 에 읽고, 20:8162~8170 이 그 반(잃는 몫)을 $43~$45 에 둔 뒤
# 20:8171 BRK 88 이 금화에서 그만큼 뺀다(실측: 전멸 뒤 7E:2019 쓰기는 21:912B 한 번, 부른 곳 20:8173. $43 을 금화 전부로
# 두자 금화가 0). 그 15바이트를 훅으로 바꾼다
WIPE_SITE = 0x208162
WIPE_ORIG = bytes((0xA5, 0x48, 0x4A, 0x85, 0x45, 0xA5, 0x47, 0x6A, 0x85, 0x44, 0xA5, 0x46, 0x6A, 0x85, 0x43))

# 상자 열림 비트: 25:FAB0 이 chest_maps(25:FAB5 의 즉값 뱅크, 25:FAC4 의 abs)를 (그룹, 맵, 개수) 3바이트씩 훑어 앞 맵들의
# 개수를 더한 것이 그 맵 첫 상자 번호 n 이고, 비트는 7E:2210 + n/8 의 25:FAE9[n & 7]. 3E/09 의 상자는 금고 하나뿐이다
CHEST_BANK, CHEST_TABLE, CHEST_MASKS, CHEST_BITS = 0x25FAB5, 0x25FAC4, 0x25FAE9, 0x7E2210
# dq4brkscan: PHP 로 시작하지 않는 진입점. chest_bit 은 JSR 로 부르는 코드, exit 는 P 를 부른 쪽이 PLP 로 되돌리는
# 훅, flood_* 는 이벤트 스크립트 자료
CODE_ENTRIES = ('chest_bit', 'exit')
DATA_ENTRIES = ('flood_right', 'flood_left')
HERO_X, HERO_Y = 0x7E3020, 0x7E3080
FLAG_AT = 0x7E2190
CHAPTER3_AT = FLAG_AT + 0x78    # dq4ch3event.CHAPTER3
PARTY_COUNT = 0x7E201D


def _al(a):
    return bytes((a & 0xFF, a >> 8 & 0xFF, a >> 16))


def _asm():
    from dq4ch2endor import Asm
    return Asm()


def _rect_test(a, rect, far):
    """M8: 주인공 셀이 rect 밖이면 far 로(인물 표 X·Y 의 bit7 은 지움, dq4prologue._inside 와 같음)."""
    from dq4ch2endor import BCC, BCS, lda
    x0, y0, x1, y1 = rect
    for table, lo, hi in ((HERO_X, x0, x1), (HERO_Y, y0, y1)):
        a(lda(table), 0x29, 0x7F, 0xC9, lo).br(BCC, far)(0xC9, hi + 1).br(BCS, far)


def _answer(a):
    """인물 명령 05 의 끝: near 면 A = 0, far 면 1."""
    a.label('near')(0xC2, 0x30, 0xA9, 0x00, 0x00, 0x28, 0x6B)
    a.label('far')(0xC2, 0x30, 0xA9, 0x01, 0x00, 0x28, 0x6B)


def _inside(rect, away=False):
    """인물 명령 05: 주인공이 rect 안이면(away 면 밖이면) A = 0."""
    a = _asm()(0x08, 0xE2, 0x30)
    _rect_test(a, rect, 'near' if away else 'far')
    from dq4ch2endor import BRA
    a.br(BRA, 'far' if away else 'near')
    _answer(a)
    return a.bytes()


def _chest_bit():
    """JSR 로(M8): 3E/09 상자의 열림 비트. X(16비트) = 7E:2210 에서의 바이트, A = 마스크, C = 0. 표에 그 맵이 없으면 C = 1."""
    from dq4ch2endor import BEQ, BRA
    a = _asm()(0x8B, 0xC2, 0x30, 0xAF, _al(CHEST_TABLE), 0xAA, 0xE2, 0x20, 0xAF, _al(CHEST_BANK), 0x48, 0xAB)
    a(0xA9, 0x00, 0x48)                                                    # 1,S = 앞 맵들의 상자 수
    a.label('row')(0xC2, 0x20, 0xBD, 0x00, 0x00, 0xC9, GROUP, _map(VAULT)).br(BEQ, 'found')
    a(0xC9, 0xFF, 0xFF).br(BEQ, 'none')
    a(0xE2, 0x20, 0xBD, 0x02, 0x00, 0x18, 0x63, 0x01, 0x83, 0x01, 0xE8, 0xE8, 0xE8).br(BRA, 'row')
    a.label('found')(0xE2, 0x20, 0x68, 0xAB, 0x48, 0x4A, 0x4A, 0x4A, 0xC2, 0x20, 0x29, 0x1F, 0x00, 0xAA)
    a(0xE2, 0x20, 0x68, 0xDA, 0xC2, 0x20, 0x29, 0x07, 0x00, 0xAA, 0xE2, 0x20, 0xBF, _al(CHEST_MASKS), 0xFA, 0x18, 0x60)
    a.label('none')(0xE2, 0x20, 0x68, 0xAB, 0x38, 0x60)
    return a


def native(ctx):
    """(바이트, {이름: 주소}). 모두 ctx.code_at 부터 이 모듈 몫 안에 둔다."""
    import dq4prologue
    from dq4ch2endor import BCS, BEQ, BNE, BRA, lda
    out = bytearray()
    at = {}

    def put(name, code):
        at[name] = ctx.code_at + len(out)
        out.extend(code)

    put('chest_bit', _chest_bit().bytes())
    bit = at['chest_bit'] & 0xFFFF
    for side, spec in (('right', RIGHT), ('left', LEFT)):
        put(f'at_{side}', _inside(spec['rect']))
        put(f'away_{side}', _inside(spec['rect'], away=True))
    put('away_chest', _inside(CHEST, away=True))
    # 인물 명령 05: 주인공이 연 금고 상자 칸에 서면 A = 0
    a = _asm()(0x08, 0xE2, 0x30)
    _rect_test(a, CHEST, 'far')
    a(0xC2, 0x10, 0x20, bit & 0xFF, bit >> 8).br(BCS, 'far')(0x3F, _al(CHEST_BITS)).br(BEQ, 'far').br(BRA, 'near')
    _answer(a)
    put('on_chest', a.bytes())
    # 대화 호출: 금고 상자의 열림 비트를 끈다(FC 1E:$B830 이 상자 열었음 비트를 끄는 것). 그림은 맵에 다시 들어오면 닫힘
    a = _asm()(ENTER, 0x20, bit & 0xFF, bit >> 8).br(BCS, 'end')
    a(0x49, 0xFF, 0x3F, _al(CHEST_BITS), 0x9F, _al(CHEST_BITS)).label('end')
    put('reclose', a.bytes() + LEAVE)
    # 물살: 아래로 걸어(이벤트 걸음은 벽·물을 지나감) 멈출 줄 위까지 간 뒤 순간이동. 왼쪽은 떨어지며 DRAINED 를 켠다
    for side, spec in (('right', RIGHT), ('left', LEFT)):
        steps = 2 * spec['stop'] + 1 - (spec['rect'][3])
        mp, (x, y) = spec['to']
        drain = bytes((0x10, *DRAINED)) if side == 'left' else b''
        put(f'flood_{side}', drain + bytes((DOWN, steps, 0x90, GROUP, _map(mp), x, y, 0x01, 0x80, 0xFF)))
        put(f'push_{side}', dq4prologue._event_start(at[f'flood_{side}']))
    # 출구 훅(2A:F7AB 에서 JSL, M8·X8, DB 2A): $BD 를 쓰고 도착 출구 번호를 A 로. 물이 빠졌으면 3E/04 대신 3E/05 이고,
    # FC 처럼 출구 번호 1 이상은 하나 뒤(3E/05 에는 (09,09) 계단이 하나 더 있음)
    a = _asm()(0xA5, 0x01, 0x85, 0xBD, 0xA0, 0x01, lda(EXIT_READ), 0xC9, 0xB7).br(BEQ, 'long')
    a(0xB1, 0x84).br(BRA, 'got').label('long')(0xB7, 0x84).label('got')(0x48)
    a(0xA5, 0xBC, 0xC9, GROUP).br(BNE, 'out')(0xA5, 0xBD, 0xC9, _map(GATES)).br(BNE, 'out')
    a(lda(FLAG_AT + DRAINED[0]), 0x29, DRAINED[1]).br(BEQ, 'out')
    a(0xA9, _map(DRY), 0x85, 0xBD, 0x68).br(BEQ, 'zero')(0x1A).label('zero')(0x6B)
    a.label('out')(0x68, 0x6B)
    put('exit', a.bytes())
    # 전멸 훅(20:8162 에서 JSL): 3장에서 일행 기록 0~3 의 소지품에 철 금고가 있으면 잃는 금화 $43~$45 를 0 으로,
    # 아니면 원래대로 금화($46~$48)의 반을. 일행 수(7E:201D)보다 뒤 기록은 보지 않는다
    a = _asm()(0x08, 0xC2, 0x30, 0xDA, 0x5A, 0xE2, 0x30, lda(CHAPTER3_AT), 0x29, 0x08).br(BEQ, 'half')
    for r in range(4):
        items = ch2.PARTY_AT + 0x16 + 42 * r
        a(lda(PARTY_COUNT), 0xC9, r + 1).br(0x90, 'half')(0xA2, 0x00)
        a.label(f'slot{r}')(0xBF, _al(items), 0xC9, IRON_SAFE).br(BEQ, 'keep')(0xE8, 0xE0, 12).br(0x90, f'slot{r}')
    a.br(BRA, 'half')
    # X·Y 는 원래 코드처럼 그대로 둔다. 금고가 있으면 잃는 금화 $43~$45 를 0 으로
    restore = (0xC2, 0x30, 0x7A, 0xFA, 0xE2, 0x20)
    a.label('keep')(*restore, 0xA9, 0x00, 0x85, 0x45, 0x85, 0x44, 0x85, 0x43, 0x28, 0x6B)
    a.label('half')(*restore, WIPE_ORIG, 0x28, 0x6B)
    put('wipe', a.bytes())
    return bytes(out), at


def hooks(ctx):
    at = ctx.at
    exit_new = bytes((0x22, *_al(at['exit']), 0x80, EXIT_DONE - (EXIT_SITE + 6), 0xEA))
    skip = len(WIPE_ORIG) - 6
    wipe_new = bytes((0x22, *_al(at['wipe']), 0x80, skip)) + bytes((0xEA,)) * skip
    return [(EXIT_SITE, EXIT_ORIG, exit_new), (WIPE_SITE, WIPE_ORIG, wipe_new)]


# FC 03B3·0296·037B 를 옮겼다. 바닥 글은 FC 처럼 인용, 앞뒤는 서술
MESSAGES = {
    'button': ch1.narrate('단추가 있다./눌러 보겠습니까?'),
    'floor': (ch1.narrate('바닥에 무언가/글자가 새겨져 있다.')[:-1] + [ch1.PAGE] +
              ch1.say('보물을 찾아/여행하는 자여./네가 훔친 보물을/이 자리에 되돌려 놓아라.',
                      '그리하면 네가/돌아갈 길이/열리리라……')[:-1] + [ch1.PAGE] +
              ch1.narrate('철 금고를/원래대로/되돌리겠습니까?')),
    'returned': ch1.narrate('톨네코는 보물을/원래대로 되돌려/놓았다!'),
}
TALKS = ('button', 'floor')
CALLS = {'take_safe': ('take', IRON_SAFE), 'reclose': ('reclose', 0)}

YES_COND = {"code": "05"}


def talk_scripts(ctx):
    asked = ctx.flag_on(ANSWERED)
    return [
        [ctx.say('button'), ctx.when(YES_COND, [ctx.flag_on(YES), asked], [asked])],
        [ctx.say('floor'), ctx.when(YES_COND, [ctx.call('take_safe'), ctx.call('reclose'), ctx.say('returned'), asked],
                                    [asked])],
    ]


def _cmd(op, *args, **kw):
    return {"op": op, "args": list(args), **kw}


def _off(flag):
    return _cmd('11', flag[0], ~flag[1] & 0xFF)


def scripts(ctx):
    at = ctx.at
    call = lambda a: _cmd('37', *_al(a))  # noqa: E731
    talk_here = ch2.native()[1]['talk_here']
    wait_answer = [_cmd('37', *_al(talk_here)), _cmd('09', 0x80 | ANSWERED[0], ANSWERED[1]), _off(ANSWERED)]
    out = {}
    # 단추: 칸에 서면 묻고, 「예」 면 물살, 「아니요」 면 칸을 떠났다가 다시 서야 또 묻는다
    for side in ('right', 'left'):
        out[side] = [_cmd('28'), _cmd('52'), _cmd('05', *_al(at[f'at_{side}']), label='wait'), *wait_answer,
                     _cmd('06', *YES, target='push'), _cmd('05', *_al(at[f'away_{side}'])), _cmd('03', target='wait'),
                     {**_off(YES), "label": 'push'}, _cmd('3F'), call(at[f'push_{side}']), _cmd('16')]
    # 금고: 상자를 연 뒤 그 칸을 떠났다가 다시 밟으면 바닥 글. 상자를 여는 동안(그 칸에 선 채)에는 묻지 않는다
    out['chest'] = [_cmd('28'), _cmd('52'), _cmd('05', *_al(at['away_chest']), label='wait'),
                    _cmd('05', *_al(at['on_chest'])), *wait_answer, _cmd('03', target='wait')]
    return [{"address": SCRIPTS[k][0], "commands": v} for k, v in out.items()]


def _src(name):
    return {"list": SCRIPT_LIST, "index": SCRIPTS[name][1]}


def npc_lists(lists, ctx):
    """3E/04 에 단추 둘, 3E/09 에 금고를 묻는 보이지 않는 인물을 더한다(낮·밤)."""
    if GATES not in lists:
        return [], []           # 인물 없이 옮긴 목록(dq4npcport.port 의 with_people=False)
    t = ctx.talk
    for side in ('right', 'left'):
        lists[GATES]["entries"] += ch2._invisible(_src(side), t['button'])
    lists[VAULT]["entries"] += ch2._invisible(_src('chest'), t['floor'])
    return [], []
