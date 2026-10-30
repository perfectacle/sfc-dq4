; 전투 메시지의 한글 구간과 이름. dq4windowname.py 가 dq4windowname.asm 뒤에 붙여 함께 넣고, 정의(!bm_*)는
; dq4battlemsg.py 가 만든다. 형식은 sfc/dq4/docs/dq4-battle-text-format.md.
;
; 전투 글은 바이트가 곧 BG3 타일 번호다. 구간(E3 n 바이트…)과 이름을 Galmuri9 띠로 그려, 칸 풀(코드 85개 ↔ 타일 85칸)에서
; 화면 격자와 글 큐에 없는 코드를 골라 올리고, 그 코드를 글 큐 0ECB 에 넣는다. 글자 맨 윗줄은 위 줄 칸 하나에 담기는
; 1바이트 무늬라 같은 무늬는 위 줄 칸을 함께 쓴다. 아래 줄 코드마다 짝 위 줄 코드(!bm_up)는 WnBattleChar 가 쓴다.

; 코드 E3 의 처리기. 24:86F2 표는 뱅크 24 안 주소라, 옮긴 디코더가 비운 트리 자리에 받침을 둔다.
org !bm_run_table
    dw !bm_run_stub
org !bm_run_stub
    JML BmRun
; 연출 끝(22:D796 LDA $19 / AND #$FD / STA $19). 큰 주문 연출이 덮은 풀 B 칸을 사본에서 다시 올린다.
org $22D796
    JML BmRestore
    NOP
    NOP
; 줄이 올라갈 때 둘째 줄 위 칸을 첫 줄 위(창 위 테두리 줄)로 옮기는 고리(24:A595~A5B1: 탁점 84·83 → 테두리+탁점 92·93).
; 빈 바탕 위 칸도 같은 무늬의 테두리 바탕 칸으로 바꾼다.
org $24A595
    JSL BmScroll
    BRA $24A5B2

org !bm_code

; 24:86CD 의 JMP ($86F2,X) 로 온다(M = X = 16). 24:86B4 가 쌓은 틀은 그대로 두고, 큐를 채운 뒤 이름 처리기처럼 24:872E 로.
BmRun:
    PHB
    SEP #$20
    LDA #$7E
    PHA
    PLB
    REP #$30
    LDA.w !bm_buf
    AND #$00FF
    STA.w !bm_n
    LDA #$0001
    STA.w !bm_p
    JSR BmClear
.token
    LDA.w !bm_p
    CMP.w !bm_n
    BEQ +
    BCS .done
+
    SEP #$20
    STZ.w !bm_tail
    REP #$20
    TAX
    LDA.w !bm_buf,X         ; 낮은 바이트 = 이 바이트, 높은 바이트 = 다음
    AND #$00FF
    CMP #$0020
    BCS .char
    CMP #$0012
    BCS .page
    CMP #$0010
    BEQ .advance
    ; 조사: 다음 바이트 = 종류
    LDA.w !bm_buf+1,X
    AND #$00FF
    JSR BmJosa
    BRA .next
.advance
    LDA.w !bm_buf+1,X
    AND #$00FF
    CMP #$0080
    BCC +
    ORA #$FF00              ; 부호 있는 점 수(좁은 문장 부호는 뒤로 당김)
+
    PHA
    CLC
    ADC.w !bm_x
    STA.w !bm_x
    PLA
    SEP #$20
    STA.w !bm_tail
    REP #$20
    BRA .next
.char
    ; 글자 표 쪽 0(1바이트, 바이트 값으로 바로)
    ASL
    TAX
    LDA.l !bm_charset,X
    JSR BmGlyph
    INC.w !bm_p
    JMP .token
.page
    ; 쪽 (토큰 - 11) 의 다음 바이트 칸
    SEC
    SBC #$0011
    XBA
    STA.w !bm_g
    LDA.w !bm_buf+1,X
    AND #$00FF
    ORA.w !bm_g
    ASL
    TAX
    LDA.l !bm_charset,X
    JSR BmGlyph
.next
    INC.w !bm_p
    INC.w !bm_p
    JMP .token
.done
    ; 버퍼에서 구간(길이 바이트 + n)을 뺀다. BmEmit 이 다음 바이트를 보므로 먼저
    LDA.w !bm_n
    INC
    STA.w !bm_s
    LDX #$0000
-
    TXA
    CLC
    ADC.w !bm_s
    TAY
    SEP #$20
    LDA #$00
    CPY #$0080
    BCS +
    LDA.w !bm_buf,Y
+
    STA.w !bm_buf,X
    REP #$20
    INX
    CPX #$0080
    BCC -
    ; 끝 띄움 뒤에 구간이 아닌 것(이름 등)이 오면, 띄움을 뺀 칸 올림 틈이 3점 이상일 때 그 틈을 띄어쓰기로 쓴다.
    ; 숫자는 원래 글자 칸이 바로 붙으므로 빼지 않는다
    LDA.w !bm_tail
    AND #$00FF
    BEQ +
    STA.w !bm_s
    LDA.w !bm_buf
    AND #$00FF
    CMP #$00E3
    BEQ +
    CMP #$00FB
    BEQ +
    LDA.w !bm_x
    SEC
    SBC.w !bm_s
    STA.w !bm_v
    EOR #$FFFF
    INC
    AND #$0007
    CMP #$0003
    BCC +
    LDA.w !bm_v
    STA.w !bm_x
+
    JSR BmEmit
    PLB
    JML $24872E

; 전투 이름(24:A83C → WnBattle → WnKorean 이 !wn_glyph 에 글리프 넉 자까지를 둔 뒤). DB = 7E, M = X = 16.
; WnBattle·WnKorean 이 쌓은 PHP·PHP·PHB 를 풀고 24:A854(RTS)로 간다.
WnBattleDraw:
    JSR BmClear
    LDX #$0000
-
    LDA.w !wn_glyph,X
    CMP #$FFFF
    BEQ +
    PHX
    JSR BmGlyph
    PLX
    INX
    INX
    CPX #$0008
    BCC -
+
    JSR BmEmit
    PLB
    PLP
    PLP
    JML $24A854

; 24:A83C 의 한글 아닌 이름(WnBattle 이 PHP 한 뒤, M = 8, X = 16, 직접 페이지 $00 = 길이, $01~ = 바이트).
; 이름 표(!bm_names)에 같은 바이트가 있으면 한글로 그리고, 없으면 원래 길(24:A841)로 가나 타일을 찍는다.
BmNameLookup:
    PHB
    LDA #$7E
    PHA
    PLB
    REP #$30
    LDA.b $00
    AND #$00FF
    STA.w !bm_s
    TAX
    SEP #$20
-
    LDA.b $00,X
    STA.w !bm_band,X
    DEX
    BPL -
    REP #$20
    LDX #$0000
.entry
    LDA.l !bm_names,X
    AND #$00FF
    BNE +
    JMP .none
+
    CMP.w !bm_s
    BNE .skip
    STX.w !bm_o
    LDY #$0000
-
    SEP #$20
    LDA.l !bm_names+1,X
    CMP.w !bm_band+1,Y
    REP #$20
    BNE .miss
    INX
    INY
    CPY.w !bm_s
    BCC -
    ; 같음: X = 첫 자리 + 길이, 글리프 수는 그 다음 바이트
    LDA.l !bm_names+1,X
    AND #$00FF
    STA.w !bm_n
    INX
    INX
    STX.w !bm_p
    JSR BmClear
.token
    LDX.w !bm_p
    LDA.l !bm_names,X
    BIT #$8000
    BNE .space
    JSR BmGlyph
    BRA +
.space
    AND #$7FFF
    CLC
    ADC.w !bm_x
    STA.w !bm_x
+
    INC.w !bm_p
    INC.w !bm_p
    DEC.w !bm_n
    BNE .token
    JSR BmEmit
    PLB
    PLP
    JML $24A854
.miss
    LDX.w !bm_o
    LDA.l !bm_names,X
    AND #$00FF
.skip
    ; 다음 항목: 첫 자리 + 1 + 길이 + 1 + 글리프 수 × 2
    STX.w !bm_o
    CLC
    ADC.w !bm_o
    INC
    TAX
    LDA.l !bm_names,X
    AND #$00FF
    ASL
    STA.w !bm_v
    TXA
    INC
    CLC
    ADC.w !bm_v
    TAX
    JMP .entry
.none
    LDA #$FFFF
    STA.w !bm_last          ; 가나 이름 뒤 조사는 받침 없는 쪽
    PLB
    SEP #$20
    JML $24A841

; 띠를 비우고 점 자리를 0 으로. 앞 이름이 덜 찬 마지막 열을 넘겼으면(!bm_carry) 그 열과 점 자리를 두고 잇는다.
BmClear:
    SEP #$20
    LDA.w !bm_carry
    STZ.w !bm_carry
    REP #$20
    AND #$00FF
    BEQ +
    RTS
+
    LDX.w #!bm_w*9-2
-
    STZ.w !bm_band,X
    DEX
    DEX
    BPL -
    STZ.w !bm_x
    RTS

; A = 조사 종류. 마지막 글리프의 받침으로 고른 한두 자를 그린다. 으로/로(3)는 ㄹ 받침이면 로.
BmJosa:
    ASL
    ASL
    ASL
    STA.w !bm_s             ; 종류 × 8
    LDA.w !bm_last
    CMP.w #!bm_glyphs
    BCS .none
    TAX
    LDA.l !bm_jong,X
    AND #$00FF
    BEQ .none
    CMP #$0002
    BNE .has
    LDA.w !bm_s
    CMP #$0018
    BEQ .none
.has
    LDA.w !bm_s
    BRA +
.none
    LDA.w !bm_s
    CLC
    ADC #$0004
+
    TAX
    LDA.l !bm_josa,X
    PHX
    JSR BmGlyph
    PLX
    LDA.l !bm_josa+2,X
    CMP #$FFFF
    BEQ +
    JSR BmGlyph
+
    RTS

; A = 글리프. 띠의 !bm_x 점에 줄 1~9 를 겹치고 !bm_x 를 한 자 나아간다. 띠를 넘는 글자는 그리지 않는다.
BmGlyph:
    STA.w !bm_last
    LDA.w !bm_x
    CMP.w #(!bm_w-3)*8+1
    BCC +
    JMP .skip
+
    LDA.w !bm_last
    JSR WnFetch             ; !wn_cell, DB = 7E
    REP #$30
    LDA.w !bm_x
    AND #$0007
    STA.w !bm_s
    LDA.w !bm_x
    LSR
    LSR
    LSR
    STA.w !bm_o
    LDA #$0001
    STA.w !bm_r
.row
    SEP #$20
    LDX.w !bm_r
    LDA.w !wn_cell,X
    STA.w !bm_sh
    LDA.w !wn_cell+16,X
    STA.w !bm_sh+1
    STZ.w !bm_sh+2
    LDX.w !bm_s
    BEQ +
-
    LSR.w !bm_sh
    ROR.w !bm_sh+1
    ROR.w !bm_sh+2
    DEX
    BNE -
+
    REP #$20
    ; 띠 자리 = (줄 - 1) × !bm_w + 바이트
    LDA.w !bm_r
    DEC
    STA.w !bm_v
    ASL
    ASL
    ASL
    ASL
    ASL                     ; × 32
    SEC
    SBC.w !bm_v
    SEC
    SBC.w !bm_v
    SEC
    SBC.w !bm_v             ; × 29
    CLC
    ADC.w !bm_o
    TAX
    SEP #$20
    LDA.w !bm_band,X
    ORA.w !bm_sh
    STA.w !bm_band,X
    LDA.w !bm_band+1,X
    ORA.w !bm_sh+1
    STA.w !bm_band+1,X
    LDA.w !bm_band+2,X
    ORA.w !bm_sh+2
    STA.w !bm_band+2,X
    REP #$20
    INC.w !bm_r
    LDA.w !bm_r
    CMP #$000A
    BCC .row
.skip
    LDA.w !bm_x
    CLC
    ADC.w #!bm_glyph_px
    STA.w !bm_x
    RTS

; 띠를 열마다 칸으로 올리고 코드를 글 큐에 쓴 뒤 FF 로 끝낸다. 다음 바이트가 한글 구간(E3)이면 덜 찬 마지막 열은
; 올리지 않고 띠 첫 열로 옮겨 구간이 이어 그리게 한다(이름과 조사 사이가 벌어지지 않게).
BmEmit:
    JSR BmMark
    STZ.w !bm_q
    STZ.w !bm_c
    LDA.w !bm_x
    CLC
    ADC #$0007
    STA.w !bm_g
    LDA.w !bm_x
    AND #$0007
    BEQ .count
    LDA.w !bm_buf
    AND #$00FF
    CMP #$00E3
    BNE .count
    LDA.w !bm_x
    STA.w !bm_g
    SEP #$20
    LDA #$01
    STA.w !bm_carry
    REP #$20
.count
    LDA.w !bm_g
    LSR
    LSR
    LSR
    STA.w !bm_g             ; 올릴 열 수
.col
    LDA.w !bm_g
    CMP.w !bm_c
    BEQ .end
    BCC .end
    JSR BmColumn
    LDX.w !bm_q
    SEP #$20
    STA.w !bm_queue,X
    REP #$20
    INC.w !bm_q
    INC.w !bm_c
    LDA.w !bm_q
    CMP #$003F
    BCC .col
.end
    LDX.w !bm_q
    SEP #$20
    LDA #$FF
    STA.w !bm_queue,X
    LDA.w !bm_carry
    REP #$20
    AND #$00FF
    BEQ +
    ; 덜 찬 열(!bm_g)을 줄마다 첫 열로, 나머지를 비우고 점 자리를 그 열 안으로
    STZ.w !bm_v             ; 줄 첫 자리
.move
    LDA.w !bm_v
    CLC
    ADC.w !bm_g
    TAX
    SEP #$20
    LDA.w !bm_band,X
    PHA
    LDX.w !bm_v
    LDY.w #!bm_w
-
    STZ.w !bm_band,X
    INX
    DEY
    BNE -
    LDX.w !bm_v
    PLA
    STA.w !bm_band,X
    REP #$20
    LDA.w !bm_v
    CLC
    ADC.w #!bm_w
    STA.w !bm_v
    CMP.w #!bm_w*9
    BCC .move
    LDA.w !bm_x
    AND #$0007
    STA.w !bm_x
+
    RTS

; 격자와 큐에 있는 풀 코드를 쓰는 중으로 표시한다.
BmMark:
    LDX.w #!bm_count-1
    SEP #$20
-
    STZ.w !bm_used,X
    DEX
    BPL -
    REP #$20
    LDY #$0000
-
    LDA.w !bm_grid,Y
    JSR .one
    INY
    CPY #$009C
    BCC -
    LDY #$0000
-
    LDA.w !bm_queue,Y
    JSR .one
    INY
    CPY #$0040
    BCC -
    RTS
.one
    AND #$00FF
    TAX
    LDA.l !bm_index,X
    AND #$00FF
    CMP #$00FF
    BEQ +
    TAX
    SEP #$20
    LDA #$01
    STA.w !bm_used,X
    REP #$20
+
    RTS

; 열 !bm_c 하나. 돌려주는 A = 코드(빈 열이거나 풀이 모자라면 빈칸 01).
BmColumn:
    ; 아래 줄 8바이트(띠 줄 1~8)와 위 줄 무늬(띠 줄 0)
    LDX.w !bm_c
    LDY #$0000
    STZ.w !bm_v
-
    TXA
    CLC
    ADC.w #!bm_w
    TAX
    SEP #$20
    LDA.w !bm_band,X
    STA.w !bm_t8,Y
    ORA.w !bm_v
    STA.w !bm_v
    REP #$20
    INY
    CPY #$0008
    BCC -
    LDX.w !bm_c
    SEP #$20
    LDA.w !bm_band,X
    STA.w !bm_pt
    ORA.w !bm_v
    REP #$20
    AND #$00FF
    BNE +
    LDA #$0001
    RTS
+
    JSR BmFree
    BCC +
    JMP .full
+
    STA.w !bm_k
    TAX
    SEP #$20
    LDA #$00
    STA.w !bm_pat,X
    STA.w !bm_up,X
    REP #$20
    JSR BmSend
    ; 위 줄 무늬가 있으면 위 칸(첫 줄이면 창 테두리 바탕)을 함께 쓰거나 새로
    LDA.w !bm_pt
    AND #$00FF
    BEQ .code
    SEP #$20
    LDA.w $0F0E             ; 글을 찍는 줄
    BEQ +
    LDA #$00
    BRA ++
+
    LDA #$01
++
    STA.w !bm_bs
    REP #$20
    LDA.w !bm_k
    PHA
    JSR BmUpper
    PLX
    STX.w !bm_k
    BCS .code               ; 위 칸이 모자라면 아래 칸만
    SEP #$20
    STA.w !bm_up,X
    REP #$20
.code
    LDX.w !bm_k
    LDA.l !bm_codes,X
    AND #$00FF
    RTS
.full
    LDA #$0001
    RTS

; 쓰지 않는 풀 번호를 A 로(C = 0), 없으면 C = 1. 고른 번호는 쓰는 중으로.
BmFree:
    LDX #$0000
-
    SEP #$20
    LDA.w !bm_used,X
    BEQ +
    REP #$20
    INX
    CPX.w #!bm_count
    BCC -
    SEC
    RTS
+
    LDA #$01
    STA.w !bm_used,X
    REP #$20
    TXA
    CLC
    RTS

; 무늬 !bm_pt·바탕 !bm_bs(0 빈칸, 1 창 위 테두리 8D)의 위 칸. 같은 칸이 있으면 그 코드, 없으면 새로 올린다.
; A = 코드, C = 1 이면 풀이 모자람.
BmUpper:
    LDX #$0000
-
    SEP #$20
    LDA.w !bm_used,X
    BEQ +
    LDA.w !bm_pat,X
    CMP.w !bm_pt
    BNE +
    LDA.w !bm_up,X
    CMP.w !bm_bs
    BEQ .found
+
    REP #$20
    INX
    CPX.w #!bm_count
    BCC -
    JSR BmFree
    BCC +
    RTS
+
    STA.w !bm_k
    TAX
    SEP #$20
    LDA.w !bm_pt
    STA.w !bm_pat,X
    LDA.w !bm_bs
    STA.w !bm_up,X          ; 위 칸은 짝 코드 대신 바탕
    REP #$20
    JSR BmSendUpper
    LDX.w !bm_k
.found
    REP #$20
    LDA.l !bm_codes,X
    AND #$00FF
    CLC
    RTS

; 위 칸 !bm_k 를 무늬·바탕으로 다시 만들어 올린다. 빈 바탕은 평면 0 만(7줄째 = 무늬), 테두리 바탕은 8D 두 평면에
; 7줄째 무늬를 색 3 으로.
BmSendUpper:
    LDX.w !bm_k
    SEP #$20
    LDA.w !bm_pat,X
    STA.w !bm_pt
    LDA.w !bm_up,X
    REP #$20
    AND #$00FF
    BNE .border
    LDX #$0006
-
    STZ.w !bm_t8,X
    DEX
    DEX
    BPL -
    SEP #$20
    LDA.w !bm_pt
    STA.w !bm_t8+7
    REP #$20
    LDA #$0101
    STA.w !bm_r
    LDA.w #!bm_t8
    BRA BmQueue
.border
    LDX #$0000
-
    TXA
    LSR
    TAY
    SEP #$20
    TYX
    LDA.l $04E978+(($8D-$8B)*16),X
    XBA
    LDA.l $04E980+(($8D-$8B)*16),X
    XBA
    CPX #$0007
    BNE +
    ORA.w !bm_pt
    XBA
    ORA.w !bm_pt
    XBA
+
    REP #$20
    PHA
    TYA
    ASL
    TAX
    PLA
    STA.w !wn_stage,X
    INX
    INX
    CPX #$0010
    BCC -
    LDA #$0100
    STA.w !bm_r
    LDA.w #!wn_stage
    BRA BmQueue

; 풀 번호 !bm_k 칸에 !bm_t8 을 올린다(평면 0, 평면 1 은 FF). 풀 B 칸이면 사본에도 둔다.
BmSend:
    LDA.w !bm_k
    CMP.w #!bm_b0
    BCC +
    CMP.w #!bm_b1
    BCS +
    SEC
    SBC.w #!bm_b0
    ASL
    ASL
    ASL
    TAY
    LDX #$0000
-
    LDA.w !bm_t8,X
    STA.w !bm_shadow,Y
    INY
    INY
    INX
    INX
    CPX #$0008
    BCC -
+
    LDA #$0101
    STA.w !bm_r
    LDA.w #!bm_t8
    ; 이어서 BmQueue

; 우리 대기열 항목 [VRAM 워드][방식 · 칸 1]![그림]. A = 그림 자리(7E), !bm_r = 방식 낱말(0101 = 평면 0 8바이트,
; 0100 = 두 평면 16바이트), 칸은 풀 번호 !bm_k. WqStage 처럼 NMI 를 잠시 끄고 쓴다.
BmQueue:
    STA.w !bm_o
    LDA.w !bm_k
    ASL
    TAX
    LDA.l !bm_tile,X
    ASL
    ASL
    ASL
    CLC
    ADC #$1000
    STA.w !bm_v
    LDA #$0010
    STA.w !bm_s
    LDA.w !bm_r
    AND #$00FF
    BEQ +
    LDA #$0008
    STA.w !bm_s
+
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
    ADC #$0004
    CLC
    ADC.w !bm_s
    CMP #!wq_size+1
    BCC .room
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
    LDA.w !bm_v
    STA.w !wq_buf,Y
    LDA.w !bm_r
    STA.w !wq_buf+2,Y
    LDX.w !bm_o
-
    LDA.w $0000,X
    STA.w !wq_buf+4,Y
    INX
    INX
    INY
    INY
    DEC.w !bm_s
    DEC.w !bm_s
    BNE -
    TYA
    CLC
    ADC #$0004
    STA.w !wq_off
    SEP #$20
    LDA.w !wq_count
    INC
    STA.w !wq_count
    LDA.b $1E
    STA.l $004200
    REP #$20
    RTS

; 22:D796(M = 8). 화면 격자에 있는 풀 B 칸을 다시 올린다(아래 칸은 사본, 위 칸은 무늬로 다시 만듦).
BmRestore:
    LDA $19
    AND #$FD
    STA $19
    PHP
    REP #$30
    PHA
    PHX
    PHY
    PHB
    SEP #$20
    LDA #$7E
    PHA
    PLB
    REP #$30
    JSR BmMark
    LDA.w #!bm_b0
    STA.w !bm_k
-
    LDX.w !bm_k
    SEP #$20
    LDA.w !bm_used,X
    REP #$20
    AND #$00FF
    BEQ +
    SEP #$20
    LDA.w !bm_pat,X
    REP #$20
    AND #$00FF
    BEQ .char
    JSR BmSendUpper
    BRA +
.char
    TXA
    SEC
    SBC.w #!bm_b0
    ASL
    ASL
    ASL
    TAY
    LDA.w !bm_shadow,Y
    STA.w !bm_t8
    LDA.w !bm_shadow+2,Y
    STA.w !bm_t8+2
    LDA.w !bm_shadow+4,Y
    STA.w !bm_t8+4
    LDA.w !bm_shadow+6,Y
    STA.w !bm_t8+6
    JSR BmSend
+
    INC.w !bm_k
    LDA.w !bm_k
    CMP.w #!bm_b1
    BCC -
    PLB
    PLY
    PLX
    PLA
    PLP
    JML $22D79C

; 24:A595(JSL, M = 8, X = 16). 줄이 반 칸 올라 첫 줄 위(테두리 줄 1DD5)가 8D 로 채워지고 둘째 줄 위 칸이 1DEF 에 온 때.
; 원래처럼 탁점 84·83 은 92·93 으로, 빈 바탕 위 칸은 같은 무늬의 테두리 바탕 칸으로 1DD5 에 쓴다.
BmScroll:
    PHB
    PHP
    SEP #$20
    LDA #$7E
    PHA
    PLB
    REP #$30
    JSR BmMark
    LDX #$0000
.col
    SEP #$20
    LDA.w $1DEF,X
    CMP #$84
    BNE +
    LDA #$92
    BRA .put
+
    CMP #$83
    BNE +
    LDA #$93
    BRA .put
+
    REP #$20
    AND #$00FF
    PHX
    TAX
    LDA.l !bm_index,X
    AND #$00FF
    CMP #$00FF
    BEQ .skip
    TAX
    SEP #$20
    LDA.w !bm_pat,X
    BEQ .skip
    STA.w !bm_pt
    LDA.w !bm_up,X
    BNE .skip               ; 이미 테두리 바탕
    LDA #$01
    STA.w !bm_bs
    REP #$20
    JSR BmUpper
    BCS .skip
    PLX
    SEP #$20
.put
    STA.w $1DD5,X
    BRA .next
.skip
    REP #$20
    PLX
.next
    REP #$20
    INX
    CPX #$001A
    BCS +
    JMP .col
+
    PLP
    PLB
    RTL
