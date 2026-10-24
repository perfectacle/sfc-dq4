-- 창 문자열 표(16:$A572)를 쓰는 순간을 적는다. win.txt 한 줄에 프레임과
--   top g=그룹($03D6) n=항목        16:$9783 이 항목 하나를 찍기 시작할 때(A = 항목 번호)
--   ref g=그룹 b=바이트 → code|str   16:$97B0 이 문자열 안의 80 이상 바이트를 만났을 때(갈래는 16:$97B6 의 carry)
-- 를 차례로 쓴다. 같은 줄이 이어지면 한 번만. 끝에서 입력 드라이버(DRIVER)를 돌리고 MAXF-1 프레임에 쓴다.
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local L = require("lib")
local f, log, last, pend = 0, {}, nil, nil
local function add(s)
  if s ~= last then log[#log + 1] = f .. " " .. s; last = s end
end
local function at(addr, fn)
  local off = 0x16 * 0x4000 + (addr & 0x3FFF)
  emu.addMemoryCallback(function(a)
    if L.prgOffset(a) == off then fn(emu.getState()) end
  end, emu.callbackType.exec, addr, addr)
end
at(0x9783, function(st) add(string.format("top g=%d n=%02X", emu.read(0x03D6, L.mem), st["cpu.a"])) end)
at(0x97B0, function(st) pend = string.format("ref g=%d b=%02X", emu.read(0x03D6, L.mem), st["cpu.a"]) end)
at(0x97B6, function(st)
  if pend then add(pend .. ((st["cpu.ps"] & 1) == 1 and " str" or " code")); pend = nil end
end)
local maxf = tonumber(os.getenv("MAXF") or "1500")
emu.addEventCallback(function()
  f = f + 1
  if f == maxf - 1 then L.write("win.txt", table.concat(log, "\n") .. "\n") end
end, emu.eventType.endFrame)
L.drive()
