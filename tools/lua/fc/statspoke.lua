-- 세이브스테이트를 불러온 뒤 ONCEAT 프레임(기본 5)에 한 번만 CPU 메모리에 쓰고 NEXT(기본 seq.lua) 드라이버를 돌린다.
-- ONCE="60C5=10,00,00;60BA=05" 처럼 주소=바이트들(16진, 쉼표). seq.lua 의 POKE 는 매 프레임 다시 쓰므로
-- 경험치처럼 게임이 바꿔야 하는 값은 이것으로 넣는다. 프로브의 DRIVER 로 이 파일을 주면 프로브와 함께 쓸 수 있다.
-- ROMONCE="60052=40" 은 같은 형식으로 PRG ROM 오프셋에 쓴다(실험 중 표 값 하나를 바꿔 보는 용도, 파일은 그대로).
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local L = require("lib")
local at = tonumber(os.getenv("ONCEAT") or "5")
local function parse(spec, mem, out)
  for a, bs in string.gmatch(spec or "", "(%x+)=([%x,]+)") do
    local base, k = tonumber(a, 16), 0
    for b in bs:gmatch("%x+") do out[#out + 1] = {base + k, tonumber(b, 16), mem}; k = k + 1 end
  end
end
local writes = {}
parse(os.getenv("ONCE"), L.mem, writes)
parse(os.getenv("ROMONCE"), emu.memType.nesPrgRom, writes)
local n = 0
emu.addEventCallback(function()
  n = n + 1
  if n == at then for _, w in ipairs(writes) do emu.write(w[1], w[2], w[3]) end end
end, emu.eventType.endFrame)
dofile(os.getenv("NEXT") or (os.getenv("LIBDIR") .. "/seq.lua"))
