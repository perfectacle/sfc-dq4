-- 조사 명령을 실제 컨트롤러로 눌러 보상·열림 비트와 최종 WRAM을 기록한다.
-- FLAG(·OLD_FLAG)를 주면 첫 프레임에 그 바이트를 0 으로 둔다. 빼면 WRAM 을 건드리지 않고 덤프만 한다.
-- SAVE 를 주면 입력을 다 누른 뒤 그 이름으로 세이브스테이트를 남긴다.
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
local n, i, left, log, ended = 0, 1, nil, {}, nil
local steps = {}
for button, frames in (os.getenv('INPUT') or ''):gmatch('([%w+]+):(%d+)') do
  steps[#steps + 1] = {button, tonumber(frames)}
end
local flag = os.getenv('FLAG') and tonumber(os.getenv('FLAG'), 16)
-- SETONCE="7E075E=00;7E36EB=06" 첫 프레임에 한 번 쓴다(CPU 주소=값)
local setonce = {}
for a, v in string.gmatch(os.getenv('SETONCE') or '', '(%x+)=(%x+)') do setonce[#setonce + 1] = {tonumber(a, 16), tonumber(v, 16)} end
-- RESETAT 프레임에 emu.reset()(교회 기록을 SRAM 에서 불러오는 장면용. INPUT 이 타이틀에서 불러오기를 누른다)
local resetat = tonumber(os.getenv('RESETAT') or '-1')
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
-- 조사 종류(12:E4C9 가 돌려준 A)로 12:E4A7 표를 뛰는 자리. 종류 1(12:EF92)은 보상이 CA 면 빛 블록을 되돌린다(12:EFB9)
emu.addMemoryCallback(function()
  log[#log + 1] = string.format('kind f=%d value=%02X', n, emu.getState()['cpu.a'] & 0xFF)
end, emu.callbackType.exec, 0x12E4A3, 0x12E4A3)
emu.addMemoryCallback(function()
  log[#log + 1] = string.format('light f=%d reward=%04X', n, w(0x7E1E73))
end, emu.callbackType.exec, 0x12EFB9, 0x12EFB9)
-- 상자 열기 12:E66F(상자 번호 16비트 훅이면 그 JML). pend 는 들어올 때의 넘길 마스크 칸 7E:291B
emu.addMemoryCallback(function()
  log[#log + 1] = string.format('open f=%d pend=%02X pos=%d,%d', n, b(0x7E291B), b(0x7E3020), b(0x7E3080))
end, emu.callbackType.exec, 0x12E66F, 0x12E66F)
-- 맵 안 순서를 세는 2A:F224. 상자 번호 16비트 훅은 291B 를 지운 뒤에 부른다
emu.addMemoryCallback(function()
  log[#log + 1] = string.format('count f=%d pend=%02X', n, b(0x7E291B))
end, emu.callbackType.exec, 0x2AF224, 0x2AF224)
-- 상자 몬스터: 12:F4A4 의 JSL $01868B(전투)와, 전투에서 돌아온 다음 명령 12:F4A8(JSR $F839)
emu.addMemoryCallback(function()
  log[#log + 1] = string.format('battle f=%d group=%02X', n, emu.getState()['cpu.a'] & 0xFF)
end, emu.callbackType.exec, 0x12F4A4, 0x12F4A4)
emu.addMemoryCallback(function()
  log[#log + 1] = string.format('back f=%d pend=%02X', n, b(0x7E291B))
end, emu.callbackType.exec, 0x12F4A8, 0x12F4A8)
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
    for _, p in ipairs(setonce) do emu.write(p[1], p[2], m) end
    local old = os.getenv('OLD_FLAG')
    if old then emu.write(tonumber(old, 16), 0, m) end
    L.dump('before.wram', emu.memType.snesWorkRam, 0x20000)
  end
  if n == resetat then emu.reset() end
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
  elseif not ended then
    ended = n
    L.dump('after.wram', emu.memType.snesWorkRam, 0x20000)
    -- SRAM=1 이면 70:0000~1FFF(기록 칸 1 은 70:0012~)도 남긴다
    if os.getenv('SRAM') == '1' then
      local t = {}
      for a = 0x700000, 0x701FFF do t[#t + 1] = string.char(b(a)) end
      L.write('after.sram', table.concat(t))
    end
    L.shot('end.png')
    -- saveState 는 다음 프레임에 쓰이므로 몇 프레임 뒤에 멈춘다
    if os.getenv('SAVE') then L.saveState(os.getenv('SAVE')) end
    log[#log + 1] = string.format('end gold=%d flag=%02X map=%02X/%02X', w(0x7E2019) | (b(0x7E201B) << 16),
      flag and b(flag) or 0, b(0x7E00BC), b(0x7E00BD))
    L.write('trace.txt', table.concat(log, '\n') .. '\n')
  elseif n >= ended + 3 then
    emu.stop(0)
  end
end, emu.eventType.endFrame)
