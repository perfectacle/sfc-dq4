-- FROM 부터 TO 프레임까지 STEP 프레임마다 화면을 SHOT_DIR 에 남긴다. 드라이버(LIBDIR 의 boot.lua) 앞에 붙여 쓴다.
-- 그 프레임의 화면 버퍼(emu.getScreenBuffer, overscan 이면 239줄 전부)를 sNNNNN.raw(점마다 32비트 ARGB, 작은 끝)로 쓰고
-- 크기는 size.txt 에 둔다. MesenCE 인자에 --Snes.DisableFrameSkipping=true 를 주어야 한다. 빠르게 돌 때 PPU 가 몇
-- 프레임을 그리지 않아, 주지 않으면 화면 버퍼가 실행마다 다르게 1~3프레임 앞의 그림으로 남는다.
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local L = require("lib")
local from, to = tonumber(os.getenv("FROM") or "0"), tonumber(os.getenv("TO") or "0")
local step = tonumber(os.getenv("STEP") or "1")
local n = 0
emu.addEventCallback(function()
  n = n + 1
  if n >= from and n <= to and (n - from) % step == 0 then
    local b = emu.getScreenBuffer()
    local t = {}
    for i = 1, #b do t[i] = string.pack("<I4", b[i]) end
    L.write(string.format("s%05d.raw", n), table.concat(t))
    local s = emu.getScreenSize()
    L.write("size.txt", s.width .. " " .. s.height)
  end
end, emu.eventType.endFrame)
dofile(os.getenv("LIBDIR") .. "/boot.lua")
