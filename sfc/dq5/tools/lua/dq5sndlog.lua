-- DQ5 소리 명령 기록. 24:FF83(소리 명령 대기열)에 들어올 때 명령(A)·인자(스택의 PHA 값)·부른 곳(JSL 24:FExx 의 자리)을
-- snd.txt 에 적는다(MAXF-1 프레임). SHOTS 프레임에 화면. 드라이버(boot.lua, 보통 dq5warp.lua·walk.lua) 뒤에 붙여 쓴다. DSP=1 이면 프레임마다 DSP 레지스터(주 음량·메아리·ENVX 합·KON·KOF·FLG·채널 0 음량)를 dsp.txt 로.
-- HCMD·HARG(·HX) 를 주면 처음 들어온 HFROM_CMD·HFROM_ARG 명령(예: 메뉴 효과음 0C 33)을 그 명령·인자·X 로 바꿔 보낸다.
-- WATCH=주소,… 는 그 주소를 실행한 프레임을, SPCDUMP=프레임,… 은 그 프레임의 SPC RAM 64KB 와 DSP 레지스터 128바이트를 spcNNNNN.bin·dspNNNNN.bin 으로 남긴다(커밋 금지).
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local L = require("lib")
local n, log = 0, {}
local shots = {}
for a in string.gmatch(os.getenv("SHOTS") or "", "[^,]+") do shots[tonumber(a)] = true end
local m = emu.memType.snesMemory
local hijacked = false
local hc0, ha0 = tonumber(os.getenv("HFROM_CMD") or "-1", 16), tonumber(os.getenv("HFROM_ARG") or "-1", 16)
emu.addMemoryCallback(function()
  local s = emu.getState()
  if not hijacked and os.getenv("HCMD") and (s["cpu.a"] & 0xFF) == hc0 and emu.read(s["cpu.sp"] + 1, m) == ha0 then
    hijacked = true
    s["cpu.a"] = (s["cpu.a"] & 0xFF00) | tonumber(os.getenv("HCMD"), 16)
    s["cpu.x"] = tonumber(os.getenv("HX") or "0", 16)
    emu.setState(s)
    emu.write(s["cpu.sp"] + 1, tonumber(os.getenv("HARG"), 16), m)
    s = emu.getState()
  end
  local sp = s["cpu.sp"]
  local arg = emu.read(sp + 1, m)
  -- 스택: [arg][P][RTL 3바이트(JSL 24:FExx 의 리턴)]
  local rl = emu.read(sp + 3, m) | emu.read(sp + 4, m) << 8
  local rb = emu.read(sp + 5, m)
  log[#log + 1] = string.format("%d cmd=%02X arg=%02X from=%02X:%04X", n, s["cpu.a"] & 0xFF, arg, rb, (rl - 3) & 0xFFFF)
end, emu.callbackType.exec, 0x24FF83, 0x24FF83)
local dsp = {}
for a in string.gmatch(os.getenv("WATCH") or "", "[^,]+") do
  local addr = tonumber(a, 16)
  emu.addMemoryCallback(function() log[#log + 1] = string.format("%d exec %06X", n, addr) end, emu.callbackType.exec, addr, addr)
end
emu.addEventCallback(function()
  n = n + 1
  if os.getenv("DSP") then
    local d = emu.memType.spcDspRegisters
    local env = 0
    for v = 0, 7 do env = env + emu.read(v * 16 + 8, d) end
    dsp[#dsp + 1] = string.format("%d mvol=%02X,%02X evol=%02X,%02X env=%d kon=%02X kof=%02X flg=%02X v0=%02X,%02X", n,
      emu.read(0x0C, d), emu.read(0x1C, d), emu.read(0x2C, d), emu.read(0x3C, d), env, emu.read(0x4C, d), emu.read(0x5C, d),
      emu.read(0x6C, d), emu.read(0x00, d), emu.read(0x01, d))
  end
  for a in string.gmatch(os.getenv("SPCDUMP") or "", "[^,]+") do
    if tonumber(a) == n then
      local t = {}
      for i = 0, 0xFFFF do t[#t + 1] = string.char(emu.read(i, emu.memType.spcRam)) end
      local fh = io.open(os.getenv("SHOT_DIR") .. string.format("/spc%05d.bin", n), "wb"); fh:write(table.concat(t)); fh:close()
      t = {}
      for i = 0, 0x7F do t[#t + 1] = string.char(emu.read(i, emu.memType.spcDspRegisters)) end
      fh = io.open(os.getenv("SHOT_DIR") .. string.format("/dsp%05d.bin", n), "wb"); fh:write(table.concat(t)); fh:close()
    end
  end
  if shots[n] then L.shot(string.format("s%05d.png", n)) end
  if n == tonumber(os.getenv("MAXF") or "0") - 1 then L.write("snd.txt", table.concat(log, "\n") .. "\n"); if #dsp > 0 then L.write("dsp.txt", table.concat(dsp, "\n") .. "\n") end end
end, emu.eventType.endFrame)
dofile(os.getenv("LIBDIR") .. "/boot.lua")
