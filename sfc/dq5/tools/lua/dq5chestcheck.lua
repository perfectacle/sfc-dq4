-- 조사 명령을 실제 컨트롤러로 눌러 보상·열림 비트와 최종 WRAM을 기록한다.
-- FLAG(·OLD_FLAG)를 주면 첫 프레임에 그 바이트를 0 으로 둔다. 빼면 WRAM 을 건드리지 않고 덤프만 한다.
package.path = os.getenv('LIBDIR') .. '/?.lua;' .. package.path
local L = require('lib')
if os.getenv('PREPARE') == '1' then
  local frame = 0
  emu.addEventCallback(function()
    frame = frame + 1
    if frame == 900 then
      L.saveState('scene.mss')
      L.shot('scene.png')
    elseif frame == 902 then
      emu.stop(0)
    end
  end, emu.eventType.endFrame)
  dofile(os.getenv('DRIVER'))
  return
end
L.loadState(os.getenv('STATE'))
local m = emu.memType.snesMemory
local n, i, left, log = 0, 1, nil, {}
local steps = {}
for button, frames in (os.getenv('INPUT') or ''):gmatch('([%w+]+):(%d+)') do
  steps[#steps + 1] = {button, tonumber(frames)}
end
local flag = os.getenv('FLAG') and tonumber(os.getenv('FLAG'), 16)
local function b(a) return emu.read(a, m) end
local function w(a) return emu.read16(a, m) end
emu.addMemoryCallback(function()
  log[#log + 1] = string.format('reward f=%d value=%04X map=%02X/%02X pos=%d,%d layer=%d',
    n, w(0x7E1E73), b(0x7E00BC), b(0x7E00BD), b(0x7E3020), b(0x7E3080), b(0x7E00C3))
end, emu.callbackType.exec, 0x12F43B, 0x12F43B)
emu.addMemoryCallback(function()
  local s = emu.getState()
  log[#log + 1] = string.format('message f=%d value=%04X', n, s['cpu.a'])
end, emu.callbackType.exec, 0x248BAF, 0x248BAF)
-- 보상 뒤 열림 비트를 켜는 12:F839. ret 는 스택 맨 위의 돌아갈 주소(JSR 이면 부른 명령 + 2)
emu.addMemoryCallback(function()
  local sp = emu.getState()['cpu.sp']
  log[#log + 1] = string.format('set f=%d index=%02X mask=%02X pend=%02X ret=%04X', n, b(0x7E1E80), b(0x7E1E81),
    b(0x7E291B), w(sp + 1))
end, emu.callbackType.exec, 0x12F839, 0x12F839)
emu.addEventCallback(function()
  n = n + 1
  if n == 1 then
    emu.write(0x7E2019, 100, m); emu.write(0x7E201A, 0, m); emu.write(0x7E201B, 0, m)
    if flag then emu.write(flag, 0, m) end
    local old = os.getenv('OLD_FLAG')
    if old then emu.write(tonumber(old, 16), 0, m) end
    L.dump('before.wram', emu.memType.snesWorkRam, 0x20000)
  end
  L.release()
  if i <= #steps then
    local step = steps[i]
    left = left or step[2]
    if step[1] ~= 'wait' then
      local keys = {}
      for key in step[1]:gmatch('[^+]+') do keys[key] = true end
      L.press(keys)
    end
    left = left - 1
    if left <= 0 then i = i + 1; left = nil end
  else
    L.dump('after.wram', emu.memType.snesWorkRam, 0x20000)
    L.shot('end.png')
    log[#log + 1] = string.format('end gold=%d flag=%02X', w(0x7E2019) | (b(0x7E201B) << 16), flag and b(flag) or 0)
    L.write('trace.txt', table.concat(log, '\n') .. '\n')
    emu.stop(0)
  end
end, emu.eventType.endFrame)
