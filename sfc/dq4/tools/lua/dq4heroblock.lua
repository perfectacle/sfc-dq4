-- dq4walkstate.lua(→ walk.lua)를 그대로 돌리며, 메시지 루틴 24:8BAF 가 SNAPMSG(16진) 번호를 처음 받은 뒤 SNAPDELAY
-- 프레임(기본 40)에 SNAPWATCH 값을 snap.txt 에, 화면을 snap.png 에 남긴다. 사건이 그 메시지를 띄울 때의 자리·방향을
-- 보려고 쓴다. SNAPWATCH 는 WATCH 와 같은 꼴("HX=7E3020:1;..."). 나머지 환경 변수는 dq4walkstate.lua 와 같다.
package.path = os.getenv('LIBDIR') .. '/?.lua;' .. package.path
local L = require('lib')
local snap = tonumber(os.getenv('SNAPMSG') or '', 16)
local delay = tonumber(os.getenv('SNAPDELAY') or '40')
local watches = {}
for name, a, len in string.gmatch(os.getenv('SNAPWATCH') or '', '([%w_]+)=(%x+):?(%d*)') do
  watches[#watches + 1] = {name, tonumber(a, 16), tonumber(len) or 1}
end
local frame, at, done = 0, nil, false
emu.addEventCallback(function()
  frame = frame + 1
  if at and not done and frame >= at then
    done = true
    local m, out = emu.memType.snesMemory, {string.format('frame %d', frame)}
    for _, w in ipairs(watches) do
      local v = 0
      for k = w[3] - 1, 0, -1 do v = v * 256 + emu.read(w[2] + k, m) end
      out[#out + 1] = string.format('%s=%0' .. (w[3] * 2) .. 'X', w[1], v)
    end
    L.write('snap.txt', table.concat(out, '\n') .. '\n')
    L.shot('snap.png')
  end
end, emu.eventType.endFrame)
if snap then
  emu.addMemoryCallback(function()
    if not at and (emu.getState()['cpu.a'] & 0xFFFF) == snap then at = frame + delay end
  end, emu.callbackType.exec, 0x248BAF, 0x248BAF)
end
dofile(os.getenv('WALK_STATE'))
