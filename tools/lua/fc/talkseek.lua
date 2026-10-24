-- 입력 드라이버: 세이브스테이트(STATE)에서 인물 표의 인물(슬롯 6~1F, 또는 TARGETS 의 16진 슬롯 목록)에게
-- 차례로 걸어가 말을 건다. 한 칸씩(16프레임) 걷고, 길이 없으면 무작위 방향(SEED)으로 걷는다.
-- 슬롯마다 GIVEUP 걸음(기본 60) 안에 못 닿으면 다음 인물로 넘어간다. 말 걸기는 A 로 「はなす」를 고르고
-- A 를 몇 번 더 눌러 창을 넘긴 뒤(예/아니오는 「はい」) B 로 닫는다.
-- 대화 기록은 프로브(talk.lua)가 남긴다. 걸음마다 (프레임, 주인공 X Y, 목표 슬롯 X Y, 방향)을 seek.txt 에 쓰고 MAXF 프레임에 멈춘다.
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local L = require("lib")
L.loadState(os.getenv("STATE"))
math.randomseed(tonumber(os.getenv("SEED") or "1"))
local maxf = tonumber(os.getenv("MAXF") or "20000")
local giveup = tonumber(os.getenv("GIVEUP") or "60")

local targets = {}
if (os.getenv("TARGETS") or "") ~= "" then
  for s in string.gmatch(os.getenv("TARGETS"), "%x+") do targets[#targets + 1] = tonumber(s, 16) end
else
  for s = 6, 0x1F do targets[#targets + 1] = s end
end

local TALK = {{"a", 6}, {"wait", 30}, {"a", 6}, {"wait", 120}, {"a", 6}, {"wait", 70}, {"a", 6}, {"wait", 70},
  {"a", 6}, {"wait", 70}, {"b", 6}, {"wait", 30}, {"b", 6}, {"wait", 30}, {"b", 6}, {"wait", 30}}
local DIRS = {up = {0, -1}, down = {0, 1}, left = {-1, 0}, right = {1, 0}}
local NAMES = {"up", "down", "left", "right"}

local talked = {}
emu.addMemoryCallback(function()
  if L.prgOffset(0x98F8) == 0x558F8 then talked[emu.getState()["cpu.a"]] = true end
end, emu.callbackType.exec, 0x98F8, 0x98F8)

local function pos(slot) return emu.read(0x6F60 + slot, L.mem), emu.read(0x6F80 + slot, L.mem) end

-- 막힌 칸은 걸어 보고 배운다(알 수 없는 칸은 지나갈 수 있다고 보고 너비 우선 탐색).
-- W·H 는 맵 크기(가장자리 칸은 밖으로 나가는 출구라 밟지 않음), AVOID="x,y;x,y" 는 출구 칸(16진).
local W, H = tonumber(os.getenv("W") or "40", 16), tonumber(os.getenv("H") or "40", 16)
local blocked = {}
for x, y in string.gmatch(os.getenv("AVOID") or "", "(%x+),(%x+)") do blocked[tonumber(y, 16) * 256 + tonumber(x, 16)] = true end
local function wall(x, y) return x <= 0 or y <= 0 or x >= W - 1 or y >= H - 1 or blocked[y * 256 + x] end

local queue, ti, steps, attempts, last, log, n = {}, 1, 0, 0, nil, {}, 0
local function push(b, f) queue[#queue + 1] = {b, f} end

local function occupied(skip)
  local o = {}
  for s = 1, 0x1F do
    if s ~= skip and (s >= 6 or s == 0) then
      local x, y = pos(s)
      if x < 0x80 then o[y * 256 + x] = true end
    end
  end
  return o
end

-- 주인공 칸에서 목표 옆 칸까지 첫 걸음 방향
local function route(hx, hy, tx, ty, occ)
  local goal = {}
  for _, d in ipairs(NAMES) do
    local v = DIRS[d]
    goal[(ty + v[2]) * 256 + tx + v[1]] = true
  end
  local start = hy * 256 + hx
  local first, seen, q, qi = {}, {[start] = true}, {start}, 1
  while qi <= #q do
    local c = q[qi]; qi = qi + 1
    if goal[c] then return first[c] end
    local cx, cy = c % 256, c // 256
    for _, d in ipairs(NAMES) do
      local v = DIRS[d]
      local nx, ny = cx + v[1], cy + v[2]
      local k = ny * 256 + nx
      if not seen[k] and not wall(nx, ny) and not occ[k] then
        seen[k] = true
        first[k] = first[c] or d
        q[#q + 1] = k
      end
    end
  end
  return nil
end

local function decide()
  if last then
    local hx, hy = pos(0)
    if hx == last[1] and hy == last[2] and not last[4] then
      local v = DIRS[last[3]]
      blocked[(hy + v[2]) * 256 + hx + v[1]] = true
    end
    last = nil
  end
  while ti <= #targets do
    local t = targets[ti]
    local tx = pos(t)
    if tx < 0x80 and not talked[t] and steps < giveup and attempts < 3 then break end
    ti, steps, attempts = ti + 1, 0, 0
  end
  if ti > #targets then return push("wait", 30) end
  local hx, hy = pos(0)
  local tx, ty = pos(targets[ti])
  local dx, dy = tx - hx, ty - hy
  if math.abs(dx) + math.abs(dy) == 1 then
    local d = dx == 1 and "right" or dx == -1 and "left" or dy == 1 and "down" or "up"
    attempts = attempts + 1
    push(d, 2); push("wait", 10)
    for _, s in ipairs(TALK) do push(s[1], s[2]) end
    return
  end
  local occ = occupied(targets[ti])
  local d = route(hx, hy, tx, ty, occ)
  if not d then
    steps = steps + 5
    d = NAMES[math.random(4)]
  end
  local v = DIRS[d]
  last = {hx, hy, d, occ[(hy + v[2]) * 256 + hx + v[1]]}
  steps = steps + 1
  log[#log + 1] = string.format("%d %02X %02X %02X %02X %02X %s", n, hx, hy, targets[ti], tx, ty, d)
  push(d, 16); push("wait", 2)
end

local cur, left = nil, 0
emu.addEventCallback(function()
  n = n + 1
  if n < 3 then return end
  L.release()
  if left <= 0 then
    if #queue == 0 then decide() end
    cur = table.remove(queue, 1)
    left = cur[2]
  end
  if cur[1] ~= "wait" then L.press({[cur[1]] = true}) end
  left = left - 1
  if n == maxf - 1 then L.write("seek.txt", table.concat(log, "\n") .. "\n") end
  if n >= maxf + 2 then emu.stop(0) end
end, emu.eventType.endFrame)
