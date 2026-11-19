"""회귀 가드 목록 검사. 규칙은 .agents/skills/guards/SKILL.md (GUARD-01~03).

트랙마다 자기 폴더에 guards.toml 을 두고, 롬이 있어야 도는 실행 검사를 등록한다.

    [[check]]
    name = "dq4-compat-walk"            # PR 본문에 적는 이름(소문자·숫자·-)
    why = "무엇이 다시 깨지지 않게 하나"
    paths = ["sfc/dq4/tools/dq4prologue.py"]   # 이 파일을 바꾼 PR 은 이 검사를 돌린다(glob, ** 가능)
    run = "uv run --locked python ..."  # 돌리는 명령
    needs = ["rom", "MESENCE"]          # 돌리는 데 필요한 것. 대문자 이름은 환경 변수로 보고 --base 때 설정됐는지 알린다
    groups = ["ch1-build"]              # (골라 씀) 같은 파일의 [groups] 에 이름 붙인 paths 묶음을 더한다
    tier = "release"                    # (골라 씀) "pr"(기본) 또는 "release": 길어서 PR 에서는 빠지고 main 머지 뒤·배포 관문이 돌리는 검사
    parts = 4                           # (골라 씀) CI 조각(--shard)에서 이 검사를 하위 조각 n 개로 나눠 러너마다 따로 돌린다

    [groups]
    ch1-build = ["sfc/dq4/tools/dq4build.py", ...]   # 여러 검사가 함께 쓰는 paths 묶음
    ch3-modules = ["sfc/dq4/tools/dq4ch3*.py", "!sfc/dq4/tools/dq4ch3*check.py"]   # 앞에 ! 를 붙인 glob 은 뺀다
    # 검사 paths 에 "@ch3-modules" 라고 적으면 그 묶음을 자기 paths 로 넣는다(PR 에서 검사를 건다. groups 키와 다름).
    # 빼기가 든 묶음은 추적 파일로 풀어 낱낱 경로가 되므로, 새 파일도 glob 에 맞으면 손대지 않고 든다

트랙의 검사 목록은 guards.toml 과 그 옆 guards.d/*.toml 조각이다(차례: guards.toml, 조각 이름 차례). 조각에는
[[check]] 와 [groups] 만 두고, 같은 이름의 묶음은 파일마다 적은 것을 합친다. [cache]·[full] 은 guards.toml 에만 둔다.

    [cache]
    key = "paths"                       # (골라 씀) 검사 결과 캐시 키에 넣을 추적 파일. "all"(기본) 또는 "paths"

    [full]
    paths = ["sfc/dq4/tools/dq4build.py", ...]   # (골라 씀) 바뀌면 이 트랙의 검사를 전체 모드로 고르는 파일

PR 에서는 바뀐 파일이 그 검사의 paths 에 바로 맞을 때, 또는 검사 목록에서 그 검사의 run·needs 가 바뀌었을 때(새 검사
포함. 트랙 전체로 견주므로 검사를 다른 조각으로 옮기기만 한 것은 바뀐 것이 아니다) 걸린다. 묶음으로만 맞는 검사와 tier = "release" 인 검사는 빠지고 main 에 머지된 뒤(ci.yml push 의 --with-release)와 배포 관문
(tools/release_check.py)이 돌린다. 이름만 모아 등급을 바꾸는 [tier] release = ["검사 이름", …] 표를 guards.toml 이나 조각에 둘 수 있다
(검사 항목을 건드리지 않고 등급만 옮길 때).
바뀐 파일이 트랙의 [full] paths 에 맞으면 그 트랙은 전체 모드라 그 트랙의 PR 등급 검사가 모두 걸린다(CI 와
로컬이 같은 판정. release 등급은 PR 에서 걸리지 않는다). PR 본문의 `가드: 전체` 줄이나 --full 은 모든 트랙을 전체 모드로 넓히기만 하고 좁히지는 못한다.
본문의 `가드: 더함 이름, 이름` 줄은 그 검사들을 걸린 목록에 더한다(guards.py 를 바꾼 PR 의 대표 셋을 CI 에서 돌릴 때).

사용:
  python tools/guards.py                         목록 형식만 검사
  python tools/guards.py --base origin/main      바뀐 파일로 걸리는 검사와 명령을 찍음(PR 올리기 전)
  python tools/guards.py --base origin/main --run
                                                 걸린 검사를 포그라운드로 함께 돌리고 본문 결과 줄을 찍음
  python tools/guards.py --base origin/main --run --only 이름,이름
                                                 걸린 검사 대신 고른 검사만 돌림(guards.py 를 바꾼 PR 의 대표 셋)
  python tools/guards.py --base origin/main --run --full
                                                 [full] 에 걸리지 않아도 전체 모드로 돌림(본문에 `가드: 전체`)
  python tools/guards.py --base SHA --head SHA --plan OUT
                                                 걸린 검사를 CI 몫과 로컬 몫(guard-shards.yml 의 LOCAL_NEEDS)으로 나눠
                                                 guards=·local=·shards= 줄을 OUT 에 더함(CI guard-plan 잡, $GITHUB_OUTPUT)
  python tools/guards.py --base SHA --head SHA --plan OUT --with-release
                                                 main push: 위에 release 등급 검사 전부를 더함(머지 뒤에 도는 긴 검사)
  python tools/guards.py --base SHA --pr-body FILE [--local-only]
                                                 걸린 검사마다 본문에 결과 줄이 있는지 봄(CI). --local-only 면 로컬 몫만
  python tools/guards.py --all --run --no-cache --shard 3/16 --exclude-needs macos --json OUT.json
                                                 등급·묶음과 상관없이 모든 검사 가운데 needs 에 macos 가 없는 것을
                                                 16 조각으로 나눠 셋째 조각만 돌리고 결과를 OUT.json 에(CI 배포 관문 잡)
  python tools/guards.py --all --sweeps --run --no-cache --shard 3/16 --json OUT.json
                                                 위에 더해 트랙마다 release.toml 의 시드 스윕도 단위로 펼쳐 함께
                                                 나눈다(CI 배포 관문 잡. sweep_units)
  python tools/guards.py --record-times FILE…    보고서(release_check report.json 또는 --json 결과)의 검사 시간으로
                                                 guardshard-times.json 을 고쳐 씀

--shard 는 검사마다 지난 실행 시간(guardshard-times.json, 없으면 그 파일에 있는 시간의 평균)으로 긴 것부터 가장 가벼운
조각에 넣는다(split_weights). 조각 잡마다 따로 나누므로 러너마다 다른 결과 캐시는 보지 않는다: 같은 목록·같은 시간 파일이면
어느 머신에서든 같은 조각이 나온다.
--exclude-needs 로 뺀 검사는 「로컬 몫」 으로 찍고 --json 에 남긴다(배포 관문이 로컬에서 돌린다).
parts = n 인 검사는 --shard 때 조각 수와 상관없이 하위 조각 n 개로 펼친다(expand_parts). 하위 조각 k 는 환경 변수
DQ4_GUARD_PART=k/n 으로 돌고, 검사 도구가 장면 목록의 k 번째 몫만 돈다(sfc/dq4/tools/dq4shards.part_of). 무게는 검사
시간/n, 같은 검사의 하위 조각은 되도록 서로 다른 조각에 넣는다. 조각이 n 보다 적어 한 조각에 같은 검사의 하위 조각이
여럿 들면 한 프로세스로 함께 돈다(DQ4_GUARD_PART=1,3/4, 작업 폴더가 같아서). 통과 기록은 하위 조각마다 「이름~kofn」 으로
남아, 조각 수가 다른 실행(PR·배포 관문·매일 데우기)도 그대로 맞는다. 결과 행은 하위 조각마다 part 를 달고,
보고(merge_parts)가 검사 하나로 합친다: 하위 조각이 모두 통과해야 통과.

DQ4_UNIT_CACHE=DIR 이면(CI 조각, 캐시 켬) 검사 단위(검사, 하위 조각이면 그 몫)마다 장면·상태·빌드 단계 캐시를
DIR/<단위>/ 아래 따로 둔다(readset·states·calls). CI 가 단위마다 enc-cache 로 되살리고 저장해(--unit-slots), 조각 수·모드가
다른 실행의 캐시를 단위 이름으로 찾는다. 캐시 안 항목은 롬 바이트·코드 지문으로 찾으므로 어느 실행이 남긴 것이든 맞을
때만 쓰인다. 상태 캐시 파일은 DIR/_pool 을 거쳐 같은 조각의 단위끼리 나눈다(share_states).

--sweeps 는 release.toml 의 [[sweep]] 을 검사 단위로 펼친다(sweep_units). 시드마다 따로 도는 스윕은 시드 하나가 단위
하나(seed_unit, 출력 work/sweep/<이름>/seed-<시드>), parts 가 있는 스윕은 모든 시드를 받은 하위 조각 n 개다(도구가
시드를 합쳐 판정할 때). 단위는 CI 조각 잡이 둔 출하 롬 SWEEP_ROM 을 읽는다. 결과 행은 "sweep": true 를 달고, 시드
단위 행은 "part"·"seeds" 를 달아 merge_parts 가 스윕 하나로 합친다(실패 글에 시드). judge 가 있는 parts 스윕은 도구가
로그에 찍은 {"sweep_data": …} 줄을 결과 행 "data" 로 옮기고, merge_parts 가 몫을 모두 모아 그 함수로 판정한다(judge_merged).

--run 은 같은 입력(.md 를 뺀 추적 파일 내용, 명령, --rom 롬 SHA-1)으로 이미 통과한 검사를 건너뛴다. [cache] key = "paths"
인 트랙은 추적 파일 가운데 그 검사의 paths·묶음에 맞는 것, 그 트랙의 어느 검사도 paths 에 적지 않은 자료 파일
(.py·.lua·.asm 밖), 의존성 파일만 본다(key_scope).
입력이 달라도 롬을 빌드하는 검사는 빌드 단계를 먼저 돌려, 만든 파일과 .py 밖 입력이 같고 검사 단계가 지난번에 실행한
함수의 코드·연 파일이 모두 같으면 검사 단계를 건너뛴다(run_check, tools/guardtrace).
캐시는 원래 체크아웃의 work/cache/guards 에 있어 워크트리끼리 함께 쓴다. --no-cache 는 이 캐시와 검사 안의 캐시를
모두 끄고 전부 돌린다(no_cache_env(logs): 장면 캐시 DQ4_READSET=off, 빌드 단계 캐시 DQ4_BUILD_CACHE=off, 서장 끝·시작
상태 캐시는 로그 폴더 아래 빈 states/ 에서 그 실행 동안만).

결과 줄: `- [x] <이름>: 통과 (…)` 또는 `- [x] <이름>: 해당 없음 — <이유>`. 그 밖의 글(「통과하지 못함」 등)은 실패로 친다.
"""
import argparse
import concurrent.futures
import functools
import glob
import hashlib
import json
import os
import shutil
import signal
import stat
import re
import subprocess
import sys
import tempfile
import time
import tomllib
from pathlib import Path, PurePosixPath

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mesence_settings import settings_digest  # noqa: E402
import headless_slots  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
NAME = re.compile(r'^[a-z0-9]+(?:-[a-z0-9]+)*$')
ENV = re.compile(r'^[A-Z][A-Z0-9_]*$')
FIELDS = {'name': str, 'why': str, 'paths': list, 'run': str, 'needs': list}
OPTIONAL = {'groups': list, 'tier': str, 'parts': int}
PARTS_MAX = 64
PART_ENV = 'DQ4_GUARD_PART'
# .github/actions/unit-cache 의 자리 수와 같아야 한다(test_release_gate_workflow 가 지킨다)
UNIT_SLOTS = 12
TIERS = ('pr', 'release')
CACHE_KEYS = ('all', 'paths')
# 이 값이 바뀌면 검사 결과가 바뀔 수 있다(why 는 설명, paths·groups 는 고르는 데만 씀)
RESULT_FIELDS = ('run', 'needs')
# CI 조각이 로컬 몫으로 빼는 needs 이름의 정본(env LOCAL_NEEDS). PR 계획·본문 검사·ship.py 가 이것을 읽는다
SHARDS_WORKFLOW = ROOT / '.github' / 'workflows' / 'guard-shards.yml'
# PR 가드 잡의 조각 수: 조각 하나에 이만큼(초)씩, 많아야 이만큼 조각. 계정 동시 잡 20 을 배포 관문(조각 18)·cache-warm(조각 16)과
# 나눠 쓰므로 그보다 작게 둔다(test_release_gate_workflow 가 지킴)
PR_SHARD_SECONDS = 480
PR_SHARDS_MAX = 8
# main push 는 release 등급까지 돌려 무게가 크다. 머지 뒤라 PR 처럼 짧을 필요는 없지만 배포 관문 조각(18)보다 작게
MAIN_SHARDS_MAX = 14


