"""DQ4 2장 텐페 제물 사건 뒤 절반: 제단 앞의 보스 전투, 아침, 괴물이 사라진 뒤의 마을(FC 1C 이벤트 02, 0E/00 목록 플래그 04&80).

앞 절반(dq4ch2event 의 TEMPE_*)의 바구니 이벤트는 밤의 텐페 제단 앞으로 옮기는 `90` 에서 끝난다. 그 `90` 을 이 모듈의
이벤트로 뛰게 덮어(hooks), 같은 자리로 옮긴 뒤 잠시 쉬고 전투 무리 GROUP(카멜레온 맨과 날뛰는 석상 둘)을 건다. FC 처럼
전투 앞에서 앞 절반의 flag 셋을 끄고, 이기면 WON 을 켜고 서술(FC 034D) 뒤 아침으로 같은 자리를 다시 불러온다. 지면
dq4ch2battle 의 공용 루틴이 보통 전멸 처리(기록한 교회)를 하고, 이벤트는 거기서 끝난다.

WON 이 켜진 텐페는 FC 가 그 flag 로 고르는 목록(AFTER)을 옮긴 대체 목록이다. 형식은 sfc/dq4/docs/dq4-chapter2-format.md
「텐페 뒤 절반」.
"""
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[1] / 'dq5' / 'tools')]

import dq4chapter1 as ch1  # noqa: E402
from dq4chapterbox import ENTER, LEAVE  # noqa: E402
import dq4ch2battle  # noqa: E402
import dq4ch2event as ch2  # noqa: E402

say, narrate = ch1.say, ch1.narrate

WON = (0x60, 0x01)             # 7E:21F0 bit0  제단의 괴물을 이김(FC $627F&80)
FLAGS = (WON,)
GROUP = 0x31
# 덮어쓸 DQ5 몬스터 자리. 그림은 DQ5 것(대역): E1 은 보랏빛 옷의 사람 꼴, E0 은 돌 석상 꼴이라 그렇게 짝지었다
CHAMELEON, STATUE = 0xE1, 0xE0
FC_CHAMELEON, FC_STATUE = 0x12, 0x18           # FC カメレオンマン·あばれこまいぬ(FC 전투 02 = 석상·카멜레온 맨·석상)
BATTLES = ({"group": GROUP, "members": ((CHAMELEON, 1), (STATUE, 2)), "flags": dq4ch2battle.MIDBOSS_FLAGS},)
MONSTERS = {CHAMELEON: FC_CHAMELEON, STATUE: FC_STATUE}
MONSTER_NAMES = {CHAMELEON: '카멜레온 맨', STATUE: '날뛰는 석상'}
# 1장 보스의 표(dq4ch1event.FC_ACTIONS)에 없는 FC 행동 번호: 22 는 ホイミ(FC 주문 29), 35 는 공격의 하나(FC 46).
# 몬스터 행동의 ホイミ 는 5B(DQ5 ホイミスライム 의 행동). 27 은 일행 주문 번호라 몬스터가 쓰면 회복 메시지 뒤 멈췄다
FC_ACTIONS = {0x22: '5B', 0x35: '73'}

# 앞 절반이 바구니 이벤트 끝에 두는 옮기기(ch2.ALTAR_CELL). 그 자리를 이 모듈의 이벤트로 뛰는 C3 으로 덮는다
_TG, _TN = (int(v, 16) for v in ch2.TEMPE.split('/'))
BASKET_WARP = bytes((0x90, _TG, _TN, *ch2.ALTAR_CELL, 0x01, 0x80))
# 제단 위 FC (0C,03). FC 는 바구니 인물(슬롯 08)이 그 칸까지 메고 올라가고, 1C 이벤트 02 가 괴물을 일행 양옆에 세운다.
# 앞 절반이 고른 ch2.ALTAR_CELL(FC (16,0F))은 제단 오른쪽 숲 속이라 사방이 나무로 막혀 있었다(실측)
ALTAR_CELL = (0x0C * 2, 0x03 * 2 + 1)
ALTAR_WARP = bytes((0x90, _TG, _TN, *ALTAR_CELL, 0x01, 0x80))
# 이긴 뒤 아침으로 다시 불러오는 자리: 같은 제단 위
MORNING_CELL = ALTAR_CELL
MORNING_WARP = ALTAR_WARP
# 이긴 뒤의 촌장(FC (0C,22)) 위 칸. 제단에서 곧장 내려오는 길(교회를 지남)의 끝이고, 아래를 보고 말을 건다
CHIEF_TALK_CELL = (0x0C * 2, 0x21 * 2 + 1)
# 전투 앞 쉼(C2 하나가 8프레임). FC 는 이 동안 괴물이 일행 양옆으로 걸어 들어온다
PAUSE_STEPS = 8
# 앞 절반의 flag. FC 1C 이벤트 02 는 전투 앞에서 $6280 bit6·$6281 bit3 을 끈다: 지면 촌장에게 다시 들어야 한다
TEMPE_FLAGS = (ch2.TEMPE_HEARD, ch2.TEMPE_GONE, ch2.TEMPE_ALTAR)
EVENT_ACTIVE = 0x19AE          # bit7: 이벤트 스크립트가 도는 중(00:BED8 의 FF 가 끔)

