-- dq4fieldmathcheck.py: dq5warp.lua 로 필드에 내린 끝 프레임의 색 연산 상태와 OAM 을 math.txt 로 남긴다.
-- dq5warp.lua 의 환경 변수는 그대로 쓴다. 기록은 dq5warp.lua 가 warp.txt 를 쓸 때(끝 프레임) 함께 쓴다.
--   math.txt  첫 줄 「colormath <PPU 의 색 연산 층 비트(bit4 = OBJ)> BE=<$BE>」, 이어 화면 안 OAM 마다 「oam 번호 x y 팔레트」
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local L = require("lib")

local write = L.write
L.write = function(name, s)
  if name == "warp.txt" then
    local st = emu.getState()
    local t = {string.format("colormath %d BE=%02X", st["ppu.colorMathEnabled"],
                             emu.read(0x7E00BE, emu.memType.snesMemory))}
    for i = 0, 127 do
      local hi = emu.read(512 + (i >> 2), emu.memType.snesSpriteRam) >> ((i & 3) * 2)
      local x = emu.read(i * 4, emu.memType.snesSpriteRam) | ((hi & 1) << 8)
      local y = emu.read(i * 4 + 1, emu.memType.snesSpriteRam)
      local attr = emu.read(i * 4 + 3, emu.memType.snesSpriteRam)
      if y < 224 and x < 256 then
        t[#t + 1] = string.format("oam %d %d %d %d", i, x, y, (attr >> 1) & 7)
      end
    end
    write("math.txt", table.concat(t, "\n") .. "\n")
  end
  return write(name, s)
end
local here = debug.getinfo(1, "S").source:match("^@(.*[/\\])") or "./"
dofile(here .. "../../../dq5/tools/lua/dq5warp.lua")
