# dq4: FC DQ4 원작 분석

FC 「드래곤 퀘스트 IV」(일본판 Rev A) 원작 데이터를 분석하는 dq4 트랙의 폴더입니다. 맵·대사·인물·스크립트·표·플래그를 롬만으로 뽑아, SFC DQ5 엔진으로 옮길 때 쓸 수 있는 형태로 남깁니다. SFC 로 만드는 포팅 결과물(그래픽 등)은 [sfc/dq4/](../../sfc/dq4/README.md) 에 있습니다. 규칙은 [AGENTS.md](../../AGENTS.md), 롬 준비는 [저장소 README](../../README.md#원본-롬) 를 봅니다.

## 문서

- [handoff.md](handoff.md): dq4 트랙 시작점(목표, 도구 현황, 다음 할 일)
- [docs/dq4-ram-format.md](docs/dq4-ram-format.md): DQ4(FC) 필드 RAM(좌표·맵 번호·출구 표)과 뱅크 전환
- [docs/dq4-bank-format.md](docs/dq4-bank-format.md): DQ4(FC) BRK 뱅크 호출과 뱅크 배치
- [docs/dq4-field-format.md](docs/dq4-field-format.md): DQ4(FC) 필드 3개(세계 지도 250×250, 줄 RLE)
- [docs/dq4-map-format.md](docs/dq4-map-format.md): DQ4(FC) 마을·던전 맵 279개(장소 번호, 비트열 압축, 연결·출구, 인물 목록)
- [docs/dq4-data-format.md](docs/dq4-data-format.md): DQ4(FC) 이름 목록·아이템·몬스터·주문 표, 레벨업 성장 곡선
- [docs/dq4-text-format.md](docs/dq4-text-format.md): DQ4(FC) 대사 텍스트(6비트 압축, 사전, 글자표, 메시지 번호)
- [docs/dq4-encounter-format.md](docs/dq4-encounter-format.md): DQ4(FC) 적 조우 표(필드 구역 지도, 구역별 무리 후보, 조우율, 던전 층, 특수 전투, 배, 성수, 기습·선제, へんげのつえ, 3장 터널)
- [docs/dq4-warp.md](docs/dq4-warp.md): DQ4(FC) 장면 이동 도구(원하는 맵·필드 자리의 세이브스테이트 만들기)
- [docs/dq4-script-format.md](docs/dq4-script-format.md): DQ4(FC) 인물 대화 스크립트(대화 번호, 조건·플래그·서비스 문장, 메시지 번호)
- [docs/dq4-shop-format.md](docs/dq4-shop-format.md): DQ4(FC) 상점 품목·장소별 값·여관 값·가게 종류, 보물상자·발밑 숨은 물건과 열었음 플래그, 얻는 물건 통합 표
- [docs/dq4-save-format.md](docs/dq4-save-format.md): DQ4(FC) 저장 데이터(모험의 서·체크섬·인물 레코드), 이벤트 플래그, 장 시작 표
- [docs/dq4-rom-map.md](docs/dq4-rom-map.md): DQ4(FC) 롬 뱅크 지도(뱅크 32개의 내용, 실행 장면, 빈 자리)
- [docs/dq4-debug.md](docs/dq4-debug.md): DQ4(FC) 디버그 스위치 `$C000`(벽 통과·인카운트 끄기·전투 테스트), 패드 2 흔적, 미실행 코드 찾기
- [docs/dq4-block-format.md](docs/dq4-block-format.md): DQ4(FC) 맵 블록 → 8×8 타일·팔레트·통행 속성, CHR 올리기, 타일 애니메이션, 지형 효과
- [docs/dq4-fcgfx.md](docs/dq4-fcgfx.md): DQ4(FC) 원작 맵·필드·블록·CHR·폰트·장면(장 제목·엔딩) 그림 뽑기(비공개 에셋용), MesenCE 색, 필드 물가 블록, 필드·폭포 팔레트 순환
- [docs/dq4-fcsprite-format.md](docs/dq4-fcsprite-format.md): DQ4(FC) 필드 인물·일행·탈것 그림 표(4방향 × 걸음 2, 돌려 그리기)와 전투 몬스터 그림(압축·배치·팔레트), 롬에서 뽑아 열람하기
- [docs/dq4-npcblock-format.md](docs/dq4-npcblock-format.md): DQ4(FC) 인물 블록(움직임·자동 이벤트 스크립트) 명령 60가지, 일행 움직임 패턴
- [todo.md](todo.md): 남은 일
- [references.md](references.md): 참고 자료
- [tools/README.md](tools/README.md): 도구 사용법

## 해킹 일지

순번은 dq4 트랙 전체에서 매깁니다. 빠진 번호(12·18)는 [sfc/dq4/](../../sfc/dq4/README.md#해킹-일지) 에 있습니다.

- [2026-10-24-01: FC DQ4 실험 환경과 첫 RAM](journal/2026-10-24-01-fc-env.md)
- [2026-10-24-02: BRK 뱅크 호출](journal/2026-10-24-02-bankcall.md)
- [2026-10-25-01: 대사 텍스트](journal/2026-10-25-01-text.md)
- [2026-10-25-02: 마을·던전 맵](journal/2026-10-25-02-map.md)
- [2026-10-25-03: 출구와 인물](journal/2026-10-25-03-exits-npcs.md)
- [2026-10-25-04: 이름·아이템·몬스터 표](journal/2026-10-25-04-data.md)
- [2026-10-25-05: 필드(세계 지도)](journal/2026-10-25-05-field.md)
- [2026-10-25-06: 필드에서 마을로 들어가기](journal/2026-10-25-06-entrances.md)
- [2026-10-25-07: 적 조우 표](journal/2026-10-25-07-encounter.md)
- [2026-10-25-08: 장면 이동(워프) 도구](journal/2026-10-25-08-warp.md)
- [2026-10-25-09: 인물 대화 스크립트](journal/2026-10-25-09-talk.md)
- [2026-10-25-10: 상점·여관·보물상자](journal/2026-10-25-10-shop.md)
- [2026-10-25-11: 저장 데이터·이벤트 플래그·장 시작](journal/2026-10-25-11-event.md)
- [2026-10-25-13: 대사 제어 바이트와 롬 뱅크 지도](journal/2026-10-25-13-textrest.md)
- [2026-10-25-14: 디버그 스위치와 숨은 개발 기능](journal/2026-10-25-14-debug.md)
- [2026-10-25-15: 주문·레벨업·몬스터·아이템 표](journal/2026-10-25-15-stats.md)
- [2026-10-25-16: 맵 블록·타일·팔레트·통행](journal/2026-10-25-16-block.md)
- [2026-10-25-17: 블록 속성 값 표](journal/2026-10-25-17-block-props.md)
- [2026-10-25-19: 대화 조건·밤 인물·호출 문장](journal/2026-10-25-19-talk2.md)
- [2026-10-25-20: 투기장 전투 테스트·효과 오류 보고와 SRAM 재현성](journal/2026-10-25-20-debug2.md)
- [2026-10-25-21: 적 조우의 남은 것](journal/2026-10-25-21-encounter2.md)
- [2026-10-25-22: 남은 제어 바이트·창 문자열·폰트 올리기·BRK 길이](journal/2026-10-25-22-textrest2.md)
- [2026-10-25-23: 플래그 교차 참조·장 끝·ルーラ 행선지](journal/2026-10-25-23-event2.md)
- [2026-10-25-24: 블록 속성의 지형 효과·문과 열쇠·카운터](journal/2026-10-25-24-block2.md)
- [2026-10-25-25: 가게 인물 전체 표·교회·맡기는 곳·상자 나머지](journal/2026-10-25-25-shop2.md)
- [2026-10-25-26: 포팅용 기호 텍스트 내보내기와 モシャス](journal/2026-10-25-26-textrest3.md)
- [2026-10-25-27: 전투 행동·주문 위력·내성·몬스터 AI·아이템 플래그](journal/2026-10-25-27-stats2.md)
- [2026-10-25-28: 이벤트 표와 진행 목록·마차·손님·움직임](journal/2026-10-25-28-talk3.md)
- [2026-10-25-29: 원작 필드 인물·몬스터 그림 뽑기](journal/2026-10-25-29-fcsprite.md)
- [2026-10-25-30: 원작 맵·필드·타일 그림 뽑기](journal/2026-10-25-30-fcgfx.md)
- [2026-10-25-31: 얻는 물건 통합 표·장소별 값·숨는 가게 인물](journal/2026-10-25-31-shop3.md)
- [2026-10-25-32: 적 조우의 남은 것 2](journal/2026-10-25-32-encounter3.md)
- [2026-10-25-33: 창 레코드(자리·크기·항목)와 자동 ＊「 의 규칙](journal/2026-10-25-33-textrest4.md)
- [2026-10-25-34: 출구 칸 연결 표·리프트 사각형·연 문 목록](journal/2026-10-25-34-block4.md)
- [2026-10-25-35: 장 시작 상태의 일행 조건, 맵 목록의 마지막 그룹, 자동 입력](journal/2026-10-25-35-talk4.md)
- [2026-10-25-36: 인물 블록 명령 해석기, 마차·배·열기구, 5장 끝과 엔딩](journal/2026-10-25-36-event3.md)
- [2026-10-25-37: 호출 분석의 BRK 길이 고치기](journal/2026-10-25-37-brklen.md)
- [2026-10-25-38: 몬스터 AI 네 갈래와 가중치, 남은 몬스터 바이트, 동료 작전 AI](journal/2026-10-25-38-stats3.md)
- [2026-10-25-39: 2×2 문·성문, せかいじゅのは, 天空 장비 검사, 모양 E 타일](journal/2026-10-25-39-block5.md)
- [2026-10-25-40: 들어갈 때 숨는 인물 전부·맡기는 곳 찾기·무료 숙박](journal/2026-10-25-40-shop4.md)
- [2026-10-25-41: 원작 그림 2차 — 필드 가장자리, 팔레트 순환, 장 제목·엔딩, 장소 이름](journal/2026-10-25-41-fcgfx2.md)
- [2026-10-25-42: 적 조우의 남은 것 3](journal/2026-10-25-42-encounter4.md)
- [2026-10-25-43: 창 본문 항목의 뜻과 폰트를 다시 올리는 두 장면](journal/2026-10-25-43-textrest5.md)
