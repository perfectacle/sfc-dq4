-- dq4namegamecheck.py 가 부른다. 세이브스테이트(STATE)를 불러 주인공 이름 7E:2001~2008 에 NAME(16진)을 쓰고,
-- PRE 입력으로 말을 건 뒤 보행 메시지의 첫 글자 코드를 1012(주인공 이름)로 바꾼다. 24:A7B6 이 24:A832 로 쌓는
-- 글자 코드를 FFFF(이름 끝)까지 codes.txt 에, SHOT 프레임 화면을 shot.png 에 남기고 MAXF 에서 멈춘다.
package.path = os.getenv('LIBDIR') .. '/?.lua;' .. package.path
local L = require('lib')
L.loadState(os.getenv('STATE'))
local m = emu.memType.snesMemory
local name = {}
for h in string.gmatch(os.getenv('NAME'), '%x%x') do name[#name + 1] = tonumber(h, 16) end
local seq = {}
for tok in string.gmatch(os.getenv('PRE') or '', '[^,]+') do
  local b, f = tok:match('([%w+]+):(%d+)')
  seq[#seq + 1] = {b, tonumber(f)}
end
local shot, maxf = tonumber(os.getenv('SHOT')), tonumber(os.getenv('MAXF'))
local frame, si, left, injected, collecting, codes = 0, 1, nil, false, false, {}
emu.addMemoryCallback(function()
  if injected then return end
  local s = emu.getState()
  if (s['cpu.a'] & 0xFFFF) < 0x1000 then
    s['cpu.a'] = 0x1012
    emu.setState(s)
    injected, collecting = true, true
  end
end, emu.callbackType.exec, 0x2481A4, 0x2481A4)
emu.addMemoryCallback(function()
  if not collecting then return end
  local a = emu.getState()['cpu.a'] & 0xFFFF
  codes[#codes + 1] = string.format('%04X', a)
  if a == 0xFFFF then collecting = false end
end, emu.callbackType.exec, 0x24A832, 0x24A832)
emu.addEventCallback(function()
  frame = frame + 1
  if frame >= 2 and frame <= 10 then
    for i = 1, 8 do emu.write(0x7E2000 + i, name[i] or 0x01, m) end
  end
  L.release()
  if si <= #seq then
    local s = seq[si]
    if left == nil then left = s[2] end
    if s[1] ~= 'wait' then local t = {}; for b in s[1]:gmatch('[^+]+') do t[b] = true end; L.press(t) end
    left = left - 1
    if left <= 0 then si = si + 1; left = nil end
  end
  if frame == shot then L.shot('shot.png') end
  if frame == maxf then
    L.write('codes.txt', table.concat(codes, ' ') .. '\n')
    emu.stop()
  end
end, emu.eventType.endFrame)
