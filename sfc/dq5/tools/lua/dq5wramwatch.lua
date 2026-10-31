-- dq5wramwatch.py 가 다른 검사 스크립트 앞에 끼우는 감시. WRAM WATCH_FROM~WATCH_TO(뱅크 거울을 모두 잡도록 WRAM
-- 기준 주소)의 읽기·쓰기를 [읽기/쓰기, 주소, 읽은 명령 다음의 PC] 마다 세어 WATCH_FILE 에 60프레임마다 쓴다.
-- 감싼 스크립트가 emu.stop 으로 끝나도 마지막 60프레임 안의 것만 잃는다. 그다음 WATCH_INNER 를 그대로 돌린다.
local from, to = tonumber(os.getenv('WATCH_FROM'), 16), tonumber(os.getenv('WATCH_TO'), 16)
local path = os.getenv('WATCH_FILE')
local counts, frames = {}, 0
local function hit(kind)
  return function(addr)
    local s = emu.getState()
    local key = string.format('%s %04X %02X%04X', kind, addr, s['cpu.k'] or 0, s['cpu.pc'] or 0)
    counts[key] = (counts[key] or 0) + 1
  end
end
emu.addMemoryCallback(hit('r'), emu.callbackType.read, from, to, emu.cpuType.snes, emu.memType.snesWorkRam)
emu.addMemoryCallback(hit('w'), emu.callbackType.write, from, to, emu.cpuType.snes, emu.memType.snesWorkRam)
local function flush()
  local rows = {}
  for k, v in pairs(counts) do rows[#rows + 1] = k .. ' ' .. v end
  table.sort(rows)
  local f = io.open(path, 'w')
  f:write(string.format('frames %d\n', frames), table.concat(rows, '\n'), '\n')
  f:close()
end
emu.addEventCallback(function()
  frames = frames + 1
  if frames % 60 == 0 then flush() end
end, emu.eventType.endFrame)
dofile(os.getenv('WATCH_INNER'))
