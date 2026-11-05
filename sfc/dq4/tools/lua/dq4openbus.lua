-- 열린 버스·롬 거울 구역의 읽기·쓰기와, 뱅크 40 이상 코드가 부른 BRK 명령을 PC 별로 적고 PROBE_TARGET 스크립트를
-- 이어 돈다(dq4compatcheck.py probe·scenes). OPENBUS_RANGES 는 「뱅크-뱅크:주소-주소」 를 쉼표로 이은 것이고, 없으면
-- 뱅크 40~7D 아래 절반(WRAM 거울이 아니라 열린 버스·롬 거울·SRAM)이다. 그때 기록 줄은 「R pc=24:FE52 bank=5E」 이고,
-- 범위를 주면 주소까지 「R pc=24:FE52 bank=00 at=4380」 으로 적는다. 콜백 수가 늘면 느려져 장면이 시간 제한에 걸리므로
-- 넓은 범위는 여러 실행으로 나눠 준다.
-- 여러 MesenCE 가 같은 파일에 덧붙인다. 파일은 한 번만 열어 두고 줄마다 비운다(줄마다 열고 닫으면 같은 루틴이 수만
-- 자리를 읽는 장면에서 콜백이 느려진다)
local out = io.open(os.getenv("OPENBUS_LOG"), "a")
local seen = {}
local function put(line)
  if not seen[line] then
    seen[line] = true
    out:write(line, "\n")
    out:flush()
  end
end
local spec = os.getenv("OPENBUS_RANGES") or ""
local withAddr = spec ~= ""
if spec == "" then spec = "40-7D:0000-7FFF" end
local function hit(kind)
  return function(addr, value)
    local s = emu.getState()
    if withAddr then
      put(string.format("%s pc=%02X:%04X bank=%02X at=%04X", kind, s["cpu.k"], s["cpu.pc"], addr >> 16, addr & 0xFFFF))
    else
      put(string.format("%s pc=%02X:%04X bank=%02X", kind, s["cpu.k"], s["cpu.pc"], addr >> 16))
    end
  end
end
for b1, b2, a1, a2 in string.gmatch(spec, "(%x+)-(%x+):(%x+)-(%x+)") do
  for b = tonumber(b1, 16), tonumber(b2, 16) do
    local lo, hi = (b << 16) | tonumber(a1, 16), (b << 16) | tonumber(a2, 16)
    emu.addMemoryCallback(hit("R"), emu.callbackType.read, lo, hi)
    emu.addMemoryCallback(hit("W"), emu.callbackType.write, lo, hi)
  end
end
-- BRK 핸들러 입구(00:FFE6 이 가리키는 00:8F80). 스택에 P, PC 낮은·높은 바이트, PB 가 쌓여 있다
emu.addMemoryCallback(function()
  local m = emu.memType.snesMemory
  local sp = emu.getState()["cpu.sp"]
  local pb = emu.read(sp + 4, m)
  if pb >= 0x40 then
    local ret = emu.read(sp + 3, m) << 8 | emu.read(sp + 2, m)
    put(string.format("BRK pc=%02X:%04X op=%02X", pb, (ret - 2) & 0xFFFF, emu.read(pb << 16 | ((ret - 1) & 0xFFFF), m)))
  end
end, emu.callbackType.exec, 0x008F80, 0x008F80)
dofile(os.getenv("PROBE_TARGET"))
