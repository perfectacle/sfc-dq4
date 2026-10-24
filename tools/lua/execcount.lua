-- EXEC="02AE55,03D4B5" 의 각 PC 가 실행된 횟수를 맵별로 세어 exec.txt 에 쓴다. 입력은 boot.lua 와 같음.
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local L = require("lib")
local n, cnt, order = 0, {}, {}
local m = emu.memType.snesMemory
for a in string.gmatch(os.getenv("EXEC"), "(%x+)") do
  local pc = tonumber(a, 16)
  emu.addMemoryCallback(function()
    local key = string.format("%06X map %02X/%02X", pc, emu.read(0x7E00BC, m), emu.read(0x7E00BD, m))
    if not cnt[key] then cnt[key] = {0, n}; order[#order + 1] = key end
    cnt[key][1] = cnt[key][1] + 1
  end, emu.callbackType.exec, pc, pc)
end
local maxf = tonumber(os.getenv("MAXF") or "1500")
emu.addEventCallback(function()
  n = n + 1
  if n == maxf - 1 then
    local t = {"frames " .. n}
    for _, k in ipairs(order) do t[#t + 1] = string.format("%s n=%d first=%d", k, cnt[k][1], cnt[k][2]) end
    L.write("exec.txt", table.concat(t, "\n") .. "\n")
  end
end, emu.eventType.endFrame)
dofile(os.getenv("LIBDIR") .. "/boot.lua")
