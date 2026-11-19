-- STATE 세이브스테이트에서 WAYPOINTS 의 토막을 차례로 하는 걷기(dq4walkstate.lua 의 WALK 로 띄운다). walk.lua 와 같은
-- 꼴로 walk.txt 를 쓰고(맵 바뀜, 끝 맵·셀, WATCH), 입력은 프레임을 세지 않고 창·맵 상태를 보고 준다.
--   x,y       그 셀까지 한 축씩 걷는다. 60프레임 막히면 옆으로 한 걸음 비켜 막힌 축부터 다시 걷고, STUCK 프레임
--             (기본 900, 조작이 막힌 7E:19AE bit0 동안은 세지 않음) 동안 목표에 가까워지지 않으면 fail. 목표 셀에 사람이
--             서 있으면 옆에서 비킬 때까지 기다리고, 꺾는 셀이면 300프레임 뒤 다음 셀로 넘어간다. x,y! 는 사람(배 등)이 선
--             셀로 그대로 걸어 들어간다. 필드는 16비트 자리(7E:00B6·00B8). 걷다 메시지가 뜨면 넘기고
--             계속 걷는다. 묻는 창이 서거나 맵이 바뀌거나 필드로 나가면 그 자리에서 이 토막을 끝낸다
--   dir:n     n 프레임 누른다(맵 가장자리 밖으로 나갈 때). wait:n 은 n 프레임 쉰다
--   face:dir  그 쪽을 짧게 눌러 돌아선다(앞이 사람·벽이면 걷지 않음)
--   talk      명령 창(7E:0A00 = 01)이 뜰 때까지 A, 뜨면 A 로 「이야기하기」(커서 첫 칸)
--   cmd:k1,k2 명령 창을 열고 k1,k2 … 를 하나씩 눌러 커서를 옮긴 뒤 A(しらべる 는 cmd:down,down,down,right)
--   free      메시지 창(00, 사건이 조작을 막았으면 금화 창 02 등도)이면 A 를 톡톡, 창이 닫히고(FF, 가만히 서면 뜨는
--             상태 창 02 는 닫힌 것으로 봄) 필드 루프가 돌아(7E:007F 가 바뀜) FREE 프레임 이어지면 끝. 예·아니요 창(32)이면 fail
--   yes / no  메시지를 넘기다 예·아니요 창이 STABLE 프레임 그대로면 A(no 는 아래로 커서를 옮긴 뒤 A)
--   yes*      free 와 같되 예·아니요 창마다 「예」
--   fight     걸음 전투가 끝날 때까지 A(AFTERPATCH 가 끝난 뒤 롬을 덮음), 맵에서 조작이 풀리면 끝
--   meet:d1,d2  필드에서 d1·d2 를 32프레임씩 번갈아 걸어 걸음 전투나 창(떠돌이 상인)이 걸릴 때까지
--   await     누르지 않고 창이 뜨거나 조작이 막힐 때까지 기다린다(사람이 다가와 말을 걸 때)
--   msg:HHH   메시지 HHH(24:8BAF 가 받은 번호)가 뜰 때까지 메시지를 넘긴다
--   win:HH/HH 창 HH(여럿이면 그 가운데 하나)가 STABLE 프레임 그대로일 때까지 A
--   near:NN   인물 칸 NN 옆에 서서 그 쪽을 본다(걸어 다니는 사람, 다음 토막 talk)
--   push:SS,x,y  밀리는 인물(인물 칸 SS)을 셀 (x,y)까지 민다(옆 모서리를 거쳐 미는 쪽 반대편에 서서 걸음)
--   pick:AAAA=VV  목록에서 아래를 눌러 WRAM 7E:AAAA 가 VV 가 되게(가게 사기 목록의 물건 7E:0F22)
--   rest:AAAA,N  WRAM 7E:AAAA·AAAA+1 이 N 프레임 그대로일 때까지 기다린다(구르는 바위가 멈출 때까지)
--   see:AAAA=VV  메시지를 넘기며 WRAM 7E:AAAA 가 VV 가 될 때까지
--   close     B 로 창을 닫아 조작이 풀릴 때까지
--   map:GG/MM 맵이 그것이 되고 free 가 될 때까지 누르지 않고 기다린다(메시지 창이면 넘김)
--   serve:AAAA>=VVVV  누르지 않고 서서 다가오는 사람의 말을 넘기고 묻는 창마다 「예」, WRAM 7E:AAAA(16비트)가 VVVV 이상이고
--             조작이 풀리면 끝(무기점 손님을 가게를 닫을 때까지 받기)
--   field     필드(7E:00BE bit7 꺼짐)에 서고 조작이 풀릴 때까지 기다린다
--   stand:SS,X,Y  누르지 않고 인물 칸 SS(16진)가 셀 (X,Y)(10진)에 서서 걷는 중(7E:3280 bit7)이 아닐 때까지 기다린다
--             (순찰하는 감옥 병사가 정한 모퉁이에 설 때)
--   pace:AAAA>=VVVV,dir1,dir2  WRAM 7E:AAAA(16비트)가 VVVV 이상이 될 때까지 dir1·dir2 를 32프레임씩 번갈아 누른다
--             (필드를 걸어 밤 7E:075E ≥ 00F0 을 기다릴 때)
-- 토막마다 TOKMAX 프레임(기본 6000)을 넘기면 fail. fail 이면 그 줄을 남기고 곧 끝낸다. 다 하면 AFTER 프레임 뒤 끝.
-- POKE·ROMPATCH·WATCH·MAXF·PRE 는 walk.lua 와 같다. AFTERPATCH 는 fight 참고.
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local L = require("lib")
L.loadState(os.getenv("STATE"))
local m = emu.memType.snesMemory
local function rd(a) return emu.read(a, m) end
-- 주인공 셀. 필드는 512 셀 너비라 16비트 자리(7E:00B6·00B8)를, 실내는 인물 표 칸 0(7E:3020·3080)을 읽는다
local function heroAt()
  if rd(0x7E00BE) & 0x80 == 0 then
    return rd(0x7E00B6) + 256 * rd(0x7E00B7), rd(0x7E00B8) + 256 * rd(0x7E00B9)
  end
  return rd(0x7E3020), rd(0x7E3080)
