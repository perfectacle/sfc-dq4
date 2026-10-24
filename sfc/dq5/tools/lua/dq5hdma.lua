-- DUMPF(쉼표 목록) 프레임 끝에 HDMA 켬($420C 에 마지막으로 쓴 값)과 DMA 채널 0~7 레지스터($43x0~$43xA),
-- WRAM 128KB, 화면을 h/w/s<프레임> 으로 저장한다. boot.lua(보통 walk.lua) 뒤에 붙여 쓴다.
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local L = require("lib")
local f = 0
local dumpf = {}
for a in string.gmatch(os.getenv("DUMPF") or "", "[^,]+") do dumpf[tonumber(a)] = true end
local hdmaen = 0
emu.addMemoryCallback(function(addr, value) hdmaen = value end, emu.callbackType.write, 0x420C, 0x420C)
emu.addEventCallback(function()
  f = f + 1
  if dumpf[f] then
    local t = {string.format("420C=%02X", hdmaen)}
    for ch = 0, 7 do
      local b = 0x4300 + ch * 16
      local r = {}
      for i = 0, 10 do r[#r + 1] = string.format("%02X", emu.read(b + i, emu.memType.snesMemory)) end
      t[#t + 1] = string.format("ch%d %s", ch, table.concat(r, " "))
    end
    L.write(string.format("h%05d.txt", f), table.concat(t, "\n") .. "\n")
    L.dump(string.format("w%05d.bin", f), emu.memType.snesWorkRam, 0x20000)
    L.shot(string.format("s%05d.png", f))
  end
end, emu.eventType.endFrame)
dofile(os.getenv("LIBDIR") .. "/boot.lua")
