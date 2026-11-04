"""장면 화면을 기준과 견준다. 형식은 sfc/dq4/docs/dq4-screen-baseline-format.md.

화면은 8×8 칸으로 나눠 칸마다 해시(SHA-1 앞 4바이트)를 내고, 기준(sfc/dq4/screens.toml)에는 이 칸 해시만 둔다. 기준 그림은
롬에서 나온 것이라 저장소에 두지 않는다(ROM-01). 칸 해시만으로 어느 머신에서나 같은 판정이 난다.

  - 가림: 직사각형(x, y, 너비, 높이) 안 픽셀은 0 으로 지우고 해시를 낸다. 칸이 모두 가려지면 견주지 않는다
  - 허용치: 다른 칸이 tolerance 개 이하면 통과(기본 0)
  - 차이 그림: 실패하면 지금 화면에 다른 칸을 빨갛게, 가림을 어둡게 그린 PNG 를 남긴다. 같은 기준을 만든 그림이
    로컬 캐시(원래 체크아웃 work/cache/screens/<digest>.png)에 있으면 기준·지금·차이를 나란히 둔다

기준은 장면 검사의 --write-screens "까닭" 으로만 쓴다(write_baselines). 칸이 바뀐 장면과 새 장면에만 그 까닭이 남고,
항목마다 표지(check)를 둔다. 손으로 고치면 표지가 맞지 않아 검사가 실패한다.
"""
import base64
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import tomllib

import numpy as np

HERE = Path(__file__).resolve().parent
BASELINES = HERE.parent / 'screens.toml'
TILE = 8
# MesenCE 가 화면 버퍼를 만들 때 쓰는 사용자 설정(영상 필터·밝기·숨긴 층 등)을 명령줄로 고정한다. 기준은 이 값에서 만든다
SCREEN_ARGS = ('--Video.VideoFilter=None', '--Video.Brightness=0', '--Video.Contrast=0', '--Video.Hue=0',
               '--Video.Saturation=0', '--Video.ScanlineIntensity=0', '--Snes.HighResBlendMode=None',
               '--Snes.HideBgLayer1=false', '--Snes.HideBgLayer2=false', '--Snes.HideBgLayer3=false',
               '--Snes.HideBgLayer4=false', '--Snes.HideSprites=false')
LUA = HERE / 'lua' / 'dq4screen.lua'
FIELDS = ('scene', 'emulator', 'width', 'height', 'masks', 'tolerance', 'digest', 'tiles')


def read_rgb(path):
    """dq4screen.lua 의 screen-NNNNN.rgb → (높이, 너비, 3) uint8."""
    data = Path(path).read_bytes()
    w, h = struct.unpack('<II', data[:8])
    if len(data) != 8 + w * h * 3:
        raise ValueError(f'{path}: 크기 {w}×{h} 와 길이 {len(data)} 가 맞지 않음')
    return np.frombuffer(data, np.uint8, offset=8).reshape(h, w, 3)


def masked(img, masks):
    out = np.array(img, dtype=np.uint8, copy=True)
    for x, y, w, h in masks:
        out[y:y + h, x:x + w] = 0
    return out


def covered(img, masks):
    """가린 픽셀은 True."""
    m = np.zeros(img.shape[:2], bool)
    for x, y, w, h in masks:
        m[y:y + h, x:x + w] = True
    return m


def tile_hashes(img, masks=()):
    """칸마다 해시(32비트). 모두 가려진 칸은 None. 차례는 위 줄부터 왼쪽에서 오른쪽."""
    h, w = img.shape[:2]
    m, cov = masked(img, masks), covered(img, masks)
    out = []
    for ty in range(0, h, TILE):
        for tx in range(0, w, TILE):
            if cov[ty:ty + TILE, tx:tx + TILE].all():
                out.append(None)
            else:
                out.append(int.from_bytes(hashlib.sha1(m[ty:ty + TILE, tx:tx + TILE].tobytes()).digest()[:4], 'big'))
    return out


