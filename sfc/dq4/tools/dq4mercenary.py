"""엔돌 용병 스콧·로렌스(dq4ch3endor 가 부르는 부분): 고용·동행·전투 행동·날수·5일 뒤 떠남.

FC(fc/dq4/docs/dq4-chapter3-format.md 「용병」):
  스콧   04/00 낮 (05,13) 대화 071: 0853(5일 400G) → 「예」 면 개가 따라오면 0854, 금화가 모자라면 0855, 아니면 0856·고용
         ($628C = 0, $628E|=80). 「아니요」 0857. 전투는 공격만(AI 레코드 C8).
  로렌스 04/0B (07,08) 대화 051: 085C(5일 600G) → 0855 대신 085D, 고용 085E, 「아니요」 085F. 전투는 ホイミ·ホイミ·ギラ·
         ラリホー·공격·ホイミ(AI 레코드 C7, 앞 칸이 많이 뽑힘).
  날수   필드 걸음 시계가 하루를 돌 때와 잘 때 + 1. 3장 필드 걸음마다 날수 ≥ 5 면 0378·0379 뒤 일행에서 빠진다(1E:$9485).

DQ5 의 몬스터 손님(일행 기록 +0 = C0 | 종류, 명령 창이 뜨지 않음. 1장 손님 호이민과 같은 장치)으로 넣는다. 사람 손님(+0 bit6
만)은 DQ5 가 몬스터 행동표 AI(21:AC88)로 고르고 かしこさ 갈래(21:AED8)를 지나지 않아, 1장 손님 AI 훅(21:AF1B)이 닿는 몬스터
손님으로 했다. 이 해킹이 쓰지 않는 동료 종류 28·29 의 이름(dq4groupbuild.COMPANION_NAMES)과 걷는 그림(05:D9E1)을 바꾼다.
"""
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[1] / 'dq5' / 'tools')]

import dq4chapter1 as ch1  # noqa: E402
import dq4ch1event as ch1e  # noqa: E402
import dq4ch2event as ch2  # noqa: E402
import dq4ch3event as ch3  # noqa: E402
from dq4chapterbox import ENTER, LEAVE  # noqa: E402

say, narrate = ch1.say, ch1.narrate
GUEST = 0xC0                   # 일행 기록 +0: bit7 몬스터 동료, bit6 손님(명령 창 없이 스스로 싸움)
SCOTT_KIND, LAWRENCE_KIND = 0x28, 0x29          # 이 해킹에서 동료가 되지 않는 DQ5 동료 종류(00~29 의 끝 둘)
# 걷는 그림(05:D9E1 + 종류)의 칸을 dq4people 이 NDS 병사·시인을 싣는 그림으로(엔돌 3장 목록의 서 있는 용병도 같은 그림)
PICTURE_TABLE = 0x05D9E1
PICTURES = {'scott': ch3.SCOTT_PICTURE, 'lawrence': ch3.LAWRENCE_PICTURE}
DAYS = 5
PRICES = {'scott': 400, 'lawrence': 600}
# FC 손님 레코드(15:$9FF8·$A002): 스콧 HP 82, 로렌스 HP 58·MP 68. 공격·수비·민첩은 AI 레코드 C8·C7(코드 읽기)
STATS = {'scott': {'hp': 82, 'mp': 0, 'agility': 8, 'stats': (58, 33, 5, 5)},
         'lawrence': {'hp': 58, 'mp': 68, 'agility': 18, 'stats': (28, 25, 5, 5)}}
KINDS = {'scott': SCOTT_KIND, 'lawrence': LAWRENCE_KIND}
FLAGS = {'scott': ch3.SCOTT, 'lawrence': ch3.LAWRENCE}
DAY_VARS = {'scott': ch3.SCOTT_DAYS, 'lawrence': ch3.LAWRENCE_DAYS}

