-- dq4ff9acheck.py 가 부른다. 배 선실 세이브스테이트(STATE)에서 인물 슬롯 1~1F 의 대화 번호를 TALK(16진, 7E:36E0+슬롯
-- 하위·7E:3700+슬롯 상위)로, 코인 7E:203C~203E 를 COINS(10진)로 두고 PRE 입력으로 파파스에게 말을 걸어 시설 장면에 들어간다.
-- NMI 공통 입구 00:887C(JMP ($1944))마다 작업 번호를 세어 nmi.txt 에 「작업 횟수」 를 남긴다.
--   ENTRY=60xxxx   WqNmiEntry 의 CPU 주소. 주면 작업마다 그 NMI 에서 WqNmiEntry 가 돈 횟수도 센다
--   INJECT=N       작업 FF9A 인 NMI 동안 대기열(!wq_*)이 비어 있으면 BG3 칸 1F0(VRAM 워드 0F80)에 그림 한 칸을 넣는다.
--                  N 번까지, 앞 항목을 확인한 뒤 30프레임 쉬고 다음. 넣은 뒤 첫 NMI 가 끝나 다음 NMI 입구에 닿았을 때
--                  항목 수가 0 이고 VRAM 이 넣기 전에는 그림과 달랐다가 넣은 그림과 같아졌으면 「다음 NMI 에 나감」
--   SHOT=f1,f2     그 프레임의 화면
--   SET="075B=00;…" 불러온 뒤 2~10프레임에 쓸 WRAM(7E 뱅크 하위 16비트 주소=값). 난수·시각을 고정한다
--   ROMPATCH="11E7C2=186B;…"  첫 프레임에 PRG 롬(파일 오프셋=바이트들)을 메모리에서만 바꾼다. 조우 없애기, 변이 시험
-- FF9A 작업 NMI 입구의 대기열 항목 수(!wq_count)를 wq.txt 에 「first 첫NMI값」「nonzero 0 아닌 NMI 수」「max 가장 큰 값」 으로.
-- 끝(MAXF)에 nmi.txt·inject.txt·wq.txt 를 쓰고 멈춘다.
package.path = os.getenv('LIBDIR') .. '/?.lua;' .. package.path
local L = require('lib')
L.loadState(os.getenv('STATE'))
local m = emu.memType.snesMemory
local vram = emu.memType.snesVideoRam

local WQ_COUNT, WQ_OFF, WQ_RD, WQ_BUF = 0x7EA97E, 0x7EA980, 0x7EA978, 0x7E3EB0
local VWORD = 0x0F80
local PATTERN = {0x81, 0x42, 0x24, 0x18, 0x18, 0x24, 0x42, 0x81, 0xFF, 0x00, 0xFF, 0x00, 0xFF, 0x00, 0xFF, 0x00}

