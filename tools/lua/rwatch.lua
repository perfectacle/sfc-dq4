-- boot.lua 와 같은 입력으로 부팅하면서 WATCH 범위("18E171-18E179,...")를 읽는 PC 를
-- 범위·PC 별로 처음 프레임과 횟수만 모아 rwatch.txt 에 쓴다. FROM 프레임 전의 읽기는 무시한다.
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local L = require("lib")
local n, seen, order = 0, {}, {}
local from = tonumber(os.getenv("FROM") or "0")
for a, b in string.gmatch(os.getenv("WATCH"), "(%x+)-(%x+)") do
  local lo, hi = tonumber(a, 16), tonumber(b, 16)
  emu.addMemoryCallback(function(addr, value)
    if n < from then return end
    local s = emu.getState()
    local pc = (s["cpu.k"] << 16) | s["cpu.pc"]
    local key = string.format("%06X-%06X pc=%06X", lo, hi, pc)
    local e = seen[key]
    if not e then
      e = {first = n, count = 0, sample = string.format("addr=%06X val=%02X", addr, value)}
      seen[key] = e; order[#order + 1] = key
    end
    e.count = e.count + 1
  end, emu.callbackType.read, lo, hi)
end
local maxf = tonumber(os.getenv("MAXF") or "1500")
emu.addEventCallback(function()
  n = n + 1
  if n == maxf - 1 then
    local t = {}
    for _, k in ipairs(order) do local e = seen[k]; t[#t + 1] = string.format("%s first=%d n=%d %s", k, e.first, e.count, e.sample) end
    L.write("rwatch.txt", table.concat(t, "\n") .. "\n")
  end
end, emu.eventType.endFrame)
dofile(os.getenv("LIBDIR") .. "/boot.lua")
