; 게임 안 창(상태 창·전투 상태 창·목록)과 전투 메시지의 한글 이름. dq4windowname.py 가 정의(!wn_*)를 앞에 붙여 asar 로 넣는다.
; 형식은 sfc/dq4/docs/dq4-window-text-format.md 「상태 창 이름」.
;
; 04:ABCF(일행 열 창)와 04:B79B(목록·つよさ 류의 공통 출력)는 이름 4바이트를 그대로 BG3 타일로 찍는다. 한글 표시 바이트(85~9A, 10~7E)면 대신 Galmuri9 글리프(뱅크 62~,
; dq4nameentry 의 16×16 칸)를 10점 간격으로 40점 띠에 겹쳐, 이름 줄 5칸과 그 위 테두리 줄 5칸(글자 맨 윗줄을 테두리 타일
; 7줄째에 합성)을 BG3 글자 칸 180~1CF 에 그려 우리 전송 대기열로 올린다. 칸은 타일맵 버퍼 자리마다 열 개씩, 여덟 자리를
; 돌려 쓴다.

lorom

; 일행 열 창은 사람마다 6칸(이름 5 + 사이 1). 원래는 5칸.
org $04A394
    ADC #$06
org $04A3A4
    SBC #$06
org $04B18E
    ADC #$000C
; 너비 6 일 때 04:ABCF 로 가던 지름길을 너비 7 에서도 탄다.
org $04AB58
    CMP #$07

org $04ABCF
    JML WnName
    NOP
    NOP
    NOP
; 쓰러짐·독 등으로 이름에 색($ED)을 입히는 길.
org $04AB73
    JML WnNameAttr
    NOP
    NOP
    NOP

org $04B79B
    JML WnList

; 전투 메시지: 이름을 글 큐 0ECB 로 옮기는 자리와, 큐의 바이트를 글 버퍼 아래 줄에 쓰는 자리.
org $24A83C
    JML WnBattle
org $24A4E0
    JML WnBattleChar
    NOP
    NOP
; NMI 가 $1944 작업(필드 00:8926, 전투 00:8952 등)으로 가기 전에 우리 대기열을 보낸다. 게임 전송 목록은 게임이
; 프레임 끝에 한 번 보내는 장치($1946 = 00:8CEF, $19 bit2)라, 창을 그리는 도중에 끼어들면 메뉴 흐름이 어긋났다.
org $00887C
    JMP $FFA1
org $00FFA1
    JML WqNmiEntry
    JMP ($1944)
; NMI 끝(작업들이 VBlank 일을 마친 뒤 모이는 00:887F 다음). LDA $1E / STA $4200 자리
org $008885
    JML WtVisTail
    NOP

; 석 자 출력 D1(강함 보기의 성별, 이름 표 2)의 끝 PHX / LDX #$0000 / LDA #$03 / STA $00 / BRL $B7A3 을, 길이 3 으로
; 04:B808 이름 표 길에 넘긴다. 두 고리 모두 PLX / BRL $BFF2 로 끝난다.
org $04B7D7
    LDA #$03
    STA $00
    db $82 : dw $B808-$B7DE     ; BRL $B808 (이 asar 는 BRL $주소 를 거리로 바꾸지 않음)
    NOP #4
; 장비 비교 창 제목의 물건 이름. PHB / LDA #$7E / PHA / PLB / LDX #$0000 / BRL $ABD6
org $04AA79
    JML WnTitleName
    NOP #7
; 이름 표 문자열(도구 이름 등)을 글자마다 04:B235 로 찍는 자리. PHX / SEP #$10 / LDX #$00
org $04B808
    JML WnText
    NOP
; 주문 목록(D6)이 이름을 다섯 글자 고정으로 찍는 자리. PHX / LDX #$0000 / LDA #$05 / STA $00 / BRL $B7A3
; 04:BD4F·04:BD9F 도 PHX 를 한 뒤 BRL 로 04:B8F3 에 들어오므로, PHX 다음 자리를 바꾼다.
org $04B8F3
    JML WnSpell
; 전투 몬스터 목록(E6)이 이름을 아홉 글자 고정으로 찍는 자리
org $04BC08
    JML WnMonster
; 전투 작전 창(E5)이 작전 이름을 넉 자씩 두 줄로 찍는 자리. PHX / SEP #$10 / LDX #$00
org $04BB70
    JML WnTactic

; 모험의 서 기록 목록(창 5D)의 코드 DC(04:B9A7)가 빈 칸이면 04:B9FB 의 10바이트를 거꾸로 JSR $B235 로 찍는 고리
org $04B9EB
    JML WnEmptySlot

; 창 바이트 갈래(메뉴 패치의 JSL). 고정 문구 접두를 먼저 가르고, 나머지는 원래 대상으로.
org $04B11E
    JSL WnPrefix

; 걷는 메시지 캔버스(7E:5800 의 평면 0 → 칸 096~)를 보내는 NMI 작업. PHB / PHK / PLB / LDA #$7E 의 첫 네 바이트
org $008E9E
    JML WqClean

; 창 제목 글자(04:AA10 고리의 B0 미만 바이트). STA $00 / PHB / LDA #$7E 자리
org $04AC25
    JML WnTitle

; 글 버퍼를 타일맵 버퍼(7E:5546~)의 낮은 바이트로 옮기는 자리
org $24A5E9
    JSL WnBattleCell
    NOP
    NOP
    NOP

!wn_keys  = $1C40           ; 8 워드: 자리마다 이름 줄 버퍼 주소(7E), 0 = 빈 자리
!wn_above = $1C50           ; 8 × 5 워드: 그 위 줄의 원래 타일맵 낱말
!wn_next  = $1CA0           ; 다음에 내줄 자리
!wn_band  = $1CA2           ; 띠 9줄 × 6바이트(줄 1~9, 40점 + 여유 8점)
!wn_cell  = $1CD8           ; 글리프 하나 32바이트(열 0 16줄, 열 1 16줄)
!wn_glyph = $1CF8           ; 4 워드: 글리프 번호, FFFF = 없음
!wn_y     = $1D00           ; 들어올 때 Y
!wn_key   = $1D02
!wn_slot  = $1D04           ; 자리 × 2
!wn_tile  = $1D06           ; 그 자리의 첫 타일 번호
!wn_t0    = $1D08
!wn_t1    = $1D09
!wn_t2    = $1D0A
!wn_s     = $1D0C           ; 밀 점 수(워드)
!wn_o     = $1D0E           ; 띠 안 바이트 자리(워드)
!wn_k     = $1D10           ; 글자 번호 × 2
!wn_c     = $1D12           ; 칸(워드)
!wn_r     = $1D14           ; 줄(워드)
!wn_base  = $1D16           ; 합성 바탕 타일(워드)
!wn_ptr   = $1D18           ; 타일맵 버퍼 포인터: 일행 열 창은 $DC, 목록은 $E0
!wn_mode  = $1D1A           ; 0 = 일행 열 창(04:ABF4 로), 1 = 목록(04:BFF2 로)
!wn_step  = $1D1C           ; 목록에서 이름 뒤 Y 를 나아갈 바이트 수
!wn_attr  = $1D42           ; 이름 줄 타일맵 높은 바이트(색). 0 이면 버퍼에 있던 것을 살림
!wt_stack = $1D83           ; 전용 스택 맨 위(1D44~1D83). 협동식 작업마다 낮은 WRAM 에 작은 스택이 있어, 그 스택을 깊게 쓰지 않는다
!wt_keys  = $3D70           ; 슬롯 수만큼 워드(7E, 30개): 슬롯마다 버퍼 자리(!wt_buf + Y)
!wt_ages  = $3D14           ; 슬롯 수만큼 워드(30개까지): 마지막으로 쓴 때, 0 = 빈 슬롯
!wt_need  = $3D6C           ; 0 = 작은 슬롯(네 열까지), 1 = 중간(일곱 열까지), 2 = 큰 슬롯
!wt_first = $3D6E           ; 빈 슬롯·오래된 슬롯을 찾기 시작할 자리(슬롯 × 2)
!wt_buf   = $3DD0           ; 타일맵 버퍼 포인터: 목록·창 본문은 $E0, 창 제목은 $DC
!wt_field = $3DD2           ; 0 = 전투(NMI 작업 $1944 = 00:8952). 필드 전용 슬롯을 쓸지
!wt_nslot = 30
!wt_nkana = 12              ; 앞 12개는 가나 칸을 길이만큼 잘라 쓰는 항목(첫 칸·칸 수는 RAM), 뒤 18개는 캔버스 안 고정 슬롯
!wt_kbase = $3DD8           ; 가나 항목마다 1바이트: 첫 칸
!wt_klen  = $3DE4           ; 가나 항목마다 1바이트: 칸 수(열 수 × 2)
!wt_occ   = $3DF0           ; 13바이트: 가나 칸 010~077 의 쓰는 칸 비트(WtOcc 가 그때그때 만듦)
!wt_tmp   = $3DFE           ; WtAlloc 안에서만: 찾는 칸 수, 찾은 첫 칸
!wt_slot2 = $3D56           ; 이번에 쓴 슬롯 × 2, FFFF = 명령 창 전용 칸
!wt_k     = $3D58           ; 그리는 고정 문구 번호
!wt_dirty = $3DD4           ; 2 워드: 슬롯마다 1비트, 메시지 캔버스 안에 그림을 올린 슬롯
!wt_age   = $3D50           ; 쓸 때마다 하나씩
!wt_mode  = $3D52           ; 고정 글자 수: 0 = 04:B808(길이 $00), 5 = 04:B8F3(주문), 9 = 04:BC08(몬스터)
!wt_lastx = $3D54           ; 원래 루틴이 마지막으로 찍는 바이트의 DP 자리
!wt_sp    = $3D60           ; 원래 스택 포인터(7E)
!wt_cols  = $1D84           ; 그릴 열 수
!wt_base  = $1D86           ; 빌린 첫 칸. 글자 줄 열 칸 다음에 위 줄 열 칸
!wt_ptr   = $1D88           ; 그림 자리(뱅크 !wt_bank 안)
!wt_len   = $1D8A           ; 원래 문자열 길이($00)
!wq_count = $3D62           ; 우리 전송 대기열 항목 수(7E, NMI 가 보내고 0 으로)
!wq_off   = $3D64           ; 대기열에 다음으로 쓸 자리
!wt_vis   = $3DAC           ; 슬롯마다 1바이트: 마지막 창 타일맵 전송 때 보였거나 그 뒤에 그렸으면 1
!wt_xfer  = $3DCA           ; 1바이트: 이번 NMI 에 게임이 보낼 창 타일맵 줄($0BEC 의 bit7·6), NMI 끝에서 WtVis 가 씀
!wt_ecsave = $3DCC          ; 1바이트: 창 제목을 그리는 동안 맡겨 둔 $EC
!wq_rd    = $3D5C           ; NMI 가 다음으로 보낼 항목 자리. VBlank 가 끝나 가면 남은 항목을 다음 NMI 로 넘긴다
!wq_defer = $3D5A           ; 1바이트: bit7·6 = 다음 NMI 로 미룬 게임의 창 타일맵 전송 요청($0BEC),
                            ; bit1·0 = 전투에 들어가면 되돌릴 가나 칸 덩이 수(필드에서 가나 칸 슬롯을 쓰면 3)
