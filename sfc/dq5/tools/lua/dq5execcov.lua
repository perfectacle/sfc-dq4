-- DQ5: 접근 카운터(콜백 없음)로 긴 실행의 커버리지를 모은다. MAXF 프레임에 SHOT_DIR 에
--   exec.txt   롬에서 실행된 바이트의 파일 오프셋(연산자 바이트도 들어감)
--   acc.txt    WRAM 범위 RANGE(기본 1ABC-1BB1)의 읽기·쓰기 횟수 합
--   vw.txt     VRAM 0x400워드 칸마다 쓰기 횟수(FROM 프레임부터)
--   probe.txt  POSFILE(쉼표로 CPU 주소)의 자리가 명령으로 실행될 때 레지스터(자리마다 처음 20번)
--   cdl.bin    CDL=1 이면 MesenCE 가 이 롬에 쌓아 둔 코드·자료 기록(emu.getCdlData, 바이트마다 bit0 코드·bit1 자료)
-- 입력: STATE 가 있으면 세이브스테이트, PRE 는 dq5msg.lua 와 같은 꼴. BOOT=1 이면 LIBDIR 의 boot.lua 를 드라이버로 돈다.
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local L = require("lib")
if os.getenv("STATE") then L.loadState(os.getenv("STATE")) end
local m = emu.memType.snesMemory
local n, maxf, from = 0, tonumber(os.getenv("MAXF")), tonumber(os.getenv("FROM") or "0")
local lo, hi = (os.getenv("RANGE") or "1ABC-1BB1"):match("(%x+)-(%x+)")
lo, hi = tonumber(lo, 16), tonumber(hi, 16)
local seq, si, left = {}, 1, nil
for tok in string.gmatch(os.getenv("PRE") or "", "[^,]+") do
  local b, f = tok:match("([%w+]+):(%d+)")
  seq[#seq + 1] = {b, tonumber(f)}
end
local hits, cnt = {}, {}
if os.getenv("POSFILE") then
  for a in string.gmatch(io.open(os.getenv("POSFILE")):read("a"), "%x+") do
    local addr = tonumber(a, 16)
    emu.addMemoryCallback(function()
      local k = addr & 0x7FFFFF
      cnt[k] = (cnt[k] or 0) + 1
      if cnt[k] > 20 then return end
      local s = emu.getState()
      local sp = s["cpu.sp"]
      hits[#hits + 1] = string.format("%06X A=%04X X=%04X Y=%04X D=%04X DB=%02X P=%02X S1=%04X", k, s["cpu.a"], s["cpu.x"],
        s["cpu.y"], s["cpu.d"], s["cpu.dbr"], s["cpu.ps"], emu.read(sp + 1, m) | emu.read(sp + 2, m) << 8)
    end, emu.callbackType.exec, addr, addr)
  end
end
local base
local function vcounts() return emu.getAccessCounters(emu.memType.snesVideoRam, emu.counterType.writeCount) end
local function write(name, s) local f = io.open(os.getenv("SHOT_DIR") .. "/" .. name, "w"); f:write(s); f:close() end
emu.addEventCallback(function()
  n = n + 1
  if n == from then base = vcounts() end
  if not os.getenv("BOOT") then
    local inp = {}
    if seq[si] then
      if not left then left = seq[si][2] end
      if seq[si][1] ~= "wait" then for b in string.gmatch(seq[si][1], "[^+]+") do inp[b] = true end end
      left = left - 1
      if left <= 0 then si = si + 1; left = nil end
    end
    emu.setInput(inp, 0)
  end
  if n >= maxf then
    local c, out = vcounts(), {}
    for blk = 0, 31 do
      local s = 0
      for i = blk * 0x800, blk * 0x800 + 0x7FF do s = s + c[i] - (base and base[i] or 0) end
      out[#out + 1] = string.format("%04X %d", blk * 0x400, s)
    end
    write("vw.txt", table.concat(out, "\n") .. "\n")
    local ex, w = emu.getAccessCounters(emu.memType.snesPrgRom, emu.counterType.execCount), {}
    for i = 0, #ex do if ex[i] and ex[i] > 0 then w[#w + 1] = string.format("%06X", i) end end
    write("exec.txt", table.concat(w, "\n") .. "\n")
    local rc = emu.getAccessCounters(emu.memType.snesWorkRam, emu.counterType.readCount)
    local wc = emu.getAccessCounters(emu.memType.snesWorkRam, emu.counterType.writeCount)
    local r, ww = 0, 0
    for i = lo, hi do r = r + rc[i]; ww = ww + wc[i] end
    write("acc.txt", string.format("r=%d w=%d\n", r, ww))
    write("probe.txt", table.concat(hits, "\n") .. "\n")
    if os.getenv("CDL") then
      local c, b = emu.getCdlData(emu.memType.snesPrgRom), {}
      for i = 0, #c do b[#b + 1] = string.char(c[i] or 0) end
      local f = io.open(os.getenv("SHOT_DIR") .. "/cdl.bin", "wb"); f:write(table.concat(b)); f:close()
    end
    emu.stop()
  end
end, emu.eventType.inputPolled)
if os.getenv("BOOT") then dofile(os.getenv("LIBDIR") .. "/boot.lua") end
