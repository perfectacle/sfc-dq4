; FC 3장 엔돌 카지노 포커. 자료는 dq4fcpoker.py 가 만든 incbin, 자리는 앞에 붙는 !정의.
; 47·54 뱅크(40 이상)라 BRK 를 쓰지 않는다. 놀이 동안 DB = 00, 자료는 긴 주소로 읽는다. 화면은 BG1 한 장(맵 7E:6000 →
; VRAM 1400, 슬롯 NMI 00:FEDD 가 매 프레임 보냄). 판정은 FC 17:$8203·$8449~$85FF 를 직접 페이지 $1200 위에서 옮긴 것.
lorom
math pri on

!coins = $1216
!lever = $121A
!pad_new = $1212
!pk_top = $1220
!pk_bet = $1221
!pk_cur = $1222
!pk_hold = $1223                    ; 5바이트
!pk_rank = $1228                    ; 판정한 패(0~8), 없으면 FF
; $1229~$1233: FC 판정의 제로 페이지 $29~$33(직접 페이지 $1200)
!pk_win = $1234                     ; 3바이트
!pk_round = $1237
!pk_tmp = $1238
!pk_num = $123A                     ; 3바이트
!pk_sub = $123D                     ; 3바이트
!pk_dig = $1240                     ; 8바이트(자리 수)
!pk_wait = $1248
!pk_lead = $1249
!pk_pos = $124A                     ; 2바이트(맵 자리)
!pk_n = $124C
!pk_dc = $1264                      ; 더블 업에서 나눈 횟수(FC $82)
!pk_sp = $1265                      ; 3바이트, 손질하는 차례(FC $83~$85)
!pk_bw = $1260                      ; 상자 안 너비(낱말)
!pk_bh = $1262                      ; 상자 안 높이(낱말)
!pk_ptr = $124E                     ; 2바이트
!counts = $1250                     ; 13바이트(FC $7635)
!deck = $1280                       ; 53바이트(FC $7600), 앞 다섯이 손
!oam = $0300
!oam_hi = $0500
!map = $7E6000

!BTN_A = $0080
!BTN_B = $8000
!BTN_UP = $0800
!BTN_DOWN = $0400
!BTN_LEFT = $0200
!BTN_RIGHT = $0100
!JOKER = $34
!BACK = $35
!CELL = 48*2                        ; 카드 한 장 낱말 바이트

macro ix()
    REP #$20 : AND #$00FF : TAX : SEP #$20
endmacro
macro iy()
    REP #$20 : AND #$00FF : TAY : SEP #$20
endmacro
macro btn(mask)
    REP #$20 : LDA !pad_new : BIT.w #<mask> : SEP #$20
endmacro

org !tiles_at
Tiles1: incbin "tiles1.bin"
warnpc !tiles_end

org !poker_at
; 02:A8BC → 11:BF71 입구(dq4fcslot)가 번호 POKER 면 여기로 JML. A = 번호(8비트), X 8비트
PokerBody:
    PHP : PHB
    REP #$10 : SEP #$20
    STA $1F57 : STZ $1F58
    JSL $00880F                     ; NMI = 슬롯 것(00:FEDD)
    PEA $1111 : PLB : PLB
    JSL $04E3FE
    PEA $0000 : PLB : PLB
    LDX #$0116
-   STZ $1216,X
    DEX : BPL -
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
    LDA.b #$80 : STA $2100
    STZ $420C : STZ $212E : STZ $212F
    STZ $2123 : STZ $2124 : STZ $2125
    LDA.b #$01 : STA $2105          ; 모드 1
    LDA.b #$14 : STA $2107          ; BG1 맵 1400(슬롯 NMI 가 7E:6000 을 보냄)
    LDA.b #$04 : STA $210B          ; BG1 글자 4000
    STZ $2101                       ; OBJ 글자 0000, 8x8
    LDA.b #$11 : STA $212C
    STZ $212D : STZ $2130 : STZ $2131
    LDX.w #$0000
-   STZ $210D,X : STZ $210D,X
    INX : CPX.w #$0008 : BCC -
    LDA.b #$80 : STA $2115
    LDX.w #$4000 : STX $2116
    LDX.w #Tiles1 : LDA.b #Tiles1>>16 : LDY.w #!tiles_end-!tiles_at : JSR Dma
    LDX.w #$4000+(!tiles_end-!tiles_at)/2 : STX $2116
    LDX.w #Tiles2 : LDA.b #Tiles2>>16 : LDY.w #Tiles2End-Tiles2 : JSR Dma
    LDX.w #$0010 : STX $2116
    LDX.w #Hand : LDA.b #Hand>>16 : LDY.w #$0040 : JSR Dma
    ; 색: BG 팔레트 0~7, OBJ 팔레트 0. 슬롯 NMI 가 $12CC(60바이트)에서 CGRAM 30~ 으로 매번 보내므로 거기에도 둔다
    STZ $2121
    LDX.w #$0000
-   LDA.l Cgram,X : STA $2122
    INX : CPX.w #$0100 : BCC -
    LDA.b #$80 : STA $2121
    LDX.w #$0000
-   LDA.l ObjCg,X : STA $2122
    INX : CPX.w #$0020 : BCC -
    LDX.w #$0000