def digest(img, masks=()):
    return hashlib.sha256(masked(img, masks).tobytes() + repr(img.shape).encode()).hexdigest()[:16]


def pack_tiles(tiles):
    # 가린 칸은 0 으로 둔다(그 칸은 견주지 않으므로 값이 우연히 0 인 칸과 섞여도 판정이 같다)
    return base64.b64encode(b''.join((t or 0).to_bytes(4, 'big') for t in tiles)).decode()


def unpack_tiles(text):
    raw = base64.b64decode(text)
    return [int.from_bytes(raw[i:i + 4], 'big') for i in range(0, len(raw), 4)]


def entry(scene, emulator, img, masks=(), tolerance=0):
    masks = [list(map(int, r)) for r in masks]
    return {'scene': scene, 'emulator': emulator, 'width': int(img.shape[1]), 'height': int(img.shape[0]),
            'masks': masks, 'tolerance': int(tolerance), 'digest': digest(img, masks),
            'tiles': pack_tiles(tile_hashes(img, masks))}


def entry_check(e, reason):
    """기준 한 항목의 표지. write_baselines 만 쓰므로, 칸·가림·허용치·까닭을 손으로 고치면 맞지 않는다."""
    text = json.dumps([e[k] for k in FIELDS] + [reason], ensure_ascii=False, sort_keys=True)
    return hashlib.sha1(text.encode('utf-8')).hexdigest()[:12]


def load_baselines(path=BASELINES):
    """{(장면, 에뮬레이터): 항목}. 파일이 없으면 빈 dict. 표지가 맞지 않거나 까닭이 비면 ValueError(손으로 고친 기준)."""
    path = Path(path)
    if not path.exists():
        return {}
    out = {}
    for e in tomllib.loads(path.read_text(encoding='utf-8')).get('screen', []):
        key = (e.get('scene'), e.get('emulator'))
        if not str(e.get('reason', '')).strip():
            raise ValueError(f'{path.name} {key}: reason 이 비어 있음')
        if e.get('check') != entry_check(e, e['reason']):
            raise ValueError(f'{path.name} {key}: check 가 맞지 않음(손으로 고친 기준, --write-screens 로 다시 만들 것)')
        out[key] = e
    return out


