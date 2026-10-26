# DQ4 사운드 포팅 작업 인계 — 2026-10-27

사운드 포팅을 이어받는 세션이 읽는 작업 기록입니다. 확정된 형식·실측은 [사운드 포팅](dq4-sound-port-format.md)에 있고, 여기에는 경과·로컬 실험 폴더(`work/`, 커밋하지 않음)·재현 명령을 둡니다. 아래 「첫 세션 인계」는 그때의 기록이며, 그 뒤 고친 것은 「이어받은 세션의 진행」에 있습니다.

## 이어받은 세션의 진행(2026-10-27 두 번째 세션)

- 브랜치를 최신 `origin/main`(`c60504a`)으로 빨리 감기했습니다. 미추적 초안은 `work/sound-port/backup-20261027/`에 복사해 두었습니다. main에서 이름 입력이 바뀌었으므로 기준 ROM `work/sound/baseline/dq4-sound-base.sfc`는 통합 전에 최신 빌드로 바꿔야 합니다.
- **시퀀스 크기**: NDS 템포는 1 BPM 단위 루바토(성 곡 1,918번)이고 세기도 음마다 달라 명령이 시퀀스를 채웠습니다. `simplify_tempo`는 원래 템포 경계마다 누적 시각 오차가 0.012초 이하가 되도록 정수 템포 구간을 합칩니다. 박마다 나눌 자리를 두어 소수 템포를 이웃 정수로 번갈아 맞춥니다. `volume2`와 음 중간 CC 분할은 1dB 이내 변화를 생략합니다. 오차·생략 수는 보고서의 `tempo_max_error_seconds`·`level_changes_merged`·`level_max_error_db`에 남습니다.
- 50곡 전체 시퀀스 합은 471,155바이트에서 243,156바이트로 줄었습니다. 50곡 모두 템포 오차 0.012초 이하입니다. 성 곡 `02`는 15,217바이트에서 6,894바이트가 됐습니다. 아직 8,000바이트를 넘는 곡은 `22` 14,941, `1C` 13,897, `14`·`07`·`15`·`16` 약 10~12KB 등 10곡입니다.
- **성 곡 `02` 실제 재생 확인**: 8kHz NDS 샘플 4개와 함께 SPC 예산 39,739/44,195바이트로 빌드됐습니다(`work/sound/castle8k/castle.sfc`, 미리듣기 타이틀 교체). 전원부터 MesenCE 2,400프레임 동안 246프레임에 곡이 올랐습니다. 새 도구 `dq4soundcheck.py` 결과는 다음과 같습니다.
  - SPC의 시퀀스와 샘플 `26`~`29`가 ROM 재배치 자료와 바이트까지 같았습니다.
  - 목소리 0~5의 예상 음 401개와 KON 401개가 모두 짝지어졌습니다. SRCN 오류 0, 같은 샘플 음 간격 오류 0입니다.
  - 공통 시작·속도 비(0.9987)를 맞춘 KON 시각 잔차는 최대 1.76프레임입니다. 남은 0.13% 속도 차이는 APU 발진기(공칭 32kHz보다 빠름) 때문으로 보며, 따로 측정하지는 않았습니다.
  - `dq5spc.py --check`·`dq5song.py --kon`은 원래 자리 시퀀스와 단일 템포를 가정하므로 재배치 곡에는 쓰지 않습니다(그 도구로는 `02 DIFF`와 큰 오차가 나옵니다).
- 청취용 렌더: `work/sound/castle8k/run/castle.wav`(libgme, 150초)입니다. NDS 참조는 에셋의 `nds/dq4/sound/songs/02-王宮のメヌエット.wav`입니다. RMS 0.039로 DQ5 원곡 렌더(0.02~0.045)와 비슷하고 NDS 참조(0.104)보다 작습니다. **사용자 청취 판단은 아직 받지 않았습니다.**
- 검사는 `test_dq4soundport.py`를 더해 26개 통과, 1개 skip입니다. 상주 곡 샘플 누락은 아직 고치지 않았습니다.

