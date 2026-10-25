-- 정해 둔 프레임 동안 PPU 레지스터 쓰기($2000·$2001·$2005·$2006, CHR 을 쓸 때의 $2007)를 (프레임, scanline, cycle, 값, pc, PRG 오프셋)으로 적고,
-- AT 프레임마다 fcgfxscene.lua 와 같은 덤프를 뜬다(줄마다 스크롤을 바꾸는 장면, CHR 을 만드는 루틴 찾기용).
-- 입력은 DRIVER(기본 boot.lua, seq.lua 도 됨)가 준다. 전원을 켜서 시작할 때는 debugsram.lua 의 SRAM_DRIVER 로 이 파일을 준다.
-- 환경 변수:
--   LOG="1000-1003"    PPU 쓰기를 적을 프레임 범위(이 Lua 가 센 endFrame 수, 쉼표로 여럿). 결과는 ppulog.txt
--   CHRLOG="a-b"       $2007 쓰기 중 PPU 주소가 $0000~$1FFF(CHR)인 것만 적을 프레임 범위. 결과는 chrlog.txt
--   AT, SHOT_DIR, STOP fcgfxscene.lua 와 같음(fNNNNN.png·.nt·.chr·.pal·.oam·.ram·.ppu·.oam2)
--   PRGPOKE="off=val;..." 3프레임째에 에뮬레이터 메모리의 PRG ROM 바이트를 바꿈(롬 파일은 그대로)
-- pc 는 쓰기 콜백 때의 cpu.pc(쓰기 명령 다음 명령의 주소)이고 PRG 오프셋은 emu.convertAddress 로 바꾼 것(뱅크 = 오프셋 / $4000).
-- 기록의 프레임 번호는 그 쓰기가 보이는 화면 덤프(fNNNNN.png)의 번호다. 화면 덤프가 한 프레임 늦으므로(fcgfxpal.lua)
-- endFrame n 과 n+1 사이의 쓰기(vblank 다음 보이는 줄)는 n+2 로 적는다.
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local L = require("lib")
local function ranges(s)
  local t = {}
  for a, b in string.gmatch(s or "", "(%d+)%-?(%d*)") do t[#t + 1] = {tonumber(a), tonumber(b ~= "" and b or a)} end
  return t
end
local function inr(t, n) for _, r in ipairs(t) do if n >= r[1] and n <= r[2] then return true end end return false end
local logR, chrR = ranges(os.getenv("LOG")), ranges(os.getenv("CHRLOG"))
local at, last = {}, 0
for f in string.gmatch(os.getenv("AT") or "", "%d+") do
  local k = tonumber(f); at[k] = true; if k > last then last = k end
end
for _, r in ipairs(logR) do if r[2] > last then last = r[2] end end
for _, r in ipairs(chrR) do if r[2] > last then last = r[2] end end
local stop = tonumber(os.getenv("STOP") or tostring(last + 5))
local prgPokes = {}
for a, v in string.gmatch(os.getenv("PRGPOKE") or "", "(%x+)=(%x+)") do prgPokes[#prgPokes + 1] = {tonumber(a, 16), tonumber(v, 16)} end
local n, ctrl = 0, 0
local log, chrlog = {}, {}
-- $2006 두 번 쓰기로 맞춘 VRAM 주소를 따라간다($2002 읽기·$2005 와 같은 w 토글, $2007 은 $2000 bit2 에 따라 +1/+32).
local w, vaddr, hi = 0, 0, 0
local function where()
  local s = emu.getState()
  local pc = s["cpu.pc"]
  local c = emu.convertAddress(pc, L.mem)
  local off = (c and c.memType == emu.memType.nesPrgRom) and string.format("%05X", c.address) or "-----"
  return s["ppu.scanline"], s["ppu.cycle"], pc, off
end
emu.addMemoryCallback(function(addr, value)
  local reg = addr & 7
  if reg == 0 then ctrl = value end
  if reg == 5 or reg == 6 then
    if reg == 6 then
      if w == 0 then hi = value & 0x3F else vaddr = hi * 256 + value end
    end
    w = 1 - w
  end
  if inr(logR, n + 2) and (reg == 0 or reg == 1 or reg == 5 or reg == 6) then
    local sl, cy, pc, off = where()
    log[#log + 1] = string.format("%05d %3d %3d %04X=%02X pc=%04X prg=%s w=%d", n + 2, sl, cy, 0x2000 + reg, value, pc, off, w)
  end
  if reg == 7 then
    if vaddr < 0x2000 and inr(chrR, n + 2) then
      local sl, cy, pc, off = where()
      chrlog[#chrlog + 1] = string.format("%05d %04X=%02X pc=%04X prg=%s", n + 2, vaddr, value, pc, off)
    end
    vaddr = (vaddr + ((ctrl & 4) ~= 0 and 32 or 1)) & 0x3FFF
  end
end, emu.callbackType.write, 0x2000, 0x3FFF)
emu.addMemoryCallback(function(addr, value) if (addr & 7) == 2 then w = 0 end end, emu.callbackType.read, 0x2000, 0x3FFF)
emu.addEventCallback(function()
  n = n + 1
  if n == 3 then for _, p in ipairs(prgPokes) do emu.write(p[1], p[2], emu.memType.nesPrgRom) end end
  if at[n + 1] then
    local p = string.format("f%05d", n + 1)
    L.dump(p .. ".nt", emu.memType.nesNametableRam)
    L.dump(p .. ".chr", emu.memType.nesChrRam)
    L.dump(p .. ".pal", emu.memType.nesPaletteRam)
    L.dump(p .. ".oam", emu.memType.nesSpriteRam)
    L.dump(p .. ".ram", emu.memType.nesInternalRam)
    L.write(p .. ".ppu", string.char(ctrl))
  end
  if at[n] then
    L.shot(string.format("f%05d.png", n))
    L.dump(string.format("f%05d.oam2", n), emu.memType.nesSpriteRam)
  end
  if n >= stop then
    if #log > 0 then L.write("ppulog.txt", table.concat(log, "\n") .. "\n") end
    if #chrlog > 0 then L.write("chrlog.txt", table.concat(chrlog, "\n") .. "\n") end
    emu.stop(0)
  end
end, emu.eventType.endFrame)
L.drive()
