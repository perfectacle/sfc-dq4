-- DQ5 빈 자리 감시: FREE="01FED0-01FFFF,…"(CPU 주소, 뱅크 +80 거울도) 범위의 읽기·실행을 세어 free.txt 로(60프레임마다
-- 다시 씀). ACCESS="read,write" 처럼 주면 그 접근만 센다(기본 read,exec. WRAM 범위는 write 를 넣는다).
-- 드라이버(LIBDIR/boot.lua, 보통 dq5warp.lua) 뒤에 얹는다. dq5freesweep.py 가 부른다.
-- 줄마다 접근한 가장 낮은·높은 주소(lo·hi)와 접근한 PC(처음 8곳)도 적는다.
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local L = require("lib")
local hits, n = {}, 0
for lo, hi in string.gmatch(os.getenv("FREE") or "", "(%x+)-(%x+)") do
  local a, b = tonumber(lo, 16), tonumber(hi, 16)
  local key = lo .. "-" .. hi
  for _, base in ipairs(a >= 0x7E0000 and {0} or {0, 0x800000}) do
    for kind in string.gmatch(os.getenv("ACCESS") or "read,exec", "%a+") do
      local ct = emu.callbackType[kind]
      emu.addMemoryCallback(function(addr)
        local h = hits[key]
        if not h then
          local st = emu.getState()
          h = {n = 0, a = addr, pc = st["cpu.k"] * 0x10000 + st["cpu.pc"], f = n, lo = addr, hi = addr, pcs = {}, npc = 0}
          hits[key] = h
        end
        h.n = h.n + 1
        if addr < h.lo then h.lo = addr end
        if addr > h.hi then h.hi = addr end
        if h.npc < 8 then
          local st = emu.getState()
          local pc = st["cpu.k"] * 0x10000 + st["cpu.pc"]
          if not h.pcs[pc] then h.pcs[pc] = true; h.npc = h.npc + 1 end
        end
      end, ct, a + base, b + base)
    end
  end
end
emu.addEventCallback(function()
  n = n + 1
  if n % 60 == 0 then
    local o = {string.format("frames=%d", n)}
    for k, h in pairs(hits) do
      local pcs = {}
      for pc in pairs(h.pcs) do pcs[#pcs + 1] = string.format("%06X", pc) end
      table.sort(pcs)
      o[#o + 1] = string.format("%s n=%d first=f%d addr=%06X pc=%06X lo=%06X hi=%06X pcs=%s", k, h.n, h.f, h.a, h.pc,
                                h.lo, h.hi, table.concat(pcs, ","))
    end
    L.write("free.txt", table.concat(o, "\n") .. "\n")
  end
end, emu.eventType.endFrame)
dofile(os.getenv("LIBDIR") .. "/boot.lua")
