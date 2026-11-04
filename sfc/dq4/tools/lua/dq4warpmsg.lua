-- dq4ch1walkcheck.py 가 순간이동 구간에 부른다. NEXT(dq5warp.lua)를 그대로 돌리며, 메시지 루틴 24:8BAF 가 받은 번호(A)를
-- 「번호@프레임」 으로 SHOT_DIR/warpmsg.txt 에 한 줄씩 적는다(프레임은 dq5warp.lua 의 fNNNNN 과 같은 세기).
-- LIMIT 줄을 넘으면 「truncated」 한 줄을 남기고 더 적지 않는다.
local h = io.open(os.getenv('SHOT_DIR') .. '/warpmsg.txt', 'w')
local limit = tonumber(os.getenv('LIMIT') or '400')
local frame, count = 0, 0
emu.addEventCallback(function() frame = frame + 1 end, emu.eventType.endFrame)
emu.addMemoryCallback(function()
  count = count + 1
  if count <= limit then
    h:write(string.format('%03X@%d\n', emu.getState()['cpu.a'] & 0xFFFF, frame))
  elseif count == limit + 1 then
    h:write('truncated\n')
  end
  h:flush()
end, emu.callbackType.exec, 0x248BAF, 0x248BAF)
dofile(os.getenv('NEXT'))
