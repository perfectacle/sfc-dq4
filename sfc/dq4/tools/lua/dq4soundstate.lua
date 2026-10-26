-- 세이브스테이트로 시작하는 소리 실험에서, 상태를 불러온 뒤 롬의 드라이버 IPL 블록(2B:E676, SPC $28E7~:
-- 샘플 자리 시작·곡 묶음 표 포인터·곡 묶음 표)을 SPC RAM 에 다시 써 넣는다. 세이브스테이트의 SPC RAM 은
-- 그 상태를 만든 롬의 표를 담고 있어, 곡 묶음을 바꾼 롬에서는 드라이버가 새 샘플을 곡의 것으로 보지 않는다.
-- 상태의 SPC 에 고정(칸 플래그 bit4)된 시퀀스 가운데 롬의 고정 목록(2B:C429)에 없는 것은 고정을 푼다.
-- 고정을 푼 시퀀스는 다음 곡 정리(1A 의 16·0A)에서 버려지고, 그 곡을 틀 때 롬의 새 시퀀스가 올라간다.
-- 그 뒤 SOUND_PROBE(예: sfc/dq5/tools/lua/dq5sndlog.lua)를 그대로 돌린다. AT(기본 2) 프레임에 한 번 쓴다.
local at = tonumber(os.getenv('AT') or '2')
local m = emu.memType.snesMemory
local n = 0
emu.addEventCallback(function()
  n = n + 1
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
    if slot ~= 0xFF and not pinned[song] and emu.read(flag, emu.memType.spcRam) & 0x10 ~= 0 then
      emu.write(flag, emu.read(flag, emu.memType.spcRam) & 0xEF, emu.memType.spcRam)
    end
  end
end, emu.eventType.endFrame)
dofile(os.getenv('SOUND_PROBE'))
