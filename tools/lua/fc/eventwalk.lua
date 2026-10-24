-- DQ4: walk by map coordinates from a savestate, then press buttons; dumps like seq.lua.
-- env: STATE, SHOT_DIR, LIBDIR, TAIL (frames after the last step, default 120),
--   SEQ="y=1C,x=1F,up:16,a:6,wait:60,..."
--     x=NN / y=NN  hold right/left (down/up) until $0044 ($0045) equals NN and the step has settled;
--                  gives up after 40 frames without a coordinate change (blocked)
--     btn:frames   hold buttons ("a", "up+b", ...) for frames; wait:frames does nothing
--     reset:1      press the console reset button (emu.reset)
--   POKEAT="frame:addr=val;..." writes CPU addresses once at that frame after the state loads.
--   PRGPOKE="offset=val;..." writes PRG ROM bytes (iNES offset minus the header) in emulator memory
--     at frame 3; the ROM file is untouched.
-- walk.txt: one line per step with the frame and the coordinates when it ended.
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local L = require("lib")
L.loadState(os.getenv("STATE"))
local steps = {}
for tok in string.gmatch(os.getenv("SEQ") or "", "[^,]+") do
  local axis, v = tok:match("^([xy])=(%x+)$")
  if axis then
    steps[#steps + 1] = {axis = axis, to = tonumber(v, 16)}
  else
    local b, f = tok:match("([%w+]+):(%d+)")
    steps[#steps + 1] = {btn = b, n = tonumber(f)}
  end
end
local pokes = {}
for f, a, v in string.gmatch(os.getenv("POKEAT") or "", "(%d+):(%x+)=(%x+)") do
  pokes[#pokes + 1] = {tonumber(f), tonumber(a, 16), tonumber(v, 16)}
end
local prgPokes = {}
for a, v in string.gmatch(os.getenv("PRGPOKE") or "", "(%x+)=(%x+)") do
  prgPokes[#prgPokes + 1] = {tonumber(a, 16), tonumber(v, 16)}
end
local tail = tonumber(os.getenv("TAIL") or "120")
local log = {}
local i, left, n, done, last, still = 1, nil, 0, nil, nil, 0
local function pos() return emu.read(0x44, L.mem), emu.read(0x45, L.mem) end
emu.addEventCallback(function()
  n = n + 1
  if n < 3 then return end
  if n == 3 then
    for _, p in ipairs(prgPokes) do emu.write(p[1], p[2], emu.memType.nesPrgRom) end
  end
  for _, p in ipairs(pokes) do if p[1] == n then emu.write(p[2], p[3], L.mem) end end
  L.release()
  if i <= #steps then
    local s = steps[i]
    if s.axis then
      local x, y = pos()
      local cur = s.axis == "x" and x or y
      local key = x * 256 + y
      if key ~= last then last = key; still = 0 else still = still + 1 end
      -- a step updates the coordinate at its start; wait 16 frames so it finishes
      if (cur == s.to and still >= 16) or still >= 40 then
        log[#log + 1] = string.format("%d %s=%02X at %02X,%02X%s", n, s.axis, s.to, x, y, cur == s.to and "" or " blocked")
        i = i + 1; still = 0
      elseif cur ~= s.to then
        local t = {}
        if s.axis == "x" then t[cur < s.to and "right" or "left"] = true
        else t[cur < s.to and "down" or "up"] = true end
        L.press(t)
      end
    else
      if left == nil then left = s.n end
      if s.btn == "reset" then
        if left == s.n then emu.reset() end
      elseif s.btn ~= "wait" then
        local t = {}
        for b in s.btn:gmatch("[^+]+") do t[b] = true end
        L.press(t)
      end
      left = left - 1
      if left <= 0 then i = i + 1; left = nil end
    end
  elseif not done then
    done = n
  end
  if done and n == done + tail then
    local x, y = pos()
    log[#log + 1] = string.format("end %d at %02X,%02X map %02X/%02X", n, x, y, emu.read(0x63, L.mem), emu.read(0x64, L.mem))
    L.write("walk.txt", table.concat(log, "\n") .. "\n")
    L.shot("end.png"); L.saveState("end.mss")
    L.dumpAll("end")
  end
  if done and n >= done + tail + 5 then emu.stop(0) end
end, emu.eventType.endFrame)
