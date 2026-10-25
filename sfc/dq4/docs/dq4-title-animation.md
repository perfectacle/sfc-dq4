# 채택된 한글 타이틀 애니메이션과 재현 방법

2026-10-25에 사용자가 실제 MesenCE 화면을 보고 채택한 기준은 성 왼쪽 아래 조각을 제거한 롬입니다. 이 문서는 그 결과를 다시 만들고 다음 작업으로 이어 가기 위한 명세입니다. 제작 과정은 [타이틀 연결](../journal/2026-10-25-51-title.md)부터의 일지에 남기며, [정지 타이틀 형식](dq4-title-format.md)의 초기 Mode 1 구현과 현재 Mode 3 애니메이션을 구분합니다.

## 기준 입력과 결과

| 항목 | 값 |
| --- | --- |
| 기준 코드 커밋 | `a934dccb28ae2453b0b8f605c1fe90598e797143` |
| 원본 DQ5 일본판 롬 | `rom/dq5.sfc`, 1,572,864바이트, 복사기 헤더 없음 |
| 원본 롬 SHA-1 | `1c47ed62c561d7965fe5dc2a03f4c37feb4a46b5` |
| 채택 결과 롬 | 2,097,152바이트, IPS로 원본에 적용 가능 |
| 채택 결과 SHA-1 | `639b221dc9c388ecb786855eecaa312d670eda51` |
| 고정 그림 | `sfc/dq4/tools/dq4art/title-ko.png`, 256×224 색 번호 PNG |
| 고정 그림 SHA-256 | `6db3d70380dd4727f3b083dae1fdb0cf501f07d84888b0462df565d65d5b392f` |
| 화면 실행 검증 | MesenCE 2.2.1, 소스 커밋 `20ba206cef5ba207c21203176d02cb9f43dda9fb` |
| 사용자 확인 | 2026-10-25, 왼쪽 아래 조각 제거본을 보고 채택 |

롬·IPS·덤프·실행 캡처는 저장소에 넣지 않습니다. 사용자가 준비한 원본 롬과 커밋된 코드·그림으로 결과를 재생성합니다. 아래 예시의 출력 이름은 바꿀 수 있으며, 이름은 롬 내용과 해시에 영향을 주지 않습니다. 이후 코드가 바뀌어 같은 결과가 필요할 때는 이 기준 커밋을 별도 워크트리로 체크아웃합니다.

## 다시 사용하는 소스와 도구

아래 그림 경로는 `sfc/dq4/tools/dq4art/` 기준입니다. 별도 레이어 그림의 제작 출처와 프롬프트 요약은 [provenance.json](../tools/dq4art/title-animation/provenance.json)에 있습니다. 프롬프트 요약은 제작 경위이며 같은 그림의 재생성을 보장하지 않습니다. 동일한 롬을 재현할 때는 커밋된 PNG를 그대로 사용합니다.

| 소스 | 현재 용도 |
| --- | --- |
| `title-ko.png` | 로고·IV·부제와 성, 성 주변 고정 구름의 원래 픽셀 |
| `title-animation/title-glyph-mask.png` | 글자·장식의 원래 픽셀 10,256개를 선택하는 이진 마스크 |
| `title-animation/dragon-rig.png` | 몸통과 두 날개를 분리해 자세를 만드는 원본 |
| `title-animation/sky.png` | 고정 성을 포함하지 않는 이동 하늘 |
| `title-animation/front-cloud.png` | 성 앞을 지나는 둥근 구름의 원본 |

`background.png`, `dragon-poses.png`, `dragon-poses-8.png`, `cloud-strip.png`는 이전 실험의 소스입니다. 현재 레이어 빌드의 직접 입력과 혼동하지 않습니다. 현재 용·구름 움직임은 새로 만든 SFC용 연출이며 NDS 그래픽이나 소리를 추출해 넣은 결과가 아닙니다. NDS 실행은 구도·등장 순서·움직임을 참고하는 데 사용했습니다.

빌드 흐름은 다음과 같습니다.