def git(*args):
    return subprocess.run(['git', *args], cwd=ROOT, check=True, capture_output=True, text=True).stdout


def tracked():
    return [line for line in git('ls-files').splitlines() if line]


def matches(path, pattern):
    """PurePosixPath(path).full_match(pattern) 와 같다. 검사 목록을 읽을 때 패턴×추적 파일을 수십만 번 부르므로 정규식으로."""
    return bool(glob_regex((pattern,)).match(path))


FRAGMENTS = 'guards.d'
MAIN_KEYS = ('check', 'groups', 'cache', 'full', 'tier')
FRAGMENT_KEYS = ('check', 'groups', 'tier')


def fragment_owner(path):
    """조각 파일(<트랙>/guards.d/*.toml)이면 그 트랙의 guards.toml 경로, 아니면 None."""
    p = PurePosixPath(path)
    if p.suffix == '.toml' and p.parent.name == FRAGMENTS and len(p.parts) >= 2:
        return str(p.parent.parent / 'guards.toml')
    return None


def track_of(path):
    """검사 목록 파일(guards.toml 또는 그 조각)이면 그 트랙의 guards.toml 경로, 아니면 None."""
    return path if PurePosixPath(path).name == 'guards.toml' else fragment_owner(path)


def group_match(patterns, path):
    """묶음 항목들에 맞는가: 앞에 ! 가 없는 glob 가운데 하나에 맞고, ! 를 붙인 glob 어느 것에도 맞지 않는다."""
    pos = tuple(p for p in patterns if not p.startswith('!'))
    neg = tuple(p[1:] for p in patterns if p.startswith('!'))
    return bool(glob_regex(pos).match(path)) and not glob_regex(neg).match(path)


def group_paths(patterns, files):
    """묶음을 검사 paths 에 넣을 꼴로. ! 빼기가 없으면 적은 glob 그대로(낱낱이 적은 것과 같은 뜻), 있으면 지금 추적 파일
    가운데 맞는 것을 낱낱 경로로 푼다(PR 에서 새로 생긴 파일도 추적 파일이라 든다)."""
    if not any(p.startswith('!') for p in patterns):
        return list(patterns)
    return sorted(f for f in files if group_match(patterns, f))


def load(files, read=lambda f: (ROOT / f).read_text(encoding='utf-8')):
    """(검사 목록, 문제 목록). 검사는 {'file': 그 검사를 적은 파일, **항목}. files 는 추적 파일 목록.

    트랙은 guards.toml 하나와 그 옆 guards.d/*.toml 조각들이다. 조각은 [[check]] 와 [groups] 만 갖고, 같은 이름의
    묶음은 파일마다 적은 것을 합친다([cache]·[full] 은 guards.toml 에만). 검사 paths 의 "@이름" 은 그 트랙 묶음을
    자기 paths 로 넣는다(PR 에서 검사를 건다). groups 키로 더한 묶음은 PR 에서 걸지 않는다."""
    checks, problems = [], []
    mains = sorted(f for f in files if PurePosixPath(f).name == 'guards.toml')
    frags = sorted(f for f in files if fragment_owner(f))
    for f in frags:
        if fragment_owner(f) not in mains:
            problems.append(f'{f}: 조각은 guards.toml 이 있는 폴더의 {FRAGMENTS}/ 에만')
    for toml in mains:
        parts = []
        for part in [toml] + [f for f in frags if fragment_owner(f) == toml]:
            try:
                parts.append((part, tomllib.loads(read(part))))
            except tomllib.TOMLDecodeError as e:
                problems.append(f'{part}: TOML 오류 {e}')
        if not parts or parts[0][0] != toml:
            continue
        for part, data in parts:
            for key in data:
                if key not in (MAIN_KEYS if part == toml else FRAGMENT_KEYS):
                    problems.append(f'{part}: 모르는 키 {key}')
        data = parts[0][1]
        full = data.get('full', {})
        if not isinstance(full, dict) or set(full) - {'paths'} or not isinstance(full.get('paths', []), list):
            problems.append(f'{toml}: [full] 는 paths = [glob, …] 만')
            full = {}
        full_paths = [p for p in full.get('paths', []) if isinstance(p, str)]
        for pattern in full.get('paths', []):
            if not isinstance(pattern, str) or not any(matches(f, pattern) for f in files):
                problems.append(f'{toml} full.paths: {pattern!r} 에 맞는 추적 파일이 없음')
        cache = data.get('cache', {})
        if not isinstance(cache, dict) or set(cache) - {'key'} or cache.get('key', 'all') not in CACHE_KEYS:
            problems.append(f'{toml}: [cache] 는 key = {" 또는 ".join(map(repr, CACHE_KEYS))} 만')
            cache = {}
        mine = []
        groups = {}
        for part, pdata in parts:
            pgroups = pdata.get('groups', {})
            if not isinstance(pgroups, dict):
                problems.append(f'{part}: groups 는 [groups] 표여야 함')
                continue
            for gname, pats in pgroups.items():
                if not NAME.match(gname):
                    problems.append(f'{part} groups.{gname}: 이름은 소문자·숫자·- 만')
                if not isinstance(pats, list) or not pats:
                    problems.append(f'{part} groups.{gname}: 비어 있지 않은 목록이어야 함')
                    continue
                for pattern in pats:
                    if not isinstance(pattern, str) or pattern.startswith('@'):
                        problems.append(f'{part} groups.{gname}: {pattern!r} 는 glob(앞에 ! 면 빼기)이어야 함')
                    elif not any(matches(f, pattern.removeprefix('!')) for f in files):
                        problems.append(f'{part} groups.{gname}: {pattern!r} 에 맞는 추적 파일이 없음')
                groups.setdefault(gname, []).extend(p for p in pats if isinstance(p, str) and not p.startswith('@'))
        resolved = {}
        for gname, pats in groups.items():
            resolved[gname] = group_paths(pats, files)
            if pats and not resolved[gname]:
                problems.append(f'{toml} groups.{gname}: 빼고 나면 맞는 추적 파일이 없음')
        for part, pdata in parts:
            items = pdata.get('check', [])
            if not isinstance(items, list):
                problems.append(f'{part}: check 는 [[check]] 배열이어야 함')
                continue
            for i, item in enumerate(items):
                where = f'{part} check[{i}]'
                if not isinstance(item, dict):
                    problems.append(f'{where}: 표가 아님')
                    continue
                for key, kind in FIELDS.items():
                    if not isinstance(item.get(key), kind):
                        problems.append(f'{where}: {key} 가 없거나 {kind.__name__} 가 아님')
                for key in item:
                    if key not in FIELDS and key not in OPTIONAL:
                        problems.append(f'{where}: 모르는 키 {key}')
                used = item.get('groups', [])
                if not isinstance(used, list):
                    problems.append(f'{where}: groups 가 list 가 아님')
                    used = []
                for g in used:
                    if g not in resolved:
                        problems.append(f'{where}: 묶음 {g!r} 이 {toml} 트랙의 [groups] 에 없음')
                if 'parts' in item and (type(item['parts']) is not int or not 2 <= item['parts'] <= PARTS_MAX):
                    problems.append(f'{where}: parts 는 2~{PARTS_MAX} 정수')
                if item.get('tier', 'pr') not in TIERS:
                    problems.append(f'{where}: tier 는 {" 또는 ".join(map(repr, TIERS))}')
                if isinstance(item.get('name'), str) and not NAME.match(item['name']):
                    problems.append(f'{where}: 이름 {item["name"]!r} 은 소문자·숫자·- 만')
                own = []
                if isinstance(item.get('paths'), list):
                    if not item['paths'] and not used:
                        problems.append(f'{where}: paths 가 비어 있음')
                    for pattern in item['paths']:
                        if isinstance(pattern, str) and pattern.startswith('@'):
                            if pattern[1:] in resolved:
                                own += resolved[pattern[1:]]
                            else:
                                problems.append(f'{where}: paths {pattern!r} 의 묶음이 {toml} 트랙의 [groups] 에 없음')
                        elif not isinstance(pattern, str) or pattern.startswith('!'):
                            problems.append(f'{where}: paths {pattern!r} 는 glob 또는 "@묶음"(! 빼기는 [groups] 에만)')
                        elif not any(matches(f, pattern) for f in files):
                            problems.append(f'{where}: paths {pattern!r} 에 맞는 추적 파일이 없음')
                        else:
                            own.append(pattern)
                if all(isinstance(item.get(k), kind) for k, kind in FIELDS.items()):
                    extra = [p for g in used if g in resolved for p in resolved[g]]
                    mine.append({'file': part, **item, 'own_paths': own, 'paths': [*own, *extra]})
        if cache.get('key') == 'paths':
            # 자료 파일의 주인은 낱낱이 적은 경로로만 친다(sfc/dq4/tools/** 같은 glob 은 읽는다는 뜻이 아니다)
            claimed = sorted({p for c in mine for p in c['paths'] if not glob.has_magic(p)})
            for c in mine:
                c['key_claimed'] = claimed
        for part, pdata in parts:
            for tname, names in (pdata.get('tier', {}) if isinstance(pdata.get('tier', {}), dict) else {}).items():
                if tname != 'release' or not isinstance(names, list):
                    problems.append(f'{part}: [tier] 는 release = [검사 이름, …] 만')
                    continue
                for n in names:
                    hit = [c for c in mine if c['name'] == n]
                    if not hit:
                        problems.append(f'{part} tier.release: 검사 {n!r} 이 {toml} 트랙에 없음')
                    for c in hit:
                        c['tier'] = 'release'
            if not isinstance(pdata.get('tier', {}), dict):
                problems.append(f'{part}: tier 는 [tier] 표여야 함')
        for c in mine:
            c['full_paths'] = full_paths
        checks += mine
    seen = {}
    for c in checks:
        name = c.get('name')
        if name in seen:
            problems.append(f'{c["file"]}: 이름 {name} 이 {seen[name]} 에도 있음')
        seen.setdefault(name, c['file'])
    return checks, problems


def unset_env(needs, environ=os.environ):
    """needs 가운데 환경 변수 이름인데 지금 비어 있는 것."""
    return [n for n in needs if ENV.match(n) and not environ.get(n)]


PLACEHOLDER = re.compile(r'<[^<>]+>')


def made_paths(run):
    """마지막 단계 앞의 단계들이 --out 으로 만드는 경로(파일 또는 폴더)."""
    return [m for st in run.split('&&')[:-1] for m in re.findall(r'--out\s+(\S+)', st)]


def written_paths(run):
    """명령이 결과로 쓰는 파일(tee·>·>>·--report·--json 뒤). 입력 키에 넣으면 도는 사이 생기거나 바뀌어 통과를 남기지 못한다."""
    return re.findall(r'(?:\btee(?:\s+-a)?|>>?|--report|--json)\s+(?:\$PWD/)?(work/[^\s;&|)]+)', run)


def under(path, base):
    p, b = PurePosixPath(path).parts, PurePosixPath(base).parts
    return p[:len(b)] == b


def rom_of(run):
    """마지막 단계(검사)가 읽는 --rom 경로. 앞 단계가 만드는 롬이면 None(돌리기 전엔 알 수 없음)."""
    m = re.search(r'--rom\s+(\S+)', run.split('&&')[-1])
    if not m:
        return None
    return None if any(under(m[1], d) for d in made_paths(run)) else m[1]


def builds(run):
    """마지막 단계 앞에 --out 으로 무언가를 만드는 단계가 있는지(롬 빌드)."""
    return bool(made_paths(run))


