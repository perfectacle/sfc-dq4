-- 장 넘김 흐름 기록: DRIVER(보통 warp.lua 에 장 끝 조건 SET 과 SEQ)를 돌리며 메시지 출력 16:$8656 진입(X:A),
-- 지금 곡($BF >> 1)이 바뀐 프레임, PPU 마스크($2001) 쓰기 값이 바뀐 프레임을 chtrans.txt 에 남기고, EVERY 프레임마다
-- 화면을 sNNNNN.png 로 찍는다(FROM 부터). RESET 프레임에 리셋 버튼을 누른다(그 뒤 입력은 DRIVER 가 계속 준다).
-- MAXF 에 멈춘다. 출력 폴더(SHOT_DIR)는 .noindex 로 끝내 색인을 피한다.
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local L = require("lib")
local every = tonumber(os.getenv("EVERY") or "10")
local from = tonumber(os.getenv("FROM") or "0")
local maxf = tonumber(os.getenv("MAXF") or "3000")
local reset = tonumber(os.getenv("RESET") or "-1")
local f, log, song, mask = 0, {}, -1, -1
local entry = 0x16 * 0x4000 + 0x0656
emu.addMemoryCallback(function(addr)
  if L.prgOffset(addr) ~= entry then return end
  local st = emu.getState()
  log[#log + 1] = string.format("%d msg %02X%02X", f, st["cpu.x"], st["cpu.a"])
end, emu.callbackType.exec, 0x8656, 0x8656)
emu.addMemoryCallback(function(addr, value)
  if value ~= mask then
    mask = value
    log[#log + 1] = string.format("%d mask %02X", f, value)
  end
end, emu.callbackType.write, 0x2001, 0x2001)
emu.addEventCallback(function()
  f = f + 1
  local s = emu.read(0xBF, L.mem) >> 1
  if s ~= song then
    song = s
    log[#log + 1] = string.format("%d song %02X", f, s)
  end
  if f == reset then
    log[#log + 1] = string.format("%d reset", f)
    emu.reset()
  end
  if f >= from and every > 0 and f % every == 0 then L.shot(string.format("s%05d.png", f)) end
  if f == maxf then
    L.write("chtrans.txt", table.concat(log, "\n") .. "\n")
    L.shot("end.png")
    emu.stop(0)
  end
end, emu.eventType.endFrame)
L.drive()
