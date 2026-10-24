-- DQ5: 배 선실 세이브스테이트(STATE)에서 원하는 장면으로 순간이동해, 조작할 수 있는 상태로 세이브스테이트(SAVE)를 남긴다.
-- 배의 사다리 출구 항목(2A:EFF5)을 목적지 표 종류 60 항목으로 덮고 사다리를 밟아, 게임의 맵 불러오기를 그대로 탄다.
--   TO="01/04,12,44[,층]"    실내 맵 $BC/$BD(16진)와 셀 좌표(10진). 층은 도착 뒤 주인공 층 마스크($C3 → 7E:31A0), 기본 1.
--                            그 맵 바닥의 층과 다르면 주인공이 움직이지 못한다(01/00 은 2)
--   FIELD="341,56"           필드 좌표($B6,$B8, 10진). 01/00 으로 간 뒤 아래로 걸어 나가는데, 그때 쓰는 입구 표
--                            04:FD97 의 01 항목을 이 좌표로 덮는다. 첫 필드 이벤트(파파스와 슬라임 전투)를 끄려고
--                            7E:2194 bit7 을 켠다(필드 루틴 15:F907 의 FE 항목)
--   BATTLE="00:3,0C:2"       FIELD 와 함께. 첫 필드 이벤트를 켠 채 그 이벤트 전투 무리(23:D757 의 1번)를 몬스터:마릿수(16진:10진,
--                            최대 4종)로 바꿔 전투를 붙인다
--   GROUP="2C"               FIELD 와 함께. 첫 필드 이벤트가 거는 무리 번호(02:A780 의 LDA #$01)를 바꿔 이벤트 전투 무리
--                            표 23:D757 의 그 번호(16진)와 전투를 붙인다. BATTLE 과 함께 주면 그 번호의 무리를 덮는다
--   SET="2194|80;1949=01"    시작할 때 한 번 WRAM(7E 뱅크 하위 16비트 주소)을 고친다. =는 값, |는 OR, &는 AND
--   PARTY="02,05"            시작할 때 동료 몬스터(23:AED1 의 종류 번호, 16진)를 주인공 뒤 일행 레코드(7E:2040 + n*42)에 넣는다.
--                            레코드는 동료가 된 スライム 의 실측 레코드를 틀로, 종류·레벨·능력치·HP·MP 만 동료 레코드에서 채운다.
--                            일행 수 7E:201D·201F, 걷는 수 7E:201E(최대 3), 순서 7E:2020~·7E:2028~ 도 고친다
--   ADULT=1                  이야기 단계 플래그 7E:2190 bit6·5 를 켜고 $1948 = 2 로 둔다(00:A72A 가 플래그로 정하는 값과 같게).
--                            주인공 그림이 노예 시절 차림으로 바뀌고, 필드 조우는 $1948 = 2 격자를 쓴다
--   ADULT=2                  ADULT=1 에 7E:21BE bit5 를 더해 망토 차림 어른 주인공(그림 2D, 05:D998)으로 한다
--   WAGON=1                  마차(7E:201C bit7, BRK 88 91). 동료 둘까지 마차 옆을 걷는다
--   LATESET="1954=80"         SET 과 같은 꼴로, 도착해 조작할 수 있게 된 첫 프레임에 한 번 고친다(사다리를 내려가기 전에 바꾸면
--                            안 되는 탈것 값 등)
--   POKE, ROMPATCH           walk.lua 와 같다(POKE 는 매 프레임 고정, ROMPATCH 는 파일 오프셋=바이트)
--   TEST="left:40,up:40"     도착 후 이 입력을 눌러 조작되는지 본다(좌표가 바뀌면 moved=yes). 세이브는 TEST 전에 한다
--   SAVE="town.mss"          도착하고 SETTLE(기본 150) 프레임 뒤 SHOT_DIR 에 세이브스테이트와 그림(.png)을 저장
-- 결과: SHOT_DIR/warp.txt(맵, 셀·필드 좌표, $BE, 플래그), end.png. 선실 세이브스테이트가 아닌 곳에서는 사다리 경로가 맞지 않는다.
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local L = require("lib")
L.loadState(os.getenv("STATE"))
local m = emu.memType.snesMemory

local function hexbytes(off, hex, list)
  list[#list + 1] = {off, hex}
end
local patches = {}
for off, hex in string.gmatch(os.getenv("ROMPATCH") or "", "(%x+)=(%x+)") do hexbytes(tonumber(off, 16), hex, patches) end

local sets = {}
for a, op, v in string.gmatch(os.getenv("SET") or "", "(%x+)([=|&])(%x+)") do
  sets[#sets + 1] = {0x7E0000 + tonumber(a, 16), op, tonumber(v, 16)}
end
-- 동료가 된 スライム 의 일행 레코드(42바이트). +6(すばやさ)·+26~+28(다음 레벨 경험치)·+29 는 동료 레코드에서 오지 않아 그대로 둔다
local PARTY_TEMPLATE = {
  0x82, 0x80, 0x08, 0x00, 0x00, 0x00, 0x03, 0x08, 0x05, 0x01, 0x03, 0x00, 0x00, 0x00, 0x08, 0x00,
  0x00, 0x00, 0x01, 0x63, 0x00, 0x00, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF,
  0xFF, 0xFF, 0x00, 0x00, 0x00, 0x00, 0x4B, 0x00, 0x00, 0x02,
}
local function buildParty()
  local kinds = {}
  for k in string.gmatch(os.getenv("PARTY") or "", "%x+") do kinds[#kinds + 1] = tonumber(k, 16) end
  if #kinds == 0 then return end
  local m = emu.memType.snesMemory
  for i, k in ipairs(kinds) do
    local c = {}
    for j = 0, 8 do c[j] = emu.read(0x23AED1 + k * 9 + j, m) end
    local r = {}
    for j = 1, 42 do r[j - 1] = PARTY_TEMPLATE[j] end
    r[0] = 0x80 | k
    r[0x12], r[0x13] = c[0], c[1]
    for j = 0, 3 do r[7 + j] = c[2 + j] end
    r[2], r[0xE] = c[6], c[6]
    r[4], r[0x10] = c[7], c[7]
    for j = 0, 41 do emu.write(0x7E2040 + i * 42 + j, r[j], m) end
  end
  -- 7E:201E 는 마차 밖을 걷는 수(주인공 포함 최대 3). 넷째부터는 마차에 탄다
  emu.write(0x7E201D, 1 + #kinds, m)
  emu.write(0x7E201E, math.min(1 + #kinds, 3), m)
  emu.write(0x7E201F, 1 + #kinds, m)
  for i = 0, #kinds do
    emu.write(0x7E2020 + i, i, m)
    emu.write(0x7E2028 + i, i, m)
  end
end
local adult = os.getenv("ADULT")
if adult == "1" or adult == "2" then
  sets[#sets + 1] = {0x7E2190, "|", 0x60}
  sets[#sets + 1] = {0x7E1948, "=", 0x02}
end
if adult == "2" then sets[#sets + 1] = {0x7E21BE, "|", 0x20} end
if os.getenv("WAGON") == "1" then sets[#sets + 1] = {0x7E201C, "|", 0x80} end
local latesets = {}
for a, op, v in string.gmatch(os.getenv("LATESET") or "", "(%x+)([=|&])(%x+)") do
  latesets[#latesets + 1] = {0x7E0000 + tonumber(a, 16), op, tonumber(v, 16)}
end
local pokes = {}
for a, v in string.gmatch(os.getenv("POKE") or "", "(%x+)=(%x+)") do pokes[#pokes + 1] = {tonumber(a, 16), tonumber(v, 16)} end

local field = os.getenv("FIELD")
local battle = os.getenv("BATTLE")
local to = os.getenv("TO")
local bc, bd, tx, ty, dir
if field then
  bc, bd, tx, ty, dir = 0x01, 0x00, 32, 92, 2
  local fx, fy = field:match("^(%d+),(%d+)$")
  fx, fy = tonumber(fx), tonumber(fy)
  -- 04:FD97 의 열한째 항목(그룹 01)의 X, Y
  hexbytes(0x27DCA, string.format("%02X%02X%02X%02X", fx & 255, fx >> 8, fy & 255, fy >> 8), patches)
  local group = os.getenv("GROUP")
  if group then hexbytes(0x12781, string.format("%02X", tonumber(group, 16)), patches) end
  if battle then
    local e = {0xD0, 0xFF, 0xFF, 0xFF, 0xFF, 0, 0, 0, 0, 0, 0, 0, 0}
    local i = 0
    for id, cnt in string.gmatch(battle, "(%x+):(%d+)") do
      e[2 + i] = tonumber(id, 16); e[6 + i] = tonumber(cnt); i = i + 1
    end
    local t = {}
    for _, b in ipairs(e) do t[#t + 1] = string.format("%02X", b) end
    hexbytes(0x11D757 + (group and tonumber(group, 16) or 1) * 13, table.concat(t), patches)
  elseif not group then
    sets[#sets + 1] = {0x7E2194, "|", 0x80}
  end
else
  local b1, b2, x, y, d = to:match("^(%x+)/(%x+),(%d+),(%d+),?(%d*)$")
  bc, bd, tx, ty = tonumber(b1, 16), tonumber(b2, 16), tonumber(x), tonumber(y)
  dir = tonumber(d) or 1
end
-- 종류 60 항목: [E0|BD][X][Y][층][BC]. bit7 은 「그 맵의 마지막 항목」 표시라 켜 둔다.
hexbytes(0x156FF5, string.format("%02X%02X%02X%02X%02X", 0xE0 | bd, tx, ty, dir, bc), patches)

local function parseSeq(s)
  local t = {}
  for tok in string.gmatch(s or "", "[^,]+") do
    local b, f = tok:match("([%w+]+):(%d+)")
    t[#t + 1] = {b, tonumber(f)}
  end
  return t
end
-- 선실에서 사다리까지: 대화 창을 닫고 (3,11) → (3,24) → (7,24), 위로 밟는다. 필드면 01/00 에서 아래로 걸어 나간다.
local route = parseSeq("b:4,wait:40")
local ladder = {{3, 11}, {3, 24}, {7, 24}}
local test = parseSeq(os.getenv("TEST"))
local settle = tonumber(os.getenv("SETTLE") or "150")
local maxf = tonumber(os.getenv("MAXF") or "3000")
local save = os.getenv("SAVE")

local function rd(a) return emu.read(a, m) end
local function rd16(a) return rd(a) | rd(a + 1) << 8 end
local log = {}
local n, phase, si, left, wi, arrived, startPos = 0, "pre", 1, nil, 1, nil, nil
local function play(seq)
  if si > #seq then return true end
  local s = seq[si]
  if left == nil then left = s[2] end
  if s[1] ~= "wait" then local t = {}; for b in s[1]:gmatch("[^+]+") do t[b] = true end; L.press(t) end
  left = left - 1
  if left <= 0 then si = si + 1; left = nil end
  return false
end
local function pos()
  if rd(0x7E00BE) & 0x80 ~= 0 then return string.format("cell %d,%d", rd(0x7E3020), rd(0x7E3080)) end
  return string.format("field %d,%d", rd16(0x7E00B6), rd16(0x7E00B8))
end
local function finish()
  local t = {}
  for i = 0, 0x1F do t[#t + 1] = string.format("%02X", rd(0x7E2190 + i)) end
  log[#log + 1] = string.format("f%05d end map %02X/%02X %s BE=%02X 1949=%02X", n, rd(0x7E00BC), rd(0x7E00BD), pos(), rd(0x7E00BE), rd(0x7E1949))
  log[#log + 1] = "flags 7E2190: " .. table.concat(t, " ")
  L.write("warp.txt", table.concat(log, "\n") .. "\n")
  L.shot("end.png")
  emu.stop(0)
end

local function applySets(list)
  for _, s in ipairs(list) do
    local v = rd(s[1])
    if s[2] == "=" then v = s[3] elseif s[2] == "|" then v = v | s[3] else v = v & s[3] end
    emu.write(s[1], v, m)
  end
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
  if n == 2 then
    buildParty()
    applySets(sets)
  end
  for _, p in ipairs(pokes) do emu.write(p[1], p[2], m) end
  L.release()
  if n < 2 then return end
  local x, y = rd(0x7E3020), rd(0x7E3080)
  local inField = rd(0x7E00BE) & 0x80 == 0
  if phase == "pre" then
    if play(route) then phase = "ladder"; si = 1 end
  elseif phase == "ladder" then
    local p = ladder[wi]
    if not p then
      L.press({up = true})
      if rd(0x7E00BC) ~= 0x17 then
        phase = "load"; arrived = n
        log[#log + 1] = string.format("f%05d left ship", n)
      end
    elseif x == p[1] and y == p[2] then
      wi = wi + 1
    else
      L.press({[(x < p[1] and "right") or (x > p[1] and "left") or (y < p[2] and "down") or "up"] = true})
    end
  elseif phase == "load" then
    -- 맵을 푸는 동안은 입력을 쉰다. 필드면 그 뒤 아래로 걸어 나간다.
    if n >= arrived + 90 then
      if field and not inField then
        L.press({down = true})
      else
        phase = "settle"; arrived = n
        applySets(latesets)
        log[#log + 1] = string.format("f%05d arrived map %02X/%02X %s", n, rd(0x7E00BC), rd(0x7E00BD), pos())
      end
    end
  elseif phase == "settle" then
    if n >= arrived + settle then
      if save then
        L.saveState(save)
        L.shot((save:gsub("%.mss$", ".png")))
        log[#log + 1] = string.format("f%05d saved %s at %s", n, save, pos())
      end
      phase = "test"; si = 1; left = nil; startPos = pos()
    end
  elseif phase == "test" then
    if play(test) then
      if #test > 0 then
        local now = pos()
        log[#log + 1] = string.format("f%05d test %s -> %s moved=%s", n, startPos, now, now ~= startPos and "yes" or "no")
      end
      finish()
    end
  end
  if n >= maxf then
    log[#log + 1] = string.format("f%05d timeout phase=%s", n, phase)
    finish()
  end
end, emu.eventType.endFrame)
