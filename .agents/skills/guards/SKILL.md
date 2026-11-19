---
name: guards
description: 버그를 고치거나 동작을 개선했을 때, PR 을 올리기 전에. 고친 것이 다시 깨지지 않게 하는 가드(단위 테스트·실행 검사)를 넣고 트랙의 guards.toml 에 등록하는 법, PR 본문의 가드 결과 줄, CI required-checks.
---

# 회귀 가드

이 스킬이 GUARD-01, GUARD-02, GUARD-03 의 정본이다. 도구는 `tools/guards.py`, CI 잡은 `guard-plan`·`pr-guards`·`pr-guards-result`·`required-checks` 다. **실행 검사는 CI 가 돈다. 로컬은 `check_docs`·compileall·바꾼 모듈의 단위 테스트만**(ship 의 checks 단계). 로컬 에뮬레이터 실행은 수동 디버그와 분석 프로브용이다.

여러 세션이 같은 저장소를 고친다. 한 세션이 고친 것을 다른 세션이 모르고 되돌리지 않게, 고친 사람이 그 자리에 가드를 남긴다. 가드는 두 가지다.

| 가드 | 언제 | 누가 돌리나 |
| --- | --- | --- |
| 단위 테스트(`test_*.py`) | 롬 없이 확인할 수 있을 때(생성 코드의 바이트, 표, 파서) | CI `test` 잡이 PR 마다 |
| 실행 검사(`<트랙폴더>/guards.toml` 에 등록) | 롬·에뮬레이터가 있어야 할 때(걷기 검사, 프로브) | CI `pr-guards` 잡이 PR 마다 바뀐 파일로 걸린 것만(같은 저장소 브랜치). `needs` 에 `guard-shards.yml` 의 `LOCAL_NEEDS` 이름이 든 「로컬 몫」 만 PR 을 올리는 세션이 돌리고 본문에 결과 줄 |

## 절차 — 고치거나 개선했을 때

1. **가드를 정한다** — 고친 것이 다시 깨지면 무엇이 달라지는지 적고, 롬 없이 잡을 수 있으면 단위 테스트로 쓴다. 롬이 있어야 하면 실행 검사로 만든다(이미 있는 검사가 그 장면을 지나면 그 검사의 `paths` 에 파일을 더한다).
   완료: 고치기 전 코드로 돌리면 가드가 실패하고, 고친 코드로는 통과한다.
