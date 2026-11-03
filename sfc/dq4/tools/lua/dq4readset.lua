-- 장면이 실제로 읽은 롬 파일 오프셋을 READSET_OUT 에 쓰는 머리말. dq4readset.py 가 장면 스크립트 앞에 dofile 한다.
-- 형식은 sfc/dq4/docs/dq4-readset-format.md.
--
-- 읽은 집합 = 접근 카운터(snesPrgRom)의 읽기 ∪ 실행(오퍼랜드 포함, DMA 원본 포함) ∪ Lua 가 emu.read* 로 읽은 롬.
-- Lua 의 emu.read 는 카운터에 잡히지 않으므로 여기서 감싸 따로 적는다.
--
-- 첫 세이브스테이트를 불러올 때의 카운터를 밑값으로 두고, 그 뒤 늘어난 바이트만 센다. 불러오기 전의 읽기는 상태가
-- 기계 전체를 덮어 결과에 남지 않는다. 다만 그 전에 상태를 만든 적이 있으면(만든 상태를 다시 불러오는 장면) 밑값을
-- 두지 않는다. 장면이 카운터를 지우면 지우기 전 값을 쌓아 둔다.
--
-- emu.stop 뒤에도 한두 프레임이 더 돌 수 있어(그 사이 스크립트가 기록을 더 쓴다) 멈춘 뒤 프레임마다 다시 쓴다.
-- 이 머리말의 endFrame 콜백이 장면 스크립트 것보다 먼저 걸리므로, 그 프레임에 스크립트가 쓰는 기록보다 뒤의 읽기는 없다.
-- testrunner 에서는 scriptEnded 가 오지 않아 그것에 기대지 않는다.
local out = READSET_OUT or os.getenv("READSET_OUT")
if not out then return end
local PRG = emu.memType.snesPrgRom
local CPU = emu.memType.snesMemory
local READ, EXEC = emu.counterType.readCount, emu.counterType.execCount

local base = nil          -- 밑값 {오프셋 = 읽기+실행}
local created = false     -- 첫 불러오기 전에 상태를 만들었는가
local kept = {}           -- 카운터를 지우기 전까지 읽은 오프셋
local luaRead = {}        -- Lua 가 읽은 롬 오프셋
-- READSET_HDMA 를 주면 HDMA 가 켜질 때 표 첫 바이트(롬이면)를 적어, 그 바이트가 카운터에 잡혔는지 dq4readsetcheck 가 본다
local hdma = os.getenv("READSET_HDMA") and {} or nil

local function snapshot()
  local rc, ec, t = emu.getAccessCounters(PRG, READ), emu.getAccessCounters(PRG, EXEC), {}
  for i = 0, #rc do
    local v = rc[i] + ec[i]
    if v ~= 0 then t[i] = v end
  end
  return t
end

local function touched()
  local now = snapshot()
  local hit = {}
  for i, v in pairs(now) do
    if not base or v > (base[i] or 0) then hit[i] = true end
  end
  for i in pairs(kept) do hit[i] = true end
  for i in pairs(luaRead) do hit[i] = true end
  return hit
end

local function dump()
  local hit, list = touched(), {}
  for i in pairs(hit) do list[#list + 1] = i end
  table.sort(list)
  local lines, s, p = {}, nil, nil
  for _, i in ipairs(list) do
    if s and i == p + 1 then p = i
    else
      if s then lines[#lines + 1] = string.format("%X %X", s, p - s + 1) end
      s, p = i, i
    end
  end
  if s then lines[#lines + 1] = string.format("%X %X", s, p - s + 1) end
  local tmp = out .. ".tmp"
  local f = assert(io.open(tmp, "w"))
  f:write(table.concat(lines, "\n"), "\n")
  f:close()
  os.rename(tmp, out)
  if hdma then
    local h = {}
    for i in pairs(hdma) do h[#h + 1] = string.format("%X %d", i, hit[i] and 1 or 0) end
    table.sort(h)
    f = assert(io.open(out .. ".hdma", "w"))
    f:write(table.concat(h, "\n"), "\n")
    f:close()
  end
end

local function noteRom(addr, memType, n)
  for k = 0, n - 1 do
    if memType == PRG then
      luaRead[addr + k] = true
    elseif memType == CPU or memType == nil then
      local r = emu.convertAddress(addr + k, CPU)
      if r and r.memType == PRG and r.address >= 0 then luaRead[r.address] = true end
    end
  end
end

for name, n in pairs({read = 1, readWord = 2, read16 = 2, read32 = 4}) do
  local orig = emu[name]
  if orig then
    emu[name] = function(addr, memType, ...)
      if memType ~= emu.memType.snesWorkRam and memType ~= emu.memType.snesVideoRam then noteRom(addr, memType, n) end
      return orig(addr, memType, ...)
    end
  end
end

local createOrig = emu.createSavestate
emu.createSavestate = function(...)
  created = true
  return createOrig(...)
end

local loadOrig = emu.loadSavestate
emu.loadSavestate = function(...)
  local r = loadOrig(...)
  if base == nil and not created then base = snapshot() end
  return r
end

local resetOrig = emu.resetAccessCounters
emu.resetAccessCounters = function(...)
  for i in pairs(touched()) do kept[i] = true end
  base = nil
  return resetOrig(...)
end

if hdma then
  local reg = {}
  emu.addMemoryCallback(function(addr, value) reg[addr & 0x7F] = value end, emu.callbackType.write, 0x4300, 0x437F)
  emu.addMemoryCallback(function(addr, value)
    for ch = 0, 7 do
      if value & (1 << ch) ~= 0 then
        local b = ch * 16
        local a = (reg[b + 4] or 0) * 65536 + (reg[b + 3] or 0) * 256 + (reg[b + 2] or 0)
        local r = emu.convertAddress(a, CPU)
        if r and r.memType == PRG and r.address >= 0 then hdma[r.address] = true end
      end
    end
  end, emu.callbackType.write, 0x420C, 0x420C)
end

local stopped = false
local stopOrig = emu.stop
emu.stop = function(...)
  stopped = true
  dump()
  return stopOrig(...)
end
emu.addEventCallback(function() if stopped then dump() end end, emu.eventType.endFrame)
