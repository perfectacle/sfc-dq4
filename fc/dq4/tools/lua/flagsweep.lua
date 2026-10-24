-- DQ4: 이벤트 플래그를 쓰는 장면을 모으는 프로브. 입력 드라이버(DRIVER, 기본 warp.lua)를 끝에서 돌린다.
-- sweep.txt 에 프레임마다 일어난 일을 한 줄씩 남긴다:
--   "f w ADDR old>new pc=PC bank=BB brk=BRK slot=SS"  플래그 영역 $627B-$62EE·일행 $616A-$6177·$618E 쓰기.
--        brk 는 고정 뱅크 BRK 플래그 처리기($C4BC-$C4EF)에서 쓸 때 BRK 명령 자리(뱅크:주소), 아니면 "-".
--        slot 은 인물 블록 명령 27/28/29 처리기(1F:$DC09-$DC2F)에서 쓸 때 $51(인물 슬롯), 아니면 "-".
--   "f msg XXXX"       메시지 출력 16:$8656(X:A)
--   "f talk SS"        대화 진입 15:$98F8(A = 슬롯), "f tid NNN" 대화 번호(15:$9942)
--   "f ev NN SS"       인물 블록 이벤트 명령 1F:$DEDD(A = 이벤트 번호, $51 = 슬롯). 슬롯마다 번호가 바뀔 때만
--   "f ev1C NN"        대화가 부르는 이벤트 1C:$AD5F, "f ev1D" 맵 이벤트 1D:$B74D, "f battle NN" 특수 전투 18:$A1AD
--   "f map GG/KK X,Y"  맵이 바뀜
-- 환경 변수(16진):
--   SLOT=SS       대화 진입 때 A 를 이 슬롯으로 바꿈(talk.lua 와 같음)
--   PIN=SS        매 프레임 그 슬롯 인물을 주인공이 보는 쪽($3D) 한 칸에 둔다. SLOT 과 같이 써서 아무 인물에게 말 건다.
--                 PIN=auto 면 비어 있지 않은 첫 슬롯을 골라 SLOT 도 그 슬롯으로
--   TID=NNN       대화 번호를 바꿈. EV=NN 이벤트 1C:$AD5F 의 A 를 바꿈
--   PRGPOKE="71A2D=EAEAEA"  3번째 프레임에 PRG ROM(iNES 머리 뺀 오프셋)에 쓸 바이트들. 롬 파일은 그대로.
--                 이벤트 안의 특수 전투 BRK 01 8F 를 EA 로 바꿔 전투를 건너뛸 때 쓴다
--   MAXF=1500     이 프레임에 sweep.txt 를 쓴다(120프레임마다도 씀)
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local L = require("lib")
local mem = L.mem
local function rd(a) return emu.read(a, mem) end
local function hex(s) return s and tonumber(s, 16) end
local slot, pin, tid, ev = hex(os.getenv("SLOT")), hex(os.getenv("PIN")), hex(os.getenv("TID")), hex(os.getenv("EV"))
-- PIN=auto: 그 프레임에 비어 있지 않은 첫 슬롯(6~1D)을 쓰고, 대화 진입도 그 슬롯으로 바꾼다
local auto = os.getenv("PIN") == "auto"
local maxf = tonumber(os.getenv("MAXF") or "1500")
local f, log, cur, lastMap = 0, {}, 0, nil
local function add(s) log[#log + 1] = string.format("%d %s", f, s) end

emu.addMemoryCallback(function(a) cur = a end, emu.callbackType.exec, 0x8000, 0xFFFF)

local function bankOf(a)
  local c = emu.convertAddress(a, mem)
  return (c and c.address >= 0) and math.floor(c.address / 0x4000) or -1
end

local function onWrite(addr, value)
  local brk, s = "-", "-"
  if cur >= 0xC4BC and cur <= 0xC4EF then
    local p = rd(0x26) + 256 * rd(0x27) - 1
    brk = string.format("%02X:%04X", bankOf(p), p)
  elseif cur >= 0xDC09 and cur <= 0xDC2F then
    s = string.format("%02X", rd(0x51))
  end
  add(string.format("w %04X %02X>%02X pc=%04X bank=%02X brk=%s slot=%s", addr, rd(addr), value, cur,
    bankOf(cur), brk, s))
end
-- write 콜백은 쓰기 직전에 불려 rd(addr) 가 옛 값이다
emu.addMemoryCallback(onWrite, emu.callbackType.write, 0x627B, 0x62EE)
emu.addMemoryCallback(onWrite, emu.callbackType.write, 0x616A, 0x6177)
emu.addMemoryCallback(onWrite, emu.callbackType.write, 0x618E, 0x618E)

local function hook(addr, prg, fn)
  emu.addMemoryCallback(function()
    if L.prgOffset(addr) == prg then fn() end
  end, emu.callbackType.exec, addr, addr)
end
hook(0x8656, 0x58656, function()
  local st = emu.getState()
  add(string.format("msg %02X%02X", st["cpu.x"], st["cpu.a"]))
end)
hook(0x98F8, 0x558F8, function()
  if slot then emu.setState({["cpu.a"] = slot}) end
  add(string.format("talk %02X", emu.getState()["cpu.a"]))
end)
hook(0x9942, 0x55942, function()
  if tid then emu.write(0x00, tid & 0xFF, mem); emu.write(0x01, tid >> 8, mem) end
  add(string.format("tid %X%02X", rd(0x01), rd(0x00)))
end)
hook(0xAD5F, 0x72D5F, function()
  if ev then emu.setState({["cpu.a"] = ev}) end
  add(string.format("ev1C %02X", emu.getState()["cpu.a"]))
end)
hook(0xB74D, 0x7774D, function() add("ev1D") end)
hook(0xA1AD, 0x621AD, function() add(string.format("battle %02X", emu.getState()["cpu.a"])) end)
-- 이벤트 명령은 조건이 맞을 때까지 차례마다 다시 불리므로 슬롯마다 번호가 바뀔 때만 남긴다
local lastEv = {}
emu.addMemoryCallback(function()
  local n, s = emu.getState()["cpu.a"], rd(0x51)
  if lastEv[s] ~= n then lastEv[s] = n; add(string.format("ev %02X %02X", n, s)) end
end, emu.callbackType.exec, 0xDEDD, 0xDEDD)

local DX, DY = {[0] = 0, 1, 0, -1}, {[0] = -1, 0, 1, 0}
emu.addEventCallback(function()
  f = f + 1
  if f == 3 then
    for a, bytes in string.gmatch(os.getenv("PRGPOKE") or "", "(%x+)=(%x+)") do
      for i = 1, #bytes - 1, 2 do
        emu.write(tonumber(a, 16) + (i - 1) // 2, tonumber(bytes:sub(i, i + 1), 16), emu.memType.nesPrgRom)
      end
    end
  end
  local m = rd(0x63) * 256 + rd(0x64)
  if m ~= lastMap then
    lastMap, lastEv = m, {}
    add(string.format("map %02X/%02X %02X,%02X", m // 256, m % 256, rd(0x44), rd(0x45)))
  end
  if auto and (not pin or rd(0x7020 + pin) == 0xFF) then
    pin = nil
    for i = 6, 0x1D do if rd(0x7020 + i) ~= 0xFF then pin = i; break end end
    slot = pin
  end
  if pin and rd(0x7020 + pin) ~= 0xFF then
    local d = rd(0x3D) & 3
    emu.write(0x6F60 + pin, (rd(0x6F60) + DX[d]) & 0xFF, mem)
    emu.write(0x6F80 + pin, (rd(0x6F80) + DY[d]) & 0xFF, mem)
  end
  -- 드라이버가 MAXF 전에 멈출 수도 있어(eventwalk.lua 등) 120프레임마다도 쓴다
  if f == maxf - 1 or f % 120 == 0 then L.write("sweep.txt", table.concat(log, "\n") .. "\n") end
end, emu.eventType.endFrame)

L.drive()
