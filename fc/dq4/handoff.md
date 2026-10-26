# dq4 트랙 핸드오프

FC DQ4 원작을 분석하는 세션이 처음 읽는 문서입니다. 이 트랙의 목표, 지금 있는 것과 없는 것, 무엇부터 하면 되는지를 적습니다. 규칙은 [AGENTS.md](../../AGENTS.md), 남은 일 목록은 [todo.md](todo.md) 가 정본입니다. 세션을 마칠 때 이 문서의 「지금 상태」와 「다음에 할 일」을 고쳐 다음 세션에 넘깁니다.

## 목표

DQ4 의 내용(맵, 인물과 대사, 이벤트 흐름, 몬스터·아이템·주문·상점 표, 곡·효과음)을 DQ5 엔진에 옮기려면, 원작에서 그 데이터를 **롬만으로** 뽑아낼 수 있어야 합니다. 이 트랙은 FC DQ4(일본판 Rev A)의 데이터 형식을 풀고 이 폴더의 `tools/dq4*.py` 추출기와 `docs/dq4-*.md` 명세를 만듭니다. DQ5 쪽에 어떻게 넣을지는 dq5 트랙의 결과([dq5-handoff.md](../../sfc/dq5/handoff.md))와 맞춰 나중에 정합니다.

그래픽은 원작 데이터를 옮기지 않고 직접 그립니다. 원작 그래픽은 무엇을 그려야 하는지 확인하는 용도로만 봅니다.

## 지금 상태

