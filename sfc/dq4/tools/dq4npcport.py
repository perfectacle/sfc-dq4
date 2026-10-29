"""FC DQ4 town people of the new DQ5 groups (dq4environmentrom.GROUPS) as dq5npcrelocate/1 lists and
their Japanese FC text as dq5text/1 messages over DQ5 messages of later towns.

Each FC person record of the day and the night list becomes one DQ5 entry of that time. It copies a DQ5
template entry: a standing one, or one that wanders (script 19 03 03) with the FC step interval. The
picture is a placeholder DQ5 townsperson of the same role (PICTURES) until DQ4 sprites exist. The talk is
the FC talk of chapter 1 at the start (dq4talk.predict with chapter 0, no flags, no party): the messages it
shows are joined into one DQ5 message, shown by talk number m - 3C6. People who open a shop, an inn, a
church or the deposit in FC take the DQ5 talk number of the same service instead (dq4shopport).

  python sfc/dq4/tools/dq4npcport.py --out work/dq4-npcs
"""

import argparse
import collections
import json
import re
import subprocess
import sys
import tempfile
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
from dq4environmentrom import GROUPS  # noqa: E402
from dq4groupbuild import LINKS, cell  # noqa: E402
from dq4shopport import merchants  # noqa: E402
from kr_patch.fc import ines  # noqa: E402

# Template entries (dq5npcrelocate `from`): one-time entries with no extra byte. STAND has no script and
# interval 0; WALK has the most common wander script 19 03 03 (walk within 3x3 of the start).
STAND = {"list": "05:86C5", "index": 1}
WALK = {"list": "05:8857", "index": 6}
# FC picture (dq4talk.sprite without the 80 bit) -> DQ5 picture of a townsperson of the same role, chosen by
# eye from the two sprite sheets (dq4fcsprite.py field, dq5sprite.py).
PICTURES = {
    0x0F: 0x14,  # king
    0x10: 0x01,  # minister
    0x11: 0x06,  # soldier
    0x12: 0x04,  # lady
    0x13: 0x09,  # old man
    0x14: 0x29,  # man
    0x15: 0x0B,  # child
    0x16: 0x38,  # bald old man
    0x17: 0x17,  # woman
    0x18: 0x03,  # man
    0x19: 0x07,  # man
    0x1B: 0x15,  # priest
    0x25: 0x26,  # dog
    0x28: 0x19,  # woman
    0x36: 0x05,  # nun
}
FACING = ("up", "right", "down", "left")
# Placeholder line for a person whose FC talk shows nothing at the start of chapter 1.
NOTHING = "＜なにもない＞"
# DQ5 groups whose people's direct messages may be overwritten: later towns. Left out: the ship 17 and the
# early or often tested groups 00-0B, 0D-0F, 12-16, 19-1A, 21.
POOL_GROUPS = {0x0C, 0x10, 0x11, 0x18, 0x1B, 0x1C, 0x1D, 0x1E, 0x1F, 0x20, 0x22, 0x23, 0x25, 0x26, 0x27, 0x29,
               0x2B, 0x2C, 0x2D, 0x31, 0x34, 0x35}
# DQ5 talk numbers 26D- show message T + 3C6 (06:AFFB).
TALK_MESSAGE = 0x3C6
TALK_FIRST = 0x26D
LINE, PAGE, END = 0x1000, 0x1002, 0x1001
NIGHT = 0x78


def fc_state(night):
    """Chapter 1 at the start: $615A = 0, no flags or party, $62ED day or night."""
    ram = bytearray(0x8000)
    ram[0x62ED] = NIGHT if night else 0
    return dq4talk.State(ram)


def fc_people(prg, fc_group, number, night):
    """FC person records of a map at that time: FC cell, facing, step interval, picture, messages."""
    state = fc_state(night)
    out = []
    for rec in dq4talk.npc_list(prg, fc_group, number, night):
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
            elif p == "WAIT":
                page()
                k = _skip_speaker(pieces, k)
            elif p == "3D":
                if k >= len(pieces) or not isinstance(pieces[k], tuple):
                    raise ValueError(f"FC message {m:04X}: dakuten mark without a character")
                codes.append(_code(m, unicodedata.normalize("NFC", pieces[k][1] + "\u3099")))
                k += 1
            elif p == "NOINDENT":
                pass
            elif p == "END":
                break
            else:
                raise ValueError(f"FC message {m:04X}: no DQ5 code for {{{p}}}")
    while codes and codes[-1] == PAGE:
        codes.pop()
    return codes + [END]


