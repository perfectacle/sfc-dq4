; FC 3장 엔돌 카지노 슬롯머신(릴 셋·줄 다섯). 자료는 dq4fcslot.py 가 FC 롬에서 만든 incbin, 자리는 앞에 붙는 !정의.
; 4E 뱅크(40 이상)라 BRK 를 쓰지 않는다: 효과음과 뱅크 11 의 JSR 루틴은 뱅크 11 받침(!stubs_at)으로 부른다.
; 놀이 동안 DB = 00(레지스터·낮은 WRAM), 자료는 긴 주소로 읽는다. 8비트 A 에서 TAX/TAY 는 B 까지 옮기므로 %ix() 로 한다.
lorom
math pri on

; 변수(DQ5 슬롯 몫 $1216~$132C 가운데 슬롯 NMI 가 쓰지 않는 곳. $1216~1218 코인, $1256~1258 배당은 글의 FE 가 읽음)
!coins = $1216
!lever = $121A
!fc_k = $1220
!fc_n = $1221
!fc_t = $1222
!fc_pos = $1224
!fc_off = $1227
!fc_run = $122A
!fc_cur = $122D
!fc_grid = $1230
!fc_row = $1239
!fc_col = $123A
!fc_first = $123B
!fc_wait = $123C
!fc_base = $123E
!fc_ry = $1240
!fc_rx = $1241
!fc_rp = $1242
!fc_ro = $1243
!fc_num = $1244
!fc_sub = $1247
!fc_lead = $124A
!fc_dig = $124B
!pay = $1256
!fc_lp = $1276                      ; 줄 다섯의 배당(낱말). 글(11:B970)의 수 자리가 $125A~$1261 을 쓰므로 그 뒤에 둔다
!fc_bt = $126A                      ; 세는 동안 깜박임 차례(0~31)
!fc_ln = $126B                      ; 세는 줄
!fc_cnt = $126C                     ; 0 이 아니면 세는 중(Frame 이 그 줄을 깜박임)
!fc_lit = $126D                     ; 켜진 램프(줄 번호 비트)
!fc_ls = $1270                      ; 줄 다섯의 배당 색인(0~7 = 배당 표 줄)
!pad_new = $1212
!oam = $0300
!oam_hi = $0500

!SPEED = 8
!ACCEL = 10
!fc_spd = $124C
!fc_acc = $124D
!fc_rs = $1250                      ; 3바이트, 세우는 릴의 빠르기
!STOP_FIRST = 185
!STOP_GAP = 60
!BTN_A = $0080
!BTN_B = $8000
!BTN_UP = $0800
!BTN_LEFT = $0200
!BTN_RIGHT = $0100
!REELS_OAM = $0100                  ; 무늬 8x8 48개(릴 셋 × 화면 행 넷 × 넷)
!LAMPS_OAM = $0030
!DIGITS_OAM = $0044
!COVER_OAM = $0060
; 판정 뒤 글 창 차례(FC 헤드리스 실측, 판정 17:$9FAC 에서 센 프레임)
!WIN_TEXT = 8                       ; 맞음: 「축하합니다」 가 뜨기까지
!COUNT_LEAD = 149                   ; 맞음: 첫 코인까지
!COUNT_GAP = 9                      ; 코인 한 장마다
!COUNT_TAIL = 193-9                 ; 마지막 코인에서 창을 지우기까지(193) 가운데 그 코인의 9프레임 뒤
!LOSE_CLEAR = 4                     ; 안 맞음: 창을 지우기까지
!LOSE_TEXT = 10                     ; 안 맞음: 「아쉽네요!」 가 뜨기까지
!LOSE_HOLD = 74                     ; 안 맞음: 그 글을 지우기까지
!ASK_GAP = 4                        ; 창을 지운 뒤 「한 번 더?」 까지
; 무늬 8점 줄은 FC y 43~139 일 때만 보인다(17:$A409 가 8C 이상을 F7 로 숨김, 실측 y 43~138). SNES y = FC y − 7
!REEL_TOP = 43-7
!REEL_BOTTOM = 139-7

