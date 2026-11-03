-- dq4readsetcheck 의 콜백 장면. 머리말이 콜백을 감싸도 장면이 add 로 받은 번호로 지우면 지워져야 하고, 지운 뒤로는
-- 불리지 않아야 한다. 10프레임째 지우고 40프레임째 SHOT_DIR/callbacks.txt 에 센 값을 적는다.
local mem, ev, n = 0, 0, 0
local mref = emu.addMemoryCallback(function() mem = mem + 1 end, emu.callbackType.exec, 0x008000, 0x00FFFF)
local eref = emu.addEventCallback(function() ev = ev + 1 end, emu.eventType.endFrame)
local m10, e10
emu.addEventCallback(function()
  n = n + 1
  if n == 10 then
    m10, e10 = mem, ev
    emu.removeMemoryCallback(mref, emu.callbackType.exec, 0x008000, 0x00FFFF)
    emu.removeEventCallback(eref, emu.eventType.endFrame)
  end
  if n == 40 then
    local f = assert(io.open(os.getenv("SHOT_DIR") .. "/callbacks.txt", "w"))
    f:write(string.format("%d %d %d %d\n", m10, mem, e10, ev))
    f:close()
    emu.stop(0)
  end
end, emu.eventType.endFrame)
