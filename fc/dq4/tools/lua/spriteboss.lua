-- デスピサロ(몬스터 AE)처럼 형태가 바뀌는 적과 전투를 일으켜, 형태 번호 $6E7E 가 바뀔 때마다 화면을 덤프한다.
-- 전투를 여는 방법은 spritebattle.lua 와 같다(조우 판정 18:$9D06 을 메모리상 CLC/RTS, 전투 시작 18:$A11A 에서 무리를 덮음).
-- 전투가 시작되면 적 HP($7274+14n+10, 2바이트)를 HP 이하로 눌러 두고 A 를 눌러 공격하게 한다.
-- $6E7E 가 바뀌면 입력과 HP 누르기를 멈추고 WAIT 프레임 뒤에 덤프한다(형태 바뀜 연출이 끝난 화면).
-- 환경 변수:
--   STATE        출발 세이브스테이트(필드에서 위아래로 걸을 수 있는 곳, 예: dq4-debugB-start.mss)
--   MON="AE:1"   무리(16진 ID:마릿수, 쉼표로 넷까지)
--   HP=1         적 HP 를 이 값 이하로 누른다(0 이면 누르지 않음)
--   HPFRAMES=n   전투 시작 뒤 n 프레임까지만 HP 를 누른다(전투 뒤 $7200 은 필드 그림 표라 덮으면 안 됨)
--   WAIT=400     전투 시작·형태 바뀜 뒤 덤프까지 기다릴 프레임
--   FORMS=8      이만큼 덤프하면 멈춘다
--   SETFORM=n    전투 시작 직후 $6E7E 를 n 으로 쓴다(16진, 없으면 쓰지 않음)
--   PRESS=1      기다리는 동안에도 A 누르기·HP 누르기를 계속한다(전투를 끝내고 필드로 돌아온 화면을 덤프할 때)
--   OAMLOG=1     전투 중 프레임마다 OAM 에 보이는 타일·속성 종류를 oamlog.txt 에(새 조합이 나온 프레임만)
--   CALLS="14:AC1A,0F:C73E"  전투 중 이 주소(뱅크:CPU 주소, 고정 뱅크는 0F)를 실행할 때마다 calls.txt 에 한 줄
--                (프레임, $6E7E, 주소, A X Y, 그때의 $8000 뱅크, ZP 의 바이트들)
--   ZP="00,01,02,03,04,05,08,09,0A,0C,C0,C1"  CALLS 줄에 적을 제로 페이지 주소
--   MAXF=20000   이 프레임에서 멈춘다
-- 결과: SHOT_DIR/f<순번>.{ram,sram,chr,nt,pal,oam,png}, boss.txt(프레임마다 바뀐 $6E7E 와 덤프 이름)
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local L = require("lib")
L.loadState(os.getenv("STATE"))
local mons = {}
for id, cnt in string.gmatch(os.getenv("MON") or "AE:1", "(%x+):(%x+)") do
  mons[#mons + 1] = {tonumber(id, 16), tonumber(cnt, 16)}
end
local hpcap = tonumber(os.getenv("HP") or "1")
local hpframes = tonumber(os.getenv("HPFRAMES") or "0")
local wait = tonumber(os.getenv("WAIT") or "400")
local forms = tonumber(os.getenv("FORMS") or "8")
local maxf = tonumber(os.getenv("MAXF") or "20000")
local setform = os.getenv("SETFORM") and tonumber(os.getenv("SETFORM"), 16)
local oamlog = os.getenv("OAMLOG") == "1"
local keep = os.getenv("PRESS") == "1"
local ENC, START = 0x18 * 0x4000 + 0x1D06, 0x18 * 0x4000 + 0x211A
local n, hit, log, form, due, dumps = 0, nil, {}, nil, nil, 0
local oamseen, oamlines = {}, {}

emu.addMemoryCallback(function(addr)
  if hit then return end
  if L.prgOffset(addr) ~= START then return end
  hit = n
  for i = 0, 3 do
    local m = mons[i + 1] or {0xFF, 0}
    emu.write(0x6E45 + i, m[1], L.mem)
    emu.write(0x6E49 + i, m[2], L.mem)
  end
  log[#log + 1] = string.format("start frame=%d mon=%s", n, os.getenv("MON") or "AE:1")
end, emu.callbackType.exec, 0xA11A, 0xA11A)

local calls, zp = {}, {}
for z in string.gmatch(os.getenv("ZP") or "00,01,02,03,04,05,08,09,0A,0C,C0,C1", "%x+") do zp[#zp + 1] = tonumber(z, 16) end
for b, a in string.gmatch(os.getenv("CALLS") or "", "(%x+):(%x+)") do
  local bank, cpu = tonumber(b, 16), tonumber(a, 16)
  local want = nil
  if cpu < 0xC000 then want = bank * 0x4000 + (cpu & 0x3FFF) end
  emu.addMemoryCallback(function(addr)
    if not hit then return end
    if want and L.prgOffset(addr) ~= want then return end
    local st = emu.getState()
    local z = {}
    for _, v in ipairs(zp) do z[#z + 1] = string.format("%02X", emu.read(v, L.mem)) end
    calls[#calls + 1] = string.format("%d %02X %02X:%04X A=%02X X=%02X Y=%02X b8=%02X %s", n, emu.read(0x6E7E, L.mem),
      bank, cpu, st["cpu.a"], st["cpu.x"], st["cpu.y"], (L.prgOffset(0x8000) or 0) // 0x4000, table.concat(z, " "))
  end, emu.callbackType.exec, cpu, cpu)
end

local function finish(tag)
  log[#log + 1] = string.format("%s frame=%d", tag, n)
  L.write("boss.txt", table.concat(log, "\n") .. "\n")
  if #calls > 0 then L.write("calls.txt", table.concat(calls, "\n") .. "\n") end
  if oamlog then L.write("oamlog.txt", table.concat(oamlines, "\n") .. "\n") end
  emu.stop()
end

emu.addEventCallback(function()
  n = n + 1
  if n == 3 then
    emu.write(ENC, 0x18, emu.memType.nesPrgRom)
    emu.write(ENC + 1, 0x60, emu.memType.nesPrgRom)
  end
  if n < 5 then return end
  if n >= maxf then finish("timeout"); return end
  if not hit then
    L.press((n // 12) % 2 == 0 and {up = true} or {down = true})
    return
  end
  if n == hit + 1 then
    if setform then emu.write(0x6E7E, setform, L.mem) end
    due = hit + wait
  end
  local f = emu.read(0x6E7E, L.mem)
  if f ~= form then
    log[#log + 1] = string.format("frame=%d form=%02X", n, f)
    if form ~= nil then due = n + wait end
    form = f
  end
  if oamlog then
    local key = {}
    for i = 0, 63 do
      local y = emu.read(i * 4, emu.memType.nesSpriteRam)
      if y < 0xEF then
        key[#key + 1] = string.format("%02X/%02X", emu.read(i * 4 + 1, emu.memType.nesSpriteRam),
          emu.read(i * 4 + 2, emu.memType.nesSpriteRam) & 0xC3)
      end
    end
    local k = table.concat(key, " ")
    if not oamseen[k] then
      oamseen[k] = true
      oamlines[#oamlines + 1] = string.format("frame=%d form=%02X n=%d %s", n, f, #key, k)
    end
  end
  if due then
    if not keep then L.release() end
    if n >= due then
      local name = string.format("f%d", dumps)
      L.dumpAll(name)
      L.shot(name .. ".png")
      log[#log + 1] = string.format("dump %s frame=%d form=%02X", name, n, f)
      dumps = dumps + 1
      due = nil
      if dumps >= forms then finish("done") end
    end
    if not keep then return end
  end
  if hpcap > 0 and (hpframes == 0 or n < hit + hpframes) then
    for i = 0, 7 do
      local a = 0x7274 + 14 * i + 10
      local hp = emu.read(a, L.mem) | emu.read(a + 1, L.mem) << 8
      if hp > hpcap then
        emu.write(a, hpcap & 0xFF, L.mem)
        emu.write(a + 1, hpcap >> 8, L.mem)
      end
    end
  end
  L.press((n // 6) % 2 == 0 and {a = true} or nil)
end, emu.eventType.endFrame)
