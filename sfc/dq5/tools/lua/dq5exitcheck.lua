-- dq5warp.lua 로 맵에 선 뒤 TEST 로 걸은 결과에 마지막 맵·칸·주인공 층(7E:31A0)·$BE 와, 맵 속성이 들어가는
-- 7E:1A98(조우 구역)·1AA0(전투 배경)·194D·194B(곡 인자), 인물 뒤 슬롯 7E:1983 을 덧붙인다.
-- 영역 이동 플래그 bit6 이 꺼진 레코드가 내는 효과음 갈래(2A:F4D1)를 지나가면 그 횟수도 적는다.
-- LIBDIR 의 boot.lua 자리에 dq5warp.lua 를 둔다(dq5exitcheck.py 가 준비).
-- AUDIT=1 이면 표 뱅크를 DB 로 두는 창(PLB 다음 명령: 출구 2A:F705, 색인 01:9441, 실행기 00:CDF9·2A:F4C2·2A:FD1A)이
-- 열린 뒤 DB 가 그 값인 동안 실행한 명령(dbwin.txt, cover.lua 꼴 "PC P 횟수")과, 그동안 그 뱅크 8000~ 에서 읽은
-- 자료의 주소(dbread.txt, "PC 주소 횟수", 명령 인출 제외)를 적는다. DB 가 5000 명령 넘게 다른 값이면 창을 닫는다.
-- AUDITOPEN="0192F4,0183F0" 이면 그 PC 들에서 창을 연다. AUDITMISS 는 창을 닫는 명령 수(BRK 처리처럼 DB 가 잠시 바뀌는 긴 갈래를 넘길 때).
-- STALE="2AD812-2AF223,..." 이면 표를 옮긴 뒤 비어야 할 옛 자리를 읽은 횟수와 처음 읽은 PC 를 적는다.
package.path = os.getenv('LIBDIR') .. '/?.lua;' .. package.path
local L = require('lib')
local m = emu.memType.snesMemory
local sound = 0
emu.addMemoryCallback(function() sound = sound + 1 end, emu.callbackType.exec, 0x2AF4D1, 0x2AF4D1)
local audit = os.getenv('AUDIT') == '1'
-- MSGLOG=1 이면 메시지 루틴 24:8BAF 에 들어갈 때의 A(메시지 번호)를 모은다. CELL="x,y" 면 끝에 그 셀 8바이트를 적는다.
local msgs = {}
if os.getenv('MSGLOG') == '1' then
  emu.addMemoryCallback(function()
    msgs[#msgs + 1] = string.format('%03X', emu.getState()['cpu.a'] & 0xFFFF)
  end, emu.callbackType.exec, 0x248BAF, 0x248BAF)
end
local stale, staleFirst = 0, nil
local function onStale(addr)
  stale = stale + 1
  if not staleFirst then
    local s = emu.getState()
    staleFirst = string.format('%02X%04X@%06X', s['cpu.k'], s['cpu.pc'], addr)
  end
end
for a, b in string.gmatch(os.getenv('STALE') or '', '(%x+)-(%x+)') do
  -- 뱅크 80~ 은 00~ 의 거울이라 같은 롬을 읽는다.
  for _, mirror in ipairs({0, 0x800000}) do
    emu.addMemoryCallback(onStale, emu.callbackType.read, tonumber(a, 16) | mirror, tonumber(b, 16) | mirror)
  end
end
-- 출구를 다른 뱅크로 옮기면 스텁이 직접 페이지 $86 을 덮는다(원래 로더는 $84·$85 만). $86 은 다른 곳에서도 임시로 쓰므로,
-- 출구 로더가 2A:F709 에 닿은 뒤 다른 코드가 $86 을 다시 쓰기 전에 읽으면(덮은 값에 기대면) 그 PC 를 모은다.
-- [$84] 읽기 11곳은 뺀다(DP86OK, 쉼표로 PC 16진).
local dp86, dirty = {}, false
local dp86ok = {}
for pc in string.gmatch(os.getenv('DP86OK') or '', '%x+') do dp86ok[tonumber(pc, 16)] = true end
emu.addMemoryCallback(function() dirty = true end, emu.callbackType.exec, 0x2AF709, 0x2AF709)
for _, a in ipairs({0x000086, 0x7E0086}) do
  emu.addMemoryCallback(function()
    if not dirty then return end
    local s = emu.getState()
    local pc = (s['cpu.k'] << 16) | s['cpu.pc']
    if not dp86ok[pc] then dp86[string.format('%06X', pc)] = true end
  end, emu.callbackType.read, a, a)
  emu.addMemoryCallback(function()
    local s = emu.getState()
    local pc = (s['cpu.k'] << 16) | s['cpu.pc']
    if not dp86ok[pc] then dirty = false end
  end, emu.callbackType.write, a, a)
end
local cover, reads = {}, {}
if audit then
  local db, miss, pc, execCb, readCb = nil, 0, 0, nil, nil
  local missLimit = tonumber(os.getenv('AUDITMISS') or '5000')
  local function close()
    emu.removeMemoryCallback(execCb, emu.callbackType.exec, 0, 0xFFFFFF)
    emu.removeMemoryCallback(readCb, emu.callbackType.read, 0, 0xFFFFFF)
    execCb, readCb, db = nil, nil, nil
  end
  local function onExec(addr)
    local s = emu.getState()
    pc = addr
    if s['cpu.dbr'] == db then
      miss = 0
      local k = addr * 256 + (s['cpu.ps'] & 0x30)
      cover[k] = (cover[k] or 0) + 1
    else
      miss = miss + 1
      if miss > missLimit then close() end
    end
  end
  local function onRead(addr)
    if db == nil or addr >> 16 ~= db or addr & 0xFFFF < 0x8000 then return end
    if addr >> 16 == pc >> 16 and addr >= pc and addr < pc + 4 then return end
    if emu.getState()['cpu.dbr'] ~= db then return end
    local k = string.format('%06X %06X', pc, addr)
    reads[k] = (reads[k] or 0) + 1
  end
  local opens = {0x2AF705, 0x019441, 0x00CDF9, 0x2AF4C2, 0x2AFD1A}
  if os.getenv('AUDITOPEN') then
    opens = {}
    for pc in string.gmatch(os.getenv('AUDITOPEN'), '%x+') do opens[#opens + 1] = tonumber(pc, 16) end
  end
  for _, open in ipairs(opens) do
    emu.addMemoryCallback(function()
      db, miss = emu.getState()['cpu.dbr'], 0
      if execCb then return end
      execCb = emu.addMemoryCallback(onExec, emu.callbackType.exec, 0, 0xFFFFFF)
      readCb = emu.addMemoryCallback(onRead, emu.callbackType.read, 0, 0xFFFFFF)
    end, emu.callbackType.exec, open, open)
  end
end
local write = L.write
L.write = function(name, data)
  if name == 'warp.txt' then
    data = data .. string.format('final map %02X/%02X cell %d,%d layer %02X BE=%02X sound %d\n', emu.read(0x7E00BC, m),
      emu.read(0x7E00BD, m), emu.read(0x7E3020, m), emu.read(0x7E3080, m), emu.read(0x7E31A0, m), emu.read(0x7E00BE, m), sound)
      .. string.format('stale reads %d %s\n', stale, staleFirst or '-')
      .. string.format('map attrs 1A98=%02X 1AA0=%02X 194D=%02X 194B=%02X 1983=%02X\n', emu.read(0x7E1A98, m),
        emu.read(0x7E1AA0, m), emu.read(0x7E194D, m), emu.read(0x7E194B, m), emu.read(0x7E1983, m))
    data = data .. 'msgs ' .. (#msgs > 0 and table.concat(msgs, ',') or '-') .. '\n'
    local cx, cy = (os.getenv('CELL') or ''):match('(%d+),(%d+)')
    if cx then
      local at = 0x7EC000 + (tonumber(cy) * emu.read(0x7E00BF, m) + tonumber(cx)) * 8
      local c = {}
      for i = 0, 7 do c[#c + 1] = string.format('%02X', emu.read(at + i, m)) end
      data = data .. 'cell ' .. table.concat(c, ' ') .. '\n'
    end
    local t = {}
    for k in pairs(dp86) do t[#t + 1] = k end
    table.sort(t)
    data = data .. 'dp86 ' .. (#t > 0 and table.concat(t, ',') or '-') .. '\n'
    if audit then
      local t, r = {}, {}
      for k, c in pairs(cover) do t[#t + 1] = string.format('%06X %02X %d', k // 256, k % 256, c) end
      for k, c in pairs(reads) do r[#r + 1] = k .. ' ' .. c end
      table.sort(t)
      table.sort(r)
      write('dbwin.txt', table.concat(t, '\n') .. '\n')
      write('dbread.txt', table.concat(r, '\n') .. '\n')
    end
  end
  return write(name, data)
end
dofile(os.getenv('LIBDIR') .. '/boot.lua')
