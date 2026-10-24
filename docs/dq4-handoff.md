# dq4 트랙 핸드오프

FC DQ4 원작을 분석하는 세션이 처음 읽는 문서입니다. 이 트랙의 목표, 지금 있는 것과 없는 것, 무엇부터 하면 되는지를 적습니다. 규칙은 [AGENTS.md](../AGENTS.md), 남은 일 목록은 [todo.md](todo.md) 의 `## dq4` 절이 정본입니다. 세션을 마칠 때 이 문서의 「지금 상태」와 「다음에 할 일」을 고쳐 다음 세션에 넘깁니다.

## 목표

DQ4 의 내용(맵, 인물과 대사, 이벤트 흐름, 몬스터·아이템·주문·상점 표)을 DQ5 엔진에 옮기려면, 원작에서 그 데이터를 **롬만으로** 뽑아낼 수 있어야 합니다. 이 트랙은 FC DQ4(일본판 Rev A)의 데이터 형식을 풀고 `tools/dq4*.py` 추출기와 `docs/dq4-*-format.md` 명세를 만듭니다. DQ5 쪽에 어떻게 넣을지는 dq5 트랙의 결과([dq5-handoff.md](dq5-handoff.md))와 맞춰 나중에 정합니다.

그래픽은 원작 데이터를 옮기지 않고 직접 그립니다. 원작 그래픽은 무엇을 그려야 하는지 확인하는 용도로만 봅니다.

## 지금 상태

아직 분석한 것이 없습니다. 확인된 사실은 아래뿐입니다.

| 항목 | 값 | 근거 |
| --- | --- | --- |
| 롬 | `rom/dq4.nes`, Rev A. SHA-1 은 [README](../README.md#원본-롬). 초판(Rev 0)은 쓰지 않음 | README |
| iNES 헤더 | `4E 45 53 1A 20 00 12 00 …`: PRG 16KB×32 = 512KB, CHR-ROM 없음(CHR-RAM), 매퍼 1(MMC1), 배터리 백업 | 헤더 바이트 |
| 에뮬레이터 | MesenCE `--testrunner` 가 dq4.nes 를 돌린다. 600프레임에 오프닝 크레디트 화면. Lua 메모리 타입 `nesMemory`(CPU 주소), `nesPrgRom`(512KB), `nesInternalRam`, `nesWorkRam`, `nesSaveRam`, `nesChrRam`, `nesPpuMemory`, `nesNametableRam`, `nesPaletteRam`, `nesSpriteRam` | 실행해 확인 |

## 도구 — 없는 것부터

[kr-patch-toolkit](https://github.com/perfectacle/kr-patch-toolkit) v0.4.0 에는 NES 지원이 없습니다(`krpatch sfc`, `krpatch nds` 만 있음). 6502 디스어셈블러도, NES 용 `boot.lua`·프로브도 없습니다. 툴킷의 Lua 라이브러리(`krpatch sfc lua`)는 SFC 메모리 타입을 쓰므로 그대로는 안 됩니다.

정할 것: 게임과 무관한 NES 도구(부팅·입력·스크린샷 Lua, 메모리 감시 프로브, 6502 디스어셈블러, 커버리지 리스팅)는 툴킷에 `krpatch nes` 로 넣는 것이 맞습니다([DEP-03](../.agents/skills/dependencies/SKILL.md#dep-03--툴킷은-릴리스-태그로)). 툴킷은 별도 저장소라 PR → 릴리스 → 이 저장소의 태그 올리기를 거쳐야 하므로, 시작 전에 사용자와 정합니다.

- 툴킷에 넣기로 하면: 툴킷 저장소의 [AGENTS.md](https://github.com/perfectacle/kr-patch-toolkit/blob/main/AGENTS.md) 규칙(게임 무관, 출력 호환, 합성 롬 테스트)을 따릅니다.
- 그 전까지 임시로 쓸 것은 이 저장소의 `tools/lua/nes/`(dq4 트랙 소유)에 둡니다. SFC 프로브(`tools/lua/*.lua`)를 고쳐 NES 를 지원하게 하지 않습니다([TRACK-02](../.agents/skills/tracks/SKILL.md#track-02--공유-파일)).

## 참고 자료

[references.md 「DQ4(FC)」](references.md#dq4fc) 의 두 디스어셈블리는 **북미판** 기준입니다. 일본판은 텍스트 부호·폰트·여러 주소가 다르므로 구조(어떤 표가 있고 어떻게 읽는지)만 참고하고, 주소는 일본판에서 실측으로 다시 찾습니다. 디스어셈블리의 데이터 파일·추출물을 받아 쓰지 않습니다([ORIG-01](../.agents/skills/analysis/SKILL.md#orig-01--남의-데이터-금지)).

## 다음에 할 일

[todo.md](todo.md) 의 `## dq4` 순서대로 합니다.

1. **NES 실험 환경** — 도구 위치를 사용자와 정한 뒤, 부팅·입력 재생·스크린샷·RAM 덤프 Lua 를 만들고 조작 가능한 장면(1장 시작 마을 등)의 세이브스테이트를 `work/state/dq4-*.mss` 로 만듭니다. 세이브스테이트 이름에 `dq4-` 를 붙여 dq5 트랙 것과 섞이지 않게 합니다.
   완료: 세이브스테이트에서 주인공을 걸려 맵 번호·좌표 RAM 이 바뀌는 것을 기록으로 확인.
2. **롬 구조** — MMC1 뱅크 전환 루틴(레지스터 `$8000`~`$FFFF` 쓰기), 고정 뱅크(`$C000`~`$FFFF`, 마지막 뱅크로 보임)의 공통 루틴, 뱅크마다 무엇이 있는지 표. 실행 커버리지로 확인합니다.
3. **대사 텍스트** — 문자 표, 압축 방식, 대사 번호에서 본문을 찾는 표. 이식에서 가장 양이 많고, 한글패치의 번역 원문이 됩니다.
4. **맵과 인물** — 마을·던전 맵 형식, 인물 배치, 출구. dq5 트랙의 [dq5-map-format.md](dq5-map-format.md) 와 같은 항목으로 정리하면 옮길 때 대응이 쉽습니다.
5. **몬스터·아이템·주문·경험치 표, 이벤트 플래그와 장(章) 전환**.

## 조심할 것

- [analysis 스킬](../.agents/skills/analysis/SKILL.md) 의 「자주 밟는 함정」은 대부분 NES 에도 해당합니다(macOS `timeout` 부재, `SHOT_DIR` 절대 경로, zsh 단어 분리).
- 주소 표기: CPU 주소는 `$8000`, PRG 위치는 「PRG 뱅크 `05`:`$8123`」 또는 「파일 오프셋 `0x14133`」(iNES 헤더 16바이트 포함 여부를 밝힘)처럼 어느 것인지 적습니다.
- 소유 파일은 `docs/dq4-*`, `tools/dq4*.py`, `tools/lua/nes/`, 일지·그림의 `dq4-*` 입니다. 공유 파일(README, `docs/todo.md`, `docs/references.md`)은 자기 줄·절만 고칩니다.
