-- 창 자리·크기 쓰기 실측(dq5windowcheck.py 가 부름). DRIVER 의 입력을 재생하며 FRAMES(쉼표로 나눈 프레임)마다
-- BG3 타일맵 버퍼 7E:5000~57FF 를 bg3-fNNNNN.bin 으로, 화면을 fNNNNN.png 로 남긴다.
package.path = os.getenv('LIBDIR') .. '/?.lua;' .. package.path
local L = require('lib')
local m = emu.memType.snesMemory
local frames = {}
for f in string.gmatch(os.getenv('FRAMES') or '', '%d+') do frames[tonumber(f)] = true end
local n = 0
emu.addEventCallback(function()
  n = n + 1
  if frames[n] then
    local t = {}
    for i = 0, 0x7FF do t[#t + 1] = string.char(emu.read(0x7E5000 + i, m)) end
    L.write(string.format('bg3-f%05d.bin', n), table.concat(t))
    L.shot(string.format('f%05d.png', n))
  end
end, emu.eventType.endFrame)
dofile(os.getenv('DRIVER'))
