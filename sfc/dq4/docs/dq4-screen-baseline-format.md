# 화면 기준 비교

장면 검사가 실제 화면 그림을 기준과 견주는 장치다(`sfc/dq4/tools/dq4screens.py`). 지금까지 장면 검사는 화면을 VRAM·버퍼 바이트나 특정 칸으로 봤다. 이 장치는 플레이어가 보는 그림 전체가 그대로인지를 본다.

## 화면을 얻는 법

| 에뮬레이터 | 얻는 법 | 결정성 |
| --- | --- | --- |
| MesenCE(헤드리스) | `lua/dq4screen.lua` 가 그 프레임 끝(endFrame)에 `emu.getScreenBuffer()` 를 읽어 `screen-NNNNN.rgb`(머리 8바이트: 너비·높이 u32 little, 이어서 RGB)로 쓴다 | 같은 장면을 차례로 네 번, 6개씩 함께 12번 돌려 버퍼가 모두 같았다 |
| libretro(bsnes·snes9x) | 코어가 넘긴 프레임(`dq4libretro.Core.frame`) | 코어 실행은 결정적이다(읽은 롬 바이트 건전성 검사와 같음). 코어 옵션은 넘기지 않아 `dq4cores` 가 고정한 커밋의 기본값에 기댄다 |

- `emu.getScreenBuffer` 는 그 프레임의 PPU 화면에 영상 필터를 바로 돌려 돌려준다(MesenCE `LuaApi::GetRenderedFrame`).
- `emu.takeScreenshot` 은 쓰지 않는다. 따로 도는 화면 디코더가 마지막으로 그린 그림이라 실행마다 다를 수 있다(읽은 롬 바이트 캐시 형식 문서 「화면 찍기는 결정적이지 않다」). 확인용 PNG(`shot-NNNNN.png`)로만 남긴다.
- 화면 버퍼는 사용자 설정을 따른다. 그래서 MesenCE 를 띄울 때 버퍼나 에뮬레이션에 닿을 수 있는 설정을 `dq4screens.SCREEN_ARGS` 로 명령줄에서 UI 기본값에 고정한다. 사용자 설정 파일은 건드리지 않는다.
  - 명령줄 값은 settings.json 보다 앞선다. 실측: 설정 파일이 밝기 0·고정 해상도 꺼짐일 때 명령줄의 밝기 50·고정 해상도 켬이 버퍼를 바꿨다.
  - 틀린 이름·값은 아무 말 없이 무시된다(`ConfigManager.ProcessSwitch` 가 false 를 돌려도 testrunner 는 멈추지 않고 기록에도 없음). 실측: `--Video.VideoFilter=Bogus`, `--Video.Bogus=1` 모두 버퍼가 그대로였고 기록이 비었다.
  - 그래서 장면 검사는 `VERIFY_ARGS` 를 하나씩 더해 타이틀을 다시 찍고, 기준과 달라지는지 본다(결과 `settings`). 달라지지 않으면 MesenCE 판이 바뀌어 그 이름이 먹지 않는 것이다. 장면마다 넘긴 명령줄은 `args.txt` 에 남는다. MesenCE 가 실제로 쓴 값은 Lua 로 읽을 수 없어, 넘긴 값만 남긴다.

설정마다 타이틀(1300프레임) 버퍼에 닿는지 잰 것(이름은 MesenCE 4b8a196e 의 `UI/Config/SnesConfig.cs`·`VideoConfig.cs` 와 맞춤):

| 설정 | 바꾼 값 | 버퍼 | 고정 |
| --- | --- | --- | --- |
| `Video.VideoFilter` | NtscBisqwit·NtscBlargg | 바뀜(602×478 등) | None |
| `Video.Brightness`·`Contrast`·`Hue`·`Saturation` | 50 | 바뀜 | 0 |
| `Video.ScanlineIntensity` | 50 | 그대로(화면 찍기만 바뀜) | 0 |
| `Snes.HideBgLayer1`·`2`·`HideSprites` | true | 바뀜 | false |
| `Snes.HideBgLayer3`·`4` | true | 그대로(타이틀이 안 씀) | false |
| `Snes.ForceFixedResolution` | true | 바뀜(512×478) | false |
| `Snes.Region` | Pal | 바뀜 | Auto |
| `Snes.PpuExtraScanlinesBeforeNmi`·`AfterNmi` | 100 | 바뀜 | 0 |
| `Snes.ColorCorrection` | NtscBlackLevel·DeepBlackBoost | 그대로 | None |
| `Snes.HighResBlendMode`·`DeinterlaceMode`·`RemoveSpriteLimit` | BlendAll·Bob·true | 그대로(고해상도·비월·한 줄 32개 넘는 스프라이트가 없음) | None·Weave·false |
| `Snes.SpcClockSpeedAdjustment` | 0 | 그대로 | 40 |
| `Snes.ConfigOverrides.OverrideVideoFilter` | true(+NtscBlargg) | 그대로 | false |
| `Snes.Overscan.Top` | 20 | 그대로(화면 찍기만 바뀜) | 고정 안 함 |
| `Video.AspectRatio`·`UseBilinearInterpolation`·`ScreenRotation` | Auto·true·_90Degrees | 그대로(돌리기는 화면 찍기만 바뀜) | 고정 안 함 |

