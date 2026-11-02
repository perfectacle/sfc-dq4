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
; NMI 가 $1944 작업의 게임 전송(00:8C1E 등) 앞에서 우리 대기열을 보낸다. 게임 전송 목록은 게임이 프레임 끝에 한 번
; 보내는 장치($1946 = 00:8CEF, $19 bit2)라, 창을 그리는 도중에 끼어들면 메뉴 흐름이 어긋났다.
; 공통 입구 00:887C(JMP ($1944))는 원래대로 두고 작업마다 건다. 전투 작업이 $0DF3 의 큰 그림 목록(00:FD4A, 전투 배경
; 0B00바이트씩)을 보내는 NMI 는 원래 롬에서도 VBlank 끝 몇십 마스터 클럭 앞에 끝나, 그 앞에 몇 명령만 더해도 DMA 꼬리가
; 화면 그리기로 넘어가 버려진다. 그 길(00:895D)에는 걸지 않는다. 그 NMI 는 게임 창 타일맵($0BEC)도 보내지 않는다.
; 03:A211 이 고르는 작업 00:FF9A(JSL $11C8AC / JML $00888F)는 통째로 우리 쪽에서 돈다. 비는 00:FF9E~ 에 필드 받침을 둔다
org $00FF9A
    JML WqNmiFF9A
; 필드 작업: 00:87E6 이 $1944 에 넣는 00:8926 을 받침으로 바꾼다
org $0087F2
    LDX.w #$FF9E
org $00FF9E
    JSL WqNmiEntry
    JMP $8926
; 전투 작업의 보통 길(00:896F JSR 8C1E / JSR 8EE1 / JSR FDE5 / JSR 89DE / JMP 887F). 뒤 셋은 큰 그림 길 00:8960 과 같고
; 그 길의 STZ $0DF3 은 여기서는 이미 0 이라 같은 일이다
org $00896F
    JSL WqNmiEntry
    JSR $8C1E
    db $80 : db $8960-$8978     ; BRA $8960 (이 asar 는 BRA $주소 를 거리로 바꾸지 않음)