def nothing_codes():
    return [CODE_OF[c] for c in NOTHING] + [END]


def message_pool(dq5_rom_path):
    """DQ5 messages >= 633 shown directly by exactly one map's people in POOL_GROUPS and by no talk script."""
    out = subprocess_json(["dq5npcrecord.py", dq5_rom_path, "dump"])
    scripts = subprocess_json(["dq5talkwrite.py", dq5_rom_path, "dump"])
    in_scripts = set()

    def walk(body):
        for op in body:
            if op.get("op") == "msg":
                in_scripts.add(op["id"])
            for key in ("then", "else", "body"):
                if isinstance(op.get(key), list):
                    walk(op[key])
    for s in scripts["scripts"]:
        walk(s["body"])
    users = collections.defaultdict(set)
    for e in out["entries"]:
        for f in [e["fields"]] if "fields" in e else [e["day"], e["night"]]:
            if TALK_FIRST <= f["talk"] < 0x900:
                users[f["talk"] + TALK_MESSAGE].add(e["name"].split()[0])
    return sorted(m for m, names in users.items()
                  if len(names) == 1 and re.fullmatch(r"[0-9A-F]{2}/[0-9A-F]{2}", name := next(iter(names)))
                  and int(name[:2], 16) in POOL_GROUPS and m not in in_scripts)


def subprocess_json(args):
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "out.json"
        subprocess.run([sys.executable, str(DQ5_TOOLS / args[0]), *args[1:], "-o", str(path)], check=True,
                       capture_output=True)
        return json.loads(path.read_text(encoding="utf-8"))


def port(dq5_path, dq4_path):
    """(dq5npcrelocate lists, dq5text messages, report)."""
    data = Path(dq4_path).read_bytes()
    prg, rom = ines.prg(data), dq4text.Rom(data)
    pool = message_pool(dq5_path)
    texts = {}
    lists, report = [], {}
    for name, (group, number) in sorted(GROUPS.items(), key=lambda kv: kv[1]):
        fc_group = LINKS[group]["fc"]
        entries, people = [], []
        shops = merchants(prg, fc_group, number)
        for night in (False, True):
            for p in fc_people(prg, fc_group, number, night):
                shows = [m for m in p["shows"] if m is not None]
                predicted = [m - dq4talk.SERVICE for m in shows if m >= dq4talk.SERVICE]
                service = shops.get((p["x"], p["y"], night), predicted[0] if predicted else None)
                message = None
                if service is not None:
                    # A seller stays behind the counter: the DQ5 wander script would walk off it.
                    talk = service
                    p = {**p, "interval": 0}
                else:
                    key = tuple(shows)
                    if key not in texts:
                        if len(texts) == len(pool):
                            raise ValueError(f"DQ5 message pool of {len(pool)} is used up")
                        texts[key] = (pool[len(texts)], dq5_codes(rom, shows) if shows else nothing_codes())
                    message = texts[key][0]
                    talk = message - TALK_MESSAGE
                if p["picture"] not in PICTURES:
                    raise ValueError(f"{name}: FC picture {p['picture']:02X} has no DQ5 picture")
                x, y = cell(p["x"], p["y"])
                fields = {"x": x, "y": y, "facing": p["facing"], "talk": talk,
                          "gfx": PICTURES[p["picture"]], "layer": 0, "interval": p["interval"]}
                entries.append({"from": WALK if p["interval"] else STAND, "time": "night" if night else "day",
                                "fields": fields})
                people.append({**p, "night": night, "service": service,
                               "message": None if message is None else f"{message:03X}", "dq5": fields})
        lists.append({"map": f"{group:02X}/{number:02X}", "entries": entries})
        report[f"{group:02X}/{number:02X}"] = people
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
