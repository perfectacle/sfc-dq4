-- CPU 메모리 RANGE(쉼표로 여럿, "6F20-6F5F,7600-76FF")를 읽는 명령을 PC 마다 모아
-- ramreads.txt 에 "pc=ADDR prg=OFFSET n=COUNT addr=LAST val=LAST a=A x=X y=Y first=FRAME" 로 쓴다(MAXF-1 프레임).
-- 블록 속성 표처럼 RAM 에 있는 표를 누가 읽는지 찾는 데 쓴다. 툴킷 probe/reads.lua 는 PRG ROM 읽기만 센다.
-- 6502 의 더미 읽기도 잡히므로 PC 의 명령이 그 주소를 실제로 읽는지 리스팅으로 확인한다.
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local L = require("lib")
local f, maxf = 0, tonumber(os.getenv("MAXF") or "1500")
local from = tonumber(os.getenv("FROM") or "0")
local cur, seen, order = 0, {}, {}
emu.addMemoryCallback(function(a) cur = a end, emu.callbackType.exec, 0, 0xFFFF)
for a, b in string.gmatch(os.getenv("RANGE"), "(%x+)-(%x+)") do
  emu.addMemoryCallback(function(addr, value)
    if f < from then return end
    local e = seen[cur]
    if not e then
      local st = emu.getState()
      e = {n = 0, first = f, prg = L.prgOffset(cur) or -1,
           a = st["cpu.a"], x = st["cpu.x"], y = st["cpu.y"]}
      seen[cur] = e; order[#order + 1] = cur
    end
    e.n = e.n + 1; e.addr = addr; e.val = value
  end, emu.callbackType.read, tonumber(a, 16), tonumber(b, 16))
end
emu.addEventCallback(function()
  f = f + 1
  if f == maxf - 1 then
    local t = {}
    for _, pc in ipairs(order) do
      local e = seen[pc]
      t[#t + 1] = string.format("pc=%04X prg=%05X n=%d addr=%04X val=%02X a=%02X x=%02X y=%02X first=%d",
        pc, e.prg, e.n, e.addr, e.val, e.a, e.x, e.y, e.first)
    end
    L.write("ramreads.txt", table.concat(t, "\n") .. "\n")
  end
end, emu.eventType.endFrame)
L.drive()