ATTACK, HEAL, GIRA, RARIHO = 0x73, 0x27, 0x04, 0x17                 # DQ5 행동: たたかう·ホイミ·ギラ·ラリホー
SPELL_MP = {HEAL: 3, GIRA: 4, RARIHO: 3}
# 로렌스(FC AI 레코드 C7, 칸 ホイミ·ホイミ·ギラ·ラリホー·공격·ホイミ): 고르는 법 1 의 칸 가중치(67 57 47 37 28 19)를 칸의
# 행동으로 합친 것(FC 18:$9A72 가 같은 행동을 첫 칸에 합침). ホイミ 는 같은 편이 HP 절반 미만일 때만. FC 실측(로렌스 + 라이안,
# 슬라임 HP 고정, 씨앗 여덟): 라이안이 다쳤을 때 ホイミ 251·ギラ 80·ラリホー 43·공격 58(432번, 식으로 56·18·15·11%)
HEAL_WEIGHT = 67 + 57 + 19
OTHER_WEIGHTS = ((GIRA, 47), (RARIHO, 37), (ATTACK, 28))

STEP_HOOK_AT = ch2.STEP_HOOK_AT            # 00:82CB(2장 걸음 훅이 JSL 로 바꿔 둔 자리)
TIME_AT = ch2.TIME_AT                      # 필드 시간 7E:075E(걸음마다 + 1, 01FF 다음 0)
HOURS = 0x01FF
AI_AT, AI_DONE = ch1e.GUEST_AI_AT, ch1e.GUEST_AI_DONE
TARGET = ch1e.SCRATCH + 0x0C               # 1장 손님 ホイミ 대상(차례 + 1). 1장 대상 훅이 읽고 지움
RANDOM = ch1e.RANDOM
PARTY_AT = ch2.PARTY_AT
COUNT, WALKERS, COUNT_COPY = 0x7E201D, 0x7E201E, 0x7E201F
ORDERS = (0x7E2020, 0x7E2028)


def _al(a):
    return bytes((a & 0xFF, a >> 8 & 0xFF, a >> 16))


def _asm():
    from dq4ch2endor import Asm
    return Asm()


def _flag_addr(flag):
    return 0x7E2190 + flag[0]


def record(data, who):
    """일행 기록 42바이트: 1장 손님 틀(dq4ch1event.companion_record, 레벨이 오르지 않음)에 FC 값. かしこさ 는 10 미만이라야
    21:AED8 → 1장 손님 AI 훅을 지난다."""
    template = ch1e.companion_record(data, KINDS[who]) if data is not None else bytes(42)
    r = bytearray(template)
    s = STATS[who]
    r[2:4] = r[0xE:0x10] = s['hp'].to_bytes(2, 'little')
    r[4:6] = r[0x10:0x12] = s['mp'].to_bytes(2, 'little')
    r[6] = s['agility']
    r[7:0xB] = bytes(s['stats'])
    r[0] = GUEST | KINDS[who]
    return bytes(r)


MESSAGES = {
    'scott_offer': say('동굴에는 굉장한/보물이 있다지만/무시무시한 괴물도/살고 있지.',
                       '5일에 400골드로/이 몸을 경호원으로/고용하지 않겠나?'),                                  # 0853
    'scott_dog': say('하지만 나는/개가 싫다./돌려주고 오라고.'),                                                # 0854
    'scott_poor': say('하지만 돈이/모자란 모양이군./다시 오도록 해.'),                                          # 0855
    'scott_hired': say('그런가! 고용해/주겠다는 건가./자, 어디든지/따라가 주지!')[:-1] + [ch1.PAGE] +
    narrate('스콧이 동료로/들어왔다!'),                                                                        # 0856
    'scott_no': say('그런가, 아쉽군./마음이 바뀌면/또 오도록 해.'),                                             # 0857
    'lawrence_offer': say('저는 수행을 쌓아/마법도 쓸 수 있게/되었습니다.',
                          '5일에 600골드로/저를 고용해/보시지 않겠습니까?'),                                  # 085C
    'lawrence_poor': say('하지만 돈이/모자란 것 같군요./돈을 모아서/와 주세요.'),                               # 085D
    'lawrence_hired': say('오오! 고용해/주시는 겁니까!?/그럼 가시지요!')[:-1] + [ch1.PAGE] +
    narrate('로렌스가 동료로/들어왔다!'),                                                                      # 085E
    'lawrence_no': say('그거 아쉽군요./또 마음이 바뀌면/와 주세요.'),                                           # 085F
    'scott_bye': ch2._speaker_pages('스콧', '오오! 아무래도/약속한 5일이/지난 모양이군.',
                                    '미안하지만/여기서 작별이다.', '그럼 조심하라고./잘 있어라!'),             # 0378
    'lawrence_bye': ch2._speaker_pages('로렌스', '아쉽지만 약속한/5일이 지났습니다.',
                                       '그럼 저는 이만./안녕히…….'),                                         # 0379
}
TALKS = ('scott', 'lawrence')
CALLS = {'pay_scott': ('pay', PRICES['scott']), 'pay_lawrence': ('pay', PRICES['lawrence']),
         'hire_scott': ('hire', 0), 'hire_lawrence': ('hire', 1)}
