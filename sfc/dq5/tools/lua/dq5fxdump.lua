-- DQ5 전투 연출 덤프. 드라이버(boot.lua, 보통 dq5battle.lua)로 싸우면서 연출 시작 22:D73C(A = 연출 번호)부터
-- 끝 22:D796 뒤 POST 프레임까지 프레임마다 VRAM·CGRAM·OAM 과 BG 스크롤을 SHOT_DIR 에 남긴다.
--   fx.txt                  "연출번호 시작프레임 끝프레임" 한 줄씩
--   e<번호>-<k>.vram/.cgram/.oam/.ppu   연출 안 k 번째 프레임(0부터). .ppu 는 "BG3 hscroll vscroll" 한 줄
--   SHOTS=1                 e<번호>-<k>.png 화면도 찍는다(dq5fx.py --check 로 연출 층과 견줌)
--   ONLY="01"               이 번호의 연출만(16진, 없으면 모두). 같은 번호는 처음 한 번만 남긴다   POST(기본 4)   MAXF 는 드라이버 몫
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local L = require("lib")
local m = emu.memType
local only = os.getenv("ONLY") and tonumber(os.getenv("ONLY"), 16)
local post = tonumber(os.getenv("POST") or "4")
local n, fx, k, stopAt, log, done = 0, nil, 0, nil, {}, {}

emu.addMemoryCallback(function()
  local a = emu.getState()["cpu.a"] & 0xFF
  if fx == nil and not done[a] and (only == nil or a == only) then done[a] = true; fx, k, stopAt = a, 0, nil; log[#log + 1] = string.format("%02X %d", a, n) end
end, emu.callbackType.exec, 0x22D73C, 0x22D73C)
emu.addMemoryCallback(function()
  if fx and not stopAt then stopAt = n + post; log[#log] = log[#log] .. " " .. n end
end, emu.callbackType.exec, 0x22D796, 0x22D796)

emu.addEventCallback(function()
  n = n + 1
  if fx then
    local p = string.format("e%02X-%03d", fx, k)
    L.dump(p .. ".vram", m.snesVideoRam, 0x10000)
    L.dump(p .. ".cgram", m.snesCgRam, 0x200)
    L.dump(p .. ".oam", m.snesSpriteRam, 0x220)
    local st = emu.getState()
    L.write(p .. ".ppu", string.format("%d %d\n", st["ppu.layers[2].hscroll"], st["ppu.layers[2].vscroll"]))
    if os.getenv("SHOTS") then L.shot(p .. ".png") end
    k = k + 1
    if stopAt and n >= stopAt then fx = nil end
  end
  L.write("fx.txt", table.concat(log, "\n") .. "\n")
end, emu.eventType.endFrame)
dofile(os.getenv("LIBDIR") .. "/boot.lua")
