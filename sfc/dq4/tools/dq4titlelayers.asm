lorom

macro Upload(bank, source, count, destination)
  lda.b #$80
  sta $2115
  ldx.w #<destination>
  stx $2116
  lda.b #$01
  sta $4300
  lda.b #$18
  sta $4301
  ldx.w #<source>
  stx $4302
  lda.b #<bank>
  sta $4304
  ldx.w #<count>
  stx $4305
  lda.b #$01
  sta $420B
endmacro

org $03FDFB
  jml Title
  nop
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
  lda.w #$FFFF
  sta $33
  sep #$20
  lda.b #$00
  pha
  plb
  jsl $009556
  stz $420C
  lda.b #$10
  jsl $24FE9A
  jsl $24FE44
  lda.b #$03
  sta $2105
  sta $210B
  lda.b #$13
  sta $212C
  stz $212D
  stz $212E
  stz $2123
  stz $2133
  lda.b #$A3
  sta $2101
  lda.b #$2C
  sta $2107
  lda.b #$25
  sta $2108
  stz $210D
  stz $210D
  lda.b #$FF
  sta $210E
  sta $210E
  %Upload($31, $8000, !background_chr_size, $0000)
  %Upload($32, $8000, !foreground_chr_size, $3000)
  %Upload($31, $D000, $1000, $2400)
  %Upload($31, $E000, $0800, $2C00)
  %Upload($34, $8000, $4000, $6000)
  stz $2121
  stz $4300
  lda.b #$22
  sta $4301
  ldx.w #$E800
  stx $4302
  lda.b #$31
  sta $4304
  ldx.w #$0100
  stx $4305
  lda.b #$01
  sta $420B
  lda.b #$80
  sta $2121
  ldx.w #$E900
  stx $4302
  ldx.w #$0020
  stx $4305
  lda.b #$01
  sta $420B
  stz $1D
  ldy.w #$0000
  ldx.w #$0000
Frame:
  jsl $009506
  jsr Motion
  cpy.w #$0040
  bcs .full
  tya
  lsr
  lsr
  sta $1D
  bra .next
.full:
  lda.b #$0F
  sta $1D
  rep #$20
  lda $0748
  and.w #$1080
  sep #$20
  bne .pressed
  ldx.w #$0001
  bra .next
.pressed:
  cpx.w #$0001
  beq FadeOut
.next:
  iny
  cpy.w #$0800
  bcc Frame
  ldy.w #$0400
  bra Frame

FadeOut:
  ldx.w #$000F
.level:
  txa
  sta $1D
  jsl $009506
  jsr Motion
  iny
  jsl $009506
  jsr Motion
  iny
  dex
  bpl .level
.release:
  jsl $009506
  jsr Motion
  iny
  rep #$20
  lda $0748
  and.w #$1080
  sep #$20
  bne .release
  stz $420C
  jsl $009556
  ; Native menu setup expects cleared VRAM and an empty object palette.
  lda.b #$80
  sta $2115
  ldx.w #$0000
  stx $2116
  stx $4305
  lda.b #$09
  sta $4300
  lda.b #$18
  sta $4301
  ldx.w #TitleZero
  stx $4302
  lda.b #$30
  sta $4304
  lda.b #$01
  sta $420B
  stz $2121
  lda.b #$08
  sta $4300
  lda.b #$22
  sta $4301
  ldx.w #$0200
  stx $4305
  lda.b #$01
  sta $420B
  jsl $02F9E3
  stz $2121
  stz $4300
  lda.b #$22
  sta $4301
  ldx.w #$3914
  stx $4302
  lda.b #$7E
  sta $4304
  ldx.w #$0100
  stx $4305
  lda.b #$01
  sta $420B
  lda.b #$09
  sta $2105
  sta $2107
  stz $2108
  lda.b #$22
  sta $210B
  lda.b #$03
  sta $2101
  stz $210D
  stz $210D
  stz $210E
  stz $210E
  stz $210F
  stz $210F
  stz $2110
  stz $2110
  stz $2123
  stz $2126
  stz $2127
  lda.b #$13
  sta $212E
  lda.b #$17
  sta $212C
  sta $212D
  lda.b #$04
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

Motion:
  phx
  lda.b #$80
  sta $2115
  lda.b #$01
  sta $4300
  lda.b #$18
  sta $4301
  rep #$20
  tya
  and.w #$007F
  xba
  tax
.next:
  lda.l $338004,x
  beq .oam
  sta $4305
  lda.l $338000,x
  sta $2116
  lda.l $338002,x
  sta $4302
  sep #$20
  lda.l $338006,x
  sta $4304
  lda.b #$01
  sta $420B
  rep #$20
  txa
  clc
  adc.w #$0008
  tax
  bra .next
.oam:
  tya
  and.w #$007F
  asl
  asl
  tax
  lda.l $31EB00,x
  sta $4302
  sep #$20
  lda.l $31EB02,x
  sta $4304
  stz $4300
  lda.b #$04
  sta $4301
  stz $2102
  stz $2103
  ldx.w #$0220
  stx $4305
  lda.b #$01
  sta $420B
  ; Two horizontal cloud bands share a periodic tilemap, with independent speeds.
  lda.b #$FF
  sta $2110
  sta $2110
  lda.b #$02
  sta $4360
  lda.b #$0F
  sta $4361
  lda.b #$35
  sta $4364
  rep #$20
  tya
  and.w #$03FF
  asl
  asl
  asl
  asl
  ora.w #$8000
  sta $4362
  sep #$20
  lda.b #$40
  sta $420C
  plx
  rts

TitleZero:
  db $00
assert pc() <= $309000
print "title_entry=",hex(Title)
print "title_frame=",hex(Frame)
print "title_exit=",hex(FadeOut)
print "title_motion=",hex(Motion)

org $318000
incbin "background.chr"
assert pc() <= $31C800
org $31D000
incbin "background.map"
org $31E000
incbin "foreground.map"
org $31E800
incbin "background.pal"
org $31E900
incbin "dragon.pal"
org $31EB00
incbin "oam-pointers.bin"
org $328000
incbin "foreground.chr"
assert pc() <= $32E000
org $338000
incbin "dragon-dma.bin"
org $348000
incbin "dragon-initial.chr"
org $358000
!cloud_frame = 0
while !cloud_frame < 1024
  db $7F
  dw ((!cloud_frame>>2)&$FF)
  db $41
  dw ((!cloud_frame>>2)&$FF)
  db $20
  dw ((!cloud_frame>>3)&$7F)
  db $00,$00,$00,$00,$00,$00,$00
  !cloud_frame #= !cloud_frame+1
endwhile
assert pc() == $35C000
org $368000
check bankcross off
incbin "layer-payload.bin"
check bankcross full