WHO = ('scott', 'lawrence')                 # hire·dismiss 의 인자 차례


def talk_scripts(ctx):
    say_, call, flag, when = ctx.say, ctx.call, ctx.flag, ctx.when
    yes = {"code": "05"}
    hire_scott = [call('pay_scott'), when(ctx.paid(), [say_('scott_hired'), call('hire_scott')], [say_('scott_poor')])]
    # 고용한 뒤 맵을 다시 불러오기 전까지 서 있는 용병에게는 아무 말도 없다(FC 는 고용하면 숨김)
    hired = lambda f: {**flag(f), "not": True}  # noqa: E731
    scott = [when(hired(ch3.SCOTT), [say_('scott_offer'), when(yes, [
        when(flag(ch3.DOG), [say_('scott_dog')], hire_scott)], [say_('scott_no')])])]
    hire_law = [call('pay_lawrence'), when(ctx.paid(), [say_('lawrence_hired'), call('hire_lawrence')],
                                           [say_('lawrence_poor')])]
    lawrence = [when(hired(ch3.LAWRENCE), [say_('lawrence_offer'), when(yes, hire_law, [say_('lawrence_no')])])]
    return [scott, lawrence]


# ---- 네이티브 ----

def _offset(a):
    """M8·X16 에서 A = 기록 번호 → X = 42 × 번호(M8 로 끝남)."""
    a(0xC2, 0x20, 0x29, 0x07, 0x00, 0x0A, 0x48, 0x0A, 0x0A, 0x48, 0x0A, 0x0A, 0x18, 0x63, 0x01, 0x63, 0x03, 0xAA,
      0x68, 0x68, 0xE2, 0x20)              # 32n + 8n + 2n


def _hire(ctx, records_at):
    """대화 호출(인자 0 스콧·1 로렌스): 일행 끝에 그 기록을 넣고 수·순서·걷는 수를 고치고 걷는 그림을 다시 세운다. 고용
    flag 와 방금 고용함(dq4ch3event.HIRED_NOW)을 켜고 날수를 0 으로."""
    from dq4ch2endor import BNE, lda, sta
    a = _asm()(ENTER, 0xC2, 0x10, lda(ch3.ARG)).br(BNE, 'law')
    for k, who in enumerate(WHO):
        if k:
            a.label('law')
        f = FLAGS[who]
        assert f[0] == ch3.HIRED_NOW[0]
        a(lda(_flag_addr(f)), 0x09, f[1] | ch3.HIRED_NOW[1], sta(_flag_addr(f)), 0xA9, 0x00, sta(DAY_VARS[who]))
        a(0xA0, *((records_at + 42 * k) & 0xFFFF).to_bytes(2, 'little'))
        if not k:
            a.br(0x80, 'copy')
    a.label('copy')(lda(COUNT))
    _offset(a)
    # Y = 원본(뱅크 5C), X = 일행 기록 끝: MVN 은 X 원본·Y 대상이라 바꾼다
    a(0xC2, 0x20, 0x8A, 0x18, 0x69, PARTY_AT & 0xFF, PARTY_AT >> 8 & 0xFF, 0x48, 0x98, 0xAA, 0x7A,
      0xA9, 41, 0x00, 0x54, 0x7E, records_at >> 16, 0xE2, 0x20)
    a(lda(COUNT), 0xAA, 0x8A, 0x9F, *_al(ORDERS[0]), 0x9F, *_al(ORDERS[1]))
    a(0x1A, sta(COUNT), sta(COUNT_COPY), 0xC9, 0x04, 0x90, 0x02, 0xA9, 0x03, sta(WALKERS))
    a(ch1e.REFRESH)
    return a.bytes() + LEAVE


