-- DQ4: log reads and writes of the event flag area $627B-$62EE (or RANGE="lo-hi", CPU addresses)
-- from frame FROM until MAXF-1, then write flags.txt. Run with DRIVER=... like the toolkit probes.
-- flags.txt lines: "frame r|w addr old>new pc=PC prg=OFFSET bank=$0507 brk=ADDR".
--   brk is the address of the BRK operand bytes ($26/$27) when the access comes from the BRK
--   flag handler in the fixed bank ($C4BC-$C4EC), otherwise "-".
-- Reads by the same PC of the same address with the same value are logged once.
-- Write callbacks see the next instruction's PC, so the PC is taken from the last exec callback.
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local L = require("lib")
local from = tonumber(os.getenv("FROM") or "0")
local maxf = tonumber(os.getenv("MAXF") or "1500")
local lo, hi = 0x627B, 0x62EE
local r = os.getenv("RANGE")
if r then
  local a, b = r:match("(%x+)-(%x+)")
  lo, hi = tonumber(a, 16), tonumber(b, 16)
end
local n, cur, out, seen = 0, 0, {}, {}
local shadow = {}
emu.addMemoryCallback(function(a) cur = a end, emu.callbackType.exec, 0, 0xFFFF)
local function where()
  local off = L.prgOffset(cur)
  local brk = "-"
  if cur >= 0xC4BC and cur <= 0xC4EF then
    brk = string.format("%04X", emu.read(0x26, L.mem) + 256 * emu.read(0x27, L.mem) - 1)
  end
  return string.format("pc=%04X prg=%s bank=%02X brk=%s", cur, off and string.format("%05X", off) or "-",
    emu.read(0x0507, L.mem), brk)
end
emu.addMemoryCallback(function(addr, value)
  if n < from then return end
  local key = string.format("%04X %04X %02X", cur, addr, value)
  if seen[key] then return end
  seen[key] = true
  out[#out + 1] = string.format("%d r %04X %02X %s", n, addr, value, where())
end, emu.callbackType.read, lo, hi)
emu.addMemoryCallback(function(addr, value)
  if n < from then return end
  local old = shadow[addr]
  out[#out + 1] = string.format("%d w %04X %s>%02X %s", n, addr, old and string.format("%02X", old) or "??", value, where())
  shadow[addr] = value
end, emu.callbackType.write, lo, hi)
emu.addEventCallback(function()
  n = n + 1
  if n == 1 then
    for a = lo, hi do shadow[a] = emu.read(a, L.mem) end
  end
  if n == maxf - 1 then L.write("flags.txt", table.concat(out, "\n") .. "\n") end
end, emu.eventType.endFrame)
L.drive()
