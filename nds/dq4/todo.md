# nds 남은 일

아직 확인하지 못한 것과 다음에 할 일입니다. 위에 있을수록 먼저 합니다. 끝낸 항목은 지우고 결과는 형식 문서와 해킹 일지에 남깁니다. 트랙과 고치는 법은 [tracks](../../.agents/skills/tracks/SKILL.md) 를 봅니다.

NDS DQ4 리메이크와 그 한글 팬패치를 참고 자료로 분석합니다. 시작점은 [handoff.md](handoff.md).

- **채택 이름 정하기**: [glossary.md](docs/glossary.md) 의 「채택」 열. 사용자 확인.
- **그래픽 추출**: 인물·몬스터·맵·전투 배경·UI·이펙트 형식(`CHR`·`MONSTER`·`MAP`·`BTLMAP`·`FIELD`·`2D`·`TRANS`·`PAM`)을 풀어 비공개 에셋 저장소에 내보내기.
- **디버그·워프 도구**: `DEBUG` 폴더와 실행 파일의 숨은 디버그 기능, RAM 지도, 장면 이동, 장 시작 세이브스테이트(desmume libretro 코어).
- **대사 나머지**: `@cN@` 숫자, `%aNNNNN` 변수 목록, MPT0 머리 `+08`·`+0C`, 대응표의 `98A8`(훑/훔), 게임 화면에서 한글판 대사와 대응표 비교.
- **늘어난 내용 나머지**: 6장 맵·이벤트 목록, 동료 대화가 문장을 고르는 조건(`SCRIPT`·`PARAM`), 이민 마을 단계·보상, 카지노·메달 상품 차이, 아이템·몬스터 번호 대조로 「표기만 다른 것」 가르기([extras.md](docs/extras.md#남은-것)).
- **롬 구조 나머지**: `arm9.bin`·오버레이의 Shift_JIS 문자열 표, `PARAM/*.dat`·`SCRIPT/*.bin` 형식, `TRANS/m278_03.dssa` 1바이트 변경.
- **툴킷 보강**: `krpatch xdelta apply` 의 VCDIFF 2차 압축(LZMA), NFTR 읽기(`ndsfont.py`)를 게임 무관 도구로 옮길지.
