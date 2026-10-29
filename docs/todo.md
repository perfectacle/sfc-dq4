# 남은 일

트랙마다 아직 확인하지 못한 것과 다음에 할 일입니다. 위에 있을수록 먼저 합니다. 끝낸 항목은 지우고 결과는 형식 문서와 해킹 일지에 남깁니다. 트랙과 고치는 법은 [tracks](../.agents/skills/tracks/SKILL.md) 를 봅니다.

## dq5

[sfc/dq5/todo.md](../sfc/dq5/todo.md) 에 있습니다.

## dq4

FC 원작 분석은 [fc/dq4/todo.md](../fc/dq4/todo.md), SFC 포팅 결과물은 [sfc/dq4/todo.md](../sfc/dq4/todo.md) 에 있습니다.

- **dq5 트랙의 요청**: `sfc/dq4/tools/dq4romassets.py` 가 인물 세트를 원래 세트 수(`A3`)만큼만 돌아, `dq5spritewrite.py --sets-at` 으로 더한 새 세트 `A5`~`FF` 를 건너뜁니다. 옮긴 표(`1F:CFB7` 이 가리키는 곳)는 `dq5sprite.set_numbers`·`set_record` 로 읽을 수 있습니다([일지](../sfc/dq5/journal/2026-10-27-63-setgrow.md)).
- **dq5 트랙의 요청**: `sfc/dq4/tools/dq4environmentrom.py` 의 `01:F42D` 물체 훅과 wrap 루틴이 Y 를 저장하지 않고 바꾼 맵 찾기 루틴을 부릅니다. 그 루틴 첫머리 `SEP #$30` 이 Y 상위 바이트를 지워, 문 표 오프셋이 `100` 이상인 바꾸지 않은 맵의 문 물체가 사라집니다. MesenCE 헤드리스 실측 셀 바이트: 1A/00 (36,27) 원본 `00 19 91 0D 00 2E 34 3F` → dq4 패치 뒤 `00 09 91 0D 00 00 00 00`, 19/00 (32,47) `00 11 32 0D 00 34 34 40` → `00 01 32 0D 00 00 00 00`. 호출을 `PHY / JSL find / PLY` 로 감싸면 원본과 같아집니다([일지](../sfc/dq5/journal/2026-10-29-02-lowfix.md)).

## nds

[nds/dq4/todo.md](../nds/dq4/todo.md) 에 있습니다.
