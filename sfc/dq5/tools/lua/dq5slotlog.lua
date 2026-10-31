-- 전투의 16x16 자리·조각 목록 할당(22:AC79)과 돌려받기(22:ADE7)를 적고 드라이버(boot.lua, 보통 dq5battle.lua)를 돌린다.
--   slots.txt  "프레임 alloc 그림 자리수 조각수 남은자리 남은조각 부른곳 연출"  22:AC79 에 들어설 때($0D1A·$0D19·$0D17·$0D1F·$0D27,
--              스택의 돌아갈 곳, 연출 번호 $0D14)와 받아들여 줄인 뒤("ok 남은자리 남은조각 첫자리", 22:AC87),
--              "프레임 free 무리칸 첫자리"(22:ADE7)
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local L = require("lib")
local m = emu.memType.snesMemory
local n, rows, written = 0, {}, 0
local function r(a) return emu.read(a, m) end
emu.addMemoryCallback(function()
  local sp = emu.getState()["cpu.sp"]
  rows[#rows + 1] = string.format("%d alloc %02X %d %d %d %d %02X%02X %02X", n, r(0x7E0D1A), r(0x7E0D19), r(0x7E0D17),
    r(0x7E0D1F), r(0x7E0D27), r((sp + 2) & 0xFFFF), r((sp + 1) & 0xFFFF), r(0x7E0D14))
end, emu.callbackType.exec, 0x22AC79, 0x22AC79)
emu.addMemoryCallback(function()
  rows[#rows + 1] = string.format("%d ok %d %d %d", n, r(0x7E0D1F), r(0x7E0D27), r(0x7E0D1D))
end, emu.callbackType.exec, 0x22AC87, 0x22AC87)
emu.addMemoryCallback(function()
  rows[#rows + 1] = string.format("%d free %d %d", n, emu.getState()["cpu.x"] & 0xFF, r(0x7E0D4D + (emu.getState()["cpu.x"] & 0xFF)))
end, emu.callbackType.exec, 0x22ADE7, 0x22ADE7)
emu.addEventCallback(function()
  n = n + 1
  if #rows > written and n % 30 == 0 then L.write("slots.txt", table.concat(rows, "\n") .. "\n"); written = #rows end
end, emu.eventType.endFrame)
dofile(os.getenv("LIBDIR") .. "/boot.lua")
