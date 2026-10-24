-- boot.lua 와 같은 입력으로 부팅하고 FROM~TO 프레임 동안 LO~HI 에서 실행된 PC 와 그때의 P(플래그)를 모은다.
-- cover.txt 한 줄: "PC P 횟수". P 의 M·X 비트로 명령 길이를 정확히 디스어셈블할 수 있다(tools/listing.py).
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local L = require("lib")
local from, to = tonumber(os.getenv("FROM")), tonumber(os.getenv("TO"))
local lo, hi = tonumber(os.getenv("LO"), 16), tonumber(os.getenv("HI"), 16)
local n, st, cb = 0, {}, nil
local function onExec(addr)
  local p = emu.getState()["cpu.ps"] & 0x30
  local k = addr * 256 + p
  st[k] = (st[k] or 0) + 1
end
emu.addEventCallback(function()
  n = n + 1
  if n == from then cb = emu.addMemoryCallback(onExec, emu.callbackType.exec, lo, hi) end
  if n == to then
    emu.removeMemoryCallback(cb, emu.callbackType.exec, lo, hi)
    local t = {}
    for k, c in pairs(st) do t[#t + 1] = string.format("%06X %02X %d", k // 256, k % 256, c) end
    table.sort(t)
    L.write("cover.txt", table.concat(t, "\n") .. "\n")
  end
end, emu.eventType.endFrame)
dofile(os.getenv("LIBDIR") .. "/boot.lua")
