-- 읽은 롬 바이트 캐시 건전성 검사용: 롬 파일 3F0000(FE:8000)에 HDMA 표를 쓰고 채널 7 로 켠 뒤 몇 프레임 돌고 멈춘다.
-- 표 바이트가 읽은 집합에 드는지 dq4readsetcheck 가 본다(HDMA 표 읽기가 접근 카운터에 잡히는가).
local TABLE = {0x02, 0xAA, 0x02, 0xBB, 0x00}
local n = 0
emu.addEventCallback(function()
  n = n + 1
  if n == 99 then
    for i, b in ipairs(TABLE) do emu.write(0x3F0000 + i - 1, b, emu.memType.snesPrgRom) end
  elseif n == 100 then
    for a, v in pairs({[0x4370] = 0x00, [0x4371] = 0x0D, [0x4372] = 0x00, [0x4373] = 0x80, [0x4374] = 0xFE}) do
      emu.write(a, v, emu.memType.snesMemory)
    end
    emu.write(0x420C, 0x80, emu.memType.snesMemory)
  elseif n == 104 then
    emu.stop(0)
  end
end, emu.eventType.endFrame)
