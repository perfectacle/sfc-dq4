-- 레이크나바 무기점 손님 겉모습 실제 장면(dq4ch3lakanabacheck 의 looks_real). STATE(출근해 카운터 안에 선 상태)에서 값을
-- 덮어쓰지 않고 사건을 그대로 돌리며, 손님이 카운터 앞에 서 있는 동안만 40프레임마다 A 를 눌러 손님 말을 넘긴다(물음은
-- 커서 그대로 「예」). 손님이 없을 때 누르면 명령 창이 열려 다음 손님이 말을 걸지 못한다.
--   SLOT       손님 물체 슬롯(16진)   COUNTER_X·ROW  손님이 서는 X 와 줄(10진 셀)
--   MAXF       돌릴 프레임 수           SHOT_DIR       그림과 looks.txt 를 둘 곳
-- 손님은 맵 구석에서 문 칸(ROW 줄)으로 순간이동해 들어온다. 그 줄에 처음 든 때부터 카운터 앞에 설 때까지 3프레임마다
-- walk-<차례>-<nn>.png(열여섯 장까지), 선 첫 프레임 arrive-<차례>-<그림>.png. 나가는 걸음은 찍지 않는다.
-- looks.txt 에 「차례 프레임 그림」 줄을 쓴다. 상태를 불러온 뒤 맵 위에 이미 서 있던 손님은 세지 않는다.
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local L = require("lib")
L.loadState(os.getenv("STATE"))
local m = emu.memType.snesMemory
local slot = tonumber(os.getenv("SLOT"), 16)
local counterX, row = tonumber(os.getenv("COUNTER_X")), tonumber(os.getenv("ROW"))
local maxf = tonumber(os.getenv("MAXF") or "30000")
local log = assert(io.open(os.getenv("SHOT_DIR") .. "/looks.txt", "w"))
local n, visit, walking, walkShots, lastA, prevY, present, stood = 0, 0, false, 0, -100, nil, false, nil
local SETTLE = 24
local function rd(a) return emu.read(a, m) end
emu.addEventCallback(function()
  n = n + 1
  local x, y, pic = rd(0x7E3020 + slot), rd(0x7E3080 + slot), rd(0x7E3220 + slot)
  if n == 10 then prevY = y end
  if prevY ~= nil and n > 10 then
    if y == row and prevY ~= row then
      walking, visit, walkShots = true, visit + 1, 0
    end
    if walking and walkShots < 16 and n % 3 == 0 then
      walkShots = walkShots + 1
      L.shot(string.format("walk-%02d-%02d.png", visit, walkShots))
    end
    -- 칸 번호는 걸음을 떼는 순간 다음 칸이 되므로, 카운터 앞 칸이 된 뒤 마지막 걸음이 끝날 때까지 기다려 찍는다
    if walking and x == counterX and not stood then stood = n end
    if walking and stood and n - stood == SETTLE then
      walking, stood = false, nil
      log:write(string.format("%d %d %02X\n", visit, n, pic))
      log:flush()
      L.shot(string.format("arrive-%02d-%02X.png", visit, pic))
    end
    prevY = y
  end
  present = y == row and x == counterX and not walking
  L.release()
  if present and n - lastA >= 40 then lastA = n end
  if n - lastA < 6 then L.press({a = true}) end
  if n >= maxf then
    log:close()
    emu.stop(0)
  end
end, emu.eventType.endFrame)
