# sfc-dq4

FC판 「드래곤 퀘스트 IV 인도받은 자들」(일본판)을 슈퍼 패미콤 「드래곤 퀘스트 V
천공의 신부」(일본판) 엔진 위에 옮기는 한글 해킹롬 프로젝트입니다. PC 포트나
Unity 리메이크가 아니라, 실제 SFC 롬에 덧대는 IPS 패치를 만듭니다.

그래픽은 직접 그립니다. 다른 팬 해킹의 데이터는 쓰지 않고 아이디어만
참고합니다.

## 원본 롬

롬 데이터는 들어 있지 않습니다. 직접 덤프한 롬을 아래 이름으로 `rom/` 에
두세요(`rom/` 은 커밋되지 않습니다).

| 파일 | 원본 | SHA-1 |
| --- | --- | --- |
| `rom/dq5.sfc` | Dragon Quest V - Tenkuu no Hanayome (Japan). LoROM 12Mbit, 카피어 헤더 없음 | `1c47ed62c561d7965fe5dc2a03f4c37feb4a46b5` |
| `rom/dq4.nes` | Dragon Quest IV - Michibikareshi Monotachi (Japan) (Rev A). MMC1, iNES 헤더 포함 | `1147ce6dfdc3354d8bb89be40f5d1a97a2be1aea` |

`dq4.nes` 는 16바이트 iNES 헤더 뒤 PRG 512KB 의 CRC32 가 `0794F2A5` 입니다.
초판(Rev 0, PRG CRC32 `2DD71ACB`)은 쓰지 않습니다.

## 준비