def compare(img, want, masks=(), tolerance=0):
    """지금 화면을 기준 항목과 견준다. {'status', 'problems', 'tiles': [(칸 x, 칸 y)], 'digest'}."""
    masks = [list(map(int, r)) for r in masks]
    got = entry(want['scene'], want['emulator'], img, masks, tolerance)
    problems = []
    if [want['width'], want['height']] != [got['width'], got['height']]:
        problems.append(f'화면 크기 {got["width"]}×{got["height"]}, 기준 {want["width"]}×{want["height"]}')
        return {'status': 'failed', 'problems': problems, 'tiles': [], 'digest': got['digest']}
    if want['masks'] != masks or want['tolerance'] != int(tolerance):
        problems.append('가림·허용치가 기준을 만들 때와 다름(--write-screens 로 다시 만들 것)')
    cols = -(-got['width'] // TILE)
    a, b = unpack_tiles(want['tiles']), unpack_tiles(got['tiles'])
    mask_tiles = {i for i, t in enumerate(tile_hashes(img, masks)) if t is None}
    diff = [(i % cols, i // cols) for i, (x, y) in enumerate(zip(a, b)) if x != y and i not in mask_tiles]
    if len(diff) > int(tolerance):
        problems.append(f'다른 칸 {len(diff)}개(허용 {int(tolerance)}개)')
    return {'status': 'failed' if problems else 'passed', 'problems': problems, 'tiles': diff,
            'digest': got['digest']}


def cache_dir():
    common = subprocess.run(['git', 'rev-parse', '--path-format=absolute', '--git-common-dir'], cwd=HERE,
                            capture_output=True, text=True, check=True).stdout.strip()
    return Path(common).parent / 'work' / 'cache' / 'screens'


def save_png(img, path):
    from PIL import Image
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(np.asarray(img, np.uint8)).save(path)


def diff_image(img, tiles, masks=(), base=None):
    """지금 화면에 다른 칸을 빨갛게, 가림을 어둡게. base(기준 그림)가 있으면 기준·지금·차이를 나란히."""
    out = np.array(img, np.uint8, copy=True)
    cov = covered(img, masks)
    out[cov] = out[cov] // 3
    for tx, ty in tiles:
        x, y = tx * TILE, ty * TILE
        out[y:y + TILE, x] = out[y:y + TILE, min(x + TILE, out.shape[1]) - 1] = (255, 0, 0)
        out[y, x:x + TILE] = out[min(y + TILE, out.shape[0]) - 1, x:x + TILE] = (255, 0, 0)
    if base is not None and base.shape == img.shape:
        out = np.concatenate([base, img, out], axis=1)
    return out


def check_screen(img, scene, emulator, out, masks=(), tolerance=0, baselines=None):
    """장면 하나를 견주고, 실패면 out/<장면>-<에뮬레이터>-diff.png 를 남긴다. 기준이 없으면 실패."""
    baselines = load_baselines() if baselines is None else baselines
    want = baselines.get((scene, emulator))
    name = f'{scene}-{emulator}'
    if want is None:
        return {'status': 'failed', 'problems': [f'기준 없음({BASELINES.name}, --write-screens 로 만들 것)'],
                'tiles': [], 'digest': digest(img, masks)}
    r = compare(img, want, masks, tolerance)
    if r['status'] != 'passed':
        cached = cache_dir() / f'{want["digest"]}.png'
        base = None
        if cached.exists():
            from PIL import Image
            with Image.open(cached) as im:
                base = np.asarray(im.convert('RGB'))
        save_png(diff_image(img, r['tiles'], masks, base), Path(out) / f'{name}-diff.png')
        r['diff'] = str(Path(out) / f'{name}-diff.png')
    else:
        cached = cache_dir() / f'{r["digest"]}.png'
        if not cached.exists():
            save_png(img, cached)
    return r


def write_baselines(rows, reason, path=BASELINES):
    """rows [(장면, 에뮬레이터, 화면, 가림, 허용치)] 로 기준 파일을 고친다. 칸·가림·허용치가 바뀐 항목과 새 항목은 reason 을,
    같은 항목은 앞 reason 을 둔다. rows 에 없는 기준은 그대로 둔다. 기준 그림은 로컬 캐시에만 둔다."""
    if not reason.strip():
        raise ValueError('까닭이 비어 있음')
    old = load_baselines(path)
    new = dict(old)
    for scene, emulator, img, masks, tolerance in rows:
        e = entry(scene, emulator, img, masks, tolerance)
        prev = old.get((scene, emulator))
        same = prev and all(prev[k] == e[k] for k in FIELDS)
        new[(scene, emulator)] = {**e, 'reason': prev['reason'] if same else reason.strip()}
        save_png(img, cache_dir() / f'{e["digest"]}.png')
    lines = ['# 장면 화면 기준(dq4screens.py). 칸(8×8)마다 해시만 둔다. 손으로 고치지 않는다. 장면 검사의 --write-screens "까닭"',
             '# 으로 다시 만든다. 바뀐 항목에만 그 까닭이 reason 으로 남고, check 는 그 도구만 쓰는 표지라 손으로 고치면 검사가 실패한다.', '']
    for key in sorted(new):
        e = new[key]
        lines += ['[[screen]]'] + [f'{k} = {json.dumps(e[k], ensure_ascii=False)}' for k in FIELDS]
        lines += ['reason = ' + json.dumps(e['reason'], ensure_ascii=False), f'check = "{entry_check(e, e["reason"])}"', '']
    Path(path).write_text('\n'.join(lines), encoding='utf-8')
    return new
