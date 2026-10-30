-- 필드 세계 $1949 에 쓰는 곳과 값, 그리고 세계를 읽는 루틴(READPC, 기본 00:BBAC)에 들어갈 때의 $1949 를 모은 뒤 NEXT 를 부른다.
-- 쓰기는 WRAM 오프셋(snesWorkRam 1949)에 건다. CPU 주소에 건 감시와 달리 00:1949 거울·MVN·$2180 포트 DMA 쓰기도 잡힌다.
-- WATCHW="075E,075F" 를 주면 그 WRAM 오프셋에 쓰는 것도 같은 꼴로 모은다.
-- 결과: SHOT_DIR/world.txt
--   "write PC 값 첫프레임 횟수"  PC·값마다 한 줄
--   "read PC 값 첫프레임 횟수"   READPC 에 들어갈 때의 $1949 값마다 한 줄
--   "wXXXX PC 값 첫프레임 횟수"  WATCHW 의 오프셋 XXXX 에 쓴 PC·값마다 한 줄
local n, writes, reads, order, kinds = 0, {}, {}, {}, {}
assert(os.getenv("NEXT"), "NEXT 필요")
local function note(tbl, key)
  local e = tbl[key]
  if not e then
    e = {first = n, count = 0}
    tbl[key] = e
    order[#order + 1] = {tbl, key}
  end
  e.count = e.count + 1
end
local function flush()
  local t = {}
  for _, o in ipairs(order) do
    local e = o[1][o[2]]
    t[#t + 1] = string.format("%s %s %d %d", kinds[o[1]], o[2], e.first, e.count)
  end
  local f = io.open(os.getenv("SHOT_DIR") .. "/world.txt", "w"); f:write(table.concat(t, "\n"), "\n"); f:close()
end
kinds[writes], kinds[reads] = "write", "read"
local function watch(addr, tbl)
  emu.addMemoryCallback(function(_, value)
    local s = emu.getState()
    note(tbl, string.format("%02X%04X %02X", s["cpu.k"], s["cpu.pc"], value))
    flush()
  end, emu.callbackType.write, addr, addr, emu.cpuType.snes, emu.memType.snesWorkRam)
end
watch(0x1949, writes)
for a in string.gmatch(os.getenv("WATCHW") or "", "%x+") do
  local tbl = {}
  kinds[tbl] = "w" .. a:upper()
  watch(tonumber(a, 16), tbl)
end
for a in string.gmatch(os.getenv("READPC") or "00BBAC", "%x+") do
  local pc = tonumber(a, 16)
  emu.addMemoryCallback(function()
    note(reads, string.format("%06X %02X", pc, emu.read(0x1949, emu.memType.snesWorkRam)))
  end, emu.callbackType.exec, pc, pc)
end
emu.addEventCallback(function()
  n = n + 1
  if n % 10 == 0 then flush() end
end, emu.eventType.endFrame)
dofile(os.getenv("NEXT"))
