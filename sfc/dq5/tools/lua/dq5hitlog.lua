-- 드라이버(boot.lua) 입력을 재생하면서 타격 효과 기준 칸(7E:9E78·9E79)이 쓰일 때마다 그 값과, 두 프레임 뒤 BG3 타일맵
-- (VRAM 워드 $1C00~$1FFF)에서 한 프레임 뒤보다 바뀐 칸을 적는다. 효과 그림은 BG3 타일로 그려진다.
-- 결과: hits.txt([프레임] [9E78] [9E79] [쓴 곳 PC]), bg3.txt([쓴 프레임] [열] [줄] [새 타일맵 값]). MAXF 직전 프레임에 쓴다.
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local L = require("lib")
local last = tonumber(os.getenv("MAXF") or "3000") - 1
local n = 0
local hits, base, hitlog, bg3log = {}, {}, {}, {}

local function bg3()
  local t = {}
  for i = 0, 0x7FF do t[i] = emu.read(0x3800 + i, emu.memType.snesVideoRam) end
  return t
end

emu.addMemoryCallback(function(_, value)
  local st = emu.getState()
  -- 한 프레임에 두 번 쓰면(앞서 0 으로 지우고 다시 둠) BG3 는 한 번만 본다.
  if hits[#hits] ~= n then hits[#hits + 1] = n end
  hitlog[#hitlog + 1] = string.format("%d %02X %02X %02X:%04X", n, emu.read(0x7E9E78, emu.memType.snesMemory), value,
    st["cpu.k"] or 0, st["cpu.pc"] or 0)
end, emu.callbackType.write, 0x7E9E79, 0x7E9E79)

emu.addEventCallback(function()
  n = n + 1
  for _, h in ipairs(hits) do
    -- 쓴 프레임의 끝에는 아직 그대로라, 한 프레임 뒤를 기준으로 두 프레임 뒤와 견준다.
    if n == h + 1 then base[h] = bg3() end
    if n == h + 2 and base[h] then
      local cur = bg3()
      for i = 0, 0x7FE, 2 do
        if cur[i] ~= base[h][i] or cur[i + 1] ~= base[h][i + 1] then
          bg3log[#bg3log + 1] = string.format("%d %d %d %02X%02X", h, (i // 2) % 32, (i // 2) // 32, cur[i + 1], cur[i])
        end
      end
    end
  end
  if n == last then
    L.write("hits.txt", table.concat(hitlog, "\n") .. "\n")
    L.write("bg3.txt", table.concat(bg3log, "\n") .. "\n")
  end
end, emu.eventType.endFrame)
dofile(os.getenv("LIBDIR") .. "/boot.lua")
