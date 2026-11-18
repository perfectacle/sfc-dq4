"""2장 걷기·주인공 막기 표(dq4ch2*_checks.py)가 함께 쓰는 입력 조각."""
import dq4ch1walkcheck as wc

talk, taps, talk_yes = wc.talk, wc.taps, wc.talk_yes
CLOSE = wc.pc.CLOSE


def flag(pair):
    return wc.flag(pair)


def set_flags(*pairs):
    """(7E:2190 + i, 마스크) flag 들을 켜는 SET 조각."""
    return ';'.join(f'{(0x2190 + i) & 0xFFFF:04X}|{m:02X}' for i, m in pairs)
