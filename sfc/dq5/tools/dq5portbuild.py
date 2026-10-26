"""DQ4 포팅 통합 빌드. 고정 패치(DQ4 타이틀·서곡·메뉴 롬)를 예약 영역으로 두고, DQ5 쓰기 도구 작업(맵·인물·필드·
대사·이벤트)의 --at 을 남은 빈 자리에서 작업마다 정한 뱅크 창 안으로 골라 돌린 뒤 dq5build 로 한 롬과 IPS 를 낸다.
형식은 sfc/dq5/docs/dq5-build-format.md 의 「통합 포팅 빌드」.

  plan   배치만 정하고 보고(롬·패치 목록을 쓰지 않음)
  build  배치 → 쓰기 도구 실행 → 겹침·orig 검사 → 롬·IPS(원래 롬에 다시 붙여 같은지 확인) → 정적 검사

  python sfc/dq5/tools/dq5portbuild.py rom/dq5.sfc build work/port/port.json --out work/port/build

작업이 들어갈 자리가 없으면 창마다 필요한 바이트와 빈 바이트를 보이고 종료값 1 로 끝난다.
디코더가 닿지 못하는 뱅크로 옮기지 않는다. 결과물은 --out 아래(work/)에만 쓴다.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, os.path.dirname(__file__))
from dq5build import HEADER_RANGE, ORIGINAL_SIZE, REACHABLE, PatchError, cpu  # noqa: E402
from dq5build import load as load_manifest  # noqa: E402
from dq5hangul import DECODER, DECODER_END, expand  # noqa: E402
from dq5map import lorom  # noqa: E402
from kr_patch import ips  # noqa: E402

FORMAT = 'dq5portbuild/1'
HERE = Path(__file__).resolve().parent
BANK = 0x8000

# 작업이 놓일 수 있는 CPU 뱅크 창. 근거는 형식 문서의 각 쓰기 도구 절.
#   low  : 맵·필드·인물 목록은 자료 뱅크를 DB 에 넣은 채 낮은 WRAM·I/O 를 절대 주소로 쓰므로 거울이 있는 30~3F 만.
#          보행 대사의 색인 창 OR 20 도 이 창이다.
#   high : 이벤트 스크립트(60:8000 실측)와 보행 대사 색인 창 OR 60(디코더 사본이 PHK·PLB 로 자기 뱅크만 읽음).
#          7E·7F 는 WRAM 이라 롬 뱅크로 쓰지 않는다.
WINDOWS = {'low': (0x30, 0x3F), 'high': (0x60, 0x7D)}
KINDS = {'map': ['low'], 'field': ['low'], 'npc': ['low'], 'text': ['low'], 'text-over': ['high', 'low'],
         'event': ['high']}


class AllocationError(Exception):
    pass


# ---- 빈 자리와 배치(롬 없이 시험하는 부분) ----

def window_range(name):
    lo, hi = WINDOWS[name]
    return lo * BANK, (hi + 1) * BANK


class Space:
    """파일 위치 [시작, 끝) 의 빈 구간 목록."""

    def __init__(self, ranges=()):
        self.ranges = []
        for s, e in sorted(ranges):
            if s >= e:
                continue
            if self.ranges and s <= self.ranges[-1][1]:
                self.ranges[-1][1] = max(self.ranges[-1][1], e)
            else:
                self.ranges.append([s, e])

    def contains(self, s, e):
        return any(a <= s and e <= b for a, b in self.ranges)

    def take(self, s, e):
        out = []
        for a, b in self.ranges:
            if b <= s or e <= a:
                out.append([a, b])
                continue
            if a < s:
                out.append([a, s])
            if e < b:
                out.append([e, b])
        self.ranges = out

    def clip(self, s, e):
        return [(max(a, s), min(b, e)) for a, b in self.ranges if a < e and s < b]

    def total(self, s, e):
        return sum(b - a for a, b in self.clip(s, e))

    def largest(self, s, e):
        return max((b - a for a, b in self.clip(s, e)), default=0)


def mask_ranges(mask, value=1):
    """바이트마다의 표시 배열에서 value 인 연속 구간."""
    out, i, n = [], 0, len(mask)
    while i < n:
        if mask[i] != value:
            i += 1
            continue
        j = i
        while j < n and mask[j] == value:
            j += 1
        out.append((i, j))
        i = j
    return out


class Piece:
    """한 --at 으로 놓이는 자료 덩어리.
    stream : sizes 를 이어 놓음(뱅크를 넘어도 됨). head 바이트는 시작 뱅크 안이어야 함.
    chunks : sizes 를 차례로 놓되 덩어리 하나가 뱅크를 넘으면 다음 뱅크 첫머리로(쓰기 도구의 규칙과 같음).
    apart  : 같은 작업의 다른 조각 이름. 그 조각과 다른 뱅크에 놓는다."""

    def __init__(self, job, name, mode, sizes, windows, head=0, apart=None, pin=None):
        self.job, self.name, self.mode, self.sizes = job, name, mode, list(sizes)
        self.windows, self.head, self.apart, self.pin = list(windows), head, apart, pin

    @property
    def size(self):
        return sum(self.sizes)

    def layout(self, at, window):
        """at(파일 위치)에 놓았을 때 차지하는 구간들. 규칙을 어기면 None."""
        lo, hi = window_range(window)
        if not lo <= at < hi:
            return None
        if self.mode == 'stream':
            end = at + self.size
            if end > hi or at % BANK + self.head > BANK:
                return None
            return [(at, end)]
        out = []
        for size in self.sizes:
            if not 0 < size <= BANK:
                return None
            if at % BANK + size > BANK:
                at = (at // BANK + 1) * BANK
            if at + size > hi:
                return None
            out.append((at, at + size))
            at += size
        return out


def candidates(space, window):
    lo, hi = window_range(window)
    for s, e in space.clip(lo, hi):
        yield s
        b = (s // BANK + 1) * BANK
        while b < e:
            yield b
            b += BANK


def fit(piece, space, banned=()):
    for window in piece.windows:
        starts = [piece.pin] if piece.pin is not None else candidates(space, window)
        for at in starts:
            ranges = piece.layout(at, window)
            if ranges and all(space.contains(s, e) for s, e in ranges) and \
                    not any(b in banned for s, e in ranges for b in range(s // BANK, (e - 1) // BANK + 1)):
                # 뱅크를 건너뛴 첫 덩어리 자리를 --at 으로 준다(건너뛰지 않는 쓰기 도구도 같은 결과).
                return ranges[0][0], window, ranges
    return None


def allocate(pieces, space):
    """주소를 정한 조각, 창이 적은 조각, 큰 조각 순으로 첫 맞는 자리에 놓는다. 실패하면 AllocationError."""
    order = sorted(pieces, key=lambda p: (p.pin is None, len(p.windows), -p.size))
    placed = {}
    for piece in order:
        banned = set()
        if piece.apart and piece.apart in placed:
            banned = {b for s, e in placed[piece.apart]['ranges'] for b in range(s // BANK, (e - 1) // BANK + 1)}
        got = fit(piece, space, banned)
        if got is None:
            raise AllocationError(failure(piece, pieces, placed, space))
        at, window, ranges = got
        for s, e in ranges:
            space.take(s, e)
        placed[piece.name] = {'at': at, 'window': window, 'ranges': ranges}
    return placed


def summary(pieces, space, placed=None):
    """창마다 이 창에만 놓일 수 있는 조각의 합, 여러 창에 놓일 수 있는 조각의 합, 남은 빈 바이트와 가장 긴 연속."""
    out = {}
    for window in WINDOWS:
        lo, hi = window_range(window)
        only = [p for p in pieces if p.windows == [window]]
        either = [p for p in pieces if window in p.windows and len(p.windows) > 1]
        out[window] = {'banks': '{:02X}~{:02X}'.format(*WINDOWS[window]),
                       'needed_only_here': sum(p.size for p in only),
                       'needed_shared': sum(p.size for p in either),
                       'free': space.total(lo, hi), 'largest_free': space.largest(lo, hi)}
        if placed is not None:
            out[window]['placed'] = sum(e - s for v in placed.values() if v['window'] == window for s, e in v['ranges'])
    return out


def failure(piece, pieces, placed, space):
    label = piece.name if piece.name.startswith(piece.job) else f'{piece.job}/{piece.name}'
    rows = [f'{label} {piece.size}바이트({piece.mode}, 창 {"·".join(piece.windows)})를 놓을 자리가 없음.']
    left = [p for p in pieces if p.name not in placed]
    stats = summary(left, space)
    for window in piece.windows:
        s = stats[window]
        rows.append(f'  창 {window}({s["banks"]}): 아직 못 놓은 작업 중 이 창만 쓰는 것 {s["needed_only_here"]}바이트'
                    f' + 다른 창도 쓰는 것 {s["needed_shared"]}바이트, 빈 자리 {s["free"]}바이트'
                    f'(가장 긴 연속 {s["largest_free"]}바이트)')
    if piece.mode == 'chunks':
        rows.append(f'  덩어리 {piece.sizes} 는 각각 한 뱅크 안이어야 함')
    if piece.head:
        rows.append(f'  머리 {piece.head}바이트는 시작 뱅크 안이어야 함')
    return '\n'.join(rows)


# ---- 고정 패치 ----

def parse_cpu(value):
    bank, low = (int(v, 16) for v in value.split(':'))
    if not 0x8000 <= low <= 0xFFFF or bank in (0x7E, 0x7F) or bank > 0x7D:
        raise ValueError(f'{value}: 뱅크 00~7D 의 BB:AAAA 여야 함')
    return bank * BANK + low - 0x8000


def title_keep(layout_dir):
    """dq4titlelayerpatch 가 선언한 타이틀 자리: 코드 30:8000~8FFF 와 에셋 PLACEMENTS(파일 크기만큼)."""
    sys.path.insert(0, str(HERE.parents[1] / 'dq4' / 'tools'))
    from dq4titlelayerpatch import PLACEMENTS
    keep = [(0x180000, 0x181000)]
    for name, offset in PLACEMENTS.items():
        keep.append((offset, offset + (Path(layout_dir) / name).stat().st_size))
    return keep


# 30~3F 에서 타이틀이 선언하지 않은 자리에 다른 단계(서곡·이름 입력)가 쓴 코드는 거울과 다른 바이트로만 보인다.
# 끝 바이트가 우연히 거울과 같을 수 있어, 다른 바이트 묶음을 이만큼 앞뒤로 넓혀 예약한다.
MIRROR_GAP = 64
MIRROR_PAD = 64
MIRROR = (ORIGINAL_SIZE, 0x200000)


def fixed_mask(original, rom, keep=None):
    """고정 롬을 만들려면 써야 하는 바이트 표시와 30~3F 확장 거울에서 예약할 구간.
    keep(타이틀이 선언한 자리)이 없으면 거울 구간은 None. 있으면 keep 과, keep 밖에서 거울(원래 롬 20~2F 복사본)과
    다른 바이트 묶음을 MIRROR_PAD 만큼 넓힌 것을 예약하고, 나머지 거울 바이트는 쓰기에서 뺀다.
    돌려주는 값은 (표시, 거울 예약 구간 또는 None, 뺀 바이트 수)."""
    mb = len(rom) // 0x100000
    if mb not in REACHABLE or len(rom) != mb * 0x100000:
        raise ValueError(f'고정 롬 크기 {len(rom):#x} 가 2·3·4MB 가 아님')
    base = bytearray(expand(original, mb))
    base[HEADER_RANGE[0]:HEADER_RANGE[1]] = rom[HEADER_RANGE[0]:HEADER_RANGE[1]]
    mask = bytearray(a != b for a, b in zip(base, rom))
    # 모두 0 인 늘린 뱅크는 표지만 다르다. 쓰지 않은 뱅크라 차지하지 않는다.
    for b in range(ORIGINAL_SIZE // BANK, len(rom) // BANK):
        s, e = b * BANK, (b + 1) * BANK
        if not any(rom[s:e]):
            mask[s:e] = bytes(BANK)
    if keep is None:
        return mask, None, 0
    lo, hi = MIRROR
    clusters = []
    held = Space(keep)
    for i in range(lo, hi):
        if rom[i] != original[i - 0x80000] and not held.contains(i, i + 1):
            if clusters and i - clusters[-1][1] <= MIRROR_GAP:
                clusters[-1][1] = i + 1
            else:
                clusters.append([i, i + 1])
    hold = Space(list(keep) + [(max(lo, s - MIRROR_PAD), min(hi, e + MIRROR_PAD)) for s, e in clusters])
    freed = 0
    keep_mask = bytearray(hi - lo)
    for s, e in hold.ranges:
        keep_mask[s - lo:e - lo] = b'\1' * (e - s)
    for i in range(lo, hi):
        if not keep_mask[i - lo] and mask[i]:
            freed += 1
            mask[i] = 0
    return mask, [tuple(r) for r in hold.ranges], freed


def occupied(mask, hold, supersede=()):
    """고정 패치가 차지하는 늘린 자리. 거울 구간에 hold 가 있으면 그것을, 나머지는 쓴 바이트가 하나라도 있는
    뱅크 전체를 잡는다(자료 안의 0 이 롬을 늘린 0 과 구별되지 않아, 뱅크 단위로 잡아야 그 사이에 끼어들지 않는다).
    supersede(다른 작업이 대신하는 구간)는 뺀다."""
    out = list(hold or [])
    for b in range(ORIGINAL_SIZE // BANK, len(mask) // BANK):
        s, e = b * BANK, (b + 1) * BANK
        if hold is not None and MIRROR[0] <= s < MIRROR[1]:
            continue
        if any(mask[s:e]):
            out.append((s, e))
    space = Space(out)
    for s, e in supersede:
        space.take(s, e)
    return [tuple(r) for r in space.ranges]


def manifest_from_mask(name, original, rom, mask, mb, out_dir):
    """표시한 바이트를 그대로 쓰는 dq5patch/1. 원래 롬 자리에는 orig 를 채운다."""
    writes = []
    for k, (s, e) in enumerate(split_banks(mask_ranges(mask))):
        w = {'at': f'0x{s:X}'} if s >= ORIGINAL_SIZE else {'at': cpu(s), 'orig': original[s:e].hex(' ')}
        if e - s > 1024:
            fn = f'{name}.{k:04d}.bin'
            (out_dir / fn).write_bytes(rom[s:e])
            w['file'] = fn
        else:
            w['hex'] = rom[s:e].hex(' ')
        writes.append(w)
    return {'format': 'dq5patch/1', 'name': name, 'rom_size': mb, 'writes': writes}


def split_banks(ranges):
    out = []
    for s, e in ranges:
        while s < e:
            k = min(e, (s // BANK + 1) * BANK) if s < ORIGINAL_SIZE else e
            out.append((s, k))
            s = k
    return out


# ---- 쓰기 도구 ----

def run_tool(tool, *args):
    r = subprocess.run([sys.executable, str(HERE / tool), *map(str, args)], capture_output=True, text=True,
                       timeout=600)
    if r.returncode:
        raise ValueError(f'{tool} 실패: {r.stderr.strip() or r.stdout.strip()}')
    return r.stdout


def expanded_writes(manifest_path):
    """패치 목록에서 늘린 자리(원래 롬 뒤)에 쓰는 구간을 위치 순으로."""
    _, _, writes = load_manifest(manifest_path)
    return sorted((off, off + len(data)) for off, data, _, _ in writes if off >= ORIGINAL_SIZE)


def merged(ranges):
    return [tuple(r) for r in Space(ranges).ranges]


class Job:
    def __init__(self, doc, root, ctx):
        self.doc, self.root, self.ctx = doc, root, ctx
        self.name = doc['name']
        self.kind = doc['kind']
        allowed = {'map': {'inputs', 'at'}, 'field': {'input', 'world', 'at'}, 'text': {'input', 'over', 'at'},
                   'npc': {'input', 'records', 'allow_growth', 'at', 'alt_at'}, 'event': {'inputs', 'at'},
                   'patch': {'input'}}.get(doc.get('kind'), set())
        unknown = set(doc) - {'name', 'kind'} - allowed
        if unknown:
            raise ValueError(f'작업 {self.name}: 모르는 필드 {sorted(unknown)}')

    def path(self, key):
        return (self.root / self.doc[key]).resolve()

    def paths(self):
        return [(self.root / p).resolve() for p in self.doc['inputs']]

    def pin(self, key='at'):
        return parse_cpu(self.doc[key]) if key in self.doc else None


class MapJob(Job):
    """dq5map/1 JSON 여럿(dq5mapsrc/1 이면 먼저 컴파일)을 dq5mapwrite.py patch --at 로 이어 놓는다."""

    def prepare(self, out):
        self.inputs = []
        for path in self.paths():
            doc = json.loads(path.read_text(encoding='utf-8'))
            if doc.get('format') == 'dq5mapsrc/1':
                target = out / f'{self.name}.{path.stem}.dq5map.json'
                run_tool('dq5mapcompile.py', self.ctx.rom_path, 'compile', path, '-o', target)
                path = target
            self.inputs.append(path)

    def run(self, out, at, alt=None):
        target = out / f'{self.name}.dq5patch.json'
        run_tool('dq5mapwrite.py', self.ctx.rom_path, 'patch', *self.inputs, '--at', cpu(at), '--name', self.name,
                 '-o', target)
        return target, [f'dq5mapwrite.py rom patch {" ".join(p.name for p in self.inputs)} --at {cpu(at)}']

    def pieces(self, probe):
        return [Piece(self.name, self.name, 'stream', [sum(e - s for s, e in probe)], KINDS['map'], pin=self.pin())]


class FieldJob(Job):
    """세계 하나의 지도 .bin 을 dq5fieldwrite.py patch --world N --at 로. 9번째 비트·지도 두 덩어리."""

    def prepare(self, out):
        if self.doc.get('world') not in (0, 1, 2):
            raise ValueError(f'작업 {self.name}: world 는 0·1·2')

    def run(self, out, at, alt=None):
        target = out / f'{self.name}.dq5patch.json'
        world = self.doc['world']
        run_tool('dq5fieldwrite.py', self.ctx.rom_path, 'patch', '--world', world, self.path('input'),
                 '--at', cpu(at), '--name', self.name, '-o', target)
        return target, [f'dq5fieldwrite.py rom patch --world {world} {self.path("input").name} --at {cpu(at)}']

    def pieces(self, probe):
        return [Piece(self.name, self.name, 'chunks', [e - s for s, e in probe], KINDS['field'], pin=self.pin())]


class NpcJob(Job):
    """dq5npcrelocate/1 을 dq5npcrelocate.py patch --base --alt 로. 기본·대체 목록은 각각 한 뱅크 안, 서로 다른 뱅크.
    records 는 dq5npcrecord/1(인물 필드·조건 표)이며 --records 로 옮기는 사본에 함께 넣는다."""

    def prepare(self, out):
        pass

    def run(self, out, at, alt):
        target = out / f'{self.name}.dq5patch.json'
        self.report = out / f'{self.name}.layout.json'
        extra = ['--records', self.path('records')] if 'records' in self.doc else []
        if self.doc.get('allow_growth'):
            extra.append('--allow-growth')
        run_tool('dq5npcrelocate.py', self.ctx.rom_path, 'patch', self.path('input'), '--base', cpu(at),
                 '--alt', cpu(alt), '-o', target, '--report', self.report, *extra)
        return target, [f'dq5npcrelocate.py rom patch {self.path("input").name} --base {cpu(at)} --alt {cpu(alt)}'
                        + (f' --records {self.path("records").name}' if 'records' in self.doc else '')
                        + (' --allow-growth' if self.doc.get('allow_growth') else '')]

    def pieces(self, probe):
        base, alt = probe
        return [Piece(self.name, f'{self.name}.base', 'chunks', [base[1] - base[0]], KINDS['npc'], apart=f'{self.name}.alt',
                      pin=self.pin()),
                Piece(self.name, f'{self.name}.alt', 'chunks', [alt[1] - alt[0]], KINDS['npc'], apart=f'{self.name}.base',
                      pin=self.pin('alt_at'))]


class TextJob(Job):
    """dq5text/1 을 dq5textwrite.py patch --at 로. over 를 주면 그 고정 롬이 옮겨 둔 보행 메시지 묶음을 기준으로
    고친 것만 바꾸고(--base) 그 묶음과 원본 훅 쓰기를 대신한다. 머리(디코더·트리·글자 묶음 표)는 한 뱅크 안."""

    def prepare(self, out):
        import dq5textwrite as tw
        doc = json.loads(self.path('input').read_text(encoding='utf-8'))
        self.base = None
        if 'over' in self.doc:
            fixed = self.ctx.fixed_by_name(self.doc['over'])
            self.base = fixed['rom_path']
            messages, font, glyphs, extent = tw.base_package(fixed['rom'])
            fixed['supersede'].append(extent)
        else:
            for fixed in self.ctx.fixed:
                if fixed['mask'][lorom(DECODER)]:
                    raise ValueError(f'작업 {self.name}: 고정 패치 {fixed["name"]} 가 보행 메시지를 이미 옮겼음. '
                                     f'over 로 그 묶음을 기준으로 삼아야 함(같은 색인·훅을 둘이 쓸 수 없음)')
            messages, font, glyphs = tw.read_messages(self.ctx.original), None, tw.GLYPHS
        self.messages = tw.overrides(messages, doc, glyphs)
        _, nodes, _ = tw.tree(self.messages, glyphs)
        self.head = DECODER_END - DECODER + 8 + len(nodes) * 4 + len(font or b'')

    def run(self, out, at, alt=None):
        target = out / f'{self.name}.dq5patch.json'
        extra = ['--base', self.base] if self.base else []
        run_tool('dq5textwrite.py', self.ctx.rom_path, 'patch', self.path('input'), '--at', cpu(at),
                 '--name', self.name, '-o', target, *extra)
        if self.base:
            # 대신하는 원본 자리(색인·훅·표 피연산자)는 고정 패치에서 뺀다.
            _, _, writes = load_manifest(target)
            fixed = self.ctx.fixed_by_name(self.doc['over'])
            fixed['supersede'] += [(off, off + len(data)) for off, data, _, _ in writes if off < ORIGINAL_SIZE]
        return target, [f'dq5textwrite.py rom patch {self.path("input").name} --at {cpu(at)}'
                        + (f' --base {Path(self.base).name}' if self.base else '')]

    def pieces(self, probe):
        kind = 'text-over' if 'over' in self.doc else 'text'
        return [Piece(self.name, self.name, 'stream', [sum(e - s for s, e in probe)], KINDS[kind], head=self.head,
                      pin=self.pin())]


class EventJob(Job):
    """dq5event/1 여럿을 dq5eventwrite.py patch --at 로. 스크립트마다 한 뱅크 안."""

    def prepare(self, out):
        pass

    def run(self, out, at, alt=None):
        target = out / f'{self.name}.dq5patch.json'
        run_tool('dq5eventwrite.py', self.ctx.rom_path, 'patch', *self.paths(), '--at', cpu(at), '--name', self.name,
                 '-o', target)
        return target, [f'dq5eventwrite.py rom patch {" ".join(p.name for p in self.paths())} --at {cpu(at)}']

    def pieces(self, probe):
        return [Piece(self.name, self.name, 'chunks', [e - s for s, e in probe], KINDS['event'], pin=self.pin())]


class PatchJob(Job):
    """이미 만든 dq5patch/1(제자리 쓰기 도구의 결과). 배치하지 않고 그대로 넣는다. 늘린 자리를 쓰면 빈 자리여야 함."""

    def prepare(self, out):
        pass

    def pieces(self, probe):
        return []


JOB_KINDS = {'map': MapJob, 'field': FieldJob, 'npc': NpcJob, 'text': TextJob, 'event': EventJob, 'patch': PatchJob}
PROBE = {'low': 0x30 * BANK, 'high': 0x60 * BANK}


class Context:
    def __init__(self, rom_path, config_path, out):
        self.rom_path = Path(rom_path).resolve()
        self.original = self.rom_path.read_bytes()
        if len(self.original) != ORIGINAL_SIZE:
            raise ValueError(f'원래 롬은 {ORIGINAL_SIZE:#x} 바이트여야 함')
        self.config_path = Path(config_path).resolve()
        self.root = self.config_path.parent
        self.config = json.loads(self.config_path.read_text(encoding='utf-8'))
        if self.config.get('format') != FORMAT:
            raise ValueError(f'format 은 {FORMAT}')
        unknown = set(self.config) - {'format', 'size', 'fixed', 'reserve', 'jobs'}
        if unknown:
            raise ValueError(f'모르는 필드 {sorted(unknown)}')
        self.mb = int(self.config.get('size', 4))
        if self.mb not in REACHABLE:
            raise ValueError('size 는 2·3·4')
        self.out = Path(out).resolve()
        self.fixed = []
        for doc in self.config.get('fixed', []):
            path = (self.root / doc['rom']).resolve()
            rom = path.read_bytes()
            unknown = set(doc) - {'name', 'rom', 'title_layout', 'keep'}
            if unknown:
                raise ValueError(f'고정 패치 {doc.get("name")}: 모르는 필드 {sorted(unknown)}')
            keep = title_keep((self.root / doc['title_layout']).resolve()) if 'title_layout' in doc else None
            if keep is not None:
                # 거울 안에 다른 단계가 둔 자료 가운데 거울과 같은 바이트가 이어지는 곳은 다른 바이트로 찾을 수 없다.
                keep += [(parse_cpu(a), parse_cpu(b) + 1) for a, b in doc.get('keep', [])]
            if len(rom) > REACHABLE[self.mb]:
                raise ValueError(f'고정 롬 {path.name} 이 size {self.mb}MB 보다 큼')
            mask, hold, freed = fixed_mask(self.original, rom, keep)
            self.fixed.append({'name': doc['name'], 'rom_path': path, 'rom': rom, 'mask': mask, 'hold': hold,
                               'mirror_freed': freed, 'supersede': []})
        names = [j['name'] for j in self.config.get('jobs', [])] + [f['name'] for f in self.fixed]
        if len(set(names)) != len(names):
            raise ValueError('작업·고정 패치 이름이 겹침')
        self.jobs = []
        for doc in self.config.get('jobs', []):
            if doc.get('kind') not in JOB_KINDS:
                raise ValueError(f'작업 {doc.get("name")}: kind 는 {sorted(JOB_KINDS)}')
            self.jobs.append(JOB_KINDS[doc['kind']](doc, self.root, self))

    def fixed_by_name(self, name):
        for f in self.fixed:
            if f['name'] == name:
                return f
        raise ValueError(f'고정 패치 {name} 가 없음')

    def space(self):
        """늘린 자리 가운데 고정 패치·예약을 뺀 빈 자리. FE·FF 뱅크(파일 3F0000~)는 어느 창에도 없어 뺀다."""
        free = bytearray(REACHABLE[self.mb])
        free[ORIGINAL_SIZE:min(len(free), 0x3F0000)] = b'\1' * (min(len(free), 0x3F0000) - ORIGINAL_SIZE)
        for f in self.fixed:
            effective(f)
            for s, e in f['occupied']:
                free[s:e] = bytes(e - s)
        self.reserved = []
        for doc in self.config.get('reserve', []):
            s, e = parse_cpu(doc['from']), parse_cpu(doc['to']) + 1
            free[s:e] = bytes(e - s)
            self.reserved.append({'name': doc['name'], 'from': doc['from'], 'to': doc['to'], 'bytes': e - s})
        return Space(mask_ranges(free))


def effective(f):
    """대신한 자리를 뺀 쓰기 표시와 차지하는 자리."""
    mask = bytearray(f['mask'])
    for s, e in f['supersede']:
        mask[s:e] = bytes(e - s)
    f['effective'] = mask
    f['occupied'] = occupied(mask, f['hold'], f['supersede'])
    return mask


def probe(job, out):
    """쓰기 도구를 원래 롬 기준으로 창 첫머리에 한 번 돌려 크기를 잰다. 크기는 놓는 자리와 상관없다
    (자리 규칙은 Piece 가 따름)."""
    window = KINDS['text-over' if job.kind == 'text' and 'over' in job.doc else job.kind][0]
    at = PROBE[window]
    target, _ = job.run(out, at, at + BANK)
    writes = expanded_writes(target)
    if job.kind == 'npc':
        # 쓰기 도구는 기본·대체 목록을 쓰기 하나씩으로 낸다. 기본이 뱅크를 꽉 채우면 이어 붙으므로 합치지 않는다.
        if len(writes) != 2:
            raise ValueError(f'작업 {job.name}: 인물 목록 쓰기가 {len(writes)}개(기본·대체 둘이어야 함)')
        return sorted(writes, key=lambda r: r[0] // BANK != at // BANK)
    if job.kind in ('field', 'event'):
        return writes
    return merged(writes)


def plan(ctx):
    probe_dir = ctx.out / 'probe'
    probe_dir.mkdir(parents=True, exist_ok=True)
    pieces = []
    for job in ctx.jobs:
        job.prepare(ctx.out)
        if job.kind == 'patch':
            continue
        job.probe = probe(job, probe_dir)
        if not job.probe:
            raise ValueError(f'작업 {job.name}: 늘린 자리에 쓰는 것이 없음(제자리 쓰기면 patch 종류로)')
        pieces += job.pieces(job.probe)
    space = ctx.space()
    before = Space(space.ranges)
    # 제자리 쓰기 결과도 늘린 자리를 쓰면 배치 전에 빼 둔다.
    for job in ctx.jobs:
        if job.kind == 'patch':
            for s, e in merged(expanded_writes(job.path('input'))):
                if not space.contains(s, e):
                    raise ValueError(f'작업 {job.name}: {cpu(s)}~{cpu(e - 1)} 이 빈 자리 밖이거나 다른 patch 작업과 겹침')
                space.take(s, e)
    placed = allocate(pieces, space)
    return pieces, placed, before, space


def check_footprint(job, manifest, placed):
    """쓰기 도구가 실제로 쓴 늘린 자리가 배치기가 예측한 구간과 같은지."""
    want = merged(r for p in placed.values() if p['job'] == job.name for r in p['ranges'])
    got = merged(expanded_writes(manifest))
    if got != want:
        raise ValueError(f'작업 {job.name}: 쓰기 도구가 쓴 자리 {[(cpu(s), cpu(e - 1)) for s, e in got]} 가 '
                         f'배치 {[(cpu(s), cpu(e - 1)) for s, e in want]} 와 다름')


def run_build(ctx, report):
    pieces, placed, before, after = plan(ctx)
    for p in pieces:
        placed[p.name]['job'] = p.job
    manifests, commands = [], []
    for job in ctx.jobs:
        if job.kind == 'patch':
            manifests.append(job.path('input'))
            continue
        names = [p.name for p in pieces if p.job == job.name]
        at = placed[names[0]]['at']
        alt = placed[names[1]]['at'] if len(names) > 1 else None
        target, cmd = job.run(ctx.out, at, alt)
        check_footprint(job, target, placed)
        manifests.append(target)
        commands += cmd
    # 고정 패치는 대신한 자리를 뺀 뒤에 쓴다(보행 대사 작업이 supersede 를 채운 뒤).
    fixed_manifests = []
    for f in ctx.fixed:
        mask = effective(f)
        doc = manifest_from_mask(f['name'], ctx.original, f['rom'], mask, ctx.mb, ctx.out)
        target = ctx.out / f'{f["name"]}.dq5patch.json'
        target.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
        fixed_manifests.append(target)
    every = fixed_manifests + manifests
    mb = max([ctx.mb] + [load_manifest(p)[1] for p in every])
    out_rom = ctx.out / 'port.sfc'
    checked = run_tool('dq5build.py', ctx.rom_path, 'check', *every, '--size', mb).strip()
    built = run_tool('dq5build.py', ctx.rom_path, 'build', *every, '--size', mb, '-o', out_rom,
                     '--ips', out_rom.with_suffix('.ips'))
    rom, patch = out_rom.read_bytes(), out_rom.with_suffix('.ips').read_bytes()
    if ips.apply(ctx.original, patch) != rom:
        raise ValueError('IPS 를 원래 롬에 다시 붙인 결과가 롬과 다름')
    allw = [line for line in built.splitlines() if ': 쓰기 ' in line]
    statics = static_checks(ctx, rom)
    report['jobs_input'] = [job_input(job) for job in ctx.jobs]
    report['mirror_freed_overwritten'] = freed_overwritten(ctx, placed)
    report['scratch'] = scratch(after, rom)
    report.update({
        'rom': str(out_rom), 'rom_sha1': hashlib.sha1(rom).hexdigest(), 'rom_bytes': len(rom),
        'ips_bytes': len(patch), 'ips_reapplied': True, 'dq5build_check': checked, 'dq5build_lists': allw,
        'manifests': [str(p) for p in fixed_manifests + manifests], 'commands': commands, 'static': statics,
    })
    return pieces, placed, before, after


def freed_overwritten(ctx, placed):
    """작업이 덮은 거울 바이트(고정 롬에서 비운 자리) 수. 그 자리를 고정 롬이 읽지 않는지는 게임 검사가 본다."""
    out = {}
    for f in ctx.fixed:
        if f['hold'] is None:
            continue
        held = Space(f['hold'])
        n = sum(1 for v in placed.values() for s, e in v['ranges'] for i in range(max(s, MIRROR[0]), min(e, MIRROR[1]))
                if not held.contains(i, i + 1))
        out[f['name']] = n
    return out


def job_input(job):
    """검사 도구가 읽을 작업 입력(절대 경로)."""
    row = {'name': job.name, 'kind': job.kind}
    for key in ('input', 'records', 'world', 'over'):
        if key in job.doc:
            row[key] = str(job.path(key)) if key in ('input', 'records') else job.doc[key]
    if 'inputs' in job.doc:
        row['inputs'] = [str(getattr(job, 'inputs', job.paths())[i]) for i in range(len(job.doc['inputs']))]
    if job.kind == 'npc':
        row['layout'] = str(job.report)
    return row


def scratch(space, rom):
    """검사 도구가 실행 때만 호출 틀을 덮을 16바이트. 배치 뒤에도 비어 있는 높은 창의 첫 자리."""
    lo, hi = window_range('high')
    for s, e in space.clip(lo, hi):
        if e - s >= 16 and not any(rom[s:s + 16]):
            return cpu(s)
    return None


def static_checks(ctx, rom):
    out = {}
    for f in ctx.fixed:
        # 원래 롬 자리의 쓰기와 늘린 자리에서 차지한 구간 전부가 고정 롬과 같아야 한다.
        ranges = [r for r in mask_ranges(f['effective']) if r[0] < ORIGINAL_SIZE] + f['occupied']
        bad = sum(1 for s, e in ranges for i in range(s, e) if rom[i] != f['rom'][i])
        if bad:
            raise ValueError(f'고정 패치 {f["name"]}: 차지한 바이트 {bad}개가 결과 롬에서 다름')
        out[f['name']] = {'bytes_equal': sum(e - s for s, e in ranges), 'differences': 0}
    for job in ctx.jobs:
        if job.kind == 'text':
            import dq5textwrite as tw
            decoded = tw.decoded_messages(rom)
            different = sum(a != b for a, b in zip(job.messages, decoded))
            if different or len(decoded) != len(job.messages):
                raise ValueError(f'작업 {job.name}: 결과 롬의 보행 메시지 {different}개가 입력과 다름')
            out[job.name] = {'messages_equal': len(decoded)}
    return out


def describe(ctx, pieces, placed, before, after):
    jobs = []
    for p in pieces:
        v = placed[p.name]
        jobs.append({'job': p.job, 'piece': p.name, 'mode': p.mode, 'bytes': p.size, 'sizes': p.sizes,
                     'window': v['window'], 'at': cpu(v['at']),
                     'ranges': [[cpu(s), cpu(e - 1)] for s, e in v['ranges']]})
    fixed = []
    for f in ctx.fixed:
        banks = {}
        for s, e in f['occupied']:
            for b in range(s // BANK, (e - 1) // BANK + 1):
                lo, hi = max(s, b * BANK), min(e, (b + 1) * BANK)
                banks[b] = banks.get(b, 0) + hi - lo
        fixed.append({'name': f['name'], 'rom': str(f['rom_path']),
                      'rom_sha1': hashlib.sha1(f['rom']).hexdigest(),
                      'mirror_freed': f['mirror_freed'],
                      'superseded': [[cpu(s), cpu(e - 1)] for s, e in merged(f['supersede'])],
                      'expanded_banks': {f'{b:02X}': n for b, n in sorted(banks.items()) if b * BANK >= ORIGINAL_SIZE}})
    return {'format': 'dq5portbuild-report/1', 'config': str(ctx.config_path), 'size': ctx.mb,
            'fixed': fixed, 'reserve': ctx.reserved, 'pieces': jobs,
            'windows': summary(pieces, before, placed),
            'free_after': {w: after.total(*window_range(w)) for w in WINDOWS}}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('rom')
    ap.add_argument('cmd', choices=('plan', 'build'))
    ap.add_argument('config')
    ap.add_argument('--out', required=True)
    a = ap.parse_args()
    try:
        ctx = Context(a.rom, a.config, a.out)
        ctx.out.mkdir(parents=True, exist_ok=True)
        extra = {}
        if a.cmd == 'plan':
            pieces, placed, before, after = plan(ctx)
        else:
            pieces, placed, before, after = run_build(ctx, extra)
        report = describe(ctx, pieces, placed, before, after) | extra
    except AllocationError as e:
        print(f'오류: 배치 실패\n{e}', file=sys.stderr)
        return 1
    except (ValueError, PatchError, OSError, KeyError) as e:
        print(f'오류: {e}', file=sys.stderr)
        return 1
    path = ctx.out / 'report.json'
    path.write_text(json.dumps(report, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    for p in report['pieces']:
        print(f'{p["piece"]:<16} {p["bytes"]:>7}바이트  창 {p["window"]:<4} {p["ranges"][0][0]}~{p["ranges"][-1][1]}')
    for w, s in report['windows'].items():
        print(f'창 {w}({s["banks"]}): 이 창만 {s["needed_only_here"]} + 공유 {s["needed_shared"]}바이트, '
              f'빈 자리 {s["free"]}바이트(가장 긴 {s["largest_free"]}), 놓음 {s.get("placed", 0)}, '
              f'남음 {report["free_after"][w]}')
    if a.cmd == 'build':
        print(f'{report["rom"]} sha1={report["rom_sha1"]} IPS {report["ips_bytes"]}바이트(다시 붙여 같음)')
    print(f'보고 → {path}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
