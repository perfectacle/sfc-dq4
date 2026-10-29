-- 맵을 놓은 뒤 슬롯을 더 쓰는 코드(04:FB1C, 01:BA95)와 그 부르는 곳을 지날 때마다 맵·$1982·$1983 을 적고 DRIVER 를 실행한다.
-- DRIVER 가 결과 파일(warp.txt·battle.txt·msg.txt)을 쓸 때 slots.txt 를 함께 남긴다.
package.path = os.getenv('LIBDIR') .. '/?.lua;' .. package.path
local L = require('lib')
local m = emu.memType.snesMemory
local log, n = {}, 0
local SITES = {0x02B3B4, 0x04FB1C, 0x01BA95, 0x02AE7B, 0x02AFB8, 0x02AFE5, 0x02B0F3, 0x05E806, 0x05E852, 0x06D716, 0x05E931, 0x06B52D, 0x05E72A, 0x05E796, 0x05E7B1}
for _, pc in ipairs(SITES) do
  emu.addMemoryCallback(function()
    if #log >= 400 then return end
    log[#log + 1] = string.format('f%d pc %06X map %02X/%02X 1982=%02X 1983=%02X 1995=%02X%02X X=%02X Y=%02X', n, pc,
      emu.read(0x7E00BC, m), emu.read(0x7E00BD, m), emu.read(0x7E1982, m), emu.read(0x7E1983, m),
      emu.read(0x7E1996, m), emu.read(0x7E1995, m), emu.getState()['cpu.x'] & 0xFF, emu.getState()['cpu.y'] & 0xFF)
  end, emu.callbackType.exec, pc, pc)
end
-- OBJ 이름 표 자리(OBSEL $2101)를 마지막으로 쓴 값.
local obsel = -1
emu.addMemoryCallback(function(_, v) obsel = v end, emu.callbackType.write, 0x2101, 0x2101)
-- 01:BA95 가 슬롯 넷을 다 만든 직후(01:BAC7)와 01:BA95 에 들어설 때의 WRAM 을 남겨, 슬롯 20 이상이 다음 칸을 덮는지 본다.
emu.addMemoryCallback(function() L.dump('ba95-before.wram', emu.memType.snesWorkRam, 0x20000) end,
  emu.callbackType.exec, 0x01BA95, 0x01BA95)
emu.addMemoryCallback(function() L.dump('ba95-after.wram', emu.memType.snesWorkRam, 0x20000) end,
  emu.callbackType.exec, 0x01BAC7, 0x01BAC7)
-- 메시지 루틴(24:8BAF)이 받은 번호도 적어, 장면이 어디까지 갔는지 본다.
emu.addMemoryCallback(function()
  if #log < 400 then log[#log + 1] = string.format('f%d msg %03X', n, emu.getState()['cpu.a'] & 0xFFFF) end
end, emu.callbackType.exec, 0x248BAF, 0x248BAF)
emu.addEventCallback(function() n = n + 1 end, emu.eventType.endFrame)
local write = L.write
L.write = function(name, data)
  if name == 'warp.txt' or name == 'battle.txt' or name == 'msg.txt' then
    write('slots.txt', table.concat(log, '\n') .. '\n' .. string.format('end f%d map %02X/%02X 1982=%02X 1983=%02X 1995=%02X%02X 1997=%02X%02X obsel=%02X\n', n,
      emu.read(0x7E00BC, m), emu.read(0x7E00BD, m), emu.read(0x7E1982, m), emu.read(0x7E1983, m),
      emu.read(0x7E1996, m), emu.read(0x7E1995, m), emu.read(0x7E1998, m), emu.read(0x7E1997, m), obsel & 0xFF))
    L.dump('final.wram', emu.memType.snesWorkRam, 0x20000)
  end
  return write(name, data)
end
dofile(os.getenv('DRIVER'))
