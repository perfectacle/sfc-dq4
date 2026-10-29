-- DQ5: 정한 뱅크의 롬(8000~FFFF, +80 거울 포함)을 읽는 명령을 PC·DB·옵코드별로 모은다. 장면은 DRIVER(dq5warp.lua 등)가 맡는다.
--   DBREAD="1E,1F"  모을 뱅크(16진)
--   DRIVER          이 스크립트 다음에 돌릴 Lua(dq5warp.lua 의 변수는 그대로 간다)
-- 결과: SHOT_DIR/dbread.txt 한 줄 = "K:PC db=DB op=XX n=읽은 횟수 lo=가장 낮은 주소 hi=가장 높은 주소". 60프레임마다 다시 쓴다.
-- DB 로 읽는 명령(abs·abs,X·abs,Y·(dp)·(dp),Y·(dp,X)·(sr),Y)인지는 op 로 가린다.
local out = os.getenv("SHOT_DIR")
local m = emu.memType.snesMemory
local hits = {}

local function dbr(st)
  local v = st["cpu.dbr"]
  if v == nil then error("emu.getState() 에 cpu.dbr 이 없음") end
  return v
end

local function add(addr)
  local st = emu.getState()
  local k, pc = st["cpu.k"], st["cpu.pc"]
  local key = string.format("%02X:%04X db=%02X op=%02X", k, pc, dbr(st), emu.read(k << 16 | pc, m))
  local h = hits[key]
  if not h then h = {n = 0, lo = addr, hi = addr}; hits[key] = h end
  h.n = h.n + 1
  if addr < h.lo then h.lo = addr end
  if addr > h.hi then h.hi = addr end
end

for bank in string.gmatch(os.getenv("DBREAD") or "", "%x+") do
  local b = tonumber(bank, 16)
  for _, v in ipairs({b, b | 0x80}) do
    emu.addMemoryCallback(add, emu.callbackType.read, v << 16 | 0x8000, v << 16 | 0xFFFF)
  end
end

-- EXEC="1F:FD60,25:FA15" 이 명령이 돈 횟수를 DB 별로 같은 파일에 "exec K:PC db=DB n=…" 로 적는다
for bank, pc in string.gmatch(os.getenv("EXEC") or "", "(%x+):(%x+)") do
  local a = tonumber(bank, 16) << 16 | tonumber(pc, 16)
  emu.addMemoryCallback(function()
    local st = emu.getState()
    local key = string.format("exec %02X:%04X db=%02X", a >> 16, a & 0xFFFF, dbr(st))
    hits[key] = hits[key] or {n = 0, lo = 0, hi = 0}
    hits[key].n = hits[key].n + 1
  end, emu.callbackType.exec, a, a)
end

