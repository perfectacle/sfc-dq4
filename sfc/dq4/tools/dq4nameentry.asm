; 조합형 이름 입력. dq4nameentry.py 가 조합 표·글리프와 함께 asar 로 넣는다.
; 형식은 sfc/dq4/docs/dq4-menu-format.md. 조합 규칙·상태 스택은 슈퍼 마리오 RPG 한글 패치 v1.3 의 name_entry.asm 과 같다.
;
; 03:8B72(이름 입력)에 들어오면 메뉴 표시 7E:1BB0 = A5 일 때만 NeKorean 으로 간다. 게임 안의 이름 짓기(뱅크 06)는
; 맵을 불러올 때 표시가 지워지므로 원래 루틴 그대로다. 결과는 원래와 같이 $72~ 에 이름 바이트, $71 에 그 길이,
; $E8 은 음이 아닌 값으로 돌려준다(25:80FF 가 $E8 bit7 이면 만들기를 그만둠, 25:84B9 가 $71 뒤를 01 로 채워 복사).

lorom
incsrc "dq4nameentry-defs.asm"

!flag        = $7E1BB0
!list_count  = $7E0758      ; NMI 전송 목록(00:8CF9): 항목 수
!list_offset = $7E0759      ; 쓸 자리(16비트), 목록은 7E:4000~
!field_upper = $27C0        ; 타일 2F8 의 VRAM 워드
!field_lower = $2FC0        ; 타일 3F8

; 7F:F000~ 은 메뉴·이름 입력 동안 전원 초기화 말고는 읽기·쓰기가 없던 자리. 루틴 안에서 DB = 7F.
!ne_n     = $F000           ; 확정한 글자 수
!ne_ch    = $F002           ; 4 워드, 글리프 번호
!ne_sp    = $F00A           ; 조합 스택의 상태 수(0 = 조합 중 아님)
!ne_stk   = $F00C           ; 6 상태 × 4바이트: 초성, 중성, 종성, 안 씀(FF = 없음)
!ne_state_end = $F024
!ne_save  = $F030           ; $F000~$F023 사본. 거절하면 되돌림
!ne_t0    = $F060
!ne_t1    = $F062
!ne_t2    = $F064
!ne_t3    = $F066
!ne_t4    = $F068
!ne_upper = $F06C
!ne_slot = $F06E
!ne_blank = $F070
!ne_vowel = $F06A
!ne_active = $F072
!ne_move = $F07A
; 방향 입력 상태는 게임 안의 메뉴도 쓴다. 7F:F000~ 은 게임 안에서 세계 지도가 덮을 수 있어 DQ5 가 쓰지 않는
; 7E:1BBE~ 79바이트 안에 둔다. josa·서장·1장 이벤트가 1BC0~1BCF 를, DQ5 바위 자리(03:8030)가 1BFF~ 를 쓴다.
; 훅은 DB = 04 라 낮은 WRAM 거울로 읽는다.
!in_direction = $1BE0       ; 고른 방향 하나
!in_raw = $1BE1             ; 지난 프레임의 실제 패드($0749 & 1F)
!in_pending = $1BE2         ; 1 이면 다음 입력 대기에서 기다리지 않고 $24 를 바로 쓴다
!in_edge = $1BE3            ; 이번 표본에 새로 누른 방향이 있음
!in_delay = $1BE4
!in_buttons = $1BE5
!in_pressed = $1BE6
!in_steady = $1BE7          ; 1 이면 반복해도 $0ADA 를 0 으로 둔다(원래 04:D27A 갈래)
!ne_tiles = $F100           ; 이름 칸 2bpp: 글자 줄 8타일(128바이트), 이어서 아래 줄 8타일

org $038B72
    JML NeHook

; 루틴은 뱅크 30 의 빈자리(서곡 문서: 30:9000~ 은 읽는 코드가 없음). BRK 서비스와 게임 루틴이 DB = PB 로 낮은 WRAM 을
; 읽으므로 WRAM 거울이 있는 뱅크(00~3F)여야 한다. 표는 뱅크 61, 글리프는 62~64.
org $04A270
    JML NeListHeight
    NOP
    NOP

