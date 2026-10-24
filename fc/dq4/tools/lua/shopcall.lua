-- PC 가 AT(16진 CPU 주소, 쉼표로 여럿)에 닿을 때마다 A X Y, 스택의 복귀 주소(JSR 다음 바이트 − 1),
-- X 가 가리키는 영 페이지 두 바이트(`$C3EA` 의 포인터), 그때의 뱅크 `$0507` 을 calls.txt 에 적는다.
-- ONLYA 를 주면 A 가 그 값일 때만 적는다. 기록은 LIMIT(기본 400)줄, MAXF−1 프레임에 쓴다.
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local L = require("lib")
local f, log = 0, {}
local limit = tonumber(os.getenv("LIMIT") or "400")
local onlyA = os.getenv("ONLYA") and tonumber(os.getenv("ONLYA"), 16)
for a in string.gmatch(os.getenv("AT"), "[^,]+") do
  local addr = tonumber(a, 16)
  emu.addMemoryCallback(function()
    if #log >= limit then return end
    local st = emu.getState()
    local A, X, Y, S = st["cpu.a"], st["cpu.x"], st["cpu.y"], st["cpu.sp"]
    if onlyA and A ~= onlyA then return end
    local ret = emu.read(0x101 + S, L.mem) | emu.read(0x102 + S, L.mem) << 8
    local ptr = emu.read(X, L.mem) | emu.read((X + 1) & 0xFF, L.mem) << 8
    log[#log + 1] = string.format("%d %s A=%02X X=%02X Y=%02X ret=%04X bank=%02X ptr=%04X", f, a, A, X, Y, ret,
      emu.read(0x0507, L.mem), ptr)
  end, emu.callbackType.exec, addr, addr)
end
local maxf = tonumber(os.getenv("MAXF") or "1500")
emu.addEventCallback(function()
  f = f + 1
  if f == maxf - 1 then L.write("calls.txt", table.concat(log, "\n") .. "\n") end
end, emu.eventType.endFrame)
L.drive()
