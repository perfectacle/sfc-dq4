-- DQ5: 같은 폴더의 dq5warp.lua 로 장면 이동과 TEST 입력을 돌리면서 곡 틀기를 기록한다.
--   24:FE9A(소리 명령 01, 곡 틀기) 실행: 프레임·곡 번호(A)·돌아갈 주소(JSL 이면 부른 곳, BRK 0F·11 이면 00:92A2·92AB)
--   BRK 0F·11(곡 틀기 BRK)을 부른 자리: BRK 벡터 처리기 00:8F80 에 들어올 때 스택의 돌아갈 주소로 찾는다
--   7E:21DF(맵을 옮겨도 남는 곡) 쓰기, 맵 번호($BC·$BD)가 바뀐 프레임
--   25:FD00(짧게 트는 곡, 끝나면 맵 곡으로) 에 들어올 때의 곡 번호와 JSL 한 곳(short), 보행 메시지 24:8157 의 번호(msg)
-- TO 나 FIELD 가 있으면 dq5warp.lua 로, 없으면 LIBDIR 의 boot.lua 로 돌고 끝날 때(없으면 MAXF 프레임) SHOT_DIR/songtrace.txt 를 쓴다.
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local L = require("lib")
local m = emu.memType.snesMemory
local f = 0
local log = {}

emu.addMemoryCallback(function()
  local st = emu.getState()
  local sp = st["cpu.sp"]
  local ret = emu.read(sp + 1, m) | emu.read(sp + 2, m) << 8 | emu.read(sp + 3, m) << 16
  log[#log + 1] = string.format("%d play %02X from %02X:%04X", f, st["cpu.a"] & 0xFF, ret >> 16, (ret & 0xFFFF) - 3)
end, emu.callbackType.exec, 0x24FE9A, 0x24FE9A)

emu.addMemoryCallback(function()
  local st = emu.getState()
  local sp = st["cpu.sp"]
  local ret = emu.read(sp + 1, m) | emu.read(sp + 2, m) << 8 | emu.read(sp + 3, m) << 16
  log[#log + 1] = string.format("%d short %02X from %02X:%04X", f, st["cpu.a"] & 0xFF, ret >> 16, (ret & 0xFFFF) - 3)
end, emu.callbackType.exec, 0x25FD00, 0x25FD00)

emu.addMemoryCallback(function()
  log[#log + 1] = string.format("%d msg %04X", f, emu.getState()["cpu.a"] & 0xFFFF)
end, emu.callbackType.exec, 0x248157, 0x248157)

emu.addMemoryCallback(function()
  local st = emu.getState()
  local sp = st["cpu.sp"]
  -- 네이티브 BRK 는 PBR, PCH, PCL, P 를 쌓는다. 돌아갈 주소는 서명 바이트 다음
  local ret = emu.read(sp + 2, m) | emu.read(sp + 3, m) << 8 | emu.read(sp + 4, m) << 16
  local sig = emu.read(ret - 1, m)
  if sig ~= 0x0F and sig ~= 0x11 then return end
  local brk = ret - 2
  log[#log + 1] = string.format("%d brk %02X:%04X %02X %02X", f, brk >> 16, brk & 0xFFFF, sig, emu.read(ret, m))
end, emu.callbackType.exec, 0x008F80, 0x008F80)

emu.addMemoryCallback(function(addr, value)
  local st = emu.getState()
  log[#log + 1] = string.format("%d 21DF=%02X pc=%02X:%04X", f, value, st["cpu.k"], st["cpu.pc"])
end, emu.callbackType.write, 0x21DF, 0x21DF, emu.cpuType.snes, emu.memType.snesWorkRam)

local lastmap = -1
local function dump() L.write("songtrace.txt", table.concat(log, "\n") .. "\n") end
local warp = os.getenv("TO") or os.getenv("FIELD")
local maxf = tonumber(os.getenv("MAXF") or "3000")
emu.addEventCallback(function()
  f = f + 1
  local map = emu.read(0x7E00BC, m) << 8 | emu.read(0x7E00BD, m)
  if map ~= lastmap then
    lastmap = map
    log[#log + 1] = string.format("%d map %02X/%02X", f, map >> 8, map & 0xFF)
  end
  if not warp and f == maxf - 1 then dump() end
end, emu.eventType.endFrame)
if not warp then
  dofile(os.getenv("LIBDIR") .. "/boot.lua")
  return
end

local write = L.write
L.write = function(name, s)
  if name == "warp.txt" then dump() end
  return write(name, s)
end
local here = debug.getinfo(1, "S").source:match("^@(.*[/\\])") or "./"
dofile(here .. "dq5warp.lua")
