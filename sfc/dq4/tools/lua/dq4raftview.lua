-- 배가 화면에 보이는지 본다(sfc/dq4/tools/dq4raftcheck.py 가 띄움). STATE 를 불러 WAIT 프레임 쉰 뒤
-- SHOT_DIR/view.txt 에 인물 슬롯 0~1F(X·Y·그림·33A0)와 OAM 128칸(X·Y·타일·속성, 높은 표의 X bit8·크기)을 적고 view.png 를 찍는다.
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local L = require("lib")
L.loadState(os.getenv("STATE"))
local m = emu.memType.snesMemory
local o = emu.memType.snesSpriteRam
local wait = tonumber(os.getenv("WAIT") or "30")
local f = 0
emu.addEventCallback(function()
  f = f + 1
  L.release()
  if f < wait then return end
  local t = {}
  for i = 0, 0x1F do
    t[#t + 1] = string.format("slot %02X %02X %02X %02X %02X", i, emu.read(0x7E3020 + i, m), emu.read(0x7E3080 + i, m),
      emu.read(0x7E3220 + i, m), emu.read(0x7E33A0 + i, m))
  end
  for i = 0, 127 do
    local hi = emu.read(0x200 + (i >> 2), o) >> ((i & 3) * 2) & 3
    t[#t + 1] = string.format("oam %02X %02X %02X %02X %02X %d", i, emu.read(4 * i, o), emu.read(4 * i + 1, o),
      emu.read(4 * i + 2, o), emu.read(4 * i + 3, o), hi)
  end
  L.write("view.txt", table.concat(t, "\n") .. "\n")
  L.shot("view.png")
  emu.stop(0)
end, emu.eventType.endFrame)
