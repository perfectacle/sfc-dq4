-- boot.lua 와 같은 입력으로 부팅하고 FROM~TO 프레임 동안 ROM 읽기(코드 실행 제외)를 PC 별로 집계한다.
-- PC 마다 횟수와 읽은 CPU 주소의 최소·최대를 rprof.txt 에 쓴다(횟수 내림차순).
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local L = require("lib")
local from, to = tonumber(os.getenv("FROM")), tonumber(os.getenv("TO"))
local n, st, cbs = 0, {}, {}
local function onRead(addr, value)
  local s = emu.getState()
  local pc = (s["cpu.k"] << 16) | s["cpu.pc"]
  if (addr >> 16) == s["cpu.k"] and math.abs((addr & 0xFFFF) - s["cpu.pc"]) < 4 then return end
  local e = st[pc]
  if not e then e = {n = 0, lo = addr, hi = addr, f = n}; st[pc] = e end
  e.n = e.n + 1
  if addr < e.lo then e.lo = addr end
  if addr > e.hi then e.hi = addr end
end
local ranges = {}
for b = 0x00, 0x3F do ranges[#ranges + 1] = {(b << 16) | 0x8000, (b << 16) | 0xFFFF} end
for b = 0x80, 0xBF do ranges[#ranges + 1] = {(b << 16) | 0x8000, (b << 16) | 0xFFFF} end
emu.addEventCallback(function()
  n = n + 1
  if n == from then for _, r in ipairs(ranges) do cbs[#cbs + 1] = {emu.addMemoryCallback(onRead, emu.callbackType.read, r[1], r[2]), r} end end
  if n == to then
    for _, c in ipairs(cbs) do emu.removeMemoryCallback(c[1], emu.callbackType.read, c[2][1], c[2][2]) end
    local t = {}
    for pc, e in pairs(st) do t[#t + 1] = {pc, e} end
    table.sort(t, function(a, b) return a[2].n > b[2].n end)
    local out = {}
    for _, x in ipairs(t) do out[#out + 1] = string.format("pc=%06X n=%d range=%06X-%06X first=%d", x[1], x[2].n, x[2].lo, x[2].hi, x[2].f) end
    L.write("rprof.txt", table.concat(out, "\n") .. "\n")
  end
end, emu.eventType.endFrame)
dofile(os.getenv("LIBDIR") .. "/boot.lua")
