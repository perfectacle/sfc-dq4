-- Capture an independently booted environment viewer without memory injection.
local out = assert(os.getenv("ENVIRONMENT_OUT"), "ENVIRONMENT_OUT")
local frames = 0
local function save(name, data)
  local f = assert(io.open(out .. "/" .. name, "wb"))
  f:write(data)
  f:close()
end
local function dump(name, kind, length)
  local bytes = {}
  for i = 0, length - 1 do bytes[#bytes + 1] = string.char(emu.read(i, kind)) end
  save(name, table.concat(bytes))
end
emu.addEventCallback(function()
  frames = frames + 1
  if frames == 120 then
    save("screen.png", emu.takeScreenshot())
    dump("screen.vram", emu.memType.snesVideoRam, 0x10000)
    dump("screen.cgram", emu.memType.snesCgRam, 0x200)
    emu.stop(0)
  end
end, emu.eventType.endFrame)
