-- 세이브스테이트에서 시작해 원하는 장소로 옮긴 뒤 조작 가능한 상태를 세이브스테이트로 남긴다.
-- 게임의 정상 진입 루틴을 그대로 타게 한다:
--   맵: 주인공 둘레 네 칸을 목적지로 가는 출구로 출구 표 $05A0 에 넣고 KEY 로 한 걸음 걷는다.
--       1B:$8014(출구 검사) → 1B:$8024(장소 쓰기) → BRK 1E 함수 1E(1E:$8ED6, 맵 진입).
--   필드: 걸음 뒤 맵 밖 검사(1E:$9155)에서 폭 $3F 를 잠깐 0 으로 해 「맵 가장자리로 나감」을 타게 하고,
--       필드 위치를 정하는 08:$B06A 가 $42/$43 을 쓴 직후(08:$B09B) $65/$42/$43 을 목적지로 바꾼다.
-- 출발 STATE 는 맵 안에서 KEY 쪽으로 한 칸 걸을 수 있는 상태여야 한다(기본 dq4-ch1-throne.mss, 아래로).
-- 환경 변수(16진):
--   MAP=GG/KK X=XX Y=YY [DIR=0..3]   맵 장소(그룹 $63/순번 $64)와 도착 좌표 $44/$45, 도착 방향(0 위 1 오른쪽 2 아래 3 왼쪽)
--   FIELD=F X=XX Y=YY                 필드 번호 $65 와 필드 좌표 $42/$43
--   SET="6157=1027;62AA=08"           출발 전 한 번 쓸 CPU 주소=바이트들(이어 쓰기). 플래그·골드·능력치 등
--   AFTER="..."                       도착 뒤 한 번 쓸 것(SET 과 같은 꼴)
--   KEY=down                          걸을 방향, WAIT=120 도착 뒤 기다릴 프레임
--   SEQ="up:16,a:6,..."               도착 뒤 이어서 줄 입력(seq.lua 와 같은 꼴), TAIL=60 그 뒤 프레임
--   STATE_OUT=warp.mss                SHOT_DIR 에 쓸 세이브스테이트 이름. 같은 이름 .png 와 warp.txt 를 같이 쓴다
-- 끝나면 seq.lua 처럼 end.png/end.mss/end.ram 등을 덤프하고 멈춘다. 다른 프로브의 DRIVER 로도 쓸 수 있고,
-- 그때는 프로브의 MAXF 까지 기다렸다 멈춘다. 진입 루틴이 돌지 않으면 warp.txt 에 「실패」를 쓰고 멈춘다.
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local L = require("lib")
local mem = L.mem
local function hex(s) return s and tonumber(s, 16) end
local function rd(a) return emu.read(a, mem) end
local function wr(a, v) emu.write(a, v, mem) end
local function pokes(spec)
  for a, bytes in string.gmatch(spec or "", "(%x+)=(%x+)") do
    local addr = tonumber(a, 16)
    for i = 1, #bytes - 1, 2 do wr(addr + (i - 1) // 2, tonumber(bytes:sub(i, i + 1), 16)) end
  end
end

