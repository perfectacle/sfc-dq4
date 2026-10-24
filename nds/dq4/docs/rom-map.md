# NDS DQ4 롬 지도

DS 일본판 `rom/dq4ds.nds`(헤더 `DRAGONQUEST4` / `YIVJ`)의 파일 시스템입니다. `krpatch nds unpack` 으로 풀고 `nds/dq4/tools/ndsfs.py` 로 셌습니다.

```sh
uv run --locked krpatch nds unpack rom/dq4ds.nds work/nds/jp
uv run --locked krpatch nds unpack rom/dq4ds-kr.nds work/nds/kr
uv run --locked python nds/dq4/tools/ndsfs.py summary work/nds/jp
uv run --locked python nds/dq4/tools/ndsfs.py diff work/nds/jp work/nds/kr
```

## 머리

| 항목 | 값 |
| --- | --- |
| 카드 크기 | 128MB, 그중 `0x6209278` 바이트 사용 |
| ARM9 | `0x4000` 에서 `0xC25B8` 바이트, 오버레이 38개 |
| ARM7 | `0x191600` 에서 `0x269A4` 바이트 |
| 파일 | 4827개(이름 있는 것 4789개) |

## data/data/ 폴더

| 폴더 | 파일 | 크기(KB) | 확장자 |
| --- | --- | --- | --- |
| `(최상위)` | 6 | 23 | `tex` 3, `dtd` 1, `bnr` 1, `bin` 1 |
| `2D` | 34 | 1545 | `tex` 34 |
| `ACT` | 3 | 4 | `tex` 3 |
| `BTLMAP` | 147 | 7236 | `lz` 146, `txt` 1 |
| `CAMERA` | 164 | 127 | `-` 162, `dat` 1, `txt` 1 |
| `CHR` | 239 | 3610 | `pack` 187, `nsbca` 32, `nsbmd` 19, `txt` 1 |
| `DATE` | 2 | 0 | `dtd` 2 |
| `DEBUG` | 4 | 25 | `dat` 4 |
| `EFFECT` | 191 | 1193 | `lz` 188, `txt` 3 |
| `ENDROLL` | 64 | 1543 | `tex` 63, `pam` 1 |
| `FIELD` | 30 | 2595 | `bin` 15, `tex` 10, `pack` 5 |
| `G2D` | 277 | 3498 | `bgc` 123, `bgp` 123, `mptp` 10, `mpt` 10, `tim` 4 |
| `MAP` | 536 | 34559 | `lz` 531, `txt` 2, `bin` 1, `pack` 1, `bin_` 1 |
| `MASK` | 4 | 28 | `tex` 4 |
| `MESS` | 942 | 6627 | `mpt` 942 |
| `MINIGAME` | 7 | 241 | `tex` 7 |
| `MONSTER` | 647 | 7944 | `tex.lz` 303, `anm.lz` 179, `panm.lz` 163, `NSSA` 2 |
| `OPENING` | 7 | 134 | `dssa` 5, `tex.lz` 2 |
| `PAM` | 445 | 5567 | `pam` 444, `txt` 1 |
| `PARAM` | 450 | 809 | `dat` 450 |
| `RISE` | 5 | 10 | `tex` 5 |
| `SCRIPT` | 396 | 3628 | `bin` 396 |
| `SOUND` | 2 | 10799 | `sdat` 1, `sadl` 1 |
| `TRANS` | 187 | 5455 | `dssa` 164, `tex` 23 |

- `MESS` 에는 일본어(`ja`) 207개 말고도 영어·프랑스어·독일어·스페인어·이탈리아어 파일이 147개씩 들어 있습니다. 일본판 롬인데 유럽판 번역이 함께 실려 있습니다. 형식은 [text-format.md](text-format.md).
- `G2D/FONT` 의 `zen10`·`zen12`(전각)·`han10`·`han12`(반각)가 대사 폰트입니다(NFTR).
- 그래픽 폴더(`CHR`, `MONSTER`, `MAP`, `BTLMAP`, `FIELD`, `2D`, `TRANS`, `PAM` 등)의 형식은 그래픽 문서에서 다룹니다.
- `DEBUG` 폴더에 `dat` 4개가 있습니다. 쓰임은 디버그·워프 도구 문서에서 다룹니다.

## 한글 팬패치가 바꾼 파일

일본판과 내용이 다른 파일은 216개입니다. 대사 파일 `MESS/ja/*.mpt` 207개 전부와 아래 9개입니다. 다른 언어 대사와 그래픽 폴더는 그대로입니다.

| 파일 | 바뀐 바이트 | 무엇 |
| --- | --- | --- |
| `G2D/FONT/zen10.nftr`, `zen12.nftr` | 글리프 1400개 | 한자·히라가나 자리 글리프를 한글 음절로 바꿈([text-format.md](text-format.md#한글-팬패치)) |
| `overlay9/overlay_0016.bin` | 406바이트, 9곳 | 메뉴 문자열(Shift_JIS). 예: `@だいじなもの` 자리를 같은 길이의 한자 코드로 덮어 「@중요한 것」으로 보이게 함 |
| `arm9.bin` | 486바이트, 11곳 | ARM9 안 Shift_JIS 문자열(파일 이름 표 근처) |
| `overlay9/overlay_0000.bin` | 4바이트 | 문자열 한 곳 |
| `OPENING/logo.tex.lz` | 압축 크기 16947 → 16735 | 타이틀 로고 |
| `TRANS/m278_03.dssa` | 1바이트 | 알 수 없음 |
| `header.bin`, `banner.bin` | 17·326바이트 | 카드 머리 체크섬, 배너 제목 |

파일 크기는 모두 같습니다(로고만 압축 결과가 다름). 팬패치는 파일을 늘리지 않고 제자리에서 바꿨습니다.

## 남은 것

- `arm9.bin`·오버레이의 Shift_JIS 문자열 표 위치와 개수 전체.
- `TRANS/m278_03.dssa` 1바이트 변경의 뜻.
- `DEBUG/*.dat`, `PARAM/*.dat`(아이템·맵·몬스터·인물 매개변수 450개), `SCRIPT/*.bin`(이벤트 스크립트 396개)의 형식.
