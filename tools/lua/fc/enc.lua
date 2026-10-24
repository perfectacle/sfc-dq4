-- 필드에서 걸어 전투를 여러 번 일으키고, 조우 루틴(뱅크 18)이 고른 무리를 enc.txt 에 적는다.
-- 시행마다 STATE 를 다시 불러 WAIT0 + 시행번호 × WAITSTEP 프레임 기다린 뒤 위아래로 걷는다(난수가 달라짐).
-- POS="A2,2B" 를 주면 기다린 직후 필드 좌표 $42/$43 에 한 번 써서 그 자리에서 걷는다(화면은 깨진다).
-- POKE1="62ED=90;..." 도 같은 때 한 번 쓴다(예: 걸음 시계를 밤으로).
-- 한 시행은 전투 무리가 정해지거나 LIMIT 프레임이 지나면 끝난다. TRIALS 번 하고 멈춘다.
-- TRIALS=60 으로는 enc.txt 가 안 나왔다(30 은 됨). 많이 돌릴 때는 WAIT0 을 바꿔 여러 번 나눠 돌린다.
-- enc.txt 줄:
--   chk  X Y 구역($07) 지형($7140) 걸음 시계($62ED) 전투 뒤 걸음($6E42, 18:$9CCC 에서 읽은 값) 조우율($0E) 난수(A)
--        18:$9D09 조우 판정. 난수 < 조우율 이면 전투
--   enc  시행 X Y 구역 지형 걸음 칸(Y) 무리 ID 4 개 ($6E45-48) 수 4 개 ($6E49-4C)   18:$A11A
--   none 시행                                                                   LIMIT 안에 전투 없음
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local L = require("lib")
local state = L.readFile(os.getenv("STATE"))
local trials = tonumber(os.getenv("TRIALS") or "10")
local wait0 = tonumber(os.getenv("WAIT0") or "1")
local waitstep = tonumber(os.getenv("WAITSTEP") or "7")
local limit = tonumber(os.getenv("LIMIT") or "3000")
local pos = os.getenv("POS")
local px, py
if pos then px, py = pos:match("(%x+),(%x+)"); px, py = tonumber(px, 16), tonumber(py, 16) end
local pokes = {}
for a, v in string.gmatch(os.getenv("POKE1") or "", "(%x+)=(%x+)") do pokes[#pokes + 1] = {tonumber(a, 16), tonumber(v, 16)} end
local log = {}
local function rd(a) return emu.read(a, L.mem) end
local trial, f, wait, done, slot, steps = 0, 0, 0, false, -1, 0

local function start()
  trial = trial + 1
  f, done, slot = 0, false, -1
  wait = wait0 + (trial - 1) * waitstep
  L.defer(function() emu.loadSavestate(state) end)
end

emu.addMemoryCallback(function(addr)
  if L.prgOffset(addr) ~= 0x61E0D then return end
  slot = emu.getState()["cpu.y"]
end, emu.callbackType.exec, 0x9E0D, 0x9E0D)
emu.addMemoryCallback(function(addr)
  if L.prgOffset(addr) == 0x61CCC then steps = rd(0x6E42) end
end, emu.callbackType.exec, 0x9CCC, 0x9CCC)
emu.addMemoryCallback(function(addr)
  if L.prgOffset(addr) ~= 0x61D09 then return end
  log[#log + 1] = string.format("chk %02X %02X %02X %02X %02X %02X %02X %02X", rd(0x42), rd(0x43), rd(0x07),
    rd(0x7140), rd(0x62ED), steps, rd(0x0E), emu.getState()["cpu.a"])
end, emu.callbackType.exec, 0x9D09, 0x9D09)
emu.addMemoryCallback(function(addr)
  if L.prgOffset(addr) ~= 0x6211A or done then return end
  local t = {string.format("enc %d %02X %02X %02X %02X %02X %d", trial, rd(0x42), rd(0x43), rd(0x07),
    rd(0x7140), rd(0x62ED), slot)}
  for a = 0x6E45, 0x6E4C do t[#t + 1] = string.format("%02X", rd(a)) end
  log[#log + 1] = table.concat(t, " ")
  done = true
end, emu.callbackType.exec, 0xA11A, 0xA11A)

start()
emu.addEventCallback(function()
  f = f + 1
  L.release()
  if f == wait then
    if px then emu.write(0x42, px, L.mem); emu.write(0x43, py, L.mem) end
    for _, p in ipairs(pokes) do emu.write(p[1], p[2], L.mem) end
  end
  if f > wait + 2 then
    local phase = (f - wait) % 64
    L.press(phase < 32 and {up = true} or {down = true})
  end
  if done or f > limit then
    if not done then log[#log + 1] = string.format("none %d", trial) end
    if trial >= trials then
      L.write("enc.txt", table.concat(log, "\n") .. "\n")
      emu.stop(0)
      return
    end
    start()
  end
end, emu.eventType.endFrame)
