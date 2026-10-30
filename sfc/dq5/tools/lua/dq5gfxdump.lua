-- 드라이버(boot.lua) 입력을 재생하면서 DUMPF 프레임마다 WRAM 128KB·CGRAM·VRAM·OAM·화면과 PPU 상태를 덤프한다.
-- 그래픽 디코더 출력을 그 순간의 VRAM·CGRAM 과 비교하려고 쓴다. seqlib.sh 로 seqboot.lua 를 드라이버로 두면
-- 세이브스테이트(STATE)에서 SEQ 입력을 누르며 찍는다.
--   DUMPF="5,300"   덤프할 프레임(쉼표로 여럿). EVERY 를 주면 DUMPF 대신 그 간격마다(FROM 부터, TO 또는 EVERYTO 까지)
-- 결과: fNNNNN.wram, .cgram, .vram, .oam, .png, .ppu.txt(emu.getState() 의 ppu 로 시작하는 값)
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local L = require("lib")
local dumpf = {}
for a in string.gmatch(os.getenv("DUMPF") or "", "[^,]+") do dumpf[tonumber(a)] = true end
local every = tonumber(os.getenv("EVERY") or "0")
local from = tonumber(os.getenv("FROM") or "0")
-- dq5warp.lua 의 TO 는 맵 목적지라 숫자가 아니다. 그 장면에서는 EVERYTO 로 끝 프레임을 준다.
local to = tonumber(os.getenv("EVERYTO") or os.getenv("TO") or "0") or 0
local n = 0

local function dump(tag)
  L.dump(tag .. ".wram", emu.memType.snesWorkRam, 0x20000)
  L.dump(tag .. ".cgram", emu.memType.snesCgRam, 0x200)
  L.dump(tag .. ".vram", emu.memType.snesVideoRam, 0x10000)
  L.dump(tag .. ".oam", emu.memType.snesSpriteRam, 0x220)
  L.shot(tag .. ".png")
  local keys, st = {}, emu.getState()
  for k, v in pairs(st) do
    if string.sub(k, 1, 3) == "ppu" then keys[#keys + 1] = k .. "=" .. tostring(v) end
  end
  table.sort(keys)
  L.write(tag .. ".ppu.txt", table.concat(keys, "\n") .. "\n")
end

emu.addEventCallback(function()
  n = n + 1
  local hit = dumpf[n]
  if every > 0 and n >= from and (to == 0 or n <= to) and (n - from) % every == 0 then hit = true end
  if hit then dump(string.format("f%05d", n)) end
end, emu.eventType.endFrame)
dofile(os.getenv("LIBDIR") .. "/boot.lua")
