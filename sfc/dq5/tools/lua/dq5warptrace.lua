-- DQ5: 같은 폴더의 dq5warp.lua 로 장면 이동과 TEST 입력을 돌리면서 기록을 남긴다. dq5warp.lua 의 환경 변수는 그대로 쓴다.
--   TRACE="0082AF,21B9B1"  PC 마다 프레임·A·X·Y 와 LOG 주소(16진, 16비트)의 값 → trace.txt
--   RWATCH="1000-1000"     WRAM 오프셋 범위(16진)를 읽는 PC 의 첫 프레임·횟수·값(뱅크 미러 모두) → rwatch.txt
--   WWATCH="0D16-0D16"     같은 범위에 쓰는 프레임·PC·값을 차례로(앞 300개) → wwatch.txt
--   WFROM                  RWATCH·WWATCH 를 이 프레임부터 센다(기본 0)
--   LATE="600:7E21C9=01;7E1A9C=05"  그 프레임에 한 번 쓴다(SET 과 달리 도착 뒤에 넣을 수 있다)
--   SHOTS="760,800"        그 프레임의 화면을 sNNNNN.png 로
-- 기록은 dq5warp.lua 가 warp.txt 를 쓸 때(끝날 때) 함께 쓴다.
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local L = require("lib")
local m = emu.memType.snesMemory
local f = 0

local log, extra = {}, {}
for a in string.gmatch(os.getenv("LOG") or "", "[^,]+") do extra[#extra + 1] = a end
for a in string.gmatch(os.getenv("TRACE") or "", "[^,]+") do
  emu.addMemoryCallback(function()
    local st = emu.getState()
    local t = {string.format("%d %s A=%04X X=%04X Y=%04X", f, a, st["cpu.a"], st["cpu.x"], st["cpu.y"])}
    for _, x in ipairs(extra) do t[#t + 1] = string.format("%s=%04X", x, emu.read16(tonumber(x, 16), m)) end
    log[#log + 1] = table.concat(t, " ")
  end, emu.callbackType.exec, tonumber(a, 16), tonumber(a, 16))
end

local wfrom = tonumber(os.getenv("WFROM") or "0")
local rseen, rorder = {}, {}
for a, b in string.gmatch(os.getenv("RWATCH") or "", "(%x+)-(%x+)") do
  emu.addMemoryCallback(function(addr, value)
    if f < wfrom then return end
    local st = emu.getState()
    -- addr 는 CPU 주소라 뱅크마다 다르다. WRAM 오프셋으로 모은다
    local key = string.format("%04X pc=%02X:%04X", addr & 0xFFFF, st["cpu.k"], st["cpu.pc"])
    if not rseen[key] then rseen[key] = {f, 0, value}; rorder[#rorder + 1] = key end
    rseen[key][2] = rseen[key][2] + 1
  end, emu.callbackType.read, tonumber(a, 16), tonumber(b, 16), emu.cpuType.snes, emu.memType.snesWorkRam)
end
local wlog = {}
for a, b in string.gmatch(os.getenv("WWATCH") or "", "(%x+)-(%x+)") do
  emu.addMemoryCallback(function(addr, value)
    if f < wfrom or #wlog >= 300 then return end
    local st = emu.getState()
    wlog[#wlog + 1] = string.format("%d %04X pc=%02X:%04X v=%02X", f, addr & 0xFFFF, st["cpu.k"], st["cpu.pc"], value)
  end, emu.callbackType.write, tonumber(a, 16), tonumber(b, 16), emu.cpuType.snes, emu.memType.snesWorkRam)
end

local shots = {}
for x in string.gmatch(os.getenv("SHOTS") or "", "%d+") do shots[tonumber(x)] = true end
local lateAt, late = nil, {}
local ls = os.getenv("LATE")
if ls and ls ~= "" then
  lateAt = tonumber(ls:match("^(%d+):"))
  for a, v in string.gmatch(ls:match(":(.*)$"), "(%x+)=(%x+)") do late[#late + 1] = {tonumber(a, 16), tonumber(v, 16)} end
end
emu.addEventCallback(function()
  f = f + 1
  if shots[f] then L.shot(string.format("s%05d.png", f)) end
  if f == lateAt then
    for _, p in ipairs(late) do emu.write(p[1], p[2], m) end
  end
end, emu.eventType.endFrame)

local write = L.write
L.write = function(name, s)
  if name == "warp.txt" then
    write("trace.txt", table.concat(log, "\n") .. "\n")
    local t = {}
    for _, k in ipairs(rorder) do
      local e = rseen[k]
      t[#t + 1] = string.format("%s first=%d n=%d v=%02X", k, e[1], e[2], e[3])
    end
    write("rwatch.txt", table.concat(t, "\n") .. "\n")
    write("wwatch.txt", table.concat(wlog, "\n") .. "\n")
  end
  return write(name, s)
end
local here = debug.getinfo(1, "S").source:match("^@(.*[/\\])") or "./"
dofile(here .. "dq5warp.lua")
