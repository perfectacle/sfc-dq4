-- たびびとのちず 세계 지도 화면(03:C8B3)이 점을 만드는 동안의 시간을 잰다. 드라이버(boot.lua, 보통 dq5warp.lua)의 입력을
-- 재생하며 점 루프 03:CAC2 의 점 하나(03:CAC5 JSR $CB07 → 03:CAC8)와 블록 번호 루틴 00:BDC5(→ 00:BE16 RTS)를
-- 부를 때마다 마스터 클록(emu.getState() 의 masterClock)을 더하고, 처음·마지막 프레임과 횟수를 적는다.
-- DUMPF 프레임에는 dq5gfxdump.lua 처럼 WRAM·VRAM·CGRAM 을 덤프한다.
-- 결과: SHOT_DIR/mapdots.txt 「이름 횟수 첫프레임 끝프레임 마스터클록합」, fNNNNN.wram·.vram·.cgram·.png
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local L = require("lib")
local dumpf = {}
for a in string.gmatch(os.getenv("DUMPF") or "", "[^,]+") do dumpf[tonumber(a)] = true end
local n = 0
local spans = {
  {name = "dot", from = 0x03CAC5, to = 0x03CAC8},
  {name = "bdc5", from = 0x00BDC5, to = 0x00BE16},
}

local function report()
  local t = {}
  for _, s in ipairs(spans) do
    t[#t + 1] = string.format("%s %d %d %d %d", s.name, s.count or 0, s.first or -1, s.last or -1, s.sum or 0)
  end
  L.write("mapdots.txt", table.concat(t, "\n") .. "\n")
end

for _, s in ipairs(spans) do
  s.count, s.sum = 0, 0
  emu.addMemoryCallback(function()
    s.start = emu.getState()["masterClock"]
  end, emu.callbackType.exec, s.from, s.from)
  emu.addMemoryCallback(function()
    if s.start then
      s.sum = s.sum + emu.getState()["masterClock"] - s.start
      s.count = s.count + 1
      s.first = s.first or n
      s.last = n
      s.start = nil
    end
  end, emu.callbackType.exec, s.to, s.to)
end

emu.addEventCallback(function()
  n = n + 1
  if dumpf[n] then
    local tag = string.format("f%05d", n)
    L.dump(tag .. ".wram", emu.memType.snesWorkRam, 0x20000)
    L.dump(tag .. ".cgram", emu.memType.snesCgRam, 0x200)
    L.dump(tag .. ".vram", emu.memType.snesVideoRam, 0x10000)
    L.shot(tag .. ".png")
    report()
  end
end, emu.eventType.endFrame)
dofile(os.getenv("LIBDIR") .. "/boot.lua")
