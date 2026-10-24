---
name: ci
description: GitHub Actions 워크플로를 바꾸거나 CI 가 실패했을 때. 필수 체크 ci-ok, 문서 검사(tools/check_docs.py), 실패 대응 원칙.
---

# CI

이 스킬이 CI-01, CI-02 의 정본이다. 워크플로는 `.github/workflows/ci.yml` 하나다. 잡 목록은 워크플로 파일을 본다.

롬이 없는 곳에서 도는 검사만 있다. 디코더가 맞는지는 CI 가 아니라 실측([VERIFY-01](../analysis/SKILL.md#verify-01--실측으로-확인))으로 확인한다.

## 절차 — CI 가 실패했을 때

1. **실패한 잡과 로그를 본다** — `gh run view <run-id> --log-failed`.
   완료: 실패 원인을 한 문장으로 말할 수 있다.
2. **로컬에서 재현한다** — `uv sync --locked && uv run --locked python tools/check_docs.py && git ls-files -z '*.py' | xargs -0 uv run --locked python -m compileall -q`. Lua 를 고쳤으면 `git ls-files -z '*.lua' | xargs -0 -n1 luac -p`.
   완료: 재현되거나, 로컬에서는 통과한다.
3. **원인을 고치고 같은 PR 에 push 한다**(CI-02). 일지 순번 중복이면 [journal 절차 5](../journal/SKILL.md#절차--한-항목을-끝냈을-때)로 번호를 다시 매긴다.
   완료: 새 커밋의 `ci-ok` 가 초록.

## 규칙

### CI-01 — ci-ok

PR 은 `ci-ok` 가 초록일 때만 머지한다. `ci-ok` 는 모든 잡을 모아 하나라도 실패·취소·skip 이면 실패한다.

- 새 잡을 추가하면 `ci-ok` 의 `needs` 에 넣는다. 빠지면 그 잡이 실패해도 머지된다.
- 자동 머지는 체크가 통과하는 순간 일어난다. PR 에 커밋을 더 올릴 계획이면 다 올린 뒤에 `gh pr merge --auto --merge` 를 건다.

### CI-02 — 실패는 원인을 고친다

검사가 실패하면 기준(`tools/check_docs.py` 의 규칙)을 낮추지 않고 원인을 고친다. 기준을 바꾸는 것은 규칙 자체가 틀렸다는 근거가 있을 때뿐이고, 그 근거를 PR 에 적는다.

## 참고

- **`docs` 잡**(`tools/check_docs.py`): 일지 이름 형식, 제목과 파일 이름의 날짜·순번 일치, 같은 트랙 안의 순번 중복, 일지 목록(트랙 폴더 `<플랫폼>/<게임>/README.md`, 옮기기 전 트랙은 저장소 README) 누락·순서, 문서 안 상대 링크 대상, 개인 경로, 추적 텍스트 파일의 rebase·merge 충돌 표시를 검사한다. Lua 문법(`luac`)과 Python 컴파일은 추적 파일 전체(`git ls-files`)를 본다.
- **보안 점검**: `zizmor` 가 워크플로를, `actionlint` 가 문법을 본다. checkout 에는 `persist-credentials: false`(이 워크플로는 push 하지 않는다). 액션은 커밋 SHA 로 고정한다([DEP-01](../dependencies/SKILL.md#dep-01--7일-쿨다운)).
