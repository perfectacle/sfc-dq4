-- BRK 뱅크 호출(처리기 $C408)을 모두 잡아, 호출 위치마다 b1 b2 셋째 바이트와 실제로 돌아온 자리를 센다.
-- 돌아온 자리는 BRK 직전과 같은 스택 높이에서 BRK+1~+6 이 처음 실행될 때로 잡는다(같은 뱅크일 때만).
-- 한 호출 위치에 돌아오기를 기다리는 중이면 그 사이의 같은 위치 호출은 횟수만 센다.
-- brk.txt: "prg=호출 위치 PRG 오프셋 cpu=주소 b1 b2 b3 n=횟수 ret=+k first=프레임", 횟수 많은 순.
-- events.txt: 메시지(b2 아래 4비트 B, 0B~BB)·플래그(CB·DB·EB) 형식마다 프레임과 값을 차례로.
--   플래그는 $627B+b1 의 호출 전 값과 셋째 바이트, 메시지는 번호 (b2>>4):b1.
-- 끝에서 입력 드라이버(DRIVER, 예: seq.lua)를 돌리고, MAXF-1 프레임에 쓴다.
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local L = require("lib")
local f, sites, events = 0, {}, {}
local KIND = {[0xC] = "flag-set", [0xD] = "flag-clear", [0xE] = "flag-test", [0xF] = "sound"}
emu.addMemoryCallback(function()
  local st = emu.getState()
  local sp = st["cpu.sp"]
  local ret = emu.read(0x0100 + ((sp + 2) & 0xFF), L.mem) | emu.read(0x0100 + ((sp + 3) & 0xFF), L.mem) << 8
  local site = (ret - 2) & 0xFFFF
  local off = L.prgOffset(site)
  if not off then return end
  local b1, b2, b3 = emu.read(site + 1, L.mem), emu.read(site + 2, L.mem), emu.read(site + 3, L.mem)
  local s = sites[off]
  if not s then
    s = {cpu = site, b1 = b1, b2 = b2, b3 = b3, n = 0, ret = {}, first = f}
    sites[off] = s
  end
  s.n = s.n + 1
  if b2 & 0x0F == 0x0B then
    local hi = b2 >> 4
    if hi <= 0x0B then
      events[#events + 1] = string.format("%d prg=%05X message %X%02X", f, off, hi, b1)
    elseif hi ~= 0x0F then
      local v = emu.read(0x627B + b1, L.mem)
      events[#events + 1] = string.format("%d prg=%05X %s %04X was=%02X mask=%02X", f, off, KIND[hi], 0x627B + b1, v, b3)
    end
  end
  if s.pending then return end
  s.pending = true
  local sp0 = (sp + 3) & 0xFF
  local ref
  ref = emu.addMemoryCallback(function(pc)
    if emu.getState()["cpu.sp"] ~= sp0 or L.prgOffset(pc) ~= off + (pc - site) then return end
    s.ret[pc - site] = (s.ret[pc - site] or 0) + 1
    s.pending = false
    emu.removeMemoryCallback(ref, emu.callbackType.exec, site + 1, site + 6)
  end, emu.callbackType.exec, site + 1, site + 6)
end, emu.callbackType.exec, 0xC408, 0xC408)
local maxf = tonumber(os.getenv("MAXF") or "1500")
emu.addEventCallback(function()
  f = f + 1
  if f ~= maxf - 1 then return end
  local list = {}
  for off, s in pairs(sites) do
    local r = {}
    for k, n in pairs(s.ret) do r[#r + 1] = string.format("+%d:%d", k, n) end
    table.sort(r)
    list[#list + 1] = {s.n, string.format("prg=%05X cpu=%04X %02X %02X %02X n=%d ret=%s first=%d",
      off, s.cpu, s.b1, s.b2, s.b3, s.n, #r > 0 and table.concat(r, ",") or "-", s.first)}
  end
  table.sort(list, function(a, b) return a[1] > b[1] end)
  local out = {}
  for _, x in ipairs(list) do out[#out + 1] = x[2] end
  L.write("brk.txt", table.concat(out, "\n") .. "\n")
  L.write("events.txt", table.concat(events, "\n") .. "\n")
end, emu.eventType.endFrame)
L.drive()