WON_LIST = 'ch2_tempe2_won'


def _al(a):
    return bytes((a & 0xFF, a >> 8 & 0xFF, a >> 16))


def altar_warp_at():
    """앞 절반 바구니 이벤트 안의 옮기기 자리(메시지 명령 60 lo hi 뒤). 주소는 메시지 번호와 상관없다."""
    return ch2.tail_native(0)[1]['altar_event'] + 3


def _fight():
    """앞 절반 flag 를 끄고 전투. 이기면 WON 을 켜고 이벤트를 잇는다.

    지면 01:868B 의 전멸 처리가 교회로 옮기며 이 루틴으로 돌아오지 않는다(A0 명령이 스크립트 자리를 넘기기 전이라,
    이벤트가 켜진 채면 교회에서 같은 A0 을 다시 읽어 전투가 또 걸렸다. 실측). 그래서 전투 앞에 이벤트를 끄고(00:BED8 의
    FF 와 같음) 이겼을 때만 다시 켠다."""
    tempe = 0x7E2190 + ch2.TEMPE_HEARD[0]
    clear = sum(f[1] for f in TEMPE_FLAGS)
    assert all(f[0] == ch2.TEMPE_HEARD[0] for f in TEMPE_FLAGS)
    won_at = 0x7E2190 + WON[0]
    lo, hi = EVENT_ACTIVE & 0xFF, EVENT_ACTIVE >> 8
    win = (bytes((0xAF,)) + _al(won_at) + bytes((0x09, WON[1], 0x8F)) + _al(won_at) +
           bytes((0xAD, lo, hi, 0x09, 0x80, 0x8D, lo, hi)))
    body = (bytes((0xAF,)) + _al(tempe) + bytes((0x29, ~clear & 0xFF, 0x8F)) + _al(tempe) +
            bytes((0xAD, lo, hi, 0x29, 0x7F, 0x8D, lo, hi)) +
            dq4ch2battle.far(GROUP) +
            bytes((0xAF,)) + _al(dq4ch2battle.WON_AT) + bytes((0x29, dq4ch2battle.BATTLE_WON[1], 0xF0, len(win))) +
            win)
    return ENTER + body + LEAVE


def _morning():
    """필드 시간을 아침으로(M 8). 맵을 다시 불러올 때 낮 목록·낮 색·낮 곡이 된다."""
    t = ch2.TIME_AT
    return (ENTER + bytes((0xA9, ch2.MORNING & 0xFF, 0x8F)) + _al(t) +
            bytes((0xA9, ch2.MORNING >> 8, 0x8F)) + _al(t + 1) + LEAVE)


def _tokens(ctx, at):
    """이벤트 토큰: 제단 앞으로 → 쉼 → 전투 → 서술 → 아침 → 같은 자리 다시 불러오기."""
    won = ctx.msg['won'] if ctx.msg else 0
    return [ALTAR_WARP + bytes((0xC2,)) * PAUSE_STEPS + bytes((0xA0, *_al(at['fight']))),
            ('msg', won), bytes((0xA0, *_al(at['morning']))) + MORNING_WARP + b'\xff']


def _event_bytes(tokens):
    return b''.join(bytes((0x60, t[1] & 0xFF, t[1] >> 8)) if isinstance(t, tuple) else t for t in tokens)