macro ix()                          ; X ← A 낮은 바이트
    REP #$20 : AND #$00FF : TAX : SEP #$20
endmacro
macro iy()
    REP #$20 : AND #$00FF : TAY : SEP #$20
endmacro
macro bank11()
    PHB : PEA $1111 : PLB : PLB
endmacro

; ── 받침(뱅크 11) ───────────────────────────────────────────────────────────────
org !stubs_at
StubClear:  JSR $BA8B : RTL         ; 글 창 테두리·안쪽(7E:6000)
StubText:   JSR $B970 : RTL         ; X = 타일맵 자리, Y = 문자열(DB 11)
warnpc !stubs_end

; ── 11:BF71 입구: 기계 번호가 !first_machine 이상이면 FC 본체 ─────────────────────
org !hook_at
    JML Entry

; ── 26:8E7C 격투장 시합 고르기의 난수(JSL $00953A)를 FC 18:$ABC3 처럼 ─────────────────────
org !arena_hook
    JSL ArenaPick

org !code_at
Entry:
    CMP.b #!poker
    BCC +
    JML !poker_body                 ; FC 포커(dq4fcpoker)
+   CMP.b #!first_machine
    BCS FcBody
    PHP : PHB : REP #$10
    JML !hook_back

; 11:BF71 과 같은 틀: NMI 를 슬롯 것(00:FEDD)으로, BG3 글자(한글 포함), 코인을 슬롯 칸으로 옮겨 놀고 되돌린다
FcBody:
    PHP : PHB
    REP #$10 : SEP #$20
    SEC : SBC.b #!first_machine
    PHA
    STA $1F57 : STZ $1F58
    JSL $00880F
    PEA $1111 : PLB : PLB
    JSL !slottext_code              ; JSL 11:BFCC(BG3 가나) 뒤 한글 타일
    JSL $04E3FE
    PEA $0000 : PLB : PLB
    LDX #$0116
-   STZ $1216,X
    DEX : BPL -
    PLA : STA !fc_k
    LDA.l $7E203C : STA !coins
    LDA.l $7E203D : STA !coins+1
    LDA.l $7E203E : STA !coins+2
    JSR Play
    LDA !coins : STA.l $7E203C
    LDA !coins+1 : STA.l $7E203D
    LDA !coins+2 : STA.l $7E203E
    JSL $00879C
    PLB : PLP
    RTL

; FC 18:$ABC3: 시합 번호를 난수로 뽑되 최근 8시합(FC $6E31~$6E38, 맨 앞이 가장 최근)에 있으면 다시 뽑는다. 100번째
; 뽑기는 기록과 상관없이 받는다. 받은 번호를 기록 맨 앞에 넣고 나머지를 한 칸씩 민다. 기록은 번호 + 1(0 = 빈칸, FC 의 FF)
; 이라 0 으로 찬 처음 칸이 빈 기록이다. A = 마지막 시합 번호(26:8E7B 의 TXA), 돌려줄 때 A = 고른 번호, DB 는 부른 쪽 그대로.
; FC 는 시합 수(18:$ADAA[$615A])로 rand 를 부르고 00:953A 도 A = n 이면 0~n-1 이라, 하나 더해 시합 수로 넘긴다(그대로면
; 마지막 시합이 뽑히지 않음)
ArenaPick:
    PHP
    SEP #$30
    PHX : PHY
    INC
    STA.l !arena_recent+9
    LDY.b #100
.try
    PHY
    LDA.l !arena_recent+9
    JSL $00953A
    SEP #$30
    PLY
    STA.l !arena_recent+8
    INC
    LDX.b #7
-   CMP.l !arena_recent,X : BEQ .seen
    DEX : BPL -
    BRA .take
.seen
    DEY : BNE .try
.take
    LDX.b #6
-   LDA.l !arena_recent,X : STA.l !arena_recent+1,X
    DEX : BPL -
    LDA.l !arena_recent+8 : INC : STA.l !arena_recent
    DEC
    PLY : PLX
    PLP
    RTL

