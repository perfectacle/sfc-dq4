-- boot.lua 와 같은 입력으로 부팅하고 FROM~TO 프레임 동안 WRAM 쓰기를 PC 별로 집계한다.
-- PC 마다 횟수, 쓴 주소의 최소·최대를 wprof.txt 에 쓴다(횟수 내림차순).
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local L = require("lib")
local from, to = tonumber(os.getenv("FROM")), tonumber(os.getenv("TO"))
local n, st, cb = 0, {}, nil
local function onWrite(addr, value)
  local s = emu.getState()
  local pc = (s["cpu.k"] << 16) | s["cpu.pc"]
  local e = st[pc]
  if not e then e = {n = 0, lo = addr, hi = addr, f = n}; st[pc] = e end
  e.n = e.n + 1
  if addr < e.lo then e.lo = addr end
  if addr > e.hi then e.hi = addr end
end
emu.addEventCallback(function()
  n = n + 1
  if n == from then cb = emu.addMemoryCallback(onWrite, emu.callbackType.write, 0x7E0000, 0x7FFFFF) end
  if n == to then
    emu.removeMemoryCallback(cb, emu.callbackType.write, 0x7E0000, 0x7FFFFF)
    local t = {}
    for pc, e in pairs(st) do t[#t + 1] = {pc, e} end
    table.sort(t, function(a, b) return a[2].n > b[2].n end)
    local out = {}
    for _, x in ipairs(t) do out[#out + 1] = string.format("pc=%06X n=%d range=%06X-%06X first=%d", x[1], x[2].n, x[2].lo, x[2].hi, x[2].f) end
    L.write("wprof.txt", table.concat(out, "\n") .. "\n")
  end
end, emu.eventType.endFrame)
dofile(os.getenv("LIBDIR") .. "/boot.lua")
