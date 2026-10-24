-- 대화 진입(뱅크 15 $98F8, A = 인물 슬롯), 메시지 출력(뱅크 16 $8656, X:A = 번호),
-- 서비스 갈래(뱅크 15 $9CBF, A = 종류), 조건 결과(뱅크 15 $9A4C)를 talk.txt 에 기록한다.
-- talk 줄은 (프레임, 슬롯, 순번, 진입 때 Y). Y 는 15:$992F 가 $E9 에 두고 조건 02 가 본다.
-- 진입 때마다 CPU 메모리 0000-7FFF 를 talk_N.bin 으로 저장한다(tools/dq4talk.py compare 가 조건을 풀 때 씀).
-- SLOT(16진)을 주면 진입 때 A 를 그 슬롯으로 바꿔, 서 있는 자리와 상관없이 그 인물의 대화를 돌린다.
-- SLOT="06,07,08" 처럼 여럿을 주면 N번째 말 걸기에 N번째 슬롯(목록이 끝나면 바꾸지 않음).
-- TID="00B,01A"(16진)를 주면 N번째 말 걸기의 대화 번호를 N번째 값으로 바꾼다(15:$9942, 갈래 직전의 $00/$01).
-- 대화 번호는 바꾸든 안 바꾸든 tid 줄로 남긴다.
-- SET="616A=8687;60D3=80"(16진 주소=바이트들)을 주면 첫 말 걸기의 RAM 덤프 전에 한 번 써서 일행·소지품·장 등을 만든다.
-- 툴킷 FC 프로브와 같이 끝에서 입력 드라이버(DRIVER)를 돌리고, MAXF-1 프레임에 talk.txt 를 쓴다.
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local L = require("lib")
local f, n, log = 0, 0, {}
local slots = {}
for t in string.gmatch(os.getenv("SLOT") or "", "%x+") do slots[#slots + 1] = tonumber(t, 16) end
local tids = {}
for t in string.gmatch(os.getenv("TID") or "", "%x+") do tids[#tids + 1] = tonumber(t, 16) end
local function pokes()
  for a, bytes in string.gmatch(os.getenv("SET") or "", "(%x+)=(%x+)") do
    for i = 1, #bytes - 1, 2 do emu.write(tonumber(a, 16) + (i - 1) // 2, tonumber(bytes:sub(i, i + 1), 16), L.mem) end
  end
end

emu.addMemoryCallback(function()
  if L.prgOffset(0x98F8) ~= 0x558F8 then return end
  n = n + 1
  local slot = #slots == 1 and slots[1] or slots[n]
  if slot then emu.setState({["cpu.a"] = slot}) end
  if n == 1 then pokes() end
  local st = emu.getState()
  log[#log + 1] = string.format("%d talk %02X %d %02X", f, st["cpu.a"], n, st["cpu.y"])
  local t = {}
  for i = 0, 0x7FFF do t[#t + 1] = string.char(emu.read(i, L.mem)) end
  L.write(string.format("talk_%d.bin", n), table.concat(t))
end, emu.callbackType.exec, 0x98F8, 0x98F8)

emu.addMemoryCallback(function()
  if L.prgOffset(0x9942) ~= 0x55942 then return end
  local t = tids[n]
  if t then emu.write(0x00, t & 0xFF, L.mem); emu.write(0x01, t >> 8, L.mem) end
  log[#log + 1] = string.format("%d tid %X%02X", f, emu.read(0x01, L.mem), emu.read(0x00, L.mem))
end, emu.callbackType.exec, 0x9942, 0x9942)

emu.addMemoryCallback(function()
  if L.prgOffset(0x8656) ~= 0x58656 then return end
  local st = emu.getState()
  log[#log + 1] = string.format("%d msg %02X%02X", f, st["cpu.x"], st["cpu.a"])
end, emu.callbackType.exec, 0x8656, 0x8656)

emu.addMemoryCallback(function()
  if L.prgOffset(0x9CBF) ~= 0x55CBF then return end
  log[#log + 1] = string.format("%d svc %02X", f, emu.getState()["cpu.a"])
end, emu.callbackType.exec, 0x9CBF, 0x9CBF)

-- 호출 문장이 넘어가는 곳: 이벤트 1C:$AD5F(A = 1C:$BF74 표 번호), 맵별 이벤트 1D:$B74D, 특수 전투 18:$A1AD(A = 번호).
local hooks = {{0xAD5F, 0x72D5F, "ev1C"}, {0xB74D, 0x7774D, "ev1D"}, {0xA1AD, 0x621AD, "battle"}}
for _, h in ipairs(hooks) do
  emu.addMemoryCallback(function()
    if L.prgOffset(h[1]) ~= h[2] then return end
    log[#log + 1] = string.format("%d %s %02X", f, h[3], emu.getState()["cpu.a"])
  end, emu.callbackType.exec, h[1], h[1])
end

-- 조건 결과(15:$9A4C): A=0 이면 then 갈래, $DC=FF(뒤집힌 조건)면 반대. then 갈래를 타면 1.
emu.addMemoryCallback(function()
  if L.prgOffset(0x9A4C) ~= 0x55A4C then return end
  local a, neg = emu.getState()["cpu.a"], emu.read(0xDC, L.mem) ~= 0
  log[#log + 1] = string.format("%d cond %d", f, ((a == 0) ~= neg) and 1 or 0)
end, emu.callbackType.exec, 0x9A4C, 0x9A4C)

local maxf = tonumber(os.getenv("MAXF") or "1500")
emu.addEventCallback(function()
  f = f + 1
  if f == maxf - 1 then L.write("talk.txt", table.concat(log, "\n") .. "\n") end
end, emu.eventType.endFrame)
L.drive()
