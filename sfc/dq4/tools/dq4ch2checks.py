"""2장 사건 모듈의 검사 표를 모은다(틀과 _checks 파일이 내놓는 것은 dq4eventchecks 머리말). 형식 문서
sfc/dq4/docs/dq4-chapter2-format.md 「검사에 구간 붙이기」.

등록 차례는 dq4ch2event.EVENTS 이고 키는 dq4ch2slots.SLOTS 의 키(E1~E5·P)다. 차례를 고정하는 곳은 dq4ch2walkcheck 의
FLAG_ORDER.
"""
import dq4ch2event
import dq4ch2slots
import dq4eventchecks as ev


def pairs():
    keys = {slot.module: key for key, slot in dq4ch2slots.SLOTS.items()}
    return [(keys[name], name) for name in dq4ch2event.EVENTS]


def tables():
    return ev.tables(pairs())


def blocks(single, many):
    return ev.blocks(pairs(), single, many)


ordered = ev.ordered


def merged(name):
    return ev.merged(pairs(), name)


def effects(data):
    return ev.effects(pairs(), data)
