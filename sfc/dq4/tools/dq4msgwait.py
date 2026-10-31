"""메시지 끝 코드를 그 메시지가 쓰이는 자리로 정한다(dq4chapter1.messages 가 부름).

끝 코드 1001 은 버튼을 기다리지 않아, 스크립트나 대화가 곧바로 다음 메시지를 띄우거나 연출을 이어 가면 마지막 쪽이
A 를 누르기 전에 밀려 올라간다. ▼ 대기 끝 1010 은 그 자리에서 멈추지만, 메시지를 띄운 쪽이 창을 닫으며 A 를 따로 받으면
(대기 루틴 00:982B) 마지막 쪽에서 A 를 두 번 눌러야 한다(실측: 모샤스 서술 한 쪽에 ▼ 대기와 닫기 대기가 하나씩).
그래서 끝 코드는 메시지를 띄운 명령과 그다음을 보고 정한다.

  대화(dq5talk/1 본문): 메시지는 창을 닫지 않고 다음으로 간다. 다음에 올 수 있는 것을 거꾸로 따라가, 다음에 메시지가
                        오면 1010, 대화 끝·예·아니요 창이 먼저 오면 1001(대화가 끝날 때 닫기 대기가 있다). 갈래(if) 중
                        하나라도 메시지로 시작하면 메시지가 온다. 조건 05 의 갈래는 예·아니요 창이라 그 앞 물음은 1001.
                        알 수 없는 명령(전투 call 등)은 1001 쪽
  인물 스크립트: 명령 21·32 는 띄운 뒤 닫기 대기를 하므로 늘 1001. 명령 30 은 창을 남기고 바로 다음으로 가므로, 다음
                 메시지(21·30·32)가 조작 풀기(40)보다 먼저 오면 1010. 갈래·점프는 보지 않고 차례대로 본다
  이벤트 스크립트(토큰 목록): 명령 60 도 닫기 대기를 하므로 늘 1001
"""
LINE_END, WAIT_END = 0x1001, 0x1010
SCRIPT_MESSAGES = {'21', '30', '32'}
OPEN_MESSAGE = '30'
UNLOCK = '40'
YES_NO = '05'


def _ops(x):
    if x is None:
        return []
    return x if isinstance(x, list) else [x]


def _talk(ops, after, wait, keep):
    """ops 를 거꾸로 따라가며 각 메시지 다음에 오는 것을 정한다. after/돌려주는 값: 'msg'·'end'·'ask'."""
    for op in reversed(_ops(ops)):
        kind = op.get('op')
        if kind == 'msg':
            (wait if after == 'msg' else keep).add(int(op['id'], 16))
            after = 'msg'
        elif kind == 'if':
            heads = [_talk(op.get(k), after, wait, keep) for k in ('then', 'else')]
            if op['cond'].get('code') == YES_NO:
                after = 'ask'
            elif 'msg' in heads:
                after = 'msg'
            else:
                after = heads[0] if heads[0] == heads[1] else 'end'
        elif kind != 'flag-on':
            after = 'end'
    return after


def _script(commands, wait, keep):
    for i, c in enumerate(commands):
        if c['op'] not in SCRIPT_MESSAGES:
            continue
        m = c['args'][0] | c['args'][1] << 8
        if c['op'] != OPEN_MESSAGE:
            keep.add(m)
            continue
        later = next((d['op'] for d in commands[i + 1:] if d['op'] in SCRIPT_MESSAGES | {UNLOCK}), None)
        (wait if later in SCRIPT_MESSAGES else keep).add(m)


def _event(tokens, wait, keep):
    for t in tokens:
        if isinstance(t, tuple) and t[0] == 'msg':
            keep.add(t[1])


def plan(talks=(), scripts=(), events=()):
    """(1010 으로 끝낼 메시지, 1001 로 둘 메시지). 한 메시지가 두 쪽에 다 쓰이면 어느 끝 코드든 한 자리가 틀리므로 멈춘다."""
    wait, keep = set(), set()
    for body in talks:
        _talk(body, 'end', wait, keep)
    for commands in scripts:
        _script(commands, wait, keep)
    for tokens in events:
        _event(tokens, wait, keep)
    both = wait & keep
    if both:
        raise ValueError(f'끝 코드를 하나로 정할 수 없는 메시지: {sorted(f"{m:03X}" for m in both)}')
    return wait, keep


def apply(texts, wait):
    """texts {번호: 부분 목록} 중 wait 의 메시지 끝을 1010 으로. 이미 다른 끝 코드면 그대로 둔다."""
    for m in wait:
        parts = texts.get(m)
        if parts and parts[-1] == LINE_END:
            texts[m] = parts[:-1] + [WAIT_END]
    return texts