!wq_buf   = $3EA0           ; 대기열 7E:3EA0~3FFF. 항목 [VRAM 워드 2][방식 1][칸 수 1][그림]
!wq_size  = $0160
!wq_left  = $3D66           ; NMI 안에서만: 남은 항목 수
!wq_head  = $3D68           ; NMI 안에서만: 방식·칸 수
!wq_len   = $3D6A           ; NMI 안에서만: 그림 바이트 수

; 칸 풀: 1FF~1D0, 이어서 17F~B0 을 위에서부터 빌린다. 096~0AF 는 전투 글자, 180~1CF 는 상태 창 이름 자리라 넣지 않는다.
; 걷는 메시지 캔버스는 096 부터 위로 채우므로 위에서부터 빌리면 겹치기 어렵다. 전투 연출(B0~122)과 전투 글 칸 풀
; (dq4battlemsg.asm)은 목록 창이 닫힌 뒤에 쓰인다.

!wn_stage = $3E00           ; 올릴 160바이트를 먼저 만드는 자리(7E:3D14~3FFF 는 실행한 장면에서 접근 없음)


org !wn_code
WnName:
    LDA.b $01
    CMP #$10
    BCC .original
    CMP #!wn_hi_base
    BCC .kana                   ; 가나 이름(탁점 83·84 포함)
    CMP #!wn_hi_base+!wn_hi_count
    BCS .original
    LDA.b $02
    CMP #$10
    BCC .original
    CMP #$10+111
    BCS .original
.kana
    REP #$20
    LDA.b $DC
    STA.l $7E0000|!wn_ptr
    LDA #$0000
    STA.l $7E0000|!wn_mode
    STA.l $7E0000|!wn_attr
    SEP #$20
    JMP WnKorean
.original
    LDX #$0000
    LDA #$04
    STA.b $00
    JML $04ABD6

; 04:AB73. A 의 높은 바이트에 $ED 가 들어 있고, 원래는 글자마다 16비트로 ($DC),Y 에 쓴 뒤 04:ABF4 로 간다.
WnNameAttr:
    LDA.b $01
    CMP #$10
    BCC .original
    CMP #!wn_hi_base
    BCC .kana                   ; 가나 이름
    CMP #!wn_hi_base+!wn_hi_count
    BCS .original
    LDA.b $02
    CMP #$10
    BCC .original
    CMP #$10+111
    BCS .original
.kana
    REP #$20
    LDA.b $DC
    STA.l $7E0000|!wn_ptr
    LDA #$0000
    STA.l $7E0000|!wn_mode
    LDA.b $ED
    AND #$00FF
    XBA
    STA.l $7E0000|!wn_attr
    SEP #$20
    JMP WnKorean
.original
    LDX #$0000
    LDA #$04
    STA.b $00
    JML $04AB7A

; 24:A83C(전투, DB = 04·20). 원래는 이름 $00 바이트를 $01~ 에서 0ECB~ 로 옮기고 FF 로 끝낸 뒤 RTS.
WnBattle:
    PHP
    SEP #$20
    REP #$10
    LDA.b $01
    CMP #!wn_hi_base
    BCC .original
    CMP #!wn_hi_base+!wn_hi_count
    BCS .original
    LDA.b $02
    CMP #$10
    BCC .original
    CMP #$10+111
    BCS .original
    LDA #$02
    STA.l $7E0000|!wn_mode
    JMP WnKorean
.original
    JML BmNameLookup

; 24:A4E0. A = 글 바이트(M = 8), X = 줄 자리 + 칸. 전투 글 칸 풀의 코드면 글 큐 머리에 짝 위 칸 코드(00 = 없음)가 있어,
; 꺼내 위 줄(1DD5)에 쓴다. 한 줄 26칸을 넘는 글자는 버린다(긴 한글 이름). 넘겨 쓰면 다음 줄 위 칸을 덮는다.
WnBattleChar:
    PHA
    PHX
    REP #$20
    AND #$00FF
    TAX
    LDA.l !bm_index,X
    SEP #$20
    CMP #$FF
    BEQ .plain
    ; 짝을 꺼내고 큐를 한 칸 당긴다
    LDA $0ECB
    PHA
    LDX #$0000
-
    LDA $0ECC,X
    STA $0ECB,X
    INX
    CPX #$003F
    BCC -
    STZ $0F0A
    PLA
    BRA .write
.plain
    LDA #$00
.write
    PLX
    XBA                     ; 높은 바이트 = 위 칸 코드
    LDA $0F0D
    CMP #$1A
    BCC +
    PLA
    JML $24A4EE
+
    PLA
    STA $1DEF,X
    XBA
    BEQ +
    STA $1DD5,X
+
    INC $0F0D
    JML $24A4EE

; 24:A5E9(JSL, DB = 24, M = 8). 글 바이트 하나를 타일맵 낱말로. 풀 코드면 그 칸을 가리키게 타일 bit8 을 칸 번호대로,
; 아니면 끈다(줄이 올라가며 같은 자리에 다른 글자가 올 수 있음).
WnBattleCell:
    LDA $1DD5,Y
    PHX
    REP #$20
    AND #$00FF
    TAX
    LDA.l !bm_index,X
    AND #$00FF
    CMP #$00FF
    BEQ .plain
    ASL
    TAX
    LDA.l !bm_tile,X
    PLX
    SEP #$20
    STA.l $7E5546,X
    XBA
    STA.l $7E0000|!bm_pt+1  ; 타일 bit8(풀 C 의 099~0AF 는 0)
    LDA.l $7E5547,X
    AND #$FE
    ORA.l $7E0000|!bm_pt+1
    STA.l $7E5547,X
    RTL
.plain
    PLX
    SEP #$20
    LDA $1DD5,Y
    STA.l $7E5546,X
    LDA.l $7E5547,X
    AND #$FE
    STA.l $7E5547,X
    RTL

; 04:B79B. 메뉴(모험의 서) 목록은 이름 입력의 훅이 그리므로 메뉴 플래그가 켜져 있거나 한글이 아니면 그리로 넘긴다.
; 원래 코드는 PHX 로 시작해 글자마다 04:B235 로 ($E0),Y 에 쓰고 PLX 뒤 04:BFF2 로 간다.
WnList:
    LDA.l !wn_menu_flag
    CMP #$A5
    BEQ .previous
    LDA.b $01
    CMP #$10
    BCC .previous
    CMP #!wn_hi_base
    BCC .kana
    CMP #!wn_hi_base+!wn_hi_count
    BCS .previous
    LDA.b $02
    CMP #$10
    BCC .previous
    CMP #$10+111
    BCS .previous
.kana
    PHX
    REP #$20
    LDA.b $E0
    STA.l $7E0000|!wn_ptr
    LDA #$0001
    STA.l $7E0000|!wn_mode
    ; 04:B235 처럼 $EC bit6 이면 $ED 를 높은 바이트로
    LDA #$0000
    BIT.b $EC-1
    BVC +
    LDA.b $ED
    AND #$00FF
    XBA
+
    STA.l $7E0000|!wn_attr
    ; X 는 창 문자열(뱅크 04)에서 D0 다음 바이트. 「누구」 고르기 창은 이름 뒤 DD(상태 표시 한 칸)가 오고 창을 한 칸
    ; 넓혀 두었으므로 5칸 나아간다. 가게 동료 창(3A)의 이름 뒤 CC(「もっていない」 등)와 대열 바꾸기 창도 다섯째 칸을
    ; 덮지 않게 5칸.
    ; 다른 창(HPとMP 등)은 뒤 내용의 자리가 정해져 있어 원래처럼 4칸.
    LDA #$0008
    STA.l $7E0000|!wn_step
    SEP #$20
    LDA.l $040000,X
    CMP #$DD
    BEQ ++
    CMP #$CC
    BEQ ++
    ; 대열 바꾸기 창(46·45)은 이름 뒤에 「Lv:」 가 붙는다. 지금 그리는 창 번호($0A00)로 가른다
    LDA.w $0A00
    CMP #$45
    BEQ ++
    CMP #$46
    BNE +
++
    LDA #$0A
    STA.l $7E0000|!wn_step
+
    SEP #$20
    JMP WnKorean
.previous
    JML !wn_list_prev

