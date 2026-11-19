-- dq4boxplay.py 가 부른다. WARPLUA(dq5warp.lua)를 돌리며 EVERY 프레임마다 화면(emu.getScreenBuffer)에 GOLD(RRGGBB 16진) 점이
-- 있으면 그 화면을 SHOT_DIR/box.rgb 에 붙인다. 화면마다 머리 12바이트(프레임·너비·높이, u32 little)에 이어 픽셀마다 R·G·B.
-- PNG 를 장마다 쓰지 않는 까닭: 장면마다 수백 장이 생기면 macOS 색인·그림 분석이 머신을 잡아먹는다
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local every = tonumber(os.getenv("EVERY") or "6")
local gold = tonumber(os.getenv("GOLD"), 16)
local out = assert(io.open(os.getenv("SHOT_DIR") .. "/box.rgb", "wb"))
local n = 0
emu.addEventCallback(function()
  n = n + 1
  if n % every ~= 0 then return end
  local buf = emu.getScreenBuffer()
  local hit = false
  for i = 1, #buf do
    if buf[i] & 0xFFFFFF == gold then hit = true; break end
  end
  if not hit then return end
  local size = emu.getScreenSize()
  out:write(string.pack("<I4I4I4", n, size.width, size.height))
  local parts = {}
  for i = 1, #buf do
    local v = buf[i]
    parts[#parts + 1] = string.char((v >> 16) & 0xFF, (v >> 8) & 0xFF, v & 0xFF)
    if #parts >= 4096 then out:write(table.concat(parts)); parts = {} end
  end
  out:write(table.concat(parts))
  out:flush()
end, emu.eventType.endFrame)
dofile(os.getenv("WARPLUA"))