def native(ctx):
    out = bytearray()
    at = {}

    def put(name, b):
        at[name] = ctx.code_at + len(out)
        out.extend(b)
    put('fight', _fight())
    put('morning', _morning())
    put('event', _event_bytes(_tokens(ctx, at)))
    return bytes(out), at


def hooks(ctx):
    return [(altar_warp_at(), BASKET_WARP, bytes((0xC3, *_al(ctx.at['event']))))]


def events(ctx):
    return [_tokens(ctx, ctx.at)]


def monster_doc(prg):
    """dq5tables/1 몬스터 칸: FC 능력치(dq4ch1event.fc_monster 와 같은 꼴)에 이 모듈의 행동 번호를 더한다."""
    import dq4ch1event
    import dq4data
    actions = {**dq4ch1event.FC_ACTIONS, **FC_ACTIONS}
    out = []
    for dq5, fc in MONSTERS.items():
        r = next(rec for i, _, _, _, rec in dq4data.monsters(prg) if i == fc)
        ten = lambda lo, hi: r[lo] | (r[hi] & 3) << 8  # noqa: E731
        out.append({"id": f"{dq5:02X}", "HP": ten(4, 15), "MP": r[3], "민첩": r[2], "공격": ten(5, 16),
                    "수비": ten(6, 17), "경험치": r[0] | r[1] << 8, "금화": ten(7, 18), "행동수": 0, "재생": 0,
                    "동료확률": 0, "드롭": "FF", **{f"행동{k + 1}": actions[r[9 + k] & 0x7F] for k in range(6)}})
    return out


# 서술과 마을 사람의 말. FC 메시지 번호(NDS 대사가 있으면 그 번호)
MESSAGES = {
    # FC 034D(NDS 4030·4031)
    'won': narrate('괴물을 물리쳤다는/소식은 순식간에/온 마을로 퍼졌다.', '그리고 날이 밝았다……'),
    # FC 07C9 뒤 교회
    'priest': say('그대의 활약,/분명 신께서도/보고 계셨을 것이오.', '그건 그렇고……'),
    'thanks': say('이 은혜는 평생/잊지 않겠습니다!'),                                    # 061A
    'elder': say('허허, 대단한/분이로구먼!/뭐라, 힘을 시험하는/여행을?',                    # 061B
                 '그렇다면 동쪽 나라/엔돌에서 열린다는/무술 대회에/나가 보시게.',
                 '엔돌에는 이 나라/남동쪽 사당에서/갈 수 있을 걸세.'),
    'kid': say('이제 괴물은/없어진 거지?/야호, 야호.'),                                   # 061C
    'bride': say('저희 결혼해요!'),                                                        # 061D
    'mother': say('이미 포기하고/있었는데……/고맙습니다.'),                                # 061E
    'chief': say('도구점 주인도/예전처럼 장사를/시작했으니 이 텐페/마을도 되살아날 겁니다.',  # 061F
                 '정말로/고맙습니다.'),
    'east': say('이 숲을 빠져나가/동쪽으로 가면/프레놀입니다.'),                          # 0620
    'seller_night': say('이제야 장사에/힘이 나는군요./고맙습니다.'),                       # 0535
    'thanks_night': say('그때는 정말/신세를 졌습니다.'),                                   # 0536
    'bride_night': say('고맙습니다./부디 몸조심하시고/여행을 계속하세요.'),               # 0537
    'chief_night': say('그러고 보니 전에도/당신을 어디선가/뵌 것 같은데……',              # 0538
                       '성에 갔을 때/였던가./생각이 안 나는구먼.'),
    'noble_ask': say('제게는 여러분이/보통 사람으로는/보이지 않습니다.',                  # 0539
                     '혹시 신분이 높은/분이 아니신지?'),
    'noble_yes': say('역시! 공주님/일행이셨군요!'),                                        # 053A
    'noble_no': say('그럼 그런 걸로/해 두지요.'),                                          # 053B
    'sleep': say('새근새근……'),                                                            # 05CA
}
TALKS = ('priest', 'thanks', 'elder', 'kid', 'bride', 'mother', 'chief', 'east', 'seller_night', 'thanks_night',
         'bride_night', 'chief_night', 'noble', 'sleep')
# 말만 하는 대화(이름 = 메시지 이름)
_PLAIN = set(TALKS) - {'priest', 'noble'}


