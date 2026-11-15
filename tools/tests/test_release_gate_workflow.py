"""배포 관문 워크플로가 시크릿·롬을 내보내지 않는 꼴인지 지킨다.

release-gate.yml(손으로만)이 롬 묶음 시크릿을 guard-shards.yml(workflow_call 전용)에 넘기고, 그 안에서 composite
action ci-roms 가 묶음을 푼다. PR·예약 실행에서 돌거나, 롬이 artifact·캐시로 새거나, 시크릿이 로그에 찍히면 안 된다.
의존성에 YAML 파서가 없어 들여쓰기로 읽는다(이 저장소 워크플로의 꼴: 잡은 2칸, 단계는 6칸 `- `).
"""
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
import ci_artifact_check  # noqa: E402

WORKFLOWS = ROOT / '.github' / 'workflows'
GATE = WORKFLOWS / 'release-gate.yml'
WORKFLOW = WORKFLOWS / 'guard-shards.yml'
ACTION = ROOT / '.github' / 'actions' / 'ci-roms' / 'action.yml'
SETUP = ROOT / 'tools' / 'ci_gate_setup.sh'
SECRET_VARS = ('CI_ROM_AGE_KEY', 'CI_ROM_TOKEN', 'GH_TOKEN')
BAD_TRIGGERS = ('pull_request', 'pull_request_target', 'schedule', 'push', 'workflow_run', 'issue_comment')


def top_block(text, key):
    """맨 왼쪽 `key:` 아래 줄들(다음 맨 왼쪽 키 앞까지)."""
    out, inside = [], False
    for line in text.splitlines():
        if re.match(r'^\S', line):
            inside = line.split(':', 1)[0].strip().strip('"\'') == key
            if inside and line.split(':', 1)[1].strip():
                out.append(line.split(':', 1)[1].strip())
            continue
        if inside:
            out.append(line)
    return out


def jobs(text):
    """{잡 이름: [단계 글, …]}."""
    out, job, step = {}, None, None
    for line in top_block(text, 'jobs'):
        m = re.match(r'^  ([A-Za-z0-9_-]+):\s*$', line)
        if m:
            job, step = m[1], None
            out[job] = []
            continue
        if job is None:
            continue
        if re.match(r'^      - ', line):
            out[job].append(line + '\n')
            step = len(out[job]) - 1
        elif step is not None and (line.startswith('        ') or not line.strip()):
            out[job][step] += line + '\n'
        else:
            step = None
    return out


def triggers(text):
    return {m[1] for line in top_block(text, 'on') if (m := re.match(r'^  ([A-Za-z_]+):', line))}


def run_texts(step):
    """단계의 run: 글(한 줄이든 | 블록이든)."""
    m = re.search(r'^\s*(?:- )?run:\s*(\|)?(.*)$', step, re.M)
    if not m:
        return ''
    if not m[1]:
        return m[2]
    body = step[m.end():]
    return '\n'.join(line for line in body.splitlines() if line.startswith('          ') or not line.strip())


def prints_secret(line):
    """시크릿 환경 변수를 표준 출력·GitHub 출력 파일로 내는 echo·printf 줄인가."""
    if not re.search(r'\b(echo|printf)\b', line):
        return False
    if not any(re.search(rf'\$\{{?{v}\b', line) for v in SECRET_VARS):
        return False
    target = re.search(r'>+\s*"?([^"\s)]+)', line)
    return not target or 'GITHUB_' in target[1]


