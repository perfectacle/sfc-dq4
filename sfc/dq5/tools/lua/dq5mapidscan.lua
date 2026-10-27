-- 맵 번호 $BC·$BD(직접 페이지 00:00BC·00:00BD 와 7E 거울)를 읽은 PC 를 모으고 DRIVER 장면 드라이버를 실행한다.
-- Mesen 은 읽은 명령 다음 명령의 PC 를 준다. 드라이버가 emu.stop 을 부를 때 SHOT_DIR/mapid.txt 에 "PC 횟수" 로 적는다.
package.path = os.getenv('LIBDIR') .. '/?.lua;' .. package.path
local L = require('lib')
local seen = {}
-- 직접 페이지는 뱅크 00, 긴 주소는 7E 거울로 읽힌다. 뱅크 80 거울도 함께 본다.
for _, r in ipairs({{0x0000BC, 0x0000BD}, {0x7E00BC, 0x7E00BD}, {0x8000BC, 0x8000BD}}) do
  emu.addMemoryCallback(function()
    local s = emu.getState()
    local k = string.format('%02X%04X', s['cpu.k'], s['cpu.pc'])
    seen[k] = (seen[k] or 0) + 1
  end, emu.callbackType.read, r[1], r[2])
end
local stop = emu.stop
emu.stop = function(code)
  local t = {}
  for k, c in pairs(seen) do t[#t + 1] = k .. ' ' .. c end
  table.sort(t)
  L.write('mapid.txt', table.concat(t, '\n') .. '\n')
  return stop(code)
end
dofile(os.getenv('DRIVER'))