WnKorean:
    PHP
    PHB
    SEP #$20
    LDA #$7E
    PHA
    PLB
    REP #$30
    STY.w !wn_y
    ; 글리프 번호: (첫 바이트 - 85) × 111 + (둘째 바이트 - 10). 01 이나 범위 밖이면 거기서 끝
    LDX #$0000
    LDA.b $01
    AND #$00FF
    CMP.w #!wn_hi_base
    BCS .decode
    ; 가나 이름: 바이트마다 글리프 하나, 84·83 은 다음 바이트의 탁점·반탁점(!wn_kana_table 의 둘째·셋째 256바이트)
    LDY #$0000
.kana
    CPY #$0008
    BCS .kanadone
    CPX #$0008
    BCS .kanadone
    LDA.b $01,X
    AND #$00FF
    INX
    STA.w !wn_c
    STZ.w !wn_r
    CMP #$0084
    BNE +
    LDA #$0100
    BRA ++
+
    CMP #$0083
    BNE +++
    LDA #$0200
++
    STA.w !wn_r
    LDA.b $01,X
    AND #$00FF
    INX
    STA.w !wn_c
+++
    LDA.w !wn_c
    CMP #$0080
    BCS .kanadone
    ASL
    CLC
    ADC.w !wn_r
    PHX
    TAX
    LDA.l !wn_kana_table,X
    PLX
    CMP #$FFFF
    BEQ .kanadone
    STA.w !wn_glyph,Y
    INY
    INY
    BRA .kana
.kanadone
    TYX
    JMP .rest
.decode
    LDA.b $01,X
    AND #$00FF
    SEC
    SBC.w #!wn_hi_base
    CMP.w #!wn_hi_count
    BCS .rest
    STA.w !wn_c
    ASL
    ASL
    ASL
    ASL
    STA.w !wn_r             ; × 16
    ASL
    ASL
    ASL                     ; × 128
    SEC
    SBC.w !wn_r
    SEC
    SBC.w !wn_c             ; × 111
    STA.w !wn_base
    LDA.b $02,X
    AND #$00FF
    SEC
    SBC #$0010
    CMP.w #111
    BCS .rest
    CLC
    ADC.w !wn_base
    STA.w !wn_glyph,X
    INX
    INX
    CPX #$0008
    BCC .decode
.rest
    CPX #$0008
    BCS .decoded
    LDA #$FFFF
    STA.w !wn_glyph,X
    INX
    INX
    BRA .rest
.decoded
    ; 띠 지우기
    LDX #$0034
-
    STZ.w !wn_band,X
    DEX
    DEX
    BPL -
    STZ.w !wn_k
.glyph
    LDX.w !wn_k
    LDA.w !wn_glyph,X
    CMP #$FFFF
    BNE +
    JMP .drawn
+
    JSR WnFetch
    LDX.w !wn_k
    LDA.l WnShift,X
    STA.w !wn_s
    LDA.l WnOffset,X
    STA.w !wn_o
    LDA #$0001
    STA.w !wn_r
.row
    SEP #$20
    LDX.w !wn_r
    LDA.w !wn_cell,X
    STA.w !wn_t0
    LDA.w !wn_cell+16,X
    STA.w !wn_t1
    STZ.w !wn_t2
    LDX.w !wn_s
    BEQ +
-
    LSR.w !wn_t0
    ROR.w !wn_t1
    ROR.w !wn_t2
    DEX
    BNE -
+
    REP #$20
    LDA.w !wn_r
    DEC
    ASL                     ; (줄 - 1) × 6
    STA.w !wn_c
    ASL
    CLC
    ADC.w !wn_c
    CLC
    ADC.w !wn_o
    TAX
    SEP #$20
    LDA.w !wn_band,X
    ORA.w !wn_t0
    STA.w !wn_band,X
    LDA.w !wn_band+1,X
    ORA.w !wn_t1
    STA.w !wn_band+1,X
    LDA.w !wn_band+2,X
    ORA.w !wn_t2
    STA.w !wn_band+2,X
    REP #$20
    INC.w !wn_r
    LDA.w !wn_r
    CMP #$000A
    BCC .row
    INC.w !wn_k
    INC.w !wn_k
    LDA.w !wn_k
    CMP #$0008
    BCS .drawn
    JMP .glyph
.drawn
    LDA.w !wn_mode
    CMP #$0002
    BNE +
    JMP WnBattleDraw
+
    JSR WnSlot
    JSR WnUpload
    JSR WnTilemap
    LDA.w !wn_mode
    BNE .list
    LDA.w !wn_y
    CLC
    ADC #$000A
    TAY
    PLB
    PLP
    SEP #$20
    REP #$10
    JML $04ABF4
.list
    LDA.w !wn_y
    CLC
    ADC.w !wn_step
    TAY
    PLB
    PLP
    SEP #$20
    REP #$10
    PLX
    JML $04BFF2

; 글리프 A 의 32바이트를 !wn_cell 로. 뱅크 62 + n / 1024, 주소 8000 + (n % 1024) × 32. 끝나면 DB = 7E.
WnFetch:
    PHA
    AND #$03FF
    ASL
    ASL
    ASL
    ASL
    ASL
    ORA #$8000
    TAX
    PLA
    XBA
    AND #$00FF
    LSR
    LSR
    TAY                     ; 0, 1, 2
    CPY #$0001
    BEQ .b1
    BCS .b2
    LDY.w #!wn_cell
    LDA #$001F
    db $54,$7E,!wn_glyph_bank     ; MVN 글리프 뱅크 → 7E
    RTS
.b1
    LDY.w #!wn_cell
    LDA #$001F
    db $54,$7E,!wn_glyph_bank+1     ; MVN 글리프 뱅크 → 7E
    RTS
.b2
    LDY.w #!wn_cell
    LDA #$001F
    db $54,$7E,!wn_glyph_bank+2     ; MVN 글리프 뱅크 → 7E
    RTS

; 자리 찾기: 이름 줄 버퍼 주소가 같은 자리, 없으면 돌려 쓰기. 위 줄의 원래 낱말을 (우리 칸이 아니면) 새로 적는다.
WnSlot:
    LDA.w !wn_ptr
    CLC
    ADC.w !wn_y
    STA.w !wn_key
    LDX #$0000
-
    LDA.w !wn_keys,X
    CMP.w !wn_key
    BEQ .found
    INX
    INX
    CPX #$0010
    BCC -
    LDA.w !wn_next
    AND #$0007
    ASL
    TAX
    LDA.w !wn_next
    INC
    AND #$0007
    STA.w !wn_next
    LDA.w !wn_key
    STA.w !wn_keys,X
.found
    STX.w !wn_slot
    TXA
    LSR
    STA.w !wn_c             ; 자리 번호
    ASL
    ASL
    CLC
    ADC.w !wn_c             ; × 5
    ASL                     ; × 10
    CLC
    ADC #$0180
    STA.w !wn_tile
    ; 위 줄 원래 낱말: 자리 × 10 바이트
    LDA.w !wn_c
    ASL
    ASL
    CLC
    ADC.w !wn_c
    ASL
    TAY
    LDA.w !wn_key
    SEC
    SBC #$0040
    TAX
    LDA #$0005
    STA.w !wn_r
-
    LDA.w $0000,X
    AND #$03FF
    CMP #$0180
    BCC +
    CMP #$01D0
    BCC ++
+
    LDA.w $0000,X
    STA.w !wn_above,Y
++
    INX
    INX
    INY
    INY
    DEC.w !wn_r
    BNE -
    RTS

; 열 칸(이름 줄 5 + 합성 5)을 NMI 전송 목록에 한 항목으로.
WnUpload:
    LDY #$0000
    ; 이름 줄 타일: 줄 r 은 띠 줄 r + 2(띠 자리 r + 1)
    STZ.w !wn_c
.name
    STZ.w !wn_r
-
    LDA.w !wn_r
    INC
    STA.w !wn_base
    ASL
    CLC
    ADC.w !wn_base
    ASL
    CLC
    ADC.w !wn_c
    TAX
    SEP #$20
    LDA.w !wn_band,X
    STA.w !wn_stage,Y
    LDA #$FF
    STA.w !wn_stage+1,Y
    REP #$20
    INY
    INY
    INC.w !wn_r
    LDA.w !wn_r
    CMP #$0008
    BCC -
    INC.w !wn_c
    LDA.w !wn_c
    CMP #$0005
    BCC .name
    ; 위 줄 합성 타일: 원래 타일 그림에 띠 줄 1(띠 자리 0)을 7줄째로
    STZ.w !wn_c
.above
    LDA.w !wn_slot
    LSR
    STA.w !wn_base
    ASL
    ASL
    CLC
    ADC.w !wn_base
    CLC
    ADC.w !wn_c
    ASL
    TAX
    LDA.w !wn_mode
    CMP #$0002
    BNE +
    LDA #$0000              ; 전투 글의 위 줄은 빈칸
    BRA ++
+
    LDA.w !wn_above,X
    AND #$03FF
++
    STA.w !wn_base
    STZ.w !wn_r
-
    JSR WnBaseRow           ; A = p0 | p1 << 8
    PHA
    LDA.w !wn_r
    CMP #$0007
    BNE +
    LDX.w !wn_c
    PLA
    SEP #$20
    ORA.w !wn_band,X
    XBA
    ORA.w !wn_band,X
    XBA
    REP #$20
    PHA
+
    PLA
    STA.w !wn_stage,Y
    INY
    INY
    INC.w !wn_r
    LDA.w !wn_r
    CMP #$0008
    BCC -
    INC.w !wn_c
    LDA.w !wn_c
    CMP #$0005
    BCC .above
    ; 우리 대기열로 보낸다. 게임 NMI 전송 목록(7E:4000~)은 가게가 창 상태($0A00~0B17)를 잠시 두는 자리이기도 해,
    ; 동료 창의 이름을 거기 붙이자 되돌린 창 번호가 바뀌어 없는 창(FF)을 열고 멈췄다
    LDA.w !wn_tile
    ASL
    ASL
    ASL
    CLC
    ADC #$1000
    JSR WqStage
    REP #$30
    RTS

