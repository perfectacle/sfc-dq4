-- CPU 주소 LO-HI(16진, RAM 쪽)를 읽거나(KIND=read, 기본) 쓰는(KIND=write) 명령을 (명령 주소, 뱅크 $0507, 주소)마다 묶어
-- 횟수·처음 프레임·처음 값과 함께 ram.txt 에 쓴다(MAXF-1 프레임). 전투 RAM 의 한 바이트를 어디서 읽는지 찾는 데 쓴다.
-- probe/reads.lua 는 PRG ROM 읽기만 세므로 RAM 은 이것으로 본다. 6502 의 더미 읽기도 잡히니 명령 주소를 디스어셈블리와 견줄 것.
-- 끝에서 DRIVER 를 돌린다.
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local L = require("lib")
local lo, hi = tonumber(os.getenv("LO"), 16), tonumber(os.getenv("HI"), 16)
local kind = os.getenv("KIND") == "write" and emu.callbackType.write or emu.callbackType.read
local f, pc, seen, order = 0, 0, {}, {}
emu.addMemoryCallback(function(a) pc = a end, emu.callbackType.exec, 0, 0xFFFF)
emu.addMemoryCallback(function(addr, value)
  local key = string.format("%04X b=%02X %04X", pc, emu.read(0x0507, L.mem), addr)
  local e = seen[key]
  if e then e[1] = e[1] + 1 return end
  seen[key] = {1, f, value or emu.read(addr, L.mem)}
  order[#order + 1] = key
end, kind, lo, hi)
local maxf = tonumber(os.getenv("MAXF") or "1500")
emu.addEventCallback(function()
  f = f + 1
  if f == maxf - 1 then
    local out = {}
    for _, k in ipairs(order) do
      local e = seen[k]
      out[#out + 1] = string.format("pc=%s n=%d first=%d v=%02X", k, e[1], e[2], e[3])
    end
    L.write("ram.txt", table.concat(out, "\n") .. "\n")
  end
end, emu.eventType.endFrame)
dofile(os.getenv("DRIVER") or (os.getenv("LIBDIR") .. "/seq.lua"))