; ── 화면 준비(강제 블랭크) ──────────────────────────────────────────────────────
Setup:
    LDA #$80 : STA $2100
    STZ $420C                       ; 필드의 HDMA·창 가림·색 계산을 끈다
    STZ $212E : STZ $212F
    STZ $2123 : STZ $2124 : STZ $2125
    LDA #$09 : STA $2105            ; 모드 1, BG3 높은 우선순위
    LDA.b #(!bg1_map>>8) : STA $2107
    LDA #$14 : STA $2109            ; BG3 맵 1400(슬롯 NMI 가 7E:6000 을 보냄)
    LDA.b #(!bg1_chr>>12) : STA $210B
    LDA #$04 : STA $210C            ; BG3 글자 4000(11:BFCC)
    LDA.b #(!obj_chr>>13) : STA $2101
    LDA #$15 : STA $212C
    STZ $212D : STZ $2130 : STZ $2131
    LDX #$0000
-   STZ $210D,X : STZ $210D,X
    INX : CPX #$0008 : BCC -
    LDA #$80 : STA $2115
    LDX.w #!bg1_chr : STX $2116
    LDX.w #BgTiles : LDA.b #BgTiles>>16 : LDY.w #BgTilesEnd-BgTiles : JSR Dma
    LDX.w #!bg1_map : STX $2116
    LDX.w #BgMap : LDA.b #BgMap>>16 : LDY #$0800 : JSR Dma
    LDX.w #!obj_chr : STX $2116
    LDX.w #ObjTiles : LDA.b #ObjTiles>>16 : LDY.w #ObjTilesEnd-ObjTiles : JSR Dma
    ; BG 팔레트는 슬롯 NMI 가 $12CC(60바이트)에서 CGRAM 30~ 으로 매번 보내므로 거기에도 둔다
    LDX #$0000
-   LDA.l BgPal,X : STA $12CC,X
    INX : CPX #$0060 : BCC -
    LDA.b #!bg_pal_cg : STA $2121
    LDX #$0000
-   LDA.l BgPal,X : STA $2122
    INX : CPX #$0080 : BCC -
    LDA.b #!obj_pal_cg : STA $2121
    LDX #$0000
-   LDA.l ObjPal,X : STA $2122
    INX : CPX.w #ObjPalEnd-ObjPal : BCC -
    ; BG3 글 팔레트 0: 0 투명, 1·3 흰색, 2 검정
    STZ $2121
    LDX #$0000
-   LDA.l TextPal,X : STA $2122
    INX : CPX #$0008 : BCC -
    STZ !lever
    REP #$20
    LDX #$0000
-   LDA #$0000 : STA.l $7E6000,X
    INX : INX : CPX #$0800 : BCC -
    SEP #$20
    JSR HideAll
    RTS

Dma:                                ; X = 원본 주소, A = 원본 뱅크, Y = 크기(채널 7: 슬롯 NMI 는 채널 0)
    STX $4372 : STA $4374 : STY $4375
    LDA #$01 : STA $4370
    LDA #$18 : STA $4371
    LDA #$80 : STA $420B
    RTS

HideAll:
    LDX #$0000
-   STZ !oam,X
    LDA #$F0 : STA !oam+1,X            ; y E0 는 화면 아래 끝(224줄째)에 걸쳐 보인다
    INX : INX : INX : INX
    CPX #$0200 : BCC -
    LDX #$0000
-   STZ !oam_hi,X
    INX : CPX #$0020 : BCC -
    RTS

TextPal: dw $0000, $7FFF, $0000, $7FFF

; ── 글·소리(뱅크 11 받침, DB 11) ─────────────────────────────────────────────
macro text(where, str)
    %bank11()
    LDX.w #<where> : LDY.w #<str>
    JSL StubText
    PLB
endmacro

Clear:
    %bank11()
    JSL StubClear
    PLB
    RTS
; 효과음: 24:FEAC(A = 효과음, X = 스크립트). DQ5 슬롯과 같은 3B-00(코인)·3B-01(릴 섬)·3C-00(맞음)
SfxCoin:
    LDA.b #$3B : LDY.w #$0000 : BRA Sfx
