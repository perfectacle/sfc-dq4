-- 필드 세이브스테이트에서 전투를 일으켜 고른 무리로 시작하게 하고, 전투 화면이 그려진 뒤 덤프한다.
-- 조우 판정 18:$9D06 을 메모리상 CLC/RTS 로 바꿔 걸음마다 전투가 나게 하고(롬 파일은 그대로),
-- 전투 시작 18:$A11A 에 닿으면 무리 칸 $6E45~$6E48(ID)·$6E49~$6E4C(마릿수)를 MON 으로 덮는다.
-- 환경 변수:
--   STATE        출발 세이브스테이트(필드에서 위아래로 걸을 수 있는 곳, 예: dq4-ch1-field.mss)
--   MON="05:1"   무리(16진 ID:마릿수, 쉼표로 넷까지). 빈 칸은 FF:0
--   WAIT=300     $A11A 뒤 덤프까지 기다릴 프레임
--   COVER=1      $A11A 부터 덤프까지 실행한 명령을 cover.txt 에(`krpatch fc listing` 형식: 오프셋 주소 횟수)
--   READS=1      $A11A 부터 덤프까지 읽은 PRG 를 256바이트 쪽마다 센 수를 reads.txt 에(쪽 오프셋 16진, 수, 첫 읽은 PC)
--   MAXF=1500    전투가 안 나도 이 프레임에서 멈춘다
-- 결과: SHOT_DIR/end.{ram,sram,chr,nt,pal,oam,png}, battle.txt(덮은 무리와 프레임)
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local L = require("lib")
L.loadState(os.getenv("STATE"))
local mons = {}
for id, cnt in string.gmatch(os.getenv("MON") or "", "(%x+):(%x+)") do
  mons[#mons + 1] = {tonumber(id, 16), tonumber(cnt, 16)}
end
local wait = tonumber(os.getenv("WAIT") or "300")
local maxf = tonumber(os.getenv("MAXF") or "1500")
local cover = os.getenv("COVER") == "1"
local ENC, START = 0x18 * 0x4000 + 0x1D06, 0x18 * 0x4000 + 0x211A
local n, hit, log, seen, order = 0, nil, {}, {}, {}

emu.addMemoryCallback(function(addr)
  if hit then return end
  if L.prgOffset(addr) ~= START then return end
  hit = n
  for i = 0, 3 do
    local m = mons[i + 1] or {0xFF, 0}
    emu.write(0x6E45 + i, m[1], L.mem)
    emu.write(0x6E49 + i, m[2], L.mem)
  end
  log[#log + 1] = string.format("start frame=%d mon=%s", n, os.getenv("MON") or "")
end, emu.callbackType.exec, 0xA11A, 0xA11A)

if cover then
  emu.addMemoryCallback(function(addr)
    if not hit then return end
    local o = L.prgOffset(addr)
    if not o then return end
    if not seen[o] then seen[o] = {addr, 0}; order[#order + 1] = o end
    seen[o][2] = seen[o][2] + 1
  end, emu.callbackType.exec, 0x8000, 0xFFFF)
end

local reads, rorder = {}, {}
if os.getenv("READS") == "1" then
  local pc = 0
  emu.addMemoryCallback(function(addr) pc = addr end, emu.callbackType.exec, 0x8000, 0xFFFF)
  emu.addMemoryCallback(function(addr)
    if not hit then return end
    local o = L.prgOffset(addr)
    if not o then return end
    local page = o // 256
    local e = reads[page]
    if not e then e = {0, pc}; reads[page] = e; rorder[#rorder + 1] = page end
    e[1] = e[1] + 1
  end, emu.callbackType.read, 0x8000, 0xFFFF)
end

local finished = false
local function finish(tag)
  if finished then return end
  finished = true
  log[#log + 1] = string.format("%s frame=%d", tag, n)
  L.dumpAll("end")
  L.shot("end.png")
  L.write("battle.txt", table.concat(log, "\n") .. "\n")
  if cover then
    table.sort(order)
    local t = {}
    for _, o in ipairs(order) do t[#t + 1] = string.format("%05X %04X %d", o, seen[o][1], seen[o][2]) end
    L.write("cover.txt", table.concat(t, "\n") .. "\n")
  end
  if #rorder > 0 then
    table.sort(rorder)
    local t = {}
    for _, p in ipairs(rorder) do t[#t + 1] = string.format("%05X %d %04X", p * 256, reads[p][1], reads[p][2]) end
    L.write("reads.txt", table.concat(t, "\n") .. "\n")
  end
  emu.stop()
end

emu.addEventCallback(function()
  n = n + 1
  if n == 3 then
    emu.write(ENC, 0x18, emu.memType.nesPrgRom)
    emu.write(ENC + 1, 0x60, emu.memType.nesPrgRom)
  end
  if n < 5 then return end
  if hit then
    L.release()
    if n >= hit + wait then finish("dump") end
  else
    L.press((n // 12) % 2 == 0 and {up = true} or {down = true})
    if n >= maxf then finish("timeout") end
  end
end, emu.eventType.endFrame)
