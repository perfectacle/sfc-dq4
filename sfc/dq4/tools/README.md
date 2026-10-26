# dq4 도구: SFC 포팅 결과물

저장소 최상위에서 `uv run --locked python sfc/dq4/tools/<스크립트>` 로 실행합니다. 모듈끼리는 같은 폴더에서 import 합니다. SFC 프로브(`lua/`)는 `"$PWD/sfc/dq4/tools/lua/<스크립트>"` 로 주고, 툴킷 `boot.lua` 드라이버는 [공통 도구](../../../tools/README.md) 의 `LIBDIR`·`seqlib.sh` 설정을 따릅니다. FC 원작 분석 도구는 [fc/dq4/tools/README.md](../../../fc/dq4/tools/README.md) 에 있습니다.

사용자가 채택한 타이틀은 `dq4titlelayers.py`와 `dq4titlelayerpatch.py`로 만듭니다. [채택본 재현 절차](../docs/dq4-title-animation.md)를 먼저 읽고, 정지 미리보기·전체 화면 교체 실험과 구분합니다.

| 스크립트 | 하는 일 |
| --- | --- |
| `dq4graphics.py [--check] [--output 폴더]` | 롬 없이 스프라이트·블록·샘플 맵·타이틀을 PNG·SFC 4bpp·팔레트로 출력. `--check` 는 파일을 쓰지 않고 반복 생성·왕복 검사 |
| `dq4romassets.py rom --out 폴더` | 라이안 정면의 DQ5 엔진 데이터·별도 롬·IPS와 역변환 검증 보고서 생성. 기존 공용 팔레트를 유지하는 색 변경 시안. [롬 삽입](../docs/dq4-rom-assets-format.md) |
| `dq4romgallery.py --input 폴더 --out 폴더` | ROM 변환 결과와 인물 시안의 비교 갤러리 생성. 시각 확인과 기술 검증 상태를 구분 |
| `dq4titlelayers.py --out 폴더` | 고정 전경·하늘·앞 구름·용의 128위상(12자세)과 차이 전송 데이터를 생성. [애니메이션 규격](../docs/dq4-title-animation.md) |
| `dq4titlelayerpatch.py --rom 롬 --input 폴더 --out 롬 [--asar 실행파일]` | 레이어별로 움직이는 DQ5 통합 롬·IPS 생성 |
| `dq4titleanimation.py --out 폴더` | 전체 화면 프레임 교체 실험용 변환. 최종 레이어 방식과 구분 |
| `dq4titleassets.py [--out 폴더] [--assets-dir 폴더]` | 선택된 실제 크기 한글 타이틀을 다시 줄이지 않고 PNG·CHR·MAP·PAL과 갤러리로 출력. [타이틀 규격](../docs/dq4-title-format.md) |
| `dq4titlepatch.py --rom 롬 --input 폴더 --out 롬 [--asar 실행파일]` | 초기 정지 타이틀을 DQ5 시작 구간에 연결한 실험 롬·IPS 생성. 페이드·광택·입력·메뉴 복귀. [연결 규격](../docs/dq4-title-format.md#dq5-타이틀-구간-연결) |
| `dq4titlepreview.py --input 폴더 --out 롬 [--asar 실행파일]` | 타이틀 에셋으로 독립 64KiB SFC 미리보기 롬 생성. DQ5 삽입본과 구분 |
| `dq4overture.py text\|build\|tempo-map\|render` | FC 서곡 악보를 NDS 템포·DQ5 악기로 편곡해 타이틀 롬의 시퀀스 10 에 갈래로 넣음(4MB 롬·IPS). `tempo-map` 은 NDS 녹음과 DTW 로 템포 지도를 다시 잼, `render` 는 프로브 결과를 .spc·.wav 로. [타이틀 서곡](../docs/dq4-overture-format.md) |
| `dq4menupatch.py build\|sheet` | 서곡 롬 위에 모험의 서 메뉴·조합형 이름 입력·메뉴 메시지를 한글로(4MB 롬·IPS). `DQ4_GALMURI` 의 Galmuri BDF 와 `ASAR` 실행 파일 필요. `sheet` 는 문구 열 그림. [메뉴 한글화](../docs/dq4-menu-format.md), [이름 입력](../docs/dq4-name-entry-format.md) |
| `dq4menumsg.py [그림]` | `dq4menupatch.py build` 가 부르는 메뉴 메시지 모듈. 보행 메시지를 새 허프만 트리로 뱅크 `65`~ 에 옮기고 한글 글자를 넣음. 직접 실행하면 세 메시지 미리보기. [메뉴 메시지](../docs/dq4-menu-format.md#메뉴-메시지) |
| `dq4nameentrycheck.py --rom 롬 --symbols 심볼 --out 새폴더` | MesenCE에서 조합·삭제·Y 완료·새 게임 이름을 검사하고 입력 칸 VRAM을 비교. `MESENCE` 실행 파일 필요. [재현](../docs/dq4-name-entry-format.md#재현) |
| `dq4namecursorcheck.py --rom 롬 --symbols 심볼 --out 새폴더` | MesenCE 실제 입력으로 빠른 방향 전환·겹침·반복·빈칸 경계와 Start 이동을 검사. `MESENCE` 실행 파일 필요. [재현](../docs/dq4-name-entry-format.md#재현) |
| `dq4namegamecheck.py --rom 롬 --state work/state/ship.mss --out 새폴더` | 선실에서 주인공 이름을 넣고 메시지 첫 코드를 `1012` 로 바꿔, 한글·가나 이름이 맞는 글자 코드가 되는지 MesenCE 로 검사. `MESENCE` 필요. [게임 안 이름](../docs/dq4-name-entry-format.md#게임-안-이름) |
| `dq4namesave.py show\|convert` | SRAM 주인공 이름의 부호(한글·예전 한글·가나)를 보고, 고른 칸의 예전 한글 이름을 표시 있는 부호로 바꿔 새 파일에 씀. [예전 저장](../docs/dq4-name-entry-format.md#예전-저장) |
| `dq4namegame.py` | `dq4menupatch.py build` 가 부르는 게임 안 메시지 이름 모듈(`24:A7D5` → `24:9E11`) |
| `dq4bg3tiles.py 장면=VRAM덤프 ...` | VRAM 덤프에서 BG3 타일맵이 가리키는 칸과 빈 칸을 셈. [게임 안 창 한글 조사](../docs/dq4-window-text-format.md) |
| `dq4bg3slot.py` | `dq4menupatch.py build` 가 마지막에 부르는 BG3 타일맵 옮기기 모듈(`60:8300`~). 필드 `7800`, 실내 `3C00`, `3C00` 을 쓰거나 가리키는 맵은 표(`MAP_SLOTS`)의 자리. `40`~`5C` 자리 맵의 전투는 `7800` |
| `dq4bg3slotcheck.py --old 원래롬 --new 새롬 --state work/state/ship.mss --out 새폴더 [--maps 맵,...]` | 실내 맵마다 순간이동해 명령 창을 열고, BG3 타일맵을 옮긴 롬이 버퍼와 같은 타일맵을 보이는지·옛 자리를 건드리지 않는지 원래 롬과 견줌. `MESENCE` 필요. [BG3 타일맵 옮기기](../docs/dq4-window-text-format.md#bg3-타일맵-옮기기) |
| `lua/dq4bg3slotwarp.lua` | `dq4bg3slotcheck.py` 가 부름. `dq5warp.lua` 를 돌리며 30프레임마다 맵, `$0725`, 타일맵과 버퍼 `7E:5000` 차이, 옛 자리 `1C00`~`1FFF` 변화를 `bg3.txt` 에 적음. `SHOTS` 프레임 화면도 남김 |
| `dq4soundcatalog.py --assets 폴더 [--dq5-rom 롬] --out JSON` | NDS 곡·효과음 목록, FC 장면 대응, DQ5 재사용 후보와 숙박곡 비교. [사운드 포팅](../docs/dq4-sound-port-format.md) |
| `dq4soundport.py export --assets 폴더 --out 폴더` | NDS 악보 JSON 을 DQ5 시퀀스로(템포·세기 합치기, 꼬리를 남기는 성부 배분, 되풀이·깊이 3 부르기로 묶기와 KOF 미리 보기 검산, 손실 보고서) |
| `dq4soundbank.py --score JSON --assets 폴더 --out 폴더 [--max-rate 8000]` | 곡에 쓰이는 NDS PCM 을 S-DSP 계산으로 BRR 로(무음 첫 블록, 실기 SNR) |
| `dq4soundpatch.py --base 롬 --replace 자리=JSON --bank 폴더 --out 롬 [--map-fades] [--preview 자리]` | 시퀀스·샘플을 롬에 넣음(4MB 롬·IPS). `--map-fades` 는 프레임을 기다리지 않는 맵 전환 페이드, `--preview` 는 청취용 타이틀 곡 교체 |
| `dq4soundset.py --base 롬 --assets 폴더 --song 자리=NDS곡 ... --out 롬 [--stream 자리=바이트] [--budget 자리=바이트] [--preview 자리] [--map-fades]` | 곡마다 SPC 샘플 예산을 정하고 샘플을 줄여(영역 합치기·표본율·자르기) 여러 곡을 한꺼번에 넣음. `--stream` 은 먼저 쓰이는 샘플만 그 바이트 안에서 곡 앞에 보내고 나머지는 곡이 울리는 동안 보냄(늦은 샘플의 음마다 악기 명령을 다시 씀). `--budget` 은 계산한 샘플 예산 대신 그 값을 씀(청취 승인한 샘플을 그대로 둘 때). 보고서에 줄인 것과 도착 전 음을 남김 |
| `dq4soundcheck.py 롬 OUT --song 자리` | `lua/dq4overturespc.lua` 결과로 SPC 의 시퀀스·샘플, KON 시각·SRCN·음 간격을 견줌. 곡 뒤 샘플이 도착하기 전의 음은 뺌 |
| `lua/dq4soundstate.lua` | 세이브스테이트를 불러온 뒤 롬의 드라이버 IPL 블록(곡 묶음 표)을 SPC RAM 에 다시 쓰고 `SOUND_PROBE` 를 돌림. 롬 목록에 없는데 상태에 고정된 시퀀스는 고정을 풂. 곡 묶음을 바꾼 롬을 세이브스테이트로 시험할 때 필요. `AT` 사용 |
| `lua/dq4soundload.lua` | `SOUND_PROBE` 로 걸어, 샘플이 SPC 에 다 받아진 프레임(`SAMPLES`), 목소리마다 울리기 시작한 프레임과 SRCN, 곡(`SONGS`)이 오르내린 프레임을 `load.txt` 로. 이어서 `NEXT_PROBE` 를 돌림 |
| `lua/dq4soundcmdlog.lua` | 전원부터 `INPUT`(버튼@프레임:길이)·`AFTER`(A 연타 간격)로 진행하며 소리 대기열 명령·부른 자리와 300프레임마다 화면을 남김. `OUT`, `MAXF`, `AFTERFROM` 사용 |
| `lua/dq4overturespc.lua` | 서곡 롬을 전원부터 돌려 곡 10 이 시작한 뒤의 SPC 상태와 DSP 쓰기(`dspw.txt`), 곡 시작·샘플 도착(`events.txt`)을 남김. `OUT`, `MAXF`, `SONG`, `SEQ`, `DUMPAT`, `QUIET` 사용 |
| `lua/dq4titleintegrationcheck.lua` | 통합 롬의 화면·VRAM·음악·메뉴 진입 관찰. `OUT`, `MAXF`, `EVERY`, `FROM`, `SEQ`, `RESETAT`, `TRACE_DMA`, `MOTION_PC` 사용 |
| `lua/dq4titlecheck.lua` | 독립 미리보기의 화면·VRAM·CGRAM 관찰. `OUT`, `FRAME` 사용 |
| `dq4pixels.py` | 스프라이트·지형 제작물을 모으는 모듈 |
| `dq4sprites.py` | DQ4 인물 9명의 16×24 스프라이트 원본. 인물별 팔레트와 색 번호 문자 행렬(방향마다 정지 자세, 보행은 몸만 바꿈). 실행하면 색 수와 행 폭 검사 |
| `dq4spritedrafts.py` | 16×24 를 끝까지 쓰는 정면 시안(톨네코·주인공). 실행하면 색 수와 평평함 지표 |
| `dq4spritecheck.py 행렬파일...` | 색 번호 행렬의 평평함 지표(같은 색 연속 길이·좌우 비대칭·색 경계 밀도). 잘 그린 참고 그림과 견줄 때 |
| `dq4spritelab.py hero\|data 이름\|compare 이름` | `hero` 는 `lua/dq4objdump.lua` 덤프에서 DQ5 주인공 4방향을 16×24 로 복원(`work/dq4-sprites/dq5-hero.png`), `data` 는 `lua/dq4sprite.lua` 용 4bpp·팔레트 Lua, `compare` 는 원작과 같은 배경·8배로 나란히. [sfc/dq4/docs/dq4-sprite-format.md](../docs/dq4-sprite-format.md) |
| `lua/dq4romcheck.lua` | `STATE`·`ROUTE`·`SEQ` 입력으로 장면 재진입을 관찰하고 로더 횟수·WRAM·VRAM·OAM·CGRAM·화면을 기록. 그래픽 주입 없음. `OUT`, `MAXF`, `EVERY`, `FROM`, `DUMPF` 사용. [실측 명령](../docs/dq4-rom-assets-format.md#mesence-실측-결과) |
| `lua/dq4objdump.lua` | SFC: 필드 세이브스테이트(`STATE`)에서 4방향으로 걷다 멈춘 VRAM·OAM·CGRAM 과 주인공을 숨긴 화면을 `OUT` 에 덤프 |
| `lua/dq4sprite.lua` | SFC: 필드 `01/00` 에서 주인공 OBJ 를 `DATA` 의 스프라이트로 프레임마다 바꿔 보여 줌(VRAM `D000`·OAM 0~5·팔레트 3). `STATE`, `OUT`, `TEST=1` 이면 4방향 자동 보행 후 `walk-test.txt`. 영구 삽입 아님 |
| `dq4terrain.py` | 성·마을 블록 49종과 이름 격자 맵의 편집 원본 |
| `dq4title.py` | 보관한 생성 원본을 256×224, 타일별 8개 BG 팔레트 타이틀로 변환하는 모듈 |
| `dq4figures.py` | 제작 원본으로 그래픽 문서의 WebP·합성 보행 애니메이션 재생성(롬 불필요) |

스프라이트·맵 출력은 채택되지 않은 초기 시안입니다. 타이틀·일러스트만 보존 대상으로 평가됐으며, 후속 작업은 [그래픽 핸드오프](../handoff.md)를 먼저 읽습니다. 그래픽 출력의 배치·제약은 [dq4-graphics.md](../docs/dq4-graphics.md)에 있습니다. 생성 원본과 프롬프트는 `sfc/dq4/tools/dq4art/` 에 보관합니다. `uv run --locked python sfc/dq4/tools/dq4graphics.py` 로 기본 출력 `work/dq4-graphics/` 를 만들고, `uv run --locked python sfc/dq4/tools/dq4figures.py` 로 문서 그림을 다시 만듭니다.

## 환경 그래픽

`uv run --locked python sfc/dq4/tools/dq4environment.py --out work/environment --rom rom/dq4.nes --references "$DQ4_ASSETS"`로 FC 원작의 색 역할과 DQ5 색·도트 구조로 새로 그린 환경 에셋, FC 배치 비교 맵, SFC 타일 데이터와 갤러리를 만듭니다. `DQ4_ASSETS`는 비공개 `sfc-dq4-assets` 체크아웃입니다. 캐릭터·몬스터는 포함하지 않습니다.

`dq4environmentprobe.py`는 독립 SFC 미리보기의 MesenCE 화면·VRAM·팔레트를 검사합니다. `dq4environmentrom.py --out 폴더`는 FC 블록 시트 `0A`·`0E` 의 실내 맵 16개를 DQ5 실내 맵 자리에 넣는 `dq5patch/1` 목록을 만들고, `dq4environmentromcheck.py --rom 롬 --out 새폴더`는 MesenCE로 워프해 게임 메모리로 다시 그린 맵·통행 속성·다른 맵 복원을 검사합니다(`lua/dq4environmentdump.lua`, `MESENCE`·`LIBDIR` 필요). 출력 규격과 실행 인수는 [환경 그래픽 문서](../docs/dq4-environment-format.md)에 있습니다.
