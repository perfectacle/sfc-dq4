-- 0F:$D259(필드 좌표 → 타일) 를 부를 때 X·Y 와 돌려준 A, 필드 번호 $65 를 lk.txt 에 기록한다(MAXF-1 프레임).
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local L = require("lib")
local log, xs, ys = {}, 0, 0
emu.addMemoryCallback(function() local s = emu.getState(); xs, ys = s["cpu.x"], s["cpu.y"] end, emu.callbackType.exec, 0xD259, 0xD259)
emu.addMemoryCallback(function()
  if #log < 5000 then log[#log + 1] = string.format("%02X %02X %02X %02X", xs, ys, emu.getState()["cpu.a"], emu.read(0x65, L.mem)) end
end, emu.callbackType.exec, 0xD269, 0xD269)
local n = 0
emu.addEventCallback(function() n = n + 1; if n == tonumber(os.getenv("MAXF")) - 1 then L.write("lk.txt", table.concat(log, "\n")) end end, emu.eventType.endFrame)
L.drive()
