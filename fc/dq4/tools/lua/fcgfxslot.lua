-- 필드 그림 칸에 표를 올리는 08:$8676(일행 칸과 BRK 0D 87 이 함께 쓰는 몸통)이 불릴 때와 WATCH 범위에 쓸 때 칸·표·부른 곳을 적는다.
-- 입력은 DRIVER(eventwalk.lua·seq.lua 등)가 그대로 준다.
-- 환경 변수:
--   SLOTS="05"     적을 칸(X, 16진, 쉼표). 비우면 모든 칸
--   WATCH="7340-737F"  이 CPU 주소 범위에 쓰는 명령도 적는다(프레임·PC 마다 한 번):
--                  <프레임> w<주소>=<값> pc=<PC> prg=<PRG 오프셋> sp=<스택 위 DEPTH(기본 12)바이트>
--   SHOT_DIR       결과 폴더. fcgfxslot.txt 에 부를 때마다 한 줄(바로 써 두므로 드라이버가 끝내도 남음):
--                  <프레임> X=<칸> A=<표> 6F60=<칸 X 좌표> 6F80=<Y> 63=<그룹> 64=<순번> sp=<스택 위 DEPTH(기본 12)바이트>
-- 스택에는 JSR 복귀 주소(−1)와 BRK 처리기가 쌓은 것이 섞여 있다. 부른 곳은 그 주소의 뱅크를 함께 보고 가린다.
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local L = require("lib")
local want = {}
for a in string.gmatch(os.getenv("SLOTS") or "", "%x+") do want[tonumber(a, 16)] = true end
local any = next(want) == nil
local f = 0
local out = assert(io.open(L.out .. "/fcgfxslot.txt", "w"))
local ENTRY = 0x08 * 0x4000 + 0x0676
local function stack(sp)
  local t = {}
  for i = 1, tonumber(os.getenv("DEPTH") or "12") do t[#t + 1] = string.format("%02X", emu.read(0x100 + ((sp + i) & 0xFF), L.mem)) end
  return table.concat(t, " ")
end
emu.addMemoryCallback(function()
  if L.prgOffset(0x8676) ~= ENTRY then return end
  local st = emu.getState()
  local x = st["cpu.x"]
  if not any and not want[x] then return end
  out:write(string.format("%d X=%02X A=%02X 6F60=%02X 6F80=%02X 63=%02X 64=%02X 0507=%02X sp=%s\n", f, x, st["cpu.a"],
    emu.read(0x6F60 + x, L.mem), emu.read(0x6F80 + x, L.mem), emu.read(0x63, L.mem), emu.read(0x64, L.mem),
    emu.read(0x507, L.mem), stack(st["cpu.sp"])))
  out:flush()
end, emu.callbackType.exec, 0x8676, 0x8676)
-- write 콜백 안의 cpu.pc 는 이미 다음 명령이라 마지막 exec 주소를 쓴다.
local cur, seen = 0, {}
if os.getenv("WATCH") then
  emu.addMemoryCallback(function(a) cur = a end, emu.callbackType.exec, 0, 0xFFFF)
end
for a, b in string.gmatch(os.getenv("WATCH") or "", "(%x+)-(%x+)") do
  emu.addMemoryCallback(function(addr, value)
    local key = f .. ":" .. cur
    if seen[key] then return end
    seen[key] = true
    local off = L.prgOffset(cur)
    out:write(string.format("%d w%04X=%02X pc=%04X prg=%s sp=%s\n", f, addr, value, cur,
      off and string.format("%05X", off) or "-", stack(emu.getState()["cpu.sp"])))
    out:flush()
  end, emu.callbackType.write, tonumber(a, 16), tonumber(b, 16))
end
emu.addEventCallback(function() f = f + 1 end, emu.eventType.endFrame)
L.drive()
