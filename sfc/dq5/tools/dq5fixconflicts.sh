#!/usr/bin/env bash
# 열린 dq5 PR 중 CONFLICTING 인 것을 origin/main 과 merge 해서 푼다.
# 자동으로 푸는 것: sfc/dq5/README.md 일지 목록 충돌(같은 번호) → 우리 일지를 main 최대+1 로 다시 매김.
# 그 밖의 충돌은 건드리지 않고 이름만 알린다.
set -u
ROOT=$(git worktree list --porcelain | sed -n "1s/^worktree //p")
TMP="$ROOT-lead-fix"
export GH_TOKEN=${GH_TOKEN:-$(gh auth token)}
cd "$ROOT"
git fetch -q origin
export NEXTFILE=$(mktemp)
# 목록 조회의 mergeable 은 자주 UNKNOWN 이라 PR 마다 따로 묻고, UNKNOWN 이면 몇 번 다시 묻는다.
for n in $(gh pr list --state open --json number,headRefName -q '.[]|select(.headRefName|test("^(feat|fix|docs|chore)/dq5"))|.number'); do
  for i in 1 2 3 4 5; do
    r=$(gh pr view "$n" --json mergeable,headRefName -q '"\(.mergeable) \(.headRefName)"')
    case "$r" in UNKNOWN*) sleep 4;; *) break;; esac
  done
  case "$r" in CONFLICTING*) echo "$n ${r#CONFLICTING }";; esac
done |
while read -r num br <&3; do
  echo "== #$num $br"
  git worktree remove --force "$TMP" 2>/dev/null
  git worktree add -q --detach "$TMP" "origin/$br" || { echo "  worktree 실패"; continue; }
  (
    cd "$TMP"
    git merge --no-commit --no-ff -q origin/main >/dev/null 2>&1
    conf=$(git diff --name-only --diff-filter=U)
    other=$(echo "$conf" | grep -v '^sfc/dq5/README.md$' | grep -v '^$')
    if [ -n "$other" ]; then echo "  손으로 풀 것: $other"; git merge --abort; exit 1; fi
    if [ -n "$conf" ]; then
      python3 - <<'EOF'
import re, subprocess, pathlib
p = pathlib.Path('sfc/dq5/README.md')
t = p.read_text(encoding='utf-8')
main = subprocess.run(['git','ls-tree','--name-only','origin/main','sfc/dq5/journal/'],capture_output=True,text=True).stdout
import collections
maxby = collections.defaultdict(int)
for d_, n_ in re.findall(r'(\d{4}-\d{2}-\d{2})-(\d+)-', main):
    maxby[d_] = max(maxby[d_], int(n_))
import os
NF = os.environ['NEXTFILE']
import json
try: floors = json.loads(open(NF).read() or '{}')
except Exception: floors = {}
def take(d):
    n = max(maxby[d] + 1, floors.get(d, 0))
    floors[d] = n + 1
    return n
ours_files = []
def fix(m):
    ours, theirs = m.group(1), m.group(2)
    out = []
    for line in ours.splitlines(True):
        mm = re.search(r'\[(\d{4}-\d{2}-\d{2})-(\d+): (.*?)\]\(journal/\1-\2-([a-z0-9-]+)\.md\)', line)
        # 같은 번호뿐 아니라 main 최대 번호 이하이면 다시 매긴다(빈 번호에 끼면 목록 순서가 깨짐).
        if mm and int(mm.group(2)) <= maxby[mm.group(1)]:
            d, n, title, slug = mm.groups()
            nn = take(d)
            nn = f'{nn:02d}'
            ours_files.append((f'{d}-{n}-{slug}.md', f'{d}-{nn}-{slug}.md', f'{d}-{n}', f'{d}-{nn}'))
            line = line.replace(f'{d}-{n}', f'{d}-{nn}')
        out.append(line)
    return theirs + ''.join(out)
t = re.sub(r'<<<<<<< HEAD\n(.*?)=======\n(.*?)>>>>>>> origin/main\n', fix, t, flags=re.S)
p.write_text(t, encoding='utf-8')
open(NF,'w').write(json.dumps(floors))
for old, new, ot, nt in ours_files:
    subprocess.run(['git','mv',f'sfc/dq5/journal/{old}',f'sfc/dq5/journal/{new}'],check=True)
    j = pathlib.Path(f'sfc/dq5/journal/{new}')
    s = j.read_text(encoding='utf-8')
    j.write_text(s.replace(f'# {ot}:', f'# {nt}:', 1), encoding='utf-8')
    for f in subprocess.run(['git','grep','-l',old],capture_output=True,text=True).stdout.split():
        q = pathlib.Path(f); q.write_text(q.read_text(encoding='utf-8').replace(old,new).replace(f'일지 {ot}]', f'일지 {nt}]'), encoding='utf-8')
    print(f'  일지 {ot} -> {nt}')
EOF
    fi
    if git grep -nqE '^(<<<<<<<|=======|>>>>>>>)( |$)'; then echo "  충돌 표시 남음"; git merge --abort; exit 1; fi
    out=$(uv run --locked python tools/check_docs.py 2>/dev/null | tail -1)
    [ "$out" = "0 errors" ] || { echo "  check_docs: $out"; uv run --locked python tools/check_docs.py | head -5; git merge --abort; exit 1; }
    git add -A sfc
    git commit -q -m "Merge origin/main into $br: 충돌 정리

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
    # 고치는 사이 머지돼 브랜치가 지워졌으면 push 가 브랜치를 되살리므로 그 전에 다시 본다.
    [ "$(gh pr view "$num" --json state -q .state)" = "OPEN" ] || { echo "  이미 닫힘, push 안 함"; exit 0; }
    git -c credential.helper= -c "credential.helper=!f(){ echo username=x-access-token; echo password=\$GH_TOKEN; };f" push -q origin "HEAD:refs/heads/$br" && echo "  push 완료"
    gh pr merge --auto --merge "$num" >/dev/null 2>&1
  )
  cd "$ROOT"; git worktree remove --force "$TMP" 2>/dev/null
done 3<&0
