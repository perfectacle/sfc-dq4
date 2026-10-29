-- WATCHR="7ECE00-7ED3FF" 범위의 CPU 읽기·쓰기를 PC 마다 모아(처음·마지막 프레임, 횟수, 닿은 주소 범위) SHOT_DIR/rw.txt 에
-- 50프레임마다와 MAXF-3 프레임에 쓴다. 그다음 NEXT(보통 dq5gfxdump.lua)를 이어 부른다. DMA 가 읽는 것은 DMA 를 건
-- 명령의 PC 로 잡힌다. WRAM 포트($2180)로 쓰는 것은 잡히지 않는다.
local n, seen, order = 0, {}, {}
local lo, hi
for a, b in string.gmatch(os.getenv("WATCHR"), "(%x+)-(%x+)") do lo, hi = tonumber(a, 16), tonumber(b, 16) end
local function cb(kind)
  return function(addr)
    local s = emu.getState()
    local key = string.format("%s %06X", kind, (s["cpu.k"] << 16) | s["cpu.pc"])
    local e = seen[key]
    if not e then e = {first = n, count = 0, lo = addr, hi = addr}; seen[key] = e; order[#order + 1] = key end
    e.count, e.last = e.count + 1, n
    if addr < e.lo then e.lo = addr end
    if addr > e.hi then e.hi = addr end
  end
end
emu.addMemoryCallback(cb("r"), emu.callbackType.read, lo, hi)
emu.addMemoryCallback(cb("w"), emu.callbackType.write, lo, hi)
local maxf = tonumber(os.getenv("MAXF") or "3000")
emu.addEventCallback(function()
  n = n + 1
  if n % 50 == 0 or n == maxf - 3 then
    local out = {}
    for _, k in ipairs(order) do
      local e = seen[k]
      out[#out + 1] = string.format("%s %d %d %d %06X %06X", k, e.first, e.last, e.count, e.lo, e.hi)
    end
    local f = io.open(os.getenv("SHOT_DIR") .. "/rw.txt", "w"); f:write(table.concat(out, "\n") .. "\n"); f:close()
  end
end, emu.eventType.endFrame)
dofile(os.getenv("NEXT"))
