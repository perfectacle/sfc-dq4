-- 전원부터 INPUT 순서대로 버튼을 눌러 진행하며 소리 대기열 명령(24:FF83 에 들어오는 명령·인자·X·돌아갈 자리)을
-- OUT/cmds.txt 에, 300프레임마다 화면을 OUT/fNNNNN.png 에 남기고 MAXF 에서 멈춘다. 세이브스테이트를 쓰지 않는다.
-- INPUT="a@300:4,a@600:4,y@2000:4" 처럼 버튼@프레임:길이. AFTER=n 이면 그 뒤로 A 를 n 프레임마다 누른다.
local out = os.getenv('OUT'); local maxf = tonumber(os.getenv('MAXF') or '6000')
local after = tonumber(os.getenv('AFTER') or '0'); local afterFrom = tonumber(os.getenv('AFTERFROM') or '0')
local f = assert(io.open(out .. '/cmds.txt', 'w'))
local m = emu.memType.snesMemory
local presses = {}
for b, fr, len in string.gmatch(os.getenv('INPUT') or '', '(%a+)@(%d+):(%d+)') do
  presses[#presses + 1] = {b, tonumber(fr), tonumber(len)}
end
local n = 0
emu.addEventCallback(function()
  local inp = {}
  for _, p in ipairs(presses) do
    if n >= p[2] and n < p[2] + p[3] then inp[p[1]] = true end
  end
  if after > 0 and n >= afterFrom and (n - afterFrom) % after < 3 then inp.a = true end
  emu.setInput(inp, 0)
end, emu.eventType.inputPolled)
emu.addEventCallback(function()
  n = n + 1
  if n % 300 == 0 then
    local png = emu.takeScreenshot()
    local h = io.open(string.format('%s/f%05d.png', out, n), 'wb'); h:write(png); h:close()
  end
  if n >= maxf then f:close(); emu.stop() end
end, emu.eventType.endFrame)
emu.addMemoryCallback(function()
  local s = emu.getState(); local sp = s['cpu.sp']
  local arg = emu.read(sp + 1, m)
  local r = emu.read(sp + 3, m) | emu.read(sp + 4, m) << 8 | emu.read(sp + 5, m) << 16
  local x = s['cpu.x'] & 0xFF
  f:write(string.format('%d cmd=%02X arg=%02X x=%02X ret=%06X\n', n, s['cpu.a'] & 0xFF, arg, x, r)); f:flush()
end, emu.callbackType.exec, 0x24FF83, 0x24FF83)
