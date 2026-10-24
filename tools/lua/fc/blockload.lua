-- PRG ROM 오프셋 AT(16진, 쉼표로 여럿)의 명령이 실행될 때마다 CPU 메모리 $0000-$7FFF 와 CHR-RAM·nametable·팔레트를
-- ld_OOOOO_N.{cpu,chr,nt,pal} 로 저장한다(오프셋마다 LIMIT 번, 기본 2). 같은 CPU 주소라도 다른 뱅크면 건너뛴다.
-- 맵에 들어갈 때 블록 표를 올린 직후(08:$853B = PRG 2053B)처럼, 나중에 애니메이션이 CHR 을 바꾸기 전 상태를 본다.
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local L = require("lib")
local limit = tonumber(os.getenv("LIMIT") or "2")
for a in string.gmatch(os.getenv("AT"), "[^,]+") do
  local off, n = tonumber(a, 16), 0
  local cpu = 0x8000 + off % 0x4000
  if off % 0x40000 >= 0x3C000 then cpu = 0xC000 + off % 0x4000 end
  emu.addMemoryCallback(function(addr)
    if n >= limit or L.prgOffset(addr) ~= off then return end
    n = n + 1
    local name = string.format("ld_%05X_%d", off, n)
    L.dump(name .. ".cpu", L.mem, 0x8000)
    L.dump(name .. ".chr", emu.memType.nesChrRam)
    L.dump(name .. ".nt", emu.memType.nesNametableRam)
    L.dump(name .. ".pal", emu.memType.nesPaletteRam)
  end, emu.callbackType.exec, cpu, cpu)
end
L.drive()