1. `dq4titlelayers.py`가 고정 그림의 마스크, 12개 날개 자세, 이동 하늘·앞 구름을 CHR·타일맵·팔레트·OAM·차분 전송표로 만듭니다.
2. 같은 도구의 `read_pack()`이 파일 해시와 크기, 원래 전경 픽셀, 두 번의 차분 재생, ROM 뱅크 경계와 전송 예산을 확인합니다.
3. `dq4titlelayerpatch.py`가 검증된 에셋과 `dq4titlelayers.asm`을 Asar로 조립하고 DQ5 원본의 타이틀 진입을 연결합니다. ROM·IPS·검사 JSON을 만듭니다.
4. `sfc/dq4/tools/lua/dq4titleintegrationcheck.lua`를 MesenCE에서 실행해 실제 화면·VRAM·OAM·CGRAM과 입력 후 복귀를 관찰합니다. 이 프로브는 게임 메모리를 덮어쓰지 않습니다.

에셋 생성과 `read_pack()` 통과만으로 에뮬레이터 검증을 완료했다고 기록하지 않습니다. 빌드 JSON의 `verification.emulator`는 실제로 `not_run`입니다.

## 채택된 그림과 동작

용의 몸통은 알파 연결 요소 전체를 추출합니다. 날개는 작은 진폭의 12자세를 각각 약 10~11게임 프레임 유지하며, 128게임 프레임에 순환합니다. 화면 처리·입력·OAM·스크롤은 매 게임 프레임 갱신하지만, 그림을 128개의 서로 다른 자세로 바꾸지는 않습니다. 몸통은 기준 위치에서 위아래 2픽셀씩, 총 4픽셀 범위로 부유합니다.

뒤쪽 하늘은 전체 화면에서 같은 속도로 왼쪽으로 흐릅니다. 스크롤은 `(counter >> 3) & 127`이므로 8게임 프레임마다 1픽셀 이동합니다. 앞 구름은 64×32 그림을 가로로 반복하며, y=168에서 4게임 프레임마다 1픽셀 이동합니다. 화면 아래쪽만 다른 속도로 움직이는 수평 구분선은 없습니다.

성 주변의 청보라 구름 일부는 성과 같은 전경에 남습니다. 움직이는 앞 구름이 지나간 뒤에도 받침이 남도록 한 것입니다. 사용자가 제거를 요청한 왼쪽 하단은 표시 마스크에서 x=180~207, y=185~223을 비웁니다. 실제 제거된 원본 전경은 y=185~199의 313픽셀이며, 오른쪽 성과 구름 받침은 남습니다.

글자·마름모 장식과 성이 공유하는 8×8 타일은 주의가 필요합니다. 원래 글자 마스크 10,256픽셀 중 부제 오른쪽 장식선 끝 30픽셀은 성과 같은 낮은 우선순위에 둡니다. 나머지 10,226픽셀은 `protected_glyph_mask()`가 보호합니다. 장식선 끝은 x=176~185, y=182~184에 있으며, 선을 원본 그림에서 지우는 것은 아닙니다. 앞 구름에 가려질 수 있는 표시 순서만 다릅니다.

## 표시·전송·메뉴 복귀 규격

현재 구현은 Mode 3의 BG1 8bpp와 BG2 4bpp입니다. 일부 로고 타일은 검정을 포함한 16색을 모두 쓰므로 4bpp에서 투명색을 추가할 수 없습니다. BG1 색 번호 0은 투명, 16은 불투명 검정으로 사용해 원래 로고 RGB를 보존합니다.

| 요소 | 표시 | 깊이 |
| --- | --- | --- |
| 이동 하늘 | BG2 | 가장 뒤 |
| 성·구름 받침·장식선 끝 | BG1 낮은 우선순위 | 하늘 앞, 앞 구름 뒤 |
| 용·앞 구름 | OBJ | 성 앞 |
| 로고·IV·부제 글자·마름모 | BG1 높은 우선순위 | 앞 구름 위 |

타일의 우선순위는 픽셀마다가 아니라 8×8 타일마다 정합니다. 앞 구름 영역에서는 보호 글자 이외의 성 픽셀이 높은 우선순위를 물려받지 않도록 회귀 검사합니다.

| 항목 | 채택 기준 |
| --- | --- |
| BG1 전경 | 280타일, 상한 384타일 |
| BG2 하늘 | 443타일 |
| 용 OBJ | 32×32 15개, 두 CHR 페이지를 번갈아 사용 |
| 앞 구름 OBJ | 32×32 9개, 두 페이지의 마지막 32×32 빈 슬롯에 절반씩 보관 |
| 가시 주사선 예산 | 최대 9스프라이트·33타일, 하드웨어 상한 32스프라이트·34타일 |
| 최대 타일 차분 전송 | 1,376바이트, 최대 9개 전송 구간 |
| 매 프레임 OAM 전송 | 기본 544바이트 + 앞 구름 68바이트 |
| 최대 합계 | 1,988바이트 |

