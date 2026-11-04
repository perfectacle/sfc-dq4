-- dq4kind14check.py 가 부른다. 실내 맵 순간이동(NEXT = dq4bg3slotwarp.lua)을 그대로 돌리며, 움직이는 타일 종류 14 의
-- 사본 7E:3D14~3E73 과 창 글자 대기열 변수(VARS)를 프레임마다 SHOT_DIR/kind14.txt 에 적는다(FLUSH 프레임마다 다시 씀).
--   「프레임 w03=수 wother=수 vars=주소:값,…」          사본 자리를 썼거나 VRAM 주소를 넣은 프레임: 쓴 횟수(뱅크 03
--                                                     코드 / 그 밖)와 프레임 끝의 변수
--   「프레임 copy 352바이트 16진」                      뱅크 03 이 쓴 프레임의 끝 사본
--   「프레임 vmadd 주소,…」                             창 글자 코드(뱅크 BANK)가 $2116 에 넣은 VRAM 워드 주소@넣은 PC(처음 64개)
--   「프레임 entry VRAM주소:Y:머리,…」                  PC 가 ENTRY 인 $2116 쓰기(대기열 항목 하나)의 주소, 항목 자리 Y,
--                                                     머리 워드(7E:3EB2+Y, 낮은 바이트 방식·높은 바이트 칸 수)
--   「프레임 tmdiff 수 첫」                            프레임 끝에 BG3 타일맵($0725 자리 2KB)이 버퍼 7E:5000 과 다른
--                                                     바이트 수와 첫 자리
-- VARS 는 「주소:바이트수」 를 쉼표로(예: 3D62:1,3D5C:2).
local m = emu.memType.snesMemory
local vram = emu.memType.snesVideoRam
local out = os.getenv('SHOT_DIR') .. '/kind14.txt'
local flush = tonumber(os.getenv('FLUSH') or '30')
local bank = tonumber(os.getenv('BANK') or '60', 16)
local vars = {}
for a, n in string.gmatch(os.getenv('VARS') or '', '(%x+):(%d+)') do vars[#vars + 1] = {tonumber(a, 16), tonumber(n)} end
local entry = tonumber(os.getenv('ENTRY') or '0', 16)
local f, log = 0, {}
local ents = {}
local w03, wother, vm, lo = 0, 0, {}, nil

local function pcbank() return emu.getState()['cpu.k'] end

emu.addMemoryCallback(function()
  if pcbank() == 0x03 then w03 = w03 + 1 else wother = wother + 1 end
end, emu.callbackType.write, 0x7E3D14, 0x7E3E73)

emu.addMemoryCallback(function(addr, value)
  if pcbank() ~= bank then return end
  if addr & 0xFFFF == 0x2116 then lo = value
  elseif lo then
    local st = emu.getState()
    local pc, a = st['cpu.pc'] & 0xFFFF, value << 8 | lo
    if #vm < 64 then vm[#vm + 1] = string.format('%04X@%04X', a, pc) end
    if pc == entry and #ents < 16 then
      local y = st['cpu.y'] & 0xFFFF
      local h = emu.read(0x7E0000 + ((0x3EB2 + y) & 0xFFFF), m) | emu.read(0x7E0000 + ((0x3EB3 + y) & 0xFFFF), m) << 8
      ents[#ents + 1] = string.format('%04X:%04X:%04X', a, y, h)
    end
    lo = nil
  end
end, emu.callbackType.write, 0x002116, 0x002117)

emu.addEventCallback(function()
  f = f + 1
  local t = {}
  for _, v in ipairs(vars) do
    local x = 0
    for i = v[2] - 1, 0, -1 do x = x << 8 | emu.read(0x7E0000 + v[1] + i, m) end
    t[#t + 1] = string.format('%04X:%0' .. (v[2] * 2) .. 'X', v[1], x)
  end
  if w03 > 0 or wother > 0 or #vm > 0 then
    log[#log + 1] = string.format('%d w03=%d wother=%d vars=%s', f, w03, wother, table.concat(t, ','))
  end
  if w03 > 0 then
    local c = {}
    for i = 0x3D14, 0x3E73 do c[#c + 1] = string.format('%02X', emu.read(0x7E0000 + i, m)) end
    log[#log + 1] = string.format('%d copy %s', f, table.concat(c))
  end
  if #vm > 0 then log[#log + 1] = string.format('%d vmadd %s', f, table.concat(vm, ',')) end
  if #ents > 0 then log[#log + 1] = string.format('%d entry %s', f, table.concat(ents, ',')) end
  local base = (emu.read(0x7E0725, m) & 0xFC) << 9
  local diff, first = 0, nil
  for i = 0, 0x7FF do
    if emu.read(base + i, vram) ~= emu.read(0x7E5000 + i, m) then
      diff = diff + 1
      first = first or i
    end
  end
  if diff > 0 then log[#log + 1] = string.format('%d tmdiff %d %04X', f, diff, first) end
  w03, wother, vm, lo, ents = 0, 0, {}, nil, {}
  if f % flush == 0 then
    local h = io.open(out, 'w')
    h:write(table.concat(log, '\n') .. '\n')
    h:close()
  end
end, emu.eventType.endFrame)

dofile(os.getenv('NEXT'))