end
local WINDOW, CURSOR, TICK = 0x7E0A00, 0x7E0AD7, 0x7E007F
local W_COMMAND, W_MESSAGE, W_YESNO, W_STATUS, W_NONE = 0x01, 0x00, 0x32, 0x02, 0xFF
-- face 토막: 주인공 셀이 이만큼 그대로이면 누름. 방향은 7E:31E0 위 니블
local FACE_STILL = 4
local FACING = {up = 0x80, down = 0x40, left = 0x20, right = 0x10}
local STABLE = tonumber(os.getenv("STABLE") or "8")
local FREE = tonumber(os.getenv("FREE") or "40")
local STUCK = tonumber(os.getenv("STUCK") or "900")
local TOKMAX = tonumber(os.getenv("TOKMAX") or "6000")
local maxf = tonumber(os.getenv("MAXF") or "20000")
local after = tonumber(os.getenv("AFTER") or "30")

local pre = {}
for tok in string.gmatch(os.getenv("PRE") or "", "[^,]+") do
  local b, f = tok:match("([%w+]+):(%d+)")
  pre[#pre + 1] = {b, tonumber(f)}
end
local toks = {}
for tok in string.gmatch(os.getenv("WAYPOINTS") or "", "[^;]+") do toks[#toks + 1] = tok end
local pokes = {}
local rngFree = false
for a, v in string.gmatch(os.getenv("POKE") or "", "(%x+)=(%x+)") do pokes[#pokes + 1] = {tonumber(a, 16), tonumber(v, 16)} end
local watches = {}
for name, a, len in string.gmatch(os.getenv("WATCH") or "", "([%w_]+)=(%x+):?(%d*)") do
  watches[#watches + 1] = {name, tonumber(a, 16), tonumber(len) or 1}
end
local patches = {}
for off, hex in string.gmatch(os.getenv("ROMPATCH") or "", "(%x+)=(%x+)") do patches[#patches + 1] = {tonumber(off, 16), hex} end

local seen = {}
emu.addMemoryCallback(function() seen[emu.getState()["cpu.a"] & 0xFFFF] = true end, emu.callbackType.exec, 0x248BAF, 0x248BAF)
-- 걸음 전투가 끝나 00:82BE(전투 뒤 걸음 처리)에 오면 AFTERPATCH 로 롬을 덮는다(붙인 전투 하나 뒤 조우를 끔)
local afterpatches, battles = {}, 0
for off, hex in string.gmatch(os.getenv("AFTERPATCH") or "", "(%x+)=(%x+)") do afterpatches[#afterpatches + 1] = {tonumber(off, 16), hex} end
emu.addMemoryCallback(function()
  battles = battles + 1
  for _, p in ipairs(afterpatches) do
    for i = 0, #p[2] / 2 - 1 do
      emu.write(p[1] + i, tonumber(p[2]:sub(i * 2 + 1, i * 2 + 2), 16), emu.memType.snesPrgRom)
    end
  end
end, emu.callbackType.exec, 0x0082BE, 0x0082BE)
-- 걸음 전투가 걸림(01:860D, dq4battlecheck 와 같은 자리)
local fights = 0
emu.addMemoryCallback(function() fights = fights + 1 end, emu.callbackType.exec, 0x01860D, 0x01860D)

local n, pi, left = 0, 1, nil
local ti, st = 1, nil           -- 지금 토막, 토막 상태(토막을 시작할 때 새로)
local log, curMap, failed, doneAt = {}, nil, false, nil
local win, winSince = nil, 0    -- 창 번호와 그 값이 이어진 프레임 수
local tick, tickSince, freeFor = nil, 0, 0

local function note(fmt, ...) log[#log + 1] = string.format("f%05d " .. fmt, n, ...) end
local function fail(fmt, ...) note("fail " .. fmt, ...); failed = true end
local function hold(b) local t = {}; for k in b:gmatch("[^+]+") do t[k] = true end; L.press(t) end
-- 버튼을 TAP 주기(누름 2, 쉼 15: 필드가 A 를 8프레임에 한 번 읽어 8 의 배수가 아닌 주기로 누르는 자리를 돌림)로 톡톡
local function tap(b) if st.t % 17 < 2 then hold(b) end end
local function stable(w) return win == w and winSince >= STABLE end
local function locked() return rd(0x7E19AE) & 1 ~= 0 end
-- 인물 표(걷는 줄 뒤 칸부터 7E:1982 앞까지)에 그 셀(또는 한 셀 위아래, 걸음 도중)에 선 사람이 있는지
-- 주인공과 겹쳐 함께 움직이는 것(탄 배)은 빼고 본다. 걷는 줄(칸 0 ~ 7E:1967 - 1: 일행·따라 걷는 개)은 주인공을 따라와
-- 길을 막지 않는다(따라 걷는 개가 출구 칸에 서 있으면 영영 기다렸다)
local function personAt(cx, cy)
  local hx, hy = rd(0x7E3020), rd(0x7E3080)
  for k = math.max(1, rd(0x7E1967)), rd(0x7E1982) - 1 do
    local px, py = rd(0x7E3020 + k), rd(0x7E3080 + k)
    if px == cx and math.abs(py - cy) <= 1 and (math.abs(px - hx) > 1 or math.abs(py - hy) > 1) then return true end
  end
  return false
end
-- 조작이 풀린 채 가만히 서 있으면 상태 창(02)이 저절로 뜬다. 걸음을 막지 않으므로 창이 없는 것과 같이 본다
local function quiet() return win == W_NONE or (win == W_STATUS and not locked()) end
local function isFree() return quiet() and freeFor >= FREE and not locked() end
-- 메시지를 넘긴다: 대화 중 뜨는 창(메시지 00, 금화 창 02 등. 7E:0A00 은 마지막으로 연 창이라 메시지와 함께 뜬 금화 창이
-- 남는다)이 그대로 서 있으면 A. 메시지 창 밖의 창은 사건이 조작을 막았을 때만(조작이 풀린 필드의 02 는 상태 창이라 A 가
-- 명령 창을 연다)
local PASS = {[0x02] = true, [0x34] = true, [0x35] = true, [0x58] = true}
local function advance()
  if winSince >= 2 and (win == W_MESSAGE or (PASS[win] and locked())) then tap("a") end
end

local function parsePace(arg)
  local a, v, d1, d2 = arg:match("^(%x+)>=(%x+),(%a+),(%a+)$")
  return tonumber(a, 16), tonumber(v, 16), d1, d2
end

-- 토막 하나를 한 프레임 한다. 끝났으면 true
local function step(tok)
  st.t = st.t + 1
  rngFree = false
  if st.t > TOKMAX then fail("timeout %s", tok); return true end
  local x, y = heroAt()
  local cx, cy, into = tok:match("^(%d+),(%d+)(!?)$")
  if cx then
    cx, cy = tonumber(cx), tonumber(cy)
    if x == cx and y == cy then note("reached %d,%d", x, y); return true end
    local key = x * 256 + y
    -- 사건이 조작을 막은 동안(구르는 바위가 따라오는 동안 등)은 막혔다고 세지 않는다
    if key == st.last and not locked() then st.stuck = st.stuck + 1 elseif key ~= st.last then st.stuck = 0 end
    st.last = key
    -- 목표에 가까워지지 않은 프레임이 STUCK 을 넘으면 fail(옆걸음으로 자리가 바뀌어도 센다)
    local dist = math.abs(cx - x) + math.abs(cy - y)
    if not st.best or dist < st.best then st.best, st.since = dist, st.t end
    -- 꺾는 자리 셀에 사람이 서 있어 닿지 못하면, 바로 옆까지 왔고 다음 토막도 셀이면 그 셀을 건너뛴다
    if (st.waited or 0) > 300 and dist <= 2 and personAt(cx, cy) and (toks[ti + 1] or ""):match("^%d+,%d+!?$") then
      note("skip %d,%d (person) at %d,%d", cx, cy, x, y); return true
    end
    -- 목표 셀(말을 걸 자리 등)에 사람이 서 있으면 비킬 때까지 그 옆에서 기다린다(옆걸음을 하지 않음)
    local waiting = into == "" and dist <= 2 and personAt(cx, cy)
    -- 기다리는 동안은 POKE(구간의 난수 묶기)를 쓰지 않는다: 묶인 난수로는 떠도는 인물이 같은 걸음만 골라 외길 칸에
    -- 끝없이 선다(레이크나바 소년). 실제 게임처럼 난수가 돌아 비키면 다음 프레임부터 다시 묶는다(dq4storytokens 와 같음)
    rngFree = waiting
    if waiting then st.waited = (st.waited or 0) + 1; st.since = st.t; st.stuck = 0 end
    if (st.waited or 0) > 3 * STUCK then fail("person stays at %d,%d", cx, cy); return true end
    if st.t - st.since > STUCK and not locked() then fail("stuck at %d,%d heading %d,%d", x, y, cx, cy); return true end
    -- 걷다 메시지가 뜨면(용병이 떠나는 말 등) 넘기고 같은 셀로 계속 걷는다. 묻는 창이 서면 이 토막을 끝내고 다음
    -- 토막(yes·no)이 답한다
    if not quiet() then
      if stable(W_YESNO) then note("question at %d,%d", x, y); return true end
      if not st.told then st.told = true; note("message at %d,%d", x, y) end
      advance(); st.stuck = 0
      return false
    end
    st.told = nil
    -- 계단·출구를 밟아 맵이 바뀌거나 필드로 나가면(필드에서는 7E:00BC·00BD 가 그대로라 7E:00BE bit7 도 봄) 그 토막은 끝
    local here = rd(0x7E00BC) * 256 + rd(0x7E00BD) + (rd(0x7E00BE) & 0x80) * 0x10000
    st.map = st.map or here
    if here ~= st.map then note("left map at %d,%d", x, y); return true end
    -- 길에 선 사람(난수로 서는 자리가 달라짐)에 60프레임 막히면 옆으로 한 걸음 비켜(번갈아 양쪽) 막힌 축을 먼저 걷는다
    if st.side and st.side > 0 then st.side = st.side - 1; hold(st.sideDir); return false end
    if waiting then return false end
    if st.stuck > 60 and quiet() and not locked() then
      st.tries = (st.tries or 0) + 1
      local horiz = x ~= cx and (st.prefer ~= "y" or y == cy)
      st.prefer = horiz and "x" or "y"
      local flip = st.tries % 2 == 1
      st.sideDir = horiz and (flip and "down" or "up") or (flip and "right" or "left")
      st.side, st.stuck = 16, 0
      note("sidestep %s at %d,%d", st.sideDir, x, y)
      return false
    end
    if st.prefer == "y" and y ~= cy then hold(y < cy and "down" or "up")
    else hold((x < cx and "right") or (x > cx and "left") or (y < cy and "down") or "up") end
    return false
  end
  local kind, arg = tok:match("^([%a*]+):?(.*)$")
  if kind == "wait" then return st.t >= tonumber(arg) end
  if kind == "face" then
    -- 걸음이 끝나는 프레임에 누르면 걸음이 비틀려 한 셀 옆에 다른 쪽을 보고 섰다(감옥 아들 앞, 실측). 주인공 셀이 FACE_STILL
    -- 프레임 그대로일 때 누르고, 다 누른 뒤 방향(7E:31E0 위 니블)이 맞지 않으면 세 번까지 다시 한다
    local here = rd(0x7E3020) * 256 + rd(0x7E3080)
    if st.at ~= here then st.at, st.still = here, 0 else st.still = (st.still or 0) + 1 end
    if not st.p0 then
      if st.still >= FACE_STILL then st.p0 = st.t end
      return false
    end
    local dt = st.t - st.p0
    if dt < 8 then hold(arg) end
    if dt < 24 then return false end
    local want = FACING[arg]
    if want == nil or rd(0x7E31E0) & 0xF0 == want then return true end
    st.tries = (st.tries or 0) + 1
    if st.tries >= 3 then fail("face %s: facing %02X", arg, rd(0x7E31E0)); return true end
    st.p0 = nil
    return false
  end
  if kind == "talk" or kind == "cmd" then
    if not st.open then
      if stable(W_COMMAND) then st.open = true; st.keys = {}; st.ki = 1; st.mark = st.t
        if kind == "cmd" then for k in arg:gmatch("[^,]+") do st.keys[#st.keys + 1] = k end end
      else tap("a") end
      return false
    end
    if st.ki <= #st.keys then
      -- 명령 창 커서 바이트를 찾지 못해, 창이 선 뒤 키마다 6프레임 누르고 25프레임 쉰다(창 안의 커서는 그 사이 늘 움직임)
      local k = st.t - st.mark
      if win ~= W_COMMAND then fail("command window closed"); return true end
      if k <= 6 then hold(st.keys[st.ki]) elseif k >= 31 then st.ki = st.ki + 1; st.mark = st.t end
      return false
    end
    if st.t < st.mark + 4 then return false end
    if win == W_COMMAND then if st.t - st.mark < 8 then hold("a") end; return false end
    return true
  end
  if kind == "serve" then
    -- 서서 다가오는 사람을 맞는다: 묻는 창마다 「예」, 메시지는 넘김. 조건이 맞고 조작이 풀리면 끝
    local a, v = arg:match("^(%x+)>=(%x+)$")
    if rd(0x7E0000 + tonumber(a, 16)) + 256 * rd(0x7E0001 + tonumber(a, 16)) >= tonumber(v, 16) and isFree() then
      return true
    end
    if stable(W_YESNO) then
      if not st.pressed then st.pressed = st.t end
      if (st.t - st.pressed) % 24 < 4 then hold("a") end
    else st.pressed = nil; advance() end
    return false
  end
  if kind == "free" or kind == "yes*" then
    if stable(W_YESNO) then
      if kind == "free" then fail("question while free"); return true end
      -- 창이 다 그려지기 전의 누름은 버려지므로, 창이 그대로면 24프레임마다 다시 누른다
      if not st.pressed then st.pressed = st.t; note("answer yes") end
      if (st.t - st.pressed) % 24 < 4 then hold("a") end
      return false
    end
    st.pressed = nil
    advance()
    return isFree()
  end
  if kind == "yes" or kind == "no" then
    if not st.asked then
      if stable(W_YESNO) then st.asked = st.t; st.cur = rd(CURSOR); note("answer %s", kind) else advance() end
      return false
    end
    local k = st.t - st.asked
    if kind == "no" and not st.moved then
      if k <= 4 then hold("down") elseif rd(CURSOR) ~= st.cur then st.moved = true; st.asked = st.t + 8
      elseif k > 60 then fail("cursor stuck no"); return true end
      return false
    end
    if k < 0 then return false end
    if k % 24 < 4 then hold("a") end
    return win ~= W_YESNO and k > 4
  end
  if kind == "fight" then
    -- 전투 동안 A 를 톡톡(たたかう·대상 첫째), 전투가 끝나 맵으로 돌아오고 조작이 풀리면 끝
    if battles > 0 and isFree() then note("battle over"); return true end
    if battles == 0 or not quiet() then tap("a") end
    return false
  end
  if kind == "meet" then
    -- 필드에서 dir1·dir2 를 32프레임씩 번갈아 걸어 무언가 걸릴 때까지(전투가 걸리거나 창이 뜸). 걸린 것을 남긴다
    if fights > (st.f0 or fights) then note("met battle"); return true end
    st.f0 = st.f0 or fights
    if not quiet() then note("met window %02X", win); return true end
    local d1, d2 = arg:match("^(%a+),(%a+)$")
    hold((st.t // 32) % 2 == 0 and d1 or d2)
    return false
  end
  if kind == "await" then
    return not quiet() or locked()
  end
  if kind == "msg" then
    if seen[tonumber(arg, 16)] then return true end
    advance()
    return false
  end
  if kind == "win" then
    -- 목표 창이 된 프레임부터는 누르지 않는다: 누르던 A 를 새 창이 받아 다음으로 넘어감
    for w in arg:gmatch("%x+") do
      if win == tonumber(w, 16) then st.hit = true; return winSince >= STABLE end
    end
    if st.hit then st.hit = nil; st.t0 = st.t end
    -- 창이 바뀐 뒤 첫 누름은 그 창이 선 뒤에
    if winSince >= 2 then tap("a") end
    return false
  end
  if kind == "near" then
    -- 인물 칸 NN(7E:3020+NN·3080+NN)의 옆(한 걸음 = 두 셀)에 서서 그 쪽을 본다. 걸어 다니는 사람에게 말을 걸 때(구간은
    -- 난수를 묶어 사람이 같은 데로 가게 함). 줄을 먼저 맞추고(위아래), 그다음 옆으로
    local slot = tonumber(arg, 16)
    local nx, ny = rd(0x7E3020 + slot), rd(0x7E3080 + slot)
    local dx, dy = nx - x, ny - y
    if (dy == 0 and math.abs(dx) == 2) or (dx == 0 and math.abs(dy) == 2) then
      st.face = st.face or st.t
      local d = (dx > 0 and "right") or (dx < 0 and "left") or (dy > 0 and "down") or "up"
      if st.t - st.face < 8 then hold(d) end
      return st.t - st.face >= 24
    end
    st.face = nil
    local key = x * 256 + y
    if key == st.last then st.stuck = st.stuck + 1 else st.stuck = 0 end
    st.last = key
    if st.stuck > STUCK then fail("near %02X stuck at %d,%d (person %d,%d)", slot, x, y, nx, ny); return true end
    if not quiet() then return false end
    local tx = nx + ((x >= nx) and 2 or -2)
    if y ~= ny then
      hold(y < ny and "down" or "up")
    else
      hold(x < tx and "right" or "left")
    end
    return false
  end
  if kind == "push" then
    -- 밀리는 인물(칸 SS)을 셀 (gx,gy)까지 민다: 인물이 그 셀이 아니면 x 를 먼저, 그다음 y 를 맞추도록 미는 쪽 반대편 셀 P 에
    -- 서서 그 쪽으로 걷는다. P 로 갈 때는 인물 옆 모서리 셀 C 를 거쳐 인물을 앞에서 밀지 않게 한다. 막히면 모서리 쪽을 바꾼다
    local slot, gx, gy = arg:match("^(%x+),(%d+),(%d+)$")
    slot, gx, gy = tonumber(slot, 16), tonumber(gx), tonumber(gy)
    local tx, ty = rd(0x7E3020 + slot), rd(0x7E3080 + slot)
    if tx == gx and ty == gy then st.ok = (st.ok or 0) + 1; return st.ok > 30 end
    st.ok = 0
    if not quiet() then advance(); return false end
    local horiz = tx ~= gx
    local dx = horiz and ((gx < tx) and -1 or 1) or 0
    local dy = horiz and 0 or ((gy < ty) and -1 or 1)
    local px, py = tx - 2 * dx, ty - 2 * dy
    local key = x * 256 + y
    if key == st.last then st.stuck = st.stuck + 1 else st.stuck = 0 end
    st.last = key
    local tkey = tx * 256 + ty
    if tkey ~= st.tlast then st.tlast, st.since = tkey, st.t end
    if st.t - st.since > STUCK then fail("push %02X stuck: person %d,%d hero %d,%d goal %d,%d", slot, tx, ty, x, y, gx, gy); return true end
    if st.stuck > 60 then st.flip = not st.flip; st.stuck = 0; note("push flip at %d,%d person %d,%d", x, y, tx, ty) end
    if x == px and y == py then
      hold((dx > 0 and "right") or (dx < 0 and "left") or (dy > 0 and "down") or "up")
      return false
    end
    local side = st.flip and -2 or 2
    local cx, cy
    if horiz then cx, cy = px, py + side else cx, cy = px + side, py end
    -- P 와 같은 줄(위아래로 밀 때)·열(옆으로 밀 때)에 오면 P 로, 아니면 모서리로. 모서리로 갈 때는 인물과 겹치지 않는 축을
    -- 먼저(위아래로 밀 때는 옆으로 먼저, 옆으로 밀 때는 위아래로 먼저)
    if not horiz and y == py then hold(x < px and "right" or "left")
    elseif horiz and x == px then hold(y < py and "down" or "up")
    elseif not horiz then hold((x < cx and "right") or (x > cx and "left") or (y < cy and "down") or "up")
    else hold((y < cy and "down") or (y > cy and "up") or (x < cx and "right") or "left") end
    return false
  end
  if kind == "pick" then
    -- 목록 커서가 고르는 값(WRAM 바이트)이 VV 가 될 때까지 아래를 톡톡(2프레임 누르고 15 쉼, 가게 장면 검사와 같은 주기)
    local a, v = arg:match("^(%x+)=(%x+)$")
    a, v = 0x7E0000 + tonumber(a, 16), tonumber(v, 16)
    if rd(a) == v then st.ok = (st.ok or 0) + 1; return st.ok > 8 end
    st.ok = 0
    if rd(a) ~= st.cur then st.cur = rd(a); st.mark = st.t; note("pick %02X", st.cur) end
    if st.t - st.mark > 200 then fail("pick stuck %02X", rd(a)); return true end
    tap("down")
    return false
  end
  if kind == "rest" then
    -- WRAM 7E:AAAA·AAAA+1(구르는 바위 X·Y 등)이 N 프레임 그대로일 때까지 누르지 않고 기다린다(움직이는 물체가 멈출 때까지)
    local a, nn = arg:match("^(%x+),(%d+)$")
    a, nn = 0x7E0000 + tonumber(a, 16), tonumber(nn)
    local v = rd(a) * 256 + rd(a + 1)
    if v ~= st.v then st.v, st.vt = v, st.t end
    advance()
    if st.t - st.vt >= nn then note("rest %04X", v); return true end
    return false
  end
  if kind == "see" then
    -- 메시지를 넘기며 WRAM 바이트 7E:AAAA 가 VV 가 될 때까지(장 끝 서술 뒤 지금 곡 등)
    local a, v = arg:match("^(%x+)=(%x+)$")
    if rd(0x7E0000 + tonumber(a, 16)) == tonumber(v, 16) then return true end
    advance()
    return false
  end
  if kind == "close" then
    -- 창을 B 로 닫아 조작이 풀릴 때까지
    if isFree() then return true end
    if not quiet() and winSince >= 4 then tap("b") end
    return false
  end
  if kind == "map" then
    local g, k = arg:match("^(%x+)/(%x+)$")
    advance()
    -- 필드에서는 7E:00BC·00BD 가 들어갈 맵 번호를 미리 갖고 있어 실내(7E:00BE bit7)도 본다
    return rd(0x7E00BC) == tonumber(g, 16) and rd(0x7E00BD) == tonumber(k, 16) and rd(0x7E00BE) & 0x80 ~= 0 and isFree()
  end
  if kind == "field" then
    advance()
    return rd(0x7E00BE) & 0x80 == 0 and isFree()
  end
  if kind == "stand" then
    local ss, sx, sy = arg:match("^(%x+),(%d+),(%d+)$")
    local slot = tonumber(ss, 16)
    return rd(0x7E3020 + slot) == tonumber(sx) and rd(0x7E3080 + slot) == tonumber(sy) and rd(0x7E3280 + slot) & 0x80 == 0
  end
  if kind == "pace" then
    local a, v, d1, d2 = parsePace(arg)
    if rd(0x7E0000 + a) + 256 * rd(0x7E0001 + a) >= v then return true end
    advance()
    if quiet() then hold((st.t // 32) % 2 == 0 and d1 or d2) end
    return false
  end
  local b, f = tok:match("^(%a+):(%d+)$")
  if b then
    if st.t <= tonumber(f) then hold(b) end
    return st.t >= tonumber(f)
  end
  fail("bad token %s", tok)
  return true
end

emu.addEventCallback(function()
  n = n + 1
  if n == 1 then
    for _, p in ipairs(patches) do
      for i = 0, #p[2] / 2 - 1 do
        emu.write(p[1] + i, tonumber(p[2]:sub(i * 2 + 1, i * 2 + 2), 16), emu.memType.snesPrgRom)
      end
    end
  end
  if not rngFree then for _, p in ipairs(pokes) do emu.write(p[1], p[2], m) end end
  L.release()
  local w = rd(WINDOW)
  if w == win then winSince = winSince + 1 else win, winSince = w, 0 end
  local t = rd(TICK)
  if t ~= tick then tick, tickSince = t, 0 else tickSince = tickSince + 1 end
  -- 필드 루프가 도는 동안 7E:007F 는 적어도 몇 프레임마다 바뀐다
  local calm = win == W_NONE or (win == W_STATUS and rd(0x7E19AE) & 1 == 0)
  if calm and tickSince < 4 then freeFor = freeFor + 1 elseif not calm or tickSince > 8 then freeFor = 0 end
  local bc, bd = rd(0x7E00BC), rd(0x7E00BD)
  local x, y = heroAt()
  local map = bc * 256 + bd
  if not curMap then curMap = map end
  if map ~= curMap then
    note("map %02X/%02X -> %02X/%02X at x=%d y=%d", curMap >> 8, curMap & 255, bc, bd, x, y)
    curMap = map
  end
  if pi <= #pre then
    local s = pre[pi]
    if left == nil then left = s[2] end
    if s[1] ~= "wait" then hold(s[1]) end
    left = left - 1
    if left <= 0 then pi = pi + 1; left = nil end
  elseif not failed and ti <= #toks then
    if st == nil then st = {t = 0, stuck = 0}; note("token %s", toks[ti]) end
    if step(toks[ti]) then ti = ti + 1; st = nil end
    if ti > #toks then doneAt = n end
  end
  if (doneAt and n >= doneAt + after) or failed or n >= maxf then
    if n >= maxf and not doneAt and not failed then note("fail maxf at token %s", toks[ti] or "?") end
    note("end map %02X/%02X x=%d y=%d", bc, bd, x, y)
    for _, wt in ipairs(watches) do
      local v = 0
      for k = wt[3] - 1, 0, -1 do v = v * 256 + rd(wt[2] + k) end
      log[#log + 1] = string.format("%s=%0" .. (wt[3] * 2) .. "X", wt[1], v)
    end
    L.write("walk.txt", table.concat(log, "\n") .. "\n")
    L.shot("end.png")
    emu.stop(0)
  end
end, emu.eventType.endFrame)
