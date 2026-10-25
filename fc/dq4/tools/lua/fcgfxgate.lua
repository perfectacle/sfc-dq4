-- 정해 둔 프레임마다 dq4fcgfx.py verify 가 읽는 덤프(end.ram·sram·nt·chr·pal·oam·png)를 프레임별 폴더에 남긴다.
-- 성문 연출처럼 프레임마다 블록 → 타일 표($7600)가 바뀌는 장면을 견주는 데 쓴다.
-- 화면 덤프는 한 프레임 늦게 바뀌므로(fc/dq4/tools/lua/fcgfxpal.lua) 메모리는 AT 앞 프레임, 화면은 AT 프레임에 찍는다.
-- seq.lua 의 end.* 는 메모리와 화면을 같은 프레임에 찍어, $7600 이 막 바뀐 프레임에서는 화면이 한 프레임 앞 것이다.
-- 입력은 DRIVER(seq.lua)가 준다. MesenCE 에 --nes.disableSprites=true --nes.forceBackgroundFirstColumn=true 를 준다.
-- 환경 변수:
--   AT="100,105,..."   덤프할 프레임(이 Lua 가 센 endFrame 수)
--   SHOT_DIR           결과 폴더. 프레임마다 SHOT_DIR/fNNNNN/end.*(폴더는 미리 만들 것)
--   STOP               이 프레임에서 멈춤(기본 AT 의 마지막 + 5)
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local L = require("lib")
local at, last = {}, 0
for f in string.gmatch(os.getenv("AT") or "", "%d+") do
  local n = tonumber(f); at[n] = true; if n > last then last = n end
end
local stop = tonumber(os.getenv("STOP") or tostring(last + 5))
local n = 0
emu.addEventCallback(function()
  n = n + 1
  if at[n + 1] then
    L.dumpAll(string.format("f%05d/end", n + 1))
  end
  if at[n] then
    L.shot(string.format("f%05d/end.png", n))
  end
  if n >= stop then emu.stop(0) end
end, emu.eventType.endFrame)
L.drive()
