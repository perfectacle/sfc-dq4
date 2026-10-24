-- VRAM 에 그래픽을 올리는 곳을 찾는다. 드라이버(boot.lua) 입력을 재생하면서
--   DMA: $420B 쓰기마다 켜진 채널의 B 버스 대상·원본·크기와 그때의 VRAM 워드 주소($2116)를 dma.txt 에
--   포트: CPU 가 $2118/$2119 에 쓴 것(DMA 포함)을 PC 별로 첫 프레임·첫 VRAM 주소·횟수만 vport.txt 에
-- 레지스터는 뱅크 00~3F·80~BF 의 미러로도 쓰므로 모든 미러에 감시를 건다.
--   FROM, STOPF  기록 구간(STOPF 프레임에 파일을 씀)
--   BBUS="18"    DMA 를 이 B 버스 대상만(16진, 0 이면 전부)
--   VLO, VHI     포트 기록을 이 VRAM 워드 주소 범위만(16진)
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local L = require("lib")
local m = emu.memType.snesMemory
local n, vaddr, inc, incHi = 0, 0, 1, true
local from, stopf = tonumber(os.getenv("FROM") or "0"), tonumber(os.getenv("STOPF") or "600")
local onlyB = tonumber(os.getenv("BBUS") or "18", 16)
local lo, hi = tonumber(os.getenv("VLO") or "0", 16), tonumber(os.getenv("VHI") or "7FFF", 16)
local dma, seen, order = {}, {}, {}

local function reg(fn, a0, a1)
  for _, base in ipairs({0x00, 0x80}) do
    for bk = base, base + 0x3F do
      emu.addMemoryCallback(function(a, v) fn(a & 0xFFFF, v) end, emu.callbackType.write, bk * 0x10000 + a0, bk * 0x10000 + a1)
    end
  end
end
local function pc()
  local st = emu.getState()
  return string.format("%02X:%04X", st["cpu.k"], st["cpu.pc"])
end

reg(function(a, v)
  if a == 0x2115 then inc = ({1, 32, 128, 128})[(v & 3) + 1]; incHi = v & 0x80 ~= 0
  elseif a == 0x2116 then vaddr = (vaddr & 0xFF00) | v
  else vaddr = (vaddr & 0xFF) | (v << 8) end
end, 0x2115, 0x2117)
reg(function(a, v)
  if n >= from and vaddr >= lo and vaddr <= hi then
    local k = pc()
    if not seen[k] then seen[k] = {n, vaddr, 0}; order[#order + 1] = k end
    seen[k][3] = seen[k][3] + 1
  end
  if (a == 0x2119) == incHi then vaddr = (vaddr + inc) & 0x7FFF end
end, 0x2118, 0x2119)
reg(function(_, v)
  if n < from then return end
  for ch = 0, 7 do
    if v & (1 << ch) ~= 0 then
      local b = 0x4300 + ch * 16
      local bb = emu.read(b + 1, m)
      if onlyB == 0 or bb == onlyB then
        local src = emu.read(b + 2, m) | emu.read(b + 3, m) << 8 | emu.read(b + 4, m) << 16
        local size = emu.read(b + 5, m) | emu.read(b + 6, m) << 8
        dma[#dma + 1] = string.format("f%05d pc %s ch%d B=%02X src %06X size %04X vram %04X", n, pc(), ch, bb, src, size, vaddr)
      end
    end
  end
end, 0x420B, 0x420B)

emu.addEventCallback(function()
  n = n + 1
  if n == stopf then
    L.write("dma.txt", table.concat(dma, "\n") .. "\n")
    local t = {}
    for _, k in ipairs(order) do local s = seen[k]; t[#t + 1] = string.format("%s f%d vram %04X count %d", k, s[1], s[2], s[3]) end
    L.write("vport.txt", table.concat(t, "\n") .. "\n")
  end
end, emu.eventType.endFrame)
dofile(os.getenv("LIBDIR") .. "/boot.lua")