def talk_scripts(ctx):
    msg = lambda k: {"op": "msg", "id": f"{ctx.msg[k]:03X}"}  # noqa: E731
    bodies = {'priest': [msg('priest'), ch2.CHURCH],
              'noble': [msg('noble_ask'), {"op": "if", "cond": {"code": "05"}, "then": msg('noble_yes'),
                                           "else": msg('noble_no')}]}
    return [bodies[name] if name not in _PLAIN else [msg(name)] for name in TALKS]


# FC 0E/00 의 목록 플래그 04&80($627F bit7) 목록: (낮/밤, FC 칸, 방향, 걸음 간격, FC 그림, 대화). 대화가 정수면 가게
# 대화 번호(006 여관, 002 도구점: dq4shopport 의 사건 판매자). test_dq4ch2tempe 가 FC 롬의 목록과 견준다
AFTER = (
    ('day', (0x0B, 0x18), 'down', 0, 0x1B, 'priest'),
    ('day', (0x08, 0x28), 'down', 0, 0x17, 0x06),
    ('day', (0x13, 0x25), 'right', 0, 0x13, 'bride'),
    ('day', (0x14, 0x1F), 'left', 0, 0x16, 'elder'),
    ('day', (0x15, 0x25), 'left', 0, 0x28, 'mother'),
    ('day', (0x0B, 0x04), 'down', 6, 0x12, 'east'),
    ('day', (0x14, 0x24), 'down', 0, 0x14, 'thanks'),
    ('day', (0x04, 0x1A), 'down', 0, 0x17, 0x02),
    ('day', (0x0C, 0x22), 'left', 0, 0x10, 'chief'),
    ('day', (0x0E, 0x28), 'down', 0, 0x15, 'kid'),
    ('night', (0x0B, 0x18), 'down', 0, 0x1B, 'priest'),
    ('night', (0x08, 0x28), 'down', 0, 0x17, 0x06),
    ('night', (0x13, 0x25), 'right', 0, 0x13, 'bride_night'),
    ('night', (0x14, 0x1F), 'left', 0, 0x16, 'elder'),
    ('night', (0x15, 0x25), 'left', 0, 0x10, 'chief_night'),
    ('night', (0x17, 0x19), 'down', 0, 0x12, 'noble'),
    ('night', (0x03, 0x21), 'left', 0, 0x14, 'thanks_night'),
    ('night', (0x02, 0x21), 'right', 0, 0x17, 'seller_night'),
    ('night', (0x17, 0x29), 'right', 0, 0x28, 'sleep'),
    ('night', (0x14, 0x1D), 'right', 0, 0x15, 'sleep'),
)
# 대화마다 FC 가 띄우는 첫 메시지(NDS 그림 표 dq4npcport.NDS_LOOKS 의 열쇠). 가게는 None
FC_FIRST = {'priest': 0x7C9, 'thanks': 0x61A, 'elder': 0x61B, 'kid': 0x61C, 'bride': 0x61D, 'mother': 0x61E,
            'chief': 0x61F, 'east': 0x620, 'seller_night': 0x535, 'thanks_night': 0x536, 'bride_night': 0x537,
            'chief_night': 0x538, 'noble': 0x539, 'sleep': 0x5CA}


def after_entries(talk):
    """AFTER 를 dq5npcrelocate 목록 항목으로(dq4npcport.port 가 FC 사람을 옮기는 것과 같은 꼴). talk: {이름: 대화 번호}."""
    import dq4npcport as port
    out = []
    for time, (x, y), facing, interval, picture, who in AFTER:
        shop = isinstance(who, int)
        gfx = port.PICTURES[picture] if shop else port.NDS_LOOKS.get((ch2.TEMPE, FC_FIRST[who]), port.PICTURES[picture])
        cx, cy = port.cell(x, y)
        out.append({"from": port.WALK if interval else port.STAND, "time": time,
                    "fields": {"x": cx, "y": cy, "facing": facing, "talk": who if shop else talk[who], "gfx": gfx,
                               "layer": 0, "interval": 0 if shop else interval}})
    return out


def npc_lists(lists, ctx):
    new = [{"name": WON_LIST, "entries": after_entries(ctx.talk)}]
    over = [{"map": ch2.TEMPE, "flag": WON[0], "when": "on", "mask": WON[1], "list": f"new:{WON_LIST}"}]
    return new, over