local talk = tonumber(os.getenv('TALK') or '0', 16)
local coins = tonumber(os.getenv('COINS') or '0')
local entry = os.getenv('ENTRY') and tonumber(os.getenv('ENTRY'), 16)
local inject = tonumber(os.getenv('INJECT') or '0')
local maxf = tonumber(os.getenv('MAXF'))
local shots = {}
for t in string.gmatch(os.getenv('SHOT') or '', '%d+') do shots[tonumber(t)] = true end
local seq = {}
for tok in string.gmatch(os.getenv('PRE') or '', '[^,]+') do
  local b, f = tok:match('([%w+]+):(%d+)')
  seq[#seq + 1] = {b, tonumber(f)}
end

local sets, patches = {}, {}
for a, v in string.gmatch(os.getenv('SET') or '', '(%x+)=(%x+)') do sets[#sets + 1] = {0x7E0000 + tonumber(a, 16), tonumber(v, 16)} end
for a, bytes in string.gmatch(os.getenv('ROMPATCH') or '', '(%x+)=(%x+)') do
  for i = 1, #bytes - 1, 2 do patches[#patches + 1] = {tonumber(a, 16) + (i - 1) // 2, tonumber(bytes:sub(i, i + 1), 16)} end
end

local frame, si, left = 0, 1, nil
local nmi, task = 0, nil
local tasks, order, entries = {}, {}, {}
local pending, injected, results, rest = nil, 0, {}, 0
local wq_first, wq_nonzero, wq_max = nil, 0, 0

-- 넣을 때마다 다른 그림(k 번째)이라야 앞 항목이 남긴 그림과 견주어 「나감」 을 가린다
local function pattern(k, i) return (PATTERN[i] + 0x13 * k) & 0xFF end

local function vram_same(k)
  for i = 1, #PATTERN do
    if emu.read(VWORD * 2 + i - 1, vram) ~= pattern(k, i) then return false end
  end
  return true
end

local function rd16(a) return emu.read(a, m) | emu.read(a + 1, m) << 8 end

emu.addMemoryCallback(function()
  nmi = nmi + 1
  task = rd16(0x7E1944)
  if not tasks[task] then tasks[task] = 0; order[#order + 1] = task end
  tasks[task] = tasks[task] + 1
  if task == 0xFF9A then
    local c = emu.read(WQ_COUNT, m)
    if wq_first == nil then wq_first = c end
    if c > 0 then wq_nonzero = wq_nonzero + 1 end
    if c > wq_max then wq_max = c end
  end
  if pending then
    if pending.nmi == nmi - 2 then
      local count = emu.read(WQ_COUNT, m)
      results[#results + 1] = string.format('%d nmi %d task %04X count %d vram %s before %s', pending.frame, pending.nmi,
        pending.task, count, vram_same(pending.k) and 'same' or 'differs', pending.before)
      pending, rest = nil, 30
    end
  end
end, emu.callbackType.exec, 0x00887C, 0x00887C)

if entry then
  emu.addMemoryCallback(function()
    if task then entries[task] = (entries[task] or 0) + 1 end
  end, emu.callbackType.exec, entry, entry)
end

emu.addEventCallback(function()
  frame = frame + 1
  if frame == 1 then
    for _, p in ipairs(patches) do emu.write(p[1], p[2], emu.memType.snesPrgRom) end
  end
  if frame >= 2 and frame <= 10 then
    for _, w in ipairs(sets) do emu.write(w[1], w[2], m) end
    for s = 1, 0x1F do
      emu.write(0x7E36E0 + s, talk & 0xFF, m)
      emu.write(0x7E3700 + s, talk >> 8, m)
    end
    emu.write(0x7E203C, coins & 0xFF, m)
    emu.write(0x7E203D, (coins >> 8) & 0xFF, m)
    emu.write(0x7E203E, (coins >> 16) & 0xFF, m)
  end
  if rest > 0 then rest = rest - 1 end
  if inject > injected and not pending and rest == 0 and task == 0xFF9A and emu.read(WQ_COUNT, m) == 0 then
    -- 넣기 전에 VRAM 이 이미 그 그림이면 나갔는지 가릴 수 없다(before 를 같이 적는다)
    local k = injected + 1
    local before = vram_same(k) and 'same' or 'differs'
    -- 항목 [VRAM 워드 2][방식 0 = 두 평면][칸 수 1][16바이트]
    emu.write(WQ_BUF, VWORD & 0xFF, m)
    emu.write(WQ_BUF + 1, VWORD >> 8, m)
    emu.write(WQ_BUF + 2, 0x00, m)
    emu.write(WQ_BUF + 3, 0x01, m)
    for i = 1, #PATTERN do emu.write(WQ_BUF + 3 + i, pattern(k, i), m) end
    emu.write(WQ_OFF, 4 + #PATTERN, m); emu.write(WQ_OFF + 1, 0, m)
    emu.write(WQ_RD, 0, m); emu.write(WQ_RD + 1, 0, m)
    emu.write(WQ_COUNT, 1, m)
    injected = injected + 1
    pending = {frame = frame, nmi = nmi, task = task, before = before, k = k}
  end
  L.release()
  if si <= #seq then
    local s = seq[si]
    if left == nil then left = s[2] end
    if s[1] ~= 'wait' then local t = {}; for b in s[1]:gmatch('[^+]+') do t[b] = true end; L.press(t) end
    left = left - 1
    if left <= 0 then si = si + 1; left = nil end
  end
  if shots[frame] then L.shot(string.format('f%05d.png', frame)) end
  if frame == maxf then
    local t = {}
    for _, k in ipairs(order) do
      t[#t + 1] = string.format('%04X %d%s', k, tasks[k], entry and string.format(' entry %d', entries[k] or 0) or '')
    end
    L.write('nmi.txt', table.concat(t, '\n') .. '\n')
    L.write('inject.txt', table.concat(results, '\n') .. (#results > 0 and '\n' or ''))
    L.write('wq.txt', string.format('first %s\nnonzero %d\nmax %d\n', wq_first and tostring(wq_first) or '-', wq_nonzero, wq_max))
    emu.stop()
  end
end, emu.eventType.endFrame)
