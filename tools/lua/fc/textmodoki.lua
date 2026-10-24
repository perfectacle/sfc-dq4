-- 전투 행동 분기 11:$8C85(BRK 03 1F 가 돌려준 A = 행동 번호, 표 11:$A3FA 의 첨자)를 기록하고,
-- FORCE=27(16진)이면 그 A 를 바꿔 모든 행동을 그 번호로 돌린다. もどき 비트(몬스터 전투 레코드 바이트 6 bit4)를
-- 누가 켜는지 보려고 쓴다. 칸 0 레코드 $7274 부터 RANGE 바이트(기본 $7274-$72FF)에 쓰기가 있으면 값·PC 를,
-- HOOK="9DDE,B114"(뱅크 11 CPU 주소)가 실행되면 프레임을 modoki.txt 에 적는다. 메시지 진입 16:$8656 의 X:A 도.
-- 끝에서 입력 드라이버(DRIVER, 예: seq.lua)를 돌린다. 기록은 MAXF-1 프레임에 쓴다.
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local L = require("lib")
local force = os.getenv("FORCE") and tonumber(os.getenv("FORCE"), 16)
local lo, hi = 0x7274, 0x72FF
local r = os.getenv("RANGE")
if r then local a, b = r:match("(%x+)-(%x+)"); lo, hi = tonumber(a, 16), tonumber(b, 16) end
local f, out = 0, {}
local maxf = tonumber(os.getenv("MAXF") or "1500")
local function log(s) out[#out + 1] = string.format("%d %s", f, s) end
emu.addMemoryCallback(function(addr)
  if L.prgOffset(addr) ~= 0x11 * 0x4000 + 0x0C85 then return end
  local a = emu.getState()["cpu.a"]
  log(string.format("action A=%02X%s", a, force and string.format(" -> %02X", force) or ""))
  if force then emu.setState({["cpu.a"] = force}) end
end, emu.callbackType.exec, 0x8C85, 0x8C85)
for h in string.gmatch(os.getenv("HOOK") or "9DDE,B114", "[^,]+") do
  local addr = tonumber(h, 16)
  emu.addMemoryCallback(function(a)
    if L.prgOffset(a) == 0x11 * 0x4000 + (addr & 0x3FFF) then log(string.format("hook 11:%04X", addr)) end
  end, emu.callbackType.exec, addr, addr)
end
emu.addMemoryCallback(function(addr, value)
  log(string.format("w %04X=%02X pc=%04X", addr, value, emu.getState()["cpu.pc"]))
end, emu.callbackType.write, lo, hi)
emu.addMemoryCallback(function(addr)
  if L.prgOffset(addr) ~= 0x16 * 0x4000 + 0x0656 then return end
  local st = emu.getState()
  log(string.format("msg %02X%02X F9=%02X", st["cpu.x"], st["cpu.a"], emu.read(0xF9, L.mem)))
end, emu.callbackType.exec, 0x8656, 0x8656)
emu.addEventCallback(function()
  f = f + 1
  if f == maxf - 1 then L.write("modoki.txt", table.concat(out, "\n") .. "\n") end
end, emu.eventType.endFrame)
L.drive()