def out_dirs(run):
    """마지막 단계의 --out 가운데 work/<이름>… 폴더(검사 출력. 돌리기 전에 비운다). work 자체와 공유 캐시는 뺀다."""
    stage = run.split('&&')[-1]
    keep = []
    for d in re.findall(r'--out\s+(\S+)', stage):
        parts = PurePosixPath(d).parts
        if len(parts) >= 2 and parts[0] == 'work' and parts[1] != 'cache' and '..' not in parts:
            keep.append(d)
    return keep


# 이보다 큰 파일은 내용 대신 (크기, mtime_ns) 로 본다
BIG_FILE = 64 << 20


def stat_key(path):
    st = path.stat()
    return f'{st.st_size}:{st.st_mtime_ns}'.encode()


def hash_path(h, path):
    """파일은 내용(BIG_FILE 보다 크면 크기·mtime_ns), 폴더는 그 안 파일들의 (상대 경로, 크기, mtime_ns).
    폴더를 내용째 읽지 않는 것은 needs 의 자원 저장소(수 GB)처럼 큰 폴더도 키를 곧 만들게 하려는 것이다.
    파일을 내용은 그대로 두고 mtime 만 되돌리면 옛 결과로 건너뛸 수 있다. 폴더 안 cache/ 아래는 내용으로 본다. 없으면 표시만."""
    path = Path(path)
    if path.is_file():
        if path.stat().st_size > BIG_FILE:
            h.update(b'big:' + stat_key(path))
        else:
            h.update(hashlib.sha1(path.read_bytes()).digest())
    elif path.is_dir():
        # 자원 저장소 같은 체크아웃의 .git 은 내용이 작업 트리 파일과 겹치고, git 명령이 index 를 고쳐 쓰거나 새로 받을
        # 때마다 시각이 바뀐다
        for f in sorted(p for p in path.rglob('*') if p.is_file() and '.git' not in p.relative_to(path).parts):
            rel = f.relative_to(path)
            # 폴더 안 cache/ 는 빌드가 같은 내용으로 다시 써 mtime 만 바뀌므로 내용으로 본다
            if 'cache' in rel.parts[:-1] and f.stat().st_size <= BIG_FILE:
                h.update(str(rel).encode() + b'\0' + hashlib.sha1(f.read_bytes()).digest())
                continue
            h.update(str(rel).encode() + b'\0' + stat_key(f))
    else:
        h.update(b'-')


def env_names(needs):
    """needs 글에 나오는 환경 변수 이름(설명문 안의 LIBRETRO_BSNES 같은 것도)."""
    return sorted({n for item in needs for n in re.findall(r'\b[A-Z][A-Z0-9_]{2,}\b', item)})


# 검사 명령이 읽거나 실행하지 않는 추적 파일. 키에서 빼도 결과가 같다(뺀 것이 결과에 닿는다고 의심되면 넣어 둔다)
#   .md: 문서. guards.toml·guards.d/*.toml: 검사 목록(그 검사의 명령과 needs 는 따로 키에 든다). 에이전트·CI 설정, 해킹 일지
NOT_INPUT = re.compile(r'(\.md$|(^|/)guards\.toml$|(^|/)guards\.d/[^/]+\.toml$|^\.agents/|^\.github/|^\.claude/|(^|/)journal/)')
# 단위 테스트 파일
TEST_FILE = re.compile(r'((^|/)test_[^/]*\.py$|(^|/)tests/)')


def runs_tests(run):
    """명령이 단위 테스트를 부르는가: unittest·pytest 를 쓰거나 test_*.py·tests/ 의 파일을 바로 돌린다."""
    return bool(re.search(r'\b(unittest|pytest)\b|(^|[\s/])test_\w*\.py\b|(^|[\s/])tests/', run))


def is_input(path, run):
    """그 추적 파일이 이 검사 명령의 결과에 닿을 수 있는가. 단위 테스트를 부르는 명령은 테스트가 무엇을 읽을지 몰라
    .md 만 뺀다."""
    if path.endswith('.md'):
        return False
    if runs_tests(run):
        return True
    return not (NOT_INPUT.search(path) or TEST_FILE.search(path))


# 어느 검사의 키에도 늘 넣는 추적 파일: 모든 검사가 도는 Python 과 의존성
ALWAYS_KEY = frozenset({'uv.lock', 'pyproject.toml', '.python-version'})
# dq4guardpaths 처럼 트랙 시험이 paths 가 덮는지 보는 종류(import·Lua·asm 으로 닿는 코드)
CODE_FILE = re.compile(r'\.(py|lua|asm)$')


@functools.lru_cache(maxsize=None)
def glob_regex(patterns):
    """paths glob 묶음(tuple)을 하나의 정규식으로. PurePosixPath.full_match 와 같은 뜻이고 훨씬 빠르다."""
    return re.compile('|'.join(glob.translate(p, recursive=True, include_hidden=True) for p in patterns) or r'(?!)')


def key_scope(check):
    """검사 결과 캐시 키에 넣을 추적 파일을 고르는 함수. [cache] key = "paths" 인 트랙(key_claimed 가 있음)은 그 검사의
    paths·묶음에 맞는 것, 트랙의 어느 검사도 paths 에 낱낱이 적지 않은 자료 파일(.py·.lua·.asm 밖), ALWAYS_KEY.
    코드와 글자 상수로 이름을 적어 읽는 자료 파일은 트랙 시험(dq4guardpaths)이 paths 가 덮는다고 보장한다. 계산한
    이름으로 여는 자료 파일은 시험이 못 보므로, 주인이 적히지 않은 것은 누가 읽을지 몰라 모두의 키에 둔다.
    그 밖의 트랙은 모두."""
    claimed = check.get('key_claimed')
    if claimed is None:
        return lambda path: True
    own, anyone = glob_regex(tuple(check['paths'])), frozenset(claimed)
    return lambda path: (path in ALWAYS_KEY or bool(own.match(path))
                         or not (CODE_FILE.search(path) or path in anyone))


def input_key(check, root=ROOT, environ=os.environ, built=False):
    """같은 입력이면 같은 키. 추적 파일 가운데 결과에 닿는 것(is_input), 명령, needs 환경 변수가 가리키는 파일·폴더
    (hash_path), MESENCE 가 있으면 MesenCE 사용자 설정 파일, rom/ 원본, 명령이 읽는 파일(앞 단계가 만드는 것 빼고).
    MESENCE 가 있는데 설정 파일을 찾지 못하면 None: 결과에 닿는 입력을 모르므로 캐시를 읽지도 쓰지도 않는다.

    추적 파일은 key_scope 가 고른 것만 본다.

    built 면 빌드 단계를 돌린 뒤의 키(built_hit): 추적 .py 는 빼고(검사 단계가 연 .py 는 캐시 항목이 따로 본다),
    앞 단계가 만든 파일을 내용째 넣는다."""
    h = hashlib.sha256()
    run = check['run']
    h.update(run.encode())

    scope = key_scope(check)

    def counts(path):
        return is_input(path, run) and scope(path) and not (built and path.endswith('.py'))
    for line in git('ls-files', '-s').splitlines():
        if counts(line.split('\t', 1)[-1]):
            h.update(line.encode())
    for f in sorted(x for x in git('diff', '--name-only', 'HEAD').splitlines() if x and counts(x)):
        h.update(f.encode())
        hash_path(h, root / f)
    for n in env_names(check.get('needs', [])):
        v = environ.get(n, '')
        h.update(f'{n}={v}'.encode())
        if v:
            hash_path(h, v)
        if n == 'MESENCE' and v:
            digest = settings_digest(v)
            if digest is None:
                return None
            h.update(b'mesence-settings:' + digest.encode())
    hash_path(h, root / 'rom')
    made = made_paths(run) + out_dirs(run) + written_paths(run)
    for tok in sorted(set(re.findall(r'(?<![\w/])(?:\$PWD/)?(work/\S+|rom/\S+)', run))):
        if not any(under(tok, d) for d in made):
            h.update(tok.encode())
            hash_path(h, root / tok)
    if built:
        for f in sorted(TRACER.glob('*.py')):
            h.update(f.name.encode() + b'\0' + f.read_bytes())
        # 새 .py 가 import 경로에서 다른 모듈을 가릴 수 있어 추적 .py 이름 목록은 넣는다(내용은 항목이 본다)
        h.update('\0'.join(sorted(x for x in tracked() if x.endswith('.py'))).encode())
        for d in made_paths(run):
            h.update(b'made:' + d.encode())
            hash_content(h, root / d)
    return h.hexdigest()


def hash_content(h, path):
    """파일은 내용, 폴더는 그 안 파일들의 (상대 경로, 내용). BIG_FILE 보다 큰 파일은 크기·mtime_ns 라 다시 만들면 빗나간다."""
    path = Path(path)
    files = [path] if path.is_file() else sorted(p for p in path.rglob('*') if p.is_file()) if path.is_dir() else []
    if not files:
        h.update(b'-')
    for f in files:
        h.update(str(f.relative_to(path) if f != path else '').encode() + b'\0')
        hash_path(h, f)


TRACER = Path(__file__).resolve().parent / 'guardtrace'
sys.path.insert(0, str(TRACER))
from guardprint import module_prints  # noqa: E402
# 검사 단계 명령의 꼴: 환경 변수 대입 뒤 uv run 의 python 과 스크립트(인터프리터 플래그 없이). 그 밖의 프로그램은
# .py 를 몰래 읽을 수 있고, -I·-E·-S 는 PYTHONPATH 의 추적기를 싣지 않는다
CHECK_STAGE = re.compile(r'^\s*([A-Za-z_][A-Za-z0-9_]*=\S*\s+)*uv run --(locked|frozen) python\s+(?P<script>[^\s-]\S*\.py)(\s|$)')
# 빌드 단계가 검사 단계에 남기는 셸 상태
SHELL_STATE = re.compile(r'(^|&&)\s*(cd|export|source|\.|set|unset|alias|pushd|popd|shopt|umask)\s')


def split_built(check):
    """빌드 결과 캐시를 쓸 수 있으면 (앞 단계들, 검사 단계) 명령, 아니면 None. 앞 단계가 무언가를 --out 으로 만들고,
    단위 테스트를 부르지 않으며, 셸 상태를 바꾸지 않고, && 말고 다른 연결(; || | & 줄바꿈)·따옴표·$( ) 가 없고,
    검사 단계가 CHECK_STAGE 꼴이어야 한다."""
    run = check['run']
    if not builds(run) or runs_tests(run) or SHELL_STATE.search(run) or re.search(r'[;\n`"\'\\]|\$\(|\|\||(?<![&|])[&|](?![&|])', run):
        return None
    stages = run.split('&&')
    if not CHECK_STAGE.match(stages[-1]):
        return None
    return '&&'.join(stages[:-1]), stages[-1]


def shadowed():
    """추적기를 가릴 수 있는 추적 sitecustomize.py(스크립트 폴더가 PYTHONPATH 보다 앞이다)가 있는가."""
    return any(PurePosixPath(f).name in ('sitecustomize.py', 'usercustomize.py') and not under(f, 'tools/guardtrace')
               for f in tracked())


def read_trace(reads, script=None):
    """검사 단계 기록을 {'files', 'dirs', 'stats': {경로: 값}, 'code': {경로: {qualname: [실행한 지문…]}}} 로.
    `?`, 기록 없음, 검사 단계 스크립트(script)의 S 줄이 없음(맨 위 Python 이 추적기를 싣지 않음), 같은 경로가 다른
    값으로 두 번(도는 중에 바뀜), 읽지 못한 파일(-)이면 None."""
    if not reads.is_file():
        return None
    out = {'files': {}, 'dirs': {}, 'stats': {}, 'links': {}, 'code': {}}
    starts = set()
    for line in reads.read_text(encoding='utf-8', errors='surrogateescape').splitlines():
        f = line.split('\t')
        kind = f[0]
        if kind == 'S' and len(f) == 2:
            starts.add(f[1])
        elif kind in ('F', 'D', 'E', 'L') and len(f) == 3:
            table = out[{'F': 'files', 'D': 'dirs', 'E': 'stats', 'L': 'links'}[kind]]
            if (kind == 'F' and f[2] == '-') or table.setdefault(f[1], f[2]) != f[2]:
                return None
        elif kind == 'C' and len(f) == 4:
            fps = out['code'].setdefault(f[1], {}).setdefault(f[2], [])
            if f[3] not in fps:
                fps.append(f[3])
        else:
            return None
    if script is not None and script not in starts:
        return None
    return out


