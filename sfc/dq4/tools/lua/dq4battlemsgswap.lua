-- 전투 메시지 바꿔 띄우기(dq4battlemsgcheck.py 가 부름). DRIVER(dq5warp.lua)로 전투를 붙이고, 24:8C39 에 들어올 때마다
-- A(메시지 번호)를 SWAP 목록의 다음 번호로 바꾼다. 바꾼 뒤 SHOTDELAY(기본 40) 프레임에 화면을 m<번호>.png 로 찍고,
-- 번호를 바꾼 프레임을 swap.txt 에 "프레임 번호" 로 적는다. POOLCODES(16진 목록)를 주면 찍을 때 글자 격자(7E:1DD5, 156바이트)에
-- 든 풀 코드 수를 그 줄 끝에 붙인다.
package.path = os.getenv('LIBDIR') .. '/?.lua;' .. package.path
local L = require('lib')
local list = {}
for a in string.gmatch(os.getenv('SWAP') or '', '%x+') do list[#list + 1] = tonumber(a, 16) end
local delay = tonumber(os.getenv('SHOTDELAY') or '40')
local pool = {}
for a in string.gmatch(os.getenv('POOLCODES') or '', '%x+') do pool[tonumber(a, 16)] = true end
local n, k, log, shots, used = 0, 1, {}, {}, {}
emu.addMemoryCallback(function()
  if k > #list then return end
  local s = emu.getState()
  s['cpu.a'] = list[k]
  emu.setState(s)
  log[#log + 1] = string.format('%d %03X', n, list[k])
  shots[n + delay] = list[k]
  k = k + 1
end, emu.callbackType.exec, 0x248C39, 0x248C39)
emu.addEventCallback(function()
  n = n + 1
  if shots[n] then
    L.shot(string.format('m%03X.png', shots[n]))
    local seen, c = {}, 0
    for i = 0, 155 do
      local b = emu.read(0x7E1DD5 + i, emu.memType.snesMemory)
      if pool[b] and not seen[b] then seen[b] = true; c = c + 1 end
    end
    used[#used + 1] = string.format('%03X %d', shots[n], c)
  end
end, emu.eventType.endFrame)
local write = L.write
L.write = function(name, data)
  if name == 'warp.txt' then
    write('swap.txt', table.concat(log, '\n') .. '\n')
    write('used.txt', table.concat(used, '\n') .. '\n')
  end
  return write(name, data)
end
dofile(os.getenv('DRIVER'))
