-- dq5warp.lua 로 맵에 선 뒤 TEST 로 걸은 결과에, 맵을 풀 때마다 15:F7D0 이 고른 맵별 루틴과 셀 하나의 값을 덧붙인다.
-- 15:F7EA(JSL 15:F7F1 직전)에서 $BC·$BD, 맵을 푼 뒤 루틴($A5~$A7), 매 프레임 루틴(7E:1AA6~1AA8)을 적고,
-- 15:F7EE(맵을 푼 뒤 루틴이 끝난 직후)에서 CELL(7E 뱅크 하위 16비트 주소, 16진)의 바이트와 셀 읽기 루틴 $1AAA 를 적는다.
-- 끝에 00:B8C6 의 JMP ($1AAA) 가 간 곳마다 횟수를 적는다(jump XXXX n).
-- LIBDIR 의 boot.lua 자리에 dq5warp.lua 를 둔다(dq5maphookcheck.py 가 준비).
package.path = os.getenv('LIBDIR') .. '/?.lua;' .. package.path
local L = require('lib')
local m = emu.memType.snesMemory
local cell = tonumber(os.getenv('CELL') or '', 16)
local loads = {}
emu.addMemoryCallback(function()
  loads[#loads + 1] = string.format('load %02X/%02X BE=%02X post %02X:%02X%02X frame %02X:%02X%02X', emu.read(0x7E00BC, m),
    emu.read(0x7E00BD, m), emu.read(0x7E00BE, m), emu.read(0x7E00A7, m), emu.read(0x7E00A6, m), emu.read(0x7E00A5, m),
    emu.read(0x7E1AA8, m), emu.read(0x7E1AA7, m), emu.read(0x7E1AA6, m))
end, emu.callbackType.exec, 0x15F7EA, 0x15F7EA)
emu.addMemoryCallback(function()
  if cell then
    loads[#loads] = (loads[#loads] or 'load ?') .. string.format(' cell %02X', emu.read(0x7E0000 + cell, m))
  end
  loads[#loads] = (loads[#loads] or 'load ?') .. string.format(' cellread %04X', emu.read16(0x7E1AAA, m))
end, emu.callbackType.exec, 0x15F7EE, 0x15F7EE)
local jumps = {}
emu.addMemoryCallback(function()
  local target = emu.read16(0x7E1AAA, m)
  jumps[target] = (jumps[target] or 0) + 1
end, emu.callbackType.exec, 0x00B8C6, 0x00B8C6)
local write = L.write
L.write = function(name, data)
  if name == 'warp.txt' then
    for target, n in pairs(jumps) do loads[#loads + 1] = string.format('jump %04X %d', target, n) end
    data = data .. table.concat(loads, '\n') .. (#loads > 0 and '\n' or '') ..
      string.format('final map %02X/%02X cell %d,%d layer %02X BE=%02X\n', emu.read(0x7E00BC, m), emu.read(0x7E00BD, m),
        emu.read(0x7E3020, m), emu.read(0x7E3080, m), emu.read(0x7E31A0, m), emu.read(0x7E00BE, m))
  end
  return write(name, data)
end
dofile(os.getenv('LIBDIR') .. '/boot.lua')