-   LDA.l Cgram+$60,X : STA $12CC,X
    INX : CPX.w #$0060 : BCC -
    STZ !lever
    REP #$20
    LDX.w #$0000
-   LDA.w #$0000 : STA.l !map,X
    INX : INX : CPX.w #$0800 : BCC -
    SEP #$20
    LDX.w #$0000
-   STZ !oam,X
    LDA.b #$F0 : STA !oam+1,X          ; y E0 는 화면 아래 끝(224줄째)에 걸쳐 보인다
    INX : INX : INX : INX
    CPX.w #$0200 : BCC -
    LDX.w #$0000
-   STZ !oam_hi,X
    INX : CPX.w #$0020 : BCC -
    RTS

Dma:                                ; X = 원본, A = 뱅크, Y = 크기(채널 7)
    STX $4372 : STA $4374 : STY $4375
    LDA.b #$01 : STA $4370
    LDA.b #$18 : STA $4371
    LDA.b #$80 : STA $420B
    RTS

; ── 프레임 ───────────────────────────────────────────────────────────────────
Frame:
    JSL $009506
    REP #$10 : SEP #$20
    REP #$20 : LDA !pad_new : TSB $1214 : SEP #$20
    RTS

Wait:                               ; A = 프레임 수
    STA !pk_wait
-   JSR Frame
    DEC !pk_wait : BNE -
    RTS

WaitKey:                            ; A 또는 B 를 누르거나 A 프레임이 지날 때까지
    STA !pk_wait
-   JSR Frame
    %btn(!BTN_A|!BTN_B) : BNE +
    DEC !pk_wait : BNE -
+   RTS

; 손가락(OBJ 0·1): X = 맵 열, Y = 맵 행(글 왼쪽 두 칸)
Hand:
    incbin "hand.bin"
HandAt:
    TXA : SEC : SBC.b #2 : ASL : ASL : ASL : STA !oam
    CLC : ADC.b #8 : STA !oam+4
    TYA : ASL : ASL : ASL : DEC : STA !oam+1 : STA !oam+5
    LDA.b #$01 : STA !oam+2
    LDA.b #$02 : STA !oam+6
    LDA.b #$30 : STA !oam+3 : STA !oam+7
    RTS
HandOff:
    LDA.b #$F0 : STA !oam+1 : STA !oam+5
    RTS

; ── 그리기 ───────────────────────────────────────────────────────────────────
; 맵 자리 = (행 × 32 + 열) × 2
macro at(row, col)
    LDX.w #((<row>)*32+(<col>))*2
endmacro

; 줄 하나: X = 맵 자리, Y = 표 안 자리(긴 주소 표 !pk_ptr 기준이 아니라 Texts 등 라벨 + Y)
; 표의 꼴: [칸 수][타일 번호 2바이트 …]
PutLabel:                           ; X = 맵 자리, Y = Labels 안 자리
    STX !pk_pos
    TYX
    LDA.l Labels,X : STA !pk_n
    INX
-   LDA !pk_n : BEQ +
    REP #$20 : LDA.l Labels,X : PHX : LDX !pk_pos : STA.l !map,X : INX : INX : STX !pk_pos : PLX : SEP #$20
    INX : INX
    DEC !pk_n : BRA -
+   RTS

; 배당 표(FC 포커 화면 네임테이블과 같은 자리): 왼쪽(패 0·1·2·6·7·8)은 행 3~8 열 2, 오른쪽(3·4·5)은 행 6~8 열 12.
; 숫자는 열 21 에서 끝나게 오른쪽 맞춤(패 6·7·8 의 한 자리만 열 10)
PayRows: db 0, 1, 2, 6, 7, 8, 3, 4, 5
PayRow:  db 3, 4, 5, 6, 7, 8, 6, 7, 8
PayCol:  db 2, 2, 2, 2, 2, 2, 12, 12, 12
PayNum:  db 19, 19, 19, 10, 10, 10, 19, 19, 19
PayLen:  db 3, 3, 3, 1, 1, 1, 3, 3, 3
DrawPay:
    STZ !pk_round                   ; 줄 i
.each
    ; PayNames 에서 패 k = PayRows[i] 번째 줄 머리(X)
    LDA !pk_round : %ix() : LDA.l PayRows,X : STA !pk_tmp+1
    LDX.w #$0000
.find
    LDA !pk_tmp+1 : BEQ .found
    TXA : CLC : ADC.l PayNames,X : CLC : ADC.l PayNames,X : INC : %ix()   ; 머리 + 칸 수 × 2 + 1
    DEC !pk_tmp+1 : BRA .find
.found
    STX !pk_ptr
    LDA !pk_round : %ix()
    LDA.l PayRow,X : REP #$20 : AND.w #$00FF : ASL : ASL : ASL : ASL : ASL : STA !pk_pos : SEP #$20
    LDA.l PayCol,X : REP #$20 : AND.w #$00FF : CLC : ADC !pk_pos : ASL : STA !pk_pos : SEP #$20
    LDX !pk_ptr
    LDA.l PayNames,X : STA !pk_n
    INX
-   LDA !pk_n : BEQ +
    REP #$20 : LDA.l PayNames,X : PHX : LDX !pk_pos : STA.l !map,X : INX : INX : STX !pk_pos : PLX : SEP #$20
    INX : INX
    DEC !pk_n : BRA -
