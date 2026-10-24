-- 창을 여는 16:$8A03(뱅크 16 함수 03, $F6 = 창 번호)을 적고, 그 뒤 nametable 에 쓴 칸을 모은다.
-- open.txt 한 줄에 프레임, $F5-$F8, $07B4, 화면 스크롤(마지막 $2005·$2000 값, 화소), 스택 12바이트, 창 레코드 주소($EE/$EF, 16:$94D9 에서)를 쓴다.
-- WIN=hex 를 주면 첫 진입 때 $F6 을 그 번호로 바꿔 아무 창이나 띄운다(F7=, F8= 로 $F7·$F8 도).
-- 진입마다 nametable 을 oNN.nt 로 덤프하고, $2006/$2007 로 $2000-$2FFF 에 쓴 값을 진입 순번별로
-- ppu.txt 에 "순번 주소 처음값 마지막값"으로 쓴다(창을 닫으면 같은 칸에 배경을 되돌려 쓰므로 둘 다). 끝에서 입력 드라이버(DRIVER)를 돌리고 MAXF-1 프레임에 쓴다.
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local L = require("lib")
local win = os.getenv("WIN") and tonumber(os.getenv("WIN"), 16)
local f7 = os.getenv("F7") and tonumber(os.getenv("F7"), 16)
local f8 = os.getenv("F8") and tonumber(os.getenv("F8"), 16)
local f, opens, log, forced = 0, 0, {}, false
local hi, latch, vaddr, ctrl, scrollX, scrollY, cells, order = 0, 0, 0, 0, 0, 0, {}, {}
local function at(addr, fn)
  local off = 0x16 * 0x4000 + (addr & 0x3FFF)
  emu.addMemoryCallback(function(a)
    if L.prgOffset(a) == off then fn(emu.getState()) end
  end, emu.callbackType.exec, addr, addr)
end
local function r(a) return emu.read(a, L.mem) end
at(0x8A03, function()
  if win and not forced then
    emu.write(0xF6, win, L.mem)
    if f7 then emu.write(0xF7, f7, L.mem) end
    if f8 then emu.write(0xF8, f8, L.mem) end
    forced = true
  end
  opens = opens + 1
  local sp, stk = emu.getState()["cpu.sp"], {}
  for i = 1, 12 do stk[#stk + 1] = string.format("%02X", r(0x100 + ((sp + i) & 0xFF))) end
  log[#log + 1] = string.format("%d open%02d F5=%02X F6=%02X F7=%02X F8=%02X 7B4=%02X scroll=%d,%d stack=%s", f, opens,
    r(0xF5), r(0xF6), r(0xF7), r(0xF8), r(0x07B4), (ctrl & 1) * 256 + scrollX, (ctrl & 2) * 120 + scrollY,
    table.concat(stk, " "))
  L.dump(string.format("o%02d.nt", opens), emu.memType.nesNametableRam)
end)
at(0x94D9, function()
  log[#log + 1] = string.format("%d rec %02X%02X", f, r(0xEF), r(0xEE))
end)
emu.addMemoryCallback(function(_, value) ctrl = value end, emu.callbackType.write, 0x2000, 0x2000)
emu.addMemoryCallback(function(_, value)
  if latch == 0 then hi = value & 0x3F; latch = 1 else vaddr = hi * 256 + value; latch = 0 end
end, emu.callbackType.write, 0x2006, 0x2006)
emu.addMemoryCallback(function(_, value)
  if latch == 0 then scrollX = value; latch = 1 else scrollY = value; latch = 0 end
end, emu.callbackType.write, 0x2005, 0x2005)
emu.addMemoryCallback(function() latch = 0 end, emu.callbackType.read, 0x2002, 0x2002)
emu.addMemoryCallback(function(_, value)
  if opens > 0 and vaddr >= 0x2000 and vaddr < 0x3000 then
    local k = opens * 0x10000 + vaddr
    if not cells[k] then order[#order + 1] = k; cells[k] = {value, value} end
    cells[k][2] = value
  end
  vaddr = (vaddr + ((ctrl & 4) ~= 0 and 32 or 1)) & 0x3FFF
end, emu.callbackType.write, 0x2007, 0x2007)
local maxf = tonumber(os.getenv("MAXF") or "1500")
emu.addEventCallback(function()
  f = f + 1
  if f == maxf - 1 then
    L.write("open.txt", table.concat(log, "\n") .. "\n")
    local t = {}
    for _, k in ipairs(order) do t[#t + 1] = string.format("%d %04X %02X %02X", k >> 16, k & 0xFFFF, cells[k][1], cells[k][2]) end
    L.write("ppu.txt", table.concat(t, "\n") .. "\n")
  end
end, emu.eventType.endFrame)
L.drive()
