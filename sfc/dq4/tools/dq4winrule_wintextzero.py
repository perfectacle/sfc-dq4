"""화면 글자 읽기가 통째로 안 돎: 실제 롬인데 글꼴(DQ4_GALMURI)을 싣지 못했거나, 창 안에 잉크 줄이 있는데 글자를 하나도
알아보지 못했다(모두 ⍰). 창이 비어 잉크 줄이 없는 모습은 걸지 않고 상태 규칙이 따로 센다: 메시지 창을 연 순간(글자를 찍기 전)이 그렇고,
캔버스(096~17F)에 글자만 찍히는 것은 새 모습이 아니라 그 뒤에 아무것도 안 바뀌면 빈 모습만 남는다. 글자 규칙이 모두
「안 봐서 통과」 하는 것을 막는 실패다. 가짜 롬(단위 시험)이면 보지 않는다. CI 가드 조각은 해시가 맞는 Galmuri 를 늘
받으므로(tools/ci_gate_setup.sh) 글꼴을 못 싣는 것은 설정이 깨진 것이다.
"""
import dq4winrule_wintextstatus as status

NAME = '글자 못 읽음'
MODE = 'fail'
ALLOW = ()


def check_run(run):
    got = status.read_lines(run)
    if got == status.NO_FONT:
        return [(0, 'DQ4_GALMURI 의 Galmuri 를 싣지 못해 글자를 하나도 읽지 않음')]
    if not isinstance(got, tuple) or got[1] == 0 or got[2] > 0:
        return []
    return [(0, f'창이 뜬 모습 {got[0]}개의 잉크 줄 {got[1]}개에서 글자를 하나도 알아보지 못함')]