org $04B79B
    JML NeListHook

org $04D1DE
    JML NePollHook
org $04D222
    JML NeRepeatHook
org $04D209
    JML NeEdgeHook
org $04D584
    JML NeUpHook
org $04D68C
    JML NeDownHook
org $04D794
    JML NeLeftHook
org $04D82E
    JML NeRightHook

org $30A000
NeHook:
    PHP
    PHB
    SEP #$20
    LDA.l !flag
    CMP #$A5
    BEQ NeKorean
    LDA #$03                ; 원래 03:8B74 PHK / PLB
    PHA
    PLB
    JML $038B76

NeKorean:
    LDA #$7F
    PHA
    PLB
    REP #$30
    STZ !ne_n
    STZ !ne_sp
    LDA #$0000
    STA.l !in_direction
    STA.l !in_pending
    STA.l !in_delay
    SEP #$30
    LDA #$01
    STA !ne_active
    LDA.b #!ne_cursor
    STA.b $CC
    JSR NeDraw
NeLoop:
    SEP #$30
    PHB
    PHK                     ; BRK 서비스는 인자를 DB 뱅크에서 읽는다(부르는 곳은 모두 DB = PB)
    PLB
    BRK #$95                ; 판(창 6C)을 띄워 고르기. $CC = 처음 커서, $E8 = 고른 칸(B 면 FF)
    db $6C
    PLB
    LDA.b $24
    AND #$10
    BNE NeDone              ; Y = 끝
    LDA.b $E8
    CMP #$FF
    BEQ NeBack
    STA.b $CC
    REP #$30
    AND #$00FF
    TAX
    SEP #$20
    LDA.l NeGrid,X
    CMP.b #!ne_back
    BEQ NeBack
    CMP.b #!ne_done
    BEQ NeDone
    CMP.b #!ne_none
    BNE +
    JMP NeLoop              ; 빈 칸(커서가 오지 않음)
+
    REP #$30
    AND #$00FF
    JSR NeSaveState
    JSR NeJamo
    BCS NeRefuse
    JSR NeCount
    CMP.w #!ne_max+1
    BCS NeRefuse
    CMP.w #!ne_max
    BNE +
    LDA !ne_sp              ; 넉 자가 찼고 조합 중이 아니면 커서를 끝으로
    BNE +
    SEP #$20
    LDA.b #!ne_last
    STA.b $CC
+
    JSR NeDraw
    BRA NeLoop

NeRefuse:
    JSR NeLoadState
NeBeep:
    SEP #$30
    PHB
    PHK
    PLB
    BRK #$19                ; 03:8CE8 과 같은 「안 됨」 소리
    db $33,$02
    PLB
    JMP NeLoop

; B 나 지우기: 조합 중인 음절의 자모 하나, 아니면 마지막 글자.
NeBack:
    REP #$30
    LDA !ne_sp
    BEQ +
    DEC !ne_sp
    BRA .draw
+
    LDA !ne_n
    BEQ NeBeep
    DEC !ne_n
.draw
    JSR NeDraw
    JMP NeLoop

NeDone:
    REP #$30
    JSR NeCount
    BEQ NeBeep
    JSR NeSerialize
NeReturn:
    SEP #$30
    STZ !ne_active
    STZ.b $E8
    PLB
    PLP
    RTL

; Out: A = 글자 수(조합 중인 음절 포함).
NeCount:
    REP #$30
    LDA !ne_sp
    BEQ +
    LDA #$0001
+
    CLC
    ADC !ne_n
    RTS

; $72~ 에 이름 바이트(글자마다 NeCode 의 두 바이트), $71 = 바이트 수.
NeSerialize:
    REP #$30
    LDX #$0000
    LDY #$0000
.chars
    CPY !ne_n
    BCS .composing
    PHY
    TYA
    ASL
    TAY
    LDA !ne_ch,Y
    JSR NeEmit
    PLY
    INY
    BRA .chars
.composing
    LDA !ne_sp
    BEQ .end
    PHX
    JSR NeTopCode
    PLX
    JSR NeEmit
