-- 걷기 드라이버(boot.lua)가 붙인 무작위 전투에서 にげる 를 고른다. FLEE="1000-1600" 프레임 동안 60프레임마다
-- 아래(0~3)와 A(20~23)를 누른다. 그 밖의 입력은 드라이버 것이다. 덤프는 DUMPER(Lua 경로, 보통 dq5gfxdump.lua)가 한다.
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
require("lib")
local from, to = string.match(os.getenv("FLEE") or "", "(%d+)-(%d+)")
from, to = tonumber(from or "0"), tonumber(to or "0")
local n = 0
emu.addEventCallback(function() n = n + 1 end, emu.eventType.endFrame)
emu.addEventCallback(function()
  if n < from or n > to then return end
  local k = n % 60
  if k < 4 then emu.setInput({down = true}, 0) elseif k >= 20 and k < 24 then emu.setInput({a = true}, 0) end
end, emu.eventType.inputPolled)
dofile(os.getenv("DUMPER"))
