# 배포 관문

사람이 플레이해 보지 않고 AI 검사만으로 IPS 를 배포하려면 그 앞에서 모든 층의 검사를 한 번에 돌려 하나의 보고서로 남겨야 한다. 그 일을 `tools/release_check.py` 가 한다. 사람이 부를 때만 돈다. 예약 실행·밤 스윕은 하지 않는다.

## 단계

| 단계 | 하는 일 | 통과 |
| --- | --- | --- |
| `build` | `dq4build.py` 로 출하 롬을 `work/release/run-*/build/` 에 빌드(빌드 단계 캐시 켬). 같은 때 모든 캐시를 끈 빌드를 `build-cold/` 에 한 번 더([캐시 빌드 대조](#캐시-빌드-대조)) | 롬이 나오고, 두 빌드의 산출물 바이트가 모두 같음. 롬 SHA-1 이 보고서 폴더 이름 |
| `unit` | CI test 잡과 같은 폴더(`sfc/dq4/tools`, `sfc/dq5/tools/tests`, `tools/tests`, `fc/dq4/tools`, `nds/dq4/tools`)마다 `unittest discover` | 모두 0 으로 끝남. 롬이 있으므로 롬 게이트 시험도 돈다 |
| `guards` | 모든 트랙 `guards.toml` 의 실행 검사 전부(`guards.run_many`). PR 에서 빠지는 `tier = "release"` 검사와 묶음으로만 걸리는 검사도 여기서 돈다 | 모두 통과 |
| `sweep` | 트랙마다 `release.toml` 의 시드 스윕 | 모두 0 으로 끝남 |
| `coverage` | 빌드 경로(`dq4publish.inputs()` 의 시험 아닌 `.py`) 커버리지를 둘로 잰다. 로컬: 단위 전부와 빌드 캐시 끈 빌드 한 번(`patch = subprocess` 로 단계 스크립트까지). CI 와 같게: 롬 링크 없는 임시 워크트리에서 롬·도구 환경 변수(`CI_UNSET`) 없이 단위만 | 로컬 ≥ 90%, CI 와 같게 ≥ 80% |

- 앞 단계가 실패해도 나머지를 돌려 보고서에 모두 남긴다. 실패한 검사·스윕은 다시 돌려 통과로 덮지 않는다. 실패 까닭(장면 검사가 남기는 「MesenCE 실행: …」)이 로그에 그대로 남고, 바쁜 머신에서 실패하는 검사의 목록이 된다.
- 단계마다 같은 머신에서 돈 MesenCE 를 30초마다 세어 적는다. 이 실행과 다른 워크트리의 수(최대·평균)와 워크트리마다의 최대 수다. libretro 코어는 파이썬 프로세스 안에서 돌아 세지 않는다.

### 걸리는 시간

머신 부하에 따라 크게 바뀌므로 결론만 적는다(실행 검사 2개씩, 다른 세션과 함께 돈 때).

- 전체는 약 3시간이다. 실행 검사 전부가 가장 길고(약 1시간 45분), 시드 스윕이 다음이다(약 1시간). 빌드·단위·커버리지는 합쳐 15분 안쪽이다.
- 스윕에서는 전투 갈래 32시드가 가장 길어(스윕 시간의 절반 남짓), 시드 수를 줄이면 가장 크게 준다.
- 위 시간은 빌드 단계 캐시와 공유 상태 캐시를 쓴 실행에서 쟀다. 그래서 passed 근거가 될 수 없다. 걷기 스윕은 그때 공유 서장 끝 상태 캐시가 맞았다. 모든 캐시를 끈 지금 관문 환경에서는 각 실행 검사가 롬을 캐시 없이 다시 빌드해 더 길어진다. 걷기 16시드 스윕을 모든 캐시를 끄고(상태 캐시 `miss`, 서장부터 새로 걸음) 다시 재니 약 8분으로, 공유 상태 캐시가 맞았을 때(약 7분)보다 1분쯤 길었다.
- IPS 를 만드는 `dq4publish.py build`·`release` 는 거의 롬 빌드 시간이다(빌드 단계 캐시 켬 약 1분, 끔 약 2분). IPS 만들기(`ips.make`)는 1초 안쪽이다.
- CI 와 같게 잰 단위에서는 롬 게이트 시험이 dq4 125개, dq5 42개 건너뛰어졌다. CI 와 같은 꼴이다.

### 캐시를 쓰지 않는다

관문 모드에서는 build 의 캐시 빌드를 뺀 모든 단계(build 의 무캐시 빌드·unit·guards·sweep·coverage)가 같은 환경(`gate_env`)으로 돈다.

| 캐시 | 관문에서 |
| --- | --- |
| 검사 결과(`guards.py` 의 `work/cache/guards`) | 쓰지 않음 |
| 장면(`DQ4_READSET=off`, [읽은 롬 바이트 캐시](dq4-readset-format.md)) | 읽지 않음 |
| 빌드 단계(`DQ4_BUILD_CACHE`) | 출하 롬 빌드만 씀(`cached_env`). 같은 실행의 무캐시 빌드와 바이트가 같아야 통과. 그 밖의 단계는 `off` |
| 곡 변환·검산(`DQ4_SOUND_CACHE`, 자원 저장소 `sfc/dq4/cache/sound`) | 출하 롬 빌드만 씀. 무캐시 빌드는 `off` |
| 서장 끝·시작 상태(`DQ4_STATES_CACHE`) | 실행 폴더의 빈 `states/` 에서 처음 한 번 만들고 그 실행 안에서만 다시 씀 |

### 캐시 빌드 대조

관문은 출하 롬을 캐시로 빨리 빌드하되, 같은 실행에서 모든 캐시를 끈 빌드와 바이트가 같아야 통과다. 캐시 키에 빠진 입력이 있으면 캐시가 옛 결과를 내 두 빌드가 갈린다.

- 무캐시 빌드(`cold_env`): `DQ4_BUILD_CACHE=off`·`DQ4_SOUND_CACHE=off`·`DQ4_READSET=off`, Go 도구 대신 파이썬 경로(`DQ4_NATIVE=off`). 두 경로는 같은 바이트여야 한다.
- 견주는 것은 빌드 폴더의 파일 전부(`ci_cache.digest`: 파일마다 SHA-256, `.prebuilt.json` 뺌)다. 중간 롬·`ledger.json`·`messages.json`·`leader/` 도 든다. 다르면 `ci_cache.verify_build` 가 단계(`STAGE_OF`)마다 묶은 해시 표와 다른 파일 목록을 낸다.
- 로컬 관문은 `build` 단계가 두 빌드를 함께 돌려 `logs/build-verify.md` 에 남긴다. `--rehearse` 는 무캐시 빌드를 하지 않는다.
- 키가 단계가 읽는 것을 모두 담는지는 따로 `dq4buildkeys.py` 가 본다(`test_dq4buildcachekeys`, CI cold-build 잡). 파이썬 감사 훅으로 단계가 연 파일·읽은 환경 변수를 적어 `dq4buildcache.key_inputs` 와 견준다. 키 밖이어도 되는 것(표준 라이브러리·설치 패키지, 단계가 먼저 쓴 파일, 결과를 바꾸지 않는 환경 변수 `IGNORED_ENV`, 키에 드는 바이너리 `EXTERNAL`)은 그 모듈에 까닭과 함께 적는다.

- 캐시 적중은 「같은 키면 같은 결과」 라는 가정에 기댄다. 그 키는 빠진 입력이 여러 번 드러나 고쳐 왔다. 롬 복사본 이름이 든 상태 해시, 로더가 매핑을 고를 때 읽는 머리 후보, MesenCE 사용자 설정이 그런 예다. 배포는 이 가정 없이 한 번 다 돈다.
- `guards.py --no-cache` 도 같은 셋을 끈다(상태 캐시는 그 로그 폴더 아래 빈 `states/`).
- 보고서에 상태 캐시를 어떻게 썼는지와, 스윕마다 검사가 찍은 상태 캐시 표시(`hit`·`miss`)를 적는다.
- `--rehearse` 는 캐시를 그대로 써서 빨리 돈다. 판정은 `rehearsal` 이라 배포 근거가 되지 않는다.

### 고친 것이 있는 트리

판정 `dirty` 는 시작할 때와 판정 직전에 두 번 잰다. 추적 파일을 고친 것뿐 아니라 추적 안 된 파일(무시 목록 밖)도 센다. 추적 안 된 빌드 입력도 결과에 닿을 수 있어서다. 도는 사이 HEAD 가 바뀌어도 `dirty` 다.

### 단계가 멈출 때

단계가 예외로 멈추면(임시 워크트리를 못 만듦, 커버리지 자료가 없음 등) 그 단계를 `failed` 로, 예외를 내용으로 적고 다음 단계로 간다. 보고서는 늘 남는다.

### 시드 스윕

`sfc/dq4/release.toml` 의 `[[sweep]]` 마다 시드를 넘겨 한 번 돈다. 그 스크립트가 시드마다 따로 돌고, 모두 통과해야 0 으로 끝난다.

| 칸 | 뜻 |
| --- | --- |
| `name`·`why` | 스윕 이름과 지키는 것 |
| `run` | 명령. `{rom}` 관문이 빌드한 롬, `{out}` 출력 폴더, `{seeds}` 쉼표로 이은 시드 |
| `seeds` | 시드 수. 없으면 `--seeds-n`(기본 16) |

- 시드는 0 부터 차례로 n 개다. 시드 0 은 실행 검사와 같은 기준이라 늘 든다.
- 그 트랙 폴더의 `seeds.json`(`{"스윕 이름": [{"seed": 5, ...}]}`)에 적은 실패 시드를 덧붙인다. 아직 파일은 없다.
- 기본 16 은 자동 검증 계획의 「배포 전 16~32」 가운데 낮은 쪽이다. 16시드로 잡아도 스윕 전체가 실행 검사 전부보다 짧아([걸리는 시간](#걸리는-시간)), 관문 한 번이 몇 시간 안에 든다.
- 스윕마다의 수는 계획의 케이스 표를 따랐다. 전투 갈래 32, 인물 길 막기 8, 코어 교차 4, 가게·마을 8 이다.

## 보고서

`work/release/<롬 SHA-1 앞 12자리>/report.json`·`report.md`(같은 이름이 있으면 시각을 붙임)와 단계별 로그 `logs/` 다.

- 커밋과 추적 파일에 고친 것이 있는지, 롬 SHA-1, 단계마다 결과·시간·내용이 든다.
- 표가 셋 있다. 단위 테스트는 폴더마다 시험 수·건너뜀, 실행 검사는 검사마다 결과, 스윕은 스윕마다 시드 목록이다.

| 판정 | 뜻 |
| --- | --- |
| `passed` | 고친 것 없는 커밋에서 모든 단계를 캐시 없이 돌려 모두 통과 |
| `failed` | 단계 하나라도 실패 |
| `rehearsal` | `--rehearse`(캐시 씀) |
| `partial` | `--stages` 로 일부만 돎 |
| `dirty` | 모두 통과했지만 커밋하지 않은 고친 것이 있음 |

`passed` 만 배포 근거다. 종료 코드는 `passed` 일 때만 0 이다.

## 배포판 IPS

사람에게 내보내는 배포판은 관문이 `passed` 로 판정한 보고서가 있어야만 만든다. 머지마다 갱신하는 개발판(`dq4publish.py build`, 에셋 저장소 `sfc/dq4/ips/`)은 그대로 둔다.

```sh
uv run --locked python sfc/dq4/tools/dq4publish.py release --report work/release/<롬 SHA-1 앞 12자리>/report.json [--commit]
```

- 보고서가 `passed` 이고(연습·일부·`dirty` 아님), 보고서의 커밋이 지금 HEAD 이며 origin/main 에 머지된 커밋이어야 한다.
- 판정 `verdict` 를 그대로 믿지 않는다. 다섯 단계(`build`·`unit`·`guards`·`sweep`·`coverage`)가 모두 있고 단계와 그 표의 줄이 모두 통과여야 한다.
- 보고서는 관문이 쓴 자리 `work/release/<롬 SHA-1 앞 12자리>/`(같은 이름이 있어 시각이 붙은 폴더 포함)에 있어야 한다.
- 이 검사는 실수(연습·실패·다른 롬의 보고서를 고름)를 막는다. 위조는 막지 못한다. 보고서는 로컬 파일이라 단계 결과까지 고쳐 쓰면 통과한다. 저장소에는 서명 비밀을 둘 곳이 없어 서명하지 않는다.
- 다시 빌드한 롬의 SHA-1 이 보고서의 롬 SHA-1 과 같아야 한다.
- 에셋 저장소 `sfc/dq4/release/dq4-ch1.ips` 와 `RELEASE.txt`(커밋, 원본·결과 롬 SHA-1, 보고서 시각과 SHA-256)에 쓴다.

## 커버리지가 단계 스크립트까지 재는가

로컬 커버리지는 `dq4build.py` 가 하위 프로세스로 부르는 단계 스크립트까지 잰다(coverage 설정 `patch = subprocess`). 실측 보고서(`coverage-local-report.txt`)에서 단계 스크립트가 모두 잡혔다. `dq4titlelayers` 92%, `dq4titlelayerpatch` 95%, `dq4overture` 96%, `dq4chapter1` 97%, `dq4menupatch` 91%, `dq4soundset` 94%, `dq4sparfx` 83%, `dq4people` 97% 다. 롬 없이(CI 와 같게) 재면 `dq4chapter1` 61%, `dq4people` 64% 다.

## CI 에서 돌리기

실행 검사는 GitHub 러너(ubuntu-26.04-arm)에서 나눠 돈다. needs 에 `macos` 가 든 검사만 로컬 몫이다(지금은 0개). 배포 관문은 사람이 `gh workflow run release-gate.yml [-f shards=N] [-f ref=REF] [-f rehearse=true]` 로 부를 때만 돈다. PR 은 `ci.yml` 의 `pr-guards` 잡이 같은 조각 워크플로를 `mode: pr` 로 부른다.

| 파일 | 하는 일 |
| --- | --- |
| `.github/workflows/release-gate.yml` | `workflow_dispatch` 만. 롬 시크릿을 이름을 대어 `guard-shards.yml` 에 넘긴다(`mode: release`, `cache` 는 입력 `rehearse`, 기본 false) |
| `.github/workflows/cache-warm.yml` | 매일 `17 15 * * *`(KST 00:17)과 `workflow_dispatch`(`force`). main 에서만. `plan` 이 평문 캐시 `cache-warm-*`(데운 커밋 SHA·시각뿐)를 보고 main HEAD 가 지난번 데운 커밋과 같고 6일이 안 지났으면 건너뛴다(GitHub 캐시는 7일 안 쓰면 지워짐). 아니면 `guard-shards.yml` 을 `mode: release`·`cache: true`·조각 16(무료 동시 잡 20개 안)으로 불러 모든 CI 가드의 통과 기록·단위 캐시(장면·출발 상태)·출하 롬 빌드 단계·사운드 캐시를 main 범위에 채운다. 통과하면 `mark` 가 그 커밋을 적는다. 판정은 연습이라 배포 근거가 아니고, 실패하면 GitHub 기본 알림만 간다. 동시 실행 묶음은 관문의 main 실행과 같은 `release-gate-main` |
| `.github/workflows/ci.yml` 의 `guard-plan`·`pr-guards`·`pr-guards-result` | PR 과 main push. `guard-plan`(시크릿 없음)이 보호 테스트(`test_release_gate_workflow`·`test_pr_guards_workflow`)를 먼저 돌리고 `guards.py --base B --head H --pr-body 본문 --plan $GITHUB_OUTPUT` 로 걸린 검사를 CI 몫 `guards`·로컬 몫 `local`(`LOCAL_NEEDS`)·조각 수 `shards`(지난 시간 합 / 480초 올림, 1~8)로 나눈다. `pr-guards` 는 CI 몫이 있고 같은 저장소 브랜치 PR 이거나 main push 일 때만 `guard-shards.yml` 을 `mode: pr`·`cache: true`·head SHA 로 부른다. PR 실행이 저장한 캐시는 그 PR 만 읽으므로, 머지 뒤 main push 실행이 같은 가드를 다시 돌려 다음 PR 들이 읽을 빌드·장면·통과 기록 캐시를 main 에 데운다(push 는 `before…sha` 로 고름). `pr-guards-result` 가 판정을 하나로 모아 `ci-ok` 에 넘긴다(가드 없음·PR 아님은 통과). 포크에서 온 PR 은 `pr-guards-result`·`ci-ok` 가 「이 저장소는 포크 PR 을 받지 않는다」 로 실패한다 |
| `.github/workflows/guard-shards.yml` | `workflow_call` 만. 입력 `ref`·`mode`(`release` 모든 검사, `pr` 은 `guards` 목록만)·`guards`·`shards`·`cache`(기본 false). `build`(커밋·조각 목록) → `rom` 행렬(`ch1`·`ch2 --chapter2` 출하 롬을 빌드 단계 캐시로 함께 한 번씩 빌드, `digest --kind cached`)과, `mode: release` 면 함께 `cold-build`(두 롬을 모든 캐시를 끄고 다시, `ch2` 는 파이썬 경로, 도구도 캐시 없이 셋업, `dq4buildkeys.py`) → `build-verify`(`ci_cache.py verify-build`, 다르면 실행 실패) → `shard` 행렬(두 롬을 받아 `work/ch1`·`work/ch2` 에 두고 `DQ4_PREBUILT` 를 켜 `guards.py --all --run [--no-cache] --shard k/N --exclude-needs macos --json`) → `report`(`release_check.py --ci-summary [--require-build]`, 조각이 받은 롬(`digest --kind shard-k`)까지 무캐시 빌드와 견줌, 실행 요약에 표, 통과 기록 캐시 저장) |
| `.github/actions/ci-roms` | composite action. 프라이빗 에셋 저장소 릴리스 `ci-roms-v1` 의 age 암호화 묶음(`dq5.sfc dq6.sfc dq4.nes dq4-rev0.nes dq4ds.nds dq4ds-kr.nds dq4ds-kr.ml1 dq4ds-kr.sav`)을 `rom/` 에 풀고 롬 SHA-256 목록을 `$RUNNER_TEMP/rom-hashes.txt` 에 |
| `.github/actions/ci-tools` | `tools/ci_gate_setup.sh tools` 를 부르고 asar·Galmuri zip·libretro 코어·Go 도구(`sfc/dq4/tools/native`, `DQ4_NATIVE`)를 저마다 평문 캐시에(키: asar 커밋, zip SHA-256, `dq4cores.py`·bsnes 패치 해시, Go 도구 소스 해시). Go(고정 판·SHA-256)는 Go 도구 캐시가 빗나갈 때만 받는다. 셋업 바로 뒤에 저장해 잡이 뒤에서 실패해도 남는다 |
| `tools/ci_gate_setup.sh tools`·`pins` | asar·Galmuri·libretro 코어·MesenCE 를 `$RUNNER_TEMP/gate-tools` 에 두고 `ASAR`·`DQ4_GALMURI`·`DQ4_CORES`·`MESENCE`·`LIBDIR` 를 잡 환경에. MesenCE 는 공식 2.2.1 리눅스 ARM64 판(SHA-256 고정, 로컬 맥 판과 같은 릴리스)을 포터블 모드로 풀고 설정은 `tools/ci-mesence-settings.json`(apt `libsdl2-2.0-0`, 화면 없이 `--testrunner`). `pins` 는 캐시 키에 쓸 고정 판을 `$GITHUB_OUTPUT` 에 |
| `.github/actions/enc-cache` | 롬에서 나온 바이트를 담는 폴더의 캐시. 입력 `op`(`restore`·`save`)·`name`·`prefix`·`dir`·`age_key`·`exclude`·`max_mb`. 폴더를 tar+zstd 로 묶어 `CI_ROM_AGE_KEY` 의 공개 키로 암호화한 파일 하나만 캐시에 둔다. 키는 `<prefix>-<내용 해시>`, 되살리기는 그 접두어의 가장 새 키. 이 잡에서 되살린 키와 내용이 같으면 저장하지 않는다 |
| `.github/actions/ship-cache` | 출하 롬 빌드 단계마다 enc-cache 하나(`tools/ci_cache.py` 의 `SHIP_LABELS`: `titlelayers chapter1-messages titlelayerpatch overture-build menupatch-build chapter1-build other`). 한 단계가 바뀌어도 나머지 묶음은 맞는다 |
| `.github/actions/unit-cache` | 검사 단위(검사, `parts` 가 있으면 하위 조각 하나)마다 enc-cache 하나, 자리 12개(`guards.UNIT_SLOTS`). 입력 `op`·`slots`(`guards.py --unit-slots` 의 JSON `[{prefix, dir}]`)·`age_key`. `tools/ci_cache.py slots` 가 목록을 `p<i>`·`d<i>` 출력으로 바꾼다 |
| `tools/ci_cache.py` | `unpack`·`pack`(enc-cache 의 몸통), `prune --dir D --since FILE`(이 잡에서 쓰지 않은 빌드 단계 칸 지우기), `ship-build --out DIR --chunks DIR [인자]`(`dq4build.py` 를 돌리고 단계 시간 `[stage]` 을 찍고, 쓴 `dq4buildcache` 칸을 단계별로 복사, `DIR/.prebuilt.json`(커밋·인자·롬 SHA-256)을 남김), `prebuilt --out DIR [인자]`(`DQ4_PREBUILT` 폴더 가운데 같은 커밋·인자·롬의 빌드를 복사, 없으면 `dq4build.py`), `digest --dir D --variant V --kind K --out F`, `verify-build DIR`([캐시 빌드 대조](#캐시-빌드-대조)) |
| `DQ4_PREBUILT` | 조각 잡 환경. 켜져 있으면 `guards.py` 가 가드 명령의 `dq4build.py` 를 `ci_cache.py prebuilt` 로 바꾼다(`with_prebuilt`). rom 행렬은 가드가 쓰는 `dq4build.py` 인자 조합을 모두 담아야 한다(보호 테스트) |
| `tools/ci_artifact_check.py DIR --hashes FILE` | 올리기 바로 앞. 롬·세이브·패치 확장자(`.sfc .smc .nes .nds .ml1 .sav .mss .ips .srm .state`), 심볼릭 링크, 롬 해시와 같은 내용, 8MB 넘는 파일이 있으면 1. 실패하면 올리지 않는다 |

- 빌드가 읽는 에셋은 에셋 저장소에 커밋돼 있어야 한다. 로컬 체크아웃에만 있는 파일은 CI 롬을 로컬 롬과 다르게 만든다.
- 리눅스 bsnes 는 WRAM 을 `/proc/self/maps` 의 코어 매핑에서 찾는다(`dq4libretro.linux_segments`). 못 찾으면 직렬화로 읽고 써서 타이밍이 바뀌어 걷기·장면이 bsnes 만 어긋난다.
- 시크릿: `CI_ROM_TOKEN`(에셋 저장소 읽기), `CI_ROM_AGE_KEY`(age 개인 키). 키 줄은 `::add-mask::` 로 가린다.
- 조각 잡은 `HEADLESS_SLOTS=4`(러너 코어 수), 검사 하나의 시간 제한 3600초. 로컬 MesenCE 설정을 바꾸면 `tools/ci-mesence-settings.json` 도 같게 맞춘다(개인 경로·창 위치는 뺀다).
- artifact 는 조각 결과 JSON, 검사 로그, 장면 로그(`scenes/`, work 아래 2MB 미만 `*.log`), 검사 통과 기록(`work/cache/guards`, 입력 키와 시간)뿐이다.

### CI 캐시

퍼블릭 저장소라 포크 PR 워크플로도 기본 브랜치 캐시를 읽는다. 롬과 무관한 것만 평문 `actions/cache` 에 두고, 롬에서 나온 바이트는 enc-cache 로만 둔다.

| 캐시 | 담는 곳 | 키 | 언제 |
| --- | --- | --- | --- |
| asar·Galmuri zip·libretro 코어 | 평문(`$RUNNER_TEMP/gate-tools/…`) | 고정 판 | 늘 |
| 사운드 변환(`assets/sfc/dq4/cache/sound`) | enc-cache `ship-sound-<변형>`(조각은 `ch2` 것을 읽기만) | 내용 해시 | 늘(로컬 관문도 에셋 저장소의 이 캐시를 쓴다) |
| 출하 롬(`ch1`·`ch2`) | enc-cache `ship-rom-<변형>-<run_id>` | 이 실행만 | 늘. rom 잡이 한 번 빌드하고 조각과 가드는 받아 쓴다(「실패한 잡만 다시」 로 다시 도는 조각도 같은 키) |
| 출하 롬 빌드 단계(`dq4buildcache` 칸) | ship-cache, 변형·단계마다 하나(`ship-<변형>-<단계>`) | 내용 해시 | 늘(관문은 cold-build 와 바이트 대조) |
| 검사 단위의 장면·상태·검사 빌드 칸(`work/cache/units/<단위>/` 의 `readset`·`states`·`calls`) | unit-cache, 단위마다 `guard-unit-<이름>[~<k>of<parts>]`, 1500MB 넘으면 저장 안 함 | 내용 해시 | `cache` 일 때만 |
| 검사 통과 기록(`work/cache/guards`) | 평문 `guard-results-<run_id>-<attempt>`, report 잡이 조각들 것을 합쳐 저장 | 실행 | 저장은 늘, 쓰기는 `cache` 일 때만 |

- 단위 캐시 열쇠에는 모드·조각 번호·조각 수가 없다. 그래서 PR 은 매일 데우기·관문 연습·다른 PR 수의 실행이 남긴 단위 캐시를 그대로 읽는다. 안의 항목은 롬 바이트·코드 지문으로 찾으므로 낡은 묶음은 빗나갈 뿐이다. 조각 잡은 `guards.py --all --shard k/N --unit-slots F` 로 자기 단위의 자리를 무거운 것부터 12개 고른다. PR(`mode: pr`)은 `--pending-only` 로 통과 기록이 다 맞는 단위를 빼 돌 것만 되살리고, `release` 는 모두 되살려 7일 안에 한 번은 읽힌다. `DQ4_UNIT_CACHE` 가 켜진 검사는 `DQ4_READSET_CACHE`·`DQ4_STATES_CACHE`·`DQ4_BUILD_CACHE` 가 그 단위 폴더를 가리킨다. 출발 상태 파일은 `_pool` 을 거쳐 같은 조각의 단위끼리 나눈다(`guards.share_states`).
- 퍼블릭 저장소의 `schedule` 워크플로는 저장소에 60일 동안 활동이 없으면 GitHub 가 끈다. 다시 켜려면 Actions 화면에서 켠다.
- 관문(`cache` false)은 위 「캐시를 쓰지 않는다」 를 지킨다: 장면·상태 캐시와 통과 기록을 쓰지 않고, 빌드 단계·사운드 캐시는 rom 잡만 쓰되 cold-build 와 바이트가 같아야 통과다. `release_check.py --ci-report` 는 연습이 아니면 이 대조(`build-digest-*` artifact)가 있고 같아야 받는다. 같은 실행 안에서 출하 롬을 한 번만 빌드해 조각과 가드가 나눠 쓰는 것(`DQ4_PREBUILT`)은 상태 캐시를 그 실행 안에서만 다시 쓰는 것과 같은 규칙이다.
- `rehearse=true` 는 모든 캐시를 쓴다. 조각 결과 JSON 에 `"cached": true` 가 붙고 요약 판정은 「연습 통과」, `release_check.py --ci-report` 는 `--rehearse` 와 함께가 아니면 받지 않는다.
- 무료 요금제의 계정 동시 잡은 20 이다. `guard-shards.yml` 의 Plan shards 가 조각 수를 `JOB_LIMIT`(20) − `FIXED_JOBS`(4) = 16 으로 자르고(넘으면 `::notice::`), 뒤 잡은 자른 수(`needs.build.outputs.count`)를 쓴다. 조각과 함께 도는 잡은 `mode: release` 의 cold-build·build-verify 둘뿐이라(build·rom 은 조각 앞에, report 는 뒤에 끝남) 16 이면 한 실행이 18 을 넘지 않는다. 관문·cache-warm 은 16, PR 은 `guards.PR_SHARDS_MAX` 8 로 한도를 함께 돌 때 나눠 쓴다(`test_shard_count_fits_the_job_limit`).
- 조각은 `tools/guardshard-times.json`(검사마다 지난 시간)으로 고르게 나눈다. `guards.py --record-times 보고서…` 로 고쳐 쓴다.
- 긴 검사는 `guards.toml` 에 `parts = n` 을 달아 하위 조각으로 나눈다. `--shard` 때 조각 수와 상관없이 하위 조각 n 개로 펼치고(`expand_parts`, 무게 = 검사 시간/n), 같은 검사의 하위 조각은 되도록 서로 다른 조각에 넣는다. 하위 조각 k 는 `DQ4_GUARD_PART=k/n` 으로 돈다. 조각이 n 보다 적어 한 조각에 여럿 들면 한 프로세스로 함께 돈다(`DQ4_GUARD_PART=1,3/4`, `guards.group_parts`). 통과 기록이 이미 있는 몫은 빼고 돈다. 결과 행은 하위 조각마다 `"part": [k, n]` 이 붙는다. `release_check.load_ci`·`ship.py` 가 `guards.merge_parts` 로 검사 하나로 합친다(하위 조각이 모두 있고 모두 통과해야 통과). 통과 기록 이름은 하위 조각마다 `<이름>~<k>of<n>` 이라 조각 수가 다른 실행끼리 맞는다. 로그 이름은 함께 돈 몫을 모두 적는다(`<이름>~1,3of4`).
- 검사 도구 쪽 인터페이스는 `sfc/dq4/tools/dq4shards.py` 의 `add_part_arg(ap)`(`--part k/n` 또는 `k1,k2/n`, 기본 `DQ4_GUARD_PART`, 읽은 뒤 환경에서 지움. 몫 여럿은 `dq4shards.Parts` 라 `f'{k}/{n}'` 이 `1,3/4`)와 `part_of(단위, part, key, weight)`(결정적 몫, 모으면 전체). 단위는 서로 상태를 주고받지 않는 장면이고, 몫에서는 판정도 그 몫 단위로 좁힌다. `parts` 가 달린 가드의 마지막 단계 도구는 `add_part_arg` 를 불러야 한다(`test_guards.test_parted_guards_run_tools_that_split`).
- 로컬에서 마무리: 조각 artifact 를 받은 폴더로 `release_check.py --ci-report DIR` 를 돌리면 guards 단계는 CI 결과(같은 커밋, 조각이 모두 있어야 함)를 쓰고 로컬 몫만 돈다.
- `tools/tests/test_release_gate_workflow.py` 가 지킨다: 관문은 `workflow_dispatch` 만(`pull_request`·`pull_request_target`·`schedule` 금지), 조각 워크플로는 `workflow_call` 만이고 부르는 곳은 관문·`cache-warm.yml`·`ci.yml` 뿐, `cache-warm.yml` 은 `schedule`·`workflow_dispatch` 만이고 정각이 아니며 main 에서만·`mode: release`·`cache: true`·조각 16 이하·시크릿은 이름으로·올리기 없음·평문 캐시는 데운 커밋 표시만·묶음 `release-gate-main`, 올리기 앞 검사 단계, 평문 캐시 경로(도구·통과 기록만), 롬 파생 폴더는 enc-cache·ship-cache 로만, ship-cache 단계 목록 = `SHIP_LABELS`, 단위 캐시 열쇠에 모드·조각 번호 없음·unit-cache 자리 수 = `guards.UNIT_SLOTS`·통과 기록 → 자리 목록 → 되살리기 차례, 관문은 `rehearse` 일 때만 장면·상태·통과 기록 캐시(빌드 단계 캐시는 늘 쓰고 cold-build 는 모든 캐시를 끔, build-verify·report 가 대조), 시크릿을 찍는 줄 없음. `tools/tests/test_pr_guards_workflow.py` 는 `ci.yml` 쪽을 지킨다: `pull_request_target`·`workflow_run`·`issue_comment`·`secrets: inherit` 없음, 시크릿을 쓰는 잡은 `pr-guards` 하나이고 조건은 「CI 몫 있음 그리고 (같은 저장소 브랜치 PR 또는 main push)」 글자 그대로, `mode: pr`·`cache: true`, `guard-plan` 이 보호 테스트를 계획보다 먼저, `ci-ok` 가 `pr-guards-result`·`required-checks` 를 기다림, `LOCAL_NEEDS` 정본은 `guard-shards.yml` 하나.

## 남은 것

- 커버리지가 기준에 못 미친다(로컬 77.1%, CI 와 같게 69.7%). 기준은 그대로 두고 빌드 경로 시험을 늘려 맞춘다. 그때까지 관문은 「커버리지 미달」 로 실패한다.
- 기능 표: 자동 검증 계획의 「배포 차단 위험」 목록(가게 거래, 전투 갈래, 여관·교회, 레벨업, 효과음, 저장 칸, 낮밤, 다른 에뮬)을 행으로, 층(L1 롬 바이트, L2 장면, L3 걷기, L4 시드)을 칸으로 하는 표다. 칸에 그 층의 검사 이름을 이어, 이번 실행에서 통과하면 ○ 로 채운다. 행 목록은 아직 정하지 않았다.
