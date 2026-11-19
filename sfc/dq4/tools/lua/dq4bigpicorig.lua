-- dq4bigpiccheck.py --measure-original 이 dq4bigpic.lua 의 NEXT 로 부른다. 원본 DQ5 롬에서 전투 중인 세이브스테이트(STATE)를
-- 불러 40프레임마다 A 를 4프레임 눌러 싸운다. 첫 공격의 효과가 끝나면 dq4bigpic.lua(EFFECT_STOP)가 멈추고, 그러지 못하면
-- MAXF 프레임에 멈춘다.
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local L = require("lib")
L.loadState(os.getenv("STATE"))
local maxf = tonumber(os.getenv("MAXF") or "1200")
local n = 0
emu.addEventCallback(function()
  n = n + 1
  L.held = (n % 40 < 4) and {a = true} or nil
  if n >= maxf then emu.stop(0) end
end, emu.eventType.endFrame)
