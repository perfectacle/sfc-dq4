; 게임 안 창(상태 창·전투 상태 창·목록)과 전투 메시지의 한글 이름. dq4windowname.py 가 정의(!wn_*)를 앞에 붙여 asar 로 넣는다.
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
    LDA.l $7E3D62               ; !wq_count(아래 정의). M = 8. 비어 있으면 바로 넘겨 NMI 시간을 거의 늘리지 않는다
    BEQ +
    JSL WqNmi
+
    JMP ($1944)

; 이름 표 문자열(도구 이름 등)을 글자마다 04:B235 로 찍는 자리. PHX / SEP #$10 / LDX #$00
org $04B808
    JML WnText
    NOP
; 주문 목록(D6)이 이름을 다섯 글자 고정으로 찍는 자리. PHX / LDX #$0000 / LDA #$05 / STA $00 / BRL $B7A3
org $04B8F2
    JML WnSpell

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
!wn_bkeys = $1D20           ; 전투 이름 4자리 × 8바이트: 자리마다 이름 바이트
!wn_bnext = $1D40           ; 다음에 내줄 전투 이름 자리
!wn_attr  = $1D42           ; 이름 줄 타일맵 높은 바이트(색). 0 이면 버퍼에 있던 것을 살림
!wt_stack = $1D83           ; 전용 스택 맨 위(1D44~1D83). 협동식 작업마다 낮은 WRAM 에 작은 스택이 있어, 그 스택을 깊게 쓰지 않는다
!wt_keys  = $3D20           ; 12 워드(7E): 슬롯마다 버퍼 자리($E0 + Y)
!wt_ages  = $3D38           ; 12 워드: 마지막으로 쓴 때
!wt_age   = $3D50           ; 쓸 때마다 하나씩
!wt_mode  = $3D52           ; 0 = 04:B808(길이 $00), 1 = 04:B8F2(다섯 글자 고정)
!wt_lastx = $3D54           ; 원래 루틴이 마지막으로 찍는 바이트의 DP 자리
!wt_sp    = $3D60           ; 원래 스택 포인터(7E)
!wt_cols  = $1D84           ; 그릴 열 수
!wt_base  = $1D86           ; 빌린 첫 칸. 글자 줄 열 칸 다음에 위 줄 열 칸
!wt_ptr   = $1D88           ; 그림 자리(뱅크 !wt_bank 안)
!wt_len   = $1D8A           ; 원래 문자열 길이($00)
!wq_count = $3D62           ; 우리 전송 대기열 항목 수(7E, NMI 가 보내고 0 으로)
!wq_off   = $3D64           ; 대기열에 다음으로 쓸 자리
!wq_buf   = $3EA0           ; 대기열 7E:3EA0~3FFF. 항목 [VRAM 워드 2][방식 1][칸 수 1][그림]
!wq_size  = $0160
!wq_left  = $3D66           ; NMI 안에서만: 남은 항목 수
!wq_head  = $3D68           ; NMI 안에서만: 방식·칸 수
!wq_len   = $3D6A           ; NMI 안에서만: 그림 바이트 수

; 칸 풀: 1FF~1D0, 이어서 17F~B0 을 위에서부터 빌린다. 096~0AF 는 전투 글자, 180~1CF 는 상태 창 이름 자리라 넣지 않는다.
; 걷는 메시지 캔버스는 096 부터 위로 채우므로 위에서부터 빌리면 겹치기 어렵다. 전투 연출(B0~122)과 전투 이름(1D0~1F7)은
; 목록 창이 닫힌 뒤에 쓰인다.

; 전투 글은 바이트가 곧 BG3 타일 번호(낮은 8비트)이고 E2 이상은 제어 코드다. 공격 연출이 BG3 칸 B0~122 를 덮으므로
; 이름 그림은 칸 1D0~1F7 에 두고, 글에는 코드 B0~D7(1D0 - 120 ~)을 쓴다. 이름 4자리 × 10칸(아래 줄 5 + 위 줄 5).
; 큐에는 아래 줄 코드만 넣고, 위 줄 코드(아래 + 5)는 WnBattleChar 가, 타일 bit8 은 WnBattleCell 이 붙인다.
!wn_btile = $B0
!wn_bvram = $1D0

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
    JML $24A841

