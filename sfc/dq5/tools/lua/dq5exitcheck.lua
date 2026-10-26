-- dq5warp.lua 로 맵에 선 뒤 TEST 로 걸은 결과에 마지막 맵·칸·주인공 층(7E:31A0)·$BE 를 덧붙인다.
-- 영역 이동 플래그 bit6 이 꺼진 레코드가 내는 효과음 갈래(2A:F4D1)를 지나가면 그 횟수도 적는다.
-- LIBDIR 의 boot.lua 자리에 dq5warp.lua 를 둔다(dq5exitcheck.py 가 준비).
-- AUDIT=1 이면 표 뱅크를 DB 로 두는 창(PLB 다음 명령: 출구 2A:F705, 색인 01:9441, 실행기 00:CDF9·2A:F4C2·2A:FD1A)이
-- 열린 뒤 DB 가 그 값인 동안 실행한 명령(dbwin.txt, cover.lua 꼴 "PC P 횟수")과, 그동안 그 뱅크 8000~ 에서 읽은
-- 자료의 주소(dbread.txt, "PC 주소 횟수", 명령 인출 제외)를 적는다. DB 가 5000 명령 넘게 다른 값이면 창을 닫는다.
-- STALE="2AD812-2AF223,..." 이면 표를 옮긴 뒤 비어야 할 옛 자리를 읽은 횟수와 처음 읽은 PC 를 적는다.
package.path = os.getenv('LIBDIR') .. '/?.lua;' .. package.path
local L = require('lib')
local m = emu.memType.snesMemory
local sound = 0
emu.addMemoryCallback(function() sound = sound + 1 end, emu.callbackType.exec, 0x2AF4D1, 0x2AF4D1)
local audit = os.getenv('AUDIT') == '1'
local stale, staleFirst = 0, nil
for a, b in string.gmatch(os.getenv('STALE') or '', '(%x+)-(%x+)') do
  emu.addMemoryCallback(function(addr)
    stale = stale + 1
    if not staleFirst then
      local s = emu.getState()
      staleFirst = string.format('%02X%04X@%06X', s['cpu.k'], s['cpu.pc'], addr)
    end
  end, emu.callbackType.read, tonumber(a, 16), tonumber(b, 16))
end
local cover, reads = {}, {}
if audit then
  local db, miss, pc, execCb, readCb = nil, 0, 0, nil, nil
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
      if miss > 5000 then close() end
    end
  end
  local function onRead(addr)
    if db == nil or addr >> 16 ~= db or addr & 0xFFFF < 0x8000 then return end
    if addr >> 16 == pc >> 16 and addr >= pc and addr < pc + 4 then return end
    if emu.getState()['cpu.dbr'] ~= db then return end
    local k = string.format('%06X %06X', pc, addr)
    reads[k] = (reads[k] or 0) + 1
  end
  for _, open in ipairs({0x2AF705, 0x019441, 0x00CDF9, 0x2AF4C2, 0x2AFD1A}) do
    emu.addMemoryCallback(function()
      if execCb then return end
      db, miss = emu.getState()['cpu.dbr'], 0
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
