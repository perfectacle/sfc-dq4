-- 성장·조우·상점 실측의 관측 프로브. MODE에 따라 기록하고 DRIVER의 입력을 재생한다.
package.path = os.getenv('LIBDIR') .. '/?.lua;' .. package.path
local L = require('lib')
local m = emu.memType.snesMemory
local mode, n, log = os.getenv('MODE'), 0, {}
local function observe(pc)
  emu.addMemoryCallback(function()
    local s = emu.getState()
    log[#log + 1] = string.format('f%d pc=%06X A=%04X X=%04X Y=%04X', n, pc, s['cpu.a'], s['cpu.x'], s['cpu.y'])
  end, emu.callbackType.exec, pc, pc)
end
if mode == 'growth' then
  observe(0x23EB50)
  observe(0x23ED58)
elseif mode == 'shop' then
  local item = 0
  observe(0x06F49C)
  emu.addMemoryCallback(function()
    item = emu.getState()['cpu.a'] & 0xFF
  end, emu.callbackType.exec, 0x21A447, 0x21A447)
  emu.addMemoryCallback(function()
    local price = emu.read16(0x46, m) | (emu.read(0x48, m) << 16)
    log[#log + 1] = string.format('price item=%02X value=%d', item, price)
  end, emu.callbackType.exec, 0x21A475, 0x21A475)
end
emu.addEventCallback(function()
  n = n + 1
  if n == 2 and mode == 'growth' then
    -- 승리 뒤 레벨업을 한 번 일으켜 성장 표가 계산하는 다음 경험치를 읽는다.
    emu.write(0x7E2066, 1, m)
    emu.write(0x7E2067, 0, m)
    emu.write(0x7E2068, 0, m)
  end
end, emu.eventType.endFrame)
local write = L.write
L.write = function(name, data)
  if name == 'battle.txt' or name == 'msg.txt' or name == 'warp.txt' then
    write('observed.txt', table.concat(log, '\n') .. '\n')
    L.dump('final.wram', emu.memType.snesWorkRam, 0x20000)
  end
  return write(name, data)
end
dofile(os.getenv('DRIVER'))