미사용 OBJ와 가로 반복 끝의 완전히 화면 밖 OBJ는 Y=224로 숨깁니다. X만 화면 밖으로 보내면 보이지 않는 OBJ도 타일 인출 예산을 소비할 수 있습니다. Y=240은 32픽셀 OBJ가 화면 위로 감길 수 있어 사용하지 않습니다.

타이틀 진입은 DQ5의 초기화 뒤 CPU 주소 `03:FDFB`에서 확장 루틴 `30:8000`으로 연결합니다. A·Start 입력 후에는 암전하고, 버튼 해제를 기다린 뒤 원래 글꼴·팔레트·화면 설정을 복원해 DQ5 메뉴로 돌아갑니다. 타이틀 표시 때문에 바꾼 WRAM 값과 PPU 설정도 복원합니다.

배경음악은 DQ5 원본 메뉴곡입니다. 곡 인자 `$10`과 사운드 명령 `$01`을 관찰했으며, 원래 메뉴 직전 재생을 타이틀 진입 시점으로 옮기고 중복 실행을 막았습니다. DQ4 음악을 이식하거나 샘플·시퀀스를 교체하지 않았습니다. 메뉴에서도 같은 곡이 이어집니다.

## 수정 위치와 롬 배치

다음 변경은 해당 생성 함수에서 시작합니다. 생성된 `work/` 바이너리를 직접 수정하면 입력 해시와 재생 검사에서 거부됩니다.

| 바꿀 내용 | 코드의 기준점 |
| --- | --- |
| 고정 전경·성 받침·제거 영역 | `dq4titlelayers.py`의 `foreground()` |
| 글자와 장식선의 깊이 | `glyph_mask()`, `protected_glyph_mask()`와 타일 우선순위 |
| 몸통 추출·날개 진폭·자세 유지 | `dragon_frames()` |
| 배경 반복·색 선택 | `background()` |
| 앞 구름 그림·OBJ 반복 | `cloud_assets()`, `add_cloud_tiles()`, `cloud_oam()` |
| 차분 전송표·예산 | `pack_payload()`, `read_pack()` |
| 실제 갱신·입력·메뉴 복귀 | `dq4titlelayers.asm`의 `Motion`, `Frame`, `FadeOut` |

아래는 `dq4titlelayerpatch.py`의 현재 배치입니다. 파일 오프셋과 CPU 주소를 구분하며, 초기 정지 타이틀의 배치표를 현재 롬에 적용하지 않습니다.

| 내용 | 파일 오프셋 | CPU 주소 |
| --- | --- | --- |
| 타이틀 코드 | `180000` | `30:8000` |
| 하늘 CHR | `188000` | `31:8000` |
| 하늘 타일맵 | `18D000` | `31:D000` |
| 전경 타일맵 | `18E000` | `31:E000` |
| BG 팔레트 | `18E800` | `31:E800` |
| 용·앞 구름 팔레트 | `18E900`, `18E920` | `31:E900`, `31:E920` |
| OAM 포인터 | `18EB00` | `31:EB00` |
| 전경 CHR | `190000` | `32:8000` |
| 용 차분 DMA 표 | `198000` | `33:8000` |
| OBJ 초기 두 페이지 | `1A0000` | `34:8000` |
| 앞 구름 OAM 표 | `1A8000` | `35:8000` |
| 차분 데이터·OAM | `1B0000` | `36:8000`부터 |

빌더는 허용 범위 밖의 기록, 원본 훅·헤더 불일치, 에셋 크기·해시 불일치를 거부합니다. `read_pack()`은 전경이 승인된 원본 픽셀과 마스크로 다시 만들어지는지, 두 주기 동안 차분 재생이 맞는지, 화면에 표시 중인 OBJ 페이지나 앞 구름 예약 타일을 덮어쓰지 않는지도 확인합니다.

## 재현: 빌드와 자동 검사

