# nds 트랙 핸드오프

NDS 판 「ドラゴンクエストIV 導かれし者たち」(일본판)과 그 한글 팬패치를 분석하는 세션이 처음 읽는 문서입니다. 규칙은 [AGENTS.md](../../AGENTS.md), 남은 일 목록은 [todo.md](todo.md) 가 정본입니다. 세션을 마칠 때 「지금 상태」와 「다음에 할 일」을 고쳐 다음 세션에 넘깁니다.

## 목표

NDS 판은 **참고 자료**입니다. 패치는 계속 SFC DQ5 롬 위에 FC DQ4 내용을 얹어 만들고, NDS 롬을 바탕으로 쓰지 않습니다. 이 트랙은 세 가지를 냅니다.

1. 명칭·고유명사 대조표: FC 일본어, DS 일본어, DS 영어, DS 한글 팬패치, 채택 이름. 채택 이름은 사용자가 확인합니다.
2. NDS 판에서 늘어난 내용 목록: 롬 확장을 전제로 DQ5 엔진에 옮길 때 필요한 기능을 적고 옮길지 제안합니다.
3. 맵·인물 스프라이트 참고: 그래픽은 계속 직접 그리고, 추출물은 비공개 에셋 저장소(`perfectacle/sfc-dq4-assets` 의 `nds/dq4/`)에만 둡니다.

## 지금 상태

| 항목 | 값 | 근거 |
| --- | --- | --- |
| 롬 | `rom/dq4ds.nds`, `rom/dq4ds-kr.nds`. SHA-1 은 [README](../../README.md#원본-롬) | `shasum` |
| 파일 시스템 | 파일 4827개, 폴더별 표는 [rom-map.md](docs/rom-map.md) | `krpatch nds info`, `ndsfs.py summary` |
| 팬패치가 바꾼 것 | 대사 207개, 폰트 2개, 메뉴 문자열(arm9·오버레이 0·16), 로고 | `ndsfs.py diff` |
| 대사 | MPT0 952개(일본어 207, 영·불·독·서·이 147씩), 문자열 91,398개 전부 해독 | `ndstext.py stats` |
| 한글 대응표 | 1400자([tables/kr-font.tsv](tables/kr-font.tsv)), KS 순서 위반 0, 확인 단어 18개 일치, 전수 눈 대조 | `ndskr.py check` |
| 대조표 | 이름 표 8개, 813줄 | [glossary.md](docs/glossary.md) |
| 늘어난 것 | 6장 805줄, 동료 대화 7,796줄, 이민 마을 796줄 등 | [extras.md](docs/extras.md) |
| 그래픽 | 인물 187팩, 몬스터 303(조립 277), 맵·전투 배경 675(텍스처와 위에서 본 렌더링), 효과 188, 아이콘 424 등 4,204파일. 세계 지도 배치는 못 풂. 결과는 비공개 저장소 `nds/dq4/` | [graphics-format.md](docs/graphics-format.md), `ndsgfx.py export` |
| 툴킷 | v0.5.0 의 `krpatch nds`. 패치 적용은 `xdelta3`(LZMA 2차 압축) | |
| 에뮬레이터 | desmume libretro 코어([EMU-01](../../.agents/skills/analysis/SKILL.md#emu-01--에뮬레이터는-mesence)) | |

실험 출력은 원래 체크아웃의 `work/nds/`(풀어 둔 두 롬 `jp`·`kr`)에 둡니다. 워크트리에서는 `ln -s "$MAIN/work/nds" work/nds` 로 링크해 씁니다(롬 하나가 100MB 넘음).

## 다음에 할 일

[todo.md](todo.md) 의 순서대로 합니다.

1. **채택 이름** — 대조표를 사용자에게 보여 채택 열을 채웁니다.
2. **그래픽 남은 것** — 세계 지도 배치(`FIELD/bin/worldmap*.bin`)부터. 추출 자체는 끝났고 결과는 비공개 에셋 저장소에만([graphics-format.md](docs/graphics-format.md#남은-것)).
3. **디버그·워프 도구** — 6장·이민 마을 같은 늘어난 장면을 바로 열어 보려면 필요합니다.
4. **늘어난 내용의 조건** — 동료 대화가 문장을 고르는 표(`SCRIPT`·`PARAM`)를 찾아 이식 설계의 근거로.

## 조심할 것

- 소유 파일은 `nds/dq4/` 아래 전부입니다. FC 쪽 이름은 dq4 트랙 도구(`dq4data.py`)를 읽기만 합니다.
- 롬에서 뽑은 대사 본문·그래픽은 `work/` 나 비공개 에셋 저장소에만 둡니다([ROM-01](../../.agents/skills/analysis/SKILL.md#rom-01--롬-데이터-금지)). 대조표처럼 단어 수준만 문서에 둡니다.
- 대사를 읽을 때 한글판은 `--kr` 을 줍니다. 그냥 읽으면 엉뚱한 한자가 나옵니다.
