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

한글판은 `uv run --locked krpatch xdelta apply rom/dq4ds.nds NDS_DQ4_v1.1.xdelta rom/dq4ds-kr.nds` 로 만듭니다. 이 패치는 LZMA 2차 압축이라 툴킷 v0.6.0 이상이 필요합니다(`xdelta3 -d -s` 로도 됩니다).

## 준비

[uv](https://docs.astral.sh/uv/) 로 Python 3.15 환경과 도구를 맞춥니다. 툴킷은 릴리스 태그로,
나머지는 `uv.lock` 으로 고정되어 있습니다.

```sh
uv sync --locked
```

- [kr-patch-toolkit](https://github.com/perfectacle/kr-patch-toolkit) v0.7.0:
  65c816 디스어셈블러(`krpatch sfc dis`), MesenCE 용 Lua 라이브러리(`krpatch sfc lua`),
  FC 용 iNES 헤더·6502 디스어셈블러·Lua 프로브(`krpatch fc`), NDS 롬 풀기(`krpatch nds`),
  xdelta 적용(`krpatch xdelta`)
- [Pillow](https://python-pillow.org/): 맵·그림 렌더링
- [MesenCE](https://github.com/nesdev-org/MesenCE) 2.2.1: 디버거와
  `--testrunner` 로 분석 스크립트를 돌립니다. 사용법은 [tools/README.md](tools/README.md).
- [asar](https://github.com/RPGHacker/asar) 1.91: 패치 어셈블(빌드 단계부터).

## 문서

코딩 에이전트로 작업할 때는 [AGENTS.md](AGENTS.md) 부터 읽습니다. 여러 세션이 트랙을 나눠 동시에 작업하는 규칙이 있습니다.


- [docs/references.md](docs/references.md): 참고 자료
- [docs/todo.md](docs/todo.md): 트랙(dq5·dq4)마다 남은 일

dq5(SFC DQ5 엔진): [sfc/dq5/README.md](sfc/dq5/README.md)

dq4(FC DQ4 원작 분석): [fc/dq4/README.md](fc/dq4/README.md), SFC 포팅 결과물: [sfc/dq4/README.md](sfc/dq4/README.md)

nds(NDS DQ4 리메이크·한글 팬패치 참고): [nds/dq4/README.md](nds/dq4/README.md)

### 해킹 일지

순번은 트랙마다 따로 매깁니다. 같은 날짜에 두 트랙의 같은 번호가 있을 수 있습니다.

#### dq5

[sfc/dq5/README.md](sfc/dq5/README.md#해킹-일지) 에 있습니다.

#### dq4

[fc/dq4/README.md](fc/dq4/README.md#해킹-일지)(FC 원작 분석)와 [sfc/dq4/README.md](sfc/dq4/README.md#해킹-일지)(SFC 포팅 결과물)에 있습니다.
