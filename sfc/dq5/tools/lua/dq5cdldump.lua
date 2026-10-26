-- MesenCE 가 이 롬에 쌓은 CDL(emu.getCdlData, 바이트마다 bit0 코드·bit1 자료·bit2 점프 대상·bit3 서브루틴 입구·
-- bit4 X 8비트·bit5 M 8비트)을 SHOT_DIR/cdl.bin 으로 남기고, 같은 폴더의 dq5warp.lua 를 이어 부른다.
-- CDLEVERY(기본 300) 프레임마다와 MAXF-3 프레임에 덮어 쓴다. dq5warp.lua 는 TEST 가 끝나면 스스로 멈추므로 주기로 쓴다.
-- 여러 MesenCE 를 함께 돌리면 디스크의 CDL 은 나중에 끝난 쪽이 덮어쓰므로, 실행마다 이 파일을 남겨 OR 로 합친다.
-- ACCRANGE="1ABC-1BB0" 이면 같은 때에 WRAM 오프셋 범위의 주소마다 읽기·쓰기 횟수(접근 카운터, 3프레임째를 0 으로 침)를
-- RESETAT 프레임에 emu.reset()(같은 실행에서 기록한 SRAM 을 불러오는 장면용).
-- 20프레임마다와 MAXF-3 프레임에 acc.txt 에 「주소 읽기 쓰기」 로 쓴다(0 인 주소는 뺌). 카운터는 주소 지정 방식·뱅크 거울과 상관없이 CPU 접근을 모두 센다.
local fr, every, maxf = 0, tonumber(os.getenv("CDLEVERY") or "300"), tonumber(os.getenv("MAXF") or "3000")
local lo, hi
for a, b in string.gmatch(os.getenv("ACCRANGE") or "", "(%x+)-(%x+)") do lo, hi = tonumber(a, 16), tonumber(b, 16) end
local base_r, base_w
local function counts()
  local w = emu.memType.snesWorkRam
  return emu.getAccessCounters(w, emu.counterType.readCount), emu.getAccessCounters(w, emu.counterType.writeCount)
end
local function dump_acc()
  local rc, wc = counts()
  local out = {string.format("frames=%d", fr)}
  for i = lo, hi do
    local r, w = rc[i] - base_r[i], wc[i] - base_w[i]
    if r ~= 0 or w ~= 0 then out[#out + 1] = string.format("%04X %d %d", i, r, w) end
  end
  local f = io.open(os.getenv("SHOT_DIR") .. "/acc.txt", "w"); f:write(table.concat(out, "\n") .. "\n"); f:close()
end
local function dump()
  local c, b = emu.getCdlData(emu.memType.snesPrgRom), {}
  for i = 0, #c do b[#b + 1] = string.char(c[i] or 0) end
  local f = io.open(os.getenv("SHOT_DIR") .. "/cdl.bin", "wb"); f:write(table.concat(b)); f:close()
end
emu.addEventCallback(function()
  fr = fr + 1
  if lo and fr == 3 then base_r, base_w = counts() end
  if fr == tonumber(os.getenv("RESETAT") or "-1") then emu.reset() end
  if lo and base_r and (fr % 20 == 0 or fr == maxf - 3) then dump_acc() end
  if fr % every == 0 or fr == maxf - 3 then dump() end
end, emu.eventType.endFrame)
local here = debug.getinfo(1, "S").source:match("^@(.*/)") or "./"
dofile(os.getenv("NEXT") or (here .. "dq5warp.lua"))
