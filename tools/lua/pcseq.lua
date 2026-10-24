-- boot.lua 와 같은 입력으로 부팅하고 FROM 프레임부터 LO~HI 범위에서 실행된 PC 를 순서대로(처음 LIMIT 개) 기록한다.
-- 각 줄: 프레임 PC A X Y DB. 실제 명령 경계를 알아내 디스어셈블 시작점을 잡는 데 쓴다.
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local L = require("lib")
local from = tonumber(os.getenv("FROM") or "0")
local lo, hi = tonumber(os.getenv("LO"), 16), tonumber(os.getenv("HI"), 16)
local limit = tonumber(os.getenv("LIMIT") or "300")
local n, log = 0, {}
emu.addMemoryCallback(function(addr)
  if n < from or #log >= limit then return end
  local s = emu.getState()
  log[#log + 1] = string.format("%d %06X A=%04X X=%04X Y=%04X DB=%02X P=%02X", n, addr, s["cpu.a"], s["cpu.x"], s["cpu.y"], s["cpu.dbr"], s["cpu.ps"])
end, emu.callbackType.exec, lo, hi)
local maxf = tonumber(os.getenv("MAXF") or "1500")
emu.addEventCallback(function()
  n = n + 1
  if n == maxf - 1 then L.write("pcseq.txt", table.concat(log, "\n") .. "\n") end
end, emu.eventType.endFrame)
dofile(os.getenv("LIBDIR") .. "/boot.lua")