def sha1_of(path):
    return hashlib.sha1(path.read_bytes()).hexdigest() if path.is_file() else None


def content_sig(path):
    """추적기(sitecustomize.content_sig)와 같은 표지."""
    if not path.is_file():
        return None
    st = path.stat()
    return f'big:{st.st_size}:{st.st_mtime_ns}' if st.st_size > BIG_FILE else sha1_of(path)


def stat_state(path):
    try:
        st = os.stat(path)
    except OSError:
        return '-'
    return 'dir' if stat.S_ISDIR(st.st_mode) else str(st.st_size)


def link_of(path):
    try:
        return os.readlink(path)
    except OSError:
        return '-'


def listing_of(path):
    if not path.is_dir():
        return None
    return hashlib.sha1('\0'.join(sorted(os.listdir(path))).encode('utf-8', 'surrogateescape')).hexdigest()


def code_prints(path):
    return module_prints(path.read_bytes(), str(path)) if path.is_file() else None


def entry_holds(entry, root):
    """캐시 항목이 지금도 맞는가: 연 파일·본 폴더·stat 으로 본 것·거쳐 간 링크가 같고, 실행한 코드가 든 파일마다 원본이 같거나
    실행한 qualname 들의 지문 목록(차례 포함)이 같다."""
    if any(content_sig(root / p) != v for p, v in entry['files'].items()):
        return False
    if any(listing_of(root / p) != v for p, v in entry['dirs'].items()):
        return False
    if any(stat_state(root / p) != v for p, v in entry['stats'].items()):
        return False
    if 'links' not in entry or any(link_of(root / p) != v for p, v in entry['links'].items()):
        return False
    for p, (src, quals) in entry['code'].items():
        if sha1_of(root / p) == src:
            continue
        prints = code_prints(root / p)
        if prints is None or any(prints.get(q) != v for q, v in quals.items()):
            return False
    return True


def trace_entry(trace, root):
    """read_trace 결과를 캐시 항목으로. 실행한 qualname 마다 지금 파일의 같은 이름 지문 목록을 담는데, 실행한 지문이
    하나라도 그 목록에 없으면(도는 중에 고침) None."""
    code = {}
    for p, quals in trace['code'].items():
        prints = code_prints(root / p)
        if prints is None:
            return None
        kept = {}
        for q, fps in quals.items():
            if q not in prints or any(fp not in prints[q] for fp in fps):
                return None
            kept[q] = prints[q]
        code[p] = [sha1_of(root / p), kept]
    return {'files': trace['files'], 'dirs': trace['dirs'], 'stats': trace['stats'], 'links': trace['links'], 'code': code}


def load_entries(path):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return []


def write_atomic(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f'.{path.name}.{os.getpid()}.{time.monotonic_ns()}')
    tmp.write_text(text, encoding='utf-8')
    os.replace(tmp, path)


def built_hit(name, key, root):
    """같은 빌드 결과 키로 통과한 기록 가운데 지금도 맞는 것(entry_holds)."""
    for old in load_entries(cache_dir() / 'built' / f'{name}-{key[:24]}.json'):
        try:
            if entry_holds(old['trace'], root):
                return old
        except (KeyError, TypeError, ValueError):
            continue
    return None


def save_built(name, key, detail, trace):
    path = cache_dir() / 'built' / f'{name}-{key[:24]}.json'
    olds = [o for o in load_entries(path) if o.get('trace') != trace][-7:]
    olds.append({'when': time.strftime('%Y-%m-%d %H:%M'), 'detail': detail, 'trace': trace})
    write_atomic(path, json.dumps(olds, ensure_ascii=False))


def cache_dir():
    common = Path(git('rev-parse', '--path-format=absolute', '--git-common-dir').strip())
    return common.parent / 'work' / 'cache' / 'guards'


RUNNING = set()


def kill_group(proc):
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass


def no_cache_env(logs):
    """캐시를 모두 끈 검사 환경. 상태 캐시는 logs/states(돌리기 전에 비움)에서 이 실행 동안만 쓴다."""
    return dict(os.environ, DQ4_READSET='off', DQ4_BUILD_CACHE='off', DQ4_STATES_CACHE=str(Path(logs) / 'states'))


DQ4BUILD = re.compile(r'\bpython (sfc/dq4/tools/dq4build\.py)(?=\s)')


def with_prebuilt(command, env):
    """env 에 DQ4_PREBUILT(CI 가 빌드 잡에서 한 번 만든 출하 롬 폴더들)가 있으면 dq4build.py 호출을
    tools/ci_cache.py prebuilt 로 바꾼다. 같은 커밋·인자·롬의 빌드가 있으면 복사하고, 없으면 그대로 빌드한다."""
    if not env.get('DQ4_PREBUILT'):
        return command
    return DQ4BUILD.sub('python tools/ci_cache.py prebuilt', command)


# 미리 만든 빌드로 바뀌는 단계: 앞에 환경 변수 없이 dq4build.py --out 폴더 뒤에 인자만
PREBUILT_STAGE = re.compile(r'\s*uv run --locked python sfc/dq4/tools/dq4build\.py --out (\S+)((?:\s+--[\w-]+)*)\s*')


def prebuilt_places(checks, env):
    """{빌드 폴더: 미리 만든 폴더}. env 의 DQ4_PREBUILT 에 그 단계의 인자와 이 커밋·롬이 맞는 빌드가 있는 dq4build 단계의
    --out 들. 같은 폴더를 다른 인자로 만드는 단계가 있으면 그 폴더는 뺀다(어느 빌드가 거기 있어야 하는지 정할 수 없음)."""
    if not env.get('DQ4_PREBUILT'):
        return {}
    import ci_cache
    saved = os.environ.get('DQ4_PREBUILT')
    os.environ['DQ4_PREBUILT'] = env['DQ4_PREBUILT']
    try:
        seen, found = {}, {}
        for c in checks:
            for st in c['run'].split('&&')[:-1]:
                m = PREBUILT_STAGE.fullmatch(st)
                if m:
                    seen.setdefault(m[1], set()).add(tuple(m[2].split()))
        for out, args in seen.items():
            hit = ci_cache.prebuilt_dir(next(iter(args))) if len(args) == 1 else None
            if hit:
                found[out] = hit[0]
        return found
    finally:
        if saved is None:
            os.environ.pop('DQ4_PREBUILT', None)
        else:
            os.environ['DQ4_PREBUILT'] = saved


def place_prebuilt(places):
    """prebuilt_places 의 폴더마다 미리 만든 빌드와 같게 맞춘다. 그 뒤로 그 단계는 아무것도 쓰지 않아(ci_cache.sync_tree)
    롬을 읽기만 하는 검사가 된다."""
    import ci_cache
    for out, d in places.items():
        ci_cache.sync_tree(d, ROOT / out)


def built_paths(run, places):
    """명령이 실제로 만드는 경로: made_paths 가운데 places 에 맞춰 둔 미리 만든 빌드 단계의 --out 을 뺀 것."""
    out = []
    for st in run.split('&&')[:-1]:
        m = PREBUILT_STAGE.fullmatch(st)
        if m and m[1] in places:
            continue
        out += re.findall(r'--out\s+(\S+)', st)
    return out


def spawn(command, log, timeout, env):
    """bash 로 명령 하나를 돌려 로그에 덧붙인다. 종료 코드, 시간을 넘기면 None."""
    command = with_prebuilt(command, env)
    with log.open('a', encoding='utf-8') as out:
        proc = subprocess.Popen(['bash', '-c', command], cwd=ROOT, stdout=out, stderr=subprocess.STDOUT,
                                start_new_session=True, env=env)
        RUNNING.add(proc)
        try:
            return proc.wait(timeout=max(1, timeout))
        except subprocess.TimeoutExpired:
            return None
        finally:
            # 명령이 남긴 백그라운드 자식까지 그룹째 정리
            kill_group(proc)
            proc.wait()
            RUNNING.discard(proc)


def part_ks(check):
    """하위 조각 번호들(차례대로). 하위 조각이 아니면 ()."""
    if not check.get('part'):
        return ()
    k = check['part'][0]
    return tuple(k) if isinstance(k, (tuple, list)) else (k,)


def with_parts(check, ks):
    """check 를 하위 조각 ks 의 단위로(하나면 (k, n), 여럿이면 ((k…), n))."""
    ks, n = tuple(sorted(ks)), check['part'][1]
    return dict(check, part=(ks[0] if len(ks) == 1 else ks, n))


def record_tags(check):
    """통과 기록 이름 꼬리: 하위 조각마다 하나(함께 돌아도 몫마다 따로 남겨 조각 수가 다른 실행이 쓴다)."""
    return [f'~{k}of{check["part"][1]}' for k in part_ks(check)] or [check.get('tag', '')]


def unit_dir(check, root):
    return Path(root) / f'{check["name"]}{part_tag(check)}'


def share_states(src, dest):
    """src 의 상태 캐시 파일 가운데 dest 에 없는 것을 복사한다(임시 이름에 쓴 뒤 이름 바꿈, 함께 도는 검사가 반쯤 쓴
    파일을 읽지 않게). 상태 캐시 파일은 롬 SHA-1·코드 지문이 이름에 들어 같은 이름이면 같은 내용이다. 복사한 수."""
    src, dest, n = Path(src), Path(dest), 0
    for f in sorted(src.rglob('*')) if src.is_dir() else ():
        to = dest / f.relative_to(src)
        if not f.is_file() or f.name.startswith('.') or to.exists():
            continue
        to.parent.mkdir(parents=True, exist_ok=True)
        tmp = to.with_name(f'.{to.name}.{os.getpid()}.{time.monotonic_ns()}')
        shutil.copy2(f, tmp)
        os.replace(tmp, to)
        n += 1
    return n


def unit_env(check, env):
    """DQ4_UNIT_CACHE 가 있으면 이 단위의 캐시 폴더를 가리키는 env(상태 캐시는 _pool 에서 받아 둔다). 없으면 env."""
    root = env.get('DQ4_UNIT_CACHE')
    if not root:
        return env
    u = unit_dir(check, root)
    share_states(Path(root) / '_pool' / 'states', u / 'states')
    return dict(env, DQ4_READSET_CACHE=str(u / 'readset'), DQ4_STATES_CACHE=str(u / 'states'), DQ4_BUILD_CACHE=str(u))


def unit_slots(checks, root, prefix='guard-unit'):
    """단위 캐시 enc-cache 자리: [{'prefix', 'dir'}]. 하위 조각 여럿을 함께 도는 단위는 몫마다 자리 하나(같은 폴더로
    되살리고, 저장도 몫마다 해 다른 묶음으로 도는 실행이 몫 이름으로 찾는다). 키 접두어는 「쉼표 없음」 이라는
    actions/cache 규칙을 지킨다."""
    out = []
    for c in checks:
        d = str(unit_dir(c, root))
        out += [{'prefix': f'{prefix}-{c["name"]}{tag}', 'dir': d} for tag in record_tags(c)]
    return out


def group_parts(checks):
    """같은 검사의 하위 조각(같은 조각에 든 것)을 단위 하나로 묶는다(첫 자리, 번호 차례)."""
    out, seen = [], {}
    for c in checks:
        if not c.get('part'):
            out.append(c)
        elif c['name'] in seen:
            g = out[seen[c['name']]]
            out[seen[c['name']]] = with_parts(g, part_ks(g) + part_ks(c))
        else:
            seen[c['name']] = len(out)
            out.append(c)
    return out


def all_passed(check, root=ROOT):
    """하위 조각 모두 같은 입력의 통과 기록이 있는가(--run 이 건너뛸 단위)."""
    key = input_key(check, root)
    return bool(key) and all((cache_dir() / f'{check["name"]}{t}-{key[:24]}.json').is_file() for t in record_tags(check))


