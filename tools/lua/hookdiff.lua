-- 세이브스테이트에서 LAST 프레임을 돌린 뒤 WRAM·VRAM·CGRAM·OAM 을 덤프한다(w.bin·v.bin·c.bin·o.bin, 화면 end.png).
-- POKE1="7E1AA6=06;7E1AA7=F9;7E1AA8=15" 는 둘째 프레임에 한 번 써서(예: 맵별 둘째 루틴 빼기) 쓴 것과 안 쓴 것을 견줄 때 쓴다.
-- EXEC="02A153,..." 이 실행된 횟수는 exec.txt. 입력은 boot.lua 와 같음.
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local L = require("lib")
local n, cnt = 0, {}
local last = tonumber(os.getenv("LAST") or "180")
local m = emu.memType.snesMemory
local pcs = {}
for a in string.gmatch(os.getenv("EXEC") or "", "(%x+)") do
  local pc = tonumber(a, 16); pcs[#pcs + 1] = pc; cnt[pc] = 0
  emu.addMemoryCallback(function() if n > 2 then cnt[pc] = cnt[pc] + 1 end end, emu.callbackType.exec, pc, pc)
end
emu.addEventCallback(function()
  n = n + 1
  if n == 2 then for a, v in string.gmatch(os.getenv("POKE1") or "", "(%x+)=(%x+)") do emu.write(tonumber(a, 16), tonumber(v, 16), m) end end
  if n == last then
    L.dump("w.bin", emu.memType.snesWorkRam, 0x20000)
    L.dump("v.bin", emu.memType.snesVideoRam, 0x10000)
    L.dump("c.bin", emu.memType.snesCgRam, 0x200)
    L.dump("o.bin", emu.memType.snesSpriteRam, 0x220)
    L.shot("end.png")
    local t = {}
    for _, pc in ipairs(pcs) do t[#t + 1] = string.format("%06X n=%d", pc, cnt[pc]) end
    L.write("exec.txt", table.concat(t, "\n") .. "\n")
  end
end, emu.eventType.endFrame)
dofile(os.getenv("LIBDIR") .. "/boot.lua")