- 겹침 테두리(Overscan)는 `GetRenderedFrame` 이 `SendFrame(…, enableOverscan=false)` 로 보내 버퍼에 들지 않는다. 화면 비율·쌍선형 보간·돌리기는 그리기 단계의 것이다. 그래서 고정하지 않는다.
- 「그대로」 인 설정도 다른 장면(어두운 색, 고해상도 등)에서는 닿을 수 있어 기본값으로 고정한다. 그 이름이 먹는지는 타이틀로 확인할 수 없다(`VERIFY_ARGS` 에 없음).
- HD 팩은 MesenCE 에서 NES 만 쓴다.
- 전원 RAM 은 읽은 롬 바이트 캐시와 같은 `FIXED_ARGS`(`RamPowerOnState=AllZeros`)로 고정한다.

## 기준

기준 그림은 롬에서 나온 것이라 저장소에 두지 않는다([ROM-01](../../../.agents/skills/analysis/SKILL.md#rom-01--롬-데이터-금지)). 대신 `sfc/dq4/screens.toml` 에 칸 해시만 둔다.

- 화면을 8×8 칸으로 나눠 칸마다 SHA-1 앞 4바이트를 낸다. 256×239 화면이면 32×30 칸, 3840바이트(base64 로 약 5KB)다.
- 판정은 이 해시만 보므로 롬이 있는 어느 머신에서나 같다.
- 칸 해시도 정보를 조금 드러낸다.
  - 한 색뿐인 칸은 SNES 색 32768가지를 모두 해시해 보면 색이 나온다.
  - 같은 해시가 되풀이되는 자리를 이으면 반복 무늬(바닥·벽)의 윤곽이 보인다.
  - 여러 색이 섞인 칸은 후보가 너무 많아 되살리기 어렵다. 그래서 그림 자체(글자·인물·타이틀 그림)는 드러나지 않는다고 보고, 롬 데이터를 커밋하는 것보다 위험이 훨씬 낮다고 판단했다.

| 칸 | 뜻 |
| --- | --- |
| `scene`·`emulator` | 장면 이름, `mesence`·`bsnes`·`snes9x` |
| `width`·`height` | 화면 크기. 다르면 실패 |
| `masks` | 가림 직사각형 `[x, y, 너비, 높이]` 목록(픽셀). 안 픽셀은 0 으로 지우고 해시를 낸다. 칸이 모두 가려지면 그 칸은 견주지 않는다. 화면 밖이거나 너비·높이가 0 이면 기준을 쓸 때 거부한다 |
| `tolerance` | 허용하는 다른 칸 수(기본 0) |
| `digest` | 가린 화면 전체의 SHA-256 앞 16자리. 로컬 기준 그림 캐시의 이름 |
| `tiles` | 칸 해시(4바이트씩, 위 줄부터)의 base64. 모두 가려진 칸은 0 |
| `reason` | 이 항목을 쓴 까닭 |
| `check` | 위 칸들과 까닭의 표지(SHA-1 앞 12자리). 만드는 법이 공개돼 있어 실수로 손댄 것만 잡는다. 일부러 고친 것은 막지 못한다 |

- 가림·허용치는 장면 정의(검사 스크립트)에 두고, 기준을 쓸 때 함께 적는다. 검사 때 장면 정의의 가림·허용치가 기준과 다르면 실패한다(기준을 다시 써야 함).
- 허용치는 칸 단위다. 픽셀 단위 허용은 기준 픽셀이 있어야 하는데, 그 픽셀은 저장소에 두지 않으므로 칸으로 센다.

### 다른 길을 고르지 않은 까닭

| 길 | 판정이 결정적인가 | CI·배포 관문 |
| --- | --- | --- |
| 기준 PNG 를 저장소에 둠 | 그렇다 | ROM-01 에 어긋난다 |
| 기준 PNG 를 로컬에서 만듦(기준 커밋의 롬을 빌드해 찍음) | 기준 커밋·코어·설정을 모두 맞춰야 한다. 머신마다 그 기준을 따로 만들어야 한다 | 기준 롬을 하나 더 빌드해야 하고, 기준 커밋이 움직이면 판정도 움직인다 |
| **칸 해시를 저장소에 둠(이것)** | 그렇다. 해시는 저장소에 있고 지금 화면만 찍는다 | 롬이 있는 곳(가드 `--run`, 배포 관문 `--no-cache`)이면 어디서나 같다. CI 에는 롬이 없어 단위 시험만 돈다 |

## 차이 그림

실패하면 검사 출력 폴더에 `<장면>-<에뮬레이터>-diff.png` 를 남긴다.

- 다른 칸은 빨간 테두리로, 가림은 어둡게 그린다.
- 기준을 쓸 때나 통과할 때 화면을 로컬 캐시(원래 체크아웃의 `work/cache/screens/<digest>.png`, 추적하지 않음)에 둔다. 그 기준의 그림이 캐시에 있으면 기준·지금·차이를 나란히 그린다. 없으면 지금과 차이만 그린다.
- 실측: 타이틀 기준(1300프레임째)을 1304프레임째 화면과 견주니 구름 쪽 74칸이 달랐다. 기준·지금·차이 세 칸 그림이 나왔다.

## 기준 갱신

기준은 장면 검사의 `--write-screens "까닭"` 으로만 쓴다(`dq4screens.write_baselines`).

- 칸·가림·허용치가 바뀐 항목과 새 항목에만 그 까닭이 `reason` 으로 남는다. 같은 항목은 앞 까닭을 둔다.
- 까닭이 비었거나 공백뿐이면 거부한다.
- 손으로 고친 기준(칸·까닭 등을 바꾸고 표지를 맞추지 않음)은 검사 때 `ValueError` 로 멈춘다. 1장 걷기 메시지 기준(`ch1-walk-messages.toml`)과 같은 꼴이다.
- `--write-screens` 는 표지를 보지 않고 읽어, 손으로 고친 파일이 있어도 다시 쓸 수 있다. 이번에 쓰지 않는 장면의 항목 가운데 표지가 맞지 않는 것은 빼므로, 그 장면은 다시 써야 한다.
- 고른 장면이 하나도 돌지 않거나 모자라면 통과가 아니다. `--only` 에 모르는 장면 이름을 주면 바로 멈춘다.

## 장면

`dq4screencheck.py`(가드 `dq4-screen-baseline`)가 흔들림 없는 장면 넷을 MesenCE 로, 타이틀을 bsnes·snes9x 로 견준다. 장면은 전원(전원 RAM 고정)이나 같은 롬으로 만든 출발 상태에서 정한 입력만 넣는다. 그래서 난수·시각·조우가 늘 같다.

| 장면 | 출발 | 입력 | 프레임 |
| --- | --- | --- | --- |
| `title` | 전원 | 없음 | 1300(타이틀 그림) |
| `start-room` | 서장 시작 상태(`dq4ch1walkcheck.prologue_start`) | 열린 명령 창을 B 로 닫음 | 80 |
| `status` | 같음 | 명령 → 상태 → 상태 보기 | 330 |
| `shop-list` | 서장 끝 상태(상태 캐시)에서 이무르 방어구점 카운터 앞(`37/00` 34,8)으로 순간이동 | 위를 보고 말을 걸어 「사기」 | 420 |

- 서장 시작 상태는 명령 창이 열린 채 남는다. 그래서 `start-room` 은 B 로 닫은 뒤 찍는다.
- 지금 장면에는 가림이 없다. 장면이 결정적이어서 깜박이는 커서·움직이는 인물도 프레임마다 같다.
- 결정성은 세 번 다시 돌려 모두 통과하는 것으로 확인했다. 가림은 시계처럼 실행마다 다른 곳(실시간 시각, 받은 기록의 날짜 등)이 있는 장면에 쓴다.

## 남은 것

- 장면을 더 붙이는 일(전투 창, 맵마다의 필드 화면 등). 장면 검사마다 `check_screen` 을 부르면 된다.
- MesenCE 와 libretro 의 같은 장면 화면은 서로 견주지 않는다(에뮬레이터마다 기준이 따로다).