def run_check(check, timeout, logs, no_cache=False, env=None):
    """검사 하나를 돌린다. (결과 'passed'|'failed'|'skipped', 본문 괄호 안 글). env 를 주면 그 환경으로 돈다(배포 관문이
    모든 단계에 같은 환경을 쓸 때).

    입력 키가 빗나가도 롬을 빌드하는 검사(split_built)는 빌드 단계만 먼저 돌린다. 만든 파일·.py 밖 입력이 같고, 지난
    통과 때 검사 단계가 실행한 함수의 코드와 연 파일·본 폴더가 모두 같으면(entry_holds) 검사 단계를 건너뛴다. 검사
    단계는 tools/guardtrace 를 PYTHONPATH 앞에 두고 돌려 그것들을 적는다. 롬이 그대로이고 검사가 실행하지 않는
    함수만 고친 PR 이 실행 검사를 다시 돌지 않게 한다."""
    name, run = check['name'], check['run']
    if PLACEHOLDER.search(run):
        return 'skipped', '명령에 <…> 자리가 있어 직접 돌릴 것'
    unset = unset_env(check.get('needs', []))
    if unset:
        return 'skipped', f'설정 안 된 환경 변수 {", ".join(unset)}'
    key = input_key(check, ROOT)
    hits = {t: cache_dir() / f'{name}{t}-{key[:24]}.json' for t in record_tags(check)} if key else {}
    done = [] if no_cache else [t for t, f in hits.items() if f.is_file()]
    if hits and len(done) == len(hits):
        old = json.loads(hits[done[0]].read_text(encoding='utf-8'))
        return 'passed', f'캐시: 같은 입력으로 {old["when"]} 통과, {old["detail"]}'
    # 단위 캐시 폴더는 조각이 고른 묶음 그대로(CI 가 그 이름으로 되살렸다), 도는 몫만 통과 기록이 없는 것으로 좁힌다
    unit = check
    if done:
        check = with_parts(check, [k for k, t in zip(part_ks(check), record_tags(check)) if t not in done])
        hits = {t: f for t, f in hits.items() if t not in done}
    tag = part_tag(check)
    # 같은 크기로 같은 초 안에 고친 원본은 옛 .pyc 를 그대로 쓰므로, 단계마다 빈 곳에서 새로 컴파일한다
    pycaches = []

    def fresh(e):
        pycaches.append(Path(tempfile.mkdtemp(prefix=f'guard-{name}-pyc-')))
        return dict(e, PYTHONPYCACHEPREFIX=str(pycaches[-1]))
    try:
        log = logs / f'{name}{tag}.log'
        shown = log.relative_to(ROOT) if log.is_relative_to(ROOT) else log
        log.write_text('', encoding='utf-8')
        env = dict(env or (no_cache_env(logs) if no_cache else os.environ))
        if no_cache:
            env.pop('DQ4_UNIT_CACHE', None)
        env = unit_env(unit, env)
        env.pop(PART_ENV, None)
        if check.get('part'):
            env[PART_ENV] = '{}/{}'.format(','.join(map(str, part_ks(check))), check['part'][1])
        t0 = time.time()
        parts = None if no_cache or key is None or shadowed() else split_built(check)
        built = reads = None
        if parts:
            code = spawn(parts[0], log, timeout, fresh(env))
            if code is None:
                return 'failed', f'{timeout}초 안에 끝나지 않음, 로그 {shown}'
            if code:
                return 'failed', f'종료 코드 {code}, 로그 {shown}'
            built = input_key(check, ROOT, built=True)
            olds = [built and built_hit(name + t, built, ROOT) for t in hits]
            old = all(olds) and olds[0]
            if old:
                return 'passed', f'캐시: 빌드 결과와 검사 코드가 같아 {old["when"]} 통과, {old["detail"]}'
            reads = logs / f'{name}{tag}.reads'
            reads.unlink(missing_ok=True)
            Path(f'{reads}.broken').unlink(missing_ok=True)
        # 검사 출력 폴더는 검사 단계를 돌릴 때만 비운다(건너뛰면 지난 출력이 남는다)
        for d in out_dirs(run):
            # 빌드 단계가 만든 폴더면(앞 단계 --out) 지우지 않는다
            if not any(under(d, m) or under(m, d) for m in made_paths(run)):
                shutil.rmtree(ROOT / d, ignore_errors=True)
        if parts:
            base = env
            env = dict(base, GUARD_READS=str(reads), GUARD_READS_ROOT=str(ROOT),
                       GUARD_READS_SKIP=os.pathsep.join(str(ROOT / d) for d in out_dirs(run)
                                                        if not any(under(d, m) or under(m, d) for m in made_paths(run))),
                       PYTHONPATH=os.pathsep.join(x for x in (str(TRACER), base.get('PYTHONPATH')) if x))
        code = spawn(parts[1] if parts else run, log, timeout - (time.time() - t0), fresh(env))
        if code is None:
            return 'failed', f'{timeout}초 안에 끝나지 않음, 로그 {shown}'
        secs = round(time.time() - t0)
        if code:
            return 'failed', f'종료 코드 {code}, 로그 {shown}'
        m = re.search(r'--rom\s+(\S+)', run.split('&&')[-1])
        rom = m[1] if m else None
        detail = f'{secs}초' + (f', 롬 SHA-1 {hashlib.sha1((ROOT / rom).read_bytes()).hexdigest()[:8]}'
                               if rom and (ROOT / rom).is_file() else '')
        # 도는 동안 입력이 바뀌었으면 그 결과는 어느 입력의 것인지 모르므로 캐시하지 않는다
        if key is not None and input_key(check, ROOT) == key:
            for f in hits.values():
                write_atomic(f, json.dumps({'when': time.strftime('%Y-%m-%d %H:%M'), 'detail': detail},
                                           ensure_ascii=False))
            trace = (read_trace(reads, CHECK_STAGE.match(parts[1])['script'])
                     if reads and not Path(f'{reads}.broken').exists() else None)
            entry = trace and trace_entry(trace, ROOT)
            # 검사 단계가 빌드 결과를 고쳐 썼으면 키가 달라져 남기지 않는다
            if built and entry and input_key(check, ROOT, built=True) == built:
                for t in hits:
                    save_built(name + t, built, detail, entry)
        return 'passed', detail
    finally:
        for d in pycaches:
            shutil.rmtree(d, ignore_errors=True)


SHARD_TIMES = Path(__file__).resolve().parent / 'guardshard-times.json'
SECONDS = re.compile(r'^(\d+)초')


def parse_shard(text):
    """'k/n' → (k, n). 1 ≤ k ≤ n."""
    m = re.fullmatch(r'(\d+)/(\d+)', text or '')
    if not m or not 1 <= int(m[1]) <= int(m[2]):
        raise ValueError(f'--shard 는 k/n(1 ≤ k ≤ n): {text!r}')
    return int(m[1]), int(m[2])


def load_shard_times(path=SHARD_TIMES):
    try:
        data = json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}
    return {k: float(v) for k, v in data.items() if isinstance(v, (int, float))} if isinstance(data, dict) else {}


def cached_seconds(folder=None):
    """검사 결과 캐시(work/cache/guards)에 남은 통과 시간 {이름: 초}. 같은 이름이 여럿이면 가장 늦게 쓴 것."""
    try:
        folder = Path(folder) if folder else cache_dir()
    except subprocess.CalledProcessError:
        return {}
    out = {}
    for f in sorted(folder.glob('*.json'), key=lambda p: p.stat().st_mtime) if folder.is_dir() else []:
        try:
            m = SECONDS.match(json.loads(f.read_text(encoding='utf-8')).get('detail', ''))
        except (OSError, ValueError, AttributeError):
            continue
        name = f.stem.rsplit('-', 1)[0]
        if m and NAME.match(name):
            out[name] = float(m[1])
    return out


def shard_weights(checks, times=None, cached=None):
    """검사마다 무게(초). 시간 파일 → 이 체크아웃의 캐시 → 아는 시간의 평균(아무것도 모르면 모두 1)."""
    times = load_shard_times() if times is None else times
    cached = cached_seconds() if cached is None else cached
    known = {c['name']: times.get(c['name'], cached.get(c['name'])) for c in checks}
    seen = [v for v in known.values() if v is not None]
    default = sum(seen) / len(seen) if seen else 1.0
    return {n: (v if v is not None else default) for n, v in known.items()}


def split_weights(checks):
    """--shard 로 나눌 때의 무게: 커밋에 든 시간 파일만 본다(없는 검사는 그 평균). CI 조각 잡마다 같은 목록을 따로 나누므로,
    잡마다 되살린 결과 캐시(cached_seconds)를 섞으면 잡마다 나눔이 달라 한 검사가 두 조각에서 돌거나 빠진다."""
    return shard_weights(checks, cached={})


def part_tag(check):
    """하위 조각·스윕 시드 단위의 이름 꼬리(캐시·로그 파일 이름). 「~」 는 NAME 에 없어 cached_seconds 가 검사 이름으로
    읽지 않는다."""
    if check.get('tag'):
        return check['tag']
    return '~{}of{}'.format(','.join(map(str, part_ks(check))), check['part'][1]) if check.get('part') else ''


def unit_name(check):
    """조각에 넣는 단위의 이름: 검사 이름, 하위 조각이면 「이름 k/n」, 스윕 시드 단위면 「이름 시드 s」."""
    if check.get('seed_unit'):
        return f'{check["name"]} 시드 {check["seeds"][0]}'
    return ('{} {}/{}'.format(check['name'], ','.join(map(str, part_ks(check))), check['part'][1]) if check.get('part')
            else check['name'])


def expand_parts(checks):
    """parts 가 있는 검사를 하위 조각 parts 개로 펼친다(차례 유지). 몫의 경계를 조각 수에 묶지 않아야 하위 조각마다
    남긴 통과 기록·단위 캐시가 조각 수가 다른 실행에서도 맞는다."""
    out = []
    for c in checks:
        p = c.get('parts', 1)
        out += [dict(c, part=(k, p)) for k in range(1, p + 1)] if p > 1 else [c]
    return out


def unit_weight(check, weights):
    """단위 무게: 검사(스윕) 시간을 하위 조각·시드 단위 수로 나눈 것."""
    of = check['part'][1] if check.get('part') else check['seed_unit'][1] if check.get('seed_unit') else 1
    return weights.get(check['name'], 1.0) / of


def held_weight(check, weights):
    """group_parts 로 묶은 단위의 무게: 든 하위 조각마다 unit_weight."""
    return unit_weight(check, weights) * len(part_ks(check) or (1,))


def shard_part(checks, k, n, weights):
    """checks(expand_parts 로 펼친 것)를 무게가 고르게 n 조각으로 나눠 k 번째(1부터) 조각을 원래 차례대로. 긴 것부터
    가장 가벼운 조각에 넣고 같은 무게는 이름 차례라, 같은 입력이면 같은 결과다. 같은 검사의 하위 조각은 그 검사가 아직
    없는 조각 가운데 가장 가벼운 곳에 넣는다(한 조각에 둘이 들면 run_many 가 한 프로세스로 묶는다). 조각을 모두 모으면
    checks 와 같다."""
    loads, owner, held = [0.0] * n, {}, [set() for _ in range(n)]
    for c in sorted(checks, key=lambda c: (-unit_weight(c, weights), unit_name(c))):
        free = [i for i in range(n) if c['name'] not in held[i]] or list(range(n))
        i = min(free, key=lambda i: (loads[i], i))
        owner[unit_name(c)] = i
        held[i].add(c['name'])
        loads[i] += unit_weight(c, weights)
    return [c for c in checks if owner[unit_name(c)] == k - 1]


