-- 화면에 보이는 BG3(창 층)이 바뀔 때마다 타일맵과 BG3 글자 칸 그림을 WINWATCH_OUT 에 적고 WINWATCH_TARGET 스크립트를
-- 이어 돈다. dq4mesen.py 가 모든 MesenCE 실행 앞에 붙이고, 판정은 dq4winwatch.py 가 한다. 형식은
-- sfc/dq4/docs/dq4-window-text-format.md 「창 테두리 검사」.
--
-- 프레임 끝마다 PPU 상태(emu.getState)의 BG3 타일맵 자리·글자 자리·스크롤로 타일맵 32 × 32 낱말을 읽는다. 화면이 꺼졌거나
-- (강제 블랭크·밝기 0) 주 화면에 BG3 이 없으면 적지 않는다. 타일맵, 테두리 칸(080~095)·이름 칸(180~1FF) 그림, 스크롤의
-- 지문이 처음 보는 것이면 그 모습(S)을, 앞 프레임과 다른 모습이면 바뀐 프레임(E)을 적는다. 메시지 캔버스(096~17F)만
-- 바뀌는 글자 찍기와 200~3FF(필드에서는 BG1·BG2 그림이라 물결마다 바뀜)는 새 모습으로 치지 않는다.
-- 모습은 앞서 적은 모습과 달라진 타일맵 낱말과, 이 타일맵이 가리키는 칸(과 테두리 칸 08B~095) 가운데 앞서 적은 그림과
-- 달라진 칸의 그림만 적는다.
--
-- emu.stop 뒤에도 프레임이 몇 개 더 도는데 그 수가 실행마다 달라, 그 뒤로는 적지 않는다(dq4readset.lua 와 같은 까닭).
local path, target = os.getenv("WINWATCH_OUT"), os.getenv("WINWATCH_TARGET")
local VRAM = emu.memType.snesVideoRam
local out = path and io.open(path, "wb")
local stopped = false
local stopOrig = emu.stop
emu.stop = function(...)
  stopped = true
  return stopOrig(...)
end
if out then
  local n, last, ids, nid = 0, nil, {}, 0
  local map, art = {}, {}
  emu.addEventCallback(function()
    n = n + 1
    if stopped then return end
    local s = emu.getState()
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
      out:write(string.pack("<c1I4I4I2I2I2I2I2I2", "S", id, n, base // 2, chr // 2, hs, vs, #cells, #tiles),
                table.concat(cells), table.concat(tiles))
    end
    if id ~= last then
      out:write(string.pack("<c1I4i4", "E", n, id))
      out:flush()
      last = id
    end
  end, emu.eventType.endFrame)
end
dofile(target)
