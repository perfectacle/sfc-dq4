-- 소리 드라이버를 실측한다. FROM 프레임부터 APU($4000~$4017) 쓰기마다 "W 프레임 주소 값",
-- NMI 의 소리 틱 1F:$E685 진입마다 "N 프레임", 소리 입구 1F:$C01F 진입마다 "S 프레임 A(원래) A(바꾼 뒤)",
-- $C022·$C025·$C028·$C02B 진입마다 "C 프레임 주소 A", 메시지 출력 16:$8656 진입마다 "M 프레임 번호" 를
-- sound.txt 에 쓴다(MAXF-1 프레임). 효과음이 어느 대사와 함께 나는지 보는 데 쓴다.
-- SONG=n(16진)을 주면 FROM 뒤 첫 $C01F 진입의 A 를 n 으로 바꾼다. MUTE=1 이면 그 뒤의 $C01F 진입은
-- A 를 지금 곡($BF >> 1)으로 바꿔 아무것도 새로 울리지 않게 한다(대사 글자 소리 등이 끼어들지 않게).
-- 끝에서 입력 드라이버(DRIVER, 예: seq.lua)를 돌린다.
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local L = require("lib")
local from = tonumber(os.getenv("FROM") or "0")
local maxf = tonumber(os.getenv("MAXF") or "1500")
local song = os.getenv("SONG") and tonumber(os.getenv("SONG"), 16)
local mute = os.getenv("MUTE") == "1"
local f, out, started = 0, {}, false
local base = 0x1F * 0x4000

emu.addMemoryCallback(function(addr)
  if f < from or L.prgOffset(addr) ~= base + 0x001F then return end
  local a = emu.getState()["cpu.a"]
  local new = a
  if not started then
    if song then new = song end
    started = true
  elseif mute then
    new = emu.read(0xBF, L.mem) >> 1
  end
  if new ~= a then emu.setState({["cpu.a"] = new}) end
  out[#out + 1] = string.format("S %d %02X %02X", f, a, new)
end, emu.callbackType.exec, 0xC01F, 0xC01F)

for _, e in ipairs({0xC022, 0xC025, 0xC028, 0xC02B}) do
  emu.addMemoryCallback(function(addr)
    if f < from or L.prgOffset(addr) ~= base + (e - 0xC000) then return end
    out[#out + 1] = string.format("C %d %04X %02X", f, e, emu.getState()["cpu.a"])
  end, emu.callbackType.exec, e, e)
end

emu.addMemoryCallback(function(addr)
  if f < from or L.prgOffset(addr) ~= 0x16 * 0x4000 + 0x0656 then return end
  local st = emu.getState()
  out[#out + 1] = string.format("M %d %02X%02X", f, st["cpu.x"], st["cpu.a"])
end, emu.callbackType.exec, 0x8656, 0x8656)

emu.addMemoryCallback(function(addr)
  if f < from or L.prgOffset(addr) ~= base + 0x2685 then return end
  out[#out + 1] = string.format("N %d", f)
end, emu.callbackType.exec, 0xE685, 0xE685)

emu.addMemoryCallback(function(addr, value)
  if f < from then return end
  out[#out + 1] = string.format("W %d %04X %02X", f, addr, value)
end, emu.callbackType.write, 0x4000, 0x4017)

emu.addEventCallback(function()
  f = f + 1
  if f == maxf - 1 then L.write("sound.txt", table.concat(out, "\n") .. "\n") end
end, emu.eventType.endFrame)
L.drive()
