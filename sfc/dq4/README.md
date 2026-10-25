# dq4: SFC 포팅 결과물

dq4 트랙이 SFC DQ5 엔진에 넣으려고 만드는 결과물(포팅용 인물 스프라이트·샘플 맵·타이틀·일러스트)의 폴더입니다. FC 원작 분석은 [fc/dq4/](../../fc/dq4/README.md) 에 있습니다. 규칙은 [AGENTS.md](../../AGENTS.md) 와 [sprites 스킬](../../.agents/skills/sprites/SKILL.md) 을 봅니다.

## 문서

- [handoff.md](handoff.md): 포팅용 그래픽 시작점(타이틀·일러스트 보존, 스프라이트 거절 사유·참고 사이트·후속 제작 방향)
- [docs/dq4-graphics.md](docs/dq4-graphics.md): 포팅용 스프라이트·샘플 맵·한글 타이틀·일러스트와 SFC 변환 규격
- [docs/dq4-sprite-format.md](docs/dq4-sprite-format.md): SFC DQ5 필드 인물 실측(크기·색·눈·보행 프레임)과 그 규칙으로 그린 DQ4 인물 9명 스프라이트, MesenCE 표시 실험
- [docs/dq4-rom-assets-format.md](docs/dq4-rom-assets-format.md): 라이안 정면의 DQ5 롬 삽입과 IPS·갤러리 검증
- [todo.md](todo.md): 남은 일
- [references.md](references.md): 참고 자료
- [tools/README.md](tools/README.md): 도구 사용법

그림은 [images/](images/) 에 있고 `uv run --locked python sfc/dq4/tools/dq4figures.py` 가 제작 원본에서 다시 만듭니다(롬 불필요, 필드 비교 그림만 `work/dq4-sprites/` 덤프 필요).

## 해킹 일지

순번은 dq4 트랙 전체에서 매깁니다. 나머지 번호는 [fc/dq4/](../../fc/dq4/README.md#해킹-일지) 에 있습니다.

- [2026-10-25-12: 그래픽 시안 평가와 작업 인계](journal/2026-10-25-12-graphics.md)
- [2026-10-25-18: DQ5 실측 규격으로 다시 그린 인물 스프라이트](journal/2026-10-25-18-sprites2.md)

- [2026-10-25-50: 라이안 정면을 DQ5 롬 데이터로 연결](journal/2026-10-25-50-rom-assets.md)
