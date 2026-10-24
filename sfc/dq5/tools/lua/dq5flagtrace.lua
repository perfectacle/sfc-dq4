-- DQ5: 같은 폴더의 dq5warp.lua 로 장면 이동과 TEST 입력을 돌리면서 이야기 플래그를 다루는 곳을 기록한다.
--   BRK 0B·0C·0D(플래그 시험·켜기·끄기)를 부른 자리: BRK 벡터 처리기 00:8F80 에 들어올 때 스택의 돌아갈 주소로 찾는다
--   7E:2190~220F 쓰기: 쓴 PC 와 값
-- TO 나 FIELD 가 있으면 dq5warp.lua 로 돌고 끝날 때, 없으면 LIBDIR 의 boot.lua(seqlib.sh 로 고른 드라이버)로 돌고 MAXF 프레임에
-- SHOT_DIR/flagtrace.txt 를 쓴다(sfc/dq5/tools/dq5flags.py --check 가 읽음). 같은 주소·값·PC 의 쓰기는 처음 한 번만 적는다.
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local L = require("lib")
local m = emu.memType.snesMemory
local f = 0
local log, seen = {}, {}

emu.addMemoryCallback(function()
  local st = emu.getState()
  local sp = st["cpu.sp"]
  -- 네이티브 BRK 는 PBR, PCH, PCL, P 를 쌓는다. 돌아갈 주소는 서명 바이트 다음
  local ret = emu.read(sp + 2, m) | emu.read(sp + 3, m) << 8 | emu.read(sp + 4, m) << 16
  local sig = emu.read(ret - 1, m)
  if sig < 0x0B or sig > 0x0D then return end
  local brk = ret - 2
  local key = string.format("%06X", brk)
  if seen[key] then seen[key][2] = seen[key][2] + 1; return end
  seen[key] = {f, 1}
  log[#log + 1] = string.format("%d brk %02X:%04X %02X %02X %02X", f, brk >> 16, brk & 0xFFFF, sig,
    emu.read(ret, m), emu.read(ret + 1, m))
end, emu.callbackType.exec, 0x008F80, 0x008F80)

emu.addMemoryCallback(function(addr, value)
  local st = emu.getState()
  local key = string.format("%04X=%02X pc=%02X:%04X", addr & 0xFFFF, value, st["cpu.k"], st["cpu.pc"])
  if seen[key] or #log > 3000 then return end
  seen[key] = true
  log[#log + 1] = string.format("%d write %s", f, key)
end, emu.callbackType.write, 0x2190, 0x220F, emu.cpuType.snes, emu.memType.snesWorkRam)

local function dump() L.write("flagtrace.txt", table.concat(log, "\n") .. "\n") end
local warp = os.getenv("TO") or os.getenv("FIELD")
local maxf = tonumber(os.getenv("MAXF") or "3000")
emu.addEventCallback(function()
  f = f + 1
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
