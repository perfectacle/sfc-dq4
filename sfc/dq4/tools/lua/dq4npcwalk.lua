-- 필드 세이브스테이트를 불러 FRAMES 프레임 동안 인물 표 슬롯마다 칸(7E:3020·3080 + 슬롯)이 바뀐 프레임을 적는다
-- (dq4npcwalkcheck.py 가 읽음). 첫 프레임에 SET 을 한 번 쓰고, 그 프레임의 맵 번호와 슬롯 표를 먼저 적는다.
-- 환경 변수: STATE(세이브스테이트 절대 경로), OUT(기록 파일 절대 경로), FRAMES(기본 1800),
--            SET("075B=00;075E=50" 처럼 7E 뱅크 아래 16비트 주소=값, 난수·시각 고정용)
local out = assert(os.getenv("OUT"), "OUT")
local f = assert(io.open(assert(os.getenv("STATE"), "STATE"), "rb"))
local state = f:read("*a")
f:close()
local frames = tonumber(os.getenv("FRAMES") or "1800")
local sets = {}
for a, v in string.gmatch(os.getenv("SET") or "", "(%x+)=(%x+)") do
  sets[#sets + 1] = { 0x7E0000 + tonumber(a, 16), tonumber(v, 16) }
end
local M = emu.memType.snesMemory
local hook
hook = emu.addMemoryCallback(function()
  emu.removeMemoryCallback(hook, emu.callbackType.exec, 0, 0xFFFFFF)
  emu.loadSavestate(state)
end, emu.callbackType.exec, 0, 0xFFFFFF)
local g = assert(io.open(out, "w"))
local frame, last = 0, {}
emu.addEventCallback(function()
  frame = frame + 1
  if frame == 1 then
    for _, p in ipairs(sets) do emu.write(p[1], p[2], M) end
    g:write(string.format("map %02X/%02X\n", emu.read(0x7E00BC, M), emu.read(0x7E00BD, M)))
    for s = 0, 0x1F do
      g:write(string.format("slot %02X gfx %02X x %02X y %02X interval %02X\n", s, emu.read(0x7E3220 + s, M),
        emu.read(0x7E3020 + s, M), emu.read(0x7E3080 + s, M), emu.read(0x7E3300 + s, M)))
    end
  end
  for s = 0, 0x1F do
    local k = emu.read(0x7E3020 + s, M) * 256 + emu.read(0x7E3080 + s, M)
    if last[s] ~= nil and last[s] ~= k then g:write(string.format("move %d %02X %04X\n", frame, s, k)) end
    last[s] = k
  end
  if frame >= frames then
    g:write("end\n")
    g:close()
    emu.stop(0)
  end
end, emu.eventType.endFrame)
