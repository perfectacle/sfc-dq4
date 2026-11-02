-- 환경 훅 wrap(15:F7D0 을 부르는 01:8F84·01:98FC·01:9FD6 자리를 대신함)이 돌 때마다 부른 자리·$BE·$BC/$BD 를,
-- 돌아온 뒤 7E:1AA6~1AA8(매 프레임 루틴)을 SHOT_DIR/wrap.txt 에 적는다. dq4wrapcheck.py 가 부른다.
--   WRAP="3DE5CB"           wrap 의 주소(01:8F84 의 JSL 피연산자)
--   WARPLUA=…/dq5warp.lua   있으면 그대로 돌린다(그 환경 변수는 dq5warp.lua 대로). 없으면 STATE 에서 DIR 쪽으로
--                           WALKF 프레임 걷고 60프레임 뒤 SAVE 로 남긴다
--   ENTRANCE="3C80EC" ARRIVALS="3C9000"
--                           dq5warp.lua 가 필드 입구를 덮는 자리(원본 04:FE83·0F:EA97)를 이 롬이 읽는 표로 돌린다.
--                           1장 롬은 두 표를 옮겼다(2A:FE12·2A:F394 의 피연산자)
--   RELOAD=N                N 프레임에 조우 판정 23:E7C2 를 한 번만 00:C71F 로 돌린다. 00:C71F 는 지금 맵을 그 자리에서
--                           다시 푸는 길(01:98D0 → 01:98FC)이고, 원래는 DQ5 사건 코드만 부른다
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local L = require("lib")
local m = emu.memType.snesMemory
local prg = emu.memType.snesPrgRom
local wrap = tonumber(os.getenv("WRAP"), 16)
local f = assert(io.open(os.getenv("SHOT_DIR") .. "/wrap.txt", "w"))
local frame = 0
local function rd(a) return emu.read(a, m) end
local function r24(a) return rd(a) | rd(a + 1) << 8 | rd(a + 2) << 16 end
local function put(s) f:write(s .. "\n"); f:flush() end

local lastBE = -1
emu.addEventCallback(function()
  frame = frame + 1
  local be = rd(0x7E00BE)
  if be ~= lastBE then put(string.format("f%05d BE -> %02X", frame, be)); lastBE = be end
end, emu.eventType.endFrame)

emu.addMemoryCallback(function()
  local sp = emu.getState()["cpu.sp"] & 0xFFFF
  -- JSL 이 쌓은 돌아갈 자리 - 1 에서 JSL 첫 바이트 자리로
  local from = (rd(sp + 1) | rd(sp + 2) << 8 | rd(sp + 3) << 16) - 3
  put(string.format("f%05d wrap from %06X BE=%02X BC=%02X BD=%02X 1AA6=%06X", frame, from, rd(0x7E00BE),
    rd(0x7E00BC), rd(0x7E00BD), r24(0x7E1AA6)))
end, emu.callbackType.exec, wrap, wrap)
for _, a in ipairs({0x018F88, 0x019900, 0x019FDA}) do
  emu.addMemoryCallback(function()
    put(string.format("f%05d back %06X BE=%02X BC=%02X BD=%02X 1AA6=%06X", frame, a, rd(0x7E00BE), rd(0x7E00BC),
      rd(0x7E00BD), r24(0x7E1AA6)))
  end, emu.callbackType.exec, a, a)
end

local reload = tonumber(os.getenv("RELOAD") or "0")
local ENCOUNTER = 0x11E7C2
local saved = nil
emu.addEventCallback(function()
  if reload > 0 and frame == reload then
    saved = {}
    for i = 0, 4 do saved[i] = emu.read(ENCOUNTER + i, prg) end
    -- CLC / JML $00C71F: 00:C71F 가 PHP·PLP 로 C=0 을 돌려주어 조우 판정은 「만나지 않음」 으로 끝난다
    for i, b in ipairs({0x18, 0x5C, 0x1F, 0xC7, 0x00}) do emu.write(ENCOUNTER + i - 1, b, prg) end
    put(string.format("f%05d reload armed", frame))
  end
end, emu.eventType.startFrame)
emu.addMemoryCallback(function()
  if saved then
    for i = 0, 4 do emu.write(ENCOUNTER + i, saved[i], prg) end
    saved = nil
    put(string.format("f%05d reload BE=%02X BC=%02X BD=%02X", frame, rd(0x7E00BE), rd(0x7E00BC), rd(0x7E00BD)))
  end
end, emu.callbackType.exec, 0x00C71F, 0x00C71F)

local function lorom(a) return ((a >> 16) & 0x7F) * 0x8000 + (a & 0x7FFF) end
local entrance = tonumber(os.getenv("ENTRANCE") or "", 16)
local arrivals = tonumber(os.getenv("ARRIVALS") or "", 16)
if entrance or arrivals then
  local write = emu.write
  emu.write = function(addr, value, mem)
    if mem == prg then
      if entrance and addr >= 0x27E83 and addr < 0x27E88 then addr = lorom(entrance) + addr - 0x27E83
      elseif arrivals and addr >= 0x7EA97 and addr < 0x7EA97 + 0x100 * 5 then addr = lorom(arrivals) + addr - 0x7EA97 end
    end
    return write(addr, value, mem)
  end
end

local warp = os.getenv("WARPLUA")
if warp and warp ~= "" then
  dofile(warp)
  return
end

L.loadState(os.getenv("STATE"))
for off, hex in string.gmatch(os.getenv("ROMPATCH") or "", "(%x+)=(%x+)") do
  for i = 0, #hex / 2 - 1 do emu.write(tonumber(off, 16) + i, tonumber(hex:sub(i * 2 + 1, i * 2 + 2), 16), prg) end
end
local dir, walkf = os.getenv("DIR") or "down", tonumber(os.getenv("WALKF") or "60")
emu.addEventCallback(function()
  if frame < walkf then L.press({[dir] = true}) else L.release() end
  if frame == walkf + 60 then
    L.saveState(os.getenv("SAVE"))
    put(string.format("f%05d end map %02X/%02X BE=%02X field %d,%d", frame, rd(0x7E00BC), rd(0x7E00BD), rd(0x7E00BE),
      rd(0x7E00B6) | rd(0x7E00B7) << 8, rd(0x7E00B8) | rd(0x7E00B9) << 8))
  end
  if frame == walkf + 62 then emu.stop(0) end
end, emu.eventType.endFrame)
