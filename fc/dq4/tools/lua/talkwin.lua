-- talk.lua 에 전투 이기기와 자동 입력 기록을 덧붙인 프로브. TALK = talk.lua 의 절대 경로. talk.lua 의 환경 변수(SLOT·TID·SET·EV·MAXF)를
-- 그대로 쓰고, 기록도 talk.txt 에 남는다. 덧붙는 것:
-- WIN=1  특수 전투 입구(18:$A1AD)를 지난 뒤 WINF(기본 6000) 프레임 동안, 적 8칸의 HP($727E + 14n, 2바이트)가
--        1 보다 크면 1 로 낮추고 수비력(+3, 2바이트)을 0 으로 둔다. 0 인 칸(쓰러진 적)은 건드리지 않으므로
--        한 번 맞히면 쓰러진다. 쓰이는 인물 레코드(+00 = 80, $6001 + 30k)의 HP 는 최대 HP 로 채운다.
-- auto.txt  $0530 bit7(자동 입력)이 서 있는 프레임마다 프레임, $0530~$0533, 패드 $14, 맵 좌표 $44/$45.
-- extra.txt  EVADDR(16진 CPU 주소, 뱅크 1C, 쉼표로 여럿)에 들어올 때마다 enter 줄. 1C:$BF74 표를 거치지 않고
--        이벤트 루틴에 들어가는 길을 볼 때 쓴다.
-- PRGPOKE="offset=val;..."  PRG ROM 바이트(iNES 머리를 뺀 오프셋)를 첫 프레임에 에뮬레이터 메모리에서만 바꾼다.
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local L = require("lib")
local f, battle, auto, extra = 0, nil, {}, {}
local winf = tonumber(os.getenv("WINF") or "6000")

emu.addMemoryCallback(function()
  if L.prgOffset(0xA1AD) == 0x621AD then battle = f end
end, emu.callbackType.exec, 0xA1AD, 0xA1AD)

for t in string.gmatch(os.getenv("EVADDR") or "", "%x+") do
  local a = tonumber(t, 16)
  emu.addMemoryCallback(function()
    if L.prgOffset(a) ~= 0x70000 + (a - 0x8000) then return end
    extra[#extra + 1] = string.format("%d enter %04X", f, a)
  end, emu.callbackType.exec, a, a)
end

local prgPokes = {}
for a, v in string.gmatch(os.getenv("PRGPOKE") or "", "(%x+)=(%x+)") do
  prgPokes[#prgPokes + 1] = {tonumber(a, 16), tonumber(v, 16)}
end

local maxf = tonumber(os.getenv("MAXF") or "1500")
emu.addEventCallback(function()
  f = f + 1
  if f == 1 then
    for _, p in ipairs(prgPokes) do emu.write(p[1], p[2], emu.memType.nesPrgRom) end
  end
  local m = emu.read(0x0530, L.mem)
  if m >= 0x80 then
    auto[#auto + 1] = string.format("%d %02X %02X %02X%02X pad=%02X xy=%02X,%02X", f, m,
      emu.read(0x0531, L.mem), emu.read(0x0533, L.mem), emu.read(0x0532, L.mem),
      emu.read(0x14, L.mem), emu.read(0x44, L.mem), emu.read(0x45, L.mem))
  end
  if os.getenv("WIN") and battle and f - battle < winf then
    for n = 0, 7 do
      local a = 0x727E + 14 * n
      local hp = emu.read(a, L.mem) + 256 * emu.read(a + 1, L.mem)
      if hp > 1 then emu.write(a, 1, L.mem); emu.write(a + 1, 0, L.mem) end
      emu.write(a - 7, 0, L.mem); emu.write(a - 6, 0, L.mem)
    end
    for k = 0, 8 do
      local r = 0x6001 + 30 * k
      if emu.read(r, L.mem) == 0x80 then
        emu.write(r + 1, emu.read(r + 12, L.mem), L.mem); emu.write(r + 2, emu.read(r + 13, L.mem), L.mem)
      end
    end
  end
  if f == maxf - 1 then
    L.write("auto.txt", table.concat(auto, "\n") .. "\n")
    L.write("extra.txt", table.concat(extra, "\n") .. "\n")
  end
end, emu.eventType.endFrame)

dofile(os.getenv("TALK"))
