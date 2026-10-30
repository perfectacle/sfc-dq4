-- 탈것 슬롯(7E:3220 = FE)을 그리는 00:FC08 이 고른 칸 블록을 센다. 드라이버(boot.lua, 보통 dq5warp.lua)를 돌리면서
-- 00:FC60(방향까지 더한 첫 칸 주소를 $AE 에 둔 뒤)마다 슬롯(Y)·칸 목록 첫 주소(7E:8000[7E:3200[슬롯]])·방향(3240)·프레임(3280)과
-- 가로·세로 칸 수(34E0·3500)·간격(37C0·37E0)·마지막 프레임(32A0)을 모아 FROM~UNTIL 프레임에 한 줄씩 센다.
--   FROM=600 UNTIL=1400   셀 프레임 범위
-- 결과: SHOT_DIR/blocks.txt — "슬롯 칸목록주소 가로x세로 37C0 37E0 32A0 오프셋(바이트) 방향 프레임 횟수" 줄들
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local L = require("lib")
local m = emu.memType.snesMemory
local from = tonumber(os.getenv("FROM") or "600")
local untilf = tonumber(os.getenv("UNTIL") or "1400")
local n, seen, order = 0, {}, {}

local function rd(a) return emu.read(a, m) end
local function rd16(a) return rd(a) | rd(a + 1) << 8 end

emu.addMemoryCallback(function()
  if n < from or n > untilf then return end
  local s = emu.getState()
  local y = s["cpu.y"] & 0xFF
  if rd(0x7E3220 + y) ~= 0xFE then return end
  local base = rd16(0x7E8000 + rd(0x7E3200 + y))
  local key = string.format("%02X %04X %dx%d %02X %02X %02X %d %X %X", y, base, rd(0x7E34E0 + y), rd(0x7E3500 + y),
    rd(0x7E37C0 + y), rd(0x7E37E0 + y), rd(0x7E32A0 + y), rd16(s["cpu.d"] + 0xAE) - base, rd(0x7E3240 + y) & 0x0F,
    rd(0x7E3280 + y))
  if not seen[key] then seen[key] = 0; order[#order + 1] = key end
  seen[key] = seen[key] + 1
end, emu.callbackType.exec, 0x00FC60, 0x00FC60)

emu.addEventCallback(function()
  n = n + 1
  if n == untilf + 1 then
    local out = {}
    table.sort(order)
    for _, k in ipairs(order) do out[#out + 1] = k .. " " .. seen[k] end
    L.write("blocks.txt", table.concat(out, "\n") .. "\n")
  end
end, emu.eventType.endFrame)
dofile(os.getenv("LIBDIR") .. "/boot.lua")
