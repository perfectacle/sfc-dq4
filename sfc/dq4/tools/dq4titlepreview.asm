lorom

org $008000
Reset:
  sei
  clc
  xce
  rep #$38
  ldx #$1FFF
  txs
  lda #$0000
  tcd
  sep #$20
  pha
  plb
  stz $4200
  stz $420C
  stz $420D
  lda #$FF
  sta $4201
  lda #$80
  sta $2100
  stz $2101
  stz $2102
  stz $2103
  stz $2106
  stz $2108
  stz $2109
  stz $210A
  stz $210B
  stz $210C
  stz $2123
  stz $2124
  stz $2125
  stz $212A
  stz $212B
  stz $212D
  stz $212E
  stz $212F
  stz $2130
  stz $2131
  stz $2133
  lda #$E0
  sta $2132
  stz $210D
  stz $210D
  ; The first visible scanline is 1; -1 displays source row 0 at the top.
  lda #$FF
  sta $210E
  sta $210E
  lda #$01
  sta $2105
  sta $212C
  lda #$40
  sta $2107
  lda #$80
  sta $2115
  ldx #$0000
  stx $2116
  lda #$01
  sta $4300
  lda #$18
  sta $4301
  ldx #$8000
  stx $4302
  lda #$01
  sta $4304
  ldx #!chr_size
  stx $4305
  lda #$01
  sta $420B
  ldx #$4000
  stx $2116
  ldx #$9000
  stx $4302
  stz $4304
  ldx #$0800
  stx $4305
  lda #$01
  sta $420B
  stz $2121
  stz $4300
  lda #$22
  sta $4301
  ldx #$9800
  stx $4302
  ldx #$0100
  stx $4305
  lda #$01
  sta $420B
  lda #$0F
  sta $2100
Forever:
  bra Forever
Interrupt:
  rti

org $009000
incbin "title.map"
org $009800
incbin "title.pal"
org $00FFC0
db "DQ4 KO TITLE PREVIEW "
db $20,$00,$06,$00,$01,$00,$00
dw $FFFF,$0000
org $00FFE4
dw Interrupt,Interrupt,Interrupt,Interrupt,Interrupt,Interrupt
org $00FFF4
dw Interrupt,Interrupt,Interrupt,Interrupt,Reset,Interrupt
org $018000
incbin "title.chr"
