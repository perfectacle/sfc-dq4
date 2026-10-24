# nds 트랙 핸드오프

NDS 판 「ドラゴンクエストIV 導かれし者たち」(일본판)과 그 한글 팬패치를 분석하는 세션이 처음 읽는 문서입니다. 규칙은 [AGENTS.md](../AGENTS.md), 남은 일 목록은 [todo.md](todo.md) 의 `## nds` 절이 정본입니다. 세션을 마칠 때 「지금 상태」와 「다음에 할 일」을 고쳐 다음 세션에 넘깁니다.

## 목표

NDS 판은 **참고 자료**입니다. 패치는 계속 SFC DQ5 롬 위에 FC DQ4 내용을 얹어 만들고, NDS 롬을 바탕으로 쓰지 않습니다. 이 트랙은 세 가지를 냅니다.

1. 명칭·고유명사 대조표: FC 일본어, DS 일본어, DS 한글 팬패치, 채택 이름. 채택 이름은 사용자가 확인합니다.
2. NDS 판에서 늘어난 내용 목록(이야기, 즐길 거리, 편의 기능): 롬 확장을 전제로 DQ5 엔진에 옮길 때 필요한 기능과 추가 용량을 적고 옮길지 제안합니다.
3. 맵 배치·인물 스프라이트 참고: 나중에 맵과 스프라이트를 그릴 때 봅니다. 그래픽은 계속 직접 그립니다.

## 지금 상태

트랙을 막 등록했습니다. 아직 분석 결과는 없습니다.

| 항목 | 값 | 근거 |
| --- | --- | --- |
| 롬 | `rom/dq4ds.nds`, `rom/dq4ds-kr.nds`. SHA-1 은 [README](../README.md#원본-롬) | `shasum` |
| 헤더 | `DRAGONQUEST4` / `YIVJ`, 128MB 중 `0x6209278` 바이트 사용, 파일 4827개(이름 있는 것 4789개, ARM9 오버레이 38개) | `krpatch nds info` |
| 한글 팬패치 | `NDS_DQ4_v1.1.xdelta`(내부 판 `DQ4_v036`), 출처는 [references.md 「DQ4(NDS)」](references.md#dq4nds). 사용자 허락 아래 참고([ORIG-01](../.agents/skills/analysis/SKILL.md#orig-01--남의-데이터-금지)) | VCDIFF 헤더의 원본 이름이 일본판 롬 이름과 같음 |
| 도구 | 툴킷 v0.5.0 의 `krpatch nds info\|ls\|unpack\|pack`, LZ10/LZ11. 패치 적용은 `xdelta3`(툴킷은 LZMA 2차 압축을 못 읽음) | 실행 |
| 에뮬레이터 | desmume libretro 코어([EMU-01](../.agents/skills/analysis/SKILL.md#emu-01--에뮬레이터는-mesence)). kr-patches 의 고스트 트릭 패치가 쓰는 방식 | |

## 다음에 할 일

[todo.md](todo.md) 의 `## nds` 순서대로 합니다.

1. **롬 구조** — `krpatch nds unpack` 로 두 롬을 `work/` 에 풀고, 파일 단위로 비교해 팬패치가 바꾼 파일 목록을 냅니다. 결과는 `docs/nds-rom-map.md`.
   완료: 바뀐 파일 목록과 각 파일의 형식(압축 여부, 묶음 형식)을 표로 말할 수 있음.
2. **대사와 대조표** — 대사 파일 디코더 `tools/ndstext.py`, 형식은 `docs/nds-text-format.md`, 대조표는 `docs/nds-glossary.md`. FC 쪽 이름은 dq4 트랙의 `tools/dq4data.py`·`tools/dq4text.py` 결과를 읽기만 합니다.
3. **늘어난 내용 목록** — `docs/nds-extras.md`. dq5 트랙 문서로 엔진에 필요한 기능을 판단합니다.
4. **맵·스프라이트 참고** — `docs/nds-map-reference.md`.

## 조심할 것

- 소유 파일은 `docs/nds-*`, `tools/nds*`, `docs/journal/nds/`, `docs/images/nds-*` 입니다. `docs/dq4-*`, `tools/dq4*` 는 dq4 트랙 소유라 읽기만 합니다.
- 롬에서 뽑은 대사 본문·그래픽은 `work/` 에만 둡니다([ROM-01](../.agents/skills/analysis/SKILL.md#rom-01--롬-데이터-금지)). 대조표의 이름처럼 단어 수준만 문서에 적습니다.
- NDS 롬은 128MB 입니다. 풀어 둔 파일은 워크트리마다 만들지 말고 원래 체크아웃의 `work/nds/` 에 한 번 풀어 링크해 씁니다.
