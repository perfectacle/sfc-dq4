-- STATE 세이브스테이트에서 시작해 주인공(인물 표 슬롯 0)을 WAYPOINTS 의 셀 좌표로 차례로 걷게 한다.
-- WAYPOINTS="3,11;3,24;7,24;7,22" 처럼 x,y(맵 셀) 목록. 한 번에 한 축만 움직이므로 꺾이는 곳마다 점을 둔다.
-- 시작 전 PRE 입력(seq 형식, 예 "b:4,wait:40")을 먼저 재생한다. 맵 번호($BC/$BD)가 바뀌면 walk.txt 에 기록하고
-- AFTER 프레임 뒤 멈춘다. 다른 프로브에 끼울 수 있게 LIBDIR/boot.lua 로도 쓸 수 있다(seqlib.sh 참고).
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local L = require("lib")
L.loadState(os.getenv("STATE"))
local m = emu.memType.snesMemory
local pre = {}
for tok in string.gmatch(os.getenv("PRE") or "", "[^,]+") do
  local b, f = tok:match("([%w+]+):(%d+)")
  pre[#pre + 1] = {b, tonumber(f)}
end
local pts = {}
for x, y in string.gmatch(os.getenv("WAYPOINTS") or "", "(%d+),(%d+)") do pts[#pts + 1] = {tonumber(x), tonumber(y)} end
local maxf = tonumber(os.getenv("MAXF") or "3000")
local after = tonumber(os.getenv("AFTER") or "120")
local n, pi, left, wi, stuck, last = 0, 1, nil, 1, 0, nil
local log, startMap, changedAt = {}, nil, nil
emu.addEventCallback(function()
  n = n + 1
  L.release()
  local bc, bd = emu.read(0x7E00BC, m), emu.read(0x7E00BD, m)
  local x, y = emu.read(0x7E3020, m), emu.read(0x7E3080, m)
  if not startMap then startMap = bc * 256 + bd end
  if not changedAt and bc * 256 + bd ~= startMap then
    changedAt = n
    log[#log + 1] = string.format("f%05d map %02X/%02X -> %02X/%02X at x=%d y=%d", n, startMap >> 8, startMap & 255, bc, bd, x, y)
  end
  if pi <= #pre then
    local s = pre[pi]
    if left == nil then left = s[2] end
    if s[1] ~= "wait" then local t = {}; for b in s[1]:gmatch("[^+]+") do t[b] = true end; L.press(t) end
    left = left - 1
    if left <= 0 then pi = pi + 1; left = nil end
  elseif not changedAt and wi <= #pts then
    local tx, ty = pts[wi][1], pts[wi][2]
    if x == tx and y == ty then
      log[#log + 1] = string.format("f%05d reached %d,%d", n, x, y)
      wi = wi + 1; stuck = 0
    else
      local key = x * 256 + y
      if key == last then stuck = stuck + 1 else stuck = 0 end
      last = key
      if stuck > 90 then
        log[#log + 1] = string.format("f%05d stuck at %d,%d heading %d,%d", n, x, y, tx, ty)
        wi = wi + 1; stuck = 0
      end
      local b = (x < tx and "right") or (x > tx and "left") or (y < ty and "down") or "up"
      L.press({[b] = true})
    end
  end
  if (changedAt and n >= changedAt + after) or n >= maxf then
    log[#log + 1] = string.format("f%05d end map %02X/%02X x=%d y=%d", n, bc, bd, x, y)
    L.write("walk.txt", table.concat(log, "\n") .. "\n")
    L.shot("end.png")
    emu.stop(0)
  end
end, emu.eventType.endFrame)
