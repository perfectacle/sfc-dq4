# 한글 타이틀과 오프닝

이 문서는 정지 타이틀과 초기 DQ5 연결 실험의 기록입니다. 현재 사용자 채택본의 Mode 3 레이어 구성·빌드·재검증은 [타이틀 애니메이션](dq4-title-animation.md)을 따릅니다. 아래 Mode 1·890타일·정지 롬 해시는 현재 애니메이션 규격과 구분합니다.

선택된 한글 타이틀은 「드래곤 퀘스트 IV / 인도받은 자들」입니다. 고해상도 제작 원본은 `tools/dq4art/title-ko-v2.png`, 실제 표시의 기준은 256×224 색 번호 이미지 `tools/dq4art/title-ko.png`입니다. 부제를 더 크게 만든 비교안 대신 작은 부제의 v2가 사용자 확인을 받았습니다.

## 선택된 픽셀을 보존하기

타이틀은 매번 고해상도 그림을 다시 줄이지 않습니다. `dq4titleassets.py`가 선택된 실제 크기 원본을 그대로 읽어 SFC 데이터로 만듭니다. 사용하지 않는 팔레트의 색 번호 0만 공통 배경색으로 맞추며, 보이는 RGB 픽셀은 바꾸지 않습니다.

| 항목 | 값 |
| --- | --- |
| 화면 | 256×224, 224라인 |
| 사용 색 | 117색 |
| BG 팔레트 | 16색 × 8개, BGR555 |
| 고유 타일 | 890개, 4bpp |
| CHR | 28,480바이트 |
| 타일맵 | 32×32, 2,048바이트 |
| 팔레트 | 256바이트 |
| 기준 PNG SHA-256 | `6db3d70380dd4727f3b083dae1fdb0cf501f07d84888b0462df565d65d5b392f` |

타일맵의 표시 영역 밖 네 행은 타일 0으로 채웁니다. 타일 0은 빈 그림이라고 보장하지 않으므로 이 맵을 그대로 스크롤해 아래 여백을 노출하면 안 됩니다. 원본 그림은 용·로고·구름이 합쳐진 한 장입니다. 서로 다른 층처럼 움직이려면 가려진 배경과 별도 마스크를 새로 만들어야 합니다.

```sh
uv run --locked python sfc/dq4/tools/dq4titleassets.py --out work/dq4-title-build
uv run --locked python sfc/dq4/tools/dq4titleassets.py \
  --out work/dq4-title-build --assets-dir "$ASSETS/sfc/dq4"
```

두 번째 명령은 비공개 에셋 저장소의 `gfx/screens/title/`과 `gallery/index-title.html`을 만듭니다. PNG·4배 미리보기·CHR·MAP·PAL·해시와 확인 상태를 기록한 `manifest.json`이 생성됩니다.

## 독립 SFC 미리보기

`dq4titlepreview.py`와 `dq4titlepreview.asm`은 타이틀만 보여 주는 64KiB LoROM을 만듭니다. DQ5 원본을 필요로 하지 않으며 DQ5 삽입본과 구분합니다. BG1 mode 1, 4bpp 타일과 8팔레트를 DMA로 올립니다. `lua/dq4titlecheck.lua`는 화면과 VRAM·CGRAM을 읽기만 합니다.

```sh
ASAR=/path/to/asar uv run --locked python sfc/dq4/tools/dq4titlepreview.py \
  --input work/dq4-title-build --out work/dq4-title-preview/title-preview.sfc
```

Asar 1.91과 MesenCE 2.2.1에서 120프레임을 실행했습니다. 선택된 v2와 실제 화면 RGB 57,344픽셀이 모두 일치하고 CHR·타일맵·팔레트도 바이트 단위로 일치했습니다. 수직 스크롤 `FFFF`는 SFC의 첫 표시 스캔라인을 보정해 첫 이미지 행을 맞추는 설정입니다.

## NDS판의 실제 연출 참고

로컬 NDS DQ4 일본판과 한글패치판을 desmume libretro 코어로 실행했습니다. 그래픽·RAM을 고정하지 않고 부팅과 입력을 관찰했습니다. 실행한 코어는 DeSmuME 소스 커밋 `95b4d798731caa809125b6c3c11d17cc332ff6ef`의 로컬 빌드와 바이너리 SHA-256이 일치했습니다. 화면 캡처와 소리 포함 영상은 로컬 `work/nds-title-reference/`에 두며 원작 자료를 이 저장소에 커밋하지 않습니다.

두 화면에 이어지는 구름과 떠 있는 천공성을 배경으로 크레딧이 지나갑니다. 약 26초에 흰 로고 실루엣이 나타나고 약 28초에 로고와 IV가 본래 색으로 바뀝니다. 위 화면의 용은 날개와 위치가 계속 바뀌며, 약 60초에는 하늘이 주황색으로 변합니다. 타이틀 대기 중 A 입력은 검은 화면을 거쳐 모험의 서 메뉴로 이어집니다.

SFC에서는 두 화면과 3D 용의 움직임을 그대로 재현하는 대신, 선택된 타이틀과 DQ5의 기존 게임 구조에 맞춰 도입·색 전환·입력·암전의 흐름을 구성합니다. 실제 관찰한 NDS 동작과 SFC에서 새로 구성한 연출을 구분합니다.

## DQ5 타이틀 구간 연결

독립 미리보기와 별도로 `dq4titlepatch.py`·`dq4titlepatch.asm`이 원본 일본판 DQ5에 타이틀을 연결합니다. 원본의 SHA-1은 `1c47ed62c561d7965fe5dc2a03f4c37feb4a46b5`이며, 원본 파일을 덮어쓰지 않습니다. 결과 롬과 IPS는 로컬 `work/`에 둡니다.

