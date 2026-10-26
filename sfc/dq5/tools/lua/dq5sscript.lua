-- DQ5 SPC 스크립트 연산 실측. SSAT 프레임에 SPC RAM SSADDR(기본 0843 = 스크립트 00 자리)에 SSCRIPT(16진 바이트)를 써 두고,
-- SSFROM 프레임부터 프레임마다 DSP 레지스터와 드라이버 변수를 sscript.txt 로(MAXF-2 프레임에 씀). 스크립트는 dq5sndlog.lua 의
-- HFROM_CMD·HCMD·HX 로 05 s n 처럼 그 번호를 부르게 해서 돌린다. 이 파일은 같은 폴더의 dq5sndlog.lua 를 이어 부른다.
-- SSROMPATCH(파일 오프셋=바이트, 세미콜론으로 여럿)는 첫 프레임에 롬을 덮는다. seqboot.lua 처럼 ROMPATCH 를 받지 않는 드라이버와 쓸 때.
-- 줄: 프레임 DSP(mvol evol flg efb edl eon non pmon fir v0~v7 왼,오) 변수(03A7 03C7 03CF 03D7 03E7 각 8, 03EF 03F0 03F1 03F8 03F9 A9~B0) kon=그 프레임에 쓴 KON 들
local spc, dsp = emu.memType.spcRam, emu.memType.spcDspRegisters
local at, from = tonumber(os.getenv("SSAT") or "550"), tonumber(os.getenv("SSFROM") or "540")
local addr = tonumber(os.getenv("SSADDR") or "0843", 16)
local out, fr, reg, kon = {}, 0, 0, {}
local function hx(a, n, mt)
  local t = {}
  for i = 0, n - 1 do t[#t + 1] = string.format("%02X", emu.read(a + i, mt)) end
  return table.concat(t, "")
end
emu.addMemoryCallback(function(_, v) reg = v end, emu.callbackType.write, 0xF2, 0xF2, emu.cpuType.spc, emu.memType.spcMemory)
emu.addMemoryCallback(function(_, v)
  if (reg & 0x7F) == 0x4C and v ~= 0 then kon[#kon + 1] = string.format("%02X", v) end
end, emu.callbackType.write, 0xF3, 0xF3, emu.cpuType.spc, emu.memType.spcMemory)
emu.addEventCallback(function()
  fr = fr + 1
  if fr == 1 and os.getenv("SSROMPATCH") then
    for off, h in string.gmatch(os.getenv("SSROMPATCH"), "(%x+)=(%x+)") do
      for i = 0, #h // 2 - 1 do emu.write(tonumber(off, 16) + i, tonumber(h:sub(i * 2 + 1, i * 2 + 2), 16), emu.memType.snesPrgRom) end
    end
  end
  if fr == at then
    local i = 0
    for b in string.gmatch(os.getenv("SSCRIPT") or "FF", "%x%x") do emu.write(addr + i, tonumber(b, 16), spc); i = i + 1 end
  end
  if fr >= from then
    local v = {}
    local fir = {}
    for c = 0, 7 do v[#v + 1] = hx(c * 16, 2, dsp); fir[#fir + 1] = hx(c * 16 + 15, 1, dsp) end
    out[#out + 1] = string.format("%d mvol=%s,%s evol=%s,%s flg=%s efb=%s edl=%s eon=%s non=%s pmon=%s fir=%s v=%s a7=%s c7=%s cf=%s d7=%s e7=%s ef=%s a9=%s kon=%s",
      fr, hx(0x0C, 1, dsp), hx(0x1C, 1, dsp), hx(0x2C, 1, dsp), hx(0x3C, 1, dsp), hx(0x6C, 1, dsp), hx(0x0D, 1, dsp), hx(0x7D, 1, dsp),
      hx(0x4D, 1, dsp), hx(0x3D, 1, dsp), hx(0x2D, 1, dsp), table.concat(fir, ""), table.concat(v, ","),
      hx(0x3A7, 8, spc), hx(0x3C7, 8, spc), hx(0x3CF, 8, spc), hx(0x3D7, 8, spc), hx(0x3E7, 8, spc), hx(0x3EF, 3, spc) .. hx(0x3F8, 2, spc),
      hx(0xA9, 8, spc), table.concat(kon, ","))
  end
  kon = {}
  if fr == tonumber(os.getenv("MAXF")) - 2 then
    local f = io.open(os.getenv("SHOT_DIR") .. "/sscript.txt", "w"); f:write(table.concat(out, "\n") .. "\n"); f:close()
  end
end, emu.eventType.endFrame)
local here = debug.getinfo(1, "S").source:match("^@(.*/)") or "./"
dofile(here .. "dq5sndlog.lua")
