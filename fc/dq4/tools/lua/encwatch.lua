-- 특수 전투·デスパレス 대화·へんげのつえ·$6E44·1E:$A5AD 를 지켜 encwatch.txt 에 적는 프로브. DRIVER(warp.lua·seq.lua)와 함께 쓴다.
-- 줄(앞 숫자는 프레임):
--   a1ad A                       18:$A1AD 특수 전투 진입(A = 번호)
--   talk $DA $63 $64 $6296 $6297 15:$B10E 말 걸기 앞(A = 겉모습이 $DA 로)
--   look Y                       08:$B752·$B755 デスパレス 표에서 고른 특수 전투 번호
--   w6296 / w6297 값 PRG 오프셋     쓰기
--   staff $63 $64 $44 $45         1E:$B02F へんげのつえ 처리기 진입
--   a5ad / a3ba / a1c9            1E:$A5AD(지우기)·1E:$A3BA(1E 함수 22)·1E:$A1C9(1E 함수 15, 전투 뒤 필드 화면) 진입.
--                                a5ad 와 a3c9(지운 뒤)에는 $0515 $6E42 $6E41 $6BEB $6E05
--   w6E44 값 PRG / r6E44 PRG 값    $6E44 쓰기·읽기(읽기는 PRG 오프셋마다 처음 RD44 번만)
--   msg 번호                      16:$8656
-- POKE="6296=78;..." 는 POKEFROM(기본 0) 프레임부터 프레임마다 쓴다. POKE1 은 POKEFROM 프레임에 한 번.
-- POKE44=NN 이면 18:$A123 에서 $6E44 를 NN 으로 바꾼다(enc.lua 의 FORCE44 와 같음).
-- ROUTE="05,0C;0A,0C;..." 이면 ROUTEFROM(기본 60) 프레임부터 맵 좌표 $44/$45 가 차례로 그 자리가 되도록 걷는다
--   (X 를 먼저 맞추고 Y). 40프레임 동안 자리가 안 바뀌면 B 를 한 번 눌러 창을 닫고 다시 걷는다.
--   다 걸으면 「route 끝 X Y」를 적는다. 입력은 inputPolled 에서 DRIVER 의 입력 위에 덮어쓴다.
-- MAXF-1 프레임에 encwatch.txt 를 쓴다.
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local L = require("lib")
local function rd(a) return emu.read(a, L.mem) end
local maxf = tonumber(os.getenv("MAXF") or "1500")
local from = tonumber(os.getenv("POKEFROM") or "0")
local rd44 = tonumber(os.getenv("RD44") or "1")
local poke44 = os.getenv("POKE44") and tonumber(os.getenv("POKE44"), 16)
local every, once = {}, {}
for a, v in string.gmatch(os.getenv("POKE") or "", "(%x+)=(%x+)") do every[#every + 1] = {tonumber(a, 16), tonumber(v, 16)} end
for a, v in string.gmatch(os.getenv("POKE1") or "", "(%x+)=(%x+)") do once[#once + 1] = {tonumber(a, 16), tonumber(v, 16)} end
local n, log, pc, seen44 = 0, {}, 0, {}
local function add(s) log[#log + 1] = string.format("%d %s", n, s) end
local function off(a) local o = L.prgOffset(a); return o and string.format("%05X", o) or string.format("%04X", a) end

local function hook(o, fn)
  local cpu = (o // 0x4000 == 0x0F or o // 0x4000 == 0x1F) and 0xC000 + o % 0x4000 or 0x8000 + o % 0x4000
  emu.addMemoryCallback(function(addr) if L.prgOffset(addr) == o then fn(emu.getState()) end end,
    emu.callbackType.exec, cpu, cpu)
end

emu.addMemoryCallback(function(a) pc = a end, emu.callbackType.exec, 0, 0xFFFF)
hook(0x621AD, function(s) add(string.format("a1ad %02X", s["cpu.a"])) end)
hook(0x5710E, function(s)
  add(string.format("talk %02X %02X %02X %02X %02X", s["cpu.a"], rd(0x63), rd(0x64), rd(0x6296), rd(0x6297)))
end)
hook(0x23752, function(s) add(string.format("look %02X", s["cpu.y"])) end)
hook(0x23755, function(s) add(string.format("look %02X", s["cpu.y"])) end)
hook(0x7B02F, function() add(string.format("staff %02X %02X %02X %02X", rd(0x63), rd(0x64), rd(0x44), rd(0x45))) end)
local function clr() return string.format("%02X %02X %02X %02X %02X", rd(0x0515), rd(0x6E42), rd(0x6E41), rd(0x6BEB), rd(0x6E05)) end
hook(0x7A5AD, function() add("a5ad " .. clr()) end)
hook(0x7A3C9, function() add("a3c9 " .. clr()) end)
hook(0x7A3BA, function() add("a3ba") end)
hook(0x7A1C9, function() add("a1c9") end)
hook(0x62123, function()
  if poke44 then emu.write(0x6E44, poke44, L.mem) end
end)
hook(0x58656, function(s) add(string.format("msg %02X%02X", s["cpu.x"], s["cpu.a"])) end)
for _, a in ipairs({0x6296, 0x6297}) do
  emu.addMemoryCallback(function(_, v) add(string.format("w%04X %02X %s", a, v, off(pc))) end, emu.callbackType.write, a, a)
end
emu.addMemoryCallback(function(_, v) add(string.format("w6E44 %02X %s", v, off(pc))) end, emu.callbackType.write, 0x6E44, 0x6E44)
emu.addMemoryCallback(function(_, v)
  local k = off(pc)
  seen44[k] = (seen44[k] or 0) + 1
  if seen44[k] <= rd44 then add(string.format("r6E44 %s %02X", k, v)) end
end, emu.callbackType.read, 0x6E44, 0x6E44)

local route, wp, lastXY, lastMove, btn = {}, 1, -1, 0, nil
for x, y in string.gmatch(os.getenv("ROUTE") or "", "(%x%x),(%x%x)") do route[#route + 1] = {tonumber(x, 16), tonumber(y, 16)} end
local routeFrom = tonumber(os.getenv("ROUTEFROM") or "60")
local function step()
  btn = nil
  if #route == 0 or n < routeFrom or wp > #route then return end
  local x, y = rd(0x44), rd(0x45)
  if x * 256 + y ~= lastXY then lastXY, lastMove = x * 256 + y, n end
  while route[wp] and route[wp][1] == x and route[wp][2] == y do wp = wp + 1 end
  local t = route[wp]
  if not t then add(string.format("route 끝 %02X %02X", x, y)); return end
  if n - lastMove > 40 then
    if n - lastMove < 47 then btn = {b = true} else lastMove = n end
    return
  end
  btn = {[t[1] > x and "right" or t[1] < x and "left" or t[2] > y and "down" or "up"] = true}
end
emu.addEventCallback(function() if btn then emu.setInput(btn, 0) end end, emu.eventType.inputPolled)

emu.addEventCallback(function()
  n = n + 1
  step()
  if n == from then for _, p in ipairs(once) do emu.write(p[1], p[2], L.mem) end end
  if n >= from then for _, p in ipairs(every) do emu.write(p[1], p[2], L.mem) end end
  if n == maxf - 1 then L.write("encwatch.txt", table.concat(log, "\n") .. "\n") end
end, emu.eventType.endFrame)
L.drive()
