"""장마다 사건 모듈 옆 <모듈>_checks.py 의 검사 표를 모으는 틀(3장 dq4ch3checks, 2장 dq4ch2checks).

사건 모듈 dq4chN<이름>.py 옆의 dq4chN<이름>_checks.py 가 그 사건의 검사 표를 갖는다. 파일이 있으면 등록 장치 차례로
들어오므로, 사건을 더하거나 고치는 PR 은 자기 _checks 파일만 고친다. _checks 파일이 내놓는 것(모두 골라 씀):

  FLAGS          걷기 검사 flag 표 {이름: (WRAM 주소, 마스크)}. 여러 묶음이면 FLAG_BLOCKS = {묶음: {…}}
  SEGMENTS       걷기 구간 표(꼴은 dq4chapterwalk 머리말). 여러 묶음이면 SEGMENT_BLOCKS = {묶음: […]}
  effects(data)  구간이 flag 말고 기록에 남기는 것 {구간 이름: {'set': …, 'party': …}}(dq4chapterwalk.setup)
  hero_cases()   주인공 막기 사례 {이름: 사례}(dq4heroblockcheck)
  PASS_NO_DEVICE 겹침 피하기 장치 없이 1C 로 걷는 인물 스크립트의 까닭 {스크립트 주소: 까닭}(test_dq4heroblock)
  WALK_EXEMPT    조작을 막지 않고 걷는 인물 스크립트의 까닭 {스크립트 주소: 까닭}(test_dq4heroblock)

걷기 표는 묶음마다 앞 구간의 want·off 를 누적해 시작하고 flag 표 차례가 기록 차례이므로, 표를 잇는 차례가 결과에 닿는다.
잇는 곳(장 걷기 검사)이 차례를 고정할 이름을 주고, 거기 없는 모듈·묶음은 등록 차례(한 모듈 안에서는 적은 차례)로 뒤에 붙는다.
"""
import importlib
import importlib.util


def tables(pairs):
    """[(키, _checks 모듈)] pairs([(키, 사건 모듈 이름)]) 차례. _checks 파일이 있는 모듈만."""
    out = []
    for key, module in pairs:
        name = f'{module}_checks'
        if importlib.util.find_spec(name) is not None:
            out.append((key, importlib.import_module(name)))
    return out


def blocks(pairs, single, many):
    """[(묶음 이름, 값)] 등록 차례. 모듈이 single 을 내놓으면 이름은 키, many 를 내놓으면 「키.묶음」."""
    out = []
    for key, mod in tables(pairs):
        if hasattr(mod, single):
            out.append((key, getattr(mod, single)))
        for block, value in getattr(mod, many, {}).items():
            out.append((f'{key}.{block}', value))
    return out


def ordered(pieces, order):
    """[(이름, 값)] 을 order 의 이름 차례로, order 에 없는 것은 원래 차례로 뒤에. order 에 있는데 없는 이름은 건너뛴다."""
    by = dict(pieces)
    return [(n, by[n]) for n in order if n in by] + [(n, v) for n, v in pieces if n not in order]


def merged(pairs, name):
    """모든 _checks 모듈의 dict 하나(hero_cases·PASS_NO_DEVICE 꼴). 이름이 겹치면 ValueError."""
    out = {}
    for key, mod in tables(pairs):
        value = getattr(mod, name, None)
        if value is None:
            continue
        got = value() if callable(value) else value
        dup = set(out) & set(got)
        if dup:
            raise ValueError(f'{key}: {name} 이름이 다른 모듈과 겹침 {sorted(dup)}')
        out.update(got)
    return out


def effects(pairs, data):
    """모든 _checks 모듈의 effects(data) 를 합친 것."""
    out = {}
    for _, mod in tables(pairs):
        if hasattr(mod, 'effects'):
            out.update(mod.effects(data))
    return out
