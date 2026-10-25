-- Observe the standalone title ROM without memory writes or input injection.
-- OUT must exist; FRAME selects the screenshot frame (default 120).
local out = assert(os.getenv("OUT"), "OUT")
local target = tonumber(os.getenv("FRAME") or "120")
local frame = 0
local function dump(name, kind, count)
  local file = assert(io.open(out .. "/" .. name, "wb"))
  local bytes = {}
  for i = 0, count - 1 do bytes[#bytes + 1] = string.char(emu.read(i, kind)) end
  file:write(table.concat(bytes))
  file:close()
end
emu.addEventCallback(function()
  frame = frame + 1
  if frame == target then
    local file = assert(io.open(out .. "/screen.png", "wb"))
    file:write(emu.takeScreenshot()); file:close()
    dump("vram.bin", emu.memType.snesVideoRam, 0x10000)
    dump("cgram.bin", emu.memType.snesCgRam, 512)
    emu.stop(0)
  end
end, emu.eventType.endFrame)
