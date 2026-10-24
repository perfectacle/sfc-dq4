-- 정해 둔 프레임마다 화면과 BG 를 그리는 데 필요한 PPU 메모리를 덤프한다(타이틀·오프닝·창 같은 장면 렌더링용).
-- 입력은 DRIVER(기본 boot.lua, seq.lua 도 됨)가 준다. 전원을 켜서 시작할 때는 debugsram.lua 의 SRAM_DRIVER 로 이 파일을 준다.
-- 환경 변수:
--   AT="300,420,..."   덤프할 프레임(이 Lua 가 센 endFrame 수)
--   SHOT_DIR           결과 폴더. 프레임마다 fNNNNN.png(화면), .nt(2KB), .chr(8KB), .pal(32B), .oam, .ram, .ppu($2000 쓰기 값),
--                      .oam2(화면을 찍은 프레임의 OAM. 화면이 어느 프레임 것인지 모호해 스프라이트 자리를 두 OAM 으로 가린다)
--   STOP               이 프레임에서 멈춤(기본 AT 의 마지막 + 5)
-- 화면 덤프는 한 프레임 늦게 바뀌므로(fc/dq4/tools/lua/fcgfxpal.lua) PPU 메모리는 AT 앞 프레임, 화면은 AT 프레임에 찍는다.
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local L = require("lib")
local at, last = {}, 0
for f in string.gmatch(os.getenv("AT") or "", "%d+") do
  local n = tonumber(f); at[n] = true; if n > last then last = n end
end
local stop = tonumber(os.getenv("STOP") or tostring(last + 5))
local ctrl = 0
-- $2000(PPUCTRL)의 마지막 값: BG 패턴 표($0000/$1000)는 bit4
emu.addMemoryCallback(function(addr, value) ctrl = value end, emu.callbackType.write, 0x2000, 0x2000)
local n = 0
emu.addEventCallback(function()
  n = n + 1
  if at[n + 1] then
    local p = string.format("f%05d", n + 1)
    L.dump(p .. ".nt", emu.memType.nesNametableRam)
    L.dump(p .. ".chr", emu.memType.nesChrRam)
    L.dump(p .. ".pal", emu.memType.nesPaletteRam)
    L.dump(p .. ".oam", emu.memType.nesSpriteRam)
    L.dump(p .. ".ram", emu.memType.nesInternalRam)
    L.write(p .. ".ppu", string.char(ctrl))
  end
  if at[n] then
    L.shot(string.format("f%05d.png", n))
    L.dump(string.format("f%05d.oam2", n), emu.memType.nesSpriteRam)
  end
  if n >= stop then emu.stop(0) end
end, emu.eventType.endFrame)
L.drive()
