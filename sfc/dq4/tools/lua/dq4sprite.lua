-- DQ5 필드에서 주인공 그림을 DQ4 인물 스프라이트로 바꿔 보여 준다. 영구 삽입이 아니라 Lua 가
-- 프레임마다 VRAM D000~D0BF(OBJ 타일 80~85)·OAM 0~7·OBJ 팔레트 3 을 덮어쓰는 실험이다.
-- 환경 변수: DATA(tools/dq4spritelab.py data 가 만든 .lua 절대 경로), STATE(메뉴가 닫힌 필드
-- 세이브스테이트 절대 경로), OUT(스크린샷 폴더), TEST=1 이면 180프레임 동안 4방향 자동 보행 후 종료.
local out = assert(os.getenv("OUT"), "OUT")
local f = assert(io.open(assert(os.getenv("STATE"), "STATE"), "rb"))
local state = f:read("*a")
f:close()
local D = dofile(assert(os.getenv("DATA"), "DATA"))
local hook
hook = emu.addMemoryCallback(function()
  emu.removeMemoryCallback(hook, emu.callbackType.exec, 0, 0xFFFFFF)
  emu.loadSavestate(state)
  for i = 0, 7 do emu.write(0x11EA44 + i, 0, emu.memType.snesPrgRom) end
end, emu.callbackType.exec, 0, 0xFFFFFF)
local frame = 0
local auto = os.getenv("TEST") == "1"
local m = emu.memType.snesMemory
local o = emu.memType.snesSpriteRam
local previous = nil
local gait = 0
local log = {}
local function screenshot(name)
  local g = assert(io.open(out .. "/" .. name .. ".png", "wb"))
  g:write(emu.takeScreenshot())
  g:close()
end
emu.addEventCallback(function()
  if frame < 3 then
    emu.setInput({}, 0)
  elseif auto then
    emu.setInput({
      right = frame >= 30 and frame < 60,
      down = frame >= 60 and frame < 90,
      left = frame >= 90 and frame < 120,
      up = frame >= 120 and frame < 150,
    }, 0)
  end
end, emu.eventType.inputPolled)
emu.addEventCallback(function()
  frame = frame + 1
  if frame < 2 then return end
  if emu.read(0x7E00BC, m) ~= 1 or emu.read(0x7E00BD, m) ~= 0 then return end -- 필드 01/00 만
  -- 원래 주인공의 머리 타일 쌍(000·001)이 슬롯 0·1 에 있을 때만 바꾼다
  if ((emu.read(2, o) ~= 0 or emu.read(6, o) ~= 1) and (emu.read(2, o) ~= 1 or emu.read(6, o) ~= 0))
      or (emu.read(3, o) & 0xBF) ~= 0x30 then
    return
  end
  local x = math.min(emu.read(0, o), emu.read(4, o))
  local y = emu.read(1, o)
  local pos = 0
  for _, a in ipairs({ 0x3000, 0x3020, 0x3060, 0x3080 }) do pos = pos * 256 + emu.read(0x7E0000 + a, m) end
  local moving = previous ~= nil and previous ~= pos
  previous = pos
  if moving then gait = gait + 1 else gait = 0 end
  local direction = emu.read(0x7E31E0, m) & 0xF0
  local row = ({ [0x40] = 0, [0x20] = 1, [0x10] = 2, [0x80] = 3 })[direction] or 0
  local pose = moving and (math.floor(gait / 8) % 2 + 1) or 0
  local data = D.frames[row * 3 + pose + 1]
  for i, v in ipairs(data) do emu.write(0xD000 + i - 1, v, emu.memType.snesVideoRam) end
  -- 팔레트 4~7 은 색 연산에 들어가므로 3 을 쓴다
  for i, v in ipairs(D.pal) do emu.write(0x160 + i - 1, v, emu.memType.snesCgRam) end
  for i = 6, 7 do emu.write(i * 4 + 1, 240, o) end
  for j = 0, 5 do
    emu.write(j * 4, (x + j % 2 * 8) & 255, o)
    emu.write(j * 4 + 1, (y + math.floor(j / 2) * 8) & 255, o)
    emu.write(j * 4 + 2, 128 + j, o)
    emu.write(j * 4 + 3, 0x36, o)
    local addr = 512 + math.floor(j / 4)
    local shift = j % 4 * 2
    emu.write(addr, emu.read(addr, o) & (~(3 << shift) & 255), o)
  end
end, emu.eventType.startFrame)
emu.addEventCallback(function()
  if not auto and (frame == 30 or frame == 120) then screenshot("gui-" .. frame) end
  if auto and frame % 30 == 0 then
    screenshot("walk-" .. frame)
    log[#log + 1] = string.format("frame=%d x=%d y=%d direction=%02X", frame,
      emu.read(0x7E3020, m), emu.read(0x7E3080, m), emu.read(0x7E31E0, m))
  end
  if auto and frame == 180 then
    local g = assert(io.open(out .. "/walk-test.txt", "w"))
    g:write(table.concat(log, "\n"))
    g:close()
    emu.stop(0)
  end
end, emu.eventType.endFrame)
