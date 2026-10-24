-- MesenCE 가 NES 색 번호 00~3F 를 어떤 RGB 로 그리는지 화면에서 잰다.
-- 세이브스테이트를 불러온 뒤 프레임마다 nametable 을 빈 타일로 채우고 OAM 을 화면 밖으로 치운 다음,
-- 프레임 시작(startFrame, 게임의 NMI 가 팔레트를 쓴 뒤)에 BG 팔레트 색 0 을 색 번호 c 로 바꾸고 네 프레임째 끝에 화면을 찍는다.
-- 환경 변수: STATE(세이브스테이트), SHOT_DIR. 결과는 SHOT_DIR/pal-XX.png 64장.
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local L = require("lib")
L.loadState(os.getenv("STATE"))
local pal, nt, oam = emu.memType.nesPaletteRam, emu.memType.nesNametableRam, emu.memType.nesSpriteRam
local n, c = 0, -1
local function blank()
  for i = 0, 0x7FF do if i % 0x400 < 0x3C0 then emu.write(i, 0, nt) end end
  for i = 0, 255, 4 do emu.write(i, 0xF8, oam) end
end
emu.addEventCallback(function()
  if c >= 0 then
    blank()
    for i = 0, 0x1F, 4 do emu.write(i, c, pal) end
  end
end, emu.eventType.startFrame)
emu.addEventCallback(function()
  n = n + 1
  if n < 10 then return end
  -- 화면 덤프는 한두 프레임 늦게 바뀌므로 색마다 4프레임을 두고 마지막 프레임에 찍는다.
  local phase = (n - 10) % 4
  if c >= 0 and phase == 3 then L.shot(string.format("pal-%02X.png", c)) end
  if phase == 3 or c < 0 then c = c + 1 end
  if c > 0x3F then emu.stop(0) end
end, emu.eventType.endFrame)