SfxStop:
    LDA.b #$3B : LDY.w #$0001 : BRA Sfx
SfxWin:
    LDA.b #$3C : LDY.w #$0000
Sfx:
    PHP : PHB
    PEA $0000 : PLB : PLB
    SEP #$30
    PHA : TYA : TAX : PLA
    JSL $24FEAC
    PLB : PLP
    RTS

Frame:
    JSR DrawReels
    JSR Blink
    JSR DrawLamps
    JSR DrawCoins
    JSL $009506
    REP #$10 : SEP #$20
    ; 슬롯 NMI 는 새로 누른 것($1212) = 누른 것 − $1214 이고 $1214 에 넣는 것은 놀이 몫이다
    REP #$20 : LDA !pad_new : TSB $1214 : SEP #$20
    RTS

Wait:                               ; A = 프레임 수
    STA !fc_wait
-   JSR Frame
    DEC !fc_wait : BNE -
    RTS

; ── 놀이 ─────────────────────────────────────────────────────────────────────
Play:
    JSR Setup
    STZ !fc_n
    JSR Clear
    %text($05CC, !str_intro)
    JSR Frame
    JSL $0094FE : JSL $009552 : JSL $00954A
    REP #$10 : SEP #$20
    JSR NoCoins : BCC Idle
    JMP Leave

NoCoins:                            ; 코인이 없으면 「코인이 모자랍니다」 를 띄우고 C 켬
    LDA !coins : ORA !coins+1 : ORA !coins+2 : BEQ +
    CLC : RTS
+   JSR Clear
    %text($060C, !str_short)
    LDA #$78 : JSR Wait
    SEC : RTS

Idle:
    JSR Frame
    REP #$20 : LDA !pad_new : BIT #!BTN_UP : SEP #$20 : BNE .insert
    REP #$20 : LDA !pad_new : BIT #!BTN_A : SEP #$20 : BNE .start
    REP #$20 : LDA !pad_new : BIT #!BTN_B : SEP #$20 : BEQ Idle
    JMP Leave
.insert
    LDA !fc_n : CMP #$05 : BCS Idle
    LDA !coins : ORA !coins+1 : ORA !coins+2 : BEQ Idle
    REP #$20 : LDA !coins : SEC : SBC #$0001 : STA !coins : SEP #$20
    LDA !coins+2 : SBC #$00 : STA !coins+2
    INC !fc_n
    LDA !fc_lit : ASL : INC : STA !fc_lit
    JSR SfxCoin
    BRA Idle
.start
    LDA !fc_n : BEQ Idle
    JSR Spin
    JSR Judge
    JSR Again
    BCC Leave
    STZ !fc_n : STZ !fc_lit
    JSR NoCoins : BCS Leave
    JSR Clear
    %text($05CC, !str_intro)
    JMP Idle

Leave:
    JSL $00954E : JSL $009502 : JSL $009556
    REP #$10 : SEP #$20
    RTS

; 릴 셋을 돌리고 정해진 프레임에 차례로 세운다(FC: A 뒤 약 185프레임에 첫 릴, 60프레임마다 다음 릴, 실측)
Spin:
    LDX #$0000
-   PHX
    LDA #$20 : JSL $00953A
    REP #$10 : SEP #$20
    PLX
    AND #$1F : STA !fc_pos,X
    STZ !fc_off,X
    LDA #$01 : STA !fc_run,X
    INX : CPX #$0003 : BCC -
    REP #$20 : STZ !fc_t : SEP #$20
    LDA.b #1 : STA !fc_spd
    STZ !fc_acc
.loop
    ; 빠르기: 1점/프레임에서 !ACCEL 프레임마다 1씩, !SPEED 까지(FC 17:$A409 트랩: 약 75프레임에 8점/프레임)
    LDA !fc_spd : CMP.b #!SPEED : BCS +
    INC !fc_acc : LDA !fc_acc : CMP.b #!ACCEL : BCC +
    STZ !fc_acc : INC !fc_spd
+   LDX #$0000
.reel
    LDA !fc_run,X : BEQ .next
    CMP #$02 : BNE +
    LDA !fc_rs,X : BRA ++
