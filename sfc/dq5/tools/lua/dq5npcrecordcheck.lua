-- dq5warp.lua 로 CHECK_GROUP/CHECK_MAP 맵에 들어가며 인물 목록 로더가 끝난 직후(12:803C)의 WRAM 을 npc.bin 으로 남기고,
-- 그 맵을 다 놓은 직후(00:E1CC)의 물체 첫 슬롯·다음 빈 슬롯(7E:1982·1983)과 도착 뒤 TEST 입력 동안
-- 메시지 루틴 24:8BAF 가 받은 번호(A)를 warp.txt 끝에 덧붙인다.
-- LIBDIR 의 boot.lua 자리에 dq5warp.lua 를 둔다(dq5npcrecordcheck.py 가 준비).
package.path = os.getenv('LIBDIR') .. '/?.lua;' .. package.path
local L = require('lib')
local m = emu.memType.snesMemory
local group, map = tonumber(os.getenv('CHECK_GROUP'), 16), tonumber(os.getenv('CHECK_MAP'), 16)
local dumped, messages, loaded = false, {}, nil
emu.addMemoryCallback(function()
  if dumped or emu.read(0x7E00BC, m) ~= group or emu.read(0x7E00BD, m) ~= map then return end
  dumped = true
  L.dump('npc.bin', emu.memType.snesWorkRam, 0x20000)
end, emu.callbackType.exec, 0x12803C, 0x12803C)
emu.addMemoryCallback(function()
  if dumped and not loaded then loaded = string.format('%02X %02X', emu.read(0x7E1982, m), emu.read(0x7E1983, m)) end
end, emu.callbackType.exec, 0x00E1CC, 0x00E1CC)
emu.addMemoryCallback(function()
  if dumped and #messages < 64 then messages[#messages + 1] = string.format('%03X', emu.getState()['cpu.a'] & 0xFFFF) end
end, emu.callbackType.exec, 0x248BAF, 0x248BAF)
local write = L.write
L.write = function(name, data)
  if name == 'warp.txt' then
    data = data .. string.format('final map %02X/%02X cell %d,%d slots %s\nmessages %s\n', emu.read(0x7E00BC, m),
      emu.read(0x7E00BD, m), emu.read(0x7E3020, m), emu.read(0x7E3080, m), loaded or '-- --', table.concat(messages, ','))
  end
  return write(name, data)
end
dofile(os.getenv('LIBDIR') .. '/boot.lua')
