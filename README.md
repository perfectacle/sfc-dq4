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

- [kr-patch-toolkit](https://github.com/perfectacle/kr-patch-toolkit) v0.3.0:
  65c816 디스어셈블러, 타일 렌더링, MesenCE 용 Lua 라이브러리
  ```sh
  pip install git+https://github.com/perfectacle/kr-patch-toolkit@v0.3.0
  ```
- [MesenCE](https://github.com/nesdev-org/MesenCE) 2.2.1: 디버거와
  `--testrunner` 로 분석 스크립트를 돌립니다. 사용법은 [tools/README.md](tools/README.md).
- [asar](https://github.com/RPGHacker/asar) 1.91: 패치 어셈블(빌드 단계부터).

## 문서

- [docs/dq5-map-format.md](docs/dq5-map-format.md): DQ5 맵 구조 분석
- [docs/references.md](docs/references.md): 참고 자료