; 24:A4E0. A = 글 바이트, X = 줄 자리 + 칸. 이름 아래 줄 타일이면 위 줄(1DD5)에 짝 타일을 함께 쓴다.
WnBattleChar:
    CMP #!wn_btile
    BCC .write
    CMP #!wn_btile+40
    BCS .write
    PHA
    SEC
    SBC #!wn_btile
-
    CMP #10
    BCC +
    SBC #10
    BRA -
+
    CMP #5
    PLA
    BCS .write
    CLC
    ADC #5
    STA $1DD5,X
    SEC
    SBC #5
.write
    STA $1DEF,X
    INC $0F0D
    JML $24A4EE

; 24:A5E9(JSL, DB = 24). 글 바이트 하나를 타일맵 낱말의 낮은 바이트로. 이름 코드면 타일 bit8 을 켜고, 아니면 끈다
; (줄이 올라가며 같은 자리에 다른 글자가 올 수 있음).
WnBattleCell:
    LDA $1DD5,Y
    CMP #!wn_btile
    BCC .plain
    CMP #!wn_btile+40
    BCS .plain
    CLC
    ADC.b #!wn_bvram-!wn_btile
    STA.l $7E5546,X
    LDA.l $7E5547,X
    ORA #$01
    STA.l $7E5547,X
    RTL
.plain
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

; 전투 이름: 이름 바이트가 같은 자리를 찾거나 돌려 쓰고, 열 칸을 올린 뒤 큐에 아래 줄 타일을 넣는다.
WnBattleDraw:
    LDX #$0000
.find
    LDY #$0000
-
    LDA.w !wn_bkeys,X
    CMP.b $01,Y
    BNE .next
    INX
    INX
    INY
    INY
    CPY #$0008
    BCC -
    TXA
    SEC
    SBC #$0008
    BRA .found
.next
    TXA
    AND #$FFF8
    CLC
    ADC #$0008
    TAX
    CPX #$0020
    BCC .find
    LDA.w !wn_bnext
    AND #$0003
    ASL
    ASL
    ASL
    PHA
    LDA.w !wn_bnext
    INC
    STA.w !wn_bnext
    PLX
    PHX
    LDY #$0000
-
    LDA.b $01,Y
    STA.w !wn_bkeys,X
    INX
    INX
    INY
    INY
    CPY #$0008
    BCC -
    PLA
.found
    LSR
    LSR
    LSR                     ; 자리 0~3
    STA.w !wn_c
    ASL
    ASL
    CLC
    ADC.w !wn_c
    ASL                     ; × 10
    CLC
    ADC.w #!wn_bvram
    STA.w !wn_tile
    JSR WnUpload
    ; 글자 수 k 면 타일 (10k + 7) / 8 칸
    LDX #$0000
-
    LDA.w !wn_glyph,X
    CMP #$FFFF
    BEQ +
    INX
    INX
    CPX #$0008
    BCC -
+
    TXA
    LSR
    STA.w !wn_c
    ASL
    ASL
    CLC
    ADC.w !wn_c
    ASL
    CLC
    ADC #$0007
    LSR
    LSR
    LSR
    STA.w !wn_r
    LDX #$0000
    LDA.w !wn_tile
    SEC
    SBC.w #!wn_bvram-!wn_btile
    SEP #$20
-
    STA.w $0ECB,X
    INC
    INX
    CPX.w !wn_r
    BCC -
    LDA #$FF
    STA.w $0ECB,X
    REP #$20
    PLB
    PLP
    PLP
    JML $24A854

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
WnSpell:
    PHX
    LDA #$01
    BRA +
WnText:
    PHX
    LDA #$00
