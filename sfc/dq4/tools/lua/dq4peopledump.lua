-- 필드 세이브스테이트를 불러 몇 프레임 둔 뒤 VRAM·OAM·CGRAM·WRAM 과 화면을 덤프한다(dq4peoplecheck.py 가 읽음).
-- 환경 변수: STATE(세이브스테이트 절대 경로), OUT(출력 폴더 절대 경로), WAIT(덤프할 프레임, 기본 30),
--            POKE(매 프레임 쓸 "7EXXXX=YY;…", 밤·낮 고정용)
local out = assert(os.getenv("OUT"), "OUT")
local f = assert(io.open(assert(os.getenv("STATE"), "STATE"), "rb"))
local state = f:read("*a")
f:close()
local wait = tonumber(os.getenv("WAIT") or "30")
local pokes = {}
for a, v in string.gmatch(os.getenv("POKE") or "", "(%x+)=(%x+)") do pokes[#pokes + 1] = { tonumber(a, 16), tonumber(v, 16) } end
local hook
hook = emu.addMemoryCallback(function()
  emu.removeMemoryCallback(hook, emu.callbackType.exec, 0, 0xFFFFFF)
  emu.loadSavestate(state)
end, emu.callbackType.exec, 0, 0xFFFFFF)
local function dump(name, kind, n)
  local g = assert(io.open(out .. "/" .. name, "wb"))
  local s = {}
  for i = 0, n - 1 do s[#s + 1] = string.char(emu.read(i, kind)) end
  g:write(table.concat(s))
  g:close()
end
local frame = 0
emu.addEventCallback(function()
  frame = frame + 1
  for _, p in ipairs(pokes) do emu.write(p[1], p[2], emu.memType.snesMemory) end
  if frame == wait then
    dump("vram.bin", emu.memType.snesVideoRam, 0x10000)
    dump("oam.bin", emu.memType.snesSpriteRam, 0x220)
    dump("cgram.bin", emu.memType.snesCgRam, 0x200)
    dump("wram.bin", emu.memType.snesWorkRam, 0x20000)
    local g = assert(io.open(out .. "/screen.png", "wb"))
    g:write(emu.takeScreenshot())
    g:close()
    emu.stop(0)
  end
end, emu.eventType.endFrame)
