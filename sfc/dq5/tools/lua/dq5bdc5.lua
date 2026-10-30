-- 지형 루틴 03:CB1B 와 그 안의 블록 번호 루틴 00:BDC5 를 누가 몇 번 부르는지와 그 시간을 잰다. 00:BDC5 는 03:CB1B
-- (JSL $00BDC1)로만 들어오므로 03:CB1B 에 들어올 때 스택의 돌아갈 자리로 부른 곳(JSL 자리)을 정하고, 03:CB1B 에서 돌아갈
-- 자리까지와 00:BDC5 에서 00:BE16(RTS) 까지의 마스터 클록(emu.getState() 의 masterClock)을 부른 곳마다 더한다.
-- FROM~UNTIL 프레임에는 화면 버퍼(emu.getScreenBuffer)의 해시를 프레임마다 적어, 같은 입력의 두 롬이 몇 프레임째부터
-- 어긋나는지 견줄 수 있게 한다. 드라이버(boot.lua, 보통 dq5warp.lua) 앞에 붙여 쓰고, MesenCE 인자에
-- --Snes.DisableFrameSkipping=true 를 준다.
-- EXEC 의 PC(16진, 쉼표로)는 실행 횟수와 처음·마지막 프레임을, 03:CB07(세계 지도 화면의 점 하나)에서는 넘겨받는 $CE·$D0 의
-- 가장 큰 값을 적는다. SHOTS 의 프레임에는 화면(fNNNNN.png)을 남긴다.
-- 결과: SHOT_DIR/bdc5.txt 「부른곳 03:CB1B횟수 03:CB1B클록합 00:BDC5횟수 첫프레임 끝프레임 00:BDC5클록합 프레임목록(앞 40개)」,
-- 「exec PC 횟수 첫프레임 끝프레임」, 「dot 횟수 최대CE 최대D0」, hash.txt 「프레임 해시 $1001 $BC/$BD」
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local L = require("lib")
local m = emu.memType.snesMemory
local from, upto = tonumber(os.getenv("FROM") or "0"), tonumber(os.getenv("UNTIL") or "0")
local every = tonumber(os.getenv("EVERY") or "100")
-- 롬에서 JSL $03CB1B 는 이 넷뿐이다. 돌아갈 자리는 JSL + 4.
local RETURNS = {0x0181DA, 0x0184E4, 0x01BE92, 0x03CB15}
local n, caller, start, land = 0, nil, nil, nil
local calls, order, hashes = {}, {}, {}
local shots = {}
for a in string.gmatch(os.getenv("SHOTS") or "", "%d+") do shots[tonumber(a)] = true end
local execs, dot = {}, {count = 0, ce = 0, d0 = 0}

local function report()
  local t = {}
  for _, k in ipairs(order) do
    local c = calls[k]
    t[#t + 1] = string.format("%06X %d %d %d %d %d %d %s", k, c.lands, c.landsum, c.count, c.first, c.last, c.sum,
      table.concat(c.frames, ","))
  end
  for _, e in ipairs(execs) do
    t[#t + 1] = string.format("exec %06X %d %d %d", e.pc, e.count, e.first or -1, e.last or -1)
  end
  t[#t + 1] = string.format("dot %d %04X %04X", dot.count, dot.ce, dot.d0)
  L.write("bdc5.txt", table.concat(t, "\n") .. "\n")
  L.write("hash.txt", table.concat(hashes, "\n") .. "\n")
end

for a in string.gmatch(os.getenv("EXEC") or "", "%x+") do
  local e = {pc = tonumber(a, 16), count = 0}
  execs[#execs + 1] = e
  emu.addMemoryCallback(function()
    e.count, e.first, e.last = e.count + 1, e.first or n, n
  end, emu.callbackType.exec, e.pc, e.pc)
end
emu.addMemoryCallback(function()
  dot.count = dot.count + 1
  dot.ce, dot.d0 = math.max(dot.ce, emu.read16(0x7E00CE, m)), math.max(dot.d0, emu.read16(0x7E00D0, m))
end, emu.callbackType.exec, 0x03CB07, 0x03CB07)
local function entry(k)
  local c = calls[k]
  if not c then
    c = {count = 0, sum = 0, lands = 0, landsum = 0, first = n, last = n, frames = {}}
    calls[k] = c
    order[#order + 1] = k
  end
  return c
end
emu.addMemoryCallback(function()
  local s = emu.getState()
  local sp = s["cpu.sp"]
  caller = (emu.read(sp + 3, m) << 16 | emu.read(sp + 2, m) << 8 | emu.read(sp + 1, m)) - 3
  land = s["masterClock"]
end, emu.callbackType.exec, 0x03CB1B, 0x03CB1B)
for _, pc in ipairs(RETURNS) do
  emu.addMemoryCallback(function()
    if land and caller == pc - 4 then
      local c = entry(caller)
      c.lands, c.landsum, c.last = c.lands + 1, c.landsum + emu.getState()["masterClock"] - land, n
      if #c.frames < 40 and c.frames[#c.frames] ~= n then c.frames[#c.frames + 1] = n end
      land, caller = nil, nil
    end
  end, emu.callbackType.exec, pc, pc)
end
emu.addMemoryCallback(function()
  start = emu.getState()["masterClock"]
end, emu.callbackType.exec, 0x00BDC5, 0x00BDC5)
emu.addMemoryCallback(function()
  if not start then return end
  local c = entry(caller or 0)
  c.count, c.sum = c.count + 1, c.sum + emu.getState()["masterClock"] - start
  start = nil
end, emu.callbackType.exec, 0x00BE16, 0x00BE16)

emu.addEventCallback(function()
  n = n + 1
  if n >= from and n <= upto then
    local b, h = emu.getScreenBuffer(), 0
    for i = 1, #b do h = (h * 31 + b[i]) & 0xFFFFFFFF end
    hashes[#hashes + 1] = string.format("%d %08X %02X %02X/%02X", n, h, emu.read(0x7E1001, m), emu.read(0x7E00BC, m),
      emu.read(0x7E00BD, m))
  end
  if shots[n] then L.shot(string.format("f%05d.png", n)) end
  if n % every == 0 then report() end
end, emu.eventType.endFrame)
dofile(os.getenv("LIBDIR") .. "/boot.lua")
