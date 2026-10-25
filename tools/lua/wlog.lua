-- WLOG="x=7E302A;y=7E308A;..." 값이 바뀔 때마다 프레임과 함께 wlog.txt 에 쓴다. 입력은 boot.lua 와 같음.
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local L = require("lib")
local n, t, items, last = 0, {}, {}, {}
local m = emu.memType.snesMemory
for name, a in string.gmatch(os.getenv("WLOG"), "([%w_]+)=(%x+)") do items[#items + 1] = {name, tonumber(a, 16)} end
local maxf = tonumber(os.getenv("MAXF") or "1500")
emu.addEventCallback(function()
  n = n + 1
  local parts, changed = {}, false
  for i, it in ipairs(items) do
    local v = emu.read(it[2], m)
    if v ~= last[i] then changed = true end
    last[i] = v
    parts[#parts + 1] = string.format("%s=%02X", it[1], v)
  end
  if changed then t[#t + 1] = string.format("f%05d %s", n, table.concat(parts, " ")) end
  if n == maxf - 1 then L.write("wlog.txt", table.concat(t, "\n") .. "\n") end
end, emu.eventType.endFrame)
dofile(os.getenv("LIBDIR") .. "/boot.lua")
