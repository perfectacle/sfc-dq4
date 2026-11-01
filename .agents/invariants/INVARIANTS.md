# 불변식 카탈로그

이 저장소가 지키는 규칙의 목록이다. 이 파일에는 규칙의 요지와 **소유자**(규칙 본문이 있는 스킬의 절)만 있다. 본문·이유·예외는 소유자에서 읽는다. 규칙을 바꿀 때는 소유자 한 곳만 고치고, 이 표의 요지가 달라졌으면 이 줄도 고친다.

## 분석 — 결과를 믿을 수 있게

| ID        | 요지                                                                 | 소유자                                                                          |
| --------- | -------------------------------------------------------------------- | ------------------------------------------------------------------------------- |
| ROM-01    | 롬·덤프·세이브스테이트를 커밋하지 않는다. 롬은 사용자가 준비한다    | [analysis §ROM-01](../skills/analysis/SKILL.md#rom-01--롬-데이터-금지)          |
| ORIG-01   | 다른 팬 해킹의 데이터·그래픽을 쓰지 않는다. 아이디어만 참고(NDS DQ4 한글패치는 참고 허락) | [analysis §ORIG-01](../skills/analysis/SKILL.md#orig-01--남의-데이터-금지)      |
| VERIFY-01 | 사실로 적는 것은 실측으로 확인한 것뿐. 나머지는 「남은 것」         | [analysis §VERIFY-01](../skills/analysis/SKILL.md#verify-01--실측으로-확인)     |
| COMPAT-01 | 뱅크 `40` 이상 네이티브 코드는 열린 버스 프로브로 확인한 BRK 만(트랙의 BRK 목록) | [analysis §COMPAT-01](../skills/analysis/SKILL.md#compat-01--높은-뱅크-코드는-확인한-brk-만) |
| EMU-01    | 분석·문서의 에뮬레이터는 MesenCE(NDS 는 desmume libretro)           | [analysis §EMU-01](../skills/analysis/SKILL.md#emu-01--에뮬레이터는-mesence)    |

## 동시 작업 — 세션끼리 부딪히지 않게

| ID       | 요지                                                                  | 소유자                                                                       |
| -------- | --------------------------------------------------------------------- | ---------------------------------------------------------------------------- |
| TRACK-01 | 세션은 트랙을 정하고 그 트랙의 소유 파일만 고친다. 트랙마다 자기 `<플랫폼>/<게임>/` 폴더에 살고, 공유 파일에는 트랙마다 가리키는 한 줄만 둔다 | [tracks §TRACK-01](../skills/tracks/SKILL.md#track-01--트랙과-소유-파일)     |
| TRACK-02 | 공유 파일은 자기 트랙 몫의 줄·절만, 공유 도구는 새 파일·옵션으로 넓힌다 | [tracks §TRACK-02](../skills/tracks/SKILL.md#track-02--공유-파일)            |
| GIT-01   | 모든 변경은 브랜치 → PR. main 에 직접 push 하지 않는다                | [git-workflow §GIT-01](../skills/git-workflow/SKILL.md#git-01--브랜치와-pr)  |
| GIT-02   | 작업마다 최신 `origin/main` 에서 워크트리, 롬은 링크, 머지 후 지운다  | [git-workflow §GIT-02](../skills/git-workflow/SKILL.md#git-02--작업마다-워크트리) |
| CI-01    | `ci-ok` 가 초록인 PR 만 머지                                          | [ci §CI-01](../skills/ci/SKILL.md#ci-01--ci-ok)                              |
| CI-02    | 실패하면 기준을 낮추지 말고 원인을 고친다                             | [ci §CI-02](../skills/ci/SKILL.md#ci-02--실패는-원인을-고친다)               |

## 회귀 — 고친 것이 다시 깨지지 않게

| ID       | 요지                                                                  | 소유자                                                                       |
| -------- | --------------------------------------------------------------------- | ---------------------------------------------------------------------------- |
| GUARD-01 | 고치거나 개선한 PR 은 가드를 함께 넣는다. 롬 없이 되면 단위 테스트, 롬이 필요하면 트랙의 `guards.toml` 에 실행 검사 등록 | [guards §GUARD-01](../skills/guards/SKILL.md#guard-01--고친-것에는-가드를-남긴다) |
| GUARD-02 | `paths` 에 걸린 실행 검사는 돌리고 PR 본문에 결과 줄. CI `required-checks` 가 본다 | [guards §GUARD-02](../skills/guards/SKILL.md#guard-02--걸린-실행-검사는-돌리고-결과를-적는다) |
| GUARD-03 | 가드가 실패하면 가드를 느슨하게 하지 말고 원인을 고친다               | [guards §GUARD-03](../skills/guards/SKILL.md#guard-03--가드를-느슨하게-하지-않는다) |

## 문서

| ID         | 요지                                                                  | 소유자                                                                          |
| ---------- | --------------------------------------------------------------------- | ------------------------------------------------------------------------------- |
| JOURNAL-01 | 일지는 `<플랫폼>/<게임>/journal/YYYY-MM-DD-NN-<주제>.md`(옮기기 전 트랙은 `docs/journal/<트랙>/`), 순번은 트랙마다 PR 직전 `origin/main` 기준 | [journal §JOURNAL-01](../skills/journal/SKILL.md#journal-01--일지-이름과-순번) |
| JOURNAL-02 | 일지는 한 항목, 한 순서대로·틀렸던 것들·남은 것                       | [journal §JOURNAL-02](../skills/journal/SKILL.md#journal-02--일지-구성)        |
| DOC-01     | 개인 경로를 쓰지 않고, 외부 자료는 링크                               | [journal §DOC-01](../skills/journal/SKILL.md#doc-01--개인-경로-금지)           |
| FIG-01     | 그림은 WebP, 트랙의 `<트랙>figures.py` 가 롬에서 다시 만든다          | [journal §FIG-01](../skills/journal/SKILL.md#fig-01--그림)                     |
| COPY-01    | 한국어 문서는 합니다체, 번역투 없이, 용어집을 따른다                  | [korean-copy](../skills/korean-copy/SKILL.md)                                  |

## 스프라이트

| ID        | 요지                                                                 | 소유자                                                                          |
| --------- | -------------------------------------------------------------------- | ------------------------------------------------------------------------------- |
| SPRITE-01 | 원작(DQ5) 인물을 덤프해 잰 격자 규칙 안에서 직접 그린다. 생성 이미지 축소 금지 | [sprites §SPRITE-01](../skills/sprites/SKILL.md#sprite-01--원작-실측-격자-안에서-그린다) |
| SPRITE-02 | 정면 한 장을 원작 옆에서 확인받은 뒤 측면·보행·다른 인물로 넓힌다    | [sprites §SPRITE-02](../skills/sprites/SKILL.md#sprite-02--정면-한-장을-원작-옆에서-확인한-뒤-넓힌다) |

## 의존성

| ID     | 요지                                                     | 소유자                                                                       |
| ------ | -------------------------------------------------------- | ---------------------------------------------------------------------------- |
| DEP-01 | 릴리스된 지 7일 지난 버전만(보안 수정 예외), 액션은 SHA  | [dependencies §DEP-01](../skills/dependencies/SKILL.md#dep-01--7일-쿨다운)   |
| DEP-02 | `pyproject.toml` 과 `uv.lock` 이 함께, `uv sync --locked` 통과 | [dependencies §DEP-02](../skills/dependencies/SKILL.md#dep-02--lockfile) |
| DEP-03 | kr-patch-toolkit 은 릴리스 태그로만 고정                 | [dependencies §DEP-03](../skills/dependencies/SKILL.md#dep-03--툴킷은-릴리스-태그로) |
