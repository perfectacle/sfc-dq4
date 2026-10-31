-- 다른 걷기 프로브(WALKLUA)를 그대로 돌리며, 메시지 루틴(24:8BAF, A = 번호)·▼ 대기(24:841F)·닫기 대기(00:982B,
-- 명령 21·34·이벤트 60·대화 끝이 창을 닫기 전에 A 를 기다림) 진입을 프레임과 함께 SHOT_DIR/msgcount.txt 에 적는다.
-- 닫기 대기는 그때의 횟수 $11(0 이면 A 까지 기다림)도 적는다. 대기 루프는 프레임마다 다시 들어오므로 3프레임 넘게
-- 끊겼을 때만 새 대기로 센다.
local n, out, last = 0, {}, {}
local function save()
  local f = io.open(os.getenv("SHOT_DIR") .. "/msgcount.txt", "w"); f:write(table.concat(out, "\n") .. "\n"); f:close()
end
local function episode(kind, extra)
  if n - (last[kind] or -100) > 2 then out[#out + 1] = string.format("%d %s%s", n, kind, extra or "") end
  last[kind] = n
end
emu.addMemoryCallback(function()
  out[#out + 1] = string.format("%d msg %03X", n, emu.getState()["cpu.a"] & 0xFFFF)
end, emu.callbackType.exec, 0x248BAF, 0x248BAF)
emu.addMemoryCallback(function() episode("wait") end, emu.callbackType.exec, 0x24841F, 0x24841F)
emu.addMemoryCallback(function()
  episode("close", string.format(" %02X", emu.read(0x7E0011, emu.memType.snesMemory)))
end, emu.callbackType.exec, 0x00982B, 0x00982B)
emu.addEventCallback(function() n = n + 1 end, emu.eventType.endFrame)
local stop = emu.stop
emu.stop = function(code) save(); stop(code) end
dofile(os.getenv("WALKLUA"))
