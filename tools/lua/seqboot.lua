-- boot.lua 대신 쓰는 드라이버: STATE 세이브스테이트에서 시작해 SEQ 입력을 재생하고 MAXF 프레임에 멈춘다.
-- SEQ 형식은 툴킷 seq.lua 와 같다("b:4,wait:40,down:120"). 프레임 번호는 스테이트를 불러온 뒤부터 센다.
-- 다른 프로브(rprof.lua 등)는 끝에서 $LIBDIR/boot.lua 를 부르므로, LIBDIR 에 이 파일을 boot.lua 로 둔 폴더를 준다
-- (tools/lua/seqlib.sh 가 만든다).
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local L = require("lib")
L.loadState(os.getenv("STATE"))
local steps = {}
for tok in string.gmatch(os.getenv("SEQ") or "", "[^,]+") do
  local b, f = tok:match("([%w+]+):(%d+)")
  steps[#steps + 1] = {b, tonumber(f)}
end
local maxf = tonumber(os.getenv("MAXF") or "600")
local every = tonumber(os.getenv("EVERY") or "0")
local i, left, n = 1, nil, 0
emu.addEventCallback(function()
  n = n + 1
  L.release()
  if i <= #steps then
    local s = steps[i]
    if left == nil then left = s[2] end
    if s[1] ~= "wait" then
      local t = {}
      for b in s[1]:gmatch("[^+]+") do t[b] = true end
      L.press(t)
    end
    left = left - 1
    if left <= 0 then i = i + 1; left = nil end
  end
  if every > 0 and n % every == 0 then L.shot(string.format("f%05d.png", n)) end
  if n >= maxf then emu.stop(0) end
end, emu.eventType.endFrame)
