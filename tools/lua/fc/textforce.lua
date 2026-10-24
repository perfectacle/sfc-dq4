-- 메시지 출력 16:$8656 에 들어갈 때 X:A 를 MSG(16진 번호)로 바꿔, 아무 메시지나 화면에 띄운다.
-- MSG 를 주지 않으면 바꾸지 않고 기록만 한다. ONCE=0 이면 진입할 때마다(기본은 첫 진입만).
-- ARGS="F9=01,FD=10"(영 페이지 16진)를 주면 같은 순간에 그 값을 써서 치환 제어(F5~F8)의 인자를 정한다.
-- 창 줄 버퍼 $06AA(132바이트)가 바뀐 프레임마다 buf.txt 에 "프레임 16진" 한 줄, 진입 때 $F9-$FF 를 enter.txt 에.
-- HOOK="C01F,8D0D"(CPU 주소)를 주면 그 주소가 실행될 때마다 프레임·PRG 오프셋·A X Y 를 hook.txt 에.
-- 끝에서 입력 드라이버(DRIVER, 예: seq.lua)를 돌린다. 버퍼를 MAXF-1 프레임에 쓴다.
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local L = require("lib")
local msg = os.getenv("MSG") and tonumber(os.getenv("MSG"), 16)
local args = {}
for a, v in string.gmatch(os.getenv("ARGS") or "", "(%x+)=(%x+)") do args[#args + 1] = {tonumber(a, 16), tonumber(v, 16)} end
local entry = 0x16 * 0x4000 + 0x0656
local once = os.getenv("ONCE") ~= "0"
local done, enter = false, {}
emu.addMemoryCallback(function(addr)
  if L.prgOffset(addr) ~= entry or (once and done) then return end
  local st = emu.getState()
  local t = {string.format("in X:A=%02X%02X", st["cpu.x"], st["cpu.a"])}
  for z = 0xF9, 0xFF do t[#t + 1] = string.format("%02X=%02X", z, emu.read(z, L.mem)) end
  for _, p in ipairs(args) do emu.write(p[1], p[2], L.mem) end
  if msg then emu.setState({["cpu.a"] = msg & 0xFF, ["cpu.x"] = msg >> 8}) end
  enter[#enter + 1] = table.concat(t, " ")
  done = true
end, emu.callbackType.exec, 0x8656, 0x8656)
local f, last, log, hooks = 0, nil, {}, {}
for a in string.gmatch(os.getenv("HOOK") or "", "[^,]+") do
  emu.addMemoryCallback(function(addr)
    local st, o = emu.getState(), L.prgOffset(addr)
    hooks[#hooks + 1] = string.format("%d %04X prg=%s A=%02X X=%02X Y=%02X", f, addr,
      o and string.format("%05X", o) or "-", st["cpu.a"], st["cpu.x"], st["cpu.y"])
  end, emu.callbackType.exec, tonumber(a, 16), tonumber(a, 16))
end
local maxf = tonumber(os.getenv("MAXF") or "1500")
emu.addEventCallback(function()
  f = f + 1
  local t = {}
  for i = 0, 131 do t[#t + 1] = string.format("%02X", emu.read(0x06AA + i, L.mem)) end
  local s = table.concat(t)
  if s ~= last then log[#log + 1] = f .. " " .. s; last = s end
  if f == maxf - 1 then
    L.write("buf.txt", table.concat(log, "\n") .. "\n")
    L.write("hook.txt", table.concat(hooks, "\n") .. "\n")
    L.write("enter.txt", table.concat(enter, "\n") .. "\n")
  end
end, emu.eventType.endFrame)
L.drive()
