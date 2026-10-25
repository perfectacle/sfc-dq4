-- 필드 세이브스테이트에서 전투를 일으켜 고른 무리로 시작하게 하고, 명령을 받을 때쯤 battle.mss 를 남기는 드라이버.
-- spritebattle.lua 와 같이 조우 판정 18:$9D06 을 메모리상 CLC/RTS 로 바꾸고(롬 파일은 그대로) 위아래로 걷는다.
-- 전투 시작 18:$A11A 에서 무리 칸 $6E45~$6E48(ID)·$6E49~$6E4C(마릿수)를 MON 으로 덮는다.
-- 이어서 창을 고르는 입력은 seq.lua 에 STATE=battle.mss 로 준다.
-- 환경 변수:
--   STATE        출발 세이브스테이트(필드에서 위아래로 걸을 수 있는 곳)
--   MON="05:1"   무리(16진 ID:마릿수, 쉼표로 넷까지). 빈 칸은 FF:0
--   WAIT=300     $A11A 뒤 세이브스테이트를 남길 때까지 기다릴 프레임
--   MAXF=1500    전투가 안 나도 이 프레임에서 멈춘다
-- 결과: SHOT_DIR/battle.mss, end.{ram,sram,chr,nt,pal,oam,png}, battle.txt
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local L = require("lib")
L.loadState(os.getenv("STATE"))
local mons = {}
for id, cnt in string.gmatch(os.getenv("MON") or "", "(%x+):(%x+)") do
  mons[#mons + 1] = {tonumber(id, 16), tonumber(cnt, 16)}
end
local wait = tonumber(os.getenv("WAIT") or "300")
local maxf = tonumber(os.getenv("MAXF") or "1500")
local ENC, START = 0x18 * 0x4000 + 0x1D06, 0x18 * 0x4000 + 0x211A
local n, hit, log, state = 0, nil, {}, "walk"

emu.addMemoryCallback(function(addr)
  if hit or L.prgOffset(addr) ~= START then return end
  hit = n
  for i = 0, 3 do
    local m = mons[i + 1] or {0xFF, 0}
    emu.write(0x6E45 + i, m[1], L.mem)
    emu.write(0x6E49 + i, m[2], L.mem)
  end
  log[#log + 1] = string.format("start frame=%d mon=%s", n, os.getenv("MON") or "")
end, emu.callbackType.exec, 0xA11A, 0xA11A)

local function finish(tag)
  log[#log + 1] = string.format("%s frame=%d", tag, n)
  L.dumpAll("end")
  L.shot("end.png")
  L.write("battle.txt", table.concat(log, "\n") .. "\n")
end

emu.addEventCallback(function()
  n = n + 1
  if n == 3 then
    emu.write(ENC, 0x18, emu.memType.nesPrgRom)
    emu.write(ENC + 1, 0x60, emu.memType.nesPrgRom)
  end
  if n < 5 then return end
  if state == "walk" then
    if hit then
      L.release()
      if n >= hit + wait then
        state = "save"
        L.saveState("battle.mss")
      end
    else
      L.press((n // 12) % 2 == 0 and {up = true} or {down = true})
      if n >= maxf then finish("timeout"); emu.stop() end
    end
  elseif state == "save" then
    state = "done"
    finish("save")
    emu.stop()
  end
end, emu.eventType.endFrame)
