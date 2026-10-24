-- 패드 2 입력과 PRG 롬 덮어쓰기를 더해 입력 드라이버(DRIVER, 기본 boot.lua)를 돌린다.
-- 패드 2 를 읽는 곳이 하나뿐(0F/1F:$CAD8)이라, 그 값이 쓰이게 롬을 고쳐 보며 무엇이 달라지는지 본다.
-- MesenCE 의 emu.setInput 은 포트 번호를 바꿔도 패드 1 로 들어가므로(MesenCE 설정의 포트 2 가 비어 있음),
-- 패드 읽기(0F/1F:$C8EC)가 패드 2 를 다 읽고 돌아가는 $C90B(X=1)에서 $15 를 덮어 패드 2 를 흉내 낸다.
-- 환경 변수:
--   PAD2=03             패드 2 값($15 꼴 16진: bit0 A, 1 B, 2 Select, 3 Start, 4 위, 5 아래, 6 왼쪽, 7 오른쪽)
--   PAD2FROM=0          덮기 시작할 프레임(드라이버 프레임과 같은 셈)
--   ROMPATCH="3CADC=F00CEA;7CADC=F00CEA"   PRG 롬 오프셋(16진)=바이트들. 세이브스테이트를 불러온 뒤에 쓴다
--   LOGW="0584,0585,0044,0045"  매 프레임 이 CPU 주소들의 값이 바뀔 때만 debugpad.txt 에 한 줄
--   PAD_DRIVER          이 스크립트를 다른 프로브의 DRIVER 로 쓸 때 실제 입력 드라이버(예: $LIBDIR/seq.lua)
--   DRIVER, SHOT_DIR, MAXF 와 드라이버의 변수(STATE, SEQ, TAIL …)는 그대로
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local L = require("lib")
local pad2 = tonumber(os.getenv("PAD2") or "", 16)
local from = tonumber(os.getenv("PAD2FROM") or "0")
local patches = {}
for a, bytes in string.gmatch(os.getenv("ROMPATCH") or "", "(%x+)=(%x+)") do
  patches[#patches + 1] = {tonumber(a, 16), bytes}
end
local logs = {}
for a in (os.getenv("LOGW") or ""):gmatch("%x+") do logs[#logs + 1] = tonumber(a, 16) end
local maxf = tonumber(os.getenv("MAXF") or "0")

local n, lines, last, patched = 0, {}, nil, false
if pad2 then
  emu.addMemoryCallback(function()
    if n >= from and emu.getState()["cpu.x"] == 1 then emu.write(0x15, pad2, L.mem) end
  end, emu.callbackType.exec, 0xC90B, 0xC90B)
end
emu.addEventCallback(function()
  n = n + 1
  -- 드라이버가 세이브스테이트를 불러오는 첫 몇 프레임 뒤에 덮어써야 남는다
  if n == 3 and not patched then
    for _, p in ipairs(patches) do
      for i = 1, #p[2] - 1, 2 do
        emu.write(p[1] + (i - 1) // 2, tonumber(p[2]:sub(i, i + 1), 16), emu.memType.nesPrgRom)
      end
    end
    patched = true
  end
  if #logs > 0 then
    local t = {}
    for _, a in ipairs(logs) do t[#t + 1] = string.format("%04X=%02X", a, emu.read(a, L.mem)) end
    local s = table.concat(t, " ")
    if s ~= last then lines[#lines + 1] = n .. " " .. s; last = s end
  end
  if maxf > 0 and n == maxf - 1 then L.write("debugpad.txt", table.concat(lines, "\n") .. "\n") end
end, emu.eventType.endFrame)
if os.getenv("PAD_DRIVER") then dofile(os.getenv("PAD_DRIVER")) else L.drive() end
