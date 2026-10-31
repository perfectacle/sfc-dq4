-- 인물 스프라이트 장면 프로브. 드라이버(DRIVER, 보통 dq5warp.lua)를 돌리며 아래를 SHOT_DIR/scene.txt 에 한 줄씩 적는다.
--   EXEC="128C9F,03D202"  그 PC 를 지날 때 프레임·주사선·A·X·Y·맵·스택 위 9바이트
--   7E:3800~381F 쓰기(0 이 아닌 값만), $212D·$2130·$2131 쓰기, OAM DMA($420B 로 B 버스 04 채널을 켬)
--   VEHICLE=1             00:FC60 이 탈것 슬롯(7E:3220 = FE)을 그릴 때 슬롯·칸 오프셋·프레임(3280)·31E7
--   FROM·UNTIL            위 둘(OAM DMA·탈것)을 적는 프레임 범위(기본 0~99999)
--   DUMPAT=500            그 프레임 끝에 oam.bin(544바이트)·cgram.bin(512바이트)
-- 프레임 번호는 끝난 프레임 수라, NMI 뒤 주사선 240 이후의 일은 그 프레임 번호로 적힌다.
local m = emu.memType.snesMemory
local n, log, dirty = 0, {}, false
local from, untilf = tonumber(os.getenv('FROM') or '0'), tonumber(os.getenv('UNTIL') or '99999')
local dumpat = tonumber(os.getenv('DUMPAT') or '-1')
local function rd(a) return emu.read(a, m) end
local function rd16(a) return rd(a) | rd(a + 1) << 8 end
local function on() return n >= from and n <= untilf end
local function line(text)
  log[#log + 1] = string.format('f=%d sl=%d %s', n, emu.getState()['ppu.scanline'], text)
  dirty = true
end

for a in string.gmatch(os.getenv('EXEC') or '', '%x+') do
  local pc = tonumber(a, 16)
  emu.addMemoryCallback(function()
    local s = emu.getState()
    local st = {}
    for k = 1, 9 do st[#st + 1] = string.format('%02X', rd(s['cpu.sp'] + k)) end
    line(string.format('exec %06X A=%04X X=%04X Y=%04X map=%02X/%02X stack=%s', pc, s['cpu.a'], s['cpu.x'], s['cpu.y'],
      rd(0x7E00BC), rd(0x7E00BD), table.concat(st, ' ')))
  end, emu.callbackType.exec, pc, pc)
end

emu.addMemoryCallback(function(addr, value)
  if (value or 0) ~= 0 then line(string.format('w%06X=%02X', addr, value)) end
end, emu.callbackType.write, 0x7E3800, 0x7E381F)

for _, a in ipairs({0x212D, 0x2130, 0x2131}) do
  emu.addMemoryCallback(function(addr, value) line(string.format('r%04X=%02X', addr & 0xFFFF, value or 0)) end,
    emu.callbackType.write, a, a)
end

emu.addMemoryCallback(function(_, value)
  if not on() then return end
  for c = 0, 7 do
    if (value or 0) >> c & 1 == 1 and rd(0x4301 + c * 16) == 0x04 then
      line(string.format('oamdma src=%02X%04X', rd(0x4304 + c * 16), rd16(0x4302 + c * 16)))
    end
  end
end, emu.callbackType.write, 0x420B, 0x420B)

if os.getenv('VEHICLE') == '1' then
  emu.addMemoryCallback(function()
    if not on() then return end
    local s = emu.getState()
    local y = s['cpu.y'] & 0xFF
    if rd(0x7E3220 + y) ~= 0xFE then return end
    local base = rd16(0x7E8000 + rd(0x7E3200 + y))
    line(string.format('draw slot=%02X off=%X frame=%02X 31E7=%02X', y, rd16(s['cpu.d'] + 0xAE) - base, rd(0x7E3280 + y),
      rd(0x7E31E7)))
  end, emu.callbackType.exec, 0x00FC60, 0x00FC60)
end

local function save(name, memType, size)
  local t = {}
  for i = 0, size - 1 do t[#t + 1] = string.char(emu.read(i, memType)) end
  local f = io.open(os.getenv('SHOT_DIR') .. '/' .. name, 'wb'); f:write(table.concat(t)); f:close()
end

emu.addEventCallback(function()
  n = n + 1
  if n == dumpat then
    save('oam.bin', emu.memType.snesSpriteRam, 544)
    save('cgram.bin', emu.memType.snesCgRam, 512)
  end
  if dirty then
    dirty = false
    local f = io.open(os.getenv('SHOT_DIR') .. '/scene.txt', 'w'); f:write(table.concat(log, '\n') .. '\n'); f:close()
  end
end, emu.eventType.endFrame)
dofile(os.getenv('DRIVER'))
