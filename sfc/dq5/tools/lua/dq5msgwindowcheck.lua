-- 전투 메시지 창 자리·크기 쓰기 실측(dq5msgwindowcheck.py 가 부름). DRIVER 의 입력을 재생하며
-- FROM 프레임부터 STEP 프레임마다 VRAM BG3 타일맵(워드 1C00~1FFF, 2KB)을 bg3.bin 에, 같은 때의 WRAM 창 버퍼
-- 7E:5000~57FF 를 buf.bin 에 이어 붙이고, SHOTEVERY 프레임마다 화면을 fNNNNN.png 로 남긴다.
-- SWAP="05E:006,118;069:006" 은 24:8C39 에 들어온 메시지 번호(A)를 차례로 바꾼다.
-- exec.txt 에는 24:A519·24:A523(▼ 기다림)·24:880A(FD ▼)·24:A569(줄 올리기)·24:8C39(메시지 번호)에 들어온 프레임,
-- 그 메시지의 이름·숫자 인자 대기열 $F5~$F8 을 ARG 줄로, 24:A4A4(글자 하나) 의 글자·줄($0F0E)·칸($0F0D), 00:FDA1 에서 $0F5E 가 1CE0(BG3 효과 층)인 전송(EFF)을 적는다.
-- 00:FDA1 의 모든 전송은 FX 줄(VRAM 자리 $0F5E, 크기 $4375(창을 올린 롬은 $4305), 1CE0 이면 7E:8A1D 에서 0 이 아닌 워드가 있는 첫·끝 BG3 줄)로,
-- 연출 시작 22:D73C 의 A 는 FXID 줄로, 행동 결정 20:8846 의 행동자 $1200·행동 $1201 은 ACT 줄로 적는다.
-- OAM(544바이트)과 OBJ 크기 모드(OBSEL 위 3비트) 1바이트는 덤프 프레임마다 oam.bin 에 이어 붙인다.
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
local n, log, dumps, bufs, oams = 0, {}, {}, {}, {}
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
  local d = emu.getState()['cpu.d']
  log[#log + 1] = string.format('%d ARG %02X %02X %02X %02X', n, emu.read(0x7E0000 + d + 0xF5, m),
    emu.read(0x7E0000 + d + 0xF6, m), emu.read(0x7E0000 + d + 0xF7, m), emu.read(0x7E0000 + d + 0xF8, m))
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
  local dest = emu.read(0x7E0F5E, m) | emu.read(0x7E0F5F, m) << 8
  -- 창을 21줄 위로 올린 롬은 이 전송을 채널 0 으로 옮긴다(dq5windowwrite.py DMA_REGS). 원본 7E:8A1D 를 가리키는 채널을 읽는다.
  local ch = (emu.read(0x4302, m) == 0x1D and emu.read(0x4303, m) == 0x8A) and 0x4300 or 0x4370
  local size = emu.read(ch + 5, m) | emu.read(ch + 6, m) << 8
  local rows = '-'
  if dest == 0x1CE0 then
    log[#log + 1] = string.format('%d EFF', n)
    local top, bot
    for r = 0, 13 do
      for c = 0, 63 do
        if emu.read(0x7E8A1D + r * 64 + c, m) ~= 0 then
          top, bot = top or r + 7, r + 7
          break
        end
      end
    end
    if top then rows = string.format('%d %d', top, bot) end
  end
  log[#log + 1] = string.format('%d FX %04X %04X %s', n, dest, size, rows)
end, emu.callbackType.exec, 0x00FDA1, 0x00FDA1)
emu.addMemoryCallback(function()
  log[#log + 1] = string.format('%d FXID %02X', n, emu.getState()['cpu.a'] & 0xFF)
end, emu.callbackType.exec, 0x22D73C, 0x22D73C)
emu.addMemoryCallback(function()
  log[#log + 1] = string.format('%d ACT %02X %02X', n, emu.read(0x7E1200, m), emu.read(0x7E1201, m))
end, emu.callbackType.exec, 0x208846, 0x208846)
-- HLOG=1 이면 보이는 줄(ppu.scanline 1~224)에서 PPU 레지스터 $2105~$2112·$2121·$2123~$2133 에 쓴 것(HDMA 쓰기도 걸림)을
-- 프레임·레지스터마다 첫·끝 줄과 횟수, HLOGTAIL(기본 150) 줄부터 쓴 줄:값(겹치지 않게, 줄 10진 세 자리:값 16진, 없으면 -)
-- 으로 모아 hdma.txt 에 "프레임 레지스터 첫줄 끝줄 횟수 줄:값,…" 으로 적는다. 레지스터는 거울 뱅크
-- 00~3F·80~BF 어디로도 쓸 수 있다. 쓰기마다 상태를 읽어 실행이 열 배 넘게 느려지므로 따로 켠다. VRAM·CGRAM 데이터
-- 포트($2118·$2119·$2122)는 DMA 로 바이트마다 걸려 뺀다.
local hlogon = os.getenv('HLOG') == '1'
local hlogtail = tonumber(os.getenv('HLOGTAIL') or '150')
local lines = {}
local function pcb(addr, value)
  local sl = emu.getState()['ppu.scanline']
  if sl < 1 or sl > 224 then return end
  local r = addr & 0xFFFF
  local e = lines[r]
  if e then
    e[1], e[2], e[3] = math.min(e[1], sl), math.max(e[2], sl), e[3] + 1
  else
    e = {sl, sl, 1, {}}
    lines[r] = e
  end
  if sl >= hlogtail then e[4][string.format('%03d:%02X', sl, value)] = true end
end
local function tail(set)
  local t = {}
  for v in pairs(set) do t[#t + 1] = v end
  table.sort(t)
  return #t > 0 and table.concat(t, ',') or '-'
end
for bank = 0, 0xBF do
  if hlogon and (bank < 0x40 or bank >= 0x80) then
    for _, r in ipairs({{0x2105, 0x2112}, {0x2121, 0x2121}, {0x2123, 0x2133}}) do
      emu.addMemoryCallback(pcb, emu.callbackType.write, bank * 0x10000 + r[1], bank * 0x10000 + r[2])
    end
  end
end
local hlog = {}
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
  for r, e in pairs(lines) do hlog[#hlog + 1] = string.format('%d %04X %d %d %d %s', n, r, e[1], e[2], e[3], tail(e[4])) end
  lines = {}
  n = n + 1
  if n == 3 and #ranges > 0 then base_r, base_w = counts() end
  if n >= from and (n - from) % step == 0 and n <= last then
    dumps[#dumps + 1] = block(0x3800, 0x800, emu.memType.snesVideoRam)
    bufs[#bufs + 1] = block(0x7E5000, 0x800, m)
    oams[#oams + 1] = block(0, 0x220, emu.memType.snesSpriteRam) .. string.char(emu.getState()['ppu.oamMode'])
    if shotevery > 0 and (n - from) % shotevery == 0 then L.shot(string.format('f%05d.png', n)) end
  end
  if n == last then
    L.write('bg3.bin', table.concat(dumps))
    L.write('buf.bin', table.concat(bufs))
    L.write('oam.bin', table.concat(oams))
    if hlogon then L.write('hdma.txt', table.concat(hlog, '\n') .. '\n') end
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