SFC 로 옮길 데이터는 거의 모두 롬만으로 뽑을 수 있게 됐습니다. 영역마다 형식 문서와 디코더가 있고, 실제 화면·RAM 과 대조했습니다. 자세한 검증 숫자는 각 형식 문서의 「확인」 절, 과정은 [README](README.md#해킹-일지) 의 일지에 있습니다.

| 영역 | 문서 · 도구 | 실측으로 맞춘 것(대표) |
| --- | --- | --- |
| 롬·뱅크 | [dq4-rom-map.md](docs/dq4-rom-map.md), [dq4-bank-format.md](docs/dq4-bank-format.md) · `dq4bank.py` | BRK 뱅크 호출 1019건, x3 형식 길이 191곳 |
| 대사 | [dq4-text-format.md](docs/dq4-text-format.md) · `dq4text.py`(`export` 가 메시지 2633·창 문자열 109·이름 434 를 기호화 JSON/TSV 로) | 왕복 검사 차이 0, 전투·필드 창 덤프 170개 |
| 창 | 같은 문서 「창 레코드」 · `dq4text.py windows --layout --meaning` | 창 115개 중 테두리 111개, 실제 장면 66번, 항목 루틴 66개 뜻 |
| 맵 | [dq4-map-format.md](docs/dq4-map-format.md) · `dq4map.py` | 맵 **279개**(그룹 48 포함), 경계 278곳 0 다름 |
| 필드 | [dq4-field-format.md](docs/dq4-field-format.md) · `dq4field.py` | 필드 0(세계 250×250)·1(ゴットサイド 섬)·3(闇の世界 62×54). 2 는 빈 자리 |
| 블록·통행·출구 | [dq4-block-format.md](docs/dq4-block-format.md) · `dq4block.py`(`props`·`links`·`json`) | 맵 종류 50가지 블록·CHR 0 다름, 출구 칸 555개(걸어서 47곳), 지형 효과·문·열쇠 |
| 인물·대화 | [dq4-script-format.md](docs/dq4-script-format.md) · `dq4talk.py` | 스크립트 346개 못 읽은 명령 0, 말 걸기 2658+337번 0 다름, 이벤트 표 50개 |
| 인물 블록(움직임·자동 이벤트) | [dq4-npcblock-format.md](docs/dq4-npcblock-format.md) · `dq4npcblock.py` | 블록 2131개·명령 5010개, 실행 2027개 0 다름 |
| 저장·플래그·장 | [dq4-save-format.md](docs/dq4-save-format.md) · `dq4event.py` | CRC, 1~5장 시작·끝·엔딩, 귀환·ルーラ 37곳, 플래그 뜻(장별 진행 순서) |
| 표 | [dq4-data-format.md](docs/dq4-data-format.md) · `dq4data.py` | 레벨업 626건, 주문·행동 256개, 몬스터 레코드 전 바이트, 몬스터·동료 AI |
| 상점·얻는 것 | [dq4-shop-format.md](docs/dq4-shop-format.md) · `dq4shop.py`·`dq4chest.py`(`loot`) | 가게 창, 여관·교회 요금, 상자 160개, 얻는 물건 238줄, 숨는 인물 |
| 조우 | [dq4-encounter-format.md](docs/dq4-encounter-format.md) · `dq4encounter.py` | 필드·던전 21층 전투 158번, 특수 전투 34개, 기습·선제 비율 |
| 원작 그림 | [dq4-fcgfx.md](docs/dq4-fcgfx.md)·[dq4-fcsprite-format.md](docs/dq4-fcsprite-format.md) · `dq4fcgfx.py`·`dq4fcsprite.py` | 맵·필드·장면 화면 픽셀 0 다름, 스프라이트·몬스터 픽셀 대조 |
| 소리 | [dq4-sound-format.md](docs/dq4-sound-format.md) · `dq4sound.py`(`export` 가 곡·효과음마다 MIDI·악보 텍스트·채널별 JSON) | 곡 50·효과음 55 를 롬 드라이버 실행과 APU 기록으로 프레임마다 0 다름, 맵·필드·전투 곡 표 |
| 디버그 | [dq4-debug.md](docs/dq4-debug.md) | `$C000` 스위치(장 고르기·벽 통과·인카운트 끄기·전투 테스트) |

뽑은 원작 그림(맵 279·필드·블록·CHR·폰트·장면, 인물 스프라이트·몬스터)과 소리(`fc/dq4/sound/` 의 MIDI·악보·JSON)는 저작권 데이터라 비공개 저장소 `perfectacle/sfc-dq4-assets` 의 `fc/dq4/` 에 있습니다(`gallery/index.html`). 공개 저장소에는 다시 만드는 도구만 둡니다. 에셋 전체는 `fc/dq4/tools/dq4assets.sh OUT` 한 번으로 롬에서 다시 뽑습니다(장면 화면은 `MESENCE` 필요, 세이브스테이트도 그 안에서 만듦). 에셋 저장소의 `SOURCE.txt` 는 그때의 커밋을 적습니다.

포팅용 그래픽의 현재 판단은 [그래픽 핸드오프](../../sfc/dq4/handoff.md)에 있습니다.

### 실험 출발점

| 세이브스테이트(`work/state/`) | 장면 |
| --- | --- |
| `dq4-ch1-throne`·`courtyard`·`field`·`battle` | 1장 왕좌의 방·성 앞·필드·첫 전투. 지금까지의 실측 숫자 다수가 이것 기준 |
| `dq4-ch{1..5}-start`, `dq4-debugB-start` | 장 시작(디버그 장 고르기로 만듦), 디버그 B(8명 일행) |
| `dq4-ch2-b3` | 2장 시작에서 B 세 번 — 바로 조작 가능, 워프 출발점 |
| `dq4-ch1-casino` | 1장 일행, 카지노 04/01 포커 딜러 앞, 코인 100 |

- 1장 상태 넷은 테스트러너가 MesenCE `Saves/dq4.sav` 를 읽던 시절에 만든 것이라, 지금 `fc/dq4/tools/dq4state.sh`(SRAM 을 00 으로 채움)로 다시 만들면 이름이 「ああ」, 첫 전투가 おおみみず·スライム 로 달라집니다. 문서 숫자가 기존 파일 기준이므로 덮어쓰지 않았습니다.
- `dq4-ch3-start` 는 머리 장면이 약 2000프레임 돌아 그동안 워프가 안 됩니다. `dq4-ch4-start` 는 A 로 대사를 넘기면 15/00 (1A,02) 에서 조작됩니다. `dq4-ch5-start` 는 명령 창이 떠 있어 B 세 번 뒤 걷습니다.
- 원하는 맵으로 가기는 [dq4-warp.md](docs/dq4-warp.md)(`STATE` 는 절대 경로, `end.mss` 에서 이으면 SEQ 를 `wait:30` 으로 시작, 일행 `$616A` 는 `SET` 이 아니라 `AFTER` 로).

## 도구

FC 도구는 툴킷에 `krpatch fc` 로 들어갔습니다(v0.5.0). 게임과 무관한 것은 툴킷에, DQ4 에만 해당하는 것은 이 폴더의 `tools/`(`dq4state.sh` 등)에 둡니다. 툴킷에 기능이 더 필요하면 툴킷 저장소에 PR 을 내고 릴리스한 뒤 태그를 올립니다([DEP-03](../../.agents/skills/dependencies/SKILL.md#dep-03--툴킷은-릴리스-태그로)). 툴킷 규칙은 그 저장소의 [AGENTS.md](https://github.com/perfectacle/kr-patch-toolkit/blob/main/AGENTS.md)(게임 무관, 출력 호환, 합성 롬 테스트)입니다.

자주 쓰는 형태:

```sh
export LIBDIR=$(uv run krpatch fc lua)
DRIVER=$LIBDIR/seq.lua STATE=$PWD/work/state/dq4-ch1-throne.mss SEQ="down:64" TAIL=200 \
  EVERY=0 FROM=1 TO=200 MAXF=240 SHOT_DIR=$PWD/work/cov \
  "$MESENCE" --testrunner "$PWD/rom/dq4.nes" "$LIBDIR/probe/cover.lua"
uv run krpatch fc listing rom/dq4.nes work/cov/cover.txt --range 3C000-3FFFF
```

- MesenCE 는 콜백마다 「Uninitialized memory read」 경고를 많이 찍습니다(세이브스테이트를 불러오기 전 몇 프레임). 출력은 `>/dev/null 2>&1` 로 버립니다.
- 오프닝은 입력 시점에 따라 장면이 수백 프레임씩 밀립니다. 새 출발점이 필요하면 기존 세이브스테이트에서 이어 `dq4state.sh` 에 단계로 더합니다.
- FC DQ4 의 문은 「とびら」 명령이 있지만, 성 밖 → 왕좌의 방 문은 열린 문이라 걸어 들어갑니다(문 바로 아래 칸에서 위로).

## 참고 자료

[references.md 「DQ4(FC)」](references.md#dq4fc) 의 두 디스어셈블리는 **북미판** 기준입니다. 일본판은 텍스트 부호·폰트·여러 주소가 다르므로 구조(어떤 표가 있고 어떻게 읽는지)만 참고하고, 주소는 일본판에서 실측으로 다시 찾습니다. 디스어셈블리의 데이터 파일·추출물을 받아 쓰지 않습니다([ORIG-01](../../.agents/skills/analysis/SKILL.md#orig-01--남의-데이터-금지)).

## 다음에 할 일

분석은 남은 세부만 있습니다([todo.md](todo.md)). 다음 큰 일은 이 데이터를 SFC DQ5 엔진에 넣는 쪽입니다.

1. **DQ5 쪽 대응 정하기** — dq5 트랙 결과([sfc/dq5/handoff.md](../../sfc/dq5/handoff.md))와 맞춰, 맵(블록 속성 → DQ5 블록), 인물·대화 스크립트·이벤트(→ DQ5 스크립트), 대사 기호(`dq4text.py export` 의 `{NAME:k}` 등 → DQ5 제어 코드), 창(`dq4-window-layouts` → DQ5 창), 표(몬스터·아이템·주문)를 어떤 형식으로 옮길지 정합니다.
2. **변환기** — 위 디코더들의 JSON 출력을 DQ5 형식으로 바꾸는 도구. 소리는 `dq4sound.py` 의 채널별 JSON 을 DQ5 SPC 악보로 다시 편곡합니다(DQ5 음원 형식은 dq5 트랙 몫). 결과물은 `sfc/dq4/` 에 둡니다.
3. **분석 세부** — [todo.md](todo.md) 의 항목. 변환하다 막히는 것부터 합니다.

## 조심할 것

- [analysis 스킬](../../.agents/skills/analysis/SKILL.md) 의 「자주 밟는 함정」은 대부분 NES 에도 해당합니다(macOS `timeout` 부재, `SHOT_DIR` 절대 경로, zsh 단어 분리).
- 주소 표기: CPU 주소는 `$8000`, PRG 위치는 「PRG 뱅크 `05`:`$8123`」 또는 「파일 오프셋 `0x14133`」(iNES 헤더 16바이트 포함 여부를 밝힘)처럼 어느 것인지 적습니다.
- 소유 파일은 `fc/dq4/`(원작 분석)와 `sfc/dq4/`(포팅 결과물) 아래 전부입니다. 일지 순번은 두 폴더가 함께 씁니다. 공유 파일(README, `docs/todo.md`, `docs/references.md`, `tools/README.md`)에는 두 폴더를 가리키는 줄만 둡니다.