def merge_parts(rows):
    """조각 결과 행 가운데 하위 조각 행(part)을 검사 하나로 합친다(처음 나온 자리). 하위 조각이 1..n 모두 있고 모두
    통과해야 통과, 하나라도 실패면 실패, 빠졌거나 돌지 않은 것이 있으면 돌리지 않음. 통과 글은 「합친 초(하위 조각 n개,
    가장 긴 것 m초)」 에 첫 하위 조각의 나머지 글(롬 SHA-1 등)."""
    out, parts = [], {}
    for r in rows:
        if not r.get('part'):
            out.append(r)
            continue
        if r['name'] not in parts:
            parts[r['name']] = []
            out.append(r['name'])
        parts[r['name']].append(r)
    merged = []
    for r in out:
        if not isinstance(r, str):
            merged.append(r)
            continue
        got = sorted(parts[r], key=lambda x: x['part'][0])
        n = got[0]['part'][1]
        have = {x['part'][0] for x in got if x['part'][1] == n}
        missing = sorted(set(range(1, n + 1)) - have)
        failed = [x for x in got if x['status'] == 'failed']

        def unit(x):
            return f'시드 {",".join(map(str, x["seeds"]))}' if x.get('seeds') else f'하위 조각 {x["part"][0]}/{n}'
        if failed:
            status = 'failed'
            detail = '; '.join(f'{unit(x)}: {x["detail"]}' for x in failed)
        elif missing or len(got) != n or any(x['status'] != 'passed' for x in got):
            status = 'skipped'
            detail = (f'하위 조각 {missing} 결과 없음' if missing else
                      '; '.join(f'{unit(x)}: {x["detail"]}' for x in got if x['status'] != 'passed')
                      or f'하위 조각 수가 맞지 않음 {[x["part"] for x in got]}')
        else:
            status = 'passed'
            secs = [int(m[1]) if (m := SECONDS.match(x['detail'])) else 0 for x in got]
            rest = re.sub(r'^\d+초,?\s*', '', got[0]['detail'])
            cached = sum(x['detail'].startswith('캐시') for x in got)
            detail = (f'{sum(secs)}초(하위 조각 {n}개, 가장 긴 것 {max(secs)}초)' if not cached else
                      f'하위 조각 {n}개 가운데 {cached}개 캐시') + (f', {rest}' if rest and not cached else '')
        if status == 'passed' and got[0].get('judge'):
            status, detail = judge_merged(got[0]['judge'], got, detail)
        merged.append({'name': r, 'file': got[0]['file'], 'status': status, 'detail': detail,
                       'parts': [{'part': x['part'], 'status': x['status'], 'detail': x['detail']}
                                 | ({'seeds': x['seeds']} if x.get('seeds') else {}) for x in got]}
                      | ({'sweep': True} if got[0].get('sweep') else {}))
    return merged


def load_judge(spec, root=ROOT):
    """'경로.py:함수' → 그 함수. 경로는 저장소 상대(트랙 도구)."""
    import importlib.util
    path, _, func = spec.partition(':')
    path = Path(root) / path
    mod = importlib.util.spec_from_file_location(f'_judge_{path.stem}', path)
    module = importlib.util.module_from_spec(mod)
    mod.loader.exec_module(module)
    return getattr(module, func)


def judge_merged(spec, got, detail, load=None):
    """하위 조각이 모두 통과한 스윕을 몫들의 원자료("data")를 모아 spec 함수로 판정한다. (결과, 글). 원자료가 없는
    몫이 캐시 통과뿐이면 통과로 두고 「합친 판정 건너뜀」 을 붙인다(캐시를 쓴 연습 실행). 그 밖에 원자료가 빠지면
    돌리지 않음: 몫마다 통과해도 합친 판정 없이 통과로 칠 수 없다."""
    missing = [x for x in got if x.get('data') is None]
    if missing:
        if all(x['detail'].startswith('캐시') for x in missing):
            return 'passed', f'{detail}, 합친 판정 건너뜀(캐시 통과 몫)'
        return 'skipped', f'하위 조각 {[x["part"][0] for x in missing]} 원자료(sweep_data) 없음'
    problems = (load or load_judge)(spec)([x['data'] for x in got])
    if problems:
        return 'failed', f'합친 판정: {"; ".join(problems)}'
    return 'passed', f'{detail}, 합친 판정 통과'


SWEEP_FIELDS = {'name': str, 'why': str, 'run': str}
SWEEP_OPTIONAL = {'seeds': int, 'needs': list, 'parts': int, 'judge': str}
SWEEP_SEEDS_N = 16
# CI 조각 잡이 rom 잡에서 받아 두는 1장 출하 롬(guard-shards.yml 「Put the ship ROMs in place」)
SWEEP_ROM = 'work/ch1/dq4-ch1-full.sfc'


def load_sweeps(files, read=lambda f: (ROOT / f).read_text(encoding='utf-8')):
    """(스윕 목록, 문제 목록). 트랙마다 release.toml 의 [[sweep]], 각 {'file': release.toml, **항목}."""
    out, problems = [], []
    for toml in sorted(f for f in files if PurePosixPath(f).name == 'release.toml'):
        try:
            data = tomllib.loads(read(toml))
        except tomllib.TOMLDecodeError as e:
            problems.append(f'{toml}: TOML 오류 {e}')
            continue
        for i, item in enumerate(data.get('sweep', [])):
            where = f'{toml} sweep[{i}]'
            bad = [k for k, kind in SWEEP_FIELDS.items() if not isinstance(item.get(k), kind)]
            bad += [k for k, kind in SWEEP_OPTIONAL.items() if k in item and not isinstance(item[k], kind)]
            bad += [k for k in item if k not in SWEEP_FIELDS and k not in SWEEP_OPTIONAL]
            if bad:
                problems.append(f'{where}: 칸이 없거나 꼴이 틀림 {bad}')
                continue
            if not NAME.match(item['name']):
                problems.append(f'{where}: 이름 {item["name"]!r} 은 소문자·숫자·- 만')
            missing = [k for k in ('{rom}', '{out}', '{seeds}') if k not in item['run']]
            if missing:
                problems.append(f'{where}: run 에 {missing} 가 없음')
            if 'parts' in item and not 2 <= item['parts'] <= PARTS_MAX:
                problems.append(f'{where}: parts 는 2~{PARTS_MAX} 정수')
            if 'judge' in item and ('parts' not in item or not re.fullmatch(r'[\w./-]+\.py:\w+', item['judge'])):
                problems.append(f'{where}: judge 는 parts 스윕에만, 「경로.py:함수」')
            out.append({'file': toml, **item})
    names = [s['name'] for s in out]
    problems += [f'스윕 이름 {n} 이 둘 이상' for n in sorted({n for n in names if names.count(n) > 1})]
    return out, problems


def seed_list(n, failed=()):
    """시드 0 부터 n 개, 이어서 실패 시드(겹침 없이 차례 유지)."""
    out = list(range(n))
    for s in failed:
        if s not in out:
            out.append(s)
    return out


def failed_seeds(sweep, root=ROOT):
    """그 트랙 폴더 seeds.json 에서 그 스윕 이름의 실패 시드. 없으면 빈 목록."""
    path = Path(root) / PurePosixPath(sweep['file']).parent / 'seeds.json'
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding='utf-8'))
    return [int(e['seed']) for e in data.get(sweep['name'], [])]


def sweep_units(sweeps, seeds_n=SWEEP_SEEDS_N, rom=SWEEP_ROM, root=ROOT):
    """스윕을 조각에 넣을 검사 단위로. 시드 단위는 tag(로그·통과 기록 이름 꼬리)와 seed_unit (i, n)을 단다. parts 스윕은
    parts 를 그대로 두어 expand_parts 가 하위 조각으로 펼친다(DQ4_GUARD_PART, 도구가 시드 말고 장면 등으로 나눔)."""
    out = []
    for s in sweeps:
        seeds = seed_list(s.get('seeds', seeds_n), failed_seeds(s, root))
        base = {'name': s['name'], 'file': s['file'], 'why': s['why'], 'needs': s.get('needs', ['rom']), 'paths': [],
                'own_paths': [], 'sweep': True}
        if s.get('parts'):
            out.append(dict(base, run=s['run'].format(rom=rom, out=f'work/sweep/{s["name"]}',
                                                      seeds=','.join(map(str, seeds))),
                            parts=s['parts'], seeds_all=seeds) | ({'judge': s['judge']} if s.get('judge') else {}))
            continue
        for i, seed in enumerate(seeds, 1):
            out.append(dict(base, run=s['run'].format(rom=rom, out=f'work/sweep/{s["name"]}/seed-{seed}', seeds=seed),
                            seeds=[seed], seed_unit=(i, len(seeds)), tag=f'~seed{seed}'))
    return out


FAILED_SEED = re.compile(r'^\{.*\}$')


def failed_seeds_in(text):
    """검사 출력의 JSON 줄 가운데 "seed" 가 정수이고 "status" 가 failed 인 것의 시드(차례, 겹침 없음)."""
    out = []
    for line in text.splitlines():
        line = line.strip()
        if not FAILED_SEED.match(line):
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict) and row.get('status') == 'failed' and type(row.get('seed')) is int:
            out.append(row['seed'])
    return list(dict.fromkeys(out))


def split_local(checks, names):
    """(돌릴 검사, 로컬 몫). needs 에 names 가운데 하나라도 든 검사가 로컬 몫이다."""
    names = set(names)
    local = [c for c in checks if names & set(c.get('needs', []))]
    return [c for c in checks if c not in local], local


def record_times(reports, path=SHARD_TIMES):
    """보고서들의 통과한 검사 시간으로 시간 파일을 고쳐 쓴다. 고친 이름 수."""
    times = load_shard_times(path)
    n, rows = 0, []
    for report in reports:
        data = json.loads(Path(report).read_text(encoding='utf-8'))
        rows += (data.get('stages', {}).get('guards', {}).get('rows') if 'stages' in data else data.get('rows')) or []
    # 하위 조각 행은 조각 결과 파일 여럿에 흩어져 있어 모두 모은 뒤 합친다(검사 하나의 시간 = 하위 조각 합)
    for r in merge_parts(rows):
        m = SECONDS.match(r.get('detail', ''))
        if r.get('status') == 'passed' and m and not r['detail'].startswith('캐시'):
            times[r['name']] = float(m[1])
            n += 1
    write_atomic(Path(path), json.dumps(dict(sorted(times.items())), indent=1, ensure_ascii=False) + '\n')
    return n


def result_json(done, local, shard=None, cached=False):
    """--json 결과: 커밋, 조각, 캐시를 썼는가, 돈 검사의 결과, 로컬 몫(뺀 검사)."""
    return {'commit': git('rev-parse', 'HEAD').strip(), 'shard': list(shard) if shard else None, 'cached': cached,
            'rows': [{'name': c['name'], 'file': c['file'], 'status': s, 'detail': d}
                     | ({'part': list(c['part'])} if c.get('part') else {})
                     | ({'part': list(c['seed_unit']), 'seeds': c['seeds']} if c.get('seed_unit') else {})
                     | ({'sweep': True} if c.get('sweep') else {})
                     | ({'judge': c['judge'], 'data': unit_data(c, s, d)} if c.get('judge') else {}) for c, s, d in done],
            'local': [{'name': c['name'], 'file': c['file'], 'needs': c.get('needs', [])} for c in local]}


def unit_log(check, logs=None):
    """검사 단위의 로그 파일(guards.py 가 쓴 것)."""
    folder = Path(logs or ROOT / 'work' / 'guards')
    log = folder / f'{check["name"]}{part_tag(check)}.log'
    if not log.is_file() and check.get('part'):
        # 한 조각에 든 하위 조각 여럿은 한 프로세스로 돌아 로그가 「이름~1,3ofn」 하나다(run_many 가 결과만 몫마다 나눔)
        n, ks = check['part'][1], set(part_ks(check))
        pat = re.compile(rf'{re.escape(check["name"])}~([\d,]+)of{n}\.log')
        log = next((f for f in sorted(folder.glob(f'{check["name"]}~*of{n}.log'))
                    if (m := pat.fullmatch(f.name)) and ks <= {int(x) for x in m[1].split(',') if x}), log)
    return log


SWEEP_DATA = '{"sweep_data":'


def sweep_data_in(text):
    """검사 출력의 마지막 {"sweep_data": …} 줄의 값. 없거나 못 읽으면 None."""
    for line in reversed(text.splitlines()):
        if line.startswith(SWEEP_DATA):
            try:
                return json.loads(line)['sweep_data']
            except (ValueError, KeyError):
                return None
    return None


def unit_data(check, status, detail='', logs=None):
    """judge 가 있는 스윕 하위 조각이 이번에 돌아 통과했으면 로그의 원자료. 그 밖에는 None(캐시 통과면 로그가 지난
    실행의 것일 수 있다)."""
    if status != 'passed' or not check.get('judge') or detail.startswith('캐시'):
        return None
    try:
        return sweep_data_in(unit_log(check, logs).read_text(encoding='utf-8', errors='replace'))
    except OSError:
        return None


