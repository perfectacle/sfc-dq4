-- 타이틀 서곡 롬을 전원부터 돌려, SPC 곡 자리에 SONG(기본 10)이 오른 뒤 첫 SPC 명령 경계의 상태와
-- DSP 쓰기(KON·KOF·FLG, 목소리마다 음량·피치·SRCN)를 남긴다. 세이브스테이트를 쓰지 않는다.
-- 결과(OUT): spc.bin(64KB), dsp.bin(128바이트), regs.txt(남긴 프레임과 SPC700 레지스터·포트·타이머),
--   dspw.txt(sfc/dq5/tools/dq5song.py --kon 이 읽는 꼴), events.txt(타이틀 진입·곡 시작 프레임). MAXF 에 멈춘다.
-- SEQ="a@600:2" 처럼 주면 그 프레임에 버튼을 누른다(메뉴로 넘어간 뒤 곡이 이어지는지 볼 때).
-- DUMPAT=n 이면 곡을 기다리지 않고 n 프레임에 남긴다(곡이 시작하지 않을 때 SPC 상태를 볼 때).
local out = os.getenv("OUT")
local maxf = tonumber(os.getenv("MAXF") or "1200")
local want = tonumber(os.getenv("SONG") or "10", 16)
local dumpAt = tonumber(os.getenv("DUMPAT") or "-1")
local spcRam = emu.memType.spcRam
local dspT = emu.memType.spcDspRegisters
local wram = emu.memType.snesMemory

local function write(name, data)
  local f = io.open(out .. "/" .. name, "wb")
  f:write(data)
  f:close()
end

local presses = {}
for b, f, n in string.gmatch(os.getenv("SEQ") or "", "(%a+)@(%d+):(%d+)") do
  presses[#presses + 1] = {b = b, from = tonumber(f), to = tonumber(f) + tonumber(n)}
end

local frame, songAt, dumped, hook = 0, nil, false, nil
local dspw, events, reg = {}, {}, 0

emu.addMemoryCallback(function(_, value) reg = value end, emu.callbackType.write, 0xF2, 0xF2,
  emu.cpuType.spc, emu.memType.spcMemory)
emu.addMemoryCallback(function(_, value)
  local r = reg & 0x7F
  if r == 0x4C or r == 0x5C or r == 0x6C or (r & 0x0F) <= 4 then
    dspw[#dspw + 1] = string.format("%d %02X=%02X", frame, r, value)
  end
end, emu.callbackType.write, 0xF3, 0xF3, emu.cpuType.spc, emu.memType.spcMemory)

local function songOn()
  for i = 0, 7 do
    if emu.read(0x03B7 + i, spcRam) ~= 0 and emu.read(0x03AF + i, spcRam) == want then return true end
  end
  return false
end

local function queueEmpty()
  for i = 0, 15 do if emu.read(0x7E1D95 + i, wram) ~= 0xFF then return false end end
  return true
end

local function dump()
  local t = {}
  for i = 0, 0xFFFF do t[#t + 1] = string.char(emu.read(i, spcRam)) end
  write("spc.bin", table.concat(t))
  t = {}
  for i = 0, 0x7F do t[#t + 1] = string.char(emu.read(i, dspT)) end
  write("dsp.bin", table.concat(t))
  local s = emu.getState()
  local o = {string.format("frame=%d", frame)}
  for _, k in ipairs({"spc.pc", "spc.a", "spc.x", "spc.y", "spc.ps", "spc.sp", "spc.dspReg", "spc.romEnabled",
    "spc.cpuRegs[0]", "spc.cpuRegs[1]", "spc.cpuRegs[2]", "spc.cpuRegs[3]", "spc.ramReg[0]", "spc.ramReg[1]",
    "spc.outputReg[0]", "spc.outputReg[1]", "spc.outputReg[2]", "spc.outputReg[3]",
    "spc.timer0.enabled", "spc.timer0.target", "spc.timer1.enabled", "spc.timer1.target",
    "spc.timer2.enabled", "spc.timer2.target"}) do
    o[#o + 1] = k .. "=" .. tostring(s[k])
  end
  write("regs.txt", table.concat(o, "\n") .. "\n")
end

emu.addEventCallback(function()
  local held = {}
  for _, p in ipairs(presses) do
    if frame >= p.from and frame < p.to then held[p.b] = true end
  end
  emu.setInput(held, 0)
end, emu.eventType.inputPolled)

emu.addEventCallback(function()
  frame = frame + 1
  if frame == dumpAt then dump(); dumped = true end
  if not songAt and songOn() and queueEmpty() then
    songAt = frame
    events[#events + 1] = string.format("song %02X on at frame %d", want, frame)
    -- 프레임 끝의 SPC700 은 명령 한가운데일 수 있어 다음 명령이 시작될 때 잡는다
    hook = emu.addMemoryCallback(function()
      if not dumped then dump(); dumped = true end
    end, emu.callbackType.exec, 0x0000, 0xFFFF, emu.cpuType.spc, emu.memType.spcMemory)
  end
  if dumped and hook then
    emu.removeMemoryCallback(hook, emu.callbackType.exec, 0x0000, 0xFFFF, emu.cpuType.spc, emu.memType.spcMemory)
    hook = nil
  end
  if frame >= maxf then
    write("dspw.txt", table.concat(dspw, "\n") .. "\n")
    write("events.txt", table.concat(events, "\n") .. "\n")
    emu.stop()
  end
end, emu.eventType.endFrame)
