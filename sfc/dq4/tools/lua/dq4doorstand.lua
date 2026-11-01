-- STATE 세이브스테이트에서 PRESS 방향을 누르고 있다가 주인공 셀($C1,$C2)이 STOPAT("x,y")이 되면 놓고, 50프레임 뒤
-- 주인공의 줄별 OAM 우선순위를 적는다. 2B:B815 는 인물(Y = 인물 번호)마다 줄 우선순위를 7E:1AB1,X 에 쓰고 곧바로 OAM 을
-- 만드므로, 프레임 끝의 1AB1 은 마지막 인물의 것이다. 그래서 주인공(인물 0)일 때 2B:BBAB(STA $1AB1,X)의 값을 모은다.
-- SET="2199|02" 는 시작할 때 WRAM 을 고친다(dq4doorwalk.lua 와 같음).
-- 결과: SHOT_DIR/stand.txt("map 36/00", "hero 70,43", "at 70,43" 인물 0 의 칸(7E:30E0·3140), "prio 30 30 …" X=0,2,…,A),
-- stand.png. 400프레임 안에 닿지 못하면 그 자리에서 적는다.
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local L = require("lib")
L.loadState(os.getenv("STATE"))
local m = emu.memType.snesMemory
local function b(a) return emu.read(a, m) end
local press = os.getenv("PRESS")
local sx, sy = os.getenv("STOPAT"):match("(%d+),(%d+)")
sx, sy = tonumber(sx), tonumber(sy)
local n, stopped = 0, nil
local who, prio = nil, {}
emu.addMemoryCallback(function()
  who = emu.getState()["cpu.y"] & 0xFF
end, emu.callbackType.exec, 0x2BB815, 0x2BB815)
emu.addMemoryCallback(function()
  if who == 0 then
    local s = emu.getState()
    prio[s["cpu.x"] & 0xFF] = s["cpu.a"] & 0xFF
  end
end, emu.callbackType.exec, 0x2BBBAB, 0x2BBBAB)
emu.addEventCallback(function()
  n = n + 1
  if n == 2 then
    for a, op, v in string.gmatch(os.getenv("SET") or "", "(%x+)([=|&])(%x+)") do
      local addr, val = 0x7E0000 + tonumber(a, 16), tonumber(v, 16)
      local cur = b(addr)
      if op == "=" then cur = val elseif op == "|" then cur = cur | val else cur = cur & val end
      emu.write(addr, cur, m)
    end
  end
  if n < 20 then return end
  if not stopped then
    if (b(0x7E00C1) == sx and b(0x7E00C2) == sy) or n > 400 then
      stopped = n
      L.release()
    else
      L.press({[press] = true})
    end
    return
  end
  if n == stopped + 50 then
    local t = {}
    for x = 0, 10, 2 do t[#t + 1] = prio[x] and string.format("%02X", prio[x]) or "--" end
    L.write("stand.txt", string.format("map %02X/%02X\nhero %d,%d\nat %d,%d\nprio %s\n", b(0x7E00BC), b(0x7E00BD),
      b(0x7E00C1), b(0x7E00C2), b(0x7E30E0), b(0x7E3140), table.concat(t, " ")))
    L.shot("stand.png")
    emu.stop(0)
  end
end, emu.eventType.endFrame)
