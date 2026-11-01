# dq4: SFC 포팅 결과물

dq4 트랙이 SFC DQ5 엔진에 넣으려고 만드는 결과물(포팅용 인물 스프라이트·샘플 맵·타이틀·일러스트)의 폴더입니다. FC 원작 분석은 [fc/dq4/](../../fc/dq4/README.md) 에 있습니다. 규칙은 [AGENTS.md](../../AGENTS.md) 와 [sprites 스킬](../../.agents/skills/sprites/SKILL.md) 을 봅니다.

## 문서

- [docs/dq4-environment-format.md](docs/dq4-environment-format.md): FC 원작의 색 역할과 DQ5 색·도트 구조로 새로 그린 환경 타일, FC 배치 비교 맵과 SFC 표시 검증
- [docs/dq4-field-format.md](docs/dq4-field-format.md): FC 필드 0·1·3 을 DQ5 세계 0·1·2 에(블록 대응, 그림·세계별 팔레트, 입구 자리, DQ5 원래 입구 옮기기, 지도·지형 실측)
- [handoff.md](handoff.md): 포팅용 그래픽 시작점(타이틀·일러스트 보존, 스프라이트 거절 사유·참고 사이트·후속 제작 방향)
- [docs/dq4-graphics.md](docs/dq4-graphics.md): 포팅용 스프라이트·샘플 맵·한글 타이틀·일러스트와 SFC 변환 규격
- [docs/dq4-sprite-format.md](docs/dq4-sprite-format.md): SFC DQ5 필드 인물 실측(크기·색·눈·보행 프레임)과 그 규칙으로 그린 DQ4 인물 9명 스프라이트, MesenCE 표시 실험
- [docs/dq4-rom-assets-format.md](docs/dq4-rom-assets-format.md): 라이안 정면의 DQ5 롬 삽입과 IPS·갤러리 검증
- [docs/dq4-title-animation.md](docs/dq4-title-animation.md): 사용자 채택본의 원본·레이어 규격·빌드·실행 검증과 재사용 절차
- [docs/dq4-overture-format.md](docs/dq4-overture-format.md): 타이틀 서곡(FC 악보·NDS 템포·DQ5 악기), 시퀀스 10 의 갈래, 뜨는 시간 실측
- [docs/dq4-sound-port-format.md](docs/dq4-sound-port-format.md): NDS 곡을 DQ5 시퀀스·BRR 로 옮기기, 롬 삽입, NMI 꺼진 맵 전환의 페이드, SPC 실측 대조
- [docs/dq4-sound-port-handoff.md](docs/dq4-sound-port-handoff.md): 사운드 포팅 작업 경과·재현 명령·로컬 실험 폴더
- [docs/dq4-menu-format.md](docs/dq4-menu-format.md): 모험의 서 메뉴 한글화(미리 그린 열을 VRAM 2000 에, 창 접두 9F, 공용 창의 WRAM 교체, Galmuri9·7·11)
- [docs/dq4-name-entry-format.md](docs/dq4-name-entry-format.md): 두벌식 자모 조합과 네 글자 이름 저장, 메뉴 이름 표시
- [docs/dq4-window-text-format.md](docs/dq4-window-text-format.md): 게임 안 창 한글 조사(이름이 지나는 루틴, 장면마다 빈 BG3 타일, 가나 칸 재사용, 글꼴 크기와 타일 수)와 BG3 타일맵 옮기기
- [docs/dq4-title-format.md](docs/dq4-title-format.md): 정지 한글 타이틀, NDS 오프닝 관찰과 초기 SFC 연결 기록
- [docs/dq4-josa-format.md](docs/dq4-josa-format.md): 받침을 보고 고르는 조사 코드와 필드·가게·여관·교회 시스템 메시지
- [docs/dq4-battle-text-format.md](docs/dq4-battle-text-format.md): 전투 메시지 432개 한글(전투 중 빈 BG3 칸 풀, 한글 구간·글자 표, 이름·조사, 창 테두리·줄 올림)
- [docs/dq4-chapter1-format.md](docs/dq4-chapter1-format.md): 1장 첫머리(새 게임 첫 맵, 왕좌의 방 연출, 한글 대사, 인물 배치, 바트랜드 성 곡)
- [docs/dq4-chapter2-format.md](docs/dq4-chapter2-format.md): 2장 첫머리(1장 끝에서 넘어가기, 아리나 일행, 산트하임 왕좌의 방 연출)
- [docs/dq4-compat-format.md](docs/dq4-compat-format.md): 호환성 검사(높은 뱅크 BRK 목록의 정적 검사, MesenCE 열린 버스 프로브, libretro bsnes·snes9x 1장 걷기)
- [docs/dq4-savefixture-format.md](docs/dq4-savefixture-format.md): 저장 기록으로 시작하는 검사(SRAM 칸 만들기, 이어 할 자리 `7E:2033`, 저장되지 않는 것, bsnes·snes9x 에 넣기)
- [docs/dq4-battle-scene-format.md](docs/dq4-battle-scene-format.md): 전투 장면 검사(저장 기록으로 전투 직전에서 시작, 주문·약초·도망·전멸·레벨업·보스, 창 번호 `7E:0A00` 으로 맞춘 입력, 시드별 선제·기습·회심·도망 실패 분포)
- [docs/dq4-shopscene-format.md](docs/dq4-shopscene-format.md): 가게 장면 검사(이무르 가게 14장면, 창 번호 `$0A00` 으로 따라가는 입력 열, 금화·물건·장비 비트 판정)
- [docs/dq4-prologue-format.md](docs/dq4-prologue-format.md): NDS 서장(지하 검술 수련, 개구리, 신시아의 모샤스, 저녁, 1장으로 넘기기)
- [docs/dq4-rom-ledger-format.md](docs/dq4-rom-ledger-format.md): 롬 쓰기 장부(빌드 단계마다 바뀐 바이트)와 에뮬레이터 없는 바이트 검사(단계끼리 겹침, 원래 롬 덮기, 뱅크 넘기, 표 불변식, 허용 목록)
- [todo.md](todo.md): 남은 일
- [references.md](references.md): 참고 자료
- [tools/README.md](tools/README.md): 도구 사용법

