-- APU 쓰기와 MesenCE 의 APU 채널 상태를 프레임마다 적는다. dq4apu.py(합성기)의 채널 모델을 실기 에뮬레이터와 견주는 데 쓴다.
-- apu.txt(MAXF-1 프레임)에:
--   W 프레임 주소 값                                   $4000~$4017 쓰기
--   F 프레임 펄스1(주기 음량 듀티) 펄스2(주기 음량 듀티) 삼각파(주기 움직임 단계) 노이즈(주기 음량 짧은꼴) 프레임 카운터 클록
-- 음량은 길이 카운터가 0 이거나 펄스가 막힌(주기 < 8, 스윕 목표 > 7FF) 때 0, 아니면 고정 음량이나 엔벨로프 값이다.
-- 삼각파 「움직임」 은 선형·길이 카운터가 모두 0 이 아니면 1. FROM 프레임부터 적는다.
-- SONG=n(16진)을 주면 FROM 뒤 첫 소리 입구 1F:$C01F 의 A 를 n 으로 바꾼다(soundlog.lua 와 같음).
-- 끝에서 입력 드라이버(DRIVER)를 돌린다.
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local L = require("lib")
local from = tonumber(os.getenv("FROM") or "0")
local maxf = tonumber(os.getenv("MAXF") or "1500")
local song = os.getenv("SONG") and tonumber(os.getenv("SONG"), 16)
local f, out, started = 0, {}, false

emu.addMemoryCallback(function(addr)
  if f < from or started or L.prgOffset(addr) ~= 0x1F * 0x4000 + 0x001F then return end
  started = true
  if song then emu.setState({["cpu.a"] = song}) end
end, emu.callbackType.exec, 0xC01F, 0xC01F)

emu.addMemoryCallback(function(addr, value)
  if f < from then return end
  out[#out + 1] = string.format("W %d %04X %02X", f, addr, value)
end, emu.callbackType.write, 0x4000, 0x4017)

local function level(st, p)
  if st[p .. "envelope.lengthCounter.counter"] == 0 then return 0 end
  if st[p .. "envelope.constantVolume"] then return st[p .. "envelope.volume"] end
  return st[p .. "envelope.counter"]
end

local function pulse(st, p)
  local per = st[p .. "realPeriod"]
  local v = level(st, p)
  local tgt = st[p .. "sweepTargetPeriod"]
  if per < 8 or (not st[p .. "sweepNegate"] and tgt > 0x7FF) then v = 0 end
  return string.format("%d %d %d", per, v, st[p .. "duty"])
end

emu.addEventCallback(function()
  f = f + 1
  if f >= from then
    local st = emu.getState()
    local t = "apu.triangle."
    local act = (st[t .. "linearCounter"] > 0 and st[t .. "lengthCounter.counter"] > 0) and 1 or 0
    out[#out + 1] = string.format("F %d %s %s %d %d %d %d %d %d %d", f, pulse(st, "apu.square1."), pulse(st, "apu.square2."),
      st[t .. "timer.period"], act, st[t .. "sequencePosition"],
      st["apu.noise.timer.period"], level(st, "apu.noise."), st["apu.noise.modeFlag"] and 1 or 0,
      st["apu.frameCounter.previousCycle"])
  end
  if f == maxf - 1 then L.write("apu.txt", table.concat(out, "\n") .. "\n") end
end, emu.eventType.endFrame)
L.drive()
