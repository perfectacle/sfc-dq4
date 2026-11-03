-- DQ5 인물 슬롯의 걸음을 맵을 불러온 프레임부터 멈추고, HOLD_NEXT 프로브를 그대로 돌린다(dq4sleepercheck 가 씀).
-- 7E:3300+슬롯은 위 니블이 이동 간격이고, 간격이 8 이상이면 아래 니블에 같은 간격 인물끼리 걸음을 엇갈리게 하는
-- 차례 번호가 든다(sfc/dq5/docs/dq5-map-format.md). 매 프레임 읽어 위 니블만 0 으로 다시 쓰고 아래 니블은 그대로
-- 둔다. 바이트를 통째로 쓰는 POKE 를 쓰지 않는 까닭이다.
--   HOLD_SLOTS="08-1F" 멈출 슬롯 범위(16진, 끝 포함)
--   HOLD_NEXT          이어 돌릴 프로브의 절대 경로
local first, last = (os.getenv("HOLD_SLOTS") or ""):match("^(%x+)-(%x+)$")
if not first then error('dq4holdwalk.lua: HOLD_SLOTS 에 멈출 슬롯 범위를 "08-1F" 꼴로 주세요') end
if not os.getenv("HOLD_NEXT") then error("dq4holdwalk.lua: HOLD_NEXT 에 이어 돌릴 프로브 경로를 주세요") end
first, last = tonumber(first, 16), tonumber(last, 16)
local m = emu.memType.snesMemory
emu.addEventCallback(function()
  for s = first, last do
    local a = 0x7E3300 + s
    local v = emu.read(a, m)
    if v & 0xF0 ~= 0 then emu.write(a, v & 0x0F, m) end
  end
end, emu.eventType.endFrame)
dofile(os.getenv("HOLD_NEXT"))
