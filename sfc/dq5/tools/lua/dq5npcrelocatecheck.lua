-- 인물 목록 로더가 끝난 직후의 표를 저장한다. 입력은 DRIVER의 보행 절차를 따른다.
package.path = os.getenv('LIBDIR') .. '/?.lua;' .. package.path
local L = require('lib')
local m = emu.memType.snesMemory
local n = 0
local group, map = tonumber(os.getenv('CHECK_GROUP'), 16), tonumber(os.getenv('CHECK_MAP'), 16)
emu.addEventCallback(function() n = n + 1 end, emu.eventType.endFrame)
emu.addMemoryCallback(function()
  if n < 300 or emu.read(0x7E00BC, m) ~= group or emu.read(0x7E00BD, m) ~= map then return end
  L.dump('npc.bin', emu.memType.snesWorkRam, 0x20000)
  L.shot('npc.png')
  L.write('frame.txt', tostring(n) .. '\n')
  emu.stop(0)
end, emu.callbackType.exec, 0x12803C, 0x12803C)
dofile(os.getenv('DRIVER'))
