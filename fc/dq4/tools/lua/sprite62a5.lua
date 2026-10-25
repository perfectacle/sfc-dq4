-- 08:$85BE(그림 번호 → 표 번호에서 $62A5 를 읽는 곳)에서만 $62A5 bit7 을 켜 보이고, 읽은 직후($85C1) 원래 값으로 되돌린다.
-- 엔딩 장면 플래그를 다른 루틴에 퍼뜨리지 않고 그림 고르기에만 주는 실험용. 입력은 DRIVER(예: warp.lua)가 맡는다.
-- 결과: SHOT_DIR/62a5.txt(50프레임마다 다시 씀) — 그 자리를 지날 때마다 「<프레임> A=<그림 번호> 62A5=<원래 값> 615C=<값>」
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local L = require("lib")
local AT, AFTER = 0x08 * 0x4000 + 0x05BE, 0x08 * 0x4000 + 0x05C1
local n, saved, log = 0, nil, {}
emu.addMemoryCallback(function(addr)
  if L.prgOffset(addr) ~= AT then return end
  saved = emu.read(0x62A5, L.mem)
  local st = emu.getState()
  log[#log + 1] = string.format("%d A=%02X 62A5=%02X 615C=%02X", n, st["cpu.a"], saved, emu.read(0x615C, L.mem))
  emu.write(0x62A5, saved | 0x80, L.mem)
end, emu.callbackType.exec, 0x85BE, 0x85BE)
emu.addMemoryCallback(function(addr)
  if saved == nil or L.prgOffset(addr) ~= AFTER then return end
  emu.write(0x62A5, saved, L.mem)
  saved = nil
end, emu.callbackType.exec, 0x85C1, 0x85C1)
emu.addEventCallback(function()
  n = n + 1
  if n % 50 == 0 then L.write("62a5.txt", table.concat(log, "\n") .. "\n") end
end, emu.eventType.endFrame)
L.drive()
