; 전투 메시지의 한글 구간과 이름. dq4windowname.py 가 dq4windowname.asm 뒤에 붙여 함께 넣고, 정의(!bm_*)는
; dq4battlemsg.py 가 만든다. 형식은 sfc/dq4/docs/dq4-battle-text-format.md.
;
; 전투 글은 바이트가 곧 BG3 타일 번호다. 구간(E3 n 바이트…)과 이름을 Galmuri9 띠로 그려, 칸 풀(코드 85개 ↔ 타일 85칸)에서
; 화면 격자와 글 큐에 없는 코드를 골라 올리고, 그 코드를 글 큐 0ECB 에 넣는다. 글자 맨 윗줄은 위 줄 칸 하나에 담기는
; 1바이트 무늬라 같은 무늬는 위 줄 칸을 함께 쓴다. 큐에는 아래 칸 코드와 짝 위 칸 코드(없으면 00)를 짝으로 넣고,
; WnBattleChar 가 아래 칸을 쓸 때 짝을 꺼내 위 줄에 쓴다.

; 코드 E3 의 처리기. 24:86F2 표는 뱅크 24 안 주소라, 옮긴 디코더가 비운 트리 자리에 받침을 둔다.
org !bm_run_table
    dw !bm_run_stub
org !bm_run_stub
    JML BmRun
; 줄 바꿈(24:A4F3, 셋째 줄이면 글을 올림)을 뱅크 60 에서 부르는 받침
BmNewLine:
    JSR $A4F3
    RTL
; 글자 하나 쓰기(24:A4A4, A = 바이트)
BmPutChar:
    JSR $A4A4
    RTL
