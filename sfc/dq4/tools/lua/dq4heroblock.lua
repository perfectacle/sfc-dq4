-- dq4walkstate.lua(→ walk.lua)를 그대로 돌리며, 메시지 루틴 24:8BAF 가 SNAPMSG(16진) 번호를 처음 받은 뒤 SNAPDELAY
-- 프레임(기본 40)에 SNAPWATCH 값을 snap.txt 에, 화면을 snap.png 에 남긴다. 사건이 그 메시지를 띄울 때의 자리·방향을
-- 보려고 쓴다. SNAPWATCH 는 WATCH 와 같은 꼴("HX=7E3020:1;..."). 나머지 환경 변수는 dq4walkstate.lua 와 같다.
-- TRACK="00,0E,0F" 를 주면 프레임마다 그 슬롯의 화면 점 자리(셀 × 8 + 걸음 도중의 점 7E:3000·3060 위 3비트)와
-- 그리지 않음(인물 목록 밖, X = 80, 3380 bit7)을 track.txt 에 「프레임 슬롯:x,y,h ...」 로 적는다. 인물이 겹쳐 보이는지 셀 때 쓴다.
package.path = os.getenv('LIBDIR') .. '/?.lua;' .. package.path
local L = require('lib')
local snap = tonumber(os.getenv('SNAPMSG') or '', 16)
local delay = tonumber(os.getenv('SNAPDELAY') or '40')
local watches = {}
for name, a, len in string.gmatch(os.getenv('SNAPWATCH') or '', '([%w_]+)=(%x+):?(%d*)') do
  watches[#watches + 1] = {name, tonumber(a, 16), tonumber(len) or 1}
end
local track = {}
for s in string.gmatch(os.getenv('TRACK') or '', '(%x+)') do track[#track + 1] = tonumber(s, 16) end
local tracked = {}
local frame, at, done = 0, nil, false
emu.addEventCallback(function()
  frame = frame + 1
  if #track > 0 then
    local m, row = emu.memType.snesMemory, {tostring(frame)}
    for _, n in ipairs(track) do
      local x = (emu.read(0x7E3020 + n, m) & 0x7F) * 8 + (emu.read(0x7E3000 + n, m) >> 5)
      local y = (emu.read(0x7E3080 + n, m) & 0x7F) * 8 + (emu.read(0x7E3060 + n, m) >> 5)
      -- 인물 목록 뒤 슬롯($1982 부터)은 맵 OBJ 물체라 인물이 아니다
      local gone = n >= emu.read(0x7E1982, m) or emu.read(0x7E3020 + n, m) == 0x80 or
        (emu.read(0x7E3380 + n, m) & 0x80) ~= 0
      row[#row + 1] = string.format('%02X:%d,%d,%d', n, x, y, gone and 1 or 0)
    end
    tracked[#tracked + 1] = table.concat(row, ' ')
    if frame % 120 == 0 then L.write('track.txt', table.concat(tracked, '\n') .. '\n') end
  end
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
if #track > 0 then
  -- 끝 기록(walk.txt)을 쓰는 프레임에 track.txt 도 마저 쓴다. 이 뒤 dq4walkstate 가 L.write 를 다시 감싼다
  local write = L.write
  L.write = function(name, data)
    if name == 'walk.txt' then write('track.txt', table.concat(tracked, '\n') .. '\n') end
    return write(name, data)
  end
end
dofile(os.getenv('WALK_STATE'))
