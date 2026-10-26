-- DQ5 전투 연출 스크립트 명령 3E(22:DBD6 → JMP ($0053))가 부르는 22 뱅크 루틴의 동작 기록.
-- 드라이버(boot.lua, 보통 dq5battle.lua)로 싸우면서 3E 로 들어갈 때(22:DBE1)부터 해석기로 돌아올 때(22:D934)까지
-- WRAM 읽기·쓰기(WRAM 안 오프셋, 거울 주소도 합침)와 PPU·DMA 레지스터 쓰기를 모아 3e.txt 에 한 줄씩 남긴다.
--   fx=연출($0D14) f=들어간·돌아온 프레임 r=루틴 y=스크립트 위치($9D9F) S=스택
--   M: 몬스터 배치 7E:5BA0~5BFF 를 썼으면 돌아온 뒤의 값
--   v: 변수 7E:9E73~9EA2 가 바뀐 것(9E73+k 의 k:전→후)   R: 읽은 WRAM 범위   W: 쓴 WRAM 범위(스택 제외)   P: PPU·DMA 쓰기(마지막 값)
--   같은 연출에서 같은 루틴은 처음 MAXCALL(기본 3)번만 자세히 적고, 나머지는 끝에 횟수만 적는다.
--   FORCE="0DA8=80;0DA7=21"  연출을 시작할 때마다 WRAM(오프셋)에 써 넣는다(회심 플래그·무기 번호처럼 스크립트가 고르는 갈래를 바꿀 때)
--   연출을 시작할 때(22:D73C) 몬스터 배치 7E:5BA0~5BFF 와 기준 칸 9E78·9E79 를 L 줄로 적는다.
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local L = require("lib")
local wram, cpu = emu.memType.snesWorkRam, emu.memType.snesMemory
local maxcall = tonumber(os.getenv("MAXCALL") or "3")
local n, log, cur, cbs, counts = 0, {}, nil, {}, {}