def sweep_failure(check, status, detail, logs=None):
    """시드를 합쳐 도는 스윕 단위(parts)가 실패하면 로그의 JSON 줄에서 실패한 시드를 읽어 글에 붙인다."""
    if status != 'failed' or not check.get('sweep') or check.get('seed_unit'):
        return detail
    log = unit_log(check, logs)
    try:
        seeds = failed_seeds_in(log.read_text(encoding='utf-8', errors='replace'))
    except OSError:
        return detail
    return f'{detail}, 실패 시드 {",".join(map(str, seeds))}' if seeds else f'{detail}, 실패 시드를 로그에서 못 읽음'


def run_all(hit, parallel, timeout, no_cache=False, out=None, local=(), shard=None):
    """걸린 검사를 parallel 개씩 함께 돌리고 본문 결과 줄을 찍는다. out 이 있으면 결과를 JSON 으로. 모두 통과하면 0."""
    done = [(c, s, sweep_failure(c, s, d)) for c, s, d in run_many(hit, parallel, timeout, no_cache)]
    if out:
        write_atomic(Path(out), json.dumps(result_json(done, local, shard, not no_cache), ensure_ascii=False, indent=1)
                     + '\n')
    print('\nPR 본문 결과 줄:')
    for c, status, detail in done:
        mark, word = ('x', '통과') if status == 'passed' else (' ', '실패' if status == 'failed' else '돌리지 않음')
        print(f'- [{mark}] {unit_name(c)}: {word} ({detail})')
    return 0 if all(s == 'passed' for _, s, _ in done) else 1


def work_paths(run):
    """명령에 나오는 work/… 경로(읽든 쓰든)."""
    return set(re.findall(r'(?<![\w/])(?:\$PWD/)?(work/[^\s;&|]+)', run))


def build_conflict(a, b, places=None):
    """두 빌드 검사가 함께 돌면 안 되는가: 한쪽이 만드는 것(built_paths)을 다른 쪽 명령이 읽거나 쓰거나 만든다."""
    def touches(x, y):
        return any(under(t, m) or under(m, t) for m in built_paths(x['run'], places or {}) for t in work_paths(y['run']))
    return touches(a, b) or touches(b, a)


def run_order(hit, builders, places, weights):
    """(띄울 차례, 앞서 끝나야 하는 것). 빌드 검사는 명단 차례로 먼저, 나머지는 무게(held_weight)가 큰 것부터. 빌드 검사는
    앞의 빌드 검사 가운데 부딪치는 것(build_conflict)이 끝나야, 나머지 검사는 자기가 읽거나 쓰는 것을 만드는 빌드 검사가
    끝나야 돈다. 부딪치지 않는 검사는 빌드 검사가 도는 동안에도 돈다."""
    rest = [c for c in hit if c not in builders]
    order = builders + sorted(rest, key=lambda c: (-held_weight(c, weights), rest.index(c)))
    after = [{j for j in range(min(i, len(builders))) if build_conflict(c, order[j], places)}
             for i, c in enumerate(order)]
    return order, after


def run_many(hit, parallel, timeout, no_cache=False, logs=None, env=None):
    """검사를 parallel 개씩 함께 돌린다. [(검사, 'passed'|'failed'|'skipped', 글)]."""
    logs = logs or ROOT / 'work' / 'guards'
    logs.mkdir(parents=True, exist_ok=True)
    if no_cache and env is None:
        shutil.rmtree(logs / 'states', ignore_errors=True)
    shown = logs.relative_to(ROOT) if logs.is_relative_to(ROOT) else logs
    hit = group_parts(hit)
    print(f'검사 {len(hit)}개를 {parallel}개씩 돌림(로그 {shown})', flush=True)
    root = (env or os.environ).get('DQ4_UNIT_CACHE')
    if root and not no_cache:
        # 되살린 단위 캐시의 출발 상태를 모아 둔다(아직 아무 검사도 돌지 않아 반쯤 쓴 파일이 없다)
        for d in sorted(Path(root).iterdir()) if Path(root).is_dir() else ():
            if d.name != '_pool':
                share_states(d / 'states', Path(root) / '_pool' / 'states')

    def one(c):
        status, detail = run_check(c, timeout, logs, no_cache, env)
        print(f'  {unit_name(c)}: {status} ({detail})', flush=True)
        if root and not no_cache:
            share_states(unit_dir(c, root) / 'states', Path(root) / '_pool' / 'states')
        return c, status, detail
    # 롬을 스스로 빌드하는 검사는 다른 검사가 읽는 롬을 다시 쓸 수 있어, 그것을 읽거나 만드는 검사보다 먼저 돌린다
    # (run_order). CI 조각에서 미리 만든 출하 롬으로 바뀌는 빌드 단계는 폴더를 미리 맞춰 두면 아무것도 쓰지 않으므로
    # 빌드로 치지 않는다. 빌드 검사가 그 폴더에 무언가 더하거나 고칠 수 있어, 끝나면 그 폴더를 다시 맞춘다(그 폴더를
    # 건드리는 검사는 모두 그 빌드 검사를 기다리므로 그동안 도는 것이 없다)
    places = prebuilt_places(hit, env or os.environ)
    builders = [c for c in hit if built_paths(c['run'], places)]
    order, after = run_order(hit, builders, places, shard_weights(hit))
    pool = concurrent.futures.ThreadPoolExecutor(max(1, parallel))
    try:
        place_prebuilt(places)
        results, running, left = {}, {}, list(range(len(order)))
        while left or running:
            for i in [i for i in left if after[i] <= results.keys()][:max(1, parallel) - len(running)]:
                left.remove(i)
                running[pool.submit(one, order[i])] = i
            finished, _ = concurrent.futures.wait(running, return_when=concurrent.futures.FIRST_COMPLETED)
            for f in finished:
                i = running.pop(f)
                results[i] = f.result()
                made = built_paths(order[i]['run'], places)
                place_prebuilt({p: d for p, d in places.items() if any(under(m, p) or under(p, m) for m in made)})
        at = {id(c): i for i, c in enumerate(order)}
        done = [results[at[id(c)]] for c in builders + [c for c in hit if c not in builders]]
    except BaseException:
        # Ctrl-C 등: 도는 검사 그룹을 모두 끄고 남은 일을 버린다
        for proc in list(RUNNING):
            kill_group(proc)
        pool.shutdown(wait=False, cancel_futures=True)
        raise
    pool.shutdown()
    # 결과 행은 하위 조각마다(merge_parts·통과 기록과 같은 단위)
    rows = []
    for c, s, d in done:
        rows += [(with_parts(c, [k]), s, d) for k in part_ks(c)] or [(c, s, d)]
    return rows


def full_files(checks, changed):
    """바뀐 파일 가운데 어느 트랙의 [full] paths 에 맞는 것."""
    pats = {p for c in checks for p in c.get('full_paths', ())}
    return [f for f in changed if any(matches(f, p) for p in pats)]


def triggered(checks, changed, edited=(), full=False):
    """걸린 검사. 전체 모드인 검사는 모두 걸린다: full 이거나 바뀐 파일이 그 트랙의 [full] paths 에 맞을 때. 그 밖에는
    바뀐 파일이 검사 자신의 paths(묶음 빼고)에 맞거나 이름이 edited 에 든 pr 등급 검사."""
    def whole(c):
        # [full] 이 켜는 전체 모드는 PR 등급만(release 등급은 main 머지 뒤와 배포 관문이 돈다). 본문 `가드: 전체`·--full 은 명시라 모두
        return full or (c.get('tier', 'pr') != 'release'
                        and any(matches(f, p) for f in changed for p in c.get('full_paths', ())))

    def hits(c):
        pats = c.get('own_paths', c.get('paths', []))
        return c.get('tier', 'pr') != 'release' and (
            c['name'] in edited or any(matches(f, p) for f in changed for p in pats))
    return [c for c in checks if whole(c) or hits(c)]


def pending(checks, changed, edited=()):
    """PR 에서 걸리지 않았지만 배포 관문이 지킬 검사: 묶음까지 보면 바뀐 파일에 맞거나 이름이 edited 에 든 것."""
    return [c for c in checks if c['name'] in edited or any(matches(f, p) for f in changed for p in c.get('paths', []))]


# PR 본문에서 [full] 판정과 상관없이 전체 모드로 넓히는 줄
FULL_LINE = re.compile(r'^[ \t]*가드[ \t]*:[ \t]*전체[ \t]*$', re.M)
# PR 본문에서 걸린 목록에 검사를 더하는 줄
EXTRA_LINE = re.compile(r'^[ \t]*가드[ \t]*:[ \t]*더함[ \t]+(\S.*?)[ \t]*$', re.M)


def extra_names(body):
    """본문의 `가드: 더함 a, b` 줄들의 이름(차례 유지, 중복 뺌)."""
    return list(dict.fromkeys(n for m in EXTRA_LINE.finditer(body or '') for n in re.split(r'[\s,]+', m[1]) if n))


def ci_local_needs(path=SHARDS_WORKFLOW):
    """CI 조각이 로컬 몫으로 빼는 needs 이름들(guard-shards.yml 맨 위 env 의 LOCAL_NEEDS). 못 읽으면 빈 것."""
    try:
        m = re.search(r'^  LOCAL_NEEDS:\s*(\S*)\s*$', Path(path).read_text(encoding='utf-8'), re.M)
    except OSError:
        return []
    return [n for n in (m[1] if m else '').split(',') if n]


