# dq4 트랙 핸드오프

FC DQ4 원작을 분석하는 세션이 처음 읽는 문서입니다. 이 트랙의 목표, 지금 있는 것과 없는 것, 무엇부터 하면 되는지를 적습니다. 규칙은 [AGENTS.md](../AGENTS.md), 남은 일 목록은 [todo.md](todo.md) 의 `## dq4` 절이 정본입니다. 세션을 마칠 때 이 문서의 「지금 상태」와 「다음에 할 일」을 고쳐 다음 세션에 넘깁니다.

## 목표

DQ4 의 내용(맵, 인물과 대사, 이벤트 흐름, 몬스터·아이템·주문·상점 표)을 DQ5 엔진에 옮기려면, 원작에서 그 데이터를 **롬만으로** 뽑아낼 수 있어야 합니다. 이 트랙은 FC DQ4(일본판 Rev A)의 데이터 형식을 풀고 `tools/dq4*.py` 추출기와 `docs/dq4-*-format.md` 명세를 만듭니다. DQ5 쪽에 어떻게 넣을지는 dq5 트랙의 결과([dq5-handoff.md](dq5-handoff.md))와 맞춰 나중에 정합니다.

그래픽은 원작 데이터를 옮기지 않고 직접 그립니다. 원작 그래픽은 무엇을 그려야 하는지 확인하는 용도로만 봅니다.

## 지금 상태

실험 환경을 갖췄고, 필드 RAM·뱅크 전환·BRK 뱅크 호출·대사 텍스트·마을/던전 맵 배치를 풀었습니다. 정리는 [dq4-ram-format.md](dq4-ram-format.md)·[dq4-bank-format.md](dq4-bank-format.md)·[dq4-text-format.md](dq4-text-format.md)·[dq4-map-format.md](dq4-map-format.md), 과정은 `docs/journal/dq4/` 일지에 있습니다.

| 항목 | 값 | 근거 |
| --- | --- | --- |
| 롬 | `rom/dq4.nes`, Rev A. SHA-1 은 [README](../README.md#원본-롬). 초판(Rev 0)은 쓰지 않음 | README |
| iNES 헤더 | 매퍼 1(MMC1, SUROM: CHR 0 레지스터 bit4 로 256KB 절반 선택), PRG 512KB, CHR-RAM, 배터리 | `krpatch fc info`, 쓰기 프로브 |
| 도구 | 툴킷 v0.5.0 의 `krpatch fc info\|dis\|listing\|lua`. 프로브 `cover`·`reads`·`writes`·`trace`·`watch` | [tools/README.md](../tools/README.md#fc-dq4-툴킷의-fc-스크립트) |
| 세이브스테이트 | `work/state/dq4-ch1-throne.mss`(1장 왕좌의 방, (10,15), 맵 `0D`), `dq4-ch1-courtyard.mss`(성 밖, (12,0A), 맵 `0A`). `tools/dq4state.sh` 가 롬에서 다시 만듦 | 스크립트 끝에 찍는 좌표·맵 번호 |
| 필드 RAM | 좌표 `$0044`/`$0045`, 장소 `$63`/`$64`, 맵 종류 `$0028`(=`$0550`), 출구 표 `$05A0`(7바이트) | 걸어서 맵 두 번 전환 |
| 맵 | 마을·던전 269개, 비트열 압축(사각형·길·점). [dq4-map-format.md](dq4-map-format.md), `tools/dq4map.py` | RAM 두 맵 0 차이, 경계 268곳 전수 |
| 뱅크 전환 | `$FF91`(A=뱅크, `$0507` 이 현재 뱅크), `$C3EA` 다른 뱅크 바이트 읽기 | 쓰기·읽기 프로브 |
| 뱅크 호출 | `BRK b1 b2`: 뱅크 = `b2` 상위 4비트+bit3, 함수 = `b1`, 주소 = 그 뱅크 `$8000` 표. [dq4-bank-format.md](dq4-bank-format.md), `tools/dq4bank.py` | 실행 기록 1019건과 디코더 0 차이 |
| 데이터 뱅크 | `00`~`04`: 대사 본문, `1B`: 대사 끝부분과 사전 | 디코더 |
| 대사 | 메시지 2633개, 6비트 압축 + 사전 192단어. [dq4-text-format.md](dq4-text-format.md), `tools/dq4text.py all` | 창 줄 버퍼 덤프 10장과 비교 |

## 도구

FC 도구는 툴킷에 `krpatch fc` 로 들어갔습니다(v0.5.0). 게임과 무관한 것은 툴킷에, DQ4 에만 해당하는 것은 `tools/dq4*`(`dq4state.sh` 등)에 둡니다. 툴킷에 기능이 더 필요하면 툴킷 저장소에 PR 을 내고 릴리스한 뒤 태그를 올립니다([DEP-03](../.agents/skills/dependencies/SKILL.md#dep-03--툴킷은-릴리스-태그로)). 툴킷 규칙은 그 저장소의 [AGENTS.md](https://github.com/perfectacle/kr-patch-toolkit/blob/main/AGENTS.md)(게임 무관, 출력 호환, 합성 롬 테스트)입니다.

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

[references.md 「DQ4(FC)」](references.md#dq4fc) 의 두 디스어셈블리는 **북미판** 기준입니다. 일본판은 텍스트 부호·폰트·여러 주소가 다르므로 구조(어떤 표가 있고 어떻게 읽는지)만 참고하고, 주소는 일본판에서 실측으로 다시 찾습니다. 디스어셈블리의 데이터 파일·추출물을 받아 쓰지 않습니다([ORIG-01](../.agents/skills/analysis/SKILL.md#orig-01--남의-데이터-금지)).

## 다음에 할 일

[todo.md](todo.md) 의 `## dq4` 순서대로 합니다.

1. **맵 나머지** — 블록 번호 → 그래픽·통행(맵 종류별 블록 정의, `$7800` 을 읽어 nametable 을 쓰는 코드부터), 출구 표 `$05A0` 을 채우는 롬 데이터(`writes.lua` 로 `05A0-05BF`), 인물 배치, 필드 지도. dq5 트랙의 [dq5-map-format.md](dq5-map-format.md) 와 같은 항목으로 정리합니다.
2. **몬스터·아이템·주문·경험치 표, 이벤트 플래그와 장(章) 전환**. 플래그는 `BRK` 특수 형식이 쓰는 `$627B` 영역부터 봅니다.
3. **롬 구조 나머지** — [dq4-bank-format.md 「남은 것」](dq4-bank-format.md#남은-것).
4. **대사 나머지** — [dq4-text-format.md 「남은 것」](dq4-text-format.md#남은-것).

## 조심할 것

- [analysis 스킬](../.agents/skills/analysis/SKILL.md) 의 「자주 밟는 함정」은 대부분 NES 에도 해당합니다(macOS `timeout` 부재, `SHOT_DIR` 절대 경로, zsh 단어 분리).
- 주소 표기: CPU 주소는 `$8000`, PRG 위치는 「PRG 뱅크 `05`:`$8123`」 또는 「파일 오프셋 `0x14133`」(iNES 헤더 16바이트 포함 여부를 밝힘)처럼 어느 것인지 적습니다.
- 소유 파일은 `docs/dq4-*`, `tools/dq4*`, `tools/lua/fc/`, 일지·그림의 `dq4-*` 입니다. 공유 파일(README, `docs/todo.md`, `docs/references.md`)은 자기 줄·절만 고칩니다.
