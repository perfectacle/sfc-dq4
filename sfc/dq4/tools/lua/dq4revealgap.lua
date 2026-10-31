-- 1장 첫머리의 검은 틈 재기: 프레임마다 마지막 $2100 쓰기, 지금 곡 $1D8B, 맵 곡 $194B, 맵 곡 요청(23:FE8F 실행 = req),
-- SPC KON 쓰기 수를 SHOT_DIR/gap.txt 에 쓴다. 입력은 $LIBDIR/boot.lua(전원부터 A 연타, 서장 길은 walk.lua 를 boot.lua 로)
local out = io.open((os.getenv('SHOT_DIR') or '.') .. '/gap.txt', 'w')
local m = emu.memType.snesMemory
local f, inidisp, req, kon, dspa = 0, -1, 0, 0, 0
emu.addMemoryCallback(function(a, v) inidisp = v end, emu.callbackType.write, 0x2100, 0x2100)
emu.addMemoryCallback(function() req = req + 1 end, emu.callbackType.exec, 0x23FE8F, 0x23FE8F)
emu.addMemoryCallback(function(a, v) dspa = v end, emu.callbackType.write, 0xF2, 0xF2, emu.cpuType.spc, emu.memType.spcMemory)
emu.addMemoryCallback(function(a, v) if dspa == 0x4C and v ~= 0 then kon = kon + 1 end end,
  emu.callbackType.write, 0xF3, 0xF3, emu.cpuType.spc, emu.memType.spcMemory)
emu.addEventCallback(function()
  f = f + 1
  out:write(string.format('%d 2100=%02X 1D8B=%02X 194B=%02X req=%d kon=%d\n', f, inidisp & 0xFF,
    emu.read(0x7E1D8B, m), emu.read(0x7E194B, m), req, kon)); out:flush()
  req, kon = 0, 0
end, emu.eventType.endFrame)
dofile(os.getenv('LIBDIR') .. '/boot.lua')