+   LDA !pk_round : %ix()
    LDA.l PayRows,X : ASL : %ix()
    REP #$20 : LDA.l Payout,X : STA !pk_num : SEP #$20 : STZ !pk_num+2
    LDA !pk_round : %ix()
    LDA.l PayRow,X : REP #$20 : AND.w #$00FF : ASL : ASL : ASL : ASL : ASL : STA !pk_pos : SEP #$20
    LDA.l PayLen,X : PHA
    LDA.l PayNum,X : REP #$20 : AND.w #$00FF : CLC : ADC !pk_pos : ASL : TAX : SEP #$20
    PLA : JSR NumberRight
    INC !pk_round : LDA !pk_round : CMP.b #9 : BCS + : JMP .each
+   RTS

; !pk_num(24비트)을 X 자리부터 A 칸에 오른쪽 맞춤(앞은 빈칸 0), 배당 표·코인 숫자 꼴
NumberRight:
    STA !pk_n
    JSR Digits
    ; 칸 수 > 자리 수면 앞을 비움
    LDA !pk_n : SEC : SBC !pk_lead : BEQ ++ : BCC ++
    STA !pk_tmp
-   REP #$20 : LDA.w #$0000 : STA.l !map,X : SEP #$20
    INX : INX
    DEC !pk_tmp : BNE -
++  LDY.w #$0000
-   TYA : CMP !pk_lead : BCS +
    LDA !pk_dig,Y : ASL : PHX : %ix() : REP #$20 : LDA.l DigitTiles,X : PLX : STA.l !map,X : SEP #$20
    INX : INX : INY : BRA -
+   RTS

; !pk_num → !pk_dig[0..] 앞 0 없는 자리, !pk_lead = 자리 수(0 이면 "0" 한 자리)
Digits:
    PHX
    LDX.w #$0000                    ; Pow 자리
    STZ !pk_lead
.d
    STZ !pk_tmp+1
.s
    REP #$20 : LDA !pk_num : SEC : SBC.l Pow,X : STA !pk_sub : SEP #$20
    LDA !pk_num+2 : SBC.l Pow+2,X : BCC .p
    STA !pk_num+2 : REP #$20 : LDA !pk_sub : STA !pk_num : SEP #$20
    INC !pk_tmp+1 : BRA .s
.p
    LDA !pk_tmp+1 : BNE +
    LDA !pk_lead : BEQ ++
+   PHX : LDA !pk_lead : %ix() : LDA !pk_tmp+1 : STA !pk_dig,X : PLX
    INC !pk_lead
++  INX : INX : INX : CPX.w #$0012 : BCC .d
    LDA !pk_lead : BNE +
    STZ !pk_dig : INC !pk_lead
+   PLX
    RTS

Pow: dl 100000, 10000, 1000, 100, 10, 1

DrawCoins:                          ; 상자(행 4~8 열 23~30) 안 행 5 코인, 행 7 건 수(FC 와 같은 자리)
    LDA !coins : STA !pk_num : LDA !coins+1 : STA !pk_num+1 : LDA !coins+2 : STA !pk_num+2
    %at(5, 24) : LDA.b #6 : JSR NumberRight
    LDA !pk_bet : STA !pk_num : STZ !pk_num+1 : STZ !pk_num+2
    %at(7, 27) : LDA.b #3 : JSR NumberRight
    RTS

; 카드 i(0~4) 칸에 카드 c(0~53, 35 = 뒷면)
DrawCard:                           ; A = 카드, Y = 칸
    STA !pk_tmp
    TYA : STA !pk_tmp+1
    ; 맵 첫 자리 = (CARD_ROW × 32 + CARD_COL0 + 6i) × 2
    ASL : CLC : ADC !pk_tmp+1 : ASL       ; 6i
    CLC : ADC.b #!card_col0
    REP #$20 : AND.w #$00FF : CLC : ADC.w #!card_row*32 : ASL : STA !pk_pos
    LDA !pk_tmp : AND.w #$00FF : STA !pk_sub
    ASL : CLC : ADC !pk_sub : ASL : ASL : ASL : ASL : ASL : TAY        ; 카드 × 96
    SEP #$20
    LDA.b #8 : STA !pk_n            ; 행
.row
    LDX !pk_pos
    LDA.b #6 : STA !pk_n+1
.col
    REP #$20 : TYX : LDA.l Cards,X : LDX !pk_pos : STA.l !map,X : SEP #$20
    INY : INY
    REP #$20 : INC !pk_pos : INC !pk_pos : SEP #$20
    DEC !pk_n+1 : BNE .col
    REP #$20 : LDA !pk_pos : CLC : ADC.w #(32-6)*2 : STA !pk_pos : SEP #$20
    DEC !pk_n : BNE .row
    RTS

DrawHandCards:                      ; 손 다섯(덱 앞 다섯)
    LDY.w #$0000
-   PHY : LDA !deck,Y : JSR DrawCard : PLY
    INY : CPY.w #$0005 : BCC -
    RTS

DrawBacks:
    LDY.w #$0000
-   PHY : LDA.b #!BACK : JSR DrawCard : PLY
    INY : CPY.w #$0005 : BCC -
    RTS

; 카드 아래 이름표(남김·바꿈), 나눠 줌
DrawLabels:
    LDY.w #$0000
