-- STATE 세이브스테이트에서 INPUT("up:100" 또는 "a:8,wait:60,..." 꼴)을 차례로 누르고, 문 열림 flag(7E:21C2~21C5)와
-- 주인공 셀($C1,$C2)을 처음과 끝에 적는다. SET="2199|02" 는 시작할 때 WRAM(7E 뱅크 하위 16비트 주소)을 고친다.
-- 결과: SHOT_DIR/door.txt("start x,y flags", "end x,y flags", "seen flags": 걷는 동안 한 번이라도 켜진 비트), end.png.
-- 열린 문을 지나 다른 그룹(필드 등)으로 나가면 flag 가 지워지므로 seen 으로 본다.
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local L = require("lib")
L.loadState(os.getenv("STATE"))
local m = emu.memType.snesMemory
local function b(a) return emu.read(a, m) end
local seq = {}
for tok in string.gmatch(os.getenv("INPUT") or "", "[^,]+") do
  local btn, f = tok:match("([%w+]+):(%d+)")
  seq[#seq + 1] = {btn, tonumber(f)}
end
local total = 0
for _, s in ipairs(seq) do total = total + s[2] end
local endf = total + 40
local n, si, left, log, seen = 0, 1, nil, {}, 0
local function line(tag)
  log[#log + 1] = string.format("%s %d,%d %02X%02X%02X%02X", tag, b(0x7E00C1), b(0x7E00C2),
    b(0x7E21C2), b(0x7E21C3), b(0x7E21C4), b(0x7E21C5))
end
emu.addEventCallback(function()
  n = n + 1
  if n == 2 then
    for a, op, v in string.gmatch(os.getenv("SET") or "", "(%x+)([=|&])(%x+)") do
      local addr, val = 0x7E0000 + tonumber(a, 16), tonumber(v, 16)
      local cur = b(addr)
      if op == "=" then cur = val elseif op == "|" then cur = cur | val else cur = cur & val end
      emu.write(addr, cur, m)
    end
    line("start")
  end
  if n >= 3 then seen = seen | (b(0x7E21C2) << 24 | b(0x7E21C3) << 16 | b(0x7E21C4) << 8 | b(0x7E21C5)) end
  if n >= 3 and si <= #seq then
    if left == nil then left = seq[si][2] end
    local btn = seq[si][1]
    if btn == "wait" then L.release() else
      local t = {}
      for x in string.gmatch(btn, "[^+]+") do t[x] = true end
      L.press(t)
    end
    left = left - 1
    if left <= 0 then si = si + 1; left = nil; L.release() end
  end
  if n == endf then
    line("end")
    log[#log + 1] = string.format("seen %08X", seen)
    L.shot("end.png")
    L.write("door.txt", table.concat(log, "\n") .. "\n")
    emu.stop(0)
  end
end, emu.eventType.endFrame)
