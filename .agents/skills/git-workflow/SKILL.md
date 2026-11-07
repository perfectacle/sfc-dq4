---
name: git-workflow
description: 분석·코드·문서를 바꾸기 전에(워크트리·브랜치), 커밋할 때, PR 을 올릴 때, 머지 후 정리할 때. 워크트리와 롬 링크, 브랜치 이름, 커밋 메시지, PR, 워크트리 삭제.
---

# git

이 스킬이 GIT-01, GIT-02 의 정본이다.

## 절차

1. **최신 main 에서 워크트리를 판다** — 기존 체크아웃에서 `git switch` 하지 않는다. 다른 세션이 같은 체크아웃에서 일하고 있을 수 있다. [GIT-02](#git-02--작업마다-워크트리)
   ```sh
   MAIN=$(git worktree list --porcelain | sed -n '1s/^worktree //p')
   git fetch origin main
   git worktree add -b <종류>/<트랙>-<짧은-설명> "$MAIN-<트랙>-<짧은-설명>" origin/main
   cd "$MAIN-<트랙>-<짧은-설명>"
   ln -s "$MAIN/rom" rom
   mkdir -p work && ln -s "$MAIN/work/state" work/state
   uv sync --locked
   ```
   브랜치 종류는 `feat`(새 분석·도구)·`fix`·`docs`·`refactor`·`chore`. 트랙이 없는 작업(에이전트 문서, CI)은 `<트랙>-` 을 뺀다. 롬과 세이브스테이트는 원래 체크아웃의 것을 링크해 함께 쓰고(읽기만), 실험 출력은 이 워크트리의 `work/` 에만 쓴다.
   완료: `git worktree list` 에 새 워크트리가 있고, 그 안에서 `git log -1 origin/main` 이 HEAD 와 같고, `ls rom/` 에 롬이 보인다.
2. **커밋한다** — 작성자는 저장소 주인(`perfectacle <perfectacle@gmail.com>`)이고 커밋은 그 계정에 등록된 키로 서명한다. 메시지는 Conventional Commits 형식(`feat: …`)에 한국어로, 첫 줄은 무엇을 확인·바꿨는지, 본문은 근거(실측 결과)와 이전에 틀렸던 것을 쓴다.
   완료: `git log -1 --format='%an <%ae> %G?'` 가 주인 정보와 `G` 다.
3. **`tools/ship.py` 한 줄로 PR 을 마무리한다** — 본문 파일(무엇을 확인했는지, 어떻게 검증했는지(실측 숫자), 다른 트랙이 알아야 할 것)을 쓰고 워크트리 안에서 돌린다. 포그라운드에서 머지까지 스스로 기다리므로 에이전트 도구의 명령 시간 제한을 넉넉히(가드가 걸리면 수십 분) 준다.
   ```sh
   uv run --locked python tools/ship.py --title "<PR 제목>" --body <본문 파일>
   ```
   차례로 rebase(충돌이면 rebase 를 그대로 두고 멈춤) → 일지 순번([JOURNAL-01](../journal/SKILL.md#journal-01--일지-이름과-순번)) → 로컬 검사([ci](../ci/SKILL.md) 의 `check_docs`·compileall·luac, 바뀐 파일에 닿는 단위 테스트) → 실행 검사([GUARD-02](../guards/SKILL.md#guard-02--걸린-실행-검사는-돌리고-결과를-적는다), `guards.py --base origin/main --run`) → 본문 「## 가드」 절과 🤖 줄 → push(원격에 같은 이름이 남의 것이면 `<브랜치>-2`) → PR 만들기·`gh pr merge --auto --merge` → 30초마다 지켜보기(충돌이면 처음부터 다시, CI 실패면 실패 잡 로그 끝을 찍고 멈춤) → 머지되면 워크트리·브랜치 정리와 원래 체크아웃 `pull --ff-only`. 마지막 줄이 `SHIP: merged #N` 또는 `SHIP: stopped <단계> <이유>` 다. 멈추면 이유를 고치고 같은 명령을 다시 돌린다. 옵션(`--dry-run`, `--no-watch`, `--auto-lists`, `--rerun`, `--only`, `--skip-guards`)은 [tools/README](../../../tools/README.md#shippy-pr-마무리-한-줄).
   push 와 `gh` 는 저장소 주인 계정으로 한다. ship 은 `GH_TOKEN` 이 없으면 `gh auth token -u perfectacle` 을 명령마다 넘긴다. 손으로 `gh` 를 부를 때도 `gh auth switch` 로 전역 계정을 바꾸지 않는다. 에이전트 권한 설정이 머지를 막으면 우회하지 말고 사용자가 실행할 명령을 넘긴다.
   완료: 마지막 줄이 `SHIP: merged #N` 이고 `git worktree list` 에 그 워크트리가 없다. `SHIP: stopped cleanup …`(워크트리에 커밋 안 된 변경)이면 `--force` 를 쓰지 않고 무엇이 남았는지 사용자에게 알린다.
4. **1장 IPS 를 다시 만든다** — 원래 체크아웃이 최신 main 이 된 뒤 `check` 가 뒤처졌다고 하면 다시 만들어 비공개 에셋 저장소에 넣는다. 빌드 입력(`dq4build.py` 에서 닿는 도구 파일, `uv.lock`)을 건드리지 않은 PR 이면 `check` 가 통과해 아무것도 하지 않는다.
   ```sh
   cd "$MAIN"
   uv run --locked python sfc/dq4/tools/dq4publish.py check || \
     GH_TOKEN=$(gh auth token -u perfectacle) uv run --locked python sfc/dq4/tools/dq4publish.py build --commit
   ```
   `DQ4_ASSETS`(에셋 저장소 체크아웃), `ASAR`, `DQ4_GALMURI` 가 필요하다. 빌드가 실패하면 IPS 는 그대로 두고 원인을 사용자에게 알린다.
   완료: `check` 가 「IPS 가 최신」.

## 규칙

### GIT-01 — 브랜치와 PR

분석 결과·코드·문서 모든 변경은 브랜치에서 하고 PR 로 main 에 넣는다. main 에 직접 커밋·push 하지 않는다.

- 이유: 여러 세션이 동시에 main 을 고치면 push 가 서로 거부되거나 rebase 중에 상대 결과가 지워진다. PR 이면 `ci-ok`(일지 순번 중복, 개인 경로, 문법)를 거쳐 들어간다.
- 커밋 메시지에 `[skip ci]` 류를 쓰지 않는다.
- 커밋 메시지·코드 주석에는 이 대화나 세션 맥락을 적지 않는다. 저장소만 보는 사람이 이해할 수 있는 근거만 쓴다.

### GIT-02 — 작업마다 워크트리

작업 하나(todo 항목 하나)는 최신 `origin/main` 에서 판 워크트리 하나에서 한다. 원래 체크아웃은 `rom/`·`work/state/` 를 두는 곳으로만 쓰고, 그 안에서 브랜치를 바꾸거나 파일을 고치지 않는다. 작업이 끝나면(머지, 또는 PR 을 닫음) 그 워크트리와 로컬 브랜치를 지운다.

- 이유: 한 체크아웃을 나눠 쓰면 서로의 변경이 섞이거나 브랜치가 바뀌어 작업이 사라진다. 다 쓴 워크트리를 남기면 어느 것이 살아 있는 작업인지 알 수 없다.
- 예외: 지우려는 워크트리에 커밋 안 된 변경이 남아 있으면 지우지 않고 사용자에게 알린다.
- 세이브스테이트를 새로 만들면(`mkstate.lua`) 원래 체크아웃의 `work/state/` 에 새 이름으로 둔다. 다른 세션이 쓰는 기존 파일을 덮어쓰지 않는다.

## 부록 — 손으로 마무리할 때

`tools/ship.py` 를 쓸 수 없을 때(도구 자체를 고치는 중 등)의 차례다. ship 이 하는 일과 같다.

1. `git fetch origin main && git rebase origin/main`. 충돌은 풀되 다른 트랙의 줄은 main 쪽을 그대로 둔다([TRACK-02](../tracks/SKILL.md#track-02--공유-파일)). 일지가 있으면 [journal](../journal/SKILL.md) 의 순번 절차로 번호를 맞춘다.
2. `uv run --locked python tools/check_docs.py`, `git ls-files -z '*.py' | xargs -0 uv run --locked python -m compileall -q`, 바뀐 트랙의 단위 테스트.
3. `uv run --locked python tools/guards.py --base origin/main --run` 이 찍는 결과 줄을 본문에 넣고, 같은 명령에 `--pr-body <본문 파일>` 을 더해 문제 0개.
4. `GH_TOKEN=$(gh auth token -u perfectacle) gh pr create --base main` 후 `gh pr merge --auto --merge`. 자동 머지가 막혀 있으면 `ci-ok` 가 초록이 된 뒤 `gh pr merge --merge`.
5. `MERGED` 까지 지켜보고, 실패하면 [ci](../ci/SKILL.md) 절차로 고친다.
6. 원래 체크아웃으로 나와서 정리한다. 실험 출력(`work/`)에 남길 것이 있으면 먼저 원래 체크아웃의 `work/` 로 옮긴다.
   ```sh
   cd "$MAIN"
   gh pr view <브랜치> --json state -q .state   # MERGED 또는 CLOSED 인지 확인
   git worktree remove "$MAIN-<트랙>-<짧은-설명>"
   git branch -D <브랜치>
   git push origin --delete <브랜치> 2>/dev/null || true
   git worktree prune
   git pull --ff-only   # 원래 체크아웃을 최신으로(다른 세션이 쓰는 중이 아닐 때만)
   ```
   `git worktree remove` 가 커밋 안 된 변경 때문에 거부하면 `--force` 를 쓰지 않는다. 롬·세이브스테이트 링크와 `work/` 는 추적되지 않는 파일이라 지울 때 함께 사라진다(링크 대상은 남는다).
