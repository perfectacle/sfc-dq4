"""2장 일행의 필드 주문 검사(MesenCE 헤드리스, dq5warp.lua FIELD). 형식은 sfc/dq4/docs/dq4-growth-format.md 「2장 일행」.

  behomara  롬의 2장 일행 셋(아리나 1레벨 기록·합류 기록, dq4ch2event.native)을 일행 칸 0~2 에 두고 셋의 HP 를
            HP_START, 최대 HP 를 MAX_HP 로 낮춰 둔 뒤, 크리프트(칸 1)가 필드에서 ベホマラー(dq4party 의 필드 처리기)를
            외운다. 셋 모두 HP 가 FC 양(dq4party.FC_BEHOMARA)만큼 오르고 크리프트 MP 가 FC 값만큼 줄어야 한다

  MESENCE=… LIBDIR=… python sfc/dq4/tools/dq4fieldspellcheck.py --rom work/ch1/dq4-ch1-full.sfc --out work/fieldspell
"""

import argparse
import json
import os
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parents[2]
for path in (TOOLS, ROOT / "fc" / "dq4" / "tools", ROOT / "sfc" / "dq5" / "tools"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import dq4freshstate  # noqa: E402
from dq4groupcheck import field_scene  # noqa: E402

HERO, RECORD = 0x2040, 42
HP, MP, MAX_HP, MAX_MP, SPELLS = 0x02, 0x04, 0x0E, 0x10, 0x23
HP_START, MAX_HP_SET, MP_SET = 5, 200, 99
FIELD_CELL = (78, 148)            # サントハイム 성 앞 필드(ルーラ 내리는 칸)
# 명령 창 → じゅもん(오른쪽) → 누가: 둘째(크리프트) → 필드 목록 한 줄씩 → ベホマラー 칸. 메시지는 A 로 넘긴다
SPELL_MENU = "a:8,wait:60,right:8,wait:40,a:8,wait:60,down:6,wait:20,a:8,wait:60,"
MESSAGES = "a:6,wait:60," * 8 + "wait:200"


def party_sets(rom, field_slot):
    """dq5warp.lua SET 꼴: 롬의 2장 일행 셋 기록, 낮춘 HP, 크리프트의 MP 와 그 필드 칸 비트."""
    import dq4ch2event as ev2
    import dq4growth
    _, at = ev2.native()
    n = len(ev2.RECRUITS)
    o = dq4growth.lorom(at["record"])
    records = [bytearray(rom[o:o + RECORD])]
    o = dq4growth.lorom(at["recruits"])
    records += [bytearray(rom[o + RECORD * k:o + RECORD * (k + 1)]) for k in range(n)]
    for r in records:
        r[HP:HP + 2] = HP_START.to_bytes(2, "little")
        r[MAX_HP:MAX_HP + 2] = MAX_HP_SET.to_bytes(2, "little")
    kiryl = records[1]
    kiryl[MP:MP + 2] = kiryl[MAX_MP:MAX_MP + 2] = MP_SET.to_bytes(2, "little")
    kiryl[SPELLS] |= 1 << field_slot
    sets = [(HERO + RECORD * k + j, b) for k, r in enumerate(records) for j, b in enumerate(r)]
    sets += [(0x201D, 1 + n), (0x201E, 1 + n), (0x201F, 1 + n)]
    sets += [(0x2020 + k, k) for k in range(1 + n)] + [(0x2028 + k, k) for k in range(1 + n)]
    return ";".join(f"{a:04X}={v:02X}" for a, v in sets)


def expect(dq5, dq4):
    """(크리프트 필드 목록의 ベホマラー 칸, 양 범위, MP)."""
    import dq4data
    import dq4growth
    import dq4party
    prg, rom = dq4party._fc(dq4), dq4party._dq5(dq5)
    field = dq4party.plan(prg, rom, dq4growth.FC_KIRYL)["field"]
    base, width = dq4party.FC_BEHOMARA
    return field.index(dq4party.BEHOMARA), (base, base + width - 1), dq4data.spell_mp(prg, 0x2C)[0]


def judge(ram, low, high, mp):
    hps = [int.from_bytes(ram[HERO + RECORD * k + HP:HERO + RECORD * k + HP + 2], "little") for k in range(3)]
    kiryl_mp = int.from_bytes(ram[HERO + RECORD + MP:HERO + RECORD + MP + 2], "little")
    problems = [f"일행 {k} HP {HP_START} → {hp}, 기대 {HP_START + low}~{HP_START + high}"
                for k, hp in enumerate(hps) if not HP_START + low <= hp <= HP_START + high]
    if kiryl_mp != MP_SET - mp:
        problems.append(f"크리프트 MP {MP_SET} → {kiryl_mp}, 기대 {MP_SET - mp}")
    return {"hp": hps, "mp": kiryl_mp, "problems": problems, "ok": not problems}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rom", required=True, type=Path)
    ap.add_argument("--dq4", default=ROOT / "rom" / "dq4.nes", type=Path)
    ap.add_argument("--dq5", default=ROOT / "rom" / "dq5.sfc", type=Path)
    dq4freshstate.add_argument(ap)
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()
    mesence = Path(os.environ["MESENCE"])
    out = args.out.resolve()
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f"{out} is not empty")
    rom = args.rom.resolve()
    state = dq4freshstate.resolve(args.state, mesence, rom, out / "start")
    slot, (low, high), mp = expect(args.dq5, args.dq4)
    test = SPELL_MENU + "down:6,wait:20," * slot + "a:8,wait:60," + MESSAGES
    got = field_scene(mesence, rom, state, out, "behomara", *FIELD_CELL, test,
                      SET=party_sets(rom.read_bytes(), slot), MAXF="3000")
    result = {"behomara": {"got": got, "slot": slot}}
    if "error" in got:
        result["behomara"].update(ok=False, problems=[got["error"]])
    else:
        result["behomara"].update(judge((out / "behomara" / "final.wram").read_bytes(), low, high, mp))
    (out / "results.json").write_text(json.dumps(result, ensure_ascii=False, indent=1))
    for name, r in result.items():
        print(name, "통과" if r["ok"] else "실패", r.get("hp"), r.get("mp"), "; ".join(r.get("problems", [])))
    return 0 if all(r["ok"] for r in result.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
