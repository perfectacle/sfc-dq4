-- Load STATE, let FRAMES frames pass, then write all 128 KiB of WRAM, VRAM and CGRAM to OUT.
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local L = require("lib")
L.loadState(os.getenv("STATE"))
local out = assert(os.getenv("OUT"), "OUT")
local wait = tonumber(os.getenv("FRAMES") or "10")
local frames = 0
local function save(name, kind, base, length)
  local b = {}
  for i = 0, length - 1 do b[#b + 1] = string.char(emu.read(base + i, kind)) end
  local f = assert(io.open(out .. "/" .. name, "wb"))
  f:write(table.concat(b))
  f:close()
end
emu.addEventCallback(function()
  frames = frames + 1
  if frames == wait then
    save("wram.bin", emu.memType.snesWorkRam, 0, 0x20000)
    save("vram.bin", emu.memType.snesVideoRam, 0, 0x10000)
    save("cgram.bin", emu.memType.snesCgRam, 0, 0x200)
    emu.stop(0)
  end
end, emu.eventType.endFrame)
