-- 걷기 구간(dq4walkstate.lua)을 그대로 돌리며 프레임 표본을 SHOT_DIR 에 남긴다(dq4peopleeventcheck.py 가 읽음).
-- 환경 변수: SAMPLE_NEXT(이어 돌릴 Lua 경로), SAMPLE_EVERY(가벼운 표본 간격, 기본 4), SAMPLE_FULL(무거운 표본 간격, 기본 120)
--   lines.bin  가벼운 표본을 이어 붙임: 프레임 u32 LE, WRAM $BC $BD $BE, 전투 중이면 1, CGRAM 0x100~0x1FF, OAM 0x220
--   full-<프레임>.bin  WRAM 0000~9FFF 와 VRAM C000~FFFF(인물 슬롯·칸 목록·OBJ 타일)
local dir = assert(os.getenv('SHOT_DIR'), 'SHOT_DIR')
local every = tonumber(os.getenv('SAMPLE_EVERY') or '4')
local full = tonumber(os.getenv('SAMPLE_FULL') or '120')
local lines = assert(io.open(dir .. '/lines.bin', 'wb'))
local frame = 0
-- 전투 루틴(JSL $208001, 격투장 관전 전투는 06:F2E7 의 JSL $208226)에 들어가 그 호출이 돌아올 때까지를 전투로 본다.
-- 전투는 OBJ 팔레트를 제 색으로 덮는다. 부르는 곳이 여럿이라(걸음 전투, 사건 전투) 들어갈 때 스택의 돌아갈 주소에
-- exec 훅을 건다
local battle, back = 0, nil
local function enter()
  if battle == 1 then return end
  battle = 1
  local sp = emu.getState()['cpu.sp']
  local w = emu.memType.snesWorkRam
  local at = (emu.read(sp + 3, w) << 16 | emu.read(sp + 2, w) << 8 | emu.read(sp + 1, w)) + 1
  back = emu.addMemoryCallback(function()
    battle = 0
    emu.removeMemoryCallback(back, emu.callbackType.exec, at, at)
  end, emu.callbackType.exec, at, at)
end
emu.addMemoryCallback(enter, emu.callbackType.exec, 0x208001, 0x208001)
emu.addMemoryCallback(enter, emu.callbackType.exec, 0x208226, 0x208226)
-- 슬롯 화면(06:D17C 의 JSL $02A8BC)도 OBJ 팔레트를 제 색으로 덮어 전투처럼 센다
emu.addMemoryCallback(enter, emu.callbackType.exec, 0x02A8BC, 0x02A8BC)
local function bytes(from, n, kind)
  local s = {}
  for i = 0, n - 1 do s[#s + 1] = string.char(emu.read(from + i, kind)) end
  return table.concat(s)
end
emu.addEventCallback(function()
  frame = frame + 1
  if frame % every == 0 then
    local w = emu.memType.snesWorkRam
    lines:write(string.char(frame & 0xFF, frame >> 8 & 0xFF, frame >> 16 & 0xFF, frame >> 24 & 0xFF,
                            emu.read(0xBC, w), emu.read(0xBD, w), emu.read(0xBE, w), battle),
                bytes(0x100, 0x100, emu.memType.snesCgRam), bytes(0, 0x220, emu.memType.snesSpriteRam))
    lines:flush()
  end
  if frame % full == 0 then
    local g = assert(io.open(string.format('%s/full-%06d.bin', dir, frame), 'wb'))
    g:write(bytes(0, 0xA000, emu.memType.snesWorkRam), bytes(0xC000, 0x4000, emu.memType.snesVideoRam))
    g:close()
  end
end, emu.eventType.endFrame)
dofile(assert(os.getenv('SAMPLE_NEXT'), 'SAMPLE_NEXT'))
