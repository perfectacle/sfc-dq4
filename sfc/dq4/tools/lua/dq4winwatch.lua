-- 화면에 보이는 BG3(창 층)이 바뀔 때마다 타일맵과 BG3 글자 칸 그림을 WINWATCH_OUT 에 적고 WINWATCH_TARGET 스크립트를
-- 이어 돈다. dq4mesen.py 가 모든 MesenCE 실행 앞에 붙이고, 판정은 dq4winwatch.py 가 한다. 형식은
-- sfc/dq4/docs/dq4-window-text-format.md 「UI 깨짐 검사」.
--
-- 프레임 끝마다 PPU 상태(emu.getState)의 BG3 타일맵 자리·글자 자리·스크롤로 타일맵 32 × 32 낱말을 읽는다. 화면이 꺼졌거나
-- (강제 블랭크·밝기 0) 주 화면에 BG3 이 없으면 적지 않는다. 타일맵, 테두리 칸(080~095)·이름 칸(180~1FF) 그림, 스크롤의
-- 지문이 처음 보는 것이면 그 모습(S)을, 앞 프레임과 다른 모습이면 바뀐 프레임(E)을 적는다. 메시지 캔버스(096~17F)만
-- 바뀌는 글자 찍기와 200~3FF(필드에서는 BG1·BG2 그림이라 물결마다 바뀜)는 새 모습으로 치지 않는다. 다만 캔버스가
-- CANVAS_QUIET 프레임 그대로 멈추면(메시지를 다 찍음) 캔버스 지문을 섞은 모습으로 한 번 더 적는다. 그러지 않으면 창을 연
-- 순간(글자를 찍기 전)의 빈 캔버스만 남아 판정이 메시지 글자를 보지 못한다.
-- 모습은 앞서 적은 모습과 달라진 타일맵 낱말과, 이 타일맵이 가리키는 칸(과 테두리 칸 08B~095) 가운데 앞서 적은 그림과
-- 달라진 칸의 그림만 적는다. 같은 때의 OAM(544바이트)·CGRAM(512바이트)도 앞 모습과 달라진 낱말만 적는다(스프라이트·색
-- 규칙용). 파일 첫머리는 판 기록 V(지금 5).
--
-- 엔진이 창 하나의 틀을 버퍼에 그릴 때(04:A56C, 창 틀 그리기가 $0A46 높이를 읽는 첫 명령)마다 D 기록(프레임, 그리는 창의
-- 번호, x·y·너비·높이 $0A43~$0A46)을 적는다. 번호는 창 쌓기 $0A00~ 의 지금 깊이 $0AD6 자리($09FF + $0AD6, 04:A45B 다시
-- 그리기와 같은 읽기)다. $0A00 은 다시 그리는 동안에도 맨 위 창 번호라, 아래 창을 다시 그릴 때 그 번호가 붙는다. 창을 닫으면 엔진이 남은 창을 아래부터 다시 그리므로 판정이 그 차례로 겹친 순서를 안다.
--
-- 화면이 켜져 있으면(강제 블랭크·밝기 0 이 아님) BG3 과 상관없이 프레임마다 스프라이트·장면 표지도 적는다(판 4):
--   O  OAM 이 바뀐 프레임과 바뀐 낱말, 이어서 P: 그 프레임의 WINWATCH_OWRAM 조각 가운데 달라진 바이트(인물 표 등)
--   B  OBJ 설정(이름 자리·둘째 표 거리·크기 꼴), 밝기·강제 블랭크, BG 모드·BG3 우선, 주·부 화면 층이 바뀐 프레임
--   M  맵 번호($BC/$BD)·세계($1949)·전투 여부(NMI 작업 $1944 = 8952)·시각($075E)·일행 수($1967)가 바뀐 프레임
--   F  스캔라인 OBJ 넘침 플래그(STAT77 bit6 rangeOver·bit7 timeOver, 그 프레임 끝의 PPU 상태)가 바뀐 프레임
--   J  M 뒤 OBJ_SETTLE 프레임과, M 뒤 엔진이 창을 처음 그린 다음 프레임에 OBJ VRAM 두 이름 표(16KB)를 32바이트 덩이로
--      앞서 적은 것과 달라진 덩이만, 이어서 CGRAM 512바이트 전부
--   R  파일 첫머리(V 뒤)에 한 번, WRAM 조각 목록 글(WINWATCH_WRAM = "주소:길이,…", 7E 뱅크 16진 주소·10진 길이)
--   W  S 바로 뒤에, 그 조각을 이은 바이트 가운데 앞서 적은 것과 달라진 것(이은 자리 번호, 값)
--
-- emu.stop 뒤에도 프레임이 몇 개 더 도는데 그 수가 실행마다 달라, 그 뒤로는 적지 않는다(dq4readset.lua 와 같은 까닭).
local path, target = os.getenv("WINWATCH_OUT"), os.getenv("WINWATCH_TARGET")
local VRAM, OAM, CGRAM = emu.memType.snesVideoRam, emu.memType.snesSpriteRam, emu.memType.snesCgRam
local out = path and io.open(path, "wb")
local stopped = false
local stopOrig = emu.stop
emu.stop = function(...)
  stopped = true
  return stopOrig(...)