2. **실행 검사를 등록한다** — 자기 트랙 폴더의 `guards.toml` 에 항목을 더한다. `paths` 에는 이 검사가 지키는 동작을 바꿀 수 있는 파일을 glob 으로 적는다.
   ```toml
   [[check]]
   name = "dq4-compat-walk"
   why = "무엇이 다시 깨지지 않게 하나(원인 한 줄과 PR 번호)"
   paths = ["sfc/dq4/tools/dq4prologue.py"]
   run = "uv run --locked python sfc/dq4/tools/<검사>.py --rom <롬> --out work/<폴더>"
   needs = ["rom", "MESENCE"]
   ```
   `needs` 의 대문자 이름(`MESENCE`, `LIBDIR` 등)은 환경 변수로 본다. 검사가 읽는 환경 변수는 빠짐없이 적는다 — 다음 단계에서 설정 안 된 것을 짚어 준다.
   여러 검사가 함께 닿는 파일 묶음(롬 빌드, 걷기 드라이버 등)은 같은 파일의 `[groups]` 에 이름을 붙여 두고 검사에 `groups = ["ch1-build"]` 로 더한다. PR 에서 검사가 걸리는 때는 [GUARD-02](#guard-02--걸린-실행-검사는-돌리고-결과를-적는다) 에 있다. 묶음은 PR 에서 검사를 걸지 않고 배포 관문과 전체 모드에서만 쓰므로, 검사가 직접 지키는 파일(검사 스크립트, 그 검사만 쓰는 asm·Lua·자료 파일)은 묶음에 있어도 `paths` 에 적는다. 여러 검사가 PR 에서 함께 걸려야 하는 파일 묶음(예: 한 장의 사건 모듈 전부)은 `paths` 에 `"@묶음"` 으로 넣는다. 묶음 항목 앞에 `!` 를 붙이면 그 glob 을 빼고, 빼기가 든 묶음은 추적 파일로 풀리므로 glob 에 맞는 새 파일은 목록을 고치지 않아도 든다. **새 검사는 `guards.d/<검사 이름>.toml` 파일 하나에 `[[check]]` 하나로 더한다**(큰 `guards.toml` 끝에 덧붙이지 않는다: 여러 세션이 같은 자리를 고쳐 충돌이 난다. 기존 검사는 옮기지 않는다). 장·모듈별 검사는 트랙 폴더 `guards.d/*.toml` 조각에 둘 수 있다(같은 트랙으로 읽음. 조각에는 `[[check]]`·`[groups]` 만, 같은 이름 묶음은 합침). 검사를 조각으로 옮기기만 한 것은 run·needs 바뀜으로 치지 않는다. dq4 트랙은 `test_dq4guardpaths` 가 모든 실행 검사의 `paths`·묶음이, 명령의 스크립트(와 `unittest discover` 가 고르는 시험 파일)에서 전이 import·띄우는 Lua·asar 에 넣는 asm·`dq4build` 단계·글자 상수로 이름을 적은 자료 파일(`.toml`·`.json`·`.args`·`.patch`·`.tsv`)로 닿는 저장소 파일을 덮는지 본다. importlib, 변수로 만든 파일 이름, 폴더째 읽는 그림처럼 그 시험이 못 보는 길로 닿는 파일은 손으로 적는다(`dq4guardpaths.py` docstring). 빠진 것은 `uv run --locked python sfc/dq4/tools/dq4guardpaths.py` 가 찍는다.
   한 번 도는 데 5분(300초, `guardshard-times.json`)을 넘거나 장을 처음부터 끝까지 걷는 검사에는 `tier = "release"` 를 단다. PR 에서는 빠지고 main 에 머지된 뒤(`ci.yml` push)와 배포 관문이 돌린다. 이미 있는 검사의 등급만 옮길 때는 검사 항목을 고치지 않고 `guards.d/main-tier.toml` 의 `[tier] release = ["이름", …]` 에 이름을 더한다(`guards.toml` 은 [full]·[cache]·묶음처럼 여러 세션이 고쳐 충돌이 잦으니 새 검사는 자기 조각에 두는 것이 낫다).
   CI 에서 한 번에 10분을 넘는 검사는 장면 목록을 나눌 수 있게 도구에 `--part`(`dq4shards.add_part_arg`·`part_of`)를 넣고 `parts = n` 을 단다. CI 조각이 하위 조각 n 개를 러너마다 따로 돌리고 결과를 하나로 합친다(형식은 `sfc/dq4/docs/dq4-release-check-format.md`).
   완료: `uv run --locked python tools/guards.py` 가 문제 0개.
3. **걸리는 검사는 CI 가 돌린다** — `uv run --locked python tools/guards.py --base origin/main` 이 이 변경이 건드리는 실행 검사와 명령, 필요한 것(`needs`)을 찍는다. PR 을 열면 CI `guard-plan` 잡이 같은 판정(`--plan`)으로 CI 몫과 로컬 몫을 나누고, `pr-guards` 잡이 CI 몫을 조각으로 나눠 롬 묶음과 캐시를 써서 돌린다. `tools/ship.py` 가 PR 을 draft 로 열고, `ci-ok` 가 초록이면 본문 「## 가드」 절에 CI 결과 줄을 채우고 ready·auto-merge 한다. 사람이 「통과」 를 손으로 적지 않는다. 로컬 몫(지금은 MesenCE 가 필요한 검사)만 ship 이 로컬에서 돌려 결과 줄을 쓴다(아래 `--run`). 묶음으로만 맞는 검사와 `tier = "release"` 검사는 「main 머지 뒤·배포 관문에서」 로 따로 찍히며 PR 에서 돌지 않는다.
   - **전체 모드는 바뀐 파일로 정해진다.** 트랙 `guards.toml` 의 `[full]` `paths` 에 맞는 파일을 바꾸면 그 트랙은 전체 모드다. 그 트랙의 PR 등급 실행 검사가 `paths` 와 상관없이 모두 걸리고(release 등급은 main 머지 뒤가 돌림), 목록 맨 위에 「전체 모드: <걸린 파일>」 이 찍힌다. CI `guard-plan` 과 로컬 `--base` 는 같은 판정을 쓰므로 따로 고를 것이 없다. `[full]` 에는 바뀌면 거의 모든 장면이 달라지는 파일만 둔다. 빌드 단계의 차례, 모든 맵 들어가기가 지나는 훅, 에뮬레이터·코어와 그 설정, 장면 캐시, 공용 걷기 드라이버, 의존성 고정이 그렇다. 자주 바뀌는 파일을 넣으면 PR 마다 전체가 되므로 넣지 않는다(dq4 는 `sfc/dq4/guards.toml` 의 주석). 검사를 고르고 캐시하는 도구(`tools/guards.py`·`tools/guardtrace/`)는 롬을 바꾸지 않고 `tools/tests` 가 지키므로 `[full]` 에 두지 않는다. 대신 그 도구를 바꾼 PR 은 대표 가드 셋(롬을 빌드하는 검사 하나 + 짧은 장면 검사 둘)을 본문 `가드: 더함 이름, …` 줄(ship `--only 이름,…` 이 넣음)로 CI 에서 돌려 실제 실행 경로가 도는 것을 본다.
   - 자동 판정보다 넓게 돌리고 싶을 때만 본문에 `가드: 전체` 줄을 쓴다. 모든 트랙의 실행 검사가 걸린다. 몇 개만 더하려면 `가드: 더함 이름, 이름`. 두 줄 모두 넓히기만 하며, `[full]` 이 켠 전체 모드를 끄지 못한다.
   - CI 가드가 실패하면 ship 이 `SHIP: stopped watch …` 에 실패 가드 이름과 로그 링크를 찍는다. 원인을 고쳐 push 하면(ship 을 다시) 바뀐 입력의 가드만 다시 돈다(통과 기록 캐시). 고칠 것 없이 다시 볼 때만 `ship.py --rerun 이름` — 마지막 CI 실행의 실패한 잡만 다시 돈다.
   - 이 저장소는 포크 PR 을 받지 않는다. 포크에서 온 PR 은 `pr-guards` 가 돌지 않고 `ci-ok` 가 실패해 머지되지 않는다. 같은 저장소 브랜치로 올린다.
   - 지금은 `LOCAL_NEEDS`(`macos`)를 needs 에 단 검사가 없어 로컬 몫이 0개다. MesenCE 검사도 리눅스 러너에서 돈다. 새 검사에 그 이름을 달면 다시 로컬 몫이 생긴다.
   - **로컬 몫과 디버그만 로컬에서**, `origin/main` 을 합친 뒤 한 번, **`--run` 으로 포그라운드에서 돌린다**: `uv run --locked python tools/guards.py --base origin/main --run --only <로컬 몫>`(ship 이 대신 함. 모두 로컬로 보려면 ship `--local-guards`). 롬을 빌드하는 검사를 먼저 돌리고(서로 만드는 것을 건드리지 않는 빌드 검사끼리만 함께), 나머지는 `--parallel`(기본 `HEADLESS_SLOTS` 의 자리 수)개씩 함께 돌리고, 검사마다 `--timeout`(기본 1800초)을 넘기면 끈다. 끝나면 본문 결과 줄을 찍는다. 검사를 백그라운드로 띄우고 완료 알림을 기다리지 않는다 — 알림을 놓치면 세션이 멈춘다. 에이전트 도구의 명령 시간 제한이 짧으면 그 제한을 늘려 포그라운드로 둔다.
   - (로컬 실행) 에뮬레이터 프로세스는 머신 전체에서 `HEADLESS_SLOTS`(기본 CPU 수의 절반)개만 함께 돈다. 다른 세션이 자리를 다 쓰면 검사가 `[headless_slots] … 기다림` 을 찍고 기다리며, 기다린 시간도 `--timeout` 에 든다. [tools/README](../../../tools/README.md#headless_slots-헤드리스-에뮬레이터-자리)
   - 같은 입력(결과에 닿는 추적 파일 내용 — `.md`·`guards.toml`·`.agents/`·`.github/`·`.claude/`·`journal/`·단위 테스트는 뺀다. 다만 명령이 단위 테스트를 부르면(unittest·pytest, `test_*.py`·`tests/` 파일을 바로 돌림) `.md` 만 뺀다. `guards.toml` 맨 위에 `[cache]` `key = "paths"` 를 둔 트랙은 그 가운데 그 검사의 `paths`·묶음에 맞는 것, 트랙의 어느 검사도 `paths` 에 낱낱이 적지 않은 자료 파일(`.py`·`.lua`·`.asm` 밖), `uv.lock`·`pyproject.toml`·`.python-version` 만 본다. 그래서 화면 기준(`screens.toml`)처럼 한 검사만 적은 파일을 고치면 그 검사만 다시 돈다. paths 가 닿는 파일을 덮는다는 트랙 시험(dq4 는 `test_dq4guardpaths`)이 있어야 켠다 —, 명령, `needs` 에 나오는 환경 변수가 가리키는 파일 내용(64MB 넘는 파일은 크기·mtime)과 폴더 안 파일 목록(상대 경로·크기·mtime. 폴더 안 `cache/` 아래는 빌드가 같은 내용으로 다시 써 mtime 만 바뀌므로 내용으로 본다), `needs` 에 `MESENCE` 가 있으면 MesenCE 사용자 설정 파일(`tools/mesence_settings.py`. 못 찾으면 그 검사는 캐시를 쓰지 않음), `rom/` 원본, 명령이 읽는 `work/`·`rom/` 파일)으로 이미 통과한 검사는 캐시(원래 체크아웃 `work/cache/guards/`)로 건너뛴다. 실패는 캐시하지 않는다.
   - 입력이 달라도 롬을 빌드하는 검사(명령이 `&&` 로만 이어지고, 마지막 앞 단계가 `--out` 으로 무언가를 만들며, 셸 상태를 바꾸지 않고, 마지막 단계가 `uv run --locked python …` 인 것)는 빌드 단계를 먼저 돌린다. 만든 파일의 내용, `.py` 밖 입력, 추적 `.py` 이름 목록이 같고, 지난 통과 때 검사 단계가 **실행한 함수**의 코드(줄 번호 뺀 바이트코드 지문)와 데이터로 연 파일·목록을 본 폴더·`os.stat` 으로 본 있음과 크기, 에뮬레이터 같은 Python 밖 자식에게 인자로 넘긴 파일, 그 경로들이 거쳐 간 심볼릭 링크가 모두 같으면 검사 단계를 건너뛴다. 기록은 `tools/guardtrace/sitecustomize.py` 가 `sys.monitoring`·audit hook 으로 남긴다. 결과 줄은 「캐시: 빌드 결과와 검사 코드가 같아 …」. 롬이 그대로이고 검사가 부르지 않는 함수만 고친 PR 은 빌드만 돌고 끝난다. 검사 단계가 아는 자식(옵션이 `-u`·`-B` 뿐인 Python, 인자·환경 변수로 받은 파일을 입력으로 보는 `$MESENCE`) 밖의 것(셸·`os.system`·git·asar 등, `PYTHONPATH` 를 바꾼 환경)을 띄우거나 검사 단계 스크립트가 추적기를 싣지 않았으면 이 기록을 남기지 않는다.
   - 검사 안에서도 장면마다 캐시하는 것이 있다(dq4 [읽은 롬 바이트 캐시](../../../sfc/dq4/docs/dq4-readset-format.md): 롬이 바뀌어도 장면이 읽은 바이트가 같으면 다시 돌리지 않음). 배포 관문처럼 캐시 없이 전부 돌릴 때는 `--run --no-cache`.
   - `needs` 에는 검사가 읽는 환경 변수 이름을 그대로 적는다(설명문 안에 써도 캐시 키에 들어간다). 그래야 에뮬레이터·어셈블러를 바꾼 뒤 옛 결과로 건너뛰지 않는다.
   - 명령에 `<…>` 자리가 있는 검사(세이브스테이트를 고르는 검사 등)는 `--run` 이 돌리지 않으니 직접 돌린다.
   ```text
   - [x] dq4-door-open: 통과 (412초)                       ← 로컬 몫, ship 이 씀
   - [x] dq4-title-scene: 통과 (CI 99초, https://github.com/…/actions/runs/…)   ← CI 몫, ci-ok 초록 뒤 ship 이 씀
   ```
   완료: `ci-ok` 초록(그 안의 `pr-guards-result` 가 CI 몫, `required-checks` 가 로컬 몫 결과 줄 — `guards.py --base origin/main --pr-body <본문> --local-only` 문제 0개).

## 규칙

### GUARD-01 — 고친 것에는 가드를 남긴다

버그를 고치거나 동작을 개선한 PR 은 그것을 지키는 가드를 함께 넣는다. 롬 없이 되면 단위 테스트, 롬이 필요하면 트랙의 `guards.toml` 에 실행 검사를 등록한다. 가드를 만들 수 없으면 PR 본문에 이유를 적는다.

- 이유: 고친 사람만 아는 함정은 다음 세션이 모르고 다시 밟는다. 가드는 그 지식을 코드로 남긴다.
- `guards.toml` 은 트랙 폴더 안에 있어 그 트랙 소유다([TRACK-01](../tracks/SKILL.md#track-01--트랙과-소유-파일)). 다른 트랙의 검사가 내 파일을 `paths` 로 잡고 있으면 그 검사도 돌린다.

### GUARD-02 — 걸린 실행 검사는 돌리고 결과를 적는다

PR 이 어떤 실행 검사의 `paths` 에 바로 맞는 파일을 바꾸거나 `guards.toml` 에서 그 검사의 `run`·`needs` 를 바꾸면(새 검사 포함), 그 검사가 돌아 통과해야 머지한다. CI 몫은 CI `pr-guards` 잡이 돌리고 `pr-guards-result` 가 `ci-ok` 에 판정을 넘긴다. 로컬 몫(`needs` 에 `guard-shards.yml` `LOCAL_NEEDS` 의 이름이 든 것)은 돌린 세션이 본문에 `- [x] <이름>: 통과 …` 줄을 쓴다. 묶음(`groups`)으로만 맞는 검사와 `tier = "release"` 검사는 PR 에서 빠진다. release 등급은 main 에 머지된 뒤 `ci.yml` push 실행이 전부 돌리고(바뀐 파일로 걸린 PR 등급과 함께, 통과 기록 캐시를 씀), 배포 관문(`tools/release_check.py`)이 캐시 없이 모두 돌린다. 바뀐 파일이 트랙의 `[full]` `paths` 에 맞으면(절차 3) 전체 모드라 그 트랙의 실행 검사를 모두 돌려 결과 줄을 쓴다. 본문의 `가드: 전체` 줄은 그보다 넓힐 때만 쓴다. 로컬 몫이 그 변경과 상관없으면 `- [x] <이름>: 해당 없음 — <이유>` 로 쓴다. CI `required-checks` 는 줄이 요구되는 검사의 줄이 없거나, 체크되지 않았거나, `실패` 가 들었거나, 이유 없는 「해당 없음」 이면 실패한다.

- 이유: 에뮬레이터 검사를 로컬에서 돌리면 세션마다 수십 분이 들고 머신 부하로 서로 막았다. CI 는 같은 판정으로 바뀐 것만, 캐시를 써서 조각마다 함께 돌리고 결과가 실행 기록으로 남는다. 로컬 몫은 CI 에 그 도구가 없어서만 남은 것이고, `LOCAL_NEEDS` 가 비면 저절로 CI 로 간다.
- 캐시: PR 실행이 저장한 캐시는 그 PR 만 읽는다. 그래서 머지 뒤 main push 실행이 바뀐 범위의 같은 가드를 다시 돌려 main 에 캐시를 데우고, 다음 PR 은 그 캐시(빌드 단계·장면·통과 기록)를 읽는다.
- 시크릿: `pr-guards` 는 같은 저장소 브랜치 PR 과 main push 에서만 롬 묶음 시크릿을 받고, 같은 커밋의 워크플로 보호 테스트(`test_release_gate_workflow`·`test_pr_guards_workflow`)가 `guard-plan` 에서 먼저 통과해야 돈다. `pull_request_target` 은 쓰지 않는다. 워크플로·`tools/ci_*` 를 고친 PR 은 `guard-plan` 이 알림을 남기니 리뷰에서 그 파일을 본다.
- **main 단계**: PR 은 짧고 결정적인 가드(15분 안)만 돌리고, 긴 가드(release 등급)는 머지 뒤 main 에서 돈다. main 실행이 실패하면 `main-guard-issues` 잡이 가드마다 issue 하나(`[main 가드] <이름> 실패`, 이미 열려 있으면 댓글)를 열어 마지막으로 통과한 main 실행 뒤로 머지된 PR 과 연속 머지로 취소된 커밋을 적는다(`tools/main_guard_issue.py`). 열린 issue 는 그 가드를 고쳐 main 이 초록이 될 때 닫는다. **배포(IPS 빌드) 전 관문은 그대로 전부 돈다: main 실행이 빨가면 배포하지 않는다.**
- PR 에서 줄이는 이유: 빌드 파일 하나만 바꿔도 묶음으로 검사 40개 넘게 걸려 45분이 넘게 들었다. 그 변경이 직접 닿는 검사만 PR 에서 돌리고, 나머지는 배포 전에 한 번 크게 돌린다.
- 결과는 `통과`(뒤에는 괄호·대시나 줄 끝만, 예: `통과 (bsnes 27/27)`) 또는 `해당 없음 — <이유>` 둘뿐이다. 「통과하지 못함」 같은 글은 실패로 친다.
- 본문을 고쳐도 CI 는 다시 돌지 않는다(`edited` 를 받지 않음 — 받으면 CI 가드가 처음부터 다시 돈다). `required-checks` 와 `guard-plan` 은 본문을 API 로 읽으므로, 새 커밋 없이 본문을 고쳤으면 `required-checks` 잡만 다시 돌린다(ship 이 함). `가드: 전체`·`가드: 더함` 줄을 더한 것은 다음 push 의 CI 부터 반영된다.
- 바뀐 파일은 PR 의 base 와 head 커밋 사이로 고른다. PR 이 열린 뒤 main 에 들어온 남의 변경은 걸리지 않는다.

### GUARD-03 — 가드를 느슨하게 하지 않는다

가드가 실패하면 가드를 지우거나 `paths` 를 줄이지 않고 원인을 고친다([CI-02](../ci/SKILL.md#ci-02--실패는-원인을-고친다) 와 같다). 가드 자체가 틀렸으면 그 가드가 있는 트랙의 PR 로 고치고, 틀렸다는 근거를 본문에 적는다.

## 참고

- `tools/guards.py` 는 모든 `guards.toml` 의 형식(이름 중복, 모르는 키, `paths` 에 맞는 파일이 있는지)도 본다. 파일을 옮기거나 지우면 `paths` 를 함께 고친다.
- 트랙별 가드 목록: 각 트랙 폴더의 `guards.toml`(없으면 아직 등록한 실행 검사가 없다).
