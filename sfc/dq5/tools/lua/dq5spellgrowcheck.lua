-- 늘린 행동 번호의 습득·필드·전투 실행을 기록하고 DRIVER 의 입력을 재생한다.
--   MODE=level            2프레임째에 다음 레벨 경험치를 1 로 두어 승리 뒤 레벨업만 일으킨다(습득 비트는 그대로)
--   MODE=field·battle     2프레임째에 LEARNED(습득 비트 3바이트, 16진)와 HP 5·MP 100 을 쓴다
--   READS="6E8000-6E80FF"  그 CPU 주소(범위)를 읽을 때 값·PC
--   EXECS="20FFE0,11FFB0"  그 PC 를 지날 때 A·X·Y
-- DRIVER 가 결과(battle.txt·msg.txt)를 쓸 때 observed.txt 와 WRAM 전체(final.wram)를 함께 남긴다.
package.path = os.getenv('LIBDIR') .. '/?.lua;' .. package.path
local L = require('lib')
local m = emu.memType.snesMemory
local n, log, LIMIT = 0, {}, 20000
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
emu.addEventCallback(function()
  n = n + 1
  if n ~= 2 then return end
  if os.getenv('MODE') == 'level' then
    emu.write(0x7E2066, 1, m)
    emu.write(0x7E2067, 0, m)
    emu.write(0x7E2068, 0, m)
  elseif os.getenv('LEARNED') then
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
