-- 대화 번호를 꺼내는 1C:$96C7 이 $64 를 바꿔 둔 동안(1C:$96DE JSR $96FC ~ $96E1) 읽힌 RAM 주소를 남긴다.
-- ADDRS(16진, 쉼표로 여럿, 기본 0064)를 읽는 명령의 PC 를 reads.txt 에 (프레임, 주소, 값, PC)로 쓴다.
-- 창 밖(그 호출 바깥)의 읽기는 세기만 한다. 툴킷 FC 프로브와 같이 끝에서 DRIVER 를 돌리고 MAXF-1 에 쓴다.
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local L = require("lib")
local f, inside, calls, outside, log = 0, false, 0, 0, {}
local pc = 0

emu.addMemoryCallback(function(addr)
  pc = addr
end, emu.callbackType.exec, 0x8000, 0xFFFF)

emu.addMemoryCallback(function()
  if L.prgOffset(0x96DE) ~= 0x716DE then return end
  inside = true
  calls = calls + 1
  log[#log + 1] = string.format("%d call %d 63=%02X 64=%02X", f, calls, emu.read(0x63, L.mem), emu.read(0x64, L.mem))
end, emu.callbackType.exec, 0x96DE, 0x96DE)

emu.addMemoryCallback(function()
  if L.prgOffset(0x96E1) ~= 0x716E1 then return end
  inside = false
end, emu.callbackType.exec, 0x96E1, 0x96E1)

for a in string.gmatch(os.getenv("ADDRS") or "0064", "%x+") do
  local addr = tonumber(a, 16)
  emu.addMemoryCallback(function(_, v)
    if inside then
      log[#log + 1] = string.format("%d read %04X %02X pc=%04X", f, addr, v, pc)
    else
      outside = outside + 1
    end
  end, emu.callbackType.read, addr, addr)
end

local maxf = tonumber(os.getenv("MAXF") or "1500")
emu.addEventCallback(function()
  f = f + 1
  if f == maxf - 1 then
    log[#log + 1] = string.format("calls=%d outside_reads=%d", calls, outside)
    L.write("reads.txt", table.concat(log, "\n") .. "\n")
  end
end, emu.eventType.endFrame)

L.drive()
