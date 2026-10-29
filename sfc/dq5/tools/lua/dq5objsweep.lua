-- DQ5: dq5warp.lua(boot.lua)로 맵(TO)에 들어가, 그 맵에 있는 동안 매 프레임 화면에 보이는 OAM 의 팔레트별 수,
-- 인물 슬롯 수(7E:3220 이 A9 미만), OBJ VRAM 다음 타일 $1995 를 모은다. dq5warp 가 warp.txt 를 쓸 때
-- objsweep.txt 와 끝 프레임의 OAM·VRAM 을 함께 남긴다(WRAM·CGRAM 은 dq5warp 의 final.*).
--   objsweep.txt: frames=N(그 맵에 있던 프레임, 앞 SKIP 프레임 포함), slots=최대 인물 슬롯 수, sets=그때의 그림 번호들,
--                 gfx=센 프레임 모두에 나온 그림 번호(합집합),
--                 v1995=최대 $1995, v1997=$1997, pal<p>=<보인 OAM 수 합>, tile<p>=<그 팔레트 OAM 의 가장 큰 타일 번호>
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local L = require("lib")
local m = emu.memType.snesMemory
local oam = emu.memType.snesSpriteRam
local bc, bd = string.match(os.getenv("TO") or "", "^(%x%x)/(%x%x)")
bc, bd = tonumber(bc or "FF", 16), tonumber(bd or "FF", 16)

-- 맵 번호가 바뀐 뒤 한동안은 앞 맵의 슬롯·$1995 가 남아 있다(인물을 다 놓기 전). 그동안은 세지 않는다.
local SKIP = 60
local frames, slots, sets, v1995 = 0, 0, "", 0
local pals, tiles, seen = {}, {}, {}
for p = 0, 7 do pals[p] = 0; tiles[p] = -1 end

emu.addEventCallback(function()
  if emu.read(0x7E00BC, m) ~= bc or emu.read(0x7E00BD, m) ~= bd or emu.read(0x7E00BE, m) & 0x80 == 0 then return end
  frames = frames + 1
  if frames <= SKIP then return end
  local n, g = 0, {}
  for s = 0, math.min(emu.read(0x7E1983, m), 0x20) - 1 do
    local v = emu.read(0x7E3220 + s, m)
    if v < 0xA9 then n = n + 1; g[#g + 1] = string.format("%02X", v); seen[v] = true end
  end
  if n > slots then slots = n; sets = table.concat(g, " ") end
  local v = emu.read(0x7E1995, m) | emu.read(0x7E1996, m) << 8
  if v > v1995 then v1995 = v end
  for i = 0, 127 do
    local y = emu.read(i * 4 + 1, oam)
    if y < 0xE0 then
      local a = emu.read(i * 4 + 3, oam)
      local p = (a >> 1) & 7
      local t = emu.read(i * 4 + 2, oam) | (a & 1) << 8
      pals[p] = pals[p] + 1
      if t > tiles[p] then tiles[p] = t end
    end
  end
end, emu.eventType.endFrame)

local write = L.write
L.write = function(name, data)
  if name == "warp.txt" then
    local all = {}
    for v in pairs(seen) do all[#all + 1] = string.format("%02X", v) end
    table.sort(all)
    local t = {string.format("frames=%d", frames), string.format("slots=%d", slots), "sets=" .. sets,
               "gfx=" .. table.concat(all, " "),
               string.format("v1995=%d", v1995),
               string.format("v1997=%d", emu.read(0x7E1997, m) | emu.read(0x7E1998, m) << 8)}
    for p = 0, 7 do t[#t + 1] = string.format("pal%d=%d", p, pals[p]); t[#t + 1] = string.format("tile%d=%d", p, tiles[p]) end
    write("objsweep.txt", table.concat(t, "\n") .. "\n")
    L.dump("final.oam", oam, 0x220)
    L.dump("final.vram", emu.memType.snesVideoRam, 0x10000)
  end
  return write(name, data)
end
dofile(os.getenv("LIBDIR") .. "/boot.lua")
