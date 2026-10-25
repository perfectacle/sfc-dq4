-- DQ5 전투 메시지 바꿔 띄우기. 24:8C39 에 들어올 때 A 가 FROMMSG 이면 TOMSG(쉼표 목록)를 차례로 넣고, SHOTS 프레임에 화면을 찍는다.
-- 메시지 번호 기록은 msg.txt. 드라이버(boot.lua, 보통 dq5warp.lua) 뒤에 붙여 쓴다.
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local L = require("lib")
local frm = tonumber(os.getenv("FROMMSG") or "0", 16)
local tos = {}
for a in string.gmatch(os.getenv("TOMSG") or "", "[^,]+") do tos[#tos + 1] = tonumber(a, 16) end
local shots = {}
for a in string.gmatch(os.getenv("SHOTS") or "", "[^,]+") do shots[tonumber(a)] = true end
local n, k, log = 0, 1, {}
emu.addMemoryCallback(function()
  local s = emu.getState()
  local a = s["cpu.a"] & 0xFFFF
  log[#log + 1] = string.format("%d %03X", n, a)
  if a == frm and k <= #tos then
    s["cpu.a"] = (s["cpu.a"] & 0xFF0000) | tos[k]
    emu.setState(s)
    log[#log + 1] = string.format("%d -> %03X", n, tos[k])
    k = k + 1
  end
end, emu.callbackType.exec, 0x248C39, 0x248C39)
emu.addEventCallback(function()
  n = n + 1
  if shots[n] then L.shot(string.format("s%05d.png", n)) end
  if n == tonumber(os.getenv("MAXF") or "0") - 1 then L.write("msg.txt", table.concat(log, "\n") .. "\n") end
end, emu.eventType.endFrame)
dofile(os.getenv("LIBDIR") .. "/boot.lua")