- **맵 페이드 멈춤의 원인과 수정**: `00:CEB1`·`CEA2`는 맵을 불러오는 중에 돌고, 이때 NMI가 꺼져 있습니다. 실측으로 320프레임에 `$4200 = 01`을 쓴 뒤 321프레임에 훅이 실행됐고, 그 뒤 NMI 처리기 `00:885D`는 돌지 않았습니다. 프레임 기다림 `00:969A`는 직접 페이지 `$19` bit0을 켜고 소리 일(`2B:C473` → `JML $0008EF`, 입구 `2B:BECE`)로 넘어간 뒤 NMI가 그 비트를 지우기를 기다리므로 끝나지 않습니다. 「PLX 폭」 가설은 원인이 아니었습니다(그때 D = 0).
  - 원래 게임에서는 화면 어둡게 하기 15프레임 → NMI 끔·검은 화면 약 70프레임(필드는 약 50) → 밝히기 순서로 진행합니다. 큐에 넣은 `1A`·`01`은 불러오기가 끝난 뒤에 처리됩니다. `$194B`(맵 곡)도 불러오기 안에서 정해지므로, 화면을 어둡게 하는 시점에는 게임도 다음 곡을 모릅니다.
  - 새 훅은 프레임을 기다리지 않습니다. `CEB1`은 대기열이 비어 있을 때(`24:FE44`와 같은 판정) `2B:C169`와 같은 손잡기(`$08DC`·`$08DA`, APU 포트만 폴링)로 SPC `04 지금곡 40`을 직접 보낸 뒤 원래 `1A`로 갑니다. `CEA2`는 곡이 바뀐 때(`A ≠ $1D8B`)만 `01` 대신 `03 n 30`을 큐에 넣습니다. 같은 곡이면 원래 `01`로 갑니다.
  - `01`과 `03`을 이어 넣으면 첫 음이 최대 음량(`17,22`)으로 약 6프레임 울린 뒤 줄어 튀었습니다. `03`만 넣으면 첫 KON부터 `01,01`로 시작해 약 65프레임 동안 커졌습니다.
  - 성 → 필드 실측(`work/sound/fv3b-field*/`): 원래는 성 곡이 검은 화면 내내 최대로 울리다가 475~505프레임에 빠르게 줄고, 515프레임에 필드 곡이 시작합니다. 수정판은 앞 곡이 455프레임에 0이 되고(검은 화면 안), 500프레임에 `01,01`로 시작해 590프레임에 `12,17`이 됐습니다. 멈춤은 없었습니다.
  - 남은 것: 이 실측에서는 앞 곡이 아직 키우는 중(`04,06`)이었으므로 최대 음량에서 줄이는 경우는 문서의 `04 02 40` 실측(약 45프레임)에 기대고 있습니다. 같은 곡 이동, 대기열이 바쁠 때 건너뛰기, 전투 복귀, 빠른 연속 이동은 실측하지 않았습니다. 사용자 청취도 받지 않았습니다.

