"""전투 무리 조합마다 몬스터 그림의 조각 합(22:91DC, 100 미만)·화면 줄마다 타일 합(22:A119, 28 미만) 한도와
그림을 푼 타일이 차지하는 16x16 자리(22:91F7) 합을 센다.

나올 수 있는 무리 조합을 모두 늘어놓는다. 구역 레코드(23:96F3, 옮겼으면 dq5progresswrite.table_bases 가 읽는 자리)의 칸 5~9 한 종 무리·칸 0~4 여러 종 무리(종 수 2~4,
나머지 종은 칸 0~4 에서 다시 뽑음)·칸 10 고정 무리(23:B04B)를 마릿수 범위의 값마다, 이벤트 무리(23:D757) 64개를 그대로.
첫 무리가 E7·EA 인 조합은 22:89E5 가 무리를 더하므로 세지 않고, 6A 는 마릿수가 짝수면 하나 뺀다.
배치는 dq5mongfx.place(줄 폭 28·조각 합·줄마다 타일 합으로 마릿수를 자름)로 센다.
무리·구역은 입력 롬에서 읽는다. 같은 빌드에서 dq5encounterwrite.py·dq5progresswrite.py 로 무리·구역을 바꾸면 그 패치를
먼저 넣은 롬을 주고, 구역 수를 늘렸으면 --progress(그 패치 목록) 또는 --areas 로 준다.

  report  그림마다, 다른 그림을 그대로 둘 때 어느 조합에서도 원래보다 덜 놓이지 않는 여유.
          pieces = 조각을 몇 개 더 늘릴 수 있는지, bands = 8픽셀 줄마다 타일을 몇 개 더 늘릴 수 있는지,
          slots = 16x16 자리를 몇 개 더 늘릴 수 있는지
  losses  바꾼 그림의 조각 수·줄마다 타일 수로 다시 세어, 원래보다 덜 놓이는 무리가 있는 조합(dq5monwrite.py 가 씀)

  python sfc/dq5/tools/dq5monlimits.py rom/dq5.sfc report [-o work/monlimits.json] [--progress progress.dq5patch.json]
"""
import argparse
import itertools
import json
import sys
from pathlib import Path

import dq5mongfx as M
from dq5encounter import AREA_COUNT, AREAS, EVENT_COUNT, EVENT_GROUPS, EVENT_SIZE, area, count_range, fixed_group
from dq5map import Rom
from dq5monster import RECORDS as MONSTER_RECORDS, SIZE as MONSTER_SIZE

PIECE_LIMIT, BAND_LIMIT = 100, 0x1C
TOP = 0x38                      # 줄마다 타일 합 표 7E:2F00 의 첫 줄(22:A177 의 (y >> 3) - 7)
# 줄 목록 사슬 7E:5B20 은 64칸이다. 그림의 마지막 줄이 64번째 칸에 들면 다음 빈 칸 찾기(22:ADA1)가 FF 를 못 찾아
# 멈추므로, 한 번에 풀려 있는 그림의 세로 칸 합은 63 까지다. 그중 16칸은 재지 않은 싸우는 도중의 풀기
# (パルプンテ 22:D45D, モシャス 22:D3B9, がったい 22:D2FE)가 그림 하나(세로 16칸까지)만 더 푼다고 보고 남긴 몫이다.
# 이 가정은 증명하지 않았다: モシャス 는 몬스터마다 걸려 여럿이 그림을 풀 수 있고, がったい·パルプンテ 의 푸는 차례는 재지 않았다.
ROW_LIMIT = 0x40 - 1 - 16
FIRST_SUMMON, SUMMONED = 0xAE, (0x1E, 0x27, 0x1B, 0x61, 0x67, 0x8C, 0xB2, 0xCF)   # 행동 AE~B5 가 부르는 몬스터(20:D9D6)
SKIP_FIRST = (0xE7, 0xEA)
# 22:89E5·22:8A57·22:8A85 가 무리를 더하거나 합치는 ミルドラース 와 그 둘째 무리. 이 셈으로는 배치를 셀 수 없다.
UNCOUNTED = range(0xE7, 0xEC)
EVEN_FIRST = 0x6A


