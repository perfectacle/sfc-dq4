-- 세이브스테이트로 시작하는 소리 실험에서, 상태를 불러온 뒤 롬의 드라이버 IPL 블록(2B:E676, SPC $28E7~:
-- 샘플 자리 시작·곡 묶음 표 포인터·곡 묶음 표)을 SPC RAM 에 다시 써 넣는다. 세이브스테이트의 SPC RAM 은
-- 그 상태를 만든 롬의 표를 담고 있어, 곡 묶음을 바꾼 롬에서는 드라이버가 새 샘플을 곡의 것으로 보지 않는다.
-- 상태의 SPC 에 고정(칸 플래그 bit4)된 시퀀스 가운데 롬의 고정 목록(2B:C429)에 없는 것은 고정을 푼다.
-- 고정을 푼 시퀀스는 다음 곡 정리(1A 의 16·0A)에서 버려지고, 그 곡을 틀 때 롬의 새 시퀀스가 올라간다.
-- RESIDENT=1 이면 늘 두는 샘플·시퀀스 목록을 바꾼 롬용으로, 상태에 고정된 샘플·시퀀스를 모두 풀고 대기열이 비었을 때
-- 1A FF(앞 곡 정리, 쓰지 않는 자료 버림)·8B 00·93 00(롬 목록대로 다시 고정, 없으면 보냄)을 넣는다. 켤 때 00:A6E1·A6E5 와 같은 일.
-- 그 뒤 SOUND_PROBE(예: sfc/dq5/tools/lua/dq5sndlog.lua)를 그대로 돌린다. AT(기본 2) 프레임에 한 번 쓴다.
local at = tonumber(os.getenv('AT') or '2')
local m = emu.memType.snesMemory
local spc = emu.memType.spcRam
local n, queued = 0, os.getenv('RESIDENT') ~= '1'
local function push(i, cmd, arg)
  i = i & 0x0F
  emu.write(0x7E1D95 + i, cmd, m); emu.write(0x7E1DA5 + i, arg, m)
  emu.write(0x7E1DB5 + i, 0, m); emu.write(0x7E1DC5 + i, 0x05, m)
end
-- 드라이버 블록(2B:C4DB)에서 고친 자리만 롬 것으로 쓴다. 블록에는 실행 중 바뀌는 자료가 있어 통째로 쓰면 전송이 멈췄다.
-- 자료 받기 입구(1046), F7 처리 표 칸(07CD, CHAIN·곡 붙들기 처리기), 곡 붙들기의 빈 자리(1049~1069, 입구를 바꿔 쓰지 않게 된 곳)와
-- 부르는 자리(146C 연주기 템포, 1861 instrument, 103A 받기 끝). 빈 자리를 먼저 써야 부르는 자리가 빈 코드로 뛰지 않는다.
-- SPC 가 쓰려는 자리를 실행하는 중이면 명령 한가운데를 바꾸게 되므로 다음 프레임으로 미룬다
-- 곡/효과음 판정(CMP A,$28EB) 8곳은 곡 번호를 47 넘게 늘린 롬에서 표 뒤 도우미를 부른다
local sites = {{0x1049, 33}, {0x1046, 3}, {0x07CD, 2}, {0x146C, 3}, {0x1861, 3}, {0x103A, 3},
  {0x0AE8, 3}, {0x0B52, 3}, {0x0C45, 3}, {0x11D6, 3}, {0x130F, 3}, {0x1683, 3}, {0x1A2D, 3}, {0x1C5F, 3}}
local entryPending = false
local function writeEntry()
  local pc = emu.getState()['spc.pc']
  for _, site in ipairs(sites) do
    if pc and pc >= site[1] and pc < site[1] + site[2] then return end
  end
  for _, site in ipairs(sites) do
    for i = 0, site[2] - 1 do
      emu.write(site[1] + i, emu.read(0x2BC4DB + 4 + (site[1] - 0x0750) + i, m), emu.memType.spcRam)
    end
  end
  entryPending = false