저장소 루트에서 실행합니다. [uv](https://docs.astral.sh/uv/), [Asar](https://github.com/RPGHacker/asar), [MesenCE](https://github.com/nesdev-org/MesenCE)가 필요합니다. `ASAR`와 `MESENCE`는 각 실행 파일의 경로이며, 앱 폴더가 아닙니다. 원본 롬은 사용자가 준비합니다. Python 의존성은 `uv.lock`으로 고정합니다. 이번 재현은 CPython 3.15.0, NumPy 2.5.4, Pillow 13.0.0, kr-patch-toolkit 0.8.0, Asar 1.91에서 같은 결과 해시를 확인했습니다.

```sh
export ASAR=/path/to/asar
export MESENCE=/path/to/Mesen
export TITLE_OUT="$PWD/work/dq4-title-baseline"
uv sync --locked
uv run --locked python sfc/dq4/tools/dq4titlelayers.py --out "$TITLE_OUT"
uv run --locked python sfc/dq4/tools/dq4titlelayerpatch.py \
  --rom rom/dq5.sfc --input "$TITLE_OUT" \
  --out "$TITLE_OUT/dq4-title-baseline.sfc"
uv run --locked python -m unittest discover \
  -s sfc/dq4/tools -p test_dq4titlelayers.py
```

채택 기준에서 검사 13개가 모두 통과합니다. `ASAR`를 내보내지 않았거나 로컬 원본 롬이 없으면 롬 빌드 검사는 건너뛰므로, `OK (skipped=...)`를 전체 통과로 기록하지 않습니다. 에셋 생성에는 1,024틱 합성 미리보기도 포함됩니다.

주요 출력은 다음과 같습니다.

| 출력 | 쓰임 |
| --- | --- |
| `title.png`, `animation.gif`, `frame-*.png` | 합성 시안 확인. 실제 에뮬레이터 캡처가 아님 |
| `layers.json` | 소스 해시, 타일 수, 차분 예산, 에셋 파일 해시 |
| `*.chr`, `*.map`, `*.pal`, `*.bin` | 롬에 들어가는 에셋과 전송표 |
| `dq4-title-baseline.sfc` | 실행할 결과 롬 |
| `dq4-title-baseline.ips` | DQ5 원본에 적용할 패치 |
| `dq4-title-baseline.json` | 입력·출력 해시, 기록 범위, IPS 동등성 검사 |

다음 명령은 채택 결과와 같은 롬인지 확인합니다.

```sh
uv run --locked python - <<'PY'
import hashlib, os
from pathlib import Path
path = Path(os.environ['TITLE_OUT']) / 'dq4-title-baseline.sfc'
actual = hashlib.sha1(path.read_bytes()).hexdigest()
assert actual == '639b221dc9c388ecb786855eecaa312d670eda51', actual
print(actual)
PY
```

용의 자세만 조정할 때는 먼저 다음 명령으로 `dragon.png`, `dragon.gif`, `poses.png`, `rig-profile.json`을 확인합니다. 이는 용만 보는 시안이며 전체 레이어 빌드와 실제 롬 확인을 대체하지 않습니다.

```sh
uv run --locked python sfc/dq4/tools/dq4titlelayers.py \
  --rig-only --out work/title-rig-preview
```

## 재현: 실제 실행과 관찰 자료

같은 이름의 저장 파일·세이브스테이트가 실험에 끼어들지 않도록 새 관찰 디렉터리에 고유한 롬 이름으로 복사합니다. `OUT`은 절대 경로이며 실행 전에 존재해야 합니다. 아래 명령은 커밋된 관찰 프로브만 사용하며, 과거 로컬 `verify.py`가 없어도 실행할 수 있습니다.

```sh
export TITLE_CHECK="$(mktemp -d "$PWD/work/title-baseline-check.XXXXXX")"
mkdir -p "$TITLE_CHECK/phases" "$TITLE_CHECK/menu"
export TITLE_IDLE_ROM="$TITLE_CHECK/idle-${TITLE_CHECK##*/}.sfc"
export TITLE_MENU_ROM="$TITLE_CHECK/menu-${TITLE_CHECK##*/}.sfc"
cp "$TITLE_OUT/dq4-title-baseline.sfc" "$TITLE_IDLE_ROM"
cp "$TITLE_OUT/dq4-title-baseline.sfc" "$TITLE_MENU_ROM"
OUT="$TITLE_CHECK/phases" MAXF=1280 FROM=300 EVERY=64 SEQ="" \
  TRACE_DMA=1 MOTION_PC=30829e \
  "$MESENCE" --testrunner "$TITLE_IDLE_ROM" \
  "$PWD/sfc/dq4/tools/lua/dq4titleintegrationcheck.lua"
OUT="$TITLE_CHECK/menu" MAXF=700 FROM=580 EVERY=20 SEQ="a@420:2" \
  "$MESENCE" --testrunner "$TITLE_MENU_ROM" \
  "$PWD/sfc/dq4/tools/lua/dq4titleintegrationcheck.lua"
```

첫 관찰 명령은 프레임 320부터 1280까지 64프레임 간격으로 16개 표본을 남깁니다. 메뉴 명령은 프레임 420에서 A를 두 프레임 누르고 메뉴 복귀를 관찰합니다. `MOTION_PC=30829e`는 **위 해시의 기준 롬**에서 확인한 `Motion` 루틴 CPU 주소입니다. 어셈블리를 바꾼 뒤에는 그대로 쓰지 말고 Asar의 `title_motion` 출력으로 다시 확인하거나, 단순 화면 관찰에서는 이 변수를 생략합니다.

관찰 결과는 `sNNNN.png`(화면), `vNNNN.bin`(VRAM), `oNNNN.bin`(OAM), `cNNNN.bin`(CGRAM), `pNNNN.txt`(PPU 상태), `events.txt`, `audio.tsv`입니다. 옵션을 켰으면 `dma.tsv`, `motion.tsv`도 남습니다. 프로브는 캡처·기록 도구이며 화면 일치를 자동으로 판정하지 않습니다. 비교할 때는 타일맵·우선순위·팔레트와 해당 카운터의 합성 결과를 함께 확인합니다.

빠른 테스트 실행에서 캡처된 표시 화면은 현재 VRAM보다 몇 틱 늦을 수 있습니다. 채택본의 16개 표본에서는 1틱 또는 3틱 차이가 관찰됐습니다. 파일 이름의 프레임만으로 같은 자세라고 단정하거나, 이 캡처를 이어 붙인 영상을 정상 속도의 프레임 속도 측정값으로 사용하지 않습니다.

직접 볼 때는 결과 롬 경로를 실행 파일에 넘깁니다. 앱만 실행해 최근 파일 목록을 표시한 것을 롬 실행으로 확인하지 않습니다.

```sh
"$MESENCE" "$TITLE_OUT/dq4-title-baseline.sfc"
```

## 검증 결과와 다음 변경의 기준

채택본 `639b221…`에 직접 수행한 검증은 다음과 같습니다.

- Asar 포함 자동 검사 13개 통과, 원본 롬 불변·IPS 적용 결과 동등성 확인
- 실제 화면 16장과 해당 위상 VRAM이 독립 합성과 일치
- A 입력 후 메뉴 화면 차이 0픽셀, CGRAM 512바이트 원본 일치
- 요청한 영역의 전경 잔여 0픽셀, 제거된 글자 픽셀 0, x=208 이후 성 유지
- 같은 구름 위치의 실제 화면 비교에서 변경 226픽셀이 모두 제거 마스크 안에 위치
- 실제 실행 화면을 본 사용자의 시각적 채택

최종 검증 당시 로컬 근거는 `work/castle-trim-verification/`의 `runtime-evidence.json`, `pack-evidence.json`, `visible-removal-evidence.json`, `visual-review.json`에 보존했습니다. 이 디렉터리는 커밋되지 않으며 새 체크아웃의 필수 입력이 아닙니다. 새 환경에서는 위 빌드·관찰 절차로 근거를 다시 만듭니다.

이 기록을 정리하면서도 잠긴 의존성으로 새 에셋·롬을 생성해 같은 SHA-1을 확인했습니다. 커밋된 Lua 프로브로 대기 구간의 화면·VRAM·OAM·CGRAM 표본 16개를 다시 남겼고, A 입력 후 메뉴 진입도 다시 관찰했습니다. 관찰 자료가 생성된 사실과 화면·메모리 일치 판정은 구분합니다.

이전 `8fb4658…`에서는 연속 1,001개 화면·OBJ·OAM·스크롤, A·Start·버튼 유지·리셋·메뉴 복귀·이름 입력을 확인했습니다. 그 뒤의 받침 추가본과 우선순위 수정본은 각각 화면 63장을 확인했습니다. 이 숫자를 최종 제거본에서 다시 수행한 검증으로 합산하지 않습니다.

다음에 그림·마스크를 바꾸면 구름이 성을 가리는 때와 완전히 지나간 때를 함께 확인합니다. CHR·OAM·런타임을 바꾸면 입력 유지·리셋·이름 입력도 새 결과 롬에서 다시 검사합니다. 실제 SFC 기기, 기존 저장 파일 불러오기, 게임 후반 전체 진행은 아직 검증하지 않았습니다. DQ5 메뉴 뒤 게임 내용을 DQ4로 바꾸는 작업은 이 타이틀의 범위 밖입니다.
