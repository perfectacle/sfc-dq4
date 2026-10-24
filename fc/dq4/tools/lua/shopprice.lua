-- 가격 루틴 15:$B2F7 에 들어갈 때의 아이템($00)과 나올 때($B36F)의 값($00~$02, 3바이트)을 price.txt 에 적는다.
-- 줄: 프레임, 그룹 $63, 순번 $64, 아이템, 값(10진). 툴킷 FC 프로브처럼 끝에서 DRIVER 를 돌리고 MAXF-1 프레임에 쓴다.
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local L = require("lib")
local f, log, item = 0, {}, nil
local function bank15(addr) return L.prgOffset(addr) == 0x54000 + (addr - 0x8000) end
emu.addMemoryCallback(function()
  if bank15(0xB2F7) then item = emu.read(0x00, L.mem) end
end, emu.callbackType.exec, 0xB2F7, 0xB2F7)
emu.addMemoryCallback(function()
  if not bank15(0xB36F) or item == nil then return end
  local v = emu.read(0x00, L.mem) | emu.read(0x01, L.mem) << 8 | emu.read(0x02, L.mem) << 16
  log[#log + 1] = string.format("%d %02X/%02X %02X %d", f, emu.read(0x63, L.mem), emu.read(0x64, L.mem), item, v)
  item = nil
end, emu.callbackType.exec, 0xB36F, 0xB36F)
local maxf = tonumber(os.getenv("MAXF") or "1500")
emu.addEventCallback(function()
  f = f + 1
  if f == maxf - 1 then L.write("price.txt", table.concat(log, "\n") .. "\n") end
end, emu.eventType.endFrame)
L.drive()
