-- DQ5 부팅 시험의 장면 단계(dq5boottest.py --scenes 가 부름): 드라이버(LIBDIR/boot.lua = dq5warp.lua)로 장면을 돌리며
-- SHOTS 프레임마다 VRAM·CGRAM·OAM·WRAM 해시와 맵 번호·$BE 를 scene.txt 에 이어 쓰고 화면(fNNNNN.png)을 남긴다.
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local L = require("lib")
local shots = {}
for f in string.gmatch(os.getenv("SHOTS") or "", "%d+") do shots[tonumber(f)] = true end
local m = emu.memType.snesMemory
local function adler(t)
  local a, b = 1, 0
  for i = 0, emu.getMemorySize(t) - 1 do a = (a + emu.read(i, t)) % 65521; b = (b + a) % 65521 end
  return string.format("%04X%04X", b, a)
end
local n, log = 0, {}
emu.addEventCallback(function()
  n = n + 1
  if shots[n] then
    log[#log + 1] = string.format("f%05d map=%02X/%02X BE=%02X vram=%s cgram=%s oam=%s wram=%s", n, emu.read(0x7E00BC, m),
      emu.read(0x7E00BD, m), emu.read(0x7E00BE, m), adler(emu.memType.snesVideoRam), adler(emu.memType.snesCgRam),
      adler(emu.memType.snesSpriteRam), adler(emu.memType.snesWorkRam))
    L.write("scene.txt", table.concat(log, "\n") .. "\n")
    L.shot(string.format("f%05d.png", n))
  end
end, emu.eventType.endFrame)
dofile(os.getenv("LIBDIR") .. "/boot.lua")
