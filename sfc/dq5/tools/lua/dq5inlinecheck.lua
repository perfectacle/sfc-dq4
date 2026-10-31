-- dq5inlinecheck.py 의 관측 프로브. 인라인 메시지 명령 처리기의 PC(MARKS="이름=PC;…")를 실행한 프레임,
-- 24:8BAF 가 받은 번호, A 를 누른 프레임을 inline.txt 에 남기고 SHOTS 프레임마다 화면을 찍은 뒤 DRIVER 를 돌린다.
package.path = os.getenv('LIBDIR') .. '/?.lua;' .. package.path
local L = require('lib')
local m = emu.memType.snesMemory
local log, n = {}, 0
for name, pc in string.gmatch(os.getenv('MARKS') or '', '([%w_]+)=(%x+)') do
  local at = tonumber(pc, 16)
  emu.addMemoryCallback(function() log[#log + 1] = string.format('f%d %s', n, name) end, emu.callbackType.exec, at, at)
end
emu.addMemoryCallback(function()
  log[#log + 1] = string.format('f%d message %04X', n, emu.getState()['cpu.a'] & 0xFFFF)
end, emu.callbackType.exec, 0x248BAF, 0x248BAF)
local shots = {}
for f in string.gmatch(os.getenv('SHOTS') or '', '%d+') do shots[tonumber(f)] = true end
local maxf = tonumber(os.getenv('MAXF'))
emu.addEventCallback(function()
  n = n + 1
  if L.held and L.held.a then log[#log + 1] = string.format('f%d press a', n) end
  if shots[n] then L.shot(string.format('f%04d.png', n)) end
  if n == maxf - 1 then L.write('inline.txt', table.concat(log, '\n') .. '\n') end
end, emu.eventType.endFrame)
dofile(os.getenv('DRIVER'))
