-- 맵을 불러올 때 슬롯 칸 목록을 옮겨 놓는 실험 프로브. 00:E98E(00:E977 이 $1A2A·$1A2C 를 0 으로 둔 바로 뒤)에서
--   SHIFT=0E   $1A2B(칸 목록 오프셋 위 바이트)를 그 값으로: 목록이 7E:8060 + SHIFT*100 부터 놓임
--   PTR=54     $1A2C(목록 번호 × 2)를 그 값으로: 첫 목록의 주소가 7E:8000 + PTR 에 적힘
-- 그다음 INNER 프로브(보통 dq5gfxdump.lua)를 그대로 돌린다.
package.path = os.getenv('LIBDIR') .. '/?.lua;' .. package.path
local m = emu.memType.snesMemory
local shift = tonumber(os.getenv('SHIFT') or '0', 16)
local ptr = tonumber(os.getenv('PTR') or '0', 16)
emu.addMemoryCallback(function()
  if shift > 0 then emu.write(0x7E1A2B, shift, m) end
  if ptr > 0 then emu.write(0x7E1A2C, ptr, m) end
end, emu.callbackType.exec, 0x00E98E, 0x00E98E)
dofile(os.getenv('INNER'))