local function ranges(t, skip)
  local ks = {}
  for a in pairs(t) do if not (skip and skip(a)) then ks[#ks + 1] = a end end
  table.sort(ks)
  local out, i = {}, 1
  while i <= #ks do
    local j = i
    while j < #ks and ks[j + 1] == ks[j] + 1 do j = j + 1 end
    if j == i then out[#out + 1] = string.format("%05X", ks[i]) else out[#out + 1] = string.format("%05X-%05X", ks[i], ks[j]) end
    i = j + 1
  end
  return table.concat(out, ",")
end

local function hex(a, len)
  local t = {}
  for i = 0, len - 1 do t[#t + 1] = string.format("%02X", emu.read(a + i, wram)) end
  return table.concat(t)
end

-- NMI·IRQ 안의 접근은 루틴 몫이 아니므로 뺀다. 인터럽트가 걸린 때의 S 보다 깊은 동안을 인터럽트 안으로 본다.
local intSP
local function onInt()
  if cur then intSP = emu.getState()["cpu.sp"] end
end
emu.addEventCallback(onInt, emu.eventType.nmi)
emu.addEventCallback(onInt, emu.eventType.irq)
local function inInt()
  if not intSP then return false end
  if emu.getState()["cpu.sp"] < intSP then return true end
  intSP = nil
  return false
end

local force = {}
for a, v in string.gmatch(os.getenv("FORCE") or "", "(%x+)=(%x+)") do force[#force + 1] = {tonumber(a, 16), tonumber(v, 16)} end
emu.addMemoryCallback(function()
  local fx = emu.getState()["cpu.a"] & 0xFF
  for _, f in ipairs(force) do emu.write(f[1], f[2], wram) end
  log[#log + 1] = string.format("L fx=%02X f=%d base=%02X,%02X 5BA0=%s", fx, n, emu.read(0x9E78, wram), emu.read(0x9E79, wram), hex(0x5BA0, 0x60))
end, emu.callbackType.exec, 0x22D73C, 0x22D73C)

emu.addMemoryCallback(function()
  local s = emu.getState()
  local r = emu.read(0x53, wram) | emu.read(0x54, wram) << 8
  local fx = emu.read(0x0D14, wram)
  local key = string.format("%02X %04X", fx, r)
  counts[key] = (counts[key] or 0) + 1
  if counts[key] > maxcall then return end
  local vars = {}
  for k = 0, 0x2F do vars[k] = emu.read(0x9E73 + k, wram) end
  cur = {fx = fx, r = r, f = n, y = emu.read(0x9D9F, wram) | emu.read(0x9DA0, wram) << 8, sp = s["cpu.sp"], vars = vars, rd = {}, wr = {}, ppu = {}}
  cbs[1] = emu.addMemoryCallback(function(a) if not inInt() then cur.rd[a & 0x1FFFF] = true end end, emu.callbackType.read, 0x0200, 0x1FFFF, emu.cpuType.snes, wram)
  cbs[2] = emu.addMemoryCallback(function(a) if not inInt() then cur.wr[a & 0x1FFFF] = true end end, emu.callbackType.write, 0x0000, 0x1FFFF, emu.cpuType.snes, wram)
  cbs[3] = emu.addMemoryCallback(function(a, v) if not inInt() then cur.ppu[a] = v end end, emu.callbackType.write, 0x2100, 0x21FF)
  cbs[4] = emu.addMemoryCallback(function(a, v) if not inInt() then cur.ppu[a] = v end end, emu.callbackType.write, 0x4200, 0x437F)
end, emu.callbackType.exec, 0x22DBE1, 0x22DBE1)

emu.addMemoryCallback(function()
  if not cur then return end
  emu.removeMemoryCallback(cbs[1], emu.callbackType.read, 0x0200, 0x1FFFF, emu.cpuType.snes, wram)
  emu.removeMemoryCallback(cbs[2], emu.callbackType.write, 0x0000, 0x1FFFF, emu.cpuType.snes, wram)
  emu.removeMemoryCallback(cbs[3], emu.callbackType.write, 0x2100, 0x21FF)
  emu.removeMemoryCallback(cbs[4], emu.callbackType.write, 0x4200, 0x437F)
  local v = {}
  for k = 0, 0x2F do
    local b = emu.read(0x9E73 + k, wram)
    if b ~= cur.vars[k] then v[#v + 1] = string.format("%X:%02X>%02X", k, cur.vars[k], b) end
  end
  local sp = cur.sp
  local stack = function(a) return a <= sp and a > sp - 0x40 end
  local nostack = function(a) return stack(a) or (a >= 0x9E73 and a < 0x9EA3) end
  local p = {}
  local pk = {}
  for a in pairs(cur.ppu) do pk[#pk + 1] = a end
  table.sort(pk)
  for _, a in ipairs(pk) do p[#p + 1] = string.format("%04X=%02X", a, cur.ppu[a]) end
  log[#log + 1] = string.format("fx=%02X f=%d-%d r=%04X y=%04X S=%04X v=%s R=%s W=%s P=%s", cur.fx, cur.f, n, cur.r, cur.y, sp,
    table.concat(v, ","), ranges(cur.rd, stack), ranges(cur.wr, nostack), table.concat(p, ","))
  local lay = false
  for a in pairs(cur.wr) do if a >= 0x5BA0 and a < 0x5C00 then lay = true end end
  if lay then log[#log] = log[#log] .. " M=" .. hex(0x5BA0, 0x60) end
  cur, intSP = nil, nil
end, emu.callbackType.exec, 0x22D934, 0x22D934)

-- VMDUMP=1: 22:D790(스크립트 해석기를 부르기 직전)에서 WRAM 128KB 와 레지스터를 v<연출>.wram·.regs 로,
-- VMSCREENS=1 이면 연출 입구의 VRAM·CGRAM·OAM(v<연출>.vram0 등)과 그 프레임의 VRAM·CGRAM·OAM·BG3 스크롤도 e<연출>-<k>.* 로.
-- 그 뒤 00:969A(프레임 기다림)마다 BG3 사본 7E:8A1D 896바이트와 $19·$0F5E·$0F5F·난수 $075B~$075D·$0DB0·$0DBC 8바이트를 v<연출>.frames 에 덧붙인다(dq5fxvm.py 가 견줌)
local vm = os.getenv("VMDUMP") and {}
if vm then
  emu.addMemoryCallback(function()
    local fx = emu.read(0x0D14, wram)
    if vm[fx] then return end
    local s = emu.getState()
    vm[fx] = {}
    vm.cur = fx
    L.dump(string.format("v%02X.wram", fx), wram, 0x20000)
    L.write(string.format("v%02X.regs", fx), string.format("%04X %04X %04X %04X %04X %02X %02X\n", s["cpu.a"], s["cpu.x"], s["cpu.y"], s["cpu.sp"], s["cpu.d"], s["cpu.dbr"] or s["cpu.db"] or 0x7E, s["cpu.ps"] or 0))
  end, emu.callbackType.exec, 0x22D790, 0x22D790)
  -- 연출 입구 22:D73C 에서도 WRAM·레지스터를 v<연출>.wram0·.regs0 으로(dq5fxvm.py --from-entry)
  emu.addMemoryCallback(function()
    local s = emu.getState()
    local fx = s["cpu.a"] & 0xFF
    if vm["e" .. fx] then return end
    vm["e" .. fx] = true
    L.dump(string.format("v%02X.wram0", fx), wram, 0x20000)
    if (os.getenv("VMSCREENS") or "") ~= "" then
      L.dump(string.format("v%02X.vram0", fx), emu.memType.snesVideoRam, 0x10000)
      L.dump(string.format("v%02X.cgram0", fx), emu.memType.snesCgRam, 0x200)
      L.dump(string.format("v%02X.oam0", fx), emu.memType.snesSpriteRam, 0x220)
    end
    L.write(string.format("v%02X.regs0", fx), string.format("%04X %04X %04X %04X %04X %02X %02X\n", s["cpu.a"], s["cpu.x"], s["cpu.y"], s["cpu.sp"], s["cpu.d"], s["cpu.dbr"] or s["cpu.db"] or 0x7E, s["cpu.ps"] or 0))
  end, emu.callbackType.exec, 0x22D73C, 0x22D73C)
  emu.addMemoryCallback(function()
    if vm.cur then vm.cur = nil end
  end, emu.callbackType.exec, 0x22D793, 0x22D793)
  emu.addMemoryCallback(function()
    if not vm.cur then return end
    local t = vm[vm.cur]
    local b = {}
    for i = 0, 0x37F do b[#b + 1] = string.char(emu.read(0x8A1D + i, wram)) end
    for _, a in ipairs({0x19, 0x0F5E, 0x0F5F, 0x075B, 0x075C, 0x075D, 0x0DB0, 0x0DBC}) do b[#b + 1] = string.char(emu.read(a, wram)) end
    t[#t + 1] = table.concat(b)
    local f = io.open(os.getenv("SHOT_DIR") .. string.format("/v%02X.frames", vm.cur), "wb")
    f:write(table.concat(t))
    f:close()
    if (os.getenv("VMSCREENS") or "") ~= "" then
      -- 같은 때의 VRAM·CGRAM·OAM 과 BG3 스크롤(dq5fxvm.py --screens 가 e<연출>-<k> 로 읽음)
      local p = string.format("e%02X-%03d", vm.cur, #t - 1)
      local st = emu.getState()
      L.dump(p .. ".vram", emu.memType.snesVideoRam, 0x10000)
      L.dump(p .. ".cgram", emu.memType.snesCgRam, 0x200)
      L.dump(p .. ".oam", emu.memType.snesSpriteRam, 0x220)
      L.write(p .. ".ppu", string.format("%d %d\n", st["ppu.layers[2].hscroll"], st["ppu.layers[2].vscroll"]))
      if (os.getenv("VMWRAM") or "") ~= "" then L.dump(p .. ".wram", wram, 0x20000) end
    end
  end, emu.callbackType.exec, 0x00969A, 0x00969A)
end

emu.addEventCallback(function()
  n = n + 1
  if n % 50 == 0 or n > 2000 then
    local t = {}
    for k, c in pairs(counts) do t[#t + 1] = string.format("C %s %d", k, c) end
    table.sort(t)
    L.write("3e.txt", table.concat(log, "\n") .. "\n" .. table.concat(t, "\n") .. "\n")
  end
end, emu.eventType.endFrame)
dofile(os.getenv("LIBDIR") .. "/boot.lua")
