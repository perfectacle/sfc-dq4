-- 실험 전에 메모리에 올라온 PRG ROM 을 바꾼다(롬 파일은 그대로). PRG="오프셋=바이트들;…"(PRG ROM 오프셋 16진,
-- 바이트는 이어 씀). 예: 15:$9CCA 의 JMP $BF28 을 JMP $BEF4 로 → PRG="55CCA=4CF4BE".
-- 첫 프레임에 한 번 쓰고, 입력은 DRIVER(seq.lua·warp.lua)가 맡는다.
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local L = require("lib")
local done = false
emu.addEventCallback(function()
  if done then return end
  done = true
  for off, bytes in string.gmatch(os.getenv("PRG") or "", "(%x+)=(%x+)") do
    local o = tonumber(off, 16)
    for i = 1, #bytes - 1, 2 do
      emu.write(o + (i - 1) // 2, tonumber(bytes:sub(i, i + 1), 16), emu.memType.nesPrgRom)
    end
  end
end, emu.eventType.endFrame)
L.drive()
