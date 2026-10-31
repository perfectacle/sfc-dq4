-- 배를 탄 채($1954 = 3) 바다 구역 직사각형(01:85D8)을 고르는 01:8590 의 01:85A9(좌표 견주기 첫머리)를 지날 때마다 프레임·$B6·$B8·$1948 과 고른 구역(01:85D1 의 A),
-- 조우 구역 23:E7C2 의 A 를 sea.txt 에 적고 DRIVER(보통 dq5warp.lua)를 돌린다.
package.path = os.getenv('LIBDIR') .. '/?.lua;' .. package.path
local L = require('lib')
local m = emu.memType.snesMemory
local log, n = {}, 0
local function w16(a) return emu.read(a, m) | emu.read(a + 1, m) << 8 end
emu.addMemoryCallback(function()
  log[#log + 1] = string.format('f%d rect B6=%d B8=%d 1948=%d', n, w16(0x7E00B6), w16(0x7E00B8), emu.read(0x7E1948, m))
end, emu.callbackType.exec, 0x0185A9, 0x0185A9)
emu.addMemoryCallback(function()
  log[#log + 1] = string.format('f%d area %02X', n, emu.getState()['cpu.a'] & 0xFF)
end, emu.callbackType.exec, 0x0185D1, 0x0185D1)
emu.addMemoryCallback(function()
  log[#log + 1] = string.format('f%d e7c2 %02X', n, emu.getState()['cpu.a'] & 0xFF)
end, emu.callbackType.exec, 0x23E7C2, 0x23E7C2)
emu.addEventCallback(function()
  n = n + 1
  if n % 60 == 0 then L.write('sea.txt', table.concat(log, '\n') .. '\n') end
end, emu.eventType.endFrame)
dofile(os.getenv('DRIVER'))
