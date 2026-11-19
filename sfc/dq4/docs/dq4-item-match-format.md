# 물건 출처와 FC 대조

장 빌드 롬이 실제로 주는 물건과, 그 물건이 FC 원작의 같은 가게·같은 칸·같은 종에서 오는지를 에뮬레이터 없이 롬 표로 잰다. 회귀 가드는 [`guards.toml`](../guards.toml) 의 `dq4-item-match` 다.

```sh
uv run --locked python sfc/dq4/tools/dq4itemreach.py --rom work/ch3/dq4-ch1.sfc --chapter 3   # 출처마다 물건
uv run --locked python sfc/dq4/tools/dq4itemmatch.py --rom work/ch3/dq4-ch1.sfc               # FC 대조, 다르면 1
```

## 장마다 주는 물건(`dq4itemreach`)

`given_items(롬 바이트, 장)` 은 `{출처: DQ5 물건 번호 집합}`, `given_union` 은 그 합이다. 장 n 빌드 롬은 1~n 장 내용을 담으므로 시작 소지품·사건 지급도 1~n 장을 더한다.

| 출처 | 읽는 자리 |
| --- | --- |
| 가게 | 옮긴 가게 표(`dq5progresswrite.shop_records`, `3C:E000`)의 종류 0~2 목록. 키는 가게 키 표(`3C:FE00` 훅이 `LDA long,X` 로 읽는 `[그룹][첫 맵][끝 맵][키]`)로 그룹에 붙이고, 그 장 이하 그룹의 키만. 한 번 덮는 키 `F0`~`F7` 은 3장 |
| 코인 경품 | 종류 3 키 `15` 목록. 3장부터 |
| 상자·조사 | 옮긴 상자 표(`dq5chestreloc.parse`)에서 그 장 이하 새 그룹 맵 |
| 몬스터 | DQ4 몬스터(`dq4windowtext.numbered_names`) 레코드 `23:8000 + n × 25` 의 `+17`, 3장은 전투 뒤 물건 16칸(`dq4fieldencounter.dq5_drop_items`)도. 장으로 가르지 않음 |
| 시작 소지품 | 1장 주인공 기록 `23:C014` 의 물건 12칸, 2장 `dq4ch2event` 기록, 3장 `dq4ch3event.start` |
| 사건 지급 | `dq4itemport.EVENT_ITEMS`, 2장 꿀·팔찌·도적의 열쇠, 3장 사건 모듈 `CALLS` 의 `give` |

새 그룹의 장은 `dq4groupbuild.LINKS` 의 `chapter`(없으면 서장·1장)다.

## FC 대조(`dq4itemmatch`)

이식 길(이름이 같은 DQ5 물건, 빌린 자리, `dq4chestport.SUBSTITUTE`·`SPECIAL`)을 거친 FC 물건이 빌드 롬의 같은 자리에 있어야 한다. 다른 줄을 `곳 자리: FC … / 빌드 …` 로 찍고, 알려진 줄(`KNOWN`, 까닭과 풀 고침)이 아니거나 더 다르지 않은 알려진 줄이 남으면 1 로 끝난다.

| 곳 | FC | 빌드 |
| --- | --- | --- |
| 가게 | 새 그룹 맵마다 그 장 시작에 서 있는 판매자(`dq4shopport.merchants`) 종류의 목록(fc `dq4shop.lookup`), 차례대로 | 그 맵의 가게 키 목록 |
| 값 | 가게 물건마다 FC 값(fc `dq4shop.price`) | `23:B081` × 배율(`dq5shop.price`) |
| 상자 | 맵 안 상자 차례(fc `dq4chest.chests`) | 그 맵 상자 |
| 조사 | タンス·つぼ(fc `dq4block.pots`) | 조사 표의 (2x+1, 2y+1) |
| 발밑 | 숨은 물건(fc `dq4chest.feet_items`)의 물건·금화, 「위를 보면」 물건(`FEET_GIFTS`). 그 장 이하 | 그 칸에서 조사는 발밑 표의 일행 칸 (2x, 2y+1), 「위를 보면」 은 바로 위 빈 가구의 조사 표 (2x+1, 2y−1) |
| 몬스터 | `dq4monport` 가 옮긴 종마다 FC 떨어뜨림 | 레코드 `+17` |

사람이 대화로 주는 물건과 떨어뜨림 확률은 견주지 않는다.
