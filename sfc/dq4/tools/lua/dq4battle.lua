-- 걸음 전투 하나를 붙여 이기고 맵으로 돌아오기까지 본다(sfc/dq4/tools/dq4battlecheck.py 가 띄움).
-- STATE 세이브스테이트를 불러 ROMPATCH(파일 오프셋=바이트, 조우 루틴을 정한 무리로 덮는 패치 등)·SET(불러온 뒤 한 번,
-- 7E 뱅크 하위 16비트 주소 =값 |OR &AND)·POKE(매 프레임, CPU 주소=값)를 건다.
--   STEP="down"   전투가 시작될 때까지(01:860D) 이 쪽으로 걷는다
--   TAP=40        전투 동안 KEYS 를 이 프레임마다 하나씩 차례로 누른다. 전투가 끝나 00:82BE(전투 뒤 이어지는 걸음 처리)에
--                 오면 멈춘다
--   KEYS="a"      누를 버튼 차례(쉼표로). 도망은 "down,a"
--   AFTERPATCH    전투가 끝나면 롬(파일 오프셋=바이트)을 이것으로 덮는다. 돌아온 뒤 걸어 볼 때 다시 전투가 걸리지 않게
--   SETTLE=120    전투가 끝나고 쉴 프레임. 그 뒤 기록하고 MOVE 쪽으로 MOVEF 프레임 걸어 조작되는지 본다
--   MAXF=6000     이 프레임에 이르면 그대로 끝낸다
--   KANATABLE="60E800-60EAFF"  전투 글 이름(24:A83C 에 온 길이·바이트)마다 이 범위(가나 글리프 표)를 읽었는지 name 줄로 남긴다.
--                 이름 표에서 한글을 못 찾은 이름만 가나 표로 그린다(dq4battlemsg.asm BmKana). 24:A854 에서 이름 하나가 끝남
-- 결과: SHOT_DIR/battle.txt(단계마다 프레임·맵·칸·곡·무리·금화·전투 슬롯), start.png(전투가 걸린 프레임의 맵 화면),
-- fight.png(전투 시작 120프레임 뒤), after.png(돌아와 SETTLE 뒤),
-- bg3.txt(전투 동안 30프레임마다 「프레임 BG3 타일맵 2KB 16진」 한 줄)
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local L = require("lib")
L.loadState(os.getenv("STATE"))
local m = emu.memType.snesMemory

