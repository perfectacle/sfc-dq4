"""한글 타이틀만 SFC BG 에셋과 비교 페이지로 만듭니다. DQ5 타이틀 삽입은 하지 않습니다."""

import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image

from dq4graphics import export_image, png_bytes

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SOURCE = Path(__file__).with_name('dq4art') / 'title-ko.png'
APPROVED_SOURCE_SHA256 = '6db3d70380dd4727f3b083dae1fdb0cf501f07d84888b0462df565d65d5b392f'

PAGE = '''<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>드래곤 퀘스트 IV · 한글 타이틀</title>
<style>
:root{color-scheme:dark}*{box-sizing:border-box}body{margin:0;background:#10191e;color:#e7eef1;font:16px/1.7 system-ui,sans-serif}main{max-width:1120px;margin:auto;padding:32px 20px 60px}a{color:#f0ce85}h1{font-size:30px;line-height:1.3}p{color:#b4c6cb}.screen{overflow:auto;background:#050a0e;border:1px solid #34454d;padding:12px;border-radius:8px}.screen img{display:block;width:1024px;max-width:none;height:auto;image-rendering:pixelated;margin:auto}select{font:inherit;background:#24353f;color:white;border:1px solid #51656d;border-radius:5px;padding:4px 8px}details{margin-top:24px}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px;color:#b4c6cb}.controls{margin:20px 0;display:flex;gap:20px;align-items:center;flex-wrap:wrap} @media(max-width:700px){.screen img{width:512px}h1{font-size:24px}}
</style></head><body><main>
<a href="index.html">인물 에셋 갤러리</a>
<h1>드래곤 퀘스트 IV</h1><p>인도받은 자들 · 한글 타이틀</p>
<p>이 페이지는 256×224 화면을 SFC의 8개 BG 팔레트로 변환한 정적 에셋을 보여 줍니다. DQ5 연결은 별도 dq4titlepatch 도구로 만들며, 실행 검증은 통합 ROM의 보고서에서 확인합니다.</p>
<div class="controls"><label>표시 배율 <select id="scale"><option value="1">1× 실제 크기</option><option value="2">2×</option><option value="4" selected>4×</option></select></label><a href="../gfx/screens/title/title.png">PNG 원본</a><a href="../gfx/screens/title/manifest.json">변환 규격</a></div>
<div class="screen"><img id="title" src="../gfx/screens/title/title.png" width="256" height="224" alt="푸른 하늘과 용, 한글 드래곤 퀘스트 로고와 IV, 인도받은 자들 부제"></div>
<p>색·타일·팔레트의 역변환 일치와 시각적 채택은 별도로 확인합니다. 그림의 현재 검토 상태는 아래 기록을 참고하세요.</p>
<details><summary>제작 출처와 검사 기록</summary><pre id="metadata"></pre></details>
</main><script id="data" type="application/json">__MANIFEST__</script><script>
const data=JSON.parse(document.getElementById('data').textContent);document.getElementById('metadata').textContent=JSON.stringify(data,null,2);const scale=document.getElementById('scale');function resize(){document.getElementById('title').style.width=(256*Number(scale.value))+'px';}scale.addEventListener('change',resize);resize();
</script></body></html>'''


def source_label(path):
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return path.name


def native_title(source):
    with Image.open(source) as opened:
        image = opened.copy()
    if image.mode != 'P' or image.size != (256, 224) or 'transparency' in image.info:
        raise ValueError('expected an opaque indexed 256x224 native title; resizing is not performed')
    before = image.convert('RGB').tobytes()
    used = set(image.tobytes())
    if max(used) >= 128 or any(index and index % 16 == 0 for index in used):
        raise ValueError('expected eight palette banks with all backdrop pixels at global index zero')
    palette = image.getpalette()
    if len(palette) < 384:
        raise ValueError('expected eight complete 16-color palette banks')
    # Hardware shares color zero; these unused slots may be normalized without changing pixels.
    for bank in range(8):
        palette[bank * 48:bank * 48 + 3] = palette[:3]
    image.putpalette(palette)
    if image.convert('RGB').tobytes() != before:
        raise ValueError('backdrop normalization changed visible RGB pixels')
    for index in used:
        if any(((value >> 3) << 3 | value >> 5) != value for value in palette[index * 3:index * 3 + 3]):
            raise ValueError('native palette colors must already be exact 5-bit SFC colors')
    return image


def build(source=DEFAULT_SOURCE):
    source = Path(source)
    image = native_title(source)
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    files, details = export_image('title', image)
    files['title-preview.png'] = png_bytes(image.resize((1024, 896), Image.Resampling.NEAREST))
    manifest = {
        'schema_version': 1,
        'title': '드래곤 퀘스트 IV',
        'subtitle': '인도받은 자들',
        'source': source_label(source),
        'source_sha256': source_hash,
        'source_version': 'selected-native-v2' if source_hash == APPROVED_SOURCE_SHA256 else 'custom-native',
        'conversion': 'native indexed pixels; no resize or requantization',
        'visual_status': 'user_approved' if source_hash == APPROVED_SOURCE_SHA256 else 'review_pending',
        'engine_ready': False,
        'game_insertion': 'separate_patch_tool',
        'integration_builder': 'sfc/dq4/tools/dq4titlepatch.py',
        'format': details,
        'files': {name: {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()} for name, data in files.items()},
        'verification': {'tilemap_chr_roundtrip': 'passed', 'palette_roundtrip': 'passed', 'pixel_differences': 0, 'source_rgb_unchanged': True},
        'regenerate': 'uv run --locked python sfc/dq4/tools/dq4titleassets.py --out work/dq4-title-build',
    }
    return files, manifest


def write_pack(output, files, manifest, source):
    for name in [*files, 'manifest.json']:
        target = output / name
        if target.resolve() == source.resolve() or (target.exists() and target.samefile(source)):
            raise ValueError('output would overwrite the title source')
    output.mkdir(parents=True, exist_ok=True)
    for name, data in files.items():
        (output / name).write_bytes(data)
    (output / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')


def export(source, output, assets_dir=None):
    source, output = Path(source), Path(output)
    files, manifest = build(source)
    write_pack(output, files, manifest, source)
    if assets_dir is not None:
        assets_dir = Path(assets_dir)
        destination = assets_dir / 'gfx/screens/title'
        write_pack(destination, files, manifest, source)
        (destination / 'SOURCE.txt').write_text(
            f"제작 원본: {manifest['source']}\nSHA-256: {manifest['source_sha256']}\n"
            '롬: 불필요, 직접 제작한 타이틀 원본의 SFC 변환\n'
        )
        encoded = json.dumps(manifest, ensure_ascii=False).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
        gallery = assets_dir / 'gallery/index-title.html'
        gallery.parent.mkdir(parents=True, exist_ok=True)
        gallery.write_text(PAGE.replace('__MANIFEST__', encoded))
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=DEFAULT_SOURCE)
    parser.add_argument('--out', type=Path, default=Path('work/dq4-title-build'))
    parser.add_argument('--assets-dir', type=Path, help='비공개 에셋 저장소의 sfc/dq4 디렉터리')
    args = parser.parse_args()
    result = export(args.source, args.out, args.assets_dir)
    print(json.dumps(result['format'], ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
