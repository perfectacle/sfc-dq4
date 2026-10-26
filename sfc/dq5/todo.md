# dq5 남은 일

아직 확인하지 못한 것과 다음에 할 일입니다. 위에 있을수록 먼저 합니다. 끝낸 항목은 지우고 결과는 형식 문서와 해킹 일지에 남깁니다. 트랙과 고치는 법은 [tracks](../../.agents/skills/tracks/SKILL.md) 를 봅니다.

SFC DQ5 엔진 분석. 시작점은 [handoff.md](handoff.md). 결과 문서: [dq5-map-format.md](docs/dq5-map-format.md), [dq5-field-format.md](docs/dq5-field-format.md), [dq5-text-format.md](docs/dq5-text-format.md), [dq5-data-format.md](docs/dq5-data-format.md), [dq5-graphics-format.md](docs/dq5-graphics-format.md).

- **소리**: 곡 이름(사용자가 주면 들어 보기 페이지에 반영), SPC 스크립트 연산 `03`·`04`·`11`~`17` 의 실측.
- **일행 관리의 남은 것**: 신부를 고른 뒤 1F/08 에서 하인·신부가 (29,23) 앞에 멈춰 결혼식(1F/01)까지 이어지지 않는 까닭, 석상 뒤 칸 0 의 아내가 일행으로 돌아오는 곳, 레코드 `+22` 를 つよさ 창 칭호로 확인([dq5-data-format.md 「사람 동료 칸」](docs/dq5-data-format.md#사람-동료-칸-7e294a)).
- **그래픽 내보내기의 남은 것**: 전투 연출을 입구 상태 없이 롬만으로 그리기(입구 상태 한 벌을 넣은 `dq5fxvm.py --clock` 은 139벌 중 135벌 같음, `0C`·`6F` 는 처리 도중 NMI 가 끼는 명령이 다름)·`3E` 의 `DDDC` 를 부르는 장면.
- **텍스트의 남은 것**: 한글 넣기([dq5-hangul-format.md](docs/dq5-hangul-format.md)): 창 2바이트 부호를 여러 글자로(캔버스 빌리기 또는 BG3 타일 칸 넓히기, 두 길의 근거는 문서, 고르기는 사람 몫), 옮긴 레코드 자리 `7E:1ABC`~ 의 정적 후보 중 코드 뱅크 미실행 6,659곳(직접 피연산자는 CDL 로 걸러 569곳 미확인), BG3 타일맵 자리: 모든 장면에서 비는 칸이 없어(실내 맵 21개가 `7800`, 필드·전투가 `4800`~) 장면마다 자리를 바꾸는 길의 실측, `21BF.5` 를 켜는 곳.
- **에셋 다시 뽑기의 남은 것**([일지 2026-10-26-34](journal/2026-10-26-34-repro.md)): Windows·Linux 판 MesenCE 에서도 `dq5assets.py` 결과가 바이트까지 같은지.
- **쓰기 도구(포팅용)**: 몬스터·물건·주문·피해량·동료 표는 `dq5tables.py`. 실내 맵은 `dq5mapwrite.py`. 배치 목록 컴파일은 `dq5mapcompile.py`, 필드 지도는 `dq5fieldwrite.py`. 남은 것: 필드 블록 정의·입구 표 쓰기, 이벤트·인물 스크립트 인코더, 대사 대량 넣기, 성장 표·조우 구역 레코드·상점 목록 쓰기. `dq5tables.py` 의 물건·주문 표 쓰기를 게임에서 실측.