end
if out then
  out:write(string.pack("<c1I2", "V", 5))
  local n, last, ids, nid = 0, nil, {}, 0
  -- 글자 찍기 사이 멈춤(한 글자마다 1~2프레임)보다 길게
  local CANVAS_QUIET = 8
  local canvas, quiet = nil, 0
  local map, art, oam, cg = {}, {}, {}, {}
  local CPU = emu.memType.snesMemory
  local drew = false
  emu.addMemoryCallback(function()
    if stopped then return end
    drew = true
    out:write(string.pack("<c1I4BBBBB", "D", n, emu.read(0x7E09FF + emu.read(0x7E0AD6, CPU), CPU), emu.read(0x7E0A43, CPU), emu.read(0x7E0A44, CPU),
                          emu.read(0x7E0A45, CPU), emu.read(0x7E0A46, CPU)))
  end, emu.callbackType.exec, 0x04A56C, 0x04A56C)
  local function delta(store, memtype, words)
    local t = {}
    for i = 0, words - 1 do
      local w = emu.read16(2 * i, memtype)
      if store[i] ~= w then
        store[i] = w
        t[#t + 1] = string.pack("<I2I2", i, w)
      end
    end
    return t
  end
  local OBJ_SETTLE = 30
  local wram, wstore, spec = {}, {}, os.getenv("WINWATCH_WRAM") or ""
  for a, len in string.gmatch(spec, "(%x+):(%d+)") do
    for k = 0, tonumber(len) - 1 do wram[#wram + 1] = 0x7E0000 + tonumber(a, 16) + k end
  end
  out:write(string.pack("<c1s2", "R", spec))
  local owram, ostorew, ospec = {}, {}, os.getenv("WINWATCH_OWRAM") or ""
  for a, len in string.gmatch(ospec, "(%x+):(%d+)") do
    for k = 0, tonumber(len) - 1 do owram[#owram + 1] = 0x7E0000 + tonumber(a, 16) + k end
  end
  out:write(string.pack("<c1s2", "Q", ospec))
  local ostore, bkey, mkey, jat, jstore, jwin, fkey = {}, nil, nil, nil, {}, false, nil
  local function scene(s)
    local on = not s["ppu.forcedBlank"] and (s["ppu.screenBrightness"] or 0) > 0
    local b = {s["ppu.oamBaseAddress"] or 0, s["ppu.oamAddressOffset"] or 0, s["ppu.oamMode"] or 0,
               s["ppu.screenBrightness"] or 0, s["ppu.forcedBlank"] and 1 or 0, s["ppu.bgMode"] or 0,
               s["ppu.mode1Bg3Priority"] and 1 or 0, s["ppu.mainScreenLayers"] or 0, s["ppu.subScreenLayers"] or 0}
    local k = table.concat(b, "/")
    if k ~= bkey then
      bkey = k
      out:write(string.pack("<c1I4I2I2BBBBBBB", "B", n, table.unpack(b)))
    end
    local m = {emu.read(0x7E00BC, CPU), emu.read(0x7E00BD, CPU), emu.read(0x7E1949, CPU),
               emu.read16(0x7E1944, CPU) == 0x8952 and 1 or 0, emu.read(0x7E075E, CPU), emu.read(0x7E1967, CPU)}
    local mk = table.concat(m, "/")
    if mk ~= mkey then
      if mkey == nil or mk:match("^[^/]*/[^/]*/[^/]*/[^/]*") ~= mkey:match("^[^/]*/[^/]*/[^/]*/[^/]*") then
        jat, jwin = n + OBJ_SETTLE, false
      end
      mkey = mk
      out:write(string.pack("<c1I4BBBBBB", "M", n, table.unpack(m)))
    end
    if drew and not jwin then
      jwin = true
      jat = math.min(jat or (n + 1), n + 1)
    end
    drew = false
    local f = (s["ppu.rangeOver"] and 1 or 0) | (s["ppu.timeOver"] and 2 or 0)
    if f ~= fkey then
      fkey = f
      out:write(string.pack("<c1I4B", "F", n, f))
    end
    if not on then return end
    local t = delta(ostore, OAM, 272)
    if #t > 0 then
      out:write(string.pack("<c1I4I2", "O", n, #t), table.concat(t))
      local bytes = {}
      for i, a in ipairs(owram) do
        local v = emu.read(a, CPU)
        if ostorew[i] ~= v then
          ostorew[i] = v
          bytes[#bytes + 1] = string.pack("<I2B", i - 1, v)
        end
      end
      out:write(string.pack("<c1I2", "P", #bytes), table.concat(bytes))
    end
    if jat and n >= jat then
      jat = nil
      local base, off = (s["ppu.oamBaseAddress"] or 0) * 2, (s["ppu.oamAddressOffset"] or 0) * 2
      local blocks = {}
      for half = 0, 1 do
        -- 둘째 이름 표는 첫째에서 oamAddressOffset 낱말 뒤(SNES OBSEL 의 (N + 1) × 4K 낱말)
        local start = (base + half * off) & 0xFFFF
        for b = 0, 0xFF do
          local px = {}
          for k = 0, 15 do px[k + 1] = string.pack("<I2", emu.read16((start + b * 32 + 2 * k) & 0xFFFF, VRAM)) end
          px = table.concat(px)
          local key = half * 256 + b
          if jstore[key] ~= px then
            jstore[key] = px
            blocks[#blocks + 1] = string.pack("<I2", key) .. px
          end
        end
      end
      local colors = {}
      for i = 0, 255 do colors[#colors + 1] = string.pack("<I2", emu.read16(2 * i, CGRAM)) end
      out:write(string.pack("<c1I4I2I2I2", "J", n, base // 2, off // 2, #blocks), table.concat(blocks), table.concat(colors))
    end
  end
  emu.addEventCallback(function()
    n = n + 1
    if stopped then return end
    local s = emu.getState()
    scene(s)
    if s["ppu.forcedBlank"] or (s["ppu.screenBrightness"] or 0) == 0 or ((s["ppu.mainScreenLayers"] or 0) & 4) == 0 then
      if last ~= -1 then
        out:write(string.pack("<c1I4i4", "E", n, -1))
        out:flush()
        last = -1
      end
      return
    end
    local base = (s["ppu.layers[2].tilemapAddress"] or 0) * 2
    local chr = (s["ppu.layers[2].chrAddress"] or 0) * 2
    local hs, vs = s["ppu.layers[2].hscroll"] or 0, s["ppu.layers[2].vscroll"] or 0
    local h = base * 65599 + chr * 31 + hs * 7 + vs
    for a = base, base + 0x7FE, 2 do h = h * 31 + emu.read16(a, VRAM) end
    for a = chr + 0x800, chr + 0x95E, 2 do h = h * 31 + emu.read16(a, VRAM) end
    for a = chr + 0x1800, chr + 0x1FFE, 2 do h = h * 31 + emu.read16(a, VRAM) end
    local c = 0
    for a = chr + 0x960, chr + 0x17FE, 2 do c = c * 31 + emu.read16(a, VRAM) end
    if c ~= canvas then
      canvas, quiet = c, 0
    else
      quiet = quiet + 1
    end
    if quiet >= CANVAS_QUIET then h = h * 131 + c end
    local id = ids[h]
    if not id then
      nid = nid + 1
      id = nid
      ids[h] = id
      local cells, used = {}, {}
      for t = 0x8B, 0x95 do used[t] = true end
      for i = 0, 1023 do
        local w = emu.read16(base + 2 * i, VRAM)
        used[w & 0x3FF] = true
        if map[i] ~= w then
          map[i] = w
          cells[#cells + 1] = string.pack("<I2I2", i, w)
        end
      end
      local tiles = {}
      for t = 0, 0x3FF do
        if used[t] then
          local o, px = chr + t * 16, {}
          for k = 0, 7 do px[k + 1] = string.pack("<I2", emu.read16(o + 2 * k, VRAM)) end
          px = table.concat(px)
          if art[t] ~= px then
            art[t] = px
            tiles[#tiles + 1] = string.pack("<I2", t) .. px
          end
        end
      end
      local sprites, colors = delta(oam, OAM, 272), delta(cg, CGRAM, 256)
      out:write(string.pack("<c1I4I4I2I2I2I2I2I2I2I2", "S", id, n, base // 2, chr // 2, hs, vs, #cells, #tiles,
                            #sprites, #colors),
                table.concat(cells), table.concat(tiles), table.concat(sprites), table.concat(colors))
      local bytes = {}
      for i, a in ipairs(wram) do
        local v = emu.read(a, CPU)
        if wstore[i] ~= v then
          wstore[i] = v
          bytes[#bytes + 1] = string.pack("<I2B", i - 1, v)
        end
      end
      out:write(string.pack("<c1I2", "W", #bytes), table.concat(bytes))
    end
    if id ~= last then
      out:write(string.pack("<c1I4i4", "E", n, id))
      out:flush()
      last = id
    end
  end, emu.eventType.endFrame)
end
dofile(target)