def pr_shards(checks, weights, per=PR_SHARD_SECONDS, most=PR_SHARDS_MAX):
    """PR 가드 잡의 조각 수: 무게 합을 per 초씩 나눈 올림, 1 ~ min(단위 수, most). 단위는 검사, parts 가 있으면 그
    하위 조각 수만큼."""
    if not checks:
        return 0
    total = sum(weights.get(c['name'], 1.0) for c in checks)
    units = sum(c.get('parts', 1) for c in checks)
    return max(1, min(units, most, -(-int(total) // per)))


def edited_checks(base_text, head_text):
    """검사 목록 두 판에서 run·needs 가 다르거나 새로 생긴 검사 이름. 판은 글 하나 또는 한 트랙 파일들의 글 목록
    (guards.toml 과 조각: 검사를 다른 파일로 옮기기만 한 것은 바뀐 것이 아니다). 읽지 못하는 글은 빈 것으로 본다."""
    def blocks(texts):
        out = {}
        for text in [texts] if isinstance(texts, str) else texts:
            try:
                data = tomllib.loads(text) if text else {}
            except tomllib.TOMLDecodeError:
                continue
            items = data.get('check', [])
            out.update({c['name']: tuple(repr(c.get(k)) for k in RESULT_FIELDS)
                        for c in (items if isinstance(items, list) else [])
                        if isinstance(c, dict) and isinstance(c.get('name'), str)})
        return out
    old, new = blocks(base_text), blocks(head_text)
    return {name for name, v in new.items() if old.get(name) != v}


def edited_between(changed, show, listing, old, new):
    """changed 가운데 검사 목록 파일이 있는 트랙마다 old·new 두 판의 트랙 전체(guards.toml 과 조각)를 견줘 run·needs 가
    바뀐 검사. show(rev, path) 는 그 판의 글(없으면 ''), listing(rev, folder) 는 그 판에서 그 폴더의 파일 경로들."""
    names = set()
    for toml in sorted({t for t in map(track_of, changed) if t}):
        folder = str(PurePosixPath(toml).parent / FRAGMENTS)

        def texts(rev):
            frags = sorted(f for f in listing(rev, folder) if fragment_owner(f) == toml)
            return [show(rev, f) for f in [toml, *frags]]
        names |= edited_checks(texts(old), texts(new))
    return names


def edited_in(base, head, changed):
    """base…head 에서 검사 목록 파일이 바뀐 트랙마다 run·needs 가 바뀐 검사(merge-base 의 판과 견줌)."""
    mb = git('merge-base', base, head).strip()

    def show(rev, f):
        r = subprocess.run(['git', 'show', f'{rev}:{f}'], cwd=ROOT, capture_output=True, text=True)
        return r.stdout if r.returncode == 0 else ''

    def listing(rev, folder):
        r = subprocess.run(['git', 'ls-tree', '--name-only', f'{rev}', f'{folder}/'], cwd=ROOT, capture_output=True,
                           text=True)
        return r.stdout.split() if r.returncode == 0 else []
    return edited_between(changed, show, listing, mb, head)


# 「통과」 다음은 줄 끝·괄호·대시만(「통과하지 못함」「통과 못 함」을 통과로 읽지 않게)
PASSED = re.compile(r'^통과(?:[ \t]*$|[ \t]*[(（]|[ \t]+[—-])')
NOT_APPLICABLE = re.compile(r'^해당 없음[ \t]*[—-][ \t]*\S')


def body_problems(checks, body):
    """걸린 검사마다 `- [x] 이름: 통과 …` 또는 `- [x] 이름: 해당 없음 — 이유` 줄이 있어야 한다."""
    problems = []
    for c in checks:
        line = re.compile(rf'^[ \t]*[-*][ \t]*\[[xX]\][ \t]*`?{re.escape(c["name"])}`?[ \t]*:[ \t]*(\S.*)$', re.M)
        found = [m[1].strip() for m in line.finditer(body)]
        if not found:
            problems.append(f'{c["name"]}: PR 본문에 결과 줄이 없음 (`- [x] {c["name"]}: 통과 …`)')
        elif not all(PASSED.match(r) or NOT_APPLICABLE.match(r) for r in found):
            problems.append(f'{c["name"]}: 결과는 「통과 (…)」 또는 「해당 없음 — 이유」만: {found}')
    return problems


def pick(checks, names):
    """이름으로 고른 검사(--only). 모르는 이름은 문제로."""
    want = [n for n in names.split(',') if n]
    by = {c['name']: c for c in checks}
    return [by[n] for n in want if n in by], [f'--only: 모르는 검사 {n}' for n in want if n not in by]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--base', help='이 커밋과 HEAD 사이에 바뀐 파일로 걸리는 검사를 고른다')
    ap.add_argument('--head', default='HEAD', help='바뀐 파일을 볼 끝 커밋(CI 는 PR 의 head SHA: 머지 커밋이면 그 뒤 main 변경까지 걸림)')
    ap.add_argument('--pr-body', type=Path, help='PR 본문 파일. 걸린 검사의 결과 줄을 확인한다')
    ap.add_argument('--run', action='store_true', help='걸린 검사를 돌린다(--base 와 함께)')
    ap.add_argument('--parallel', type=int, default=None,
                    help='--run 에서 함께 돌릴 검사 수(기본 HEADLESS_SLOTS 의 자리 수. 검사마다 안에서 다시 병렬)')
    ap.add_argument('--timeout', type=int, default=1800, help='--run 에서 검사 하나의 시간 제한(초)')
    ap.add_argument('--no-cache', action='store_true', help='--run 에서 검사 캐시·장면 캐시를 모두 끄고 전부 돌린다(배포 관문)')
    ap.add_argument('--full', action='store_true',
                    help='[full] 에 걸리지 않아도 전체 모드로 고른다(PR 본문의 `가드: 전체` 와 같음)')
    ap.add_argument('--only', metavar='이름,…',
                    help='--run 에서 걸린 검사 대신 이 검사들만 돌린다(tools/guards.py 를 바꾼 PR 의 대표 가드 셋)')
    ap.add_argument('--all', action='store_true', help='--base 없이 등급·묶음과 상관없이 모든 검사를 고른다(배포 관문)')
    ap.add_argument('--shard', metavar='k/n', help='--all 로 고른 검사를 시간이 고르게 n 조각으로 나눠 k 번째만')
    ap.add_argument('--sweeps', action='store_true',
                    help='--all 에 트랙마다 release.toml 의 시드 스윕(sweep_units)을 더한다(배포 관문 CI)')
    ap.add_argument('--exclude-needs', metavar='이름,…', default='',
                    help='--all 에서 needs 에 이 이름이 든 검사를 빼 「로컬 몫」 으로 찍는다(리눅스 CI 에서 결과가 다른 검사의 macos 등)')
    ap.add_argument('--json', type=Path, help='--all --run 결과(커밋·조각·결과·로컬 몫)를 이 파일에')
    ap.add_argument('--unit-slots', type=Path, metavar='OUT',
                    help='--all --shard 로 고른 단위의 캐시 자리(JSON [{prefix, dir}], 무거운 것부터 --slots 개)를 OUT 에. '
                         '폴더 뿌리는 DQ4_UNIT_CACHE')
    ap.add_argument('--slots', type=int, default=UNIT_SLOTS, help=f'--unit-slots 자리 수(기본 {UNIT_SLOTS})')
    ap.add_argument('--pending-only', action='store_true',
                    help='--unit-slots 에서 하위 조각 모두 같은 입력의 통과 기록이 있는 단위를 뺀다(돌 것만 되살림)')
    ap.add_argument('--plan', type=Path, metavar='OUT',
                    help='--base 에서 걸린 검사를 CI 몫·로컬 몫으로 나눠 guards=·local=·shards= 줄을 OUT 에 더한다')
    ap.add_argument('--with-release', action='store_true',
                    help='--plan 에서 바뀐 파일로 걸린 검사에 release 등급 검사 전부를 더한다(main push: 머지 뒤 긴 검사)')
    ap.add_argument('--local-only', action='store_true',
                    help='--pr-body 에서 로컬 몫(LOCAL_NEEDS)만 결과 줄을 요구한다(CI 몫은 CI 가드 잡이 판정)')
    ap.add_argument('--record-times', type=Path, nargs='+', metavar='보고서',
                    help='보고서의 검사 시간으로 guardshard-times.json 을 고쳐 쓴다')
    args = ap.parse_args()
    if args.record_times:
        print(f'시간 {record_times(args.record_times)}개를 {SHARD_TIMES.name} 에 적음')
        return 0
    if not args.all and (args.shard or args.exclude_needs or args.json or args.sweeps):
        ap.error('--shard·--exclude-needs·--json·--sweeps 는 --all 과 함께')
    if args.with_release and not args.plan:
        ap.error('--with-release 는 --plan 과 함께')
    if not args.base and (args.plan or args.local_only):
        ap.error('--plan·--local-only 는 --base 와 함께')
    files = tracked()
    checks, problems = load(files)
    if args.all:
        if args.base or args.pr_body:
            ap.error('--all 은 --base·--pr-body 와 함께 쓰지 않는다')
        try:
            shard = parse_shard(args.shard) if args.shard else None
        except ValueError as e:
            ap.error(str(e))
        hit = checks
        if args.only:
            hit, bad = pick(checks, args.only)
            problems += bad
        if args.sweeps:
            sweeps, bad = load_sweeps(files)
            problems += bad
            taken = {c['name'] for c in checks}
            problems += [f'{s["file"]}: 스윕 이름 {s["name"]} 이 검사 이름과 같음' for s in sweeps if s['name'] in taken]
            hit = hit + sweep_units(sweeps)
        hit, local = split_local(hit, [n for n in args.exclude_needs.split(',') if n])
        if shard:
            hit = shard_part(expand_parts(hit), *shard, split_weights(hit))
        print(f'고른 검사 {len(hit)}개' + (f'(조각 {shard[0]}/{shard[1]})' if shard else '') + ': '
              + (', '.join(map(unit_name, hit)) or '없음'))
        if local:
            print(f'로컬 몫 {len(local)}개(needs 에 {args.exclude_needs}): ' + ', '.join(c['name'] for c in local))
        if args.unit_slots and not problems:
            root = os.environ.get('DQ4_UNIT_CACHE')
            if not root:
                ap.error('--unit-slots 는 DQ4_UNIT_CACHE 가 있어야 한다')
            units = group_parts(hit)
            if args.pending_only:
                units = [c for c in units if not all_passed(c)]
            weights = shard_weights(units)
            units.sort(key=lambda c: (-held_weight(c, weights), unit_name(c)))
            slots = unit_slots(units, root)
            if len(slots) > args.slots:
                print(f'::warning::단위 캐시 자리 {len(slots)}개 가운데 무거운 {args.slots}개만: '
                      + ', '.join(s['prefix'] for s in slots[args.slots:]))
            write_atomic(args.unit_slots, json.dumps(slots[:args.slots], ensure_ascii=False) + '\n')
            print(f'단위 캐시 자리 {min(len(slots), args.slots)}개: ' + (', '.join(s['prefix'] for s in slots[:args.slots])
                                                                     or '없음'))
        if args.run and not problems:
            parallel = args.parallel or headless_slots.limit() or os.cpu_count() or 2
            return run_all(hit, parallel, args.timeout, args.no_cache, args.json, local, shard)
    elif args.base:
        changed = [f for f in git('diff', '--name-only', f'{args.base}...{args.head}').splitlines() if f]
        edited = edited_in(args.base, args.head, changed)
        body = args.pr_body.read_text(encoding='utf-8') if args.pr_body else ''
        full = args.full or bool(FULL_LINE.search(body))
        hit = triggered(checks, changed, edited, full)
        extra, bad = pick(checks, ','.join(extra_names(body)))
        problems += [p.replace('--only', '`가드: 더함`') for p in bad]
        hit += [c for c in extra if c not in hit]
        auto = full_files(checks, changed)
        if auto:
            print(f'전체 모드: {", ".join(auto)}')
        if full:
            print('전체 모드: ' + ('--full' if args.full else '본문의 `가드: 전체`'))
        if hit:
            print('이 변경이 건드리는 실행 검사(돌리고 PR 본문에 결과 줄):')
            for c in hit:
                print(f'- {c["name"]} ({c["file"]}): {c["why"]}\n    {c["run"]}')
                if c.get('needs'):
                    print(f'    필요: {", ".join(c["needs"])}')
                    unset = unset_env(c['needs'])
                    if unset:
                        print(f'    ⚠ 지금 설정 안 된 환경 변수: {", ".join(unset)} (export 한 뒤 돌릴 것)')
                print(f'    본문 줄: - [x] {c["name"]}: 통과 …')
        else:
            print('걸리는 실행 검사 없음')
        later = [c for c in pending(checks, changed, edited) if c not in hit]
        if later:
            print('main 머지 뒤·배포 관문에서(이 PR 에서는 돌리지 않음. 더 넓게 돌리려면 본문에 `가드: 전체` 를 쓰고 --full 로):')
            for c in later:
                why = 'release 등급' if c.get('tier', 'pr') == 'release' else '묶음으로만 맞음'
                print(f'- {c["name"]} ({why})')
        if args.with_release:
            hit += [c for c in checks if c.get('tier', 'pr') == 'release' and c not in hit]
        ci, local = split_local(hit, ci_local_needs())
        if args.plan:
            n = pr_shards(ci, shard_weights(ci), most=MAIN_SHARDS_MAX if args.with_release else PR_SHARDS_MAX)
            with args.plan.open('a', encoding='utf-8') as f:
                f.write(f'guards={",".join(c["name"] for c in ci)}\nlocal={",".join(c["name"] for c in local)}\n'
                        f'shards={n}\n')
            print(f'CI 몫 {len(ci)}개(조각 {n}), 로컬 몫 {len(local)}개'
                  + (f': {", ".join(c["name"] for c in local)}' if local else ''))
        # --plan 과 함께 준 본문은 넓히는 줄(`가드: 전체`·`가드: 더함`)만 읽는다
        if args.pr_body and not args.plan:
            problems += body_problems(local if args.local_only else hit, body)
        if args.only:
            hit, bad = pick(checks, args.only)
            problems += bad
            print('--only 로 돌릴 검사: ' + ', '.join(c['name'] for c in hit))
        if args.run and hit and not problems:
            parallel = args.parallel or headless_slots.limit() or os.cpu_count() or 2
            return run_all(hit, parallel, args.timeout, args.no_cache)
    elif args.pr_body or args.run or args.only:
        ap.error('--pr-body·--run·--only 는 --base 와 함께')
    for p in problems:
        print(f'오류: {p}')
    print(f'가드 {len(checks)}개, 문제 {len(problems)}개')
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main())
