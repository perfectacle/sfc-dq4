"""메시지 끝 코드를 그 메시지가 쓰이는 자리로 정한다(dq4chapter1.messages 가 부름).

끝 코드 1001 은 버튼을 기다리지 않아, 스크립트나 대화가 곧바로 다음 메시지를 띄우거나 연출을 이어 가면 마지막 쪽이
A 를 누르기 전에 밀려 올라간다. ▼ 대기 끝 1010 은 그 자리에서 멈추지만, 그 뒤 대화가 끝나거나 조작을 풀면(인물
명령 40) 창을 닫는 A 를 한 번 더 받아야 한다(실측: 목소리 메시지에 1010 을 주자 움직이기까지 A 가 2번 → 3번).
그래서 메시지 다음에 다른 메시지나 연출이 먼저 오면 1010, 대화 끝·조작 풀기·예·아니요 창이 먼저 오면 1001 로 둔다.

  대화(dq5talk/1 본문): 다음에 올 수 있는 것을 거꾸로 따라간다. 갈래(if) 중 하나라도 메시지로 시작하면 메시지가 온다.
                        조건 05 의 갈래는 예·아니요 창이라 그 앞 물음은 1001. 알 수 없는 명령(전투 call 등)은 1001 쪽
  인물 스크립트: 메시지(21·30) 뒤로 다음 메시지가 40 보다 먼저 오면 1010, 아니면 1001. 메시지 없이 연출만 이어지다
                 끝나도(16) 1001: 명령 21 이 창을 닫는 A 를 따로 받아, 1010 이면 ▼ 를 넘긴 뒤 같은 쪽에서 A 를 한 번
                 더 받는다(실측: 신시아 사과 뒤 모샤스 돌기). 갈래·점프는 보지 않고 차례대로 본다
  이벤트 스크립트(토큰 목록): 메시지가 마지막 토큰이면 1001, 뒤에 무엇이든 있으면 1010
"""
LINE_END, WAIT_END = 0x1001, 0x1010
SCRIPT_MESSAGES = {'21', '30'}
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
        later = next((d['op'] for d in commands[i + 1:] if d['op'] in SCRIPT_MESSAGES | {UNLOCK}), None)
        (wait if later in SCRIPT_MESSAGES else keep).add(m)


def _event(tokens, wait, keep):
    for i, t in enumerate(tokens):
        if isinstance(t, tuple) and t[0] == 'msg':
            (wait if i + 1 < len(tokens) else keep).add(t[1])


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
