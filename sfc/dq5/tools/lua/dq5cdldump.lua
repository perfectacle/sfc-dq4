-- MesenCE 가 이 롬에 쌓은 CDL(emu.getCdlData, 바이트마다 bit0 코드·bit1 자료·bit2 점프 대상·bit3 서브루틴 입구·
-- bit4 X 8비트·bit5 M 8비트)을 SHOT_DIR/cdl.bin 으로 남기고, 같은 폴더의 dq5warp.lua 를 이어 부른다.
-- CDLEVERY(기본 300) 프레임마다와 MAXF-3 프레임에 덮어 쓴다. dq5warp.lua 는 TEST 가 끝나면 스스로 멈추므로 주기로 쓴다.
-- 여러 MesenCE 를 함께 돌리면 디스크의 CDL 은 나중에 끝난 쪽이 덮어쓰므로, 실행마다 이 파일을 남겨 OR 로 합친다.
local fr, every, maxf = 0, tonumber(os.getenv("CDLEVERY") or "300"), tonumber(os.getenv("MAXF") or "3000")
local function dump()
  local c, b = emu.getCdlData(emu.memType.snesPrgRom), {}
  for i = 0, #c do b[#b + 1] = string.char(c[i] or 0) end
  local f = io.open(os.getenv("SHOT_DIR") .. "/cdl.bin", "wb"); f:write(table.concat(b)); f:close()
end
emu.addEventCallback(function()
  fr = fr + 1
  if fr % every == 0 or fr == maxf - 3 then dump() end
end, emu.eventType.endFrame)
local here = debug.getinfo(1, "S").source:match("^@(.*/)") or "./"
dofile(os.getenv("NEXT") or (here .. "dq5warp.lua"))
