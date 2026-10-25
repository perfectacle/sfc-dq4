-- DQ5 필드 인물 스프라이트 검증용. 세이브스테이트(STATE)를 불러 SEQ 대로 패드를 누르면서 정한 프레임마다
-- WRAM·VRAM·OAM·CGRAM·화면을 OUT 에 덤프한다(sfc/dq5/tools/dq5sprite.py --compare 가 읽음).
-- 환경 변수:
--   STATE  세이브스테이트 절대 경로      OUT  출력 폴더 절대 경로
--   SEQ    "down@20:30,right@70:30"(버튼@시작 프레임:길이)
--   DUMPF  "5,60"(덤프 프레임 목록)   EVERY·FROM  FROM 프레임부터 EVERY 프레임마다 덤프(DUMPF 와 함께 써도 됨)
--   MAXF   끝 프레임(기본 300)
--   ROMPATCH "1573E6=51;1573EC=51"(파일 오프셋=바이트, 런타임 롬만 고침)  POKE "7E075E=F0"(매 프레임 고정)
-- 걷는 동안 전투가 나지 않게 런타임 롬의 조우 계수표(파일 오프셋 11EA44, 8바이트)를 0 으로 둔다.
local out = assert(os.getenv("OUT"), "OUT")
local f = assert(io.open(assert(os.getenv("STATE"), "STATE"), "rb"))
local state = f:read("*a")
f:close()
local maxf = tonumber(os.getenv("MAXF") or "300")
local every = tonumber(os.getenv("EVERY") or "0")
local from = tonumber(os.getenv("FROM") or "0")
local seq = {}
for b, s, n in string.gmatch(os.getenv("SEQ") or "", "(%a+)@(%d+):(%d+)") do
  seq[#seq + 1] = { b, tonumber(s), tonumber(n) }
end
local dumpf = {}
for a in string.gmatch(os.getenv("DUMPF") or "", "[^,]+") do dumpf[tonumber(a)] = true end
local hook
hook = emu.addMemoryCallback(function()
  emu.removeMemoryCallback(hook, emu.callbackType.exec, 0, 0xFFFFFF)
  emu.loadSavestate(state)
  for i = 0, 7 do emu.write(0x11EA44 + i, 0, emu.memType.snesPrgRom) end
  for off, hex in string.gmatch(os.getenv("ROMPATCH") or "", "(%x+)=(%x+)") do
    local o = tonumber(off, 16)
    for i = 1, #hex, 2 do emu.write(o + (i - 1) // 2, tonumber(hex:sub(i, i + 1), 16), emu.memType.snesPrgRom) end
  end
end, emu.callbackType.exec, 0, 0xFFFFFF)
local pokes = {}
for a, v in string.gmatch(os.getenv("POKE") or "", "(%x+)=(%x+)") do pokes[#pokes + 1] = { tonumber(a, 16), tonumber(v, 16) } end
emu.addEventCallback(function()
  for _, p in ipairs(pokes) do emu.write(p[1], p[2], emu.memType.snesMemory) end
end, emu.eventType.startFrame)
local frame = 0
emu.addEventCallback(function()
  local inp = {}
  for _, p in ipairs(seq) do
    if frame >= p[2] and frame < p[2] + p[3] then inp[p[1]] = true end
  end
  emu.setInput(inp, 0)
end, emu.eventType.inputPolled)
local function dump(name, kind, n)
  local g = assert(io.open(out .. "/" .. name, "wb"))
  local s = {}
  for i = 0, n - 1 do s[#s + 1] = string.char(emu.read(i, kind)) end
  g:write(table.concat(s))
  g:close()
end
emu.addEventCallback(function()
  frame = frame + 1
  if dumpf[frame] or (every > 0 and frame >= from and (frame - from) % every == 0) then
    local k = string.format("%04d", frame)
    dump("w" .. k .. ".bin", emu.memType.snesWorkRam, 0x20000)
    dump("v" .. k .. ".vram", emu.memType.snesVideoRam, 0x10000)
    dump("o" .. k .. ".oam", emu.memType.snesSpriteRam, 544)
    dump("c" .. k .. ".cgram", emu.memType.snesCgRam, 512)
    local g = assert(io.open(out .. "/s" .. k .. ".png", "wb"))
    g:write(emu.takeScreenshot())
    g:close()
  end
  if frame >= maxf then emu.stop(0) end
end, emu.eventType.endFrame)
