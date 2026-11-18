-- dq4boxplay.py 가 부른다. WARPLUA(dq5warp.lua)를 돌리며 SHOTS 에 적은 프레임("6,12,...")마다 화면을 SHOT_DIR/sNNNNN.png 로 남긴다.
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local L = require("lib")
local shots = {}
for a in string.gmatch(os.getenv("SHOTS") or "", "%d+") do shots[tonumber(a)] = true end
local n = 0
emu.addEventCallback(function()
  n = n + 1
  if shots[n] then L.shot(string.format("s%05d.png", n)) end
end, emu.eventType.endFrame)
dofile(os.getenv("WARPLUA"))
