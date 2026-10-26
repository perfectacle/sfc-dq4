# dq5 남은 일

아직 확인하지 못한 것과 다음에 할 일입니다. 위에 있을수록 먼저 합니다. 끝낸 항목은 지우고 결과는 형식 문서와 해킹 일지에 남깁니다. 트랙과 고치는 법은 [tracks](../../.agents/skills/tracks/SKILL.md) 를 봅니다.

SFC DQ5 엔진 분석. 시작점은 [handoff.md](handoff.md). 결과 문서: [dq5-map-format.md](docs/dq5-map-format.md), [dq5-field-format.md](docs/dq5-field-format.md), [dq5-text-format.md](docs/dq5-text-format.md), [dq5-data-format.md](docs/dq5-data-format.md), [dq5-graphics-format.md](docs/dq5-graphics-format.md).

- **소리**: 곡 이름(사용자가 주면 들어 보기 페이지에 반영), SPC 스크립트 연산 `03`·`04`·`11`~`17` 의 실측.
- **일행 관리의 남은 것**: 석상 장면 뒤 02/06 에서 オジロン 이 부르는 장면(석상 세이브스테이트가 `dq5warp.lua` 로 만든 것이라 플래그가 모자라 02/06 이 처음 왔을 때의 기본 목록 `10:9A2F` 로 열림), フローラ 갈래의 ヴェール·교회 단계(1F/08 의 문만 실측)([dq5-data-format.md 「사람 동료 칸」](docs/dq5-data-format.md#사람-동료-칸-7e294a) 실측 6·7, [일지 2026-10-26-51](journal/2026-10-26-51-party6.md)).
- **그래픽 내보내기의 남은 것**: 전투 연출을 입구 상태 없이 롬만으로 그리기(입구 상태 한 벌을 넣은 `dq5fxvm.py --clock` 은 139벌 중 135벌 같음, `0C`·`6F` 는 처리 도중 NMI 가 끼는 명령이 다름)·`3E` 의 `DDDC` 를 부르는 장면.
- **텍스트의 남은 것**: 한글 넣기([dq5-hangul-format.md](docs/dq5-hangul-format.md)): 창 2바이트 부호를 여러 글자로(캔버스 빌리기 또는 BG3 타일 칸 넓히기, 두 길의 근거는 문서, 고르기는 사람 몫), 옮긴 레코드 자리 `7E:1ABC`~ 의 정적 후보 중 코드 뱅크 미실행 6,659곳(직접 피연산자는 CDL 로 걸러 569곳 미확인), BG3 타일맵 자리: 모든 장면에서 비는 칸이 없어(실내 맵 21개가 `7800`, 필드·전투가 `4800`~) 장면마다 자리를 바꾸는 길의 실측, `21BF.5` 를 켜는 곳.
- **에셋 다시 뽑기의 남은 것**([일지 2026-10-26-34](journal/2026-10-26-34-repro.md)): Windows·Linux 판 MesenCE 에서도 `dq5assets.py` 결과가 바이트까지 같은지.
- **쓰기 도구(포팅용)**: 몬스터·물건·주문·피해량·동료 표는 `dq5tables.py`. 실내 맵은 `dq5mapwrite.py`. 배치 목록 컴파일은 `dq5mapcompile.py`, 필드 지도는 `dq5fieldwrite.py`(뱅크30~3F), 필드 블록·입구·도착 고정 표는 `dq5fieldtables.py`이며 세계0~2 지도 쓰기도 게임에서 확인. 이벤트·인물 스크립트는 `dq5eventwrite.py`·`dq5npcwrite.py`(인물은 기존 슬롯 안에서 교체). 성장·조우 구역·상점 고정 목록은 `dq5progresswrite.py`이며 레벨업·조우·상점과 물건 가격 쓰기를 게임에서 확인. 보행 대사 코드 목록은 `dq5textwrite.py`로 일괄 재압축하며 앞·뒤 메시지를 게임에서 확인. 인물 스크립트 길이 변경과 목록 재배치는 `dq5npcrelocate.py`로 694쌍·긴 스크립트 실행 5건을 게임에서 확인. 남은 것: 필드 표 항목 증설·재배치, 인물 수·순서·조건 편집과 새 목록 추가, 문자열 번역 편집·새 한글 글꼴 대량 삽입·전투 메시지/창/이름 쓰기, 성장·조우 레코드와 상점 품목 수 증설, 필드 조우 격자·실내 구역 연결·고정 무리·전투 이벤트 무리 쓰기. `dq5tables.py`의 가격 외 물건 필드·주문 표 쓰기를 게임에서 실측.
