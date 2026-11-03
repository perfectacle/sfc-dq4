-- DQ4: 인물 슬롯의 숨음 바이트 $7020+슬롯 쓰기를 감시하고, 그 뒤 NEXT 프로브(talk.lua·talkwin.lua 등)를 그대로 돌린다.
-- 들어설 때 숨는 인물이 언제 누구에게 드러나는지 볼 때 쓴다. 환경 변수(16진은 따로 적음):
--   WSLOTS=06,07       감시할 슬롯(16진). 쓰기마다 w7020.txt 에 「프레임 w 주소=값 pc= prg= map= xy=」
--   WEXTRA=6F71,6F91   더 감시할 CPU 주소(16진). 인물 자리 $6F60/$6F80+슬롯 등
--   SNAP=300,2000      그 프레임(10진)에 슬롯마다 「슬롯:$7020@X,Y」 줄과 화면 fNNNNN.png
--   FORCEHIDE=15       그 슬롯(16진)의 $7020 bit7 을 매 프레임 켠다. 같은 장면과 화면을 견주어 그 인물이 그려지는지 본다.
--                      $7020 이 FF 면 빈 슬롯이라(fc/dq4/docs/dq4-npcblock-format.md 「인물 표 열」) 건드리지 않는다.
--                      이 emu.write 는 쓰기 감시 콜백을 부르지 않아 w7020.txt 에는 게임의 쓰기만 남는다
--   NEXT               이어 돌릴 프로브의 절대 경로. MAXF 는 그 프로브와 같은 값을 쓴다(MAXF-2 에 w7020.txt 를 씀)
-- 드라이버가 MAXF 보다 먼저 멈추면(seq.lua 는 SEQ·TAIL 뒤에 멈춤) w7020.txt 가 남지 않으므로 MAXF 를 그보다 작게 준다.
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local L = require("lib")
local f, log = 0, {}

local function hexes(name)
  local out = {}
  for t in string.gmatch(os.getenv(name) or "", "%x+") do out[#out + 1] = tonumber(t, 16) end
  return out
end

local slots, forceHide = hexes("WSLOTS"), hexes("FORCEHIDE")
local snaps = {}
for t in string.gmatch(os.getenv("SNAP") or "", "%d+") do snaps[tonumber(t)] = true end

local function where()
  return string.format("map=%02X/%02X xy=%02X,%02X", emu.read(0x63, L.mem), emu.read(0x64, L.mem),
    emu.read(0x44, L.mem), emu.read(0x45, L.mem))
end

local function watch(a)
  emu.addMemoryCallback(function(addr, v)
    local pc = emu.getState()["cpu.pc"]
    log[#log + 1] = string.format("%d w %04X=%02X pc=%04X prg=%05X %s", f, addr, v, pc, L.prgOffset(pc) or 0, where())
  end, emu.callbackType.write, a, a)
end
for _, s in ipairs(slots) do watch(0x7020 + s) end
for _, a in ipairs(hexes("WEXTRA")) do watch(a) end

local maxf = tonumber(os.getenv("MAXF") or "1500")
emu.addEventCallback(function()
  f = f + 1
  for _, s in ipairs(forceHide) do
    local v = emu.read(0x7020 + s, L.mem)
    if v ~= 0xFF then emu.write(0x7020 + s, v | 0x80, L.mem) end
  end
  if snaps[f] then
    local t = {}
    for _, s in ipairs(slots) do
      t[#t + 1] = string.format("%02X:%02X@%02X,%02X", s, emu.read(0x7020 + s, L.mem), emu.read(0x6F60 + s, L.mem),
        emu.read(0x6F80 + s, L.mem))
    end
    log[#log + 1] = string.format("%d snap %s %s", f, where(), table.concat(t, " "))
    L.shot(string.format("f%05d.png", f))
  end
  if f == maxf - 2 then L.write("w7020.txt", table.concat(log, "\n") .. "\n") end
end, emu.eventType.endFrame)

dofile(os.getenv("NEXT"))
