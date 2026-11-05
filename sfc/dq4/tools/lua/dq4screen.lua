-- 화면 기준 비교(dq4screens.py)용 장면 드라이버. STATE 세이브스테이트(없으면 전원을 켠 상태)에서 SET(첫 프레임에 한 번,
-- 7E 뱅크 주소=값)·POKE(매 프레임 고정, CPU 주소=값)를 걸고 PRE 입력("a:4,wait:30" 꼴, + 로 함께 누름)을 재생한다.
--   SCREENS="300,400"  그 프레임 끝의 화면을 SHOT_DIR/screen-NNNNN.rgb 로. 머리 8바이트(너비·높이, u32 little)에 이어 픽셀마다
--                      R·G·B. emu.getScreenBuffer 는 그 프레임의 PPU 화면을 바로 읽는다(emu.takeScreenshot 은 따로 도는
--                      화면 디코더가 마지막으로 그린 것이라 실행마다 다를 수 있다)
--   PNGS="300"         확인용으로 그 프레임의 takeScreenshot 도 SHOT_DIR/shot-NNNNN.png 로(비교에는 쓰지 않음)
-- 마지막 SCREENS 프레임 다음 프레임에 멈춘다.
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local L = require("lib")
if os.getenv("STATE") then L.loadState(os.getenv("STATE")) end
local m = emu.memType.snesMemory
local dir = os.getenv("SHOT_DIR")
local seq, sets, pokes, screens, pngs = {}, {}, {}, {}, {}
for tok in string.gmatch(os.getenv("PRE") or "", "[^,]+") do
  local b, f = tok:match("([%w+]+):(%d+)")
  seq[#seq + 1] = {b, tonumber(f)}
end
for a, v in string.gmatch(os.getenv("SET") or "", "(%x+)=(%x+)") do sets[#sets + 1] = {tonumber(a, 16), tonumber(v, 16)} end
for a, v in string.gmatch(os.getenv("POKE") or "", "(%x+)=(%x+)") do pokes[#pokes + 1] = {tonumber(a, 16), tonumber(v, 16)} end
local last = 0
for a in string.gmatch(os.getenv("SCREENS") or "", "%d+") do
  screens[tonumber(a)] = true
  last = math.max(last, tonumber(a))
end
for a in string.gmatch(os.getenv("PNGS") or "", "%d+") do pngs[tonumber(a)] = true end

local function dump(path)
  local buf = emu.getScreenBuffer()
  local size = emu.getScreenSize()
  assert(#buf == size.width * size.height, "화면 버퍼 크기가 화면 크기와 다름")
  local f = assert(io.open(path, "wb"))
  f:write(string.pack("<I4I4", size.width, size.height))
  local parts = {}
  for i = 1, #buf do
    local v = buf[i]
    parts[#parts + 1] = string.char((v >> 16) & 0xFF, (v >> 8) & 0xFF, v & 0xFF)
    if #parts >= 4096 then
      f:write(table.concat(parts))
      parts = {}
    end
  end
  f:write(table.concat(parts))
  f:close()
end

local n, si, left = 0, 1, nil
emu.addEventCallback(function()
  n = n + 1
  if n == 1 then
    for _, s in ipairs(sets) do emu.write(0x7E0000 | s[1], s[2], m) end
  end
  for _, p in ipairs(pokes) do emu.write(p[1], p[2], m) end
  L.release()
  if si <= #seq then
    local s = seq[si]
    if left == nil then left = s[2] end
    if s[1] ~= "wait" then
      local t = {}
      for b in s[1]:gmatch("[^+]+") do t[b] = true end
      L.press(t)
    end
    left = left - 1
    if left <= 0 then
      si = si + 1
      left = nil
    end
  end
  if screens[n] then dump(string.format("%s/screen-%05d.rgb", dir, n)) end
  if pngs[n] then L.shot(string.format("shot-%05d.png", n)) end
  if n > last then emu.stop(0) end
end, emu.eventType.endFrame)
