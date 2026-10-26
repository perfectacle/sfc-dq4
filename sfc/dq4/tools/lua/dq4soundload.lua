-- 곡이 울리는 동안 샘플이 SPC 에 도착하는 프레임과 목소리마다 소리가 나기 시작하는 프레임을 load.txt 에 적는다.
-- SAMPLES=36,37,… (16진) 의 SPC 칸 색인 03FF+n 이 바뀔 때 「프레임 sample=n slot=칸」을(받는 중, 곧 $0184 = n 이면
-- 드라이버 instrument(182E)처럼 없는 것 FF 로 본다),
-- 목소리의 ENVX 가 0 에서 0 보다 커질 때 「프레임 on v=목소리 srcn=칸」을, 곡 자리(03AF~03B6)에 SONGS(16진, 쉼표)의
-- 곡이 오르내릴 때 「프레임 song=n on/off」를 적는다. MAXF-1 프레임에 SHOT_DIR/load.txt 로 쓴다.
-- dq4soundstate.lua 의 SOUND_PROBE 로 걸고, 이어서 돌릴 프로브를 NEXT_PROBE(예: sfc/dq5/tools/lua/dq5sndlog.lua)로 준다.
local spc, dsp = emu.memType.spcRam, emu.memType.spcDspRegisters
local samples = {}
for a in string.gmatch(os.getenv('SAMPLES') or '', '[^,]+') do samples[#samples + 1] = tonumber(a, 16) end
local songs = {}
for a in string.gmatch(os.getenv('SONGS') or '', '[^,]+') do songs[#songs + 1] = tonumber(a, 16) end
local maxf = tonumber(os.getenv('MAXF') or '0')
local n, log, slots, env, playing = 0, {}, {}, {}, {}
emu.addEventCallback(function()
  n = n + 1
  for _, s in ipairs(samples) do
    local v = emu.read(0x03FF + s, spc)
    if emu.read(0x0184, spc) == s then v = 0xFF end
    if slots[s] ~= v then
      if slots[s] ~= nil then log[#log + 1] = string.format('%d sample=%02X slot=%02X', n, s, v) end
      slots[s] = v
    end
  end
  for _, song in ipairs(songs) do
    local now = false
    for i = 0, 7 do
      if emu.read(0x03B7 + i, spc) ~= 0 and emu.read(0x03AF + i, spc) == song then now = true end
    end
    if now ~= (playing[song] or false) then
      log[#log + 1] = string.format('%d song=%02X %s', n, song, now and 'on' or 'off')
      playing[song] = now
    end
  end
  for v = 0, 7 do
    local e = emu.read(v * 16 + 8, dsp)
    if e > 0 and (env[v] or 0) == 0 then
      log[#log + 1] = string.format('%d on v=%d srcn=%02X', n, v, emu.read(v * 16 + 4, dsp))
    end
    env[v] = e
  end
  if n == maxf - 1 then
    local fh = io.open(os.getenv('SHOT_DIR') .. '/load.txt', 'w')
    fh:write(table.concat(log, '\n') .. '\n')
    fh:close()
  end
end, emu.eventType.endFrame)
dofile(os.getenv('NEXT_PROBE'))
