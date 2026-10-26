# dq4: SFC 포팅 결과물

dq4 트랙이 SFC DQ5 엔진에 넣으려고 만드는 결과물(포팅용 인물 스프라이트·샘플 맵·타이틀·일러스트)의 폴더입니다. FC 원작 분석은 [fc/dq4/](../../fc/dq4/README.md) 에 있습니다. 규칙은 [AGENTS.md](../../AGENTS.md) 와 [sprites 스킬](../../.agents/skills/sprites/SKILL.md) 을 봅니다.

## 문서

- [docs/dq4-environment-format.md](docs/dq4-environment-format.md): FC 원작의 색 역할과 DQ5 색·도트 구조로 새로 그린 환경 타일, FC 배치 비교 맵과 SFC 표시 검증
- [handoff.md](handoff.md): 포팅용 그래픽 시작점(타이틀·일러스트 보존, 스프라이트 거절 사유·참고 사이트·후속 제작 방향)
- [docs/dq4-graphics.md](docs/dq4-graphics.md): 포팅용 스프라이트·샘플 맵·한글 타이틀·일러스트와 SFC 변환 규격
- [docs/dq4-sprite-format.md](docs/dq4-sprite-format.md): SFC DQ5 필드 인물 실측(크기·색·눈·보행 프레임)과 그 규칙으로 그린 DQ4 인물 9명 스프라이트, MesenCE 표시 실험
- [docs/dq4-rom-assets-format.md](docs/dq4-rom-assets-format.md): 라이안 정면의 DQ5 롬 삽입과 IPS·갤러리 검증
- [docs/dq4-title-animation.md](docs/dq4-title-animation.md): 사용자 채택본의 원본·레이어 규격·빌드·실행 검증과 재사용 절차
- [docs/dq4-overture-format.md](docs/dq4-overture-format.md): 타이틀 서곡(FC 악보·NDS 템포·DQ5 악기), 시퀀스 10 의 갈래, 뜨는 시간 실측
- [docs/dq4-menu-format.md](docs/dq4-menu-format.md): 모험의 서 메뉴 한글화(미리 그린 열을 VRAM 2000 에, 창 접두 9F, 공용 창의 WRAM 교체, Galmuri11)
- [docs/dq4-name-entry-format.md](docs/dq4-name-entry-format.md): 두벌식 자모 조합과 네 글자 이름 저장, 메뉴 이름 표시
- [docs/dq4-title-format.md](docs/dq4-title-format.md): 정지 한글 타이틀, NDS 오프닝 관찰과 초기 SFC 연결 기록
- [todo.md](todo.md): 남은 일
- [references.md](references.md): 참고 자료
- [tools/README.md](tools/README.md): 도구 사용법

그림은 [images/](images/) 에 있고 `uv run --locked python sfc/dq4/tools/dq4figures.py` 가 제작 원본에서 다시 만듭니다(롬 불필요, 필드 비교 그림만 `work/dq4-sprites/` 덤프 필요).

## 해킹 일지

순번은 dq4 트랙 전체에서 매깁니다. 나머지 번호는 [fc/dq4/](../../fc/dq4/README.md#해킹-일지) 에 있습니다.

- [2026-10-25-12: 그래픽 시안 평가와 작업 인계](journal/2026-10-25-12-graphics.md)
- [2026-10-25-18: DQ5 실측 규격으로 다시 그린 인물 스프라이트](journal/2026-10-25-18-sprites2.md)

- [2026-10-25-50: 라이안 정면을 DQ5 롬 데이터로 연결](journal/2026-10-25-50-rom-assets.md)

- [2026-10-25-51: 한글 타이틀과 DQ5 오프닝 연결](journal/2026-10-25-51-title.md)


- [2026-10-25-52: 용의 날갯짓과 구름 이동](journal/2026-10-25-52-title-animation.md)

- [2026-10-25-64: 타이틀 그림과 레이어의 연결](journal/2026-10-25-64-title-cohesion.md)

- [2026-10-25-65: 성 밑동의 구름 받침 보존](journal/2026-10-25-65-castle-cloud.md)

- [2026-10-25-66: 성 왼쪽 밑동의 구름 겹침 수정](journal/2026-10-25-66-castle-edge.md)

- [2026-10-25-67: 성 왼쪽 아래 조각 제거](journal/2026-10-25-67-castle-trim.md)

- [2026-10-25-70: 채택된 타이틀과 재사용 기준 정리](journal/2026-10-25-70-title-baseline.md)

- [2026-10-25-72: 톨네코·주인공 정면 시안과 손으로 그리기의 한계](journal/2026-10-25-72-sprite-drafts.md)

- [2026-10-26-35: 부제 장식선을 앞 구름 위로](journal/2026-10-26-35-title-ornament.md)

- [2026-10-26-36: 타이틀에 DQ4 서곡 넣기](journal/2026-10-26-36-overture.md)

- [2026-10-26-37: 모험의 서 메뉴를 한글로](journal/2026-10-26-37-menu.md)

- [2026-10-26-38: 자모를 조합해서 이름 넣기](journal/2026-10-26-38-name-entry.md)

- [2026-10-26-39: 부제 위 얼룩 제거와 앞 구름 배치 변형](journal/2026-10-26-39-title-cloud-variation.md)

- [2026-10-26-40: 자모판 방향 전환과 Start 이동](journal/2026-10-26-40-name-cursor.md)

- [2026-10-27-01: 모험의 서 지우기·기록 깨짐 메시지를 한글로](journal/2026-10-27-01-menu-messages.md)

- [2026-10-27-02: 환경 타일을 드래곤 퀘스트 색으로](journal/2026-10-27-02-environment.md)

- [2026-10-27-03: 바트랜드 성을 어두운 돌로](journal/2026-10-27-03-castle.md)