.end
    SEP #$20
    TXA
    STA.b $71
    REP #$20
    RTS

; In: A = 글리프, X = $72 에서의 자리. Out: X += 2.
NeEmit:
    ASL
    PHX
    TAX
    LDA.l NeCode,X
    PLX
    SEP #$20
    STA.b $72,X
    XBA
    STA.b $73,X
    REP #$20
    INX
    INX
    RTS

; 이름 칸 넷을 그려 NMI 전송 목록으로 올린다(한 프레임 기다림).
NeDraw:
    REP #$30
    LDA.w #!field_upper
    STA !ne_upper
    LDA.w #!ne_star
    STA !ne_blank
NeDrawCells:
    REP #$30
    LDY #$0000
.cell
    PHY
    CPY !ne_n
    BCC .committed
    BNE .star
    LDA !ne_sp
    BEQ .star
    JSR NeTopCode
    BRA .have
.committed
    TYA
    ASL
    TAX
    LDA !ne_ch,X
    BRA .have
.star
    LDA !ne_blank
.have
    STA !ne_t0              ; 글리프 n 은 뱅크 62 + n / 1024 의 $8000 + (n % 1024) × 32
    AND #$03FF
    ASL
    ASL
    ASL
    ASL
    ASL
    ORA #$8000
    STA.b $00
    LDA !ne_t0
    XBA
    AND #$00FF
    LSR
    LSR
    CLC
    ADC.w #!ne_glyph_bank
    SEP #$20
    STA.b $02
    REP #$20
    PLY
    PHY
    TYA
    ASL
    ASL
    ASL
    ASL
    ASL
    TAX                     ; 칸 c 의 첫 열 = 타일 2c, 버퍼 자리 32c
    LDY #$0000
    SEP #$20
.column
    JSR .rows               ; 글자 줄 여덟 줄
    REP #$20
    TXA
    CLC
    ADC #$0070              ; 같은 열의 아래 줄 타일(+128 - 16)
    TAX
    SEP #$20
    JSR .rows
    REP #$20
    TXA
    SEC
    SBC #$0080              ; 다음 열의 글자 줄
    TAX
    SEP #$20
    CPY #$0020
    BCC .column
    REP #$30
    PLY
    INY
    CPY #$0004
    BCC .cell
    JMP NeUpload
.rows
    LDA #$08
    STA !ne_t3
-
    LDA [$00],Y
    STA !ne_tiles,X
    LDA #$FF                ; 둘째 평면 FF: 점은 색 3, 빈 곳은 색 2(창 바탕)
    STA !ne_tiles+1,X
    INY
    INX
    INX
    DEC !ne_t3
    BNE -
    RTS

NeUpload:
    REP #$30
    SEP #$20
    LDA.l !list_count
    BNE +
    REP #$20
    LDA #$0000
    STA.l !list_offset
+
    REP #$20
    LDA !ne_upper
    LDY.w #!ne_tiles
    JSR .entry
    LDA !ne_upper
    CLC
    ADC #$0800
    LDY.w #!ne_tiles+128
    JSR .entry
    SEP #$20
    LDA #$80
    TSB.b $1A
    PHB
    PHK
    PLB
    JSL $00958A             ; NMI 가 목록을 보낼 때까지 기다림(04:E317 과 같은 순서)
    PLB
    REP #$30
    RTS
; In: A = VRAM 워드, Y = 7F 의 128바이트. 머리 [80][VRAM][워드 수 64] 뒤에 자료.
.entry
    PHY
    PHA
    LDA.l !list_offset
    TAX
    SEP #$20
    LDA #$80
    STA.l $7E4000,X
    REP #$20
    PLA
    STA.l $7E4001,X
    LDA #$0040
    STA.l $7E4003,X
    TXA
    CLC
    ADC #$4005
    TAY
    PLX
    LDA #$007F
    PHB
    db $54,$7E,$7F          ; MVN: 7F:X → 7E:Y, 128바이트
    PLB
    TYA
    SEC
    SBC #$4000
    STA.l !list_offset
    SEP #$20
    LDA.l !list_count
    INC
    STA.l !list_count
    REP #$20
    RTS

