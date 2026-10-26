"""DQ5(SFC) 효과음(소리 명령 0C, 번호 32~46)을 부르는 곳 목록. 형식은 sfc/dq5/docs/dq5-sound-format.md 의 「효과음 쓰임」.

효과음은 네 길로 나간다.
  연출  전투 연출 스크립트의 3A(22:DB9E)와 26:8B59(7E:100E bit7)가 연출 번호로 28:8000 을 부른다.
        28:8074[연출] = 소리 칸(FF 없음, FE 무기), 28:811E[칸*2] = (효과음, 갈래 X). 무기면 26:8A65[무기] & 3C 로
        28:816E 를 고른다(맨손 $0DA7 bit7 은 첫 칸).
  인물  인물 인라인 스크립트 명령 20 n X(dq5npc.py).
  코드  BRK 16 n X · BRK 19 n X(00:9256)와 LDA #n … JSL 24:FEAC. 롬 전체에서 바이트 꼴로 찾으므로 데이터 속 우연한
        바이트도 섞인다(정적 후보). 실측한 자리는 형식 문서에 있다.
  전투 메시지  코드 F9(24:8898, BRK 19 32).

  python sfc/dq5/tools/dq5sfx.py rom/dq5.sfc                # 효과음마다 갈래별로 부르는 곳
  python sfc/dq5/tools/dq5sfx.py rom/dq5.sfc --fx           # 연출 번호 → 효과음 표
  python sfc/dq5/tools/dq5sfx.py rom/dq5.sfc --json out.json
"""
import argparse
import json
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(__file__))
from dq5map import Rom, lorom  # noqa: E402
import dq5fx  # noqa: E402
import dq5npc  # noqa: E402

FX_SLOT = 0x288074                  # [연출] → 소리 칸
FX_SOUND = 0x28811E                 # [칸*2] → 효과음, 갈래
WEAPON_SOUND = 0x28816E             # [(26:8A65[무기] & 3C) >> 1] → 효과음, 갈래
ITEM_FLAGS = 0x268A65
FX_LIMIT = 0xAA                     # 28:802A CMP #$AA
SFX = range(0x32, 0x47)
ITEMS = 0xD8
WEAPON_KINDS = 6                    # 종류 0~6 이 무기(칼·지팡이·채찍·부메랑·발톱·창·철퇴). 7 부터는 갑옷 등이라 공격에 안 쓰임


def fx_sounds(rom):
    """{연출: [(효과음, 갈래, 조건)]}. 무기 칸(FE)은 무기 종류마다 한 줄."""
    out = {}
    for fx in range(FX_LIMIT):
        slot = rom.u8(FX_SLOT + fx)
        if slot == 0xFF:
            continue
        if slot == 0xFE:
            out[fx] = weapon_sounds(rom)
        else:
            out[fx] = [(rom.u8(FX_SOUND + slot * 2), rom.u8(FX_SOUND + slot * 2 + 1), '')]
    return out


def weapon_sounds(rom):
    """[(효과음, 갈래, '무기 종류 k: 물건…')]. 26:8A65 bit2-5 가 종류."""
    import dq5text
    kinds = defaultdict(list)
    for item in range(ITEMS):
        kinds[(rom.u8(ITEM_FLAGS + item) & 0x3C) >> 2].append(item)
    out = [(rom.u8(WEAPON_SOUND), rom.u8(WEAPON_SOUND + 1), '맨손($0DA7 bit7)')]
    for k in sorted(kinds):
        if k > WEAPON_KINDS:
            continue
        o = WEAPON_SOUND + k * 2
        names = [dq5text.text(dq5text.string_codes(rom, dq5text.string(rom, 5, i))) for i in kinds[k][:3]]
        out.append((rom.u8(o), rom.u8(o + 1), '무기 종류 %d(%s 등 %d개)' % (k, '·'.join(names), len(kinds[k]))))
    return out


