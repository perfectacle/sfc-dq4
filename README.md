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

`nds` 트랙은 분석 참고용으로 아래 두 롬을 씁니다. 패치의 바탕이 아닙니다.

| 파일 | 원본 | SHA-1 |
| --- | --- | --- |
| `rom/dq4ds.nds` | Dragon Quest IV - Michibikareshi Mono-tachi (Japan), NDS. 헤더 `DRAGONQUEST4` / `YIVJ`, CRC32 `3257B207` | `84baf75d79b842fa5ecfdc66c112f1d19bf228ae` |
| `rom/dq4ds-kr.nds` | 위 롬에 한글 팬패치 `NDS_DQ4_v1.1.xdelta` 를 적용한 것. CRC32 `4DA617AF` | `a2ee52765cd54715e777b2993277e752e3ec276d` |

한글판은 `xdelta3 -d -s rom/dq4ds.nds NDS_DQ4_v1.1.xdelta rom/dq4ds-kr.nds` 로 만듭니다. 이 패치는 LZMA 2차 압축이라 툴킷 v0.5.0 의 `krpatch xdelta apply` 로는 풀리지 않습니다.

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

dq5(SFC DQ5 엔진): [sfc/dq5/README.md](sfc/dq5/README.md)

dq4(FC DQ4 원작):

- [docs/dq4-handoff.md](docs/dq4-handoff.md): dq4 트랙 시작점(목표, 도구 현황, 다음 할 일)
- [docs/dq4-ram-format.md](docs/dq4-ram-format.md): DQ4(FC) 필드 RAM(좌표·맵 번호·출구 표)과 뱅크 전환
- [docs/dq4-bank-format.md](docs/dq4-bank-format.md): DQ4(FC) BRK 뱅크 호출과 뱅크 배치
- [docs/dq4-field-format.md](docs/dq4-field-format.md): DQ4(FC) 필드 3개(세계 지도 250×250, 줄 RLE)
- [docs/dq4-map-format.md](docs/dq4-map-format.md): DQ4(FC) 마을·던전 맵 279개(장소 번호, 비트열 압축, 연결·출구, 인물 목록)
- [docs/dq4-data-format.md](docs/dq4-data-format.md): DQ4(FC) 이름 목록·아이템·몬스터·주문 표, 레벨업 성장 곡선
- [docs/dq4-text-format.md](docs/dq4-text-format.md): DQ4(FC) 대사 텍스트(6비트 압축, 사전, 글자표, 메시지 번호)
- [docs/dq4-encounter-format.md](docs/dq4-encounter-format.md): DQ4(FC) 적 조우 표(필드 구역 지도, 구역별 무리 후보, 조우율, 던전 층, 특수 전투, 배, 성수, 기습·선제)
- [docs/dq4-warp.md](docs/dq4-warp.md): DQ4(FC) 장면 이동 도구(원하는 맵·필드 자리의 세이브스테이트 만들기)
- [docs/dq4-script-format.md](docs/dq4-script-format.md): DQ4(FC) 인물 대화 스크립트(대화 번호, 조건·플래그·서비스 문장, 메시지 번호)
- [docs/dq4-shop-format.md](docs/dq4-shop-format.md): DQ4(FC) 상점 품목·장소별 값·여관 값·가게 종류, 보물상자·발밑 숨은 물건과 열었음 플래그, 얻는 물건 통합 표
- [docs/dq4-save-format.md](docs/dq4-save-format.md): DQ4(FC) 저장 데이터(모험의 서·체크섬·인물 레코드), 이벤트 플래그, 장 시작 표
- [docs/dq4-graphics-handoff.md](docs/dq4-graphics-handoff.md): 타이틀·일러스트 보존, 스프라이트 거절 사유·참고 사이트·후속 제작 방향
- [docs/dq4-graphics.md](docs/dq4-graphics.md): 포팅용 스프라이트·샘플 맵·한글 타이틀·일러스트와 SFC 변환 규격
- [docs/dq4-sprite-format.md](docs/dq4-sprite-format.md): SFC DQ5 필드 인물 실측(크기·색·눈·보행 프레임)과 그 규칙으로 그린 DQ4 인물 9명 스프라이트, MesenCE 표시 실험
- [docs/dq4-rom-map.md](docs/dq4-rom-map.md): DQ4(FC) 롬 뱅크 지도(뱅크 32개의 내용, 실행 장면, 빈 자리)
- [docs/dq4-debug.md](docs/dq4-debug.md): DQ4(FC) 디버그 스위치 `$C000`(벽 통과·인카운트 끄기·전투 테스트), 패드 2 흔적, 미실행 코드 찾기
- [docs/dq4-block-format.md](docs/dq4-block-format.md): DQ4(FC) 맵 블록 → 8×8 타일·팔레트·통행 속성, CHR 올리기, 타일 애니메이션, 지형 효과
- [docs/dq4-fcgfx.md](docs/dq4-fcgfx.md): DQ4(FC) 원작 맵·필드·블록·CHR·폰트·장면 그림 뽑기(비공개 에셋용), MesenCE 색, 필드 물가 블록
- [docs/dq4-fcsprite-format.md](docs/dq4-fcsprite-format.md): DQ4(FC) 필드 인물·일행·탈것 그림 표(4방향 × 걸음 2, 돌려 그리기)와 전투 몬스터 그림(압축·배치·팔레트), 롬에서 뽑아 열람하기

