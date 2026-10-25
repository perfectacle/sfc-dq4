lorom

org $03FDFB
  jml Title
  nop

; The menu's native music command is moved to the opening, without restarting it.
org $00A70C
  nop #3

org $308000
Title:
  php
  phb
  rep #$30
  pha
  phx
  phy
  lda $33
  pha
  lda #$FFFF
  sta $33
  sep #$20
  lda #$00
  pha
  plb
  jsl $009556
  lda #$10
  jsl $24FE9A
  jsl $24FE44
  lda #$01
  sta $2105
  sta $212C
  sta $212E
  stz $212D
  stz $2133
  lda #$24
  sta $210B
  lda #$78
  sta $2107
  stz $210D
  stz $210D
  lda #$FF
  sta $210E
  sta $210E
  lda #$03
  sta $2123
  lda #$7F
  sta $2126
  lda #$80
  sta $2127
  sta $2115
  ldx #$4000
  stx $2116
  lda #$01
  sta $4300
  lda #$18
  sta $4301
  ldx #$8000
  stx $4302
  lda #$31
  sta $4304
  ldx #!chr_size
  stx $4305
  lda #$01
  sta $420B
  ldx #$7800
  stx $2116
  ldx #$8000
  stx $4302
  lda #$32
  sta $4304
  ldx #$0800
  stx $4305
  lda #$01
  sta $420B
  ldx #$8800
  jsr Palette
  stz $1D
  ldy #$0000
  ldx #$0000

Frame:
  jsl $009506
  cpy #$0020
  bcs .open
  tya
  asl
  asl
  pha
  clc
  adc #$80
  sta $2127
  pla
  eor #$FF
  clc
  adc #$80
  sta $2126
  bra .brightness
.open:
  stz $2123
  stz $212E
.brightness:
  cpy #$0040
  bcs .full
  tya
  lsr
  lsr
  sta $1D
  bra .input
.full:
  lda #$0F
  sta $1D
  jsr Gleam
.input:
  cpy #$0040
  bcc .next
  rep #$20
  lda $0748
  and #$1080
  sep #$20
  bne .pressed
  ldx #$0001
  bra .next
.pressed:
  cpx #$0001
  beq FadeOut
.next:
  iny
  cpy #$0400
  bcc Frame
  ldy #$0200
  bra Frame

FadeOut:
  ldy #$000F
.level:
  tya
  sta $1D
  jsl $009506
  jsl $009506
  dey
  bpl .level
.release:
  jsl $009506
  rep #$20
  lda $0748
  and #$1080
  sep #$20
  bne .release
  jsl $009556
  ; The original menu's palette copy was never modified by the title.
  stz $2121
  stz $4300
  lda #$22
  sta $4301
  ldx #$3914
  stx $4302
  lda #$7E
  sta $4304
  ldx #$0100
  stx $4305
  lda #$01
  sta $420B
  lda #$09
  sta $2105
  sta $2107
  lda #$22
  sta $210B
  stz $210D
  stz $210D
  stz $210E
  stz $210E
  stz $2123
  stz $2126
  stz $2127
  lda #$13
  sta $212E
  lda #$17
  sta $212C
  sta $212D
  lda #$04
  sta $2133
  stz $1D
  stz $2100
  rep #$30
  pla
  sta $33
  ply
  plx
  pla
  plb
  plp
  jml $03FE5C

Gleam:
  phx
  rep #$20
  tya
  and #$01FF
  cmp #$00A0
  bcc .done
  cmp #$00C0
  bcs .done
  sec
  sbc #$00A0
  xba
  clc
  adc #$A000
  tax
  sep #$20
  jsr Palette
.done:
  sep #$20
  plx
  rts

Palette:
  phx
  stz $2121
  stz $4300
  lda #$22
  sta $4301
  stx $4302
  lda #$32
  sta $4304
  ldx #$0100
  stx $4305
  lda #$01
  sta $420B
  plx
  rts

assert pc() <= $309000
print "title_entry=",hex(Title)
print "title_frame=",hex(Frame)
print "title_exit=",hex(FadeOut)

org $318000
incbin "title.chr"
org $328000
incbin "title.map"
org $328800
incbin "title.pal"
org $32A000
incbin "gleam.pal"
