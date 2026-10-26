-- DQ5: dq5warp.lua 를 돌리며 30프레임마다 VRAM 0x400워드 칸 32개의 쓰기 횟수(접근 카운터, 세이브스테이트를 불러온 뒤부터)와
-- 지금 맵 번호($BC·$BD)를 SHOT_DIR/vw.txt 에 덮어쓴다. WARPLUA 에 dq5warp.lua 경로, 나머지 환경 변수는 dq5warp.lua 와 같다
local n = 0
local m = emu.memType.snesMemory
emu.addEventCallback(function()
  n = n + 1
  if n % 30 ~= 0 then return end
  local c, out = emu.getAccessCounters(emu.memType.snesVideoRam, emu.counterType.writeCount), {}
  for blk = 0, 0x1F do
    local s = 0
    for i = blk * 0x800, blk * 0x800 + 0x7FF do s = s + c[i] end
    out[#out + 1] = string.format("%04X %d", blk * 0x400, s)
  end
  out[#out + 1] = string.format("map %02X/%02X f=%d", emu.read(0x7E00BC, m), emu.read(0x7E00BD, m), n)
  local f = io.open(os.getenv("SHOT_DIR") .. "/vw.txt", "w"); f:write(table.concat(out, "\n"), "\n"); f:close()
end, emu.eventType.endFrame)
dofile(os.getenv("WARPLUA"))