nds(NDS DQ4 리메이크·한글 팬패치 참고): [nds/dq4/README.md](nds/dq4/README.md)

### 해킹 일지

순번은 트랙마다 따로 매깁니다. 같은 날짜에 두 트랙의 같은 번호가 있을 수 있습니다.

#### dq5

[sfc/dq5/README.md](sfc/dq5/README.md#해킹-일지) 에 있습니다.

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
- [2026-10-25-18: DQ5 실측 규격으로 다시 그린 인물 스프라이트](docs/journal/dq4/2026-10-25-18-sprites2.md)
- [2026-10-25-19: 대화 조건·밤 인물·호출 문장](docs/journal/dq4/2026-10-25-19-talk2.md)
- [2026-10-25-20: 투기장 전투 테스트·효과 오류 보고와 SRAM 재현성](docs/journal/dq4/2026-10-25-20-debug2.md)
- [2026-10-25-21: 적 조우의 남은 것](docs/journal/dq4/2026-10-25-21-encounter2.md)
- [2026-10-25-22: 남은 제어 바이트·창 문자열·폰트 올리기·BRK 길이](docs/journal/dq4/2026-10-25-22-textrest2.md)
- [2026-10-25-23: 플래그 교차 참조·장 끝·ルーラ 행선지](docs/journal/dq4/2026-10-25-23-event2.md)
- [2026-10-25-24: 블록 속성의 지형 효과·문과 열쇠·카운터](docs/journal/dq4/2026-10-25-24-block2.md)
- [2026-10-25-25: 가게 인물 전체 표·교회·맡기는 곳·상자 나머지](docs/journal/dq4/2026-10-25-25-shop2.md)
- [2026-10-25-26: 포팅용 기호 텍스트 내보내기와 モシャス](docs/journal/dq4/2026-10-25-26-textrest3.md)
- [2026-10-25-27: 전투 행동·주문 위력·내성·몬스터 AI·아이템 플래그](docs/journal/dq4/2026-10-25-27-stats2.md)
- [2026-10-25-28: 이벤트 표와 진행 목록·마차·손님·움직임](docs/journal/dq4/2026-10-25-28-talk3.md)
- [2026-10-25-29: 원작 필드 인물·몬스터 그림 뽑기](docs/journal/dq4/2026-10-25-29-fcsprite.md)
- [2026-10-25-30: 원작 맵·필드·타일 그림 뽑기](docs/journal/dq4/2026-10-25-30-fcgfx.md)
- [2026-10-25-31: 얻는 물건 통합 표·장소별 값·숨는 가게 인물](docs/journal/dq4/2026-10-25-31-shop3.md)
- [2026-10-25-32: 적 조우의 남은 것 2](docs/journal/dq4/2026-10-25-32-encounter3.md)
