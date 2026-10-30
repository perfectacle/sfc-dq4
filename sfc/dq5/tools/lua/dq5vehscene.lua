-- 탈것 장면(타고 내리기·펴기·내려앉기)을 한 번에 잰다. 드라이버(boot.lua, 보통 dq5warp.lua) 앞에 붙여 쓰고, MesenCE 인자에
-- --Snes.DisableFrameSkipping=true 를 준다.
--   1. 00:FC60 에서 탈것 슬롯(7E:3220 = FE)이 그린 블록: dq5vehicleblocks.lua 와 같은 줄을 blocks.txt 에 센다(FROM~UNTIL).
--   2. 지형 루틴 03:CB1B 를 부른 곳(스택의 돌아갈 자리 − 3)마다 횟수와 처음·마지막 프레임, 돌아간 A(16비트)의 값 모음.
--   3. EXEC 의 PC(16진, 쉼표로)마다 실행 횟수와 처음·마지막 프레임.
--   4. 프레임마다 $1954(탈것)·$BC/$BD·$1949(세계)·$B6·$B8(필드 좌표)이 바뀐 프레임을 state.txt 에 적는다.
--   5. SHOTS 의 프레임에는 화면(fNNNNN.png)과 WRAM(fNNNNN.wram)·OAM(fNNNNN.oam)을 남긴다. SHOTLAG=N 이면 1 의 줄을
--      처음 센 프레임 + N 에도 남긴다.
-- 결과는 EVERY(기본 100) 프레임마다 다시 쓴다: SHOT_DIR/blocks.txt, calls.txt
-- 「cb1b 부른곳 횟수 첫프레임 끝프레임 A값들」·「exec PC 횟수 첫프레임 끝프레임」, state.txt 「프레임 1954 BC/BD 1949 B6,B8」.
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local L = require("lib")
local m = emu.memType.snesMemory
local from = tonumber(os.getenv("FROM") or "0")
local untilf = tonumber(os.getenv("UNTIL") or "100000")
local every = tonumber(os.getenv("EVERY") or "100")
local n = 0
local seen, order, first, last = {}, {}, {}, {}
local calls, corder, caller = {}, {}, nil
local execs, states, prev = {}, {}, nil
local shots = {}
for a in string.gmatch(os.getenv("SHOTS") or "", "%d+") do shots[tonumber(a)] = true end
-- 블록 프로브의 프레임 번호는 끝난 프레임 수라, 그 프레임에 그린 칸은 두 프레임 뒤 덤프의 OAM 에 나온다.
local shotlag = tonumber(os.getenv("SHOTLAG") or "")

local function rd(a) return emu.read(a, m) end
local function rd16(a) return rd(a) | rd(a + 1) << 8 end

