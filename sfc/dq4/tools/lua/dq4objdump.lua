-- DQ5 필드 세이브스테이트에서 주인공을 아래·왼쪽·위·오른쪽으로 걷게 한 뒤 멈춘 순간의
-- VRAM·OAM·CGRAM 을 덤프한다(tools/dq4spritelab.py hero 가 읽음). 주인공 OBJ 를 숨긴 화면(nohero.png)도 찍는다.
-- 환경 변수: STATE(필드 세이브스테이트 절대 경로), OUT(출력 폴더 절대 경로)
local out = assert(os.getenv("OUT"), "OUT")
local f = assert(io.open(assert(os.getenv("STATE"), "STATE"), "rb"))
local state = f:read("*a")
f:close()
local hook
hook = emu.addMemoryCallback(function()
  emu.removeMemoryCallback(hook, emu.callbackType.exec, 0, 0xFFFFFF)
  emu.loadSavestate(state)
  -- 조우 계수표를 0 으로 두어 걷는 동안 전투가 나지 않게 한다(런타임 롬만, 파일은 그대로)
  for i = 0, 7 do emu.write(0x11EA44 + i, 0, emu.memType.snesPrgRom) end
end, emu.callbackType.exec, 0, 0xFFFFFF)
local frame = 0
local plan = { { "down", 20, 60 }, { "left", 80, 120 }, { "up", 140, 180 }, { "right", 200, 240 } }
emu.addEventCallback(function()
  local inp = {}
  for _, p in ipairs(plan) do inp[p[1]] = frame >= p[2] and frame < p[2] + 12 end
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
  if frame >= 9 and frame <= 12 then
    for i = 0, 7 do emu.write(i * 4 + 1, 240, emu.memType.snesSpriteRam) end
  end
end, emu.eventType.startFrame)
emu.addEventCallback(function()
  frame = frame + 1
  if frame == 12 then
    local g = assert(io.open(out .. "/nohero.png", "wb"))
    g:write(emu.takeScreenshot())
    g:close()
  end
  for _, p in ipairs(plan) do
    if frame == p[3] then
      dump(p[1] .. "-vram.bin", emu.memType.snesVideoRam, 0x10000)
      dump(p[1] .. "-oam.bin", emu.memType.snesSpriteRam, 544)
      dump(p[1] .. "-cgram.bin", emu.memType.snesCgRam, 512)
      local g = assert(io.open(out .. "/" .. p[1] .. ".png", "wb"))
      g:write(emu.takeScreenshot())
      g:close()
    end
  end
  if frame == 250 then emu.stop(0) end
end, emu.eventType.endFrame)