그림은 [images/](images/) 에 있고 `uv run --locked python sfc/dq4/tools/dq4figures.py` 가 제작 원본에서 다시 만듭니다(롬 불필요, 필드 비교 그림만 `work/dq4-sprites/` 덤프 필요).

## 해킹 일지

순번은 dq4 트랙 전체에서 매깁니다. 나머지 번호는 [fc/dq4/](../../fc/dq4/README.md#해킹-일지) 에 있습니다.

- [2026-10-25-12: 그래픽 시안 평가와 작업 인계](journal/2026-10-25-12-graphics.md)
- [2026-10-25-18: DQ5 실측 규격으로 다시 그린 인물 스프라이트](journal/2026-10-25-18-sprites2.md)

- [2026-10-25-50: 라이안 정면을 DQ5 롬 데이터로 연결](journal/2026-10-25-50-rom-assets.md)

- [2026-10-25-51: 한글 타이틀과 DQ5 오프닝 연결](journal/2026-10-25-51-title.md)


- [2026-10-25-52: 용의 날갯짓과 구름 이동](journal/2026-10-25-52-title-animation.md)

- [2026-10-25-64: 타이틀 그림과 레이어의 연결](journal/2026-10-25-64-title-cohesion.md)

- [2026-10-25-65: 성 밑동의 구름 받침 보존](journal/2026-10-25-65-castle-cloud.md)

- [2026-10-25-66: 성 왼쪽 밑동의 구름 겹침 수정](journal/2026-10-25-66-castle-edge.md)

- [2026-10-25-67: 성 왼쪽 아래 조각 제거](journal/2026-10-25-67-castle-trim.md)

- [2026-10-25-70: 채택된 타이틀과 재사용 기준 정리](journal/2026-10-25-70-title-baseline.md)

- [2026-10-25-72: 톨네코·주인공 정면 시안과 손으로 그리기의 한계](journal/2026-10-25-72-sprite-drafts.md)

- [2026-10-26-35: 부제 장식선을 앞 구름 위로](journal/2026-10-26-35-title-ornament.md)

- [2026-10-26-36: 타이틀에 DQ4 서곡 넣기](journal/2026-10-26-36-overture.md)

- [2026-10-26-37: 모험의 서 메뉴를 한글로](journal/2026-10-26-37-menu.md)

- [2026-10-26-38: 자모를 조합해서 이름 넣기](journal/2026-10-26-38-name-entry.md)

- [2026-10-26-39: 부제 위 얼룩 제거와 앞 구름 배치 변형](journal/2026-10-26-39-title-cloud-variation.md)

- [2026-10-26-40: 자모판 방향 전환과 Start 이동](journal/2026-10-26-40-name-cursor.md)

- [2026-10-27-01: 모험의 서 지우기·기록 깨짐 메시지를 한글로](journal/2026-10-27-01-menu-messages.md)

- [2026-10-27-02: 환경 타일을 드래곤 퀘스트 색으로](journal/2026-10-27-02-environment.md)

- [2026-10-27-03: 바트랜드 성을 어두운 돌로](journal/2026-10-27-03-castle.md)

- [2026-10-27-04: 게임 안 메시지에 한글 이름 찍기와 저장 표시](journal/2026-10-27-04-name-game.md)

- [2026-10-27-05: 환경 맵을 DQ5 엔진에 넣기](journal/2026-10-27-05-environment-rom.md)

- [2026-10-27-06: 창 한글 글꼴을 원작 크기에 맞추기](journal/2026-10-27-06-font-size.md)

- [2026-10-27-07: NDS 성 곡을 DQ5 엔진으로](journal/2026-10-27-07-sound-port.md)

- [2026-10-27-08: DQ5 에 넣은 환경 맵의 물을 움직이기](journal/2026-10-27-08-environment-water.md)

- [2026-10-27-09: 게임 안 창에 한글을 넣을 자리 조사](journal/2026-10-27-09-window-text.md)

- [2026-10-27-10: 환경 맵의 문을 DQ5 문 물체로](journal/2026-10-27-10-environment-doors.md)

- [2026-10-27-11: 마을·필드 곡을 SPC 예산에 맞추기](journal/2026-10-27-11-sound-budget.md)

- [2026-10-27-12: 같은 블록 시트의 마을 16곳을 DQ5 에 넣기](journal/2026-10-27-12-environment-towns.md)

- [2026-10-27-13: 전투 곡을 곡 뒤 샘플 전송으로](journal/2026-10-27-13-sound-battle.md)

- [2026-10-27-14: 다른 마을·성 블록 시트로 넓히기](journal/2026-10-27-14-environment-castles.md)

- [2026-10-27-15: 게임 안 BG3 타일맵을 빈 VRAM 자리로 옮기기](journal/2026-10-27-15-bg3-slot.md)

- [2026-10-27-16: 항구 석축과 극장 객석](journal/2026-10-27-16-environment-harbour.md)

- [2026-10-27-17: 시퀀스를 되풀이·부르기로 묶기](journal/2026-10-27-17-sound-compact.md)

- [2026-10-27-18: 던전·탑 시트는 재질로 그리기](journal/2026-10-27-18-environment-dungeons.md)

- [2026-10-27-19: BG3 타일맵 자리 표를 넓은 실측으로 다시 정하기](journal/2026-10-27-19-bg3-slot-table.md)

- [2026-10-27-20: 필드 지형 그리기](journal/2026-10-27-20-environment-field.md)

- [2026-10-27-21: 간판 바탕과 열쇠 문, とびら 실측](journal/2026-10-27-21-environment-locks.md)

- [2026-10-27-22: 전투 뒤 물 루틴이 빈 타일을 덮던 것](journal/2026-10-27-22-environment-battle-water.md)

- [2026-10-27-23: 남은 NDS 곡을 DQ5 곡 자리 45곳에 한꺼번에](journal/2026-10-27-23-sound-all-bgm.md)
- [2026-10-27-24: 전투·레벨 업 곡을 다시 늘 두기 위한 조사](journal/2026-10-27-24-sound-resident-plan.md)
- [2026-10-27-25: 상태 창에 한글 이름 찍기](journal/2026-10-27-25-status-window-name.md)
- [2026-10-27-26: つよさ·「누구」 고르기 창의 한글 이름](journal/2026-10-27-26-list-window-name.md)
- [2026-10-27-27: 전투 메시지와 이름 색](journal/2026-10-27-27-battle-message-name.md)
- [2026-10-27-28: 도구 목록을 한글로, 게임 전송 목록을 비켜 가기](journal/2026-10-27-28-item-list.md)
- [2026-10-27-29: 주문 목록과 전투 NMI](journal/2026-10-27-29-spell-list.md)
- [2026-10-27-30: 명령 창 고정 문구](journal/2026-10-27-30-window-fixed-text.md)
- [2026-10-27-31: 창 제목과 전투 명령 창](journal/2026-10-27-31-window-titles.md)
- [2026-10-27-32: つよさみる 에서 멈추던 주문 훅](journal/2026-10-27-32-spell-hook-crash.md)
- [2026-10-28-01: 메시지 캔버스와 명령 창 전용 칸](journal/2026-10-28-01-message-canvas.md)
- [2026-10-28-02: 전투 몬스터 목록과 전투 도구 창](journal/2026-10-28-02-battle-list.md)
- [2026-10-28-03: 가게 창](journal/2026-10-28-03-shop.md)
- [2026-10-28-04: 작전 창](journal/2026-10-28-04-tactics.md)
- [2026-10-28-05: 강함 보기의 빈 주문 칸과 라벨](journal/2026-10-28-05-status-blank.md)
- [2026-10-28-06: 강함 보기 라벨과 창 타일맵 전송](journal/2026-10-28-06-status-label.md)
- [2026-10-28-07: 교회와 맡기는 곳 창](journal/2026-10-28-07-church.md)
- [2026-10-28-08: 게임 안 예/아니요 창](journal/2026-10-28-08-yes-no.md)
- [2026-10-28-09: 강함 보기의 성별 값](journal/2026-10-28-09-gender.md)
- [2026-10-28-10: 장비 창과 남은 가나](journal/2026-10-28-10-equip.md)
- [2026-10-29-01: 필드에서 가나 칸을 슬롯으로](journal/2026-10-29-01-kana-slots.md)
- [2026-10-29-02: 가나가 남은 창](journal/2026-10-29-02-kana-windows.md)
- [2026-10-29-03: 한글 없는 이름을 가나 그림으로](journal/2026-10-29-03-kana-names.md)
- [2026-10-29-04: 한 줄 창과 전투에서 미룬 창 타일맵](journal/2026-10-29-04-line-windows.md)
- [2026-10-29-05: 가게 팔기 목록과 VBlank 를 넘긴 대기열](journal/2026-10-29-05-vblank-queue.md)
- [2026-10-29-06: 주문 연출과 전투 이름 칸](journal/2026-10-29-06-spell-fx.md)
- [2026-10-29-07: 공용 창 62 는 게임 안에서 열리나](journal/2026-10-29-07-shared-window.md)
- [2026-10-29-08: 창 글자 깨짐 검사](journal/2026-10-29-08-window-check.md)
- [2026-10-29-09: 가나 이름을 Galmuri9 로](journal/2026-10-29-09-kana-names.md)
- [2026-10-29-10: 대열 바꾸기 창](journal/2026-10-29-10-formation.md)
- [2026-10-29-11: 가나 칸을 이름 길이만큼](journal/2026-10-29-11-kana-alloc.md)
- [2026-10-29-12: 창 문구 다듬기](journal/2026-10-29-12-wording.md)
- [2026-10-29-13: 창 제목 바탕이 어두운 것](journal/2026-10-29-13-title-color.md)
- [2026-10-29-14: 타이틀 구름 모서리·로고 둘레·부제 정리](journal/2026-10-29-14-title-cleanup.md)
- [2026-10-29-15: 경험치 줄과 HP와 MP 창](journal/2026-10-29-15-exp-row.md)
- [2026-10-29-16: 전투·레벨 업 곡을 다시 늘 두기](journal/2026-10-29-16-sound-resident.md)
- [2026-10-29-17: 모험의 서 기록 목록의 빈 칸](journal/2026-10-29-17-save-list.md)
- [2026-10-30-01: 환경 맵 훅이 지우던 Y 상위 바이트](journal/2026-10-30-01-env-hook-y.md)
- [2026-10-30-02: 맵 곡을 곡 앞 샘플만 먼저 보내기](journal/2026-10-30-02-sound-mapstream.md)
- [2026-10-30-03: バトランド 성·イムル 을 새 그룹으로 옮겨 출구 잇기](journal/2026-10-30-03-group-links.md)
- [2026-10-30-04: 맵 곡에서 빠지는 음 없애기와 배·동굴 음색](journal/2026-10-30-04-sound-nolate.md)
- [2026-10-30-05: 타이틀 부제 문양 옆의 세로 잡티](journal/2026-10-30-05-title-speck.md)
- [2026-10-30-06: バトランド 성·イムル 에 FC 인물 놓기](journal/2026-10-30-06-group-people.md)
- [2026-10-30-07: SPC 전송 빠르게](journal/2026-10-30-07-sound-fastrecv.md)
- [2026-10-30-08: バトランド 성·イムル 의 가게·여관·교회](journal/2026-10-30-08-group-shops.md)
- [2026-10-30-09: 새 게임을 DQ4 1장 첫머리로](journal/2026-10-30-09-chapter1.md)
- [2026-10-30-10: 맵을 불러오는 동안의 CPU](journal/2026-10-30-10-sound-mapload.md)
- [2026-10-30-11: 1장의 우물·탑·`41`·우물 아래를 새 그룹으로](journal/2026-10-30-11-ch1-dungeons.md)
- [2026-10-30-12: 1장을 FC 처럼 검은 화면에서 시작하기](journal/2026-10-30-12-chapter1-opening.md)
- [2026-10-30-13: 메뉴까지 이어지는 서곡과 소리 없는 1장 시작](journal/2026-10-30-13-opening-sound.md)
- [2026-10-30-14: 인물 대사로 덮은 DQ5 메시지를 다른 길로 띄우는지](journal/2026-10-30-14-pool-messages.md)
- [2026-10-30-15: 모험의 서 곡을 DQ4 판으로](journal/2026-10-30-15-menu-intermezzo.md)
- [2026-10-30-16: 새 게임에서 메뉴 곡 끄기](journal/2026-10-30-16-newgame-stop-song.md)
- [2026-10-30-17: 던전 시트의 벼랑·비탈을 모양대로](journal/2026-10-30-17-cliff-shapes.md)
- [2026-10-30-18: 메뉴를 나갈 때 메뉴 곡 줄이기](journal/2026-10-30-18-menu-exit-fade.md)
- [2026-10-30-19: 받침을 보고 조사를 고르는 코드와 시스템 메시지](journal/2026-10-30-19-josa.md)
- [2026-10-30-20: 메시지의 물건·주문 이름을 한글로](journal/2026-10-30-20-msg-names.md)
- [2026-10-30-21: 1장 새 그룹의 상자·タンス·つぼ](journal/2026-10-30-21-ch1-chests.md)
- [2026-10-30-22: 구름 가장자리와 밝은 바위 면](journal/2026-10-30-22-cloud-stripes.md)
- [2026-10-30-23: 이무르의 도구점 간판과 분수](journal/2026-10-30-23-imuru-fountain.md)
- [2026-10-30-24: 필드 입구마다 도착을 고르는 훅](journal/2026-10-30-24-entrance-hook.md)
- [2026-10-30-25: 맵 곡 시작 당기기](journal/2026-10-30-25-sound-mapstart.md)
- [2026-10-30-26: FC 그룹마다 가게·여관 키를 따로 주는 훅](journal/2026-10-30-26-shop-key.md)
- [2026-10-30-27: 곡 번호 늘리기](journal/2026-10-30-27-sound-slots.md)
- [2026-10-30-28: 문 물체 항목을 뱅크 3D 로](journal/2026-10-30-28-door-bank.md)
- [2026-10-30-29: 서장의 산골 마을을 새 그룹 3C 로](journal/2026-10-30-29-prologue-village.md)
- [2026-10-30-30: 동굴 바닥의 마물 부조](journal/2026-10-30-30-floor-relief.md)
- [2026-10-30-31: 사운드 빌드 캐시](journal/2026-10-30-31-sound-buildcache.md)
- [2026-10-30-32: 서장의 수련과 마을 사람](journal/2026-10-30-32-prologue-events.md)
- [2026-10-30-33: 보스 곡 당기기와 필드 출구 실측](journal/2026-10-30-33-sound-boss.md)
- [2026-10-30-34: 서장 끝에서 1장으로](journal/2026-10-30-34-prologue-end.md)
- [2026-10-30-35: 곡 첫 음이 나뉘는 까닭](journal/2026-10-30-35-sound-firstkon.md)
- [2026-10-30-36: 서장을 한 번에 걷는 검사](journal/2026-10-30-36-prologue-walk.md)
- [2026-10-30-37: 세이브스테이트에서만 본 소리 문제를 전원부터 다시 재기](journal/2026-10-30-37-sound-poweron.md)
- [2026-10-30-38: 저녁 식탁에 앉기와 명령 08](journal/2026-10-30-38-prologue-supper.md)
- [2026-10-30-39: FC 필드 0 을 DQ5 세계 0 에](journal/2026-10-30-39-field-world0.md)
- [2026-10-30-40: 세이브스테이트 실측이 틀리던 까닭](journal/2026-10-30-40-sound-statelua.md)
- [2026-10-30-41: 서장 인물이 저절로 말을 걸기](journal/2026-10-30-41-prologue-autotalk.md)
- [2026-10-30-42: 보스 곡도 앞부분·본체로 나누기](journal/2026-10-30-42-sound-bosschain.md)
- [2026-10-30-43: 마을 곡이 카지노 곡이던 것](journal/2026-10-30-43-village-song.md)
- [2026-10-30-44: 1장 인물 대사를 한글로](journal/2026-10-30-44-ch1-talk.md)
- [2026-10-30-45: 지금 롬으로 지연 다시 재기](journal/2026-10-30-45-sound-delaycheck.md)
- [2026-10-30-46: 왕좌의 방 밤 인물](journal/2026-10-30-46-ch1-night.md)
- [2026-10-30-47: 2장 성과 두 마을을 한 그룹에, 대사는 3200 뒤에](journal/2026-10-30-47-ch2-bundle.md)
- [2026-10-30-48: 필드를 DQ4 그림으로](journal/2026-10-30-48-field-gfx.md)
- [2026-10-30-49: 맵을 옮기면 곡이 앞부분 뒤 멈추던 버그](journal/2026-10-30-49-sound-chainfix.md)
- [2026-10-30-50: ドラゴン 에서 내릴 때 필드 곡 잇기](journal/2026-10-30-50-sound-dragon.md)
- [2026-10-30-51: FC 필드 1·3 을 DQ5 세계 1·2 에](journal/2026-10-30-51-field-worlds12.md)
- [2026-10-30-52: 이무르의 밤, 프레아, 감옥 재회](journal/2026-10-30-52-ch1-imuru-night.md)
- [2026-10-30-53: 배와 마법 융단의 곡 전환 재기](journal/2026-10-30-53-sound-vehicles.md)
- [2026-10-30-54: 필드 바다를 DQ4 물결로](journal/2026-10-30-54-field-sea.md)
- [2026-10-30-55: 우물 아래로 떨어지기, 아이 목소리, 호이민 합류](journal/2026-10-30-55-ch1-well.md)
- [2026-10-30-56: そらとぶくつ 로 탑에, 아이 납치, 탑에서 뛰어내리기](journal/2026-10-30-56-ch1-tower.md)
- [2026-10-30-57: 필드의 ルーラ·배·조우를 FC 대로](journal/2026-10-30-57-field-behaviour.md)
- [2026-10-30-58: 탑 위 보스](journal/2026-10-30-58-ch1-boss.md)
- [2026-10-30-59: 곡을 바꿀 때 함께 쓰는 샘플 살리기](journal/2026-10-30-59-sound-keep.md)
- [2026-10-30-60: 보스 뒤의 인물 목록, 병사의 보고, 아이들의 귀가](journal/2026-10-30-60-ch1-afterboss.md)
- [2026-10-30-61: 탈것을 타는 동안 맵 곡 샘플 미리 받기](journal/2026-10-30-61-sound-prefetch.md)
- [2026-10-30-62: 왕에게 보고, 1장 끝과 2장 제목](journal/2026-10-30-62-ch1-end.md)
- [2026-10-30-63: 1장 보스를 FC 원작 몬스터로](journal/2026-10-30-63-ch1-bossmon.md)
- [2026-10-30-64: 3장 마을 셋을 새 그룹에, 새 맵 레코드는 여러 자리에](journal/2026-10-30-64-ch3-bundle.md)
- [2026-10-30-65: 효과음이 시퀀스 칸을 얻지 못하던 것](journal/2026-10-30-65-sound-sfxslot.md)
- [2026-10-30-66: 전투 메시지 한글](journal/2026-10-30-66-battle-text.md)
- [2026-10-30-67: 1장 연출 — 왕의 귀환, 선물과 필드 레벨업, 잡힌 아이와 철창, 이무르 귀가](journal/2026-10-30-67-ch1-scenes.md)
- [2026-10-30-68: 효과음 이식 첫걸음, 잡음 효과음 셋](journal/2026-10-30-68-sound-sfx.md)
- [2026-10-30-69: 타이틀 차분 자료를 한 벌씩 모아 36~39 비우기](journal/2026-10-30-69-title-pack.md)
- [2026-10-31-01: 왕 앞까지 저절로 걷기와 레벨업 능력치 줄](journal/2026-10-31-01-ch1-levelup.md)
- [2026-10-31-02: 전투 메시지 한글의 남은 것](journal/2026-10-31-02-battle-text2.md)
- [2026-10-31-03: 풀 C 도 되살리기](journal/2026-10-31-03-battle-shadow.md)
- [2026-10-31-04: 왕의 선물을 상태 창으로 — BRK 95 가 창을 못 연 까닭](journal/2026-10-31-04-ch1-statwin.md)
- [2026-10-31-05: 레벨업 동안 능력치 창 남기기](journal/2026-10-31-05-ch1-statkeep.md)
- [2026-10-31-06: 라이안은 주문을 배우지 않는다](journal/2026-10-31-06-ch1-nospell.md)
- [2026-10-31-07: 게임 안 창에서 방향키 겹침 고치기](journal/2026-10-31-07-menu-cursor.md)
- [2026-10-31-08: 전투 레벨업에서 멈추던 줄 올림 고리](journal/2026-10-31-08-battle-scroll.md)
- [2026-10-31-09: 전투 글의 긴 줄과 한 프레임 옛 그림](journal/2026-10-31-09-battle-wrap.md)
- [2026-10-31-10: 전투 글 숫자 간격과 줄 넘김 폭](journal/2026-10-31-10-battle-digits.md)
- [2026-10-31-11: 개구리는 연못에서 뛰어오른다](journal/2026-10-31-11-prologue-frog.md)
- [2026-10-31-12: 1장 롬에 상자가 없었다](journal/2026-10-31-12-ch1-chests.md)
- [2026-10-31-13: 전멸하면 서장 마을로 돌아갔다](journal/2026-10-31-13-ch1-return.md)
- [2026-10-31-14: 41 동굴이 한쪽으로만 통했다](journal/2026-10-31-14-cave-both-ways.md)
- [2026-10-31-15: 가게를 FC 값으로, てつのやり 는 빌린 자리로](journal/2026-10-31-15-shop-prices.md)
- [2026-10-31-16: 1장 던전에 조우와 동굴 곡을 넣었다](journal/2026-10-31-16-ch1-dungeons.md)
- [2026-10-31-17: 진행에 따라 바뀌는 1장 대사와 손님 호이민](journal/2026-10-31-17-ch1-talks.md)
- [2026-10-31-18: 동료 이름 「호이민」](journal/2026-10-31-18-companion-name.md)
- [2026-10-31-19: 호이민이 FC 가중치로 행동을 고른다](journal/2026-10-31-19-hoimin-ai.md)
- [2026-10-31-20: 1장 끝에서 2장 첫머리로](journal/2026-10-31-20-ch2-start.md)
- [2026-10-31-21: 호이민이 누구를 고칠지 FC 에서 쟀다](journal/2026-10-31-21-hoimin-heal-target.md)
- [2026-10-31-22: 1장 연출 깃발을 DQ5 가 안 쓰는 자리로 옮겼다](journal/2026-10-31-22-ch1-flag.md)
- [2026-10-31-23: 1장 첫머리의 검은 틈은 이미 FC 보다 짧았다](journal/2026-10-31-23-ch1-black-gap.md)
- [2026-10-31-24: 가게·여관·교회와 도구 사용 메시지 한글](journal/2026-10-31-24-shop-inn-church-text.md)
- [2026-10-31-25: 우물 아래 조우 켬/끔과 던전 조우율을 FC 에 맞췄다](journal/2026-10-31-25-well-encounter-switch.md)
- [2026-10-31-26: 호이민·프레아·아이들이 뒤따라 걷게 했다](journal/2026-10-31-26-ch1-followers.md)
- [2026-10-31-27: 1장 진행 대사, 예·아니요 갈래, 합류 팡파르, 창살 너머 말 걸기](journal/2026-10-31-27-ch1-talk-progress.md)
- [2026-10-31-28: 1장을 한 번에 걷는 검사](journal/2026-10-31-28-ch1-walk.md)
- [2026-10-31-29: 산트하임 성을 빠져나가 두 사람과 떠나기까지](journal/2026-10-31-29-ch2-castle.md)
- [2026-10-31-30: 상자·열쇠 문·여관·교회·가게 갈래 메시지를 게임에서 띄웠다](journal/2026-10-31-30-sysmsg-scenes.md)
- [2026-10-31-31: 곡을 얹은 1장 롬이 전투 뒤 멈추던 것](journal/2026-10-31-31-boss-hang.md)
- [2026-10-31-32: 4장 마을 넷과 동굴을 새 그룹에, 자리 늘리기](journal/2026-10-31-32-ch4-bundle.md)
- [2026-10-31-33: 1A 를 다시 넣는다던 것은 분기 범위였다](journal/2026-10-31-33-keep-requeue.md)
- [2026-10-31-34: 1장·서장이 DQ5 메시지와 깃발을 덮지 않게 자리를 옮겼다](journal/2026-10-31-34-ch1-slots.md)
- [2026-10-31-35: 남은 2장 맵을 그룹 45 에](journal/2026-10-31-35-ch2-maps.md)
- [2026-10-31-36: 1장 깃발 둘은 레ヌール城 자리에 그대로 둔다](journal/2026-10-31-36-ch1-flag-0405.md)
- [2026-10-31-37: 필드 조우율을 전투까지 거리로 맞추고 우물 깃발을 불러오기·전멸에서 껐다](journal/2026-10-31-37-field-encounter-distance.md)
- [2026-10-31-38: 왕의 선물 레벨업 곡, 뒤따라오는 성 앞 노인, 맵을 다시 불러온 뒤의 줄](journal/2026-10-31-38-ch1-fanfare-oldman.md)
- [2026-10-31-39: 가게 「누가」 창이 메시지 창에 비친 까닭](journal/2026-10-31-39-shop-who-window.md)
- [2026-10-31-40: 1장을 저장하고 이어 해도 진행이 그대로다](journal/2026-10-31-40-ch1-save-continue.md)
- [2026-10-31-41: 전투 메시지 418개와 이름 뒤 조사, 넘치는 줄 나누기](journal/2026-10-31-41-battle-josa-wrap.md)
- [2026-10-31-42: 빌린 전용 칸을 명령 창 문구가 덮던 것](journal/2026-10-31-42-fixed-cell-lend.md)
- [2026-10-31-43: NDS 시트로 줄인 장 주인공과 장마다 그림 고르기](journal/2026-10-31-43-leader-sprite.md)
- [2026-10-31-44: 성 앞 상자, 맡기는 곳 대사, 서술문 15칸](journal/2026-10-31-44-ch1-chest-bank-narration.md)
- [2026-10-31-45: 막힌 셀을 피해 걷는 성 앞 노인](journal/2026-10-31-45-ch1-oldman-reroute.md)
- [2026-10-31-46: 던전 조우를 FC 처럼 두 셀에 한 번, 방이 바뀐 걸음은 85/256](journal/2026-10-31-46-dungeon-step-chance.md)
- [2026-10-31-47: 넘친 목록 이름을 목록 창 밑에 숨기기](journal/2026-10-31-47-list-overflow-hidden.md)
- [2026-10-31-48: 서장·1장 인물을 NDS 시트로 바꾸다](journal/2026-10-31-48-ch1-people.md)
- [2026-10-31-49: 조우는 3/4, 전투 보상은 4/3 배](journal/2026-10-31-49-encounter-tune.md)
- [2026-10-31-50: 뒷걸음질하던 옆모습과 뭉개진 눈](journal/2026-10-31-50-people-facing-eyes.md)
- [2026-10-31-51: 검사끼리 배터리 기록을 나눠 쓰지 않게](journal/2026-10-31-51-mesen-saves.md)
- [2026-10-31-52: 텐페, 바구니에 실려 제단으로](journal/2026-10-31-52-ch2-tempe.md)
- [2026-10-31-53: 청취로 곡 세기·음색 맞추기](journal/2026-10-31-53-sound-listening.md)
- [2026-10-31-54: 또렷한 1×2 눈, 주인공을 보는 신시아, 잔디 위의 개구리](journal/2026-10-31-54-eyes-shinsia-frog.md)
- [2026-10-31-55: A 를 두 번 눌러야 넘어가던 메시지](journal/2026-10-31-55-double-a.md)
- [2026-10-31-56: 말을 걸면 돌아보는 마을 사람, 주인공 줄에 앉는 개구리](journal/2026-10-31-56-npc-turn-frog-row.md)
- [2026-10-31-57: NDS 효과음을 늘 두는 효과음 파형 자리에](journal/2026-10-31-57-sound-sfx-wave.md)
- [2026-10-31-58: 항아리 바로 아래에서 가려지던 머리 줄](journal/2026-10-31-58-pot-head-row.md)
- [2026-10-31-59: 레벨업 마지막 줄의 A 두 번](journal/2026-10-31-59-levelup-last-line.md)
- [2026-10-31-60: 맵 그룹마다 인물 팔레트를 따로](journal/2026-10-31-60-group-palettes.md)
- [2026-10-31-61: 1장에서 끝내고 타이틀로](journal/2026-10-31-61-ch1-ending.md)
- [2026-10-31-62: 반 블록 걸친 문과 걸어서 여는 문](journal/2026-10-31-62-door-walk-open.md)
- [2026-10-31-63: 무기 효과음을 전투 곡에 붙이다](journal/2026-10-31-63-sound-sfx-weapon.md)
- [2026-10-31-64: 아리나 일행과 2장 인물을 NDS 시트로](journal/2026-10-31-64-ch2-people.md)
- [2026-10-31-65: 서장 수련의 칼 여섯 합](journal/2026-10-31-65-prologue-sparring.md)
- [2026-10-31-66: 5장 시작 지역(브랑카·나무꾼 집·터널)을 새 그룹에](journal/2026-10-31-66-ch5-start.md)
- [2026-10-31-67: 무기마다 NDS 타격음](journal/2026-10-31-67-sound-sfx-weapon2.md)
- [2026-10-31-68: 끝난 곡의 샘플이 SPC 칸을 잡던 것](journal/2026-10-31-68-sound-stale-samples.md)
- [2026-11-01-01: 메시지 덩어리를 둘째 자리로 잇기](journal/2026-11-01-01-msg-second-area.md)
- [2026-11-01-02: 서장·1장 인물 확인과 멈춘 걸음 살리기](journal/2026-11-01-02-people-check.md)
- [2026-11-01-03: 타이틀 뒤 메뉴가 늦게 뜨던 것](journal/2026-11-01-03-menu-delay.md)
- [2026-11-01-04: 서장에서 저절로 말을 걸기까지 늘어지던 것](journal/2026-11-01-04-prologue-talk-delay.md)
- [2026-11-01-05: 곡이 줄어들 때 느려지고 뭉개지던 것](journal/2026-11-01-05-sound-tick-scan.md)
- [2026-11-01-06: 문·여관·개구리 소리와 뒤바뀐 맞음·빗나감](journal/2026-11-01-06-sound-sfx-door.md)
- [2026-11-01-07: 타이틀 그림 자료를 42~47 로 옮겨 30~3F 를 비우기](journal/2026-11-01-07-title-high.md)
- [2026-11-01-08: 연못 분수를 물과 함께 움직이기](journal/2026-11-01-08-fountain.md)
- [2026-11-01-09: 이무르 37/01 계단 앞에서 멈추던 것 다시 재기](journal/2026-11-01-09-imuru-3701.md)
- [2026-11-01-10: 효과음을 입구에서 돌려 부르다](journal/2026-11-01-10-sound-sfx-remap.md)
- [2026-11-01-11: snes9x 에서 서장이 멈추던 BRK 16 의 DB](journal/2026-11-01-11-spar-brk-db.md)
- [2026-11-01-12: 침대에서 자는 인물 눕히기](journal/2026-11-01-12-beds.md)
- [2026-11-01-13: 왕좌의 방 계단의 왕, 성 마을 도착 칸, 롬 내부 제목](journal/2026-11-01-13-throne-stair-title.md)
- [2026-11-01-14: 일행 그림을 다시 실을 때 깨지던 주인공과 호이민](journal/2026-11-01-14-party-reload.md)
- [2026-11-01-15: 맵 밖을 FC 바깥 블록으로 채우기](journal/2026-11-01-15-map-outside.md)
- [2026-11-01-16: 잠긴 문에 부딪힘 소리](journal/2026-11-01-16-locked-door-bump.md)
- [2026-11-01-17: 주인공을 가두던 성 앞 노인과 노인 그림](journal/2026-11-01-17-ch1-oldman-push.md)
- [2026-11-01-18: 가게 동료 창의 「소지 중 ↔ 없음」 이 바뀔 때 깨지던 글자](journal/2026-11-01-18-shop-status-tear.md)
- [2026-11-01-19: 운에 기대지 않는 헤드리스 검사와 걸음 전투 검사](journal/2026-11-01-19-deterministic-checks.md)
- [2026-11-01-20: 서장 저녁 장면을 메시지 창 위로](journal/2026-11-01-20-supper-view.md)
- [2026-11-01-21: 젊은 남자로 보이던 대머리 노인들](journal/2026-11-01-21-bald-oldmen.md)
- [2026-11-01-22: 벽에 막히면 줄을 맞추는 성 앞 노인](journal/2026-11-01-22-ch1-oldman-lineup.md)
- [2026-11-01-23: 가게 목록의 값에 「G」, 팔기 목록에 파는 값](journal/2026-11-01-23-shop-price-g.md)
- [2026-11-01-24: 저녁의 주인공 뒷모습과 누운 인물의 방향](journal/2026-11-01-24-face-up.md)
- [2026-11-01-25: 가게 동료 창에 가진 개수](journal/2026-11-01-25-shop-held-count.md)
- [2026-11-01-26: 여관 징글 앞당기기와 물건을 찾을 때의 소리](journal/2026-11-01-26-inn-jingle-item-sound.md)
- [2026-11-01-27: 가게에서 사기 전에 확인](journal/2026-11-01-27-shop-buy-confirm.md)
- [2026-11-01-28: snes9x·bsnes 로 1장 끝까지 걷기와 회귀 가드](journal/2026-11-01-28-compat-walk.md)
- [2026-11-01-29: 주인공이 선 자리 때문에 멈추는 사건](journal/2026-11-01-29-hero-block-events.md)
- [2026-11-01-30: 가게에서 도구를 여러 개 사기](journal/2026-11-01-30-shop-multi-buy.md)
- [2026-11-01-31: 호환성 검사 코어를 고정 커밋에서 빌드하기](journal/2026-11-01-31-compat-cores.md)
- [2026-11-01-32: 가게에서 같은 물건을 여러 개 팔기](journal/2026-11-01-32-shop-multi-sell.md)
- [2026-11-01-33: 장착 중인 장비를 팔 때 한 줄 알림](journal/2026-11-01-33-shop-equip-warn.md)
- [2026-11-01-34: 주인공과 인물이 겹쳐 보이는 사건](journal/2026-11-01-34-sprite-overlap.md)
- [2026-11-01-35: 가게에서 취소하면 제 목록으로](journal/2026-11-01-35-shop-cancel-back.md)
- [2026-11-01-36: 가게 개수 창을 최대까지만](journal/2026-11-01-36-shop-qty-cap.md)
- [2026-11-01-37: 저장 기록으로 검사 시작하기](journal/2026-11-01-37-save-fixture.md)
- [2026-11-01-38: 팔기에서 값 매기는 말 빼기](journal/2026-11-01-38-shop-sell-lines.md)
- [2026-11-01-39: 롬 쓰기 장부와 바이트 검사](journal/2026-11-01-39-rom-ledger.md)
- [2026-11-01-40: 개수 창에서 쓰는 돈·남는 돈 보이기](journal/2026-11-01-40-shop-qty-preview.md)
- [2026-11-01-41: 필드에서 반투명하던 주인공](journal/2026-11-01-41-field-hero-translucent.md)
- [2026-11-01-42: 가게 장면 검사](journal/2026-11-01-42-shop-scene.md)
- [2026-11-01-43: 전투 상태 창 오른쪽 위 모서리](journal/2026-11-01-43-battle-status-corner.md)
- [2026-11-01-44: 필드 전투 메시지의 몬스터 이름 한글화](journal/2026-11-01-44-battle-monster-names.md)
- [2026-11-01-45: 전투 장면 검사](journal/2026-11-01-45-battle-scene.md)
