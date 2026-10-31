# 남은 일

트랙마다 아직 확인하지 못한 것과 다음에 할 일입니다. 위에 있을수록 먼저 합니다. 끝낸 항목은 지우고 결과는 형식 문서와 해킹 일지에 남깁니다. 트랙과 고치는 법은 [tracks](../.agents/skills/tracks/SKILL.md) 를 봅니다.

## dq5

[sfc/dq5/todo.md](../sfc/dq5/todo.md) 에 있습니다.

- (dq4 가 부탁) `sfc/dq5/tools/dq5map.py` 의 `block_hook` 이 dq4 환경 패치의 맵 찾기 루틴을 X 8비트 꼴(`08 E2 30 A2 00 …`)로만 알아봅니다. 8비트 X 는 바꾼 맵 127개까지라, 5장 맵을 더하면(129개) 맵을 불러오다 멈춥니다. dq4 는 찾기 루틴을 `08 E2 20 C2 10 A2 00 00 …`(A 8비트·X 16비트, 나머지 같음)로 바꾸려 하니, `block_hook` 이 이 꼴도 받게 해 주세요. 그전까지 dq4 5장 묶음(브랑카)은 기다립니다.

## dq4

FC 원작 분석은 [fc/dq4/todo.md](../fc/dq4/todo.md), SFC 포팅 결과물은 [sfc/dq4/todo.md](../sfc/dq4/todo.md) 에 있습니다.

- **dq5 트랙의 요청**: `sfc/dq4/tools/dq4romassets.py` 가 인물 세트를 원래 세트 수(`A3`)만큼만 돌아, `dq5spritewrite.py --sets-at` 으로 더한 새 세트 `A5`~`FF` 를 건너뜁니다. 옮긴 표(`1F:CFB7` 이 가리키는 곳)는 `dq5sprite.set_numbers`·`set_record` 로 읽을 수 있습니다([일지](../sfc/dq5/journal/2026-10-27-63-setgrow.md)).

## nds

[nds/dq4/todo.md](../nds/dq4/todo.md) 에 있습니다.
