-- tools/lua/walk.lua 를 그대로 돌리며, 메시지 루틴 24:8BAF 가 받은 번호(A)를 프레임과 함께 walk.txt 끝에 덧붙이고,
-- walk.txt 를 쓰는 끝 프레임에 세이브스테이트를 SAVE(SHOT_DIR 기준 파일 이름)로 남긴다. 구간을 이어 걸을 때 쓴다.
-- WALK 에 walk.lua 경로를 준다. 나머지 환경 변수는 walk.lua 와 같다.
-- SET="075B=12;21E7|01" 은 세이브스테이트를 불러온 바로 뒤 한 번 WRAM(7E 뱅크 하위 16비트 주소)을 고친다(dq5warp.lua 의 SET 과 같은 꼴).
package.path = os.getenv('LIBDIR') .. '/?.lua;' .. package.path
local L = require('lib')
local messages, frame = {}, 0
emu.addEventCallback(function() frame = frame + 1 end, emu.eventType.endFrame)
emu.addMemoryCallback(function()
  if #messages < 400 then messages[#messages + 1] = string.format('%03X@%d', emu.getState()['cpu.a'] & 0xFFFF, frame) end
end, emu.callbackType.exec, 0x248BAF, 0x248BAF)
local write, ended = L.write, {}
L.write = function(name, data)
  -- 미룬 멈춤을 기다리는 동안 walk.lua 가 끝 기록을 다시 쓰지 않게 한다
  if name == 'walk.txt' or name == 'end.png' then
    if ended[name] then return end
    ended[name] = true
  end
  if name == 'walk.txt' then
    data = data .. 'messages ' .. table.concat(messages, ',') .. '\n'
    local save = os.getenv('SAVE')
    if save then
      -- 세이브스테이트는 다음 명령의 exec 훅에서 만들어지므로(lib.lua), walk.lua 의 emu.stop 을 그 뒤로 미룬다
      local stop = emu.stop
      emu.stop = function(code)
        L.defer(function() L.write(save, emu.createSavestate()); stop(code) end)
      end
    end
  end
  return write(name, data)
end
dofile(os.getenv('WALK'))
-- walk.lua 가 세이브스테이트 불러오기를 먼저 미뤄 두었으므로 같은 exec 훅에서 그 뒤에 돈다
local sets = {}
for a, op, v in string.gmatch(os.getenv('SET') or '', '(%x+)([=|&])(%x+)') do
  sets[#sets + 1] = {0x7E0000 + tonumber(a, 16), op, tonumber(v, 16)}
end
if #sets > 0 then
  L.defer(function()
    local m = emu.memType.snesMemory
    for _, s in ipairs(sets) do
      local v = emu.read(s[1], m)
      if s[2] == '=' then v = s[3] elseif s[2] == '|' then v = v | s[3] else v = v & s[3] end
      emu.write(s[1], v, m)
    end
  end)
end
