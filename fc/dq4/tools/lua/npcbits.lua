-- DQ4: 인물 표 상태 비트 $70E0 를 매 프레임 바꿔 두고 그림·자리가 어떻게 달라지나 본다. 입력 드라이버(DRIVER)를 끝에서 돌린다.
-- 환경 변수(16진): SLOTS="06,07"(기본 6~1D), OR=80 / AND=7F 매 프레임 $70E0+슬롯 에 적용(FROM 프레임부터), FROM=10(10진).
-- SHOTS="300,316" 그 프레임의 화면을 fNNNNN.png 로.
-- npcbits.txt: 프레임마다 OAM 타일 바이트($0201+4i)가 앞 프레임과 다른 스프라이트 수 "f oam N",
--   슬롯 자리가 바뀌면 "f SS pos X,Y", 끝에 슬롯마다 "$70E0 값".
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local L = require("lib")
local mem = L.mem
local function rd(a) return emu.read(a, mem) end
local want = {}
for s in (os.getenv("SLOTS") or ""):gmatch("%x+") do want[#want + 1] = tonumber(s, 16) end
if #want == 0 then for s = 6, 0x1D do want[#want + 1] = s end end
local orv, andv = tonumber(os.getenv("OR") or "0", 16), tonumber(os.getenv("AND") or "FF", 16)
local from = tonumber(os.getenv("FROM") or "10")
local maxf = tonumber(os.getenv("MAXF") or "600")
local f, log, prev, pos = 0, {}, {}, {}
local shots = {}
for v in (os.getenv("SHOTS") or ""):gmatch("%d+") do shots[tonumber(v)] = true end
emu.addEventCallback(function()
  f = f + 1
  if f >= from then
    for _, s in ipairs(want) do
      if rd(0x7020 + s) ~= 0xFF then emu.write(0x70E0 + s, (rd(0x70E0 + s) | orv) & andv, mem) end
    end
  end
  local n = 0
  for i = 0, 63 do
    local t = rd(0x0201 + 4 * i)
    if prev[i] ~= nil and prev[i] ~= t then n = n + 1 end
    prev[i] = t
  end
  log[#log + 1] = string.format("%d oam %d", f, n)
  for _, s in ipairs({0, table.unpack(want)}) do
    local k = rd(0x6F60 + s) * 256 + rd(0x6F80 + s)
    if pos[s] ~= k then pos[s] = k; log[#log + 1] = string.format("%d %02X pos %02X,%02X", f, s, k // 256, k % 256) end
  end
  if shots[f] then
    local o = assert(io.open(string.format("%s/f%05d.png", os.getenv("SHOT_DIR") or ".", f), "wb"))
    o:write(emu.takeScreenshot()); o:close()
  end
  if f == maxf - 1 then
    local t = {}
    for _, s in ipairs(want) do t[#t + 1] = string.format("%02X=%02X", s, rd(0x70E0 + s)) end
    log[#log + 1] = "70E0 " .. table.concat(t, " ")
    L.write("npcbits.txt", table.concat(log, "\n") .. "\n")
  end
end, emu.eventType.endFrame)
L.drive()
