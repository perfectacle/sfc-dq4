-- SLOT 인물의 셀 좌표(7E:3020/3080+슬롯)가 바뀔 때마다 프레임과 함께 track.txt 에 쓴다. 입력은 boot.lua 와 같음.
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local L = require("lib")
local n, last, t = 0, nil, {}
local m = emu.memType.snesMemory
local slot = tonumber(os.getenv("SLOT"), 16)
local maxf = tonumber(os.getenv("MAXF") or "1500")
emu.addEventCallback(function()
  n = n + 1
  local s = string.format("%02X/%02X (%d,%d)", emu.read(0x7E00BC, m), emu.read(0x7E00BD, m),
    emu.read(0x7E3020 + slot, m), emu.read(0x7E3080 + slot, m))
  if s ~= last then t[#t + 1] = string.format("f%05d %s", n, s); last = s end
  if n == maxf - 1 then L.write("track.txt", table.concat(t, "\n") .. "\n") end
end, emu.eventType.endFrame)
dofile(os.getenv("LIBDIR") .. "/boot.lua")