+
    STA.l $7E0000|!wt_mode
    REP #$30
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
    ; 원래 루틴이 나아가는 칸 수: 탁점 바이트(84·83)는 위 줄에 탁점만 찍고 칸을 나아가지 않는다.
    ; 04:B808 은 $00 바이트를, 04:B8F2 는 탁점이 아닌 글자 다섯을 찍는다
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
    LDA.w !wt_len
    CMP #$0005
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
    LDA #$05
    STA.b $00
    JML $04B7A3

; 칸 슬롯: 20칸(최대 10열 × 글자 줄·위 줄)씩 12개. 같은 버퍼 자리($E0 + Y)에 다시 그리면 같은 슬롯을, 처음 보는 자리면
; 가장 오래 쓰지 않은 슬롯을 쓴다. 타일맵 버퍼를 훑어 빈 칸을 찾던 방식은, 다른 창을 여는 동안 게임이 버퍼를 비워
; 화면에 보이는 칸을 다시 빌렸다.
WtAlloc:
    LDA.b $E0
    CLC
    ADC.w !wn_y
    STA.w !wn_key
    INC.w !wt_age
    LDX #$0000
-
    LDA.w !wt_keys,X
    CMP.w !wn_key
    BEQ .found
    INX
    INX
    CPX #$0018
    BCC -
    ; 가장 오래된 슬롯
    LDX #$0000
    LDY #$0000
    LDA #$FFFF
    STA.w !wn_c
-
    LDA.w !wt_age
    SEC
    SBC.w !wt_ages,X        ; 지난 횟수(돌아가도 뺄셈이면 맞음)
    CMP.w !wn_c
    BCC +
    BEQ +
    STA.w !wn_c
    TXY
+
    ; 빈 슬롯(나이 0)은 가장 오래된 것으로
    LDA.w !wt_ages,X
    BNE +
    TXY
    BRA .pick
+
    INX
    INX
    CPX #$0018
    BCC -
.pick
    TYX
    LDA.w !wn_key
    STA.w !wt_keys,X
.found
    LDA.w !wt_age
    STA.w !wt_ages,X
    LDA.l WtSlot,X
    STA.w !wt_base
    CLC
    RTS

; 슬롯 첫 칸: 1D0·1E4 와 B0 부터 20칸씩 열(180~1CF 는 상태 창 이름, 096~0AF 는 전투 글자)
WtSlot:
    dw $01D0, $01E4, $00B0, $00C4, $00D8, $00EC, $0100, $0114, $0128, $013C, $0150, $0164

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
    SEP #$20
    LDA.b $1E
    STA.l $004200
    REP #$20
    LDX #$0000
-
    LDA.w !wq_count
    AND #$00FF
    BEQ +
    DEX
    BNE -
+
    SEP #$20
    LDA.b $1E
    AND #$7F
    STA.l $004200
    REP #$20
    STZ.w !wq_off
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
    LDA.w !wn_k
    ASL
    ASL
    ASL
    ASL
    CLC
    ADC.w !wt_ptr
    CLC
    ADC #$0009              ; 열 수 바이트 + 위 줄 8줄
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
    ADC.b $E0
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
    LDA.w !wn_k
    ASL
    ASL
    ASL
    ASL
    CLC
    ADC.w !wt_ptr
    CLC
    ADC #$0008              ; 열 수 바이트 + 위 줄 7줄
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
    SEP #$20
    LDA.w !wq_count
    CLC
    ADC #$02
    STA.w !wq_count
    LDA.b $1E
    STA.l $004200
    REP #$30
    RTS

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
    LDY #$0000
.entry
    REP #$20
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
    PLB
    PLP
    RTL

WqFF:
    db $FF

; 타일맵: 글자 줄은 빌린 칸, 위 줄은 빌린 칸 + 열 수. 높은 바이트는 우선·팔레트만 살리고, 색($ED)이 있으면 글자 줄에 쓴다.
WtTilemap:
    STZ.w !wn_k
-
    LDA.w !wn_k
    ASL
    CLC
    ADC.w !wn_y
    CLC
    ADC.b $E0
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
    ADC.b $E0
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
