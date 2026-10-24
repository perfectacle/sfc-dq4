-- 전원을 켜기 전에 배터리 RAM(SRAM 8KB)을 정해진 값으로 채우고 다른 Lua 를 돌린다.
-- MesenCE 테스트러너는 롬 파일 이름으로 설정 폴더의 Saves/<롬 이름>.sav 를 불러오고 끝날 때 그 파일에
-- 다시 쓴다. 다른 실험이 남긴 모험의 서가 있으면 타이틀에서 같은 입력이 다른 장면으로 가므로,
-- 전원을 켜서 시작하는 실험은 이 스크립트로 SRAM 을 고정한다(세이브스테이트를 불러오면 SRAM 도
-- 세이브스테이트 것으로 바뀌므로 그때는 필요 없음).
-- 환경 변수:
--   SRAM=path        SRAM 에 채울 파일(8192바이트). 없으면 모두 00(.sav 가 없을 때와 같음)
--   SRAM_DRIVER=path 이어서 돌릴 Lua(예: $LIBDIR/mkstate.lua). 없으면 입력 드라이버(DRIVER, 기본 boot.lua)
package.path = os.getenv("LIBDIR") .. "/?.lua;" .. package.path
local L = require("lib")
local mt = emu.memType.nesSaveRam
local size = emu.getMemorySize(mt)
local src = os.getenv("SRAM")
local data = src and src ~= "" and L.readFile(src) or nil
-- 스크립트를 읽는 시점은 첫 프레임 전이라, 리셋 루틴이 SRAM 을 읽기 전에 덮인다
for a = 0, size - 1 do
  emu.write(a, data and data:byte(a + 1) or 0, mt)
end
if os.getenv("SRAM_DRIVER") then dofile(os.getenv("SRAM_DRIVER")) else L.drive() end