+   LDA !fc_spd
++  CLC : ADC !fc_off,X
    CMP #$20 : BCC .keep
    ; 한 칸 내려감
    SEC : SBC #$20 : STA !fc_off,X
    LDA !fc_pos,X : INC : AND #$1F : STA !fc_pos,X
    ; 세우는 중이면 칸마다 8 → 6 → 4 → 2 → 1 로 늦추고 1 로 칸에 닿으면 선다(FC 17:$A409 트랩: 릴마다 약 60프레임)
    LDA !fc_run,X : CMP #$02 : BNE .next
    LDA !fc_rs,X : CMP #$01 : BEQ .halt
    CMP #$03 : BCC +
    SBC #$02 : BRA ++
+   LDA #$01
++  STA !fc_rs,X
    BRA .next
.halt
    STZ !fc_off,X : STZ !fc_run,X
    PHX : JSR SfxStop : PLX
    BRA .next
.keep
    STA !fc_off,X
.next
    INX : CPX #$0003 : BCC .reel
    REP #$20 : INC !fc_t : LDA !fc_t
    LDX #$0000
    CMP.w #!STOP_FIRST : BEQ .stop
    INX
    CMP.w #!STOP_FIRST+!STOP_GAP : BEQ .stop
    INX
    CMP.w #!STOP_FIRST+!STOP_GAP+!STOP_GAP : BEQ .stop
    SEP #$20
    BRA .frame
.stop
    SEP #$20
    LDA #$02 : STA !fc_run,X
    LDA !fc_spd : STA !fc_rs,X
.frame
    JSR Frame
    LDA !fc_run : ORA !fc_run+1 : ORA !fc_run+2 : BEQ +
    JMP .loop
+   RTS

; X = 릴(0~2) → !fc_base = Machines 안 그 릴 띠 첫 칸(기계 × 97 + 1 + 릴 × 32). X 는 그대로
StripBase:
    LDA !fc_k : STA $4202 : LDA.b #97 : STA $4203
    NOP : NOP : NOP : NOP
    REP #$20
    TXA : ASL : ASL : ASL : ASL : ASL
    CLC : ADC $4216 : INC : STA !fc_base
    SEP #$20
    RTS

; X = 릴, A = 띠 칸(0~31) → A = 무늬
Symbol:
    REP #$20 : AND #$001F : CLC : ADC !fc_base : PHX : TAX : SEP #$20
    LDA.l Machines,X
    PLX
    RTS

; 격자(행 × 3 + 릴)와 줄마다 판정·배당(FC 17:$9FAC·17:$9F27)
Judge:
    LDX #$0000                      ; 릴
.reel
    JSR StripBase
    STZ !fc_row
.row
    LDA !fc_pos,X : CLC : ADC !fc_row : JSR Symbol
    PHA
    LDA !fc_row : ASL : CLC : ADC !fc_row : STX !fc_col : CLC : ADC !fc_col
    %iy()
    PLA : STA !fc_grid,Y
    INC !fc_row : LDA !fc_row : CMP #$03 : BCC .row
    INX : CPX #$0003 : BCC .reel
    REP #$20 : STZ !pay
    LDX #$0000
-   STZ !fc_lp,X : INX : INX : CPX #$000A : BCC -
    SEP #$20 : STZ !pay+2
    STZ !fc_row                     ; 줄 번호
    STZ !fc_lit                     ; 판정하면 램프를 모두 끄고 맞은 줄만 켠다(FC 17:$A0D8·$9E35)
.line
    LDA !fc_row : CMP !fc_n : BCC +
    JMP .done
+
    ASL : CLC : ADC !fc_row : %ix()                     ; 줄 × 3
    LDA.l Lines,X : %iy() : LDA !fc_grid,Y : STA !fc_first
    LDA.l Lines+1,X : %iy() : LDA !fc_grid,Y : CMP !fc_first : BNE .miss
    LDA.l Lines+2,X : %iy() : LDA !fc_grid,Y : CMP !fc_first : BEQ .hit
    LDA !fc_first : CMP #$01 : BNE .miss
    STZ !fc_first                   ; 체리 둘 = 색인 0
