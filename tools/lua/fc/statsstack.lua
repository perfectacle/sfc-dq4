-- PC 가 AT(CPU 주소, 쉼표로 여럿)에 닿을 때마다 프레임, 뱅크($0507), A X Y, LOG 주소들의 바이트,
-- 스택 위 STACK 바이트(기본 12, 복귀 주소로 부른 곳을 찾는 데 씀)를 stack.txt 에 쓴다(MAXF-1 프레임, LIMIT 줄까지).
-- LOG="79:2,6E0E" 처럼 주소:길이(16진 주소, 길이 생략 시 1). 끝에서 DRIVER 를 돌린다.
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local L = require("lib")
local f, log = 0, {}
local limit = tonumber(os.getenv("LIMIT") or "2000")
local depth = tonumber(os.getenv("STACK") or "12")
local extra = {}
for a, len in string.gmatch(os.getenv("LOG") or "", "(%x+):?(%d*)") do extra[#extra + 1] = {a, tonumber(a, 16), tonumber(len) or 1} end
local function hex(a, n)
  local t = {}
  for k = 0, n - 1 do t[#t + 1] = string.format("%02X", emu.read(a + k, L.mem)) end
  return table.concat(t)
end
for a in string.gmatch(os.getenv("AT"), "[^,]+") do
  local addr = tonumber(a, 16)
  emu.addMemoryCallback(function()
    if #log >= limit then return end
    local s = emu.getState()
    local t = {string.format("%d %s b=%02X A=%02X X=%02X Y=%02X", f, a, emu.read(0x0507, L.mem), s["cpu.a"], s["cpu.x"], s["cpu.y"])}
    for _, x in ipairs(extra) do t[#t + 1] = x[1] .. "=" .. hex(x[2], x[3]) end
    local sp = s["cpu.sp"]
    local st = {}
    for k = 1, depth do if sp + k <= 0xFF then st[#st + 1] = string.format("%02X", emu.read(0x100 + sp + k, L.mem)) end end
    t[#t + 1] = "st=" .. table.concat(st)
    log[#log + 1] = table.concat(t, " ")
  end, emu.callbackType.exec, addr, addr)
end
local maxf = tonumber(os.getenv("MAXF") or "1500")
emu.addEventCallback(function()
  f = f + 1
  if f == maxf - 1 then L.write("stack.txt", table.concat(log, "\n") .. "\n") end
end, emu.eventType.endFrame)
L.drive()
