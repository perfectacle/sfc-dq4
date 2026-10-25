# nds: NDS DQ4 리메이크·한글 팬패치 참고

NDS 「ドラゴンクエストIV 導かれし者たち」(일본판)과 그 한글 팬패치를 **참고 자료로** 분석하는 트랙입니다. 패치는 계속 SFC DQ5 롬 위에 FC DQ4 내용을 얹어 만들고, NDS 롬을 바탕으로 쓰지 않습니다. 여기서는 이름을 통일할 대조표, DS 판에서 늘어난 내용과 이식 판단, 맵·스프라이트를 그릴 때 볼 참고 자료를 냅니다. 규칙은 [AGENTS.md](../../AGENTS.md), 롬 준비는 [저장소 README](../../README.md#원본-롬) 를 봅니다.

## 문서

- [handoff.md](handoff.md): nds 트랙 시작점(지금 상태, 다음 할 일)
- [docs/rom-map.md](docs/rom-map.md): 파일 시스템 지도, 한글 팬패치가 바꾼 파일
- [docs/text-format.md](docs/text-format.md): 대사 파일 MPT0·표지·파일 묶음, 폰트 NFTR, 한글 팬패치 방식과 대응표
- [docs/glossary.md](docs/glossary.md): 명칭 대조표(FC·DS 일본어·DS 영어·한글 팬패치), 본문은 [docs/glossary-table.md](docs/glossary-table.md)
- [docs/extras.md](docs/extras.md): DS 판에서 늘어난 것과 이식 판단
- [docs/graphics-format.md](docs/graphics-format.md): 그래픽 형식(텍스처·인물 팩·DSSA 조립 애니메이션·3D 맵과 배치표·2D 아이콘·글꼴), 참고용 추출과 갤러리
- [docs/debug.md](docs/debug.md): 남은 디버그 기능(부팅 디버그 메뉴·전투 테스트·진행도 프리셋), RAM 지도, 장면 이동과 장 시작 세이브스테이트
- [todo.md](todo.md): 남은 일
- [references.md](references.md): 참고 자료

## 도구

`uv run --locked python nds/dq4/tools/<도구>.py` 로 씁니다. 롬은 먼저 `work/nds/` 에 풉니다.

```sh
uv run --locked krpatch nds unpack rom/dq4ds.nds work/nds/jp
uv run --locked krpatch nds unpack rom/dq4ds-kr.nds work/nds/kr
```

| 도구 | 하는 일 |
| --- | --- |
| `ndsfs.py` | 파일 시스템 요약, 두 롬의 파일 비교 |
| `ndstext.py` | 대사 파일 읽기(`dump`, `--kr` 로 한글판), 이름 표(`names`), 대조표(`glossary`), 통계(`stats`) |
| `ndsfont.py` | NFTR 폰트 정보(`info`)와 글자 시트(`sheet`) |
| `ndskr.py` | 한글 대응표 검사(`check`)와 다시 만들기(`draft`) |
| `ndsgfx.py` | 그래픽 디코더. `survey` 폴더·헤더별 파일 수, `export OUT` 으로 인물·몬스터(조립·애니메이션 WebP)·맵 텍스처와 위에서 본 렌더링·전투 배경·아이콘·글꼴·효과·타이틀을 PNG 로(`--only` 단계, `--kr work/nds/kr` 한글판 글꼴·로고), `gallery OUT` 으로 `index.html`. 결과는 비공개 에셋 저장소에만 |
| `ndsplay.py` | desmume libretro 코어(`DESMUME_CORE`)를 화면 없이 돌리며 버튼·터치를 넣고 화면 저장(`every N K 이름`), RAM 읽기·쓰기·고정(`peek`·`poke`·`freeze`·`until`), 세이브스테이트 |
| `ndswarp.py` | 장면 이동(`map`), 진행도 프리셋(`presets`·`preset`), 부팅 디버그 메뉴로 시작(`boot`), 장 시작 세이브스테이트(`chapters`). [docs/debug.md](docs/debug.md) |
| `ndsfigures.py` | `images/` 의 일지 그림을 다시 만듦 |

표는 [tables/](tables/) 에 있습니다. `kr-font.tsv` 는 한글 팬패치의 「일본어 코드 → 한글 음절」 표, `hangul-freq.json` 은 `draft` 가 쓰는 음절 빈도입니다.

## 해킹 일지

- [2026-10-25-01: 대사 파일과 한글 팬패치 글꼴 읽기](journal/2026-10-25-01-text.md)
- [2026-10-25-02: NDS 그래픽 형식 풀기와 참고용 추출](journal/2026-10-25-02-graphics.md)
- [2026-10-25-03: 동료 대화 표](journal/2026-10-25-03-talk.md)
- [2026-10-25-04: 디버그 메뉴·진행도 프리셋으로 장 시작 세이브스테이트 만들기](journal/2026-10-25-04-debug.md)
- [2026-10-25-06: 메시지 번호, 대사 표지, 실행 파일 문자열, 이벤트 스크립트](journal/2026-10-25-06-text2.md)
- [2026-10-25-08: 조우 끄기·필드 워프·장 번호와 플래그·메시지 디버그](journal/2026-10-25-08-debug2.md)
- [2026-10-25-09: 전투 테스트 Select 모드와 fk01](journal/2026-10-25-09-debug3.md)