; 카지노 슬롯 작업 00:FEDD 의 첫 부름 00:FF08(LDX #$1400 / STX $2116, 00:FEDD 만 부름)
org $00FF08
    JSL WqNmiSlot
    NOP #2
; 게임이 $0BEC 에 쓰는 곳은 셋뿐이다(롬 정적 훑기): 2KB 요청 04:9D39 LDA #$0080 / 9D3C STA(루틴 04:9D35), 위·아래 줄 요청
; 04:9D64 LDA #$40 / 9D66 STA(루틴 04:9D5E), 보낸 뒤 지우는 00:8E90 STZ. 2KB 요청 뒤 게임은 바로 NMI 를 기다리므로 버퍼가
; 다음 NMI 까지 그대로다. WhReq 가 그 버퍼로 묶음 그림·가림을 미리 짠다(원래 바이트는 dq4windowname.WH_REQ_ORIG 로 확인)
org !wh_req_site
    JSL WhReq
    NOP
    NOP
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
; 격투장 거는 창(76)의 D4(04:B859)가 몬스터 이름 뒤에 빈칸·구별 글자를 붙여 열 글자 고정으로 찍는 자리.
; REP #$10 / PLY 다음의 LDX #$0000 / LDA #$0A / STA $00 / BRL $B7A3. 코드 갈래가 이미 PHX 를 했다
org $04B880
    JML WnArena
; 전투 작전 창(E5)이 작전 이름을 넉 자씩 두 줄로 찍는 자리. PHX / SEP #$10 / LDX #$00
org $04BB70
    JML WnTactic

; 모험의 서 기록 목록(창 5D)의 코드 DC(04:B9A7)가 빈 칸이면 04:B9FB 의 10바이트를 거꾸로 JSR $B235 로 찍는 고리
org $04B9EB
    JML WnEmptySlot

; 가게 동료 창(3A)의 「소지 중」 을 고르는 두 자리(장비류·도구). LDY #$000A / BRL $C440
org $04C3B1
    JML ShopHeldCount
    NOP #2
org $04C508
    JML ShopHeldCount
    NOP #2

; 가게 사기의 도구·장비 갈래가 값을 $0F28~ 에 두는 STA $0F28 / LDA $47 / STA $0F29 / LDA $48 / STA $0F2A.
; 다음 JSR $F5E9 가 돈을 뺀다
org $06DCDF
    JSR ShopBuyTool
    NOP #10
org $06DDFC
    JSR ShopBuyEquip
    NOP #10
; 도구 갈래가 물건을 주는 자리 앞(LDA $0F23 / STA $42 / LDA $0F22 / STA $43, 뒤는 BRK 89 80 30)
org $06DD39
    JSR ShopGiveExtra
    NOP #7

; 도구 갈래(M = 8, X = 8, 값 $46~$48). 최대 개수(ShopQtyMax)가 2 이상이면 「몇 개 사시겠어요?」 와 다섯 자리 수 창(끝 자리만 씀)을 묻고,
; 개수 × 값으로 ShopBuyConfirm 의 확인으로 간다. 개수는 물건을 줄 때까지 $0F21 에 둔다. $0F21 은 팔기·필드 도구
; 메뉴 등이 사람 번호로도 쓰므로, 06:DD39 로 오는 두 사기 갈래(ShopBuyTool·ShopBuyEquip)가 모두 먼저 둔다.
; 수 창(5C, 맡기는 곳 등과 같은 창)은 고르면 $E8 = 0 이고 자리마다 숫자(0~9)를 $0AFE~$0B02 에 둔다(06:EF06 이 값으로
; 바꾸는 자리). 끝 자리를 개수로 쓰고, 앞 자리가 0 이 아니거나 최대보다 크면 최대로, 0 이거나 B 면 확인의 「아니요」 길로
org !shop_qty_spot
ShopBuyTool:
    LDA.b $46
    STA.w $0F28
    LDA.b $47
    STA.w $0F29
    LDA.b $48
    STA.w $0F2A
    LDA #$01
    STA.w $0F21
    JSL ShopQtyMax
    CMP #$02
    BCC .one
    PHA
    ORA #$40                ; 수 창 동안 $0F2C = 최대 | 40(열림). WnQtyUp·WnQtyDown 이 끝 자리를 1~최대로 돌리고 QpFrame 이 금액을 쓴다
    STA.w $0F2C
    JSL ShopQtyAsk
    db $00, $95, $5C        ; BRK 95 5C: 다섯 자리 수 창. 커서는 맨 끝 자리에서 시작한다
    STZ.w $0F2C
    PLA
    LDX.b $E8
    BNE .cancel
    LDX #$03
-
    LDY.w $0AFE,X
    BNE +
    DEX
    BPL -
    LDX.w $0B02
    BEQ .cancel
    CMP.w $0B02
    BCC +
    LDA.w $0B02
+
    STA.w $0F21
    JSL ShopQtyTotal
    JMP ShopBuyConfirm
.one
    LDA #$01
    JSL ShopQtyTotal
    JMP ShopBuyConfirm
.cancel
    JMP ShopBuyConfirm_no

; 고른 개수에서 하나 모자라게 더 준다(BRK 89 80 30). 마지막 하나는 원래 코드가 준다
ShopGiveExtra:
-
    LDA.w $0F23
    STA.b $42
    LDA.w $0F22
    STA.b $43
    LDA.w $0F21
    CMP #$02
    BCC +
    DEC
    STA.w $0F21
    db $00, $89, $80, $30
    BRA -
+
    RTS

; 팔기의 「아니요」(06:DF48, 개수 0·B 도 여기로). 원래는 「아쉽네요」 뒤 「그 밖에 또 볼일이」 와 사기/팔기 창(06:DF50)으로
; 갔다. 사기처럼 「아쉽네요」 ▼ 뒤(06:DEC6 의 BRK 97 13) 같은 사람의 팔기 목록으로
; 돌아가고, 「어느 물건을 팔아 주시겠어요?」(묶음 13)는 다시 띄우지 않는다.
; 06:DF48 은 팔기 목록(06:DEC1)과 같은 스택 깊이다
ShopSellNo:
    ; 여러 개 팔기의 개수(ShopSellQty 가 둔 $0F2C)는 058 의 「아니요」 로 와도 0 으로 되돌린다
    STZ.w $0F2C
    db $00, $95, $00
    LDA #$18
    JSR $DFC4
    JMP $DEC6
assert pc() <= !shop_qty_end

; 가게 BRK 를 부르는 도우미. BRK 처리기는 DB 를 부른 코드의 뱅크로 두므로, 뱅크 40 이상(창 코드의 60)에서 부르면
; WRAM 대신 열린 버스를 읽는다(dq4brkscan). 원래 롬에서도 비어 있는 뱅크 05 끝에 둔다
org !shop_low_spot
; 04:C3B1·04:C508(M = 8, X = 16, DB = 04, 줄 $E4, 고른 물건 $0F22). 원래는 04:C511 표의 「 소지 중」 을 문자열 버퍼
; $01~(빈칸 01 로 채운 16바이트)에 베끼고 04:C45A(PLY / RTS)로 끝난다. 그 사람 소지품 12칸에서 같은 물건을 세어
; 고정 문구 「 N개 소지」 를 9E k 로 넣는다. BRK 88 은 A·X·Y 를 지키고 부른 뱅크에서 피연산자를 읽는다
ShopHeldCount:
    LDA.b $E4
    STA.b $42
    db $00, $88, $46        ; BRK 88 46: 줄 → 사람
    LDA.b $46
    PHA
    LDY.w #$0000
    LDX.w #$0000
-
    TXA
    STA.b $43
    LDA $01,S
    STA.b $42
    db $00, $88, $2E        ; BRK 88 2E: $46 = 사람 $42 의 칸 $43 의 물건
    LDA.b $46
    CMP.w $0F22
    BNE +
    INY
+
    INX
    CPX.w #$000C
    BCC -
    PLA
    CPY.w #$0001
    BCS +
    LDY.w #$000A
    JML $04C440
+
    LDX.w #$000F
    LDA #$01
-
    STA.b $00,X
    DEX
    BPL -
    LDA #!wt_fixed
    STA.b $01
    TYA
    CLC
    ADC #!wt_held_first-1
    STA.b $02
    JML $04C45A

; 가게 도구 사기의 최대 개수(M = 8, X = 8, 값 $0F28~, 사람 $0F23). 그 사람 빈칸(12 − 가진 수, BRK 89 80 2F)과 9 가운데
; 작은 수까지, 가진 돈(BRK 88 49)에서 값을 몇 번 뺄 수 있는지 센다. A = 최대(0~9)
ShopQtyMax:
    LDA.w $0F23
    STA.b $42
    db $00, $89, $80, $2F   ; BRK 89 80 2F: $46 = 가진 물건 수
    LDA #$0C
    SEC
    SBC.b $46
    CMP #$0A
    BCC +
    LDA #$09
+
    PHA
    db $00, $88, $49        ; BRK 88 49: $46~$48 = 가진 돈
    LDX #$00
-
    TXA
    CMP $01,S
    BCS +
    LDA.b $46
    SEC
    SBC.w $0F28
    STA.b $46
    LDA.b $47
    SBC.w $0F29
    STA.b $47
    LDA.b $48
    SBC.w $0F2A
    STA.b $48
    BCC +
    INX
    BRA -
+
    PLA
    TXA
    RTL

; 개수 A(1~9) × 값(BRK 94 02, 물건 $0F22)을 $46~$48 에(M = 8, X = 8)
ShopQtyTotal:
    TAX
    LDA.w $0F22
    STA.b $42
    db $00, $94, $02
    LDA.b $46
    STA.w $0F28
    LDA.b $47
    STA.w $0F29
    LDA.b $48
    STA.w $0F2A
-
    DEX
    BEQ +
    LDA.b $46
    CLC
    ADC.w $0F28
    STA.b $46
    LDA.b $47
    ADC.w $0F29
    STA.b $47
    LDA.b $48
    ADC.w $0F2A
    STA.b $48
    BRA -
+
    RTL

; 사기 개수 묻기: 창을 닫고 「몇 개 사시겠어요? / 쓰는 돈 / 남는 돈」(가게 종류마다)을 띄운다. 숫자는 수 창이 떠 있는 동안
; QpFrame 이 매 프레임 그 줄 뒤에 쓴다. 뱅크 06 자리가 모자라 여기(뱅크 05, BRK 가능)에 둔다
; 팔기 개수 묻기: 창을 닫고 「몇 개 파시겠어요? / 받는 돈 / 판 뒤」(가게 종류마다) 뒤 수 창 5C 를 연다. 뱅크 12 는 자리가 없어 여기
ShopSellAsk:
    db $00, $95, $00
    LDA.w $0F20
    AND #$03
    ASL
    TAX
    REP #$20
    LDA.l ShopSellMsg,X
    JSL $248157
    SEP #$20
    db $00, $95, $5C
    RTL

ShopQtyAsk:
    db $00, $95, $00
    LDA.w $0F20
    AND #$03
    ASL
    TAX
    REP #$20
    LDA.l ShopQtyMsg,X
    JSL $248157
    SEP #$20
    RTL

; 「몇 개 사시겠어요?」 메시지 번호(가게 종류 $0F20 마다). 원작에서 비어 있고 부르는 곳이 없는 메시지
ShopQtyMsg:
    dw $009C, $009D, $00AB, $00C3
assert pc() <= !shop_low_end

; 가게 팔기: 값을 셈(06:DF06, LDA $0F22 / STA $42 / JSL $06DF5B)과 물건 빼기 앞(06:DF35, LDA $0F21 / STA $42 / LDA $0F23 /
; STA $43, 뒤는 BRK 89 80 32). 팔기에서 $0F21 은 사람, $0F23 은 고른 칸이라 개수는 $0F2C 에 둔다. $0F2C 는 06:E36B 가
; 16비트 $0F2B 의 높은 바이트로 읽는데 그 처리기들이 들어올 때 지우므로, 다 쓰면 0 으로 되돌린다
; 팔기에서 물건을 고른 뒤 050 「{I} 말이죠. 잠깐만 기다려 주세요!」(LDA #$14 / JSR $DFC4 / BRK 97 13)를 건넌다.
; 팔기 목록에 값이 이미 보여 값을 매기며 기다리게 하는 말이 필요 없다. 058 이 바로 값을 묻는다
org $06DEFE
    BRA $06DF06
    NOP #6
org $06DF06
    JSL ShopSellQty
    NOP #5
org $06DF35
    JSL ShopSellExtra
    NOP #6
org $06DF48
    JMP ShopSellNo
    NOP #5

; 원래 롬도 빈 뱅크 12 끝. BRK 를 부르므로 뱅크 40 아래에 둔다
org !shop_sell_spot
; 06:DF06(M = 8, X = 8). 한 개 값(06:DF5B, 산 값의 3/4)을 낸 뒤, 같은 사람에게 장비하지 않은 같은 물건이 더 있으면(고른 칸 포함
; 최대 9) 「몇 개 파시겠어요?」 와 수 창 5C 를 묻고, 개수 × 값을 $0F28~ 과 메시지의 {N}($F5~)에 둔다. 0·B 면 돌아갈 자리를
; 버리고 팔기의 「아니요」(06:DF48)로 간다
ShopSellQty:
    LDA.w $0F22
    STA.b $42
    JSL $06DF5B
    LDA #$01
    STA.w $0F2C
    JSR ShopSellCount
    CMP #$02
    BCS +
    JMP .done
+
    PHA
    ORA #$C0                ; 수 창 동안 $0F2C = 최대 | 40(열림) | 80(팔기). 뒤에서 개수를 쓰거나 0 으로 둔다
    STA.w $0F2C
    JSL ShopSellAsk
    PLA
    LDX.b $E8
    BNE .cancel
    LDX #$03
-
    LDY.w $0AFE,X
    BNE +
    DEX
    BPL -
    LDX.w $0B02
    BEQ .cancel
    CMP.w $0B02
    BCC +
    LDA.w $0B02
+
    STA.w $0F2C
    TAX
    LDA.w $0F28
    STA.b $46
    LDA.w $0F29
    STA.b $47
    LDA.w $0F2A
    STA.b $48
-
    DEX
    BEQ +
    LDA.w $0F28
    CLC
    ADC.b $46
    STA.w $0F28
    LDA.w $0F29
    ADC.b $47
    STA.w $0F29
    LDA.w $0F2A
    ADC.b $48
    STA.w $0F2A
    BRA -
+
    LDA.w $0F28
    STA.b $F5
    LDA.w $0F29
    STA.b $F6
    LDA.w $0F2A
    STA.b $F7
.done
    JSR ShopSellWarn
    RTL
.cancel
    STZ.w $0F2C
    PLA
    PLA
    PLA
    JML $06DF48

; 사람 $0F21 의 소지품에서 고른 칸($0F23) 말고 장비하지 않은 같은 물건($0F22) 수 + 1, 9 까지(A). BRK 88 2E: $42 사람, $43 칸
; → $46 물건, $47 장비 중
ShopSellCount:
    LDY #$01
    ; 고른 칸이 장비 중이면 묻지 않는다(한꺼번에 팔다 입은 장비까지 벗겨 팔지 않게)
    LDX.w $0F23
    JSR ShopSellSlot
    LDA.b $47
    BNE ++
    LDX #$00
-
    CPX.w $0F23
    BEQ +
    JSR ShopSellSlot
    BNE +
    INY
+
    INX
    CPX #$0C
    BCC -
++
    TYA
    CMP #$0A
    BCC +
    LDA #$09
+
    RTS

; 칸 X 가 장비하지 않은 고른 물건이면 Z = 1
ShopSellSlot:
    TXA
    STA.b $43
    LDA.w $0F21
    STA.b $42
    db $00, $88, $2E
    LDA.b $46
    CMP.w $0F22
    BNE +
    LDA.b $47
+
    RTS

; 고른 칸이 장비 중이면 058 「{N}골드에 사들일게요」 앞에 「지금 장착하고 있는 물건이다.」(원작에서 빈 메시지 3D, ▼ 를 기다린
; 뒤 058 이 이어 찍힘). 이름이 가나로 남은 물건 뒤 조사({은})는 찍다 멈추므로 이름을 넣지 않는다. 가게 말투 넷을 쓸 빈 메시지가 남지 않아 서술 한 줄로 두고, 058 이 가게 말투로 다시 묻는다
ShopSellWarn:
    db $00, $95, $00        ; 개수를 물었으면 미리보기 창이 058 뒤에 남지 않게(골드 창은 남음). 장착 알림 앞에도 닫아야 한다
    LDX.w $0F23
    JSR ShopSellSlot
    LDA.b $47
    BEQ +
    REP #$20
    LDA #$003D
    JSL $248157
    SEP #$20
    ; 메시지를 찍으면 $F5~ 가 바뀌어 058 의 {N} 이 0 이 된다. 치를 값($0F28~)으로 되돌린다
    LDA.w $0F28
    STA.b $F5
    LDA.w $0F29
    STA.b $F6
    LDA.w $0F2A
    STA.b $F7
+
    RTS

; 06:DF35. 개수 − 1 개를 뒤 칸부터 찾아 BRK 89 80 32 로 빼고(빼면 뒤 칸이 앞으로 당겨지므로, 고른 칸보다 앞을 빼면 고른 칸
; 번호를 하나 줄인다), 마지막 하나는 원래 코드가 고른 칸에서 뺀다
ShopSellExtra:
-
    LDA.w $0F2C
    CMP #$02
    BCC ++
    LDX #$0B
--
    CPX.w $0F23
    BEQ +
    JSR ShopSellSlot
    BNE +
    TXA
    STA.b $43
    LDA.w $0F21
    STA.b $42
    db $00, $89, $80, $32
    DEC.w $0F2C
    CPX.w $0F23
    BCS -
    DEC.w $0F23
    BRA -
+
    DEX
    BPL --
++
    LDA.w $0F21
    STA.b $42
    LDA.w $0F23
    STA.b $43
    STZ.w $0F2C
    RTL

assert pc() <= !shop_sell_end

; 값을 $0F28~ 에 둔 뒤, 돈이 되면(06:F602, C = 모자람) 창을 닫고 「{N}골드인데 사시겠어요?」(메시지 묶음 19 = 064~067)와
; 예/아니요를 묻는다. 예거나 돈이 모자라면 돌아가 06:F5E9 가 원래대로 돈을 빼거나 「돈이 모자란」 메시지를 낸다.
; 아니요·B 면 돌아갈 자리(JSR 2바이트)만 버리고 「그래요? 아쉽네요」(묶음 18) ▼ 뒤 물건 목록 창(06:DC37)으로 간다. 06:DC2F 의 「사시려고요? 어느 것으로」(묶음 01)는 처음 들어올 때만 띄운다. 06:DC37 은 두 자리와 같은 스택 깊이여야 한다. 뱅크 60 에서 부르면 BRK 95 가 돌아오지 않아 뱅크 06 끝에 둔다
org !shop_buy_spot
ShopBuyConfirm:
    LDA.b $46
    STA.w $0F28
    LDA.b $47
    STA.w $0F29
    LDA.b $48
    STA.w $0F2A
    JSR $F602
    BCS .done
    LDA.w $0F28
    STA.b $F5
    LDA.w $0F29
    STA.b $F6
    LDA.w $0F2A
    STA.b $F7
    db $00, $95, $00        ; BRK 95 00: 「누가」·소지품 창을 닫는다. 열린 채면 메시지가 찍히지 않는다
    LDA #!shop_buy_ask
    JSR $DFC4
    db $00, $95, $32        ; BRK 95 32: 예/아니요
    LDA.b $E8
    BNE .no
.done
    RTS
.no
    PLA
    PLA
    db $00, $95, $00
    LDA #$18
    JSR $DFC4
    db $00, $97, $13        ; BRK 97 13: ▼ 를 기다린다
    JMP $DC37
; 장비 갈래. 「바로 장비하시겠어요?」 에 아니요거나 장비할 수 없으면 06:DE77 → 06:DCFF 로 도구 갈래와 합쳐
; 06:DD39(ShopGiveExtra)를 지나므로, 개수를 1 로 두고 확인으로 간다. $0F21 은 팔기·필드 도구 메뉴 등이 사람 번호로 쓴다
ShopBuyEquip:
    LDA #$01
    STA.w $0F21
    JMP ShopBuyConfirm
assert pc() <= $070000

; 창 바이트 갈래(메뉴 패치의 JSL). 고정 문구 접두를 먼저 가르고, 나머지는 원래 대상으로.
org $04B11E
    JSL WnPrefix

; 창 표를 읽어 별칭(레코드 첫 바이트 bit7, 셋째 바이트 = 대상 창)을 푸는 세 자리: 창 열기·그리기·크기 셈.
; 셋 모두 $DA 에 별칭 레코드 주소가 있고, 돌아온 A(16비트)를 대상 레코드로 쓴다
org $049C5C
    JSR ShopListRes
org $049FBB
    JSR ShopListRes
org $04A8C2
    JSR ShopListRes
org !shop_sell_slot
    dw ShopSellPrice

; 가게 팔기 목록. 창 37 은 창 0F(물건 목록, 필드 도구 창 등과 함께 씀)의 별칭인데 맡기는 곳(06:E5E5)도 연다.
; 가게($0F20: 0 도구·1 방어구·2 무기·3 06:E02E 가게(같은 사기·팔기 흐름), 맡기는 곳은 6)에서 37 을 풀 때만 값 열을 붙인 레코드를 돌려주고, 사기 목록과
; 같은 자리(x 2, 너비 20)에 둔다. 오른쪽에 골드 창과 「누가」 창이 있어 오른쪽으로는 넓히지 못한다
org !shop_spot
; 가게 개수 창: 창 5C(16 05 08 23 00 01 | 01 FD×5 FF | 52) 에서 높이(+3 아래 5비트)를 3 → 5 로, 자리 표시 FD 다섯을 뺐다.
; FD 는 창을 열 때 「0」 으로 찍혀 QpWindow 가 지우기 전 한 프레임 비쳤고, 자리 칸 좌표는 QpWindow 가 매 프레임 쓴다.
; 줄 끝 FF 뒤 바이트 & 1F 가 입력 갈래($0AD8, 04:C681, 12 = 수 창)라 빼면 커서 메뉴가 된다
ShopQtyRec:
    db $16, $05, $08, $25, $00, $01, $01, $FF, $52
ShopSellRec:
    db $4F, $03, $80|!shop_sell_w, $B9, $00, $81, $FE, $D3, $01, !shop_sell_code, $FF, $83
ShopListRes:
    LDA.b $DA
    CMP.w #!shop_sell_alias
    BNE .plain
    LDA.w $0F20
    AND #$00FF
    CMP #$0004
    BCS .plain
    SEP #$20
    LDA #$02
    STA.w $0A43
    REP #$20
    LDA.w #ShopSellRec
    RTS
.plain
    LDA.w $EB48,X
    RTS

; 자리 표시 코드(M = 8, X = 16, DB = 04, 스택에 갈래가 넣은 레코드 자리 X). 같은 줄 D3 이 찍은 물건의 파는 값
; (산 값의 3/4, 06:DF75 와 같은 셈)을 다섯 자리 + 「G」 로, 팔 수 없는 물건(BRK 94 06 의 C)이면 「판매불가」 를 같은 여섯 칸에
; D3 은 이름 뒤 Y 를 원래 가나 길이만큼만 나아가므로, 값은 줄 첫 칸($E0) 기준 안쪽 12열(커서·장비 표시·이름 9열·빈칸 뒤)에 둔다
ShopSellPrice:
    LDY.w #$0018
    LDA.b $E4
    STA.b $42
    db $00, $88, $46        ; BRK 88 46: 「누가」 창 줄 → 사람
    LDA.b $46
    STA.b $42
    LDA.w $0B9E
    STA.b $43
    db $00, $88, $2E        ; BRK 88 2E: $46 = 사람 $42 의 칸 $43($0B9E, 지금 줄) 의 물건
    LDA.b $46
    CMP #$FF
    BCS .done
    STA.b $42
    PHA
    db $00, $94, $06
    PLA
    BCS .cannot
    db $00, $94, $02        ; $46~$48 = 값
    ; 값을 $03~$05 에 맡기고 3/4 를 $46~$48 에 낸다. $03~ 은 다음 04:C0AB 가 자릿수로 덮는 자리이고, 가게가 실제로
    ; 치를 값인 $0F28~ 은 예/아니요 사이에 목록을 다시 그려도 건드리지 않는다
    LDA.b $46
    STA.b $03
    LDA.b $47
    STA.b $04
    LDA.b $48
    STA.b $05
    ASL.b $46
    ROL.b $47
    ROL.b $48
    LDA.b $46
    CLC
    ADC.b $03
    STA.b $46
    LDA.b $47
    ADC.b $04
    STA.b $47
    LDA.b $48
    ADC.b $05
    LSR
    STA.b $48
    ROR.b $47
    ROR.b $46
    LSR.b $48
    ROR.b $47
    ROR.b $46
    JSR $C0AB
    LDX.w #$0003
-
    LDA.b $00,X
    JSR $B235
    INX
    CPX.w #$0008
    BCC -
    LDA #$0F
    JSR $B235
.done
    PLX
    JMP $BFF2
.cannot
    ; 빈칸 여섯을 먼저 찍어 칸 셈과 Y 를 값과 같게 두고, 그 자리에 고정 문구를 덮는다
    LDX.w #$0006
-
    LDA #$01
    JSR $B235
    DEX
    BNE -
    JSL ShopSellCannot
    BRA .done

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
; 창 글자 변수와 !wn_stage 는 7E:A930~AABB(전투 글 엔진 !bm_* 뒤)에 둔다. 7E:3D14~3E73 은 DQ5 의 움직이는 타일 종류 14
; 사본(03:D3E9 가 맵에 들어갈 때 채우고 03:D5CC 가 미는 11칸)이라 쓰지 않는다
!wt_keys  = $A98C           ; 슬롯 수만큼 워드(7E, 30개): 슬롯마다 버퍼 자리(!wt_buf + Y)
!wt_ages  = $A930           ; 슬롯 수만큼 워드(30개까지): 마지막으로 쓴 때, 0 = 빈 슬롯
!wt_need  = $A988           ; 0 = 작은 슬롯(네 열까지), 1 = 중간(일곱 열까지), 2 = 큰 슬롯
!wt_first = $A98A           ; 빈 슬롯·오래된 슬롯을 찾기 시작할 자리(슬롯 × 2)
!wt_buf   = $A9EC           ; 타일맵 버퍼 포인터: 목록·창 본문은 $E0, 창 제목은 $DC
!wt_field = $A9EE           ; 0 = 전투(NMI 작업 $1944 = 00:8952). 필드 전용 슬롯을 쓸지
!wt_nslot = 30
!wt_nkana = 12              ; 앞 12개는 가나 칸을 길이만큼 잘라 쓰는 항목(첫 칸·칸 수는 RAM), 뒤 18개는 캔버스 안 고정 슬롯
!wt_kbase = $A9F4           ; 가나 항목마다 1바이트: 첫 칸
!wt_klen  = $AA00           ; 가나 항목마다 1바이트: 칸 수(열 수 × 2)
!wt_occ   = $AA0C           ; 13바이트: 가나 칸 010~077 의 쓰는 칸 비트(WtOcc 가 그때그때 만듦)
!wt_tmp   = $AA1A           ; WtAlloc 안에서만: 찾는 칸 수, 찾은 첫 칸
!wt_hash  = $1D0C           ; WtAlloc 안에서만: 그린 문구 표식. 이름 그리기(WnKorean)의 !wn_s 와 자리를 함께 씀(겹쳐 돌지 않음)
!wt_slot2 = $A972           ; 이번에 쓴 슬롯 × 2, FFFF = 명령 창 전용 칸
!wt_fixkeys = $3EA0         ; 8 워드: 전용 칸에 그린 명령 창·가게 창 문구의 버퍼 자리, 0 = 빈 칸. WtVis 가 안 보이는 것을 지움
!wt_k     = $A974           ; 그리는 고정 문구 번호
!wt_dirty = $A9F0           ; 2 워드: 슬롯마다 1비트, 메시지 캔버스 안에 그림을 올린 슬롯
!wt_age   = $A96C           ; 쓸 때마다 하나씩
!wt_mode  = $A96E           ; 고정 글자 수: 0 = 04:B808(길이 $00), 5 = 04:B8F3(주문), 9 = 04:BC08(몬스터)
!wt_lastx = $A970           ; 원래 루틴이 마지막으로 찍는 바이트의 DP 자리
!wt_sp    = $A97C           ; 원래 스택 포인터(7E)
!wt_cols  = $1D84           ; 그릴 열 수
!wt_base  = $1D86           ; 빌린 첫 칸(글자 줄)
!wt_ubase = $A9EA           ; 위 줄 첫 칸. 가나 항목·전투 슬롯·전용 칸은 글자 줄 열 칸 다음, 필드 캔버스 슬롯은 WtUpperF
!wt_ptr   = $1D88           ; 그림 자리(뱅크 !wt_bank 안, 몬스터는 !wt_mbank 안). 그리기는 WtFetchPic 이 !wn_stage 로 옮긴 사본을 읽는다
!wt_len   = $A97A           ; 원래 문자열 길이($00). $1D8A 에 두면 16비트 쓰기가 지금 곡 번호 $1D8B 를 00 으로 덮음
!wq_count = $A97E           ; 우리 전송 대기열 항목 수(7E, NMI 가 보내고 0 으로)
!wq_off   = $A980           ; 대기열에 다음으로 쓸 자리
!wt_vis   = $A9C8           ; 슬롯마다 1바이트: bit0 = 마지막 창 타일맵 전송 때 보였거나 그 뒤에 그렸음, bit1~7 = 그린 문구 표식
!wt_xfer  = $A9E6           ; 1바이트: 이번 NMI 에 게임이 보낼 창 타일맵 줄($0BEC 의 bit7·6), NMI 끝에서 WtVis 가 씀
!wt_late_line = 245         ; 게이트 일 뒤 이 주사선부터는 게임의 창 타일맵 2KB 를 미룬다(실측: 게임 NMI 진입이 한 줄쯤
                            ; 뒤, 2KB DMA 시작이 그 세 줄 뒤. 2KB 는 열두 줄이라 249 줄까지 시작해야 261 줄 안에 끝남)
!wt_restore_line = 250      ; 게이트가 이 주사선 앞에서만 슬롯을 하나 더 되돌린다(하나에 다섯 줄까지)
!wh_with_line = 245        ; WhWith 가 이 주사선 앞에서만 창 타일맵(1920바이트, 열한 줄 남짓)을 대신 보낸다
!wh_dma_line = 260          ; 묶음 그림 DMA 하나(160바이트까지, 한 줄 남짓)를 이 주사선 앞에서만 시작한다
!wh_mask_line = 261         ; 가림 두 칸 묶음을 이 주사선 앞에서만 쓴다(두 칸에 반 줄이 안 됨)
!wh_budget = 670           ; WhReq 가 짜는 한 NMI 몫(바이트). 그림 바이트에 DMA 하나마다 !wh_dma_cost, 가림 한 칸마다
                            ; !wh_mask_cost 를 더해 센다. 넘는 것은 다음 NMI 로(WhNmi). 실제 상한은 WhWith 의 주사선 확인
!wh_dma_cost = 64
!wh_mask_cost = 24          ; 가림 한 칸(VRAM 주소·값 쓰기)
!wh_ndma = 9                ; DMA 표 칸 수
; 묶음 버퍼(WhStash·WhRelease) 자리. 7F:8300~ 은 1장 이어 걷기·창 검사 장면에서 읽는 곳이 없고 맵을 불러올 때 지우기만 함
!wh_magic = $7F8300
!wh_count = $7F8302         ; 항목 수
!wh_off   = $7F8304         ; 다음에 쓸 자리
!wh_rd    = $7F8306         ; 다음에 보낼 자리
!wh_go    = $7F8308         ; 보내도 되는 항목 수(창 타일맵을 보낸 NMI 에 그때까지 쌓인 수로 정함)
!wh_msgwin = $7F830A        ; 0 = 마지막으로 보낸 창 타일맵에 메시지 창 테두리가 없음(캔버스 칸이 화면에 안 보임)
!wh_pend  = $7F830C         ; 1 = WhWith 가 게임의 창 타일맵 요청을 한 NMI 붙잡아 둠(다음 NMI 에 다시 함)
!wh_maskthis = $7F830E      ; 이 NMI 에 WhWith 가 쓴 가림 칸 수(NMI 끝 WhMsgWin 이 보고 지움)
!wh_dma   = $7FA210         ; WhReq 가 짠 DMA 표([VRAM 워드][원본][길이][묶음 안 자리] 8바이트씩, VRAM 워드 FFFF 로 끝)
!wh_mask  = $7FA260         ; WhReq 가 짠 가림 표([타일맵 VRAM 워드][값] 4바이트씩, FFFF 로 끝, !wh_nmask 개까지)
!wh_snap  = $7FA2E0         ; WhReq 가 잴 때의 !wh_rd·!wh_count(그사이 NMI 가 묶음을 보냈으면 WhWith 가 표를 쓰지 않음)
!wh_snapn = $7FA2E2
; WhReq(본 흐름) 전용 임시 칸. NMI 가 쓰는 칸을 빌리면 그사이 NMI 가 덮는다
!wh_tmpn = $7FA2E4
!wh_tmpl = $7FA2E6
!wh_tmpb = $7FA2E8
!wh_tmpv = $7FA2EA
!wh_tmpm = $7FA2EC
!wh_tmpx = $7FA2EE
!wh_tmpk = $7FA2F0
!wh_tmpc = $7FA2F2
!wh_tmpd = $7FA2F4
!wh_tmpt = $7FA2F6
!wh_tmpi = $7FA2F8
!wh_tmpe = $7FA2FA
!wh_tmpr = $7FA2FC          ; WhReq: DMA 표에 넣은 칸 수
!wh_tmpq = $7FA2FE          ; WhReq: 건너뛴 항목 VRAM 워드 수
!wh_skip = $7FA300          ; WhReq: 건너뛴 항목 VRAM 워드(8개까지)
!wh_tmps = $7FA310          ; WhShown(본 흐름: WhStash·WhReq). 7E 의 우리 칸(!wn_*)은 이름을 그리는 동안만 비어 있다
!wh_nmask = 24
!wt_stc   = $7F8310         ; 후보 둘 × [버퍼 칸 주소, 타일, 버퍼 칸 주소, 타일] 워드. 찾기가 적고 게이트가 비교만 함
!wh_buf   = $7F8320
!wh_size  = $1EF0
!wh_magic_value = $4857
!wt_stale = $A9E7           ; 1바이트씩: 그림을 올렸는데 WtVis 가 안 보인다고 잰 캔버스 슬롯 × 2 + 1 둘(0 = 없음).
!wt_stale2 = $A9E9          ; NMI 끝(WtStaleFind)마다 새로 찾고, 게이트(WtStaleGate)가 메시지 창이 그 칸을 가리키면 되돌림
!wt_ecsave = $A9E8          ; 1바이트: 창 제목을 그리는 동안 맡겨 둔 $EC
!wq_rd    = $A978           ; NMI 가 다음으로 보낼 항목 자리. VBlank 가 끝나 가면 남은 항목을 다음 NMI 로 넘긴다
!wq_defer = $A976           ; 1바이트: bit7·6 = 다음 NMI 로 미룬 게임의 창 타일맵 전송 요청($0BEC),
                            ; bit1·0 = 전투에 들어가면 되돌릴 가나 칸 덩이 수(필드에서 가나 칸 슬롯을 쓰면 3),
                            ; bit3 = 이 NMI 의 창 타일맵은 이미 한 번 미룬 것,
                            ; bit4 = 그 NMI 에 게임이 새 요청을 걸지 않아 버퍼가 미룰 때 잰 그대로,
                            ; bit5 = 다음 NMI 첫머리에 WhWith 가 창 타일맵과 묶음 그림·가림을 함께 보냄(WhReq 가 켬),
                            ; bit2 = 화면 타일맵에 가림(WhWith)이 들어 있음. 가린 슬롯을 되돌리면 타일맵을 다시 보냄(WhUnmask)
!wq_buf   = $3EB0           ; 대기열 7E:3EB0~3FFF. 항목 [VRAM 워드 2][방식 1][칸 수 1][그림]
!wq_size  = $0150
!wq_left  = $A982           ; NMI 안에서만: 남은 항목 수
!wq_head  = $A984           ; NMI 안에서만: 방식·칸 수
!wq_len   = $A986           ; NMI 안에서만: 그림 바이트 수

; 칸 풀: 1FF~1D0, 이어서 17F~B0 을 위에서부터 빌린다. 096~0AF 는 전투 글자, 180~1CF 는 상태 창 이름 자리라 넣지 않는다.
; 걷는 메시지 캔버스는 096 부터 위로 채우므로 위에서부터 빌리면 겹치기 어렵다. 전투 연출(B0~122)과 전투 글 칸 풀
; (dq4battlemsg.asm)은 목록 창이 닫힌 뒤에 쓰인다.

!wn_stage = $AA1C           ; 올릴 160바이트를 먼저 만드는 자리


; 수 창(5C 등 자리마다 0~9 를 고르는 창)의 위·아래(04:C967·04:C98C). 자리 숫자는 타일 코드 02~0B 로 $0AFE + 자리에 둔다.
; 원래는 0~9 를 돈다. 가게 개수 창은 $0F2C 에 최대를 둔 동안만 끝 자리를 1~최대 사이로 움직이고(끝에서 멈춤) 앞 자리는 0 으로 둔다
org $04D16D
    JSL QpFrame
; 창 표를 창 번호로 읽어 $DA 에 두는 네 자리(LDA $EB48,X / STA $DA): 창 열기 04:9C46 와 크기·그리기 쪽
; 04:A437·04:A48A·04:A7F4. 가게 개수 창은 열 때 9C46 뒤 A48A 에서 레코드를 다시 읽으므로 넷 모두 같은 훅으로 바꾼다
org $049C46
    JSL ShopOpenRes
    NOP
org $04A437
    JSL ShopOpenRes
    NOP
org $04A48A
    JSL ShopOpenRes
    NOP
org $04A7F4
    JSL ShopOpenRes
    NOP
org $04C970
    JSL WnQtyUp
    NOP #6
org $04C995
    JSL WnQtyDown
    NOP #6

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
; 04:B880(D4 격투장 몬스터 이름, 열 글자). 한글로 그리면 원래 이름 뒤에 붙이던 구별 글자(A·B, $1005 bit7 이 꺼진
; 몬스터)는 빠진다
WnArena:
    LDA #$0A
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
    PHA
    LDX #$0000
    LDA.b $43
    AND #$00FF
    CMP.w #!wt_mkind
    BNE +
    INX
+
    PLA
    JSR WtFetchPic
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
    LDA.l $7E0000|!wn_stage
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
; WqClean 이 지우고, 필드 전용 가나 칸 슬롯은 캔버스 밖이다(명령 창·가게 창 문구는 캔버스 밖 1D0~1FF 의 전용 칸이고,
; 그 창이 안 보이는 동안은 같은 칸을 필드 전용 슬롯 셋으로 빌려 가나 칸이 찬 목록이 메시지 창에 비치지 않게 한다).
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
    ; 그린 문구의 표식(!wt_vis bit1~7): 그림 자리의 7비트 해시, bit0 = 보임
    LDA.w !wt_ptr
    LSR
    LSR
    LSR
    LSR
    LSR
    LSR
    LSR
    EOR.w !wt_ptr
    ASL
    ORA #$0001
    AND #$00FF
    STA.w !wt_hash
    LDX #$0000
-
    LDA.w !wt_keys,X
    CMP.w !wn_key
    BNE +
    JSR WtFits
    BCC .resize
    ; 보이는 슬롯에 다른 문구를 덮으면 게임이 새 창 타일맵을 보내기 전 몇 프레임 동안 옛 타일맵이 새 그림을 가리켜
    ; 글자가 깨진다(가게 동료 창의 「소지 중 ↔ 없음」). 그때는 새 슬롯에 그리고, 옛 슬롯은 같은 키로 남겨 타일맵이
    ; 바뀌면 WtVis 가 안 보인다고 표시하게 둔다
    PHX
    TXA
    LSR
    TAX
    LDA.w !wt_vis,X
    PLX
    AND #$00FF
    BIT #$0001
    BEQ .found
    EOR.w !wt_hash
    AND #$00FE
    BEQ .found
    BRA +
.resize
    JSR WtResize
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
    AND #$0001
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
    LDA.w !wt_hash
    STA.w !wt_vis,X
    REP #$20
    PLX
    JSR WtBaseOf
    STA.w !wt_base
    JSR WtUpperOf
    STA.w !wt_ubase
    CLC
    RTS

; 슬롯 X 의 첫 칸(A). 가나 항목은 RAM, 캔버스 슬롯은 필드면 WtSlotF, 전투면 WtSlot
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
    LDA.w $1944
    CMP #$8952
    BEQ +
    LDA.l WtSlotF,X
    RTS
+
    LDA.l WtSlot,X
    RTS

; 슬롯 X 의 등급(A). 필드면 WtClassF, 전투면 WtClass
WtClassOf:
    LDA.w $1944
    CMP #$8952
    BEQ +
    LDA.l WtClassF,X
    RTS
+
    LDA.l WtClass,X
    RTS

; 슬롯 X 의 위 줄 첫 칸(A). WtBaseOf 바로 뒤에 부르고 !wt_base·!wt_cols 가 정해져 있어야 한다
WtUpperOf:
    CPX.w #!wt_nkana*2
    BCC +
    LDA.w $1944
    CMP #$8952
    BEQ +
    LDA.l WtUpperF,X
    BEQ +
    RTS
+
    LDA.w !wt_base
    CLC
    ADC.w !wt_cols
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
    LDA.w !wt_field
    BEQ .battle
    ; 캔버스 밖 1D0~1FF 의 슬롯은 전용 칸 문구가 하나도 안 보일 때만(일부만 가려진 명령 창의 문구를 덮지 않게)
    LDA.l WtClassF,X
    AND #$0020
    BEQ +
    PHX
    LDX #$000E
-
    LDA.w !wt_fixkeys,X
    BNE .busy
    DEX
    DEX
    BPL -
    PLX
    BRA +
.busy
    PLX
    BRA ++
+
    LDA.l WtClassF,X
    AND #$000F
    BRA .cmp
.battle
    LDA.l WtClass,X
    CMP #$0010
    BCS ++
.cmp
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
    AND #$0001
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

; 전투에서 쓰는 슬롯의 첫 칸과 등급(필드는 WtSlotF). 0 = 작은 슬롯 8칸(네 열), 1 = 중간 슬롯 14칸(일곱 열),
; 2 = 큰 슬롯 20칸(열 열), 글자 줄 다음에 위 줄이 이어진다. $10 을 더하면 필드에서만 쓰는 슬롯이라 전투에서는 고르지 않고,
; $20 은 캔버스 밖 1D0~1FF 의 슬롯이다. 앞 12개는 가나 항목 자리라 0. 맞는 크기가 모자라면 더 큰 슬롯을 빌리고, 빈 슬롯은
; 표 순서로 고른다. 작은 것부터, 같은 크기면 높은 칸부터: 메시지는 캔버스를 096 부터 채워 낮은 칸일수록 메시지 글자에 덮이기
; 쉽고, 전투 공격 연출은 B0~122 를 덮는다.
WtSlot:
    dw 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0
    dw $0174, $016C, $0164, $015C, $0154, $014C, $01F8, $01E4, $01D0
    dw $013E, $0130, $0122, $0114
    dw $0100, $00EC, $00D8, $00C4, $00B0
WtClass:
    dw $FF, $FF, $FF, $FF, $FF, $FF, $FF, $FF, $FF, $FF, $FF, $FF
    dw 0, 0, 0, 0, 0, 0, $30, $32, $32
    dw 1, 1, 1, 1
    dw 2, 2, 2, 2, 2
; 필드에서 쓰는 슬롯(WtBaseOf·WtUpperOf·WtFits·WqClean 이 $1944 로 고름). 앞 셋은 전투 표의 캔버스 밖 1D0~1FF 슬롯이고
; ($20, 위 줄은 글자 줄 바로 뒤라 WtUpperF = 0), 메시지 창에 비치지 않으니 먼저 고르게 맨 앞에 둔다. 캔버스 밖이라 WqClean 이
; 비우지 않는다. 나머지는 캔버스 안에서 글자 줄과 위 줄을 따로 둔다. 가게 팔기·
; 맡기기 목록 창은 메시지 창의 화면 9~21열을 덮으므로, 앞쪽 캔버스 슬롯(작은 셋, 중간 셋, 큰 하나)은 두 줄 모두 캔버스 앞
; 여덟 줄의 7~19번째 칸에 두어 가나 칸을 넘친 목록 이름이 메시지 창에 비치지 않게 한다. 캔버스 마지막 줄(화면 26줄)은 가게
; 사기의 장비 비교 창이 덮지 않아 뺀다. 한 줄에 일곱 칸 넘는 줄은 하나만 들어가 더 가리지는 못하고, DQ4 물건 이름은 6~7열이
; 가장 많아 중간을 많이 가렸다. 빈 슬롯은 표 순서로 고르므로 가린 큰 슬롯을 보이는 중간 슬롯보다 앞에 둔다. 칸은 서로 겹치지
; 않는다(test_dq4windowname.py).
WtSlotF:
    dw 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0
    dw $01F8, $01E4, $01D0, $010D, $011E, $00A4, $0147, $00A8, $0166
    dw $0122, $00BA, $009D, $00D0
    dw $0096, $00AC, $015C, $0176, $00DA
WtUpperF:
    dw 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0
    dw 0, 0, 0, $00EC, $00B6, $013F, $00C1, $0101, $0143
    dw $00F0, $0106, $0138, $0152
    dw $016F, $0111, $00F7, $00C6, $0129
WtClassF:
    dw $FF, $FF, $FF, $FF, $FF, $FF, $FF, $FF, $FF, $FF, $FF, $FF
    dw $20, $22, $22, 0, 0, 0, 0, 0, 0
    dw 1, 1, 1, 2
    dw 1, 2, 2, 2, 2
; 필드 슬롯마다 (버퍼 자리, 타일) 넷: 글자 줄 첫·끝 칸과 위 줄 첫·끝 칸을 메시지 창(화면 18~26줄·3~28열에 캔버스 096~17F 를
; 한 줄 26칸씩)이 가리키는 7E:5000 버퍼 자리. 그 자리가 그 타일이면 메시지 창이 그 칸을 보인다. 캔버스 밖 슬롯은 0
; (test_dq4windowname.py 가 WtSlotF·WtUpperF 와 맞는지 본다)
WtMsgCellF:
    dw 0, 0, 0, 0, 0, 0, 0, 0
    dw 0, 0, 0, 0, 0, 0, 0, 0
    dw 0, 0, 0, 0, 0, 0, 0, 0
    dw 0, 0, 0, 0, 0, 0, 0, 0
    dw 0, 0, 0, 0, 0, 0, 0, 0
    dw 0, 0, 0, 0, 0, 0, 0, 0
    dw 0, 0, 0, 0, 0, 0, 0, 0
    dw 0, 0, 0, 0, 0, 0, 0, 0
    dw 0, 0, 0, 0, 0, 0, 0, 0
    dw 0, 0, 0, 0, 0, 0, 0, 0
    dw 0, 0, 0, 0, 0, 0, 0, 0
    dw 0, 0, 0, 0, 0, 0, 0, 0
    dw 0, 0, 0, 0, 0, 0, 0, 0
    dw 0, 0, 0, 0, 0, 0, 0, 0
    dw 0, 0, 0, 0, 0, 0, 0, 0
    dw $55A4, $010D, $55AA, $0110, $5556, $00EC, $555C, $00EF
    dw $55D2, $011E, $55D8, $0121, $54D2, $00B6, $54D8, $00B9
    dw $54A2, $00A4, $54A8, $00A7, $5620, $013F, $5626, $0142
    dw $5630, $0147, $5636, $014A, $54E8, $00C1, $54EE, $00C4
    dw $54AA, $00A8, $54B0, $00AB, $558C, $0101, $5592, $0104
    dw $5686, $0166, $568C, $0169, $5628, $0143, $562E, $0146
    dw $55DA, $0122, $55E6, $0128, $555E, $00F0, $556A, $00F6
    dw $54DA, $00BA, $54E6, $00C0, $5596, $0106, $55A2, $010C
    dw $5494, $009D, $54A0, $00A3, $5612, $0138, $561E, $013E
    dw $5512, $00D0, $5524, $00D9, $5652, $0152, $5664, $015B
    dw $5486, $0096, $5492, $009C, $5698, $016F, $56A4, $0175
    dw $54B2, $00AC, $54D0, $00B5, $55AC, $0111, $55CA, $011A
    dw $5666, $015C, $5678, $0165, $556C, $00F7, $558A, $0100
    dw $56A6, $0176, $56B8, $017F, $54F2, $00C6, $5510, $00CF
    dw $5526, $00DA, $5538, $00E3, $55E8, $0129, $5606, $0132
; 슬롯 × 2 → !wt_dirty 의 비트(낮은 워드, 높은 워드). 슬롯 i 는 비트 i 이고, 캔버스 밖 가나 항목은 0. 1D0~1FF 슬롯(등급 $20)은
; 전투 표와 필드 표에서 번호가 달라 비트를 두고 WqClean 이 등급을 보고 건너뛴다
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

; 04:C970·04:C995(M = 8, X = 자리). 돌려준 A 를 원래 코드가 $0AFE,X 에 쓴다. $0F2C 가 0 이면 원래대로.
; $0F2C 아래 6비트 = 최대, bit6 = 수 창이 떠 있음(QpFrame), bit7 = 팔기(QpDraw 의 셈)
WnQtyUp:
    LDA.l $7E0F2C
    BNE .cap
    LDA.w $0AFE,X
    INC
    CMP #$0C
    BCC +
    LDA #$02
+
    RTL
.cap
    TXA                     ; X 는 8·16비트 어느 쪽이어도 낮은 바이트가 자리
    CMP #$04
    BNE WnQtyZero
    LDA.l $7E0F2C
    AND #$3F
    PHA                     ; 최대(DP 를 쓰지 않으려고 스택에)
    LDA.w $0AFE,X
    SEC
    SBC #$01                ; 다음 숫자(코드 − 2 + 1)
    CMP $01,S
    BEQ +
    BCC +
    LDA $01,S               ; 최대에서 멈춘다(오른쪽 ▲ 가 사라져 더 못 감을 보인다)
+
    XBA
    PLA
    XBA
    JMP WnQtyDone
WnQtyZero:
    LDA #$02
    RTL

WnQtyDown:
    LDA.l $7E0F2C
    BNE .cap
    LDA.w $0AFE,X
    DEC
    CMP #$02
    BCS +
    LDA #$0B
+
    RTL
.cap
    TXA
    CMP #$04
    BNE WnQtyZero
    LDA.w $0AFE,X
    SEC
    SBC #$03                ; 앞 숫자(코드 − 2 − 1)
    BEQ +
    BPL WnQtyDone
+
    LDA #$01                ; 1 에서 멈춘다
WnQtyDone:
    CLC
    ADC #$02
    STA.w $0AFE,X           ; 원래 코드도 쓰지만, 뒤의 키 반복 대기 동안 화살표·금액이 옛 개수로 남지 않게 먼저 쓰고 바로 그린다
    PHA
    PHP
    REP #$10                ; QpWindow·QpDraw 는 X = 16 을 바란다(이 자리는 X = 8)
    JSR QpWindow
    LDA.l $7E0B02
    SEC
    SBC #$02
    JSR QpDraw
    PLP
    PLA
    RTL

; 「몇 개 파시겠어요? / 받는 돈 / 판 뒤」 메시지 번호(가게 종류 $0F20 마다). 원작에서 비어 있고 부르는 곳이 없는 메시지.
; ShopSellQty 가 LDA.l 로 읽으므로 자리가 모자란 뱅크 12 대신 여기에 둔다
ShopSellMsg:
    dw $00C4, $00D6, $00D7, $00D8

; 04:D16D(수 창 깜박임 04:D162 안, M = 8, X = 16, 레지스터는 04:D162 가 맡김). 수 창이 떠 있는 동안 매 프레임 부른다.
; 가게 개수 창($0F2C ≠ 0)이면 끝 자리($0B02, 타일 코드)로 금액 두 줄을 메시지 창에 쓰고, 덮은 LDA $0AD9 / CLC 를 한다
QpFrame:
    LDA.l $7E0F2C
    AND #$40
    BNE .shop
    LDA.w $0AD9
    CLC
    RTL
.shop
    JSR QpWindow
    LDA.l $7E0B02
    SEC
    SBC #$02
    JSR QpDraw
    LDA #$00                ; 깜박임 박자(뒤에서 8 을 더함)를 늘 양수로 두어 끝 자리 숫자를 깜박이지 않게 한다
    CLC
    RTL

; 개수 창 칸을 ▲ / 숫자 / ▼ 세 줄로 고쳐 쓴다(M = 8, X = 16). 원래 창은 다섯 자리를 하나씩 고르는 은행용이라
; 「0000N」 에 커서 자리가 ✱ 와 번갈아 깜박인다. 가게는 끝 자리만 쓰므로 높이 5 의 ShopQtyRec 으로 열고(ShopOpenRes)
; 숫자 위·아래에 더 갈 수 있는 쪽 화살표만 둔다(▲ 는 ▼ 타일을 위아래로 뒤집어 쓴다).
; 커서 자리 칸 좌표표($0A56, 자리마다 x·y)를 끝 자리 → 숫자 칸, 나머지 → 화면 밖 칸으로 바꿔, 엔진이 그리는 숫자도
; 같은 칸에 가고 왼쪽·오른쪽으로 커서를 옮겨도 ✱ 가 보이지 않게 한다. 옮긴 커서 자리는 다음 프레임에 끝 자리로 되돌린다
QpWindow:
    PHX
    LDA #$04
    STA.l $7E0AD7
    LDA.l $7E0B02
    CMP #$02
    BNE +
    INC                     ; 처음 열린 0 을 1 로
    STA.l $7E0B02
+
    REP #$20
    LDA.w #!qp_off_xy
    STA.l $7E0A56
    STA.l $7E0A58
    STA.l $7E0A5A
    STA.l $7E0A5C
    LDA.w #!qp_num_xy
    STA.l $7E0A5E
    LDA.w #$2001            ; 엔진이 첫 줄에 그린 「0000」 과 커서를 지운다
    LDX.w #$000A
-
    STA.l !qp_line,X
    DEX
    DEX
    BPL -
    SEP #$20
    LDA.l $7E0B02
    STA.l !qp_num
    LDA #$20
    STA.l !qp_num+1
    LDA.l $7E0F2C
    AND #$3F
    CLC
    ADC #$02                ; 최대의 타일 코드
    LDX.w #$A07B            ; ▲
    CMP.l $7E0B02
    BNE +
    LDX.w #$2001
+
    REP #$20
    TXA
    STA.l !qp_up
    SEP #$20
    LDX.w #$207B            ; ▼
    LDA.l $7E0B02
    CMP #$03
    BNE +
    LDX.w #$2001
+
    REP #$20
    TXA
    STA.l !qp_down
    SEP #$20
    PLX
    RTS

; 04:9C46 등(M = 16, X = 16 = 창 번호 × 2, DB = 04). 덮은 LDA $EB48,X / STA $DA 를 하되(A 도 레코드로 남김), 가게 개수 창
; ($0F2C bit6)이 창 5C 를 열 때만 ShopQtyRec 을 준다. 5C 는 맡기는 곳 등과 같이 쓰므로 레코드는 그대로 둔다
ShopOpenRes:
    LDA.w $EB48,X
    CPX.w #$005C*2
    BNE +
    PHA
    LDA.l $7E0F2C
    AND.w #$0040
    BEQ .keep
    PLA
    LDA.w #ShopQtyRec
    BRA +
.keep
    PLA
+
    STA.b $DA
    RTL

; 개수 창 메시지(「몇 개 사시겠어요? / 쓰는 돈 / 남는 돈」, 팔기는 「받는 돈 / 판 뒤」)의 둘째·셋째 줄 숫자 다섯 칸과 G 를 다섯 칸을 창 버퍼(7E:5000, 수 창이 떠 있는 동안 매 프레임 VRAM 으로 감)에 쓴다.
; A = 개수. 첫 줄 = 개수 × 한 개 값($0F28~), 둘째 줄 = 가진 돈(7E:2019~) − 첫 줄(사기) 또는 + 첫 줄(팔기, 99999 에서 멈춤).
; 숫자 타일은 값 + 2, 앞의 0 은 빈칸 01. 낮은 바이트만 쓴다(높은 바이트는 창이 그린 색). DP $00~$08 을 쓴다
QpDraw:
    PHP
    PHB
    PHK                     ; 자리값 표 QpPlace 를 .w 로 읽으려고 DB = 이 뱅크(부르는 곳은 DB = 04)
    PLB
    REP #$30
    PHX
    PHY
    TAX
    LDA.b $00               ; 수 창 깜박임(04:D162) 안에서 불리므로 둘레 코드의 DP $00~$09 를 맡겼다가 되돌린다
    PHA
    LDA.b $02
    PHA
    LDA.b $04
    PHA
    LDA.b $06
    PHA
    LDA.b $08
    PHA
    TXA
    AND.w #$000F
    TAX
    SEP #$20
    STZ.b $00
    STZ.b $01
    STZ.b $02
-
    DEX
    BMI +
    REP #$21
    LDA.b $00
    ADC.l $7E0F28
    STA.b $00
    SEP #$20
    LDA.b $02
    ADC.l $7E0F2A
    STA.b $02
    BRA -
+
    REP #$20
    LDA.b $00
    STA.b $04
    SEP #$20
    LDA.b $02
    STA.b $06
    LDA.l $7E0F2C
    BMI .sell
    REP #$21
    LDA.l $7E2019
    SEC
    SBC.b $04
    STA.b $04
    SEP #$20
    LDA.l $7E201B
    SBC.b $06
    STA.b $06
    BRA .draw
.sell
    REP #$21
    LDA.l $7E2019
    ADC.b $04
    STA.b $04
    SEP #$20
    LDA.l $7E201B
    ADC.b $06
    STA.b $06
.draw
    LDX.w #!qp_row1
    JSR QpNumber
    REP #$20
    LDA.b $04
    STA.b $00
    SEP #$20
    LDA.b $06
    STA.b $02
    LDX.w #!qp_row2
    JSR QpNumber
    REP #$30
    PLA
    STA.b $08
    PLA
    STA.b $06
    PLA
    STA.b $04
    PLA
    STA.b $02
    PLA
    STA.b $00
    PLY
    PLX
    PLB
    PLP
    RTS

; $00~$02(24비트)를 99999 에서 멈춰 X(7E 뱅크 버퍼 주소)부터 다섯 칸에 쓴다. M = 8, X = 16
QpNumber:
    LDA.b $02
    BNE .max
    REP #$20
    LDA.b $00
    CMP.w #$86A0            ; 100000 = $0186A0. 높은 바이트가 1 이면 아래 16비트로 견준다
    SEP #$20
    BRA .ok
.max
    CMP #$01
    BNE .big
    REP #$20
    LDA.b $00
    CMP.w #$86A0
    SEP #$20
    BCC .ok
.big
    LDA #$9F                ; 99999 = $01869F
    STA.b $00
    LDA #$86
    STA.b $01
    LDA #$01
    STA.b $02
.ok
    LDY.w #$0000
    STZ.b $08               ; 앞자리 0 을 빈칸으로(0 이 아닌 숫자를 만나면 1)
-
    STZ.b $07
--
    ; $00~$02 >= 자리값(QpPlace,Y)이면 빼고 숫자를 하나 올린다
    REP #$20
    LDA.b $00
    SEC
    SBC.w QpPlace,Y
    STA.b $09
    SEP #$20
    LDA.b $02
    SBC.w QpPlace+2,Y
    BCC +
    STA.b $02
    REP #$20
    LDA.b $09
    STA.b $00
    SEP #$20
    INC.b $07
    BRA --
+
    LDA.b $07
    BNE ++
    LDA.b $08
    BNE ++
    CPY.w #$000C            ; 마지막(일의 자리)은 0 도 찍는다
    BEQ ++
    LDA #$01
    BRA +++
++
    INC.b $08
    LDA.b $07
    CLC
    ADC #$02
+++
    XBA                     ; 메시지 창 칸은 캔버스 타일(096~, 높은 바이트에 타일 bit8)이라 글자 색 20 과 함께 워드로 쓴다
    LDA #$20
    XBA
    REP #$20
    STA.l $7E0000,X
    SEP #$20
    INX
    INX
    INY
    INY
    INY
    CPY.w #$000F
    BCC -
    REP #$20
    LDA.w #$200F            ; G
    STA.l $7E0000,X
    SEP #$20
    RTS
QpPlace:
    dl 10000, 1000, 100, 10, 1

; 가게 팔기 목록의 「판매불가」(ShopSellPrice, Y = 빈칸 여섯을 찍은 뒤 자리). 그 여섯 칸에 그리고 Y 는 그대로 둔다
ShopSellCannot:
    REP #$30
    PHY
    TYA
    SEC
    SBC #$000C
    TAY
    LDA.b $E0
    STA.l $7E0000|!wt_buf
    LDA.w #!wt_cannot_sell
    JSR WtFixedDraw
    PLY
    SEP #$20
    RTL



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
; 전용 칸 문구(!wt_base 부터 열 × 2 칸)를 그리기 전에 같은 칸을 빌린 슬롯을 본다. 그 슬롯이 보이면 C = 1(문구는 일반
; 슬롯으로 그려, 보이는 빌린 글자를 덮지 않는다). 안 보이면 슬롯을 비우고, 문구 자리를 !wt_fixkeys 에 넣고 C = 0.
; 빌려 주는 쪽(WtFits)은 !wt_fixkeys 가 하나라도 있으면 빌려 주지 않아, 일부만 가려진 창의 문구도 덮지 않는다
; 빌린 슬롯의 번호·자리는 필드와 전투 표가 달라 WtClassOf·WtBaseOf 로 본다
WtFixLend:
    LDA.w !wt_cols
    ASL
    CLC
    ADC.w !wt_base
    STA.w !wt_tmp
    LDX.w #!wt_nkana*2
.slot
    JSR WtClassOf
    AND #$0020
    BEQ .next
    LDA.w !wt_ages,X
    BEQ .next
    JSR WtBaseOf
    CMP.w !wt_tmp
    BCS .next
    STA.w !wn_c
    JSR WtClassOf
    AND #$000F
    ASL
    PHX
    TAX
    LDA.l WtLen,X
    PLX
    CLC
    ADC.w !wn_c
    CMP.w !wt_base
    BEQ .next
    BCC .next
    PHX
    TXA
    LSR
    TAX
    LDA.w !wt_vis,X
    PLX
    AND #$0001
    BEQ +
    SEC
    RTS
+
    STZ.w !wt_keys,X
    STZ.w !wt_ages,X
.next
    INX
    INX
    CPX.w #!wt_nslot*2
    BCC .slot
    LDA.w !wt_buf
    CLC
    ADC.w !wn_y
    STA.w !wt_tmp
    LDX #$000E
-
    LDA.w !wt_fixkeys,X
    CMP.w !wt_tmp
    BEQ .done
    DEX
    DEX
    BPL -
    LDX #$000E
-
    LDA.w !wt_fixkeys,X
    BEQ +
    DEX
    DEX
    BPL -
    ; 가득 차면(안 보이는데 줄을 아직 재지 않은 자리) 마지막 칸을 덮는다
    LDX #$000E
+
    LDA.w !wt_tmp
    STA.w !wt_fixkeys,X
.done
    CLC
    RTS

WtLen:
    dw 8, 14, 20

; 그림(A = 뱅크 안 주소, 0 이면 그대로 돌아감)을 7E:!wn_stage 로 옮긴다. X = 0 이면 뱅크 !wt_bank, 아니면 몬스터 그림
; 뱅크 !wt_mbank. 몬스터 이름 그림이 !wt_bank 에 다 들어가지 않아 나눴고, 그리기 쪽은 뱅크와 상관없이 사본을 읽는다.
; A·X·Y·DB 를 지킨다(M = X = 16)
WtFetchPic:
    PHB
    PHY
    PHX
    PHA
    CMP #$0000
    BEQ .out
    CPX #$0000
    BNE .monster
    TAX
    LDA.l !wt_bank<<16,X
    JSR .len
    LDY.w #!wn_stage
    db $54,$7E,!wt_bank     ; MVN !wt_bank → 7E
    BRA .out
.monster
    TAX
    LDA.l !wt_mbank<<16,X
    JSR .len
    LDY.w #!wn_stage
    db $54,$7E,!wt_mbank    ; MVN !wt_mbank → 7E
.out
    PLA
    PLX
    PLY
    PLB
    RTS
; A = 열 수 바이트 → MVN 횟수(1 + 열 × 9 − 1)
.len
    AND #$00FF
    STA.l $7E0000|!wt_tmp
    ASL
    ASL
    ASL
    CLC
    ADC.l $7E0000|!wt_tmp
    RTS

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
    PHA
    XBA
    LSR
    AND #$0007
    LDX #$0000
    CMP.w #!wt_mkind
    BNE +
    INX
+
    PLA
    PHX
    TAX
    LDA.l (!wt_bank<<16)|$8000,X
    STA.l $7E0000|!wt_ptr
    PLX
    JSR WtFetchPic
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
    LDA.w !wn_stage
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
    JSR WtFixLend
    BCS +
    LDA.w !wt_base
    CLC
    ADC.w !wt_cols
    STA.w !wt_ubase
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
    ADC.w #!wn_stage
    CLC
    ADC #$0002              ; 열 수 바이트 + 위 줄 7줄째
    TAX
    LDA #$0008
    STA.w !wn_r
-
    LDA.l $7E0000,X
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
    LDA.w !wt_ubase
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
    ADC.w #!wn_stage
    CLC
    ADC #$0001              ; 열 수 바이트 다음이 위 줄 7줄째
    TAX
    LDA.l $7E0000,X
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
    ; 필드의 캔버스 안 슬롯 그림은 창 타일맵을 보내는 NMI 까지 묶음 버퍼로(WhStash)
    LDA.w $1944
    CMP #$8952
    BEQ +++
    LDA.l WtClassF,X
    AND #$0020
    BNE +++
    JSR WhStash
+++
    ; WtAlloc 과 여기 사이에 NMI 의 WtStaleGate 가 이 슬롯을 비웠을 수 있어 NMI 를 끈 채 키·나이를 다시 쓴다
    LDA.w !wn_key
    STA.w !wt_keys,X
    LDA.w !wt_age
    STA.w !wt_ages,X
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
    ; bit3: 이 NMI 의 창 타일맵은 한 번 미룬 것이라 묶음 버퍼·되돌리기가 다시 미루지 않는다(매 프레임 다시 그리는 창에서
    ; 미루기가 이어지면 창이 뜨지 않음). bit4: 그사이 게임이 새 요청을 걸지 않았다
    LDA.l $000BEC
    BEQ +++
    LDA #$08
    BRA ++++
+++
    LDA #$18
++++
    PHA
    LDA.l $7E0000|!wq_defer
    AND #$C0
    ORA.l $000BEC
    STA.l $000BEC
    LDA.l $7E0000|!wq_defer
    AND #$03
    ORA $01,S
    STA.l $7E0000|!wq_defer
    PLA
    BRA ++
+
    LDA.l $7E0000|!wq_defer
    AND #$E7
    STA.l $7E0000|!wq_defer
++
    ; 게임의 창 타일맵 2KB 전송이 이 게이트 뒤에 오므로, 할 일이 없으면 들르지도 않는다(들러 재는 시간만으로 전송이 한두 줄
    ; 밀렸다). 일을 했으면 WtLateDefer 가 늦어진 타일맵을 미룬다. 미룬 타일맵을 보내는 NMI 에 버퍼가 그대로면(bit4) 미룰 때
    ; 이미 재고 되돌렸으므로 다시 재지 않는다(WtVis 는 타일맵을 보낸 NMI 에만 돌아 그사이 후보도 그대로)
    LDA.l $7E0000|!wq_defer
    AND #$10
    BNE .nostale
    LDA.l $000BEC
    BNE .stale
    LDA.l $7E0000|!wt_stale
    BEQ +
    BPL .stale
+
    LDA.l $7E0000|!wt_stale2
    BEQ .nostale
    BMI .nostale
.stale
    JSR WtStaleFast
    BCC .nostale
    JSR WtStaleGate
    JSR WtLateDefer
.nostale
    LDA.l !wh_count
    ORA.l !wh_count+1
    BEQ +++
    ; 미룬 타일맵을 보내는 NMI(bit3)에 WhRelease 가 할 일은 이번 타일맵까지 쌓인 수를 다음 NMI 몫으로 정하는 것뿐이다.
    ; 그 NMI 는 후보 검사와 겹치기 쉬워 들르지 않고 바로 적는다
    LDA.l $7E0000|!wq_defer
    AND #$08
    BEQ ++
    LDA.l $000BEC
    BEQ ++
    REP #$20
    LDA.l !wh_count
    STA.l !wh_go
    SEP #$20
    BRA +++
++
    JSR WhRelease
    JSR WtLateDefer
+++
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

; 게이트(M = 8). 후보마다 찾기가 적어 둔 버퍼 칸 둘(!wt_stc)을 곧 보낼 버퍼와 바로 비교한다. 하나라도 메시지 창이
; 가리키면 C = 1(WtStaleGate 가 검증하고 되돌림), 아니면 후보에 bit7 을 켜고 C = 0. 창 타일맵을 보내는 NMI 마다 도는 자리라
; DB·슬롯 검증 없이 짧게 둔다(WtStaleGate 로 재면 후보 둘에 두 줄이 들어 2KB 전송이 VBlank 를 넘겼다)
WtStaleFast:
    PHP
    REP #$30
    LDA.l $7E0000|!wt_stale
    AND #$00FF
    BEQ +
    LDA.l !wt_stc
    TAX
    LDA.l $7E0000,X
    AND #$03FF
    CMP.l !wt_stc+2
    BEQ .hit
    LDA.l !wt_stc+4
    TAX
    LDA.l $7E0000,X
    AND #$03FF
    CMP.l !wt_stc+6
    BEQ .hit
+
    LDA.l $7E0000|!wt_stale2
    AND #$00FF
    BEQ +
    LDA.l !wt_stc+8
    TAX
    LDA.l $7E0000,X
    AND #$03FF
    CMP.l !wt_stc+10
    BEQ .hit
    LDA.l !wt_stc+12
    TAX
    LDA.l $7E0000,X
    AND #$03FF
    CMP.l !wt_stc+14
    BEQ .hit
+
    SEP #$20
    LDA.l $7E0000|!wt_stale
    BEQ +
    ORA #$80
    STA.l $7E0000|!wt_stale
+
    LDA.l $7E0000|!wt_stale2
    BEQ +
    ORA #$80
    STA.l $7E0000|!wt_stale2
+
    PLP
    CLC
    RTS
.hit
    PLP
    SEC
    RTS

; 게이트(M = 8). 필드에서 게이트 일이 길어 주사선이 !wt_late_line 에 닿았으면 게임의 창 타일맵 2KB 전송을 다음 NMI 로
; 미룬다(늦게 시작하면 아래쪽 줄이 VBlank 밖으로 밀려 화면에 가지 않는다). 한 번 미룬 것은 다시 미루지 않는다(bit3).
; 전투는 미룬 요청을 다시 보내지 않으므로 두지 않는다
WtLateDefer:
    LDA.l $000BEC
    BEQ +
    LDA.l $7E0000|!wq_defer
    AND #$08
    BNE +
    LDA.l $001945
    CMP #$89
    BNE ++
    LDA.l $001944
    CMP #$52
    BEQ +
++
    JSR WtLine
    CMP.w #!wt_late_line
    SEP #$20
    BCC +
    LDA.l $000BEC
    ORA.l $7E0000|!wq_defer
    STA.l $7E0000|!wq_defer
    LDA #$00
    STA.l $000BEC
+
    RTS

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
    ; 찾기는 VBlank 일이 끝난 뒤인 여기서 NMI 마다 한다(게이트에서 슬롯을 훑으면 게임의 창 타일맵 2KB DMA 가 VBlank 를
    ; 넘김). 전투에서는 부르지 않는다(전투 NMI 길이를 바꾸지 않게)
    LDA.l $001945
    CMP #$89
    BNE ++
    LDA.l $001944
    CMP #$52
    BEQ +
++
    PHX
    PHY
    JSR WtStaleFind
    ; 게임이 이 NMI 의 작업을 건너뛰어 아직 VBlank 안이면(주사선 225~!wt_restore_line) 여기서 바로 되돌린다. 가게 「누가」
    ; 미리보기 목록을 지운 뒤 게임이 몇 NMI 를 건너뛰는 동안 게이트가 돌지 않아 메시지 창에 이름이 남았다
    LDA.l $7E0000|!wt_stale
    ORA.l $7E0000|!wt_stale2
    BEQ +++
    PHP
    REP #$20
    JSR WtLine
    PLP
    CMP #$E1
    XBA
    BNE +++                 ; 256~
    XBA
    CMP #$E1
    BCC +++
    CMP.b #!wt_restore_line
    BCS +++
    JSR WtStaleGate
+++
    PLY
    PLX
+
    PLP
    LDA.b $1E
    STA.l $004200
    JML $00888A
; NMI 작업마다 건 자리에서 JSL(M = 8, X = 16, DB = 00). 우리 대기열·미룬 요청·게임의 창 타일맵 요청 가운데 하나라도
; 있으면 게이트를 부른다. 창 타일맵 요청만 있어도 부르는 것은 WtVis 가 그 전송 때의 버퍼를 재기 위해서다
; A 는 바꾸고 X·Y 는 지킨다. 게임 NMI 작업은 들어올 때의 X·Y 를 이어 쓴다.
WqNmiEntry:
    JSR WhWith
    LDA.l $7E0000|!wt_stale
    ORA.l $7E0000|!wt_stale2
    AND #$7F
    ORA.l $7E0000|!wq_count
    ORA.l $7E0000|!wq_defer
    ORA.l $000BEC
    BEQ +
    PHX
    PHY
    JSL WqNmiGate
    PLY
    PLX
+
    RTL

WqNmiFF9A:
    JSL WqNmiEntry
    JSL $11C8AC
    JML $00888F

; DB = 00(NMI)
WqNmiSlot:
    JSL WqNmiEntry
    LDX.w #$1400
    STX.w $2116
    RTL

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
    LDA.w !wt_vis,Y
    AND #$FE
    BRA ++
+
    LDA.w !wt_vis,Y
    ORA #$01
++
    STA.w !wt_vis,Y
    REP #$20
.next
    INX
    INX
    CPX.w #!wt_nslot*2
    BCC .slot
    ; 전용 칸 문구 자리도 같은 줄 거르기로 재, 그 자리가 더는 1D0~1FF 를 가리키지 않으면 지운다
    LDX #$000E
.fix
    LDA.w !wt_fixkeys,X
    BEQ .fixnext
    SEC
    SBC #$5000
    CMP #$0800
    BCS .fixgone
    TAY
    LDA.w !wq_head
    AND #$0080
    BNE .fixcheck
    TYA
    LSR
    LSR
    LSR
    LSR
    LSR
    LSR
    CMP #$0007
    BCC .fixcheck
    CMP #$0015
    BCC .fixnext
    CMP #$001E
    BCS .fixnext
.fixcheck
    LDA.w $5000,Y
    AND #$03FF
    CMP #$01D0
    BCS .fixnext
.fixgone
    STZ.w !wt_fixkeys,X
.fixnext
    DEX
    DEX
    BPL .fix
    JSR WhMsgWin
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

; 묶음 버퍼(7F:!wh_*): 마을·던전에서 캔버스 안 슬롯에 그린 그림은 게임이 그 창의 타일맵을 보내는 NMI 까지 올리지
; 않는다. 목록을 다 그린 뒤에야 타일맵을 보내는 창(가게 「누가」 미리보기 목록 열두 줄, 약 11프레임)을 그리는 동안 먼저
; 올리면 아직 화면에 남은 메시지 창이 그 칸을 보여 이름이 비쳤다. 자리는 7F:8300~ 로, 1장 이어 걷기·창 검사 장면에서
; CPU·DMA 가 읽지 않고 맵을 불러올 때 지우기(01:9937)만 썼다. 필드(세계 지도, $BE bit7 = 0)는 지도를 그 자리에 풀어
; 묶지 않는다. 켤 때·맵을 불러올 때 지워지므로 머리 낱말(!wh_magic)이 맞을 때만 읽는다. 항목 꼴은 대기열(!wq_buf)과 같다

; WtQueue 끝(NMI 꺼짐, DB = 7E, M = X = 16, X = 슬롯 × 2 보존). 방금 대기열 끝에 쓴 이 이름의 두 항목(8 + 열 × 24 바이트)을
; 묶음 버퍼로 옮기고 대기열에서 거둔다. 필드이거나 자리가 모자라면 그대로 둔다(원래처럼 바로 올라감)
WhStash:
    LDA.w $00BE
    AND #$0080
    BNE +
    RTS
+
    LDA.l !wh_magic
    CMP #!wh_magic_value
    BEQ +
    LDA #!wh_magic_value
    STA.l !wh_magic
    LDA #$0000
    STA.l !wh_count
    STA.l !wh_off
    STA.l !wh_rd
    STA.l !wh_go
+
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
    STA.w !wn_c             ; 이 이름의 바이트
    ; 화면에 메시지 창이 없고 버퍼의 메시지 창도 이 칸을 가리키지 않으면 묶지 않고 바로 올린다. 묶으면 창 타일맵이 먼저 뜨고
    ; 이름이 몇 NMI 뒤에 채워져, 메시지 창이 없는 도구 목록에서도 목록 줄이 그동안 비었다
    LDA.l !wh_msgwin
    BNE +
    JSR WhShown
    BCS +
    JMP .no
+
    ; 묶음에서는 평면 0 만 든 항목(위 줄)도 평면 1 = FF 를 끼운 두 평면 항목으로 늘려 둔다. 그래야 WhWith 가 항목마다 DMA
    ; 하나·같은 설정으로 보낸다(평면 따로 보내면 DMA 가 둘이라 VBlank 가 모자랐다). 크기는 항목 머리로 잰다
    JSR WhStashSize
    BCC +
    RTS
+
    STA.w !wt_tmp           ; 묶음에 쓸 바이트
    CLC
    ADC.l !wh_off
    CMP.w #!wh_size+1
    BCC +
    JMP .no
+
    JSR WhStashCopy
    LDA.l !wh_off
    CLC
    ADC.w !wt_tmp
    STA.l !wh_off
    LDA.l !wh_count
    CLC
    ADC #$0002
    STA.l !wh_count
    SEP #$20
    LDA.w !wq_count
    SEC
    SBC #$02
    STA.w !wq_count
    REP #$20
    RTS
; 자리가 모자라 이 이름은 대기열로 바로 올라간다. 같은 칸의 옛 그림이 묶여 있으면 나중에 새 그림을 덮으므로 VRAM 워드를
; $FFFF 로 바꿔 죽인다(WhNmi 가 건너뜀). NMI 가 꺼져 있어 NMI 안에서만 쓰는 !wq_left·!wq_head·!wq_len 을 빌린다
.no
    LDA.l !wh_count
    BNE +
    RTS
+
    PHX
    LDA.w !wq_off
    SEC
    SBC.w !wn_c
    TAX
    LDA.w !wq_buf,X
    STA.w !wq_left          ; 글자 줄 항목의 VRAM 워드
    LDA.w !wq_buf+2,X
    JSR WhEntLen
    STA.w !wq_len
    TXA
    CLC
    ADC.w !wq_len
    TAX
    LDA.w !wq_buf,X
    STA.w !wq_head          ; 위 줄 항목의 VRAM 워드
    LDA.l !wh_count
    STA.w !wq_len
    LDA.l !wh_rd
    TAX
-
    LDA.l !wh_buf,X
    CMP.w !wq_left
    BEQ +
    CMP.w !wq_head
    BNE ++
+
    LDA #$FFFF
    STA.l !wh_buf,X
++
    LDA.l !wh_buf+2,X
    JSR WhEntLen
    STA.l $7E0000|!wt_tmp
    TXA
    CLC
    ADC.l $7E0000|!wt_tmp
    TAX
    DEC.w !wq_len
    BNE -
    PLX
    RTS

; A = 항목 머리 둘째 낱말(낮은 바이트 = 방식, 높은 바이트 = 칸 수) → 항목 바이트 수(4 + 방식 0 이면 칸 × 16, 아니면 칸 × 8). M = 16
WhEntLen:
    PHA
    AND #$FF00
    LSR
    LSR
    LSR
    LSR
    LSR
    STA.l $7E0000|!wt_tmp
    PLA
    AND #$00FF
    BNE +
    LDA.l $7E0000|!wt_tmp
    ASL
    BRA ++
+
    LDA.l $7E0000|!wt_tmp
++
    CLC
    ADC #$0004
    RTS

; 게이트(M = 8). 게임이 이 NMI 에 창 타일맵을 보내면($0BEC) 그때까지 쌓인 항목을 다음 NMI 부터 보낸다(!wh_go). 그림을
; 타일맵보다 먼저 올리면 그 한 프레임 동안 메시지 창에 비쳤다. 창이 먼저 뜨면 묶은 이름 줄이 한두 프레임 늦게 채워질 뿐
; 메시지 창에는 비치지 않는다. 묶음과 창 타일맵을 한 NMI 에 함께 보내지 않는다. 전투에 들어가면 버린다
WhRelease:
    PHP
    PHB
    REP #$30
    PEA $7E7E
    PLB
    PLB
    LDA.l !wh_magic
    CMP #!wh_magic_value
    BNE .out
    LDA.l !wh_count
    BEQ .out
    LDA.w $1944
    CMP #$8952
    BNE +
    LDA #$0000
    STA.l !wh_count
    STA.l !wh_off
    STA.l !wh_rd
    STA.l !wh_go
    BRA .out
+
    LDA.l !wh_go
    BEQ .noxfer
    ; 창 타일맵과 같은 NMI 에 보내면 2KB 전송이 VBlank 를 넘긴다: 타일맵을 한 번 미루고 보낸다. 이미 한 번 미룬 타일맵이면
    ; 이번에는 타일맵을 보내고 묶음은 다음 NMI 에. 다시 미루고 묶음을 먼저 보내면, 보낼 수(!wh_go)에 든 이름 가운데 아직
    ; 화면에 뜨지 않은 창의 것이 옛 메시지 창에 비쳤다(팔기 목록 324프레임 11칸)
    LDA.l $000BEC
    AND #$00FF
    BEQ .send
    LDA.w !wq_defer
    AND #$0008
    BNE .noxfer
    SEP #$20
    LDA.l $000BEC
    ORA.w !wq_defer
    STA.w !wq_defer
    LDA #$00
    STA.l $000BEC
    REP #$20
.send
    JSR WhNmi
.noxfer
    LDA.l $000BEC
    AND #$00FF
    BEQ .out
    LDA.l !wh_count
    STA.l !wh_go
.out
    PLB
    PLP
    RTS


; 묶음 버퍼 항목을 !wh_go 개까지 차례로 보낸다(WqNmi 와 같은 방식, 원본 뱅크 7F). 주사선이 VBlank 밖이거나 끝 무렵이면 남긴다.
; M = X = 16, DB = 7E
WhNmi:
    LDA.l !wh_rd
    TAX
.entry
    JSR WtLine
    CMP #$00E1
    BCS +
    JMP .stop
+
    CMP #$0103
    BCC +
    JMP .stop
+
    LDA.l !wh_buf+2,X       ; 낮은 바이트 = 방식, 높은 바이트 = 칸 수
    STA.w !wq_head
    AND #$FF00
    LSR
    LSR
    LSR
    LSR
    LSR                     ; 칸 × 8
    STA.w !wq_len
    LDA.l !wh_buf,X
    CMP #$FFFF
    BNE +
    ; 넘침으로 죽인 항목(WhStash .no): 보내지 않고 넘어간다
    LDA.w !wq_head
    AND #$00FF
    BNE ++
    ASL.w !wq_len
++
    JMP .next
+
    STA.l $002116
    TXA
    CLC
    ADC.w #(!wh_buf&$FFFF)+4
    STA.l $004302
    SEP #$20
    LDA #$7F
    STA.l $004304
    LDA #$18
    STA.l $004301
    LDA.w !wq_head
    BNE .plane0
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
    LDA.l !wh_buf,X
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
    REP #$20
    TXA
    CLC
    ADC #$0004
    CLC
    ADC.w !wq_len
    TAX
    LDA.l !wh_go
    DEC
    STA.l !wh_go
    LDA.l !wh_count
    DEC
    STA.l !wh_count
    BEQ +
    LDA.l !wh_go
    BEQ .stop
    JMP .entry
+
    STA.l !wh_off
    STA.l !wh_rd
    STA.l !wh_go
    RTS
.stop
    TXA
    STA.l !wh_rd
    RTS

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
    LDA.w $1944
    CMP #$8952
    BEQ .battle
    ; 필드의 캔버스 밖 슬롯은 메시지가 덮지 않아 그대로 둔다
    LDA.l WtClassF,X
    AND #$0020
    BEQ +
    JMP .next
+
    STZ.w !wt_keys,X
    STZ.w !wt_ages,X
    ; 필드 캔버스 슬롯은 글자 줄과 위 줄이 떨어져 있다(WtSlotF·WtUpperF)
    LDA.l WtClassF,X
    AND #$000F
    JSR WqRunBytes
    STA.w !wq_left
    LDA.l WtUpperF,X
    BEQ .joined
    JSR WqCleanRun
    LDA.l WtSlotF,X
    JSR WqCleanRun
    BRA .next
.joined
    ASL.w !wq_left
    LDA.l WtSlotF,X
    JSR WqCleanRun
    BRA .next
.battle
    LDA.l WtClass,X
    AND #$0020
    BEQ +
    JMP .next
+
    STZ.w !wt_keys,X
    STZ.w !wt_ages,X
    LDA.l WtClass,X
    AND #$000F
    JSR WqRunBytes
    ASL
    STA.w !wq_left
    LDA.l WtSlot,X
    JSR WqCleanRun
.next
    INX
    INX
    CPX.w #!wt_nslot*2
    BCS .out
    JMP .slot
.out
    JSR WhUnmask
    SEP #$20
    PLB
    ; 원래 명령: PHB / PHK / PLB(DB = 00) / LDA #$7E
    PHB
    LDA #$00
    PHA
    PLB
    LDA #$7E
    JML $008EA3

; 등급(A: 0·1·2) → 한 줄(글자 줄 또는 위 줄)의 평면 1 바이트 수(열 4·7·10 × 8)
WqRunBytes:
    CMP #$0001
    BNE +
    LDA #$0038
    RTS
+
    CMP #$0002
    BNE +
    LDA #$0050
    RTS
+
    LDA #$0020
    RTS

; 필드에서 그림을 올린 캔버스 슬롯(!wt_dirty)의 창이 닫히면, 게임이 캔버스를 다시 보내기 전까지 메시지 창이 그 칸에 옛
; 이름을 보인다(가게 팔기 목록을 닫으며 「어느 물건을 팔아 주시겠어요?」 창을 다시 그릴 때). NMI 끝(WtVisTail, VBlank 일이
; 끝난 뒤)마다 WtVis 가 안 보인다고 잰 그런 슬롯을 둘까지
; !wt_stale·!wt_stale2 에 두고, 다음 NMI 첫머리(게이트, WtStaleGate)가 곧 보낼 버퍼에서 메시지 창이 그 칸을 가리키면 메시지 캔버스(7E:5800 평면 0, 평면 1 = FF)로 되돌리고
; 비운다. 게임이 그 NMI 작업을 건너뛰어 아직 VBlank 안이면 NMI 끝에서 바로 되돌린다. 보이는 슬롯은 건드리지 않는다.
; 메시지 창이 없으면 찾지 않는다(게이트가 재는 시간만큼 게임의 창 타일맵 전송이 밀림). M = 8 로 들어옴
WtStaleFind:
    PHB
    REP #$30
    PEA $7E7E
    PLB
    PLB
    ; 같은 슬롯을 다시 찾으면 bit7(지금 버퍼에선 메시지 창이 안 가리킴)을 잇는다
    SEP #$20
    LDA.w !wt_stale
    PHA
    LDA.w !wt_stale2
    PHA
    STZ.w !wt_stale
    STZ.w !wt_stale2
    REP #$20
    ; 1D0~1FF 슬롯(비트 12~14)은 캔버스 밖
    LDA.w !wt_dirty
    AND #$8FFF
    ORA.w !wt_dirty+2
    BNE +
    JMP .out
+
    ; 메시지 창 왼쪽(2열)·오른쪽(29열) 테두리(타일 08E)가 18~26줄 어디에도 없으면 후보를 두지 않는다(게이트가 매 NMI
    ; 슬롯을 재는 시간만큼 게임의 창 타일맵 2KB 전송이 밀림). 메시지 창이 없으면 창이 닫혀도 드러날 칸이 없다
    LDX.w #(18*32+2)*2
-
    LDA.w $5000,X
    AND #$03FF
    CMP #$008E
    BEQ .msg
    LDA.w $5000+(27*2),X
    AND #$03FF
    CMP #$008E
    BEQ .msg
    TXA
    CLC
    ADC #$0040
    TAX
    CPX.w #(27*32+2)*2
    BCC -
    JMP .out
.msg
    LDX.w #!wt_nkana*2
.slot
    JSR WtStalePre
    BCC .next
    TXA
    INC
    SEP #$20
    PHA                     ; 1,S = 새 값, 2,S = 옛 stale2, 3,S = 옛 stale
    LDA $03,S
    AND #$7F
    CMP $01,S
    BNE +
    LDA $03,S
    STA $01,S
    BRA ++
+
    LDA $02,S
    AND #$7F
    CMP $01,S
    BNE ++
    LDA $02,S
    STA $01,S
++
    LDA.w !wt_stale
    BEQ +
    PLA
    STA.w !wt_stale2
    REP #$20
    TXA
    ASL
    ASL
    ASL
    TAX
    LDA.l WtMsgCellF,X
    STA.l !wt_stc+8
    LDA.l WtMsgCellF+2,X
    STA.l !wt_stc+10
    LDA.l WtMsgCellF+8,X
    STA.l !wt_stc+12
    LDA.l WtMsgCellF+10,X
    STA.l !wt_stc+14
    JMP .out
+
    PLA
    STA.w !wt_stale
    REP #$20
    PHX
    TXA
    ASL
    ASL
    ASL
    TAX
    LDA.l WtMsgCellF,X
    STA.l !wt_stc
    LDA.l WtMsgCellF+2,X
    STA.l !wt_stc+2
    LDA.l WtMsgCellF+8,X
    STA.l !wt_stc+4
    LDA.l WtMsgCellF+10,X
    STA.l !wt_stc+6
    PLX
.next
    INX
    INX
    CPX.w #!wt_nslot*2
    BCS .out
    JMP .slot
.out
    PLA                     ; 옛 stale·stale2
    PLB
    RTS


; 슬롯 X 가 그림을 올린 캔버스 안 슬롯이고 WtVis 가 안 보인다고 쟀으면 C = 1(M = 16, DB = 7E). 찾기의 후보
WtStalePre:
    LDA.l WtBitLo,X
    AND.w !wt_dirty
    BNE +
    LDA.l WtBitHi,X
    AND.w !wt_dirty+2
    BEQ .no
+
    LDA.l WtClassF,X
    AND #$0020
    BNE .no
    LDA.w !wt_ages,X
    BEQ .no
    TXA
    LSR
    TAY
    LDA.w !wt_vis,Y
    AND #$0001
    BNE .no
    SEC
    RTS
.no
    CLC
    RTS

; 게이트(VBlank 첫머리, M = 8). !wt_stale·!wt_stale2 의 슬롯마다 메시지 창이 그 칸을 가리키면 되돌린다. 그사이 다시
; 그렸으면(보임 bit0) 두고, 게임이 캔버스를 보내 WqClean 이 이미 비웠으면(!wt_dirty 비트 꺼짐) 둔다. 이 NMI 에 게임이
; 캔버스를 보내면($0F59) 하지 않는다(WqClean 이 비움). 주사선 !wt_restore_line 앞에서만 되돌린다. 늦어진 창 타일맵은
; 부르는 쪽(WtLateDefer)이 미룬다. 우리 대기열보다 먼저 보내므로 같은 슬롯에 새로 그린 그림이 뒤에 덮는다
WtStaleGate:
    PHP
    PHB
    REP #$30
    PEA $7E7E
    PLB
    PLB
    LDA.w $1944
    CMP #$8952
    BNE +
    ; 전투에서는 찾기가 돌지 않아 들어오기 전 필드의 후보가 남는다. 지워 두어야 전투 NMI 마다 들르지 않는다
    SEP #$20
    STZ.w !wt_stale
    STZ.w !wt_stale2
    BRA .out
+
    LDA.w $0F59
    AND #$00FF
    BNE .out
    LDY.w #!wt_stale
    LDX.w #0
    JSR .one
    LDY.w #!wt_stale2
    LDX.w #8
    JSR .one
.out
    PLB
    PLP
    RTS
; Y = 후보 바이트 자리. 켤 때 남은 값이면 슬롯 번호가 아닐 수 있어 캔버스 슬롯(짝수 × 2, 가나 항목 뒤)만 본다.
; bit7 = 지금 버퍼에선 메시지 창이 그 칸을 가리키지 않음. 게임이 버퍼를 다시 보내기($0BEC) 전까지 화면은 그대로라 다시 재지 않는다
.one
    LDA.w $0000,Y
    AND #$00FF
    BEQ .skip
    BIT #$0080
    BEQ +
    LDA.l $000BEC
    AND #$00FF
    BEQ .skip
+
    ; 창 타일맵을 보내는 NMI 에 도는 자리라 찾기가 적어 둔 칸 둘만 비교한다(슬롯 검증은 맞을 때만)
    LDA.l !wt_stc,X
    PHX
    TAX
    LDA.w $0000,X
    PLX
    AND #$03FF
    CMP.l !wt_stc+2,X
    BEQ .hit
    LDA.l !wt_stc+4,X
    PHX
    TAX
    LDA.w $0000,X
    PLX
    AND #$03FF
    CMP.l !wt_stc+6,X
    BEQ .hit
    SEP #$20
    LDA.w $0000,Y
    ORA #$80
    STA.w $0000,Y
    REP #$20
    RTS
.hit
    LDA.w $0000,Y
    AND #$007F
    DEC
    TAX
    CPX.w #!wt_nkana*2
    BCC .drop
    CPX.w #!wt_nslot*2
    BCS .drop
    TXA
    LSR
    BCS .drop
    PHY
    TAY
    LDA.w !wt_vis,Y
    PLY
    AND #$0001
    BNE .drop
    JSR WtLine
    CMP #$00E1
    BCC .skip
    CMP.w #!wt_restore_line
    BCS .skip
    PHY
    JSR WtRestoreSlot
    PLY
.drop
    SEP #$20
    LDA #$00
    STA.w $0000,Y
    REP #$20
.skip
    RTS

; 지금 주사선(A, M = 16). WqNmi 와 같은 순서로 V 카운터를 읽는다($4201 bit7 은 게임이 부팅 때 켬)
WtLine:
    SEP #$20
    LDA.l $00213F
    LDA.l $002137
    LDA.l $00213D
    XBA
    LDA.l $00213D
    AND #$01
    XBA
    REP #$20
    RTS

; 슬롯 X 의 그림을 메시지 캔버스로 되돌리고 비운다(M = 16, DB = 7E)
WtRestoreSlot:
    JSR WhUnmask
    LDA.l WtBitLo,X
    EOR #$FFFF
    AND.w !wt_dirty
    STA.w !wt_dirty
    LDA.l WtBitHi,X
    EOR #$FFFF
    AND.w !wt_dirty+2
    STA.w !wt_dirty+2
    STZ.w !wt_keys,X
    STZ.w !wt_ages,X
    LDA.l WtClassF,X
    AND #$000F
    JSR WqRunBytes
    STA.w !wq_left
    LDA.l WtUpperF,X
    BEQ .joined
    JSR WqRestoreRun
    LDA.l WtSlotF,X
    JMP WqRestoreRun
.joined
    ASL.w !wq_left
    LDA.l WtSlotF,X
    JMP WqRestoreRun

; 칸 A 부터 !wq_left 바이트: 평면 0 은 메시지 캔버스 버퍼(7E:5800, 칸 096 부터 8바이트씩)에서, 평면 1 은 FF. X 는 그대로
WqRestoreRun:
    PHA
    ASL
    ASL
    ASL
    CLC
    ADC #$1000
    STA.l $002116
    LDA $01,S
    SEC
    SBC #$0096
    ASL
    ASL
    ASL
    CLC
    ADC #$5800
    STA.l $004302
    LDA.w !wq_left
    STA.l $004305
    SEP #$20
    LDA #$7E
    STA.l $004304
    LDA #$00
    STA.l $002115
    STA.l $004300
    LDA #$18
    STA.l $004301
    LDA #$01
    STA.l $00420B
    REP #$20
    PLA
    JMP WqCleanRun

; 칸 A 부터 !wq_left 바이트만큼 평면 1 을 FF 로(DMA 0, 고정 원본). X 는 그대로
WqCleanRun:
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
    RTS

; 타일맵: 글자 줄은 빌린 칸, 위 줄은 !wt_ubase. 높은 바이트는 우선·팔레트만 살리고, 색($ED)이 있으면 글자 줄에 쓴다.
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
    ORA.w !wt_ubase
    CLC
    ADC.w !wn_k
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

; 묶음 버퍼 보조 코드. 창 이름 코드 자리(60:C000~DFFF)가 차서 코드 넘침 검사 자리(E000~E0FF) 뒤, 가나 표(E800~) 앞에 둔다.
; 같은 뱅크라 JSR 로 부른다
pushpc
org !wh_extra
; NMI 첫머리(WqNmiEntry, M = 8, X·Y 보존). WhReq 가 켜 두었으면(!wq_defer bit5) 게임이 요청한 창 타일맵 2KB 를 여기서 먼저
; 보내고, 남은 VBlank 에 WhReq 가 짠 묶음 그림 DMA 와 가림을 이어 보낸다. 타일맵과 그림이 한 NMI 에 가므로 창이 뜬 프레임에
; 이름이 함께 보이고(빈칸 없음) 옛 타일맵이 새 그림을 보이는 프레임도 없다(비침 없음). 화면 239줄 모드라 VBlank 는 주사선
; 240~261 이고, 게임의 2KB 전송은 게이트 일 뒤에 시작해 VBlank 끝까지 차므로 그 뒤로는 남지 않는다. 그래서 게이트보다 앞에서
; 보내고, 화면 밖 30·31줄 128바이트는 보내지 않는다(게임의 위·아래 줄 전송도 29줄까지). 게임 전송 뒤의 일(00:8840, NMI 전송
; 목록 고르기)도 대신 한다. 그림 DMA·가림은 칸마다 주사선을 보고 늦으면 남긴다(남은 그림은 WhNmi 가 다음 NMI 부터 보냄)
WhWith:
    LDA.l $7E0000|!wq_defer
    BIT #$20
    BNE +
    RTS
+
    PHP
    PHB
    PHD
    PHX
    PHY
    REP #$30
    PEA $7F7F
    PLB
    PLB
    ; 세계 지도로 바뀌었으면 7F 를 게임이 쓰므로 손대지 않는다
    LDA.l $0000BE
    AND #$0080
    BEQ .drop
    ; 요청: 이 NMI 의 게임 요청($80) 또는 한 NMI 붙잡아 둔 요청(!wh_pend)
    LDA.l $000BEC
    AND #$00FF
    CMP #$0080
    BEQ +
    LDA.w !wh_pend&$FFFF
    BEQ .drop
+
    LDA.w !wh_rd&$FFFF
    CMP.w !wh_snap&$FFFF
    BNE .give
    LDA.w !wh_count&$FFFF
    CMP.w !wh_snapn&$FFFF
    BNE .give
    LDA.l $7E0000|!wq_count
    ORA.l $000F59
    AND #$00FF
    BNE .wait
    JSR WtLine
    CMP #$00E1
    BCC .wait
    CMP.w #!wh_with_line
    BCC .go
.wait
    ; 대기열·캔버스 전송과 겹치거나 NMI 가 늦었으면 게임 요청을 한 NMI 붙잡고(화면은 옛 타일맵 그대로) 다음 NMI 에 다시
    ; 한다. 그냥 넘기면 짠 표를 잃고 게임 타일맵만 먼저 가 목록 줄이 빈다. 두 번째도 안 되면 놓는다
    LDA.w !wh_pend&$FFFF
    BNE .give
    INC.w !wh_pend&$FFFF
    SEP #$20
    LDA #$00
    STA.l $000BEC
    BRA .out
.give
    ; 표를 버리고 게임이 보내게 한다(붙잡아 둔 요청이면 되돌림). 묶음은 예전처럼 다음 NMI 부터
    LDA.w !wh_pend&$FFFF
    BEQ .drop
    SEP #$20
    LDA #$80
    STA.l $000BEC
.drop
    REP #$20
    STZ.w !wh_pend&$FFFF
    SEP #$20
    LDA.l $7E0000|!wq_defer
    AND #$DF
    STA.l $7E0000|!wq_defer
.out
    REP #$30
    PLY
    PLX
    PLD
    PLB
    PLP
    RTS
.go
    PEA $4300
    PLD
    LDA.l $7E1ABC
    EOR #$001C
    AND #$00FC
    XBA
    STA.l $002116
    LDA #$1801
    STA.b $00
    LDA #$5000
    STA.b $02
    LDA #$0780              ; 0~29줄
    STA.b $05
    SEP #$20
    LDA #$80
    STA.l $002115
    LDA #$7E
    STA.b $04
    LDA #$01
    STA.l $00420B
    LDA #$7F                ; 묶음 그림: 같은 설정(VRAM 워드씩, 2118·2119)에 원본 뱅크만 7F
    STA.b $04
    REP #$20
    LDX #$0000
.dma
    LDA.w !wh_dma&$FFFF,X
    BMI .mask
    JSR WtLine
    CMP.w #!wh_dma_line
    BCS .mask
    LDA.w !wh_dma&$FFFF,X
    STA.l $002116
    LDA.w (!wh_dma&$FFFF)+2,X
    STA.b $02
    LDA.w (!wh_dma&$FFFF)+4,X
    STA.b $05
    SEP #$20
    LDA #$01
    STA.l $00420B
    REP #$20
    ; 보낸 항목은 묶음에서 죽인다(VRAM 워드 FFFF, WhNmi 가 건너뜀). 앞에서부터 이어 죽은 것은 NMI 끝 WhTrim 이 걷는다
    LDY.w (!wh_dma&$FFFF)+6,X
    LDA #$FFFF
    STA.w !wh_buf&$FFFF,Y
    TXA
    CLC
    ADC #$0008
    TAX
    BRA .dma
.mask
    ; 가림: 메시지 창이 살아 있는 슬롯 칸을 가리키는 타일맵 자리를 빈 바탕 칸(001)으로. 버퍼는 그대로 둔다
    STZ.w !wh_maskthis&$FFFF
    LDX #$0000
.mgroup
    LDA.w !wh_mask&$FFFF,X
    BMI .done
    JSR WtLine
    CMP.w #!wh_mask_line
    BCS .done
    LDY #$0002
.mone
    LDA.w !wh_mask&$FFFF,X
    BMI .done
    STA.l $002116
    LDA.w (!wh_mask&$FFFF)+2,X
    STA.l $002118
    INC.w !wh_maskthis&$FFFF
    INX
    INX
    INX
    INX
    DEY
    BNE .mone
    BRA .mgroup
.done
    ; 이 NMI 의 요청과 미룬 요청(bit7·6)·켬(bit5)을 지운다(같은 버퍼를 방금 보냄). 가림을 썼으면 bit2
    LDA.w !wh_maskthis&$FFFF
    SEP #$20
    BEQ +
    LDA.l $7E0000|!wq_defer
    ORA #$04
    BRA ++
+
    LDA.l $7E0000|!wq_defer
    AND #$FB
++
    AND #$1F
    STA.l $7E0000|!wq_defer
    LDA #$00
    STA.l $000BEC
    LDA.l $7E0000|!wt_xfer
    ORA #$80
    STA.l $7E0000|!wt_xfer
    LDA.l $001821
    CMP #$07
    REP #$20
    BEQ +
    LDA #$8CEF
    BRA ++
+
    LDA #$8D84
++
    STA.l $001946
    STZ.w !wh_pend&$FFFF
    ; 남은 묶음 항목도 방금 보낸 타일맵의 것이므로 다음 NMI 부터 보내게 한다(게임 요청을 지워 WhRelease 가 정하지 못함)
    LDA.w !wh_count&$FFFF
    STA.w !wh_go&$FFFF
    BRL .out

; 가린 슬롯을 되돌렸으면(WtRestoreSlot·WqClean) 화면 타일맵이 버퍼와 다르게 001 을 가리키고 있으므로, 다음 NMI 에 버퍼를
; 다시 보내게 한다(!wq_defer bit7 = 미룬 요청). 게임이 더 요청하지 않아도 메시지 글자가 가려진 채 남지 않게
WhUnmask:
    PHP
    SEP #$20
    LDA.l $7E0000|!wq_defer
    BIT #$04
    BEQ +
    AND #$FB
    ORA #$80
    STA.l $7E0000|!wq_defer
+
    PLP
    RTS

; 04:9D39(게임이 창 타일맵 2KB 전송을 요청하는 LDA #$0080 / STA $0BEC(9D3C) 자리, M = X = 16, NMI 켜짐). 원래 두 명령을
; 하기 전에, 지금 버퍼로 다음 NMI 의 WhWith 가 할 일을 짠다. 요청 뒤 게임은 바로 NMI 를 기다리므로 버퍼가 그대로다. 표를 다
; 짠 뒤에만 bit5 를 켜므로 그사이 NMI 가 와도 반쯤 짠 표를 쓰지 않는다. 그사이 NMI 가 묶음을 보냈으면 !wh_snap 이 달라
; WhWith 가 쉰다
;  - 묶음 그림: 예산(!wh_budget)까지. 메시지 창이 가리키는 항목(함께 보내면 메시지 창에 비침)은 건너뛰고 뒤를 계속 본다.
;    건너뛴 항목과 같은 VRAM 워드의 뒤 항목은 보내지 않는다(나중에 옛 그림이 새 그림을 덮지 않게)
;  - 가림: 그림을 올린 캔버스 슬롯 칸을 메시지 창이 가리키는 자리. 창이 아래 줄부터 닫히며(두 줄씩) 메시지 창 줄이 드러날 때,
;    아직 보이는 같은 슬롯의 이름이 메시지 창에도 보였다. 슬롯 키 자리(이름이 보이는 곳)는 빼고
WhReq:
    PHP
    PHB
    PHX
    PHY
    REP #$30
    SEP #$20
    LDA.l $7E0000|!wq_defer
    AND #$DF
    STA.l $7E0000|!wq_defer
    REP #$20
    ; 세계 지도(필드 $BE bit7 = 0)에서는 게임이 7F 를 쓰므로 건드리지 않는다
    LDA.l $0000BE
    AND #$0080
    BNE +
    JMP .out
+
    LDA.l !wh_magic
    CMP #!wh_magic_value
    BEQ +
    JMP .out
+
    LDA.l $001944
    CMP #$8952
    BNE +
    JMP .out
+
    LDA.l $7E21BF
    AND #$0020
    BEQ +
    JMP .out
+
    PEA $7F7F
    PLB
    PLB
    ; !wh_pend 는 지우지 않는다. 게임이 매 NMI 다시 요청하는 창에서 지우면, 늦은 NMI 가 이어질 때 타일맵을 끝없이 붙잡았다
    LDA #$FFFF
    STA.w !wh_dma&$FFFF
    STA.w !wh_mask&$FFFF
    LDA.w !wh_rd&$FFFF
    STA.w !wh_snap&$FFFF
    LDA.w !wh_count&$FFFF
    STA.w !wh_snapn&$FFFF
    LDA.w #!wh_budget
    STA.w !wh_tmpb&$FFFF    ; 남은 예산
    JSR WhReqMask
    STZ.w !wh_tmpr&$FFFF
    STZ.w !wh_tmpq&$FFFF
    LDA.w !wh_count&$FFFF
    BNE +
    JMP .done
+
    STA.w !wh_tmpn&$FFFF    ; 남은 항목
    LDY #$0000
    LDA.w !wh_rd&$FFFF
    TAX
.entry
    ; 묶음 항목은 모두 두 평면(방식 0)이다(WhStash). 아니면 멈춘다
    LDA.w (!wh_buf&$FFFF)+2,X
    BIT #$00FF
    BEQ +
    JMP .done
+
    AND #$FF00
    LSR
    LSR
    LSR
    LSR                     ; 칸 × 16
    STA.w !wh_tmpl&$FFFF
    LDA.w !wh_buf&$FFFF,X
    CMP #$FFFF
    BEQ .next
    JSR WhEntShown
    BCS .skipit
    JSR WhSkipped
    BCS .next
    LDA.w !wh_tmpr&$FFFF
    CMP.w #!wh_ndma
    BCS .done
    LDA.w !wh_tmpb&$FFFF
    SEC
    SBC.w !wh_tmpl&$FFFF
    BCC .done
    SBC.w #!wh_dma_cost
    BCC .done
    STA.w !wh_tmpb&$FFFF
    LDA.w !wh_buf&$FFFF,X
    STA.w !wh_dma&$FFFF,Y
    TXA
    STA.w (!wh_dma&$FFFF)+6,Y
    CLC
    ADC.w #(!wh_buf&$FFFF)+4
    STA.w (!wh_dma&$FFFF)+2,Y
    LDA.w !wh_tmpl&$FFFF
    STA.w (!wh_dma&$FFFF)+4,Y
    TYA
    CLC
    ADC #$0008
    TAY
    LDA #$FFFF
    STA.w !wh_dma&$FFFF,Y
    INC.w !wh_tmpr&$FFFF
    BRA .next
.skipit
    LDA.w !wh_tmpq&$FFFF
    CMP #$0008
    BCS .done
    PHY
    ASL
    TAY
    LDA.w !wh_buf&$FFFF,X
    STA.w !wh_skip&$FFFF,Y
    PLY
    INC.w !wh_tmpq&$FFFF
.next
    TXA
    CLC
    ADC #$0004
    CLC
    ADC.w !wh_tmpl&$FFFF
    TAX
    DEC.w !wh_tmpn&$FFFF
    BEQ .done
    JMP .entry
.done
    ; 할 일이 있으면 다음 NMI 첫머리의 WhWith 를 켠다(!wq_defer bit5)
    LDA.w !wh_dma&$FFFF
    BPL +
    LDA.w !wh_mask&$FFFF
    BMI .out
+
    SEP #$20
    LDA.l $7E0000|!wq_defer
    ORA #$20
    STA.l $7E0000|!wq_defer
.out
    REP #$30
    PLY
    PLX
    PLB
    PLP
    LDA #$0080
    STA.l $000BEC
    RTL

; WhReq 안(DB = 7F, X = 항목 자리). 이 항목의 VRAM 워드가 앞에서 건너뛴 항목과 같으면 C = 1. X·Y 를 지킨다
WhSkipped:
    PHY
    LDA.w !wh_tmpq&$FFFF
    ASL
    TAY
-
    DEY
    DEY
    BMI +
    LDA.w !wh_skip&$FFFF,Y
    CMP.w !wh_buf&$FFFF,X
    BNE -
    PLY
    SEC
    RTS
+
    PLY
    CLC
    RTS

; NMI 끝(WhMsgWin 안, M = X = 16, DB = 7E). WhWith 가 보내고 죽인 항목이 묶음 앞에 이어 있으면 걷어 낸다(!wh_rd 를 넘기고
; 항목 수·보내도 되는 수를 줄임). 비면 머리를 처음으로
WhTrim:
    LDA.l !wh_magic
    CMP #!wh_magic_value
    BNE .out
.loop
    LDA.l !wh_count
    BEQ .empty
    LDA.l !wh_rd
    TAX
    LDA.l !wh_buf,X
    CMP #$FFFF
    BNE .out
    LDA.l !wh_buf+2,X
    PHA
    AND #$FF00
    LSR
    LSR
    LSR
    LSR
    LSR                     ; 칸 × 8
    STA.w !wq_len
    PLA
    AND #$00FF
    BNE +
    ASL.w !wq_len
+
    TXA
    CLC
    ADC #$0004
    CLC
    ADC.w !wq_len
    STA.l !wh_rd
    LDA.l !wh_count
    DEC
    STA.l !wh_count
    LDA.l !wh_go
    BEQ .loop
    DEC
    STA.l !wh_go
    BRA .loop
.empty
    STA.l !wh_off
    STA.l !wh_rd
    STA.l !wh_go
.out
    RTS

; WhReq 안(M = X = 16, DB = 7F). 그림을 올린 캔버스 슬롯마다 칸(글자 줄·위 줄)을 메시지 창이 가리키는 버퍼 자리를 찾아
; !wh_mask 에 [타일맵 VRAM 워드][(원래 값 & FC00) | 001] 로 적고, 그만큼 !wh_tmpb(예산)를 줄인다. 슬롯 키 두 줄(그 슬롯
; 이름이 보이는 자리)은 뺀다
WhReqMask:
    LDA.l $7E1ABC
    EOR #$001C
    AND #$00FC
    XBA
    STA.w !wh_tmpv&$FFFF    ; 타일맵 VRAM 기준 워드
    STZ.w !wh_tmpm&$FFFF    ; 가림 표 자리
    LDX.w #!wt_nkana*2
.slot
    LDA.l WtBitLo,X
    AND.l $7E0000|!wt_dirty
    BNE +
    LDA.l WtBitHi,X
    AND.l $7E0000|!wt_dirty+2
    BEQ .next
+
    LDA.l $7E0000|!wt_ages,X
    BEQ .next
    JSR WhShown
    BCC .next
    STX.w !wh_tmpx&$FFFF
    LDA.l $7E0000|!wt_keys,X
    STA.w !wh_tmpk&$FFFF
    LDA.l WtClassF,X
    AND #$0003
    ASL
    TAX
    LDA.l WhColsOf,X
    STA.w !wh_tmpc&$FFFF    ; 열 수
    ASL
    STA.w !wh_tmpd&$FFFF    ; 열 × 2(키 줄의 바이트)
    LDX.w !wh_tmpx&$FFFF
    LDA.l WtSlotF,X
    JSR .run
    LDX.w !wh_tmpx&$FFFF
    LDA.l WtUpperF,X
    BEQ +
    JSR .run
+
    LDX.w !wh_tmpx&$FFFF
.next
    INX
    INX
    CPX.w #!wt_nslot*2
    BCC .slot
    RTS
; A = 첫 칸, !wh_tmpc 칸. 칸마다 메시지 창 자리가 그 칸이고 키 두 줄 밖이면 가림 표에 더한다
.run
    STA.w !wh_tmpt&$FFFF
    LDA.w !wh_tmpc&$FFFF
    STA.w !wh_tmpi&$FFFF
.cell
    LDA.w !wh_tmpt&$FFFF
    SEC
    SBC #$0096
    BCC .rnext
    CMP #$00EA
    BCS .rnext
    JSR WhCellOf
    TAX
    LDA.l $7E0000,X
    AND #$03FF
    CMP.w !wh_tmpt&$FFFF
    BNE .rnext
    ; 칸 자리 − 키 를 부호 없이 견준다. 키 앞쪽 칸이면 뺄셈이 FFxx 로 돌아 「열 × 2 이상」 이 되어 범위 밖으로 친다.
    ; 64 를 더하면 키 한 줄 위(위 줄)에서부터 잰 거리가 된다
    TXA
    SEC
    SBC.w !wh_tmpk&$FFFF
    CMP.w !wh_tmpd&$FFFF
    BCC .rnext
    CLC
    ADC #$0040
    CMP.w !wh_tmpd&$FFFF
    BCC .rnext
    LDA.w !wh_tmpm&$FFFF
    CMP.w #!wh_nmask*4
    BCS .rnext
    LDA.w !wh_tmpb&$FFFF
    SEC
    SBC.w #!wh_mask_cost
    BCC .rnext
    STA.w !wh_tmpb&$FFFF
    LDY.w !wh_tmpm&$FFFF
    TXA
    SEC
    SBC #$5000
    LSR
    CLC
    ADC.w !wh_tmpv&$FFFF
    STA.w !wh_mask&$FFFF,Y
    LDA.l $7E0000,X
    AND #$FC00
    ORA #$0001
    STA.w (!wh_mask&$FFFF)+2,Y
    INY
    INY
    INY
    INY
    STY.w !wh_tmpm&$FFFF
    LDA #$FFFF
    STA.w !wh_mask&$FFFF,Y
.rnext
    INC.w !wh_tmpt&$FFFF
    DEC.w !wh_tmpi&$FFFF
    BNE .cell
    RTS

WhColsOf:
    dw 4, 7, 10, 0

; WtAlloc 안(M = X = 16, DB = 7E, X = 슬롯 × 2). 같은 자리를 다른 크기로 다시 그림: 옛 슬롯은 비운다. 다만 화면에 보이는
; 슬롯(WtVis bit0)은 새 창 타일맵이 갈 때까지 옛 타일맵이 그 칸을 가리키므로 남겨 두고, 다음 창 타일맵 전송(2KB·위아래 줄
; 모두 WtVis 가 잼)에서 안 보인다고 잰 뒤에 비우게 한다. 바로 비우면 가게 목록을 다시 그릴 때 화면의 이름이 빈 슬롯의 칸이
; 되어 다른 문구가 먼저 차지할 수 있었다. 남긴 슬롯은 나이를 새로 매겨, 빈 슬롯이 없을 때 고르는 「가장 오래된 슬롯」 이
; 아직 보이는 이 슬롯을 덮지 않게 한다
WtResize:
    PHX
    TXA
    LSR
    TAX
    LDA.w !wt_vis,X
    PLX
    AND #$0001
    BNE +
    STZ.w !wt_keys,X
    STZ.w !wt_ages,X
    RTS
+
    LDA.w !wt_age
    STA.w !wt_ages,X
    RTS

; WhStash 안(NMI 꺼짐, DB = 7E, M = X = 16). 대기열 끝 이 이름의 두 항목을 머리로 재, 묶음에 쓸 바이트(평면 0 만 든
; 항목은 두 배)를 A 로 준다. 두 항목의 대기열 바이트가 !wn_c(열 수로 셈)와 다르면 C = 1(묶지 않음: 크기를 잘못 알면 묶음을
; 넘기거나 대기열을 잘못 거둠). X·Y 를 지킨다
WhStashSize:
    PHX
    LDA #$0000
    PHA                     ; 5,S = 묶음 바이트
    PHA                     ; 3,S = 대기열 바이트
    LDA #$0002
    PHA                     ; 1,S = 남은 항목
    LDA.w !wq_off
    SEC
    SBC.w !wn_c
    TAX
-
    LDA.w !wq_buf+2,X
    AND #$FF00
    LSR
    LSR
    LSR
    LSR
    LSR                     ; 칸 × 8
    STA.w !wt_tmp
    LDA.w !wq_buf+2,X
    AND #$00FF
    BNE +
    ASL.w !wt_tmp           ; 두 평면: 칸 × 16, 그대로 옮김
    LDA.w !wt_tmp
    BRA ++
+
    LDA.w !wt_tmp           ; 평면 0 만: 칸 × 8, 묶음에서는 두 배
    ASL
++
    CLC
    ADC #$0004
    CLC
    ADC $05,S
    STA $05,S
    LDA.w !wt_tmp
    CLC
    ADC #$0004
    PHA
    CLC
    ADC $05,S
    STA $05,S
    TXA
    CLC
    ADC $01,S
    TAX
    PLA
    LDA $01,S
    DEC
    STA $01,S
    BNE -
    PLA
    PLA
    CMP.w !wn_c
    BEQ +
    PLA
    PLX
    SEC
    RTS
+
    PLA
    PLX
    CLC
    RTS

; WhStash 안(NMI 꺼짐, DB = 7E, M = X = 16). 대기열 끝의 이 이름 두 항목(!wn_c 바이트)을 대기열에서 거두고 묶음 버퍼
; 끝(!wh_off)에 옮긴다. 평면 0 만 든 항목은 평면 1 = FF 를 끼운 두 평면 항목으로 늘린다. X·Y 를 지킨다
WhStashCopy:
    PHX
    PHY
    PHB
    PEA $7F7F
    PLB
    PLB
    LDA.l $7E0000|!wq_off
    SEC
    SBC.l $7E0000|!wn_c
    STA.l $7E0000|!wq_off
    CLC
    ADC.w #!wq_buf
    TAX
    LDA.w !wh_off&$FFFF
    CLC
    ADC.w #!wh_buf&$FFFF
    TAY
    LDA #$0002
    STA.l $7E0000|!wn_t0
.ent
    LDA.l $7E0002,X
    AND #$00FF
    BNE .exp
    LDA.l $7E0002,X
    AND #$FF00
    LSR
    LSR
    LSR
    LSR                     ; 칸 × 16
    CLC
    ADC #$0003              ; 머리 4바이트 − 1
    db $54,$7F,$7E          ; MVN 7E → 7F
    BRA .nx
.exp
    LDA.l $7E0000,X
    STA.w $0000,Y
    LDA.l $7E0002,X
    AND #$FF00
    STA.w $0002,Y
    LSR
    LSR
    LSR
    LSR
    LSR                     ; 칸 × 8
    STA.l $7E0000|!wn_k
    INX
    INX
    INX
    INX
    INY
    INY
    INY
    INY
-
    SEP #$20
    LDA.l $7E0000,X
    STA.w $0000,Y
    LDA #$FF
    STA.w $0001,Y
    REP #$20
    INX
    INY
    INY
    LDA.l $7E0000|!wn_k
    DEC
    STA.l $7E0000|!wn_k
    BNE -
.nx
    LDA.l $7E0000|!wn_t0
    DEC
    STA.l $7E0000|!wn_t0
    BNE .ent
    PLB
    PLY
    PLX
    RTS

; 묶음 항목 X(바이트 자리)의 첫 칸·끝 칸 가운데 하나라도 버퍼의 메시지 창이 가리키면 C = 1. 죽인 항목은 C = 0(M = X = 16)
WhEntShown:
    LDA.l !wh_buf,X
    CMP #$FFFF
    BEQ .no
    SEC
    SBC #$1000
    LSR
    LSR
    LSR
    PHA
    JSR WhTileShown
    PLA
    BCS .yes
    STA.l !wh_tmpe
    LDA.l !wh_buf+2,X
    XBA
    AND #$00FF
    DEC
    CLC
    ADC.l !wh_tmpe
    JMP WhTileShown
.yes
    SEC
    RTS
.no
    CLC
    RTS

; A = BG3 칸. 캔버스 칸(096~17F)이고 버퍼 7E:5000 의 메시지 창 자리(WhCellOf)가 그 칸이면 C = 1. A·X 를 지킨다(M = X = 16)
WhTileShown:
    CMP #$0096
    BCC .no
    CMP #$0180
    BCS .no
    PHA
    PHX
    SEC
    SBC #$0096
    JSR WhCellOf
    TAX
    LDA.l $7E0000,X
    PLX
    AND #$03FF
    CMP $01,S
    BEQ +
    PLA
    CLC
    RTS
+
    PLA
    SEC
    RTS
.no
    CLC
    RTS

; A = 캔버스 안 차례(칸 − 096, 0~233) → 메시지 창(화면 18~26줄·3~28열, 한 줄 26칸)이 그 칸을 가리키는 7E:5000 버퍼 자리.
; 본 흐름(WhReq)에서만 부르므로 표 대신 26 을 빼 가며 줄을 센다(코드 자리가 모자람). M = X = 16, X 를 지킨다
WhCellOf:
    PHX
    LDX.w #$5000+(18*32+3)*2
-
    CMP.w #26
    BCC +
    SBC.w #26
    PHA
    TXA
    CLC
    ADC #$0040
    TAX
    PLA
    BRA -
+
    ASL
    PHA
    TXA
    CLC
    ADC $01,S
    PLX
    PLX
    RTS

; 슬롯 X(× 2)의 글자 줄·위 줄 첫·끝 칸 가운데 하나라도 버퍼의 메시지 창이 가리키면 C = 1(WtMsgCellF). X 를 지킨다(M = X = 16, 본 흐름에서만)
WhShown:
    PHX
    TXA
    ASL
    ASL
    ASL
    TAX
    LDA.l WtMsgCellF,X
    BEQ .no
    LDA #$0004
    STA.l !wh_tmps
-
    LDA.l WtMsgCellF,X
    PHX
    TAX
    LDA.l $7E0000,X
    PLX
    AND #$03FF
    CMP.l WtMsgCellF+2,X
    BEQ .yes
    INX
    INX
    INX
    INX
    LDA.l !wh_tmps
    DEC
    STA.l !wh_tmps
    BNE -
.no
    PLX
    CLC
    RTS
.yes
    PLX
    SEC
    RTS

; WtVis 끝(M = X = 16, DB = 7E, !wq_head = 보낸 줄 $C0). 보낸 버퍼의 18~26줄 한 줄에 메시지 창 테두리(2열과 29열 08E)가 있으면
; !wh_msgwin 을 1 로. 2KB 를 다 보냈는데 없으면 0. 위·아래 줄만 보냈으면 없다고 내리지 않는다. 묶음 버퍼를 쓰는 필드에서만.
; 머리 낱말(!wh_magic)과 상관없이 쓴다. 맵을 불러오면 7F 가 지워져 0(창 없음)이 되고, 창은 타일맵을 보내야 뜨므로
; 그 뒤 첫 전송부터 맞는 값이다
WhMsgWin:
    LDA.w $00BE
    AND #$0080
    BNE +
    RTS
+
    LDA.w $1944
    CMP #$8952
    BNE +
    RTS
+
    JSR WhTrim
    ; 이 전송이 WhWith 의 가림 없이 갔는데 화면에 가림이 남았으면(bit2): 2KB 였으면 다 덮였고, 위·아래 줄만이었으면
    ; 덮이지 않은 18~20줄 가림이 남을 수 있어 2KB 를 다시 요청한다(bit7)
    LDA.l !wh_maskthis
    BNE +
    SEP #$20
    LDA.w !wq_defer
    BIT #$04
    BEQ ++
    AND #$FB
    BIT.w !wq_head          ; bit7 = 2KB 를 보냄
    BMI +++
    ORA #$80
+++
    STA.w !wq_defer
++
    REP #$20
+
    LDA #$0000
    STA.l !wh_maskthis
    ; 왼쪽(2열)과 오른쪽(29열) 테두리가 같은 줄에 함께 있어야 메시지 창이다. 2열에서 시작하는 다른 창(상태 창 등)도 같은
    ; 테두리 칸을 써, 한쪽만 보면 메시지 창이 없는 화면에서도 이름을 묶어 목록 줄이 몇 프레임 비었다
    LDX.w #(18*32+2)*2
-
    LDA.w $5000,X
    AND #$03FF
    CMP #$008E
    BNE +
    LDA.w $5000+(27*2),X
    AND #$03FF
    CMP #$008E
    BEQ .yes
+
    TXA
    CLC
    ADC #$0040
    TAX
    CPX.w #(27*32+2)*2
    BCC -
    LDA.w !wq_head
    AND #$0080
    BEQ .out
    LDA #$0000
    STA.l !wh_msgwin
    RTS
.yes
    LDA #$0001
    STA.l !wh_msgwin
.out
    RTS
assert pc() <= !wn_kana_table
pullpc