def summoned(rom, m):
    """몬스터 m 의 행동 여섯(23:8000 레코드 +11~+16) 가운데 부르기 AE~B5 가 부르는 몬스터."""
    acts = [rom.u8(MONSTER_RECORDS + m * MONSTER_SIZE + 0x11 + i) for i in range(6)]
    return [SUMMONED[a - FIRST_SUMMON] for a in acts if FIRST_SUMMON <= a < FIRST_SUMMON + len(SUMMONED)]


def counts(span):
    return range(span[0], span[1] + 1)


def area_base(rom):
    """구역 표 자리. dq5progresswrite.py 가 옮겼으면 읽는 명령의 피연산자를 따른다."""
    from dq5progresswrite import table_bases
    return table_bases(rom)['area']


def area_count(progress=None, areas=None):
    """구역 수. --areas 를 주면 그 값, 구역 표를 옮긴 dq5progresswrite.py 패치 목록이면 그 표의 항목 수.
    둘 다 없거나 패치 목록에 구역 표를 옮긴 기록이 없으면 None 이고, 그때의 기본 85 는 compositions 가
    구역 표가 원래 자리일 때만 정한다."""
    if areas is not None:
        return areas
    if progress is not None:
        from dq5encounterwrite import areas_in
        doc = json.loads(Path(progress).read_text(encoding='utf-8'))
        if any(w.get('note') == 'area table relocated' for w in doc.get('writes', [])):
            return areas_in(doc)
    return None


def compositions(rom, areas=None):
    """{((몬스터, 마릿수, 무리 값), …): 처음 나온 곳} 과 세지 않은 조합 수. areas 는 구역 수(없으면 원래 85개)."""
    found, skipped = {}, 0
    base = area_base(rom)
    if areas is None:
        # 구역 수는 롬에 없어, 옮긴 표에서 원래 85개만 세면 늘린 구역이 소리 없이 빠진다.
        if base != AREAS:
            raise ValueError('구역 표를 옮긴 롬은 --progress 나 --areas 를 주어야 함'
                             '(--progress 는 구역 표를 옮긴 기록이 있는 dq5progresswrite.py 패치 목록)')
        areas = AREA_COUNT

    def add(groups, where):
        nonlocal skipped
        groups = [g for g in groups if g[1] > 0]
        if not groups:
            return
        if groups[0][0] in SKIP_FIRST:
            skipped += 1
            return
        if groups[0][0] == EVEN_FIRST and groups[0][1] % 2 == 0:
            groups[0] = (groups[0][0], groups[0][1] - 1, groups[0][2])
        found.setdefault(tuple(groups), where)

    for n in range(areas):
        ar = area(rom, n, base)
        mixed = [s for s in range(5) if ar['weights'][s]]
        for s in range(11):
            if not ar['weights'][s]:
                continue
            where = f'구역 {n:02X} 칸 {s}'
            if s < 5:
                for species, weight in zip((2, 3, 4), ar['species_weights']):
                    if not weight:
                        continue
                    for rest in itertools.product(mixed, repeat=species - 1):
                        slots = (s, *rest)
                        spans = [counts(count_range(rom, ar['count_codes'][x] + 7)) for x in slots]
                        for cs in itertools.product(*spans):
                            add([(ar['monsters'][x], c, 0) for x, c in zip(slots, cs)], where)
            elif s < 10:
                for c in counts(count_range(rom, ar['count_codes'][s])):
                    add([(ar['monsters'][s], c, 0)], where)
            else:
                rows = fixed_group(rom, ar['fixed_group'])
                for cs in itertools.product(*(counts(span) for _, span, _ in rows)):
                    add([(m, c, flag) for (m, _, flag), c in zip(rows, cs)], where)
    for g in range(EVENT_COUNT):
        raw = [rom.u8(EVENT_GROUPS + g * EVENT_SIZE + i) for i in range(EVENT_SIZE)]
        add([(raw[1 + i], raw[5 + i], raw[9 + i]) for i in range(4) if raw[1 + i] != 0xFF], f'이벤트 무리 {g:02X}')
    return found, skipped


