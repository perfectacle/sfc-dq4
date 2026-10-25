-- DQ5: dq5warp.lua 로 장면을 옮겨 돌리면서, 롬 표의 정한 자리를 읽는 PC 를 모은다(LoROM 뱅크와 그 +80 거울 모두).
--   ROMREAD="23:8000-970B/25/11,16,24;23:AED1-AFFA/9;23:B159-B230"
--            뱅크:시작-끝[/레코드 크기[/레코드 안 오프셋들]]. 오프셋을 빼면 레코드의 모든 자리, 크기를 빼면 범위 전부
-- 결과: SHOT_DIR/romread.txt 한 줄 = "이름(범위 번호와 오프셋) 뱅크:PC n=읽은 횟수 addrs=서로 다른 주소 수". 120프레임마다 다시 쓴다.
-- 나머지 환경 변수는 dq5warp.lua 에 그대로 간다. LIBDIR 의 boot.lua 가 dq5warp.lua 여야 한다.
local out = os.getenv("SHOT_DIR")
local hits = {}

local function add(name, addr)
  local st = emu.getState()
  local key = string.format("%s %02X:%04X", name, st["cpu.k"], st["cpu.pc"])
  local h = hits[key]
  if not h then h = {n = 0, a = {}, c = 0}; hits[key] = h end
  h.n = h.n + 1
  if not h.a[addr] then h.a[addr] = true; h.c = h.c + 1 end
end

local i = 0
for spec in string.gmatch(os.getenv("ROMREAD") or "", "[^;]+") do
  i = i + 1
  local bank, lo, hi, rest = spec:match("^(%x+):(%x+)-(%x+)(.*)$")
  bank, lo, hi = tonumber(bank, 16), tonumber(lo, 16), tonumber(hi, 16)
  local size, offs = rest:match("^/(%d+)/?([%d,]*)$")
  size = tonumber(size)
  local want = nil
  if offs and offs ~= "" then
    want = {}
    for o in string.gmatch(offs, "%d+") do want[tonumber(o)] = true end
  end
  local id = i
  for _, b in ipairs({bank, bank | 0x80}) do
    emu.addMemoryCallback(function(addr)
      if not size then add(string.format("r%d", id), addr); return end
      local r = ((addr & 0xFFFF) - lo) % size
      if not want or want[r] then add(string.format("r%d+%d", id, r), addr) end
    end, emu.callbackType.read, (b << 16) | lo, (b << 16) | hi)
  end
end

local fr = 0
emu.addEventCallback(function()
  fr = fr + 1
  if fr % 120 ~= 0 then return end
  local t = {}
  for key, h in pairs(hits) do t[#t + 1] = string.format("%s n=%d addrs=%d", key, h.n, h.c) end
  table.sort(t)
  local f = assert(io.open(out .. "/romread.txt", "w")); f:write(table.concat(t, "\n") .. "\n"); f:close()
end, emu.eventType.endFrame)
dofile(os.getenv("LIBDIR") .. "/boot.lua")
