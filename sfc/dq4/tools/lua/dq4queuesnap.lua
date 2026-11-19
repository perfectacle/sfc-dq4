-- dq5msg.lua 장면에 덧붙여, QSNAP(24비트 PC)을 지날 때 레지스터와 WRAM 128KB 를 SHOT_DIR/qNNNN.bin 으로 뜬다.
--   QSNAP="60D536"  QSNAPFROM=300  QSNAPTO=400  QSNAPMAX=40
-- 파일 꼴: 머리 32바이트(프레임 4, A·X·Y·S·D 2씩, DBR·P·PBR 1씩, PC 2, 나머지 0) + WRAM 7E:0000~7F:FFFF.
-- 장면 자체는 dq5msg.lua 가 돈다(같은 환경 변수).
local here = debug.getinfo(1, "S").source:match("^@(.*)/[^/]*$")
local addr = tonumber(assert(os.getenv("QSNAP"), "QSNAP"), 16)
local from = tonumber(os.getenv("QSNAPFROM") or "0")
local to = tonumber(os.getenv("QSNAPTO") or "1000000")
local max = tonumber(os.getenv("QSNAPMAX") or "40")
local dir = assert(os.getenv("SHOT_DIR"), "SHOT_DIR")
local frame, taken = 0, 0
emu.addEventCallback(function() frame = frame + 1 end, emu.eventType.endFrame)
local function w16(t, v) t[#t + 1] = string.char(v & 0xFF, (v >> 8) & 0xFF) end
emu.addMemoryCallback(function()
  if frame < from or frame > to or taken >= max then return end
  local s = emu.getState()
  local t = {string.char(frame & 0xFF, (frame >> 8) & 0xFF, (frame >> 16) & 0xFF, 0)}
  w16(t, s["cpu.a"]); w16(t, s["cpu.x"]); w16(t, s["cpu.y"]); w16(t, s["cpu.sp"]); w16(t, s["cpu.d"])
  t[#t + 1] = string.char(s["cpu.dbr"], s["cpu.ps"], s["cpu.k"])
  w16(t, s["cpu.pc"])
  t[#t + 1] = string.rep("\0", 32 - 19)
  local kind = emu.memType.snesWorkRam
  for i = 0, 0x1FFFF do t[#t + 1] = string.char(emu.read(i, kind)) end
  local f = assert(io.open(string.format("%s/q%04d.bin", dir, taken), "wb"))
  f:write(table.concat(t))
  f:close()
  taken = taken + 1
end, emu.callbackType.exec, addr, addr)
dofile(here .. "/../../../dq5/tools/lua/dq5msg.lua")
