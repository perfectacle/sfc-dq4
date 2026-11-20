-- dq4whwithcheck.py 가 부른다. 장면은 dq5msg.lua 가 돌고(같은 환경 변수), 이 파일은 그 위에서 창 타일맵·묶음 그림을 함께
-- 보내는 WhWith 와 묶음 그림을 보내는 WhNmi 를 잰다. 줄마다 SHOT_DIR/whwith.txt 에 바로 쓴다.
--   「프레임 meas 줄 V H」      WhWith 가 들어오자마자 잰 주사선(A)과 그 직후의 V·H(마스터 클록)
--   「프레임 이름 V H」         WHEV 의 자리를 지남(go·wait·give·done·tmend)
--   「프레임 dma V H PC 바이트」 WHRANGE 안의 코드가 $420B 를 씀(DMA 시작). 바이트는 채널 0 의 $4305(우리 DMA 는 채널 0)
--   WHEV="meas=60E10F,go=60E191,…"  WHRANGE="60E100-60E2A0,60DD00-60DEC0"
local dir = assert(os.getenv("SHOT_DIR"), "SHOT_DIR")
local out = assert(io.open(dir .. "/whwith.txt", "w"))
local frame = 0
emu.addEventCallback(function() frame = frame + 1 end, emu.eventType.endFrame)

local ranges = {}
for lo, hi in string.gmatch(os.getenv("WHRANGE") or "", "(%x+)-(%x+)") do
  ranges[#ranges + 1] = {tonumber(lo, 16), tonumber(hi, 16)}
end

local function put(s)
  out:write(s, "\n")
  out:flush()
end

for name, hex in string.gmatch(assert(os.getenv("WHEV"), "WHEV"), "([%w_]+)=(%x+)") do
  local addr = tonumber(hex, 16)
  emu.addMemoryCallback(function()
    local s = emu.getState()
    if name == "meas" then
      put(string.format("%d meas %d %d %d", frame, s["cpu.a"] & 0x1FF, s["ppu.scanline"], s["memoryManager.hClock"]))
    else
      put(string.format("%d %s %d %d", frame, name, s["ppu.scanline"], s["memoryManager.hClock"]))
    end
  end, emu.callbackType.exec, addr, addr)
end

emu.addMemoryCallback(function()
  local s = emu.getState()
  local pc = (s["cpu.k"] << 16) | s["cpu.pc"]
  for _, r in ipairs(ranges) do
    if pc >= r[1] and pc < r[2] then
      local n = emu.read(0x4305, emu.memType.snesMemory) | (emu.read(0x4306, emu.memType.snesMemory) << 8)
      put(string.format("%d dma %d %d %06X %d", frame, s["ppu.scanline"], s["memoryManager.hClock"], pc, n))
      return
    end
  end
end, emu.callbackType.write, 0x00420B, 0x00420B)

dofile(debug.getinfo(1, "S").source:match("^@(.*)/[^/]*$") .. "/../../../dq5/tools/lua/dq5msg.lua")
