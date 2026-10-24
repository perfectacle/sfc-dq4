-- boot.lua(seqlib.sh 로 walk.lua 등을 드라이버로 둔 폴더)의 입력을 재생하다가 SAVEAT 프레임에
-- 세이브스테이트(SAVENAME)와 화면을 저장한다. 세이브스테이트에서 출발해 새 세이브스테이트를 만들 때 쓴다.
-- mkstate.lua 는 STATE 를 출력 이름으로 쓰므로, STATE 를 입력으로 읽는 walk.lua 와 함께 쓸 수 없다.
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local L = require("lib")
local at = tonumber(os.getenv("SAVEAT"))
local name = os.getenv("SAVENAME") or "save.mss"
local n = 0
emu.addEventCallback(function()
  n = n + 1
  if n == at then
    L.saveState(name)
    L.shot(name:gsub("%.mss$", ".png"))
  end
end, emu.eventType.endFrame)
dofile(os.getenv("LIBDIR") .. "/boot.lua")
