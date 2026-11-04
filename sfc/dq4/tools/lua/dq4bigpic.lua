-- dq4bigpiccheck.py 가 부른다. 전투 NMI 작업(00:8952)마다 $0DF3(큰 그림 요청, 0 이 아니면 큰 그림 길 00:895D)과 NMI 입구
-- 00:887C 의 창 글자 대기열 항목 수(!wq_count)를 nmi.txt 에 「프레임 작업 0DF3 항목수」 로 남기고, 전투 메시지 번호(24:8C39 의 A)를
-- 「프레임 msg 번호」 로 끼운 뒤 NEXT 프로브(dq4battle.lua)를 그대로 돌린다. 기록은 FLUSH 프레임마다 다시 쓴다
-- (NEXT 가 emu.stop 으로 끝내므로 끝에서 한 번만 쓰면 남지 않을 수 있다).
--   WQCOUNT=7EA97E  대기열 항목 수 자리
--   INJECT=N        큰 그림 길 NMI(00:8958 에서 $0DF3 ≠ 0)에 대기열이 비어 있으면 항목 하나(BG3 칸 1F0, VRAM 워드 0F80, 그림
--                   한 칸 = 16바이트)를 넣는다. N 번까지, 앞 항목이 나간 뒤 다음. 그림은 넣을 때마다 바꾸고, 넣기 직전 VRAM 이
--                   그 그림과 같은지 적는다. 뒤 NMI 입구에서 항목 수가 0 이 되면 그때 VRAM 이 그 그림과 같은지 보고
--                   「프레임 inj 넣은NMI 나간NMI before same|differs after same|differs」 를 남긴다(나간 NMI 는 항목 수가 0 이 된
--                   입구의 바로 앞 NMI)
local wq = tonumber(os.getenv('WQCOUNT') or '7EA97E', 16)
local inject = tonumber(os.getenv('INJECT') or '0')
local WQ_OFF, WQ_RD, WQ_BUF = wq + 2, wq - 6, 0x7E3EB0
local nmi, pending, injected = 0, nil, 0
local vram = emu.memType.snesVideoRam

local function pattern(k, i) return (i * 0x11 + 0x13 * k) & 0xFF end

local function vram_same(k)
  for i = 0, 15 do
    if emu.read(0x0F80 * 2 + i, vram) ~= pattern(k, i) then return 'differs' end
  end
  return 'same'
end
local flush = tonumber(os.getenv('FLUSH') or '60')
local m = emu.memType.snesMemory
local out = os.getenv('SHOT_DIR') .. '/nmi.txt'
local f, task, count, log = 0, nil, 0, {}

emu.addMemoryCallback(function()
  nmi = nmi + 1
  task = emu.read(0x7E1944, m) | emu.read(0x7E1945, m) << 8
  count = emu.read(wq, m)
  if pending and count == 0 then
    log[#log + 1] = string.format('%d inj %d %d before %s after %s', f, pending.nmi, nmi - 1, pending.before,
      vram_same(pending.k))
    pending = nil
  end
end, emu.callbackType.exec, 0x00887C, 0x00887C)

emu.addMemoryCallback(function()
  local kind = emu.read(0x7E0DF3, m)
  -- 넣은 항목이 대기열에 있는 동안은 게임 항목 수를 알 수 없어 -1 로 적는다
  log[#log + 1] = string.format('%d %04X %02X %d', f, task or 0, kind, pending and -1 or count)
  if kind ~= 0 and inject > injected and not pending and emu.read(wq, m) == 0 then
    -- 항목 [VRAM 워드 0F80][방식 0 = 두 평면][칸 수 1][16바이트]
    emu.write(WQ_BUF, 0x80, m); emu.write(WQ_BUF + 1, 0x0F, m)
    emu.write(WQ_BUF + 2, 0x00, m); emu.write(WQ_BUF + 3, 0x01, m)
    local k = injected + 1
    local before = vram_same(k)
    for i = 0, 15 do emu.write(WQ_BUF + 4 + i, pattern(k, i), m) end
    emu.write(WQ_OFF, 20, m); emu.write(WQ_OFF + 1, 0, m)
    emu.write(WQ_RD, 0, m); emu.write(WQ_RD + 1, 0, m)
    emu.write(wq, 1, m)
    injected, pending = k, {nmi = nmi, k = k, before = before}
  end
end, emu.callbackType.exec, 0x008958, 0x008958)

emu.addMemoryCallback(function()
  log[#log + 1] = string.format('%d msg %03X', f, emu.getState()['cpu.a'] & 0xFFFF)
end, emu.callbackType.exec, 0x248C39, 0x248C39)

emu.addEventCallback(function()
  f = f + 1
  if f % flush == 0 then
    local h = io.open(out, 'w')
    h:write(table.concat(log, '\n') .. '\n')
    h:close()
  end
end, emu.eventType.endFrame)

dofile(os.getenv('NEXT'))