; 연출 끝(22:D796 LDA $19 / AND #$FD / STA $19). 큰 주문 연출이 덮은 풀 B 칸을 사본에서 다시 올린다.
org $22D796
    JML BmRestore
    NOP
    NOP
; 줄이 올라갈 때 둘째 줄 위 칸을 첫 줄 위(창 위 테두리 줄)로 옮기는 고리(24:A595~A5B1: 탁점 84·83 → 테두리+탁점 92·93).
; 빈 바탕 위 칸도 같은 무늬의 테두리 바탕 칸으로 바꾼다.
org $24A595
    JSL BmScroll
    BRA BmScrolled
; 24:A569 는 JSR 로 불리므로 원래 고리 끝(A5B2)으로 가야 한다. 근처 24:A54D 는 PLP/RTL 꼬리라 거기로 가면 스택이 한 바이트
; 어긋난다. 24비트 숫자 주소로 BRA 를 쓰면 asar 가 낮은 바이트를 거리로 넣으므로 라벨로 둔다
org $24A5B2
BmScrolled:
org $04BFF5
    JML BmEncounter

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
    JSR BmCarrySave
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
    ; 끝 띄움 뒤에 구간이 아닌 것(이름 등)이 오면, 띄움을 뺀 칸 올림 틈이 3점 이상일 때 그 틈을 띄어쓰기로 쓴다.
    ; 숫자는 원래 글자 칸이 바로 붙으므로 빼지 않는다. 줄 넘김 검사(BmCarryWrap)가 줄인 폭을 보도록 그보다 먼저
    LDA.w !bm_tail
    AND #$00FF
    BEQ ++
    CMP #$0080              ; 좁은 부호 뒤 당김(음수)은 띄움이 아니다. 빼면 !bm_x 가 FFxx 로 깨진다
    BCS ++
    STA.w !bm_s
    LDX.w !bm_n
    LDA.w !bm_buf+1,X       ; 구간 다음 바이트(버퍼를 당기기 전)
    AND #$00FF
    CMP #$00E3
    BEQ ++
    CMP #$00FB
    BEQ ++
    LDA.w !bm_x
    SEC
    SBC.w !bm_s
    STA.w !bm_v
    EOR #$FFFF
    INC
    AND #$0007
    CMP #$0003
    BCC ++
    LDA.w !bm_v
    STA.w !bm_x
++
    JSR BmCarryWrap
    BCC +
    JMP .token
+
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
    JSR BmFind
    BCS .none
    JSR BmClear
    JSR BmTokens
    JSR BmEmit
    PLB
    PLP
    JML $24A854
.none
    ; 가나 이름도 Galmuri 가나로 그린다. 원래 길은 가나 바이트를 격자에 쓰는데, 그 바이트는 칸 풀 코드로 쓴다
    JSR BmClear
    JSR BmKana
    JSR BmEmit
    PLB
    PLP
    JML $24A854

; 직접 페이지 $00 = 길이, $01~ = 가나 이름 바이트를 띠에 그린다. 84·83 은 다음 바이트의 탁점·반탁점,
; 02~0B 는 숫자. 가나 표(!wn_kana_table)에 없는 바이트는 띄움 하나로.
BmKana:
    LDA.b $00
    AND #$00FF
    STA.w !bm_n             ; BmGlyph 가 !bm_s 를 쓴다
    LDX #$0000
.byte
    TXA
    CMP.w !bm_n
    BCC +
    RTS
+
    LDA.b $01,X
    AND #$00FF
    STZ.w !bm_r
    CMP #$0084
    BNE +
    LDA #$0100
    BRA ++
+
    CMP #$0083
    BNE +++
    LDA #$0200
++
    STA.w !bm_r
    INX
    LDA.b $01,X
    AND #$00FF
+++
    INX
    PHX
    CMP #$0002
    BCC .unknown
    CMP #$000C
    BCS .kana
    ; 숫자는 글리프 폭대로 붙인다(한글 간격이면 「1 0 0」처럼 벌어짐)
    SEC
    SBC #$0002
    PHA
    CLC
    ADC.w #!bm_digit0
    JSR BmGlyph
    PLX
    LDA.l BmDigitAdv,X
    AND #$00FF
    CMP #$0080
    BCC +
    ORA #$FF00
+
    CLC
    ADC.w !bm_x
    STA.w !bm_x
    PLX
    BRL .byte
.kana
    CMP #$0080
    BCS .unknown
    ASL
    CLC
    ADC.w !bm_r
    TAX
    LDA.l !wn_kana_table,X
    CMP #$FFFF
    BEQ .unknown
.glyph
    JSR BmGlyph
    PLX
    BRL .byte
.unknown
    LDA.w !bm_x
    CLC
    ADC.w #!bm_space
    STA.w !bm_x
    PLX
    BRL .byte

; 숫자 0~9 마다 글리프 폭 − 한글 간격(부호 있는 점 수)
BmDigitAdv:
    db !bm_digit_adv

; 직접 페이지 $00 = 길이, $01~ = 이름 바이트를 이름 표(!bm_names)에서 찾는다(DB = 7E, M = X = 16).
; 있으면 C = 0, !bm_p = 첫 토큰 자리, !bm_n = 토큰 수. 없으면 C = 1.
BmFind:
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
    SEC
    RTS
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
    ; 같음: X = 첫 자리 + 길이, 토큰 수는 그 다음 바이트
    LDA.l !bm_names+1,X
    AND #$00FF
    STA.w !bm_n
    INX
    INX
    STX.w !bm_p
    CLC
    RTS
.miss
    LDX.w !bm_o
    LDA.l !bm_names,X
    AND #$00FF
.skip
    ; 다음 항목: 첫 자리 + 1 + 길이 + 1 + 토큰 수 × 2
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

; !bm_names + !bm_p 의 토큰 !bm_n 개를 띠에 그린다. 토큰: 글리프, 8000 + 띄울 점(낮은 바이트, 부호 있음),
; C000 + 조사 종류.
BmTokens:
    LDA.w !bm_n
    BNE +
    RTS
+
    LDX.w !bm_p
    LDA.l !bm_names,X
    BIT #$8000
    BNE .special
    JSR BmGlyph
    BRA .next
.special
    BIT #$4000
    BEQ .space
    AND #$00FF
    JSR BmJosa
    BRA .next
.space
    AND #$00FF
    CMP #$0080
    BCC +
    ORA #$FF00
+
    CLC
    ADC.w !bm_x
    STA.w !bm_x
.next
    INC.w !bm_p
    INC.w !bm_p
    DEC.w !bm_n
    BRA BmTokens

; 04:BFF5(PHP / PHX / REP #$20 자리, M = 8, X = 16). 전투 첫머리 창 25 의 한 줄 「(이름)が　あらわれた！」.
; 이름이 이름 표에 있으면 「(이름){이} 나타났다!」를 띠로 그려, 줄 k = $0A4C / 2 마다 BG3 칸 B0 + k × 52 에서 아래 칸
; 26·위 칸 26 을 쓴다. 전투가 막 시작해 연출이 B0~17F 를 아직 쓰지 않고, 이 창은 명령 창이 뜨기 전에 닫힌다.
; 위 칸은 그 자리 타일(첫 줄은 창 위 테두리)에 글자 맨 윗줄을 겹친다. 끝나면 원래처럼 04:C044(창 전송·다음 줄)로.
BmEncounter:
    PHP
    PHX
    REP #$20
    PHB
    SEP #$20
    LDA #$7E
    PHA
    PLB
    REP #$30
    JSR BmFind
    BCC +
    PLB
    REP #$20
    JML $04BFF9
+
    SEP #$20
    STZ.w !bm_carry
    REP #$20
    JSR BmClear
    JSR BmTokens
    LDA.w #!bm_appear-!bm_names
    STA.w !bm_p
    LDA.w #!bm_appear_count
    STA.w !bm_n
    JSR BmTokens
    ; 줄 자리 Y = $0E0B + $0A4C × 40, 첫 칸 B0 + ($0A4C / 2) × 52
    LDA.w $0E0B
    LDX.w $0A4C
    BEQ +
-
    CLC
    ADC #$0040
    DEX
    BNE -
+
    STA.w !bm_o
    LDA.w $0A4C
    LSR
    STA.w !bm_s
    ASL
    ASL
    CLC
    ADC.w !bm_s             ; × 5
    ASL
    ASL                     ; × 20
    STA.w !bm_v
    LDA.w !bm_s
    ASL
    ASL
    ASL
    ASL
    ASL                     ; × 32
    CLC
    ADC.w !bm_v             ; × 52
    CLC
    ADC #$00B0
    STA.w !bm_g             ; 이 줄 첫 칸
    STZ.w !bm_c
.col
    LDA.w !bm_x
    CLC
    ADC #$0007
    LSR
    LSR
    LSR
    CMP #$001A
    BCC +
    LDA #$001A
+
    CMP.w !bm_c
    BEQ .done
    BCC .done
    JSR BmEncCol
    INC.w !bm_c
    BRA .col
.done
    PLB
    SEP #$20
    REP #$10
    JML $04C044

; 첫머리 줄의 열 !bm_c. 아래 칸 = !bm_g + 열, 위 칸 = !bm_g + 26 + 열. 타일맵 버퍼($E0 + 줄 자리)의 낮은 바이트와 bit8.
BmEncCol:
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
    REP #$20
    LDA.w !bm_v
    AND #$00FF
    BEQ .upper
    LDA.w !bm_g
    CLC
    ADC.w !bm_c
    PHA
    ASL
    ASL
    ASL
    CLC
    ADC #$1000
    STA.w !bm_v
    LDA #$0101
    STA.w !bm_r
    LDA.w #!bm_t8
    JSR BmQueueAt
    PLA
    PHA
    LDA.w !bm_c
    ASL
    CLC
    ADC.w !bm_o
    CLC
    ADC.b $E0
    TAY
    PLA
    JSR BmEncCell
.upper
    LDA.w !bm_pt
    AND #$00FF
    BNE +
    RTS
+
    ; 위 칸 바탕: 그 자리의 지금 타일
    LDA.w !bm_c
    ASL
    CLC
    ADC.w !bm_o
    SEC
    SBC #$0040
    CLC
    ADC.b $E0               ; 첫 줄은 Y - 40 이 음수라 ($E0),Y 로는 뱅크를 넘는다. 16비트로 더해 7E 안에서
    TAX
    LDA.w $0000,X
    AND #$03FF
    STA.w !wn_base
    STZ.w !wn_r
-
    JSR WnBaseRow           ; A = p0 | p1 << 8
    PHA
    LDA.w !wn_r
    CMP #$0007
    BNE +
    PLA
    SEP #$20
    ORA.w !bm_pt
    XBA
    ORA.w !bm_pt
    XBA
    REP #$20
    PHA
+
    LDA.w !wn_r
    ASL
    TAX
    PLA
    STA.w !wn_stage,X
    INC.w !wn_r
    LDA.w !wn_r
    CMP #$0008
    BCC -
    LDA.w !bm_g
    CLC
    ADC #$001A
    CLC
    ADC.w !bm_c
    PHA
    ASL
    ASL
    ASL
    CLC
    ADC #$1000
    STA.w !bm_v
    LDA #$0100
    STA.w !bm_r
    LDA.w #!wn_stage
    JSR BmQueueAt
    LDA.w !bm_c
    ASL
    CLC
    ADC.w !bm_o
    SEC
    SBC #$0040
    CLC
    ADC.b $E0
    TAY
    PLA
    ; 이어서 BmEncCell

; A = 타일 번호를 7E:Y 낱말에. 높은 바이트는 bit8 만 바꾸고 나머지(우선·팔레트)는 둔다.
BmEncCell:
    SEP #$20
    STA.w $0000,Y
    XBA
    AND #$01
    STA.w !bm_pt+1
    LDA.w $0001,Y
    AND #$FE
    ORA.w !bm_pt+1
    STA.w $0001,Y
    REP #$20
    RTS

; 앞 이름의 덜 찬 열을 이어 받았으면(줄 첫 칸이 아닐 때만) 그 점 자리·띠 첫 열·마지막 글리프를 둔다. 구간을 다 그린
; 뒤 한 줄에 들지 않으면 BmCarryWrap 이 이 열만 앞 줄에 찍고 구간을 다음 줄 첫머리부터 다시 그린다. 폭을 미리 어림하지
; 않고 실제로 그려서 재므로 글리프·띄움 폭이 바뀌어도 맞는다.
BmCarrySave:
    STZ.w !bm_cx
    LDA.w !bm_x
    BEQ +
    LDA.w $0F0D
    AND #$00FF
    BEQ +
    LDA.w !bm_x
    STA.w !bm_cx
    LDA.w !bm_last
    STA.w !bm_cl
    SEP #$20
    LDX #$0000
    LDY #$0000
-
    LDA.w !bm_band,X
    STA.w !bm_col0,Y
    REP #$20
    TXA
    CLC
    ADC.w #!bm_w
    TAX
    SEP #$20
    INY
    CPY #$0009
    BCC -
    REP #$20
+
    RTS

; C = 1 이면 다시 그릴 준비를 마쳤다(!bm_p = 1, 띠 빔, 줄 바뀜).
BmCarryWrap:
    LDA.w !bm_cx
    BNE +
    CLC
    RTS
+
    STZ.w !bm_cx
    LDA.w !bm_x
    CLC
    ADC #$0007
    LSR
    LSR
    LSR
    STA.w !bm_s
    LDA.w $0F0D
    AND #$00FF
    CLC
    ADC.w !bm_s
    CMP #$001B
    BCS +
    CLC
    RTS
+
    ; 띠 첫 열을 이어 받은 그대로 되돌려 칸으로 올려 찍는다. 짝 위 칸은 WnBattleChar 가 큐 머리에서 꺼낸다
    SEP #$20
    LDX #$0000
    LDY #$0000
-
    LDA.w !bm_col0,Y
    STA.w !bm_band,X
    REP #$20
    TXA
    CLC
    ADC.w #!bm_w
    TAX
    SEP #$20
    INY
    CPY #$0009
    BCC -
    REP #$20
    JSR BmMark
    STZ.w !bm_c
    JSR BmColumn
    PHA
    JSR BmDrain
    PLA
    SEP #$20
    CMP #$01
    BEQ +
    STA.w !bm_pt+1
    LDA.w !bm_upc
    STA.w !bm_queue
    LDA #$FF
    STA.w !bm_queue+1
    LDA #$24
    PHA
    PLB
    LDA.l $7E0000|!bm_pt+1
    JSL BmPutChar
    LDA #$7E
    PHA
    PLB
+
    LDA #$24
    PHA
    PLB
    REP #$30
    JSL BmNewLine
    SEP #$20
    LDA #$7E
    PHA
    PLB
    STZ.w !bm_carry
    REP #$30
    JSR BmClear
    LDA.w !bm_cl
    STA.w !bm_last
    LDA #$0001
    STA.w !bm_p
    SEC
    RTS

; 올린 칸 그림이 VRAM 에 닿을 때까지 기다린다(DB = 7E, M = X = 16). 전투 NMI 는 창 타일맵 요청($0BEC)이 있으면 우리
; 대기열을 다음 NMI 로 미루므로(WqNmiGate), 기다리지 않고 글자를 격자에 쓰면 타일맵이 먼저 가 한 프레임 동안 새로 고른
; 칸이 옛 그림으로 보였다. NMI 가 꺼져 있으면 BmQueueAt 처럼 VBlank 마다 직접 보내고, 켜져 있으면 약 10프레임까지만 돈다.
BmDrain:
    SEP #$20
    LDA.b $1E
    BPL .direct
    LDX #$0000
-
    LDA.w !wq_count
    BEQ .done
    DEX
    BNE -
.done
    REP #$20
    RTS
.direct
    LDA.w !wq_count
    BEQ .done
-
    LDA.l $004212
    BMI -
-
    LDA.l $004212
    BPL -
    JSL WqNmi
    SEP #$20
    LDA.l $004210
    BRA .direct

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
    ; 띠가 홀수 바이트라 두 바이트씩 지우면 맨 앞 바이트(줄 0 열 0)가 남는다. 남으면 앞 띠의 점이 위 칸에 찍힌다
    SEP #$20
    STZ.w !bm_band
    REP #$20
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
    ; 지금 칸 + 이 띠의 열 수가 한 줄(26칸)을 넘고 줄 첫 칸이 아니면 먼저 줄을 바꾼다(긴 이름). 줄이 바뀌면 첫 줄인지가
    ; 달라지므로 칸 고르기보다 먼저
    LDA.w $0F0D
    AND #$00FF
    BEQ .fit
    STA.w !bm_v
    LDA.w !bm_x
    CLC
    ADC #$0007
    LSR
    LSR
    LSR
    CLC
    ADC.w !bm_v
    CMP #$001B
    BCC .fit
    PHB
    SEP #$20
    LDA #$24
    PHA
    PLB
    REP #$30
    JSL BmNewLine
    REP #$30
    PLB
.fit
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
    INX
    CMP #$01
    BEQ +
    LDA.w !bm_upc           ; 풀 코드 뒤에는 늘 짝 위 칸 코드
    STA.w !bm_queue,X
    INX
+
    REP #$20
    STX.w !bm_q
    INC.w !bm_c
    LDA.w !bm_q
    CMP #$003E
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
    JMP BmDrain

; 격자와 큐에 있는 풀 코드를 쓰는 중으로 표시한다.
BmMark:
    LDX.w #!bm_bits-2
-
    STZ.w !bm_used,X
    DEX
    DEX
    BPL -
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
    JSR BmUsedSet
+
    RTS

; 풀 번호 X 의 비트: Y = 바이트 자리, A = 마스크(Y·X 는 BmUsed*·BmBase* 가 지킨다).
BmBit:
    TXA
    LSR
    LSR
    LSR
    TAY
    TXA
    AND #$0007
    PHX
    TAX
    LDA.l BmMasks,X
    AND #$00FF
    PLX
    RTS
BmMasks:
    db $01,$02,$04,$08,$10,$20,$40,$80

; 쓰는 중 비트. BmUsedGet 은 Z = 1 이면 비어 있음.
BmUsedGet:
    PHY
    JSR BmBit
    AND.w !bm_used,Y
    PLY
    AND #$00FF
    RTS
BmUsedSet:
    PHY
    JSR BmBit
    ORA.w !bm_used,Y
    STA.w !bm_used,Y
    PLY
    RTS

; 위 칸 바탕 비트(1 = 창 위 테두리). BmBaseGet 은 A = 0 또는 1. BmBaseSet 은 !bm_bs 대로.
BmBaseGet:
    PHY
    JSR BmBit
    AND.w !bm_base,Y
    PLY
    AND #$00FF
    BEQ +
    LDA #$0001
+
    RTS
BmBaseSet:
    PHY
    JSR BmBit
    PHA
    EOR #$FFFF
    AND.w !bm_base,Y
    STA.w !bm_base,Y
    PLA
    PHA
    LDA.w !bm_bs
    AND #$00FF
    BEQ +
    PLA
    ORA.w !bm_base,Y
    STA.w !bm_base,Y
    PLY
    RTS
+
    PLA
    PLY
    RTS

; 열 !bm_c 하나. 돌려주는 A = 아래 칸 코드(빈 열이거나 풀이 모자라면 빈칸 01), !bm_upc = 짝 위 칸 코드(없으면 00).
BmColumn:
    ; 아래 줄 8바이트(띠 줄 1~8)와 위 줄 무늬(띠 줄 0)
    SEP #$20
    STZ.w !bm_upc
    REP #$20
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
    STA.w !bm_upc
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
    JSR BmUsedGet
    BEQ +
    INX
    CPX.w #!bm_count
    BCC -
    SEC
    RTS
+
    JSR BmUsedSet
    TXA
    CLC
    RTS

; 무늬 !bm_pt·바탕 !bm_bs(0 빈칸, 1 창 위 테두리 8D)의 위 칸. 같은 칸이 있으면 그 코드, 없으면 새로 올린다.
; A = 코드, C = 1 이면 풀이 모자람.
BmUpper:
    LDX #$0000
-
    JSR BmUsedGet
    BEQ +
    SEP #$20
    LDA.w !bm_pat,X
    CMP.w !bm_pt
    REP #$20
    BNE +
    JSR BmBaseGet
    SEP #$20
    CMP.w !bm_bs
    REP #$20
    BEQ .found
+
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
    REP #$20
    JSR BmBaseSet
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
    REP #$20
    JSR BmBaseGet
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
    PHA
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
    PLA
    ; 이어서 BmQueueAt

; A = 그림 자리, !bm_v = VRAM 워드, !bm_r = 방식 낱말.
BmQueueAt:
    STA.w !wn_k             ; 창 이름 임시(이름 그리기가 끝난 뒤라 비어 있음)
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
    LDX.w !wn_k
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
    JSR BmUsedGet
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
    REP #$20
    JSR BmBaseGet
    BNE .skip               ; 이미 테두리 바탕
    SEP #$20
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