emu.addMemoryCallback(function()
  if n < from or n > untilf then return end
  local s = emu.getState()
  local y = s["cpu.y"] & 0xFF
  if rd(0x7E3220 + y) ~= 0xFE then return end
  local base = rd16(0x7E8000 + rd(0x7E3200 + y))
  local key = string.format("%02X %04X %dx%d %02X %02X %02X %d %X %X", y, base, rd(0x7E34E0 + y), rd(0x7E3500 + y),
    rd(0x7E37C0 + y), rd(0x7E37E0 + y), rd(0x7E32A0 + y), rd16(s["cpu.d"] + 0xAE) - base, rd(0x7E3240 + y) & 0x0F,
    rd(0x7E3280 + y))
  if not seen[key] then
    seen[key] = 0; order[#order + 1] = key; first[key] = n
    if shotlag then shots[n + shotlag] = true end
  end
  seen[key] = seen[key] + 1
  last[key] = n
end, emu.callbackType.exec, 0x00FC60, 0x00FC60)

-- 롬에서 JSL $03CB1B 는 01:81D6·01:84E0·01:BE8E·03:CB11 넷뿐이다. 돌아갈 자리는 JSL + 4.
emu.addMemoryCallback(function()
  local sp = emu.getState()["cpu.sp"]
  caller = (rd(sp + 3) << 16 | rd(sp + 2) << 8 | rd(sp + 1)) - 3
end, emu.callbackType.exec, 0x03CB1B, 0x03CB1B)
for _, pc in ipairs({0x0181DA, 0x0184E4, 0x01BE92, 0x03CB15}) do
  emu.addMemoryCallback(function()
    if caller ~= pc - 4 then return end
    local c = calls[caller]
    if not c then c = {count = 0, first = n, vals = {}, vorder = {}}; calls[caller] = c; corder[#corder + 1] = caller end
    c.count, c.last = c.count + 1, n
    local a = string.format("%04X", emu.getState()["cpu.a"] & 0xFFFF)
    if not c.vals[a] then c.vals[a] = 0; c.vorder[#c.vorder + 1] = a end
    c.vals[a] = c.vals[a] + 1
    caller = nil
  end, emu.callbackType.exec, pc, pc)
end

for a in string.gmatch(os.getenv("EXEC") or "", "%x+") do
  local e = {pc = tonumber(a, 16), count = 0}
  execs[#execs + 1] = e
  emu.addMemoryCallback(function()
    e.count, e.first, e.last = e.count + 1, e.first or n, n
  end, emu.callbackType.exec, e.pc, e.pc)
end

local function report()
  local out = {}
  table.sort(order)
  for _, k in ipairs(order) do out[#out + 1] = k .. " " .. seen[k] .. " " .. first[k] .. " " .. last[k] end
  L.write("blocks.txt", table.concat(out, "\n") .. "\n")
  local t = {}
  for _, k in ipairs(corder) do
    local c, vs = calls[k], {}
    for _, a in ipairs(c.vorder) do vs[#vs + 1] = a .. ":" .. c.vals[a] end
    t[#t + 1] = string.format("cb1b %06X %d %d %d %s", k, c.count, c.first, c.last, table.concat(vs, ","))
  end
  for _, e in ipairs(execs) do t[#t + 1] = string.format("exec %06X %d %d %d", e.pc, e.count, e.first or -1, e.last or -1) end
  L.write("calls.txt", table.concat(t, "\n") .. "\n")
  L.write("state.txt", table.concat(states, "\n") .. "\n")
end

emu.addEventCallback(function()
  n = n + 1
  local cur = string.format("%02X %02X/%02X %02X %d,%d", rd(0x7E1954), rd(0x7E00BC), rd(0x7E00BD), rd(0x7E1949),
    rd16(0x7E00B6), rd16(0x7E00B8))
  if cur ~= prev then states[#states + 1] = n .. " " .. cur; prev = cur end
  if shots[n] then
    L.shot(string.format("f%05d.png", n))
    L.dump(string.format("f%05d.wram", n), emu.memType.snesWorkRam, 0x20000)
    L.dump(string.format("f%05d.oam", n), emu.memType.snesSpriteRam, 0x220)
  end
  if n % every == 0 then report() end
end, emu.eventType.endFrame)
dofile(os.getenv("LIBDIR") .. "/boot.lua")
-- FLEE=1: 무작위 전투(01:8677 JSL $208001 ~ 01:867B)에서는 드라이버 입력 대신 60프레임마다 아래·A 로 にげる 를 고른다
-- (dq5battleflee.lua 와 같은 입력). 전투 중 $1001 은 0 이라 전투 진입·복귀 주소로 가린다. 드라이버 입력보다 뒤에 걸어야
-- 덮이지 않는다.
if os.getenv("FLEE") == "1" then
  local battle = false
  emu.addMemoryCallback(function() battle = true end, emu.callbackType.exec, 0x208001, 0x208001)
  emu.addMemoryCallback(function() battle = false end, emu.callbackType.exec, 0x01867B, 0x01867B)
  emu.addEventCallback(function()
    if not battle then return end
    local k = n % 60
    if k < 4 then emu.setInput({down = true}, 0) elseif k >= 20 and k < 24 then emu.setInput({a = true}, 0)
    else emu.setInput({}, 0) end
  end, emu.eventType.inputPolled)
end
-- APRESS=F: F 프레임부터 탈것의 A 처리(00:8127 → 01:BC3F)가 돌 때까지, 7E:007F & 7 이 6 이상인 프레임마다 A 를 3프레임 누른다
-- (天空城 은 7F 가 프레임마다 1, マスタードラゴン 은 2 씩 늘고 & 7 = 0 인 프레임에 읽는다).
-- 탈것이 움직이는 동안은 00:8185 가 입력을 몇 프레임에 한 번만 읽어 드라이버의 고정 프레임 입력이 창을 비껴가기 쉽다.
local apress = tonumber(os.getenv("APRESS") or "")
if apress then
  local left, done = 0, false
  emu.addMemoryCallback(function() if n >= apress then done = true end end, emu.callbackType.exec, 0x01BC3F, 0x01BC3F)
  emu.addEventCallback(function()
    if not done and left == 0 and n >= apress and rd(0x7E007F) & 7 >= 6 then left = 3 end
    if left > 0 then emu.setInput({a = true}, 0); left = left - 1 end
  end, emu.eventType.inputPolled)
end
