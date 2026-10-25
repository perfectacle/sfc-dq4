-- Observe the integrated title and automate input without changing game memory.
-- OUT must exist. MAXF=900, EVERY=10, FROM=0; SEQ="a@420:2,start@600:2".
-- RESETAT optionally exercises the console's reset button at an absolute frame.
local out = assert(os.getenv("OUT"), "OUT")
local maxf = tonumber(os.getenv("MAXF") or "900")
local every = tonumber(os.getenv("EVERY") or "10")
local first = tonumber(os.getenv("FROM") or "0")
local resetat = tonumber(os.getenv("RESETAT") or "-1")
local frame = 0
local active_audio_frames = 0
local audio = assert(io.open(out .. "/audio.tsv", "w"))
audio:write("frame\tleft\tright\tactive_frames\n")
local seq = {}
for button, start, count in (os.getenv("SEQ") or ""):gmatch("(%a+)@(%d+):(%d+)") do
  seq[#seq + 1] = {button, tonumber(start), tonumber(count)}
end
local log = assert(io.open(out .. "/events.txt", "w"))
for _, address in ipairs({0x03FDFB, 0x308000, 0x03FE5C, 0x00A6F1, 0x25801C}) do
  emu.addMemoryCallback(function()
    log:write(string.format("frame=%d pc=%06X\n", frame, address)); log:flush()
  end, emu.callbackType.exec, address)
end
emu.addMemoryCallback(function()
  local state = emu.getState()
  log:write(string.format("sound frame=%d argument=%04X\n", frame, state["cpu.a"])); log:flush()
end, emu.callbackType.exec, 0x24FE9A)
local function dump(path, kind, count)
  local file = assert(io.open(path, "wb"))
  local bytes = {}
  for i = 0, count - 1 do bytes[#bytes + 1] = string.char(emu.read(i, kind)) end
  file:write(table.concat(bytes)); file:close()
end
emu.addEventCallback(function()
  local input = {}
  for _, item in ipairs(seq) do
    if frame >= item[2] and frame < item[2] + item[3] then input[item[1]] = true end
  end
  emu.setInput(input, 0)
end, emu.eventType.inputPolled)
emu.addEventCallback(function()
  frame = frame + 1
  local state = emu.getState()
  local left, right = state["spc.dsp.outSamples0"], state["spc.dsp.outSamples1"]
  if left ~= 0 or right ~= 0 then active_audio_frames = active_audio_frames + 1 end
  if frame % 60 == 0 then
    audio:write(string.format("%d\t%d\t%d\t%d\n", frame, left, right, active_audio_frames)); audio:flush()
  end
  if frame >= first and frame % every == 0 then
    local name = string.format("%04d", frame)
    local file = assert(io.open(out .. "/s" .. name .. ".png", "wb"))
    file:write(emu.takeScreenshot()); file:close()
    file = assert(io.open(out .. "/p" .. name .. ".txt", "w"))
    local state, keys = emu.getState(), {}
    for key in pairs(state) do if key:match("^ppu%.") then keys[#keys + 1] = key end end
    table.sort(keys)
    for _, key in ipairs(keys) do file:write(key .. "=" .. tostring(state[key]) .. "\n") end
    file:close()
    dump(out .. "/v" .. name .. ".bin", emu.memType.snesVideoRam, 0x10000)
    dump(out .. "/c" .. name .. ".bin", emu.memType.snesCgRam, 512)
  end
  if frame == resetat then emu.reset() end
  if frame >= maxf then log:close(); audio:close(); emu.stop(0) end
end, emu.eventType.endFrame)
