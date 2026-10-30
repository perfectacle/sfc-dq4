-- 사운드 롬으로 전원을 켜 새 게임 첫 장면(배 선실 17/00)까지 가서 세이브스테이트 SAVE 를 남긴다.
-- 세이브스테이트의 SPC 는 그 상태를 만든 롬의 자리 배치를 담으므로, 곡 번호를 늘린 롬은 원본 DQ5 로 만든 상태에서
-- 재면 판정 도우미 자리가 덮여 효과음이 되풀이되는 등 틀렸다. 시간을 재는 롬마다 이 lua 로 상태를 새로 만든다.
-- A 를 PERIOD 프레임마다 누르고(dq5shipstate.lua 와 같음) 여섯 번째마다 Y 를 눌러 한글 이름 입력을 끝낸다(Y = 완료).
-- 선실에 닿으면 누르기를 멈추고 600~900 프레임 뒤 B 로 창을 닫은 뒤 1000 프레임 뒤에 저장한다. LIBDIR 의 lib.lua 를 쓴다.
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local L = require("lib")
local period = tonumber(os.getenv("PERIOD") or "40")
local tapUntil = tonumber(os.getenv("TAPUNTIL") or "9000")
local save = os.getenv("SAVE") or "ship.mss"
local m = emu.memType.snesMemory
local n, cabin, saveAt, log = 0, nil, nil, {}
emu.addEventCallback(function()
  n = n + 1
  L.release()
  if emu.read(0x7E00BC, m) == 0x17 and emu.read(0x7E00BD, m) == 0x00 and not cabin then cabin = n end
  if cabin and n > cabin + 600 and n < cabin + 900 and n % 30 < 4 then L.press({b = true}) end
  if cabin and n == cabin + 1000 then saveAt = n end
  if not cabin and n < tapUntil and n % period < 4 then
    if (n // period) % 6 == 5 then L.press({y = true}) else L.press({a = true}) end
  end
  if n == saveAt then
    log[#log + 1] = string.format("f%05d save map %02X/%02X", n, emu.read(0x7E00BC, m), emu.read(0x7E00BD, m))
    L.saveState(save)
    L.shot(save:gsub("%.mss$", ".png"))
    L.write("ship.txt", table.concat(log, "\n") .. "\n")
  end
  -- 세이브스테이트는 다음 명령 실행 때 쓰이므로 한 프레임 뒤에 멈춘다.
  if saveAt and n == saveAt + 1 then emu.stop(0) end
  if not cabin and n == tapUntil then emu.stop(1) end
end, emu.eventType.endFrame)
