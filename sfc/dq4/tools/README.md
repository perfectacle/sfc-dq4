# dq4 도구: SFC 포팅 결과물

저장소 최상위에서 `uv run --locked python sfc/dq4/tools/<스크립트>` 로 실행합니다. 모듈끼리는 같은 폴더에서 import 합니다. SFC 프로브(`lua/`)는 `"$PWD/sfc/dq4/tools/lua/<스크립트>"` 로 주고, 툴킷 `boot.lua` 드라이버는 [공통 도구](../../../tools/README.md) 의 `LIBDIR`·`seqlib.sh` 설정을 따릅니다. FC 원작 분석 도구는 [fc/dq4/tools/README.md](../../../fc/dq4/tools/README.md) 에 있습니다.

| 스크립트 | 하는 일 |
| --- | --- |
| `dq4graphics.py [--check] [--output 폴더]` | 롬 없이 스프라이트·블록·샘플 맵·타이틀을 PNG·SFC 4bpp·팔레트로 출력. `--check` 는 파일을 쓰지 않고 반복 생성·왕복 검사 |
| `dq4romassets.py rom --out 폴더` | 라이안 정면의 DQ5 엔진 데이터·별도 롬·IPS와 역변환 검증 보고서 생성. 기존 공용 팔레트를 유지하는 색 변경 시안. [롬 삽입](../docs/dq4-rom-assets-format.md) |
| `dq4romgallery.py --input 폴더 --out 폴더` | ROM 변환 결과와 인물 시안의 비교 갤러리 생성. 시각 확인과 기술 검증 상태를 구분 |
| `dq4pixels.py` | 스프라이트·지형 제작물을 모으는 모듈 |
| `dq4sprites.py` | DQ4 인물 9명의 16×24 스프라이트 원본. 인물별 팔레트와 색 번호 문자 행렬(방향마다 정지 자세, 보행은 몸만 바꿈). 실행하면 색 수와 행 폭 검사 |
| `dq4spritelab.py hero\|data 이름\|compare 이름` | `hero` 는 `lua/dq4objdump.lua` 덤프에서 DQ5 주인공 4방향을 16×24 로 복원(`work/dq4-sprites/dq5-hero.png`), `data` 는 `lua/dq4sprite.lua` 용 4bpp·팔레트 Lua, `compare` 는 원작과 같은 배경·8배로 나란히. [sfc/dq4/docs/dq4-sprite-format.md](../docs/dq4-sprite-format.md) |
| `lua/dq4romcheck.lua` | `STATE`·`ROUTE`·`SEQ` 입력으로 장면 재진입을 관찰하고 로더 횟수·WRAM·VRAM·OAM·CGRAM·화면을 기록. 그래픽 주입 없음. `OUT`, `MAXF`, `EVERY`, `FROM`, `DUMPF` 사용. [실측 명령](../docs/dq4-rom-assets-format.md#mesence-실측-결과) |
| `lua/dq4objdump.lua` | SFC: 필드 세이브스테이트(`STATE`)에서 4방향으로 걷다 멈춘 VRAM·OAM·CGRAM 과 주인공을 숨긴 화면을 `OUT` 에 덤프 |
| `lua/dq4sprite.lua` | SFC: 필드 `01/00` 에서 주인공 OBJ 를 `DATA` 의 스프라이트로 프레임마다 바꿔 보여 줌(VRAM `D000`·OAM 0~5·팔레트 3). `STATE`, `OUT`, `TEST=1` 이면 4방향 자동 보행 후 `walk-test.txt`. 영구 삽입 아님 |
| `dq4terrain.py` | 성·마을 블록 49종과 이름 격자 맵의 편집 원본 |
| `dq4title.py` | 보관한 생성 원본을 256×224, 타일별 8개 BG 팔레트 타이틀로 변환하는 모듈 |
| `dq4figures.py` | 제작 원본으로 그래픽 문서의 WebP·합성 보행 애니메이션 재생성(롬 불필요) |

스프라이트·맵 출력은 채택되지 않은 초기 시안입니다. 타이틀·일러스트만 보존 대상으로 평가됐으며, 후속 작업은 [그래픽 핸드오프](../handoff.md)를 먼저 읽습니다. 그래픽 출력의 배치·제약은 [dq4-graphics.md](../docs/dq4-graphics.md)에 있습니다. 생성 원본과 프롬프트는 `sfc/dq4/tools/dq4art/` 에 보관합니다. `uv run --locked python sfc/dq4/tools/dq4graphics.py` 로 기본 출력 `work/dq4-graphics/` 를 만들고, `uv run --locked python sfc/dq4/tools/dq4figures.py` 로 문서 그림을 다시 만듭니다.
