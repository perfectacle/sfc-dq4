-- 필드에서 입구로 들어가는 길을 잰다. 계단 판정(00:E2C5) 뒤 $198F 를 보는 00:C7C6, 일반 입구 00:C7DD(→ 2A:F230 → 2A:F247),
-- 보조 입구 2A:FDCB 를 지날 때 프레임·$B6·$B8·맵($BC·$BD)·$198F 와 두 셀의 +4·+7(7E:3740·3760·3780·37A0)을
-- entry.txt 에 적고 DRIVER(보통 dq5warp.lua)를 돌린다. 2A:FDCB 는 처음 SKIPFDCB(기본 0)번을 뺀 뒤 바뀔 때만 적는다.
package.path = os.getenv('LIBDIR') .. '/?.lua;' .. package.path
local L = require('lib')
local m = emu.memType.snesMemory
local log, n, last = {}, 0, nil
local function w16(a) return emu.read(a, m) | emu.read(a + 1, m) << 8 end
local function row(tag)
  return string.format('f%d %s B6=%d B8=%d map=%02X/%02X 198F=%02X cells=%02X,%02X,%02X,%02X', n, tag, w16(0x7E00B6),
    w16(0x7E00B8), emu.read(0x7E00BC, m), emu.read(0x7E00BD, m), emu.read(0x7E198F, m), emu.read(0x7E3740, m),
    emu.read(0x7E3760, m), emu.read(0x7E3780, m), emu.read(0x7E37A0, m))
end
for _, s in ipairs({{0x00C7C6, 'stair'}, {0x00C7DD, 'normal'}, {0x2AF247, 'f247'}}) do
  emu.addMemoryCallback(function()
    local r = row(s[2])
    if s[2] ~= 'stair' or emu.read(0x7E198F, m) ~= 0 then log[#log + 1] = r end
  end, emu.callbackType.exec, s[1], s[1])
end
emu.addMemoryCallback(function()
  local key = string.format('%d,%d', w16(0x7E00B6), w16(0x7E00B8))
  if key ~= last then last = key; log[#log + 1] = row('fdcb') end
end, emu.callbackType.exec, 0x2AFDCB, 0x2AFDCB)
emu.addEventCallback(function()
  n = n + 1
  if n % 30 == 0 then L.write('entry.txt', table.concat(log, '\n') .. '\n') end
end, emu.eventType.endFrame)
dofile(os.getenv('DRIVER'))