class ReleaseGateWorkflowTest(unittest.TestCase):
    def setUp(self):
        self.text = WORKFLOW.read_text(encoding='utf-8')
        self.jobs = jobs(self.text)

    def test_parser_sees_the_jobs(self):
        self.assertEqual(set(self.jobs), {'build', 'shard', 'report'})
        self.assertTrue(all(self.jobs.values()))

    def test_gate_is_manual_only(self):
        gate = GATE.read_text(encoding='utf-8')
        self.assertEqual(triggers(gate), {'workflow_dispatch'})
        for bad in BAD_TRIGGERS:
            self.assertNotRegex('\n'.join(top_block(gate, 'on')), rf'\b{bad}\b')

    def test_shards_workflow_is_call_only(self):
        self.assertEqual(triggers(self.text), {'workflow_call'})

    def test_only_known_callers_pass_rom_secrets(self):
        """guard-shards.yml 을 부르는 워크플로는 release-gate.yml 뿐이고, 시크릿은 이름을 대어 넘긴다(inherit 금지).
        PR 에서 부르는 워크플로를 더할 때는 이 테스트에 같은 저장소 브랜치 조건 검사를 함께 더한다."""
        callers = sorted(p.name for p in WORKFLOWS.glob('*.y*ml') if 'guard-shards.yml' in p.read_text(encoding='utf-8')
                         and p != WORKFLOW)
        self.assertEqual(callers, ['release-gate.yml'])
        gate = GATE.read_text(encoding='utf-8')
        self.assertNotRegex(gate, r'secrets:\s*inherit')
        self.assertRegex(gate, r'uses:\s*\./\.github/workflows/guard-shards\.yml')
        self.assertRegex(gate, r'mode:\s*release\b')

    def test_permissions_read_only(self):
        for text in (self.text, GATE.read_text(encoding='utf-8')):
            self.assertEqual([x.strip() for x in top_block(text, 'permissions') if x.strip()], ['contents: read'])
            self.assertNotRegex(text, r':\s*write\b')

    def test_actions_pinned_to_commits(self):
        for f in (WORKFLOW, GATE, ACTION):
            for m in re.finditer(r'uses:\s*(\S+)', f.read_text(encoding='utf-8')):
                if m[1].startswith('./.github/'):
                    continue
                self.assertRegex(m[1], r'^[\w.-]+/[\w./-]+@[0-9a-f]{40}$', m[1])

    def test_roms_come_only_from_the_composite_action(self):
        uses = [s for steps in self.jobs.values() for s in steps if './.github/actions/ci-roms' in s]
        self.assertEqual(len(uses), sum('ci_artifact_check.py' in run_texts(s) for st in self.jobs.values() for s in st)
                         + 1, '롬을 받는 잡마다(빌드 잡 + 올리는 잡) ci-roms 를 쓴다')
        for f in (WORKFLOW, GATE):
            self.assertNotIn('ci_gate_setup.sh roms', f.read_text(encoding='utf-8'))
        action = ACTION.read_text(encoding='utf-8')
        self.assertIn('using: composite', action)
        self.assertIn('tools/ci_gate_setup.sh roms', action)

    def test_every_upload_is_checked_first(self):
        uploads = 0
        for name, steps in self.jobs.items():
            for i, step in enumerate(steps):
                if 'actions/upload-artifact@' not in step:
                    continue
                uploads += 1
                path = re.search(r'^\s+path:\s*(\S+)', step, re.M)[1]
                checks = [s for s in steps[:i] if 'tools/ci_artifact_check.py' in run_texts(s)
                          and re.search(rf'ci_artifact_check\.py\s+{re.escape(path)}\s', run_texts(s))]
                self.assertTrue(checks, f'{name}: {path} 를 올리기 전에 ci_artifact_check.py 가 없음')
                sid = re.search(r'^\s+id:\s*(\S+)', checks[-1], re.M)
                self.assertIsNotNone(sid, f'{name}: 검사 단계에 id 가 없음')
                cond = re.search(r'^\s+if:\s*(.+)$', step, re.M)
                self.assertIsNotNone(cond, f'{name}: 올리기 단계가 검사 결과를 보지 않음')
                self.assertIn(f"steps.{sid[1]}.outcome == 'success'", cond[1])
                self.assertNotRegex(path, r'(^|/)rom(/|$)')
        self.assertGreater(uploads, 0)

    def test_cache_never_holds_roms_or_builds(self):
        for steps in self.jobs.values():
            for step in steps:
                if 'actions/cache@' not in step:
                    continue
                paths = re.search(r'path:\s*\|\n((?:\s{12}.+\n)+)', step)
                for p in ([x.strip() for x in paths[1].splitlines()] if paths else [re.search(r'path:\s*(\S+)', step)[1]]):
                    self.assertTrue(p.startswith('${{ runner.temp }}/gate-tools/'), p)
                    self.assertNotRegex(p, r'(^|/)(rom|work|build)(/|$)|\.(sfc|smc|nes|nds|mss)$', p)

    def test_secrets_only_through_env_or_with(self):
        for name, steps in self.jobs.items():
            for step in steps:
                self.assertNotIn('secrets.', run_texts(step), f'{name}: run 안에서 시크릿을 바로 씀')
                self.assertNotRegex(run_texts(step), r'set\s+-[a-z]*x', f'{name}: set -x')
                for line in run_texts(step).splitlines():
                    self.assertFalse(prints_secret(line), f'{name}: 시크릿을 찍음: {line.strip()}')

    def test_setup_script_and_action_never_print_secrets(self):
        for f in (SETUP, ACTION):
            text = f.read_text(encoding='utf-8')
            self.assertNotRegex(text, r'(?m)^\s*set\s+-[a-z]*x')
            for line in text.splitlines():
                self.assertFalse(prints_secret(line), f'{f.name}: {line.strip()}')
        action = ACTION.read_text(encoding='utf-8')
        self.assertNotRegex(action, r'run:[^\n]*\$\{\{\s*inputs\.', 'action: 입력을 run 에 바로 끼움')
        for block in re.split(r'\n    - ', action):
            if 'run:' in block:
                self.assertNotIn('${{ inputs.', block.split('run:', 1)[1], 'action: 입력을 run 안에서 바로 씀')

    def test_setup_script_masks_the_key(self):
        self.assertIn('::add-mask::', SETUP.read_text(encoding='utf-8'))

    def test_secret_check_helper(self):
        self.assertTrue(prints_secret('echo "$CI_ROM_AGE_KEY"'))
        self.assertTrue(prints_secret('printf "%s" "${CI_ROM_TOKEN}"'))
        self.assertTrue(prints_secret('echo "k=$CI_ROM_TOKEN" >> "$GITHUB_ENV"'))
        self.assertFalse(prints_secret('printf "%s\\n" "$CI_ROM_AGE_KEY" >"$key"'))
        self.assertFalse(prints_secret('echo "::error::secret CI_ROM_TOKEN is not set"'))

    def test_guards_run_without_cache_and_local_needs_are_excluded(self):
        shard = ''.join(run_texts(s) for s in self.jobs['shard'])
        self.assertRegex(shard, r'guards\.py --all ("\$\{only\[@\]\}" )?--run --no-cache')
        self.assertIn('--exclude-needs "$LOCAL_NEEDS"', shard)
        self.assertRegex(self.text, r'LOCAL_NEEDS:\s*MESENCE,LIBDIR')

    def test_banned_suffixes_cover_rom_and_save_kinds(self):
        for ext in ('.sfc', '.smc', '.nes', '.nds', '.ml1', '.sav', '.mss', '.ips'):
            self.assertIn(ext, ci_artifact_check.BANNED)


if __name__ == '__main__':
    unittest.main()
