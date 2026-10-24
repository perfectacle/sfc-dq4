# 에이전트 진입 문서

이 저장소는 FC판 「드래곤 퀘스트 IV」(일본판)를 SFC 「드래곤 퀘스트 V」(일본판) 엔진 위에 옮기는 한글 해킹롬 sfc-dq4 의 소스다. 결과물은 실제 SFC 롬에 덧대는 IPS 패치이고, 지금은 두 원작의 데이터 형식을 분석하는 단계다. 분석 결과는 형식 문서와 해킹 일지(블로그 분석 노트의 원고)로 남긴다. 이 문서는 모든 코딩 에이전트(Claude Code, Codex, Cursor 등)가 처음 읽는 곳이다. 규칙의 정본은 `.agents/` 에 한 벌만 있고, 여기에는 요약과 "무엇을 하려면 어디를 읽나" 만 있다.

도구별 경로는 정본을 가리킨다: `CLAUDE.md` 는 이 파일을 import 하고, `.claude/skills` 는 `.agents/skills` 의 심볼릭 링크다. 스킬을 고칠 때는 `.agents/skills/` 실경로를 쓴다 — 심볼릭 링크 너머 경로는 `git add` 가 거부한다.

## 작업 트랙

여러 에이전트 세션이 동시에 일한다. 세션은 시작할 때 자기 트랙을 정하고, 그 트랙이 소유한 파일만 고친다. [TRACK-01](.agents/skills/tracks/SKILL.md#track-01--트랙과-소유-파일)

| 트랙  | 하는 일                                     | 소유 파일(접두어)                                              |
| ----- | ------------------------------------------- | -------------------------------------------------------------- |
| `dq5` | SFC DQ5 엔진(맵·필드·인물·스크립트) 분석    | `docs/dq5-*`, `tools/dq5*.py`, `docs/journal/dq5/`, 그림의 `dq5-*` |
| `dq4` | FC DQ4 원작 데이터(맵·대사·몬스터 등) 분석 | `docs/dq4-*`, `tools/dq4*`, `docs/journal/dq4/`, 그림의 `dq4-*`     |

공유 파일(`README.md`, `docs/todo.md`, `docs/references.md`, `tools/README.md`, `tools/lua/`, `tools/listing.py`)은 자기 트랙 몫의 줄·절만 고친다. 목록·표·순번은 트랙마다 나눠 두어, 두 트랙이 동시에 PR 을 올려도 충돌하지 않게 한다.

## 절대 규칙

어떤 도구를 쓰든 지킨다. 각 줄의 링크가 정본이다.

- **롬·덤프·세이브스테이트를 커밋하지 않는다** — 저작권 데이터다. 롬은 사용자가 직접 준비해 `rom/` 에 둔다. [ROM-01](.agents/skills/analysis/SKILL.md#rom-01--롬-데이터-금지)
- **다른 팬 해킹의 데이터를 쓰지 않는다** — 아이디어만 참고하고 그래픽은 직접 그린다. [ORIG-01](.agents/skills/analysis/SKILL.md#orig-01--남의-데이터-금지)
- **가설은 실측으로 확인한 뒤에 사실로 적는다** — 확인 못 한 것은 「남은 것」으로 남긴다. [VERIFY-01](.agents/skills/analysis/SKILL.md#verify-01--실측으로-확인)
- **문서에 개인 경로를 쓰지 않는다** — 환경 변수와 저장소 상대 경로만. [DOC-01](.agents/skills/journal/SKILL.md#doc-01--개인-경로-금지)
- **일지 순번은 트랙마다 PR 직전 `origin/main` 기준으로 매긴다** — 같은 트랙의 세션끼리 번호가 겹치지 않게. 다른 트랙과는 겹쳐도 된다. [JOURNAL-01](.agents/skills/journal/SKILL.md#journal-01--일지-이름과-순번)
- **작업마다 최신 `origin/main` 에서 워크트리를 파고, 머지가 끝나면 지운다** — [GIT-02](.agents/skills/git-workflow/SKILL.md#git-02--작업마다-워크트리)
- **모든 변경은 브랜치 → PR, `ci-ok` 를 통과시킨다** — [GIT-01](.agents/skills/git-workflow/SKILL.md#git-01--브랜치와-pr), [CI-01](.agents/skills/ci/SKILL.md#ci-01--ci-ok)
- **검사가 실패하면 기준을 낮추지 말고 원인을 고친다** — [CI-02](.agents/skills/ci/SKILL.md#ci-02--실패는-원인을-고친다)

전체 목록: [불변식 카탈로그](.agents/invariants/INVARIANTS.md)

## 무엇을 하려면 어디를 읽나

| 하려는 일                                                         | 읽을 정본                                            |
| ----------------------------------------------------------------- | ---------------------------------------------------- |
| 세션을 시작한다(트랙 정하기, 남은 항목 고르기)                    | [tracks](.agents/skills/tracks/SKILL.md)             |
| 롬을 분석한다(MesenCE 프로브, 자동 보행, 리스팅, 디코더 작성)     | [analysis](.agents/skills/analysis/SKILL.md)         |
| 해킹 일지·형식 문서·그림을 쓴다                                   | [journal](.agents/skills/journal/SKILL.md)           |
| 워크트리·브랜치·커밋·PR 을 만들거나 정리한다                      | [git-workflow](.agents/skills/git-workflow/SKILL.md) |
| 워크플로를 바꾸거나 CI 실패를 고친다                              | [ci](.agents/skills/ci/SKILL.md)                     |
| 의존성·Python·uv·툴킷 버전을 바꾼다                               | [dependencies](.agents/skills/dependencies/SKILL.md) |
| 한국어 문서(README, 일지, 형식 문서)를 쓴다                       | [korean-copy](.agents/skills/korean-copy/SKILL.md)   |

남은 일은 [docs/todo.md](docs/todo.md), 도구 사용법은 [tools/README.md](tools/README.md), CI 구성은 `.github/workflows/ci.yml` 에서 바로 확인한다.
