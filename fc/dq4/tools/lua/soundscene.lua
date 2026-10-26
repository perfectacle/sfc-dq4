-- 장면마다 게임이 고른 곡을 적는다. APU 쓰기는 적지 않으므로 긴 장면에도 쓸 수 있다.
-- scene.txt(MAXF-1 프레임)에 다음 줄을 쓴다:
--   S 프레임 A 탈것($0515) 그룹($63) 순번($64) 필드($65)   소리 입구 1F:$C01F(곡·효과음 시작)
--   C 프레임 주소 A                                       $C022·$C025·$C028·$C02B(페이드·음량·기다림)
--   B 프레임 곡                                           지금 곡($BF >> 1)이 바뀐 프레임
--   X 프레임 주소 A                                       맵 곡 고르기 19:$803B 안의 x3 호출이 돌아온 자리
--                                                         ($806F 은 x3 2B 63 41, $8050 은 x3 62 63 41 의 A)
--   E 프레임 PC 값                                        $6BF9(명령 EB 가 늘리는 셈)를 읽은 곳과 그 값(EVERY_READ=1 일 때,
--                                                         PC 는 읽은 명령의 다음 자리). 같은 PC·값이 이어지면 첫 줄만 쓴다
-- SHOTS="1970,2065" 를 주면 그 프레임마다 화면을 shot-프레임.png 로 남긴다.
-- POKE="0515=01;6292=FF" 를 주면 POKEAT 프레임(기본 1)에 그 바이트들을 쓴다.
-- 끝에서 입력 드라이버(DRIVER, 예: seq.lua·warp.lua)를 돌린다.
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local L = require("lib")
local mem = L.mem
local maxf = tonumber(os.getenv("MAXF") or "1500")
local pokeAt = tonumber(os.getenv("POKEAT") or "1")
local poke = os.getenv("POKE")
local f, out, last = 0, {}, -1
local shots = {}
for n in string.gmatch(os.getenv("SHOTS") or "", "%d+") do shots[tonumber(n)] = true end
local base = 0x1F * 0x4000
local function rd(a) return emu.read(a, mem) end

emu.addMemoryCallback(function(addr)
  if L.prgOffset(addr) ~= base + 0x001F then return end
  out[#out + 1] = string.format("S %d %02X %02X %02X %02X %02X", f, emu.getState()["cpu.a"],
    rd(0x0515), rd(0x63), rd(0x64), rd(0x65))
end, emu.callbackType.exec, 0xC01F, 0xC01F)

for _, e in ipairs({0xC022, 0xC025, 0xC028, 0xC02B}) do
  emu.addMemoryCallback(function(addr)
    if L.prgOffset(addr) ~= base + (e - 0xC000) then return end
    out[#out + 1] = string.format("C %d %04X %02X", f, e, emu.getState()["cpu.a"])
  end, emu.callbackType.exec, e, e)
end

for _, e in ipairs({0x806F, 0x8050}) do
  emu.addMemoryCallback(function(addr)
    if L.prgOffset(addr) ~= 0x19 * 0x4000 + (e - 0x8000) then return end
    out[#out + 1] = string.format("X %d %04X %02X", f, e, emu.getState()["cpu.a"])
  end, emu.callbackType.exec, e, e)
end

if os.getenv("EVERY_READ") == "1" then
  local prev
  emu.addMemoryCallback(function(addr, value)
    local key = string.format("%04X %02X", emu.getState()["cpu.pc"], value)
    if key ~= prev then out[#out + 1] = string.format("E %d %s", f, key); prev = key end
  end, emu.callbackType.read, 0x6BF9, 0x6BF9)
end

emu.addEventCallback(function()
  f = f + 1
  if poke and f == pokeAt then
    for a, bytes in string.gmatch(poke, "(%x+)=(%x+)") do
      local addr = tonumber(a, 16)
      for i = 1, #bytes - 1, 2 do emu.write(addr + (i - 1) // 2, tonumber(bytes:sub(i, i + 1), 16), mem) end
    end
  end
  local cur = rd(0xBF) >> 1
  if cur ~= last then out[#out + 1] = string.format("B %d %02X", f, cur); last = cur end
  if shots[f] then L.shot(string.format("shot-%d.png", f)) end
  if f == maxf - 1 then L.write("scene.txt", table.concat(out, "\n") .. "\n") end
end, emu.eventType.endFrame)
L.drive()
