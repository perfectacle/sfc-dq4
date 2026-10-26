-- DQ5: 세이브스테이트 STATE 에서 SEQ 입력(wait:40,a:4,up+b:3,…)을 재생하며 기록한다. 드라이버 없이 혼자 돈다.
-- WR="7E36EB=4D;…" 는 처음 WRN(기본 3) 프레임 동안 매 프레임 쓴다.
-- HOOK="248BAF,…" 실행 때 프레임·A·X·Y·S 와 스택 24바이트, WLOG="이름=7E2199;…" 값이 바뀐 프레임을 trc.txt 에.
-- LO·HI(16진)가 있으면 FROM~TO 프레임 동안 그 범위의 실행을 순서대로(CAP 줄까지) trc.txt 에, 커버리지를 cover.txt 에.
-- SAVEAT 프레임에 세이브스테이트 SAVE 와 save.png, SHOTS="300,600" 프레임에 sNNN.png.
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local L = require("lib")
L.loadState(os.getenv("STATE"))
local m = emu.memType.snesMemory
local wr = {}
for a, v in string.gmatch(os.getenv("WR") or "", "(%x+)=(%x+)") do wr[#wr + 1] = {tonumber(a, 16), tonumber(v, 16)} end
local wrn = tonumber(os.getenv("WRN") or "3")
local steps = {}
for tok in string.gmatch(os.getenv("SEQ") or "", "[^,]+") do
  local b, f = tok:match("([%w+]+):(%d+)")
  steps[#steps + 1] = {b, tonumber(f)}
end
local maxf = tonumber(os.getenv("MAXF") or "600")
local lo, hi = tonumber(os.getenv("LO") or "", 16), tonumber(os.getenv("HI") or "", 16)
local from, to = tonumber(os.getenv("FROM") or "1"), tonumber(os.getenv("TO") or "0")
local cap = tonumber(os.getenv("CAP") or "20000")
local saveat = tonumber(os.getenv("SAVEAT") or "-1")
local shots = {}
for f in string.gmatch(os.getenv("SHOTS") or "", "%d+") do shots[tonumber(f)] = true end
local out, cov, n, i, left, cb = {}, {}, 0, 1, nil, nil

local function onExec(addr)
  local s = emu.getState()
  local p = s["cpu.ps"]
  local k = addr * 256 + (p & 0x30)
  cov[k] = (cov[k] or 0) + 1
  if #out < cap then
    out[#out + 1] = string.format("f%d %06X A=%04X X=%04X Y=%04X P=%02X S=%04X D=%04X DB=%02X", n, addr,
      s["cpu.a"], s["cpu.x"], s["cpu.y"], p, s["cpu.sp"], s["cpu.d"], s["cpu.dbr"])
  end
end

for a in string.gmatch(os.getenv("HOOK") or "", "%x+") do
  emu.addMemoryCallback(function()
    local s = emu.getState()
    local st = {}
    for k = 1, 24 do st[#st + 1] = string.format("%02X", emu.read(s["cpu.sp"] + k, m)) end
    out[#out + 1] = string.format("f%d hook %s A=%04X X=%04X Y=%04X S=%04X stk=%s", n, a,
      s["cpu.a"], s["cpu.x"], s["cpu.y"], s["cpu.sp"], table.concat(st, " "))
  end, emu.callbackType.exec, tonumber(a, 16), tonumber(a, 16))
end

local wl, last = {}, {}
for name, a in string.gmatch(os.getenv("WLOG") or "", "([%w_]+)=(%x+)") do wl[#wl + 1] = {name, tonumber(a, 16)} end

local function flush()
  L.write("trc.txt", table.concat(out, "\n") .. "\n")
end

emu.addEventCallback(function()
  n = n + 1
  local ch = {}
  for _, e in ipairs(wl) do
    local v = emu.read(e[2], m)
    if last[e[1]] ~= v then last[e[1]] = v; ch[#ch + 1] = string.format("%s=%02X", e[1], v) end
  end
  if #ch > 0 then out[#out + 1] = string.format("f%d %s", n, table.concat(ch, " ")) end
  if n <= wrn then for _, e in ipairs(wr) do emu.write(e[1], e[2], m) end end
  if lo and hi then
    if n == from then cb = emu.addMemoryCallback(onExec, emu.callbackType.exec, lo, hi) end
    if n == to and cb then emu.removeMemoryCallback(cb, emu.callbackType.exec, lo, hi); cb = nil end
  end
  L.release()
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
  end
  if n == saveat then L.saveState(os.getenv("SAVE") or "save.mss"); L.shot("save.png") end
  if shots[n] then L.shot("s" .. n .. ".png") end
  -- 테스트 러너가 오래 돌다 끊기면 끝 기록이 없으므로 중간에도 쓴다. 긴 장면은 SAVEAT 으로 나눠 잇는다.
  if n % 2000 == 0 then flush() end
  if n == maxf then
    L.shot("end.png")
    flush()
    if lo and hi then
      local t = {}
      for k, c in pairs(cov) do t[#t + 1] = string.format("%06X %02X %d", k // 256, k % 256, c) end
      table.sort(t)
      L.write("cover.txt", table.concat(t, "\n") .. "\n")
    end
    emu.stop(0)
  end
end, emu.eventType.endFrame)
