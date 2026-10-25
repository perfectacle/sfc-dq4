-- 정해 둔 PRG 오프셋이 실행될 때 레지스터를 바꾸고(REGS="43ADB:a=00,ps=06;47C21:x=01"), 메모리 위의 PRG 바이트를
-- 처음에 바꾼 뒤(PRGPOKE="5A80E=B3", PRG 오프셋) 다른 프로브 THEN(이 폴더의 파일 이름, 기본 textbrk.lua)을 그대로 돌린다.
-- 롬 안의 드문 갈래를 억지로 지나게 하거나 창 레코드 바이트 하나의 효과를 볼 때 쓴다.
-- 바꾼 순간은 regs.txt 에 "프레임 PRG 오프셋 바꾸기 전 A X Y" 로 적는다(MAXF-1 프레임).
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local L = require("lib")
local here = debug.getinfo(1, "S").source:sub(2):match("(.*/)")
local f, log = 0, {}
for off, sets in string.gmatch(os.getenv("REGS") or "", "(%x+):([^;]+)") do
  local o = tonumber(off, 16)
  local addr = 0x8000 + (o & 0x3FFF)
  if o >= 0x3C000 and o < 0x40000 or o >= 0x7C000 then addr = 0xC000 + (o & 0x3FFF) end
  local t = {}
  for r, v in string.gmatch(sets, "(%a+)=(%x+)") do t["cpu." .. r] = tonumber(v, 16) end
  emu.addMemoryCallback(function(a)
    if L.prgOffset(a) ~= o then return end
    local st = emu.getState()
    log[#log + 1] = string.format("%d %05X A=%02X X=%02X Y=%02X", f, o, st["cpu.a"], st["cpu.x"], st["cpu.y"])
    emu.setState(t)
  end, emu.callbackType.exec, addr, addr)
end
local maxf = tonumber(os.getenv("MAXF") or "1500")
emu.addEventCallback(function()
  f = f + 1
  if f == maxf - 1 then L.write("regs.txt", table.concat(log, "\n") .. "\n") end
end, emu.eventType.endFrame)
for off, v in string.gmatch(os.getenv("PRGPOKE") or "", "(%x+)=(%x+)") do
  emu.write(tonumber(off, 16), tonumber(v, 16), emu.memType.nesPrgRom)
end
dofile(here .. (os.getenv("THEN") or "textbrk.lua"))