.hit
    LDA !fc_row : %ix() : LDA !fc_first : AND #$07 : STA !fc_ls,X
    LDA.l LineBit,X : TSB !fc_lit
    LDA !fc_first : AND #$07 : ASL : %ix()
    REP #$20 : LDA.l Pay,X : PHA : CLC : ADC !pay : STA !pay
    LDA !fc_row : AND #$00FF : ASL : TAX : PLA : STA !fc_lp,X : SEP #$20
.miss
    INC !fc_row : JMP .line
.done
    REP #$20 : LDA !pay : SEP #$20 : BNE +
    JMP .lose
+
    ; FC 17:$9DFA: 배당 합을 알리는 글(0475)과 맞음 소리 뒤에 세기 시작
    LDA.b #!WIN_TEXT : JSR Wait
    JSR Clear
    %text($05CC, !str_win)
    JSR SfxWin
    LDA.b #!COUNT_LEAD-!WIN_TEXT : JSR Wait
    ; FC 17:$9EDA: 맞은 줄마다 한 장씩 세며 장마다 소리. 세는 동안 배당 표의 그 무늬 줄을 32프레임마다 8프레임 숨기고
    ; 그 줄 램프는 16프레임마다 한 프레임 흰 램프(17:$9E9D, 차례 $83 은 줄마다 0 부터, 매 프레임 1씩)
    STZ !fc_ln
    LDA #$01 : STA !fc_cnt
.cline
    LDA !fc_ln : ASL : %ix()
    REP #$20 : LDA !fc_lp,X : SEP #$20 : BEQ .nline
    STZ !fc_bt
.count
    REP #$20 : INC !coins : SEP #$20 : BNE +
    INC !coins+2
+   LDA !fc_ln : ASL : %ix()
    REP #$20 : DEC !fc_lp,X : SEP #$20
    JSR SfxCoin
    LDA.b #!COUNT_GAP : STA !fc_wait
-   JSR Frame
    LDA !fc_bt : INC : AND #$1F : STA !fc_bt
    DEC !fc_wait : BNE -
    LDA !fc_ln : ASL : %ix()
    REP #$20 : LDA !fc_lp,X : SEP #$20 : BNE .count
.nline
    INC !fc_ln : LDA !fc_ln : CMP #$05 : BCC .cline
    STZ !fc_cnt
    LDA.b #!COUNT_TAIL : JSR Wait
    JSR Clear
    LDA.b #!ASK_GAP : JSR Wait
    RTS
.lose
    LDA.b #!LOSE_CLEAR : JSR Wait
    JSR Clear
    LDA.b #!LOSE_TEXT-!LOSE_CLEAR : JSR Wait
    %text($05CC, !str_lose)
    LDA.b #!LOSE_HOLD-!LOSE_TEXT : JSR Wait
    JSR Clear
    LDA.b #!ASK_GAP : JSR Wait
    RTS

; 「한 번 더?」 예면 C 켬
Again:
    JSR Clear
    %text($05CC, !str_again)
    STZ !fc_cur
.loop
    JSR DrawCursor
    JSR Frame
    REP #$20 : LDA !pad_new : BIT #!BTN_LEFT|!BTN_RIGHT : SEP #$20 : BEQ +
    LDA !fc_cur : EOR #$01 : STA !fc_cur
+   REP #$20 : LDA !pad_new : BIT #!BTN_B : SEP #$20 : BNE .no
    REP #$20 : LDA !pad_new : BIT #!BTN_A : SEP #$20 : BEQ .loop
    LDA !fc_cur : BNE .no
    SEC : RTS
.no
    CLC : RTS

!yes_cell = $6000+(25*32+11)*2
!no_cell = $6000+(25*32+17)*2
DrawCursor:
    REP #$20
    LDA #$2001 : STA.l $7E0000+!yes_cell : STA.l $7E0000+!no_cell   ; 창 안 빈칸(11:BA8B)
    SEP #$20
    LDA !fc_cur : BNE +
    REP #$20 : LDA.w #$2100|!cursor_tile : STA.l $7E0000+!yes_cell : SEP #$20
    RTS