class Pictures:
    """그림마다 머리·조각 수·줄마다 타일 수·16x16 자리 수. pictures = {그림: (조각 수, 줄마다 타일 수[, 자리 수[, 머리]])}
    로 바꾼 그림을, monsters = {몬스터: 그림} 으로 바꾼 그림 번호를 덮는다. 머리는 dq5mongfx.header 꼴(크기·띄움·들어올림)."""

    def __init__(self, rom, pictures=None, monsters=None):
        self.rom, self.pictures, self.monsters, self.cache = rom, pictures or {}, monsters or {}, {}

    def picture(self, m):
        return self.monsters.get(m, M.monster(self.rom, m)[0])

    def stats(self, g):
        if g not in self.cache:
            d = M.decode(self.rom, g)
            size, bands, *rest = self.pictures.get(g, (len(d['pieces']), M.band_counts(d)))
            self.cache[g] = (rest[1] if len(rest) > 1 else M.header(self.rom, g), size, list(bands),
                             rest[0] if rest else M.slot_count(d))
        return self.cache[g][:3]

    def slots(self, g):
        self.stats(g)
        return self.cache[g][3]

    def place(self, groups):
        return M.place([(m, n, flag, *self.stats(self.picture(m))) for m, n, flag in groups])

    def head(self, g):
        return M.head(self.rom, g)

    def listed(self, groups):
        """조합의 그림마다 한 번씩 푼 조각 수의 합. 풀 때 조각마다 7E:5800 에 4바이트씩 적는다(22:9DB0)."""
        return sum(self.stats(g)[1] for g in {self.picture(m) for m, _, _ in groups})

    def loads(self, groups, kept=None):
        """그림을 푸는 차례대로 [(그림, 첫 자리, 자리 수)]. 조각 한도까지 센 몬스터가 있는 무리만 풀고(22:9088 의 검사를
        모두 지난 무리), 이미 푼 그림 번호는 다시 풀지 않는다(7E:0D3D). 새 전투는 자리 0 부터 차례로 준다(22:ACFE)."""
        out, cursor = [], 0
        for m, _, _, _, _, k in kept if kept is not None else self.place(groups)[0]:
            g = self.picture(m)
            if k and all(g != x for x, _, _ in out):
                out.append((g, cursor, self.slots(g)))
                cursor += self.slots(g)
        return out

    def band_rows(self, groups):
        """조합에서 푼 그림의 세로 칸 수 합. 풀 때 8픽셀 줄마다 줄 목록 사슬 7E:5B20(64칸)의 한 칸을 쓴다(22:AD73).
        싸우는 도중 부르기로 새 종이 오면 그 그림도 푼다. 부른 몬스터가 다시 부를 수 있고(27 → 1E), 무리가 넷이면
        22:D322 가 몬스터 없는 무리를 지우고 실패하지만 그 그림은 풀어 두며(95A1 을 부르지 않음), 다음 부르기는 새 그림을
        먼저 풀고(22:D388) 나서 푼 그림을 정리한다(22:D3A1, 모두 코드 읽기). 그래서 빈 무리 칸 수로 자르지 않고
        부르기를 거듭해 닿는 그림을 모두 더한다."""
        loaded = {g for g, _, _ in self.loads(groups)}
        seen = {m for m, _, _ in groups if self.picture(m) in loaded}
        todo = list(seen)
        while todo:
            for s in summoned(self.rom, todo.pop()):
                if s not in seen:
                    seen.add(s)
                    todo.append(s)
        return sum(self.stats(g)[0]['h'] for g in loaded | {self.picture(m) for m in seen})