; !wn_stage 의 160바이트(10칸, 두 평면)를 VRAM 워드 A 로 보내는 대기열 항목. DB = 7E, M = X = 16.
WqStage:
    STA.w !wn_k
    SEP #$20
    LDA.b $1E
    AND #$7F
    STA.l $004200
    REP #$20
    LDA.w !wq_count
    AND #$00FF
    BNE +
    STZ.w !wq_off
    STZ.w !wq_rd
+
    LDA.w !wq_off
    CLC
    ADC #$00A4
    CMP #!wq_size+1
    BCC .room
    ; 대기열이 차면 WtQueue 처럼 NMI 를 끈 채 VBlank 마다 직접 보낸다
    SEP #$20
--
    LDA.l $004212
    BMI --
-
    LDA.l $004212
    BPL -
    JSL WqNmi
    SEP #$20
    LDA.l $004210
    LDA.w !wq_count
    BNE --
    REP #$20
    STZ.w !wq_off
    STZ.w !wq_rd
.room
    LDY.w !wq_off
    LDA.w !wn_k
    STA.w !wq_buf,Y
    LDA #$0A00              ; 방식 0(두 평면), 10칸
    STA.w !wq_buf+2,Y
    TYA
    CLC
    ADC.w #!wq_buf+4
    TAY
    LDX.w #!wn_stage
    LDA #$009F
    db $54,$7E,$7E          ; MVN 7E → 7E, 160바이트
    TYA
    SEC
    SBC.w #!wq_buf
    STA.w !wq_off
    SEP #$20
    LDA.w !wq_count
    INC
    STA.w !wq_count
    LDA.b $1E
    STA.l $004200
    REP #$20
    RTS

; !wn_base 타일의 줄 !wn_r 을 A = p0 | p1 << 8 로. 가나 칸 01~8A 는 1bpp(둘째 평면 FF), 테두리 8B~95 는 두 평면.
WnBaseRow:
    LDA.w !wn_base
    BEQ .blank
    CMP #$008B
    BCS .border
    DEC
    ASL
    ASL
    ASL
    CLC
    ADC.w !wn_r
    TAX
    LDA.l $04E528,X
    ORA #$FF00
    RTS
.border
    CMP #$0096
    BCS .blank
    SEC
    SBC #$008B
    ASL
    ASL
    ASL
    ASL
    CLC
    ADC.w !wn_r
    TAX
    SEP #$20
    LDA.l $04E980,X
    XBA
    LDA.l $04E978,X
    REP #$20
    RTS
.blank
    LDA #$FF00
    RTS

; 타일맵 버퍼: 이름 줄 5칸과 위 줄 5칸. 높은 바이트의 우선·팔레트는 살리고 뒤집기는 지운다.
WnTilemap:
    LDX.w !wn_key
    LDA.w !wn_slot
    LSR
    STA.w !wn_base
    ASL
    ASL
    CLC
    ADC.w !wn_base
    ASL
    TAY                     ; 위 줄 원래 낱말 자리
    LDA.w !wn_tile
    STA.w !wn_base
    LDA #$0005
    STA.w !wn_r
-
    LDA.w !wn_attr
    BNE +
    LDA.w $0000,X
+
    AND #$3C00
    ORA.w !wn_base
    STA.w $0000,X
    PHX
    TXA
    SEC
    SBC #$0040
    TAX
    LDA.w !wn_above,Y
    AND #$3C00
    ORA.w !wn_base
    CLC
    ADC #$0005
    STA.w $0000,X
    PLX
    INC.w !wn_base
    INX
    INX
    INY
    INY
    DEC.w !wn_r
    BNE -
    RTS

; 04:B808. $43 = 이름 표 번호, $42 = 이름 번호, $00·$01~ = 원래 문자열, ($E0),Y = 타일맵 버퍼 자리.
; 원래는 글자마다 04:B235 로 쓰고 REP #$10 / PLX 뒤 04:BFF2 로 간다.
; 04:B8F3. 부른 쪽이 이미 PHX 를 했다.
WnSpell:
    LDA #$05
    BRA +
; 04:BC08(E6 전투 몬스터 이름, 04:B6A0 의 C9 도 BRL 로 옴). 원래는 REP #$10 / LDX #0 / LDA #9 / STA $00 / BRL $B7A3,
; 부른 쪽이 이미 PHX 를 했다.
WnMonster:
    REP #$10
    LDA #$09
    BRA +
WnText:
    PHX
    LDA #$00
+
    STA.l $7E0000|!wt_mode
    REP #$30
    ; 버퍼가 9E k 로 시작하면(INLINE_STRINGS) 고정 문구 k 를 그린다. $42·$43 에는 앞서 받은 이름이 남아 있다
    LDA.b $01
    AND #$00FF
    CMP.w #!wt_fixed
    BNE +
    LDA.b $02
    AND #$00FF
    ORA.w #!wt_fixed_kind<<8
    STA.b $42
+
    ; 빈 자리(주문이 없는 칸 등)는 이름을 받지 않고 빈칸을 찍어, $42·$43 에 앞서 받은 이름이 남아 있다
    LDA.b $01
    AND #$00FF
    CMP #$0001
    BNE +
    JMP .original
+
    LDA.b $43
    AND #$00FF
    CMP #$0008
    BCC +
    JMP .original
+
    XBA
    ASL                     ; 번호 × 200
    STA.l $7E0000|!wt_ptr
    LDA.b $42
    AND #$00FF
    ASL
    CLC
    ADC.l $7E0000|!wt_ptr
    TAX
    LDA.l (!wt_bank<<16)|$8000,X
    BNE +
    JMP .original
+
    STA.l $7E0000|!wt_ptr
    PHB
    SEP #$20
    LDA #$7E
    PHA
    PLB
    REP #$30
    TSC
    STA.w !wt_sp
    LDA #!wt_stack
    TCS
    STY.w !wn_y
    LDA #$0000
    BIT.b $EC-1
    BVC +
    LDA.b $ED
    AND #$00FF
    XBA
+
    STA.w !wn_attr
    LDX.w !wt_ptr
    LDA.l !wt_bank<<16,X
    AND #$00FF
    STA.w !wt_cols
    ; 아홉 글자 고정(전투 몬스터·도구 창)은 자리가 아홉 칸이라 열 칸 이름(도구 9개)은 가나로 둔다
    LDA.w !wt_mode
    AND #$00FF
    CMP #$0009
    BNE +
    LDA.w !wt_cols
    CMP #$000A
    BCC +
    JMP .full
+
    ; 원래 루틴이 나아가는 칸 수: 탁점 바이트(84·83)는 위 줄에 탁점만 찍고 칸을 나아가지 않는다.
    ; 04:B808 은 $00 바이트를, 04:B8F3·04:BC08 은 탁점이 아닌 글자 다섯·아홉을 찍는다
    STZ.w !wt_len
    STZ.w !wt_lastx
    LDX #$0001
.count
    LDA.w !wt_mode
    AND #$00FF
    BNE +
    LDA.b $00
    AND #$00FF
    STA.w !wn_c
    CPX.w !wn_c
    BEQ ++
    BCS .counted
    BRA ++
+
    STA.w !wn_c
    LDA.w !wt_len
    CMP.w !wn_c
    BCS .counted
++
    STX.w !wt_lastx
    LDA.b $00,X
    AND #$00FF
    CMP #$0083
    BEQ +
    CMP #$0084
    BEQ +
    INC.w !wt_len
+
    INX
    BRA .count
.counted
    STZ.w !wt_first
    LDA.b $E0
    STA.w !wt_buf
    JSR WtAlloc
    BCS .full
    JSR WtQueue
    JSR WtTilemap
    ; Y 는 원래처럼 가나 글자 수만큼만 나아간다. 창 해석에는 Y 가 정한 열에 닿을 때까지 칸을 채우는 코드가 있어,
    ; 그 열을 넘기면 끝나지 않고 WRAM 을 덮었다.
    LDA.w !wt_len
    ASL
    CLC
    ADC.w !wn_y
    TAY
    LDA.w !wt_sp
    TCS
    ; 원래처럼 A 에 마지막 글자 바이트를 남긴다(창 해석이 돌아가서 A 를 본다)
    LDX.w !wt_lastx
    PLB
    SEP #$20
    REP #$10
    LDA.b $00,X
    PLX
    JML $04BFF2
.full
    LDA.w !wt_sp
    TCS
    LDY.w !wn_y
    PLB
.original
    LDA.l $7E0000|!wt_mode
    AND #$00FF
    BNE +
    SEP #$30
    LDX #$00
    JML $04B80D
+
    SEP #$20
    REP #$10
    LDX #$0000
    LDA.l $7E0000|!wt_mode
    STA.b $00
    JML $04B7A3

; 칸 슬롯: 큰 20칸(10열 × 글자 줄·위 줄), 중간 14칸, 작은 8칸(WtSlot). 캔버스 096~17F 안의 슬롯은 메시지 창이 뜨면
; WqClean 이 지우고, 필드 전용 가나 칸 슬롯은 캔버스 밖이다(명령 창·가게 창 문구만 캔버스 밖 1D0~1FF 의 전용 칸).
; 같은 버퍼 자리(!wt_buf + Y)에 들어갈 크기의 슬롯이 있으면 그 슬롯을, 아니면 들어갈 크기 가운데 빈 슬롯이나 가장 오래 쓰지
; 않은 슬롯을 쓴다. 타일맵 버퍼를 훑어 빈 칸을 찾던 방식은, 다른 창을 여는 동안 게임이 버퍼를 비워 화면에 보이는 칸을
; 다시 빌렸다.
WtAlloc:
    LDA #$0000
    LDX.w !wt_cols
    CPX #$0005
    BCC +
    INC
    CPX #$0008
    BCC +
    INC
