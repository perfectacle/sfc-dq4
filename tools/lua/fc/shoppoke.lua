-- PC 가 AT(16진 CPU 주소)에 닿을 때 POKE("주소=바이트들;…", CPU 주소, 바이트는 이어 씀)를 RAM 에 쓴다.
-- BANK 를 주면 그때 `$0507` 이 그 뱅크일 때만 쓴다(같은 CPU 주소가 다른 뱅크에도 있으므로).
-- ONCE=1 이면 처음 한 번만. 입력은 DRIVER(보통 seq.lua)가 맡고, 덤프도 드라이버가 남긴다.
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local L = require("lib")
local at = tonumber(os.getenv("AT"), 16)
local bank = os.getenv("BANK") and tonumber(os.getenv("BANK"), 16)
local once = os.getenv("ONCE") == "1"
local pokes = {}
for addr, bytes in string.gmatch(os.getenv("POKE") or "", "(%x+)=(%x+)") do
  local a = tonumber(addr, 16)
  for i = 1, #bytes - 1, 2 do
    pokes[#pokes + 1] = {a + (i - 1) // 2, tonumber(bytes:sub(i, i + 1), 16)}
  end
end
local done = false
emu.addMemoryCallback(function()
  if done or (bank and emu.read(0x0507, L.mem) ~= bank) then return end
  for _, p in ipairs(pokes) do emu.write(p[1], p[2], L.mem) end
  done = once
end, emu.callbackType.exec, at, at)
L.drive()