- **청취에서 들린 딸깍 소리와 잡음의 원인**: 사용자가 첫 렌더에서 「음정이 바뀔 때마다 스위치 같은 소리, 노이즈」를 들었습니다. KOF 없이 KON 된 경우는 0건이었고, 고역 튐은 KON 뒤 일정 시각(약 0.1초)에 났습니다.
  - `dq5brrenc`는 넘친 표본을 15비트로 자른다고 보고 골랐습니다. 실기 S-DSP(`dq5brr.decode`, bsnes와 같은 계산)는 16비트로 자른 뒤 1비트 밀어 부호가 뒤집힙니다. 샘플 `28`·`29`에서 두 계산이 최대 29,476 달랐고, 원래 PCM 대비 3000을 넘는 튐이 각각 53·23개였습니다. `28`의 첫 튐은 샘플 시작 0.095초 뒤였습니다. 실기 방식 SNR은 13.7·17.1dB로, 이전 보고서의 29.5·27.2dB(인코더 자기 모형 기준)보다 훨씬 낮았습니다.
  - `dq4soundbank.py`에 실기와 같은 계산으로 표본을 고르는 `encode_hw`를 두고, SNR도 `dq5brr.decode`로 잽니다. `dq5brrenc.py`는 dq5 트랙 파일이라 고치지 않았습니다. dq5 쪽 인코더도 큰 진폭에서 같은 문제를 낼 수 있으니 dq5 트랙에 알려야 합니다.
  - 다시 만든 `work/sound/bank02-8k-hw/`는 4개 모두 튐 0, 실기 SNR 27.2~38.7dB입니다. `work/sound/castle8k-hw/` 빌드·실행·`dq4soundcheck.py` 검사를 통과했습니다. 렌더는 `work/sound/castle8k-hw/run/castle.wav`입니다. 4ms 창 5kHz 이상 에너지가 중앙값의 30배를 넘는 창 수(60초)는 900에서 560이 됐고, DQ5 원곡 렌더는 243~862입니다. 다시 듣는 판단은 아직입니다. 남은 잡음은 8kHz 표본율과 BRR 양자화 때문일 수 있으며, 12kHz로 올리면 SPC 예산(지금 39,739/44,195)을 넘습니다.

- **음머리의 짧은 「팟」**: 인코더 수정 뒤 사용자는 딸깍이 크게 줄었지만 음 시작에 아주 짧은 잡음이 남는다고 했습니다. DQ5 원래 샘플 38개는 모두 무음 첫 블록(`02 00 …`)으로 시작하지만 새 샘플은 첫 블록부터 큰 값이었습니다. KON 직후 보간 버퍼에 앞 음 표본이 남는 것과 겹쳐 튈 수 있어, `convert_sample`이 16표본 무음 블록을 앞에 붙이고 반복 위치를 16표본 뒤로 옮깁니다. `work/sound/castle8k-lead/`(SPC 39,775바이트) 실행·검사를 통과했습니다. 렌더는 `run/castle.wav`, 목소리별 단독 렌더는 `solo/`입니다. 다시 듣는 판단은 아직입니다.

- **혼합본의 박마다 「똑딱」**: 목소리별 솔로는 깨끗했고(곡 시작 한 번만 「팟」), 혼합본은 솔로 합과 같았습니다(잔차 RMS 5.7). 드라이버(SPC `15E5`)는 음이 끝나기 1틱 전에 다음 바이트를 미리 봅니다. 다음이 음이면 KOF 해 하드웨어 릴리스로 8ms 만에 끊고, 쉼표(`00`·`50`)이면 건너뜁니다. 게이트 끝 `1A7F`는 KOF 대신 ADSR2를 `$0393`(SL | `DD` 속도)으로 바꾸는 소프트 릴리스입니다. 첫 배분은 같은 성부를 같은 목소리에 붙여, 775음이 앞 음 끝 12틱 안에 같은 목소리로 들어왔습니다. 그래서 앞 음이 최대의 40~65%로 울리다가 박마다 여러 목소리에서 동시에 끊겼습니다.
  - `allocate(tail_ticks=12)`는 앞 음 끝에서 12틱 이상 쉰 목소리를 먼저 고릅니다(12틱 미만으로 붙는 음 775 → 160). `release_rate=0x1C`(e-fold 약 48ms)로 꼬리를 빨리 줄입니다. 성 곡 시퀀스는 8,667바이트, SPC 41,548/44,195바이트입니다. 목소리 0의 처음 KOF 40번 중 최대의 30% 넘게 남은 채 끊긴 것이 30 → 9번이 됐습니다. `work/sound/castle8k-tail/` 실행·검사를 통과했습니다. **사용자가 2026-10-27에 이 렌더(`work/sound/listen/v4-tail-voices.wav`)를 듣고 딸깍 없이 깨끗하다고 확인했습니다.** 그 전에 「똑같다」고 들은 것은 이름이 모두 `castle.wav`인 이전 렌더였을 가능성이 큽니다. 청취 파일은 `work/sound/listen/v<번호>-<내용>.wav`처럼 이름을 겹치지 않게 둡니다. 50곡 일괄 변환(`converted/`)은 이 수정 전 결과이므로 다시 만들어야 합니다.
  - 곡 시작 한 번의 「팟」은 혼합과 솔로 합의 차이가 0.03초에만 컸습니다(700). 앞 곡의 메아리 버퍼가 남은 것으로 추정하지만 확인하지 않았습니다.