[uv](https://docs.astral.sh/uv/) 로 Python 3.15 환경과 도구를 맞춥니다. 툴킷은 릴리스 태그로,
나머지는 `uv.lock` 으로 고정되어 있습니다.

```sh
uv sync --locked
```

- [kr-patch-toolkit](https://github.com/perfectacle/kr-patch-toolkit) v0.5.0:
  65c816 디스어셈블러(`krpatch sfc dis`), MesenCE 용 Lua 라이브러리(`krpatch sfc lua`),
  FC 용 iNES 헤더·6502 디스어셈블러·Lua 프로브(`krpatch fc`)
- [Pillow](https://python-pillow.org/): 맵·그림 렌더링
- [MesenCE](https://github.com/nesdev-org/MesenCE) 2.2.1: 디버거와
  `--testrunner` 로 분석 스크립트를 돌립니다. 사용법은 [tools/README.md](tools/README.md).
- [asar](https://github.com/RPGHacker/asar) 1.91: 패치 어셈블(빌드 단계부터).

## 문서

코딩 에이전트로 작업할 때는 [AGENTS.md](AGENTS.md) 부터 읽습니다. 여러 세션이 트랙을 나눠 동시에 작업하는 규칙이 있습니다.


- [docs/references.md](docs/references.md): 참고 자료
- [docs/todo.md](docs/todo.md): 트랙(dq5·dq4)마다 남은 일

dq5(SFC DQ5 엔진):

- [docs/dq5-handoff.md](docs/dq5-handoff.md): dq5 트랙 시작점(지금 상태, 실험 출발점, 다음 할 일)
- [docs/dq5-map-format.md](docs/dq5-map-format.md): DQ5 실내 맵 형식(지형·팔레트·인물·출구·영역 이동·보물상자)
- [docs/dq5-field-format.md](docs/dq5-field-format.md): DQ5 필드(세계 지도) 형식
- [docs/dq5-text-format.md](docs/dq5-text-format.md): DQ5 메시지(허프만 부호)·제어 코드·폰트·대화 스크립트·이름 문자열·메뉴 창 문자열
- [docs/dq5-data-format.md](docs/dq5-data-format.md): DQ5 게임 데이터(상점 품목·물건 가격·물건 표·몬스터·전투 조우)
- [docs/dq5-graphics-format.md](docs/dq5-graphics-format.md): DQ5 전투 몬스터 그림(레코드·머리·조각·타일 압축·팔레트)

dq4(FC DQ4 원작):

- [docs/dq4-handoff.md](docs/dq4-handoff.md): dq4 트랙 시작점(목표, 도구 현황, 다음 할 일)
- [docs/dq4-ram-format.md](docs/dq4-ram-format.md): DQ4(FC) 필드 RAM(좌표·맵 번호·출구 표)과 뱅크 전환
- [docs/dq4-bank-format.md](docs/dq4-bank-format.md): DQ4(FC) BRK 뱅크 호출과 뱅크 배치
- [docs/dq4-field-format.md](docs/dq4-field-format.md): DQ4(FC) 필드 3개(세계 지도 250×250, 줄 RLE)
- [docs/dq4-map-format.md](docs/dq4-map-format.md): DQ4(FC) 마을·던전 맵 269개(장소 번호, 비트열 압축, 연결·출구, 인물 목록)
- [docs/dq4-data-format.md](docs/dq4-data-format.md): DQ4(FC) 이름 목록·아이템·몬스터·주문 표, 레벨업 성장 곡선
- [docs/dq4-text-format.md](docs/dq4-text-format.md): DQ4(FC) 대사 텍스트(6비트 압축, 사전, 글자표, 메시지 번호)
- [docs/dq4-encounter-format.md](docs/dq4-encounter-format.md): DQ4(FC) 적 조우 표(필드 구역 지도, 구역별 무리 후보, 조우율, 던전 층, 특수 전투)
- [docs/dq4-warp.md](docs/dq4-warp.md): DQ4(FC) 장면 이동 도구(원하는 맵·필드 자리의 세이브스테이트 만들기)
- [docs/dq4-script-format.md](docs/dq4-script-format.md): DQ4(FC) 인물 대화 스크립트(대화 번호, 조건·플래그·서비스 문장, 메시지 번호)
- [docs/dq4-shop-format.md](docs/dq4-shop-format.md): DQ4(FC) 상점 품목·여관 값·가게 종류, 보물상자·발밑 숨은 물건과 열었음 플래그
- [docs/dq4-save-format.md](docs/dq4-save-format.md): DQ4(FC) 저장 데이터(모험의 서·체크섬·인물 레코드), 이벤트 플래그, 장 시작 표
- [docs/dq4-graphics-handoff.md](docs/dq4-graphics-handoff.md): 타이틀·일러스트 보존, 스프라이트 거절 사유·참고 사이트·후속 제작 방향
- [docs/dq4-graphics.md](docs/dq4-graphics.md): 포팅용 스프라이트·샘플 맵·한글 타이틀·일러스트와 SFC 변환 규격
- [docs/dq4-rom-map.md](docs/dq4-rom-map.md): DQ4(FC) 롬 뱅크 지도(뱅크 32개의 내용, 실행 장면, 빈 자리)
- [docs/dq4-debug.md](docs/dq4-debug.md): DQ4(FC) 디버그 스위치 `$C000`(벽 통과·인카운트 끄기·전투 테스트), 패드 2 흔적, 미실행 코드 찾기
- [docs/dq4-block-format.md](docs/dq4-block-format.md): DQ4(FC) 맵 블록 → 8×8 타일·팔레트·통행 속성, CHR 올리기, 타일 애니메이션, 지형 효과

### 해킹 일지

순번은 트랙마다 따로 매깁니다. 같은 날짜에 두 트랙의 같은 번호가 있을 수 있습니다.

#### dq5

- [2026-10-24-01: DQ5 실내 맵 풀기](docs/journal/dq5/2026-10-24-01-map.md)
- [2026-10-24-02: 팔레트와 셀 속성](docs/journal/dq5/2026-10-24-02-map-attributes.md)
- [2026-10-24-03: 인물과 낮·밤](docs/journal/dq5/2026-10-24-03-npc.md)
- [2026-10-24-04: 출구](docs/journal/dq5/2026-10-24-04-exits.md)
- [2026-10-24-05: 가장자리 출구와 필드로 나가기](docs/journal/dq5/2026-10-24-05-edge-exit.md)
- [2026-10-24-06: 영역 이동(트리거)](docs/journal/dq5/2026-10-24-06-triggers.md)
- [2026-10-24-07: 셀 속성과 맵 머리 확인](docs/journal/dq5/2026-10-24-07-cells-header.md)
- [2026-10-24-08: 이벤트 플래그로 바뀌는 인물](docs/journal/dq5/2026-10-24-08-npc-flags.md)
- [2026-10-24-09: 필드(세계 지도)](docs/journal/dq5/2026-10-24-09-field.md)
- [2026-10-24-10: 필드 걷기 실험(입장은 아직)](docs/journal/dq5/2026-10-24-10-field-walk.md)
- [2026-10-24-11: 필드에서 마을로 들어가기](docs/journal/dq5/2026-10-24-11-field-entrance.md)
- [2026-10-24-12: 맵별 루틴과 출구 번호](docs/journal/dq5/2026-10-24-12-exit-hook.md)
- [2026-10-25-01: 메시지, 폰트, 대화 스크립트](docs/journal/dq5/2026-10-25-01-text.md)
- [2026-10-25-02: 보물상자와 이름 문자열](docs/journal/dq5/2026-10-25-02-treasure.md)
- [2026-10-25-03: 상점과 물건 가격](docs/journal/dq5/2026-10-25-03-shop.md)
- [2026-10-25-04: 물건 표](docs/journal/dq5/2026-10-25-04-items.md)
- [2026-10-25-05: 몬스터 레코드](docs/journal/dq5/2026-10-25-05-monster.md)
- [2026-10-25-06: 전투 조우 표](docs/journal/dq5/2026-10-25-06-encounter.md)
- [2026-10-25-07: 메시지 제어 코드, 대화 조건, 메뉴 문자열](docs/journal/dq5/2026-10-25-07-textctl.md)
- [2026-10-25-08: 디버그 모드 찾기와 장면 이동 도구](docs/journal/dq5/2026-10-25-08-warp.md)
- [2026-10-25-09: 전투 몬스터 그림](docs/journal/dq5/2026-10-25-09-mongfx.md)
- [2026-10-25-10: 주문 표와 몬스터 필드](docs/journal/dq5/2026-10-25-10-spell.md)
- [2026-10-25-11: 메달·코인 교환·여관 값과 상자 내용물의 남은 것](docs/journal/dq5/2026-10-25-11-shop2.md)
- [2026-10-25-12: 이벤트 전투 무리 표와 롬 밖 뱅크 실행 감시](docs/journal/dq5/2026-10-25-12-event-battle.md)
- [2026-10-25-13: 인물 표와 인라인 스크립트](docs/journal/dq5/2026-10-25-13-npc-script.md)
- [2026-10-25-14: 조우의 남은 것](docs/journal/dq5/2026-10-25-14-encounter2.md)
- [2026-10-25-15: 마을 입장 실측과 세계 지도 셋](docs/journal/dq5/2026-10-25-15-field.md)
- [2026-10-25-16: 내성·상태 주문·동료가 되는 몬스터](docs/journal/dq5/2026-10-25-16-recruit.md)
- [2026-10-25-17: 조우의 남은 것 2](docs/journal/dq5/2026-10-25-17-encounter3.md)

#### dq4

- [2026-10-24-01: FC DQ4 실험 환경과 첫 RAM](docs/journal/dq4/2026-10-24-01-fc-env.md)
- [2026-10-24-02: BRK 뱅크 호출](docs/journal/dq4/2026-10-24-02-bankcall.md)
- [2026-10-25-01: 대사 텍스트](docs/journal/dq4/2026-10-25-01-text.md)
- [2026-10-25-02: 마을·던전 맵](docs/journal/dq4/2026-10-25-02-map.md)
- [2026-10-25-03: 출구와 인물](docs/journal/dq4/2026-10-25-03-exits-npcs.md)
- [2026-10-25-04: 이름·아이템·몬스터 표](docs/journal/dq4/2026-10-25-04-data.md)
- [2026-10-25-05: 필드(세계 지도)](docs/journal/dq4/2026-10-25-05-field.md)
- [2026-10-25-06: 필드에서 마을로 들어가기](docs/journal/dq4/2026-10-25-06-entrances.md)
- [2026-10-25-07: 적 조우 표](docs/journal/dq4/2026-10-25-07-encounter.md)
- [2026-10-25-08: 장면 이동(워프) 도구](docs/journal/dq4/2026-10-25-08-warp.md)
- [2026-10-25-09: 인물 대화 스크립트](docs/journal/dq4/2026-10-25-09-talk.md)
- [2026-10-25-10: 상점·여관·보물상자](docs/journal/dq4/2026-10-25-10-shop.md)
- [2026-10-25-11: 저장 데이터·이벤트 플래그·장 시작](docs/journal/dq4/2026-10-25-11-event.md)
- [2026-10-25-12: 그래픽 시안 평가와 작업 인계](docs/journal/dq4/2026-10-25-12-graphics.md)
- [2026-10-25-13: 대사 제어 바이트와 롬 뱅크 지도](docs/journal/dq4/2026-10-25-13-textrest.md)
- [2026-10-25-14: 디버그 스위치와 숨은 개발 기능](docs/journal/dq4/2026-10-25-14-debug.md)
- [2026-10-25-15: 주문·레벨업·몬스터·아이템 표](docs/journal/dq4/2026-10-25-15-stats.md)
- [2026-10-25-16: 맵 블록·타일·팔레트·통행](docs/journal/dq4/2026-10-25-16-block.md)
- [2026-10-25-17: 블록 속성 값 표](docs/journal/dq4/2026-10-25-17-block-props.md)