+
    STA.w !wt_need
    LDA #$0000
    LDX.w $1944
    CPX #$8952
    BEQ +
    INC
+
    STA.w !wt_field
    LDA.w !wt_buf
    CLC
    ADC.w !wn_y
    STA.w !wn_key
    INC.w !wt_age
    LDX #$0000
-
    LDA.w !wt_keys,X
    CMP.w !wn_key
    BNE +
    JSR WtFits
    BCS .found
    ; 같은 자리를 다른 크기로 다시 그림: 옛 슬롯은 비운다
    STZ.w !wt_keys,X
    STZ.w !wt_ages,X
+
    INX
    INX
    CPX.w #!wt_nslot*2
    BCC -
    ; 필드에서는 가나 칸에서 열 수만큼 잘라 쓴다. 가나 칸은 메시지 캔버스 밖이라 메시지와 함께 뜨는 목록이 비치지 않는다
    LDA.w !wt_field
    BEQ +
    JSR WtKana
    BCS .found
+
    ; 캔버스 안 고정 슬롯: 들어갈 크기 가운데 빈 슬롯, 이미 안 보이는 슬롯, 가장 오래된 슬롯 순. 오래된 순만 보면 전투처럼
    ; 슬롯이 모자란 곳에서 아직 보이는 작전 창을 밀어내고 닫힌 창의 슬롯을 남겼다. 안 보이는지는 지금 버퍼가 아니라 WtVis
    ; 가 창 타일맵을 보낸 NMI 에 잰 표시로 본다(게임이 뒤 창을 다시 그리거나 버퍼를 비우는 동안 버퍼만 보면 틀렸다)
    LDX.w #!wt_nkana*2
    LDY #$0000
    STZ.w !wn_c
-
    JSR WtFits
    BCC .next
    LDA.w !wt_ages,X
    BNE +
    TXY
    BRA .pick
+
    PHX
    TXA
    LSR
    TAX
    LDA.w !wt_vis,X
    PLX
    AND #$00FF
    BNE +
    TXY
    BRA .pick
+
    LDA.w !wt_age
    SEC
    SBC.w !wt_ages,X        ; 지난 횟수(돌아가도 뺄셈이면 맞음)
    CMP.w !wn_c
    BCC .next
    BEQ .next
    STA.w !wn_c
    TXY
.next
    INX
    INX
    CPX.w #!wt_nslot*2
    BCC -
.pick
    TYX
    LDA.w !wn_key
    STA.w !wt_keys,X
.found
    STX.w !wt_slot2
    LDA.w !wt_age
    STA.w !wt_ages,X
    PHX
    TXA
    LSR
    TAX
    SEP #$20
    LDA #$01
    STA.w !wt_vis,X
    REP #$20
    PLX
    JSR WtBaseOf
    STA.w !wt_base
    CLC
    RTS

; 슬롯 X 의 첫 칸(A). 가나 항목은 RAM, 캔버스 슬롯은 WtSlot
WtBaseOf:
    CPX.w #!wt_nkana*2
    BCS +
    PHX
    TXA
    LSR
    TAX
    LDA.w !wt_kbase,X
    PLX
    AND #$00FF
    RTS
+
    LDA.l WtSlot,X
    RTS

; 슬롯 X 가 이번 크기에 맞고 이 장면에서 쓸 수 있으면 C = 1. 가나 항목은 필드에서 칸 수가 열 수 × 2 이상이면
WtFits:
    CPX.w #!wt_nkana*2
    BCS .fixed
    LDA.w !wt_field
    BEQ ++
    LDA.w !wt_cols
    ASL
    STA.w !wt_tmp
    PHX
    TXA
    LSR
    TAX
    LDA.w !wt_klen,X
    PLX
    AND #$00FF
    CMP.w !wt_tmp
    BCC ++
    SEC
    RTS
.fixed
    LDA.l WtClass,X
    CMP #$0010
    BCC +
    LDA.w !wt_field
    BEQ ++
    LDA.l WtClass,X
    AND #$000F
+
    CMP.w !wt_need
    BCC ++
    SEC
    RTS
++
    CLC
    RTS

; 가나 칸 010~077 에서 열 수 × 2 칸이 이어 빈 자리를 처음부터 찾아 빈 가나 항목에 준다. 자리나 빈 항목이 없으면 안 보이는
; 항목 가운데 가장 오래된 것을 비우고 다시 찾는다. 안 보이는 항목도 없으면 C = 0(캔버스 슬롯으로). 찾으면 C = 1, X = 슬롯.
WtKana:
.retry
    JSR WtOcc
    LDA.w !wt_cols
    ASL
    STA.w !wt_tmp
    ; 이어 빈 칸 세기
    LDX #$0000
    STZ.w !wn_r
-
    PHX
    TXA
    AND #$0007
    TAX
    LDA.l WtOccBit,X
    AND #$00FF
    STA.w !wn_k
    PLX
    TXA
    LSR
    LSR
    LSR
    TAY
    LDA.w !wt_occ,Y
    AND.w !wn_k
    BEQ +
    LDY #$0000
    STY.w !wn_r
    BRA ++
+
    INC.w !wn_r
    LDA.w !wn_r
    CMP.w !wt_tmp
    BCS .room
++
    INX
    CPX #$0068
    BCC -
    BRA .evict
.room
    ; 첫 칸 = X − 칸 수 + 1 + 010
    TXA
    SEC
    SBC.w !wt_tmp
    CLC
    ADC #$0011
    STA.w !wn_r
    LDX #$0000
-
    LDA.w !wt_ages,X
    BEQ .use
    INX
    INX
    CPX.w #!wt_nkana*2
    BCC -
    JSR WtKEvict
    BCS .retry
    CLC
    RTS
.use
    LDA.w !wn_key
    STA.w !wt_keys,X
    PHX
    TXA
    LSR
    TAX
    SEP #$20
    LDA.w !wn_r
    STA.w !wt_kbase,X
    LDA.w !wt_tmp
    STA.w !wt_klen,X
    REP #$20
    PLX
    SEC
    RTS
.evict
    JSR WtKEvict
    BCC +
    JMP .retry
+
    RTS

; 안 보이는 가나 항목 가운데 가장 오래된 것을 비운다. 비우면 C = 1
WtKEvict:
    LDX #$0000
    LDY #$FFFF
    STZ.w !wn_c
-
    LDA.w !wt_ages,X
    BEQ .next
    PHX
    TXA
    LSR
    TAX
    LDA.w !wt_vis,X
    PLX
    AND #$00FF
    BNE .next
    LDA.w !wt_age
    SEC
    SBC.w !wt_ages,X
    CMP.w !wn_c
    BCC .next
    STA.w !wn_c
    TXY
.next
    INX
    INX
    CPX.w #!wt_nkana*2
    BCC -
    CPY #$FFFF
    BEQ +
    TYX
    STZ.w !wt_keys,X
    STZ.w !wt_ages,X
    SEC
    RTS
+
    CLC
    RTS

; !wt_occ 에 살아 있는 가나 항목이 쓰는 칸을 켠다
WtOcc:
    LDX #$000C
-
    STZ.w !wt_occ,X
    DEX
    BPL -
    LDX #$0000
.entry
    LDA.w !wt_ages,X
    BEQ .next
    PHX
    TXA
    LSR
    TAX
    LDA.w !wt_kbase,X
    AND #$00FF
    SEC
    SBC #$0010
    STA.w !wn_c
    LDA.w !wt_klen,X
    AND #$00FF
    STA.w !wn_r
-
    LDA.w !wn_c
    LSR
    LSR
    LSR
    TAY
    LDA.w !wn_c
    AND #$0007
    TAX
    SEP #$20
    LDA.w !wt_occ,Y
    ORA.l WtOccBit,X
    STA.w !wt_occ,Y
    REP #$20
    INC.w !wn_c
    DEC.w !wn_r
    BNE -
    PLX
.next
    INX
    INX
    CPX.w #!wt_nkana*2
    BCC .entry
    RTS

WtOccBit:
    db $01, $02, $04, $08, $10, $20, $40, $80

; 슬롯 첫 칸과 등급. 0 = 작은 슬롯 8칸(네 열), 1 = 중간 슬롯 14칸(일곱 열), 2 = 큰 슬롯 20칸(열 열), $10 을 더하면 필드에서만
; 쓰는 슬롯. 맞는 크기가 모자라면 더 큰 슬롯을 빌리고, 빈 슬롯은 표 순서로 고른다. 가나 칸(010~073) 슬롯을 크기와 상관없이
; 모두 앞에 둔다. 가나 칸은 메시지 캔버스 밖이라 메시지와 함께 뜨는 창(교회·가게 팔기 목록 등)의 글자가 메시지 창에 비치지
; 않는다. 가나 칸은 DQ4 물건 이름(6~7열이 가장 많음)에 맞춰 중간을 많이 두고, 「누구의」 창 뒤 강함 보기(문구 25개 남짓)가 들어가게 캔버스 안은 작은 슬롯을 늘려 모두 26개. 전투 메시지와 몬스터 목록이 가나 1바이트
; 타일을 써서 가나 칸은 전투에서 못 쓰고, 전투에 들어가면 WqKana 가 원래 그림으로 되돌린다. 096~0AD 는 전투에서 전투
; 글자 칸이라 필드 전용. 캔버스 안에서는 작은 것부터, 같은 크기면 높은 칸부터: 메시지는 캔버스를 096 부터 채워, 낮은
; 칸일수록 메시지 글자에 덮이기 쉽다. 전투 공격 연출은 B0~122 를 덮는다.
WtSlot:
    dw 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0
    dw $0174, $016C, $0164, $015C, $0154, $014C, $00A6, $009E, $0096
    dw $013E, $0130, $0122, $0114
    dw $0100, $00EC, $00D8, $00C4, $00B0
