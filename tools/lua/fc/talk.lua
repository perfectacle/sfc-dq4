-- 대화 진입(뱅크 15 $98F8, A = 인물 슬롯), 메시지 출력(뱅크 16 $8656, X:A = 번호),
-- 서비스 갈래(뱅크 15 $9CBF, A = 종류), 조건 결과(뱅크 15 $9A4C)를 talk.txt 에 기록한다.
-- talk 줄은 (프레임, 슬롯, 순번, 진입 때 Y). Y 는 15:$992F 가 $E9 에 두고 조건 02 가 본다.
-- 진입 때마다 CPU 메모리 0000-7FFF 를 talk_N.bin 으로 저장한다(tools/dq4talk.py compare 가 조건을 풀 때 씀).
-- SLOT(16진)을 주면 진입 때 A 를 그 슬롯으로 바꿔, 서 있는 자리와 상관없이 그 인물의 대화를 돌린다.
-- 툴킷 FC 프로브와 같이 끝에서 입력 드라이버(DRIVER)를 돌리고, MAXF-1 프레임에 talk.txt 를 쓴다.
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local L = require("lib")
local f, n, log = 0, 0, {}
local slot = os.getenv("SLOT") and tonumber(os.getenv("SLOT"), 16)

emu.addMemoryCallback(function()
  if L.prgOffset(0x98F8) ~= 0x558F8 then return end
  if slot then emu.setState({["cpu.a"] = slot}) end
  local st = emu.getState()
  n = n + 1
  log[#log + 1] = string.format("%d talk %02X %d %02X", f, st["cpu.a"], n, st["cpu.y"])
  local t = {}
  for i = 0, 0x7FFF do t[#t + 1] = string.char(emu.read(i, L.mem)) end
  L.write(string.format("talk_%d.bin", n), table.concat(t))
end, emu.callbackType.exec, 0x98F8, 0x98F8)

emu.addMemoryCallback(function()
  if L.prgOffset(0x8656) ~= 0x58656 then return end
  local st = emu.getState()
  log[#log + 1] = string.format("%d msg %02X%02X", f, st["cpu.x"], st["cpu.a"])
end, emu.callbackType.exec, 0x8656, 0x8656)

emu.addMemoryCallback(function()
  if L.prgOffset(0x9CBF) ~= 0x55CBF then return end
  log[#log + 1] = string.format("%d svc %02X", f, emu.getState()["cpu.a"])
end, emu.callbackType.exec, 0x9CBF, 0x9CBF)

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
