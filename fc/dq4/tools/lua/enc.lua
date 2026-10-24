-- 필드·맵 안에서 걸어 전투를 여러 번 일으키고, 조우 루틴(뱅크 18)이 고른 무리를 enc.txt 에 적는다.
-- 시행마다 STATE 를 다시 불러 WAIT0 + 시행번호 × WAITSTEP 프레임 기다린 뒤 걷는다(난수가 달라짐).
-- POS="A2,2B" 를 주면 기다린 직후 필드 좌표 $42/$43 에 한 번 써서 그 자리에서 걷는다(화면은 깨진다).
-- POKE1="62ED=90;..." 도 같은 때 한 번 쓴다(예: 걸음 시계를 밤으로).
-- WALK=updown(기본)은 위아래 32프레임씩, WALK=random 은 시행마다 다른 순서로 네 방향을 STEPF(기본 16)프레임씩 걷는다
-- (맵 안에서 벽에 막혀도 다른 방향으로 걸음이 나게).
-- FORCE44=NN 이면 18:$A123(무리를 정한 뒤 음악을 고르기 전)에서 $6E44 를 NN 으로 바꾼다.
-- BOSS=NN 이면 18:$9D0E(보통 무리 고르기)를 메모리상 PRG 에서 LDA #NN ; JSR $A1AD ; RTS 로 덮어
-- 걸어서 난 전투를 특수 전투 NN 으로 바꾼다(롬 파일은 그대로).
-- CONT=N 이면 무리가 정해진 뒤 N 프레임 더 돌며 A 를 눌러 메시지 번호(16:$8656 의 X:A)를 적는다.
-- SHOT=1 이면 시행이 끝날 때 화면을 tNN.png 로 남긴다.
-- 한 시행은 무리가 정해지고 CONT 프레임이 지나거나 LIMIT 프레임이 지나면 끝난다. TRIALS 번 하고 멈춘다.
-- enc.txt 는 시행마다 다시 쓴다(한 번에 많이 돌리다 멈춰도 그때까지 기록이 남게).
-- enc.txt 줄:
--   stp  $41 $63 $64 $44 $45 $6E05                          18:$9BE6 걸음마다 조우 루틴에 들어옴
--   shp  X Y 지도 값(A) $07                                   18:$9C81 배($0515=1)일 때 구역 대신 $07 을 읽는 곳
--   chk  X Y 구역($07) 지형($7140) 걸음 시계($62ED) 전투 뒤 걸음($6E42, 18:$9CCC 에서 읽은 값) 조우율($0E) 난수(A)
--        $41 $63 $64 $615A $0515 $6BEB(18:$9CF6 에서 줄이기 전) $6E41 $44 $45 $65 $62D5
--        18:$9D09 조우 판정. 난수 < 조우율 이면 전투
--   enc  시행 X Y 구역 지형 걸음 칸(Y) 무리 ID 4 개 ($6E45-48) 수 4 개 ($6E49-4C)
--        $41 $63 $64 $615A $0515 $6E01 $44 $45 $65        18:$A11A
--   c55  $44 $45 난수(A) $627D                              18:$9FAA 맵 안 $627D bit4 판정. 난수 < 55 면 전투
--   e44  시행 $6E44 $0B(구역 레코드 바이트 0)                 18:$A123
--   boss 시행 번호 무리 ID 4 개 수 4 개 $6E44                18:$A207
--   msg  시행 프레임 번호                                   16:$8656
--   none 시행                                               LIMIT 안에 전투 없음
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local L = require("lib")
local state = L.readFile(os.getenv("STATE"))
local trials = tonumber(os.getenv("TRIALS") or "10")
local wait0 = tonumber(os.getenv("WAIT0") or "1")
local waitstep = tonumber(os.getenv("WAITSTEP") or "7")
local limit = tonumber(os.getenv("LIMIT") or "3000")
local walk = os.getenv("WALK") or "updown"
local stepf = tonumber(os.getenv("STEPF") or "16")
local cont = tonumber(os.getenv("CONT") or "0")
local force44 = os.getenv("FORCE44") and tonumber(os.getenv("FORCE44"), 16)
local boss = os.getenv("BOSS") and tonumber(os.getenv("BOSS"), 16)
local pos = os.getenv("POS")
local px, py
if pos then px, py = pos:match("(%x+),(%x+)"); px, py = tonumber(px, 16), tonumber(py, 16) end
local pokes = {}
for a, v in string.gmatch(os.getenv("POKE1") or "", "(%x+)=(%x+)") do pokes[#pokes + 1] = {tonumber(a, 16), tonumber(v, 16)} end
local log = {}
local function rd(a) return emu.read(a, L.mem) end
local function hx(list)
  local t = {}
  for _, a in ipairs(list) do t[#t + 1] = string.format("%02X", rd(a)) end
  return table.concat(t, " ")
end
local trial, f, wait, done, slot, steps, doneAt, bbPre = 0, 0, 0, false, -1, 0, 0, 0
local seed, dirs = 0, {"up", "right", "down", "left"}

if boss then
  -- 18:$9D0E = PRG 61D0E. $A1AD 끝의 PLA PLA 가 이 JSR 의 복귀 주소를 버리고
  -- RTS 가 함수 00 을 부른 곳으로 돌아간다(이벤트 스크립트의 BRK 01 8F 와 같은 끝맺음)
  local code = {0xA9, boss, 0x20, 0xAD, 0xA1, 0x60}
  for i, b in ipairs(code) do emu.write(0x61D0E + i - 1, b, emu.memType.nesPrgRom) end
end

local function start()
  trial = trial + 1
  f, done, slot, doneAt = 0, false, -1, 0
  wait = wait0 + (trial - 1) * waitstep
  seed = trial * 7919 + wait0
  L.defer(function() emu.loadSavestate(state) end)
end

local function hook(off, fn)
  local cpu = 0x8000 + off % 0x4000
  emu.addMemoryCallback(function(addr) if L.prgOffset(addr) == off then fn() end end, emu.callbackType.exec, cpu, cpu)
end

hook(0x61BE6, function()
  log[#log + 1] = string.format("stp %02X %02X %02X %02X %02X %02X", rd(0x41), rd(0x63), rd(0x64), rd(0x44), rd(0x45), rd(0x6E05))
end)
hook(0x61C81, function()
  log[#log + 1] = string.format("shp %02X %02X %02X %02X", rd(0x42), rd(0x43), emu.getState()["cpu.a"], rd(0x07))
end)
hook(0x61E0D, function() slot = emu.getState()["cpu.y"] end)
hook(0x61CCC, function() steps = rd(0x6E42) end)
hook(0x61CF6, function() bbPre = rd(0x6BEB) end)
hook(0x61D09, function()
  log[#log + 1] = string.format("chk %02X %02X %02X %02X %02X %02X %02X %02X ", rd(0x42), rd(0x43), rd(0x07),
    rd(0x7140), rd(0x62ED), steps, rd(0x0E), emu.getState()["cpu.a"])
    .. hx({0x41, 0x63, 0x64, 0x615A, 0x0515}) .. string.format(" %02X ", bbPre)
    .. hx({0x6E41, 0x44, 0x45, 0x65, 0x62D5})
end)
hook(0x61FAA, function()
  log[#log + 1] = string.format("c55 %02X %02X %02X %02X", rd(0x44), rd(0x45), emu.getState()["cpu.a"], rd(0x627D))
end)
hook(0x6211A, function()
  if done then return end
  log[#log + 1] = string.format("enc %d %02X %02X %02X %02X %02X %d ", trial, rd(0x42), rd(0x43), rd(0x07),
    rd(0x7140), rd(0x62ED), slot) .. hx({0x6E45, 0x6E46, 0x6E47, 0x6E48, 0x6E49, 0x6E4A, 0x6E4B, 0x6E4C})
    .. " " .. hx({0x41, 0x63, 0x64, 0x615A, 0x0515, 0x6E01, 0x44, 0x45, 0x65})
  done = true; doneAt = f
end)
hook(0x62123, function()
  if force44 then emu.write(0x6E44, force44, L.mem) end
  log[#log + 1] = string.format("e44 %d %02X %02X", trial, rd(0x6E44), rd(0x0B))
end)
hook(0x62207, function()
  log[#log + 1] = string.format("boss %d %02X ", trial, boss or 0xFF)
    .. hx({0x6E45, 0x6E46, 0x6E47, 0x6E48, 0x6E49, 0x6E4A, 0x6E4B, 0x6E4C, 0x6E44})
  if not done then done = true; doneAt = f end
end)
hook(0x58656, function()
  local st = emu.getState()
  log[#log + 1] = string.format("msg %d %d %02X%02X", trial, f, st["cpu.x"], st["cpu.a"])
end)

start()
emu.addEventCallback(function()
  f = f + 1
  L.release()
  if f == wait then
    if px then emu.write(0x42, px, L.mem); emu.write(0x43, py, L.mem) end
    for _, p in ipairs(pokes) do emu.write(p[1], p[2], L.mem) end
  end
  if done then
    if f - doneAt < cont and f % 16 < 4 then L.press({a = true}) end
  elseif f > wait + 2 then
    if walk == "random" then
      local k = (f - wait) // stepf
      L.press({[dirs[((k * 2654435761 + seed * 40503) >> 13) % 4 + 1]] = true})
    else
      L.press((f - wait) % 64 < 32 and {up = true} or {down = true})
    end
  end
  if (done and f - doneAt >= cont) or f > limit then
    if not done then log[#log + 1] = string.format("none %d", trial) end
    if os.getenv("SHOT") then L.shot(string.format("t%02d.png", trial)) end
    L.write("enc.txt", table.concat(log, "\n") .. "\n")
    if trial >= trials then
      emu.stop(0)
      return
    end
    start()
  end
end, emu.eventType.endFrame)
