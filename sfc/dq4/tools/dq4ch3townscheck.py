"""3장 그룹 인물이 낼 수 있는 대사에 남은 일본어와 창 넘침을 센다(에뮬레이터 없이 빌드 산출물만 읽음).

3장 그룹(dq4npccheck.CHAPTER3_GROUPS)의 맵마다 3장 동안 걸릴 수 있는 인물 목록을 모은다: 옮긴 대체 표를 앞 줄부터
보며 3장 flag 로 거는 줄(3장 내내 맞음)에서 멈추고, 그 앞의 줄(사건 flag 로 거는 목록)을 모두 넣는다. 그런 줄이 없으면
기본 목록도 넣는다. 2장 flag(dq4ch2event.CHAPTER2)로 거는 줄은 3장에 꺼져 있어 뺀다. 인물마다 대화 스크립트의 모든
갈래에서 띄우는 메시지를 모아, 빌드의 messages.json 에서

  - 가나·한자 글자 코드(DQ5 글꼴 dq5text.CHARS 의 일본 글자)를 센다. 0 이어야 한다.
  - 한글로 쓴 메시지의 줄이 창(dq4chapter1.LINE_COLS, 서술 NARR_COLS, 이름을 단 쪽의 첫 줄은 이름만큼 짧게)과
    쪽당 줄 수(PAGE_LINES)를 넘는지 본다.

FC 가 사람을 닿지 않는 곳에 세운 칸(dq4npccheck.staged)은 뺀다. ALLOW 는 아직 다른 모듈이 맡을 사람이다(이유를 적음).
3장 동료 대화(dq4ch3partytalk, 「はなす」로 일행이 하는 말)의 메시지도 같은 둘을 본다(한글이 아니면 일본어로 셈).

  uv run --locked python sfc/dq4/tools/dq4ch3townscheck.py --keep work/ch3/keep --texts work/ch3/messages.json
"""
import argparse
import json
import re
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[1] / 'dq5' / 'tools'), str(HERE.parents[2] / 'fc' / 'dq4' / 'tools')]

import dq4chapter1 as ch1  # noqa: E402

def _cell(x, y):
    return (2 * x, 2 * y + 1)


# 일본어로 남아도 되는 사람: (맵, 낮·밤 또는 None, FC 칸 또는 None(그 맵 모두)) → 이유. 맡을 사건이 들어오면 지운다
ALLOW = {}
# 사건 모듈이 맡아 한글로 바꿀 사람. 그 모듈 파일이 없을 때만 남겨 둔다(파일이 생기면 이 사람도 0 이어야 함)
PENDING = {
    'dq4ch3bonmalmo': {('3F/00', 'day', (0x0D, 0x0C)), ('3F/01', 'day', (0x01, 0x0B)), ('3F/01', 'night', (0x20, 0x06)),
                       ('3F/01', None, (0x11, 0x07)), ('48/00', None, (0x0C, 0x01)), ('48/01', None, (0x04, 0x0D)),
                       ('40/06', 'day', (0x0F, 0x0A))},
    'dq4ch3endor': {('40/00', 'day', (0x06, 0x1C)), ('40/02', 'day', (0x11, 0x12)), ('40/02', 'day', (0x12, 0x12)),
                    ('40/06', 'day', (0x0B, 0x0A)), ('40/08', None, None), ('40/0A', None, None)},
    'dq4ch3tunnel': {('47/00', None, None), ('47/01', None, None)},
}


def allowed(m, time, at, have=None):
    """이 사람(맵, 낮·밤, DQ5 셀)의 일본어를 남겨 둘 이유. 없으면 None. have(모듈 이름 → 파일이 있는지)는 시험용."""
    have = have or (lambda name: (HERE / f'{name}.py').is_file())

    def hit(mm, t, fc):
        return mm == m and t in (None, time) and (fc is None or _cell(*fc) == at)
    why = next((why for who, why in ALLOW.items() if hit(*who)), None)
    if why:
        return why
    return next((f'{module} 몫(모듈이 아직 없음)' for module, people in PENDING.items()
                 if not have(module) and any(hit(*who) for who in people)), None)


