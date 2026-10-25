-- FROM 부터 TO 프레임까지 STEP 프레임마다 화면을 SHOT_DIR/sNNNNN.png 로 찍는다. 드라이버(LIBDIR 의 boot.lua) 앞에 붙여 쓴다.
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local L = require("lib")
local from, to = tonumber(os.getenv("FROM") or "0"), tonumber(os.getenv("TO") or "0")
local step = tonumber(os.getenv("STEP") or "1")
local n = 0
emu.addEventCallback(function()
  n = n + 1
  if n >= from and n <= to and (n - from) % step == 0 then L.shot(string.format("s%05d.png", n)) end
end, emu.eventType.endFrame)
dofile(os.getenv("LIBDIR") .. "/boot.lua")
