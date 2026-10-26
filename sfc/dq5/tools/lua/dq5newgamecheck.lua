-- 새 게임 일행 쓰기 실측(dq5newgamecheck.py 가 부름). 세이브스테이트 없이 전원부터 A 를 40프레임마다 4프레임 눌러
-- 새 게임을 시작하고, FRAMES(기본 6600) 프레임에 WRAM 을 final.wram, 맵 번호를 newgame.txt, 화면을 end.png 로 남긴다.
-- 롬 이름마다 SRAM 이 남으므로 부르는 쪽이 처음 쓰는 이름의 롬 사본을 준다.
package.path = os.getenv('LIBDIR') .. '/?.lua;' .. package.path
local L = require('lib')
local m = emu.memType.snesMemory
local frames = tonumber(os.getenv('FRAMES') or '6600')
local n = 0
emu.addEventCallback(function()
  n = n + 1
  if n % 40 < 4 then L.press({a = true}) else L.release() end
  if n == frames then
    L.write('newgame.txt', string.format('f%05d map %02X/%02X\n', n, emu.read(0x7E00BC, m), emu.read(0x7E00BD, m)))
    L.dump('final.wram', emu.memType.snesWorkRam, 0x20000)
    L.shot('end.png')
    emu.stop(0)
  end
end, emu.eventType.endFrame)
