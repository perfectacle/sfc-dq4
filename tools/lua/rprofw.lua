-- boot.lua 와 같은 입력으로 부팅하고 FROM~TO 프레임 동안 LO~HI(WRAM 등 CPU 주소) 읽기를 PC 별로 집계한다.
-- PC 마다 횟수, 읽은 주소 범위, 그리고 셀 버퍼처럼 구조가 있는 영역이면 주소 하위 3비트(셀 안 오프셋) 분포를 rprofw.txt 에 쓴다.
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local L = require("lib")
local from, to = tonumber(os.getenv("FROM")), tonumber(os.getenv("TO"))
local lo, hi = tonumber(os.getenv("LO"), 16), tonumber(os.getenv("HI"), 16)
local n, st, cb = 0, {}, nil
local function onRead(addr)
  local s = emu.getState()
  local pc = (s["cpu.k"] << 16) | s["cpu.pc"]
  local e = st[pc]
  if not e then e = {n = 0, lo = addr, hi = addr, f = n, off = {}}; st[pc] = e end
  e.n = e.n + 1
  if addr < e.lo then e.lo = addr end
  if addr > e.hi then e.hi = addr end
  local o = addr & 7
  e.off[o] = (e.off[o] or 0) + 1
end
emu.addEventCallback(function()
  n = n + 1
  if n == from then cb = emu.addMemoryCallback(onRead, emu.callbackType.read, lo, hi) end
  if n == to then
    emu.removeMemoryCallback(cb, emu.callbackType.read, lo, hi)
    local t = {}
    for pc, e in pairs(st) do t[#t + 1] = {pc, e} end
    table.sort(t, function(a, b) return a[2].n > b[2].n end)
    local out = {}
    for _, x in ipairs(t) do
      local offs = {}
      for o = 0, 7 do if x[2].off[o] then offs[#offs + 1] = string.format("+%d:%d", o, x[2].off[o]) end end
      out[#out + 1] = string.format("pc=%06X n=%d range=%06X-%06X first=%d %s", x[1], x[2].n, x[2].lo, x[2].hi, x[2].f, table.concat(offs, " "))
    end
    L.write("rprofw.txt", table.concat(out, "\n") .. "\n")
  end
end, emu.eventType.endFrame)
dofile(os.getenv("LIBDIR") .. "/boot.lua")
