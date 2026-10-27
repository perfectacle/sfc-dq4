; 게임 안 일행 열 창(상태 창·전투 상태 창)의 한글 이름. dq4windowname.py 가 정의(!wn_*)를 앞에 붙여 asar 로 넣는다.
; 형식은 sfc/dq4/docs/dq4-window-text-format.md 「상태 창 이름」.
;
; 04:ABCF(일행 열 창)와 04:B79B(목록·つよさ 류의 공통 출력)는 이름 4바이트를 그대로 BG3 타일로 찍는다. 한글 표시 바이트(85~9A, 10~7E)면 대신 Galmuri9 글리프(뱅크 62~,
; dq4nameentry 의 16×16 칸)를 10점 간격으로 40점 띠에 겹쳐, 이름 줄 5칸과 그 위 테두리 줄 5칸(글자 맨 윗줄을 테두리 타일
; 7줄째에 합성)을 BG3 글자 칸 180~1CF 에 그려 NMI 전송 목록으로 올린다. 칸은 타일맵 버퍼 자리마다 열 개씩, 여덟 자리를
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

org $04B79B
    JML WnList

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

!wn_stage = $3E00           ; 올릴 160바이트를 먼저 만드는 자리(7E:3D14~3FFF 는 실행한 장면에서 접근 없음)

!list_count  = $0758        ; NMI 전송 목록(00:8CF9) 항목 수
!list_offset = $0759        ; 쓸 자리(16비트), 목록은 7E:4000~

org !wn_code
WnName:
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
    REP #$20
    LDA.b $DC
    STA.l $7E0000|!wn_ptr
    LDA #$0000
    STA.l $7E0000|!wn_mode
    SEP #$20
    JMP WnKorean
.original
    LDX #$0000
    LDA #$04
    STA.b $00
    JML $04ABD6

; 04:B79B. 메뉴(모험의 서) 목록은 이름 입력의 훅이 그리므로 메뉴 플래그가 켜져 있거나 한글이 아니면 그리로 넘긴다.
; 원래 코드는 PHX 로 시작해 글자마다 04:B235 로 ($E0),Y 에 쓰고 PLX 뒤 04:BFF2 로 간다.
WnList:
    LDA.l !wn_menu_flag
    CMP #$A5
    BEQ .previous
    LDA.b $01
    CMP #!wn_hi_base
    BCC .previous
    CMP #!wn_hi_base+!wn_hi_count
    BCS .previous
    LDA.b $02
    CMP #$10
    BCC .previous
    CMP #$10+111
    BCS .previous
    PHX
    REP #$20
    LDA.b $E0
    STA.l $7E0000|!wn_ptr
    LDA #$0001
    STA.l $7E0000|!wn_mode
    ; X 는 창 문자열(뱅크 04)에서 D0 다음 바이트. 「누구」 고르기 창은 이름 뒤 DD(상태 표시 한 칸)가 오고 창을 한 칸
    ; 넓혀 두었으므로 5칸 나아간다. 다른 창(HPとMP 등)은 뒤 내용의 자리가 정해져 있어 원래처럼 4칸.
    LDA #$0008
    STA.l $7E0000|!wn_step
    SEP #$20
    LDA.l $040000,X
    CMP #$DD
    BNE +
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
    LDA.w !wn_above,X
    AND #$03FF
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
    ; 목록에 한 항목으로. 붙이는 동안 NMI 가 목록을 비우면 항목이 엉키므로 NMI 를 잠시 끈다(그림자 $1E).
    SEP #$20
    LDA.b $1E
    AND #$7F
    STA.l $004200
    LDA.w !list_count
    BNE +
    REP #$20
    STZ.w !list_offset
+
    REP #$20
    LDY.w !list_offset
    SEP #$20
    LDA #$80
    STA.w $4000,Y
    REP #$20
    LDA.w !wn_tile
    ASL
    ASL
    ASL
    CLC
    ADC #$1000
    STA.w $4001,Y
    LDA #$0050
    STA.w $4003,Y
    TYA
    CLC
    ADC #$4005
    TAY
    LDX.w #!wn_stage
    LDA #$009F
    db $54,$7E,$7E          ; MVN 7E → 7E, 160바이트
    TYA
    SEC
    SBC #$4000
    STA.w !list_offset
    SEP #$20
    LDA.w !list_count
    INC
    STA.w !list_count
    LDA #$80
    TSB.b $1A
    LDA.b $1E
    STA.l $004200
    ; 04:9D41 이 매 프레임 $19 워드를 AND #$7FFF 로 써 $1A bit7 을 지우므로, 붙인 자리에서 NMI 가 보낼 때까지 기다린다.
    ; 00:958A 는 저 RAM 을 절대 주소로 읽을 수 있어 DB = 00 으로 부른다(뱅크 60 에는 저 RAM 미러가 없음).
    PHB
    LDA #$00
    PHA
    PLB
    JSL $00958A
    PLB
    REP #$30
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
    LDA.w $0000,X
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

WnShift:
    dw 0, 2, 4, 6
WnOffset:
    dw 0, 1, 2, 3
