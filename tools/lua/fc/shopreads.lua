-- RANGE("6000-62FF", CPU 주소)를 읽는 명령을 PC 와 읽은 주소로 모아 reads.txt 에 적는다(MAXF−1 프레임).
-- FROM 프레임부터 센다. BANK 를 주면 그때 `$0507` 이 그 뱅크일 때만, PCLO-PCHI 를 주면 PC 가 그 사이일 때만 센다.
-- 줄은 "뱅크:PC 주소 값 횟수 첫프레임". 입력은 DRIVER(seq.lua·warp.lua)가 맡는다.
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local L = require("lib")
local lo, hi = string.match(os.getenv("RANGE") or "6000-62FF", "(%x+)-(%x+)")
lo, hi = tonumber(lo, 16), tonumber(hi, 16)
local bank = os.getenv("BANK") and tonumber(os.getenv("BANK"), 16)
local pclo = tonumber(os.getenv("PCLO") or "0", 16)
local pchi = tonumber(os.getenv("PCHI") or "FFFF", 16)
local from = tonumber(os.getenv("FROM") or "0")
local f, pc, seen, order = 0, 0, {}, {}
emu.addMemoryCallback(function(addr) pc = addr end, emu.callbackType.exec, 0x8000, 0xFFFF)
emu.addMemoryCallback(function(addr, value)
  if f < from or pc < pclo or pc > pchi then return end
  local b = emu.read(0x0507, L.mem)
  if bank and b ~= bank then return end
  local key = string.format("%02X:%04X %04X", b, pc, addr)
  local e = seen[key]
  if e then
    e.n = e.n + 1
  else
    seen[key] = {n = 1, v = value, f = f}
    order[#order + 1] = key
  end
end, emu.callbackType.read, lo, hi)
local maxf = tonumber(os.getenv("MAXF") or "1500")
emu.addEventCallback(function()
  f = f + 1
  if f == maxf - 1 then
    local out = {}
    for _, k in ipairs(order) do
      local e = seen[k]
      out[#out + 1] = string.format("%s %02X %d %d", k, e.v, e.n, e.f)
    end
    L.write("reads.txt", table.concat(out, "\n") .. "\n")
  end
end, emu.eventType.endFrame)
L.drive()
