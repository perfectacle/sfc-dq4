-- dq4critcheck.py 가 부른다. 일행 たたかう 의 회심 판정(20:C697~C6C4)을 지날 때마다 crit.txt 에 남기고 NEXT 프로브
-- (dq4battle.lua)를 그대로 돌린다. 기록은 FLUSH 프레임마다 다시 쓴다(NEXT 가 emu.stop 으로 끝내므로).
--   「프레임 enter 10F5=공격하는쪽 100E=값」        20:C697 에 들어옴
--   「프레임 f41 49=값 reads=주소,…」              20:C6A8: 필드 41 조회(20:C6A4 BRK 8D) 뒤 직접 페이지 $49, 그 사이 읽은
--                                                   WRAM 0760~07FF(뱅크 7E 와 00 거울)
--   「프레임 have C=0|1」                           20:C6B0: 26:8D0A(가진 물건) 뒤 carry
--   「프레임 crit」 / 「프레임 nocrit」              20:C6BE(회심) / 20:C6BC(회심 아님)
local m = emu.memType.snesMemory
local out = os.getenv('SHOT_DIR') .. '/crit.txt'
local flush = tonumber(os.getenv('FLUSH') or '30')
local f, log, reading, reads = 0, {}, false, {}

local function at(addr, fn) emu.addMemoryCallback(fn, emu.callbackType.exec, addr, addr) end

at(0x20C697, function()
  log[#log + 1] = string.format('%d enter 10F5=%02X 100E=%02X', f, emu.read(0x7E10F5, m), emu.read(0x7E100E, m))
end)
at(0x20C6A4, function() reading, reads = true, {} end)
local function watch(lo, hi)
  emu.addMemoryCallback(function(addr)
    if reading then reads[#reads + 1] = string.format('%04X', addr & 0xFFFF) end
  end, emu.callbackType.read, lo, hi)
end
watch(0x7E0760, 0x7E07FF)
watch(0x000760, 0x0007FF)
at(0x20C6A8, function()
  reading = false
  local dp = emu.getState()['cpu.d']
  log[#log + 1] = string.format('%d f41 49=%02X reads=%s', f, emu.read(0x7E0000 + ((dp + 0x49) & 0xFFFF), m),
    table.concat(reads, ','))
end)
at(0x20C6B0, function()
  log[#log + 1] = string.format('%d have C=%d', f, emu.getState()['cpu.ps'] & 1)
end)
at(0x20C6BE, function() log[#log + 1] = string.format('%d crit', f) end)
at(0x20C6BC, function() log[#log + 1] = string.format('%d nocrit', f) end)

emu.addEventCallback(function()
  f = f + 1
  if f % flush == 0 then
    local h = io.open(out, 'w')
    h:write(table.concat(log, '\n') .. '\n')
    h:close()
  end
end, emu.eventType.endFrame)

dofile(os.getenv('NEXT'))
