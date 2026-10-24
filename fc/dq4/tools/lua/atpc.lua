-- PC 가 AT(CPU 주소, 쉼표로 여럿)에 닿을 때마다 CPU 메모리 RANGE(기본 0000-7FFF)를 at_PPPP_N.bin 으로 저장한다.
-- 툴킷 FC 프로브와 같이 끝에서 입력 드라이버(DRIVER, 기본 boot.lua)를 돌린다. LIMIT 은 PC 마다 저장 횟수.
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local L = require("lib")
local lo, hi = 0, 0x7FFF
local r = os.getenv("RANGE")
if r then local a, b = r:match("(%x+)-(%x+)"); lo, hi = tonumber(a, 16), tonumber(b, 16) end
local limit = tonumber(os.getenv("LIMIT") or "4")
for a in string.gmatch(os.getenv("AT"), "[^,]+") do
  local addr, n = tonumber(a, 16), 0
  emu.addMemoryCallback(function()
    if n >= limit then return end
    n = n + 1
    local t = {}
    for i = lo, hi do t[#t + 1] = string.char(emu.read(i, L.mem)) end
    L.write(string.format("at_%04X_%d.bin", addr, n), table.concat(t))
  end, emu.callbackType.exec, addr, addr)
end
L.drive()
