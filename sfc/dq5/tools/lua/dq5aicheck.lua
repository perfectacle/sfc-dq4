-- 작전 AI 가 고른 행동을 기록하고 DRIVER(전투 드라이버)를 실행한다.
-- 20:8846(21:BC6D 에서 돌아온 직후)마다 행동자 $1200, 행동 $1201, 대상 $1202 를 decisions.txt 에 적는다.
package.path = os.getenv('LIBDIR') .. '/?.lua;' .. package.path
local L = require('lib')
local m = emu.memType.snesMemory
local log, n = {}, 0
emu.addMemoryCallback(function()
  log[#log + 1] = string.format('f%d actor %02X action %02X target %02X', n, emu.read(0x7E1200, m),
    emu.read(0x7E1201, m), emu.read(0x7E1202, m))
end, emu.callbackType.exec, 0x208846, 0x208846)
emu.addEventCallback(function() n = n + 1 end, emu.eventType.endFrame)
local write = L.write
L.write = function(name, data)
  if name == 'battle.txt' then
    write('decisions.txt', table.concat(log, '\n') .. '\n')
  end
  return write(name, data)
end
dofile(os.getenv('DRIVER'))
