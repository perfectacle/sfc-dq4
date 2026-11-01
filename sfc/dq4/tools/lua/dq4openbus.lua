-- 뱅크 40~7D 아래 절반(xx:0000-7FFF) 읽기·쓰기와, 뱅크 40 이상 코드가 부른 BRK 명령을 PC 별로 적고 PROBE_TARGET
-- 스크립트를 이어 돈다(dq4compatcheck.py --probe). 그 자리는 WRAM 거울이 아니라 열린 버스·롬 거울·SRAM 이다.
-- 뱅크 00~3F 의 다른 열린 버스 구역까지 넓히면 콜백이 너무 많아 걷기 검사가 시간 제한에 걸린다.
local log = os.getenv("OPENBUS_LOG")
local seen = {}
local function put(line)
  if not seen[line] then
    seen[line] = true
    local f = io.open(log, "a"); f:write(line .. "\n"); f:close()
  end
end
local function hit(kind)
  return function(addr, value)
    local s = emu.getState()
    put(string.format("%s pc=%02X:%04X bank=%02X", kind, s["cpu.k"], s["cpu.pc"], addr >> 16))
  end
end
for b = 0x40, 0x7D do
  emu.addMemoryCallback(hit("R"), emu.callbackType.read, (b << 16), (b << 16) | 0x7FFF)
  emu.addMemoryCallback(hit("W"), emu.callbackType.write, (b << 16), (b << 16) | 0x7FFF)
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
