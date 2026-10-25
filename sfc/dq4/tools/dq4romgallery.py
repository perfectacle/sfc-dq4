"""Publish original DQ4 studies and a ROM patch comparison to a private asset gallery."""

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

from PIL import Image

from dq4sprites import SPRITE_NAMES, build_sheet

NAMES = dict(zip(SPRITE_NAMES, ("라이안", "호이미 슬라임", "아리나", "크리프트", "브라이", "토르네코", "마냐", "미네아", "주인공"), strict=True))
ROOT = Path(__file__).resolve().parents[3]
ROM_IMAGES = {
    "original_sheet": (32, 96),
    "source_front": (16, 24),
    "mapped_front": (16, 24),
    "sheet": (32, 96),
}

HTML = r'''<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>SFC DQ4 · 제작 에셋</title><style>
:root{color-scheme:dark;--bg:#101719;--panel:#192326;--line:#334449;--text:#e8efec;--muted:#a7b9b7;--gold:#eed49a;--scale:4}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:15px/1.65 system-ui,sans-serif}main{max-width:1200px;margin:auto;padding:40px 24px 80px}a{color:var(--gold)}nav{display:flex;gap:18px;flex-wrap:wrap;font-size:13px}h1{font-size:clamp(30px,5vw,52px);line-height:1.15;margin:22px 0 12px;letter-spacing:-2px}h2{font-size:24px;margin:44px 0 10px}h3{font-size:17px;margin:10px 0}.eyebrow{color:var(--gold);font:12px/1.5 monospace;letter-spacing:3px}.lead,.muted{color:var(--muted)}.lead{max-width:760px}.notice{border-left:3px solid var(--gold);padding:14px 18px;background:#252b27;margin:24px 0}.controls{display:flex;flex-wrap:wrap;gap:16px;padding:14px 0;border-block:1px solid var(--line);margin:22px 0}label{font-size:13px;color:var(--muted)}select,button{font:inherit;color:var(--text);background:#263539;border:1px solid #526869;border-radius:6px;padding:6px 10px}label select{margin-left:6px}button{cursor:pointer}button:hover,a:hover{filter:brightness(1.2)}:focus-visible{outline:2px solid var(--gold);outline-offset:3px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(235px,1fr));gap:16px}.card{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:18px;min-width:0}.stage{min-height:180px;display:flex;justify-content:center;align-items:center;overflow:auto;background-color:#26352e;background-image:linear-gradient(45deg,#304137 25%,transparent 25%),linear-gradient(-45deg,#304137 25%,transparent 25%),linear-gradient(45deg,transparent 75%,#304137 75%),linear-gradient(-45deg,transparent 75%,#304137 75%);background-size:16px 16px;background-position:0 0,0 8px,8px -8px,-8px 0;border-radius:7px;padding:16px}canvas{image-rendering:pixelated;flex-shrink:0}.tag{display:inline-block;color:var(--gold);border:1px solid #665e43;font-size:11px;padding:2px 8px;border-radius:20px}.card p{font-size:13px;margin:9px 0}.download{font-size:12px}details{margin-top:24px;border:1px solid var(--line);border-radius:8px;padding:14px}summary{cursor:pointer}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:12px/1.6 monospace;color:var(--muted)}footer{margin-top:42px;border-top:1px solid var(--line);padding-top:20px;font-size:12px;color:var(--muted)}.error{color:#ffb7a8}.counter{font-size:12px;color:var(--muted);align-self:center} @media(max-width:520px){main{padding:24px 14px}.controls{gap:10px}.grid{grid-template-columns:1fr}}
</style></head><body><main>
<header><div class="eyebrow">DRAGON QUEST IV / SUPER FAMICOM</div><h1>작은 도트에서 실제 ROM까지</h1>
<p class="lead">DQ4의 인물과 복장을 DQ5의 16×24 격자에 맞춘 제작물입니다. 그림의 확인 상태와 ROM 변환 결과를 나란히 살펴봅니다.</p>
<nav aria-label="갤러리 이동"><a href="#rom">ROM 비교</a><a href="#drafts">인물 시안 9명</a><a href="../../../fc/dq4/gallery/index.html">FC DQ4 참고</a><a href="../../../nds/dq4/index.html">NDS DQ4 참고</a><a href="../../dq5/gallery/index.html">SFC DQ5 참고</a></nav></header>
<div class="notice"><strong>첫 패치는 라이안 정면의 기술 검증용입니다.</strong><br>기존 라이안 정면 정지 자세만 사용자 확인을 받았습니다. 팔레트를 맞춘 새 색은 미확인이고, 두 번째 정면 프레임은 라이안 머리와 DQ5의 원래 몸이 섞입니다. 다른 방향은 DQ5 원본을 유지합니다.</div>
<div class="controls" aria-label="미리보기 설정">
<label>배율<select id="scale"><option value="1">1× 실제 크기</option><option value="2">2×</option><option value="4" selected>4×</option><option value="8">8×</option></select></label>
<label>방향<select id="direction"><option value="0">아래 · 정면</option><option value="1">왼쪽</option><option value="2">오른쪽</option><option value="3">위 · 후면</option></select></label>
<label>보기<select id="view"><option value="frame">한 프레임</option><option value="sheet">전체 시트</option></select></label>
<label>프레임<select id="frame"><option value="0">0 · 첫 자세</option><option value="1">1 · 두 번째 자세</option></select></label>
<button id="play" type="button" aria-pressed="false">보행 비교 재생</button><span id="position" class="counter" aria-live="polite"></span></div>
<section id="rom"><h2>ROM에 기록되는 그림</h2><p class="muted">같은 배율로 원본 색과 팔레트 변환 결과를 비교합니다. 16×24 정면 단독 이미지는 방향·프레임 선택에 따라 바뀌지 않습니다.</p><div id="rom-cards" class="grid"></div><details><summary>ROM 변환 검사 기록 · 에뮬레이터 검증과 구분</summary><pre id="verification"></pre><p class="muted">압축·역변환 통과는 실제 게임 플레이 검증을 뜻하지 않습니다. 아래 기록의 에뮬레이터 상태와 검증 범위를 확인하세요.</p></details></section>
<section id="drafts"><h2>인물 제작 시안</h2><p class="muted">아래 9명은 직접 작성한 픽셀 원본입니다. 이 시트 전체가 이번 패치에 들어간 것은 아닙니다. 행은 아래·왼쪽·오른쪽·위, 열은 두 자세입니다.</p><div id="draft-cards" class="grid"></div></section>
<details><summary>제작 출처와 산출물 메타데이터</summary><pre id="provenance"></pre><a href="../sprites/index.json">스프라이트 메타데이터 JSON</a> · <a href="../rom/index.json">ROM 비교 메타데이터 JSON</a></details>
<noscript><p>프레임 비교에는 JavaScript가 필요합니다. <a href="../sprites/index.json">시트 목록</a>과 <a href="../rom/index.json">ROM 비교 이미지 목록</a>에서 PNG를 열 수 있습니다.</p></noscript>
<footer>PNG는 원래 크기로 저장하고 화면에서만 확대합니다. IPS·ROM 파일은 이 갤러리에 복사하지 않습니다.</footer>
</main><script id="gallery-data" type="application/json">__DATA__</script><script>
'use strict';
const data=JSON.parse(document.getElementById('gallery-data').textContent), cards=[];
const el=id=>document.getElementById(id);
function addCard(parent,item){
 const article=document.createElement('article');article.className='card';
 const stage=document.createElement('div');stage.className='stage';
 const canvas=document.createElement('canvas');canvas.setAttribute('role','img');canvas.setAttribute('aria-label',item.label+' 픽셀 미리보기');stage.append(canvas);
 const title=document.createElement('h3');title.textContent=item.label;
 const tag=document.createElement('span');tag.className='tag';tag.textContent=item.status_label;
 const description=document.createElement('p');description.className='muted';description.textContent=item.description;
 const link=document.createElement('a');link.className='download';link.href='../'+item.path;link.textContent='원본 PNG · '+item.width+'×'+item.height;
 article.append(stage,title,tag,description,link);el(parent).append(article);
 const image=new Image();const card={canvas,image,item};cards.push(card);image.onload=draw;
 image.onerror=()=>{description.textContent='이미지를 읽지 못했습니다. 원본 PNG 경로를 확인하세요.';description.className='error';};image.src=link.href;
}
data.rom.forEach(x=>addCard('rom-cards',x));data.sprites.forEach(x=>addCard('draft-cards',x));
el('verification').textContent=JSON.stringify({visual_status:data.manifest.visual_status,scope:data.manifest.scope,compiler_verification:data.manifest.verification,runtime_evidence:data.runtime_evidence||'별도 에뮬레이터 검증 기록 없음'},null,2);
el('provenance').textContent=JSON.stringify(data.provenance,null,2);
function draw(){
 const scale=Number(el('scale').value),row=Number(el('direction').value),col=Number(el('frame').value),sheet=el('view').value==='sheet';
 for(const {canvas,image,item} of cards){if(!image.complete||!image.naturalWidth)continue;
 const full=sheet||item.width===16,w=full?item.width:16,h=full?item.height:24;
 canvas.width=w;canvas.height=h;canvas.style.width=w*scale+'px';canvas.style.height=h*scale+'px';
 const ctx=canvas.getContext('2d');ctx.imageSmoothingEnabled=false;ctx.clearRect(0,0,w,h);ctx.drawImage(image,full?0:col*16,full?0:row*24,w,h,0,0,w,h);
 }
 el('position').textContent=sheet?'전체 시트':el('direction').selectedOptions[0].text+' / 프레임 '+col;
}
let timer=null;
function stop(){clearInterval(timer);timer=null;el('play').textContent='보행 비교 재생';el('play').setAttribute('aria-pressed','false');}
for(const id of ['scale','direction','view','frame'])el(id).addEventListener('change',()=>{if(id==='frame'||id==='view')stop();draw();});
el('play').addEventListener('click',()=>{if(timer){stop();return;}el('view').value='frame';el('play').textContent='재생 멈춤';el('play').setAttribute('aria-pressed','true');timer=setInterval(()=>{el('frame').value=el('frame').value==='0'?'1':'0';draw();},350);draw();});
document.addEventListener('visibilitychange',()=>{if(document.hidden)stop();});draw();
</script></body></html>'''