local patches, sets, pokes, afterpatches = {}, {}, {}, {}
for off, hex in string.gmatch(os.getenv("ROMPATCH") or "", "(%x+)=(%x+)") do patches[#patches + 1] = {tonumber(off, 16), hex} end
for off, hex in string.gmatch(os.getenv("AFTERPATCH") or "", "(%x+)=(%x+)") do afterpatches[#afterpatches + 1] = {tonumber(off, 16), hex} end
for a, op, v in string.gmatch(os.getenv("SET") or "", "(%x+)([=|&])(%x+)") do sets[#sets + 1] = {0x7E0000 + tonumber(a, 16), op, tonumber(v, 16)} end
for a, v in string.gmatch(os.getenv("POKE") or "", "(%x+)=(%x+)") do pokes[#pokes + 1] = {tonumber(a, 16), tonumber(v, 16)} end
local step = os.getenv("STEP") or "down"
local tap = tonumber(os.getenv("TAP") or "40")
local keys = {}
for k in string.gmatch(os.getenv("KEYS") or "a", "[^,]+") do keys[#keys + 1] = k end
local settle = tonumber(os.getenv("SETTLE") or "120")
local move = os.getenv("MOVE") or "up"
local movef = tonumber(os.getenv("MOVEF") or "24")
local maxf = tonumber(os.getenv("MAXF") or "6000")

local function patchRom(list)
  for _, p in ipairs(list) do
    for i = 0, #p[2] / 2 - 1 do
      emu.write(p[1] + i, tonumber(p[2]:sub(i * 2 + 1, i * 2 + 2), 16), emu.memType.snesPrgRom)
    end
  end
end
-- 세이브스테이트를 불러온 뒤 같은 exec 훅에서 롬·WRAM 을 고친다
L.defer(function()
  patchRom(patches)
  for _, s in ipairs(sets) do
    local v = emu.read(s[1], m)
    if s[2] == "=" then v = s[3] elseif s[2] == "|" then v = v | s[3] else v = v & s[3] end
    emu.write(s[1], v, m)
  end
end)

local n, phase, mark = 0, "walk", 0
local started, ended = nil, nil
local log, bg3 = {}, {}
local function rd(a) return emu.read(a, m) end
local function hex(a, len)
  local t = {}
  for i = 0, len - 1 do t[#t + 1] = string.format("%02X", rd(a + i)) end
  return table.concat(t, "")
end
local function record(what)
  log[#log + 1] = string.format("%s f=%d map=%02X/%02X BE=%02X cell=%d,%d field=%d,%d song=%02X group=%s count=%s gold=%s",
    what, n, rd(0x7E00BC), rd(0x7E00BD), rd(0x7E00BE), rd(0x7E3020), rd(0x7E3080),
    rd(0x7E00B6) | rd(0x7E00B7) << 8, rd(0x7E00B8) | rd(0x7E00B9) << 8, rd(0x7E1D8B),
    hex(0x7E1001, 4), hex(0x7E1005, 4), hex(0x7E2019, 3))
end
local done = false
local function finish()
  -- emu.stop 뒤 한 프레임이 더 돌 수 있어 두 번 쓰지 않는다
  if done then return end
  done = true
  L.write("battle.txt", table.concat(log, "\n") .. "\n")
  L.write("bg3.txt", table.concat(bg3, "\n") .. "\n")
  emu.stop(0)
end

local kanaLo, kanaHi = string.match(os.getenv("KANATABLE") or "", "(%x+)-(%x+)")
if kanaLo then
  local naming, kana, bytes = false, 0, ""
  emu.addMemoryCallback(function()
    naming, kana = true, 0
    local len = rd(0x7E0000)
    bytes = hex(0x7E0001, len)
  end, emu.callbackType.exec, 0x24A83C, 0x24A83C)
  emu.addMemoryCallback(function()
    if naming then kana = kana + 1 end
  end, emu.callbackType.read, tonumber(kanaLo, 16), tonumber(kanaHi, 16))
  emu.addMemoryCallback(function()
    if naming then
      naming = false
      log[#log + 1] = string.format("name f=%d bytes=%s kana=%d", n, bytes, kana)
    end
  end, emu.callbackType.exec, 0x24A854, 0x24A854)
end

emu.addMemoryCallback(function()
  if not started then started = n; phase = "battle"; record("start"); L.shot("start.png") end
end, emu.callbackType.exec, 0x01860D, 0x01860D)
emu.addMemoryCallback(function()
  if started and not ended then ended = n; phase = "settle"; mark = n; patchRom(afterpatches) end
end, emu.callbackType.exec, 0x0082BE, 0x0082BE)

emu.addEventCallback(function()
  n = n + 1
  for _, p in ipairs(pokes) do emu.write(p[1], p[2], m) end
  L.release()
  if done then return end
  if n == 1 then record("before") end
  if phase == "walk" then
    L.press({[step] = true})
  elseif phase == "battle" then
    if n == started + 120 then
      L.shot("fight.png")
      log[#log + 1] = string.format("slots f=%d %s", n, hex(0x7E07C0, 64))
    end
    if (n - started) % 30 == 0 then
      local base, t = (rd(0x7E0725) & 0xFC) << 9, {}
      for i = 0, 0x7FF do t[#t + 1] = string.format("%02X", emu.read(base + i, emu.memType.snesVideoRam)) end
      bg3[#bg3 + 1] = string.format("%d %s", n, table.concat(t))
    end
    local k = (n - started) // tap
    if (n - started) % tap < 8 then L.press({[keys[k % #keys + 1]] = true}) end
  elseif phase == "settle" then
    if n >= mark + settle then
      record("after"); L.shot("after.png")
      phase = "move"; mark = n
    end
  elseif phase == "move" then
    if n < mark + movef then
      L.press({[move] = true})
    elseif n >= mark + movef + 30 then
      record("moved")
      finish()
      return
    end
  end
  if n >= maxf then
    record("timeout " .. phase)
    finish()
  end
end, emu.eventType.endFrame)
