# nds: NDS DQ4 리메이크·한글 팬패치 참고

NDS 「ドラゴンクエストIV 導かれし者たち」(일본판)과 그 한글 팬패치를 **참고 자료로** 분석하는 트랙입니다. 패치는 계속 SFC DQ5 롬 위에 FC DQ4 내용을 얹어 만들고, NDS 롬을 바탕으로 쓰지 않습니다. 여기서는 이름을 통일할 대조표, DS 판에서 늘어난 내용과 이식 판단, 맵·스프라이트를 그릴 때 볼 참고 자료를 냅니다. 규칙은 [AGENTS.md](../../AGENTS.md), 롬 준비는 [저장소 README](../../README.md#원본-롬) 를 봅니다.

## 문서

- [handoff.md](handoff.md): nds 트랙 시작점(지금 상태, 다음 할 일)
- [docs/rom-map.md](docs/rom-map.md): 파일 시스템 지도, 한글 팬패치가 바꾼 파일
- [docs/text-format.md](docs/text-format.md): 대사 파일 MPT0·표지·파일 묶음, 폰트 NFTR, 한글 팬패치 방식과 대응표
- [docs/glossary.md](docs/glossary.md): 명칭 대조표(FC·DS 일본어·DS 영어·한글 팬패치), 본문은 [docs/glossary-table.md](docs/glossary-table.md)
- [docs/extras.md](docs/extras.md): DS 판에서 늘어난 것과 이식 판단
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

표는 [tables/](tables/) 에 있습니다. `kr-font.tsv` 는 한글 팬패치의 「일본어 코드 → 한글 음절」 표, `hangul-freq.json` 은 `draft` 가 쓰는 음절 빈도입니다.

## 해킹 일지

- [2026-10-25-01: 대사 파일과 한글 팬패치 글꼴 읽기](journal/2026-10-25-01-text.md)
