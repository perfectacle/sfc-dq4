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
| 세이브스테이트 | `work/state/dq4-ch1-throne.mss`(1장 왕좌의 방), `dq4-ch1-courtyard.mss`(성 밖), `dq4-ch1-field.mss`(필드), `dq4-ch1-battle.mss`(첫 전투). `tools/dq4state.sh` 가 롬에서 다시 만듦(`--nes.ramPowerOnState=AllZeros` 로 결정적) | 두 번 돌려 RAM md5 같음 |
| 필드 RAM | 좌표 `$0044`/`$0045`, 장소 `$63`/`$64`, 맵 종류 `$0028`(=`$0550`), 출구 표 `$05A0`(7바이트) | 걸어서 맵 두 번 전환 |
| 맵 | 마을·던전 269개, 비트열 압축(사각형·길·점). [dq4-map-format.md](dq4-map-format.md), `tools/dq4map.py` | RAM 두 맵 0 차이, 경계 268곳 전수 |
| 필드 | 3개(250×250 등), 줄 RLE(`0B:$8000`). [dq4-field-format.md](dq4-field-format.md), `tools/dq4field.py` | 게임 조회 147번 0 차이, 기준점 250줄 |
| 이름·표 | 이름 목록 7종(`0B:$B006`), 아이템 강도·가격(뱅크 10), 몬스터 22바이트(`18:$8046`). [dq4-data-format.md](dq4-data-format.md), `tools/dq4data.py` | 전투 두 번의 경험치·골드·HP |
| 출구·인물 | 연결 표 125개(`1B:$8223`), 인물 목록(뱅크 05, 레코드 944개). `dq4map.py exits`·`npcs` | 두 맵 RAM 과 같음, 그룹 경계 71곳 전수 |
| 뱅크 전환 | `$FF91`(A=뱅크, `$0507` 이 현재 뱅크), `$C3EA` 다른 뱅크 바이트 읽기 | 쓰기·읽기 프로브 |
| 뱅크 호출 | `BRK b1 b2`: 뱅크 = `b2` 상위 4비트+bit3, 함수 = `b1`, 주소 = 그 뱅크 `$8000` 표. [dq4-bank-format.md](dq4-bank-format.md), `tools/dq4bank.py` | 실행 기록 1019건과 디코더 0 차이 |
| 데이터 뱅크 | `00`~`04`: 대사 본문, `1B`: 대사 끝부분과 사전 | 디코더 |
| 대사 | 메시지 2633개, 6비트 압축 + 사전 192단어. [dq4-text-format.md](dq4-text-format.md), `tools/dq4text.py all` | 창 줄 버퍼 덤프 10장과 비교 |

포팅용 그래픽 시안도 만들었습니다. [dq4-graphics.md](dq4-graphics.md)에 스프라이트·샘플 맵·타이틀·일러스트와 재생성 방법이 있습니다. 롬 없이 제작하며 SFC 4bpp 변환을 검사합니다. DQ5 엔진 삽입과 MesenCE 표시는 아직 확인하지 않았습니다.

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

[todo.md](todo.md) 의 `## dq4` 순서대로 합니다. 각 형식 문서의 「남은 것」이 세부 목록입니다.

1. **인물 대화 → 메시지 번호** — 대화는 뱅크 15 의 스크립트 해석기(`15:$B7E8`~ 부근이 BRK 로 뱅크 16 함수 00·05 를 부름)가 인물 레코드 블록(바이트코드)을 실행해 메시지를 고릅니다. 메시지 출력은 `16[07]`(`16:$89A3`) → `16:$8656`(X:A = 메시지 번호)입니다. 실측: 왕좌의 방에서 왕((10,0D), 레코드 `17 08 10 02 6b 90 8d` + 블록 `82 0c 01 81 26 …`)에게 말 걸면 `060A`(「そなたの かつやくを きたいしているぞ。」), 아무도 없는 방향은 `02F0`. 해석기 명령표를 풀어 `dq4map.py npcs` 가 인물마다 메시지 번호를 내게 하는 것이 목표입니다.
   완료: 인물 몇 명의 대화 메시지 번호를 디코더가 내고 `probe/trace.lua TRACE=8656` 기록과 같음.
2. **블록 → 그래픽·통행** — 맵 블록 번호(5비트)·필드 타일 번호 → 타일 4개·팔레트·통행. `$7800` 을 읽어 nametable 을 쓰는 코드부터. 다른 dq4 세션이 그래픽 쪽(`feat/dq4-graphics-kit`)을 하고 있으면 겹치지 않게 나눕니다.
3. **표 나머지** — 주문(MP·효과), 레벨별 능력치·경험치, 상점 목록, 보물상자, 조우 표, 몬스터 레코드 나머지 바이트.
4. **이벤트 플래그와 장(章) 전환** — `BRK` 특수 형식이 쓰는 `$627B` 영역, `$62A1`·`$62AA` 처럼 맵·입구를 바꾸는 플래그.
5. **대사 나머지·롬 구조 나머지** — [dq4-text-format.md](dq4-text-format.md#남은-것), [dq4-bank-format.md](dq4-bank-format.md#남은-것).

실험 출발점은 `tools/dq4state.sh` 가 만드는 세이브스테이트 5개(이름 입력 → 왕좌의 방 → 앞마당 → 필드 → 첫 전투)이고, MesenCE 를 돌릴 때는 `--nes.ramPowerOnState=AllZeros` 를 줘야 같은 입력에 같은 결과가 나옵니다.

5. **그래픽 연결** — [dq4-graphics.md 「남은 것」](dq4-graphics.md#남은-것)의 OBJ 조합·팔레트·압축·VRAM 배치를 dq5 트랙과 맞추고, 샘플 맵을 실제 맵과 연결합니다.

## 조심할 것

- [analysis 스킬](../.agents/skills/analysis/SKILL.md) 의 「자주 밟는 함정」은 대부분 NES 에도 해당합니다(macOS `timeout` 부재, `SHOT_DIR` 절대 경로, zsh 단어 분리).
- 주소 표기: CPU 주소는 `$8000`, PRG 위치는 「PRG 뱅크 `05`:`$8123`」 또는 「파일 오프셋 `0x14133`」(iNES 헤더 16바이트 포함 여부를 밝힘)처럼 어느 것인지 적습니다.
- 소유 파일은 `docs/dq4-*`, `tools/dq4*`, `tools/lua/fc/`, 일지·그림의 `dq4-*` 입니다. 공유 파일(README, `docs/todo.md`, `docs/references.md`)은 자기 줄·절만 고칩니다.
