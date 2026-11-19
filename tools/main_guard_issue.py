"""main push 의 가드(release 등급 전부 + 바뀐 파일로 걸린 것)가 실패했을 때 가드마다 GitHub issue 를 열거나 덧붙인다.

ci.yml 의 main-guard-issues 잡이 부른다. 입력은 guard-shard-pr-* 아티팩트(조각마다 shard-K.json 의 rows 와 logs/<가드>.log).
같은 가드의 issue 는 하나다: 제목 `[main 가드] <이름> 실패` 인 열린 issue 가 있으면 댓글로 덧붙인다. 연속 머지로 앞 실행이
취소되면(ci.yml 의 concurrency) 그 커밋이 검증되지 않으므로, 마지막으로 통과한 main 실행 뒤로 머지된 PR 전부와 취소된 실행의
커밋을 적어 어느 머지가 깼는지 좁힌다.

  python tools/main_guard_issue.py --reports work/ci-report --sha SHA --repo OWNER/REPO --run-url URL [--dry-run]
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

TITLE = '[main 가드] {name} 실패'
LOG_TAIL = 30
NO_VERDICT = 'pr-guards'
MERGE = re.compile(r'^Merge pull request #(\d+) ')


def failures(reports):
    """{가드 이름: {'details': [실패 줄…], 'log': 로그 끝}}. reports 아래 shard-*.json 의 failed 행."""
    out = {}
    for f in sorted(Path(reports).rglob('shard-*.json')):
        try:
            rows = json.loads(f.read_text(encoding='utf-8')).get('rows', [])
        except (OSError, ValueError):
            continue
        for r in rows:
            if not isinstance(r, dict) or r.get('status') != 'failed' or not r.get('name'):
                continue
            item = out.setdefault(r['name'], {'details': [], 'log': ''})
            item['details'].append(str(r.get('detail', '')).strip())
            log = f.parent / 'logs' / f'{r["name"]}.log'
            if log.is_file() and not item['log']:
                item['log'] = '\n'.join(log.read_text(encoding='utf-8', errors='replace').splitlines()[-LOG_TAIL:])
    return out


def range_from_runs(runs, sha):
    """runs: 최신순 [{headSha, conclusion}]. (마지막으로 통과한 커밋 또는 None, 그 뒤 sha 앞까지 취소된 실행의 커밋들)."""
    cancelled, seen = [], False
    for r in runs:
        if r.get('headSha') == sha:
            seen = True
            continue
        if not seen:
            continue
        if r.get('conclusion') == 'success':
            return r['headSha'], cancelled
        if r.get('conclusion') == 'cancelled' and r['headSha'] not in cancelled:
            cancelled.append(r['headSha'])
    return None, cancelled


def merged_prs(log_lines):
    """git log --merges --format=%s 줄들에서 PR 번호."""
    return [int(m[1]) for line in log_lines if (m := MERGE.match(line))]


def body(name, info, sha, green, cancelled, prs, run_url):
    lines = [f'main 커밋 `{sha[:8]}` 의 가드 `{name}` 이 실패했다. 실행: {run_url}', '']
    if green:
        lines.append(f'마지막으로 통과한 main 실행: `{green[:8]}`. 그 뒤로 머지된 PR: '
                     + (', '.join(f'#{n}' for n in prs) if prs else '없음(범위를 git 으로 못 읽음)') + '.')
    else:
        lines.append('마지막으로 통과한 main 실행을 찾지 못했다.')
    if cancelled:
        lines.append('연속 머지로 취소되어 검증되지 않은 커밋: ' + ', '.join(f'`{c[:8]}`' for c in cancelled) + '.')
    shown = [d for d in info['details'] if d] or ['(상세 없음)']
    lines += ['', '실패 줄:', '```', *shown, '```']
    if info['log']:
        lines += ['로그 끝:', '```', info['log'], '```']
    return '\n'.join(lines) + '\n'


def run(gh, git, reports, sha, run_url, dry=False):
    """(가드 잡이 실패했을 때만 부른다) 실패 가드마다 issue 를 열거나 덧붙이고 [(이름, 'created'|'commented', 번호 또는 None)]을 돌려준다."""
    found = failures(reports) or {NO_VERDICT: {'details': ['실패한 가드 행이 없다: 빌드·조각 단계가 가드 결과를 남기기 전에 실패했다'],
                                               'log': ''}}
    runs = json.loads(gh(['run', 'list', '--workflow', 'ci.yml', '--branch', 'main', '--event', 'push', '--limit', '60',
                          '--json', 'headSha,conclusion']) or '[]')
    green, cancelled = range_from_runs(runs, sha)
    prs = []
    if green:
        try:
            prs = merged_prs(git(['log', '--merges', '--format=%s', f'{green}..{sha}']).splitlines())
        except subprocess.CalledProcessError:
            prs = []
    done = []
    for name, info in sorted(found.items()):
        text = body(name, info, sha, green, cancelled, prs, run_url)
        title = TITLE.format(name=name)
        opened = json.loads(gh(['issue', 'list', '--state', 'open', '--search', f'"{title}" in:title',
                                '--json', 'number,title']) or '[]')
        same = [i for i in opened if i.get('title') == title]
        if same:
            number = same[0]['number']
            if not dry:
                gh(['issue', 'comment', str(number), '--body', text])
            done.append((name, 'commented', number))
        else:
            if not dry:
                out = gh(['issue', 'create', '--title', title, '--body', text])
                m = re.search(r'/issues/(\d+)', out)
                done.append((name, 'created', int(m[1]) if m else None))
            else:
                done.append((name, 'created', None))
    return done


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--reports', required=True)
    ap.add_argument('--sha', required=True)
    ap.add_argument('--repo', required=True)
    ap.add_argument('--run-url', required=True)
    ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args()

    def gh(args):
        return subprocess.run(['gh', *args, '-R', a.repo] if args[0] in ('run', 'issue') else ['gh', *args],
                              check=True, capture_output=True, text=True).stdout

    def git(args):
        return subprocess.run(['git', *args], check=True, capture_output=True, text=True).stdout
    for name, how, number in run(gh, git, a.reports, a.sha, a.run_url, a.dry_run):
        print(f'{name}: issue {how}' + (f' #{number}' if number else ''))
    return 0


if __name__ == '__main__':
    sys.exit(main())
