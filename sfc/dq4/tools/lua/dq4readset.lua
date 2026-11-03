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
-- emu.stop 뒤에도 프레임이 더 도는데, 몇 프레임 더 도는지는 실행마다 다르다(머신이 바쁘면 더 돈다). 그 사이 장면
-- 콜백이 기록을 더 쓰면 같은 장면의 출력이 실행마다 달라진다. 그래서 emu.stop 을 부른 뒤로는 장면 콜백을 부르지 않고,
-- 읽은 집합은 emu.stop 때 한 번 쓴다. 출력은 모두 그 앞에 생긴 것이라 그 뒤의 읽기는 결과에 닿지 않는다.
-- testrunner 에서는 scriptEnded 가 오지 않아 그것에 기대지 않는다.
local out = READSET_OUT or os.getenv("READSET_OUT")
if not out then return end
local PRG = emu.memType.snesPrgRom
local CPU = emu.memType.snesMemory
local READ, EXEC = emu.counterType.readCount, emu.counterType.execCount

-- 장면 Lua 의 오류. testrunner 는 콜백 안 오류를 삼키고 다음 프레임을 계속 돌며, emu.stop 뒤에 난 오류에도 0 으로 끝난다.
-- 오류가 나면 읽은 집합 파일을 지우고(그 파일이 없으면 dq4readset.py 가 캐시에 넣지 않는다), .err 와 표준 오류에
-- 적는다. 그 뒤 dump 는 끝줄을 LUAERROR 로 쓴다. 어느 쓰기가 실패해도 캐시에 들지 않는 쪽으로 기운다
local errOut = out .. ".err"
local failed = false
function READSET_FAIL(e)
  failed = true
  os.remove(out)
  local msg = tostring(e)
  pcall(function() io.stderr:write("[dq4readset] Lua 오류: ", msg, "\n") end)
  local f = io.open(errOut, "a")
  if f then f:write(msg, "\n"); f:close() end
end

-- 콜백의 반환값은 개수까지 그대로 넘긴다(메모리 콜백은 값을 돌려주어 읽은·쓴 값을 바꿀 수 있다). 매 명령마다 불리는 콜백도
-- 있어 표를 만들지 않는다
local function pass(ok, ...)
  if not ok then
    local e = ...
    READSET_FAIL(e)
    error(e, 0)
  end
  return ...
end

local stopped = false     -- emu.stop 을 불렀는가. 그 뒤로는 장면 콜백을 부르지 않는다

local function guarded(fn)
  return function(...)
    if stopped then return end
    return pass(pcall(fn, ...))
  end
end

-- MesenCE 는 지울 콜백을 add 가 돌려준 번호로 찾는다(함수를 넘기면 머리말이 없어도 지워지지 않는다). 그래서 감싼
-- 함수를 넘겨도 장면이 받은 번호로 그대로 지워진다. 머리말 자신의 콜백보다 먼저 건다
for _, name in ipairs({"addEventCallback", "addMemoryCallback"}) do
  local orig = emu[name]
  emu[name] = function(fn, ...) return orig(guarded(fn), ...) end
end

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
  lines[#lines + 1] = failed and "LUAERROR" or "OK"
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

local stopOrig = emu.stop
emu.stop = function(...)
  if not stopped then
    stopped = true
    dump()
  end
  return stopOrig(...)
end