-- DBWIN="1FFD1E,25FAB8" 이 PC 들에 닿을 때 그때의 DB 로 창을 열고, DB 가 그 값인 동안 실행한 명령을
-- SHOT_DIR/dbwin.txt 에 cover.lua 꼴("PC P 횟수")로 적는다. DB 가 DBMISS(기본 5000) 명령 넘게 다른 값이면 창을 닫는다.
-- 모든 명령에 콜백을 거는 동안은 느리므로 창을 연 동안만 건다. 창 안에서 부른 JSL·JSR·BRK 가 길어 창이 닫혀도
-- 돌아오는 자리에서 DB 가 같으면 창을 다시 연다(돌아온 뒤의 명령을 놓치지 않게).
-- 창 안의 BRK 가 돌아온 자리는 SHOT_DIR/dbbrk.txt 에 "BRK 자리 돌아온 자리 횟수" 로 적는다.
local win = os.getenv("DBWIN")
local cover = {}
local brkBack = {}
if win then
  local db, miss, execCb = nil, 0, nil
  local missLimit = tonumber(os.getenv("DBMISS") or "5000")
  local returns = {}
  local onExec
  local function open(value)
    db, miss = value, 0
    if not execCb then execCb = emu.addMemoryCallback(onExec, emu.callbackType.exec, 0, 0xFFFFFF) end
  end
  -- 부른 뒤 돌아오는 자리. BRK 는 서비스마다 인자 수가 다르고(dq5talk.brk_args, 80~93 은 롬 표) 처리기(00:8F80)가
  -- 스택의 PC 를 인자만큼 옮기므로, 처리기의 RTI 가 꺼내는 PC 를 돌아오는 자리로 본다.
  local CALL = {[0x22] = 4, [0x20] = 3, [0xFC] = 3}
  local function watch(back, want)
    local key = back * 256 + want
    if returns[key] then return end
    returns[key] = true
    emu.addMemoryCallback(function()
      if dbr(emu.getState()) == want then open(want) end
    end, emu.callbackType.exec, back, back)
  end
  -- BRK 를 실행할 때의 SP - 4(P·PC·K 를 쌓은 뒤)를 열쇠로, 그 SP 에서 도는 RTI 를 기다린다.
  local brks = {}
  local brkCount = 0
  local function onRti()
    if brkCount == 0 then return end
    local sp = emu.getState()["cpu.sp"]
    local b = brks[sp]
    if b == nil then return end
    brks[sp], brkCount = nil, brkCount - 1
    local back = emu.read(sp + 4, m) << 16 | emu.read(sp + 3, m) << 8 | emu.read(sp + 2, m)
    local key = string.format("%06X %06X", b.pc, back)
    brkBack[key] = (brkBack[key] or 0) + 1
    watch(back, b.db)
  end
  -- 처리기와 서비스는 뱅크 00 이므로 뱅크 00 의 40 바이트(RTI 후보)마다 건다. 명령 중간의 40 은 실행되지 않는다.
  for a = 0x8000, 0xFFFF do
    if emu.read(a, m) == 0x40 then emu.addMemoryCallback(onRti, emu.callbackType.exec, a, a) end
  end
  onExec = function(addr)
    local st = emu.getState()
    if dbr(st) == db then
      miss = 0
      local k = addr * 256 + (st["cpu.ps"] & 0x30)
      cover[k] = (cover[k] or 0) + 1
      local op = emu.read(addr, m)
      local size = CALL[op]
      if size then
        watch((addr & 0xFF0000) | ((addr + size) & 0xFFFF), db)
      elseif op == 0x00 then
        local sp = (st["cpu.sp"] - 4) & 0xFFFF
        if brks[sp] == nil then brkCount = brkCount + 1 end
        brks[sp] = {db = db, pc = addr}
      end
    else
      miss = miss + 1
      if miss > missLimit then
        emu.removeMemoryCallback(execCb, emu.callbackType.exec, 0, 0xFFFFFF)
        execCb, db = nil, nil
      end
    end
  end
  for pc in string.gmatch(win, "%x+") do
    local at = tonumber(pc, 16)
    emu.addMemoryCallback(function() open(dbr(emu.getState())) end, emu.callbackType.exec, at, at)
  end
end

local fr = 0
emu.addEventCallback(function()
  fr = fr + 1
  if fr % 60 ~= 0 then return end
  local t = {}
  for key, h in pairs(hits) do t[#t + 1] = string.format("%s n=%d lo=%06X hi=%06X", key, h.n, h.lo, h.hi) end
  table.sort(t)
  local f = assert(io.open(out .. "/dbread.txt", "w")); f:write(table.concat(t, "\n") .. "\n"); f:close()
  if not win then return end
  t = {}
  for k, n in pairs(cover) do t[#t + 1] = string.format("%06X %02X %d", k >> 8, k & 0xFF, n) end
  table.sort(t)
  f = assert(io.open(out .. "/dbwin.txt", "w")); f:write(table.concat(t, "\n") .. "\n"); f:close()
  t = {}
  for k, n in pairs(brkBack) do t[#t + 1] = string.format("%s %d", k, n) end
  table.sort(t)
  f = assert(io.open(out .. "/dbbrk.txt", "w")); f:write(table.concat(t, "\n") .. "\n"); f:close()
end, emu.eventType.endFrame)
dofile(os.getenv("DRIVER"))
