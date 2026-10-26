-- DQ5 전투 몬스터 움직임 기록. 드라이버(boot.lua, 보통 dq5battle.lua)로 싸우면서 FROM~TO 프레임 동안 프레임마다
--   o<프레임>.oam(544) · c<프레임>.cgram(512) · w<프레임>.bin(7E:0C00~0DFF, 몬스터 표) 와
--   ppu.txt 한 줄 "프레임 밝기 모자이크켬 모자이크크기 메인화면층 색더하기켬 BG1~3 가로·세로 스크롤" 을 남기고,
--   VFRAMES(쉼표 목록) 프레임에는 v<프레임>.vram 도 남긴다. SHOTS=1 이면 그 프레임의 화면 버퍼(emu.getScreenBuffer)를
--   s<프레임>.raw(점마다 32비트 ARGB, 작은 끝)로, 크기를 size.txt 에 남긴다(emu.takeScreenshot 은 1~3프레임 늦을 때가 있음).
--   EXEC="22B38C,22B347"   그 PC 를 실행한 프레임을 exec.txt 에 "프레임 PC A X Y" 로
--   CGW=1 이면 화면을 그리는 동안(줄 0~224) $2121·$2122 에 쓴 것을 cgw.txt 에 "프레임 줄 레지스터 값" 으로(HDMA 가 CGRAM 을 바꾸는 것)
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local L = require("lib")
local m = emu.memType
local from, to = tonumber(os.getenv("FROM") or "0"), tonumber(os.getenv("TO") or "600")
local vf = {}
for a in string.gmatch(os.getenv("VFRAMES") or "", "[^,]+") do vf[tonumber(a)] = true end
local n, ppu, ex = 0, {}, {}
for a in string.gmatch(os.getenv("EXEC") or "", "%x+") do
  local pc = tonumber(a, 16)
  emu.addMemoryCallback(function()
    if n < from or n > to then return end
    local st = emu.getState()
    ex[#ex + 1] = string.format("%d %06X %04X %04X %04X", n, pc, st["cpu.a"], st["cpu.x"], st["cpu.y"])
  end, emu.callbackType.exec, pc, pc)
end
local cgw = {}
if os.getenv("CGW") then
  emu.addMemoryCallback(function(a, v)
    if n < from or n > to then return end
    local sl = emu.getState()["ppu.scanline"]
    if sl < 225 then cgw[#cgw + 1] = string.format("%d %d %04X %02X", n, sl, a & 0xFFFF, v) end
  end, emu.callbackType.write, 0x2121, 0x2122)
end
emu.addEventCallback(function()
  n = n + 1
  if n < from or n > to then return end
  local f = string.format("%05d", n)
  L.dump("o" .. f .. ".oam", m.snesSpriteRam, 0x220)
  L.dump("c" .. f .. ".cgram", m.snesCgRam, 0x200)
  local w = {}
  for i = 0, 0x1FF do w[#w + 1] = string.char(emu.read(0x7E0C00 + i, m.snesMemory)) end
  L.write("w" .. f .. ".bin", table.concat(w))
  if vf[n] then L.dump("v" .. f .. ".vram", m.snesVideoRam, 0x10000) end
  if os.getenv("SHOTS") then
    local b = emu.getScreenBuffer()
    local t = {}
    for i = 1, #b do t[i] = string.pack("<I4", b[i]) end
    L.write("s" .. f .. ".raw", table.concat(t))
    local sz = emu.getScreenSize()
    L.write("size.txt", sz.width .. " " .. sz.height)
  end
  local st = emu.getState()
  local sc = {}
  for i = 0, 2 do sc[#sc + 1] = st["ppu.layers[" .. i .. "].hscroll"] .. " " .. st["ppu.layers[" .. i .. "].vscroll"] end
  ppu[#ppu + 1] = string.format("%d %d %d %d %d %d %s", n, st["ppu.screenBrightness"], st["ppu.mosaicEnabled"],
    st["ppu.mosaicSize"], st["ppu.mainScreenLayers"], st["ppu.colorMathEnabled"], table.concat(sc, " "))
  if n == to then
    L.write("ppu.txt", table.concat(ppu, "\n") .. "\n")
    L.write("exec.txt", table.concat(ex, "\n") .. "\n")
    if os.getenv("CGW") then L.write("cgw.txt", table.concat(cgw, "\n") .. "\n") end
  end
end, emu.eventType.endFrame)
dofile(os.getenv("LIBDIR") .. "/boot.lua")