| 위치 | 역할 |
| --- | --- |
| `00:A6ED` → `03:FDE8` | 원래 타이틀 진입. 실행 추적으로 확인 |
| `03:FDFB` | 기존 타이틀 초기화 뒤 새 루틴 `30:8000`으로 연결 |
| `03:FE5C` | 원래 타이틀 종료 처리로 복귀 |
| `00:A70C` | 메뉴 음악 명령을 새 타이틀로 옮긴 뒤 중복 시작을 막는 위치 |
| `24:FE9A`·`24:FE44` | 기존 사운드 명령과 처리 대기. 곡 인자 `$10`(사운드 명령 `$01`) 사용 |
| `00:9506` | 기존 NMI 대기·입력 갱신 경로 |
| `7E:0033` | NMI가 매 프레임 읽는 세로 스크롤. 타이틀 동안 `FFFF`, 복귀 전에 원래 값 복원 |
| `7E:3914` | 원래 팔레트 사본. 타이틀이 끝날 때 화면 팔레트를 복원 |

1.5MiB 원본의 마지막 512KiB 미러를 유지하며 2MiB로 확장합니다. 루틴은 `30:8000`, CHR은 `31:8000`, 타일맵은 `32:8000`, 팔레트는 `32:8800`, 광택 단계별 팔레트는 `32:A000`에 둡니다. 선언한 패치 영역 밖의 변경을 빌더가 거부합니다.

새 타이틀은 원래 사운드·메뉴 초기화를 재사용합니다. 기존 DQ5 크레딧 구간은 무음이고 메뉴 진입 때 음악이 시작되는 것이 관찰되어, 그 곡 인자 `$10`(사운드 명령 `$01`)의 실행을 타이틀로 옮겼습니다. 메뉴에 들어가 같은 음악을 다시 시작하지 않게 합니다. NDS 음악 데이터를 복사하지 않습니다.

연출은 어둠 속에서 창이 열리는 도입과 밝기 증가, 로고의 짧은 광택, 대기, 입력 뒤 암전으로 구성합니다. 광택은 로고 사각형 안에서만 사용되는 따뜻한 색 7개에만 적용합니다. 부제·구름을 함께 번쩍이게 하지 않으며 효과의 처음과 끝은 원래 팔레트와 같습니다. 정지 타이틀에 있는 용을 독립된 3D 모델처럼 움직이는 재현은 아닙니다.

A 또는 Start를 누르면 약 0.5초 동안 어두워진 뒤 원래 메뉴로 돌아갑니다. 도입 중 눌러 둔 입력으로 바로 넘어가지 않도록 입력 해제를 확인하며, 타이틀 확인 입력이 다음 메뉴 선택까지 이어지지 않도록 복귀 전에도 해제를 기다립니다.

```sh
uv run --locked python sfc/dq4/tools/dq4titleassets.py --out work/dq4-title-build
ASAR=/path/to/asar uv run --locked python sfc/dq4/tools/dq4titlepatch.py \
  --rom rom/dq5.sfc --input work/dq4-title-build \
  --out work/dq4-title-integrated/dq4-title.sfc
```

빌드 보고서는 입력·출력 해시, 패치 위치, 에셋 해시, 광택 색과 IPS 적용 일치를 기록합니다. 실제 에뮬레이터 검증은 별도 관찰 결과와 함께 판단합니다.

## 통합 롬 실행 검증

MesenCE 2.2.1에서 메모리 주입 없이 부팅·입력·소프트 리셋을 검사했습니다. 검증한 롬 SHA-1은 `ee6fa4db691c791ed67379594c6094433e0be2f4`입니다. 로컬 `work/dq4-title-integrated/emulator-verification.json`에 해시와 관찰 경로를 기록합니다.

| 검사 | 결과 |
| --- | --- |
| 대기·리셋 뒤 타이틀 | 기준 RGB 57,344픽셀 모두 일치 |
| VRAM·팔레트 | CHR 28,480·맵 2,048·팔레트 256바이트 일치 |
| 광택 | 로고 안 919픽셀만 변화하고 원래 색으로 복귀 |
| A·Start | 420프레임 입력 뒤 456프레임에 원래 메뉴 진입 |
| 부팅부터 Start 유지 | 타이틀 유지, 해제 후 새 입력으로만 진행 |
| 메뉴 화면 | 원본 DQ5 화면 및 CGRAM 512바이트 일치 |
| 소프트 리셋 | 두 번째 타이틀과 메뉴 정상 진입 |
| 음악 | 부팅당 한 번 시작, 메뉴 뒤에도 DSP 출력 유지 |
| 새 게임 | 별도 ROM 이름과 빈 저장 환경에서 이름 입력 화면까지 정상 진입 |

```sh
mkdir -p work/dq5-title-research/replay-a
OUT="$PWD/work/dq5-title-research/replay-a" MAXF=700 EVERY=10 SEQ="a@420:2" \
  "$MESENCE" --testrunner "$PWD/work/dq4-title-integrated/dq4-title.sfc" \
  "$PWD/sfc/dq4/tools/lua/dq4titleintegrationcheck.lua"
```

`MESENCE`는 MesenCE 실행 파일 경로입니다. 관찰 스크립트는 화면·메모리 읽기와 컨트롤러 입력·리셋만 사용합니다. 실행 영상은 무음이며 음악은 별도 DSP 기록으로 확인했습니다. 실제 SFC 기기에서의 검증과 전체 게임 진행 검사는 하지 않았습니다.
