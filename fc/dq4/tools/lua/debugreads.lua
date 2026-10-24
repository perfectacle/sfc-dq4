-- 디버그 스위치 $C000(PRG 3C000·7C000)을 읽는 명령을 모아 debugreads.txt 에 "PRG오프셋 CPU주소 횟수 첫프레임".
-- 읽기 콜백 안의 cpu.pc 는 다음 명령이므로, 직전 3바이트가 "AD/2C/AC/AE 00 C0" 인 자리를 읽은 명령으로 본다.
-- 그 꼴이 아니면(색인 읽기·더미 읽기) PC 를 "?" 와 함께 그대로 적는다.
-- 환경 변수: DRIVER(입력 드라이버), SHOT_DIR, MAXF
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local L = require("lib")
local maxf = tonumber(os.getenv("MAXF") or "1500")
local rom = emu.memType.nesPrgRom
local n, hits, order = 0, {}, {}
local function onRead()
  local pc = emu.getState()["cpu.pc"]
  local at, tag = pc, "?"
  if emu.read(pc - 2, L.mem) == 0x00 and emu.read(pc - 1, L.mem) == 0xC0 then at, tag = pc - 3, "" end
  local off = L.prgOffset(at)
  local key = string.format("%s %04X%s", off and string.format("%05X", off) or "-", at, tag)
  if not hits[key] then hits[key] = {0, n}; order[#order + 1] = key end
  hits[key][1] = hits[key][1] + 1
end
for _, off in ipairs({0x3C000, 0x7C000}) do
  emu.addMemoryCallback(onRead, emu.callbackType.read, off, off, emu.cpuType.nes, rom)
end
emu.addEventCallback(function()
  n = n + 1
  if n == maxf - 1 then
    local t = {}
    for _, k in ipairs(order) do t[#t + 1] = string.format("%s %d %d", k, hits[k][1], hits[k][2]) end
    L.write("debugreads.txt", table.concat(t, "\n") .. "\n")
  end
end, emu.eventType.endFrame)
L.drive()