검증 재현:

```sh
OUT="$PWD/work/sound/castle8k/run" MAXF=2400 SONG=02 \
  "$MESENCE" --testrunner work/sound/castle8k/castle.sfc \
  "$PWD/sfc/dq4/tools/lua/dq4overturespc.lua" > work/sound/castle8k/run/emulator.log 2>&1
uv run --locked python sfc/dq4/tools/dq4soundcheck.py \
  work/sound/castle8k/castle.sfc work/sound/castle8k/run --song 02
```

## 첫 세션 인계(기록)

첫 세션은 구현 도중 인계를 요청받아 멈췄습니다. 그때 코드는 커밋하지 않은 상태였고, 두 번째 세션이 이어받아 PR로 올렸습니다.

- 브랜치: `feat/dq4-sound-port`
- 워크트리: 원래 체크아웃의 형제 폴더 `sfc-dq4-dq4-sound-port`. `git worktree list`로 실제 위치를 확인합니다.
- 시작점: `8a7cd6a`, 당시 최신 `origin/main`의 PR #463 머지 커밋. 재개 시 최신 main과의 차이를 확인합니다.
- 승인된 계획: 워크트리의 `.omc/plans/dq4-sound-port.md`. Plannotator에서 승인됐으므로 같은 계획의 승인을 다시 받을 필요는 없습니다.
- 트랙: `dq4`. DQ5·NDS 도구는 읽고 가져다 쓰며 다른 트랙 파일은 수정하지 않았습니다.
- 마지막 에이전트 작업들은 워크스페이스 지출 한도 오류로 종료됐습니다. 해결 중이던 문제가 끝났다고 가정하면 안 됩니다.

기존 워크트리의 미커밋 변경을 이어받습니다. 새 워크트리를 만들고 원래 것을 지우면 미추적 코드와 로컬 실험 결과를 잃습니다. 먼저 현재 파일을 보존합니다.

## 사용자 요구