JAPANESE = re.compile('[぀-ヿ一-鿿]')
LINE, END, PAGE, SPEAK, NARR, HERO = ch1.LINE, ch1.END, ch1.PAGE, ch1.SPEAK, ch1.NARR, ch1.HERO
TALK_BASE, MESSAGE_OF_TALK, SCRIPT_TALK = ch1.TALK_BASE, ch1.MESSAGE_OF_TALK, 0x900


def japanese_codes():
    """DQ5 글꼴에서 가나·한자인 글자 코드."""
    import dq5text
    return {code for code, char in enumerate(''.join(dq5text.CHARS)) if JAPANESE.match(char)}


def candidate_lists(doc, maps):
    """{맵: [(목록 이름, 항목)]}: 3장 동안 그 맵에 걸릴 수 있는 목록."""
    import dq4ch2event
    import dq4ch3event
    new = {lst["name"]: lst["entries"] for lst in doc["new_lists"]}
    base = {lst["map"]: lst["entries"] for lst in doc["lists"]}
    out = {}
    for m in maps:
        got, always = [], False
        for o in doc["overrides"]:
            if o["map"] != m:
                continue
            flag = (o["flag"], o["mask"])
            if flag == dq4ch2event.CHAPTER2 and o["when"] == "on":
                continue
            name = o["list"][4:] if o["list"].startswith("new:") else o["list"]
            got.append((name, new.get(name, [])))
            if flag == dq4ch3event.CHAPTER3 and o["when"] == "on":
                always = True
                break
        if not always:
            got.append(('기본', base.get(m, [])))
        out[m] = got
    return out


def messages_of(body, acc):
    for op in body:
        if op.get("op") == "msg":
            acc.append(int(op["id"], 16))
        for k in ("then", "else"):
            if isinstance(op.get(k), list):
                messages_of(op[k], acc)
    return acc


def talk_messages(talk, scripts):
    """대화 번호 → 띄우는 메시지 번호들. DQ5 원래 대화(시설 등, 덧붙인 대화 밖)는 None."""
    if talk in scripts:
        return messages_of(scripts[talk], [])
    if TALK_BASE <= talk < SCRIPT_TALK:
        return [talk + MESSAGE_OF_TALK]
    return None


def width(piece):
    if isinstance(piece, str):
        return len(piece)
    if piece == HERO:
        return ch1.NAME_COLS
    return 1 if piece < 0x1000 else 0


def window_problems(parts):
    """한글로 쓴 메시지의 넘침: [(쪽, 줄, 칸, 한도)]."""
    out, page, lines, cols, limit, first_cut = [], 0, 0, 0, ch1.LINE_COLS, 0
    narr = NARR in parts
    i = 0

    def close():
        room = (ch1.NARR_COLS if narr else ch1.LINE_COLS) - (first_cut if lines == 0 else 0)
        if cols > room:
            out.append((page, lines, cols, room))
    while i < len(parts):
        p = parts[i]
        if p == SPEAK:
            # 이름과 「 가 ＊「 자리를 넘는 만큼 그 쪽 첫 줄이 짧다(dq4chapter1._message)
            first_cut = max(0, len(parts[i + 1]) + 1 - 2)
            i += 3
            continue
        if p in (LINE, PAGE, END):
            close()
            if p == LINE:
                lines += 1
                if lines >= ch1.PAGE_LINES:
                    out.append((page, lines, cols, f'{ch1.PAGE_LINES}줄'))
            else:
                page, lines, first_cut = page + 1, 0, 0
            cols = 0
        else:
            cols += width(p)
        i += 1
    return out


def party_talk_messages(dq5, dq4):
    """{메시지 번호: 이름}: 3장 동료 대화(dq4ch3partytalk) 메시지. 빌드와 같은 셈(옮긴 인물 메시지 뒤 1장·2장 사건 메시지,
    그 뒤 3장 모듈 차례)."""
    import dq4ch3event
    import dq4ch3partytalk
    import dq4npcport
    _, ported, _ = dq4npcport.port(dq5, dq4)
    first = ch1.chapter3_message(dq4npcport.FIRST_MESSAGE + len(ported))
    ctx = next(c for c in dq4ch3event.contexts(first) if c.module is dq4ch3partytalk)
    return {mid: name for name, mid in ctx.msg.items()}


