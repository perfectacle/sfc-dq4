# dq4 남은 일: FC 원작 분석

아직 확인하지 못한 것과 다음에 할 일입니다. 위에 있을수록 먼저 합니다. 끝낸 항목은 지우고 결과는 형식 문서와 해킹 일지에 남깁니다. 트랙과 고치는 법은 [tracks](../../.agents/skills/tracks/SKILL.md) 를 봅니다.

FC DQ4(Rev A) 원작 데이터 분석. 이식할 데이터가 어디에 어떤 형식으로 있는지 찾습니다. 시작점은 [handoff.md](handoff.md). 포팅 결과물의 남은 일은 [sfc/dq4/todo.md](../../sfc/dq4/todo.md) 에 있습니다.

분석은 포팅에 필요한 큰 줄기를 마쳤고, 아래는 남은 세부입니다. 각 형식 문서의 「남은 것」 절이 더 자세한 목록입니다. 포팅(DQ5 엔진에 넣기)이 시작되면 거기서 막히는 것부터 합니다.

- **이벤트·플래그**: [추정]으로 남은 플래그 뜻, 인물·OAM 만 움직이는 이벤트(05 06 07 0B 10 19 21 2D 2E)의 장면, 마지막 전투(2B) 뒤 マスタードラゴン 장면, 맵 이벤트 줄 3~9·B, `$70E0`·`$7140`, 마차 안 자리 `$6172~$6177`, 이벤트 루틴 138개의 조건([dq4-save-format.md](docs/dq4-save-format.md), [dq4-npcblock-format.md](docs/dq4-npcblock-format.md), [dq4-script-format.md](docs/dq4-script-format.md)).
- **표**: 작전마다 7바이트 표(`13:$BB53`~)와 후보 비교(`13:$AB92`)·공격 후보 점수 식, トルネコ·ライアン·アリーナ(`13:$B049`)·작전 4 규칙, 수비력 상한·バイキルト 비트·두 배 조건(`11:$AC4C`)·ザオラル 등 남은 주문 효과량, 몬스터 바이트 21 bit2-0, 아이템 플래그 `$8D1B` bit7·`$8D9A`, 여자 勇者 레코드 8([dq4-data-format.md](docs/dq4-data-format.md)).
- **창**: 본문 바이트 `B0` 이 켜는 `$F5` bit0 의 효과, 걸러내기 값 `08`·`80`·`40`, 값 번호 `4A`, 목록 `DC`, 곁 창 `0F` 의 틀, 화면에서 못 본 항목 몇 개, x3 `83` 두 곳이 실제 장면에서 도는 것(`10:$BAE1` 은 억지로 지나게 해 BRK+5 확인, `11:$BC2B` 는 5장 いれかえ)([dq4-text-format.md](docs/dq4-text-format.md), [dq4-bank-format.md](docs/dq4-bank-format.md)).
- **블록·맵**: 맵 번호 bit6·`$41` bit7 화면 확인, 그룹 48 의 장면, 성 앞 워프 nametable 차이, 배 자리 `$6195/$6196`, `12:$A728`·`15:$B110` 을 부르는 곳, 필드 3 막이의 `$62A4` 갈래([dq4-block-format.md](docs/dq4-block-format.md), [dq4-map-format.md](docs/dq4-map-format.md), [dq4-field-format.md](docs/dq4-field-format.md)).
- **상점·조우**: 숨김 조건의 플래그 사이 관계, 그룹 FE 호출 경로, `$6E44` bit7 을 읽는 나머지 곳, へんげのつえ 모습 표 `1E:$B079`, 장 중간 저장 칸 불러오기([dq4-shop-format.md](docs/dq4-shop-format.md), [dq4-encounter-format.md](docs/dq4-encounter-format.md)).
- **원작 그림**: 엔딩 바다 물결(줄 스크롤), 장 제목 타일 둘째 평면, 1장 제목 화면, 이름 없는 그룹 30개, デスピサロ 등 [dq4-fcsprite-format.md](docs/dq4-fcsprite-format.md) 의 남은 것([dq4-fcgfx.md](docs/dq4-fcgfx.md)).
- **실험 환경**: 1장 세이브스테이트 넷을 지금 `dq4state.sh` 로 다시 만들지(문서 숫자 다시 확인 필요, [handoff.md](handoff.md#실험-출발점)).
