-- dq4menucursorcheck.py 가 부른다. 전원부터 A·Y 를 눌러 1장 첫 맵에 선 뒤(BOOT 프레임까지), 그 뒤 프레임 기준
-- 이벤트(MENU_CURSOR_CASE)대로 실제 패드를 누르며 커서 색인 $0AD7 이 바뀔 때마다 프레임·창 번호 $0A00 과 함께 적는다.
package.path = os.getenv('LIBDIR') .. '/?.lua;' .. package.path
local L = require('lib')
local cfg = dofile(os.getenv('MENU_CURSOR_CASE'))
local m = emu.memType.snesMemory
for a = 0, 0x1FFF do emu.write(a, 0, emu.memType.snesSaveRam) end
local frame, log = 0, {}
emu.addMemoryCallback(function(a, value)
  local old = emu.read(0xAD7, m)
  if frame > cfg.boot and value ~= old then
    log[#log + 1] = string.format('MOVE %d %d %d %02X', frame - cfg.boot, old, value, emu.read(0xA00, m))
  end
end, emu.callbackType.write, 0xAD7, 0xAD7, emu.cpuType.snes, emu.memType.snesWorkRam)
emu.addEventCallback(function()
  frame = frame + 1
  L.release()
  local t = frame - cfg.boot
  if t <= 0 then
    if frame % 40 < 4 and frame < cfg.boot - 600 then
      if (frame // 40) % 6 == 5 then L.press({y = true}) else L.press({a = true}) end
    elseif frame > cfg.boot - 600 and frame < cfg.boot - 300 and frame % 30 < 4 then
      L.press({b = true})
    end
    return
  end
  local buttons = {}
  for _, e in ipairs(cfg.events) do
    if t >= e[1] and t < e[1] + e[2] then buttons[e[3]] = true end
  end
  L.press(buttons)
  if t == cfg.shot then L.shot('menu.png') end
  if t == cfg.stop then
    L.write('cursor.txt', table.concat(log, '\n') .. '\n')
    emu.stop()
  end
end, emu.eventType.endFrame)
