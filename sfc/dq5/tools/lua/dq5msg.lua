-- DQ5 메시지·대화 실험 드라이버. STATE 세이브스테이트를 불러 ROMPATCH(파일 오프셋=바이트)·SET(첫 프레임에 한 번,
-- 7E 뱅크 주소 =값 |OR &AND)·POKE(매 프레임 고정, CPU 주소=값)를 걸고 PRE 입력(walk.lua 와 같은 "a:4,wait:30" 꼴)을 재생한다.
--   CALLS="248BAF,2481A4"   그 PC 를 지날 때 프레임·A·X·Y(와 LOG 에 적은 주소의 16비트 값)를 기록
--   WW="0000F5,7E31EB"      그 주소에 쓸 때 프레임·값·PC 를 기록
--   WWRANGE="7E3000-7E37FF:1F=0B"  범위 안에서 (주소 & 마스크) = 값 인 곳(인물 표의 한 슬롯)에 쓸 때 기록
--   SHOTS="300,400"         그 프레임 화면을 sNNNNN.png 로
--   DUMP="300:7E2000:64"    그 프레임에 메모리(CPU 주소부터 길이)를 16진으로 기록
-- STATE 가 없으면 전원을 켠 상태에서 시작한다. MAXF 프레임에 SHOT_DIR/msg.txt 와 end.png 를 쓰고 멈춘다.
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local L = require("lib")
if os.getenv("STATE") then L.loadState(os.getenv("STATE")) end
local m = emu.memType.snesMemory
local seq = {}
for tok in string.gmatch(os.getenv("PRE") or "", "[^,]+") do
  local b, f = tok:match("([%w+]+):(%d+)")
  seq[#seq + 1] = {b, tonumber(f)}
end
local patches, sets, pokes, shots, dumps, extra = {}, {}, {}, {}, {}, {}
for off, hex in string.gmatch(os.getenv("ROMPATCH") or "", "(%x+)=(%x+)") do patches[#patches + 1] = {tonumber(off, 16), hex} end
for a, op, v in string.gmatch(os.getenv("SET") or "", "(%x+)([=|&])(%x+)") do sets[#sets + 1] = {tonumber(a, 16), op, tonumber(v, 16)} end
for a, v in string.gmatch(os.getenv("POKE") or "", "(%x+)=(%x+)") do pokes[#pokes + 1] = {tonumber(a, 16), tonumber(v, 16)} end
for a in string.gmatch(os.getenv("SHOTS") or "", "%d+") do shots[tonumber(a)] = true end
for fr, a, len in string.gmatch(os.getenv("DUMP") or "", "(%d+):(%x+):(%d+)") do dumps[#dumps + 1] = {tonumber(fr), tonumber(a, 16), tonumber(len)} end
for a in string.gmatch(os.getenv("LOG") or "", "[^,]+") do extra[#extra + 1] = a end
local log, n, si, left = {}, 0, 1, nil
for a in string.gmatch(os.getenv("CALLS") or "", "[^,]+") do
  local addr = tonumber(a, 16)
  emu.addMemoryCallback(function()
    if #log > 20000 then return end
    local s = emu.getState()
    local t = {string.format("%d %06X A=%04X X=%04X Y=%04X", n, addr, s["cpu.a"], s["cpu.x"], s["cpu.y"])}
    for _, x in ipairs(extra) do t[#t + 1] = string.format("%s=%04X", x, emu.read16(tonumber(x, 16), m)) end
    log[#log + 1] = table.concat(t, " ")
  end, emu.callbackType.exec, addr, addr)
end
for a in string.gmatch(os.getenv("WW") or "", "[^,]+") do
  local addr = tonumber(a, 16)
  emu.addMemoryCallback(function(adr, val)
    if #log > 20000 then return end
    local s = emu.getState()
    log[#log + 1] = string.format("%d W %06X=%02X pc=%02X:%04X", n, adr, val or 0, s["cpu.k"], s["cpu.pc"])
  end, emu.callbackType.write, addr, addr)
end
local wr = os.getenv("WWRANGE")
if wr then
  local a, b, mask, val = wr:match("(%x+)-(%x+):(%x+)=(%x+)")
  a, b, mask, val = tonumber(a, 16), tonumber(b, 16), tonumber(mask, 16), tonumber(val, 16)
  emu.addMemoryCallback(function(adr, v)
    if (adr & mask) ~= val or #log > 20000 then return end
    local s = emu.getState()
    log[#log + 1] = string.format("%d W %06X=%02X pc=%02X:%04X", n, adr, v or 0, s["cpu.k"], s["cpu.pc"])
  end, emu.callbackType.write, a, b)
end
local maxf = tonumber(os.getenv("MAXF") or "1000")
emu.addEventCallback(function()
  n = n + 1
  if n == 1 then
    for _, p in ipairs(patches) do
      for i = 0, #p[2] / 2 - 1 do
        emu.write(p[1] + i, tonumber(p[2]:sub(i * 2 + 1, i * 2 + 2), 16), emu.memType.snesPrgRom)
      end
    end
    for _, s in ipairs(sets) do
      local a = 0x7E0000 | s[1]
      local v = emu.read(a, m)
      if s[2] == "=" then v = s[3] elseif s[2] == "|" then v = v | s[3] else v = v & s[3] end
      emu.write(a, v, m)
    end
  end
  for _, p in ipairs(pokes) do emu.write(p[1], p[2], m) end
  L.release()
  if si <= #seq then
    local s = seq[si]
    if left == nil then left = s[2] end
    if s[1] ~= "wait" then local t = {}; for b in s[1]:gmatch("[^+]+") do t[b] = true end; L.press(t) end
    left = left - 1
    if left <= 0 then si = si + 1; left = nil end
  end
  if shots[n] then L.shot(string.format("s%05d.png", n)) end
  for _, d in ipairs(dumps) do
    if d[1] == n then
      local t = {}
      for i = 0, d[3] - 1 do t[#t + 1] = string.format("%02X", emu.read(d[2] + i, m)) end
      log[#log + 1] = string.format("%d dump %06X %s", n, d[2], table.concat(t, " "))
    end
  end
  if n == maxf then
    L.write("msg.txt", table.concat(log, "\n") .. "\n")
    L.shot("end.png")
    emu.stop()
  end
end, emu.eventType.endFrame)
