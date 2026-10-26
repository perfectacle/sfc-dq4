-- 표 쓰기 실측의 관측 프로브. READS 의 롬 주소를 읽을 때와 EXECS 의 PC 를 지날 때를 기록하고 DRIVER 의 입력을 재생한다.
--   READS="23B591-23B668,278073"   그 CPU 주소(범위)를 읽을 때 값·PC
--   EXECS="21A561"          그 PC 를 지날 때 A·X·Y
-- DRIVER 가 결과(battle.txt·msg.txt)를 쓸 때 observed.txt 와 WRAM 전체(final.wram)를 함께 남긴다.
package.path = os.getenv('LIBDIR') .. '/?.lua;' .. package.path
local L = require('lib')
local n, log, LIMIT = 0, {}, 20000
-- 상한에 닿으면 표시를 남겨, 「없어야 하는 값」 검사가 잘린 기록으로 통과하지 않게 한다.
local function full()
  if #log < LIMIT then return false end
  if #log == LIMIT then log[#log + 1] = 'truncated' end
  return true
end
for tok in string.gmatch(os.getenv('READS') or '', '[^,]+') do
  local a, b = tok:match('^(%x+)-(%x+)$')
  a, b = tonumber(a or tok, 16), tonumber(b or tok, 16)
  emu.addMemoryCallback(function(adr, v)
    if full() then return end
    local s = emu.getState()
    log[#log + 1] = string.format('f%d read %06X=%02X pc=%02X%04X', n, adr, v or 0, s['cpu.k'], s['cpu.pc'])
  end, emu.callbackType.read, a, b)
end
for a in string.gmatch(os.getenv('EXECS') or '', '%x+') do
  local pc = tonumber(a, 16)
  emu.addMemoryCallback(function()
    if full() then return end
    local s = emu.getState()
    log[#log + 1] = string.format('f%d pc=%06X A=%04X X=%04X Y=%04X', n, pc, s['cpu.a'], s['cpu.x'], s['cpu.y'])
  end, emu.callbackType.exec, pc, pc)
end
emu.addEventCallback(function() n = n + 1 end, emu.eventType.endFrame)
local write = L.write
L.write = function(name, data)
  if name == 'battle.txt' or name == 'msg.txt' then
    write('observed.txt', table.concat(log, '\n') .. '\n')
    L.dump('final.wram', emu.memType.snesWorkRam, 0x20000)
  end
  return write(name, data)
end
dofile(os.getenv('DRIVER'))
