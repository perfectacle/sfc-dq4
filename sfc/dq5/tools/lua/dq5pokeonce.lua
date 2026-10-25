-- 드라이버 앞에 끼워, 세이브스테이트를 불러온 뒤 셋째 프레임 끝에 한 번만 메모리를 쓴다(다음 프레임부터는 게임이 바꾸게 둠).
-- 프로브의 LIBDIR 폴더에 boot.lua 로 두고, 실제 드라이버(seqboot.lua 등)는 NEXT 로 준다.
--   POKEONCE "7E21EA=84;7E2190=80"(CPU 주소=값)   NEXT 다음에 dofile 할 드라이버 절대 경로
-- 예: 엔딩 장면 세이브스테이트에서 7E:21EA 를 84 로 한 번 두면 스태프 롤이 올라가고 3,750프레임쯤 「THE END」 가 뜬다.
local n = 0
local pokes = {}
for a, v in string.gmatch(os.getenv("POKEONCE") or "", "(%x+)=(%x+)") do pokes[#pokes + 1] = { tonumber(a, 16), tonumber(v, 16) } end
emu.addEventCallback(function()
  n = n + 1
  if n == 3 then
    for _, p in ipairs(pokes) do emu.write(p[1], p[2], emu.memType.snesMemory) end
  end
end, emu.eventType.endFrame)
dofile(assert(os.getenv("NEXT"), "NEXT"))
