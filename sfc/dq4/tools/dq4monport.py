"""2장 전투 몬스터를 NDS 그림으로: FC 몬스터마다 DQ5 몬스터 번호·그림 번호를 따로 주고, dq4monart 로 15색으로 다듬은
NDS 그림을 dq5monwrite 문서(dq5monster/1)로 쓴다. 형식 문서 sfc/dq4/docs/dq4-sprite-format.md 「2장 전투 몬스터 그림」.

필드 조우의 대역(dq4fieldencounter.MONSTERS)은 여러 FC 몬스터가 DQ5 몬스터 하나를 같이 써서, 그림을 바꾸려면 번호를
나눠야 한다. 새 번호(PORT)에는 지금 대역의 레코드 25바이트를 그대로 옮겨(능력치·행동은 지금과 같음) 이름과 그림만 바꾼다.
사건 몬스터(텐페 보스·대회 상대)는 사건 모듈이 그 번호에 FC 능력치와 이름을 쓴다.

  python sfc/dq4/tools/dq4monport.py doc rom/dq5.sfc -o work/monport     # 그림 PNG 와 dq5monster/1 문서
"""
import argparse
import json
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
DQ5_TOOLS = TOOLS.parents[1] / 'dq5' / 'tools'
for path in (TOOLS, DQ5_TOOLS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from PIL import Image  # noqa: E402

import dq4monart  # noqa: E402

# FC 몬스터 → DQ5 몬스터 번호. 그림은 그 번호가 원래 쓰는 DQ5 그림 자리에 덮는다. 몬스터의 그림 번호를 바꾸면
# dq5monwrite 가 새 그림이 원래 그림의 전투 배치 한도(조각·타일·가로·세로·줄 최대 타일) 안이어야 받으므로, 원래 그림이
# NDS 그림을 담을 만큼 크고, 그 그림의 머리를 다른 그림 번호가 같이 쓰지 않으며(같이 쓰는 번호는 dq5monlimits 가
# 세는 조합에 나오지 않아 받지 않음), 그 그림(머리)을 계속 쓰이는 몬스터(다른 FC 몬스터의 대역, 1장 보스)가 쓰지 않으며, DQ5 가나
# 이름이 롬 안에서 하나뿐인(전투 글 이름 표 dq4battlemsg 가 가나 이름 바이트로 한글을 찾음) 번호 01~BF 를 골랐다.
# 40(ニセたいこう: 지면 snes9x 에서 멈춤)·ダミー 몬스터·2장 예비(dq4ch2slots.SPARE)는 뺐다.
# 필드 조우에 나오는 FC 몬스터 → DQ5 번호(지금 대역 레코드를 옮김)
PORT = {
    0x00: 0x02, 0x01: 0x13, 0x02: 0x30, 0x03: 0x7C, 0x05: 0x8B, 0x07: 0x37, 0x08: 0xB2, 0x0B: 0x1A, 0x0C: 0x35,
    0x0D: 0x15, 0x0E: 0x44, 0x11: 0x0D, 0x14: 0x05, 0x18: 0x61, 0x1A: 0x06, 0x1C: 0x87, 0x1D: 0x33, 0x1F: 0x5C,
    0x20: 0x60, 0x24: 0x3B, 0x25: 0x5F, 0x26: 0x27, 0x28: 0x48, 0x2A: 0x8F, 0x2C: 0xA6, 0x2E: 0x41, 0x33: 0x76,
    0x36: 0x77, 0x38: 0x56, 0x3E: 0xAE, 0x40: 0x34, 0x46: 0x9E, 0x48: 0x83, 0x4D: 0x6C, 0x5C: 0x0C,
}
# 사건 전투의 FC 몬스터 → DQ5 번호. 능력치·이름은 사건 모듈(dq4ch2tempe·dq4ch2endor)이 쓰고 dq4ch2slots 가 예약한다.
# 필드의 あばれこまいぬ(PORT 18)와 텐페 석상은 번호가 달라(예약 번호는 필드에 나오지 않음) 같은 그림을 두 자리에 둔다
EVENT = {0x12: 0x53, 0x18: 0xA3, 0xAF: 0xAA, 0xB0: 0xA4, 0xB1: 0x8E, 0xB2: 0x68, 0xBA: 0x72}
GRID = 8
RECORD, RECORD_SIZE = 0x238000, 25      # DQ5 몬스터 표(dq5tables monsters)


def nds_of(fc):
    return next(nds for f, nds, _ in dq4monart.TARGETS if f == fc)




def picture_image(fc):
    """색 번호 PNG(팔레트 모드, 0 투명, 1~15)와 색 목록(BGR555). 불투명 상자를 8픽셀 칸으로 늘려 가운데에 둔다."""
    src = Image.open(dq4monart.pose_path(nds_of(fc))).convert('RGBA')
    red, pal, _ = dq4monart.reduce(src, nds_of(fc))
    box = red.getbbox()
    red = red.crop(box)
    w, h = -(-red.width // GRID) * GRID, -(-red.height // GRID) * GRID
    colors = [c for _, c in pal]
    index = {c: i + 1 for i, c in enumerate(colors)}
    img = Image.new('P', (w, h), 0)
    ox, oy = (w - red.width) // 2, h - red.height        # 발이 칸 바닥에 닿게
    for y in range(red.height):
        for x in range(red.width):
            p = red.getpixel((x, y))
            if p[3]:
                img.putpixel((ox + x, oy + y), index[p[:3]])
    img.putpalette([0, 0, 0] + [v for c in colors for v in c] + [0, 0, 0] * (255 - len(colors)))
    return img, [(c[0] >> 3) | (c[1] >> 3) << 5 | (c[2] >> 3) << 10 for c in colors]


def doc(rom, out_dir, only=None):
    """dq5monster/1 문서를 out_dir/monsters.json 으로, 그림 PNG 를 그 옆에 쓴다. rom 은 원래 DQ5(dq5map.Rom).
    only 는 넣을 DQ5 번호(없으면 모두)."""
    import dq5mongfx
    out_dir.mkdir(parents=True, exist_ok=True)
    pictures, monsters = [], []
    for fc, m in [*PORT.items(), *EVENT.items()]:
        if only is not None and m not in only:
            continue
        g = dq5mongfx.monster(rom, m)[0]
        img, colors = picture_image(fc)
        name = f'{g:02X}.png'
        img.save(out_dir / name)
        w, h = img.width // GRID, img.height // GRID
        pictures.append({'picture': f'{g:02X}', 'image': name,
                         'header': {'float': False, 'raise': 0, 'hit_x': w // 2, 'hit_y': h // 2}})
        monsters.append({'monster': f'{m:02X}', 'colors': colors})
        # 같은 그림을 쓰는 다른 DQ5 몬스터는 이 롬에 나오지 않지만, 색 수가 그림보다 적으면 dq5monwrite 가 거부해 같은 색을 준다
        for other in range(dq5mongfx.COUNT):
            if other not in PORT.values() and other not in EVENT.values() and dq5mongfx.monster(rom, other)[0] == g:
                monsters.append({'monster': f'{other:02X}', 'colors': colors})
    d = {'format': 'dq5monster/1', 'pictures': pictures, 'monsters': monsters}
    (out_dir / 'monsters.json').write_text(json.dumps(d, indent=1))
    return out_dir / 'monsters.json'


def record_writes(original, dq5_of):
    """사건 몬스터가 아닌 것의 새 번호에 지금 대역의 레코드 25바이트를 옮기는 dq5patch/1 쓰기. dq5_of 는 FC → 대역 DQ5
    번호(dq4fieldencounter.PLACEHOLDERS)."""
    from dq5map import lorom
    out = []
    for fc, m in PORT.items():
        if dq5_of[fc] == m:
            continue
        src = original[lorom(RECORD + dq5_of[fc] * RECORD_SIZE):][:RECORD_SIZE]
        at = RECORD + m * RECORD_SIZE
        out.append({'at': f'{at >> 16:02X}:{at & 0xFFFF:04X}', 'hex': src.hex(' '),
                    'orig': original[lorom(at):lorom(at) + RECORD_SIZE].hex(' '),
                    'note': f'FC {fc:02X} 몬스터 레코드(대역 {dq5_of[fc]:02X} 의 것)'})
    return out


# dq5monwrite 의 옮긴 그림(24비트 머리 포인터 표 뒤, 뱅크를 넘으면 다음 뱅크로)과 늘린 몬스터 레코드 자리. 빌드 롬에서
# 통째로 0 인 뱅크 48~4B 가운데. 빌드가 쓰기 전에 0 인지 본다(dq4chapter1.apply_writes)
PICTURES_AT, RECORDS_AT = '48:8000', '4B:8000'


def reachable(zone_report, event_groups):
    """dq5monlimits 조합 「나온 곳」 → 이 롬에서 나올 수 있는지. DQ5 구역·이벤트 무리 가운데 FC 조우가 쓰는 것(그룹 빌드의
    zone-report.json 의 zone, 배의 SEA_AREAS)과 이 해킹의 사건 무리만. 나머지 DQ5 구역·무리는 닿지 않는데, 새 번호의 원래
    DQ5 몬스터나 그림을 같이 쓰는 DQ5 몬스터가 거기 남아 있어 세면 덜 놓인다고 거부된다."""
    import dq4fieldencounter
    areas = {v['zone'] for v in json.loads(zone_report.read_text()).values()} | set(dq4fieldencounter.SEA_AREAS)
    areas = {f'구역 {a:02X} ' for a in areas}
    groups = {f'이벤트 무리 {g:02X}' for g in event_groups}
    return lambda where: where in groups or any(where.startswith(a) for a in areas)


def build(dq5, rom, work, zone_report, event_groups):
    """빌드 중인 롬(무리·구역·사건 무리가 들어간 것)으로 그림·색 패치 목록을 만들어 경로를 돌려준다. 무리 조합 검사
    (dq5monlimits)는 이 롬의 무리 가운데 나올 수 있는 것(reachable)만 센다."""
    import dq5monlimits
    import dq5monwrite
    from dq5map import Rom
    work.mkdir(parents=True, exist_ok=True)
    keep = reachable(zone_report, event_groups)
    counted = dq5monlimits.compositions

    def scoped(r, areas=None):
        found, skipped = counted(r, areas)
        return {k: w for k, w in found.items() if keep(w)}, skipped
    # 이 롬의 조우에 아직 나오지 않는 몬스터(뒷 장 구역에만 나옴)는 한도를 셀 수 없어 그 장을 옮길 때 넣는다
    appear = {m for groups in scoped(Rom(bytes(rom)))[0] for m, _, _ in groups}
    source = doc(Rom(dq5.read_bytes()), work / 'pictures', appear)
    later = sorted(m for m in [*PORT.values(), *EVENT.values()] if m not in appear)
    if later:
        print('dq4monport: 조우에 아직 없어 그림을 넣지 않은 번호 ' + ' '.join(f'{m:02X}' for m in later), file=sys.stderr)
    dq5monlimits.compositions = scoped
    try:
        manifest = dq5monwrite.patch(Rom(bytes(rom)), json.loads(source.read_text()), source.parent,
                                     at=dq5monwrite.address(PICTURES_AT),
                                     records_at=dq5monwrite.address(RECORDS_AT))
    finally:
        dq5monlimits.compositions = counted
    out = work / 'monsters.dq5patch.json'
    out.write_text(json.dumps(manifest, ensure_ascii=False))
    return out


def records_patch(original, path):
    """record_writes 를 dq5patch/1 파일로."""
    import dq4fieldencounter
    path.write_text(json.dumps({'format': 'dq5patch/1', 'name': 'dq4-monster-records',
                                'writes': record_writes(original, dq4fieldencounter.PLACEHOLDERS)}, ensure_ascii=False))
    return path


def korean_names():
    """사건 몬스터가 아닌 번호 → NDS 한글 이름(adopt.tsv 몬스터 표). 사건 몬스터의 이름은 그 모듈의 MONSTER_NAMES."""
    names = dq4monart.korean_names()
    return {m: names[nds_of(fc)][1] for fc, m in PORT.items()}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    s = sub.add_parser('doc')
    s.add_argument('rom', type=Path)
    s.add_argument('-o', '--out', type=Path, required=True)
    a = ap.parse_args(argv)
    from dq5map import Rom
    print(doc(Rom(a.rom.read_bytes()), a.out))


if __name__ == '__main__':
    sys.exit(main())
