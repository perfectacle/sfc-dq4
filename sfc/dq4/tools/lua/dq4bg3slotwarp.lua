-- dq4bg3slotcheck.py 가 부른다. dq5warp.lua(WARPLUA)를 돌리며 30프레임마다 맵 번호와 BG3SC 그림자 $0725,
-- 그 자리 BG3 타일맵 2KB 의 0 아닌 바이트 수, 화면에 쓰는 자리의 타일맵이 버퍼 7E:5000 과 다른 바이트 수,
-- 타일맵이 1C00 을 떠날 때 찍어 둔 옛 자리(VRAM 바이트 3800~3FFF)에서 그 뒤 바뀐 바이트 수를 SHOT_DIR/bg3.txt 에 덮어쓰고,
-- SHOTS 프레임 화면을 sNNNNN.png 로 남긴다. 30프레임마다 VRAM 64KB(vram.bin), OAM 544바이트(oam.bin), PPU 상태(ppu.txt,
-- 첫 줄 frame=N)를 덮어써, 두 롬의 같은 프레임을 견줄 수 있게 한다.
-- 게임이 버퍼를 고친 프레임은 NMI 가 아직 보내지 않아 버퍼와 VRAM 이 잠깐 다르다. 그래서 30프레임째에 바로 적지 않고,
-- 버퍼가 STILL 프레임 동안 바뀌지 않은 첫 프레임에 적는다(still= 에 그 프레임 수).
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local L = require("lib")
local m = emu.memType.snesMemory
local vram = emu.memType.snesVideoRam
local shots = {}
for a in string.gmatch(os.getenv("SHOTS") or "", "%d+") do shots[tonumber(a)] = true end
local STILL = 2
local n, log, snap = 0, {}, nil
local sum, still, due = nil, 0, false

local function bufferSum()
  local s = 0
  for i = 0, 0x7FF do s = (s * 31 + emu.read(0x7E5000 + i, m)) % 0x7FFFFFFF end
  return s
end

emu.addEventCallback(function()
  n = n + 1
  if shots[n] then L.shot(string.format("s%05d.png", n)) end
  if n % 30 == 0 then
    local dir = os.getenv("SHOT_DIR")
    local t = {}
    for i = 0, 0xFFFF do t[#t + 1] = string.char(emu.read(i, vram)) end
    local f = io.open(dir .. "/vram.bin", "wb"); f:write(table.concat(t)); f:close()
    t = {}
    for i = 0, 543 do t[#t + 1] = string.char(emu.read(i, emu.memType.snesSpriteRam)) end
    f = io.open(dir .. "/oam.bin", "wb"); f:write(table.concat(t)); f:close()
    f = io.open(dir .. "/ppu.txt", "w"); f:write("frame=", n, "\n")
    for key, v in pairs(emu.getState()) do
      if string.find(key, "^ppu%.") then f:write(key, "=", tostring(v), "\n") end
    end
    f:close()
  end
  local now = bufferSum()
  if now == sum then still = still + 1 else still = 0 end
  sum = now
  if n % 30 == 0 then due = true end
  if not due or still < STILL then return end
  due = false
  local sc = emu.read(0x7E0725, m)
  local base, nz = (sc & 0xFC) * 0x200, 0
  for i = base, base + 0x7FF do if emu.read(i, vram) ~= 0 then nz = nz + 1 end end
  -- 화면에 쓰는 자리(7E:1ABC ^ 1C, 원래 롬은 0 이라 1C)의 VRAM 타일맵과 게임의 타일맵 버퍼 7E:5000 이 다른 바이트 수
  local shown = (emu.read(0x7E1ABC, m) ~ 0x1C) & 0xFC
  local vb, diff = shown * 0x200, 0
  for i = 0, 0x7FF do
    if emu.read(vb + i, vram) ~= emu.read(0x7E5000 + i, m) then diff = diff + 1 end
  end
  local old = 0
  if shown == 0x1C then
    snap = nil
  elseif not snap then
    snap = {}
    for i = 0x3800, 0x3FFF do snap[i] = emu.read(i, vram) end
  else
    for i = 0x3800, 0x3FFF do if emu.read(i, vram) ~= snap[i] then old = old + 1 end end
  end
  log[#log + 1] = string.format("f%05d map %02X/%02X 0725=%02X shown=%02X nz=%d vsbuf=%d old=%d still=%d", n,
    emu.read(0x7E00BC, m), emu.read(0x7E00BD, m), sc, shown, nz, diff, old, still)
  if #log > 400 then table.remove(log, 1) end
  local f = io.open(os.getenv("SHOT_DIR") .. "/bg3.txt", "w"); f:write(table.concat(log, "\n"), "\n"); f:close()
end, emu.eventType.endFrame)
dofile(os.getenv("WARPLUA"))
