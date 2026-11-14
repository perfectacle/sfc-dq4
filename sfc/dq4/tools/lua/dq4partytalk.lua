-- 2장 동료 대화 검사(dq4ch2partytalkcheck.py). STATE 세이브스테이트(말 상대가 없는 쪽을 보고 선 맵)에서 PRE 입력을
-- 재생한 뒤, STEPS 의 단계마다 flag·시각·마지막 줄 값을 WRAM 에 쓰고 명령 창 「はなす」를 고른다. 메시지 루틴 24:8BAF 가
-- 받은 번호(A)를 단계마다 talk.txt 에 「단계 이름 번호,번호」 로 적고 끝에 end.png 를 남긴다.
-- STEPS="이름|2190+i=값/마스크,...|075E=값,075F=값;..."(주소는 7E 뱅크 하위 16비트, 16진). 마스크 밖 비트는 그대로 둔다.
-- SHOTS=1 이면 단계마다 대사 첫 쪽 화면을 <단계>.png 로 남긴다.
-- TALK 는 한 단계의 입력(seq 꼴 "a:8,wait:60,..."), PRE 는 첫 단계 앞 입력, ROMPATCH·POKE(매 프레임 씀)는 walk.lua 와 같다.
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local L = require("lib")
L.loadState(os.getenv("STATE"))
local m = emu.memType.snesMemory

local function seq(text)
  local out = {}
  for tok in string.gmatch(text or "", "[^,]+") do
    local b, f = tok:match("([%w+]+):(%d+)")
    out[#out + 1] = {b, tonumber(f)}
  end
  return out
end

local steps = {}
for tok in string.gmatch(os.getenv("STEPS") or "", "[^;]+") do
  local name, rest = tok:match("^([^|]+)|(.*)$")
  local writes = {}
  for a, v, k in string.gmatch(rest, "(%x+)=(%x+)/?(%x*)") do
    writes[#writes + 1] = {tonumber(a, 16), tonumber(v, 16), k ~= "" and tonumber(k, 16) or 0xFF}
  end
  steps[#steps + 1] = {name = name, writes = writes, got = {}}
end
local pre, talk = seq(os.getenv("PRE")), seq(os.getenv("TALK"))
local patches = {}
for off, hex in string.gmatch(os.getenv("ROMPATCH") or "", "(%x+)=(%x+)") do patches[#patches + 1] = {tonumber(off, 16), hex} end
local pokes = {}
for a, v in string.gmatch(os.getenv("POKE") or "", "(%x+)=(%x+)") do pokes[#pokes + 1] = {tonumber(a, 16), tonumber(v, 16)} end
local maxf = tonumber(os.getenv("MAXF") or "60000")

local current
emu.addMemoryCallback(function()
  if current then current.got[#current.got + 1] = string.format("%03X", emu.getState()["cpu.a"] & 0xFFFF) end
end, emu.callbackType.exec, 0x248BAF, 0x248BAF)

local n, si, pi, left, queue = 0, 0, 1, nil, pre
local function finish()
  local out = {}
  for _, s in ipairs(steps) do out[#out + 1] = s.name .. " " .. table.concat(s.got, ",") end
  out[#out + 1] = string.format("frames %d steps %d/%d", n, math.max(si, 0), #steps)
  L.write("talk.txt", table.concat(out, "\n") .. "\n")
  L.shot("end.png")
  emu.stop(0)
end

emu.addEventCallback(function()
  n = n + 1
  if n == 1 then
    for _, p in ipairs(patches) do
      for i = 0, #p[2] / 2 - 1 do
        emu.write(p[1] + i, tonumber(p[2]:sub(i * 2 + 1, i * 2 + 2), 16), emu.memType.snesPrgRom)
      end
    end
  end
  for _, p in ipairs(pokes) do emu.write(p[1], p[2], m) end
  L.release()
  if n >= maxf then finish() return end
  if pi > #queue then
    si = si + 1
    if si > #steps then finish() return end
    current = steps[si]
    for _, w in ipairs(current.writes) do
      local a = 0x7E0000 + w[1]
      emu.write(a, (emu.read(a, m) & ~w[3] & 0xFF) | (w[2] & w[3]), m)
    end
    queue, pi, left = talk, 1, nil
  end
  local s = queue[pi]
  -- SHOTS 가 있으면 단계마다 첫 B 직전(대사 첫 쪽이 찍힌 화면)을 남긴다
  if left == nil and queue == talk and current and os.getenv("SHOTS") and s[1] == "b" and not current.shot then
    current.shot = true
    L.shot(current.name .. ".png")
  end
  if left == nil then left = s[2] end
  if s[1] ~= "wait" then local t = {}; for b in s[1]:gmatch("[^+]+") do t[b] = true end; L.press(t) end
  left = left - 1
  if left <= 0 then pi = pi + 1; left = nil end
end, emu.eventType.endFrame)
