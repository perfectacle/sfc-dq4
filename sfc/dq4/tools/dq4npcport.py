"""FC DQ4 town people of the new DQ5 groups (dq4environmentrom.GROUPS) as dq5npcrelocate/1 lists and
their Japanese FC text as dq5text/1 messages appended after DQ5's 3,200 walking messages.

Each FC person record of the day and the night list becomes one DQ5 entry of that time. It copies a DQ5
template entry: a standing one, or one that wanders (script 19 03 03) with the FC step interval. The
picture is a placeholder DQ5 townsperson of the same role (PICTURES) until DQ4 sprites exist. The talk is
the FC talk of chapter 1 at the start (dq4talk.predict with chapter 0, no flags, no party): the messages it
shows are joined into one new DQ5 message (FIRST_MESSAGE-, gap-free), shown by an appended talk script (talk_doc).
People who open a shop, an inn, a church or the deposit in FC take the DQ5 talk number of the same service
instead (dq4shopport).

  python sfc/dq4/tools/dq4npcport.py --out work/dq4-npcs
"""

import argparse
import json
import sys
import unicodedata
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
DQ5_TOOLS = TOOLS.parents[1] / "dq5" / "tools"
FC_TOOLS = TOOLS.parents[2] / "fc" / "dq4" / "tools"
for path in (TOOLS, DQ5_TOOLS, FC_TOOLS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import dq4talk  # noqa: E402
import dq4text  # noqa: E402
import dq5text  # noqa: E402
from dq5hangul import MESSAGES  # noqa: E402
from dq4environmentrom import GROUPS  # noqa: E402
from dq4environmentmap import edit_cells, sheet_art  # noqa: E402
import dq4block  # noqa: E402
from dq4groupbuild import cell, chapter, fc_map, has_people  # noqa: E402
import dq4shopport  # noqa: E402
import dq4prologue  # noqa: E402
from dq4shopport import merchants  # noqa: E402
from kr_patch.fc import ines  # noqa: E402

# Template entries (dq5npcrelocate `from`): one-time entries with no extra byte. STAND has no script and
# interval 0; WALK has the most common wander script 19 03 03 (walk within 3x3 of the start).
# 기타 bit4-5 가 00 이라 말을 걸면 주인공 쪽으로 돈다(05:86C5 1번은 30 이라 정면만 봄)
STAND = {"list": "05:870A", "index": 2}
WALK = {"list": "05:8857", "index": 6}
# 같은 FC 그림이라도 NDS 가 다른 시트로 그리는 인물: (맵, 처음 보이는 FC 대사) -> DQ5 그림(dq4people 의 시트).
# NDS 맵 스크립트에서 같은 대사를 하는 오브젝트의 모습 번호로 골랐다(nds/dq4/tools/ndsscript.py dump)
NDS_LOOKS = {
    # 바트랜드 성 앞의 장로(NDS ham2f1 長老 h039, 대사 287·320). 9C 는 서장 장로 시트를 싣는 빌린 그림
    ("36/00", 1932): 0x9C, ("36/00", 1312): 0x9C,
    # 사막 바자의 아저씨(NDS mem1f1·mey1f1 砂漠のおじさん h058). 그 시트가 없어 おじさん h002 로 둔다
    ("45/05", 1583): 0x38, ("45/05", 1362): 0x38,
    # 사란의 역사 학자(FC 그림 29, NDS mbw1f1 学者 h033, 대사 95566)
    ("45/04", 1807): 0x1F,
}
# A person FC puts on a bed lies in it: a one-time entry with 기타 bit7 (lying, drawn rotated 8 px lower) and bit4
# (does not turn when spoken to, which would swap the head to the foot of the bed), no script.
LIE = {"list": "10:A4E9", "index": 14}
LIE_GROUPS = range(0x36, 0x3D)    # 서장·1장 그룹. 2장 이후는 그 장을 옮길 때 화면으로 보고 넓힌다
# FC picture (dq4talk.sprite without the 80 bit) -> DQ5 picture of a townsperson of the same role, chosen by
# eye from the two sprite sheets (dq4fcsprite.py field, dq5sprite.py).
PICTURES = {
    0x0F: 0x14,  # king
    0x10: 0x01,  # minister
    0x11: 0x06,  # soldier
    0x12: 0x04,  # lady
    0x13: 0x17,  # woman with long hair (Flare, the mothers of Imuru)
    0x14: 0x29,  # man
    0x15: 0x0B,  # child
    0x16: 0x09,  # bald old man (NDS draws them 老人 h005, see NDS_LOOKS)
    0x17: 0x40,  # man in a green cap (shopkeepers; NDS 商人 h009)
    0x18: 0x03,  # man
    0x19: 0x07,  # man
    0x1B: 0x15,  # priest
    0x25: 0x24,  # cat (unused DQ5 picture carrying NDS ネコ h047, dq4people)
    0x28: 0x19,  # woman
    0x36: 0x05,  # nun
    0x27: 0x4E,  # fire (48 is on the list of pictures nobody talks to, 05:862F)
    0x40: 0x42,  # horned monster with a staff (NDS h171, dq4people)
    0x41: 0x9B,  # purple monster
    0x45: 0x1F,  # wizard
    0x3D: 0x5B,  # heal slime
    0x1A: 0x0E,  # princess
    0x1C: 0x51,  # skeleton
    0x1D: 0x28,  # dancer
    0x1E: 0x1A,  # man in a green cap
    0x1F: 0x45,  # hobbit
    0x20: 0x3D,  # man in stripes
    0x21: 0x40,  # bearded merchant
    0x22: 0x0D,  # woman soldier
    0x23: 0x23,  # fox
    0x24: 0x20,  # dog
    0x26: 0x26,  # horse
    0x29: 0x09,  # bald old man
    0x2A: 0x50,  # slime
    0x2B: 0xA1,  # boat
    0x2C: 0x52,  # cloud
    0x2D: 0x0F,  # purple-haired man
    0x2E: 0x0D,  # sky castle man
    0x2F: 0x8F,  # sky castle woman
    0x30: 0x5C,  # waterfall
    0x31: 0xA1,  # river boat
    0x32: 0xA0,  # wagon
    0x33: 0x87,  # round rock
    0x35: 0x75,  # machine
    0x37: 0x3A,  # miner
    0x38: 0x29,  # farmer
    0x39: 0x67,  # armoured guard
    0x3A: 0x0A,  # bunny girl
    0x3B: 0x21,  # young man
    0x3C: 0x9D,  # dragon
    0x3E: 0x5E,  # baby dragon
    0x3F: 0x88,  # purple monster
    0x42: 0x52,  # ghost
    0x43: 0x74,  # brown beast
    0x44: 0x60,  # imp with a fork
    0x46: 0x6E,  # brown beast
    0x47: 0x8A,  # winged demon
    0x49: 0x15,  # priest
    0x4A: 0x1C,  # fortune teller
    0x4B: 0x28,  # dancer
    0x4C: 0x1F,  # wizard
    0x4D: 0x36,  # merchant
    0x4E: 0x08,  # soldier
    0x4F: 0x2F,  # princess
    0x53: 0x9D,  # big monster, quarter
    0x54: 0x9D,  # big monster, quarter
    0x55: 0x9D,  # big monster, quarter
    0x56: 0x9D,  # big monster, quarter
    0x57: 0x43,  # workman
    0x58: 0x8E,  # sky castle soldier
    0x59: 0x9B,  # purple demon
    0x5E: 0x29,  # man (drawn invisible in FC)
    0x5F: 0xA0,  # wagon
    0x60: 0x52,  # balloon, left edge
    0x61: 0x52,  # balloon
    0x62: 0x52,  # balloon, right edge
    0x66: 0x70,  # statue
    0x67: 0x70,  # statue
    0x68: 0x33,  # green-haired boy
    0x69: 0x0F,  # purple-haired man
    0x6A: 0x4E,  # fire
    0x6C: 0x4E,  # fire
    0x76: 0x9B,  # purple demon
}
FACING = ("up", "right", "down", "left")
# Placeholder line for a person whose FC talk shows nothing at the start of chapter 1.
NOTHING = "＜なにもない＞"
# Ported lines are new messages after DQ5's own, right after chapter 1's and the prologue's Korean messages
# (dq4chapter1.TALK_BASE), gap-free.
FIRST_MESSAGE = dq4prologue.TALK_END + 0x3C6
assert FIRST_MESSAGE > MESSAGES
# Talk numbers 900- run talk scripts appended by dq5talkwrite --extra-at, gap-free from 900: the prologue's
# first (dq4prologue.talk_doc), then chapter 1's event talks (dq4ch1event), then one `msg` script per ported
# message. A talk number T >= 26D shows message
# T + 3C6 directly, but the talk numbers below 900 reach only a few of the new messages.
SCRIPT_TALK = 0x900
LINE, PAGE, END = 0x1000, 0x1002, 0x1001
# FC F4 는 30프레임 쉼(16:$80E9), DQ5 100D 는 31프레임 멈춤(24:84E9).
PAUSE = 0x100D
# FC 이름 0(勇者)은 새 게임에서 지은 이름이고, DQ5 는 그 이름을 7E:2001 에 두고 1012 로 찍는다.
HERO = 0x1012
NIGHT = 0x78
MAX_CELL = 0x7F


def fc_state(night, flags=None, chapter_number=1):
    """A chapter at its start: $615A = chapter - 1, no flags or party, $62ED day or night. flags {address: value}
    sets event flags for a later state."""
    ram = bytearray(0x8000)
    ram[0x615A] = chapter_number - 1
    ram[0x62ED] = NIGHT if night else 0
    for a, v in (flags or {}).items():
        ram[a] = v
    return dq4talk.State(ram)


def bed_cells(prg, fc_group, number):
    """FC cells of a bed's foot (bed_left with bed_right on its right): a person FC puts there sleeps."""
    source = dq4block.Map(prg, fc_group, number)
    edit_cells(source, fc_group, number)
    art = sheet_art(prg, source.t)
    name = lambda x, y: art.get(source.cell(x, y) & 31, ("",))[0]  # noqa: E731
    return {(x, y) for y in range(source.h) for x in range(source.w - 1)
            if name(x, y) == "bed_left" and name(x + 1, y) == "bed_right"}


def fc_people(prg, fc_group, number, night, flags=None):
    """FC person records of a map at that time: FC cell, facing, step interval, picture, messages. With flags
    the list is the one FC picks for those event flags (dq4map.place_records)."""
    state = fc_state(night, flags, chapter(fc_group))
    out = []
    for rec in dq4talk.npc_list(prg, fc_group, number, night, ram=state.ram if flags else None):
        x, y = dq4talk.pos(rec, night)
        step = rec[2] & 0x0F if night else rec[2] >> 4
        # Facing comes from the picture's byte: byte 3, or byte 7 at night when F bit0 is off (1C:$99B3).
        facing = rec[7] if night and not rec[0] & 1 else rec[3]
        out.append({"x": x, "y": y, "facing": FACING[facing & 3], "interval": step,
                    "picture": dq4talk.sprite(rec, night) & 0x7F, "talk": dq4talk.talk_id(rec, night),
                    "shows": dq4talk.predict(prg, dq4talk.talk_id(rec, night), state)})
    return out


def _codes_of_char():
    table = {}
    for code, char in enumerate("".join(dq5text.CHARS)):
        table.setdefault(char, code)
    return table


CODE_OF = _codes_of_char()
FULLWIDTH_DIGITS = {ord(c): ord(c) + 0xFEE0 for c in "0123456789"}
REVERSE = {code: char for char, code in CODE_OF.items()}


def _pieces(text):
    """dq4text symbols as a list: control names as str, characters as ("char", c)."""
    pieces, i = [], 0
    while i < len(text):
        if text[i] == "{":
            j = text.index("}", i)
            pieces.append(text[i + 1:j])
            i = j + 1
        else:
            pieces.append(("char", text[i]))
            i += 1
    return pieces


def _skip_speaker(pieces, k):
    """Index after a speaker mark 「＊「」 (and a line break after it) at k, or k. DQ5 puts the mark on a
    message and a page itself (24:8AF9), so a written one would show twice."""
    if pieces[k:k + 2] == [("char", "＊"), ("char", "「")]:
        k += 2
        if pieces[k:k + 1] == ["LINE"]:
            k += 1
    return k


def _code(m, char):
    if char not in CODE_OF:
        char = unicodedata.normalize("NFKC", char).translate(FULLWIDTH_DIGITS)
    if char not in CODE_OF:
        raise ValueError(f"FC message {m:04X}: no DQ5 character for {char!r}")
    return CODE_OF[char]


def dq5_codes(rom, messages):
    """FC messages (dq4text symbols) as one DQ5 message: {LINE} -> line break, {WAIT} -> page, a dakuten
    mark {3D} joins the next kana, messages are joined by pages. Speaker marks at the start of a message or
    a page are dropped, and a page is never doubled or left empty at the end."""
    codes = []

    def page():
        if codes and codes[-1] != PAGE:
            codes.append(PAGE)
    for m in messages:
        pieces = _pieces(dq4text.symbolize(dq4text.message_bytes(rom, m)))
        page()
        k = 0
        while k < len(pieces) and pieces[k] == "NOINDENT":
            k += 1
        k = _skip_speaker(pieces, k)
        while k < len(pieces):
            p = pieces[k]
            k += 1
            if isinstance(p, tuple):
                codes.append(_code(m, p[1]))
            elif p == "LINE":
                codes.append(LINE)
            elif p == "PAUSE":
                codes.append(PAUSE)
            elif p == "NAME:0":
                codes.append(HERO)
            elif p == "WAIT":
                page()
                k = _skip_speaker(pieces, k)
            elif p == "3D":
                if k >= len(pieces) or not isinstance(pieces[k], tuple):
                    raise ValueError(f"FC message {m:04X}: dakuten mark without a character")
                codes.append(_code(m, unicodedata.normalize("NFC", pieces[k][1] + "\u3099")))
                k += 1
            elif p in ("NOINDENT", "STOP") or p.startswith("SOUND:"):
                # No sound control in DQ5 walking text: the placeholder text goes without them. A STOP before
                # more text would need a DQ5 wait, which these messages do not have.
                if p == "STOP" and k < len(pieces) and pieces[k] != "END":
                    raise ValueError(f"FC message {m:04X}: {{STOP}} before more text")
            elif p == "END":
                break
            else:
                raise ValueError(f"FC message {m:04X}: no DQ5 code for {{{p}}}")
    while codes and codes[-1] == PAGE:
        codes.pop()
    return codes + [END]


def nothing_codes():
    return [CODE_OF[c] for c in NOTHING] + [END]


def first_talk():
    """Talk number of the first ported message's script: the prologue's, chapter 1's and chapter 2's event scripts
    come first."""
    import dq4ch1event
    import dq4ch2event
    import dq4prologue
    return SCRIPT_TALK + len(dq4prologue.talk_doc()["scripts"]) + len(dq4ch1event.TALKS) + len(dq4ch2event.TALKS)


def allocate(texts, key, codes):
    """Message number of a line (key = the FC messages it shows), a new one in order of first use."""
    if key not in texts:
        texts[key] = (FIRST_MESSAGE + len(texts), codes())
    return texts[key][0]


def talk_doc(messages):
    """dq5talk/1: the prologue's appended scripts, chapter 1's event scripts, and then one script per ported
    message in id order, so message FIRST_MESSAGE + k has talk number first_talk() + k. The event scripts show
    messages right after the ported ones (dq4ch1event.MESSAGES)."""
    import dq4ch1event
    import dq4prologue
    doc = dq4prologue.talk_doc()
    first = first_talk()
    ids = [m["id"] for m in messages]
    if ids != list(range(FIRST_MESSAGE, FIRST_MESSAGE + len(ids))):
        raise ValueError(f"ported messages must run gap-free from {FIRST_MESSAGE:X}")
    events = dq4ch1event.talk_numbers(SCRIPT_TALK + len(doc["scripts"]))
    doc["scripts"] += [{"talk": f"{events[name]:03X}", "body": body}
                       for name, body in zip(dq4ch1event.TALKS, dq4ch1event.talk_scripts(FIRST_MESSAGE + len(ids)))]
    import dq4ch2event
    ch2 = dq4ch2event.talk_numbers(SCRIPT_TALK + len(doc["scripts"]))
    ch2_first = FIRST_MESSAGE + len(ids) + len(dq4ch1event.MESSAGES)
    doc["scripts"] += [{"talk": f"{ch2[name]:03X}", "body": body}
                       for name, body in zip(dq4ch2event.TALKS, dq4ch2event.talk_scripts(ch2_first))]
    doc["scripts"] += [{"talk": f"{first + k:03X}", "body": [{"op": "msg", "id": f"{m:03X}"}]}
                       for k, m in enumerate(ids)]
    return doc


def port(dq5_path, dq4_path, with_people=True):
    """(dq5npcrelocate lists, dq5text messages, report); `with_people` False ports no FC people. After the maps'
    own lists come the lists of later states (dq4ch1event.ALT_STATES) as {"name": dq4ch1event.alt_name(state, map),
    "entries": …}, reported under the same name; their new lines get message numbers after the start state's."""
    import dq4ch1event
    data = Path(dq4_path).read_bytes()
    items = dq4shopport.dq5_items(dq4shopport.dq5item.Rom(Path(dq5_path).read_bytes()))
    prg, rom = ines.prg(data), dq4text.Rom(data)
    first = first_talk()
    texts = {}
    lists, report = [], {}

    def people_of(name, fc_group, fc_number, flags=None):
        entries, people = [], []
        shops = merchants(prg, fc_group, fc_number, items)
        group = int(name[:2], 16) if "/" in name else GROUPS[name][0]
        dq5_map = name if "/" in name else "%02X/%02X" % GROUPS[name]
        beds = bed_cells(prg, fc_group, fc_number) if group in LIE_GROUPS else set()
        for night in (False, True) if has_people(fc_group, with_people) else ():
            for p in fc_people(prg, fc_group, fc_number, night, flags):
                if max(cell(p["x"], p["y"])) > MAX_CELL:
                    # Parked far off the map until an event brings them (エンドール 04/02 night, (1A,7F)·(1B,7F)):
                    # the DQ5 person record holds 7-bit cells.
                    continue
                shows = [m for m in p["shows"] if m is not None]
                predicted = [m - dq4talk.SERVICE for m in shows if m >= dq4talk.SERVICE]
                service = shops.get((p["x"], p["y"], night))
                if service is None and predicted and dq4shopport.has_goods(prg, predicted[0], fc_group, fc_number, items):
                    service = dq4shopport.SERVICE[predicted[0]]
                message = None
                if service is not None:
                    # A seller stays behind the counter: the DQ5 wander script would walk off it.
                    talk = service
                    p = {**p, "interval": 0}
                else:
                    # A seller with nothing DQ5 has (has_goods) keeps the lines before its service.
                    shows = [m for m in shows if m < dq4talk.SERVICE]
                    message = allocate(texts, tuple(shows),
                                       lambda: dq5_codes(rom, shows) if shows else nothing_codes())
                    talk = first + message - FIRST_MESSAGE
                if p["picture"] not in PICTURES:
                    raise ValueError(f"{name}: FC picture {p['picture']:02X} has no DQ5 picture")
                gfx = NDS_LOOKS.get((dq5_map, p["shows"][0] if p["shows"] else None), PICTURES[p["picture"]])
                x, y = cell(p["x"], p["y"])
                fields = {"x": x, "y": y, "facing": p["facing"], "talk": talk,
                          "gfx": gfx, "layer": 0, "interval": p["interval"]}
                template = WALK if p["interval"] else STAND
                if (p["x"], p["y"]) in beds and service is None:
                    # Lying on the bed's row, half a block right so the head rests on the pillow and the foot of
                    # the bed shows. The lying picture is the standing one turned clockwise: facing down turns the
                    # front view so the eyes stand one above the other and the face reads as turned to the wall;
                    # facing right (as most DQ5 sleepers) turns the side view to a face up from the pillow.
                    fields.update(x=x + 1, y=y - 1, facing="right", interval=0)
                    template = LIE
                entries.append({"from": template, "time": "night" if night else "day", "fields": fields})
                people.append({**p, "night": night, "service": service,
                               "message": None if message is None else f"{message:03X}", "dq5": fields})
        return entries, people

    for name, (group, number) in sorted(GROUPS.items(), key=lambda kv: kv[1]):
        fc_group, fc_number = fc_map(prg, group, number)
        m = f"{group:02X}/{number:02X}"
        entries, people = people_of(name, fc_group, fc_number)
        lists.append({"map": m, "entries": entries})
        report[m] = people
    for state, flags, maps in dq4ch1event.ALT_STATES:
        for m in maps:
            group, number = (int(v, 16) for v in m.split("/"))
            entries, people = people_of(m, *fc_map(prg, group, number), flags)
            lists.append({"name": dq4ch1event.alt_name(state, m), "entries": entries})
            report[dq4ch1event.alt_name(state, m)] = people
    messages = [{"id": m, "codes": codes} for m, codes in sorted(texts.values())]
    return lists, messages, report


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dq5", default="rom/dq5.sfc")
    ap.add_argument("--dq4", default="rom/dq4.nes")
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    lists, messages, report = port(args.dq5, args.dq4)
    (args.out / "npc-lists.json").write_text(json.dumps(lists, ensure_ascii=False, indent=1) + "\n")
    (args.out / "messages.json").write_text(json.dumps({"format": "dq5text/1", "messages": messages}) + "\n")
    (args.out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n")
    print(json.dumps({m: len(v) for m, v in report.items()} | {"messages": len(messages)}))


if __name__ == "__main__":
    main()