+   REP #$20 : LDA.w #$2100|!cursor_tile : STA.l $7E0000+!no_cell : SEP #$20
    RTS

; ── 그리기(OAM 그림자) ─────────────────────────────────────────────────────────
DrawReels:                          ; 릴마다 화면 행 -1~2(위→아래)의 무늬를 8x8 넷으로, y = 48 + 32 × 행 + 밀림.
                                    ; FC 격자 행 0(띠 pos)이 아래라 화면 행 i 는 띠 pos + 2 − i. 8점 줄마다
                                    ; !REEL_TOP~!REEL_BOTTOM 밖이면 숨긴다(16x16 이면 창 밖 반쪽이 코인 상자 위에 비침)
    LDX #$0000
    LDY.w #!REELS_OAM
.reel
    JSR StripBase
    LDA !fc_off,X : STA !fc_ro
    LDA !fc_pos,X : STA !fc_rp
    LDA.l ReelX,X : STA !fc_rx
    LDA #$FF : STA !fc_ry
.row
    LDA !fc_ry : ASL : ASL : ASL : ASL : ASL : CLC : ADC.b #48 : CLC : ADC !fc_ro : STA !fc_num+1
    LDA !fc_rp : CLC : ADC.b #2 : SEC : SBC !fc_ry : JSR Symbol
    PHA
    DEC : ASL : STA !fc_num
    PLA : PHX : %ix() : LDA.l SymPal,X : PLX
    ASL : ORA #$20 : STA !fc_num+2
    LDA !fc_num+1 : JSR ReelHalf
    LDA !fc_num : CLC : ADC.b #$10 : STA !fc_num
    LDA !fc_num+1 : CLC : ADC.b #8 : JSR ReelHalf
    INC !fc_ry : LDA !fc_ry : CMP #$03 : BNE .row
    INX : CPX #$0003 : BCC .reel
    RTS

ReelHalf:                           ; A = 8점 줄 y. 왼쪽·오른쪽 8x8 둘(타일 !fc_num·+1, 속성 !fc_num+2)을 Y 에 쓰고 Y += 8
    CMP.b #!REEL_TOP : BCC +
    CMP.b #!REEL_BOTTOM+1 : BCC ++
+   LDA.b #$F0
++  STA !oam+1,Y : STA !oam+5,Y
    LDA !fc_rx : STA !oam,Y : CLC : ADC.b #8 : STA !oam+4,Y
    LDA !fc_num : STA !oam+2,Y : INC : STA !oam+6,Y
    LDA !fc_num+2 : STA !oam+3,Y : STA !oam+7,Y
    INY : INY : INY : INY : INY : INY : INY : INY
    RTS

; 세는 줄 무늬의 배당 표 줄(6칸)을 !fc_bt 0~7 동안 FC 바탕 칸 8F 의 OBJ 로 덮음(FC 17:$9EB4 → $9E80 이 그 줄 BG 를 8F 로
; 바꾸고 $9E64 가 되돌림). BG1 맵은 VRAM 에만 있어 OBJ(우선순위 3, 바탕 팔레트 !cover_pal)로 가린다
Blink:
    LDX #$0000
-   LDA #$F0 : STA !oam+!COVER_OAM+1,X
    INX : INX : INX : INX : CPX #$0018 : BCC -
    LDA !fc_cnt : BEQ .ret
    LDA !fc_bt : CMP #$08 : BCS .ret
    LDA !fc_ln : %ix() : LDA !fc_ls,X : ASL : %ix()
    LDA.l PayCell,X : STA !fc_rx
    LDA.l PayCell+1,X : STA !fc_ry
    LDX #$0000
-   LDA !fc_rx : STA !oam+!COVER_OAM,X
    CLC : ADC #$08 : STA !fc_rx
    LDA !fc_ry : STA !oam+!COVER_OAM+1,X
    LDA.b #!cover_name : STA !oam+!COVER_OAM+2,X
    LDA.b #$30|(!cover_pal<<1) : STA !oam+!COVER_OAM+3,X
    INX : INX : INX : INX : CPX #$0018 : BCC -
