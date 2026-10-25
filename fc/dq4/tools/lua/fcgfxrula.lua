-- ルーラ·キメラのつばさ 목록에서 고른 순번($76)을 바꿔 1E:$AE19 에 원하는 목적지 번호가 들어가게 한다.
-- 10:$951E(디버그 목록, $C000 bit4 = 0)나 10:$952A(제품판 목록)가 $76 을 읽기 직전에 $76 = PICK 으로 쓴다.
-- 1E:$AE2E(레코드 번호가 A 에 정해진 자리)와 $AE96·$AEBE(레코드를 다 쓴 자리)에서 RAM 을 적는다.
-- 환경 변수: PICK(16진), AT(기본 951E), 드라이버(DRIVER, 기본 boot.lua)와 그 변수, SHOT_DIR, MAXF.
-- 결과: SHOT_DIR/fcgfxrula.txt(MAXF-1 프레임에 한 번 쓰므로 MAXF 를 꼭 준다) — 지날 때마다 한 줄:
--   <프레임> <pick|AE2E|AE96|AEBE> A=<A> 0063=… 0064=… 0044=… 0045=… 0065=… 0042=… 0043=… 6195=… ~ 6198=…
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local L = require("lib")
local pick = tonumber(os.getenv("PICK") or "0", 16)
local at = tonumber(os.getenv("AT") or "951E", 16)
local maxf = tonumber(os.getenv("MAXF") or "0")
local f, log = 0, {}
local regs = {0x63, 0x64, 0x44, 0x45, 0x65, 0x42, 0x43, 0x6195, 0x6196, 0x6197, 0x6198}
local function line(tag)
  local st = emu.getState()
  local t = {string.format("%d %s A=%02X", f, tag, st["cpu.a"])}
  for _, a in ipairs(regs) do t[#t + 1] = string.format("%04X=%02X", a, emu.read(a, L.mem)) end
  log[#log + 1] = table.concat(t, " ")
end
emu.addMemoryCallback(function()
  if L.prgOffset(at) and L.prgOffset(at) >> 14 == 0x10 then
    emu.write(0x76, pick, L.mem)
    line("pick")
  end
end, emu.callbackType.exec, at, at)
for _, a in ipairs({0xAE2E, 0xAE96, 0xAEBE}) do
  emu.addMemoryCallback(function()
    if L.prgOffset(a) and L.prgOffset(a) >> 14 == 0x1E then line(string.format("%04X", a)) end
  end, emu.callbackType.exec, a, a)
end
emu.addEventCallback(function()
  f = f + 1
  if f == maxf - 1 then L.write("fcgfxrula.txt", table.concat(log, "\n") .. "\n") end
end, emu.eventType.endFrame)
L.drive()