def losses(rom, pictures=None, monsters=None, found=None, areas=None):
    """바꾼 그림·그림 번호로 다시 세어 걸리는 조합 [(조합, 원래 수, 바뀐 수, 나온 곳, 까닭)].
    까닭은 원래보다 덜 놓이는 무리가 있음, 조합의 그림 조각 합(7E:5800 목록)·16x16 자리 합이 원래 롬의 모든 조합 중
    가장 큰 값을 넘음, 그림 세로 칸 합(줄 목록 7E:5B20, 부르기를 거듭해 올 그림 포함)이 ROW_LIMIT 를 넘음, 바꾼 그림의
    상자 위가 y $38 보다 위임이다.
    자리는 연출의 OBJ 그림(22:BB3D)도 같은 128개에서 받으므로, 원래 게임이 이미 쓰는 합까지만 받는다. 줄마다 타일 합은
    7E:2F00 + (y >> 3) - 7 에 세는데(22:A177) X 가 8비트라, y 가 $38 보다 작으면 X 가 $F9~$FF 로 돌아
    7E:2FF9~ 를 고친다(코드 읽기)."""
    found = found if found is not None else compositions(rom, areas)[0]
    before, after = Pictures(rom), Pictures(rom, pictures, monsters)
    most = max((before.listed(groups) for groups in found), default=0)
    most_slots = max((sum(s for _, _, s in before.loads(groups)) for groups in found), default=0)
    changed = set(monsters or ()) | {m for m in range(M.COUNT) if before.picture(m) in (pictures or {})}
    out = []
    # 바꾼 뒤 기준으로, 늘린 그림을 쓰는 몬스터가 센 조합에 하나도 없거나 ミルドラース(E7~EB)면 셀 수 없다.
    appear = {m for groups in found for m, _, _ in groups}
    for g in sorted(pictures or ()):
        users = {m for m in range(M.COUNT) if after.picture(m) == g}
        if users & set(UNCOUNTED):
            out.append(((), [], [], f'그림 {g:02X}', '무리를 더하는 몬스터(E7~EB)가 써서 한도를 정할 수 없음'))
        elif not users & appear:
            out.append(((), [], [], f'그림 {g:02X}', '세는 조합에 나오지 않아 한도를 정할 수 없음'))
    for groups, where in found.items():
        if not changed & {m for m, _, _ in groups}:
            continue
        old = [k[1] for k in before.place(groups)[0]]
        kept = after.place(groups)[0]
        new = [k[1] for k in kept]
        high = [(m, y) for m, _, _, _, y, k in kept if k and m in changed and y < TOP]
        if high:
            out.append((groups, old, new, where, f'몬스터 {high[0][0]:02X} 상자 위 y ${high[0][1]:02X} < ${TOP:02X}'))
        elif any(b < a for a, b in zip(old, new)):
            out.append((groups, old, new, where, '덜 놓임'))
        elif after.listed(groups) > most:
            out.append((groups, old, new, where, f'조각 목록 {after.listed(groups)}개 > {most}개'))
        elif sum(s for _, _, s in after.loads(groups)) > most_slots:
            out.append((groups, old, new, where, f'16x16 자리 {sum(s for _, _, s in after.loads(groups))}개 > {most_slots}개'))
        elif after.band_rows(groups) > ROW_LIMIT:
            out.append((groups, old, new, where, f'그림 세로 칸 {after.band_rows(groups)}개 > {ROW_LIMIT}개'))
    return out


