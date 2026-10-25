-- DQ5 곡·효과음 하나를 틀고 SPC700 상태(spcRam 64KB, DSP 레지스터 128바이트, CPU 레지스터·타이머)를 남긴다.
-- dq5spcfile.py 가 부르고 .spc 로 묶는다. STATE 세이브스테이트에서 시작한다.
-- CMDS="20:1A:00:00;24:01:05:00" 은 그 프레임(스테이트를 불러온 뒤부터)에 소리 대기열(7E:1D95~)에 [명령][인자][X] 를 넣는다.
--   넣는 자리는 24:FF83 과 같은 셈으로 고르고, 2B 뱅크가 다음 프레임부터 SPC 로 보낸다.
-- FULLSET=n 이면 곡 묶음(2B:E67F) n 번째 레코드의 둘째 바이트(곡을 틀기 전에 보낼 샘플 수)를 샘플 수로 바꿔,
--   곡이 시작하기 전에 샘플을 모두 보내게 한다(롬 그 자체는 바꾸지 않고 이 실행에서만).
-- WAITSONG=n 이면 SPC 의 곡 자리(03AF 곡 번호, 03B7 켜짐)에 n 이 오르고 대기열이 빈 첫 프레임에서 DELAY 프레임 뒤에 남긴다.
-- 결과: spc.bin, dsp.bin, regs.txt(남긴 프레임·CPU 레지스터·포트·타이머·목소리 BRR 표본). MAXF 에 멈춘다.
-- ENVLOG=1 이면 남긴 뒤 프레임마다 목소리별 음높이·샘플 번호(DSP x2·x3·x4)를 env.txt 로(.spc 를 따로 틀어 견줄 때).
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local L = require("lib")
L.loadState(os.getenv("STATE"))
local m = emu.memType.snesMemory
local spc = emu.memType.spcRam
local dspT = emu.memType.spcDspRegisters
local maxf = tonumber(os.getenv("MAXF") or "600")
local delay = tonumber(os.getenv("DELAY") or "0")
local want = tonumber(os.getenv("WAITSONG") or "-1", 16)
local cmds = {}
for f, c, a, x in string.gmatch(os.getenv("CMDS") or "", "(%d+):(%x+):(%x+):(%x+)") do
  cmds[tonumber(f)] = {tonumber(c, 16), tonumber(a, 16), tonumber(x, 16)}
end

local fullset = tonumber(os.getenv("FULLSET") or "-1", 16)
if fullset >= 0 then
  local prg = emu.memType.snesPrgRom
  local o = 0x2B * 0x8000 + (0xE67F - 0x8000)
  for _ = 1, fullset do o = o + emu.read(o, prg) + 2 end
  emu.write(o + 1, emu.read(o, prg), prg)
end

local function enqueue(c, a, x)
  -- 24:FF94~FFE4 와 같은 셈: 쓰기 칸에서 읽기 칸 쪽으로 빈 칸(FF)을 건너뛰어 내려간 다음 칸에 넣는다.
  local w, r = emu.read(0x7E1D91, m), emu.read(0x7E1D93, m)
  while w ~= r and emu.read(0x7E1D95 + w, m) == 0xFF do w = (w - 1) & 0x0F end
  w = (w + 1) & 0x0F
  if emu.read(0x7E1D95 + w, m) ~= 0xFF then return false end
  emu.write(0x7E1D95 + w, c, m)
  emu.write(0x7E1DC5 + w, 0x05, m)
  emu.write(0x7E1DB5 + w, x, m)
  emu.write(0x7E1DA5 + w, a, m)
  emu.write(0x7E1D91, (w + 1) & 0x0F, m)
  return true
end

local function queueEmpty()
  for i = 0, 15 do if emu.read(0x7E1D95 + i, m) ~= 0xFF then return false end end
  return true
end

local function songOn(n)
  for i = 0, 7 do
    if emu.read(0x03B7 + i, spc) ~= 0 and emu.read(0x03AF + i, spc) == n then return true end
  end
  return false
end

local function dump(n)
  local t = {}
  for i = 0, 0xFFFF do t[#t + 1] = string.char(emu.read(i, spc)) end
  L.write("spc.bin", table.concat(t))
  t = {}
  for i = 0, 0x7F do t[#t + 1] = string.char(emu.read(i, dspT)) end
  L.write("dsp.bin", table.concat(t))
  local s = emu.getState()
  local o = {string.format("frame=%d", n)}
  for _, k in ipairs({"spc.pc", "spc.a", "spc.x", "spc.y", "spc.ps", "spc.sp", "spc.dspReg", "spc.romEnabled",
    "spc.cpuRegs[0]", "spc.cpuRegs[1]", "spc.cpuRegs[2]", "spc.cpuRegs[3]", "spc.ramReg[0]", "spc.ramReg[1]",
    "spc.outputReg[0]", "spc.outputReg[1]", "spc.outputReg[2]", "spc.outputReg[3]",
    "spc.timer0.enabled", "spc.timer0.target", "spc.timer1.enabled", "spc.timer1.target",
    "spc.timer2.enabled", "spc.timer2.target"}) do
    o[#o + 1] = k .. "=" .. tostring(s[k])
  end
  -- 목소리마다 지금 읽는 BRR 주소와 풀어 둔 표본(디코더 확인용)
  for v = 0, 7 do
    local p = string.format("spc.dsp.voices[%d].", v)
    local b = {}
    for i = 0, 11 do b[#b + 1] = tostring(s[p .. "sampleBuffer" .. i]) end
    o[#o + 1] = string.format("voice%d brrAddress=%s brrOffset=%s bufferPos=%s buf=%s", v, tostring(s[p .. "brrAddress"]),
      tostring(s[p .. "brrOffset"]), tostring(s[p .. "bufferPos"]), table.concat(b, ","))
  end
  L.write("regs.txt", table.concat(o, "\n") .. "\n")
end

local envlog = os.getenv("ENVLOG") and {} or nil
local n, ready, done, hook = 0, nil, false, nil
emu.addEventCallback(function()
  n = n + 1
  local c = cmds[n]
  if c and not enqueue(c[1], c[2], c[3]) then cmds[n + 1] = cmds[n + 1] or c end
  if not done and want >= 0 then
    if not ready and songOn(want) and queueEmpty() then ready = n end
    -- 프레임 끝의 SPC700 은 명령 한가운데일 수 있다. 다음 SPC 명령이 시작될 때(실행 콜백) 잡아 명령 경계의 상태를 남긴다.
    if ready and n >= ready + delay and not hook then
      hook = emu.addMemoryCallback(function()
        if not done then dump(n); done = true end
      end, emu.callbackType.exec, 0x0000, 0xFFFF, emu.cpuType.spc, emu.memType.spcMemory)
    end
  end
  if done and hook then
    emu.removeMemoryCallback(hook, emu.callbackType.exec, 0x0000, 0xFFFF, emu.cpuType.spc, emu.memType.spcMemory)
    hook = false
  end
  if done and envlog then
    local t = {}
    for v = 0, 7 do t[#t + 1] = string.format("%02X%02X%02X", emu.read(v * 16 + 3, dspT), emu.read(v * 16 + 2, dspT), emu.read(v * 16 + 4, dspT)) end
    envlog[#envlog + 1] = table.concat(t, " ")
  end
  if n >= maxf then
    if not done then dump(n) end
    if envlog then L.write("env.txt", table.concat(envlog, "\n") .. "\n") end
    emu.stop(0)
  end
end, emu.eventType.endFrame)