def _dismiss(who):
    """이벤트 A0(5일이 지나 떠남): 그 용병 기록(+0 = C0 | 종류, 기록 1 부터)을 빼고 뒤 기록 1~7 을 당기고, 두 순서
    목록에서 그 번호를 빼고 뒤 번호를 하나씩 줄이고, 수·걷는 수를 고치고 그림을 다시 세운다. 고용 flag 를 끈다."""
    from dq4ch2endor import BCC, BCS, BEQ, BRA, lda, sta
    end = (PARTY_AT & 0xFFFF) + 42 * 7 - 1          # 기록 7 끝: 당길 바이트 수 − 1 = end − 대상 주소
    a = _asm()(ENTER, 0xC2, 0x10, 0xA0, 0x01, 0x00)
    a.label('scan')(0x98, 0xCF, *_al(COUNT)).br(BCC, 'look').brl('none').label('look')(0x98)
    _offset(a)
    a(0xBF, *_al(PARTY_AT), 0xC9, GUEST | KINDS[who]).br(BEQ, 'found')(0xC8).br(BRA, 'scan')
    a.label('found')(0x5A, 0x98)
    _offset(a)
    a(0xC2, 0x20, 0x8A, 0x18, 0x69, *(PARTY_AT & 0xFFFF).to_bytes(2, 'little'), 0xA8, 0x69, 42, 0x00, 0xAA)
    a(0x5A, 0xA9, *end.to_bytes(2, 'little'), 0x38, 0xE3, 0x01, 0x7A, 0x54, 0x7E, 0x7E, 0xE2, 0x20)
    for k, order in enumerate(ORDERS):
        a(0xA2, 0x00, 0x00, 0xA0, 0x00, 0x00)
        a.label(f'o{k}')(0xBF, *_al(order), 0xC3, 0x01).br(BEQ, f'skip{k}').br(BCC, f'keep{k}')(0x3A)
        a.label(f'keep{k}')(0xDA, 0xBB, 0x9F, *_al(order), 0xFA, 0xC8)
        a.label(f'skip{k}')(0xE8, 0xE0, 0x08, 0x00).br(BCC, f'o{k}')
    f = FLAGS[who]
    a(0x7A, lda(COUNT), 0x3A, sta(COUNT), sta(COUNT_COPY), 0xC9, 0x04, 0x90, 0x02, 0xA9, 0x03, sta(WALKERS))
    a(lda(_flag_addr(f)), 0x29, ~f[1] & 0xFF, sta(_flag_addr(f)), ch1e.REFRESH)
    a.label('none')
    return a.bytes() + LEAVE


SCRATCH_HURT, SCRATCH_MP = ch1e.SCRATCH + 0x0E, ch1e.SCRATCH + 0x0F     # 1장 손님 AI 가 쓰지 않는 바로 뒤 칸
MONSTER_SLOTS = 0x7E07C0                   # DQ5 전투 몬스터 칸 16개(16바이트씩)


