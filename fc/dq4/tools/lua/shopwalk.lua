-- STATE 에서 시작해 맵 좌표($44/$45)를 보며 WAY 의 칸들("13,1C 0D,1C 0D,18", 16진)로 차례로 걷는다.
-- 한 칸씩 X 먼저, 다음 Y 를 맞춘다. 인물에 막히면 같은 방향을 계속 누르고(인물은 곧 비킨다),
-- 마지막 칸에 닿으면 TAIL 프레임 쉬고 end.mss·end.png·end.* 덤프를 남긴다. 돌아서기·말 걸기는
-- 이어서 seq.lua 로 한다(이 드라이버에서 누른 방향은 걸음 직후라 돌아서지 않았다).
-- MAXF 까지 못 닿으면 fail.png 를 남기고 멈춘다.
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local L = require("lib")
L.loadState(os.getenv("STATE"))
local way = {}
for x, y in string.gmatch(os.getenv("WAY") or "", "(%x+),(%x+)") do way[#way + 1] = {tonumber(x, 16), tonumber(y, 16)} end
local tail = tonumber(os.getenv("TAIL") or "30")
local maxf = tonumber(os.getenv("MAXF") or "3000")
local n, i, phase, t = 0, 1, "walk", 0
local log = {}
emu.addEventCallback(function()
  n = n + 1
  if n < 3 then return end
  L.release()
  local x, y = emu.read(0x44, L.mem), emu.read(0x45, L.mem)
  if phase == "walk" then
    local w = way[i]
    if not w then phase = "rest"; t = 0
    elseif x == w[1] and y == w[2] then log[#log + 1] = string.format("%d %02X,%02X", n, x, y); i = i + 1
    elseif x ~= w[1] then L.press({[x < w[1] and "right" or "left"] = true})
    else L.press({[y < w[2] and "down" or "up"] = true}) end
  elseif phase == "rest" then
    t = t + 1
    if t > tail then
      phase = "done"
      L.write("walk.txt", table.concat(log, "\n") .. "\n")
      L.shot("end.png"); L.saveState("end.mss"); L.dumpAll("end")
    end
  elseif phase == "done" then
    t = t + 1
    if t > tail + 10 then emu.stop(0) end
  end
  if n >= maxf and phase == "walk" then
    log[#log + 1] = string.format("fail %d at %02X,%02X", n, x, y)
    L.write("walk.txt", table.concat(log, "\n") .. "\n")
    L.shot("fail.png"); emu.stop(1)
  end
end, emu.eventType.endFrame)
