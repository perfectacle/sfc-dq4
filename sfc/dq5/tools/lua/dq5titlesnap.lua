-- DQ5: dq5titlevm.py 의 입력. FROM 프레임 뒤 처음 프레임 기다림(00:969A)에 닿을 때 WRAM·VRAM·CGRAM·OAM 과
-- emu.getState() 의 ppu.*·dmaController.*·cpu.* 를 SHOT_DIR/snap.* 로 남기고, 그 뒤 969A 마다 그때의 프레임 번호를
-- snap.frames.txt 에 적는다(MAXN 번째에서 멈춤). 프레임 번호는 시작부터 센 프레임 끝 수다.
--   STATE="…mss"   세이브스테이트에서 시작. 없으면 BOOT=1 로 LIBDIR 의 boot.lua(SEQ 등 입력)를 드라이버로 돌린다
--   DUMPFROM, DUMPTO  그 프레임 끝마다 화면 버퍼를 fNNNNN.raw(32비트 ARGB, 239줄)로(dq5titlevm.py --check)
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local L = require("lib")
if os.getenv("STATE") then L.loadState(os.getenv("STATE")) end
local from, maxn = tonumber(os.getenv("FROM") or "0"), tonumber(os.getenv("MAXN") or "1300")
local d0, d1 = tonumber(os.getenv("DUMPFROM") or "-1"), tonumber(os.getenv("DUMPTO") or "-2")
local n, k, log = 0, 0, {}
emu.addMemoryCallback(function()
  if n < from then return end
  k = k + 1
  log[#log + 1] = tostring(n)
  if k == 1 then
    L.dump("snap.wram", emu.memType.snesWorkRam, 0x20000)
    L.dump("snap.vram", emu.memType.snesVideoRam, 0x10000)
    L.dump("snap.cgram", emu.memType.snesCgRam, 0x200)
    L.dump("snap.oam", emu.memType.snesSpriteRam, 0x220)
    local st, keys = emu.getState(), {}
    for key, v in pairs(st) do
      local p = key:sub(1, 4)
      if p == "ppu." or p == "dmaC" or p == "cpu." then keys[#keys + 1] = key .. "=" .. tostring(v) end
    end
    table.sort(keys)
    L.write("snap.state.txt", table.concat(keys, "\n") .. "\n")
  end
  if k >= maxn then
    L.write("snap.frames.txt", table.concat(log, "\n") .. "\n")
    if n >= d1 then emu.stop() end
  end
end, emu.callbackType.exec, 0x00969A, 0x00969A)
emu.addEventCallback(function()
  n = n + 1
  if n >= d0 and n <= d1 then
    local b, t = emu.getScreenBuffer(), {}
    for i = 1, #b do t[i] = string.pack("<I4", b[i]) end
    L.write(string.format("f%05d.raw", n), table.concat(t))
  end
  if k >= maxn and n >= d1 then emu.stop() end
end, emu.eventType.endFrame)
if os.getenv("BOOT") then dofile(os.getenv("LIBDIR") .. "/boot.lua") end
