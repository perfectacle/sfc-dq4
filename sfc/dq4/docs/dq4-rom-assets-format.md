# DQ4 인물의 DQ5 롬 삽입

라이안의 정면 정지 자세를 DQ5 어린 주인공 자리에 넣는 최소 패치입니다. 제작 원본은 [스프라이트 규격](dq4-sprite-format.md), 엔진 형식은 [DQ5 그래픽 형식](../../dq5/docs/dq5-graphics-format.md#필드-인물-스프라이트-1fcf1e)을 따릅니다. 전체 인물 이식이나 DQ4 게임 완성본이 아닙니다.

## 제작물의 범위

사용자 확인을 받은 것은 기존 라이안 정면 정지 자세 한 장입니다. DQ5 팔레트로 바꾼 그림은 별도 시안이며, 기술 검증이 시각적 채택을 뜻하지 않습니다. 나머지 방향과 보행은 기존 DQ5 데이터를 유지하는 것을 기준으로 합니다. DQ5는 방향별 머리를 두 보행 프레임에서 공유하므로, 정면 머리를 바꾸면 두 번째 프레임에도 영향을 줍니다. 이 프레임은 라이안 머리와 기존 몸이 섞이는 검증용 결과입니다. 머리만 정면을 향하는 혼합 자세와 눕기 변환에도 변경이 전파될 수 있습니다. 다른 방향 6프레임 보존은 일반 보행 자세의 범위이며 모든 연출 보존을 뜻하지 않습니다.

## 삽입 대상과 제약

| 항목 | 값 |
| --- | --- |
| 원본 | `rom/dq5.sfc`, 카피어 헤더 없는 일본판 |
| SHA-1 | `1c47ed62c561d7965fe5dc2a03f4c37feb4a46b5` |
| 그림 / 세트 | `2E` / `82` |
| 레코드 | `1F:EEAF`, 52바이트 |
| 기존 타일 자료 | `0E:A76B`부터 `0E:AA61` 직전, 758바이트 |
| 기존 타일 수 | 34개 |
| 일행 예약 | 최대 48타일 |
| 팔레트 | OBJ 0, 다른 인물과 공유 |

팔레트 0을 통째로 바꾸면 다른 인물의 색도 바뀝니다. 첫 패치는 기존 팔레트를 유지하고 라이안의 색 번호를 그 팔레트에 맞춥니다. 팔레트 3도 맵에 따라 바뀌므로 빈 슬롯으로 사용하지 않습니다. 원래 분홍색을 정확하게 유지하는 팔레트 할당은 후속 과제입니다.

## 변환과 검증 원칙

- 색 번호 0은 투명으로 유지합니다. 16×24 프레임을 DQ5의 머리·몸 겹침 배치에 맞춥니다.
- 표준 4bpp 타일의 낮은 바이트와 높은 바이트를 각각 압축하고, 레코드의 48칸과 타일 수를 함께 기록합니다.
- 새 데이터는 37타일, 압축 804바이트로 기존 758바이트를 넘습니다. 롬을 1.5MiB에서 2MiB로 확장하고 CPU 주소 `30:8000`에 기록합니다. 기존 헤더의 크기 값 `0B`는 이미 2MiB입니다. 확장 영역에는 원본 마지막 512KiB의 미러를 먼저 채우고 새 데이터를 씁니다. 데이터 포인터를 바꾸되 팔레트 비트는 유지합니다.
- 확장한 롬의 크기와 체크섬을 검증합니다. IPS는 확장 데이터를 포함하므로 로컬 `work/`에만 둡니다.
- 기존 `dq5sprite.py`로 패치 롬을 다시 읽어 프레임을 비교합니다. 바꾸지 않은 세트와 공유 팔레트도 원본과 비교합니다.
- IPS를 원본에 적용한 결과와 별도 출력 롬이 같아야 합니다. 원본 파일은 바꾸지 않습니다.
- 실제 표시 검사는 패치 롬 자체로 합니다. VRAM·OAM·CGRAM을 매 프레임 덮어쓰는 기존 `dq4sprite.lua` 실험과 구분합니다.
- 세이브스테이트에는 이전 그래픽이 들어 있으므로, 로드 직후 화면만 보고 새 롬의 표시라고 판단하지 않습니다. 장면 재진입과 롬 로더 동작을 확인합니다.

## 산출물의 위치

소스와 재현 도구는 이 저장소에 둡니다. 롬·IPS·추출 바이너리·덤프는 `work/dq4-rom-assets/`에 만들고 커밋하지 않습니다. 미리보기 갤러리는 비공개 [sfc-dq4-assets](https://github.com/perfectacle/sfc-dq4-assets)의 `sfc/dq4/gallery/index.html`에 생성합니다. 갤러리는 제작물의 시각 확인 상태와 엔진 검증 상태를 따로 표시합니다.

## 다시 만들기

저장소 최상위에서 실행합니다. `ASSETS`는 별도로 복제한 비공개 에셋 저장소 경로입니다.

```sh
uv sync --locked
uv run --locked python sfc/dq4/tools/dq4romassets.py rom/dq5.sfc --out work/dq4-rom-assets
uv run --locked python sfc/dq4/tools/dq4romgallery.py --input work/dq4-rom-assets --out "$ASSETS/sfc/dq4"
```

변환 결과의 `manifest.json`은 입력 해시, 대상 세트, 변경 범위와 역변환 검사 결과를 담습니다. 갤러리만 보고 에뮬레이터 검증까지 끝났다고 판단하지 않습니다. 실제 표시 검증은 관찰 프로브의 결과와 함께 확인합니다.

## MesenCE 실측 결과

MesenCE `2.2.1+20ba206cef5ba207c21203176d02cb9f43dda9fb`에서 패치 롬을 실행했습니다. 관찰 프로브 `lua/dq4romcheck.lua`는 입력과 메모리 읽기·덤프만 사용하며 롬·그래픽 메모리에 쓰지 않습니다.

| 검사 | 결과 |
| --- | --- |
| 콜드 부팅 | 2,400프레임, 새 게임 메뉴 도달, 종료 코드 0 |
| 마을 → 필드 → 마을 재진입 | 그래픽 로더 9회 실행 |
| 로더 실행 후 덤프 | 181개 |
| VRAM 타일 비교 | 32,281건 중 32,281건 일치 |
| OAM 그림 비교 | 215건 중 215건 일치 |
| 세트 `82` VRAM 비교 | 6,697건 중 6,697건 일치, 4방향 × 2프레임 확인 |
| 출력 SHA-1 | `930231b6b80b8bd9eaec7a50ad506438cb132a4c` |
| 체크섬 | `89D0` |

콜드 부팅 검사와 기존 상태에서 시작한 장면 검사는 별개입니다. 새 게임을 처음부터 끝까지 진행한 결과가 아닙니다. 세이브스테이트 실행에서는 원본과 패치 양쪽에 같은 미초기화 읽기 경고가 있었으며, 같은 입력으로 비교했을 때 추가 경고는 없었습니다.

`work/dq4-rom-assets/emulator-verification.json`에 실행 명령과 해시를 기록합니다. `MESENCE`에 실행 파일을 지정하고 다음처럼 다시 관찰할 수 있습니다.

```sh
mkdir -p work/romcheck/patched-cold work/romcheck/patched-entry
OUT="$PWD/work/romcheck/patched-cold" MAXF=2400 DUMPF=1200,1800,2400 \
  "$MESENCE" --testrunner "$PWD/work/dq4-rom-assets/dq4-ragnar-front.sfc" "$PWD/sfc/dq4/tools/lua/dq4romcheck.lua"
OUT="$PWD/work/romcheck/patched-entry" STATE="$PWD/work/state/field-free.mss" \
  ROUTE="331,56;331,67" \
  SEQ="up@350:40,left@410:24,right@460:24,down@520:40,down@700:100,left@950:30,right@1000:30,up@1050:30,down@1100:30" \
  MAXF=1200 EVERY=5 FROM=300 \
  "$MESENCE" --testrunner "$PWD/work/dq4-rom-assets/dq4-ragnar-front.sfc" "$PWD/sfc/dq4/tools/lua/dq4romcheck.lua"
uv run --locked python sfc/dq5/tools/dq5sprite.py work/dq4-rom-assets/dq4-ragnar-front.sfc --compare work/romcheck/patched-entry -q
```

기존 `field-free.mss`는 별도 준비물이며 저장소에 포함하지 않습니다. 위 경로가 없는 환경에서는 같은 출발점의 상태를 먼저 준비해야 합니다.
