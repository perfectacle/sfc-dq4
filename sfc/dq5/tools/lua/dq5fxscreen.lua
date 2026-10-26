-- DQ5 전투 연출 한 벌을 화면 전체로 견주기 위한 덤프(dq5fxscreen.py 의 입력). 드라이버(boot.lua, 보통 dq5battle.lua)로 싸우면서
-- 처음 연출 시작(22:D73C, A = 연출 번호. ONLY="5A" 면 그 번호만)부터 끝(22:D796) 뒤 4프레임까지 프레임마다 SHOT_DIR 에 남긴다.
--   e<번호>-<k>.state0 / .wram0 / .cgram0 / .preg0   프레임 첫머리(startFrame)의 ppu.*·dmaController.* 상태, WRAM, CGRAM, $212A~$2131 마지막 쓰기
--   e<번호>-<k>.state / .vram / .cgram / .oam / .preg  프레임 끝(endFrame)의 같은 것과 VRAM·OAM
--   e<번호>-<k>.raw    그 프레임의 화면 버퍼(32비트 ARGB, 256 x 239)
--   e<번호>-<k>.wlog   그 프레임 동안 CPU 가 HDMA 표 자리(7E:5B00~5FFF, 7E:0D00~0DFF 와 거울 00:0D00~)에 쓴 것 "줄 마스터주기 주소 값"
--   e<번호>-<k>.plog   그 프레임 동안 PPU 레지스터 $2100~$2133 에 쓴 것(HDMA 쓰기도 걸린다) "줄 마스터주기 주소 값"
--   end.txt            연출이 끝난 프레임 k
-- $2130 은 MesenCE 상태에 없어 .preg 로 따로 남긴다(세이브스테이트에서 시작하기 전에 쓴 값은 모른다).   MAXK(기본 600)
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local L = require("lib")
local m = emu.memType
local maxk = tonumber(os.getenv("MAXK") or "600")
local only = os.getenv("ONLY") and tonumber(os.getenv("ONLY"), 16)
local fx, k, stopk = nil, 0, nil
local wl, pl, preg = {}, {}, {}

local function at()
  local st = emu.getState()
  return st["ppu.scanline"], st["memoryManager.hClock"]
end
local function wcb(addr, value)
  if fx then local sl, h = at(); wl[#wl + 1] = string.format("%d %d %06X %02X", sl, h, addr, value) end
end
emu.addMemoryCallback(wcb, emu.callbackType.write, 0x7E5B00, 0x7E5FFF)
emu.addMemoryCallback(wcb, emu.callbackType.write, 0x7E0D00, 0x7E0DFF)
emu.addMemoryCallback(wcb, emu.callbackType.write, 0x000D00, 0x000DFF)
local function pcb(addr, value)
  preg[addr & 0xFFFF] = value
  if fx then local sl, h = at(); pl[#pl + 1] = string.format("%d %d %04X %02X", sl, h, addr & 0xFFFF, value) end
end
-- 레지스터는 거울 뱅크 00~3F·80~BF 어디로도 쓸 수 있다(데이터 뱅크가 2B 면 2B:2109)
for bank = 0, 0xBF do
  if bank < 0x40 or bank >= 0x80 then emu.addMemoryCallback(pcb, emu.callbackType.write, bank * 0x10000 + 0x2100, bank * 0x10000 + 0x2133) end
end

emu.addMemoryCallback(function()
  local a = emu.getState()["cpu.a"] & 0xFF
  if fx == nil and (only == nil or a == only) then fx, k = a, 0 end
end, emu.callbackType.exec, 0x22D73C, 0x22D73C)
emu.addMemoryCallback(function()
  if fx and not stopk then stopk = k + 4; L.write("end.txt", tostring(k) .. "\n") end
end, emu.callbackType.exec, 0x22D796, 0x22D796)

local function state(p)
  local st, keys = emu.getState(), {}
  for key, v in pairs(st) do
    local q = key:sub(1, 4)
    if q == "ppu." or q == "dmaC" then keys[#keys + 1] = key .. "=" .. tostring(v) end
  end
  table.sort(keys)
  L.write(p, table.concat(keys, "\n") .. "\n")
end
local function pregs(p)
  local t = {}
  for a = 0x212A, 0x2131 do if preg[a] then t[#t + 1] = string.format("%04X=%02X", a, preg[a]) end end
  L.write(p, table.concat(t, "\n") .. "\n")
end

emu.addEventCallback(function()
  wl, pl = {}, {}
  if fx and k < maxk then
    local p = string.format("e%02X-%03d", fx, k)
    state(p .. ".state0"); pregs(p .. ".preg0")
    L.dump(p .. ".wram0", m.snesWorkRam, 0x20000)
    L.dump(p .. ".cgram0", m.snesCgRam, 0x200)
  end
end, emu.eventType.startFrame)
emu.addEventCallback(function()
  if fx and k < maxk then
    local p = string.format("e%02X-%03d", fx, k)
    state(p .. ".state"); pregs(p .. ".preg")
    L.dump(p .. ".vram", m.snesVideoRam, 0x10000)
    L.dump(p .. ".cgram", m.snesCgRam, 0x200)
    L.dump(p .. ".oam", m.snesSpriteRam, 0x220)
    local b, t = emu.getScreenBuffer(), {}
    for i = 1, #b do t[i] = string.pack("<I4", b[i]) end
    L.write(p .. ".raw", table.concat(t))
    L.write(p .. ".wlog", table.concat(wl, "\n") .. "\n")
    L.write(p .. ".plog", table.concat(pl, "\n") .. "\n")
    k = k + 1
    if k >= maxk or (stopk and k >= stopk) then emu.stop() end
  end
end, emu.eventType.endFrame)
dofile(os.getenv("LIBDIR") .. "/boot.lua")
