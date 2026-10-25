-- 메모리에 올라온 PRG ROM 을 바꾸고(롬 파일은 그대로) 메시지 출력과 정한 PC 를 기록한다.
-- PRG="4786C=43;478A7=A905EA"(PRG ROM 오프셋=바이트들, 16진)는 첫 프레임에 한 번 쓴다.
-- 메시지 진입 16:$8656 의 X:A 를 msg 줄로, HOOK="11:B8B9,10:B0EF"(뱅크:CPU 주소)에 닿으면 pc 줄(A·X·Y·P)로 남긴다.
-- RAM="6E44,72E4"(CPU 주소)를 주면 pc 줄에 그 바이트들을 붙인다.
-- 입력은 DRIVER(seq.lua·warp.lua)가 맡고, 기록은 MAXF-1 프레임에 shopenc2.txt 로 쓴다.
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local L = require("lib")
local f, out, done = 0, {}, false
local maxf = tonumber(os.getenv("MAXF") or "1500")
local rams = {}
for a in string.gmatch(os.getenv("RAM") or "", "%x+") do rams[#rams + 1] = tonumber(a, 16) end
local function log(s) out[#out + 1] = string.format("%d %s", f, s) end
for b, a in string.gmatch(os.getenv("HOOK") or "", "(%x+):(%x+)") do
  local bank, addr = tonumber(b, 16), tonumber(a, 16)
  emu.addMemoryCallback(function(pc)
    if L.prgOffset(pc) ~= bank * 0x4000 + (addr & 0x3FFF) then return end
    local st = emu.getState()
    local s = string.format("pc %02X:%04X A=%02X X=%02X Y=%02X P=%02X", bank, addr, st["cpu.a"], st["cpu.x"], st["cpu.y"], st["cpu.ps"])
    for _, r in ipairs(rams) do s = s .. string.format(" %04X=%02X", r, emu.read(r, L.mem)) end
    log(s)
  end, emu.callbackType.exec, addr, addr)
end
emu.addMemoryCallback(function(addr)
  if L.prgOffset(addr) ~= 0x16 * 0x4000 + 0x0656 then return end
  local st = emu.getState()
  log(string.format("msg %02X%02X", st["cpu.x"], st["cpu.a"]))
end, emu.callbackType.exec, 0x8656, 0x8656)
emu.addEventCallback(function()
  if not done then
    done = true
    for off, bytes in string.gmatch(os.getenv("PRG") or "", "(%x+)=(%x+)") do
      local o = tonumber(off, 16)
      for i = 1, #bytes - 1, 2 do
        emu.write(o + (i - 1) // 2, tonumber(bytes:sub(i, i + 1), 16), emu.memType.nesPrgRom)
      end
    end
  end
  f = f + 1
  if f == maxf - 1 then L.write("shopenc2.txt", table.concat(out, "\n") .. "\n") end
end, emu.eventType.endFrame)
L.drive()
