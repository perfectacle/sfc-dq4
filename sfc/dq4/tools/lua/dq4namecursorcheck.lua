-- dq4namecursorcheck.py 가 정한 실제 패드 입력과 커서·이름 버퍼를 기록한다.
package.path = os.getenv('LIBDIR') .. '/?.lua;' .. package.path
local L = require('lib')
local cfg = dofile(os.getenv('NAME_CURSOR_CASE'))
local m = emu.memType.snesMemory
for a = 0, 0x1FFF do emu.write(a, 0, emu.memType.snesSaveRam) end
local frame, initialized, finished = 0, false, false
local log = {}
local function snapshot()
  local bytes = {}
  for a = 0x7FF000, 0x7FF023 do bytes[#bytes + 1] = string.format('%02X', emu.read(a, m)) end
  for a = 0x71, 0x79 do bytes[#bytes + 1] = string.format('%02X', emu.read(a, m)) end
  bytes[#bytes + 1] = string.format('%02X', emu.read(0xE8, m))
  return table.concat(bytes, ' ')
end
emu.addMemoryCallback(function()
  if not initialized then
    emu.write(0xCC, cfg.initial, m)
    initialized = true
  end
end, emu.callbackType.exec, cfg.loop, cfg.loop)
emu.addMemoryCallback(function(a, value)
  local old = emu.read(0xAD7, m)
  if frame >= 1290 and not finished and value ~= old and emu.getState()["cpu.k"] == 0x30 then
    log[#log + 1] = string.format('MOVE %d %d %d', frame, old, value)
  end
end, emu.callbackType.write, 0xAD7, 0xAD7, emu.cpuType.snes, emu.memType.snesWorkRam)
emu.addMemoryCallback(function()
  finished = true
  log[#log + 1] = string.format('RETURN %d %s', frame, snapshot())
end, emu.callbackType.exec, cfg.finish, cfg.finish)
emu.addEventCallback(function()
  frame = frame + 1
  L.release()
  local buttons = {}
  for _, e in ipairs(cfg.events) do
    if frame >= e[1] and frame < e[1] + e[2] then buttons[e[3]] = true end
  end
  L.press(buttons)
  if frame == 1290 then log[#log + 1] = 'BEFORE ' .. snapshot() end
  if frame == 1370 then
    log[#log + 1] = 'AFTER ' .. snapshot()
    L.shot('cursor.png')
  end
  if frame == 1500 then
    log[#log + 1] = string.format('NAME %d %d', emu.read16(0x7FF000, m), emu.read16(0x7FF00A, m))
    log[#log + 1] = 'CURSOR ' .. tostring(emu.read(0xAD7, m))
    L.write('cursor.txt', table.concat(log, '\n') .. '\n')
    L.shot('end.png')
    emu.stop()
  end
end, emu.eventType.endFrame)