local mapG, mapK
if os.getenv("MAP") then mapG, mapK = os.getenv("MAP"):match("(%x+)/(%x+)"); mapG, mapK = hex(mapG), hex(mapK) end
local field = hex(os.getenv("FIELD"))
local tx, ty = hex(os.getenv("X")), hex(os.getenv("Y"))
assert((mapG or field) and tx and ty, "MAP=GG/KK 또는 FIELD=F 와 X, Y 가 필요합니다")
local dir = hex(os.getenv("DIR")) or 2
local key = os.getenv("KEY") or "down"
local waitF = tonumber(os.getenv("WAIT") or "120")
local tail = tonumber(os.getenv("TAIL") or "60")
local out = os.getenv("STATE_OUT") or "warp.mss"
-- 프로브가 MAXF - 1 에 결과를 쓰므로 DRIVER 로 쓸 때는 MAXF 까지 멈추지 않는다
local maxf = tonumber(os.getenv("MAXF") or "0")
local steps = {}
for tok in string.gmatch(os.getenv("SEQ") or "", "[^,]+") do
  local b, f = tok:match("([%w+]+):(%d+)")
  steps[#steps + 1] = {b, tonumber(f)}
end

L.loadState(os.getenv("STATE") or (os.getenv("PWD") .. "/work/state/dq4-ch1-throne.mss"))

-- 필드 쪽 갈고리. armed 동안만 값을 바꾼다.
local armed, savedW, entered = false, nil, nil
local function bank() return rd(0x0507) end
emu.addMemoryCallback(function()
  if armed and field and bank() == 0x1E then savedW = rd(0x3F); wr(0x3F, 0) end
end, emu.callbackType.exec, 0x9155, 0x9155)
emu.addMemoryCallback(function()
  if savedW and bank() == 0x1E then wr(0x3F, savedW); savedW = nil end
end, emu.callbackType.exec, 0x9166, 0x9166)
emu.addMemoryCallback(function()
  if armed and field and bank() == 0x08 then
    wr(0x65, field); wr(0x42, tx); wr(0x43, ty); armed = false; entered = "field"
  end
end, emu.callbackType.exec, 0xB09B, 0xB09B)
emu.addMemoryCallback(function()
  if armed and mapG and bank() == 0x1B then armed = false; entered = "map" end
end, emu.callbackType.exec, 0x8024, 0x8024)

local function injectExits()
  local px, py = rd(0x6F60), rd(0x6F80)
  local nb = {{px, py - 1}, {px + 1, py}, {px, py + 1}, {px - 1, py}}
  for i, p in ipairs(nb) do
    local b = 0x05A0 + (i - 1) * 7
    wr(b, p[1] & 0xFF); wr(b + 1, p[2] & 0xFF); wr(b + 2, mapG); wr(b + 3, mapK)
    wr(b + 4, tx); wr(b + 5, ty); wr(b + 6, 0x80 | (dir & 3))
  end
  wr(0x05A0 + 4 * 7, 0xFF)
end

local function report(tag)
  local t = {tag}
  for _, v in ipairs({{"63", 0x63}, {"64", 0x64}, {"65", 0x65}, {"42", 0x42}, {"43", 0x43},
                      {"44", 0x44}, {"45", 0x45}, {"28", 0x28}}) do
    t[#t + 1] = string.format("%s=%02X", v[1], rd(v[2]))
  end
  return table.concat(t, " ")
end

local n, phase, mark, i, left, log = 0, "start", 0, 1, nil, {}
emu.addEventCallback(function()
  n = n + 1
  if n < 4 then return end
  L.release()
  if phase == "start" then
    log[#log + 1] = report(string.format("f%d 출발", n))
    pokes(os.getenv("SET"))
    if mapG then injectExits() end
    armed = true; phase = "walk"; mark = n
  elseif phase == "walk" then
    if entered then phase = "settle"; mark = n
    elseif n - mark < 16 then L.press({[key] = true})
    elseif n - mark > 240 then
      log[#log + 1] = report(string.format("f%d 실패: 진입 루틴이 돌지 않음", n))
      L.write("warp.txt", table.concat(log, "\n") .. "\n"); emu.stop(1)
    end
  elseif phase == "settle" then
    if n - mark >= waitF then
      pokes(os.getenv("AFTER"))
      log[#log + 1] = report(string.format("f%d 도착(%s)", n, entered))
      L.write("warp.txt", table.concat(log, "\n") .. "\n")
      L.shot((out:gsub("%.mss$", "")) .. ".png"); L.saveState(out)
      phase = "seq"
    end
  elseif phase == "seq" then
    if i <= #steps then
      local s = steps[i]
      if left == nil then left = s[2] end
      if s[1] ~= "wait" then
        local t = {}
        for b in s[1]:gmatch("[^+]+") do t[b] = true end
        L.press(t)
      end
      left = left - 1
      if left <= 0 then i = i + 1; left = nil end
    else phase = "tail"; mark = n end
  elseif phase == "tail" then
    if n - mark == tail then
      log[#log + 1] = report(string.format("f%d 끝", n))
      L.write("warp.txt", table.concat(log, "\n") .. "\n")
      L.shot("end.png"); L.saveState("end.mss"); L.dumpAll("end")
    elseif n - mark >= tail + 5 and n >= maxf then emu.stop(0) end
  end
end, emu.eventType.endFrame)