; ---------------------------------------------------------------------------
; 조합(슈퍼 마리오 RPG 한글 패치 v1.3 과 같은 규칙)

NeSaveState:
    PHA
    LDX.w #!ne_state_end-!ne_n-2
-
    LDA !ne_n,X
    STA !ne_save,X
    DEX
    DEX
    BPL -
    PLA
    RTS

NeLoadState:
    REP #$30
    LDX.w #!ne_state_end-!ne_n-2
-
    LDA !ne_save,X
    STA !ne_n,X
    DEX
    DEX
    BPL -
    RTS

; Out: carry set if there is no room for another character.
NeCommit:
    LDA !ne_sp
    BEQ .none
    JSR NeTopCode
    STZ !ne_sp
    JMP NeAppend
.none
    CLC
    RTS

; In: A = glyph. Out: carry set if 4 characters are already there.
NeAppend:
    PHA
    LDA !ne_n
    CMP.w #!ne_max
    BCS .full
    ASL
    TAX
    PLA
    STA !ne_ch,X
    INC !ne_n
    CLC
    RTS
.full
    PLA
    SEC
    RTS

NeTop:
    LDA !ne_sp
    DEC
    ASL
    ASL
    TAX
    RTS

NeTopCode:
    JSR NeTop
    ; fall through

; In: X = offset of a state. Out: A = glyph, carry set if 2,350 has no such syllable.
NeStateCode:
    LDA !ne_stk+1,X
    AND #$00FF
    CMP #$00FF
    BNE .medial
    LDA !ne_stk,X           ; an initial alone
    AND #$00FF
    TAX
    LDA.l NeChoJ,X
    AND #$00FF
    CLC
    RTS
.medial
    STA !ne_t1
    LDA !ne_stk,X
    AND #$00FF
    CMP #$00FF
    BNE .syllable
    LDX !ne_t1              ; a medial alone
    LDA.l NeJungJ,X
    AND #$00FF
    CLC
    RTS
.syllable
    STA !ne_t0              ; s = (initial * 21 + medial) * 28 + final
    ASL
    ASL
    STA !ne_t2
    ASL
    ASL
    CLC
    ADC !ne_t2
    ADC !ne_t0
    ADC !ne_t1
    STA !ne_t2
    ASL
    ASL
    ASL
    ASL
    ASL
    SEC
    SBC !ne_t2
    SBC !ne_t2
    SBC !ne_t2
    SBC !ne_t2
    STA !ne_t2
    LDA !ne_stk+2,X
    AND #$00FF
    CLC
    ADC !ne_t2
    STA !ne_t2
    STZ !ne_t0              ; binary search in NeKsSyl
    LDA.w #!ne_ks_count
    STA !ne_t1
.search
    LDA !ne_t0
    CMP !ne_t1
    BCS .missing
    CLC
    ADC !ne_t1
    LSR
    STA !ne_t3
    ASL
    TAX
    LDA.l NeKsSyl,X
    CMP !ne_t2
    BEQ .found
    BCS .lower
    LDA !ne_t3
    INC
    STA !ne_t0
    BRA .search
.lower
    LDA !ne_t3
    STA !ne_t1
    BRA .search
.missing
    SEC
    RTS
.found
    LDA !ne_t3
    CLC
    ADC.w #!ne_jamo
    CLC
    RTS

; Pushes (!ne_t0, !ne_t1, !ne_t2; $FF = none) if 2,350 has it. Out: carry set, nothing pushed, if not.
NePush:
    LDA !ne_sp
    ASL
    ASL
    TAX
    SEP #$20
    LDA !ne_t0
    STA !ne_stk,X
    LDA !ne_t1
    STA !ne_stk+1,X
    LDA !ne_t2
    STA !ne_stk+2,X
    REP #$20
    JSR NeStateCode
    BCS +
    INC !ne_sp
+
    RTS

