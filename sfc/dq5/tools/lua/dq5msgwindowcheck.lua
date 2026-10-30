-- 전투 메시지 창 자리·높이 쓰기 실측(dq5msgwindowcheck.py 가 부름). DRIVER 의 입력을 재생하며
-- FROM 프레임부터 STEP 프레임마다 VRAM BG3 타일맵(워드 1C00~1FFF, 2KB)을 bg3.bin 에 이어 붙이고, SHOTEVERY 프레임마다
-- 화면을 fNNNNN.png 로 남긴다. SWAP="05E:006,118;069:006" 은 24:8C39 에 들어온 메시지 번호(A)를 차례로 바꾼다.
-- 24:A519·24:A523(▼ 기다림)·24:880A(FD ▼)·24:A569(줄 올리기)·24:8C39 에 들어온 프레임은 exec.txt 에 적는다.
package.path = os.getenv('LIBDIR') .. '/?.lua;' .. package.path
local L = require('lib')
local from, step = tonumber(os.getenv('FROM')), tonumber(os.getenv('STEP'))
local last, shotevery = tonumber(os.getenv('MAXF')) - 2, tonumber(os.getenv('SHOTEVERY') or '0')
local swaps = {}
for src, list in string.gmatch(os.getenv('SWAP') or '', '(%x+):([%x,]+)') do
  local q = {}
  for m in string.gmatch(list, '%x+') do q[#q + 1] = tonumber(m, 16) end
  swaps[tonumber(src, 16)] = q
end
local n, log, dumps = 0, {}, {}
emu.addMemoryCallback(function()
  local s = emu.getState()
  local a = s['cpu.a'] & 0xFFFF
  local q = swaps[a]
  if q and #q > 0 then
    s['cpu.a'] = (s['cpu.a'] & 0xFF0000) | table.remove(q, 1)
    emu.setState(s)
  end
  log[#log + 1] = string.format('%d 248C39 %03X', n, emu.getState()['cpu.a'] & 0xFFFF)
end, emu.callbackType.exec, 0x248C39, 0x248C39)
for _, addr in ipairs({0x24A519, 0x24A523, 0x24880A, 0x24A569}) do
  emu.addMemoryCallback(function()
    log[#log + 1] = string.format('%d %06X', n, addr)
  end, emu.callbackType.exec, addr, addr)
end
emu.addEventCallback(function()
  n = n + 1
  if n >= from and (n - from) % step == 0 and n <= last then
    local t = {}
    for i = 0, 0x7FF do t[#t + 1] = string.char(emu.read(0x3800 + i, emu.memType.snesVideoRam)) end
    dumps[#dumps + 1] = table.concat(t)
    if shotevery > 0 and (n - from) % shotevery == 0 then L.shot(string.format('f%05d.png', n)) end
  end
  if n == last then
    L.write('bg3.bin', table.concat(dumps))
    L.write('exec.txt', table.concat(log, '\n') .. '\n')
  end
end, emu.eventType.endFrame)
dofile(os.getenv('DRIVER'))
