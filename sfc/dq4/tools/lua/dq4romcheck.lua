-- Observe ROM-loaded graphics without changing ROM, WRAM, VRAM, OAM or CGRAM.
-- OUT must exist. Optional STATE; SEQ="down@30:60,up@300:60"; DUMPF="1,200";
-- EVERY=10, FROM=200, MAXF=600. SHIP=1 follows the cabin ladder using input only.
-- ROUTE="331,56;331,67" walks world coordinates (or indoor cells) before SEQ.
local out = assert(os.getenv("OUT"), "OUT")
local maxf = tonumber(os.getenv("MAXF") or "600")
local every = tonumber(os.getenv("EVERY") or "0")
local from = tonumber(os.getenv("FROM") or "0")
local frame, loads = 0, 0
local m = emu.memType.snesMemory
local function rd(a) return emu.read(a, m) end
local function word(a) return rd(a) | rd(a + 1) << 8 end
local log = assert(io.open(out .. "/observe.tsv", "w"))
log:write("frame\tmap\tmode\tx\ty\tfield_x\tfield_y\tgfx\tdirection\tloader_calls\n")
local function status()
  log:write(string.format("%d\t%02X/%02X\t%02X\t%d\t%d\t%d\t%d\t%02X\t%02X\t%d\n",
    frame, rd(0x7E00BC), rd(0x7E00BD), rd(0x7E00BE), rd(0x7E3020), rd(0x7E3080),
    word(0x7E00B6), word(0x7E00B8), rd(0x7E196F), rd(0x7E31E0), loads))
  log:flush()
end
local state = os.getenv("STATE")
if state and state ~= "" then
  local f = assert(io.open(state, "rb"))
  local data = f:read("*a")
  f:close()
  local hook
  hook = emu.addMemoryCallback(function()
    emu.removeMemoryCallback(hook, emu.callbackType.exec, 0, 0xFFFFFF)
    emu.loadSavestate(data)
  end, emu.callbackType.exec, 0, 0xFFFFFF)
end
emu.addMemoryCallback(function() loads = loads + 1 end, emu.callbackType.exec, 0x1FCF14)
local seq, dumpf = {}, {}
for b, s, n in string.gmatch(os.getenv("SEQ") or "", "(%a+)@(%d+):(%d+)") do
  seq[#seq + 1] = { b, tonumber(s), tonumber(n) }
end
for n in string.gmatch(os.getenv("DUMPF") or "", "%d+") do dumpf[tonumber(n)] = true end
local ship, waypoint = os.getenv("SHIP") == "1", 1
local ladder = {{3, 11}, {3, 24}, {7, 24}}
local departed = false
local route, route_index = {}, 1
for x, y in string.gmatch(os.getenv("ROUTE") or "", "(%d+),(%d+)") do
  route[#route + 1] = {tonumber(x), tonumber(y)}
end
emu.addEventCallback(function()
  local inp = {}
  if ship and not departed then
    if frame < 4 then inp.b = true
    elseif frame >= 44 then
      local x, y = rd(0x7E3020), rd(0x7E3080)
      local p = ladder[waypoint]
      if p and x == p[1] and y == p[2] then waypoint = waypoint + 1; p = ladder[waypoint] end
      if p then
        inp[(x < p[1] and "right") or (x > p[1] and "left") or (y < p[2] and "down") or "up"] = true
      else
        inp.up = true
        if rd(0x7E00BC) ~= 0x17 or rd(0x7E00BD) ~= 0 then departed = true end
      end
    end
  elseif route[route_index] then
    local p = route[route_index]
    local field = rd(0x7E00BE) & 0x80 == 0
    local x = field and word(0x7E00B6) or rd(0x7E3020)
    local y = field and word(0x7E00B8) or rd(0x7E3080)
    if x == p[1] and y == p[2] then
      route_index = route_index + 1
    else
      inp[(x < p[1] and "right") or (x > p[1] and "left") or (y < p[2] and "down") or "up"] = true
    end
  else
    for _, p in ipairs(seq) do
      if frame >= p[2] and frame < p[2] + p[3] then inp[p[1]] = true end
    end
  end
  emu.setInput(inp, 0)
end, emu.eventType.inputPolled)
local function dump(name, kind, n)
  local f = assert(io.open(out .. "/" .. name, "wb"))
  local bytes = {}
  for i = 0, n - 1 do bytes[#bytes + 1] = string.char(emu.read(i, kind)) end
  f:write(table.concat(bytes)); f:close()
end
emu.addEventCallback(function()
  frame = frame + 1
  local capture = dumpf[frame] or (every > 0 and frame >= from and (frame - from) % every == 0)
  if frame == 1 or frame % 30 == 0 or capture then status() end
  if capture then
    local k = string.format("%04d", frame)
    dump("w" .. k .. ".bin", emu.memType.snesWorkRam, 0x20000)
    dump("v" .. k .. ".vram", emu.memType.snesVideoRam, 0x10000)
    dump("o" .. k .. ".oam", emu.memType.snesSpriteRam, 544)
    dump("c" .. k .. ".cgram", emu.memType.snesCgRam, 512)
    local f = assert(io.open(out .. "/s" .. k .. ".png", "wb"))
    f:write(emu.takeScreenshot()); f:close()
  end
  if frame >= maxf then status(); log:close(); emu.stop(0) end
end, emu.eventType.endFrame)
