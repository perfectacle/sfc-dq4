-- dq4readsetcheck 의 오류 장면. READSET_ERR 가 고른 자리에서 오류를 낸다(어느 경우든 캐시에 들면 안 된다).
--   top       스크립트 맨 위에서
--   callback  30프레임째 콜백 안에서(testrunner 는 삼키고 계속 돈다), 60프레임째 emu.stop(0)
--   stop      30프레임째 emu.stop(0) 바로 뒤 같은 콜백에서
--   dump      30프레임째 os.rename 을 던지게 바꾼 뒤 emu.stop(0). 머리말이 읽은 집합을 쓰다 실패해도 멈춰야 한다
local mode = os.getenv("READSET_ERR")
if mode == "top" then error("readset err: top") end
local n = 0
emu.addEventCallback(function()
  n = n + 1
  if mode == "callback" and n == 30 then error("readset err: callback") end
  if mode == "dump" and n == 30 then
    os.rename = function() error("readset err: rename") end
    emu.stop(0)
  end
  if mode == "stop" and n == 30 then
    emu.stop(0)
    error("readset err: after stop")
  end
  if n == 60 then emu.stop(0) end
end, emu.eventType.endFrame)
