-- DQ5 전투 메시지·이름 쓰기 검사(dq5battletextcheck.py 가 부름). DRIVER(dq5warp.lua)로 전투를 붙이고,
-- 24:8C39 에 들어올 때 메시지 번호(A), 24:8C21 에 들어올 때 비트 위치($F0~$F3), 24:869A(푼 뒤)에 7E:0E4B 128바이트,
-- 그 GRIDDELAY(기본 40) 프레임 뒤 글자 격자 7E:1DD5(26칸 × 6줄)를 battletext.txt 에 적는다.
package.path = os.getenv('LIBDIR') .. '/?.lua;' .. package.path
local L = require('lib')
local m = emu.memType.snesMemory
local delay = tonumber(os.getenv('GRIDDELAY') or '40')
local n, msg, lines, grids = 0, nil, {}, {}

local function hex(addr, len)
  local t = {}
  for i = 0, len - 1 do t[#t + 1] = string.format('%02X', emu.read(addr + i, m)) end
  return table.concat(t)
end

emu.addMemoryCallback(function()
  msg = emu.getState()['cpu.a'] & 0xFFFF
end, emu.callbackType.exec, 0x248C39, 0x248C39)
emu.addMemoryCallback(function()
  if msg then
    lines[#lines + 1] = string.format('f%05d msg %03X stream %02X%02X%02X.%d', n, msg, emu.read(0xF2, m),
      emu.read(0xF1, m), emu.read(0xF0, m), emu.read(0xF3, m) & 7)
  end
end, emu.callbackType.exec, 0x248C21, 0x248C21)
emu.addMemoryCallback(function()
  if msg then
    lines[#lines + 1] = string.format('f%05d buffer %03X %s', n, msg, hex(0x7E0E4B, 128))
    grids[n + delay] = msg
    msg = nil
  end
end, emu.callbackType.exec, 0x24869A, 0x24869A)
emu.addEventCallback(function()
  n = n + 1
  if grids[n] then
    lines[#lines + 1] = string.format('f%05d grid %03X %s', n, grids[n], hex(0x7E1DD5, 26 * 6))
    L.shot(string.format('f%05d.png', n))
  end
end, emu.eventType.endFrame)

local write = L.write
L.write = function(name, data)
  if name == 'warp.txt' then write('battletext.txt', table.concat(lines, '\n') .. '\n') end
  return write(name, data)
end
dofile(os.getenv('DRIVER'))
