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
emu.addEventCallback(function()
  n = n + 1
  if not queued and n > at and emu.read(0x7E1D91, m) == emu.read(0x7E1D93, m) then
    -- 24:FF83 처럼 빈 대기열에서는 쓰기 자리 다음 칸부터 넣고 읽기 자리를 그 칸으로 맞춘다
    local i = emu.read(0x7E1D91, m) + 1
    push(i, 0x1A, 0xFF); push(i + 1, 0x8B, 0x00); push(i + 2, 0x93, 0x00)
    emu.write(0x7E1D93, i & 0x0F, m)
    emu.write(0x7E1D91, (i + 3) & 0x0F, m)
    queued = true
  end
  if n ~= at then return end
  local base = 0x2BE676
  local size = emu.read(base, m) | emu.read(base + 1, m) << 8
  local dest = emu.read(base + 2, m) | emu.read(base + 3, m) << 8
  for i = 0, size - 1 do
    emu.write(dest + i, emu.read(base + 4 + i, m), emu.memType.spcRam)
  end
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
