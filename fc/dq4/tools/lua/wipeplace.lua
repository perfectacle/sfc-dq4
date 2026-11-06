-- 전멸한 뒤 일행이 어디서 다시 서는지 wipe.txt 에 적는다.
-- STATE 를 불러 WAIT 프레임 뒤 POKE1="6290=0B;60B6=01;60B7=00" 을 한 번 쓰고, 위아래로 걸어 전투가 나면
-- A 를 눌러 싸우게 둔다(맞아서 전멸하도록 HP 를 1 로 둠). LIMIT 프레임까지 60프레임마다, 그리고 맵이 바뀔 때마다
--   at  프레임 $63 $64 $44 $45 $6290 $616A
-- 를 적는다. 전투가 정해진 프레임은 enc, 전멸 처리에 들어간 프레임은 1E:$A3BA(장·불러오기와 같은 시작 루틴) 에서 a3ba.
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local L = require("lib")
local state = L.readFile(os.getenv("STATE"))
local wait = tonumber(os.getenv("WAIT") or "10")
local limit = tonumber(os.getenv("LIMIT") or "6000")
local pokes = {}
for a, v in string.gmatch(os.getenv("POKE1") or "", "(%x+)=(%x+)") do pokes[#pokes + 1] = {tonumber(a, 16), tonumber(v, 16)} end
local log = {}
local function rd(a) return emu.read(a, L.mem) end
local f, fought, lastMap = 0, false, -1

local function hook(off, fn)
  local cpu = 0x8000 + off % 0x4000
  emu.addMemoryCallback(function(addr) if L.prgOffset(addr) == off then fn() end end, emu.callbackType.exec, cpu, cpu)
end

local function at(tag)
  log[#log + 1] = string.format("%s %d %02X %02X %02X %02X %02X %02X", tag, f, rd(0x63), rd(0x64), rd(0x44), rd(0x45),
    rd(0x6290), rd(0x616A))
end

-- 18:$A11A 무리가 정해짐, 1E:$A3BA 시작 루틴(전멸·불러오기)
hook(0x6211A, function() if not fought then fought = true; at("enc") end end)
hook(0x7A3BA, function() at("a3ba") end)

L.defer(function() emu.loadSavestate(state) end)
emu.addEventCallback(function()
  f = f + 1
  L.release()
  if f == wait then
    for _, p in ipairs(pokes) do emu.write(p[1], p[2], L.mem) end
  end
  if f > wait then
    if fought then
      if f % 16 < 4 then L.press({a = true}) end
    else
      L.press((f - wait) % 64 < 32 and {up = true} or {down = true})
    end
  end
  local map = rd(0x63) * 256 + rd(0x64)
  if map ~= lastMap or f % 60 == 0 then lastMap = map; at("at") end
  if f >= limit then
    L.shot("end.png")
    L.write("wipe.txt", table.concat(log, "\n") .. "\n")
    emu.stop(0)
  end
end, emu.eventType.endFrame)