def code_sites(rom):
    """[(주소, 꼴, 효과음, 갈래)]. 바이트 꼴로 찾은 정적 후보."""
    d = rom.d
    out = []
    for o in range(len(d) - 8):
        bank, addr = o // 0x8000, 0x8000 | (o & 0x7FFF)
        cpu = bank << 16 | addr
        if d[o] == 0x00 and d[o + 1] in (0x16, 0x19) and d[o + 2] in SFX and d[o + 3] <= 0x20:
            out.append((cpu, 'BRK %02X' % d[o + 1], d[o + 2], d[o + 3]))
        if d[o] == 0xA9 and d[o + 1] in SFX:
            # LDA #n [LDX #x] JSL 24:FEAC
            if d[o + 2:o + 6] == b'\x22\xAC\xFE\x24':
                # 바로 앞이 LDA #x / TAX 면 아래에서 갈래 x 로 센다
                if not (d[o - 1] == 0xAA and d[o - 3] == 0xA9):
                    out.append((cpu, 'JSL', d[o + 1], None))
            elif d[o + 2] == 0xA2 and d[o + 4:o + 8] == b'\x22\xAC\xFE\x24':
                out.append((cpu, 'JSL', d[o + 1], d[o + 3]))
        # LDA #x / TAX / LDA #n / JSL 24:FEAC (00:944E)
        if d[o] == 0xA9 and d[o + 2] == 0xAA and d[o + 3] == 0xA9 and d[o + 4] in SFX and \
                d[o + 5:o + 9] == b'\x22\xAC\xFE\x24':
            out.append(((o // 0x8000) << 16 | 0x8000 | ((o + 3) & 0x7FFF), 'JSL', d[o + 4], d[o + 1]))
    return out


def npc_sites(rom):
    """[(목록 이름, 인물 엔트리, 효과음, 갈래)]. 같은 스크립트를 낮·밤이 나눠 쓰면 한 번."""
    out = []
    for la, name in dq5npc.all_lists(rom):
        for a, _ in dq5npc.list_entries(rom, la):
            seen = set()
            for night in (False, True):
                s = dq5npc.script_address(rom, a, night)
                if s is None or s in seen:
                    continue
                seen.add(s)
                for _, raw, _ in dq5npc.script_ops(dq5npc.script_bytes(rom, s)):
                    if raw[0] == 0x20:
                        out.append((name, a, raw[1], raw[2]))
    return out


def catalogue(rom):
    """{(효과음, 갈래): {'fx': [...], 'npc': [...], 'code': [...]}}. 갈래 None 은 레지스터 X."""
    cat = defaultdict(lambda: {'fx': [], 'npc': [], 'code': []})
    for fx, rows in fx_sounds(rom).items():
        name, side, _ = dq5fx.fx_name(rom, fx) if fx < dq5fx.FX_COUNT else ('', '', [])
        for n, x, cond in rows:
            cat[(n, x)]['fx'].append({'fx': fx, 'name': name, 'side': side, 'cond': cond})
    for name, a, n, x in npc_sites(rom):
        cat[(n, x)]['npc'].append({'list': name, 'entry': '%06X' % a})
    for a, kind, n, x in code_sites(rom):
        cat[(n, x)]['code'].append({'at': '%02X:%04X' % (a >> 16, a & 0xFFFF), 'kind': kind})
    for c in cat[(0x32, 0)]['code']:
        if c['at'] == '24:8898':
            c['kind'] += ' (전투 메시지 F9)'
    return cat


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('rom')
    ap.add_argument('--fx', action='store_true', help='연출 번호 → 효과음')
    ap.add_argument('--json')
    a = ap.parse_args()
    rom = Rom(open(a.rom, 'rb').read())
    if a.fx:
        for fx, rows in sorted(fx_sounds(rom).items()):
            name = dq5fx.fx_name(rom, fx)[0] if fx < dq5fx.FX_COUNT else ''
            for n, x, cond in rows:
                print('연출 %02X %-10s 효과음 %02X 갈래 %02X %s' % (fx, name, n, x, cond))
        return
    cat = catalogue(rom)
    if a.json:
        json.dump({'%02X-%s' % (n, '--' if x is None else '%02X' % x): v for (n, x), v in sorted(
            cat.items(), key=lambda t: (t[0][0], -1 if t[0][1] is None else t[0][1]))}, open(a.json, 'w'),
            ensure_ascii=False, indent=1)
    for (n, x), v in sorted(cat.items(), key=lambda t: (t[0][0], -1 if t[0][1] is None else t[0][1])):
        if n not in SFX:
            continue
        parts = []
        if v['fx']:
            parts.append('연출 ' + ' '.join('%02X%s' % (f['fx'], '(%s)' % f['name'] if f['name'] else '') for f in v['fx']))
        if v['npc']:
            parts.append('인물 ' + ' '.join(sorted({p['list'] for p in v['npc']})))
        if v['code']:
            parts.append('코드 %d곳 ' % len(v['code']) + ' '.join(c['at'] for c in v['code'][:12]))
        print('%02X-%s  %s' % (n, '레지' if x is None else '%02X' % x, ' | '.join(parts)))


if __name__ == '__main__':
    main()