def check(keep, texts, dq4):
    import dq4npccheck
    from kr_patch.fc import ines
    import dq4block
    doc = json.loads((keep / 'npc.json').read_text(encoding='utf-8'))
    scripts = {int(s["talk"], 16): s["body"]
               for s in json.loads((keep / 'groups' / 'talk.json').read_text(encoding='utf-8'))["scripts"]}
    report = json.loads((keep / 'groups' / 'npc-report.json').read_text(encoding='utf-8'))
    msgs = {int(k, 16): v for k, v in json.loads(texts.read_text(encoding='utf-8'))["messages"].items()}
    jp = japanese_codes()
    prg = ines.prg(dq4.read_bytes())
    maps = sorted({lst["map"] for lst in doc["lists"] if lst["map"][:2] in dq4npccheck.CHAPTER3_GROUPS} |
                  {m for m in report if m[:2] in dq4npccheck.CHAPTER3_GROUPS and '/' in m and len(m) == 5})
    japanese, window, kept, seen = [], [], [], set()
    people = 0
    for m, got in candidate_lists(doc, maps).items():
        fc_of = {(p["night"], p["dq5"]["x"], p["dq5"]["y"]): p for p in report.get(m, [])}
        source = dq4block.Map(prg, *dq4npccheck.fc_map(prg, int(m[:2], 16), int(m[3:], 16)))
        for name, entries in got:
            for e in entries:
                f = e["fields"]
                p = fc_of.get((e["time"] == "night", f["x"], f["y"]))
                if p is not None and dq4npccheck.staged(source, dq4npccheck.fc_map(prg, int(m[:2], 16), int(m[3:], 16)), p):
                    continue
                ids = talk_messages(f["talk"], scripts)
                if ids is None:
                    continue
                people += 1
                who = (m, e["time"], (f["x"], f["y"]))
                for mid in ids:
                    parts = msgs.get(mid, [])
                    bad = sum(1 for c in parts if isinstance(c, int) and c in jp)
                    if bad:
                        why = allowed(*who)
                        if why:
                            kept.append((who, mid, why))
                        else:
                            japanese.append((who, name, mid, bad))
                    elif (mid, 'w') not in seen and any(isinstance(c, str) for c in parts):
                        seen.add((mid, 'w'))
                        window += [(who, mid, *w) for w in window_problems(parts)]
    # 동료 대화(「はなす」): 말 상대가 아니라 일행이 띄우는 메시지라 맵·칸 대신 동료 대화로 적는다
    party = party_talk_messages(dq4.parent / 'dq5.sfc', dq4)
    for mid, name in sorted(party.items()):
        who = ('동료 대화', name, None)
        parts = msgs.get(mid, [])
        bad = sum(1 for c in parts if isinstance(c, int) and c in jp)
        if bad or not any(isinstance(c, str) for c in parts):
            japanese.append((who, '동료 대화', mid, bad))
        else:
            window += [(who, mid, *w) for w in window_problems(parts)]
    return {'people': people, 'party_talk': len(party), 'japanese': japanese, 'window': window, 'kept': kept}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--keep', required=True, type=Path, help='dq4chapter1.py build --keep 폴더(npc.json, groups/)')
    ap.add_argument('--texts', required=True, type=Path, help='같은 빌드의 messages.json')
    ap.add_argument('--dq4', default=HERE.parents[2] / 'rom' / 'dq4.nes', type=Path)
    args = ap.parse_args()
    r = check(args.keep, args.texts, args.dq4)
    for who, name, mid, bad in r['japanese']:
        print(f'일본어: {who[0]} {who[1]} 셀 {who[2]} 목록 {name} 메시지 {mid:03X} 글자 {bad}')
    for who, mid, page, line, cols, room in r['window']:
        print(f'창 넘침: {who[0]} {who[1]} 셀 {who[2]} 메시지 {mid:03X} 쪽 {page} 줄 {line} {cols}칸 > {room}')
    for who, mid, why in r['kept']:
        print(f'남겨 둠: {who[0]} {who[1]} 셀 {who[2]} 메시지 {mid:03X} — {why}')
    ok = not r['japanese'] and not r['window']
    print(json.dumps({'status': 'passed' if ok else 'failed', 'people': r['people'], 'party_talk': r['party_talk'],
                      'japanese': len(r['japanese']),
                      'window': len(r['window']), 'kept': len(r['kept'])}, ensure_ascii=False))
    raise SystemExit(0 if ok else 1)


if __name__ == '__main__':
    main()
