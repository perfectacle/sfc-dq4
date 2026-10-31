-- 걸음 루틴 받침 감시: 00:C656~C686(뱅크 80 거울도, 기본 루틴 C687 앞까지)의 실행 PC 마다 횟수와 처음 프레임, 그 범위의 읽기 횟수를 센다.
-- STEPBODY(16진 24비트)를 주면 그 자리에 들어올 때마다 P·DB·D·S·A·$00·$C1·$C2 와 스택의 돌아갈 자리 둘
-- (JSL 이 쌓은 24비트, 그 위의 16비트)을 처음 8번까지 적는다. 결과는 SHOT_DIR/step.txt(60프레임마다 다시 씀).
-- 드라이버(LIBDIR/boot.lua, 보통 dq5warp.lua) 뒤에 얹는다. dq5stepcheck.py 가 부른다.
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local L = require("lib")
local m = emu.memType.snesMemory
local n, reads, execs, order, entries = 0, 0, {}, {}, {}
local body = tonumber(os.getenv("STEPBODY") or "", 16)

for _, base in ipairs({0, 0x800000}) do
  emu.addMemoryCallback(function()
    local st = emu.getState()
    local pc = st["cpu.k"] * 0x10000 + st["cpu.pc"]
    local e = execs[pc]
    if not e then
      e = {n = 0, f = n}
      execs[pc] = e
      order[#order + 1] = pc
    end
    e.n = e.n + 1
  end, emu.callbackType.exec, base + 0xC656, base + 0xC686)
  emu.addMemoryCallback(function() reads = reads + 1 end, emu.callbackType.read, base + 0xC656, base + 0xC686)
end

if body then
  emu.addMemoryCallback(function()
    if #entries >= 8 then return end
    local st = emu.getState()
    local sp = st["cpu.sp"]
    local ret = emu.read(sp + 3, m) << 16 | emu.read(sp + 2, m) << 8 | emu.read(sp + 1, m)
    local outer = emu.read(sp + 5, m) << 8 | emu.read(sp + 4, m)
    entries[#entries + 1] = string.format("entry f=%d P=%02X DB=%02X D=%04X S=%04X A=%04X 00=%02X C1=%02X C2=%02X ret=%06X outer=%04X",
      n, st["cpu.ps"], st["cpu.dbr"], st["cpu.d"], sp, st["cpu.a"], emu.read(0x7E0000, m), emu.read(0x7E00C1, m),
      emu.read(0x7E00C2, m), ret, outer)
  end, emu.callbackType.exec, body, body)
end

emu.addEventCallback(function()
  n = n + 1
  if n % 60 == 0 then
    local o = {string.format("frames=%d reads=%d", n, reads)}
    for _, pc in ipairs(order) do o[#o + 1] = string.format("exec %06X n=%d first=f%d", pc, execs[pc].n, execs[pc].f) end
    for _, line in ipairs(entries) do o[#o + 1] = line end
    L.write("step.txt", table.concat(o, "\n") .. "\n")
  end
end, emu.eventType.endFrame)
dofile(os.getenv("LIBDIR") .. "/boot.lua")
