-- 전투를 일으켜(spritebattle.lua 와 같은 방법) A 를 눌러 싸우게 하며, 프레임마다 화면 쪽 메모리가 바뀐 것을 적는다.
-- 몬스터가 공격·주문할 때와 맞을 때 nametable·CHR·팔레트·OAM·PPU 레지스터가 어떻게 바뀌는지 보는 데 쓴다.
-- 환경 변수:
--   STATE        출발 세이브스테이트(필드에서 위아래로 걸을 수 있는 곳, 예: dq4-ch1-field.mss)
--   MON="0D:1"   무리(16진 ID:마릿수, 쉼표로 넷까지)
--   HPFILL=200   적 HP($7274+14n+10, 2바이트)가 이보다 작으면 이 값으로 채운다(0 이면 건드리지 않음).
--                최대 HP 보다 크게 채우면 「おっと！」 메시지(01D0·01D1)가 나오는 일이 있다.
--                이 자리는 필드 그림 표 $7200 과 겹치므로 전투가 끝난 뒤에도 채우면 필드 그림 표를 깨뜨린다
--   HPFRAMES=n   전투 시작 뒤 n 프레임까지만 HP 를 채운다(0 이면 FRAMES 끝까지)
--   FRAMES=2000  전투 시작 뒤 기록할 프레임
--   PRESS=6      A 를 이 프레임마다 눌렀다 뗀다
--   SHOTS=80     바뀐 프레임 중 앞의 이만큼은 스크린샷(s<프레임>.png)을 남긴다
--   MAXF=4000    전투가 안 나도 이 프레임에서 멈춘다
--   CALLS="1E:8D18,1E:8D2C"  이 주소(뱅크:CPU 주소, 고정 뱅크는 0F)를 실행하면 그 프레임 줄에 call=<주소>/A/X/Y 를 붙인다.
--                메시지 시작 16:$8656 은 늘 msg=<X:A> 로 붙인다
--   WATCH="0600-060B,00D6-00D7"  이 CPU 주소 범위에 쓰는 명령을 그 프레임 줄에 w<주소>@<뱅크:PC>=<값> 으로 붙인다
--                (프레임마다 같은 (주소, PC) 는 한 번)
--   RAW=1        전투 시작 뒤 프레임마다 nt(2KB)·pal(32)·oam(256)·chr(8KB)·ram(2KB)·sram(8KB, $6000~)을 이 순서로 이어 raw.bin 에
-- 결과: SHOT_DIR/frames.txt — 바뀐 프레임마다 한 줄:
--   f=<전투 시작부터 프레임> nt=<바뀐 바이트 수>[첫-끝] pal=… oam=… chr=…
--   w2007=<PC>:<PPU 주소 첫-끝>x<수> …(그 프레임에 $2007 로 쓴 명령), r2001=<그 프레임에 $2001 에 쓴 값들>, r2005=…
-- 그리고 SHOT_DIR/start.*(전투 시작 300프레임 뒤), end.*(끝).
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local L = require("lib")
L.loadState(os.getenv("STATE"))
local mons = {}
for id, cnt in string.gmatch(os.getenv("MON") or "0D:1", "(%x+):(%x+)") do
  mons[#mons + 1] = {tonumber(id, 16), tonumber(cnt, 16)}
end
local hpfill = tonumber(os.getenv("HPFILL") or "200")
local frames = tonumber(os.getenv("FRAMES") or "2000")
local hpframes = tonumber(os.getenv("HPFRAMES") or "0")
local press = tonumber(os.getenv("PRESS") or "6")
local shots = tonumber(os.getenv("SHOTS") or "80")
local maxf = tonumber(os.getenv("MAXF") or "4000")
local ENC, START = 0x18 * 0x4000 + 0x1D06, 0x18 * 0x4000 + 0x211A
local n, hit, lines, nshot = 0, nil, {}, 0

emu.addMemoryCallback(function(addr)
  if hit then return end
  if L.prgOffset(addr) ~= START then return end
  hit = n
  for i = 0, 3 do
    local m = mons[i + 1] or {0xFF, 0}
    emu.write(0x6E45 + i, m[1], L.mem)
    emu.write(0x6E49 + i, m[2], L.mem)
  end
end, emu.callbackType.exec, 0xA11A, 0xA11A)

local events, pc = {}, 0
emu.addMemoryCallback(function(a) pc = a end, emu.callbackType.exec, 0x8000, 0xFFFF)
local function hook(bank, cpu, fmt)
  local want = cpu < 0xC000 and bank * 0x4000 + (cpu & 0x3FFF) or nil
  emu.addMemoryCallback(function(addr)
    if not hit then return end
    if want and L.prgOffset(addr) ~= want then return end
    local st = emu.getState()
    if #events < 40 then events[#events + 1] = fmt(st) end
  end, emu.callbackType.exec, cpu, cpu)
end
hook(0x16, 0x8656, function(st) return string.format("msg=%02X%02X", st["cpu.x"], st["cpu.a"]) end)
for b, a in string.gmatch(os.getenv("CALLS") or "", "(%x+):(%x+)") do
  local bank, cpu = tonumber(b, 16), tonumber(a, 16)
  hook(bank, cpu, function(st)
    return string.format("call=%02X:%04X/%02X/%02X/%02X", bank, cpu, st["cpu.a"], st["cpu.x"], st["cpu.y"])
  end)
end

local wseen = {}
for a, b in string.gmatch(os.getenv("WATCH") or "", "(%x+)-(%x+)") do
  emu.addMemoryCallback(function(addr, value)
    if not hit then return end
    local off = L.prgOffset(pc)
    local k = string.format("w%04X@%s", addr, off and string.format("%02X:%04X", off // 0x4000, pc) or string.format("%04X", pc))
    if wseen[k] then return end
    wseen[k] = true
    if #events < 40 then events[#events + 1] = string.format("%s=%02X", k, value) end
  end, emu.callbackType.write, tonumber(a, 16), tonumber(b, 16))
end

-- PPU 쓰기 기록. $2006 두 번(위, 아래) 쓰기로 주소를 따라가고 $2007 마다 +1 또는 +32.
local latch, vaddr, inc32 = 0, 0, false
local w7, w7order, regs = {}, {}, {}
emu.addMemoryCallback(function(addr, value)
  if not hit then return end
  local r = addr & 7
  if r == 0 then
    inc32 = (value & 4) ~= 0
  elseif r == 2 then
    latch = 0
  elseif r == 6 then
    if latch == 0 then vaddr = (value & 0x3F) << 8 | (vaddr & 0xFF); latch = 1
    else vaddr = (vaddr & 0x3F00) | value; latch = 0 end
  elseif r == 7 then
    local off = L.prgOffset(pc)
    local key = off and string.format("%02X:%04X", off // 0x4000, pc) or string.format("%04X", pc)
    local e = w7[key]
    if not e then e = {vaddr, vaddr, 0}; w7[key] = e; w7order[#w7order + 1] = key end
    if vaddr < e[1] then e[1] = vaddr end
    if vaddr > e[2] then e[2] = vaddr end
    e[3] = e[3] + 1
    vaddr = (vaddr + (inc32 and 32 or 1)) & 0x3FFF
  end
  if r == 1 or r == 5 or r == 0 then
    local k = "r200" .. r
    regs[k] = regs[k] or {}
    local t = regs[k]
    if #t < 8 then t[#t + 1] = string.format("%02X", value) end
  end
end, emu.callbackType.write, 0x2000, 0x3FFF)
emu.addMemoryCallback(function() latch = 0 end, emu.callbackType.read, 0x2002, 0x2002)

local areas = {
  {"nt", emu.memType.nesNametableRam}, {"pal", emu.memType.nesPaletteRam},
  {"oam", emu.memType.nesSpriteRam}, {"chr", emu.memType.nesChrRam},
}
local prev = {}
local function snap(mt)
  local size = emu.getMemorySize(mt)
  local t = {}
  for i = 0, size - 1 do t[i] = emu.read(i, mt) end
  return t, size
end
local function diff(name, mt)
  local cur, size = snap(mt)
  local old = prev[name]
  prev[name] = cur
  if not old then return nil end
  local c, lo, hi = 0, nil, nil
  for i = 0, size - 1 do
    if cur[i] ~= old[i] then
      c = c + 1
      lo = lo or i
      hi = i
    end
  end
  if c == 0 then return nil end
  return string.format("%s=%d[%X-%X]", name, c, lo, hi)
end

local lastregs = {}
local raw = os.getenv("RAW") == "1" and {} or nil
local rawareas = {
  emu.memType.nesNametableRam, emu.memType.nesPaletteRam, emu.memType.nesSpriteRam,
  emu.memType.nesChrRam, emu.memType.nesInternalRam, emu.memType.nesSaveRam,
}
local function rawframe()
  local t = {}
  for _, mt in ipairs(rawareas) do
    for i = 0, emu.getMemorySize(mt) - 1 do t[#t + 1] = string.char(emu.read(i, mt)) end
  end
  raw[#raw + 1] = table.concat(t)
end

local function frameline(f)
  if raw then rawframe() end
  local parts = {}
  for _, a in ipairs(areas) do
    local d = diff(a[1], a[2])
    if d then parts[#parts + 1] = d end
  end
  local w = {}
  for _, k in ipairs(w7order) do
    local e = w7[k]
    w[#w + 1] = string.format("%s:%04X-%04Xx%d", k, e[1], e[2], e[3])
  end
  if #w > 0 then parts[#parts + 1] = "w2007=" .. table.concat(w, ",") end
  for _, k in ipairs({"r2000", "r2001", "r2005"}) do
    local s = regs[k] and table.concat(regs[k], " ") or ""
    if s ~= "" and s ~= lastregs[k] then parts[#parts + 1] = k .. "=" .. s end
    if s ~= "" then lastregs[k] = s end
  end
  for _, e in ipairs(events) do parts[#parts + 1] = e end
  w7, w7order, regs, events, wseen = {}, {}, {}, {}, {}
  if #parts == 0 then return end
  lines[#lines + 1] = string.format("f=%d %s", f, table.concat(parts, " "))
  if nshot < shots then
    nshot = nshot + 1
    L.shot(string.format("s%04d.png", f))
  end
end

local function finish(tag)
  lines[#lines + 1] = tag .. " frame=" .. n
  L.write("frames.txt", table.concat(lines, "\n") .. "\n")
  if raw then L.write("raw.bin", table.concat(raw)) end
  L.dumpAll("end")
  emu.stop()
end

emu.addEventCallback(function()
  n = n + 1
  if n == 3 then
    emu.write(ENC, 0x18, emu.memType.nesPrgRom)
    emu.write(ENC + 1, 0x60, emu.memType.nesPrgRom)
  end
  if n < 5 then return end
  if not hit then
    L.press((n // 12) % 2 == 0 and {up = true} or {down = true})
    if n >= maxf then finish("timeout") end
    return
  end
  local f = n - hit
  if f == 1 then lines[#lines + 1] = string.format("start frame=%d mon=%s", hit, os.getenv("MON") or "0D:1") end
  frameline(f)
  if f == 300 then L.dumpAll("start") end
  if hpfill > 0 and (hpframes == 0 or f < hpframes) then
    for i = 0, 7 do
      local a = 0x7274 + 14 * i + 10
      local hp = emu.read(a, L.mem) | emu.read(a + 1, L.mem) << 8
      if hp > 0 and hp < hpfill then
        emu.write(a, hpfill & 0xFF, L.mem)
        emu.write(a + 1, hpfill >> 8, L.mem)
      end
    end
  end
  L.press((f // press) % 2 == 0 and {a = true} or nil)
  if f >= frames or n >= maxf then finish("done") end
end, emu.eventType.endFrame)
