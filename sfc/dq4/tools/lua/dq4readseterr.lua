-- dq4readsetcheck 의 오류 장면. READSET_ERR 가 고른 자리에서 오류를 낸다(어느 경우든 캐시에 들면 안 된다).
--   top       스크립트 맨 위에서
--   callback  30프레임째 콜백 안에서(testrunner 는 삼키고 계속 돈다), 60프레임째 emu.stop(0)
--   stop      30프레임째 emu.stop(0) 바로 뒤 같은 콜백에서
local mode = os.getenv("READSET_ERR")
if mode == "top" then error("readset err: top") end
local n = 0
emu.addEventCallback(function()
  n = n + 1
  if mode == "callback" and n == 30 then error("readset err: callback") end
  if mode == "stop" and n == 30 then
    emu.stop(0)
    error("readset err: after stop")
  end
  if n == 60 then emu.stop(0) end
end, emu.eventType.endFrame)
