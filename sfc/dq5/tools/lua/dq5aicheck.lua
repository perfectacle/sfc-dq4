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
-- AIPROBE="21DA52,…" 면 그 PC 마다 직접 페이지 $42~$4A·$1211(작전)·X 를 함께 적는다(같은 decisions.txt).
for pc in string.gmatch(os.getenv('AIPROBE') or '', '%x+') do
  local at = tonumber(pc, 16)
  emu.addMemoryCallback(function()
    local dp = {}
    for a = 0x42, 0x4A do dp[#dp + 1] = string.format('%02X', emu.read(0x7E0000 + a, m)) end
    log[#log + 1] = string.format('f%d probe %06X dp42=%s 1211=%02X X=%04X', n, at, table.concat(dp, ' '),
      emu.read(0x7E1211, m), emu.getState()['cpu.x'])
  end, emu.callbackType.exec, at, at)
end
-- AIREADS="21DA4F-21DA52" 면 앞 PC 에서 뒤 PC 까지 읽은 롬(8000~)·WRAM(7E:0200~) 자리를 창마다 적는다.
local from, upto = string.match(os.getenv('AIREADS') or '', '(%x+)-(%x+)')
if from then
  local open, seen = false, {}
  emu.addMemoryCallback(function() open, seen = true, {} end, emu.callbackType.exec, tonumber(from, 16), tonumber(from, 16))
  emu.addMemoryCallback(function()
    if not open then return end
    open = false
    local o = {}
    for _, a in ipairs(seen) do o[#o + 1] = string.format('%06X', a) end
    log[#log + 1] = string.format('f%d reads 43=%02X %s', n, emu.read(0x7E0043, m), table.concat(o, ','))
  end, emu.callbackType.exec, tonumber(upto, 16), tonumber(upto, 16))
  emu.addMemoryCallback(function(addr)
    if open and #seen < 96 and (addr & 0xFFFF >= 0x8000 or addr >> 16 == 0x7E and addr & 0xFFFF >= 0x0200) then
      seen[#seen + 1] = addr
    end
  end, emu.callbackType.read, 0x000000, 0xFFFFFF)
end
emu.addEventCallback(function() n = n + 1 end, emu.eventType.endFrame)
local write = L.write
L.write = function(name, data)
  if name == 'battle.txt' then
    write('decisions.txt', table.concat(log, '\n') .. '\n')
  end
  return write(name, data)
end
dofile(os.getenv('DRIVER'))
