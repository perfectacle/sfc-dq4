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
| 대사 | MPT0 952개(일본어 207, 영·불·독·서·이 147씩), 문자열 91,398개 전부 해독. 메시지 번호 = 머리 `+08` + 색인 번호. `@cN@` 은 글자 효과음 301~303, `%a` 는 변수 이름표 92칸(주인공·마을 이름·돈 실측), `@a` 는 맵 인물 오브젝트와 짝. 한글판 대사 창 13장을 화면과 글자 단위로 대조 | `ndstext.py`, [text-format.md](docs/text-format.md) |
| 한글 대응표 | 1400자([tables/kr-font.tsv](tables/kr-font.tsv)), KS 순서 위반 0, 확인 단어 18개 일치, 전수 눈 대조. `98A8` = 훔 | `ndskr.py check` |
| 대조표 | 이름 표 8개, 813줄 | [glossary.md](docs/glossary.md) |
| 늘어난 것 | 6장 805줄, 동료 대화 7,796줄, 이민 마을 796줄 등 | [extras.md](docs/extras.md) |
| 그래픽 | 인물 187팩, 몬스터 303 전부 조립(좌우·상하 뒤집기), 맵·전투 배경 675, 효과 188, 3D 효과 17, 아이콘 424, 세계 지도 4장과 gotmap·yamimap(칸 값 → 칩, 기호 74곳), 인물·모델 애니메이션(BCA0·BTA0·BMA0). 필드 주인공은 화면과 471픽셀 중 469 일치. `ubtl*` 는 쓰이지 않는 자료. 결과는 비공개 저장소 `nds/dq4/` | [graphics-format.md](docs/graphics-format.md), `ndsgfx.py export`, `ndsvram.py` |
| 동료 대화 표 | `PARAM/param_player_talk1`~`6.dat`, 44바이트 레코드 7,209개 전부 대사와 맞음. 거르는 루틴 `0x02036530` 을 그대로 적용하면 프리셋 280곳의 실제 통과 목록과 모두 같음(조건 종류 18가지, 일행, 시간대, 우선순위). 고르기는 난수, 들은 20문장 제외 | `ndsparam.py talk`, [param-format.md](docs/param-format.md#동료-대화-표) |
| PARAM·스크립트 | 몬스터(60바이트, 내성 15칸 FC 와 153~156/156 일치)·아이템 강도와 장비 인물(ARM9 `0x02095594`)·가게(ARM9 표, 맵 이름 앞 두 글자로 고름)·メダル·카지노·얻는 물건(`FMAP` `+0x2C` 로 자리) 표. 이민 마을 단계는 이민자 수 `0x020ED358` 1·5·9·13·17명. `SCRIPT` 396개, 분기표 `0x0201FDC0`, 명령 50여 가지 실측, 6장 이벤트 명령 단위 | [param-format.md](docs/param-format.md), [script-format.md](docs/script-format.md), `ndsscript.py` |
| 사운드 | SDAT 의 곡 50(+서곡 STRM)·효과음 634·샘플 362·뱅크 54 추출(원본 SSEQ·MIDI·합성 WAV, 비공개 저장소 `nds/dq4/sound/`). 곡 시작 함수 훅으로 장면 26곡 실측, 맵 표 741건 중 733 일치. DS 에서 늘어난 곡(밤 곡, ピサロ 곡 등)과 FC·DQ5 장면 대응 | [sound-format.md](docs/sound-format.md), `ndssound.py` |
| 툴킷 | v0.8.0 의 `krpatch nds`(롬 풀기, NFTR 폰트 `nds font info`·`sheet`)·`krpatch xdelta apply`(LZMA 2차 압축 포함, 한글판 SHA-1 일치) | `krpatch nds font info` |
| 디버그·워프 | 부팅 디버그 메뉴(장면 `0x01`)·전투 테스트(`0x11`, Select 모드로 몬스터 지정)·메시지 디버그(`0x16`, 번호 키 화면 확인), 진행도 프리셋 347개 적용, 맵·필드 좌표 워프, 조우 끄기, 시간대 지정, 장 시작 세이브스테이트 `work/state/dq4ds-{boot,ch0..ch6,ch6-psaro}.state`, 맵 화면 544장(비공개 저장소 `nds/dq4/screens/`) | [debug.md](docs/debug.md), `ndswarp.py` |
| RAM | 장면 `0x021080AC`/요청 `0x021080B4`, 맵 이름 `0x020C4F44`, 필드 좌표 `[[0x020EC4F0]+0x70]`, 조우 비트 `0x020CE100 & 0x200`, 시간대 `0x020CE1B4`, 장 번호 `0x020EB9A8`, 이야기 플래그 `0x020CE7DC`, 맵 플래그 `0x020CE6DC`, 열었음 플래그 `0x020CE248`, 일행 `0x020C5614`, 인물 레코드 `0x020C5B74 + id×0x50C`(경험치·능력치·도구·주문·상태), 돈 `0x020C55F0`, 이민자 수 `0x020ED358` | [debug.md](docs/debug.md#ram-지도) |
| 에뮬레이터 | desmume libretro 코어([EMU-01](../../.agents/skills/analysis/SKILL.md#emu-01--에뮬레이터는-mesence)) | |

실험 출력은 원래 체크아웃의 `work/nds/`(풀어 둔 두 롬 `jp`·`kr`)에 둡니다. 워크트리에서는 `ln -s "$MAIN/work/nds" work/nds` 로 링크해 씁니다(롬 하나가 100MB 넘음).

## 다음에 할 일

분석 항목은 한 차례씩 모두 다뤘고, 남은 것은 [todo.md](todo.md) 에 문서별로 모았습니다. 남은 것 대부분은 패치에 직접 쓰이지 않는 세부입니다. DS 내용을 실제로 옮기기 시작할 때 그 기능 쪽부터 다시 봅니다.

1. **채택 이름** — 대조표를 사용자에게 보여 채택 열을 채웁니다.
2. **이식 설계** — [extras.md](docs/extras.md) 의 이식 판단과 [param-format.md](docs/param-format.md)·[script-format.md](docs/script-format.md) 의 동작 규칙을 근거로 DQ5 엔진 쪽 설계를 잡습니다. 동료 대화는 거르는 규칙까지 밝혀져 있습니다.
3. **사운드** — 곡 대응([sound-format.md](docs/sound-format.md#곡-목록))은 FC(`fc/dq4/docs/dq4-sound-format.md`)·DQ5(`sfc/dq5/docs/dq5-sound-format.md`) 사운드 분석과 함께 씁니다.

## 조심할 것

- 소유 파일은 `nds/dq4/` 아래 전부입니다. FC 쪽 이름은 dq4 트랙 도구(`fc/dq4/tools/dq4data.py`)를 읽기만 합니다.
- 롬에서 뽑은 대사 본문·그래픽은 `work/` 나 비공개 에셋 저장소에만 둡니다([ROM-01](../../.agents/skills/analysis/SKILL.md#rom-01--롬-데이터-금지)). 대조표처럼 단어 수준만 문서에 둡니다.
- 대사를 읽을 때 한글판은 `--kr` 을 줍니다. 그냥 읽으면 엉뚱한 한자가 나옵니다.
