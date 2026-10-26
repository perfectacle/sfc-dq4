-- DQ5: 전원을 켜 A 를 PERIOD 프레임마다 누르며(dq5boot.lua 와 같은 입력) 새 게임 첫 장면(배 선실 17/00)까지 가서
-- SAVEAT 프레임에 세이브스테이트 SAVE 와 화면을 남긴다. 세이브스테이트 없이 롬만으로 ship.mss 에 해당하는 출발점을 만든다.
-- LOGFROM 부터 LOGEVERY 프레임마다 맵·21A1 을 ship.txt 에 적어 언제 조작 가능해지는지 본다.
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local L = require("lib")
local period = tonumber(os.getenv("PERIOD") or "40")
local tapUntil = tonumber(os.getenv("TAPUNTIL") or "6600")
local saveAt = tonumber(os.getenv("SAVEAT") or "6600")
local save = os.getenv("SAVE") or "ship.mss"
local logFrom = tonumber(os.getenv("LOGFROM") or "0")
local logEvery = tonumber(os.getenv("LOGEVERY") or "0")
local m = emu.memType.snesMemory
local n = 0
local log = {}
emu.addEventCallback(function()
  n = n + 1
  L.release()
  if n < tapUntil and n % period < 4 then L.press({a = true}) end
  if logEvery > 0 and n >= logFrom and n % logEvery == 0 then
    log[#log + 1] = string.format("f%05d map %02X/%02X 21A1=%02X", n, emu.read(0x7E00BC, m), emu.read(0x7E00BD, m), emu.read(0x7E21A1, m))
  end
  if n == saveAt then
    log[#log + 1] = string.format("f%05d save map %02X/%02X 21A1=%02X", n, emu.read(0x7E00BC, m), emu.read(0x7E00BD, m), emu.read(0x7E21A1, m))
    L.saveState(save)
    L.shot(save:gsub("%.mss$", ".png"))
    L.write("ship.txt", table.concat(log, "\n") .. "\n")
  end
  -- 세이브스테이트는 다음 명령 실행 때 쓰이므로 한 프레임 뒤에 멈춘다.
  if n == saveAt + 1 then emu.stop(0) end
end, emu.eventType.endFrame)
