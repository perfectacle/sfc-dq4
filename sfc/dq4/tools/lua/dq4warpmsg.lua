-- dq4ch1walkcheck.py 가 순간이동 구간에 부른다. NEXT(dq5warp.lua)를 그대로 돌리며, 메시지 루틴 24:8BAF 가 받은 번호(A)를
-- 「번호@프레임」 으로 SHOT_DIR/warpmsg.txt 에 한 줄씩 적는다. 맵 번호($BC/$BD)가 TO 의 맵과 처음 같아진 프레임은
-- 「map@프레임」 으로 적는다(그 프레임부터의 메시지를 견준다). LIMIT 줄(기본 400)을 넘으면 「truncated」 한 줄을 남기고
-- 더 적지 않는다. 프레임은 이 스크립트가 끝난 프레임을 1부터 센 것이다.
local m = emu.memType.snesMemory
local h = io.open(os.getenv('SHOT_DIR') .. '/warpmsg.txt', 'w')
local limit = tonumber(os.getenv('LIMIT') or '400')
local bc, bd = (os.getenv('TO') or ''):match('^(%x%x)/(%x%x)')
bc, bd = tonumber(bc or '', 16), tonumber(bd or '', 16)
local frame, count, there = 0, 0, false
emu.addEventCallback(function()
  frame = frame + 1
  if not there and bc and emu.read(0x7E00BC, m) == bc and emu.read(0x7E00BD, m) == bd then
    there = true
    h:write(string.format('map@%d\n', frame))
    h:flush()
  end
end, emu.eventType.endFrame)
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
