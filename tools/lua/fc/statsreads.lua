-- PRG ROM 오프셋 LO-HI(16진) 를 읽을 때마다 프레임, 읽은 명령의 CPU 주소, 읽은 PRG 오프셋, A X Y 를 rd.txt 에 쓴다
-- (MAXF-1 프레임, LIMIT 줄까지). STACK=n 이면 스택 위 n 바이트(부른 곳의 복귀 주소)도 붙인다.
-- probe/reads.lua 는 읽는 명령마다 범위만 남기므로, 고정 뱅크의 바이트 읽기 루틴($C3EA)처럼 여러 표를 읽는 곳에서는
-- 어느 바이트를 읽었는지 이것으로 본다. 끝에서 DRIVER 를 돌린다.
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local L = require("lib")
local rom = emu.memType.nesPrgRom
local lo, hi = tonumber(os.getenv("LO"), 16), tonumber(os.getenv("HI"), 16)
local limit = tonumber(os.getenv("LIMIT") or "5000")
local depth = tonumber(os.getenv("STACK") or "0")
local f, log, pc = 0, {}, 0
emu.addMemoryCallback(function(a) pc = a end, emu.callbackType.exec, 0, 0xFFFF)
emu.addMemoryCallback(function(addr)
  if #log >= limit then return end
  local off = emu.convertAddress(addr, L.mem).address
  if off < lo or off > hi then return end
  local s = emu.getState()
  local t = {string.format("%d pc=%04X off=%05X A=%02X X=%02X Y=%02X", f, pc, off, s["cpu.a"], s["cpu.x"], s["cpu.y"])}
  if depth > 0 then
    local st = {}
    for k = 1, depth do if s["cpu.sp"] + k <= 0xFF then st[#st + 1] = string.format("%02X", emu.read(0x100 + s["cpu.sp"] + k, L.mem)) end end
    t[#t + 1] = "st=" .. table.concat(st)
  end
  log[#log + 1] = table.concat(t, " ")
end, emu.callbackType.read, 0x8000, 0xBFFF)
local maxf = tonumber(os.getenv("MAXF") or "1500")
emu.addEventCallback(function()
  f = f + 1
  if f == maxf - 1 then L.write("rd.txt", table.concat(log, "\n") .. "\n") end
end, emu.eventType.endFrame)
L.drive()
