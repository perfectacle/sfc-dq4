# nds: NDS DQ4 리메이크·한글 팬패치 참고

NDS 「ドラゴンクエストIV 導かれし者たち」(일본판)과 그 한글 팬패치를 **참고 자료로** 분석하는 트랙입니다. 패치는 계속 SFC DQ5 롬 위에 FC DQ4 내용을 얹어 만들고, NDS 롬을 바탕으로 쓰지 않습니다. 여기서는 이름을 통일할 대조표, DS 판에서 늘어난 내용과 이식 판단, 맵·스프라이트를 그릴 때 볼 참고 자료를 냅니다. 규칙은 [AGENTS.md](../../AGENTS.md), 롬 준비는 [저장소 README](../../README.md#원본-롬) 를 봅니다.

## 문서

- [handoff.md](handoff.md): nds 트랙 시작점(지금 상태, 다음 할 일)
- [docs/rom-map.md](docs/rom-map.md): 파일 시스템 지도, 한글 팬패치가 바꾼 파일
- [docs/text-format.md](docs/text-format.md): 대사 파일 MPT0·표지·파일 묶음, 폰트 NFTR, 한글 팬패치 방식과 대응표
- [docs/script-format.md](docs/script-format.md): 이벤트 스크립트(`SCRIPT/*.bin`) 블록·실행 방식·명령표·깃발, 6장 이벤트
- [docs/glossary.md](docs/glossary.md): 명칭 대조표(FC·DS 일본어·DS 영어·한글 팬패치), 본문은 [docs/glossary-table.md](docs/glossary-table.md)
- [docs/extras.md](docs/extras.md): DS 판에서 늘어난 것과 이식 판단
- [docs/param-format.md](docs/param-format.md): `PARAM` 표(동료 대화 조건·몬스터·가게·メダル·카지노·얻는 물건)
- [docs/graphics-format.md](docs/graphics-format.md): 그래픽 형식(텍스처·인물 팩·DSSA 조립 애니메이션·3D 맵과 배치표·2D 아이콘·글꼴), 참고용 추출과 갤러리
- [docs/sound-format.md](docs/sound-format.md): 소리 묶음(SDAT·SSEQ·SBNK·SWAR·STRM), 게임이 곡을 고르는 함수, 곡 목록과 장면·FC·DQ5 대응, 효과음, 참고용 추출과 갤러리
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
| `ndstext.py` | 대사 파일 읽기(`dump`, `--kr` 로 한글판), 이름 표(`names`), 대조표(`glossary`), 통계(`stats`), 동료 대화 문장(`talk`), 실행 파일의 Shift_JIS 문자열과 포인터(`sjis`) |
| `ndsscript.py` | 이벤트 스크립트 `SCRIPT/<맵>.bin` 의 블록 나무(`tree`), 명령 목록(`dump`, 메시지 명령 옆에 문장), 전체 검사(`stats`) |
| `ndsparam.py` | `PARAM` 표: 몬스터(`monsters`, FC 와 짝 찾기), 아이템 번호 대조(`items`), 가게(`shops`), 카지노·メダル(`casino`), 얻는 물건(`chests`), 동료 대화 조건(`talk`), 대사 파일을 부르는 스크립트(`scripts`). [docs/param-format.md](docs/param-format.md) |
| `ndskr.py` | 한글 대응표 검사(`check`)와 다시 만들기(`draft`) |
| `ndsgfx.py` | 그래픽 디코더. `survey` 폴더·헤더별 파일 수, `export OUT` 으로 인물·몬스터(조립·애니메이션 WebP)·맵 텍스처와 위에서 본 렌더링·전투 배경·세계 지도(WTEX·기호)·3D 인물·효과 애니메이션·아이콘·글꼴·효과·타이틀을 PNG 로(`--only` 단계, `--kr work/nds/kr` 한글판 글꼴·로고), `gallery OUT` 으로 `index.html`. 결과는 비공개 에셋 저장소에만 |
| `ndsvram.py` | desmume 세이브스테이트에서 메인 RAM·VRAM·I/O 레지스터·팔레트를 꺼냄. `info` 레이어 설정, `bg` 텍스트 BG 그림 |
| `ndsgfxfig.py` | 그래픽 형식 문서의 그림(`images/nds-gfx-*`)을 다시 만듦 |
| `ndsplay.py` | desmume libretro 코어(`DESMUME_CORE`)를 화면 없이 돌리며 버튼·터치를 넣고 화면 저장(`every N K 이름`), RAM 읽기·쓰기·고정(`peek`·`poke`·`freeze`·`until`), 세이브스테이트 |
| `ndswarp.py` | 장면 이동(`map`, `--time` 시간대·`--no-encounter`), 필드 워프(`field`), 진행도 프리셋(`presets`·`preset`), 전투 테스트로 몬스터 고르기(`battle`), 부팅 디버그 메뉴로 시작(`boot`), 장 시작 세이브스테이트(`chapters`), 맵 544개 화면 모음(`screens`). [docs/debug.md](docs/debug.md) |
| `ndsvram.py` | 세이브스테이트에서 VRAM·레이어 레지스터·팔레트를 꺼내 레이어 설정(`info`)과 BG 화면(`bg`)을 그림 |
| `ndsgfxfig.py` | `images/nds-gfx-*` 그림을 롬에서 다시 만듦 |
| `ndssound.py` | 소리 묶음 읽기. `info` SDAT 목록, `export OUT` 으로 곡(원본 SSEQ·MIDI·합성 WAV)·효과음·샘플과 폴더별 `index.json`, `maps` 맵 곡 표, `scenes` 에뮬레이터로 장면마다 곡·효과음 요청 기록, `summary`·`gallery`. 결과는 비공개 에셋 저장소에만. [docs/sound-format.md](docs/sound-format.md) |
| `ndsfigures.py` | `images/` 의 일지 그림을 다시 만듦 |
| `ndsassets.sh` | 비공개 에셋 저장소의 `nds/dq4/` 전체를 롬에서 다시 만들고 동기화([아래](#에셋-다시-만들기)) |

표는 [tables/](tables/) 에 있습니다. `kr-font.tsv` 는 한글 팬패치의 「일본어 코드 → 한글 음절」 표, `hangul-freq.json` 은 `draft` 가 쓰는 음절 빈도입니다.

## 에셋 다시 만들기

비공개 에셋 저장소(`perfectacle/sfc-dq4-assets`)의 `nds/dq4/` 는 이 저장소와 두 롬만으로 다시 만들 수 있습니다. 저장소 최상위에서 한 줄로 돌립니다.

```sh
export DESMUME_CORE=/path/to/desmume_libretro.dylib   # 맵 화면·소리 장면용, docs/debug.md 「준비」
nds/dq4/tools/ndsassets.sh OUT <sfc-dq4-assets>        # 둘째 인자를 빼면 OUT 에만 만듦
STEPS="gfx screens" nds/dq4/tools/ndsassets.sh OUT     # 단계 고르기(unpack gfx screens sound)
```

순서는 롬 SHA-1 확인 → 풀기(`work/nds/{jp,kr}` 가 없을 때만) → 그래픽(`ndsgfx.py export`) → 맵 화면(`ndswarp.py screens`) → 소리(`ndssound.py export`·`scorecheck`·`scenes` 4조각·`summary`·`gallery`) → 첫 페이지(`ndsgfx.py gallery`, 옆 폴더 링크가 들어가도록 마지막) → 동기화입니다. 동기화는 만든 단계의 폴더만 `rsync --delete` 로 맞추고(그래픽은 `screens/`·`sound/`·`README.md` 를 뺀 최상위, 맵 화면은 `screens/`, 소리는 `sound/`), 최상위·`screens/`·`sound/` 마다 커밋 해시·롬 SHA-1·명령을 적은 `SOURCE.txt` 를 씁니다. 손으로 쓴 안내 `README.md` 는 지우지 않습니다. 전체는 약 35분(그래픽·맵 화면 23분, 소리 11분) 걸립니다.

깨끗한 폴더에 다시 만들어 에셋 저장소(커밋 `0761722`)와 맞춘 결과입니다. 자세한 과정은 아래 「해킹 일지」의 2026-10-26-02 에 있습니다.

| 폴더 | 파일 | 바이트까지 같음 | 다름과 이유 |
| --- | --- | --- | --- |
| 그래픽(최상위, `screens/`·`sound/` 밖) | 4,289 | 4,289(PNG·WebP·`manifest.json`·`index.html`) | 없음. `SOURCE.txt` 만 새로 씀 |
| `screens/` | 544장 | 431 | 113장. `fk01` 1장은 일부러 바꿈(전에는 `ckout` 화면, 이제 天空城). 112장은 맵 인물 걸음·물·불꽃·카메라 위치. 다른 픽셀은 전체의 0.59%, 한 장 중앙값 805픽셀 |
| `sound/` | 2,520 | 2,517 | `songs/index.json`·`gallery/index.html` 의 한 줄: 에셋은 6장 필드 곡을 선두 7명(マーニャ 포함)으로 쟀고 지금 `scenes` 는 6명만 잼. `SOURCE.txt` 는 새로 씀 |

`scorecheck` 는 곡 50개(음표 98,679)·효과음 634개(음표 3,460) 모두 일치했습니다. 그래픽은 실행마다 바이트까지 같습니다. 맵 화면은 desmume 시계가 호스트 시각을 따라 실행마다 84장이 달랐으므로, `screens` 가 시계를 고정합니다. 고친 뒤 세 번 돌린 544장은 서로 바이트까지 같습니다. 에셋의 맵 화면은 고치기 전에 찍어서, 다른 112장은 다시 만들 수 없습니다. 그래서 에셋의 `screens/` 를 이번 결과로 바꿨습니다.


- [2026-10-25-01: 대사 파일과 한글 팬패치 글꼴 읽기](journal/2026-10-25-01-text.md)
- [2026-10-25-02: NDS 그래픽 형식 풀기와 참고용 추출](journal/2026-10-25-02-graphics.md)
- [2026-10-25-03: 동료 대화 표](journal/2026-10-25-03-talk.md)
- [2026-10-25-04: 디버그 메뉴·진행도 프리셋으로 장 시작 세이브스테이트 만들기](journal/2026-10-25-04-debug.md)
- [2026-10-25-05: 그래픽의 남은 것, 에뮬레이터 화면과 맞대기](journal/2026-10-25-05-graphics2.md)
- [2026-10-25-06: 메시지 번호, 대사 표지, 실행 파일 문자열, 이벤트 스크립트](journal/2026-10-25-06-text2.md)
- [2026-10-25-07: PARAM 표로 늘어난 내용 가르기, 동료 대화 조건](journal/2026-10-25-07-param.md)
- [2026-10-25-08: 조우 끄기·필드 워프·장 번호와 플래그·메시지 디버그](journal/2026-10-25-08-debug2.md)
- [2026-10-25-09: 전투 테스트 Select 모드와 fk01](journal/2026-10-25-09-debug3.md)
- [2026-10-25-10: 동료 대화 거르기 루틴, 아이템 표, 남은 PARAM 칸](journal/2026-10-25-10-param2.md)
- [2026-10-25-11: 스크립트 명령표와 대사 표지·변수의 코드](journal/2026-10-25-11-script.md)
- [2026-10-25-12: 시간대·인물 레코드·필드 좌표 범위·메시지 디버그 키·fk01 조건](journal/2026-10-25-12-debug4.md)
- [2026-10-25-13: 필드 기호·WTEX, ubtl, DSSA 플래그, LOCN, 3D 효과 재생](journal/2026-10-25-13-graphics3.md)
- [2026-10-25-14: 주문 배우는 표, ドラン 의 고정 능력치, 상태 이상 칸](journal/2026-10-25-14-debug5.md)
- [2026-10-25-15: 장비 인물 비트, 몬스터 내성, 동료 대화 줄 수와 조건 값](journal/2026-10-25-15-param3.md)
- [2026-10-25-16: 소리 묶음(SDAT) 풀기와 곡이 울리는 장면](journal/2026-10-25-16-sound.md)
- [2026-10-25-17: 이민 마을 단계 전환, 얻는 물건 자리와 종류](journal/2026-10-25-17-param4.md)
- [2026-10-25-18: 가게 여는 명령과 가게 레코드 고르기, 스크립트 명령 다시 시험](journal/2026-10-25-18-script2.md)
- [2026-10-25-19: 이민자 수, 가게 표 자리, 맵 안 임시 플래그](journal/2026-10-25-19-param5.md)
- [2026-10-25-20: 상태 이상 번호와 ドラン 고정 블록](journal/2026-10-25-20-debug6.md)
- [2026-10-25-21: 가게 표는 ARM9 안, 레코드 고르기, 몬스터 내성 칸 바로잡기](journal/2026-10-25-21-param6.md)
- [2026-10-26-01: 곡·효과음 악보를 FC 와 같은 json·txt 로](journal/2026-10-26-01-score.md)
- [2026-10-26-02: 에셋을 롬에서 처음부터 다시 만들기](journal/2026-10-26-02-repro.md)
- [2026-10-26-03: 스크립트 명령 처리 함수 분류, 칸·상태 비트·깃발 종류](journal/2026-10-26-03-script3.md)
- [2026-10-26-04: 글자 효과음이 나는 길, `%a` 값을 대는 코드, 메뉴의 빈 글자, PARAM 나머지 표](journal/2026-10-26-04-text3.md)
- [2026-10-26-05: 행동 표, 상태 번호, 내성 값 1·2, 동료 대화의 세 값](journal/2026-10-26-05-actions.md)
- [2026-10-26-06: 메모리 감시 코어로 DSSA 반투명·동작 표·LOCN·필드 지도 번호 찾기](journal/2026-10-26-06-graphics4.md)
