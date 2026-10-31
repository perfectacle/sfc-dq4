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
  lda.b #$63
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
  ldx.w #$00A0
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
  jsl MenuInit
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
  rep #$20
  tya
  lsr
  lsr
  and.w #$00FF
  xba
  lsr
  ora.w #$8000
  sta $4302
  sep #$20
  lda.b #$35
  sta $4304
  lda.b #$1E
  sta $2102
  stz $2103
  ldx.w #$0024
  stx $4305
  lda.b #$01
  sta $420B
  stz $2102
  lda.b #$01
  sta $2103
  ldx.w #$0020
  stx $4305
  lda.b #$01
  sta $420B
  stz $420C
  rep #$20
  tya
  lsr
  lsr
  lsr
  and.w #$007F
  sep #$20
  sta $210F
  stz $210F
  lda.b #$FF
  sta $2110
  sta $2110
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
org $31E920
incbin "cloud.pal"

org $31E9A0
MenuFadeTail = 17
; Same work as the native menu setup 02:F9E3, minus its frame waits. That routine fills
; 7E:A007 from the run-length table at 1E:D7E3 and waits a frame after every fill run
; (27 waits), then clears VRAM 4000-5FFF in eight 2-frame steps. The screen is already
; force-blanked here, so the waits only kept the menu black for about 44 frames.
; Channel 7 and the direct-page scratch ($00, $09, $CE) match the native routine.
MenuInit:
  phb
  stz $2115
  lda.b #$1E
  sta $4374
  pha
  plb
  lda.b #$07
  sta $2181
  lda.b #$A0
  sta $2182
  stz $2183
  lda.b #$80
  sta $4371
  ldx.w #$D7E3
  stx $09
  ldx.w #$0000
  stx $00
.run:
  lda ($09)
  stz $4376
  bmi .fill
  inc a
  sta $4375
  rep #$20
  and.w #$00FF
  pha
  clc
  adc $00
  sta $00
  pla
  ldx $09
  inx
  stx $4372
  sec
  adc $09
  sta $09
  sep #$20
  stz $4370
  lda.b #$80
  sta $420B
  bra .run
.fill:
  cmp.b #$80
  beq .filled
  and.b #$7F
  inc a
  sta $4375
  rep #$20
  and.w #$00FF
  clc
  adc $00
  sta $00
  sep #$20
  ldx $09
  inx
  stx $4372
  inx
  stx $09
  lda.b #$08
  sta $4370
  lda.b #$80
  sta $420B
  bra .run
.filled:
  phk
  plb
  ldx.w #$FFFF
  stx $1F0E
  ldx.w #$000F
  lda.b #$00
.state:
  sta $1F10,x
  dex
  bpl .state
  ldx.w #$1C00
  stx $1F18
  ldx.w #$0001
  stx $1F1A
  ldx.w #$4008
  stx $1F1E
  ldx.w #$0005
  stx $1F20
  ldx.w #$0000
  stx $1C93
  stz $00
  stz $01
  stz $CE
  lda.b #$60
  sta $CF
  lda.b #$80
  sta $2115
  ldx.w #$4000
  stx $2116
  lda.b #$09
  sta $4370
  lda.b #$18
  sta $4371
  stz $4372
  stz $4373
  stz $4374
  stz $4377
  ldx.w #$4000
  stx $4375
  lda.b #$80
  sta $420B
  lda.b #$24
  sta $210C
  ldx.w #$003F
.windows:
  stz $1C33,x
  dex
  bpl .windows
  lda.b #$7E
  pha
  plb
  ldx.w #$0002
.palette:
  lda.l $02FAD0,x
  sta $3914,x
  inx
  cpx.w #$0008
  bcc .palette
  jsl $04FAB3
  ; The overture fade from FadeOut's start runs about 56 frames, and the menu song load
  ; silences the SPC at once. Wait out the fade's tail so it still ends on its own.
  lda.b #MenuFadeTail
.tail:
  pha
  jsl $009506
  pla
  dec a
  bne .tail
  plb
  rtl
assert pc() <= $31EB00
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
incbin "cloud-oam.bin"
assert pc() == $360000
org $368000
incbin "layer-payload.bin"
assert pc() <= $370000
