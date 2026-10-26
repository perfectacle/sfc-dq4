-- dq5warp.lua 로 맵에 선 뒤 TEST 로 걸은 결과에 마지막 맵·칸·주인공 층(7E:31A0)·$BE 를 덧붙인다.
-- 영역 이동 플래그 bit6 이 꺼진 레코드가 내는 효과음 갈래(2A:F4D1)를 지나가면 그 횟수도 적는다.
-- LIBDIR 의 boot.lua 자리에 dq5warp.lua 를 둔다(dq5exitcheck.py 가 준비).
package.path = os.getenv('LIBDIR') .. '/?.lua;' .. package.path
local L = require('lib')
local m = emu.memType.snesMemory
local sound = 0
emu.addMemoryCallback(function() sound = sound + 1 end, emu.callbackType.exec, 0x2AF4D1, 0x2AF4D1)
local write = L.write
L.write = function(name, data)
  if name == 'warp.txt' then
    data = data .. string.format('final map %02X/%02X cell %d,%d layer %02X BE=%02X sound %d\n', emu.read(0x7E00BC, m),
      emu.read(0x7E00BD, m), emu.read(0x7E3020, m), emu.read(0x7E3080, m), emu.read(0x7E31A0, m), emu.read(0x7E00BE, m), sound)
  end
  return write(name, data)
end
dofile(os.getenv('LIBDIR') .. '/boot.lua')
