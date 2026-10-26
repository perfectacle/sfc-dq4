# dq5 남은 일

아직 확인하지 못한 것과 다음에 할 일입니다. 위에 있을수록 먼저 합니다. 끝낸 항목은 지우고 결과는 형식 문서와 해킹 일지에 남깁니다. 트랙과 고치는 법은 [tracks](../../.agents/skills/tracks/SKILL.md) 를 봅니다.

SFC DQ5 엔진 분석. 시작점은 [handoff.md](handoff.md). 결과 문서: [dq5-map-format.md](docs/dq5-map-format.md), [dq5-field-format.md](docs/dq5-field-format.md), [dq5-text-format.md](docs/dq5-text-format.md), [dq5-data-format.md](docs/dq5-data-format.md), [dq5-graphics-format.md](docs/dq5-graphics-format.md).

- **소리**: 곡 이름(사용자가 주면 들어 보기 페이지에 반영).
- **일행 관리의 남은 것**: 신부를 고른 뒤 1F/08 에서 하인·신부가 (29,23) 앞에 멈춰 결혼식(1F/01)까지 이어지지 않는 까닭, 석상 뒤 칸 0 의 아내가 일행으로 돌아오는 곳, 레코드 `+22` 를 つよさ 창 칭호로 확인([dq5-data-format.md 「사람 동료 칸」](docs/dq5-data-format.md#사람-동료-칸-7e294a)).
- **그래픽 내보내기의 남은 것**: 전투 연출을 입구 상태 없이 롬만으로 그리기(입구 상태 한 벌을 넣은 `dq5fxvm.py --clock` 은 139벌 중 135벌 같음, `0C`·`6F` 는 처리 도중 NMI 가 끼는 명령이 다름)·`3E` 의 `DDDC` 를 부르는 장면.
- **텍스트의 남은 것**: 한글 넣기([dq5-hangul-format.md](docs/dq5-hangul-format.md)): 창 2바이트 부호를 여러 글자로(캔버스 빌리기 또는 BG3 타일 칸 넓히기, 두 길의 근거는 문서), 옮긴 레코드 자리 `7E:1ABC`~ 를 실행하지 않은 코드까지 증명(장면 열일곱의 접근 카운터는 0), BG3 타일맵을 옮길 자리(`3C00` 은 필드 글자, `4C00` 은 로고·전투 그림과 겹침, 즉값 열일곱은 `dq5hangul.py bg3move`)·BG1·BG2 글자 빌리기.
- **에셋 다시 뽑기의 남은 것**([일지 2026-10-26-34](journal/2026-10-26-34-repro.md)): 무리 `2F` 전투 칸 0 의 첫 바이트가 `E8`·HP 4500 이 되는 곳, 고정 시퀀스 곡을 `01 n` 으로 틀 때 `2B:C20F` 가 본 대기열 칸이 `FF` 인 까닭, Windows·Linux 판 MesenCE 에서도 `dq5assets.py` 결과가 바이트까지 같은지.
- **쓰기 도구(포팅용)**: 몬스터·물건·주문·피해량·동료 표는 `dq5tables.py`. 남은 것: 실내 맵·필드 지도 인코더, 이벤트·인물 스크립트 인코더, 대사 대량 넣기, 성장 표·조우 구역 레코드·상점 목록 쓰기. `dq5tables.py` 의 물건·주문 표 쓰기를 게임에서 실측.
