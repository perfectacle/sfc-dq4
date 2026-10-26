# dq5 남은 일

아직 확인하지 못한 것과 다음에 할 일입니다. 위에 있을수록 먼저 합니다. 끝낸 항목은 지우고 결과는 형식 문서와 해킹 일지에 남깁니다. 트랙과 고치는 법은 [tracks](../../.agents/skills/tracks/SKILL.md) 를 봅니다.

SFC DQ5 엔진 분석. 시작점은 [handoff.md](handoff.md). 결과 문서: [dq5-map-format.md](docs/dq5-map-format.md), [dq5-field-format.md](docs/dq5-field-format.md), [dq5-text-format.md](docs/dq5-text-format.md), [dq5-data-format.md](docs/dq5-data-format.md), [dq5-graphics-format.md](docs/dq5-graphics-format.md).

- **소리**: 곡 이름(사용자가 주면 들어 보기 페이지에 반영), 효과음 `3A`·`3C`·`42`·`43`·`45` 의 장면 실측(코드 읽기 자리는 [dq5-sound-format.md](docs/dq5-sound-format.md) 「효과음마다」), 즉값으로 부르는 곳이 없는 16갈래.
- **조우의 남은 것**: 예외 표 플래그 장면 가운데 이벤트 `3B` 를 31/10 에서 대화 `1A4` 로 앞부분까지 걸기(네이티브 `05:E4B8`·`E542`·`E5A3`·`E5BF` 와 기다리는 플래그 `21A1.5`·`21A2.7`·`.6`·`21A4.7`), `2190.6` 을 켠 뒤 그 상태에서의 ルーラ.
- **그래픽 내보내기의 남은 것**: 오프닝 타이틀의 별·링 반짝이 자리와 HDMA 표를 만드는 곳(롬만으로 연출 그리기), 전투 연출 `3E` 루틴의 동작 실측(묶음은 문서에, 롬만으로 움직임 그리기).
- **텍스트의 남은 것**: 한글 넣기([dq5-hangul-format.md](docs/dq5-hangul-format.md)): 창 2바이트 부호를 여러 글자로(캔버스 빌리기 또는 BG3 타일 칸 넓히기, 두 길의 근거는 문서), 옮긴 레코드 자리 `7E:1ABC`~ 의 간접·DP 접근까지 증명, BG3 칸 넓히기(타일맵을 `1C00` 에 쓰는 나머지 곳 찾기·BG1·BG2 글자 빌리기).
