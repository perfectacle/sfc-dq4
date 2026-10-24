-- 전투 그림 실험용. boot.lua(보통 walk.lua)로 걸으면서 다음을 덤프한다.
--   AT(16진 CPU 주소)를 FROM 프레임 뒤 처음 실행할 때 WRAM 128KB → at.bin (예: AT=2290DC, 몬스터 그림을 다 푼 직후)
--   DUMPF(쉼표 목록) 프레임 끝에 WRAM·VRAM·CGRAM·OAM·화면·PPU 상태 → w/v/c/o/s/p<프레임>
--   FROM~TO 프레임 동안 DMA($420B) 기록 → dma.txt, VRAM 직접 쓰기($2118/9) → cpuw.txt (MAXF-1 프레임에 씀)
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local L = require("lib")
local f = 0
local dumpf = {}
for a in string.gmatch(os.getenv("DUMPF") or "", "[^,]+") do dumpf[tonumber(a)] = true end
local from = tonumber(os.getenv("FROM") or "0")
local to = tonumber(os.getenv("TO") or "0")
local maxf = tonumber(os.getenv("MAXF") or "1500")
local m = emu.memType.snesMemory
local log = {}
local at = tonumber(os.getenv("AT") or "0", 16)
local atdone = false
if at ~= 0 then
  emu.addMemoryCallback(function()
    if atdone or f < from then return end
    atdone = true
    L.dump("at.bin", emu.memType.snesWorkRam, 0x20000)
  end, emu.callbackType.exec, at, at)
end
emu.addMemoryCallback(function(addr, value)
  if f < from or f > to then return end
  local s = emu.getState()
  for ch = 0, 7 do
    if value & (1 << ch) ~= 0 then
      local b = 0x4300 + ch * 16
      local src = emu.read(b + 2, m) | emu.read(b + 3, m) << 8 | emu.read(b + 4, m) << 16
      local n = emu.read(b + 5, m) | emu.read(b + 6, m) << 8
      log[#log + 1] = string.format("%d ch%d ctl=%02X B=21%02X src=%06X n=%04X vaddr=%04X pc=%02X:%04X", f, ch,
        emu.read(b, m), emu.read(b + 1, m), src, n, s["ppu.vramAddress"] or -1, s["cpu.k"] or 0, s["cpu.pc"] or 0)
    end
  end
end, emu.callbackType.write, 0x420B, 0x420B)
local cw = {}
emu.addMemoryCallback(function(addr, value)
  if f < from or f > to then return end
  local s = emu.getState()
  local k = string.format("%02X:%04X %04X", s["cpu.k"] or 0, s["cpu.pc"] or 0, addr)
  if not cw[k] then cw[k] = {f, 0, s["ppu.vramAddress"]} end
  cw[k][2] = cw[k][2] + 1
end, emu.callbackType.write, 0x2118, 0x2119)
emu.addEventCallback(function()
  f = f + 1
  if dumpf[f] then
    L.dump(string.format("w%05d.bin", f), emu.memType.snesWorkRam, 0x20000)
    L.dump(string.format("v%05d.vram", f), emu.memType.snesVideoRam, 0x10000)
    L.dump(string.format("c%05d.cgram", f), emu.memType.snesCgRam, 0x200)
    L.dump(string.format("o%05d.oam", f), emu.memType.snesSpriteRam, 0x220)
    L.shot(string.format("s%05d.png", f))
    local s = emu.getState()
    local keys = {}
    for k, v in pairs(s) do if string.find(k, "^ppu") then keys[#keys + 1] = k .. "=" .. tostring(v) end end
    table.sort(keys)
    L.write(string.format("p%05d.txt", f), table.concat(keys, "\n"))
  end
  if f == maxf - 1 then L.write("dma.txt", table.concat(log, "\n") .. "\n")
    local t = {}
    for k, v in pairs(cw) do t[#t + 1] = string.format("%s first=%d n=%d vaddr=%04X", k, v[1], v[2], v[3] or 0) end
    L.write("cpuw.txt", table.concat(t, "\n") .. "\n")
  end
end, emu.eventType.endFrame)
dofile(os.getenv("LIBDIR") .. "/boot.lua")