def _ai(ch1_entry):
    """21:AF1B 의 JML 대상(1장 손님 AI 앞): 행동자 $7B 의 일행 기록 +0 이 몬스터 손님(C0)이고 용병 종류면 행동을 골라
    21:AF3B 로, 아니면 1장 손님 AI(그다음 원래 고르기)로. 스콧은 늘 공격. 로렌스는 같은 편이 HP 절반 미만이고 MP 가 되면
    ホイミ(그 사람에게, 1장 대상 훅이 읽음)·ギラ·ラリホー·공격 가운데 FC 처럼 쓸 수 있는 칸만 남겨(ホイミ 는 다친 사람이
    있을 때, 주문은 MP 가 될 때, ラリホー 는 깨어 있는 몬스터가 있을 때) 그 가중치 합으로 고른다."""
    from dq4ch2endor import BCC, BCS, BEQ, BNE, BRA, lda, sta
    a = _asm()(0x08, 0xE2, 0x30, 0xA5, 0x7B, 0x00, 0x8B, 0x80, 0x2A, 0xA5, 0x46, 0x29, 0xC0, 0xC9, GUEST)
    a.br(BEQ, 'guest').label('other')(0x28, 0x5C, *_al(ch1_entry))
    a.label('guest')(0xA5, 0x46, 0x29, 0x3F, 0xC9, SCOTT_KIND).br(BNE, 'law')
    a(0xA9, ATTACK, 0x28, 0x5C, *_al(AI_DONE)).label('law')
    a(0xC9, LAWRENCE_KIND).br(BNE, 'other')
    a(0xC2, 0x10, 0xA9, 0x00, sta(SCRATCH_HURT), sta(SCRATCH_MP))
    for k in range(3):
        a(lda(WALKERS), 0xC9, k + 1).br(BCC, f'skip{k}')(lda(ORDERS[0] + k))
        _offset(a)
        a(0xBF, *_al(PARTY_AT), 0xC9, GUEST | LAWRENCE_KIND).br(BNE, f'hp{k}')
        a(0xBF, *_al(PARTY_AT + 4), sta(SCRATCH_MP))
        a.label(f'hp{k}')(0xC2, 0x20, 0xBF, *_al(PARTY_AT + 2)).br(BEQ, f'skip{k}')
        a(0x0A, 0xDF, *_al(PARTY_AT + 0x0E)).br(BCS, f'skip{k}')
        a(0xE2, 0x20, lda(SCRATCH_HURT)).br(BNE, f'skip{k}')(0xA9, k + 1, sta(SCRATCH_HURT))
        a.label(f'skip{k}')(0xE2, 0x20)
    # 쓸 수 있는 칸(FC 10:$AF70 이 지우지 않는 칸)을 스택 마스크로: 1 ホイミ, 2 ギラ, 4 ラリホー. 공격은 늘 남는다
    acc = SCRATCH_MP
    a(0xA9, 0x00, 0x48, lda(SCRATCH_HURT)).br(BEQ, 'noheal')(lda(SCRATCH_MP), 0xC9, SPELL_MP[HEAL]).br(BCC, 'noheal')
    a(0xA3, 0x01, 0x09, 0x01, 0x83, 0x01).label('noheal')
    a(lda(SCRATCH_MP), 0xC9, SPELL_MP[GIRA]).br(BCC, 'nogira')(0xA3, 0x01, 0x09, 0x02, 0x83, 0x01).label('nogira')
    a(lda(SCRATCH_MP), 0xC9, SPELL_MP[RARIHO]).br(BCC, 'norari')(0xA2, 0x00, 0x00)
    # 몬스터 칸 7E:07C0 + 16 × 칸: +A bit7 있는 칸, +B bit7 잠. 깨어 있는 몬스터가 하나라도 있어야 ラリホー
    a.label('scan')(0xBF, *_al(MONSTER_SLOTS + 0x0A)).br(0x10, 'next')(0xBF, *_al(MONSTER_SLOTS + 0x0B)).br(0x10, 'awake')
    a.label('next')(0xC2, 0x20, 0x8A, 0x18, 0x69, 0x10, 0x00, 0xAA, 0xE2, 0x20, 0xE0, 0x00, 0x01).br(BCC, 'scan')
    a.br(BRA, 'norari')
    a.label('awake')(0xA3, 0x01, 0x09, 0x04, 0x83, 0x01).label('norari')
    # 남은 칸 가중치 합으로 r 을 뽑아(00:953A = (난수 × A) >> 8) 누적이 r 보다 커지는 칸(FC 10:$B12B)
    weights = dict(OTHER_WEIGHTS)
    picks = ((0x01, HEAL, HEAL_WEIGHT), (0x02, GIRA, weights[GIRA]), (0x04, RARIHO, weights[RARIHO]))
    a(0xA9, weights[ATTACK], sta(acc))
    for bit, act, w in picks:
        a(0xA3, 0x01, 0x29, bit).br(BEQ, f'sum{act:02X}')(lda(acc), 0x18, 0x69, w, sta(acc)).label(f'sum{act:02X}')
    a(lda(acc), 0x22, *_al(RANDOM), sta(acc))
    for bit, act, w in picks:
        a(0xA3, 0x01, 0x29, bit).br(BEQ, f'skip{act:02X}')(lda(acc), 0xC9, w).br(BCC, f'act{act:02X}')
        a(0xE9, w, sta(acc)).label(f'skip{act:02X}')
    a(0x68, 0xA9, ATTACK).br(BRA, 'done')
    a.label(f'act{HEAL:02X}')(0x68, lda(SCRATCH_HURT), sta(TARGET), 0xA9, HEAL).br(BRA, 'done')
    for _, act, _ in picks[1:]:
        a.label(f'act{act:02X}')(0x68, 0xA9, act).br(BRA, 'done')
    a.label('done')(0x28, 0x5C, *_al(AI_DONE))
    return a.bytes()