; In: A = jamo. Starts a new syllable with it (sp must be 0).
NeStart:
    TAX
    LDA.l NeJCho,X
    AND #$00FF
    STA !ne_t0
    LDA.l NeJJung,X
    AND #$00FF
    STA !ne_t1
    STZ !ne_t2
    JMP NePush

; In: A = jamo. Out: carry set if the jamo cannot be typed here.
NeJamo:
    STA !ne_t4
    LDA !ne_sp
    BNE +
    LDA !ne_t4
    JMP NeStart
+
    JSR NeTop
    LDA !ne_stk,X
    AND #$00FF
    STA !ne_t0
    LDA !ne_stk+1,X
    AND #$00FF
    STA !ne_t1
    LDA !ne_stk+2,X
    AND #$00FF
    STA !ne_t2
    LDX !ne_t4
    LDA.l NeJJung,X
    AND #$00FF
    CMP #$00FF
    BEQ .consonant
    JMP .vowel

.consonant
    LDA !ne_t1
    CMP #$00FF
    BEQ .new                ; an initial alone: it stays one
    LDA !ne_t0
    CMP #$00FF
    BEQ .new                ; a medial alone
    LDA !ne_t2
    BNE .double
    LDX !ne_t4
    LDA.l NeJJong,X
    AND #$00FF
    BEQ .new                ; ㄸ ㅃ ㅉ are never finals
    STA !ne_t2
    JSR NePush
    BCS .new
    RTS
.double
    JSR NeFindJongMix
    BCS .new
    STA !ne_t2
    JSR NePush
    BCS .new
    RTS
.new
    JSR NeCommit
    BCS +
    LDA !ne_t4
    JMP NeStart
+
    RTS

.vowel
    STA !ne_vowel
    LDA !ne_t1
    CMP #$00FF
    BNE +
    LDA !ne_vowel           ; an initial alone takes the medial
    STA !ne_t1
    JMP NePush
+
    LDA !ne_t2
    BNE .split
    JSR NeFindJungMix
    BCS .new
    STA !ne_t1
    JMP NePush
.split
    ; The final moves on to the next syllable (only its last consonant if double).
    TAX
    LDA.l NeJongRest,X
    AND #$00FF
    STA !ne_t2
    LDA.l NeJongMove,X
    AND #$00FF
    PHA
    JSR NeStateCode2        ; the syllable without what moves
    BCS .drop1
    PHA
    LDA $03,S
    STA !ne_t0
    LDA !ne_vowel
    STA !ne_t1
    STZ !ne_t2
    JSR NeStateCode2        ; the next syllable
    BCS .drop2
    PLA
    STZ !ne_sp
    JSR NeAppend
    PLA
    BCS .refuse
    STA !ne_t0
    LDA #$00FF
    STA !ne_t1
    STZ !ne_t2
    JSR NePush              ; the moved initial alone, so B can take the medial back
    LDA !ne_vowel
    STA !ne_t1
    STZ !ne_t2
    JMP NePush
.drop2
    PLA
.drop1
    PLA
.refuse
    SEC
    RTS

; (!ne_t0, !ne_t1, !ne_t2) -> glyph without touching the stack.
NeStateCode2:
    LDA !ne_sp
    ASL
    ASL
    TAX
    SEP #$20
    LDA !ne_t0
    STA !ne_stk,X
    LDA !ne_t1
    STA !ne_stk+1,X
    LDA !ne_t2
    STA !ne_stk+2,X
    REP #$20
    JMP NeStateCode

; Medial !ne_t1 + jamo !ne_t4 -> A = compound medial, carry set if none.
NeFindJungMix:
    LDX #$0000
-
    LDA.l NeJungMix,X
    AND #$00FF
    CMP #$00FF
    BEQ .none
    CMP !ne_t1
    BNE +
    LDA.l NeJungMix+1,X
    AND #$00FF
    CMP !ne_t4
    BNE +
    LDA.l NeJungMix+2,X
    AND #$00FF
    CLC
    RTS
+
    INX
    INX
    INX
    BRA -
.none
    SEC
    RTS

; Final !ne_t2 + jamo !ne_t4 -> A = double final, carry set if none.
NeFindJongMix:
    LDX #$0000
