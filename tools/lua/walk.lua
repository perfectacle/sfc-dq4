-- STATE 세이브스테이트에서 시작해 주인공(인물 표 슬롯 0)을 WAYPOINTS 의 셀 좌표로 차례로 걷게 한다.
-- WAYPOINTS="3,11;3,24;7,24;7,22" 처럼 x,y(맵 셀) 목록. 한 번에 한 축만 움직이므로 꺾이는 곳마다 점을 둔다.
-- 맵이 바뀌어도 다음 경유점으로 계속 간다(바뀐 직후 HOLD 프레임은 입력을 쉰다). 경유점 대신 "down:60" 처럼
-- 방향:프레임을 쓰면 좌표와 상관없이 그만큼 누른다(맵 가장자리 밖으로 걸어 나갈 때).
-- 시작 전 PRE 입력(seq 형식, 예 "b:4,wait:40")을 먼저 재생한다. 맵 번호($BC/$BD)가 바뀔 때마다 walk.txt 에 기록하고,
-- CHANGES 번 바뀐 뒤 AFTER 프레임이 지나거나 MAXF 에 이르면 멈춘다.
-- ROMPATCH="156FF5=E0253C0103;..." 는 시작할 때 ROM(파일 오프셋)을 덮어쓴다. 실험용이며 원본 롬 파일은 바뀌지 않는다.
-- POKE="7E2192=80;..." 는 매 프레임 그 값을 써서 고정한다(이벤트 플래그 같은 조건 실험). WATCH="이름=7E3228:1;..." 는 끝날 때 값을 walk.txt 에 적는다.
-- 다른 프로브에 끼울 수 있게 LIBDIR/boot.lua 로도 쓸 수 있다(seqlib.sh 참고).
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
for tok in string.gmatch(os.getenv("WAYPOINTS") or "", "[^;]+") do
  local x, y = tok:match("^(%d+),(%d+)$")
  if x then
    pts[#pts + 1] = {tonumber(x), tonumber(y)}
  else
    local b, f = tok:match("^(%a+):(%d+)$")
    pts[#pts + 1] = {b, tonumber(f)}
  end
end
local pokes = {}
for a, v in string.gmatch(os.getenv("POKE") or "", "(%x+)=(%x+)") do pokes[#pokes + 1] = {tonumber(a, 16), tonumber(v, 16)} end
local watches = {}
for name, a, len in string.gmatch(os.getenv("WATCH") or "", "([%w_]+)=(%x+):?(%d*)") do watches[#watches + 1] = {name, tonumber(a, 16), tonumber(len) or 1} end
local patches = {}
for off, hex in string.gmatch(os.getenv("ROMPATCH") or "", "(%x+)=(%x+)") do patches[#patches + 1] = {tonumber(off, 16), hex} end
local maxf = tonumber(os.getenv("MAXF") or "3000")
local after = tonumber(os.getenv("AFTER") or "120")
local changesWanted = tonumber(os.getenv("CHANGES") or "1")
local hold = tonumber(os.getenv("HOLD") or "90")
local n, pi, left, wi, stuck, last, press = 0, 1, nil, 1, 0, nil, nil
local log, curMap, changes, lastChange = {}, nil, 0, nil
emu.addEventCallback(function()
  n = n + 1
  if n == 1 then
    for _, p in ipairs(patches) do
      for i = 0, #p[2] / 2 - 1 do
        emu.write(p[1] + i, tonumber(p[2]:sub(i * 2 + 1, i * 2 + 2), 16), emu.memType.snesPrgRom)
      end
    end
  end
  for _, p in ipairs(pokes) do emu.write(p[1], p[2], m) end
  L.release()
  local bc, bd = emu.read(0x7E00BC, m), emu.read(0x7E00BD, m)
  local x, y = emu.read(0x7E3020, m), emu.read(0x7E3080, m)
  local map = bc * 256 + bd
  if not curMap then curMap = map end
  if map ~= curMap then
    changes = changes + 1; lastChange = n
    log[#log + 1] = string.format("f%05d map %02X/%02X -> %02X/%02X at x=%d y=%d", n, curMap >> 8, curMap & 255, bc, bd, x, y)
    curMap = map
  end
  if pi <= #pre then
    local s = pre[pi]
    if left == nil then left = s[2] end
    if s[1] ~= "wait" then local t = {}; for b in s[1]:gmatch("[^+]+") do t[b] = true end; L.press(t) end
    left = left - 1
    if left <= 0 then pi = pi + 1; left = nil end
  elseif lastChange and n < lastChange + hold then
    -- 맵을 바꾸는 동안은 입력을 쉰다.
  elseif wi <= #pts then
    local p = pts[wi]
    if type(p[1]) == "string" then
      if press == nil then press = p[2]; log[#log + 1] = string.format("f%05d press %s:%d at %d,%d", n, p[1], p[2], x, y) end
      L.press({[p[1]] = true})
      press = press - 1
      if press <= 0 then press = nil; wi = wi + 1 end
    elseif x == p[1] and y == p[2] then
      log[#log + 1] = string.format("f%05d reached %d,%d", n, x, y)
      wi = wi + 1; stuck = 0
    else
      local key = x * 256 + y
      if key == last then stuck = stuck + 1 else stuck = 0 end
      last = key
      if stuck > 90 then
        log[#log + 1] = string.format("f%05d stuck at %d,%d heading %d,%d", n, x, y, p[1], p[2])
        wi = wi + 1; stuck = 0
      end
      local b = (x < p[1] and "right") or (x > p[1] and "left") or (y < p[2] and "down") or "up"
      L.press({[b] = true})
    end
  end
  if (changes >= changesWanted and n >= lastChange + after) or n >= maxf then
    log[#log + 1] = string.format("f%05d end map %02X/%02X x=%d y=%d", n, bc, bd, x, y)
    for _, w in ipairs(watches) do
      local v = 0
      for k = w[3] - 1, 0, -1 do v = v * 256 + emu.read(w[2] + k, m) end
      log[#log + 1] = string.format("%s=%0" .. (w[3] * 2) .. "X", w[1], v)
    end
    L.write("walk.txt", table.concat(log, "\n") .. "\n")
    L.shot("end.png")
    emu.stop(0)
  end
end, emu.eventType.endFrame)
