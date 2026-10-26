# dq5 남은 일

아직 확인하지 못한 것과 다음에 할 일입니다. 위에 있을수록 먼저 합니다. 끝낸 항목은 지우고 결과는 형식 문서와 해킹 일지에 남깁니다. 트랙과 고치는 법은 [tracks](../../.agents/skills/tracks/SKILL.md) 를 봅니다.

SFC DQ5 엔진 분석. 시작점은 [handoff.md](handoff.md). 결과 문서: [dq5-map-format.md](docs/dq5-map-format.md), [dq5-field-format.md](docs/dq5-field-format.md), [dq5-text-format.md](docs/dq5-text-format.md), [dq5-data-format.md](docs/dq5-data-format.md), [dq5-graphics-format.md](docs/dq5-graphics-format.md).

- **소리**: 곡 이름(사용자가 주면 들어 보기 페이지에 반영), 효과음 `42`·`45` 를 원래 장면에서 듣기(루틴만 직접 불러 확인, [dq5-sound-format.md](docs/dq5-sound-format.md) 「효과음마다」), 부르는 곳이 없는 15갈래, 에셋 `17.spc`·`17-01.spc` 에 빠진 샘플 여섯, 악보 박자를 들어서 정하기·`FB` 가 다음 음 뒤에도 머무는지.
- **조우의 남은 것**: 원래 순서의 ラインハット 01/04·01/00 에서 パパス 가 기다리는 `21A1.7` 을 켜는 곳([dq5-story.md 「남은 것」](docs/dq5-story.md#남은-것)).
- **일행 관리의 남은 것**: 신부를 사람 동료 칸으로 옮기는 `05:FB7D`(`2F:8F7A` 가 부름)와 결혼식 뒤 ビアンカ 를 칸 0 에서 데려오는 `05:F6FF` 를 장면으로 실측, `21:8923`·루틴 `BD` 가 `2190.5`·`21B7.5` 로 칸 번호에 1 을 더하는 갈래([dq5-data-format.md 「사람 동료 칸」](docs/dq5-data-format.md#사람-동료-칸-7e294a)).
- **네이티브 호출의 남은 것**: `21AA.7` 을 켜는 03/07 장면(인물 스크립트 `05:9653`+30)부터 03/05 소동·`FB41` 까지 이어 걷기.
- **그래픽 내보내기의 남은 것**: 오프닝 타이틀을 A 로 끝내는 마지막 14장을 롬 코드 실행(`dq5titlevm.py`)과 맞추기(그 앞 328장은 같음), 전투 연출을 입구 상태 없이 롬만으로 그리기(입구 WRAM·VRAM 한 벌을 넣은 롬 코드 실행 `dq5fxvm.py` 는 139벌 중 133벌 같음, 처리 도중 NMI·HDMA 는 흉내 안 함)·`3E` 의 `DDDC`·`F01F` 를 부르는 장면, `2F`(ミルドラース 둘째 모습)가 쓰러질 때 HDMA 채널 4(표 `00:0DB9`, 간접 뱅크 `27`)가 몇 프레임만 OBJ 팔레트 0 의 색 하나를 덮는 까닭.
- **텍스트의 남은 것**: 한글 넣기([dq5-hangul-format.md](docs/dq5-hangul-format.md)): 창 2바이트 부호를 여러 글자로(캔버스 빌리기 또는 BG3 타일 칸 넓히기, 두 길의 근거는 문서), 옮긴 레코드 자리 `7E:1ABC`~ 를 실행하지 않은 코드까지 증명(장면 열일곱의 접근 카운터는 0), BG3 타일맵을 옮길 자리(`3C00` 은 필드 글자, `4C00` 은 로고·전투 그림과 겹침, 즉값 열일곱은 `dq5hangul.py bg3move`)·BG1·BG2 글자 빌리기.
- **카지노·숨은 물건의 남은 것**: 슬롯 난수 `11:BC26` 이 실제 놀이에서 고른지와 기대 수익(1 넘음)을 수천 판으로 확인([dq5-data-format.md](docs/dq5-data-format.md)), 그룹 `50` 이상 맵의 아래층 상자 칸 11개가 이벤트로 열리는지와 상자 찾기 `12:F849` 가 보는 칸([dq5-map-format.md](docs/dq5-map-format.md)).