def _step(ch2_step, leave_starts):
    """00:82CB 의 JSL 대상(2장 걸음 훅 앞): 2장 훅(끝에 원래 LDA $7E2190)을 부른 뒤 A·P 를 지킨 채, 3장 필드 걸음이면
    시간이 01FF 에서 돌 걸음(시간 멈춤 7E:2190 bit1 꺼짐, 세계 0)에 용병 날수 둘을 + 1(FF 에서 멈춤), 고용한 용병의
    날수가 5 이상이면 떠나는 이벤트를 건다(스콧 먼저, 한 걸음에 하나)."""
    from dq4ch2endor import BCC, BEQ, BNE, lda, sta
    a = _asm()(0x22, *_al(ch2_step), ENTER)
    a(lda(_flag_addr(ch3.CHAPTER3)), 0x29, ch3.CHAPTER3[1]).br(BNE, 'ch3').brl('out').label('ch3')
    a(0xA5, 0xBE).br(0x10, 'field').brl('out').label('field')          # BPL: 필드($BE bit7 꺼짐)
    a(lda(0x7E2190), 0x29, 0x02).br(BNE, 'leave')(lda(0x7E1949)).br(BNE, 'leave')
    a(0xC2, 0x20, lda(TIME_AT), 0xC9, *HOURS.to_bytes(2, 'little'), 0xE2, 0x20).br(BNE, 'leave')
    for who in WHO:
        a(lda(DAY_VARS[who]), 0x1A).br(BEQ, f'full_{who}')(sta(DAY_VARS[who])).label(f'full_{who}')
    a.label('leave')
    for who in WHO:
        f = FLAGS[who]
        a(lda(_flag_addr(f)), 0x29, f[1]).br(BEQ, f'stay_{who}')(lda(DAY_VARS[who]), 0xC9, DAYS).br(BCC, f'stay_{who}')
        a(leave_starts[who]).brl('out').label(f'stay_{who}')
    a.label('out')
    return a.bytes() + LEAVE


def leave_tokens(ctx, who, dismiss_at):
    m = ctx.msg[f'{who}_bye'] if ctx.msg else 0
    return [('msg', m), bytes((0xA0, *_al(dismiss_at), 0xFF))]


def natives(ctx, put, at, event_bytes):
    """dq4ch3endor.native 에 이어 놓는다: 기록 둘, hire, dismiss·떠나는 이벤트, 걸음 훅, AI 훅."""
    import dq4prologue
    put('merc_records', record(ctx.original, 'scott') + record(ctx.original, 'lawrence'))
    put('hire', _hire(ctx, at['merc_records']))
    starts = {}
    for who in WHO:
        put(f'dismiss_{who}', _dismiss(who))
        put(f'leave_{who}_event', event_bytes(leave_tokens(ctx, who, at[f'dismiss_{who}'])))
        starts[who] = dq4prologue._event_start(at[f'leave_{who}_event'])[len(ENTER):-len(LEAVE)]
    put('merc_step', _step(_ch2_step(), starts))
    put('merc_ai', _ai(_ch1_ai()))


def _ch2_step():
    return ch2.tail_native(0)[1]['step']


def _ch1_ai():
    return ch1e.native()[1]['guest_ai']


def events(ctx):
    return [leave_tokens(ctx, who, ctx.at[f'dismiss_{who}']) for who in WHO]


def hooks(ctx):
    at = ctx.at
    data = ctx.original
    pictures = [(PICTURE_TABLE + KINDS[who], data[ch1.lorom(PICTURE_TABLE + KINDS[who]):][:1] if data else b'\x00',
                 bytes((PICTURES[who],))) for who in WHO]
    return pictures + [(AI_AT, bytes((0x5C, *_al(_ch1_ai()))), bytes((0x5C, *_al(at['merc_ai'])))),
            (STEP_HOOK_AT, bytes((0x22, *_al(_ch2_step()))), bytes((0x22, *_al(at['merc_step']))))]


CODE_ENTRIES = ('merc_ai', 'merc_step')
DATA_ENTRIES = ('merc_records', 'leave_scott_event', 'leave_lawrence_event')
