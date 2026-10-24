-- PC 가 정한 주소에 닿을 때 CPU 메모리에 쓰고 PCNEXT(기본 seq.lua) 드라이버를 돌린다.
-- PCPOKE="A11A@18:6E45=05,FF,FF,FF;A11A@18:6E49=03,00,00,00" 처럼 주소[@뱅크]:주소=바이트들(16진, 쉼표).
-- 뱅크($0507)를 주면 그 뱅크일 때만 쓴다. 기본은 닿을 때마다 쓰고, PCTIMES=n 이면 항목마다 n 번까지.
-- 전투 시작 루틴에서 무리를 바꾸거나, 데미지 계산 직전에 난수·능력치를 고정하는 데 쓴다.
-- 프로브의 DRIVER 로 이 파일을 주고, 이 파일의 PCNEXT 로 statspoke.lua 나 seq.lua 를 준다.
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local L = require("lib")
local times = tonumber(os.getenv("PCTIMES") or "0")
for spec in string.gmatch(os.getenv("PCPOKE") or "", "[^;]+") do
  local at, bank, dst, bs = spec:match("^(%x+)@?(%x*):(%x+)=([%x,]+)$")
  assert(at, "PCPOKE 형식: " .. spec)
  local pc, b, base, vals, n = tonumber(at, 16), tonumber(bank, 16), tonumber(dst, 16), {}, 0
  for v in bs:gmatch("%x+") do vals[#vals + 1] = tonumber(v, 16) end
  emu.addMemoryCallback(function()
    if b and emu.read(0x0507, L.mem) ~= b then return end
    if times > 0 and n >= times then return end
    n = n + 1
    for k, v in ipairs(vals) do emu.write(base + k - 1, v, L.mem) end
  end, emu.callbackType.exec, pc, pc)
end
dofile(os.getenv("PCNEXT") or (os.getenv("LIBDIR") .. "/seq.lua"))