WtClass:
    dw $FF, $FF, $FF, $FF, $FF, $FF, $FF, $FF, $FF, $FF, $FF, $FF
    dw 0, 0, 0, 0, 0, 0, $10, $10, $10
    dw 1, 1, 1, 1
    dw 2, 2, 2, 2, 2
; 슬롯 × 2 → !wt_dirty 의 비트(낮은 워드, 높은 워드). 슬롯 i 는 비트 i 이고, 캔버스 밖 가나 항목은 0
WtBitLo:
    dw 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0
    dw $1000, $2000, $4000, $8000, 0, 0, 0, 0, 0
    dw 0, 0, 0, 0
    dw 0, 0, 0, 0, 0
WtBitHi:
    dw 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0
    dw 0, 0, 0, 0, $0001, $0002, $0004, $0008, $0010
    dw $0020, $0040, $0080, $0100
    dw $0200, $0400, $0800, $1000, $2000

; 04:B11E(JSL, A = 창 바이트 8비트, X = 레코드에서 그다음 바이트 자리 16비트, DB = 04, Y = $E0 기준 자리). 9E k 면
; 고정 문구 k 를 그리고, 원래 접두 처리처럼 C = 1 로 돌아간다. 칸 셈 $0ADE 는 접두 바이트에서 하나 셌으므로 열 수 − 1 을
; 더한다. 빌드가 레코드의 남는 칸을 빈칸 01 로 채워 뒤 항목의 열 자리는 원래와 같다.
WnPrefix:
    CMP #!wt_fixed
    BEQ +
    JML !wt_prefix_prev
+
    LDA.w $0000,X
    INX
    PHX
    REP #$30
    AND #$00FF
    PHA
    LDA.b $E0
    STA.l $7E0000|!wt_buf
    PLA
    JSR WtFixedDraw
    SEP #$20
    DEC
    CLC
    ADC.w $0ADE
    STA.w $0ADE
    PLX
    SEC
    RTL

; 04:B9EB(M = 8, Y = $E0 기준 자리). 원래 고리는 빈칸 하나와 「しようしていません」 아홉 칸을 찍어 Y 를 20 나아간다.
; 빈칸 자리를 건너뛰고 고정 문구를 그린 뒤 Y 를 원래만큼 나아가, 고리 다음 PLX / BRL 로 돌아간다.
; 필드에서는 원래 가나 타일 칸을 가나 칸 슬롯이 쓰므로 가나로 찍으면 깨진다
WnEmptySlot:
    REP #$30
    TYA
    CLC
    ADC #$0014
    PHA
    INY
    INY
    LDA.b $E0
    STA.l $7E0000|!wt_buf
    LDA.w #!wt_empty_slot
    JSR WtFixedDraw
    PLY
    SEP #$20
    JML $04B9F7

; 04:AC25(04:AA10 제목 고리에서 B0 미만 바이트, A = 바이트 8비트, X = 그 바이트 자리, DB = 04, Y = $DC 기준 자리).
; 원래는 STA $00 / PHB / LDA #$7E / PHA / PLB 뒤 ($DC),Y 에 쓴다. 9E k 면 고정 문구를 그리고 고리로 돌아간다.
; 원래 제목 글자는 낮은 바이트만 써 버퍼의 색을 살린다. 본문 색($EC bit6·$ED)은 앞서 그린 창(어두운 뒤 창의 2C 등)의
; 것이 남아 있으므로, 그리는 동안 bit6 을 꺼 버퍼 색을 쓰게 한다(WtTitleColorOff·On).
WnTitle:
    CMP #!wt_fixed
    BEQ +
    STA.b $00
    PHB
    LDA #$7E
    JML $04AC2A
+
    JSR WtTitleColorOff
    LDA.w $0001,X
    INX
    INX
    PHX
    REP #$30
    AND #$00FF
    PHA
    LDA.b $DC
    STA.l $7E0000|!wt_buf
    PLA
    JSR WtFixedDraw
    SEP #$20
    PLX
    JSR WtTitleColorOn
    JML $04AA10

; $EC 를 !wt_ecsave 에 두고 bit6 을 끈다 / 되돌린다(M = 8)
WtTitleColorOff:
    LDA.b $EC
    STA.l $7E0000|!wt_ecsave
    AND #$BF
    STA.b $EC
    RTS
WtTitleColorOn:
    LDA.l $7E0000|!wt_ecsave
    STA.b $EC
    RTS

; 04:AA79(장비 비교 창 제목의 물건 이름, M = 8, X = 16, PHX 뒤 BRK 88 로 $42·$43 의 이름을 $01~ 에 받은 뒤).
; 원래는 PHB / DB = 7E / LDX #0 / BRL $ABD6 로 제목 줄에 찍고 PLB / PLX / INX / BRL $AA10.
; 제목 코드 E4(가게의 「どうぐ」 등)도 JSR $C25D 로 장비 비교 라벨을 $01~ 에 베껴 여기로 온다. 라벨은 9E k 로 바꿔 두었다.
WnTitleName:
    REP #$30
    LDA.b $01
    AND #$00FF
    CMP.w #!wt_fixed
    BNE +
    SEP #$20
    JSR WtTitleColorOff
    REP #$20
    LDA.b $DC
    STA.l $7E0000|!wt_buf
    LDA.b $02
    AND #$00FF
    JSR WtFixedDraw
    SEP #$20
    JSR WtTitleColorOn
    PLX
    INX
    JML $04AA10
+
    LDA.b $43
    AND #$00FF
    CMP #$0008
    BCS .original
    XBA
    ASL
    PHA                     ; $00 은 원래 고리의 글자 수라 건드리지 않는다
    LDA.b $42
    AND #$00FF
    ASL
    CLC
    ADC 1,S
    TAX
    PLA
    LDA.l (!wt_bank<<16)|$8000,X
    BEQ .original
    SEP #$20
    JSR WtTitleColorOff
    REP #$20
    LDA.b $DC
    STA.l $7E0000|!wt_buf
    TXA
    JSR WtNameDraw
    SEP #$20
    JSR WtTitleColorOn
    PLX
    INX
    JML $04AA10
.original
    SEP #$20
    PHB
    LDA #$7E
    PHA
    PLB
    LDX #$0000
    JML $04ABD6

; 04:BB70(E5, M = 8, X = 16, BRK 88 2B 로 $42 = 작전 번호의 이름을 받은 뒤). 원래는 넉 자를 찍고 Y 를 0x78 더해
; 두 줄 아래 같은 열로 가 넉 자를 더 찍은 뒤 INC $0A4C, PLX, 04:BFF2. 한글은 윗줄·아랫줄 고정 문구 둘로 그린다.
WnTactic:
    PHX
    LDA.b $42
    CMP #!wt_tactic_count
    BCC +
    SEP #$10
    LDX #$00
    JML $04BB75
+
    REP #$30
    PHY
    LDA.b $E0
    STA.l $7E0000|!wt_buf
    LDA.b $42
    AND #$00FF
    ASL
    CLC
    ADC.w #!wt_tactic
    PHA
    JSR WtFixedDraw
    PLA
    INC
    PLY
    PHY
    PHA
    TYA
    CLC
    ADC #$0080
    TAY
    PLA
    JSR WtFixedDraw
    PLA
    CLC
    ADC #$0088
    TAY
    SEP #$20
    INC.w $0A4C
    LDA #$08
    PLX
    JML $04BFF2

; 고정 문구 A(16비트)를 Y 자리(!wt_buf 기준)에 그린다. REP #$30 으로 부르고, Y 를 열 수 × 2 나아가 A = 열 수로 돌려준다.
; DB 는 그대로 둔다.
WtFixedDraw:
    PHB
    STA.l $7E0000|!wt_k
    ASL
    CLC
    ADC.w #!wt_fixed_kind*$200
    BRA WtNameDraw_go
; A = 이름 표 자리(종류 × 200 + 번호 × 2). 고정 문구와 같은 자리에 그리되 전용 칸은 쓰지 않는다
WtNameDraw:
    PHB
    PHA
    LDA #$FFFF
    STA.l $7E0000|!wt_k
    PLA
.go
    TAX
    LDA.l (!wt_bank<<16)|$8000,X
    STA.l $7E0000|!wt_ptr
    PEA $7E7E
    PLB
    PLB
    TSC
    STA.w !wt_sp
    LDA #!wt_stack
    TCS
    STY.w !wn_y
    STZ.w !wt_cols
    LDX.w !wt_ptr
    BEQ .done
    LDA #$0000
    BIT.b $EC-1
    BVC +
    LDA.b $ED
    AND #$00FF
    XBA
+
    STA.w !wn_attr
    LDA.l !wt_bank<<16,X
    AND #$00FF
    STA.w !wt_cols
    STZ.w !wt_len
    STZ.w !wt_first
    ; 메시지 창과 함께 뜨는 창(명령 창·가게)의 문구는 캔버스 밖 1D0~1FF 의 전용 칸(빌드가 정한 첫 칸). 메시지가 떠도 남는다
    LDA.w !wt_k
    BMI +
    ASL
    TAX
    LDA.l (!wt_bank<<16)|!wt_safe,X
    BEQ +
    STA.w !wt_base
    LDA #$FFFF
    STA.w !wt_slot2
    BRA ++
+
    JSR WtAlloc
++
    JSR WtQueue
    JSR WtTilemap
    LDA.w !wt_cols
    ASL
    CLC
    ADC.w !wn_y
    STA.w !wn_y
.done
    LDY.w !wn_y
    LDA.w !wt_sp
    TCS
    LDA.w !wt_cols
    PLB
    RTS

