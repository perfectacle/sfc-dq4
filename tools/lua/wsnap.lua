-- boot.lua 와 같은 입력으로 부팅하면서 FROM 프레임부터 STEP 프레임마다 WRAM 128KB·CGRAM·화면을 덤프한다.
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local L = require("lib")
local from = tonumber(os.getenv("FROM") or "0")
local step = tonumber(os.getenv("STEP") or "30")
local n = 0
emu.addEventCallback(function()
  n = n + 1
  if n >= from and (n - from) % step == 0 then
    L.dump(string.format("w%05d.bin", n), emu.memType.snesWorkRam, 0x20000)
    L.dump(string.format("c%05d.bin", n), emu.memType.snesCgRam, 0x200)
    L.shot(string.format("s%05d.png", n))
  end
end, emu.eventType.endFrame)
dofile(os.getenv("LIBDIR") .. "/boot.lua")
