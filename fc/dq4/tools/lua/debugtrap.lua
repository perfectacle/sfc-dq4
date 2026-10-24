-- PRG 롬 오프셋으로 고른 명령이 실행될 때마다 레지스터·RAM·스택을 적는다.
-- probe/trace.lua 는 CPU 주소로 걸어 같은 주소의 다른 뱅크도 잡으므로, 여기서는 실행 순간의 PRG 오프셋이
-- 맞는 것만 남긴다(뱅크 10 의 $81B9 와 뱅크 08 의 $81B9 를 가름).
-- 환경 변수:
--   TRAP=401B9,6ABA9   PRG 롬 오프셋(16진, 쉼표). CPU 주소는 오프셋 % 4000 + 8000(고정 뱅크면 C000)
--   LOG=6E0B,006E      적을 CPU 주소(16진, 쉼표)
--   STACK=8            스택 맨 위에서 적을 바이트 수(누가 불렀는지 볼 때)
--   LIMIT=200          적을 줄 수 상한
--   SHOTS_AFTER=60     처음 걸린 뒤 이 프레임마다 shot-N.png 를 4장까지
--   TRAP_DRIVER=path   이어서 돌릴 Lua(예: fc/dq4/tools/lua/debugpad.lua). 없으면 입력 드라이버(DRIVER)
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local L = require("lib")
local logs, lines, n, first, shots, written = {}, {}, 0, nil, 0, 0
for a in (os.getenv("LOG") or ""):gmatch("%x+") do logs[#logs + 1] = tonumber(a, 16) end
local depth = tonumber(os.getenv("STACK") or "8")
local limit = tonumber(os.getenv("LIMIT") or "200")
local every = tonumber(os.getenv("SHOTS_AFTER") or "0")
for a in (os.getenv("TRAP") or ""):gmatch("%x+") do
  local off = tonumber(a, 16)
  local cpu = off % 0x4000 + ((off // 0x4000) % 16 == 15 and 0xC000 or 0x8000)
  emu.addMemoryCallback(function()
    if L.prgOffset(cpu) ~= off or #lines >= limit then return end
    first = first or n
    local st = emu.getState()
    local t = {string.format("%d %05X A=%02X X=%02X Y=%02X S=%02X", n, off, st["cpu.a"], st["cpu.x"], st["cpu.y"], st["cpu.sp"])}
    for _, x in ipairs(logs) do t[#t + 1] = string.format("%04X=%02X", x, emu.read(x, L.mem)) end
    local s = {}
    for i = 1, depth do s[#s + 1] = string.format("%02X", emu.read(0x100 + ((st["cpu.sp"] + i) & 0xFF), L.mem)) end
    t[#t + 1] = "stack=" .. table.concat(s, " ")
    lines[#lines + 1] = table.concat(t, " ")
  end, emu.callbackType.exec, cpu, cpu)
end
emu.addEventCallback(function()
  n = n + 1
  if first and every > 0 and shots < 4 and n == first + every * (shots + 1) then
    shots = shots + 1
    L.shot("shot-" .. shots .. ".png")
  end
  -- 드라이버가 언제 멈출지 모르므로 줄이 늘 때마다 다시 쓴다
  if n == 1 or #lines > written then
    written = #lines
    L.write("debugtrap.txt", table.concat(lines, "\n") .. "\n")
  end
end, emu.eventType.endFrame)
if os.getenv("TRAP_DRIVER") then dofile(os.getenv("TRAP_DRIVER")) else L.drive() end