; 대기열에 두 항목: 글자 줄(방식 1, 평면 0 만 열 × 8바이트, NMI 가 평면 1 을 FF 로)과 위 줄(방식 0, 두 평면 열 × 16바이트).
; 위 줄은 지금 그 자리의 타일 그림에 글자 맨 윗줄을 겹친다. 넣는 동안은 NMI 를 끈다.
WtQueue:
    SEP #$20
    LDA.b $1E
    AND #$7F
    STA.l $004200
    REP #$20
    LDA.w !wq_count
    AND #$00FF
    BNE +
    STZ.w !wq_off
    STZ.w !wq_rd
+
    ; 필요한 바이트 = 8 + 열 × 24. 모자라면 대기열이 비워질 때까지 기다린다
    LDA.w !wt_cols
    ASL
    ASL
    ASL
    STA.w !wn_c             ; 열 × 8
    ASL
    CLC
    ADC.w !wn_c
    CLC
    ADC #$0008
    CLC
    ADC.w !wq_off
    CMP #!wq_size+1
    BCC .room
    ; 대기열이 차면 NMI 를 끈 채 다음 VBlank 를 기다려 직접 보낸다. NMI 에 맡기면 게임이 그 프레임의 작업을
    ; 건너뛸 때($19 bit7) 비워지지 않을 수 있다. 이 프레임의 게임 NMI 는 $4210 을 읽어 건너뛴다(VBlank 가 끝난 뒤
    ; NMI 를 다시 켜면 화면을 그리는 도중에 NMI 가 돌기 때문).
    SEP #$20
--
    LDA.l $004212
    BMI --
-
    LDA.l $004212
    BPL -
    JSL WqNmi
    SEP #$20
    LDA.l $004210
    LDA.w !wq_count
    BNE --
    REP #$20
    STZ.w !wq_off
    STZ.w !wq_rd
.room
    ; 글자 줄 항목 머리
    LDY.w !wq_off
    LDA.w !wt_base
    ASL
    ASL
    ASL
    CLC
    ADC #$1000
    STA.w !wq_buf,Y
    LDA.w !wt_cols
    XBA
    ORA #$0001
    STA.w !wq_buf+2,Y
    INY
    INY
    INY
    INY
    STZ.w !wn_k
.lower
    LDA.w !wn_k             ; 열 × 9
    ASL
    ASL
    ASL
    CLC
    ADC.w !wn_k
    CLC
    ADC.w !wt_ptr
    CLC
    ADC #$0002              ; 열 수 바이트 + 위 줄 7줄째
    TAX
    LDA #$0008
    STA.w !wn_r
-
    LDA.l !wt_bank<<16,X
    SEP #$20
    STA.w !wq_buf,Y
    REP #$20
    INX
    INY
    DEC.w !wn_r
    BNE -
    INC.w !wn_k
    LDA.w !wn_k
    CMP.w !wt_cols
    BCC .lower
    ; 위 줄 항목 머리
    LDA.w !wt_base
    CLC
    ADC.w !wt_cols
    ASL
    ASL
    ASL
    CLC
    ADC #$1000
    STA.w !wq_buf,Y
    LDA.w !wt_cols
    XBA
    STA.w !wq_buf+2,Y
    INY
    INY
    INY
    INY
    STZ.w !wn_k
.upper
    ; 위 줄 원래 타일: ($E0) + Y + 2 × 열 − 40
    LDA.w !wn_k
    ASL
    CLC
    ADC.w !wn_y
    CLC
    ADC.w !wt_buf
    SEC
    SBC #$0040
    TAX
    LDA.w $0000,X
    AND #$03FF
    STA.w !wn_base
    STZ.w !wn_r
-
    PHY
    JSR WnBaseRow           ; A = p0 | p1 << 8
    PLY
    STA.w !wq_buf,Y
    INY
    INY
    INC.w !wn_r
    LDA.w !wn_r
    CMP #$0008
    BCC -
    ; 7줄째에 글자 맨 윗줄
    LDA.w !wn_k             ; 열 × 9
    ASL
    ASL
    ASL
    CLC
    ADC.w !wn_k
    CLC
    ADC.w !wt_ptr
    CLC
    ADC #$0001              ; 열 수 바이트 다음이 위 줄 7줄째
    TAX
    LDA.l !wt_bank<<16,X
    AND #$00FF
    STA.w !wn_t0
    XBA
    ORA.w !wn_t0
    ORA.w !wq_buf-2,Y
    STA.w !wq_buf-2,Y
    INC.w !wn_k
    LDA.w !wn_k
    CMP.w !wt_cols
    BCC .upper
    STY.w !wq_off
    LDX.w !wt_slot2
    BMI +
    CPX.w #!wt_nkana*2
    BCS ++
    SEP #$20
    LDA #$03
    TSB.w !wq_defer
    REP #$20
++
    LDA.l WtBitLo,X
    ORA.w !wt_dirty
    STA.w !wt_dirty
    LDA.l WtBitHi,X
    ORA.w !wt_dirty+2
    STA.w !wt_dirty+2
+
    SEP #$20
    LDA.w !wq_count
    CLC
    ADC #$02
    STA.w !wq_count
    LDA.b $1E
    STA.l $004200
    REP #$30
    RTS

; 게임의 창 타일맵 전송($0BEC: bit7 = 7E:5000 2KB, bit6 = 위·아래 줄, 00:8DED 만 읽음)과 우리 대기열이 한 NMI 에
; 겹치면 대기열을 보내고 게임 요청은 다음 NMI 로 미룬다. 둘 다 보내면 우리 뒤에 도는 2KB DMA 가 VBlank 를 넘겨 창
; 아래쪽 줄이 VRAM 에 가지 않고, 대기열 쪽을 미루면 명령 창처럼 매 프레임 요청을 거는 동안 글자가 끝내 올라가지 않는다.
WqNmiGate:
    LDA.l $7E0000|!wq_defer
    AND #$C0
    BEQ +
    ORA.l $000BEC
    STA.l $000BEC
    LDA.l $7E0000|!wq_defer
    AND #$03
    STA.l $7E0000|!wq_defer
+
    LDA.l $7E0000|!wq_defer
    BEQ +
    JSR WqKana
+
    LDA.l $7E0000|!wq_count
    BEQ .done
    LDA.l $000BEC
    BEQ +
    ; 전투 NMI 작업은 00:8DED 를 요청이 있을 때 한 번만 돌아, 미룬 요청을 다음 NMI 에 되돌려도 보내지 않는다.
    ; 전투에서는 우리 대기열 쪽을 다음 NMI 로 미룬다
    LDA.l $001945
    CMP #$89
    BNE ++
    LDA.l $001944
    CMP #$52
    BEQ .done
++
    LDA.l $000BEC
    ORA.l $7E0000|!wq_defer
    STA.l $7E0000|!wq_defer
    LDA #$00
    STA.l $000BEC
+
    JSR WtXfer
    JMP WqNmi
.done
    JSR WtXfer
    RTL

WtXfer:
    LDA.l $000BEC
    ORA.l $7E0000|!wt_xfer
    STA.l $7E0000|!wt_xfer
    RTS

; 00:8885(NMI 끝, M = 8, DB = 00, D = 0). VRAM 을 건드리지 않는 WtVis 를 VBlank 일 뒤에서 돌린다. NMI 앞에서 돌리자 슬롯
; 26개를 재는 시간만큼 게임의 창 타일맵 DMA 가 밀려 메시지 창 아래쪽 줄이 화면으로 가지 않았다
WtVisTail:
    PHP
    LDA.l $7E0000|!wt_xfer
    BEQ +
    PHX
    PHY
    JSR WtVis
    PLY
    PLX
+
    PLP
    LDA.b $1E
    STA.l $004200
    JML $00888A
; 00:FFA1 받침에서 JML(NMI, M = 8). 우리 대기열·미룬 요청·게임의 창 타일맵 요청 가운데 하나라도 있으면 게이트를 부르고
; 00:FFA5(JMP ($1944))로 돌아간다. 창 타일맵 요청만 있어도 부르는 것은 WtVis 가 그 전송 때의 버퍼를 재기 위해서다
; X·Y 는 지킨다. 원래 받침은 A 만 바꿨고, 게임 NMI 는 들어올 때의 X·Y 를 이어 쓴다(창 타일맵을 보내는 NMI 마다 WtVis 가
; X·Y 를 바꾸자 메시지 창 아래쪽 줄이 화면으로 가지 않았다).
WqNmiEntry:
    LDA.l $7E0000|!wq_count
    ORA.l $7E0000|!wq_defer
    ORA.l $000BEC
    BEQ +
    PHX
    PHY
    JSL WqNmiGate
    PLY
    PLX
+
    JML $00FFA5

; 이 NMI 에 게임이 창 타일맵을 보냈으면(!wt_xfer: bit7 = 7E:5000 전체, bit6 = 0~6줄과 21~29줄), 보낸 줄에 키가 있는
; 슬롯마다 키 자리의 타일이 그 슬롯인지 재 !wt_vis 에 둔다. 화면은 보낸 버퍼대로라 이때의 버퍼가 화면과 같다. M = 8.
WtVis:
    PHP
    PHB
    REP #$30
    PEA $7E7E
    PLB
    PLB
    LDA.w !wt_xfer
    AND #$00C0
    STA.w !wq_head
    LDX #$0000
.slot
    LDA.w !wt_ages,X
    BEQ .next
    LDA.w !wt_keys,X
    SEC
    SBC #$5000
    CMP #$0800
    BCS .next
    STA.w !wq_len
    LDA.w !wq_head
    AND #$0080
    BNE .check
    LDA.w !wq_len
    LSR
    LSR
    LSR
    LSR
    LSR
    LSR
    CMP #$0007
    BCC .check
    CMP #$0015
    BCC .next
    CMP #$001E
    BCS .next
.check
    LDY.w !wq_len
    LDA.w $5000,Y
    AND #$03FF
    STA.w !wq_left
    JSR WtBaseOf
    CMP.w !wq_left
    PHP
    TXA
    LSR
    TAY
    PLP
    SEP #$20
    BEQ +
    LDA #$00
    BRA ++