-
    LDA.l NeJongMix,X
    AND #$00FF
    CMP #$00FF
    BEQ .none
    CMP !ne_t2
    BNE +
    LDA.l NeJongMix+1,X
    AND #$00FF
    CMP !ne_t4
    BNE +
    LDA.l NeJongMix+2,X
    AND #$00FF
    CLC
    RTS
+
    INX
    INX
    INX
    BRA -
.none
    SEC
    RTS


; 창 61 은 저장 칸 수로 높이를 다시 계산한다. 마지막 한글의 아래 여덟 줄을 위한 한 칸을 남긴다.
NeListHeight:
    REP #$10
    PLX
    PHA
    LDA.l !flag
    CMP #$A5
    BEQ .menu
    PLA
    JML $04A126
.menu
    PLA
    ASL
    CLC
    ADC #$04
    JML $04A12A

; 목록 이름은 입력 칸과 다른 타일을 쓴다. 동시에 보이는 저장 슬롯 셋에 각 여덟 열을 배정한다.
NeListHook:
    LDA.l !flag
    CMP #$A5
    BEQ .korean
.original
    PHX
    LDX #$0000
    JML $04B79F
.korean
    PHP
    PHB
    PHX
    PHY
    REP #$30
    SEP #$20
    LDA #$7F
    PHA
    PLB
    REP #$20
    STZ !ne_n
    STZ !ne_sp
    LDX #$0000
.decode
    LDA.b $01,X
    AND #$00FF
    CMP #$0001
    BEQ .decoded
    SEC
    SBC.w #!ne_hi_base       ; 표시 없는 이름은 일본어라 원래 경로로
    CMP #$0016
    BCC +
    JMP .legacy
+
    STA !ne_t0
    STZ !ne_t1
.multiply
    LDA !ne_t0
    BEQ .low
    DEC !ne_t0
    LDA !ne_t1
    CLC
    ADC #$006F
    STA !ne_t1
    BRA .multiply
.low
    LDA.b $02,X
    AND #$00FF
    SEC
    SBC #$0010
    CMP #$006F
    BCC +
    JMP .legacy
+
    CLC
    ADC !ne_t1
    CMP.w #!ne_star
    BCC +
    JMP .legacy
+
    STA !ne_ch,X
    INC !ne_n
    INX
    INX
    CPX #$0008
    BCC .decode
.decoded
    LDA !ne_slot
    CMP #$0003
    BCC +
    LDA #$0000
+
    STA !ne_slot
    ASL
    ASL
    ASL
    ASL
    ASL
    ASL
    CLC
    ADC #$2680
    STA !ne_upper
    LDA.w #!ne_blank_glyph
    STA !ne_blank
    ; Draw uses $00-$02 as a long pointer; the caller has already consumed the name buffer.
    JSR NeDrawCells
    PLY
    PHY
    TYA
    CLC
    ADC.b $E0
    TAY
    LDA !ne_slot
    ASL
    ASL
    ASL
    CLC
    ADC #$02D0
    TAX
    LDA #$0008
    STA !ne_t0
    SEP #$20
    LDA #$7E
    PHA
    PLB
    REP #$20
.tiles
    TXA
    STA.l $7FF062
    LDA $0001,Y
    AND #$00FC
    XBA
    ORA.l $7FF062
    STA $0000,Y
    CLC
    ADC #$0100
    STA $0040,Y
    INX
    INY
    INY
    LDA.l $7FF060
    DEC
    STA.l $7FF060
    BNE .tiles
    LDA.l $7FF06E
    INC
    STA.l $7FF06E
    PLY
    TYA
    CLC
    ADC #$0010
    TAY
    PLX
    PLB
    PLP
    JML $04BFF2
.legacy
    PLY
    PLX
    PLB
    PLP
    JMP .original


; 자모판 밖의 커서 이동은 원래 루틴으로 간다.
macro NameGuard(original)
    PHP
    REP #$20
    PHA
    SEP #$20
    LDA.l !flag
    CMP #$A5
    BNE ?original
    LDA.l $7FF072
    CMP #$01
    BEQ ?name
