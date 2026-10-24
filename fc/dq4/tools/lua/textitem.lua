-- 창 본문을 그리는 동안 갈래마다 무엇이 불리고 무엇을 찍는지 적는다(뱅크 16).
-- item.txt 한 줄에 프레임과 아래 중 하나를 쓴다.
--   open W=창 F7 F8                16:$94D9(레코드를 찾은 뒤, W = $03C7)
--   top g n F7 F3 DB DC DD          16:$9783 창 문자열 항목 하나(그룹 $03D6, 항목 A)
--   sub g n                         16:$97D5 문자열 안의 80 이상 바이트가 루틴 항목으로 감
--   cond b T F5 → A 3D2 7B0..7B7 DB DC DD   16:$96E4 항목 루틴(80~9F, 표 $03D7)과 돌아온 뒤(16:$96DD)
--   flag b F5                      16:$96DA 머리 뒤 A0~BF 를 다시 읽을 때
--   list n                          16:$98EE 목록 시작 Dn
--   place n / init n / c1 n         16:$A467·$A472·$A47D(표 16:$A72C·$A734)
--   mode n                          16:$9321 E0~FF($03C6)
--   put 열:바이트 …                 직전 줄 뒤에 16:$981C(글자)·$983F(탁점)로 줄 버퍼에 넣은 바이트(m 은 탁점)
-- F7=hex, F3=hex 를 주면 WIN 과 함께 첫 열기 때 그 값으로 바꾼다. WIN 은 textlayout.lua 와 같다.
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local L = require("lib")
local win = os.getenv("WIN") and tonumber(os.getenv("WIN"), 16)
local f7 = os.getenv("F7") and tonumber(os.getenv("F7"), 16)
local f, log, puts, forced = 0, {}, {}, false
local function r(a) return emu.read(a, L.mem) end
local function flush()
  if #puts > 0 then log[#log + 1] = "  put " .. table.concat(puts, " "); puts = {} end
end
local function add(s) flush(); log[#log + 1] = f .. " " .. s end
local function at(addr, fn)
  local off = 0x16 * 0x4000 + (addr & 0x3FFF)
  emu.addMemoryCallback(function(a)
    if L.prgOffset(a) == off then fn(emu.getState()) end
  end, emu.callbackType.exec, addr, addr)
end
local function regs()
  return string.format("F7=%02X F3=%02X DB=%02X DC=%02X DD=%02X", r(0xF7), r(0xF3), r(0x3DB), r(0x3DC), r(0x3DD))
end
at(0x8A03, function()
  if win and not forced then
    emu.write(0xF6, win, L.mem)
    if f7 then emu.write(0xF7, f7, L.mem) end
    forced = true
  end
end)
at(0x94D9, function() add(string.format("open W=%02X F7=%02X F8=%02X", r(0x3C7), r(0xF7), r(0xF8))) end)
at(0x9783, function(st) add(string.format("top g=%d n=%02X %s", r(0x3D6), st["cpu.a"], regs())) end)
local pend
at(0x97B0, function(st) pend = st["cpu.a"] end)
at(0x97D5, function() add(string.format("sub g=%d n=%02X %s", r(0x3D6), (pend or 0) & 0x7F, regs())) end)
at(0x96E4, function(st)
  add(string.format("cond b=%02X T=%d F5=%02X %s", st["cpu.a"], r(0x3D7), r(0xF5), regs()))
end)
at(0x96DA, function(st) add(string.format("flag b=%02X F5=%02X", (st["cpu.a"] - 0x60) & 0xFF, r(0xF5))) end)
at(0x96DD, function(st)
  local t = {}
  for i = 0, 7 do t[#t + 1] = string.format("%02X", r(0x7B0 + i)) end
  add(string.format("  => A=%02X 3D2=%02X 7B0=%s %s F5=%02X", st["cpu.a"], r(0x3D2), table.concat(t, " "), regs(), r(0xF5)))
end)
at(0x98EE, function(st) add(string.format("list n=%X %s", st["cpu.a"], regs())) end)
at(0xA467, function(st) add(string.format("place n=%02X", st["cpu.a"])) end)
at(0xA472, function(st) add(string.format("init n=%02X", st["cpu.a"])) end)
at(0xA47D, function(st) add(string.format("c1 n=%02X %s", st["cpu.a"], regs())) end)
at(0x9321, function(st) add(string.format("mode n=%02X", st["cpu.a"])) end)
at(0x981C, function(st) puts[#puts + 1] = string.format("%d:%02X", st["cpu.x"], st["cpu.a"]) end)
at(0x983F, function(st) puts[#puts + 1] = string.format("%dm%02X", st["cpu.x"], st["cpu.a"]) end)
local maxf = tonumber(os.getenv("MAXF") or "1500")
emu.addEventCallback(function()
  f = f + 1
  if f == maxf - 1 then flush(); L.write("item.txt", table.concat(log, "\n") .. "\n") end
end, emu.eventType.endFrame)
L.drive()
