-- dq4sound.py nsf 로 만든 NSF 를 MesenCE 로 틀어 APU 쓰기를 soundlog.lua 와 같은 꼴(sound.txt)로 적는다.
-- 그러면 `dq4sound.py rom/dq4.nes compare N DIR` 로 롬의 드라이버를 해석기로 돌린 쓰기와 프레임마다 견줄 수 있다.
--   S 0 A A     INIT 이 곡 시작($EF59)을 부르는 자리(START, 16진, nsf 명령이 찍는 「곡 시작 자리」)의 A
--   N 프레임    PLAY($C019) 진입
--   W 프레임 주소 값
-- MAXF-1 프레임에 쓰고 멈춘다. SHOT_DIR 에 쓴다(lib.lua).
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local L = require("lib")
local maxf = tonumber(os.getenv("MAXF") or "1500")
local start = tonumber(os.getenv("START"), 16)
local f, out, on, lastN = 0, {}, false, nil

emu.addMemoryCallback(function()
  local a = emu.getState()["cpu.a"]
  out[#out + 1] = string.format("S 0 %02X %02X", a, a)
  on = true
end, emu.callbackType.exec, start, start)

emu.addMemoryCallback(function()
  if on then out[#out + 1] = string.format("N %d", f); lastN = #out end
end, emu.callbackType.exec, 0xC019, 0xC019)

emu.addMemoryCallback(function(addr, value)
  if on then out[#out + 1] = string.format("W %d %04X %02X", f, addr, value) end
end, emu.callbackType.write, 0x4000, 0x4017)

emu.addEventCallback(function()
  f = f + 1
  if f == maxf - 1 then
    -- 마지막 PLAY 는 이 프레임 끝에서 아직 도는 중일 수 있어 그 N 부터는 버린다
    L.write("sound.txt", table.concat(out, "\n", 1, (lastN or #out + 1) - 1) .. "\n")
    emu.stop(0)
  end
end, emu.eventType.endFrame)