.ret
    RTS

; 줄 램프 다섯. 켜진 줄(!fc_lit: 넣은 코인의 줄, 판정 뒤에는 맞은 줄)은 팔레트 3, 아니면 2(FC 실측). 세는 줄의 램프는
; 차례(!fc_bt)가 16의 배수인 프레임에 흰 램프 타일 0D(FC 17:$9EAC → $9E92)
DrawLamps:
    LDX #$0000
-   TXA : ASL : ASL : %iy()
    LDA.b #24 : STA !oam+!LAMPS_OAM,Y
    LDA.l LampY,X : STA !oam+!LAMPS_OAM+1,Y
    LDA.b #(!small_name+$0C) : STA !oam+!LAMPS_OAM+2,Y
    LDA !fc_cnt : BEQ +
    LDA.l LampLine,X : CMP !fc_ln : BNE +
    LDA !fc_bt : AND #$0F : BNE +
    LDA.b #(!small_name+$0D) : STA !oam+!LAMPS_OAM+2,Y
+   LDA.l LampLine,X : PHX : %ix() : LDA.l LineBit,X : PLX
    AND !fc_lit : BEQ +
    LDA.b #$36 : BRA ++
+   LDA.b #$34
++  STA !oam+!LAMPS_OAM+3,Y
    INX : CPX #$0005 : BCC -
    RTS

DrawCoins:                          ; 코인 수 6자리(앞의 0 은 빈칸, 0 이면 마지막 자리만)
    LDA !coins : STA !fc_num : LDA !coins+1 : STA !fc_num+1 : LDA !coins+2 : STA !fc_num+2
    LDX #$0000                      ; 자리 × 3(Pow)
    LDY.w #!DIGITS_OAM
    STZ !fc_lead
.digit
    STZ !fc_dig
.sub
    REP #$20 : LDA !fc_num : SEC : SBC.l Pow,X : STA !fc_sub : SEP #$20
    LDA !fc_num+2 : SBC.l Pow+2,X : BCC .put
    STA !fc_num+2 : REP #$20 : LDA !fc_sub : STA !fc_num : SEP #$20
    INC !fc_dig : BRA .sub
.put
    TXA : CMP #$0F : BEQ +           ; 마지막 자리는 늘 숫자
    LDA !fc_dig : ORA !fc_lead : BNE +
    LDA.b #(!small_name+$0B) : BRA ++
+   LDA #$01 : STA !fc_lead
    LDA !fc_dig : CLC : ADC.b #(!small_name+$01)
++  STA !oam+2,Y
    TYA : SEC : SBC.b #!DIGITS_OAM : ASL : CLC : ADC.b #88  ; x = 88 + 8 × 자리 = 88 + 2 × (Y − 첫 OAM)
    STA !oam,Y
    LDA.b #152 : STA !oam+1,Y
    LDA #$34 : STA !oam+3,Y
    INY : INY : INY : INY
    INX : INX : INX : CPX #$0012 : BCC .digit
    RTS

Pow: dl 100000, 10000, 1000, 100, 10, 1
LampY: db 20, 52, 84, 116, 148
LampLine: db 3, 1, 0, 2, 4          ; 램프(위→아래)가 맡은 줄 번호(코인 1~5장째에 켜지는 차례, FC 실측)
LineBit: db $01, $02, $04, $08, $10
PayCell: incbin "paycell.bin"       ; 배당 색인 0~7 마다 배당 표 줄 첫 칸의 OBJ (x, y)

BgTiles: incbin "bgtiles.bin"
BgTilesEnd:
BgMap: incbin "bgmap.bin"
ObjTiles: incbin "objtiles.bin"
ObjTilesEnd:
BgPal: incbin "bgpal.bin"
ObjPal: incbin "objpal.bin"
ObjPalEnd:
Machines: incbin "machines.bin"
Lines: incbin "lines.bin"
Pay: incbin "pay.bin"
SymPal: incbin "sympal.bin"
ReelX: incbin "reelx.bin"
warnpc !code_end
