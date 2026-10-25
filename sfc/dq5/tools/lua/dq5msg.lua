-- DQ5 메시지·대화 실험 드라이버. STATE 세이브스테이트를 불러 ROMPATCH(파일 오프셋=바이트)·SET(첫 프레임에 한 번,
-- 7E 뱅크 주소 =값 |OR &AND)·POKE(매 프레임 고정, CPU 주소=값)를 걸고 PRE 입력(walk.lua 와 같은 "a:4,wait:30" 꼴)을 재생한다.
--   CALLS="248BAF,2481A4"   그 PC 를 지날 때 프레임·A·X·Y(와 LOG 에 적은 주소의 16비트 값)를 기록
--   WW="0000F5,7E31EB"      그 주소에 쓸 때 프레임·값·PC 를 기록
--   WWRANGE="7E3000-7E37FF:1F=0B"  범위 안에서 (주소 & 마스크) = 값 인 곳(인물 표의 한 슬롯)에 쓸 때 기록(WWFROM 프레임부터)
--   SHOTS="300,400"         그 프레임 화면을 sNNNNN.png 로
--   DUMP="300:7E2000:64"    그 프레임에 메모리(CPU 주소부터 길이)를 16진으로 기록
--   WRAMWATCH="119F-13FF"  WRAM 오프셋 범위에 쓰는 PC 를 처음 한 번씩(뱅크 거울과 상관없이) 기록.
--                           WRAMWATCHBY=addr 면 주소마다 처음 한 번씩(낮은 8KB 거울 주소로 묶음), WRAMWATCHREAD=1 이면 읽기도(WRAMR). WWFROM 프레임부터
--   COVER="008000-3FFFFF"   그 범위(쉼표로 여럿)에서 실행한 PC 와 그때의 M·X(cover.txt, tools/listing.py 가 읽음), 본 D 값(dregs.txt). 짧은 실행에만
--   ACCESS="1ABC-1BB1"     끝에 MesenCE 접근 카운터로 그 WRAM 오프셋 범위의 읽기·쓰기 횟수(access.txt)와 롬에서 실행된
--                           바이트(exec.txt, 파일 오프셋). 콜백이 없어 긴 실행에도 쓸 수 있음
--   VMADD=1                 VMADD($2116/2117)를 쓴 PC·주소와 MDMAEN($420B) 때 채널 설정을 모아 vmadd.txt 로
--   VRAMDUMP="300,400"      그 프레임에 VRAM 64KB 를 vNNNNN.bin 으로
--   BG3FONT="26528:8A"      2프레임째에 롬(파일 오프셋)의 1bpp 글자 n 개를 전원을 켤 때(04:E17D)처럼 둘째 평면 FF 로 BG3 타일 1~ 에
--                           다시 써 넣는다(세이브스테이트의 VRAM 에는 고친 롬의 창 글자가 없으므로)
-- STATE 가 없으면 전원을 켠 상태에서 시작한다. MAXF 프레임에 SHOT_DIR/msg.txt 와 end.png 를 쓰고 멈춘다.
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local L = require("lib")
if os.getenv("STATE") then L.loadState(os.getenv("STATE")) end
local m = emu.memType.snesMemory
local seq = {}
for tok in string.gmatch(os.getenv("PRE") or "", "[^,]+") do
  local b, f = tok:match("([%w+]+):(%d+)")
  seq[#seq + 1] = {b, tonumber(f)}
end
local patches, sets, pokes, shots, dumps, extra = {}, {}, {}, {}, {}, {}
for off, hex in string.gmatch(os.getenv("ROMPATCH") or "", "(%x+)=(%x+)") do patches[#patches + 1] = {tonumber(off, 16), hex} end
for a, op, v in string.gmatch(os.getenv("SET") or "", "(%x+)([=|&])(%x+)") do sets[#sets + 1] = {tonumber(a, 16), op, tonumber(v, 16)} end
for a, v in string.gmatch(os.getenv("POKE") or "", "(%x+)=(%x+)") do pokes[#pokes + 1] = {tonumber(a, 16), tonumber(v, 16)} end
for a in string.gmatch(os.getenv("SHOTS") or "", "%d+") do shots[tonumber(a)] = true end
for fr, a, len in string.gmatch(os.getenv("DUMP") or "", "(%d+):(%x+):(%d+)") do dumps[#dumps + 1] = {tonumber(fr), tonumber(a, 16), tonumber(len)} end
for a in string.gmatch(os.getenv("LOG") or "", "[^,]+") do extra[#extra + 1] = a end
local log, n, si, left = {}, 0, 1, nil
local vdumps = {}
for a in string.gmatch(os.getenv("VRAMDUMP") or "", "%d+") do vdumps[tonumber(a)] = true end
local font = os.getenv("BG3FONT")
for a in string.gmatch(os.getenv("CALLS") or "", "[^,]+") do
  local addr = tonumber(a, 16)
  emu.addMemoryCallback(function()
    if #log > 20000 then return end
    local s = emu.getState()
    local t = {string.format("%d %06X A=%04X X=%04X Y=%04X", n, addr, s["cpu.a"], s["cpu.x"], s["cpu.y"])}
    for _, x in ipairs(extra) do t[#t + 1] = string.format("%s=%04X", x, emu.read16(tonumber(x, 16), m)) end
    log[#log + 1] = table.concat(t, " ")
  end, emu.callbackType.exec, addr, addr)
end
for a in string.gmatch(os.getenv("WW") or "", "[^,]+") do
  local addr = tonumber(a, 16)
  emu.addMemoryCallback(function(adr, val)
    if #log > 20000 then return end
    local s = emu.getState()
    log[#log + 1] = string.format("%d W %06X=%02X pc=%02X:%04X", n, adr, val or 0, s["cpu.k"], s["cpu.pc"])
  end, emu.callbackType.write, addr, addr)
end
local wwfrom = tonumber(os.getenv("WWFROM") or "0")
local wr = os.getenv("WWRANGE")
if wr then
  local a, b, mask, val = wr:match("(%x+)-(%x+):(%x+)=(%x+)")
  a, b, mask, val = tonumber(a, 16), tonumber(b, 16), tonumber(mask, 16), tonumber(val, 16)
  emu.addMemoryCallback(function(adr, v)
    if (adr & mask) ~= val or n < wwfrom or #log > 20000 then return end
    local s = emu.getState()
    log[#log + 1] = string.format("%d W %06X=%02X pc=%02X:%04X", n, adr, v or 0, s["cpu.k"], s["cpu.pc"])
  end, emu.callbackType.write, a, b)
end
local ww = os.getenv("WRAMWATCH")
local wseen = {}
if ww then
  local a, b = ww:match("(%x+)-(%x+)")
  local function watch(kind, ctype)
    emu.addMemoryCallback(function(adr, v)
      if n < wwfrom then return end
      local s = emu.getState()
      local key = string.format("%s %02X:%04X", kind, s["cpu.k"], s["cpu.pc"])
      if os.getenv("WRAMWATCHBY") == "addr" and adr then key = kind .. (math.floor(adr) % 0x2000) end
      if not wseen[key] then
        wseen[key] = true
        log[#log + 1] = string.format("%d WRAM%s %05X=%02X pc=%02X:%04X", n, kind, adr or 0, v or 0, s["cpu.k"], s["cpu.pc"])
      end
    end, ctype, tonumber(a, 16), tonumber(b, 16), emu.cpuType.snes, emu.memType.snesWorkRam)
  end
  watch("", emu.callbackType.write)
  if os.getenv("WRAMWATCHREAD") then watch("R", emu.callbackType.read) end
end
local cover = os.getenv("COVER")
local cst, cd = {}, {}
if cover then
  local function hit(addr)
    local st = emu.getState()
    local k = addr * 256 + (st["cpu.ps"] & 0x30)
    if not cst[k] then cst[k] = 0 end
    cst[k] = cst[k] + 1
    local d = st["cpu.d"]
    if not cd[d] then cd[d] = addr end
  end
  for a, b in cover:gmatch("(%x+)-(%x+)") do
    emu.addMemoryCallback(hit, emu.callbackType.exec, tonumber(a, 16), tonumber(b, 16))
  end
end
local vmadd, vlo, vlast, vseen = os.getenv("VMADD"), 0, 0, {}
if vmadd then
  -- VMADD($2116/2117)를 쓴 PC 와 주소, MDMAEN($420B)을 쓴 PC 와 그때 켠 채널의 B 버스·A 주소·길이·VMADD
  local function rec(k) vseen[k] = (vseen[k] or 0) + 1 end
  emu.addMemoryCallback(function(adr, v)
    local s = emu.getState()
    local pc = string.format("%02X:%04X", s["cpu.k"], s["cpu.pc"])
    if adr & 0xFFFF == 0x2116 then vlo = v; vlast = (vlast & 0xFF00) | v
    else vlast = (v << 8) | vlo; rec(string.format("VMADD %04X pc=%s", vlast, pc)) end
  end, emu.callbackType.write, 0x2116, 0x2117)
  emu.addMemoryCallback(function(adr, v)
    local s = emu.getState()
    local pc = string.format("%02X:%04X", s["cpu.k"], s["cpu.pc"])
    for ch = 0, 7 do
      if v & (1 << ch) ~= 0 then
        local b = 0x4300 + ch * 16
        local bb = emu.read(b + 1, emu.memType.snesMemory)
        local aa = emu.read(b + 4, emu.memType.snesMemory) * 65536 + emu.read16(b + 2, emu.memType.snesMemory)
        local len = emu.read16(b + 5, emu.memType.snesMemory)
        local tag = (bb == 0x18 or bb == 0x19) and string.format(" vmadd=%04X", vlast) or ""
        rec(string.format("DMA ch%d bbus=21%02X src=%06X len=%04X%s pc=%s", ch, bb, aa, len, tag, pc))
      end
    end
  end, emu.callbackType.write, 0x420B, 0x420B)
end
local maxf = tonumber(os.getenv("MAXF") or "1000")
emu.addEventCallback(function()
  n = n + 1
  if n == 1 then
    for _, p in ipairs(patches) do
      for i = 0, #p[2] / 2 - 1 do
        emu.write(p[1] + i, tonumber(p[2]:sub(i * 2 + 1, i * 2 + 2), 16), emu.memType.snesPrgRom)
      end
    end
    for _, s in ipairs(sets) do
      local a = 0x7E0000 | s[1]
      local v = emu.read(a, m)
      if s[2] == "=" then v = s[3] elseif s[2] == "|" then v = v | s[3] else v = v & s[3] end
      emu.write(a, v, m)
    end
  end
  if n == 2 and font then
    local off, cnt = font:match("(%x+):(%x+)")
    off, cnt = tonumber(off, 16), tonumber(cnt, 16)
    for t = 1, cnt do
      for r = 0, 7 do
        local b = emu.read(off + (t - 1) * 8 + r, emu.memType.snesPrgRom)
        emu.write(0x2000 + t * 16 + r * 2, b, emu.memType.snesVideoRam)
        emu.write(0x2000 + t * 16 + r * 2 + 1, 0xFF, emu.memType.snesVideoRam)
      end
    end
  end
  for _, p in ipairs(pokes) do emu.write(p[1], p[2], m) end
  L.release()
  if si <= #seq then
    local s = seq[si]
    if left == nil then left = s[2] end
    if s[1] ~= "wait" then local t = {}; for b in s[1]:gmatch("[^+]+") do t[b] = true end; L.press(t) end
    left = left - 1
    if left <= 0 then si = si + 1; left = nil end
  end
  if shots[n] then L.shot(string.format("s%05d.png", n)) end
  if vdumps[n] then L.dump(string.format("v%05d.bin", n), emu.memType.snesVideoRam, 0x10000) end
  for _, d in ipairs(dumps) do
    if d[1] == n then
      local t = {}
      for i = 0, d[3] - 1 do t[#t + 1] = string.format("%02X", emu.read(d[2] + i, m)) end
      log[#log + 1] = string.format("%d dump %06X %s", n, d[2], table.concat(t, " "))
    end
  end
  if n == maxf and os.getenv("ACCESS") then
    -- MesenCE 접근 카운터(콜백 없이 빠름, 배열 첨자는 0부터): WRAM 범위의 읽기·쓰기 횟수, 롬에서 실행된 바이트 수
    local a, b = os.getenv("ACCESS"):match("(%x+)-(%x+)")
    a, b = tonumber(a, 16), tonumber(b, 16)
    local rd = emu.getAccessCounters(emu.memType.snesWorkRam, emu.counterType.readCount)
    local wr = emu.getAccessCounters(emu.memType.snesWorkRam, emu.counterType.writeCount)
    local ex = emu.getAccessCounters(emu.memType.snesPrgRom, emu.counterType.execCount)
    local t = {}
    for i = a, b do
      if (rd[i] or 0) > 0 or (wr[i] or 0) > 0 then t[#t + 1] = string.format("%05X r=%d w=%d", i, rd[i] or 0, wr[i] or 0) end
    end
    local e = {}
    for i, v in pairs(ex) do if v > 0 then e[#e + 1] = string.format("%06X %d", i, v) end end
    table.sort(e)
    L.write("access.txt", table.concat(t, "\n") .. "\n")
    L.write("exec.txt", table.concat(e, "\n") .. "\n")
  end
  if n == maxf and vmadd then
    local t = {}
    for k, c in pairs(vseen) do t[#t + 1] = k .. " x" .. c end
    table.sort(t)
    L.write("vmadd.txt", table.concat(t, "\n") .. "\n")
  end
  if n == maxf then
    if cover then
      local t = {}
      for k, c in pairs(cst) do t[#t + 1] = string.format("%06X %02X %d", k // 256, k % 256, c) end
      table.sort(t)
      L.write("cover.txt", table.concat(t, "\n") .. "\n")
      local u = {}
      for d, pc in pairs(cd) do u[#u + 1] = string.format("D=%04X first=%06X", d, pc) end
      table.sort(u)
      L.write("dregs.txt", table.concat(u, "\n") .. "\n")
    end
    L.write("msg.txt", table.concat(log, "\n") .. "\n")
    L.shot("end.png")
    emu.stop()
  end
end, emu.eventType.endFrame)
