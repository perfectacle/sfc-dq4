-- WIPEF 프레임 끝에 VRAM 바이트 WIPE="8000-BFFF" 범위를 0 으로 지운 뒤 NEXT(보통 dq5gfxdump.lua)를 이어 부른다.
-- 다시 보내는 코드가 그 뒤 장면에서 도는지 볼 때 쓴다(dq5gfxlimitcheck.py 의 다시 그리기 시험).
local n, at = 0, tonumber(os.getenv("WIPEF"))
local lo, hi = (os.getenv("WIPE") or "8000-BFFF"):match("(%x+)-(%x+)")
lo, hi = tonumber(lo, 16), tonumber(hi, 16)
emu.addEventCallback(function()
  n = n + 1
  if n == at then
    for a = lo, hi do emu.write(a, 0, emu.memType.snesVideoRam) end
  end
end, emu.eventType.endFrame)
dofile(os.getenv("NEXT"))
