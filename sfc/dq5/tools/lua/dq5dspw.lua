-- SPC 가 DSP 에 쓰는 KON·KOF·FLG 와 목소리마다 음량·피치·SRCN 을 프레임과 함께 dspw.txt 로(MAXF-2 프레임에 씀). DSPFROM 프레임부터 적는다.
-- 드라이버(boot.lua, 보통 dq5warp.lua·walk.lua) 뒤에 붙여 쓴다. sfc/dq5/tools/dq5song.py --kon 이 읽는다.
local out, fr = {}, 0
local reg = 0
local from = tonumber(os.getenv("DSPFROM") or "0")
emu.addEventCallback(function() fr = fr + 1; if fr == tonumber(os.getenv("MAXF")) - 2 then local f = io.open(os.getenv("SHOT_DIR") .. "/dspw.txt", "w"); f:write(table.concat(out, "\n") .. "\n"); f:close() end end, emu.eventType.endFrame)
emu.addMemoryCallback(function(addr, value) reg = value end, emu.callbackType.write, 0xF2, 0xF2, emu.cpuType.spc, emu.memType.spcMemory)
emu.addMemoryCallback(function(addr, value)
  if fr < from then return end
  local r = reg & 0x7F
  if r == 0x4C or r == 0x5C or r == 0x6C or (r & 0x0F) <= 4 then
    out[#out + 1] = string.format("%d %02X=%02X", fr, r, value)
  end
end, emu.callbackType.write, 0xF3, 0xF3, emu.cpuType.spc, emu.memType.spcMemory)
dofile(os.getenv("LIBDIR") .. "/boot.lua")
