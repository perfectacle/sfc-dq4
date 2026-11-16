"""DQ4 3장 레이크나바 사건(dq4ch3slots 'L'): 지금은 네네가 주는 도시락만.

FC 16/01 의 낮 네네(대화 057, 15:$9DED)는 일행에게 おべんとう 가 없으면 「はい これ おべんとう」(080E) 와 함께 도시락을
주고 $6285 bit1 을 켠다. 있으면 「なにか わすれもの？」(0810) 와 「わたしたちも いずれは」(080F). FC 는 오늘 일했을 때도
(그날 일삯을 받은 뒤) 재우고 새 도시락을 주는데, 무기점 일이 아직 없어 이 갈래는 「도시락이 없을 때」 만 본다.
형식은 sfc/dq4/docs/dq4-chapter3-format.md 「레이크나바」.
"""
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[1] / 'dq5' / 'tools')]

import dq4ch2event as ch2  # noqa: E402
import dq4ch3event as ch3  # noqa: E402
from dq4itemport import BENTO  # noqa: E402

BENTO_TODAY = (0x70, 0x01)     # 7E:2200 bit0  오늘 네네에게 도시락을 받음(FC $6285&02)
FLAGS = (BENTO_TODAY,)

MESSAGES = {
    # FC 080E
    'bento': ch2._speaker_pages('네네', '자, 여기 도시락./오늘도 힘내고 와요.'),
    # FC 0810·080F
    'forgot': ch2._speaker_pages('네네', '어머 여보./뭐 두고 간 거라도/있어요?', '일 힘내고 와요./쪽.',
                                 '있잖아요……/우리도 언젠가는/우리 가게를/갖고 싶네요.',
                                 '당신은 언제까지나/남 밑에서 일할/사람이 아니에요.',
                                 '그렇게 생각해서/나는 당신과/결혼한 거예요.', '물론 그것만은/아니지만요. 우후.'),
}
TALKS = ('nene',)
CALLS = {'give_bento': ('give', BENTO)}


def talk_scripts(ctx):
    give = [ctx.say('bento'), ctx.call('give_bento'), ctx.flag_on(BENTO_TODAY)]
    return [[ctx.when(ctx.has(BENTO), [ctx.say('forgot')], give)]]


def npc_lists(lists, ctx):
    """3E/01 의 낮 네네(첫머리를 맡은 자리)가 이 대화를 쓴다. 첫머리 대기 목록은 dq4ch3event 가 따로 만들어 그대로다."""
    if ch3.HOUSE in lists:
        ctx.retalk(lists, ch3.HOUSE, ch3.NENE_CELL, ctx.talk['nene'], time='day')
    return [], []


def start_messages(ctx):
    """3장 처음 상태(도시락을 가짐)에서 낮 네네의 첫 메시지."""
    return {(ch3.HOUSE, FC_NENE, False): ctx.msg['forgot']}


FC_NENE = 0x057
