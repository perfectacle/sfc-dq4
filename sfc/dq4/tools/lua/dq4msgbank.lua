-- 보행 메시지 뱅크 검사(dq4msgbankcheck.py 가 부름). DRIVER(dq5warp.lua)로 장면을 띄우고, 메시지 입구 24:8BAF 에 처음
-- 들어올 때 A(메시지 번호)를 SWAP 으로 바꾼다. 그 뒤 색인 훅(24:9E07)에서 돌아온 자리(24:8BD9)의 스트림 주소 $F0~$F2 와,
-- 디코더 사본의 RTL(RETURN_PC)이 돌려주는 글자 코드를 차례로 decoded.txt 에 적는다. 24:8BAF 는 같은 16개 묶음의 앞
-- 메시지를 디코더로 건너뛰므로 코드는 묶음 첫 메시지부터 나온다.
package.path = os.getenv('LIBDIR') .. '/?.lua;' .. package.path
local L = require('lib')
local m = emu.memType.snesMemory
local swap = tonumber(os.getenv('SWAP'), 16)
local ret = tonumber(os.getenv('RETURN_PC'), 16)
local limit = tonumber(os.getenv('CODES') or '2000')
local state, lines, count = 0, {}, 0
emu.addMemoryCallback(function()
  if state ~= 0 then return end
  local s = emu.getState()
  s['cpu.a'] = swap
  emu.setState(s)
  state = 1
end, emu.callbackType.exec, 0x248BAF, 0x248BAF)
emu.addMemoryCallback(function()
  if state ~= 1 then return end
  lines[#lines + 1] = string.format('stream=%06X', emu.read16(0xF0, m) | (emu.read(0xF2, m) << 16))
  state = 2
end, emu.callbackType.exec, 0x248BD9, 0x248BD9)
emu.addMemoryCallback(function()
  if state == 2 and count < limit then
    lines[#lines + 1] = string.format('%04X', emu.getState()['cpu.a'] & 0x1FFF)
    count = count + 1
  end
end, emu.callbackType.exec, ret, ret)
local write = L.write
L.write = function(name, data)
  if name == 'warp.txt' then write('decoded.txt', table.concat(lines, '\n') .. '\n') end
  return write(name, data)
end
dofile(os.getenv('DRIVER'))
