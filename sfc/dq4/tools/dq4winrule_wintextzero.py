"""화면 글자 읽기가 통째로 안 돎: 글꼴과 실제 롬이 있는데 창이 뜬 장면에서 글자를 한 줄도 읽지 못했다. 글자 규칙이 모두
「안 봐서 통과」 하는 것을 막는 실패다. 글꼴이 없거나 가짜 롬(단위 시험)이면 보지 않는다(상태 규칙이 따로 남김).
"""
import dq4winrule_wintextstatus as status

NAME = '글자 못 읽음'
MODE = 'fail'
ALLOW = ()


def check_run(run):
    got = status.read_lines(run)
    if not isinstance(got, tuple) or got[0] == 0 or got[1] > 0:
        return []
    return [(0, f'창이 뜬 모습 {got[0]}개에서 글자를 한 줄도 읽지 못함')]
