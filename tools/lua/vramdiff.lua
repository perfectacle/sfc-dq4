-- 프레임 A0 의 VRAM(MEM=cg 면 CGRAM)과 그 뒤 STEP 프레임마다의 값을 견주어 바뀐 바이트 수·주소 범위를 vram.txt 에 쓴다.
-- POKE1="7E1AA6=06;..." 은 둘째 프레임에 한 번 쓴다. 입력은 boot.lua 와 같음.
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local L = require("lib")
local n, base, out = 0, nil, {}
local a0, step, last = tonumber(os.getenv("A0") or "30"), tonumber(os.getenv("STEP") or "8"), tonumber(os.getenv("LAST") or "200")
local vm = os.getenv("MEM") == "cg" and emu.memType.snesCgRam or emu.memType.snesVideoRam
local size = os.getenv("MEM") == "cg" and 0x1FF or 0xFFFF
local function snap() local t = {} for i = 0, size do t[i] = emu.read(i, vm) end return t end
emu.addEventCallback(function()
  n = n + 1
  if n == 2 then for a, v in string.gmatch(os.getenv("POKE1") or "", "(%x+)=(%x+)") do emu.write(tonumber(a, 16), tonumber(v, 16), emu.memType.snesMemory) end end
  if n == a0 then base = snap() end
  if base and n > a0 and (n - a0) % step == 0 and n <= last then
    local t, ch, lo, hi = snap(), 0, nil, nil
    for i = 0, size do if t[i] ~= base[i] then ch = ch + 1; lo = lo or i; hi = i end end
    out[#out + 1] = string.format("f%05d changed=%d range=%s-%s", n, ch, lo and string.format("%04X", lo) or "-", hi and string.format("%04X", hi) or "-")
    base = t
  end
  if n == last + 1 then L.write("vram.txt", table.concat(out, "\n") .. "\n") end
end, emu.eventType.endFrame)
dofile(os.getenv("LIBDIR") .. "/boot.lua")
