# sfc-dq4

FC판 「드래곤 퀘스트 IV 인도받은 자들」(일본판)을 슈퍼패미컴 「드래곤 퀘스트 V
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

- [kr-patch-toolkit](https://github.com/perfectacle/kr-patch-toolkit) v0.4.0:
  65c816 디스어셈블러(`krpatch sfc dis`), MesenCE 용 Lua 라이브러리(`krpatch sfc lua`)
- [Pillow](https://python-pillow.org/): 맵·그림 렌더링
- [MesenCE](https://github.com/nesdev-org/MesenCE) 2.2.1: 디버거와
  `--testrunner` 로 분석 스크립트를 돌립니다. 사용법은 [tools/README.md](tools/README.md).
- [asar](https://github.com/RPGHacker/asar) 1.91: 패치 어셈블(빌드 단계부터).

## 문서

- [docs/dq5-map-format.md](docs/dq5-map-format.md): DQ5 실내 맵 형식(지형·팔레트·인물·출구·영역 이동)
- [docs/dq5-field-format.md](docs/dq5-field-format.md): DQ5 필드(세계 지도) 형식
- [docs/references.md](docs/references.md): 참고 자료

### 해킹 일지

- [2026-10-24-01: DQ5 실내 맵 풀기](docs/journal/2026-10-24-01-dq5-map.md)
- [2026-10-24-02: 팔레트와 셀 속성](docs/journal/2026-10-24-02-dq5-map-attributes.md)
- [2026-10-24-03: 인물과 낮·밤](docs/journal/2026-10-24-03-dq5-npc.md)
- [2026-10-24-04: 출구](docs/journal/2026-10-24-04-dq5-exits.md)
- [2026-10-24-05: 가장자리 출구와 필드로 나가기](docs/journal/2026-10-24-05-dq5-edge-exit.md)
- [2026-10-24-06: 영역 이동(트리거)](docs/journal/2026-10-24-06-dq5-triggers.md)
- [2026-10-24-07: 셀 속성과 맵 머리 확인](docs/journal/2026-10-24-07-dq5-cells-header.md)
- [2026-10-24-08: 이벤트 플래그로 바뀌는 인물](docs/journal/2026-10-24-08-dq5-npc-flags.md)
- [2026-10-24-09: 필드(세계 지도)](docs/journal/2026-10-24-09-dq5-field.md)
- [2026-10-24-10: 필드 걷기 실험(입장은 아직)](docs/journal/2026-10-24-10-dq5-field-walk.md)
- [2026-10-24-11: 필드에서 마을로 들어가기](docs/journal/2026-10-24-11-dq5-field-entrance.md)
