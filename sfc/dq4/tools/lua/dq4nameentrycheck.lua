-- dq4nameentrycheck.py 가 만든 사례를 실제 입력으로 실행하고 조합 상태·저장 이름을 확인한다.
package.path = os.getenv('LIBDIR') .. '/?.lua;' .. package.path
local L = require('lib')
local cfg = dofile(os.getenv('NAME_ENTRY_CASES'))
local m = emu.memType.snesMemory
for a = 0, 0x1FFF do emu.write(a, 0, emu.memType.snesSaveRam) end
local frame, entered, index, step, lastloop = 0, false, 1, 0, -100
local final, saved_at = false, nil
local log = {}
local function read(a) return emu.read(a, m) end
local function word(a) return emu.read16(a, m) end
local function current()
  local out = {}
  for i = 0, word(0x7FF000) - 1 do out[#out + 1] = word(0x7FF002 + i * 2) end
  local sp = word(0x7FF00A)
  if sp > 0 then
    local a = 0x7FF00C + (sp - 1) * 4
    local c, v, j = read(a), read(a + 1), read(a + 2)
    local glyph
    if v == 255 then glyph = cfg.initials[c + 1]
    elseif c == 255 then glyph = cfg.medials[v + 1]
    else glyph = cfg.syllables[(c * 21 + v) * 28 + j] end
    out[#out + 1] = glyph or -1
  end
  return out
end
local function equal(a, b)
  if #a ~= #b then return false end
  for i = 1, #a do if a[i] ~= b[i] then return false end end
  return true
end
local function bytes(a, n)
  local out = {}
  for i = 0, n - 1 do out[#out + 1] = read(a + i) end
  return out
end
local function record(ok, label, got)
  log[#log + 1] = string.format('%s %s got=%s', ok and 'PASS' or 'FAIL', label, table.concat(got, ','))
end
emu.addMemoryCallback(function()
  entered = true
  lastloop = frame
  local case = cfg.cases[index]
  if step == #case.keys then
    local got = current()
    record(equal(got, case.expected), case.label, got)
    index = index + 1
    step = 0
    if index > #cfg.cases then
      final = true
      L.shot('entry.png')
      L.dump('tiles.bin', emu.memType.snesVideoRam, 0x10000)
      return
    end
    case = cfg.cases[index]
  end
  if step == 0 then
    for a = 0x7FF000, 0x7FF023 do emu.write(a, 0, m) end
  end
  step = step + 1
  local key = case.keys[step]
  if key >= 0 then emu.write(0xCC, key, m) end
end, emu.callbackType.exec, cfg.loop, cfg.loop)
emu.addMemoryCallback(function()
  local got = bytes(0x72, read(0x71))
  record(equal(got, cfg.encoded), 'Y 완료 직렬화', got)
  saved_at = frame
end, emu.callbackType.exec, cfg.finish, cfg.finish)
emu.addEventCallback(function()
  frame = frame + 1
  L.release()
  if not entered then
    if frame == 600 or frame == 900 or frame == 1100 then L.press({a = true}) end
  elseif saved_at then
    local age = frame - saved_at
    if age == 190 or age == 191 or age == 340 or age == 341 then L.press({a = true}) end
    if age == 1100 then
      local got = bytes(0x7E2001, #cfg.encoded)
      record(equal(got, cfg.encoded) and read(0x7E1BB0) == 0, '새 게임 이름·메뉴 표시 해제', got)
      L.write('composition.txt', table.concat(log, '\n') .. '\n')
      L.shot('game.png')
      emu.stop()
    end
  else
    local age = frame - lastloop
    if age == 15 or age == 16 then
      local key = final and -2 or cfg.cases[index].keys[step]
      if key == -1 then L.press({b = true})
      elseif key == -2 then L.press({y = true})
      else L.press({a = true}) end
    end
  end
  if frame == 6000 then
    L.shot('timeout.png')
    L.write('composition.txt', string.format('TIMEOUT entered=%s index=%d step=%d\n', tostring(entered), index, step) .. table.concat(log, '\n'))
    emu.stop()
  end
end, emu.eventType.endFrame)
