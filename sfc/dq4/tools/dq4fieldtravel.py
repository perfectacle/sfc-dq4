"""ルーラ destinations of the FC towns ported as DQ5 groups (dq4groupbuild.LINKS).

The DQ5 ルーラ list (25:85D5, 22 groups; its names are name table 0B by slot, its visited flags 7E:2030~ by
slot) takes the FC towns in FC destination order (FC_GROUPS). 1E:E545 lands the party on (X, Y+1) of the group's
first entrance row, so the group's aux entrance rows start with the cell above the FC destination block
(landing_rows): the party lands on that block's top-left cell. sfc/dq4/docs/dq4-field-format.md 「ルーラ」.

  python sfc/dq4/tools/dq4fieldtravel.py -o work/travel
"""

import argparse
import functools
import json
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
DQ5_TOOLS = TOOLS.parents[1] / "dq5" / "tools"
FC_TOOLS = TOOLS.parents[2] / "fc" / "dq4" / "tools"
for path in (TOOLS, DQ5_TOOLS, FC_TOOLS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

RULER_LIST, RULER_COUNT = 0x2585D5, 22
NAME_TABLE = 11
# FC ルーラ destinations (fc/dq4/tools/dq4field.py places) by FC group, in FC destination order. Each must be the
# first FC group of its DQ5 group: the landing takes the DQ5 group's first entrance row. テンペ (0E) and フレノール
# (0F) share DQ5 group 3D with サントハイム, so they have no slot of their own.
FC_GROUPS = (0x01, 0x02, 0x12, 0x14)


def lorom(addr):
    return (addr >> 16 & 0x7F) * 0x8000 + (addr & 0x7FFF)


def cpu(addr):
    return f"{addr >> 16:02X}:{addr & 0xFFFF:04X}"


@functools.cache
def _codes(dq5):
    """DQ5 name byte(s) of each kana: single bytes first, then 84 (dakuten) or 83 (handakuten) + key."""
    import dq5text
    from dq5map import Rom
    rom = Rom(dq5)
    out = {}
    for b in range(0x02, 0x83):
        out.setdefault(dq5text.text([rom.u16(dq5text.STRING_CODES + b * 2)]), bytes([b]))
    for k in range(0x28 + 11):
        prefix = 0x84 if k < 0x28 else 0x83
        out.setdefault(dq5text.text([rom.u16(dq5text.MARK_CODES + k * 2)]),
                       bytes([prefix, rom.u8(dq5text.MARK_KEYS + k)]))
    return out


def name_bytes(dq5, name):
    """DQ5 name-table bytes of a kana name. FC text writes some katakana with the hiragana glyph (り), so a kana
    with no code is tried in the other script."""
    codes = _codes(dq5)
    out = b""
    for c in name:
        other = chr(ord(c) + 0x60) if "ぁ" <= c <= "ゖ" else chr(ord(c) - 0x60) if "ァ" <= c <= "ヶ" else c
        if c not in codes and other not in codes:
            raise ValueError(f"{name}: no DQ5 code for {c!r}")
        out += codes.get(c, codes.get(other))
    return out


def destinations(prg, links, doors):
    """[{slot, fc, group, name, land, row}] of FC_GROUPS: the DQ5 group whose first part is the FC group, the
    landing cell (top-left cell of the FC destination block) and the entrance cell above it that must lead the
    group's entrance rows. doors[FC group] = (DQ5 entrance cells, leave cell) as dq4groupbuild.doors."""
    import dq4field
    records = {e["group"]: e for e in dq4field.places(prg) if e["kind"] == "field" and e["field"] == 0}
    first = {parts[0]["fc"]: group for group, parts in links.items()}
    out = []
    for slot, fc in enumerate(FC_GROUPS):
        if fc not in first:
            raise ValueError(f"FC group {fc:02X} is not the first part of a LINKS group")
        e = records[fc]
        land = (2 * e["x"], 2 * e["y"])
        row = (land[0], land[1] - 1)
        if row not in doors[fc][0]:
            raise ValueError(f"FC group {fc:02X}: {row} above the landing {land} is not one of its entrance cells")
        out.append({"slot": slot, "fc": fc, "group": first[fc], "name": e["name"], "land": land, "row": row})
    return out


def landing_rows(rows, dests):
    """Aux entrance rows ({group, x, y}) with each destination's row first among its group's rows."""
    want = {(d["group"], *d["row"]) for d in dests}
    return sorted(rows, key=lambda r: (r["group"], r["x"], r["y"]) not in want)


def writes(dq5, dests):
    """dq5patch/1 writes: the ルーラ list slots."""
    o = lorom(RULER_LIST)
    old = dq5[o:o + RULER_COUNT]
    new = bytearray(old)
    for d in dests:
        new[d["slot"]] = d["group"]
    return [{"at": cpu(RULER_LIST), "hex": new.hex(" ").upper(), "orig": old.hex(" ").upper(),
             "note": "ルーラ 행선지 그룹"}]


def names_doc(dq5, dests):
    """dq5names/1 of the destinations' names in name table 0B (the ルーラ list window)."""
    return {"format": "dq5names/1", "tables": [{"table": NAME_TABLE, "names": [
        {"id": d["slot"], "bytes": list(name_bytes(dq5, d["name"]))} for d in dests]}]}


def main():
    import dq4groupbuild
    from kr_patch.fc import ines
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dq5", default="rom/dq5.sfc", type=Path)
    ap.add_argument("--dq4", default="rom/dq4.nes", type=Path)
    ap.add_argument("-o", "--out", required=True, type=Path)
    args = ap.parse_args()
    prg = ines.prg(args.dq4.read_bytes())
    dests = destinations(prg, dq4groupbuild.LINKS, dq4groupbuild.doors(prg))
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "travel.json").write_text(json.dumps(dests, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(dests, ensure_ascii=False))


if __name__ == "__main__":
    main()
