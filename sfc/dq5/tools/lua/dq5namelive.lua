-- 이름 문자열(21:955D)을 읽은 뒤 살아 있는 직접 페이지 재기. DRIVER(dq5warp·dq5warptrace·dq5msg 등)의 입력을 재생하며
-- 21:959A(복사 끝)부터 그 프레임 끝까지 WRAM $00~$3F 의 첫 접근이 읽기이고 이름 길이보다 뒤인 주소를 live.txt 에 모은다.
-- 줄 꼴: t<이름 표> len=<길이> $<주소> pc=<읽은 명령 다음 PC> n=<횟수>.
package.path = os.getenv('LIBDIR') .. '/?.lua;' .. package.path
local L = require('lib')
local m = emu.memType.snesMemory
local n, phase, len, st, tab = 0, false, 0, {}, 0
local live, calls = {}, 0
emu.addMemoryCallback(function()
  tab = emu.read(0x7E0043, m)
end, emu.callbackType.exec, 0x21955D, 0x21955D)
emu.addMemoryCallback(function()
  phase, st, len, calls = true, {}, emu.read(0x7E0000, m), calls + 1
end, emu.callbackType.exec, 0x21959A, 0x21959A)
emu.addMemoryCallback(function(addr)
  if not phase then return end
  local a = addr & 0xFFFF
  if st[a] == nil then
    st[a] = 'R'
    if a > len then
      local s = emu.getState()
      local key = string.format('t%02X len=%02X $%02X pc=%02X:%04X', tab, len, a, s['cpu.k'], s['cpu.pc'])
      live[key] = (live[key] or 0) + 1
    end
  end
end, emu.callbackType.read, 0x0000, 0x003F, emu.cpuType.snes, emu.memType.snesWorkRam)
emu.addMemoryCallback(function(addr)
  if phase and st[addr & 0xFFFF] == nil then st[addr & 0xFFFF] = 'W' end
end, emu.callbackType.write, 0x0000, 0x003F, emu.cpuType.snes, emu.memType.snesWorkRam)
emu.addEventCallback(function() n = n + 1; phase = false end, emu.eventType.endFrame)
local write = L.write
L.write = function(name, data)
  if name == 'warp.txt' or name == 'battle.txt' or name == 'msg.txt' then
    local t = {string.format('calls=%d', calls)}
    for k, v in pairs(live) do t[#t + 1] = k .. ' n=' .. v end
    table.sort(t)
    write('live.txt', table.concat(t, '\n') .. '\n')
  end
  return write(name, data)
end
dofile(os.getenv('DRIVER'))