def provenance():
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    return {
        "source_repository": "perfectacle/sfc-dq4",
        "source_commit": commit,
        "source_files": {
            str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (Path(__file__).resolve(), ROOT / "sfc/dq4/tools/dq4sprites.py")
        },
        "art_source": "sfc/dq4/tools/dq4sprites.py의 직접 작성한 색 번호 행렬",
        "references": "FC/NDS DQ4는 복장·색 참고, SFC DQ5는 실측 규격 참고",
        "approval": "원본 라이안 정면 정지 한 장만 확인. 팔레트 변환본과 나머지 시안 미확인",
        "regenerate": "uv run --locked python sfc/dq4/tools/dq4romgallery.py --input work/dq4-rom-assets --out <private-assets>/sfc/dq4",
    }


def generate(source, output):
    manifest = json.loads((source / "manifest.json").read_text())
    if manifest.get("schema_version") != 1:
        raise ValueError("unsupported ROM manifest schema")
    runtime_evidence = None
    evidence_path = source / "emulator-verification.json"
    if evidence_path.exists():
        runtime_evidence = json.loads(evidence_path.read_text())
        if runtime_evidence.get("schema_version") != 1 or runtime_evidence.get("rom_sha1") != manifest.get("output_sha1"):
            raise ValueError("emulator evidence does not match the generated ROM")
        rom_name = manifest["files"]["rom"]
        if not isinstance(rom_name, str) or Path(rom_name).name != rom_name:
            raise ValueError("expected a plain ROM filename")
        if hashlib.sha1((source / rom_name).read_bytes()).hexdigest() != runtime_evidence["rom_sha1"]:
            raise ValueError("emulator evidence ROM hash mismatch")
    images = {}
    for key, size in ROM_IMAGES.items():
        filename = manifest["files"][key]
        if not isinstance(filename, str) or Path(filename).name != filename:
            raise ValueError(f"{key}: expected a plain image filename")
        if hashlib.sha256((source / filename).read_bytes()).hexdigest() != manifest["file_sha256"][key]:
            raise ValueError(f"{key}: image hash differs from ROM manifest")
        image = Image.open(source / filename)
        image.load()
        if image.size != size or image.mode != "P" or image.info.get("transparency") != 0:
            raise ValueError(f"{key}: expected indexed transparent image of size {size}")
        images[key] = (filename, image)
    origin = provenance()
    sprites = []
    for name in SPRITE_NAMES:
        sheet = build_sheet(name).crop((0, 0, 32, 96))
        item = {
            "name": name, "label": NAMES[name], "path": f"sprites/{name}.png",
            "width": 32, "height": 96, "frame": [16, 24],
            "rows": ["아래", "왼쪽", "오른쪽", "위"], "cols": ["첫 자세", "두 번째 자세"],
            "approval": "front_stationary_only" if name == "ragnar" else "draft",
            "rom_status": "not_inserted_as_sheet",
            "status_label": "정면 정지만 확인" if name == "ragnar" else "미확인 시안",
            "description": "원본 정면 정지 자세만 확인. 다른 방향·보행은 시안입니다." if name == "ragnar" else "복장·색과 방향별 자세의 확인이 필요한 제작 시안입니다.",
        }
        sprites.append(item)
        destination = output / item["path"]
        destination.parent.mkdir(parents=True, exist_ok=True)
        sheet.save(destination, transparency=0)
    labels = {
        "original_sheet": ("DQ5 원래 주인공", "원본 ROM 참고", "세트 82의 원래 그림입니다. 비교용으로만 표시합니다."),
        "source_front": ("라이안 · 원본 정면", "기존 정지 자세 확인", "직접 그린 원본의 색입니다. 기존 확인은 이 정지 자세에 한정됩니다."),
        "mapped_front": ("라이안 · 팔레트 변환", "새 색 미확인", "다른 인물의 공유 팔레트를 바꾸지 않도록 DQ5의 색으로 맞춘 결과입니다."),
        "sheet": ("패치 ROM · 세트 82", "부분 교체 · 시각 미확인", "정면 첫 자세가 교체됩니다. 둘째 자세는 원래 몸과 혼합되며 다른 방향은 DQ5 원본입니다."),
    }
    rom = []
    for key, (filename, image) in images.items():
        label, status, description = labels[key]
        item = {"key": key, "label": label, "status_label": status, "description": description,
                "path": f"rom/{filename}", "width": image.width, "height": image.height}
        rom.append(item)
        destination = output / item["path"]
        destination.parent.mkdir(parents=True, exist_ok=True)
        image.save(destination, transparency=0)
    for directory, content in (
        ("sprites", {"provenance": origin, "sprites": sprites}),
        ("rom", {"provenance": origin, "images": rom, "manifest": manifest, "runtime_evidence": runtime_evidence}),
    ):
        (output / directory / "index.json").write_text(json.dumps(content, ensure_ascii=False, indent=2) + "\n")
        (output / directory / "SOURCE.txt").write_text(
            f"sfc-dq4 커밋: {origin['source_commit']}\n명령: {origin['regenerate']}\n"
            + ("롬: 원본 픽셀 제작물, ROM 불필요\n" if directory == "sprites" else f"롬: dq5.sfc, SHA-1 {manifest['source_sha1']}; 로컬 패치 결과는 manifest 참고\n")
        )
    data = {"sprites": sprites, "rom": rom, "manifest": manifest, "provenance": origin, "runtime_evidence": runtime_evidence}
    encoded = json.dumps(data, ensure_ascii=False).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    gallery = output / "gallery/index.html"
    gallery.parent.mkdir(parents=True, exist_ok=True)
    gallery.write_text(HTML.replace("__DATA__", encoded))
    return gallery


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path("work/dq4-rom-assets"))
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        gallery = generate(args.input, args.out)
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"dq4romgallery: {error}\n")
    print(f"Gallery: {gallery}")


if __name__ == "__main__":
    main()
