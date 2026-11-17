-- tools/lua/walk.lua 와 같은 걷기에 창 상태를 보고 넘기는 경유점 토큰 둘을 더한 dq4 판(공유 walk.lua 는 다른 트랙도 쓰므로
-- 바꾸지 않는다). 그 밖의 환경 변수·출력은 walk.lua 와 같다.
--   until:N   창 번호(7E:0A00)가 이 토큰을 시작한 때와 달라질 때까지 기다린다(많아야 N 프레임). 물음 창이 뜨는 것을
--             기다릴 때 쓴다. 다 기다려도 그대로면 walk.txt 에 「until timeout」 을 적고 넘어간다
--   cursor:K  고르기 창 커서(7E:0AD7)가 K 가 될 때까지 아래(K 가 크면)·위를 6프레임 누르고 6프레임 뗀다(많아야 120 프레임)
--   ask:N     물음 창(창 번호 32, 예/아니요)이 뜰 때까지 A 를 8프레임 누르고 8프레임 떼며 글을 넘긴다(많아야 N 프레임).
--             창이 뜬 프레임부터 누르지 않으므로 넘기는 A 가 물음에 답하지 않는다(누른 채로 뜬 A 는 새 입력이 아님)
--   pick:K    DQ5 가게 사기 목록에서 고른 물건 번호(7E:0F22, 10진 K)가 K 가 될 때까지 아래를 cursor 처럼 누른다. 목록 커서는
--             0AD7 이 아니고, 목록이 열려야 움직이므로 열림을 함께 기다린다
-- 프레임 수만 정해 누르면, 앞 장·앞 모듈이 메시지를 더해 창이 뜨는 때가 바뀔 때 누른 방향이 물음 창 커서를 옮겼다.
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
    if b == "until" or b == "cursor" or b == "ask" or b == "pick" then
      pts[#pts + 1] = {kind = b, arg = tonumber(f)}
    else
      pts[#pts + 1] = {b, tonumber(f)}
    end
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
local n, pi, left, wi, stuck, last, press, since = 0, 1, nil, 1, 0, nil, nil, nil
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
    if p.kind == "until" then
      local w = emu.read(0x7E0A00, m)
      if press == nil then press = p.arg; since = w end
      press = press - 1
      if w ~= since then
        log[#log + 1] = string.format("f%05d until window %02X -> %02X", n, since, w)
        press = nil; wi = wi + 1
      elseif press <= 0 then
        log[#log + 1] = string.format("f%05d until timeout window %02X", n, w)
        press = nil; wi = wi + 1
      end
    elseif p.kind == "ask" then
      local w = emu.read(0x7E0A00, m)
      if press == nil then press = p.arg; since = 0 end
      press = press - 1
      if w == 0x32 then
        log[#log + 1] = string.format("f%05d ask window 32", n)
        press = nil; wi = wi + 1
      elseif press <= 0 then
        log[#log + 1] = string.format("f%05d ask timeout window %02X", n, w)
        press = nil; wi = wi + 1
      else
        if since % 16 < 8 then L.press({a = true}) end
        since = since + 1
      end
    elseif p.kind == "cursor" or p.kind == "pick" then
      local c = emu.read(p.kind == "pick" and 0x7E0F22 or 0x7E0AD7, m)
      if press == nil then press = 120 end
      press = press - 1
      if c == p.arg then
        log[#log + 1] = string.format("f%05d %s %d", n, p.kind, c)
        press = nil; wi = wi + 1
      elseif press <= 0 then
        log[#log + 1] = string.format("f%05d %s timeout at %d want %d", n, p.kind, c, p.arg)
        press = nil; wi = wi + 1
      elseif press % 12 >= 6 then
        L.press({[(p.kind == "pick" or c < p.arg) and "down" or "up"] = true})
      end
    elseif type(p[1]) == "string" then
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
