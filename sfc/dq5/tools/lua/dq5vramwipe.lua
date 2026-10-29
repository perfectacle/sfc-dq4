-- WIPEF 프레임 끝에 VRAM 바이트 WIPE="8000-BFFF" 범위를 0 으로 지운 뒤 NEXT(보통 dq5gfxdump.lua)를 이어 부른다.
-- 다시 보내는 코드가 그 뒤 장면에서 도는지 볼 때 쓴다(dq5gfxlimitcheck.py 의 다시 그리기 시험).
-- WIPEF 를 주지 않으면 지우지 않고 EXECLOG 만 적는다(dq5gfxlimitcheck.py 의 다시 불러오기 시험).
--   EXECLOG="01A4A7,00A788"  이 PC 들이 실행된 프레임을 SHOT_DIR/exec.txt 에 "PC 프레임" 줄로 적는다
local n, at = 0, tonumber(os.getenv("WIPEF"))
assert(os.getenv("NEXT"), "NEXT 필요")
local lo, hi = (os.getenv("WIPE") or "8000-BFFF"):match("(%x+)-(%x+)")
lo, hi = tonumber(lo, 16), tonumber(hi, 16)
local log = {}
local function flush()
  local f = io.open(os.getenv("SHOT_DIR") .. "/exec.txt", "w"); f:write(table.concat(log, "\n"), "\n"); f:close()
end
for a in string.gmatch(os.getenv("EXECLOG") or "", "%x+") do
  local pc = tonumber(a, 16)
  emu.addMemoryCallback(function()
    log[#log + 1] = string.format("%06X %d", pc, n)
    flush()
  end, emu.callbackType.exec, pc, pc)
end
emu.addEventCallback(function()
  n = n + 1
  if n == at then
    for a = lo, hi do emu.write(a, 0, emu.memType.snesVideoRam) end
  end
end, emu.eventType.endFrame)
dofile(os.getenv("NEXT"))