?original:
    REP #$20
    PLA
    PLP
    PHP
    LDA $0AD7
    JML <original>+4
?name:
    REP #$20
    PLA
    PLP
    PHP
    PHB
    REP #$30
    PHA
    PHX
    PHY
    SEP #$20
    LDA #$04
    PHA
    PLB
endmacro

NeUpHook:
    %NameGuard($04D584)
    LDA #$00
    JMP NeMoveCursor
NeDownHook:
    %NameGuard($04D68C)
    LDA #$2C
    JMP NeMoveCursor
NeLeftHook:
    %NameGuard($04D794)
    LDA #$58
    JMP NeMoveCursor
NeRightHook:
    %NameGuard($04D82E)
    LDA #$84
NeMoveCursor:
    REP #$30
    AND #$00FF
    STA.l $7FF07A
    LDA $0AD7
    AND #$00FF
    CLC
    ADC.l $7FF07A
    TAX
    SEP #$20
    LDA.l NeNavigation,X
    STA $0AD7
    LDA #$00
    STA !in_pending
    JSL !ne_row
    JML $04CEBF

; 입력 대기·반복 처리는 모든 창에서 이쪽으로 온다. 원래 선택 고리는 위·아래·왼쪽·오른쪽을 차례로 보므로,
; 두 방향을 함께 누르면 한 번에 두 칸을, 하나를 먼저 떼면 남은 방향으로 또 한 칸을 움직였다.
macro InputHook()
    PHP
    PHB
    REP #$30
    PHA
    PHX
    PHY
    SEP #$20
    LDA #$04
    PHA
    PLB
endmacro

; 커서를 그리는 동안 들어온 입력은 다음 선택 고리에서 기다리지 않고 먼저 쓴다.
NePollHook:
    %InputHook()
    LDA !in_pending
    BEQ .wait
    LDA #$00
    STA !in_pending
    BRA .sample             ; 같은 프레임에 다시 떠도 $0749 기준이라 결과가 같고, $24 가 걸러지지 않았어도 거른다
.wait
    JSL !ne_blink
    JSL !ne_wait
.sample
    JSR NeSampleInput
    LDA.b $24
    STA $0ADB
    STZ $0ADA
    JML $04CEBF

; 한 방향만 고른 뒤 반복 대기를 센다. 다른 방향을 떼는 것은 새 누름이 아니다.
; 대기 프레임은 원래 04:D22B~D282 처럼 $0AEA·$0A50 으로 줄인다.
NeRepeatHook:
    %InputHook()
    JSR NeSampleInput
    JSR NeInputReady
    BCS .return
    LDA #$00
    STA !in_steady
    LDA $0ADA
    BEQ .first
    LDA #$07
    BRA .adjust
.first
    LDA #$10
.adjust
    BIT $0AEA
    BMI .shorter
    BVC .delay
    PHA
    LDA $0A50
    CMP #$04
    BCC .steady
    CMP #$07
    PLA
    BCC .shorter
    DEC
    DEC
.shorter
    DEC
    BRA .delay
.steady
    LDA #$01
    STA !in_steady
    PLA
.delay
    STA !in_delay
.wait
    JSL !ne_wait
    JSR NeSampleInput
    JSR NeInputReady
    BCS .return
    LDA !in_delay
    DEC
    STA !in_delay
    BNE .wait
    LDA !in_steady
    BNE .repeat
    LDA #$FF                ; bit7 = 반복 중. 좌우 끝에서 돌아가지 않고 멈추는 창(04:C9C4)이 본다
    STA $0ADA
.repeat
    LDA #$01
    STA $0B4C
    STA !in_pending
.return
    JML $04CEBF

; 끝 칸에 닿은 이동 루틴이 부르는 04:D1FA 의 대기 고리. 방향이 바뀌거나 버튼을 누를 때까지 기다린다.
; 걸러 쓴 $0ADB 를 걸러지지 않은 $24 와 견주면 두 방향을 누른 채로는 곧바로 빠져나간다.
NeEdgeHook:
    LDA #$04
    PHA
    PLB
