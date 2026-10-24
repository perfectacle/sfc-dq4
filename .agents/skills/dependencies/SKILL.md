---
name: dependencies
description: Python 의존성·Python·uv·kr-patch-toolkit·GitHub Actions 버전을 추가하거나 올릴 때. 7일 쿨다운, uv.lock, 툴킷 태그 고정.
---

# 의존성

이 스킬이 DEP-01, DEP-02, DEP-03 의 정본이다.

## 절차 — 의존성 추가·변경

1. **추가한다** — `uv add <pkg>`. `pyproject.toml` 의 `exclude-newer` 가 7일 안 된 버전을 알아서 건너뛴다.
   완료: `pyproject.toml` 과 `uv.lock` 이 함께 바뀌었다.
2. **검증한다** — `uv sync --locked` 후 영향받는 도구를 다시 돌려, 이전과 같은 결과가 나오는지 본다(예: `tools/dq5map.py --compare`, `tools/dq5figures.py` 가 만든 그림이 바이트까지 같은지).
   완료: 출력이 같거나, 달라진 이유를 PR 에 적었다.

## 절차 — 툴킷 올리기

1. [kr-patch-toolkit 릴리스](https://github.com/perfectacle/kr-patch-toolkit/releases)의 CHANGELOG 에서 바뀐 명령·모듈 이름을 확인한다(예: 0.4.0 에서 `kr_patch.snes` → `kr_patch.sfc`, `krpatch snes` → `krpatch sfc`).
2. `pyproject.toml` 의 `@vX.Y.Z` 를 바꾸고 `uv lock`.
3. 코드·문서에서 옛 이름을 모두 고친다: `README.md` 의 버전 줄과 링크, `tools/README.md`, `tools/*.py` 의 import.
4. 위 「검증한다」를 돌린다. 출력이 바뀌면 툴킷 쪽 변경 때문인지 확인하고 PR 에 적는다.
   완료: `git grep -n 'v0\.'` 에 옛 버전이 남지 않았다.

## 규칙

### DEP-01 — 7일 쿨다운

릴리스된 지 7일이 지난 버전만 쓴다(`[tool.uv] exclude-newer = "7 days"`). GitHub Actions 도 같은 기준이고, 액션은 커밋 SHA 로 고정하고 `# vX.Y.Z` 주석을 단다.

- 이유: 공급망 공격은 대개 배포 직후 며칠 안에 발견·회수된다.
- 예외: 보안 수정. 근거(advisory 링크)를 PR 에 적는다.
- 같은 사람이 만든 툴킷은 git 태그로 고정하므로 쿨다운 대상이 아니다.

### DEP-02 — lockfile

`pyproject.toml` 을 바꾸면 `uv.lock` 도 같이 바뀌어야 하고 `uv sync --locked` 가 통과해야 한다. 충돌이 나면 main 의 lock 을 가져와(`git checkout origin/main -- uv.lock`) `uv lock` 으로 다시 만든다. 손으로 고치지 않는다.

### DEP-03 — 툴킷은 릴리스 태그로

kr-patch-toolkit 은 `git+https://…@vX.Y.Z` 릴리스 태그로만 고정한다. 브랜치나 로컬 경로로 바꾸지 않는다.

- 이유: 분석 결과와 나중의 패치 빌드가 툴킷 버전에 따라 달라지면 안 된다. 태그는 옮기지 않으므로 같은 태그면 같은 도구다.
- 툴킷에 기능이 필요하면 툴킷 저장소에 PR 을 내고 릴리스된 뒤에 올린다. 이 저장소에만 필요한 게임별 코드는 `tools/` 에 둔다(툴킷은 게임 무관이다).
