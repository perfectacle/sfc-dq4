-- DQ4: log NPC block commands as 1F:$D884 runs them, on top of an input driver.
-- env: DRIVER (default eventwalk.lua next to this file, with its STATE/SEQ/POKEAT/PRGPOKE/TAIL; warp.lua also works
--   and then needs MAXF), SLOTS="06,07" (NPC table slots to log; default all), SHOT_EVERY=N (screenshot fNNNNN.png
--   every N frames), LIBDIR, SHOT_DIR.
-- npcblock.txt: "frame slot bank:addr byte" when a slot reaches a command it was not on the frame before,
--   "frame slot pos X,Y dir D" whenever $6F60/$6F80/$7000 of a logged slot changes, and "frame map GG/KK" when $63/$64 change.
-- PRG bank of the block pointer comes from emu.convertAddress at the moment $D892 reads the command byte.
local dir = debug.getinfo(1, "S").source:sub(2):match("(.*/)")
local want = nil
if os.getenv("SLOTS") then
  want = {}
  for s in os.getenv("SLOTS"):gmatch("%x+") do want[tonumber(s, 16)] = true end
end
local mem = emu.memType.nesMemory
local shotEvery = tonumber(os.getenv("SHOT_EVERY") or "0")
local log, frame, lastPtr, lastPos, lastMap = {}, 0, {}, {}, nil
local function flush()
  local f = assert(io.open((os.getenv("SHOT_DIR") or ".") .. "/npcblock.txt", "wb"))
  f:write(table.concat(log, "\n") .. "\n"); f:close()
end
emu.addMemoryCallback(function()
  local s = emu.read(0x51, mem)
  if want and not want[s] then return end
  local p = emu.read(0x4D, mem) + 256 * emu.read(0x4E, mem)
  if lastPtr[s] == p then return end
  lastPtr[s] = p
  local c = emu.convertAddress(p, mem)
  local bank = c and c.address >= 0 and math.floor(c.address / 0x4000) or -1
  log[#log + 1] = string.format("%d %02X %02X:%04X %02X", frame, s, bank, p, emu.read(p, mem))
end, emu.callbackType.exec, 0xD892, 0xD892)
emu.addEventCallback(function()
  frame = frame + 1
  local m = emu.read(0x63, mem) * 256 + emu.read(0x64, mem)
  if m ~= lastMap then
    lastMap, lastPtr = m, {}
    log[#log + 1] = string.format("%d map %02X/%02X", frame, m // 256, m % 256)
  end
  for s = 6, 0x1F do
    if not want or want[s] then
      local x, y, d = emu.read(0x6F60 + s, mem), emu.read(0x6F80 + s, mem), emu.read(0x7000 + s, mem) % 4
      local k = x * 1024 + y * 4 + d
      if lastPos[s] ~= k then
        lastPos[s] = k
        log[#log + 1] = string.format("%d %02X pos %02X,%02X dir %d", frame, s, x, y, d)
      end
    end
  end
  if frame % 60 == 0 then flush() end
  if shotEvery > 0 and frame % shotEvery == 0 then
    local f = assert(io.open(string.format("%s/f%05d.png", os.getenv("SHOT_DIR") or ".", frame), "wb"))
    f:write(emu.takeScreenshot()); f:close()
  end
end, emu.eventType.endFrame)
dofile(os.getenv("DRIVER") or dir .. "eventwalk.lua")