-   PHY
    TYA : STA !pk_tmp : ASL : CLC : ADC !pk_tmp : ASL : CLC : ADC.b #!card_col0+1   ; 열 = 6i + 1 + 첫 열
    REP #$20 : AND.w #$00FF : CLC : ADC.w #!label_row*32 : ASL : TAX : SEP #$20
    LDA !pk_hold,Y : BEQ +
    LDY.w #!label_keep : BRA ++
+   LDY.w #!label_swap
++  JSR PutLabel
    PLY : INY : CPY.w #$0005 : BCC -
    %at(!deal_row, !deal_col) : LDY.w #!label_deal : JSR PutLabel
    RTS

ClearLabels:
    REP #$20
    LDX.w #(!label_row*32)*2
-   LDA.w #$0000 : STA.l !map,X
    INX : INX : CPX.w #((!deal_row+1)*32)*2 : BCC -
    SEP #$20
    RTS

; 글 창: 행 !window_row~+5, 열 3~28(FC 포커 화면과 같은 자리·크기)
DrawWindow:
    REP #$20
    LDA.w #24 : STA !pk_bw : LDA.w #4 : STA !pk_bh
    %at(!window_row, 3)
    BRA Box

DrawCoinBox:
    REP #$20
    LDA.w #6 : STA !pk_bw : LDA.w #3 : STA !pk_bh
    %at(4, 23)
    ; 떨어짐

; FC 상자(테두리 FC 18:$BC60 타일, 안은 바닥색 빈칸). 16비트 A 로 들어옴. X = 왼쪽 위 맵 자리, 안 너비 !pk_bw·높이 !pk_bh
Box:
    STX !pk_pos
    LDA.w #$008C : STA.l !map,X : INX : INX
    LDY !pk_bw
-   LDA.w #$008D : STA.l !map,X : INX : INX : DEY : BNE -
    LDA.w #$408C : STA.l !map,X
.mid
    LDA !pk_pos : CLC : ADC.w #64 : STA !pk_pos : TAX
    LDA.w #$008E : STA.l !map,X : INX : INX
    LDY !pk_bw
-   LDA.w #$0000 : STA.l !map,X : INX : INX : DEY : BNE -
    LDA.w #$408E : STA.l !map,X
    DEC !pk_bh : BNE .mid
    LDA !pk_pos : CLC : ADC.w #64 : TAX
    LDA.w #$808C : STA.l !map,X : INX : INX
    LDY !pk_bw
-   LDA.w #$808D : STA.l !map,X : INX : INX : DEY : BNE -
    LDA.w #$C08C : STA.l !map,X
    SEP #$20
    RTS

