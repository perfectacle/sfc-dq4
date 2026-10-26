-- 습득 비트와 주문 목록 읽기를 기록하고 기존 장면 드라이버를 실행한다.
package.path = os.getenv('LIBDIR') .. '/?.lua;' .. package.path
local L = require('lib')
local m = emu.memType.snesMemory
local log, n = {}, 0
for _, address in ipairs({0x23BE28, 0x23BE31}) do
  emu.addMemoryCallback(function(addr, value)
    local state = emu.getState()
    log[#log + 1] = string.format('read %06X=%02X pc=%02X:%04X', addr, value or 0, state['cpu.k'], state['cpu.pc'])
  end, emu.callbackType.read, address, address)
end
emu.addEventCallback(function()
  n = n + 1
  if n ~= 2 then return end
  if os.getenv('MODE') == 'level' then
    -- 습득 비트를 건드리지 않고 승리 뒤 레벨업만 일으킨다.
    emu.write(0x7E2066, 1, m)
    emu.write(0x7E2067, 0, m)
    emu.write(0x7E2068, 0, m)
  else
    local bits = os.getenv('LEARNED')
    for i = 0, 2 do
      emu.write(0x7E2063 + i, tonumber(bits:sub(i * 2 + 1, i * 2 + 2), 16), m)
    end
    for address, value in pairs({[0x2042]=5, [0x2043]=0, [0x2044]=100, [0x2045]=0,
                                [0x204E]=200, [0x204F]=0, [0x2050]=100, [0x2051]=0}) do
      emu.write(0x7E0000 + address, value, m)
    end
  end
end, emu.eventType.endFrame)
local write = L.write
L.write = function(name, data)
  if name == 'battle.txt' or name == 'msg.txt' then
    write('observed.txt', table.concat(log, '\n') .. '\n')
    L.dump('final.wram', emu.memType.snesWorkRam, 0x20000)
  end
  return write(name, data)
end
dofile(os.getenv('DRIVER'))
