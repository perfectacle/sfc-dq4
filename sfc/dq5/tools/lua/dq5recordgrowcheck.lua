-- 성장·조우 레코드 증설 실측(dq5recordgrowcheck.py 가 부름). DRIVER 의 입력을 그대로 재생하면서
--   LVLUP=1  2프레임에 일행 레코드 0 의 다음 레벨 경험치를 1 로 둬 승리 때 레벨업시킨다
--   23:EDF5(성장 레코드 주소를 Y 에 둔 RTS)와 23:E7C2(조우 판정, A = 구역, 맵 $BC/$BD)의 값, 23:E9B0·23:E99B(무리 정함) 때의
--   7E:1001~1008 을 records.txt 에, DRIVER 가 끝날 때 WRAM 을 final.wram 에 쓴다.
package.path = os.getenv('LIBDIR') .. '/?.lua;' .. package.path
local L = require('lib')
local m = emu.memType.snesMemory
local lvlup = os.getenv('LVLUP')
local n, log = 0, {}
local function hex(addr, len)
  local t = {}
  for i = 0, len - 1 do t[#t + 1] = string.format('%02X', emu.read(addr + i, m)) end
  return table.concat(t)
end
emu.addMemoryCallback(function()
  log[#log + 1] = string.format('f%05d growth record=23%04X', n, emu.getState()['cpu.y'] & 0xFFFF)
end, emu.callbackType.exec, 0x23EDF5, 0x23EDF5)
emu.addMemoryCallback(function()
  log[#log + 1] = string.format('f%05d area %02X map %02X/%02X', n, emu.getState()['cpu.a'] & 0xFF,
    emu.read(0x7E00BC, m), emu.read(0x7E00BD, m))
end, emu.callbackType.exec, 0x23E7C2, 0x23E7C2)
emu.addMemoryCallback(function()
  log[#log + 1] = string.format('f%05d group %s', n, hex(0x7E1001, 8))
end, emu.callbackType.exec, 0x23E9B0, 0x23E9B0)
emu.addEventCallback(function()
  n = n + 1
  if n == 2 and lvlup then
    emu.write(0x7E2066, 1, m)
    emu.write(0x7E2067, 0, m)
    emu.write(0x7E2068, 0, m)
  end
end, emu.eventType.endFrame)
local write = L.write
L.write = function(name, data)
  if name == 'battle.txt' or name == 'warp.txt' then
    write('records.txt', table.concat(log, '\n') .. '\n')
    L.dump('final.wram', emu.memType.snesWorkRam, 0x20000)
  end
  return write(name, data)
end
dofile(os.getenv('DRIVER'))