.wait
    JSL !ne_blink
    JSL !ne_wait
    JSR NeSampleInput
    LDA.b $24
    AND #$E0
    BNE .return
    LDA.b $24
    CMP $0ADB
    BEQ .wait
    LDA !in_edge            ; 새로 누른 방향은 이어지는 반복 처리에서도 새 누름으로 보이게 지난 패드에서 뺀다
    BEQ .return
    LDA !in_direction
    EOR #$FF
    AND !in_raw
    STA !in_raw
.return
    JML $04CEBF

; C=1 이면 새 입력·해제. 새 방향은 곧바로, 유지한 방향은 반복 시각에만 움직인다.
NeInputReady:
    LDA.b $24
    STA $0ADB
    AND #$F0
    BNE .button
    LDA.b $24
    AND #$0F
    BEQ .released
    LDA !in_edge
    BNE .direction
    CLC
    RTS
.direction
    LDA #$01
    STA $0B4C
    STA !in_pending
    STZ $0ADA
    SEC
    RTS
.button
    LDA #$01
    STA !in_pending
.released
    STZ $0B4C
    STZ $0ADA
    SEC
    RTS

; $0749 는 실제 패드 상위 바이트다. Start 는 DQ5 의 $24 로 옮겨지지 않는다. 방향도 $24 가 아니라 여기서 읽어야
; 걸러 쓴 $24 를 다시 읽어도(프레임을 기다리지 않은 표본) 같은 결과가 된다.
NeSampleInput:
    SEP #$20
    LDA #$00
    STA !in_edge
    LDA.b $24
    AND #$F0
    STA !in_buttons
    LDA $0749
    AND #$1F
    PHA
    AND #$10
    BEQ .directions
    JSR NeBoardActive
    BCC .directions
    LDA !in_raw
    AND #$10
    BNE .startHeld
    LDA.b #!ne_last
    STA.b $CC
    LDA $0AD7
    CMP.b #!ne_last
    BEQ .startHeld
    JSL !ne_erase
    STZ $0AD9
    LDA.b #!ne_last
    STA $0AD7
    JSL !ne_row
    JSL !ne_draw
    PHB
    PHK
    PLB
    BRK #$19
    db $33,$00
    PLB
.startHeld
    PLA
    STA !in_raw
    LDA #$00
    STA !in_direction
    STA.b $24
    RTS
.directions
    PLA
    PHA
    AND #$0F
    STA !in_pressed
    LDA !in_raw
    EOR #$FF
    AND !in_pressed
    BEQ .held
    JSR NeChooseDirection
    STA !in_direction
    LDA #$01
    STA !in_edge
    BRA .emit
.held
    LDA !in_direction
    AND !in_pressed
    BNE .emit
    LDA !in_pressed
    JSR NeChooseDirection
    STA !in_direction
.emit
    PLA
    STA !in_raw
    LDA !in_direction
    ORA !in_buttons
    STA.b $24
    RTS

; C=1 이면 첫 메뉴의 한글 자모판
NeBoardActive:
    LDA.l !flag
    CMP #$A5
    BNE .no
    LDA.l $7FF072
    CMP #$01
    BNE .no
    SEC
    RTS
.no
    CLC
    RTS

; 동시에 누른 방향에 순서가 없으면 위·아래·왼쪽·오른쪽 순으로 고른다.
NeChooseDirection:
    BIT #$08
    BEQ +
    LDA #$08
    RTS
+
    BIT #$04
    BEQ +
    LDA #$04
    RTS
+
    BIT #$02
    BEQ +
    LDA #$02
    RTS
+
    AND #$01
    RTS

assert pc() <= $30A900   ; 30:A900~ 은 1장 레코드(dq4chapter1.py RECORDS_AT)

org $618000
NeTables:
incsrc "dq4nameentry-tables.asm"
assert pc() <= $61FFFF

org $628000
incbin "glyphs0.bin"
org $638000
incbin "glyphs1.bin"
org $648000
incbin "glyphs2.bin"
