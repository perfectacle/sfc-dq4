-- dq5scriptcheck.py의 관측 프로브. 표 조회·이벤트 명령·인물 좌표를 기록하고 DRIVER 보행 드라이버를 실행한다.
package.path = os.getenv('LIBDIR') .. '/?.lua;' .. package.path
local L = require('lib')
local m = emu.memType.snesMemory
local log, n = {}, 0
local function b(a) return emu.read(a, m) end
local function w(a) return emu.read16(a, m) end
for _, pc in ipairs({0x23E2F4,0x23E29A,0x00BED2}) do
  emu.addMemoryCallback(function()
    local s = emu.getState()
    local ptr = w(0x7E19B3) | (b(0x7E19B5) << 16)
    if #log < 4000 then log[#log+1] = string.format('f%d pc=%06X a=%04X event=%06X op=%02X hero=%d,%d flag=%02X',n,pc,s['cpu.a'],ptr,b(ptr),b(0x7E3020),b(0x7E3080),b(0x7E220F)) end
  end, emu.callbackType.exec,pc,pc)
end
local last = ''
emu.addEventCallback(function()
  n=n+1
  local rows={}
  for i=0,15 do
    rows[#rows+1]=string.format('%02X:%02X,%02X@%02X%02X%02X/m%02X',i,b(0x7E3020+i),b(0x7E3080+i),b(0x7E34C0+i),b(0x7E34A0+i),b(0x7E3480+i),b(0x7E3300+i))
  end
  local line=table.concat(rows,' ')
  if line~=last then log[#log+1]=string.format('f%d map=%02X/%02X %s',n,b(0x7E00BC),b(0x7E00BD),line); last=line end
  if n==tonumber(os.getenv('MAXF'))-1 then L.write('trace.txt',table.concat(log,'\n')..'\n') end
end, emu.eventType.endFrame)
dofile(os.getenv('DRIVER'))
