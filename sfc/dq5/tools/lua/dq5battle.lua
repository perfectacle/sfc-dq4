-- DQ5 전투 실험. walk.lua 처럼 PRE 입력 → WAYPOINTS 로 걷고, 경유점이 끝나면 LOOP 입력(기본 A 연타 = 싸운다)을 되풀이한다.
-- 전투 메시지(24:8C39)가 불릴 때마다 프레임·메시지 번호(A)·PEEK 주소들의 값을 battle.txt 에 적는다.
--   ROMPATCH="파일오프셋=16진,…"  첫 프레임에 롬을 덮는다(레코드·표 바꾸기)
--   POKE="CPU주소=값,…"           매 프레임 RAM 에 쓴다
--   PEEK="7E07C0:64,7E206C:4"      메시지마다 적을 주소:길이
--   SHOTMSG="0B4,069" 또는 all     그 메시지가 뜬 뒤 SHOTDELAY(기본 34)프레임에 화면을 찍는다
-- 쓰는 예는 sfc/dq5/docs/dq5-data-format.md 의 「주문과 행동」 과 그 일지.
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local L = require("lib")
L.loadState(os.getenv("STATE"))
local m = emu.memType.snesMemory

local function parseSeq(s)
  local t = {}
  for tok in string.gmatch(s or "", "[^,;]+") do
    local b, f = tok:match("([%w+]+):(%d+)")
    if b then t[#t + 1] = {b, tonumber(f)} end
  end
  return t
end

local pre = parseSeq(os.getenv("PRE"))
local loop = parseSeq(os.getenv("LOOP") or "a:4,wait:20")
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
local patches = {}
for off, hex in string.gmatch(os.getenv("ROMPATCH") or "", "(%x+)=(%x+)") do patches[#patches + 1] = {tonumber(off, 16), hex} end
local peeks = {}
for a, len in string.gmatch(os.getenv("PEEK") or "", "(%x+):?(%d*)") do peeks[#peeks + 1] = {tonumber(a, 16), tonumber(len) or 1} end
local shotmsg = os.getenv("SHOTMSG")
local shotdelay = tonumber(os.getenv("SHOTDELAY") or "34")
local maxf = tonumber(os.getenv("MAXF") or "3000")

local n, pi, left, wi, stuck, last, press, li, lleft = 0, 1, nil, 1, 0, nil, nil, 1, nil
local log, shots = {}, {}

local function peekstr()
  local t = {}
  for _, p in ipairs(peeks) do
    local s = {}
    for k = 0, p[2] - 1 do s[#s + 1] = string.format("%02X", emu.read(p[1] + k, m)) end
    t[#t + 1] = string.format("%06X=%s", p[1], table.concat(s))
  end
  return table.concat(t, " ")
end

emu.addMemoryCallback(function()
  local msg = emu.getState()["cpu.a"] & 0xFFFF
  log[#log + 1] = string.format("f%05d msg %03X %s", n, msg, peekstr())
  if shotmsg and (shotmsg == "all" or shotmsg:find(string.format("%03X", msg))) then shots[n + shotdelay] = true end
end, emu.callbackType.exec, 0x248C39, 0x248C39)

local function pressSeq(s)
  if s[1] == "wait" then return end
  local t = {}
  for b in s[1]:gmatch("[^+]+") do t[b] = true end
  L.press(t)
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
  for _, p in ipairs(pokes) do emu.write(p[1], p[2], m) end
  L.release()
  local x, y = emu.read(0x7E3020, m), emu.read(0x7E3080, m)
  if pi <= #pre then
    if left == nil then left = pre[pi][2] end
    pressSeq(pre[pi])
    left = left - 1
    if left <= 0 then pi = pi + 1; left = nil end
  elseif wi <= #pts then
    local p = pts[wi]
    if type(p[1]) == "string" then
      if press == nil then press = p[2] end
      if p[1] ~= "wait" then L.press({[p[1]] = true}) end
      press = press - 1
      if press <= 0 then press = nil; wi = wi + 1 end
    elseif x == p[1] and y == p[2] then
      wi = wi + 1; stuck = 0
    else
      local key = x * 256 + y
      if key == last then stuck = stuck + 1 else stuck = 0 end
      last = key
      if stuck > 90 then wi = wi + 1; stuck = 0 end
      local b = (x < p[1] and "right") or (x > p[1] and "left") or (y < p[2] and "down") or "up"
      L.press({[b] = true})
    end
  else
    if lleft == nil then lleft = loop[li][2] end
    pressSeq(loop[li])
    lleft = lleft - 1
    if lleft <= 0 then li = li % #loop + 1; lleft = nil end
  end
  if shots[n] then L.shot(string.format("s%05d.png", n)) end
  if n >= maxf then
    L.write("battle.txt", table.concat(log, "\n") .. "\n")
    L.shot("end.png")
    emu.stop(0)
  end
end, emu.eventType.endFrame)
