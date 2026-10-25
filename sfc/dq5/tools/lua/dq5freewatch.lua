-- DQ5 빈 자리 감시: FREE="01FED0-01FFFF,…"(CPU 주소, 뱅크 +80 거울도) 범위의 읽기·실행을 세어 free.txt 로(60프레임마다
-- 다시 씀). 드라이버(LIBDIR/boot.lua, 보통 dq5warp.lua) 뒤에 얹는다. dq5freesweep.py 가 부른다.
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local L = require("lib")
local hits, n = {}, 0
for lo, hi in string.gmatch(os.getenv("FREE") or "", "(%x+)-(%x+)") do
  local a, b = tonumber(lo, 16), tonumber(hi, 16)
  local key = lo .. "-" .. hi
  for _, base in ipairs({0, 0x800000}) do
    for _, ct in ipairs({emu.callbackType.read, emu.callbackType.exec}) do
      emu.addMemoryCallback(function(addr)
        local h = hits[key]
        if not h then
          local st = emu.getState()
          h = {n = 0, a = addr, pc = st["cpu.k"] * 0x10000 + st["cpu.pc"], f = n}
          hits[key] = h
        end
        h.n = h.n + 1
      end, ct, a + base, b + base)
    end
  end
end
emu.addEventCallback(function()
  n = n + 1
  if n % 60 == 0 then
    local o = {string.format("frames=%d", n)}
    for k, h in pairs(hits) do o[#o + 1] = string.format("%s n=%d first=f%d addr=%06X pc=%06X", k, h.n, h.f, h.a, h.pc) end
    L.write("free.txt", table.concat(o, "\n") .. "\n")
  end
end, emu.eventType.endFrame)
dofile(os.getenv("LIBDIR") .. "/boot.lua")
