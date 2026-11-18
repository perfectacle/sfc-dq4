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
!fc_lp = $1260                      ; 줄 다섯의 배당(낱말)
!fc_bt = $126A                      ; 세는 동안 깜박임 차례(0~31)
!fc_ln = $126B                      ; 세는 줄
!fc_cnt = $126C                     ; 0 이 아니면 세는 중(Frame 이 그 줄을 깜박임)
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
!REELS_OAM = $0000
!LAMPS_OAM = $0030
!DIGITS_OAM = $0044

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
    INX : CPX #$0080 : BCC -
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
    LDA #$AA                        ; 릴 무늬 12개(OAM 0~11)는 16x16
    STA !oam_hi : STA !oam_hi+1 : STA !oam_hi+2
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
    LDA !fc_cnt : BEQ +
    JSR Blink
+   JSR DrawLamps
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
    JSR SfxCoin
    BRA Idle
.start
    LDA !fc_n : BEQ Idle
    JSR Spin
    JSR Judge
    JSR Again
    BCC Leave
    STZ !fc_n
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
    LDA !fc_first : AND #$07 : ASL : %ix()
    REP #$20 : LDA.l Pay,X : PHA : CLC : ADC !pay : STA !pay
    LDA !fc_row : AND #$00FF : ASL : TAX : PLA : STA !fc_lp,X : SEP #$20
.miss
    INC !fc_row : JMP .line
.done
    REP #$20 : LDA !pay : SEP #$20 : BNE +
    JMP .lose
+
    JSR SfxWin
    ; 맞은 줄마다 배당을 한 프레임에 한 장씩 세며 장마다 소리, 그 줄 무늬는 32프레임마다 8프레임 숨김(FC 17:$9EDA)
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
    JSR Frame
    LDA !fc_bt : INC : AND #$1F : STA !fc_bt
    LDA !fc_ln : ASL : %ix()
    REP #$20 : LDA !fc_lp,X : SEP #$20 : BNE .count
.nline
    INC !fc_ln : LDA !fc_ln : CMP #$05 : BCC .cline
    STZ !fc_cnt
    JSR Clear
    %text($05CC, !str_win)
    LDA #$5A : JSR Wait
    RTS
.lose
    JSR Clear
    %text($05CC, !str_lose)
    LDA #$5A : JSR Wait
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
DrawReels:                          ; 릴마다 화면 행 -1~2(위→아래)의 16x16 넷, y = 48 + 32 × 행 + 밀림.
                                    ; FC 격자 행 0(띠 pos)이 아래라 화면 행 i 는 띠 pos + 2 − i
    LDX #$0000
    LDY.w #!REELS_OAM
.reel
    JSR StripBase
    LDA !fc_off,X : STA !fc_ro
    LDA !fc_pos,X : STA !fc_rp
    LDA.l ReelX,X : STA !fc_rx
    LDA #$FF : STA !fc_ry
.row
    LDA !fc_rx : STA !oam,Y
    LDA !fc_ry : ASL : ASL : ASL : ASL : ASL : CLC : ADC.b #48 : CLC : ADC !fc_ro : STA !oam+1,Y
    LDA !fc_rp : CLC : ADC.b #2 : SEC : SBC !fc_ry : JSR Symbol
    PHA
    DEC : ASL : STA !oam+2,Y
    PLA : PHX : %ix() : LDA.l SymPal,X : PLX
    ASL : ORA #$20 : STA !oam+3,Y
    INY : INY : INY : INY
    INC !fc_ry : LDA !fc_ry : CMP #$03 : BNE .row
    INX : CPX #$0003 : BCC .reel
    RTS

; 세는 줄(!fc_ln)의 세 칸을 !fc_bt 0~7 동안 숨김(FC 17:$9EB4). DrawReels 뒤에 불러야 한다
Blink:
    LDA !fc_bt : CMP #$08 : BCS .ret
    LDA !fc_ln : ASL : CLC : ADC !fc_ln : %ix()
    LDY #$0003
-   PHX : PHY
    LDA.l Lines,X : %ix() : LDA.l CellOam,X : %ix()
    LDA #$F0 : STA !oam+!REELS_OAM+1,X
    PLY : PLX
    INX : DEY : BNE -
.ret
    RTS

; 격자 칸(행 × 3 + 릴, 행 0 이 아래) → 그 칸 OAM 자리(DrawReels: 릴 × 4 + 3 − 행 번째)
CellOam: db 12, 28, 44, 8, 24, 40, 4, 20, 36

DrawLamps:                          ; 줄 램프 다섯. 켜진 줄(줄 번호 < 넣은 수)은 팔레트 3, 아니면 2(FC 실측)
    LDX #$0000
-   TXA : ASL : ASL : %iy()
    LDA.b #24 : STA !oam+!LAMPS_OAM,Y
    LDA.l LampY,X : STA !oam+!LAMPS_OAM+1,Y
    LDA.b #(!small_name+$0C) : STA !oam+!LAMPS_OAM+2,Y
    LDA.l LampLine,X : CMP !fc_n
    LDA.b #$36 : BCC +
    LDA.b #$34
+   STA !oam+!LAMPS_OAM+3,Y
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

BgTiles: incbin "bgtiles.bin"
BgTilesEnd:
BgMap: incbin "bgmap.bin"
ObjTiles: incbin "objtiles.bin"
ObjTilesEnd:
BgPal: incbin "bgpal.bin"
ObjPal: incbin "objpal.bin"
Machines: incbin "machines.bin"
Lines: incbin "lines.bin"
Pay: incbin "pay.bin"
SymPal: incbin "sympal.bin"
ReelX: incbin "reelx.bin"
warnpc !code_end
