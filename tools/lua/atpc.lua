-- boot.lua 와 같은 입력으로 부팅하고 FROM 프레임 이후 PC 가 AT 에 처음 닿을 때 WRAM 128KB 와 CGRAM 을 덤프한다.
-- 맵 디코더가 끝난 직후처럼, 프레임 경계가 아닌 정확한 시점의 RAM 이 필요할 때 쓴다.
-- POKE="7E075E=F0;..." 는 매 프레임 다시 써서 그 값을 고정한다(CPU 주소). 시간대 같은 조건을 바꿔 볼 때 쓴다.
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local L = require("lib")
local from = tonumber(os.getenv("FROM") or "0")
local n = 0
local list = {}
for a in string.gmatch(os.getenv("AT"), "[^,]+") do list[#list + 1] = tonumber(a, 16) end
local pokes = {}
for a, v in string.gmatch(os.getenv("POKE") or "", "(%x+)=(%x+)") do pokes[#pokes + 1] = {tonumber(a, 16), tonumber(v, 16)} end
local done = {}
for _, at in ipairs(list) do
  emu.addMemoryCallback(function()
    if n < from or done[at] then return end
    done[at] = true
    L.dump(string.format("at_%06X.bin", at), emu.memType.snesWorkRam, 0x20000)
    L.dump(string.format("at_%06X.cgram", at), emu.memType.snesCgRam, 0x200)
  end, emu.callbackType.exec, at, at)
end
emu.addEventCallback(function()
  n = n + 1
  for _, p in ipairs(pokes) do emu.write(p[1], p[2], emu.memType.snesMemory) end
end, emu.eventType.endFrame)
dofile(os.getenv("LIBDIR") .. "/boot.lua")
