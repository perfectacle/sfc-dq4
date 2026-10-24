-- boot.lua 의 입력을 재생하면서 SHOTS 에 적은 프레임("300,420,...")마다 화면을 sNNNNN.png 로 저장한다.
-- 메시지 창처럼 여러 장면을 한 번에 보고 싶을 때 쓴다. 결과 파일은 SHOT_DIR 에 쓴다.
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local L = require("lib")
local want = {}
for a in string.gmatch(os.getenv("SHOTS") or "", "%d+") do want[tonumber(a)] = true end
local n = 0
emu.addEventCallback(function()
  n = n + 1
  if want[n] then L.shot(string.format("s%05d.png", n)) end
end, emu.eventType.endFrame)
dofile(os.getenv("LIBDIR") .. "/boot.lua")
