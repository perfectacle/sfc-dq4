-- DQ5 소리 명령 기록. 24:FF83(소리 명령 대기열)에 들어올 때 명령(A)·인자(스택의 PHA 값)·부른 곳(JSL 24:FExx 의 자리)을
-- snd.txt 에 적는다(MAXF-1 프레임). SHOTS 프레임에 화면. 드라이버(boot.lua, 보통 dq5warp.lua·walk.lua) 뒤에 붙여 쓴다.
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local L = require("lib")
local n, log = 0, {}
local shots = {}
for a in string.gmatch(os.getenv("SHOTS") or "", "[^,]+") do shots[tonumber(a)] = true end
local m = emu.memType.snesMemory
emu.addMemoryCallback(function()
  local s = emu.getState()
  local sp = s["cpu.sp"]
  local arg = emu.read(sp + 1, m)
  -- 스택: [arg][P][RTL 3바이트(JSL 24:FExx 의 리턴)]
  local rl = emu.read(sp + 3, m) | emu.read(sp + 4, m) << 8
  local rb = emu.read(sp + 5, m)
  log[#log + 1] = string.format("%d cmd=%02X arg=%02X from=%02X:%04X", n, s["cpu.a"] & 0xFF, arg, rb, (rl - 3) & 0xFFFF)
end, emu.callbackType.exec, 0x24FF83, 0x24FF83)
emu.addEventCallback(function()
  n = n + 1
  if shots[n] then L.shot(string.format("s%05d.png", n)) end
  if n == tonumber(os.getenv("MAXF") or "0") - 1 then L.write("snd.txt", table.concat(log, "\n") .. "\n") end
end, emu.eventType.endFrame)
dofile(os.getenv("LIBDIR") .. "/boot.lua")
