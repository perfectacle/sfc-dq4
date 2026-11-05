# 2026-11-05-03: 가드에 없던 실행 검사 다섯을 등록

`guards.toml` 에 없던 dq4 실행 검사를 하나씩 지금 main(`8e08fc25`)의 1장 빌드로 돌렸다. 통과하고 결정적인 다섯을 가드로 등록했다. 평평함 지표 도구 하나는 롬 검사가 아니라 등록하지 않았다.

## 1. 하나씩 돌린 결과

검사마다 같은 명령을 두 번 돌려, 판정 줄과 남긴 기록 파일이 같은지 보았다. 헤드리스 자리를 기다린 줄은 뺐다.

| 검사 | 롬 | 결과 | 두 번 | 지키는 것 | 가드 |
| --- | --- | --- | --- | --- | --- |
| `dq4menucursorcheck.py` | `dq4-ch1.sfc` | 통과(10개 사례, 59초) | 같음(커서 기록 SHA-1 같음) | 명령 창에서 두 방향을 겹쳐 눌러도 한 칸씩만 | `dq4-menu-cursor` |
| `dq4namecursorcheck.py` | 이름 입력 롬(아래) | 통과(52개, 65초) | 같음 | 자모판 방향 전환·반복·빈 칸·Start 커서 | `dq4-name-cursor` |
| `dq4msgcountcheck.py` | `dq4-ch1.sfc` | 통과(서장 60·왕 133 메시지, 92초) | 같음 | 메시지마다 받은 A ≤ 쪽 수 | `dq4-msg-count` |
| `dq4peoplecheck.py` | `dq4-ch1-full.sfc` | 통과(66장면, 28초) | 같음(`results.json` 같음) | 맵마다 인물 OBJ 가 제 세트로 실림 | `dq4-people-sets` |
| `dq4spritecheck.py` | — | 롬을 띄우지 않음 | — | 색 번호 행렬의 평평함 지표(통과·실패 없음) | 등록 안 함 |

- 이름 입력 롬: 1장 빌드의 `overture.sfc` 에 `dq4menupatch.py build` 를 `DQ4_NAMEENTRY_SYMBOLS` 와 함께 다시 돌려, 롬과 기호 파일을 만든다(창 글자 검사가 `DQ4_WINDOWNAME_SYMBOLS` 로 하는 것과 같은 꼴).
- 결정성: 네 검사는 정한 입력으로 전원부터 걷거나, 1장 걷기 검사(난수·낮밤·조우 고정)의 세이브스테이트에서 출발한다.
- `dq4peoplecheck.py` 를 처음 `dq4-ch1.sfc` 로 돌리자 훅 흉내가 `w65816.Stop: step limit at 2BC339` 로 죽었다.
  - 그 롬의 인물 훅 자리 `3E:FC00` 은 비어 있고 훅을 부르는 곳도 없다. 인물 단계(`people`)는 그 뒤 단계에서 들어간다. 흉내가 `BRK` 를 밟고 소리 포트 대기 고리(`2B:C333`)를 돌았다.
  - 출하 롬 `dq4-ch1-full.sfc` 로는 66장면이 통과했다. 검사가 깨진 것이 아니라 롬을 잘못 고른 것이라 기준은 그대로 두고, 가드는 출하 롬으로 돌린다.
- `dq4msgcountcheck.py` 는 출하 롬으로도 통과했다(서장 56·왕 133). 문서의 명령대로 `dq4-ch1.sfc` 로 등록했다.

## 2. 같이 등록한 것

다섯째 등록은 `dq4nameentrycheck.py` 다(이름 조합·삭제·Y 완료·새 게임 기록, 15개 사례). 같은 이름 입력 롬으로 통과했고 두 번 돌린 판정이 같아, `dq4-name-entry` 로 함께 등록했다.

## 3. 가드

새 가드 다섯은 아래와 같다.

- `dq4-menu-cursor`
- `dq4-name-cursor`
- `dq4-name-entry`
- `dq4-msg-count`: 같은 명령 안에서 1장 걷기 `--units` 로 출발 상태를 만든다.
- `dq4-people-sets`: 같은 명령 안에서 1장 걷기 `--units` 로 출발 상태를 만든다.

paths 는 묶음 `ch1-build`(·`ch1-walk`) 와 `dq4guardpaths.py` 가 찍은 빠진 파일(각 검사의 lua, `dq4mesen`, `dq4openbus.lua`)로 채웠고, `tools/mesence_settings.py` 를 넣었다. 빠짐은 0 이다.

## 4. 그 밖의 미등록 실행 도구

롬을 띄우는(MesenCE·libretro) `sfc/dq4/tools/*.py` 가운데 어느 가드의 명령에도 없는 것을 훑었다.

| 도구 | 하는 일 | 판정 | 의견 |
| --- | --- | --- | --- |
| `dq4environmentprobe.py` | 환경 그래픽을 따로 된 SFC 뷰어로 띄워 MesenCE 출력과 견줌 | 없음 | 그래픽 인코딩 확인 도구. 맵 엔진 삽입은 보지 않음 |
| `dq4prologuecheck.py` | 새 게임부터 서장 끝까지 한 번에 걷기 | 있음 | 같은 길(`ROUTE`)을 1장 걷기 검사의 서장 구간이 걸어, 여러 가드가 그 모듈을 씀. 따로 등록할지는 판단 필요 |
| `dq4talkdelay.py` | 서장 자동 대화까지의 시각을 재는 프로브 | 있음(일부) | 측정 도구 |
| `dq4freshstate.py`·`dq4mesen.py` | 출발 상태 만들기·MesenCE 띄우기 | — | 다른 검사가 쓰는 공용 모듈 |
| `dq4spritecheck.py` | 평평함 지표 | 없음 | 롬 검사가 아님(위) |

## 남은 것

- `dq4prologuecheck.py`·`dq4talkdelay.py` 를 따로 등록할지.