; 글: Y = Texts 안 자리, !pk_num = 수 자리(#)에 찍을 값. 줄 l 은 창 행 2 + 2l, 열 5(FC 와 같음)
Message:                            ; Y = Texts 안 자리
    STY !pk_ptr
    JSR DrawWindow
    LDX !pk_ptr
    LDA.l Texts,X : STA !pk_n       ; 줄 수
    INX
    STZ !pk_n+1                     ; 줄 번호
.line
    LDA !pk_n+1 : ASL : CLC : ADC.b #!window_row+2
    REP #$20 : AND.w #$00FF : ASL : ASL : ASL : ASL : ASL : CLC : ADC.w #5 : ASL : STA !pk_pos : SEP #$20
    LDA.l Texts,X : STA !pk_wait    ; 칸 수
    INX
.cell
    LDA !pk_wait : BEQ .next
    REP #$20 : LDA.l Texts,X : CMP.w #$FFFF : BNE +
    SEP #$20 : PHX : LDX !pk_pos : JSR WindowNumber : STX !pk_pos : PLX : BRA ++
+   PHX : LDX !pk_pos : STA.l !map,X : INX : INX : STX !pk_pos : PLX
++  SEP #$20
    INX : INX
    DEC !pk_wait : BRA .cell
.next
    INC !pk_n+1 : LDA !pk_n+1 : CMP !pk_n : BCC .line
    RTS

WindowNumber:                       ; !pk_num 을 X 자리부터(창 글 숫자 꼴), X 를 뒤로
    LDA !pk_num : PHA : LDA !pk_num+1 : PHA : LDA !pk_num+2 : PHA
    JSR Digits
    LDY.w #$0000
-   TYA : CMP !pk_lead : BCS +
    LDA !pk_dig,Y : ASL : PHX : %ix() : REP #$20 : LDA.l WDigitTiles,X : PLX : STA.l !map,X : SEP #$20
    INX : INX : INY : BRA -
+   PLA : STA !pk_num+2 : PLA : STA !pk_num+1 : PLA : STA !pk_num
    RTS

; 「예·아니요」(창 넷째 줄) 고르기. 예면 C 켬
YesNo:
    %at(!window_row+4, 8) : LDY.w #!label_yes : JSR PutLabel
    %at(!window_row+4, 16) : LDY.w #!label_no : JSR PutLabel
    STZ !pk_cur
.loop
    LDA !pk_cur : BNE +
    LDX.w #8 : BRA ++
+   LDX.w #16
++  LDY.w #!window_row+4 : JSR HandAt
    JSR Frame
    %btn(!BTN_LEFT|!BTN_RIGHT) : BEQ +
    LDA !pk_cur : EOR.b #1 : STA !pk_cur
+   %btn(!BTN_B) : BNE .no
    %btn(!BTN_A) : BEQ .loop
    JSR HandOff
    LDA !pk_cur : BNE .no2
    SEC : RTS
.no
    JSR HandOff
.no2
    CLC : RTS

; ── 놀이 ─────────────────────────────────────────────────────────────────────
Play:
    JSR Setup
    LDA.b #1 : STA !pk_bet
    JSR DrawPay
    JSR DrawCoinBox
    JSR DrawCoins
    JSR DrawBacks
    JSR Frame
    JSL $0094FE : JSL $009552 : JSL $00954A
    REP #$10 : SEP #$20
.round
    LDA !coins : ORA !coins+1 : ORA !coins+2 : BNE +
    LDY.w #!text_nocoin : JSR Message
    LDA.b #$78 : JSR WaitKey
    JMP Leave
+   JSR Bet
    JSR Deal
    JSR Hold
    JSR Draw
    JSR Judge
    BCC .lose
    JSR Double
    BRA .again
.lose
    LDY.w #!text_lose : JSR Message
    LDA.b #$5A : JSR WaitKey
.again
    LDY.w #!text_again : JSR Message
    JSR YesNo : BCC Leave
    JSR DrawBacks
    JMP .round

Leave:
    JSR HandOff
    JSL $00954E : JSL $009502 : JSL $009556
    REP #$10 : SEP #$20
    RTS

; 걸기: 위 1 늘림(10 과 코인까지), 아래 1 줄임(1 까지), A 로 정함(FC 17:$8A47)
Bet:
    ; 코인이 건 수보다 적으면 코인 수로(FC $04F4)
    LDA !coins+1 : ORA !coins+2 : BNE +
    LDA !coins : CMP !pk_bet : BCS +
    STA !pk_bet
+   JSR DrawCoins
    LDY.w #!text_bet : JSR Message
.loop
    JSR Frame
    %btn(!BTN_UP) : BEQ .down
    LDA !pk_bet : CMP.b #10 : BCS .loop
    INC : STA !pk_tmp
    LDA !coins+1 : ORA !coins+2 : BNE +
    LDA !coins : CMP !pk_tmp : BCC .loop
+   LDA !pk_tmp : STA !pk_bet : JSR DrawCoins : BRA .loop
.down
    %btn(!BTN_DOWN) : BEQ .a
    LDA !pk_bet : CMP.b #2 : BCC .loop
    DEC !pk_bet : JSR DrawCoins : BRA .loop
.a
    %btn(!BTN_A) : BEQ .loop
    REP #$20 : LDA !coins : SEC : SBC !pk_bet : STA !coins : SEP #$20
    LDA !coins+2 : SBC.b #0 : STA !coins+2
    JSR DrawCoins
    RTS

; 섞기(FC 17:$9117·$8ECC): 덱 0~52 를 두고 0~52 두 자리를 200번 맞바꾼 뒤 앞 다섯을 손으로
Shuffle:
    LDX.w #$0000
-   TXA : STA !deck,X
    INX : CPX.w #$0035 : BCC -
    LDA.b #200 : STA !pk_n
.swap
    LDA.b #$35 : JSL $00953A : REP #$10 : SEP #$20 : %ix() : STX !pk_ptr
    LDA.b #$35 : JSL $00953A : REP #$10 : SEP #$20 : %iy()
    LDX !pk_ptr
    LDA !deck,X : PHA : LDA !deck,Y : STA !deck,X : PLA : STA !deck,Y
    DEC !pk_n : BNE .swap
    LDA.b #5 : STA !pk_top
    RTS

Deal:
    JSR Shuffle
    JSR DrawHandCards
    LDX.w #$0000
-   STZ !pk_hold,X : INX : CPX.w #$0005 : BCC -
    RTS

; 남길 카드 고르기: 좌우로 카드, A 로 남김·바꿈, 아래로 「나눠 줌」, 거기서 A
Hold:
    LDY.w #!text_hold : JSR Message
    STZ !pk_cur
.loop
    JSR DrawLabels
    LDA !pk_cur : CMP.b #5 : BCC +
    LDX.w #!deal_col : LDY.w #!deal_row : BRA ++
+   STA !pk_tmp : ASL : CLC : ADC !pk_tmp : ASL : CLC : ADC.b #!card_col0+1 : %ix()
    LDY.w #!label_row
++  JSR HandAt
    JSR Frame
    LDA !pk_cur : CMP.b #5 : BCS .ondeal
    %btn(!BTN_LEFT) : BEQ +
    LDA !pk_cur : BEQ + : DEC !pk_cur
+   %btn(!BTN_RIGHT) : BEQ +
    LDA !pk_cur : CMP.b #4 : BCS + : INC !pk_cur
+   %btn(!BTN_DOWN) : BEQ +
    LDA !pk_cur : STA !pk_round
    LDA.b #5 : STA !pk_cur : BRL .loop
+   %btn(!BTN_A) : BNE ++++
    BRL .loop
++++
    LDA !pk_cur : %ix() : LDA !pk_hold,X : EOR.b #1 : STA !pk_hold,X
    BRL .loop
.ondeal
    %btn(!BTN_UP) : BEQ +
    LDA !pk_round : STA !pk_cur : BRL .loop
+   %btn(!BTN_A) : BNE ++++
    BRL .loop
++++
    JSR HandOff
    JSR ClearLabels
    RTS

; 바꿀 카드를 덱 다음 장과 맞바꿈
Draw:
    LDX.w #$0000
-   LDA !pk_hold,X : BNE +
    LDA !pk_top : %iy() : LDA !deck,Y : PHA : LDA !deck,X : STA !deck,Y : PLA : STA !deck,X
    INC !pk_top
+   INX : CPX.w #$0005 : BCC -
    JSR DrawHandCards
    RTS

; 판정(FC 17:$8203): C 켜지면 이김, !pk_rank = 패, !pk_win = 배당 × 건 수, 이김 글
Judge:
    PHD : PEA $1200 : PLD
    JSR Fc8203
    PLD
    BCC .no
    TXA : STA !pk_rank
    TXA : ASL : %ix()
    REP #$20 : LDA.l Payout,X : STA !pk_sub : SEP #$20
    ; 배당 × 건 수(16 × 8 비트)
    STZ !pk_win : STZ !pk_win+1 : STZ !pk_win+2
    LDA !pk_bet : STA !pk_n
-   REP #$20 : LDA !pk_win : CLC : ADC !pk_sub : STA !pk_win : SEP #$20
    LDA !pk_win+2 : ADC.b #0 : STA !pk_win+2
    DEC !pk_n : BNE -
    JSR ShowWin
    SEC : RTS
.no
    LDA.b #$FF : STA !pk_rank
    CLC : RTS

ShowWin:
    LDA !pk_win : STA !pk_num : LDA !pk_win+1 : STA !pk_num+1 : LDA !pk_win+2 : STA !pk_num+2
    LDY.w #!text_win : JSR Message
    LDA.b #$5A : JSR WaitKey
    RTS

; 더블 업(FC 17:$85FD~$8875): 묻고, 펴 보인 카드보다 센 카드를 엎은 넷에서 고름. 이기면 두 배, 같으면 다시, 지면 잃음.
; 그만두면 배당을 코인에 더함
Double:
    LDA.b #1 : STA !pk_round
    ; FC 17:$85FD: 나눈 횟수 0, 손질 차례 셋은 0~7 난수
    STZ !pk_dc
    LDX.w #$0000
-   PHX : LDA.b #8 : JSL $00953A : REP #$10 : SEP #$20 : PLX
    AND.b #$07 : STA !pk_sp,X
    INX : CPX.w #$0003 : BCC -
.ask
    LDA !pk_round : STA !pk_num : STZ !pk_num+1 : STZ !pk_num+2
    LDY.w #!text_double_ask : JSR Message
    JSR YesNo : BCS .go
    REP #$20 : LDA !coins : CLC : ADC !pk_win : STA !coins : SEP #$20
    LDA !coins+2 : ADC !pk_win+2 : STA !coins+2
    JSR DrawCoins
    RTS
.go
    REP #$20 : LDA !pk_win : ASL : STA !pk_num : SEP #$20
    LDA !pk_win+2 : ROL : STA !pk_num+2
    LDY.w #!text_double_ok : JSR Message
    LDA.b #$3C : JSR WaitKey
.deal
    JSR Shuffle
    JSR Rig
    INC !pk_dc
    LDA !deck : LDY.w #$0000 : JSR DrawCard
    LDY.w #$0001
-   PHY : LDA.b #!BACK : JSR DrawCard : PLY
    INY : CPY.w #$0005 : BCC -
    ; 펴 보인 카드가 조커면 이길 카드가 없다(FC 17:$864F): 80프레임 뒤 넷을 펴고 짐
    LDA !deck : CMP.b #!JOKER : BNE +
    LDA.b #80 : JSR Wait
    STZ !pk_cur : JSR Reveal
    JMP .lose
+
    LDY.w #!text_double_pick : JSR Message
    LDA.b #1 : STA !pk_cur
.pick
    LDA !pk_cur : STA !pk_tmp : ASL : CLC : ADC !pk_tmp : ASL : CLC : ADC.b #!card_col0+1 : %ix()
    LDY.w #!label_row : JSR HandAt
    JSR Frame
    %btn(!BTN_LEFT) : BEQ +
    LDA !pk_cur : CMP.b #2 : BCC + : DEC !pk_cur
+   %btn(!BTN_RIGHT) : BEQ +
    LDA !pk_cur : CMP.b #4 : BCS + : INC !pk_cur
+   %btn(!BTN_A) : BNE ++++
    BRL .pick
++++
    JSR HandOff
    JSR Reveal
    ; 세기 견주기(FC 17:$87A6): 숫자 순위 2 < … < K < A, 조커 가장 셈
    LDA !deck : JSR Strength : STA !pk_tmp
    LDA !pk_cur : %ix() : LDA !deck,X : JSR Strength
    CMP !pk_tmp : BEQ .draw : BCC .lose
    ; 이김: 배당 두 배, 다음 도전
    REP #$20 : ASL !pk_win : SEP #$20 : ROL !pk_win+2
    JSR ShowWin
    INC !pk_round
    JMP .ask
.draw
    LDY.w #!text_draw : JSR Message
    LDA.b #$5A : JSR WaitKey
    JMP .deal
.lose
    LDY.w #!text_lose : JSR Message
    LDA.b #$5A : JSR WaitKey
    RTS

; 엎은 카드를 10프레임마다 하나씩 편다. 고른 칸(!pk_cur, 0 이면 없음)은 맨 끝(FC 17:$879A·$87A0)
Reveal:
    LDY.w #$0001
-   TYA : CMP !pk_cur : BEQ +
    PHY : LDA.b #10 : JSR Wait : PLY
    PHY : LDA !deck,Y : JSR DrawCard : PLY
+   INY : CPY.w #$0005 : BCC -
    LDA !pk_cur : BEQ +
    LDA.b #10 : JSR Wait
    LDA !pk_cur : %iy() : LDA !deck,Y : JSR DrawCard
+   RTS

; 더블 업 덱 손질(FC 17:$8665). X = 맞바꿔 넣을 다음 카드(5 부터). 카드 = 숫자 × 4 + 무늬, 2~9 는 04~23
; - 보통: 펴 보이는 카드를 2~9 로, 엎은 넷이 모두 2~9 면 그 하나를 A·10~K·조커로
; - 나눈 횟수 & 7 이 !pk_sp 첫째·둘째: 펴 보이는 카드와 엎은 하나를 모두 A·10~K·조커로
; - 셋째: 펴 보이는 카드를 2~4, 엎은 하나를 2~3 으로
Rig:
    LDX.w #$0005
    LDA !pk_dc : AND.b #$07
    CMP !pk_sp : BEQ .high
    CMP !pk_sp+1 : BEQ .high
    CMP !pk_sp+2 : BEQ .low
    LDY.w #$0000
-   LDA !deck : CMP.b #$04 : BCC + : CMP.b #$24 : BCC ++
+   JSR SwapY : BRA -
++  LDY.w #$0001
-   LDA !deck,Y : CMP.b #$04 : BCC .done : CMP.b #$24 : BCS .done
    INY : CPY.w #$0005 : BCC -
    BRA .pick
.high
    LDY.w #$0000
.hi
    LDA !deck,Y : CMP.b #$04 : BCC + : CMP.b #$24 : BCS +
    JSR SwapY : BRA .hi
+   CPY.w #$0000 : BNE .done
.pick
    JSR RandY : BRA .hi
.low
    LDY.w #$0000
-   LDA !deck : CMP.b #$04 : BCC + : CMP.b #$10 : BCC ++
+   JSR SwapY : BRA -
++  JSR RandY
-   LDA !deck,Y : CMP.b #$04 : BCC + : CMP.b #$0C : BCC .done
+   JSR SwapY : BRA -
.done
    RTS

SwapY:                              ; 덱 X 와 Y 맞바꿈, X 다음으로
    LDA !deck,X : PHA : LDA !deck,Y : STA !deck,X : PLA : STA !deck,Y
    INX
    RTS

RandY:                              ; Y = 엎은 칸 1~4 가운데 하나, X 다음으로(FC 17:$86CD)
    PHX : LDA.b #4 : JSL $00953A : REP #$10 : SEP #$20 : PLX
    AND.b #$03 : INC : %iy()
    INX
    RTS

Strength:                           ; A = 카드 → 세기(2 = 0 … K = 11, A = 12, 조커 = FE)
    CMP.b #!JOKER : BCC +
    LDA.b #$FE : RTS
+   LSR : LSR : BNE +
    LDA.b #13
+   DEC
    RTS

; ── FC 판정 옮김(직접 페이지 $1200: $29~$2D 숫자+1, $2E~$32 무늬 비트, $33 임시; !counts = FC $7635) ──
Fc8EF3:                             ; A = 카드 → A = 숫자(0~12), X = 무늬, 조커는 A = X = FF
    CMP.b #!JOKER : BCS +
    PHA : AND.b #$03 : %ix() : PLA
    LSR : LSR
    RTS
+   LDX.w #$00FF : LDA.b #$FF
    RTS

Fc8203:
    SEP #$30
    LDA.b #$00 : STA $7E
    JSR Fc8449
    JSR Fc8476
    JSR Fc8498 : BCS .done
    JSR Fc84B9 : BCS .done
    JSR Fc84CB : BCS .done
    JSR Fc84DB : BCS .done
    JSR Fc84ED : BCS .done
    JSR Fc850D : BCS .done
    JSR Fc851B : BCS .done
    JSR Fc85B5 : BCS .done
    JSR Fc85C8
.done
    REP #$10
    RTS

Fc8449:                             ; 손 다섯을 숫자+1·무늬 비트로
    LDY.b #$00
    STY $33
.c
    LDA.w !deck,Y
    REP #$10 : JSR Fc8EF3 : SEP #$10
    LDY $33
    STA.w $1229,Y
    INX
    BEQ .joker
    LDA.b #$01
-   ASL
    DEX
    BNE -
    LSR
.s  STA.w $122E,Y
    LDX $33
    INC $29,X
    INC $33
    INY
    CPY.b #$05
    BNE .c
    RTS
.joker
    LDA.b #$FF
    BRA .s

Fc8476:                             ; 숫자마다 장 수(조커는 모든 숫자에 하나)
    LDX.b #$0C
    LDA.b #$00
-   STA.w !counts,X
    DEX
    BPL -
    LDY.b #$04
.c
    LDX $29,Y
    BEQ .joker
    INC.w !counts-1,X
.n  DEY
    BPL .c
    RTS
.joker
    LDX.b #$0C
-   INC.w !counts,X
    DEX
    BPL -
    BRA .n

Fc8498:                             ; 로열 스트레이트 플러시(조커 있으면 스트레이트 플러시)
    JSR Fc850D : BCC .no
    JSR Fc851B : BCC .no
    JSR Fc85F0 : BCS .sf
    LDA.w !counts : AND.w !counts+12 : BNE .royal
.no CLC : RTS
.sf LDX.b #$02 : SEC : RTS
.royal LDX.b #$00 : SEC : RTS

Fc84B9:                             ; 파이브 카드
    LDX.b #$0C
-   LDA.w !counts,X : CMP.b #$05 : BEQ +
    DEX : BPL -
    CLC : RTS
+   LDX.b #$01 : SEC : RTS

Fc84CB:                             ; 스트레이트 플러시
    JSR Fc850D : BCC +
    JSR Fc851B : BCS ++
+   CLC : RTS
++  LDX.b #$02 : SEC : RTS

Fc84DB:                             ; 포 카드
    LDX.b #$0C
-   LDA.w !counts,X : CMP.b #$04 : BEQ +
    DEX : BPL -
    CLC : RTS
+   LDX.b #$03 : SEC : RTS

Fc84ED:                             ; 풀 하우스
    JSR Fc85B5 : BCC .no
    PHA
    JSR Fc85F0
    PLA
    TAX
    BCS .j
    JSR Fc85E0 : BCS .yes
.no CLC : RTS
.j  DEX : BMI .no
    JSR Fc85B7 : BCC .no
.yes LDX.b #$04 : SEC : RTS

Fc850D:                             ; 플러시: 무늬 비트 다섯을 AND 해 0 이 아님
    LDA $32
    LDX.b #$03
-   AND $2E,X
    DEX
    BPL -
    CMP.b #$01
    LDX.b #$05
    RTS

Fc851B:                             ; 스트레이트
    JSR Fc85F0 : BCS .joker
    LDX.b #$0C
-   LDA.w !counts,X : CMP.b #$02 : BCS .no
    DEX : BPL -
    LDX.b #$00
-   LDA.w !counts,X : BNE +
    INX : BRA -
+   CPX.b #$00 : BEQ .ace
.run
    INX
.run4
    LDY.b #$04
-   LDA.w !counts,X : BEQ .no
    INX : DEY : BNE -
.yes LDX.b #$06 : SEC : RTS
.ace
    JSR .run : BCC + : RTS
+   LDX.b #$09 : BRA .run4
.no CLC : RTS
.joker
    LDA.b #$00 : STA $33
    LDX.b #$0C
-   LDA.w !counts,X : CMP.b #$03 : BCS .no
    DEX : BPL -
    LDX.b #$00
-   LDA.w !counts,X : INX : CMP.b #$02 : BNE -
    CPX.b #$01 : BEQ .jace
    CPX.b #$0A : BEQ .yes
.j4 LDY.b #$04
.jl LDA.w !counts,X : CMP.b #$02 : BNE .jgap
.jn INX : DEY : BNE .jl
    BRA .yes
.jgap
    LDA $33 : BNE .no
    INC $33 : BRA .jn
.jace
    LDY.b #$04
.al LDA.w !counts,X : CMP.b #$02 : BNE .agap
.an INX : DEY : BNE .al
    BRA .yes
.agap
    LDA $33 : BNE +
    INC $33 : BRA .an
+   LDA.b #$00 : STA $33
    LDX.b #$09 : BRA .j4

Fc85B5:                             ; 스리 카드(A = 그 숫자)
    LDX.b #$0C
Fc85B7:
-   LDA.w !counts,X : CMP.b #$03 : BEQ +
    DEX : BPL -
    CLC : RTS
+   TXA
    LDX.b #$07 : SEC : RTS

Fc85C8:                             ; 투 페어
    JSR Fc85F0 : BCS .no
    JSR Fc85E0 : BCC .no
    DEX : BMI .no
    JSR Fc85E2 : BCS .yes
.no CLC : RTS
.yes LDX.b #$08 : SEC : RTS

Fc85E0:
    LDX.b #$0C
Fc85E2:
-   LDA.w !counts,X : CMP.b #$02 : BEQ +
    DEX : BPL -
    CLC : RTS
+   SEC : RTS

Fc85F0:                             ; 조커가 있으면 C
    LDX.b #$04
-   LDA $29,X : BEQ +
    DEX : BPL -
    CLC : RTS
+   SEC : RTS

; ── 자료 ─────────────────────────────────────────────────────────────────────
Cards: incbin "cards.bin"
Texts: incbin "texts.bin"
Labels: incbin "labels.bin"
PayNames: incbin "pay.bin"
Payout: incbin "payout.bin"
DigitTiles: incbin "digits.bin"
WDigitTiles: incbin "wdigits.bin"
Cgram: incbin "cgram.bin"
ObjCg: incbin "objcg.bin"
Tiles2: incbin "tiles2.bin"
Tiles2End:
warnpc !poker_end
