package.path = os.getenv('LIBDIR') .. '/?.lua;' .. package.path
local L = require('lib')
local m = emu.memType.snesMemory
local wanted = tonumber(os.getenv('MESSAGE'))
local active, count, lines = false, 0, {}
emu.addMemoryCallback(function()
  active = (emu.getState()['cpu.a'] & 0xFFFF) == wanted
end, emu.callbackType.exec, 0x248BAF, 0x248BAF)
emu.addMemoryCallback(function()
  if active and count == 0 then
    count = 1
    lines[#lines + 1] = string.format('stream=%06X', emu.read16(0xF0, m) | (emu.read(0xF2, m) << 16))
  end
end, emu.callbackType.exec, 0x248B98, 0x248B98)
local ret = tonumber(os.getenv('RETURN_PC'), 16)
emu.addMemoryCallback(function()
  if count >= 1 and count <= 64 then
    lines[#lines + 1] = string.format('%04X', emu.getState()['cpu.a'] & 0x1FFF)
    count = count + 1
  end
end, emu.callbackType.exec, ret, ret)
local write = L.write
L.write = function(name, data)
  if name == 'msg.txt' then write('decoded.txt', table.concat(lines, '\n') .. '\n') end
  return write(name, data)
end
dofile(os.getenv('DRIVER'))
