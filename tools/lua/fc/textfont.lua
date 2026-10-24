-- CHR-RAM 오프셋 PPU(기본 10B0-10B7, 글자 바이트 0B「あ」의 타일 앞 8바이트)에 쓰기가 일어날 때마다
-- 프레임, 직전 실행 PC 와 그 PRG 오프셋, 쓴 값, $0507(현재 뱅크)을 font.txt 에 적는다(MAXF-1 프레임).
-- 끝에서 입력 드라이버(DRIVER, 기본 boot.lua)를 돌린다.
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local L = require("lib")
local lo, hi = 0x10B0, 0x10B7
local r = os.getenv("PPU")
if r then local a, b = r:match("(%x+)-(%x+)"); lo, hi = tonumber(a, 16), tonumber(b, 16) end
local f, pc, log = 0, 0, {}
emu.addMemoryCallback(function(a) pc = a end, emu.callbackType.exec, 0, 0xFFFF)
emu.addMemoryCallback(function(addr, value)
  local o = L.prgOffset(pc)
  log[#log + 1] = string.format("%d chr=%04X val=%02X pc=%04X prg=%s 0507=%02X", f, addr, value, pc,
    o and string.format("%05X", o) or "-", emu.read(0x0507, L.mem))
end, emu.callbackType.write, lo, hi, emu.cpuType.nes, emu.memType.nesChrRam)
local maxf = tonumber(os.getenv("MAXF") or "1500")
emu.addEventCallback(function()
  f = f + 1
  if f == maxf - 1 then L.write("font.txt", table.concat(log, "\n") .. "\n") end
end, emu.eventType.endFrame)
L.drive()
