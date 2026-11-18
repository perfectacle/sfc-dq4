"""UI 깨짐 규칙 U2f 이름과 일행: 상태 창·「누구」 창에 찍힌 일행 이름의 차례가 그 모습 때 일행 기록(WRAM)의 차례와 다르다
(장비 「누구」 창을 열면 뒤 상태 창 이름이 「호이민 크리프트」 로 뒤바뀌어 HP 열과 엇갈린 꼴). dq4winwatch 의 규칙 파일.

일행 수 7E:201D, 일행 기록 7E:2040 + 42 × k 의 +0(사람 번호, 80 이상이면 동료 몬스터 종류)으로 이름을 정한다:
사람 번호 - 3 은 dq4groupbuild.PERSON_NAMES, 동료 몬스터는 종류 × 4 + 이름 번호의 COMPANION_NAMES 가운데 그 종류의 하나뿐인
이름. 주인공(사람 0)과 이름을 정하지 못한 칸은 비교에서 뺀다. 한 줄(상태 창 이름 줄)이나 한 창의 줄들(「누구」 창)에
찍힌 일행 이름을 x·y 차례로 늘어놓고, 그 가운데 정한 이름끼리의 차례가 기록 차례와 다르면 건다.
"""
import dq4wintext as wt

NAME = '이름과 일행'
MODE = 'report'
ALLOW = ()
COUNT, RECORDS, RECORD = 0x201D, 0x2040, 42
WRAM = [(COUNT, 1)] + [(RECORDS + RECORD * k, 1) for k in range(8)]


def expected(screen):
    import dq4groupbuild as GB
    n = screen.wram(COUNT)[0]
    if n is None:
        return None
    out = []
    for k in range(min(n, 8)):
        v = screen.wram(RECORDS + RECORD * k)[0]
        name = None
        if v is not None and v < 0x80:
            name = GB.PERSON_NAMES.get(v - 3)
        elif v is not None:
            names = {nm for key, nm in GB.COMPANION_NAMES.items() if key // 4 == v & 0x3F}
            name = names.pop() if len(names) == 1 else None
        out.append(name)
    return out


def check(screen):
    got = wt.lines(screen)
    if not got:
        return []
    want = expected(screen)
    if not want:
        return []
    known = [n for n in want if n]
    names = wt.party_names()
    out = []
    for w, lines in got.items():
        groups = [[(line, t) for t in line.text.split() if t in names] for line in lines]
        column = [g[0] for g in groups if len(g) == 1]
        for shown in [g for g in groups if len(g) > 1] + ([column] if len(column) > 1 else []):
            seq = [t for _, t in shown if t in known]
            ref = [n for n in known if n in seq]
            if len(seq) > 1 and seq != ref:
                line = shown[0][0]
                r, c = wt.cell_of(w, line.x, line.y)
                out.append((r, c, f'창 {w} 이름 차례 {seq}, 일행 기록 차례 {ref}'))
    return out
