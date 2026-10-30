-- 프레임마다 $7F(본 루프가 프레임마다 $19C3 만큼 더함)·$BE·필드 좌표 $B6·$B8·세계 $1949 를 SHOT_DIR/frames.txt 에
-- 「프레임 7F BE B6 B8 1949」(16진) 한 줄씩 50프레임마다와 MAXF-3 프레임에 쓴다. 그다음 NEXT(보통 dq5gfxdump.lua)를
-- 이어 부른다. $7F·$BE 가 둘 다 그대로인 프레임은 본 루프가 돌지 않은(불러오는 동안 멈춘) 프레임이다.
local n, rows = 0, {}
local m = emu.memType.snesMemory
local maxf = tonumber(os.getenv("MAXF") or "3000")
emu.addEventCallback(function()
  n = n + 1
  rows[#rows + 1] = string.format("%d %02X %02X %04X %04X %02X", n, emu.read(0x7E007F, m), emu.read(0x7E00BE, m),
    emu.read16(0x7E00B6, m), emu.read16(0x7E00B8, m), emu.read(0x7E1949, m))
  if n % 50 == 0 or n == maxf - 3 then
    local f = io.open(os.getenv("SHOT_DIR") .. "/frames.txt", "w"); f:write(table.concat(rows, "\n") .. "\n"); f:close()
  end
end, emu.eventType.endFrame)
dofile(os.getenv("NEXT"))
