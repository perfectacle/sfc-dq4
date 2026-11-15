-- 리눅스는 환경 변수 한 줄(이름=값)을 128KiB 까지만 새 프로세스에 넘긴다(MAX_ARG_STRLEN). dq4mesen.py 가 그보다 긴 값을
-- 「이름__FILE」 이 가리키는 파일로 옮기고 그 이름들을 BIGENV 에 적는다. 그 이름의 os.getenv 는 파일 내용을 돌려주고,
-- 나머지는 그대로 둔 채 BIGENV_TARGET 스크립트를 이어 돈다.
local getenv = os.getenv
local values = {}
for name in string.gmatch(getenv("BIGENV") or "", "[^,]+") do
  local f = assert(io.open(getenv(name .. "__FILE"), "rb"))
  values[name] = f:read("a")
  f:close()
end
os.getenv = function(name)
  local v = values[name]
  if v ~= nil then return v end
  return getenv(name)
end
dofile(getenv("BIGENV_TARGET"))
