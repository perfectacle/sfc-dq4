-- 필드 세이브스테이트에서 전투를 일으키고, 명령마다 A 를 눌러 몇 턴을 돌리며 정한 PC 에서
-- $96(전투원)·$0B(행동 ID)를 기록하는 드라이버 겸 프로브. 손님 동료(레코드 9 이상)의 AI 를 보려고 만들었다.
-- 조우 판정 18:$9D06 을 메모리상 CLC/RTS 로 바꾸고(롬 파일은 그대로) 위아래로 걷는다(uibattle.lua 와 같음).
-- 환경 변수:
--   STATE          출발 세이브스테이트(필드에서 위아래로 걸을 수 있는 곳, 손님이 일행에 든 상태)
--   SET="6114=C6"  첫 프레임에 한 번 쓸 CPU 주소=바이트들(이어 쓰기)
--   MON="00:1"     무리(16진 ID:마릿수, 쉼표로 넷까지)
--   POKE="6E44=80" 프레임마다 다시 쓸 CPU 주소=바이트들
--   PRG="..."      첫 프레임에 메모리상 PRG ROM 오프셋=바이트들
--   HOOK="10:B497" 뱅크:주소. 닿을 때마다 $96(전투원)·$0B(행동 ID)·A·X·Y 를 적는다
--   MAXF=3000      이 프레임에 guestai.txt 를 쓰고 멈춘다
-- 결과: SHOT_DIR/guestai.txt, end.{ram,sram,...,png}
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local L = require("lib")
L.loadState(os.getenv("STATE"))
local mem = L.mem
local maxf = tonumber(os.getenv("MAXF") or "3000")
local mons = {}
for id, cnt in string.gmatch(os.getenv("MON") or "00:1", "(%x+):(%x+)") do
  mons[#mons + 1] = {tonumber(id, 16), tonumber(cnt, 16)}
end
local ENC, START = 0x18 * 0x4000 + 0x1D06, 0x18 * 0x4000 + 0x211A
local n, hit, out = 0, nil, {}
local function log(s) out[#out + 1] = string.format("%d %s", n, s) end

emu.addMemoryCallback(function(addr)
  if hit or L.prgOffset(addr) ~= START then return end
  hit = n
  for i = 0, 3 do
    local m = mons[i + 1] or {0xFF, 0}
    emu.write(0x6E45 + i, m[1], mem)
    emu.write(0x6E49 + i, m[2], mem)
  end
  log("start")
end, emu.callbackType.exec, 0xA11A, 0xA11A)

for b, a in string.gmatch(os.getenv("HOOK") or "10:B497", "(%x+):(%x+)") do
  local bank, addr = tonumber(b, 16), tonumber(a, 16)
  emu.addMemoryCallback(function(pc)
    if L.prgOffset(pc) ~= bank * 0x4000 + (addr & 0x3FFF) then return end
    local st = emu.getState()
    log(string.format("pc %02X:%04X 96=%02X 0B=%02X A=%02X X=%02X Y=%02X", bank, addr,
      emu.read(0x96, mem), emu.read(0x0B, mem), st["cpu.a"], st["cpu.x"], st["cpu.y"]))
  end, emu.callbackType.exec, addr, addr)
end

emu.addMemoryCallback(function(addr)
  if L.prgOffset(addr) ~= 0x16 * 0x4000 + 0x0656 then return end
  local st = emu.getState()
  log(string.format("msg %02X%02X", st["cpu.x"], st["cpu.a"]))
end, emu.callbackType.exec, 0x8656, 0x8656)

local function pokes(spec, memType, base)
  for a, bytes in string.gmatch(spec or "", "(%x+)=(%x+)") do
    local o = tonumber(a, 16)
    for i = 1, #bytes - 1, 2 do emu.write(o + (i - 1) // 2, tonumber(bytes:sub(i, i + 1), 16), memType) end
  end
end

emu.addEventCallback(function()
  n = n + 1
  if n == 3 then
    emu.write(ENC, 0x18, emu.memType.nesPrgRom)
    emu.write(ENC + 1, 0x60, emu.memType.nesPrgRom)
    pokes(os.getenv("PRG"), emu.memType.nesPrgRom)
    pokes(os.getenv("SET"), mem)
  end
  if n < 5 then return end
  pokes(os.getenv("POKE"), mem)
  if not hit then
    L.press((n // 12) % 2 == 0 and {up = true} or {down = true})
  elseif n > hit + 300 then
    L.press((n // 8) % 4 == 0 and {a = true} or {})
  else
    L.release()
  end
  if n == maxf then
    L.dumpAll("end")
    L.shot("end.png")
    L.write("guestai.txt", table.concat(out, "\n") .. "\n")
    emu.stop()
  end
end, emu.eventType.endFrame)
