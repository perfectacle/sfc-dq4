-- DQ5 카지노 슬롯 화면 세이브스테이트(STATE)에서 위(코인 넣기)를 눌러 판을 이어 돌리고, 판마다 한 줄씩 NAME.txt 에 덧붙인다.
--   S 판 묶음 시작$1294×5 R r×5 F 판시작부터의프레임×5 P 배당합($1252, 표 값) T 마지막누름부터판시작까지프레임
-- 위를 세 번 누르면 3장(세 줄)을 걸고 바로 돈다. 누름 간격은 GAP(기본 4) + 0~JITTER 프레임(난수 SEED).
-- 첫 묶음 셋째 프레임에 슬롯 안 코인 7E:1216~1218 을 3000000 으로 채운다.
-- MesenCE testrunner 는 약 100초가 지나면 스스로 끝나므로, BUDGET 초(기본 75)가 지나면 판 사이(돌지 않고 버튼을 뗀 때)에
-- NAME.mss 와 NAME.prog(판 수·넣은 코인·받은 코인·묶음 수)를 남기고 멈춘다. 같은 명령을 다시 부르면 거기서 이어 가고,
-- SPINS 판을 채우면 END 줄과 NAME.done 을 남긴다. 세이브스테이트로 잇는 것이라 게임 진행은 끊지 않고 돌린 것과 같다.
-- RNGLOG=1 이면 릴마다 11:B6F6(JSR $BC26) 직전의 $1200~$120F 와 돌아온 r 을 NAME.rng 에 덧붙인다.
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local L = require("lib")
local name = os.getenv("NAME") or "slot"
local base = L.out .. "/" .. name
local k, cin, cout, chunk = 0, 0, 0, 0
local pf = io.open(base .. ".prog", "r")
if pf then k, cin, cout, chunk = pf:read("n", "n", "n", "n"); pf:close() end
local first = chunk == 0
L.loadState(first and os.getenv("STATE") or (base .. ".mss"))
local m = emu.memType.snesMemory
local spins = tonumber(os.getenv("SPINS") or "100")
local budget = tonumber(os.getenv("BUDGET") or "75")
local hold = tonumber(os.getenv("HOLD") or "2")
local gap = tonumber(os.getenv("GAP") or "4")
local jit = tonumber(os.getenv("JITTER") or "0")
local rnglog = os.getenv("RNGLOG") == "1"
math.randomseed(tonumber(os.getenv("SEED") or "1") * 1000 + chunk)
local t0wall = os.time()
local function rd(a) return emu.read(a, m) end
local function rd16(a) return rd(a) | rd(a + 1) << 8 end
local function coins() return rd16(0x7E1216) | rd(0x7E1218) << 16 end
local n, prev, busy, stopping = 0, nil, false, false
local starts, rs, rf, pay, t0, tp, lastp = {}, {}, {}, 0, 0, 0, 0
local out, rngline = {}, nil
local nextp, phase = 10, 0
emu.addMemoryCallback(function()
  for i = 0, 4 do starts[i + 1] = rd16(0x7E1294 + i * 2) end
  rs, rf, pay, t0, tp, busy = {}, {}, 0, n, lastp, true
end, emu.callbackType.exec, 0x11B673, 0x11B673)
if rnglog then
  emu.addMemoryCallback(function()
    local b = {}
    for i = 0, 15 do b[#b + 1] = string.format("%02X", rd(0x7E1200 + i)) end
    rngline = table.concat(b)
  end, emu.callbackType.exec, 0x11B6F6, 0x11B6F6)
end
emu.addMemoryCallback(function()
  local s = emu.getState()
  local i = (s["cpu.x"] // 2) + 1
  rs[i] = s["cpu.a"] & 0xFF; rf[i] = n - t0
  if rnglog then
    local f = io.open(base .. ".rng", "a"); f:write(string.format("%d %s %d\n", i - 1, rngline, rs[i])); f:close()
  end
end, emu.callbackType.exec, 0x11B6F9, 0x11B6F9)
emu.addMemoryCallback(function()
  pay = rd16(0x7E1252) | rd(0x7E1254) << 16
end, emu.callbackType.exec, 0x11B39F, 0x11B39F)
emu.addMemoryCallback(function()
  if #rs == 5 then
    k = k + 1
    out[#out + 1] = string.format("S %d %d %s R %s F %s P %d T %d", k, chunk, table.concat(starts, ","),
      table.concat(rs, ","), table.concat(rf, ","), pay, t0 - tp)
  end
  rs, busy = {}, false
end, emu.callbackType.exec, 0x11B415, 0x11B415)
local function finish(done)
  local f = io.open(base .. ".txt", "a")
  if #out > 0 then f:write(table.concat(out, "\n") .. "\n") end
  if done then
    f:write(string.format("END spins=%d machine=%d in=%d out=%d coins=%d chunks=%d\n", k, rd(0x7E1F57), cin, cout, coins(), chunk + 1))
  end
  f:close()
  local p = io.open(base .. ".prog", "w"); p:write(string.format("%d %d %d %d\n", k, cin, cout, chunk + 1)); p:close()
  if done then local d = io.open(base .. ".done", "w"); d:write("1\n"); d:close() end
  emu.stop(0)
end
emu.addEventCallback(function()
  if stopping then return end
  n = n + 1
  if first and n == 3 then emu.write(0x7E1216, 0xC0, m); emu.write(0x7E1217, 0xC6, m); emu.write(0x7E1218, 0x2D, m) end
  if n > 3 or not first then
    local c = coins()
    if prev then
      if c < prev then cin = cin + prev - c elseif c > prev then cout = cout + c - prev end
    end
    prev = c
  end
  if k >= spins then stopping = true; finish(true); return end
  if os.time() - t0wall >= budget and not busy and phase == 0 then
    stopping = true
    L.defer(function() L.write(name .. ".mss", emu.createSavestate()); finish(false) end)
    return
  end
  if n >= nextp then
    if phase == 0 then L.press({up = true}); phase = 1; lastp = n; nextp = n + hold
    else L.release(); phase = 0; nextp = n + gap + (jit > 0 and math.random(0, jit) or 0) end
  end
end, emu.eventType.endFrame)