def budgets(rom, found=None):
    """그림마다 {pieces: 더 늘릴 수 있는 조각 수, bands: 8픽셀 줄마다 더 늘릴 수 있는 타일 수, slots: 더 늘릴 수 있는
    16x16 자리 수, compositions: 나온 조합 수}.
    한 그림만 바꿀 때 이 안이면 losses() 에 걸리는 조합이 없다(마지막 합 + 늘린 양이 한도 밑이면 도중의 합도 밑이고,
    조각 목록·자리 합도 원래 가장 큰 값 안). 같은 머리를 쓰는 그림 번호(00·11·29 등)는 함께 바뀌므로 머리마다 합쳐 세고,
    그 번호들에 같은 값을 준다."""
    found = found if found is not None else compositions(rom)[0]
    pics = Pictures(rom)
    most = max((pics.listed(groups) for groups in found), default=0)
    most_slots = max((sum(s for _, _, s in pics.loads(groups)) for groups in found), default=0)
    table, members = {}, {}
    for groups in found:
        kept, pieces, bands = pics.place(groups)
        spare = most - pics.listed(groups)
        spare_slots = most_slots - sum(s for _, _, s in pics.loads(groups, kept))
        by_head = {}
        for m, j, hd, row, y, k in kept:
            g = pics.picture(m)
            key = pics.head(g)
            members.setdefault(key, set()).add(g)
            entry = by_head.setdefault(key, [0, 0, [], set(), g])
            entry[0] += k
            entry[1] += j
            entry[3].add(g)
            if j:
                entry[2].append((y >> 3) - 7)
        for key, (counted, placed, starts, numbers, g) in by_head.items():
            row = table.setdefault(key, {'pieces': None, 'bands': [None] * pics.stats(g)[0]['h'], 'slots': None,
                                         'compositions': 0})
            row['compositions'] += 1
            # 조각 목록에는 그림 번호마다 한 번씩 들어가므로, 같은 머리 번호가 둘이면 늘린 양도 두 번 든다.
            row['pieces'] = least(row['pieces'], spare // len(numbers))
            row['slots'] = least(row['slots'], spare_slots // len(numbers))
            if counted:
                row['pieces'] = least(row['pieces'], (PIECE_LIMIT - 1 - pieces) // counted)
            for b in starts:
                for r in range(len(row['bands'])):
                    row['bands'][r] = least(row['bands'][r], (BAND_LIMIT - 1 - bands[b + r]) // placed)
    return {g: table[key] for key, gs in members.items() for g in gs}


def least(a, b):
    return b if a is None else min(a, b)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('rom', type=Path)
    sub = ap.add_subparsers(dest='command', required=True)
    report = sub.add_parser('report')
    report.add_argument('-o', '--out', type=Path)
    report.add_argument('--progress', type=Path, help='구역 수를 읽을 dq5progresswrite.py 패치 목록(구역 표를 옮겼을 때)')
    report.add_argument('--areas', type=int, help='구역 수(기본 85)')
    args = ap.parse_args()
    try:
        rom = Rom(args.rom.read_bytes())
        found, skipped = compositions(rom, area_count(args.progress, args.areas))
        table = budgets(rom, found)
        pics = Pictures(rom)
        rows = []
        for g in sorted(table):
            hd, size, bands = pics.stats(g)
            rows.append({'picture': f'{g:02X}', 'w': hd['w'], 'h': hd['h'], 'pieces': size, 'bands': bands,
                         'slots': pics.slots(g), 'extra_pieces': table[g]['pieces'], 'extra_bands': table[g]['bands'],
                         'extra_slots': table[g]['slots'],
                         'compositions': table[g]['compositions'],
                         'monsters': [f'{m:02X}' for m in range(M.COUNT) if pics.picture(m) == g]})
        body = {'compositions': len(found), 'skipped': skipped, 'pictures': rows}
        if args.out:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(json.dumps(body, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
        print(f'무리 조합 {len(found)}개(E7·EA 첫 무리 {skipped}개는 세지 않음), 나오는 그림 {len(rows)}개')
        for row in rows:
            print(f"그림 {row['picture']}: 조각 {row['pieces']} 여유 {row['extra_pieces']}, "
                  f"줄마다 타일 {row['bands']} 여유 {row['extra_bands']}, 자리 {row['slots']} 여유 {row['extra_slots']}, "
                  f"조합 {row['compositions']}")
        return 0
    except (ValueError, OSError) as error:
        print(f'오류: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