+
    LDA #$01
++
    STA.w !wt_vis,Y
    REP #$20
.next
    INX
    INX
    CPX.w #!wt_nslot*2
    BCC .slot
    SEP #$20
    STZ.w !wt_xfer
    PLB
    PLP
    RTS

; 전투 NMI 작업($1944 = 00:8952)이면 가나 칸 한 덩이(35칸)를 롬의 1bpp 그림(04:E5A0~, 칸 10~)으로 되돌린다. 게임은 가나
; 칸을 평면 0 = 1bpp, 평면 1 = FF 로 올리고(VRAM 덤프 105칸 일치) 전투에 들어갈 때 다시 올리지 않는다. 한 NMI 에 다 보내지
; 않고 세 덩이로 나눠, 전투 화면을 여는 NMI 의 전송과 겹쳐도 VBlank 를 넘기지 않게 한다. M = 8.
WqKana:
    PHP
    REP #$30
    LDA.l $001944
    CMP #$8952
    BEQ +
    PLP
    RTS
+
    LDA.l $7E0000|!wq_defer
    AND #$0003
    EOR #$0003
    ASL
    TAX
    LDA.l WqKanaOff,X
    PHA
    CLC
    ADC #$1080
    STA.l $002116
    PLA
    CLC
    ADC #$E5A0
    STA.l $004302
    LDA #$0118
    STA.l $004305
    SEP #$20
    LDA #$04
    STA.l $004304
    LDA #$00
    STA.l $002115
    STA.l $004300
    LDA #$18
    STA.l $004301
    LDA #$01
    STA.l $00420B
    REP #$20
    LDA.l WqKanaOff,X
    CLC
    ADC #$1080
    STA.l $002116
    LDA.w #WqFF
    STA.l $004302
    LDA #$0118
    STA.l $004305
    SEP #$20
    LDA.b #WqFF>>16
    STA.l $004304
    LDA #$80
    STA.l $002115
    LDA #$08
    STA.l $004300
    LDA #$19
    STA.l $004301
    LDA #$01
    STA.l $00420B
    LDA.l $7E0000|!wq_defer
    DEC
    STA.l $7E0000|!wq_defer
    PLP
    RTS
WqKanaOff:
    dw $0000, $0118, $0230

; NMI(00:FFA1 받침에서 JSL, DB = 00, D = 0). 대기열 항목을 DMA 채널 0 으로 보낸다.
; 게임 목록(00:8CF9)도 채널 0 을 쓰며 보낼 때마다 다시 맞춘다.
WqNmi:
    PHP
    PHB
    SEP #$20
    REP #$10
    LDA.l $7E0000|!wq_count
    BNE +
    PLB
    PLP
    RTL
+
    PHA
    LDA #$7E
    PHA
    PLB
    PLA
    STA.w !wq_left
    LDY.w !wq_rd
.entry
    ; 주사선이 VBlank(225~) 밖이거나 끝 무렵(259~)이면 남은 항목을 다음 NMI 로. VBlank 가 끝난 뒤의 VRAM 쓰기는
    ; 버려진다(강함 보기 라벨이 앞 NMI 들이 길어 주사선 0·1 에 보내져 빠졌음). $2137 래치는 $4201 bit7 이 켜져 있어야
    ; 하고, 게임은 부팅 때 $4201 = FF 로 둔다
    LDA.l $00213F
    LDA.l $002137
    LDA.l $00213D
    XBA
    LDA.l $00213D
    AND #$01
    XBA
    REP #$20
    CMP #$00E1
    BCC +
    CMP #$0103
    BCC ++
+
    JMP .stop
++
    LDA.w !wq_buf,Y
    STA.l $002116
    LDA.w !wq_buf+2,Y       ; 낮은 바이트 = 방식, 높은 바이트 = 칸 수
    STA.w !wq_head
    AND #$FF00
    LSR
    LSR
    LSR
    LSR
    LSR                     ; 칸 × 8
    STA.w !wq_len
    TYA
    CLC
    ADC.w #!wq_buf+4
    STA.l $004302
    SEP #$20
    LDA #$7E
    STA.l $004304
    LDA #$18
    STA.l $004301
    LDA.w !wq_head
    BNE .plane0
    ; 방식 0: 두 평면, 칸 × 16바이트
    LDA #$80
    STA.l $002115
    LDA #$01
    STA.l $004300
    REP #$20
    LDA.w !wq_len
    ASL
    STA.w !wq_len
    STA.l $004305
    SEP #$20
    LDA #$01
    STA.l $00420B
    BRA .next
.plane0
    ; 방식 1: 평면 0 만(칸 × 8바이트), 이어서 같은 자리 평면 1 에 FF
    LDA #$00
    STA.l $002115
    STA.l $004300
    REP #$20
    LDA.w !wq_len
    STA.l $004305
    SEP #$20
    LDA #$01
    STA.l $00420B
    REP #$20
    LDA.w !wq_buf,Y
    STA.l $002116
    LDA.w #WqFF
    STA.l $004302
    LDA.w !wq_len
    STA.l $004305
    SEP #$20
    LDA #$80
    STA.l $002115
    LDA #$08                ; 고정 원본
    STA.l $004300
    LDA #$19
    STA.l $004301
    LDA.b #WqFF>>16
    STA.l $004304
    LDA #$01
    STA.l $00420B
.next
    ; Y += 4 + 그림 바이트
    REP #$20
    TYA
    CLC
    ADC #$0004
    CLC
    ADC.w !wq_len
    TAY
    SEP #$20
    DEC.w !wq_left
    BEQ +
    JMP .entry
+
    STZ.w !wq_count
    STZ.w !wq_rd
    STZ.w !wq_rd+1
    PLB
    PLP
    RTL
.stop
    STY.w !wq_rd
    SEP #$20
    LDA.w !wq_left
    STA.w !wq_count
    PLB
    PLP
    RTL

WqFF:
    db $FF

; 00:8E9E(NMI 작업 안, 게임이 메시지 캔버스를 보내기 직전, M = 8, X = 16). 캔버스 안에 그림을 올린 슬롯의 평면 1 을
; 원래 글자 칸처럼 FF 로 되돌리고 슬롯을 비운다. 게임은 캔버스의 평면 0 만 보내므로, 위 줄 합성(테두리 무늬가 든 평면 1)이
; 남아 메시지 창 빈 줄에 선으로 보였다. NMI 작업 안이라 큐용 NMI 변수(!wq_head·!wq_len·!wq_left)를 쓴다.
WqClean:
    PHB
    PEA $7E7E
    PLB
    PLB
    REP #$30
    LDA.w !wt_dirty
    ORA.w !wt_dirty+2
    BNE +
    JMP .out
+
    LDA.w !wt_dirty
    STA.w !wq_head
    LDA.w !wt_dirty+2
    STA.w !wq_len
    STZ.w !wt_dirty
    STZ.w !wt_dirty+2
    LDX #$0000
.slot
    LSR.w !wq_len
    ROR.w !wq_head
    BCS +
    JMP .next
+
    STZ.w !wt_keys,X
    STZ.w !wt_ages,X
    LDA.l WtClass,X
    CMP #$0001
    BNE +
    LDA #$0070              ; 14칸 × 8
    BRA ++
+
    CMP #$0002
    BNE +
    LDA #$00A0              ; 20칸 × 8
    BRA ++
+
    LDA #$0040              ; 8칸 × 8
++
    STA.w !wq_left
    LDA.l WtSlot,X
    ASL
    ASL
    ASL
    CLC
    ADC #$1000
    STA.l $002116
    LDA.w !wq_left
    STA.l $004305
    LDA.w #WqFF
    STA.l $004302
    SEP #$20
    LDA.b #WqFF>>16
    STA.l $004304
    LDA #$08                ; 고정 원본
    STA.l $004300
    LDA #$80
    STA.l $002115
    LDA #$19
    STA.l $004301
    LDA #$01
    STA.l $00420B
    REP #$20
.next
    INX
    INX
    CPX.w #!wt_nslot*2
    BCS .out
    JMP .slot
.out
    SEP #$20
    PLB
    ; 원래 명령: PHB / PHK / PLB(DB = 00) / LDA #$7E
    PHB
    LDA #$00
    PHA
    PLB
    LDA #$7E
    JML $008EA3

; 타일맵: 글자 줄은 빌린 칸, 위 줄은 빌린 칸 + 열 수. 높은 바이트는 우선·팔레트만 살리고, 색($ED)이 있으면 글자 줄에 쓴다.
WtTilemap:
    STZ.w !wn_k
-
    LDA.w !wn_k
    ASL
    CLC
    ADC.w !wn_y
    CLC
    ADC.w !wt_buf
    TAX
    LDA.w !wn_attr
    BNE +
    LDA.w $0000,X
+
    AND #$3C00
    ORA.w !wt_base
    CLC
    ADC.w !wn_k
    STA.w $0000,X
    TXA
    SEC
    SBC #$0040
    TAX
    LDA.w $0000,X
    AND #$3C00
    ORA.w !wt_base
    CLC
    ADC.w !wn_k
    CLC
    ADC.w !wt_cols
    STA.w $0000,X
    INC.w !wn_k
    LDA.w !wn_k
    CMP.w !wt_cols
    BCC -
    ; 한글이 가나보다 짧으면 남는 칸을 빈칸으로
-
    LDA.w !wn_k
    CMP.w !wt_len
    BCS +
    ASL
    CLC
    ADC.w !wn_y
    CLC
    ADC.w !wt_buf
    TAX
    LDA.w !wn_attr
    BNE ++
    LDA.w $0000,X
++
    AND #$3C00
    ORA #$0001
    STA.w $0000,X
    INC.w !wn_k
    BRA -
+
    RTS

WnShift:
    dw 0, 2, 4, 6
WnOffset:
    dw 0, 1, 2, 3
