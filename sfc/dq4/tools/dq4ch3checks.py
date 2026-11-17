"""3장 사건 모듈의 검사 표를 모은다(틀과 _checks 파일이 내놓는 것은 dq4eventchecks 머리말). 형식 문서
sfc/dq4/docs/dq4-chapter3-format.md 「검사」.

등록 차례는 dq4ch3slots.SLOTS 이고 키는 SLOTS 의 키(L·S·B·E·T·W)다. 차례를 고정하는 곳은 dq4ch3walkcheck 의
SEGMENT_ORDER·FLAG_ORDER.
"""
import dq4ch3slots
import dq4eventchecks as ev


def pairs():
    return [(key, slot.module) for key, slot in dq4ch3slots.SLOTS.items()]


def tables():
    return ev.tables(pairs())


def blocks(single, many):
    return ev.blocks(pairs(), single, many)


ordered = ev.ordered


def merged(name):
    return ev.merged(pairs(), name)


def effects(data):
    return ev.effects(pairs(), data)
