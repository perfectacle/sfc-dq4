# sfc-dq4

FC판 드래곤 퀘스트 IV(일본판) 를 슈퍼패미컴 DQ5(일본판) 엔진 위에 옮기는 한글 해킹롬 프로젝트.

- 실제 SFC 롬으로 동작하는 IPS 패치를 만든다(PC 포트·Unity 아님).
- 롬 데이터는 저장소에 없다. 직접 덤프한 롬을 `rom/` 에 둔다.

| 파일 | 원본 | SHA-1 |
| --- | --- | --- |
| `rom/dq5.sfc` | Dragon Quest V - Tenkuu no Hanayome (Japan), LoROM 12Mbit, 헤더 없음 | `1c47ed62c561d7965fe5dc2a03f4c37feb4a46b5` |
| `rom/dq4.nes` | Dragon Quest IV - Michibikareshi Monotachi (Japan) (Rev A), MMC1, iNES 헤더 포함 | `1147ce6dfdc3354d8bb89be40f5d1a97a2be1aea` |

`dq4.nes` 의 PRG(헤더 16바이트 뒤 512KB) CRC32 는 `0794F2A5` 다. 초판(Rev 0, PRG CRC32 `2DD71ACB`)은 쓰지 않는다.
- 그래픽은 직접 찍는다. 다른 팬 해킹의 데이터는 쓰지 않는다.

참고 자료: [docs/references.md](docs/references.md)
