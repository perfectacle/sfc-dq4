-- eventwalk.lua(리셋·저장·불러오기를 걸어서 하는 드라이버)를 돌리면서
--   RANGE(CPU 주소 "6C0C-6CAB", 쉼표로 여럿)에 쓰는 명령을 PC 마다 모아 wlog.txt 에
--     "pc=ADDR prg=OFFSET first=FRAME last=FRAME n=COUNT v=LAST" 로,
--   TR(PRG ROM 오프셋, 쉼표로 여럿)의 명령이 돌 때마다 tr.txt 에 "f=FRAME prg=OFFSET a=A ret=스택 위 복귀 주소" 로 쓴다.
-- eventwalk.lua 는 끝에 emu.stop 으로 멈추므로 두 파일은 쓸 때마다 통째로 다시 쓴다.
-- 환경 변수는 eventwalk.lua 와 같고, EVENTWALK 에 그 파일의 절대 경로를 준다.
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local L = require("lib")
local dir = os.getenv("SHOT_DIR")
local f, cur, seen, order, tr = 0, 0, {}, {}, {}

local function save(name, lines)
  local fh = io.open(dir .. "/" .. name, "w")
  fh:write(table.concat(lines, "\n") .. "\n")
  fh:close()
end

local function flush()
  local t = {}
  for _, k in ipairs(order) do
    local e = seen[k]
    t[#t + 1] = string.format("pc=%04X prg=%05X first=%d last=%d n=%d v=%02X", e.pc, e.prg, e.first, e.last, e.n, e.v)
  end
  save("wlog.txt", t)
end

emu.addMemoryCallback(function(a) cur = a end, emu.callbackType.exec, 0x8000, 0xFFFF)
for a, b in string.gmatch(os.getenv("RANGE") or "", "(%x+)-(%x+)") do
  emu.addMemoryCallback(function(_, v)
    local prg = L.prgOffset(cur) or 0
    local k = cur * 0x100000 + prg
    local e = seen[k]
    if not e then
      e = {pc = cur, prg = prg, first = f, n = 0}
      seen[k] = e; order[#order + 1] = k
    end
    e.n = e.n + 1; e.last = f; e.v = v
    flush()
  end, emu.callbackType.write, tonumber(a, 16), tonumber(b, 16))
end

for a in string.gmatch(os.getenv("TR") or "", "[^,]+") do
  local off = tonumber(a, 16)
  local cpu = 0x8000 + off % 0x4000
  if off % 0x40000 >= 0x3C000 then cpu = 0xC000 + off % 0x4000 end
  emu.addMemoryCallback(function(addr)
    if L.prgOffset(addr) ~= off then return end
    local st = emu.getState()
    local sp = st["cpu.sp"]
    tr[#tr + 1] = string.format("f=%d prg=%05X a=%02X ret=%02X%02X", f, off, st["cpu.a"],
      emu.read(0x102 + sp, L.mem), emu.read(0x101 + sp, L.mem))
    save("tr.txt", tr)
  end, emu.callbackType.exec, cpu, cpu)
end

emu.addEventCallback(function() f = f + 1 end, emu.eventType.endFrame)
dofile(os.getenv("EVENTWALK"))