1. BGM·효과음·짧은 팡파르를 SFC DQ5 엔진으로 포팅합니다. [sfc-dq4-assets](https://github.com/perfectacle/sfc-dq4-assets)를 참고합니다.
2. **NDS DQ4를 편곡·악기·표현의 주된 참고로 씁니다.** FC만 참고하면 품질이 낮아질 수 있다는 지시입니다. FC는 원작 곡·장면 대응의 보조 자료입니다.
3. 채택된 타이틀 서곡과 화면 연출을 보존합니다. 최신 사운드 구현은 `dq4overture.py`이며 `dq4titlepatch.asm` 단독이 아닙니다.
4. 같은 BGM은 화면이 바뀌어도 불필요하게 재시작하지 않습니다. 곡 동일성에는 곡 번호와 변형 flag를 함께 봅니다. 시퀀스 `10`의 서곡과 메뉴곡이 그 예입니다.
5. **빠른 전환이 자연스러운 전투·짧은 팡파르 등에 페이드를 강제하지 않습니다.** 끊김이 거슬리는 장면에만 fade out/in을 적용합니다.
6. DQ4·DQ5의 같은 원곡은 재사용합니다. 장면이나 이름이 같다는 것만으로 동일한 곡이라고 판정하지 않습니다.
7. 롬·추출 악보·음원·샘플·덤프는 커밋하지 않습니다. 생성물은 `work/`에만 있으며 참고 에셋 저장소는 수정하지 않았습니다.

## 작성된 코드와 API

아래 7개 파일은 인계 시점에 모두 미추적(`??`)입니다. 독립 리뷰와 실제 재생 검증이 끝나지 않은 초안입니다.

| 파일 | 구현과 한계 |
| --- | --- |
| [dq4soundcatalog.py](../tools/dq4soundcatalog.py) | 전체 목록, FC 장면 대응, DQ5 재사용 후보, 동시발음 수. `--dq5-rom`으로 숙박곡 두 성부를 다시 비교합니다. |
| [dq4soundport.py](../tools/dq4soundport.py) | NDS 악보 JSON → 최대 7성부 DQ5 시퀀스. 음량·팬·템포, 음역별 샘플 선택, 반복 명령 압축과 손실 보고서. 기본 DQ5 악기 대응은 청취 미승인 시안입니다. |
| [dq4soundbank.py](../tools/dq4soundbank.py) | NDS PCM WAV → BRR. 루프 정렬·표본율·조율 보정, 캐시·SNR 보고서. ADSR은 근사이며 PSG·noise는 명시적으로 거부합니다. |
| [dq4soundpatch.py](../tools/dq4soundpatch.py) | 기존 뱅크 `70` 재배치를 보존하고 `72` 이후에 시퀀스·샘플을 배치합니다. 새 샘플 번호 `26`~`C7`, 곡 묶음·IPL 길이·SPC 예산 검사, 청취용 타이틀 교체. 맵 페이드 훅은 두 번째 세션에서 프레임을 기다리지 않는 방식으로 바꿨습니다. |
| [test_dq4soundcatalog.py](../tools/test_dq4soundcatalog.py) | 목록과 숙박곡 비교 검사 |
| [test_dq4soundbank.py](../tools/test_dq4soundbank.py) | 조율식·루프 길이·BRR 캐시 검사 |
| [test_dq4soundpatch.py](../tools/test_dq4soundpatch.py) | 패치 구조·공간·기존 서곡 보존 검사 |

`test_dq4soundport.py`는 아직 없습니다. 변환기는 마지막에 길이 명령 중복 제거와 루프 처리를 수정했으므로, 남아 있는 보고서가 현재 코드와 같은 버전인지 재확인해야 합니다.

```python
conversion = dq4soundport.convert(score, voices=7, program_map=mapping)
# conversion.text, sequence, samples, report

resources, mapping, report = dq4soundbank.build_bank(
    score, asset_root, start_id=0x26, max_rate=8000, cache_dir=cache_dir,
)
# resources: {global_sample_id: bytes([length2] + sample_body)}
# mapping: {program: [{lo, hi, sample: global_sample_id}, ...]}

rom, report = dq4soundpatch.install(
    base_bytes,
    {slot: dq4soundpatch.Replacement(conversion.sequence, tuple(conversion.samples))},
    sample_resources=resources, map_fades=False, preview=slot,
)
```

`preview`는 청취용으로 타이틀 곡을 바꿉니다. 채택된 타이틀을 교체하는 결정이 아닙니다. CLI의 IPS는 `--base`에서의 차분이며 원본 DQ5에 바로 적용하는 패치가 아닙니다.

## 확인된 결과

### 입력과 기준 ROM

- `rom/`과 `work/state/`는 원래 체크아웃의 공유 링크입니다. 기존 원본·상태는 덮어쓰지 않았습니다.
- 기준은 원래 체크아웃의 `work/name-entry/dq4-name-entry.sfc`입니다. 4MB, SHA-1 `cc0e33a75fa06e34b5d2e57eb7db1143da336383`로 기존 문서와 일치했습니다.
- 이 워크트리의 `work/sound/baseline/dq4-sound-base.sfc`에 복사했습니다. 이후 main의 변경이 있다면 통합 전에 최신 빌드를 확인합니다.
- `uv sync --locked`를 마쳤습니다. MesenCE·Asar·libgme도 이 환경에서 찾았습니다. 다음 세션은 `MESENCE`·`ASAR`·필요하면 `GME_LIB`를 설정합니다. 개인 경로는 문서에 고정하지 않습니다.

### 목록·변환·재사용

- NDS는 서곡 스트림 1개＋시퀀스 곡 50개, 효과음 634개입니다. 전체 목록을 만들었습니다.
- `work/sound-port/converted/index.json`은 50/50곡 변환 결과입니다. **전곡 ROM 삽입·재생 성공을 뜻하지 않습니다.** 마지막으로 읽은 최대 시퀀스는 `1C`의 33,120바이트, `22`는 32,406바이트입니다. 바이트 크기만으로도 삽입 한도를 넘는 곡이 있습니다.
- 효과음 634개는 목록화까지입니다. 전체 변환·삽입·재생은 하지 못했습니다.
- NDS 숙박곡 `29`의 주선율 7음과 화음 7음은 DQ5 `1D`의 각 2트랙을 시간순으로 합친 음 배열과 일치했습니다. NDS의 지연 중복 파트·시각 차이는 편곡 차이입니다. `--dq5-rom`으로 재확인할 수 있습니다. 저장곡 등 다른 후보는 동일성 미확정입니다.
- 성 곡 `02`의 한 변환 결과는 원래 1,671음에서 1,669음을 내고 2음을 생략, 2음을 단축했습니다. 변환기 수정 뒤 다시 집계합니다.

### 샘플과 공간

- 성 곡 `02`는 NDS 프로그램48의 음역별 4샘플입니다. 12kHz 상한 BRR 리소스 합계 23,562바이트, 8kHz 상한판 15,723바이트를 만들었습니다.
- BRR SNR은 12kHz판 32.49~43.149dB, 8kHz판 27.191~38.718dB입니다. 비교 대상은 **리샘플링한 15-bit PCM**이며 원본 NDS 대비 종합 음질 평가가 아닙니다.
- 12kHz판 헤더 조율값 반올림 오차는 최대0.271cent였습니다. 계산 검사이며 실제 SPC 음높이 측정은 아닙니다.
- 삽입기의 SPC 예산은44,195바이트입니다. 상주 샘플11,067바이트＋상주 시퀀스5,551바이트＋여유512바이트를 잡습니다. 상주 샘플 `00`만9,889바이트입니다.
- 첫 성 곡＋NDS12kHz판 빌드는 `SPC budget exceeded (56711/44195 bytes)`로 멈췄습니다. 8kHz판 샘플 생성은 끝났지만 결합된 완성 ROM·재생 확인은 없습니다. 최신 악보 압축 결과로 다시 계산합니다.

### 실제 실행과 검사

- 기준ROM 전원→600프레임 A→메뉴의1,000프레임 실행은 끝났습니다. `work/sound/baseline/events.txt`의319프레임은 곡 자리＋키ュー가 빈 상태의 검출 시각으로, 첫 발음 시각이 아닙니다.
- `work/sound-port/runtime-smoke.sfc`는 단음만 slot`02`에 넣은 시험입니다. 전원부터144프레임에 곡 자리가 검출됐습니다. `work/sound/smoke/`에 결과가 있습니다. NDS 성 곡을 재생한 결과가 아닙니다.
- 마지막 부모 세션 단위 검사는19개 중18개 통과·1개skip입니다. 최신 변환기 수정까지 포함한 최종 전체 검증은 아닙니다.

## 가장 먼저 해결할 문제

### 맵 페이드 실행 오류

**(위 「이어받은 세션의 진행」에서 원인을 찾고 고쳤습니다. 아래는 첫 세션 기록입니다.)** `--map-fades`는 첫 세션 당시 사용할 수 있는 품질이 아니었습니다. `00:CEB1` 정리 호출을 `71:8000`으로, `00:CEA2` 재생 호출을 `71:8080`으로 바꿉니다. `04`로 구곡을 줄이고 기다린 뒤 정리하며, `03`으로 새 곡을 키우는 설계입니다.

| 실험 폴더 | 관찰 |
| --- | --- |
| `work/sound/base-change/` | 원본은 `01/00` 지정 셀12,12에 도착 |
| `work/sound/fade-change/` | 패치판은7,23이 되고 플래그에도 이상 변화. 정상 도착으로 판정하면 안 됨 |
| `work/sound/fade-same/` | 321프레임 `718000`, `cmd=04 arg=00` 뒤 시간 초과 |
| `work/sound/trace-fade/` | 마지막 추가 추적. `trace.txt`에 CPU 상태와 스택 |

추적 마지막은 `71:8017`→`24:FE44`→`00:9506`→`00:969A`→`2B:C473`입니다. 페이드 대기 본체 이전의 키ュー 대기 안에서 멈출 가능성도 살핍니다. `00:9506`은 JSL 가능한 입구이며 `00:969A`는 P/X/Y/DB/DP 등을 저장하는 코드였습니다. **「PLX 폭만이 원인」이라는 가설은 확인되지 않았습니다.** 호출 문맥·상태 복원·SPC 대기를 실측해야 합니다.

프로브의 `TEST=wait:500`은 warp가973프레임에 끝나 `MAXF-1`에 쓰는`snd.txt`가 없었습니다. 다음에는 `TEST=wait:1000 MAXF=1000`처럼 먼저 종료되지 않게 합니다. 미초기화 메모리 경고는 원본 비교군에서도 많았습니다. 출력은 실험 로그에 저장합니다.

### 상주 곡을 바꿀 때 샘플이 빠질 가능성

독립 코드 리뷰의 **미수정** 지적입니다. 상주 시퀀스`17` 등을 바꾸면서 곡 세트를 `[L,L,samples...]`로 두면, 시퀀스가 이미 있어 선전송을 건너뛰고 후전송`L-k=0`이 되어 새 샘플이 빠질 수 있습니다. [DQ5 소리 형식](../../dq5/docs/dq5-sound-format.md)의 FULLSET 문제와 같은 조건입니다. 전투곡 번호만 교체한 상태를 완료로 보지 않습니다.

### 용량·표현·회귀

- 시퀀스 압축, 양자화 뒤 값이 같은 CC 경계 제거 등으로 공간을 줄입니다. 검사 상한을 높여 통과시키면 안 됩니다.
- 곡 세트 표는 SPC `28EC`~`2A5D`의369바이트이며 기존 서곡 후363바이트입니다. 여러 곡의 샘플 수를 늘리면 넘칩니다. IPL 길이·종료 마커까지 함께 맞춰야 합니다.
- 피치벤드·모듈레이션·NDS ADSR/릴리스, 루프를 가로지르는 지속음은 미지원 또는 근사입니다. 보고서에서 빠진 음과 표현을 숨기지 않습니다.
- 루프 시작점이 지속음 중간일 때 tie 처리 문제가 리뷰 중이었습니다. 일부 수정은 들어갔지만 최종 검사는 없습니다.
- 변환 보고서는 NDS 샘플을 줘도 「DQ5 native samples」라고 쓰는 부분이 있습니다. 실제 입력에 맞게 바로잡아야 합니다.
- 새 샘플ID 로딩, BGM＋SFX 동시 출력, 빠른 연속 전환, 팡파르 후 복귀, 최신 타이틀·이름 입력 회귀는 미검증입니다.
- 지금은 DQ5 곡 슬롯을 바꾸는 기반 작업입니다. 미구현 DQ4 맵·이벤트 전체가 연결됐다는 뜻이 아닙니다.

## 재개 명령

이 워크트리에서 실행합니다. `ASSETS`는 실제 에셋 저장소 위치로 바꿉니다.

```sh
export ASSETS=../sfc-dq4-assets
git status --short
uv sync --locked
uv run --locked python -m unittest discover -s sfc/dq4/tools -p 'test_dq4sound*.py'
uv run --locked python sfc/dq4/tools/dq4soundcatalog.py \
  --assets "$ASSETS" --dq5-rom rom/dq5.sfc --out work/sound-port/catalog.json
uv run --locked python sfc/dq4/tools/dq4soundport.py export \
  --assets "$ASSETS/nds/dq4/sound/songs" --out work/sound-port/converted
uv run --locked python sfc/dq4/tools/dq4soundbank.py \
  --score "$ASSETS/nds/dq4/sound/songs/02-王宮のメヌエット.json" \
  --assets "$ASSETS" --max-rate 8000 --out work/sound/bank02-8k
```

다음은 공간 검사를 포함한 구성 명령이며 성공을 아직 보장하지 않습니다. 먼저 `--map-fades` 없이 곡만 확인합니다.

```sh
uv run --locked python sfc/dq4/tools/dq4soundpatch.py \
  --base work/sound/baseline/dq4-sound-base.sfc \
  --replace "02=$ASSETS/nds/dq4/sound/songs/02-王宮のメヌエット.json" \
  --bank work/sound/bank02-8k --preview 02 --out work/sound/castle/castle.sfc
```

빌드가 되면 전원부터 새 실험 폴더에서 실행합니다. 새 샘플 검사에 원본ship 상태를 바로 쓰면 SPC의 표가 원래 값으로 복원될 수 있습니다.

```sh
mkdir -p work/sound/castle/run
OUT="$PWD/work/sound/castle/run" MAXF=2400 SONG=02 \
  "$MESENCE" --testrunner work/sound/castle/castle.sfc \
  "$PWD/sfc/dq4/tools/lua/dq4overturespc.lua" \
  > work/sound/castle/run/emulator.log 2>&1
```

기존 페이드 오류를 재현하려면 다음을 씁니다. `fade-only.sfc`는 **옛 오류가 남은 ROM**입니다. 코드를 고쳐도 자동 갱신되지 않으므로 수정 뒤에는 `install()`에 기준ROM의 원래 slot02 악보·샘플 목록을 넣고 `map_fades=True`로 다시 만듭니다.

```sh
mkdir -p work/sound/fade-recheck
LIBDIR="$PWD/work/sound/warplib" STATE="$PWD/work/state/ship.mss" \
  TO='01/00,12,12,2' SETTLE=60 TEST=wait:1000 MAXF=1000 \
  SHOT_DIR="$PWD/work/sound/fade-recheck" DSP=1 WATCH=718000,718080,00CEA2 \
  "$MESENCE" --testrunner work/sound/fade-only.sfc \
  "$PWD/sfc/dq5/tools/lua/dq5sndlog.lua" \
  > work/sound/fade-recheck/emulator.log 2>&1
```

## 로컬 자료와 다음 완료 조건

| 위치 | 내용 |
| --- | --- |
| `work/sound-port/catalog.json`, `converted/` | 목록, 50곡의 악보·바이너리·손실 보고서 |
| `work/sound-port/bank02/`, `work/sound/bank02-8k/` | NDS 성 곡4샘플의12kHz·8kHz판 |
| `work/sound/castle/` | 실패한 조합의 변환 보고서·텍스트. 완성ROM과 혼동하지 않음 |
| `work/sound/baseline/`, `work/sound/smoke/` | 기준ROM·단음 시험의 실행 기록과 SPC/DSP 덤프 |
| `work/sound/fade-only.sfc`, `*-change/`, `fade-same/` | 오류가 있는 페이드 비교 실험 |
| `work/sound/trace.lua`, `work/sound/trace-fade/` | 마지막 CPU·스택 추적 |
| `work/sound/warplib/` | 툴킷lib.lua 링크와 dq5warp.lua를 복사한boot.lua |

실제 재생·독립 리뷰·비교 청취를 마친 뒤 형식 문서·일지·todo를 갱신합니다. 최신main 기준 일지 번호, 필수 문서 검사·Python 컴파일·관련 테스트, PR의`ci-ok`는 아직입니다. 음질의 사용자 청취 확인도 아직 받지 않았습니다.
