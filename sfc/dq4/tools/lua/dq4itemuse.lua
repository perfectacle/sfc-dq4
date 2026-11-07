-- STATE 에서 SET 으로 WRAM 을 고치고 INPUT 열("a:6,wait:60,..." 꼴)을 누른 뒤, WATCH(16진 주소 쉼표 목록)의 코드가
-- 몇 번 돌았는지와 끝 화면을 남긴다. 결과: SHOT_DIR/use.txt("addr 횟수" 줄), 창이 바뀔 때마다 shot-NNNN.png.
-- "open:N" 은 창 번호(7E:0A00)가 바뀔 때까지 A 를 8프레임 누르고 8프레임 떼기를 되풀이한다(N 프레임까지). 필드는 8프레임에
-- 한 번 패드를 읽고 그 사이의 누름·뗌을 보지 못해, 정해진 길이로 한 번 누르면 맵에 들어온 프레임 위상에 따라 창이 열리지 않는다.
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local L = require("lib")
L.loadState(os.getenv("STATE"))
local m = emu.memType.snesMemory
local seq = {}
for tok in string.gmatch(os.getenv("INPUT") or "", "[^,]+") do
  local btn, f = tok:match("([%w+]+):(%d+)")
  seq[#seq + 1] = {btn, tonumber(f)}
end
local total = 0
for _, s in ipairs(seq) do total = total + s[2] end
local endf = total + 60
local hits, order = {}, {}
for a in string.gmatch(os.getenv("WATCH") or "", "%x+") do
  local addr = tonumber(a, 16)
  order[#order + 1] = addr
  hits[addr] = 0
  emu.addMemoryCallback(function() hits[addr] = hits[addr] + 1 end, emu.callbackType.exec, addr, addr)
end
local n, si, left, window = 0, 1, nil, -1
local opened, held = nil, 0
emu.addEventCallback(function()
  n = n + 1
  if n == 2 then
    for a, op, v in string.gmatch(os.getenv("SET") or "", "(%x+)([=|&])(%x+)") do
      local addr, val = 0x7E0000 + tonumber(a, 16), tonumber(v, 16)
      local cur = emu.read(addr, m)
      if op == "=" then cur = val elseif op == "|" then cur = cur | val else cur = cur & val end
      emu.write(addr, cur, m)
    end
  end
  if n >= 3 and si <= #seq then
    if left == nil then left = seq[si][2] end
    local btn = seq[si][1]
    if btn == "open" then
      if opened == nil then opened, held = window, 0 end
      if (held % 16) < 8 then L.press({a = true}) else L.release() end
      held = held + 1
      if emu.read(0x7E0A00, m) ~= opened then left = 1 end
    elseif btn == "wait" then L.release() else
      local t = {}
      for x in string.gmatch(btn, "[^+]+") do t[x] = true end
      L.press(t)
    end
    left = left - 1
    if left <= 0 then si = si + 1; left = nil; opened = nil; L.release() end
  end
  local w = emu.read(0x7E0A00, m)
  if n >= 3 and w ~= window then
    window = w
    L.shot(string.format("shot-%04d.png", n))
  end
  if n == endf then
    local out = {}
    for _, a in ipairs(order) do out[#out + 1] = string.format("%06X %d", a, hits[a]) end
    L.shot("end.png")
    L.write("use.txt", table.concat(out, "\n") .. "\n")
    emu.stop(0)
  end
end, emu.eventType.endFrame)
