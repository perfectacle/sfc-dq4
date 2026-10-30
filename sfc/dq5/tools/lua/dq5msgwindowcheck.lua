-- 전투 메시지 창 자리·크기 쓰기 실측(dq5msgwindowcheck.py 가 부름). DRIVER 의 입력을 재생하며
-- FROM 프레임부터 STEP 프레임마다 VRAM BG3 타일맵(워드 1C00~1FFF, 2KB)을 bg3.bin 에, 같은 때의 WRAM 창 버퍼
-- 7E:5000~57FF 를 buf.bin 에 이어 붙이고, SHOTEVERY 프레임마다 화면을 fNNNNN.png 로 남긴다.
-- SWAP="05E:006,118;069:006" 은 24:8C39 에 들어온 메시지 번호(A)를 차례로 바꾼다.
-- exec.txt 에는 24:A519·24:A523(▼ 기다림)·24:880A(FD ▼)·24:A569(줄 올리기)·24:8C39(메시지 번호)에 들어온 프레임,
-- 24:A4A4(글자 하나) 의 글자·줄($0F0E)·칸($0F0D), 00:FDA1 에서 $0F5E 가 1CE0(BG3 효과 층)인 전송(EFF)을 적는다.
-- FIELDSNAP=N 이면 첫 전투 메시지 뒤 필드 메시지 글자(24:9E94)가 N 번째일 때 그 프레임·맵·필드 좌표와 7E:1E71~1EFF 를
-- field.txt 에 적는다(전투가 끝나고 필드로 돌아온 때).
-- acc.txt 에는 3프레임째부터 MAXF-2 프레임까지 WRAM 범위 ACC="1DD5-1E70,…" 마다 읽기·쓰기 횟수 합(접근 카운터)을 적는다.
package.path = os.getenv('LIBDIR') .. '/?.lua;' .. package.path
local L = require('lib')
local from, step = tonumber(os.getenv('FROM')), tonumber(os.getenv('STEP'))
local last, shotevery = tonumber(os.getenv('MAXF')) - 2, tonumber(os.getenv('SHOTEVERY') or '0')
local m = emu.memType.snesMemory
local swaps = {}
for src, list in string.gmatch(os.getenv('SWAP') or '', '(%x+):([%x,]+)') do
  local q = {}
  for v in string.gmatch(list, '%x+') do q[#q + 1] = tonumber(v, 16) end
  swaps[tonumber(src, 16)] = q
end
local ranges = {}
for lo, hi in string.gmatch(os.getenv('ACC') or '', '(%x+)-(%x+)') do ranges[#ranges + 1] = {tonumber(lo, 16), tonumber(hi, 16)} end
local n, log, dumps, bufs = 0, {}, {}, {}
local battled, fieldchars, fieldsnap = false, 0, tonumber(os.getenv('FIELDSNAP') or '0')
emu.addMemoryCallback(function()
  local s = emu.getState()
  local a = s['cpu.a'] & 0xFFFF
  local q = swaps[a]
  if q and #q > 0 then
    s['cpu.a'] = (s['cpu.a'] & 0xFF0000) | table.remove(q, 1)
    emu.setState(s)
  end
  log[#log + 1] = string.format('%d 248C39 %03X', n, emu.getState()['cpu.a'] & 0xFFFF)
  battled = true
end, emu.callbackType.exec, 0x248C39, 0x248C39)
emu.addMemoryCallback(function()
  if not battled or fieldsnap == 0 then return end
  fieldchars = fieldchars + 1
  if fieldchars ~= fieldsnap then return end
  local t = {}
  for i = 0x1E71, 0x1EFF do t[#t + 1] = string.format('%02X', emu.read(0x7E0000 + i, m)) end
  L.write('field.txt', string.format('f%d map %02X/%02X field %d,%d\n%s\n', n, emu.read(0x7E00BC, m), emu.read(0x7E00BD, m),
    emu.read(0x7E00B6, m) | emu.read(0x7E00B7, m) << 8, emu.read(0x7E00B8, m) | emu.read(0x7E00B9, m) << 8, table.concat(t, ' ')))
end, emu.callbackType.exec, 0x249E94, 0x249E94)
for _, addr in ipairs({0x24A519, 0x24A523, 0x24880A, 0x24A569}) do
  emu.addMemoryCallback(function()
    log[#log + 1] = string.format('%d %06X', n, addr)
  end, emu.callbackType.exec, addr, addr)
end
emu.addMemoryCallback(function()
  log[#log + 1] = string.format('%d 24A4A4 %02X %d %d', n, emu.getState()['cpu.a'] & 0xFF, emu.read(0x7E0F0E, m),
    emu.read(0x7E0F0D, m))
end, emu.callbackType.exec, 0x24A4A4, 0x24A4A4)
emu.addMemoryCallback(function()
  if emu.read(0x7E0F5E, m) == 0xE0 and emu.read(0x7E0F5F, m) == 0x1C then log[#log + 1] = string.format('%d EFF', n) end
end, emu.callbackType.exec, 0x00FDA1, 0x00FDA1)
local base_r, base_w
local function counts()
  local w = emu.memType.snesWorkRam
  return emu.getAccessCounters(w, emu.counterType.readCount), emu.getAccessCounters(w, emu.counterType.writeCount)
end
local function block(addr, size, mem)
  local t = {}
  for i = 0, size - 1 do t[#t + 1] = string.char(emu.read(addr + i, mem)) end
  return table.concat(t)
end
emu.addEventCallback(function()
  n = n + 1
  if n == 3 and #ranges > 0 then base_r, base_w = counts() end
  if n >= from and (n - from) % step == 0 and n <= last then
    dumps[#dumps + 1] = block(0x3800, 0x800, emu.memType.snesVideoRam)
    bufs[#bufs + 1] = block(0x7E5000, 0x800, m)
    if shotevery > 0 and (n - from) % shotevery == 0 then L.shot(string.format('f%05d.png', n)) end
  end
  if n == last then
    L.write('bg3.bin', table.concat(dumps))
    L.write('buf.bin', table.concat(bufs))
    L.write('exec.txt', table.concat(log, '\n') .. '\n')
    if base_r then
      local rc, wc = counts()
      local out = {}
      for _, r in ipairs(ranges) do
        local reads, writes = 0, 0
        for i = r[1], r[2] do
          reads = reads + rc[i] - base_r[i]
          writes = writes + wc[i] - base_w[i]
        end
        out[#out + 1] = string.format('%04X-%04X %d %d', r[1], r[2], reads, writes)
      end
      L.write('acc.txt', table.concat(out, '\n') .. '\n')
    end
  end
end, emu.eventType.endFrame)
dofile(os.getenv('DRIVER'))
