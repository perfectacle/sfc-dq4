-- DQ5 부팅 시험: 전원을 켜 A 를 PERIOD 프레임마다 누르며 새 게임 첫 장면(배 선실 17/00)까지 간다.
-- SHOTS 프레임마다 VRAM·CGRAM·OAM·WRAM 해시(boot.txt)와 화면(fNNNNN.png), CHECKAT 프레임에 맵 번호·21A1.
-- 화면 PNG 는 실행마다 한 프레임 앞뒤가 섞여 찍히므로 견주는 것은 메모리 해시다. dq5boottest.py 가 부른다.
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local L = require("lib")
local maxf = tonumber(os.getenv("MAXF") or "6600")
local period = tonumber(os.getenv("PERIOD") or "40")
local tapUntil = tonumber(os.getenv("TAPUNTIL") or "6600")
local checkAt = tonumber(os.getenv("CHECKAT") or "6500")
local shots = {}
for f in string.gmatch(os.getenv("SHOTS") or "600,1200,1800,2400,3000,3600,4200,4800,5400,6000,6500", "%d+") do shots[tonumber(f)] = true end
local m = emu.memType.snesMemory
local function adler(t)
  local a, b = 1, 0
  for i = 0, emu.getMemorySize(t) - 1 do a = (a + emu.read(i, t)) % 65521; b = (b + a) % 65521 end
  return string.format("%04X%04X", b, a)
end
local n = 0
local log = {}
emu.addEventCallback(function()
  n = n + 1
  L.release()
  if n < tapUntil and n % period < 4 then L.press({a = true}) end
  if shots[n] then
    log[#log + 1] = string.format("f%05d vram=%s cgram=%s oam=%s wram=%s", n, adler(emu.memType.snesVideoRam),
      adler(emu.memType.snesCgRam), adler(emu.memType.snesSpriteRam), adler(emu.memType.snesWorkRam))
    L.shot(string.format("f%05d.png", n))
  end
  if n == checkAt then
    log[#log + 1] = string.format("f%05d map %02X/%02X 21A1=%02X", n, emu.read(0x7E00BC, m), emu.read(0x7E00BD, m), emu.read(0x7E21A1, m))
  end
  if n >= maxf then L.write("boot.txt", table.concat(log, "\n") .. "\n"); emu.stop(0) end
end, emu.eventType.endFrame)
