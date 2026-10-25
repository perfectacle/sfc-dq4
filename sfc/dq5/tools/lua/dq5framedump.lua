-- DQ5: dq5warp.lua 로 순간이동하면서, 목적지에 들어선 뒤 STEP 프레임마다 WRAM·VRAM·CGRAM·OAM 을 SHOT_DIR/frames.bin 에 잇는다.
-- 같은 명령을 ROMPATCH 만 바꿔 두 번 돌리고 sfc/dq5/tools/dq5framediff.py 로 견주면, 기록용 스크립트 없이 패치 하나의 효과만 남는다.
--   TARGET="51/54"   실내 맵 $BC/$BD(16진). 배 선실을 떠난 뒤 이 맵에 들어선 프레임부터 센다
--   FIELDT=1         TARGET 대신 필드($BE bit7 = 0)에 나선 프레임부터 센다
--   STEP, COUNT      덤프 간격(기본 8)과 횟수(기본 40). 열둘째와 마지막 덤프에서 sNNN.png 를 찍는다
--   POKEAT="40:7E3028=0A;7E3088=29"  들어선 뒤 그 프레임에 한 번 WRAM 을 고친다(인물 옮기기 등). 프레임 번호 없는 항목은 앞 번호를 따름
--   COVLO, COVHI     주면 덤프하는 동안 그 범위에서 실행된 PC 와 M·X 를 cover.txt 에 모은다(tools/listing.py 로 읽음)
-- 나머지 환경 변수(TO·FIELD·ROMPATCH·SET·SETTLE·MAXF 등)는 dq5warp.lua 에 그대로 간다. LIBDIR 의 boot.lua 가 dq5warp.lua 여야 한다.
-- frames.bin 한 덤프: WRAM 20000 + VRAM 10000 + CGRAM 200 + OAM 220 바이트.
local m = emu.memType
local tb, td = (os.getenv("TARGET") or "FF/FF"):match("(%x+)/(%x+)")
tb, td = tonumber(tb, 16), tonumber(td, 16)
local fieldT = os.getenv("FIELDT") == "1"
local step, count = tonumber(os.getenv("STEP") or "8"), tonumber(os.getenv("COUNT") or "40")
local out = os.getenv("SHOT_DIR")
local f = assert(io.open(out .. "/frames.bin", "wb"))
local clo, chi = tonumber(os.getenv("COVLO") or "", 16), tonumber(os.getenv("COVHI") or "", 16)
local seenShip, n, k, cover, cb = false, nil, 0, {}, nil
local pokeAt, at = {}, nil
for tok in string.gmatch(os.getenv("POKEAT") or "", "[^;]+") do
  local f0, a, v = tok:match("^(%d+):(%x+)=(%x+)$")
  if f0 then at = tonumber(f0) else a, v = tok:match("^(%x+)=(%x+)$") end
  pokeAt[#pokeAt + 1] = {at, tonumber(a, 16), tonumber(v, 16)}
end

local function onExec(addr)
  local key = addr * 256 + (emu.getState()["cpu.ps"] & 0x30)
  cover[key] = (cover[key] or 0) + 1
end
local function block(t, size)
  local b = {}
  for i = 0, size - 1 do b[#b + 1] = string.char(emu.read(i, t)) end
  return table.concat(b)
end
local function save(name, data)
  local d = assert(io.open(out .. "/" .. name, "wb")); d:write(data); d:close()
end

emu.addEventCallback(function()
  local rd = function(a) return emu.read(a, m.snesMemory) end
  local bc, bd, be = rd(0x7E00BC), rd(0x7E00BD), rd(0x7E00BE)
  -- 세이브스테이트를 불러오기 전 부팅 화면의 값과 섞이지 않게, 배 선실(17)을 본 뒤부터 센다
  if bc == 0x17 then seenShip = true end
  if not seenShip or k >= count then return end
  if not n and ((fieldT and be & 0x80 == 0) or (bc == tb and bd == td and be & 0x80 ~= 0)) then
    n = 0
    if clo then cb = emu.addMemoryCallback(onExec, emu.callbackType.exec, clo, chi) end
  end
  if not n then return end
  n = n + 1
  for _, p in ipairs(pokeAt) do
    if p[1] == n then emu.write(p[2], p[3], m.snesMemory) end
  end
  if n % step ~= 0 then return end
  f:write(block(m.snesWorkRam, 0x20000), block(m.snesVideoRam, 0x10000), block(m.snesCgRam, 0x200), block(m.snesSpriteRam, 0x220))
  k = k + 1
  if k == 12 or k == count then save(string.format("s%03d.png", n), emu.takeScreenshot()) end
  if k < count then return end
  f:close()
  if cb then
    emu.removeMemoryCallback(cb, emu.callbackType.exec, clo, chi)
    local t = {}
    for key, c in pairs(cover) do t[#t + 1] = string.format("%06X %02X %d", key // 256, key % 256, c) end
    table.sort(t)
    save("cover.txt", table.concat(t, "\n") .. "\n")
  end
end, emu.eventType.endFrame)
dofile(os.getenv("LIBDIR") .. "/boot.lua")
