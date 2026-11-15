---
name: ci
description: GitHub Actions 워크플로를 바꾸거나 CI 가 실패했을 때. 필수 체크 ci-ok, 문서 검사(tools/check_docs.py), 실패 대응 원칙.
---

# CI

이 스킬이 CI-01, CI-02 의 정본이다. 워크플로는 `.github/workflows/ci.yml` 하나다. 잡 목록은 워크플로 파일을 본다.

`pr-guards` 잡(같은 저장소 브랜치 PR·main push, 롬 묶음 시크릿)과 손으로 부르는 배포 관문(`release-gate.yml`) 밖에는 롬이 없는 곳에서 도는 검사만 있다. 롬이 있어야 하는 단위 테스트는 롬이 없으면 스스로 skip 하고, 디코더가 원작과 맞는지는 CI 가 아니라 실측([VERIFY-01](../analysis/SKILL.md#verify-01--실측으로-확인))으로 확인한다.

## 절차 — CI 가 실패했을 때

1. **실패한 잡과 로그를 본다** — `gh run view <run-id> --log-failed`.
   완료: 실패 원인을 한 문장으로 말할 수 있다.
2. **로컬에서 재현한다** — `uv sync --locked && uv run --locked python tools/check_docs.py && git ls-files -z '*.py' | xargs -0 uv run --locked python -m compileall -q`. Lua 를 고쳤으면 `git ls-files -z '*.lua' | xargs -0 -n1 luac -p`. 테스트가 실패했으면 그 트랙 폴더(`sfc/dq4/tools`, `sfc/dq5/tools/tests`)에서 `uv run --locked python -m unittest discover -p 'test_*.py'`. 롬이 있는 체크아웃에서는 CI 가 skip 하는 테스트까지 돌므로, CI 에서만 실패하면 롬 링크 없는 워크트리에서 재현한다. 실행 검사(가드)는 로컬에서 재현하지 않고 CI 실패 잡을 다시 돌린다(`ship.py --rerun 이름`). 로컬 에뮬레이터 실행은 원인을 찾는 수동 디버그일 때만 쓴다.
   완료: 재현되거나, 로컬에서는 통과한다.
3. **원인을 고치고 같은 PR 에 push 한다**(CI-02). 일지 순번 중복이면 [journal 절차 5](../journal/SKILL.md#절차--한-항목을-끝냈을-때)로 번호를 다시 매긴다.
   완료: 새 커밋의 `ci-ok` 가 초록.

## 규칙

### CI-01 — ci-ok

PR 은 `ci-ok` 가 초록일 때만 머지한다. `ci-ok` 는 모든 잡을 모아 하나라도 실패·취소·skip 이면 실패한다.

- 이 저장소는 포크 PR 을 받지 않는다. 사용자 소유 퍼블릭 저장소는 포크 자체를 끌 수 없어서, 포크에서 온 PR(`head.repo.full_name != github.repository`)이면 `ci-ok` 가 「이 저장소는 포크 PR 을 받지 않는다」 로 실패해 머지되지 않는다. 자동 닫기는 `pull_request_target` 이 필요해 하지 않는다.
- 새 잡을 추가하면 `ci-ok` 의 `needs` 에 넣는다. 빠지면 그 잡이 실패해도 머지된다.
- 자동 머지는 체크가 통과하는 순간 일어난다. PR 에 커밋을 더 올릴 계획이면 다 올린 뒤에 `gh pr merge --auto --merge` 를 건다.

### CI-02 — 실패는 원인을 고친다

검사가 실패하면 기준(`tools/check_docs.py` 의 규칙)을 낮추지 않고 원인을 고친다. 기준을 바꾸는 것은 규칙 자체가 틀렸다는 근거가 있을 때뿐이고, 그 근거를 PR 에 적는다.

## 참고

- **`docs` 잡**(`tools/check_docs.py`): 일지 이름 형식, 제목과 파일 이름의 날짜·순번 일치, 같은 트랙 안의 순번 중복, 일지 목록(트랙 폴더 `<플랫폼>/<게임>/README.md`, 옮기기 전 트랙은 저장소 README) 누락·순서, 문서 안 상대 링크 대상, 개인 경로, 추적 텍스트 파일의 rebase·merge 충돌 표시를 검사한다.
- **`syntax` 잡**: Lua 문법(`luac`)과 Python 컴파일을 추적 파일 전체(`git ls-files`)로 본다.
- **`test` 잡**: 트랙마다 한 잡으로 unittest 를 돌린다. 오래 걸리는 dq4·dq5 는 두 조각(`test (dq4 1/2)`·`test (dq4 2/2)` 등)으로 나눠 함께 돈다. 조각은 `tools/unitshard.py` 가 `tools/unitshard-times.json` 의 파일별 시간으로 고르게 나누며, 모으면 그 폴더의 `test_*.py` 전부다. 테스트 파일이 크게 늘거나 느려져 조각이 기울면 `uv run --locked python tools/unitshard.py --record <폴더>` 로 시간을 고친다(롬 링크 없는 워크트리에서). 롬을 읽는 테스트는 `skipUnless(<롬>.is_file(), ...)` 로 감싸야 한다. 가드가 빠지면 로컬에서는 통과해도 CI 에서 `FileNotFoundError` 로 실패한다. 테스트 파일을 새 폴더에 두면 matrix 에도 넣는다.
- **`guard-plan`·`pr-guards`·`pr-guards-result` 잡**: PR 이 걸리게 한 실행 검사(자기 `paths` 에 바로 맞는 pr 등급 검사. 바뀐 파일이 트랙 `[full]` `paths` 에 맞으면 그 트랙 전부, 본문 `가드: 전체` 면 모든 트랙, `가드: 더함 이름` 은 더함) 가운데 CI 몫을 `guard-shards.yml`(`mode: pr`, 캐시 켬)로 돌리고 판정을 하나로 모은다([GUARD-02](../guards/SKILL.md#guard-02--걸린-실행-검사는-돌리고-결과를-적는다)). main push 에서도 같은 판정으로 돌아 다음 PR 이 읽을 캐시를 데운다. 시크릿은 같은 저장소 브랜치 PR·main push 의 `pr-guards` 만, 보호 테스트가 먼저(`tools/tests/test_pr_guards_workflow.py`).
- **`required-checks` 잡**(`tools/guards.py`): 모든 `guards.toml` 의 형식을 보고, PR 이면 CI 가 돌리지 않는 걸린 검사(로컬 몫)마다 본문에 결과 줄이 있는지 본다. 본문은 API 로 읽어 이 잡만 다시 돌려도 고친 본문을 본다. 본문 고침(`edited`)으로는 CI 가 돌지 않는다. 공유 도구 테스트는 `test (common)`(`tools/tests`).
- **보안 점검**: `zizmor` 가 워크플로를, `actionlint` 가 문법을 본다. checkout 에는 `persist-credentials: false`(이 워크플로는 push 하지 않는다). 액션은 커밋 SHA 로 고정한다([DEP-01](../dependencies/SKILL.md#dep-01--7일-쿨다운)).
