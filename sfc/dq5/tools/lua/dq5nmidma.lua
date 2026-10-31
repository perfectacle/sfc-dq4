-- DQ5 전투 NMI 의 몬스터 타일 전송(00:FD4A, 목록 7E:0F5E) 시각을 재면서 드라이버(boot.lua, 보통 dq5warp.lua)를 돌린다.
-- 목록 항목마다 DMA 를 거는 00:FD6A(STA $420B 직전)와 목록 끝 00:FD6F, NMI 첫머리 00:885D 의 줄·마스터 주기를 남긴다.
--   dma.txt   "프레임 곳 줄 hClock 화면끔 Y 바이트 수 버퍼 주소 VRAM 워드 주소"   곳 = nmi·entry·end
--             nmi 는 그 프레임의 몬스터 타일 전송이 있을 때만 적는다. 화면끔은 ppu.forcedBlank. nmi 줄 끝에 그때의 $19 와,
--             그 NMI 에서 00:89BB 의 OAM DMA(00:89DA STA $420B)가 돌았으면 "oam 줄 hClock" 을 붙인다
--   DUMPF="1200,1600"  그 프레임 끝에 fNNNNN.vram·.wram 도 남긴다(dq5gfxdump.lua 와 같은 이름)
--   PIECES=29          전투를 시작할 때 자리 사슬을 비운 뒤(22:ABE5) 조각 목록 사슬 7E:8480 의 앞 29칸을 이미 쓴 그림 하나로
--                      채우고(남은 수 $0D27 = 128 - 29, 다음 칸 $0D25 = 29), 빈 칸 찾기(22:AD67)를 돈 횟수를 프레임마다
--                      search.txt 에 "프레임 횟수" 로 남긴다. 조각 목록의 끝을 싸우는 도중에 그림을 더 푼 것처럼 잰다
--   SLOTS=114          같은 때 16x16 자리 사슬 7E:8400 의 앞 114칸을 같은 꼴로 채운다(남은 수 $0D1F = 128 - 114,
--                      다음 칸 $0D1D = 114). 자리 사슬의 빈 칸 찾기(22:AD0F·22:AD2C)를 돈 횟수를 slotsearch.txt 에 같은 꼴로
--                      남기고, 22:AC87 에서 받아들인 할당마다 "프레임 그림 남은자리 첫자리" 를 slotalloc.txt 에 남긴다
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local L = require("lib")
local dumpf = {}
for a in string.gmatch(os.getenv("DUMPF") or "", "[^,]+") do dumpf[tonumber(a)] = true end
local n, rows, nmi, written = 0, {}, nil, 0

local function at()
  local st = emu.getState()
  return st["ppu.scanline"], st["memoryManager.hClock"], st["ppu.forcedBlank"] and 1 or 0, st["cpu.y"]
end

emu.addMemoryCallback(function()
  local sl, h, fb = at()
  nmi = string.format("%d nmi %d %d %d 19=%02X", n, sl, h, fb, emu.read(0x7E0019, emu.memType.snesMemory))
end, emu.callbackType.exec, 0x00885D, 0x00885D)
emu.addMemoryCallback(function()
  local sl, h = at()
  if nmi then nmi = nmi .. string.format(" oam %d %d", sl, h) end
end, emu.callbackType.exec, 0x0089DA, 0x0089DA)
emu.addMemoryCallback(function()
  local sl, h, fb, y = at()
  -- 00:FD65 에서 Y 가 이미 다음 항목(+6)으로 갔다
  local base = 0x7E0F5E + ((y - 6) & 0xFF)
  local function w(o) return emu.read(base + o, emu.memType.snesMemory) | emu.read(base + o + 1, emu.memType.snesMemory) << 8 end
  if nmi then rows[#rows + 1] = nmi; nmi = nil end
  rows[#rows + 1] = string.format("%d entry %d %d %d %d %d %04X %04X", n, sl, h, fb, (y - 6) & 0xFF, w(0), w(2), w(4))
end, emu.callbackType.exec, 0x00FD6A, 0x00FD6A)
emu.addMemoryCallback(function()
  local sl, h, fb = at()
  if nmi == nil then rows[#rows + 1] = string.format("%d end %d %d %d", n, sl, h, fb) end
  nmi = nil
end, emu.callbackType.exec, 0x00FD6F, 0x00FD6F)

local pieces, search, searched = tonumber(os.getenv("PIECES") or ""), {}, 0
if pieces then
  emu.addMemoryCallback(function()
    local m = emu.memType.snesMemory
    for i = 0, pieces - 1 do emu.write(0x7E8480 + i, i == pieces - 1 and 0x80 or i + 1, m) end
    emu.write(0x7E0D25, pieces, m)
    emu.write(0x7E0D27, 0x80 - pieces, m)
  end, emu.callbackType.exec, 0x22ABE5, 0x22ABE5)
  emu.addMemoryCallback(function() searched = searched + 1 end, emu.callbackType.exec, 0x22AD67, 0x22AD67)
end

local slots, slotsearch, slotsearched, allocs = tonumber(os.getenv("SLOTS") or ""), {}, 0, {}
if slots then
  emu.addMemoryCallback(function()
    local m = emu.memType.snesMemory
    for i = 0, slots - 1 do emu.write(0x7E8400 + i, i == slots - 1 and 0x80 or i + 1, m) end
    emu.write(0x7E0D1D, slots, m)
    emu.write(0x7E0D1F, 0x80 - slots, m)
  end, emu.callbackType.exec, 0x22ABE5, 0x22ABE5)
  local function count() slotsearched = slotsearched + 1 end
  emu.addMemoryCallback(count, emu.callbackType.exec, 0x22AD0F, 0x22AD0F)
  emu.addMemoryCallback(count, emu.callbackType.exec, 0x22AD2C, 0x22AD2C)
  emu.addMemoryCallback(function()
    local m = emu.memType.snesMemory
    allocs[#allocs + 1] = string.format("%d %02X %d %d", n, emu.read(0x7E0D1A, m), emu.read(0x7E0D1F, m), emu.read(0x7E0D1D, m))
    L.write("slotalloc.txt", table.concat(allocs, "\n") .. "\n")
  end, emu.callbackType.exec, 0x22AC87, 0x22AC87)
end

emu.addEventCallback(function()
  n = n + 1
  if slots and slotsearched > 0 then
    slotsearch[#slotsearch + 1] = string.format("%d %d", n, slotsearched)
    L.write("slotsearch.txt", table.concat(slotsearch, "\n") .. "\n")
    slotsearched = 0
  end
  if pieces and searched > 0 then
    search[#search + 1] = string.format("%d %d", n, searched)
    L.write("search.txt", table.concat(search, "\n") .. "\n")
    searched = 0
  end
  if dumpf[n] then
    local tag = string.format("f%05d", n)
    L.dump(tag .. ".vram", emu.memType.snesVideoRam, 0x10000)
    L.dump(tag .. ".wram", emu.memType.snesWorkRam, 0x20000)
  end
  -- 드라이버가 먼저 끝낼 수 있어 늘어날 때마다 다시 쓴다
  if #rows > written then L.write("dma.txt", table.concat(rows, "\n") .. "\n"); written = #rows end
end, emu.eventType.endFrame)
dofile(os.getenv("LIBDIR") .. "/boot.lua")