end
-- 세이브스테이트의 SPC 는 옛 샘플 자리 기준으로 자료를 옮기거나 다시 올리며 늘어난 표·판정 도우미를 덮는다.
-- 표 블록(2B:E676, SPC $28E7~)을 매 프레임 롬과 견주어 다시 쓴다(전원부터 켜면 생기지 않는 실험용 보정)
local function keepTable()
  local size = emu.read(0x2BE676, m) | emu.read(0x2BE677, m) << 8
  for i = 0, size - 1 do
    local v = emu.read(0x2BE67A + i, m)
    if emu.read(0x28E7 + i, spc) ~= v then emu.write(0x28E7 + i, v, spc) end
  end
end
emu.addEventCallback(function()
  n = n + 1
  if entryPending then writeEntry() end
  if n > at then keepTable() end
  if not queued and n > at and emu.read(0x7E1D91, m) == emu.read(0x7E1D93, m) then
    -- 24:FF83 처럼 빈 대기열에서는 쓰기 자리 다음 칸부터 넣고 읽기 자리를 그 칸으로 맞춘다
    local i = emu.read(0x7E1D91, m) + 1
    push(i, 0x1A, 0xFF); push(i + 1, 0x8B, 0x00); push(i + 2, 0x93, 0x00)
    emu.write(0x7E1D93, i & 0x0F, m)
    emu.write(0x7E1D91, (i + 3) & 0x0F, m)
    queued = true
  end
  if n ~= at then return end
  -- 표 블록 뒤에 붙인 블록(빠른 받기 코드 FF00 등)도 끝 표시(크기 0)까지 쓴다
  local base = 0x2BE676
  while true do
    local size = emu.read(base, m) | emu.read(base + 1, m) << 8
    if size == 0 then break end
    local dest = emu.read(base + 2, m) | emu.read(base + 3, m) << 8
    for i = 0, size - 1 do
      emu.write(dest + i, emu.read(base + 4 + i, m), emu.memType.spcRam)
    end
    base = base + 4 + size
  end
  -- 드라이버는 샘플 자리 시작($28E7)을 켤 때만 읽어 $0100(시작)·$0102(D6F6 - 시작)에 둔다. 표가 늘어난 롬에서는
  -- 옛 시작부터 샘플을 다시 올려 표 뒤 판정 도우미를 덮었으므로(SPC 가 샘플 자리를 실행) 롬 값으로 맞춘다
  local heap = emu.read(0x2BE67A, m) | emu.read(0x2BE67B, m) << 8
  local size = 0xD6F6 - heap
  emu.write(0x0100, heap & 0xFF, spc); emu.write(0x0101, heap >> 8, spc)
  emu.write(0x0102, size & 0xFF, spc); emu.write(0x0103, size >> 8, spc)
  entryPending = true
  local pinned, a = {}, 0x2BC429
  while emu.read(a, m) ~= 0xFF do pinned[emu.read(a, m)] = true; a = a + 1 end
  for song = 0, 0x63 do
    local slot = emu.read(0x04C7 + song, emu.memType.spcRam)
    local flag = 0x05D5 + slot * 6 + 5
    if slot ~= 0xFF and (not pinned[song] or not queued) and emu.read(flag, spc) & 0x10 ~= 0 then
      emu.write(flag, emu.read(flag, spc) & 0xEF, spc)
    end
  end
  if not queued then
    -- 롬 목록에 없는 샘플(원래 늘 두던 00 등)은 플래그를 모두 비워야 1A 가 버린다. 고정 비트만 지우면 칸에 남았다
    local resident, b = {}, emu.read(0x2BBFDF + 1, m) | emu.read(0x2BBFDF + 2, m) << 8 | emu.read(0x2BBFDF + 3, m) << 16
    while emu.read(b, m) ~= 0xFF do resident[emu.read(b, m)] = true; b = b + 1 end
    for sample = 0, 0xC7 do
      local slot = emu.read(0x03FF + sample, spc)
      if slot ~= 0xFF then
        local flag = 0x0535 + slot * 8 + 7
        emu.write(flag, resident[sample] and emu.read(flag, spc) & 0xEF or 0, spc)
      end
    end
  end
end, emu.eventType.endFrame)
dofile(os.getenv('SOUND_PROBE'))
