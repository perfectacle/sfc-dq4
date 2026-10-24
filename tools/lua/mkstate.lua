-- boot.lua 와 같은 입력으로 부팅하고 SAVEAT 프레임에 세이브스테이트(STATE 이름)와 화면을 저장한다.
-- 오프닝을 A 연타로 넘긴 뒤 조작 가능한 장면을 출발점으로 만들 때 쓴다(TAPUNTIL 로 연타를 미리 멈춘다).
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local L = require("lib")
local at = tonumber(os.getenv("SAVEAT"))
local name = os.getenv("STATE") or "start.mss"
local n = 0
emu.addEventCallback(function()
  n = n + 1
  if n == at then
    L.saveState(name)
    L.shot(name:gsub("%.mss$", ".png"))
  end
end, emu.eventType.endFrame)
dofile(os.getenv("LIBDIR") .. "/boot.lua")
