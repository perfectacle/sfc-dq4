-- dq5textgrowcheck.py 의 관측 프로브. 24:8BAF 가 받은 번호마다 24:8B98 이 푼 첫 64코드(디코더 사본의 RTL,
-- RETURN_PC 에서 본 A)와 그때의 스트림 주소($F0~$F2)를 decoded.txt 에 남기고 INNER 프로브를 그대로 돌린다.
-- 줄 꼴: 번호 스트림 코드…(16진). INNER 가 L.write 로 결과를 쓸 때마다 함께 쓴다.
package.path = os.getenv('LIBDIR') .. '/?.lua;' .. package.path
local L = require('lib')
local m = emu.memType.snesMemory
local ret = tonumber(os.getenv('RETURN_PC'), 16)
local rows, cur = {}, nil
emu.addMemoryCallback(function()
  cur = nil
  if #rows < 32 then
    cur = {string.format('%04X', emu.getState()['cpu.a'] & 0xFFFF)}
    rows[#rows + 1] = cur
  end
end, emu.callbackType.exec, 0x248BAF, 0x248BAF)
emu.addMemoryCallback(function()
  if cur and #cur == 1 then
    cur[2] = string.format('%06X', emu.read16(0xF0, m) | (emu.read(0xF2, m) << 16))
  end
end, emu.callbackType.exec, 0x248B98, 0x248B98)
emu.addMemoryCallback(function()
  if cur and #cur >= 2 and #cur < 66 then
    cur[#cur + 1] = string.format('%04X', emu.getState()['cpu.a'] & 0x1FFF)
  end
end, emu.callbackType.exec, ret, ret)
local write = L.write
L.write = function(name, data)
  if name ~= 'decoded.txt' then
    local lines = {}
    for i, row in ipairs(rows) do lines[i] = table.concat(row, ' ') end
    write('decoded.txt', table.concat(lines, '\n') .. '\n')
  end
  return write(name, data)
end
dofile(os.getenv('INNER'))
