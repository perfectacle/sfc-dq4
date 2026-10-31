-- 다른 프로브(WALKLUA)를 그대로 돌리며 서장 자동 대화의 시각을 SHOT_DIR/talkdelay.txt 에 적는다: 메시지 루틴(24:8BAF,
-- A = 번호) 진입, ▼ 대기(24:841F)·닫기 대기(00:982B)의 처음과 끝, NATIVE="이름=주소;…" 로 받은
-- 루틴 진입, 주인공(슬롯 0) 자리가 바뀐 프레임. 대기 루프는 프레임마다 다시 들어오므로 3프레임 넘게 끊겼을 때만 새로 적는다.
local n, out, last = 0, {}, {}
local m = emu.memType.snesMemory
local function save()
  local f = io.open(os.getenv("SHOT_DIR") .. "/talkdelay.txt", "w"); f:write(table.concat(out, "\n") .. "\n"); f:close()
end
local open = {}
local function episode(kind)
  if n - (last[kind] or -100) > 2 then out[#out + 1] = string.format("%d %s", n, kind) end
  last[kind] = n; open[kind] = true
end
emu.addMemoryCallback(function()
  out[#out + 1] = string.format("%d msg %03X", n, emu.getState()["cpu.a"] & 0xFFFF)
end, emu.callbackType.exec, 0x248BAF, 0x248BAF)
emu.addMemoryCallback(function() episode("wait") end, emu.callbackType.exec, 0x24841F, 0x24841F)
emu.addMemoryCallback(function() episode("close") end, emu.callbackType.exec, 0x00982B, 0x00982B)
for name, a in string.gmatch(os.getenv("NATIVE") or "", "([%w_]+)=(%x+)") do
  local addr = tonumber(a, 16)
  emu.addMemoryCallback(function() out[#out + 1] = string.format("%d call %s", n, name) end,
    emu.callbackType.exec, addr, addr)
end
local px, py
emu.addEventCallback(function()
  n = n + 1
  for kind, on in pairs(open) do
    if on and n - last[kind] > 2 then out[#out + 1] = string.format("%d %s-end", last[kind], kind); open[kind] = false end
  end
  local x, y = emu.read(0x7E3020, m), emu.read(0x7E3080, m)
  if x ~= px or y ~= py then out[#out + 1] = string.format("%d hero %d,%d", n, x, y); px, py = x, y end
end, emu.eventType.endFrame)
local stop = emu.stop
emu.stop = function(code) save(); stop(code) end
dofile(os.getenv("WALKLUA"))
