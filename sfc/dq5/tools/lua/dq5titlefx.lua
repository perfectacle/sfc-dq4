-- 타이틀 세이브스테이트(STATE)에서 MAXF 프레임 동안 프레임 끝마다 $075B(1)·$71(2)·$75(2)·7E:A000~A1E6(HDMA 간접 표와 물결 값)·
-- 7E:A4DC~A4EB(BG4 가로 HDMA 표)·OAM 앞 48바이트(반짝이 12개)를 이어 붙여 SHOT_DIR/titlefx.bin 에 쓴다. dq5titlefx.py --check 가 읽는다.
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local L = require("lib")
local maxf = tonumber(os.getenv("MAXF") or "1300")
local W, O = emu.memType.snesWorkRam, emu.memType.snesSpriteRam
local n, out = 0, {}
local function rd(m, a, len) local t = {} for i = 0, len - 1 do t[#t + 1] = string.char(emu.read(a + i, m)) end return table.concat(t) end
L.loadState(os.getenv("STATE"))
emu.addEventCallback(function()
  n = n + 1
  out[#out + 1] = rd(W, 0x075B, 1) .. rd(W, 0x71, 2) .. rd(W, 0x75, 2) .. rd(W, 0xA000, 0x1E7) .. rd(W, 0xA4DC, 16) .. rd(O, 0, 48)
  if n == maxf then L.write("titlefx.bin", table.concat(out)); emu.stop() end
end, emu.eventType.endFrame)
